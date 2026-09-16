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

from .wikipage import is_entity

UA = "youtube-research-automation/0.1 (research; contact: research@example.com)"
API = "https://ja.wikipedia.org/w/api.php"

# 固有名詞になりやすい形。「アンティキティラ島の機械」のような複合も拾う。
_CANDIDATE = re.compile(
    r"[ァ-ヶー]{3,}(?:・[ァ-ヶー]{2,})*(?:島|山|川|海|人)?の[一-龥]{2,6}"
    r"|[ァ-ヶー]{4,}(?:・[ァ-ヶー]{2,})*"
    r"|[一-龥]{2,6}(?:文書|手稿|写本|遺跡|神殿|地上絵|王朝|帝国|事件|鉄柱|電池|地図)"
    r"|[一-龥]{3,8}")

# 一般語。記事が存在してしまうので、先に落とす。
_STOP = {
    "動画", "説明", "解説", "検証", "内容", "場合", "部分", "程度", "以上", "以下",
    "現在", "当時", "最初", "最後", "今回", "結果", "理由", "意味", "可能", "必要",
    "問題", "方法", "状態", "関係", "世界", "日本", "人間", "時代", "年代",
    "チャンネル", "一次資料", "分解能", "考古学", "都市伝説", "研究者", "専門家",
    "可能性", "研究所", "大学", "博物館", "図書館", "報告書", "参考文献",
}

# 英語の見出しが一般概念だと、画像検索でも記事からでも題材と無関係な画が返る。
# 語を列挙して弾く運用は、新しい題材のたびに漏れる（実測で Channel /
# Primary source / Metre / Percentage / Washer (hardware) が順に漏れた）。
# Wikidata では個体は P31 を、クラスは P279 を持つので、そちらで判定する。


def _usable(en_title: str) -> bool:
    """画像に使える固有名詞か。Wikidataの構造で個体と一般概念を分ける。"""
    if "(disambiguation)" in en_title.lower():
        return False
    if len(en_title) < 3:
        return False
    return is_entity(en_title)


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


def english_title(ja_term: str) -> str | None:
    """日本語見出し -> 英語見出し。記事が無ければ None。"""
    d = _get({"action": "query", "prop": "langlinks", "lllang": "en",
              "titles": ja_term, "redirects": 1})
    if not d:
        return None
    for page in (d.get("query", {}).get("pages") or {}).values():
        if "missing" in page:
            return None
        links = page.get("langlinks")
        if links:
            return links[0]["*"]
    return None


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

    区間から候補語を長い順に試し、Wikipediaに記事があったものを採る。
    見つからない区間は空リストを返す（呼び出し側で前の語を引き継ぐ）。
    """
    cache: dict[str, str | None] = {}
    out: list[list[str]] = []
    for seg in segments:
        picked: list[str] = []
        for term in candidates(seg):
            if len(picked) >= per_segment:
                break
            if term not in cache:
                cache[term] = english_title(term)
                time.sleep(pause)
            en = cache[term]
            if en and _usable(en) and en not in picked:
                picked.append(en)
        out.append(picked)
    return out
