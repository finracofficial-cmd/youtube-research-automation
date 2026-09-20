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


def cmd_pipeline(args) -> int:
    """調査 → 台本プロンプト。出典を渡さずに書かせないための一本道。"""
    from script_engine.render import Topic, build_prompt

    subject, subject_en, claims, spec = _load(Path(args.spec))
    d = build(subject, subject_en, claims, exclude=spec["_exclude"])
    cited = [f"{s.year or '----'} {s.title} {s.url}".strip() for s in d.all_sources[:30]]
    facts = [f for c in d.claims for f in c.numeric_facts]

    topic = Topic(subject=subject, genre=spec.get("genre", "古代の謎"),
                  claims=tuple(c.ja for c in d.claims), sources=tuple(cited))
    prompt = build_prompt(topic, kind=args.kind, duration_sec=args.duration)
    if facts:
        prompt += ("\n\n## 一次資料から拾った数字（可能な限りこれを使う）\n"
                   + "\n".join(f"- {f}" for f in facts))
    prompt += ("\n\n## 厳守\n"
               "上の出典リストに無いものを出典として書かない。"
               "裏が取れていない数字を出さない。")
    out = Path(args.out or f"drafts/prompt_{Path(args.spec).stem}.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")

    # 出典は台本を書かせるためだけに使って捨てていた。概要欄に載せるので
    # 題材の仕様の隣に残す。ここを残さないと、何を読んで書いたのかが
    # 動画からも手元からも辿れなくなる。
    spec_path = Path(args.spec)
    kept = [{"kind": x.kind, "title": x.title, "year": x.year,
             "venue": getattr(x, "venue", None), "identifier": x.identifier}
            for x in d.all_sources[:30]]
    src_path = spec_path.with_name(f"{spec_path.stem}_sources.json")
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
