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

UA = "youtube-research-automation/0.1 (research; contact: research@example.com)"
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
    r"|star\.svg|emblem-|information.?icon|stub|spoken.?wikipedia",
    re.I)

# P31 の指す型がこれらの語を含むなら、個体ではなく抽象。
# 実測で Percentage が P31=parts-per notation / dimensionless unit で通った。
_ABSTRACT_TYPE = (
    "unit", "notation", "disambiguation", "metaclass", "class of",
    "list of", "template", "category", "concept", "quantity",
    "number format", "writing system", "aspect of",
)


def _get(api: str, params: dict, retries: int = 5) -> dict | None:
    url = api + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503):
                time.sleep(2 ** a * 3)
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


def is_entity(en_title: str) -> bool:
    """個体（人・物・場所・出来事）か、それとも一般概念か。

    Wikidataでは個体は P31（instance of）を持ち、クラスは P279（subclass of）
    を持つ。Washer (hardware) や Volcanic rock は P279 しか持たない。
    単位や記法は P31 を持ってしまうので、型のラベルで追加で落とす。
    """
    d = _get(WD_API, {"action": "wbgetentities", "sites": "enwiki",
                      "titles": en_title, "props": "claims"})
    if not d:
        return False
    ents = [e for e in (d.get("entities") or {}).values() if "claims" in e]
    if not ents:
        return False
    claims = ents[0]["claims"]
    p31 = _claim_ids(claims, "P31")
    if not p31 or _claim_ids(claims, "P279"):
        return False
    lab = _get(WD_API, {"action": "wbgetentities", "ids": "|".join(p31[:6]),
                        "props": "labels", "languages": "en"})
    names = []
    for ent in ((lab or {}).get("entities") or {}).values():
        v = (ent.get("labels", {}).get("en") or {}).get("value")
        if v:
            names.append(v.lower())
    if not names:
        return True
    return not any(w in n for n in names for w in _ABSTRACT_TYPE)


def _file_names(en_title: str, limit: int = 40) -> list[str]:
    """記事に出てくる順で画像のファイル名を返す。

    prop=images は名前順に並ぶ。parse は本文の出現順で返すので、
    冒頭の代表画像が先頭に来る。
    """
    d = _get(EN_API, {"action": "parse", "page": en_title,
                      "prop": "images", "redirects": 1})
    names = ((d or {}).get("parse") or {}).get("images") or []
    out = []
    for n in names:
        if _JUNK.search(n):
            continue
        if n.lower().endswith((".ogg", ".ogv", ".webm", ".mid", ".wav", ".pdf")):
            continue
        # parse はアンダースコア、Commons は空白で返す。ここで揃えないと
        # 後段の突き合わせが複数語の名前で全部外れ、UI画像だけが残る。
        out.append(n.replace("_", " "))
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


def page_images(en_title: str, *, limit: int = 6, width: int = 1920) -> list[Asset]:
    """記事に使われている画像を、ライセンスを確かめたうえで返す。"""
    names = _file_names(en_title)
    if not names:
        return []
    lead = _lead(en_title)
    d = _get(COMMONS_API, {
        "action": "query", "titles": "|".join("File:" + n for n in names[:40]),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": width,
    })
    if not d:
        return []
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
        by_name[filename] = Asset(
            source="commons", title=filename,
            url=info.get("thumburl") or _filepath_url(filename, width),
            page_url=info.get("descriptionurl", ""),
            license=lic,
            author=_clean(meta.get("Artist", {}).get("value")) or "不明",
            width=int(info.get("thumbwidth") or w or 0),
            height=int(info.get("thumbheight") or h or 0),
        )
    # 記事の出現順を保ち、代表画像だけ先頭に上げる
    ordered = [by_name[n] for n in names if n in by_name]
    if lead:
        ordered.sort(key=lambda a: a.title != lead)
    return ordered[:limit]
