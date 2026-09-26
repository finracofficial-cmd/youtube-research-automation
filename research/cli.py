"""取材メモを作り、そのまま台本プロンプトまで繋ぐ。

  python -m research dossier seeds/topics/oparts.yaml
  python -m research pipeline seeds/topics/oparts.yaml --duration 900
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .dossier import build, to_markdown


def _load(path: Path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    claims = [(c["ja"], c["en"]) for c in spec.get("claims", [])]
    spec["_exclude"] = tuple(spec.get("exclude", []))
    return spec["subject"], spec["subject_en"], claims, spec


def cmd_dossier(args) -> int:
    subject, subject_en, claims, spec = _load(Path(args.spec))
    d = build(subject, subject_en, claims, exclude=spec["_exclude"])
    out = Path(args.out or f"drafts/dossier_{Path(args.spec).stem}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text(to_markdown(d), encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(d.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"題材全体 {len(d.background)}件 / 主張 {len(d.claims)}件")
    for c in d.claims:
        print(f"  - {c.ja}: 出典{len(c.sources)}件 数字入り記述{len(c.numeric_facts)}件")
    print(f"-> {out.with_suffix('.md')}")
    return 0


def merge_previous(d, path: Path) -> int:
    """前回の出典の一覧を、今回の取材メモに合流させる。

    学術APIは日によって429で痩せる。実測で同じ題材が17件→4件になり、
    そのまま上書きすると、前に取れていた出典が消えた。主張ごとに、
    今回無いものを前回から足す。戻り値は足した件数。
    """
    from .sources import Source

    if not path.exists():
        return 0
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    if isinstance(prev, list):                    # 平らな旧形式
        prev = {"claims": [], "background": prev}

    def to_src(x: dict) -> Source:
        return Source(kind=x.get("kind") or "paper", title=x.get("title") or "",
                      year=x.get("year"), url=x.get("url") or "",
                      identifier=x.get("identifier") or "",
                      open_access=bool(x.get("open_access")), cited_by=0,
                      venue=x.get("venue") or "", authors=x.get("authors") or "")

    def key(x) -> str:
        ident = (x.identifier if hasattr(x, "identifier") else x.get("identifier")) or ""
        title = (x.title if hasattr(x, "title") else x.get("title")) or ""
        return (ident or title).strip().lower()

    added = 0
    by_ja = {c.get("ja"): c for c in prev.get("claims") or []}
    for c in d.claims:
        have = {key(x) for x in c.sources}
        for x in (by_ja.get(c.ja) or {}).get("sources") or []:
            if key(x) and key(x) not in have:
                c.sources.append(to_src(x)); have.add(key(x)); added += 1
    have = {key(x) for x in d.background}
    for x in prev.get("background") or []:
        if key(x) and key(x) not in have:
            d.background.append(to_src(x)); have.add(key(x)); added += 1
    return added


def enrich_authors(d, *, limit: int = 20) -> int:
    """DOI はあるのに著者が無い出典に、Crossref から筆頭著者を足す。

    前回から引き継いだ出典は著者を持っていないことがある（著者を取り始める
    前に集めたもの）。参考chは人の名前で語るので、名前が無いと本文が
    「1931年の論文」止まりになる。1件ずつ引くが、http のキャッシュに乗る。
    """
    from .http import get_json
    from .sources import first_author

    n = 0
    for x in d.all_sources:
        if n >= limit:
            break
        if x.authors or not x.identifier.startswith("10."):
            continue
        r = get_json("https://api.crossref.org/works/" + x.identifier, retries=1)
        auth = ((r or {}).get("message") or {}).get("author") or []
        x.authors = first_author([" ".join(v for v in (a.get("given"), a.get("family")) if v)
                                  for a in auth])
        n += 1
    return n


def cmd_pipeline(args) -> int:
    """調査 → 台本プロンプト。出典を渡さずに書かせないための一本道。"""
    from script_engine.render import Topic, build_prompt

    subject, subject_en, claims, spec = _load(Path(args.spec))
    d = build(subject, subject_en, claims, exclude=spec["_exclude"])
    src_path = Path(args.spec).with_name(f"{Path(args.spec).stem}_sources.json")
    kept_from_before = merge_previous(d, src_path)
    if kept_from_before:
        print(f"前回の出典を {kept_from_before}件 引き継いだ")
    enrich_authors(d)
    # 著者名を先に出す。参考chは「フリードマンは」「高橋は」と人で語る。
    # 題名だけ渡すと「2026年の論文の著者は不明」と本文に書かれた（実測）
    cited = [f"{s.year or '----'} {(s.authors + ' ') if s.authors else ''}{s.title} {s.url}".strip()
             for s in d.all_sources[:30]]
    facts = [f for c in d.claims for f in c.numeric_facts]

    topic = Topic(subject=subject, genre=spec.get("genre", "古代の謎"),
                  claims=tuple(c.ja for c in d.claims), sources=tuple(cited))
    prompt = build_prompt(topic, kind=args.kind, duration_sec=args.duration)
    if facts:
        prompt += ("\n\n## 一次資料から拾った数字（可能な限りこれを使う）\n"
                   + "\n".join(f"- {f}" for f in facts))
    # 題材が何なのかと、各主張の話の元（なぜそう語られるのか）。出典としては書かせない。
    # 冒頭1,800字だけ渡していたときは、死海文書の「公開が40年遅れた」「1991年の本が
    # バチカンの陰謀と言った」が資料に無く、台本が題材の説明も話の元も書けなかった
    from .wiki import lead, material as wiki_material, section
    prompt += (wiki_material(subject, subject_en, [(c.ja, c.en) for c in d.claims])
               or section(subject, lead(subject, subject_en)))
    prompt += ("\n\n## 厳守\n"
               "上の出典リストに無いものを出典として書かない。"
               "裏が取れていない数字を出さない。")
    out = Path(args.out or f"drafts/prompt_{Path(args.spec).stem}.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")

    # 出典は台本を書かせるためだけに使って捨てていた。概要欄に載せるので
    # 題材の仕様の隣に残す。ここを残さないと、何を読んで書いたのかが
    # 動画からも手元からも辿れなくなる。
    def rec(x):
        return {"kind": x.kind, "title": x.title, "year": x.year,
                "venue": getattr(x, "venue", None), "identifier": x.identifier,
                "url": x.url, "open_access": getattr(x, "open_access", False),
                "authors": getattr(x, "authors", "")}

    # 主張ごとに束ねる。概要欄では「何が分かるか」を先に書くので、
    # どの主張の根拠なのかが要る。平らに並べるとそれが消える。
    kept = {
        "claims": [{"ja": c.ja, "sources": [rec(x) for x in c.sources[:6]],
                    "evidence_level": getattr(c, "evidence_level", "")}
                   for c in d.claims],
        "background": [rec(x) for x in d.background[:8]],
    }
    src_path.write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"出典 {len(cited)}件 / 数字入り記述 {len(facts)}件 -> {out}")
    print(f"出典の一覧 -> {src_path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="research")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dossier", help="取材メモを作る")
    d.add_argument("spec"); d.add_argument("--out")
    d.set_defaults(func=cmd_dossier)
    q = sub.add_parser("pipeline", help="調査して台本プロンプトまで出す")
    q.add_argument("spec"); q.add_argument("--out")
    q.add_argument("--kind", choices=["flagship", "bundle"], default="bundle")
    q.add_argument("--duration", type=int, default=900)
    q.set_defaults(func=cmd_pipeline)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
