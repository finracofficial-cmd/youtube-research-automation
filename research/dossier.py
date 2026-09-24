"""題材から「取材メモ」を組む。台本生成の前段。

台本の数字密度は、文体ではなく調査の深さで決まる（工程Bの実測で判明:
記憶だけで書くと numerics_per_min が参照動画の72%で頭打ちになった）。
だからここで、出典そのものより先に「数字を含む一文」を集める。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict

from .sources import (WEAK, Source, archive_org, crossref, openalex,
                      relevance_filter)

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


# クエリの骨組みに使うだけで、中身を指していない語。題材語を引いただけでは
# 残ってしまう。実測で "botanical identification real plants" の主張に、
# 言語統計の論文が identification / real の一致だけで通った。
FILLER = {"identification", "identify", "real", "theory", "theories",
          "evidence", "comparison", "origin", "origins", "case", "cases",
          "method", "methods", "approach", "using", "based", "data",
          "results", "overview", "problem", "question", "questions"}


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text or "")}


def discriminators(claims: list[tuple[str, str]]) -> list[set[str]]:
    """主張ごとに「その主張だけの語」を出す。

    relevance_filter は題材の語で絞るので、同じ題材の論文なら何でも通る。
    主張に紐づけるにはそれでは足りない。実測で「手稿の植物は実在の植物か」
    という主張に、言語統計の論文が3本ぶら下がった。見出しにその主張文を
    使う以上、これは概要欄が嘘をつくのと同じになる。

    どの主張にも出てくる語（= 題材名）を引き、残りをその主張の語とする。
    subject_en の書き方に依存しない（voynich の subject_en は
    "botanical identification" を含んでいて、題材語として引くと
    植物の主張から識別語が消える）。
    """
    sets = [_words(en) - WEAK - FILLER for _, en in claims]
    if len(sets) < 2:
        return [set() for _ in sets]
    common = set.intersection(*sets)
    return [s - common for s in sets]


def on_topic(sources: list[Source], keys: set[str]) -> list[Source]:
    """その主張の語をタイトルに持つものだけ残す。語が無ければ素通し。"""
    if not keys:
        return sources
    return [s for s in sources
            if any(k in (s.title or "").lower() for k in keys)]


def build(subject: str, subject_en: str, claims: list[tuple[str, str]],
          exclude: tuple[str, ...] = ()) -> Dossier:
    """exclude には同名語の別分野を落とす語を渡す。
    実測で "Nazca" が地上絵とナスカプレート（地質学）で衝突した。"""
    d = Dossier(subject=subject, subject_en=subject_en)
    d.background = gather(subject_en, exclude=exclude)[:12]
    seen = {(s.title or "").lower() for s in d.background}
    spare: list[Source] = []
    for (ja, en), keys in zip(claims, discriminators(claims)):
        time.sleep(1.5)   # 続けて投げると429が連発する（実測）
        found = gather(en, exclude=exclude)[:10]
        kept = on_topic(found, keys)
        # 主張から外れたものは捨てずに背景へ。題材の資料ではあるので、
        # 概要欄では「題材全体の背景」の側に並ぶ。
        for s in found:
            if s not in kept and (s.title or "").lower() not in seen:
                seen.add((s.title or "").lower())
                spare.append(s)
        d.claims.append(Claim(ja=ja, en=en, sources=kept,
                              numeric_facts=extract_numeric_facts(kept or found)))
    d.background += spare
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
