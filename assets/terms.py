"""台本から画の検索語を自動で作る。

素材が7枚しか無く、112カットで1枚を16回ずつ使い回していた。
台本には題材固有の語が時刻つきで並んでいるので、そこから検索語を起こす。

日本語のままでは所蔵機関のAPIを引けない。Wikipediaの言語間リンクを使うと、
「日本語版の記事が存在する」＝固有名詞である、という判定と、
英語版の見出し＝そのまま使える検索語、が同時に手に入る。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .wikipage import entity_types, is_entity, is_meta

UA = "youtube-research-automation/0.1 (research; contact: research@example.com)"

# 同じ語を何度も引き直さないための控え。題材を変えても語は重なるし、
# 検索語の選び方を試すたびに全部引き直していては手数が合わない。
CACHE = Path(__file__).resolve().parent.parent / ".cache" / "terms.json"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 壊れていたら作り直す
        return {"en": {}, "types": {}}


def _save_cache(c: dict) -> None:
    """書き戻す前にもう一度読んで混ぜる。

    題材ごとに並行して走らせると、後から書いた方が前の結果を消していた
    （実測でナスカの語が丸ごと消え、取得できた区間が30から3に見えた）。
    """
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    merged = _load_cache()
    for key in ("en", "types"):
        merged.setdefault(key, {}).update(c.get(key, {}))
    CACHE.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
API = "https://ja.wikipedia.org/w/api.php"

# 固有名詞になりやすい形。「アンティキティラ島の機械」のような複合も拾う。
_CANDIDATE = re.compile(
    # 中黒で繋ぐ名前は前半が2文字のことがある。{3,} を要求すると
    # 「ピリ・レイスの地図」を「レイスの地図」としか拾えない。
    r"(?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{3,})"
    r"(?:島|山|川|海|人|語|族)?の[一-龥]{2,8}"
    # 「コソ加工物」のようなカタカナ＋漢字の複合
    r"|(?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{2,})[一-龥]{2,6}"
    r"|[一-龥]{2,8}(?:文書|手稿|写本|遺跡|神殿|地上絵|王朝|帝国|事件|鉄柱|電池|地図|加工物)"
    r"|(?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{4,})"
    r"|[一-龥]{3,8}")

# 一般語。記事が存在してしまうので、先に落とす。
_STOP = {
    "動画", "説明", "解説", "検証", "内容", "場合", "部分", "程度", "以上", "以下",
    "現在", "当時", "最初", "最後", "今回", "結果", "理由", "意味", "可能", "必要",
    "問題", "方法", "状態", "関係", "世界", "日本", "人間", "時代", "年代",
    "チャンネル", "一次資料", "分解能", "考古学", "都市伝説", "研究者", "専門家",
    "可能性", "研究所", "大学", "博物館", "図書館", "報告書", "参考文献",
    # 暦の表記。記事はあるが題材ではない。実測で「紀元前」が
    # Ante Christum natum として全区間に配られた。
    "紀元前", "西暦", "世紀", "年代", "今世紀", "前世紀",
}

# 英語の見出しが一般概念だと、画像検索でも記事からでも題材と無関係な画が返る。
# 語を列挙して弾く運用は、新しい題材のたびに漏れる（実測で Channel /
# Primary source / Metre / Percentage / Washer (hardware) が順に漏れた）。
# Wikidata では個体は P31 を、クラスは P279 を持つので、そちらで判定する。


def _plausible(en_title: str) -> bool:
    """通信する前に落とせるもの。曖昧さ回避と短すぎる見出し。"""
    return "(disambiguation)" not in en_title.lower() and len(en_title) >= 3


def _usable(en_title: str) -> bool:
    """画像に使える固有名詞か。Wikidataの構造で個体と一般概念を分ける。"""
    return _plausible(en_title) and is_entity(en_title)


def _get(params: dict, retries: int = 3) -> dict | None:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.loads(urllib.request.urlopen(req, timeout=45).read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                time.sleep(2 ** a * 2); continue
            return None
        except Exception:  # noqa: BLE001
            time.sleep(2 ** a)
    return None


def english_titles(ja_terms: list[str]) -> dict[str, str | None]:
    """日本語見出しをまとめて英語見出しに直す。

    1語ずつ引くと、候補語の数だけ往復が要る。実測で1区間あたり数十秒かかり、
    台本1本の処理が1時間を超えた。APIは50件までまとめて受けるので、
    語の数ではなくバッチ数で効く形にする。

    リダイレクトと正規化で見出しが変わるため、問い合わせた語に戻す対応表を
    作ってから結果を引き当てる。
    """
    out: dict[str, str | None] = {t: None for t in ja_terms}
    for i in range(0, len(ja_terms), 50):
        chunk = ja_terms[i:i + 50]
        d = _get({"action": "query", "prop": "langlinks", "lllang": "en",
                  "titles": "|".join(chunk), "redirects": 1, "lllimit": "max"})
        if not d:
            continue
        q = d.get("query", {})
        back: dict[str, str] = {}
        for kind in ("normalized", "redirects"):
            for m in q.get(kind, []):
                back[m["to"]] = back.get(m["from"], m["from"])
        for page in (q.get("pages") or {}).values():
            links = page.get("langlinks")
            if "missing" in page or not links:
                continue
            title = page.get("title", "")
            out[back.get(title, title)] = links[0]["*"]
        time.sleep(0.3)
    return out


def english_title(ja_term: str) -> str | None:
    """日本語見出し -> 英語見出し。記事が無ければ None。"""
    return english_titles([ja_term])[ja_term]


def candidates(text: str) -> list[str]:
    """固有名詞になりそうな語を、長いものを優先して返す。"""
    found: list[str] = []
    for m in _CANDIDATE.finditer(text):
        t = m.group()
        if t in _STOP or len(t) < 3:
            continue
        found.append(t)
    # 長い語を先に試す。「アンティキティラ島の機械」を「アンティキティラ」より優先
    uniq = sorted(set(found), key=len, reverse=True)
    return uniq


def queries_for_segments(segments: list[str], *, per_segment: int = 1,
                         pause: float = 0.3) -> list[list[str]]:
    """区間ごとに、英語の検索語を作る。

    長い語から試すだけでは、どの区間にも出る背景語が各区間を占めてしまう
    （実測で「紀元前」が全区間に配られた）。その区間にしか出ない語を優先する。
    画は区間ごとに変わってほしいので、欲しいのは長さではなく固有性になる。

    先に全候補を解決してから選ぶ。区間ごとに上位から試して打ち切る形だと、
    記事の無い複合語が候補の上位を埋めたときに、その下にある使える語まで
    諦めてしまう（実測で取得できた区間が17から7に落ちた）。
    問い合わせはまとめて投げるので、全部解決しても往復は数回で済む。
    """
    per_seg = [candidates(seg) for seg in segments]
    wanted = sorted({t for terms in per_seg for t in terms})
    cache = _load_cache()

    fresh = [t for t in wanted if t not in cache["en"]]
    print(f"候補語 {len(wanted)}語（うち未取得 {len(fresh)}語）を英訳…", flush=True)
    cache["en"].update({k: v for k, v in english_titles(fresh).items()})
    en_of = {t: cache["en"].get(t) for t in wanted}

    resolved = sorted({e for e in en_of.values() if e and _plausible(e)})
    need = [e for e in resolved if e not in cache["types"]]
    print(f"英語版があった {len(resolved)}語（うち未判定 {len(need)}語）を判定…", flush=True)
    cache["types"].update(entity_types(need))
    _save_cache(cache)
    types = {e: cache["types"].get(e) or [] for e in resolved}
    usable = {ja: en for ja, en in en_of.items() if en and types.get(en)}
    meta = {ja for ja, en in usable.items() if is_meta(types[en])}
    print(f"個体だったのは {len(set(usable.values()))}語"
          f"（うち器が {len({usable[j] for j in meta})}語）", flush=True)

    # 使える語だけで出現区間数を数える。使えない語の分布は関係ない
    df: dict[str, int] = {}
    for terms in per_seg:
        for t in {t for t in terms if t in usable}:
            df[t] = df.get(t, 0) + 1
    n = max(1, len(segments))

    out: list[list[str]] = []
    for terms in per_seg:
        # 半分以上の区間に出る語は背景。区間の画を分ける役に立たない
        # 器（掲載誌・所蔵館・国）は採らない。台本の本文では主題が代名詞で
        # 受けられ、名前は主張の頭にしか出ない。器を採ると、その区間だけ
        # 主題から離れた画に差し替わる（実測で本文の途中にネイチャー誌の
        # 表紙が出た）。語が無い区間として返し、前の主題を引き継がせる。
        ranked = sorted({t for t in terms
                         if t in usable and t not in meta and df[t] <= max(1, n // 2)},
                        key=lambda t: (df[t], -len(t)))
        picked: list[str] = []
        for t in ranked:
            en = usable[t]
            if en not in picked:
                picked.append(en)
            if len(picked) >= per_segment:
                break
        out.append(picked)
    return out
