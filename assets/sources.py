"""素材の収集元。すべて「ライセンスが明示されているもの」だけを扱う。

元チャンネルは概要欄で画像を全点クレジットしている（CC BY / CC BY-SA を
作者名とライセンス名つきで列挙し、PD/CC0 は画面表示で対応）。
それを自動でやるため、収集の時点で作者とライセンスを必ず持ち帰る。
ライセンスが判定できない素材は捨てる。後から調べ直せないため。
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict

# Wikimedia は実在の連絡先を求める。research@example.com のような置き場所の
# 文字列だと、APIは通っても実体の取得が403で弾かれる（実測で動画が落ちた）。
CONTACT = "https://github.com/finracofficial-cmd/youtube-research-automation"
UA = f"youtube-research-automation/0.1 ({CONTACT})"

# 使ってよいライセンス。ここに無いものは落とす。
ALLOWED = (
    "public domain", "pd", "cc0", "cc-zero",
    "cc by", "cc-by", "cc by-sa", "cc-by-sa",
)
# 商用不可・改変不可は動画に使えない
FORBIDDEN = ("nc", "nd", "non-commercial", "noderivs", "fair use", "non-free")


@dataclass
class Asset:
    source: str          # "commons" | "met" | "nasa"
    title: str
    url: str             # 画像の直リンク
    page_url: str        # 出典ページ
    license: str
    author: str
    width: int = 0
    height: int = 0
    # "image" か "video"。Commons には CC の動画があり、静止画だけで
    # 構成すると参考chとの差が一番出るところになる。
    kind: str = "image"
    durationSec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def needs_attribution(self) -> bool:
        """CC BY / CC BY-SA は表示が条件。PD/CC0 は任意。"""
        return "by" in self.license.lower()


def _get(url: str, retries: int = 4, timeout: int = 60) -> dict | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt * 3)
                continue
            return None
        except Exception:  # noqa: BLE001
            time.sleep(2 ** attempt * 2)
    return None


def _clean(raw: str | None) -> str:
    """extmetadata の値はHTML片。タグを剥がし、重複した繰り返しを畳む。"""
    if not raw:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
    text = re.sub(r"\s+", " ", text)
    # "Unknown authorUnknown author" のように同じ語が続けて入ることがある
    half = len(text) // 2
    if half and text[:half] == text[half:]:
        text = text[:half]
    return text


# どの題材でも出るので、一致判定に使っても絞り込めない語
WEAK = {"ancient", "history", "photo", "image", "file", "view", "the"}


def title_matches(title: str, query: str, *, min_ratio: float = 0.5) -> bool:
    """タイトルが検索語に本当に対応しているかを見る。

    キーワード検索は語の一部だけ一致した無関係な画像を平気で返す。
    実測で "Baghdad battery" にバグダッドの米兵の写真が返ってきた。
    先頭語（多くの場合は固有名詞）を必須にし、残りも半分は含ませる。
    """
    keys = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", query)]
    keys = [k for k in keys if k not in WEAK] or keys
    if not keys:
        return True
    low = (title or "").lower()
    head, rest = keys[0], keys[1:]
    if head not in low:
        return False
    if not rest:
        return True
    # min_ratio=0 は「先頭語だけ合えばよい」という意味。
    # ここで max(1, ...) を噛ませると緩和モードが機能しなくなる（実際にならなかった）。
    need = 0 if min_ratio <= 0 else max(1, round(len(rest) * min_ratio))
    return sum(k in low for k in rest) >= need


def license_ok(license_name: str) -> bool:
    low = (license_name or "").lower()
    if not low:
        return False
    if any(bad in low for bad in FORBIDDEN):
        return False
    return any(ok in low for ok in ALLOWED)


def _filepath_url(filename: str, width: int) -> str:
    """Special:FilePath は必ずサムネイルへ転送してくれる。

    imageinfo の url（原寸）は 403 で弾かれることがあり、
    thumburl も元画像が要求幅より小さいと返ってこない。
    ダウンロード先はこちらに寄せる。
    """
    return ("https://commons.wikimedia.org/wiki/Special:FilePath/"
            + urllib.parse.quote(filename.replace(" ", "_"))
            + f"?width={width}")


def commons(query: str, limit: int = 20, width: int = 1920, *, strict: bool = True) -> list[Asset]:
    """Wikimedia Commons。ライセンス情報がAPIで取れるのが最大の利点。"""
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6,  # File名前空間。指定しないと0件になる
        "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": width, "format": "json",
    })
    d = _get(url)
    if not d:
        return []
    out = []
    for page in (d.get("query", {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = _clean(meta.get("LicenseShortName", {}).get("value"))
        if not license_ok(lic):
            continue
        filename = page.get("title", "").removeprefix("File:")
        if strict and not title_matches(filename, query):
            continue
        if not strict and not title_matches(filename, query, min_ratio=0.0):
            continue  # 緩和時も先頭語だけは必須
        out.append(Asset(
            source="commons",
            title=filename,
            url=info.get("thumburl") or _filepath_url(filename, width),
            page_url=info.get("descriptionurl", ""),
            license=lic,
            author=_clean(meta.get("Artist", {}).get("value")) or "不明",
            width=int(info.get("thumbwidth") or info.get("width") or 0),
            height=int(info.get("thumbheight") or info.get("height") or 0),
        ))
    return out


def met(query: str, limit: int = 10) -> list[Asset]:
    """メトロポリタン美術館のオープンアクセス。CC0 のものだけ返る。"""
    search = _get("https://collectionapi.metmuseum.org/public/collection/v1/search?"
                  + urllib.parse.urlencode({"q": query, "hasImages": "true"}))
    if not search:
        return []
    out = []
    for oid in (search.get("objectIDs") or [])[:limit]:
        obj = _get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
        if not obj or not obj.get("isPublicDomain") or not obj.get("primaryImage"):
            continue
        if not title_matches(obj.get("title", ""), query):
            continue
        out.append(Asset(
            source="met", title=obj.get("title", ""),
            url=obj["primaryImage"], page_url=obj.get("objectURL", ""),
            license="CC0", author=obj.get("artistDisplayName") or "不明",
        ))
        time.sleep(0.2)  # 1オブジェクト1リクエストなので間隔を空ける
    return out


def nasa(query: str, limit: int = 10, *, strict: bool = True) -> list[Asset]:
    """NASA の画像。原則パブリックドメイン。"""
    d = _get("https://images-api.nasa.gov/search?"
             + urllib.parse.urlencode({"q": query, "media_type": "image"}))
    if not d:
        return []
    out = []
    for item in (d.get("collection", {}).get("items") or [])[:limit]:
        data = (item.get("data") or [{}])[0]
        links = item.get("links") or []
        if not links:
            continue
        if not title_matches(data.get("title", ""), query,
                             min_ratio=0.5 if strict else 0.0):
            continue
        out.append(Asset(
            source="nasa", title=data.get("title", ""),
            url=links[0].get("href", ""),
            page_url=f"https://images.nasa.gov/details-{data.get('nasa_id','')}",
            license="Public domain (NASA)", author=data.get("center") or "NASA",
        ))
    return out


def search_all(query: str, *, per_source: int = 12) -> tuple[list[Asset], bool]:
    """候補と、「絞り込みを緩めたか」を返す。

    厳しく絞ると題材によっては0件になる（実測で "Ottoman cartography" が全滅した）。
    黙って諦めるのでも、黙って無関係な画像を使うのでもなく、
    緩めて拾ったことを呼び出し側に伝えて、人の確認に回す。
    """
    found = commons(query, limit=per_source) + nasa(query, limit=max(3, per_source // 3))
    relaxed = False
    if not found:
        found = (commons(query, limit=per_source, strict=False)
                 + nasa(query, limit=max(3, per_source // 3), strict=False))
        relaxed = bool(found)
    # PD/CC0 を優先し、表示義務のあるものを後ろに回す
    found.sort(key=lambda a: (a.needs_attribution, -a.width))
    return found, relaxed
