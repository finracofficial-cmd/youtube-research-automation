"""題材から「取材メモ」を組む。台本生成の前段。

台本の数字密度は、文体ではなく調査の深さで決まる（工程Bの実測で判明:
記憶だけで書くと numerics_per_min が参照動画の72%で頭打ちになった）。
だからここで、出典そのものより先に「数字を含む一文」を集める。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .sources import Source, archive_org, crossref, openalex, relevance_filter

# 学術APIは英語が主。数字を含む主張だけを拾いたいので、年号単体は弾く。
NUM_SENT = re.compile(r"[^.。]*\d[^.。]*[.。]")
BARE_YEAR_ONLY = re.compile(r"^\D*(19|20)\d{2}\D*$")


@dataclass
class Claim:
    """語られている主張1つ。en は学術DBに投げるための英語クエリ。"""
    ja: str
    en: str
    sources: list[Source] = field(default_factory=list)
    numeric_facts: list[str] = field(default_factory=list)

    @property
    def evidence_level(self) -> str:
        """文献の厚みから、束ね型のどの位置に置くかを示唆する。

        学術文献がまったく出ない主張は、たいてい近代に作られた話である。
        これは収集の失敗ではなく、その主張自体の性質を表す信号として扱う。
        実際、バグダッド電池とコソ加工物はここで0件になり、
        どちらも台本では「跡形もなくなるもの」に置いた。
        """
        papers = [s for s in self.sources if s.kind == "paper"]
        if len(papers) >= 5:
            return "厚い（査読文献が複数）→ 当たっている側に置く候補"
        if papers:
            return "薄い（査読文献がわずか）→ 理由が違う側に置く候補"
        if self.sources:
            return "文献なし（原典・書籍のみ）→ 跡形もなくなる側に置く候補"
        return "文献なし → 跡形もなくなる側に置く候補。近代の創作を疑う"


@dataclass
class Dossier:
    subject: str
    subject_en: str
    claims: list[Claim] = field(default_factory=list)
    background: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject, "subject_en": self.subject_en,
            "background": [s.to_dict() for s in self.background],
            "claims": [{"ja": c.ja, "en": c.en,
                        "sources": [s.to_dict() for s in c.sources],
                        "numeric_facts": c.numeric_facts,
                        "evidence_level": c.evidence_level} for c in self.claims],
        }

    @property
    def all_sources(self) -> list[Source]:
        """主張ごとの出典を先、題材全体の資料を後に並べる。

        「オーパーツ」のような通俗語は学術用語ではないので、題材レベルの検索は
        高確率で無関係な論文を拾う（実測: "out-of-place artifact archaeology" で
        "Archaeology of Place" が上位に来た）。プロンプトに渡す本数には上限があるため、
        精度の高い主張別の出典が先に入るようにする。
        """
        out: list[Source] = []
        for c in self.claims:
            out += c.sources
        out += self.background
        seen, uniq = set(), []
        for s in out:
            k = s.identifier or s.title
            if k not in seen:
                seen.add(k); uniq.append(s)
        return uniq


def extract_numeric_facts(sources: list[Source], limit: int = 8) -> list[str]:
    """抄録から、数字を含む一文だけ抜く。台本の具体性の原料になる。"""
    out: list[str] = []
    for s in sources:
        for sent in NUM_SENT.findall(s.abstract or ""):
            sent = sent.strip()
            if len(sent) < 30 or BARE_YEAR_ONLY.match(sent):
                continue
            tag = s.identifier or s.title[:30]
            out.append(f"{sent}  [{tag}]")
            if len(out) >= limit:
                return out
    return out


def gather(query_en: str, *, papers: int = 30, books: int = 10,
           exclude: tuple[str, ...] = ()) -> list[Source]:
    """論文と原典を引いて、タイトル一致で絞り、被引用順に並べる。"""
    found = openalex(query_en, limit=papers) or crossref(query_en, limit=papers)
    found = relevance_filter(found, query_en, exclude=exclude)
    # archive.org は全文検索なので、絞り込みも同じクエリで行う。
    # 先頭1語だけで絞ると "Delhi" が裁判所文書を拾うなど無関係な結果が混ざる。
    found += relevance_filter(archive_org(query_en, limit=books), query_en, exclude=exclude)
    found.sort(key=lambda s: (-(s.open_access), -s.cited_by, -(s.year or 0)))
    return found


def build(subject: str, subject_en: str, claims: list[tuple[str, str]],
          exclude: tuple[str, ...] = ()) -> Dossier:
    """exclude には同名語の別分野を落とす語を渡す。
    実測で "Nazca" が地上絵とナスカプレート（地質学）で衝突した。"""
    d = Dossier(subject=subject, subject_en=subject_en)
    d.background = gather(subject_en, exclude=exclude)[:12]
    for ja, en in claims:
        found = gather(en, exclude=exclude)[:10]
        d.claims.append(Claim(ja=ja, en=en, sources=found,
                              numeric_facts=extract_numeric_facts(found)))
    return d


def to_markdown(d: Dossier) -> str:
    L = [f"# 取材メモ: {d.subject}", "",
         "自動収集した**候補**であって、裏取り済みの事実ではない。",
         "台本に使う前に、必ず本文に当たること。", ""]
    if d.background:
        L += ["## 題材全体の資料", ""]
        for s in d.background:
            oa = " [OA]" if s.open_access else ""
            L.append(f"- {s.year or '----'} {s.title}{oa}  \n  {s.url}")
        L.append("")
    for i, c in enumerate(d.claims, 1):
        L += [f"## 主張{i}: {c.ja}", f"検索語: `{c.en}`",
              f"**文献の厚み**: {c.evidence_level}", ""]
        if c.numeric_facts:
            L += ["**数字を含む記述（台本の具体性の原料）**", ""]
            L += [f"- {f}" for f in c.numeric_facts] + [""]
        L += ["**出典候補**", ""]
        for s in c.sources:
            oa = " [OA]" if s.open_access else ""
            L.append(f"- {s.year or '----'} {s.title}{oa}  \n  {s.url}")
        L.append("")
    return "\n".join(L)
