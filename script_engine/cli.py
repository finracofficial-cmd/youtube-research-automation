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


def cmd_compare(args) -> int:
    """複数の台本を、参照動画に対して横並びで比べる。

    「別テーマでも同じ構成になっているか」は1本では答えられない。
    テーマを変えて書いたものを並べ、ばらつきを見るための道具。
    """
    from .style import REFERENCE, analyze

    rows = []
    for item in args.drafts:
        path, _, dur = item.partition(":")
        if not dur:
            raise SystemExit(f"'{item}' は path:duration の形で渡す")
        m = analyze(Path(path).read_text(encoding="utf-8"), int(dur))
        rows.append((Path(path).stem, m))

    keys = list(REFERENCE)
    print(f"{'指標':<22}{'参照':>9}" + "".join(f"{n[:13]:>15}" for n, _ in rows))
    print("-" * (31 + 15 * len(rows)))
    for k in keys:
        line = f"{k:<22}{REFERENCE[k]:>9.2f}"
        for _, m in rows:
            got = getattr(m, k)
            line += f"{got:>9.2f}({got/REFERENCE[k]*100:>3.0f}%)"
        print(line)
    print(f"\n{'忠実度':<22}{'100%':>9}" + "".join(f"{m.fidelity*100:>14.0f}%" for _, m in rows))

    if len(rows) >= 2:
        print("\n--- テーマ間のばらつき ---")
        worst = 0.0
        for k in keys:
            vals = [getattr(m, k) for _, m in rows]
            spread = (max(vals) - min(vals)) / REFERENCE[k]
            worst = max(worst, spread)
            print(f"  {k:<22}幅 {spread*100:>5.1f}%")
        verdict = "安定" if worst < 0.20 else "不安定"
        print(f"\n最大ぶれ {worst*100:.1f}% → {verdict}"
              f"（20%未満を安定とみなす）")
    return 0


def cmd_write(args) -> int:
    """プロンプトを渡して台本を書かせ、実測から外れていれば直させる。"""
    from .write import WriteFailed, write

    prompt = Path(args.prompt).read_text(encoding="utf-8")

    def checker(text: str) -> list[str]:
        m = validate(text, args.duration)
        notes = list(m.violations)
        # レンジは通っていても型として痩せている場合がある。そこも直させる
        if m.fidelity < 0.85:
            notes += [l for l in m.fidelity_report() if "±" not in l][:3]
        return notes

    try:
        text, left = write(prompt, model=args.model, rounds=args.rounds,
                           checker=checker, duration_sec=args.duration)
    except WriteFailed as exc:
        print(f"生成できなかった: {exc}")
        return 1

    Path(args.out).write_text(text, encoding="utf-8")
    m = validate(text, args.duration)
    print(f"{len(text)}字 / 忠実度 {m.fidelity:.0%} -> {args.out}")
    if left:
        print("直しきれなかった点:")
        for n in left:
            print(f"  - {n}")
    return 0 if m.ok else 1


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

    w = sub.add_parser("write", help="プロンプトから台本を書かせる")
    w.add_argument("prompt", help="prompt サブコマンドが出したファイル")
    w.add_argument("--out", required=True)
    w.add_argument("--duration", type=float, default=900.0)
    w.add_argument("--model", default="gpt-4.1")
    w.add_argument("--rounds", type=int, default=2,
                   help="実測から外れていたときに直させる回数")
    w.set_defaults(func=cmd_write)

    m = sub.add_parser("compare", help="複数の台本を参照動画と横並びで比べる")
    m.add_argument("drafts", nargs="+", help="path:duration の形で複数指定")
    m.set_defaults(func=cmd_compare)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
