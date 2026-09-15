"""一次資料の候補を集める。

元チャンネルが概要欄で挙げている出典の内訳に合わせて、3系統から引く:
  査読論文（DOI付き）      -> OpenAlex / Crossref
  パブリックドメインの原典 -> archive.org
学術データベースは英語が主なので、クエリは英語で投げる前提。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .http import get_json, q


@dataclass
class Source:
    kind: str           # "paper" | "book"
    title: str
    year: int | None
    url: str
    identifier: str     # DOI / archive.org ID
    open_access: bool
    cited_by: int
    abstract: str = ""
    venue: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _deinvert(idx: dict | None) -> str:
    """OpenAlex の abstract_inverted_index を普通の文章に戻す。"""
    if not idx:
        return ""
    pos: dict[int, str] = {}
    for word, places in idx.items():
        for p in places:
            pos[p] = word
    return " ".join(pos[i] for i in sorted(pos))


# 環境によっては OpenAlex がプロキシ側で恒常的に429を返す。
# 毎回リトライすると1クエリ90秒を捨てるので、一度落ちたらそのセッションでは諦める。
_OPENALEX_DOWN = False


def openalex(query: str, limit: int = 25) -> list[Source]:
    global _OPENALEX_DOWN
    if _OPENALEX_DOWN:
        return []
    url = "https://api.openalex.org/works?" + q({
        "search": query, "per-page": limit, "sort": "cited_by_count:desc",
        "mailto": "research@example.com",
    })
    d = get_json(url, retries=2)
    if not d or "results" not in d:
        _OPENALEX_DOWN = True
        return []
    out = []
    for w in d["results"]:
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        loc = w.get("primary_location") or {}
        src = (loc.get("source") or {}).get("display_name") or ""
        out.append(Source(
            kind="paper",
            title=w.get("title") or "",
            year=w.get("publication_year"),
            url=w.get("doi") or (loc.get("landing_page_url") or ""),
            identifier=doi,
            open_access=bool((w.get("open_access") or {}).get("is_oa")),
            cited_by=int(w.get("cited_by_count") or 0),
            abstract=_deinvert(w.get("abstract_inverted_index")),
            venue=src,
        ))
    return out


def crossref(query: str, limit: int = 25) -> list[Source]:
    url = "https://api.crossref.org/works?" + q({
        "query.bibliographic": query, "rows": limit,
        "select": "title,issued,DOI,container-title,is-referenced-by-count,abstract",
        "mailto": "research@example.com",
    })
    d = get_json(url)
    if not d:
        return []
    out = []
    for it in (d.get("message", {}).get("items") or []):
        title = " ".join(it.get("title") or [])
        parts = (it.get("issued", {}).get("date-parts") or [[None]])[0]
        doi = it.get("DOI") or ""
        out.append(Source(
            kind="paper", title=title, year=parts[0] if parts else None,
            url=f"https://doi.org/{doi}" if doi else "", identifier=doi,
            open_access=False,
            cited_by=int(it.get("is-referenced-by-count") or 0),
            abstract=re.sub(r"<[^>]+>", "", it.get("abstract") or ""),
            venue=" ".join(it.get("container-title") or []),
        ))
    return out


def archive_org(query: str, limit: int = 15) -> list[Source]:
    """パブリックドメインの原典。元チャンネルはここを多用している。"""
    url = "https://archive.org/advancedsearch.php?" + q({
        "q": f"{query} AND mediatype:texts", "rows": limit, "output": "json",
    }) + "&fl[]=identifier&fl[]=title&fl[]=year&fl[]=downloads"
    d = get_json(url)
    if not d:
        return []
    out = []
    for x in (d.get("response", {}).get("docs") or []):
        ident = x.get("identifier", "")
        year = x.get("year")
        out.append(Source(
            kind="book", title=x.get("title") or "",
            year=int(year) if str(year).isdigit() else None,
            url=f"https://archive.org/details/{ident}",
            identifier=ident, open_access=True,
            cited_by=int(x.get("downloads") or 0),
        ))
    return out


# どの題材にも出てくるので、一致判定に使っても絞り込めない語
WEAK = {"ancient", "study", "analysis", "history", "research", "review", "new", "the"}


def relevance_filter(sources: list[Source], query: str, *, min_ratio: float = 0.7) -> list[Source]:
    """タイトルにクエリ語が入っているものだけ残す。

    学術APIのあいまい検索は「Antikythera mechanism」で70万件返す。
    総件数は当てにならないので、タイトル一致で絞る。

    ただし全語一致を求めると、"Delhi iron pillar corrosion" のような
    4語クエリがほぼ全滅する。識別力のある語の7割が入っていれば通す。

    そのかわり**先頭の語は必須**にする。クエリは固有名詞から書く決まりなので、
    先頭を落とした一致は題材違いになる。実測で "Gobekli Tepe Neolithic chronology" が
    Gobekli を含まないイランの新石器年代論を拾っていた。
    """
    keys = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", query)]
    keys = [k for k in keys if k not in WEAK] or keys
    if not keys:
        return sources
    head, rest = keys[0], keys[1:]
    need = max(0, round(len(rest) * min_ratio))
    out = []
    for s in sources:
        title = (s.title or "").lower()
        if head in title and sum(k in title for k in rest) >= need:
            out.append(s)
    return out
