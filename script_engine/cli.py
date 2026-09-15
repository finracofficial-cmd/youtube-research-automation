"""台本の骨組みを出す CLI。

  python -m script_engine prompt "巨石遺跡" --kind bundle --claims "..." "..."
  python -m script_engine check draft.txt --duration 2272
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .render import Topic, build_prompt
from .style import validate


def cmd_prompt(args) -> int:
    topic = Topic(subject=args.subject, genre=args.genre,
                  claims=tuple(args.claims or ()), sources=tuple(args.sources or ()))
    text = build_prompt(topic, kind=args.kind, duration_sec=args.duration)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"-> {args.out}")
    else:
        print(text)
    return 0


def cmd_check(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    m = validate(text, args.duration)
    print(f"文数 {m.n_sentences} / 字数 {m.n_chars}")
    print(f"  平均文長      {m.avg_sentence_len:.1f}字")
    print(f"  文の密度      {m.sentences_per_min:.1f}文/分")
    print(f"  話速          {m.chars_per_min:.0f}字/分")
    print(f"  常体率        {m.plain_form_ratio:.0%}")
    print(f"  疑問文        {m.question_ratio:.1%}")
    print(f"  数字          {m.numerics_per_min:.1f}個/分")
    print(f"  短文(10字以下) {m.short_sentence_ratio:.0%}")
    print(f"\n参照動画への忠実度: {m.fidelity:.0%}")
    for line in m.fidelity_report():
        print(f"  {line}")
    if m.ok:
        print("\n合格")
        if m.fidelity < 0.85:
            print(f"（ただし忠実度 {m.fidelity:.0%}。レンジは通っているが型としては痩せている）")
        return 0
    print("\n不合格:")
    for v in m.violations:
        print(f"  - {v}")
    return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="script_engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("prompt", help="台本生成プロンプトを組み立てる")
    a.add_argument("subject")
    a.add_argument("--kind", choices=["flagship", "bundle"], default="flagship")
    a.add_argument("--genre", default="未解決の謎")
    a.add_argument("--duration", type=int, default=None, help="尺（秒）")
    a.add_argument("--claims", nargs="*", help="束ね型で検証する主張")
    a.add_argument("--sources", nargs="*", help="事前に当たった一次資料")
    a.add_argument("--out")
    a.set_defaults(func=cmd_prompt)

    c = sub.add_parser("check", help="台本を実測プロファイルに照らす")
    c.add_argument("file")
    c.add_argument("--duration", type=int, required=True, help="尺（秒）")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
