"""解決済みのWikipedia記事から、その記事に実際に使われている画像を取る。

キーワード検索をやめた理由。Commonsの検索は語義を区別しない。実測で
Archimedes -> 月のクレーター、Columbus -> ジョージア州コロンバス市、
Baghdad -> 1258年のバグダード陥落、が返ってきた。ナレーションと画が
食い違うのは、密度を上げた代償として受け入れられない種類の誤りになる。

記事側から引けば、記事の同一性が言語間リンクで固定されているので、
同名衝突が原理的に起きない。en.wikipedia.org/wiki/Archimedes に載っている
画像は、定義上アルキメデス本人のものになる。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .sources import Asset, _clean, _filepath_url, license_ok

# Wikimedia は実在の連絡先を求める。research@example.com のような
# 置き場所の文字列だと、APIは通っても実体の取得が403で弾かれる
# （実測で動画の取得が落ちた）。連絡先はリポジトリのURLにする。
UA = "youtube-research-automation/0.1 (https://github.com/finracofficial-cmd/youtube-research-automation)"
EN_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"

# 記事本文ではなく、ウィキの体裁として貼られている画像。題材と無関係。
_JUNK = re.compile(
    r"commons-logo|wiki.?letter|edit-clear|question.?book|ambox|disambig"
    r"|folder.hexagonal|text.document|padlock|wikidata|wikisource|wikiquote"
    r"|wiktionary|portal|blue.?pencil|magnify-clip|loudspeaker|speakerlink"
    r"|nuvola|crystal.?clear|merge-arrow|symbol.?(list|template|support)"
    r"|increase|decrease|steady|red.?pog|green.?pog|locator|^flag.of"
    r"|translation.?to|sound-icon|gnome-|oojs|mediawiki|searchtool"
    r"|cscr-|semi-protection|shackle|^p vip|featured|good.?article"
    r"|star\.svg|emblem-|information.?icon|stub|spoken.?wikipedia"
    r"|unbalanced|scales\.svg|globe|split-arrows|imbox|mbox",
    re.I)

# P31 の指す型がこれらの語を含むなら、個体ではなく抽象。
# 実測で Percentage が P31=parts-per notation / dimensionless unit で通った。
_ABSTRACT_TYPE = (
    "unit", "notation", "disambiguation", "metaclass", "class of",
    "list of", "template", "category", "concept", "quantity",
    "number format", "writing system", "aspect of",
    # 学問分野。台本が方法を語る場面で拾われる（考古学・地質学）
    "academic discipline", "academic major", "branch of science",
    "field of study", "field of work", "科学",
    # 活動・過程。名前ではなく振る舞いを指す（協力・観光・収集・再利用）
    "activity", "hobby", "gathering", "process", "travel",
    "economic sector", "industry", "occupation", "profession",
    # 集団・図形。画にしても題材を指さない（共同体・三角形・多角形）
    "social group", "group of humans", "cluster",
    "geometric shape", "plane figure", "polytope", "geometric figure",
)


# 直前の呼び出しからの最低間隔。連続で叩くと 429 が返り、その分だけ
# 記事から画を引けずに検索へ落ちる。待つ方が結果として速い。
_MIN_INTERVAL = 0.35
_last_call = 0.0


def _get(api: str, params: dict, retries: int = 5) -> dict | None:
    global _last_call
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()
    url = api + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503):
                time.sleep(2 ** a * 3)
                _last_call = time.monotonic()
                continue
            return None
        except Exception:  # noqa: BLE001
            time.sleep(2 ** a * 2)
    return None


def _claim_ids(claims: dict, prop: str) -> list[str]:
    out = []
    for st in claims.get(prop, []):
        dv = st.get("mainsnak", {}).get("datavalue")
        if dv and isinstance(dv.get("value"), dict):
            qid = dv["value"].get("id")
            if qid:
                out.append(qid)
    return out


def _qids(en_titles: list[str]) -> dict[str, str | None]:
    """英語版の見出しから Wikidata の項目IDをまとめて引く。

    Wikidata に見出しで直接問い合わせるとリダイレクトや大文字小文字の
    違いで外れる（実測で "Nazca Lines" が引けなかった）。Wikipedia 側から
    引けば、リダイレクトを辿ったうえで正規の項目IDが返る。
    """
    out: dict[str, str | None] = {t: None for t in en_titles}
    for i in range(0, len(en_titles), 50):
        chunk = en_titles[i:i + 50]
        d = _get(EN_API, {"action": "query", "titles": "|".join(chunk),
                          "redirects": 1, "prop": "pageprops",
                          "ppprop": "wikibase_item"})
        if not d:
            continue
        q = d.get("query", {})
        back: dict[str, str] = {}
        for kind in ("normalized", "redirects"):
            for m in q.get(kind, []):
                back[m["to"]] = back.get(m["from"], m["from"])
        for page in (q.get("pages") or {}).values():
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                title = page.get("title", "")
                out[back.get(title, title)] = qid
        time.sleep(0.3)
    return out


def _entities(qids: list[str], props: str, lang: str | None = None) -> dict:
    """wbgetentities を50件ずつに割って引く。"""
    merged: dict = {}
    for i in range(0, len(qids), 50):
        params = {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                  "props": props}
        if lang:
            params["languages"] = lang
        d = _get(WD_API, params)
        merged.update((d or {}).get("entities") or {})
        time.sleep(0.3)
    return merged


# 題材そのものではなく、題材が言及される器。論文の掲載誌、所蔵する博物館、
# 発見地の国。記事の画像は器の画像（雑誌の表紙、建物、地図）になるので、
# 主題を指す語があるならそちらを先に使う。落とすのではなく順位を下げる。
_META_TYPE = (
    "journal", "newspaper", "magazine", "publisher", "periodical",
    "university", "institute", "college", "school", "academy",
    "museum", "library", "archive",
    "organization", "organisation", "society", "association", "foundation",
    "nonprofit", "non-profit", "company", "enterprise", "agency",
    "institution", "publisher", "publishing", "broadcaster", "network",
    "press", "media", "studio", "trust", "charity", "council", "committee",
    "union", "federation", "club", "business", "corporation",
    "country", "sovereign state", "state of", "province", "prefecture",
    "ocean", "sea", "continent", "region", "city", "capital",
)


# 画にできる具体物の型。除外リストで運用すると題材が変わるたびに漏れる
# （実測で Replica / Aerial photography / Life and death / Groundwater が
# 順に漏れ、ブガッティ・キャンプ場の空撮・静物画・地下水断面図が画面に出た）。
# 落とすべきものを数えるのではなく、通してよいものを数える。
# 通すのは「世界に実在し、写真に撮れる個物」。方法・媒体・分野・性質は通さない。
_CONCRETE_TYPE = (
    # 人
    "human", "deity", "legendary figure", "mythical",
    # 場所・地形
    "site", "city", "town", "village", "settlement", "island", "volcano",
    "mountain", "crater", "lake", "river", "desert", "plateau", "tell",
    "trench", "valley", "cave", "spring", "oasis", "peninsula", "cape",
    # 構造物
    "monument", "column", "palace", "castle", "temple", "church", "shrine",
    # 「building」単独は building material（建材）にも当たるので入れない
    "tower", "wall", "ruins", "cromlech", "henge", "tomb",
    "stele", "obelisk", "bridge", "aqueduct", "fortress", "pyramid",
    "landform", "geoglyph", "petroglyph",
    # 物
    "artefact", "artifact", "manuscript", "codex", "chart", "painting",
    "sculpture", "artwork", "book", "mechanism", "battery", "instrument",
    "vessel", "ship", "spacecraft", "clock", "calculator",
    # 生き物
    "taxon", "species", "breed",
    # 集団・時代
    "civilization", "culture", "empire", "historical country", "dynasty",
    "kingdom", "archaeological culture",
    # 出来事
    "battle", "war", "expedition", "earthquake", "eruption", "shipwreck",
)


def is_concrete(types: list[str]) -> bool:
    """写真に撮れる個物か。1つでも当たれば通す。"""
    return any(re.search(rf"\b{re.escape(w)}\b", t)
               for t in types for w in _CONCRETE_TYPE)


def entity_types(en_titles: list[str]) -> dict[str, dict]:
    """見出しごとに {"t": 型名, "c": クラスか} を返す。

    使えない語は型名が空リスト。"c" は P31（個体）ではなく P279（クラス）で
    判定が通ったことを示す。呼び出し側は可否・順位・扱いの差をこれで決める。
    """
    return _types_of(en_titles)


def is_meta(types: list[str]) -> bool:
    """題材そのものではなく、題材が言及される器か。

    1つでも当たれば器、とすると取りこぼす。Stonehenge の P31 には
    併設の展示施設に由来する history museum が混ざっていて、
    cromlech / monument / archaeological site / henge を押しのけて
    器と判定されていた。型が全部器のときだけ器とみなす。
    """
    return bool(types) and all(
        any(re.search(rf"\b{re.escape(w)}\b", t) for w in _META_TYPE) for t in types)


def are_entities(en_titles: list[str]) -> dict[str, bool]:
    """個体（人・物・場所・出来事）か、それとも一般概念かをまとめて判定する。

    Wikidataでは個体は P31（instance of）を持ち、クラスは P279（subclass of）
    を持つ。Washer (hardware) や Volcanic rock は P279 しか持たない。
    単位や記法は P31 を持ってしまうので、型のラベルで追加で落とす。

    1語ずつだと1語あたり3往復かかる。語の数だけ往復すると台本1本で
    百回を超え、レート制限の待ちが処理時間の大半になっていた。
    """
    return {t: bool(v["t"]) for t, v in _types_of(en_titles).items()}


def _types_of(en_titles: list[str]) -> dict[str, list[str]]:
    titles = sorted(set(en_titles))
    qid_of = _qids(titles)
    qids = sorted({q for q in qid_of.values() if q})
    claims_of = _entities(qids, "claims")

    # P31（individual）と P279（class）の両方を見る。
    # 画を検索で拾っていた頃はクラスを落としていた。語義を区別しない検索が
    # Volcanic rock に無関係な岩を返したためだが、記事から引く今は、
    # クラスの記事はそのクラスの画を返す（Moai の記事にはモアイが載っている）。
    # 落とし続けると、題材がクラスである回（巨石遺跡のモアイ、ドルメン、
    # メンヒル）で主題が丸ごと検索語から消える。
    p31_of: dict[str, list[str]] = {}
    class_of: dict[str, bool] = {}
    for qid in qids:
        c = (claims_of.get(qid) or {}).get("claims") or {}
        individual = _claim_ids(c, "P31")
        p31_of[qid] = individual or _claim_ids(c, "P279")
        class_of[qid] = not individual

    types = sorted({t for v in p31_of.values() for t in v[:6]})
    label_of = {}
    for qid, ent in _entities(types, "labels", "en").items():
        v = (ent.get("labels", {}).get("en") or {}).get("value")
        if v:
            label_of[qid] = v.lower()

    out: dict[str, dict] = {}
    for title in titles:
        qid = qid_of.get(title) or ""
        names = [label_of[t] for t in p31_of.get(qid, [])[:6] if t in label_of]
        # 抽象（単位・記法・曖昧さ回避）は個体として扱わない
        if not names or any(w in n for n in names for w in _ABSTRACT_TYPE):
            out[title] = {"t": [], "c": False}
        else:
            # 「type of tool」のように、型のラベル自体が種別を名乗る記事も
            # クラス扱いにする。P279 を持たなくても中身は分類の説明で、
            # 載っている画は任意の一例になる（Replica にブガッティ、
            # Quarry に適当な採石場）。
            klass = class_of.get(qid, False) or any(
                n.startswith(("type of", "class of", "form of", "genre of",
                              "kind of", "category of")) for n in names)
            out[title] = {"t": names, "c": klass}
    return out


def is_entity(en_title: str) -> bool:
    """個体か一般概念か。まとめて判定できるなら are_entities を使う。"""
    return are_entities([en_title])[en_title]


class Unreachable(RuntimeError):
    """APIに届かなかった。「記事に画が無い」とは区別する。

    レート制限や一時的な失敗を「画が無い」と同じ扱いにすると、黙って
    キーワード検索に落ちる。検索は語義を区別しないので、通信が詰まった
    ぶんだけ題材と食い違う画が増える。実測で、続けて3テーマ取得した
    3本目で要確認が23件に跳ねた。
    """


def _file_names(en_title: str, limit: int = 40) -> list[str] | None:
    """記事に出てくる順で画像のファイル名を返す。

    prop=images は名前順に並ぶ。parse は本文の出現順で返すので、
    冒頭の代表画像が先頭に来る。
    """
    d = _get(EN_API, {"action": "parse", "page": en_title,
                      "prop": "images", "redirects": 1})
    if d is None:
        return None
    names = (d.get("parse") or {}).get("images") or []
    out = []
    for raw in names:
        # parse はアンダースコア、Commons は空白で返す。先に揃えないと
        # 空白を含む除外規則（"p vip" など）に当たらない。
        n = raw.replace("_", " ")
        if _JUNK.search(n):
            continue
        # 読み上げ音声が記事画像として並ぶ。実測で Moai の記事から
        # En-moai.oga（記事の読み上げ）が素材として通った。音声と文書は
        # 落とす。動画は素材として使うので残す（VIDEO_EXT）。
        if n.lower().endswith((".ogg", ".oga", ".opus", ".flac", ".mp3",
                               ".mid", ".wav", ".pdf", ".djvu",
                               ".stl", ".xcf")):
            continue
        out.append(n)
        if len(out) >= limit:
            break
    return out


def _lead(en_title: str) -> str | None:
    d = _get(EN_API, {"action": "query", "titles": en_title,
                      "prop": "pageimages", "piprop": "name", "redirects": 1})
    for page in (((d or {}).get("query") or {}).get("pages") or {}).values():
        name = page.get("pageimage")
        if name:
            return name.replace("_", " ")
    return None


# 図解・地図・グラフ。題材として正しくても背景には向かない。英語の
# ラベルが敷き詰められていて字幕と競り合う。実測でナスカの回に
# 米地質調査所の地下水断面図が全画面で出た。
_DIAGRAM = re.compile(
    r"diagram|schematic|map|chart|graph|plot|figure|infographic|timeline"
    r"|cross.?section|illustration|drawing|sketch|blueprint|\bplan\b"
    r"|locator|location|relief|topograph|\.svg$", re.I)


# 実在の個人が写っている可能性が高いファイル名。題材が人物でないのに
# 顔写真を全画面に出すと、その人が題材に関係しているように見える。
# 実測で「National Geographic Society」の記事から、無関係な回に
# 特定個人の肖像が出た。ライセンスの問題ではなく、出してはいけない絵になる。
_PERSON = re.compile(
    r",\s*(a\s+)?(photographer|scientist|author|director|president|founder"
    r"|researcher|professor|journalist|explorer|artist|curator|archaeologist)"
    r"|portrait of|headshot|\bspeaking\b|\binterview\b|\bCEO\b|\bDr\.?\s"
    r"|\b(at the )?.{0,30}(awards|festival|conference|summit|gala|ceremony"
    r"|forum|expo|convention|symposium|meetup)\s*\d{0,4}\s*[-–—]\s*\w"
    r"|press conference|photo ?call|red carpet", re.I)


def _looks_like_a_person(title: str) -> bool:
    return bool(_PERSON.search(title))


# Commons に載っている動画。Chromium が再生できる形式だけ通す。
VIDEO_EXT = (".webm", ".ogv", ".mp4")
# 動画1本の上限。Commons には数百MBのものがあり、取得で実行時間を食う。
MAX_VIDEO_BYTES = 60 * 1024 * 1024
# 1カット（既定8秒）に満たない動画は使わない。描画側に繰り返しが無く、
# 足りない分は最後のコマで止まる。止まった動画は静止画より悪い。
MIN_VIDEO_SEC = 8.0


def is_video(title: str) -> bool:
    return title.lower().endswith(VIDEO_EXT)


def _is_diagram(title: str) -> bool:
    """図解らしさ。名前に出ない図解もあるので拡張子も見る。

    実測で Groundwater の代表画像が
    「Groundwater (aquifer, aquitard, 3 type wells).PNG」で、名前には
    図解と分かる語が無かった。写真はほぼ JPEG で入っているので、
    PNG/SVG/GIF は図解寄りとして後ろに回す。落とすのではなく順位を下げる。
    """
    if _DIAGRAM.search(title):
        return True
    if is_video(title):
        return False  # 動画は図解ではない。むしろ先に使いたい
    return not title.lower().endswith((".jpg", ".jpeg", ".webp"))


def _video_seconds(info: dict) -> float:
    """動画の長さ。imageinfo の metadata に length が入る。"""
    for item in info.get("metadata") or []:
        if str(item.get("name", "")).lower() in ("length", "playtime_seconds"):
            try:
                return float(item.get("value") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def page_images(en_title: str, *, limit: int = 6, width: int = 1920,
                people_ok: bool = False) -> list[Asset]:
    """記事に使われている画像を、ライセンスを確かめたうえで返す。

    people_ok が偽のとき、実在の個人が写っていそうな画は外す。題材が
    人物でないのに顔写真を全画面に出すと、その人が題材に関係している
    ように見える。ライセンスが許しても出してよい絵にはならない。
    """
    names = _file_names(en_title)
    if names is None:
        raise Unreachable(en_title)
    if not names:
        return []
    lead = _lead(en_title)
    d = _get(COMMONS_API, {
        "action": "query", "titles": "|".join("File:" + n for n in names[:40]),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mediatype|metadata", "iiurlwidth": width,
    })
    if d is None:
        raise Unreachable(en_title)
    by_name: dict[str, Asset] = {}
    for page in (((d.get("query") or {}).get("pages")) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = _clean(meta.get("LicenseShortName", {}).get("value"))
        if not license_ok(lic):
            continue
        filename = page.get("title", "").removeprefix("File:")
        w = int(info.get("width") or 0)
        h = int(info.get("height") or 0)
        if w and h and (w < 400 or h < 300):
            continue  # アイコン相当。全画面に引き伸ばすと破綻する
        if not people_ok and _looks_like_a_person(filename):
            continue
        video = is_video(filename)
        if video:
            # 動画は縮小版ではなく実体を落とす。thumburl は1枚目の静止画。
            if int(info.get("size") or 0) > MAX_VIDEO_BYTES:
                continue
            length = _video_seconds(info)
            if length and length < MIN_VIDEO_SEC:
                continue
        by_name[filename] = Asset(
            source="commons", title=filename,
            kind="video" if video else "image",
            durationSec=round(_video_seconds(info), 3) if video else 0.0,
            url=(info.get("url") if video
                 else (info.get("thumburl") or _filepath_url(filename, width))),
            page_url=info.get("descriptionurl", ""),
            license=lic,
            author=_clean(meta.get("Artist", {}).get("value")) or "不明",
            width=int(info.get("thumbwidth") or w or 0),
            height=int(info.get("thumbheight") or h or 0),
        )
    # 記事の出現順を保ち、代表画像を先頭に、図解を後ろに回す
    ordered = [by_name[n] for n in names if n in by_name]
    # 図解は代表画像であっても後ろ。写真のうちで代表画像を先頭にする
    ordered.sort(key=lambda a: (_is_diagram(a.title), a.title != lead))
    return ordered[:limit]
