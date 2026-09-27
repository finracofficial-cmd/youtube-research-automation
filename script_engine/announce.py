"""書き上がった台本の案内文。Issue のコメントと Actions の Summary に貼る。

Make video に何を入れればいいかが、コメントを読んでも分からなかった
（パスが本文に埋まっていて、判定のブロックは空だった）。できたファイルを
全部リンク付きで並べ、Make video に入れる値を表にして出す。

  python -m script_engine.announce --name dead-sea --subject 死海文書 \\
      --repo finracofficial-cmd/youtube-research-automation --branch claude/x
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

FILES = (
    ("台本", "drafts/{name}.txt"),
    ("判定", "reports/{name}_report.txt"),
    ("設計図", "reports/{name}_plan.json"),
    ("題材の仕様", "seeds/topics/{name}.yaml"),
    ("出典の一覧", "seeds/topics/{name}_sources.json"),
    ("市場の集計", "reports/{name}_market.json"),
)


def title_lines(name: str, root: Path) -> list[str]:
    """市場の数字つきの題名の案（上位3つ）。市場の集計が無ければ空。"""
    import json
    import sys

    import yaml
    market_p, plan_p = root / f"reports/{name}_market.json", root / f"reports/{name}_plan.json"
    script_p, spec_p = root / f"drafts/{name}.txt", root / f"seeds/topics/{name}.yaml"
    if not (market_p.exists() and script_p.exists()):
        return []
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import titles
    market = json.loads(market_p.read_text(encoding="utf-8"))
    plan = json.loads(plan_p.read_text(encoding="utf-8")) if plan_p.exists() else {}
    spec = yaml.safe_load(spec_p.read_text(encoding="utf-8")) if spec_p.exists() else {}
    script = script_p.read_text(encoding="utf-8")
    subject = (spec or {}).get("subject") or market.get("subject") or name
    got = titles.market_propose(subject, (spec or {}).get("claims") or [], script, plan, market, k=3)
    rank = {x["term"]: x.get("adj", x["lift"]) for x in market.get("lifts") or []}
    out = ["**題名の案**（市場で伸びている語の効きで点を付けた。選ぶのは人）", ""]
    for i, x in enumerate(got, 1):
        why = "・".join(f"{t} {rank.get(t, 1.0)}倍" for t in x["hot"]) or "なし"
        out.append(f"{i}. {x['title']}  \n   効く語: {why}")
    gap = titles.opening_gap(script, plan, market)
    if gap:
        out += ["", f"注意: {gap}"]
    return out


def verdict_lines(report: str) -> list[str]:
    """判定ファイルから、合格条件の表と尺と資料に無い数字だけ抜く。"""
    out: list[str] = []
    grab = False
    for line in report.splitlines():
        if "合格条件:" in line:
            grab = True
        if grab:
            out.append(line)
            if line.strip().startswith("→"):
                grab = False
            continue
        if re.match(r"^(尺:|資料に無い数字|初見の読み)", line):
            out.append(line)
    return out


def render(name: str, subject: str, *, repo: str, branch: str, root: Path | str = ".") -> str:
    root = Path(root)
    base = f"https://github.com/{repo}/blob/{branch}/"
    lines = [f"## {subject}", "",
             f"**Make video に入れる値**（ブランチ `{branch}`）", "",
             "| 欄 | 値 |", "|---|---|",
             f"| script | `drafts/{name}.txt` |",
             f"| name | `{name}` |", "",
             "script は **drafts/ の台本だけ**。reports/ の判定や設計図を渡すと、それを読み上げる動画になる。", "",
             f"→ [Make video を実行する](https://github.com/{repo}/actions/workflows/make-video.yml)"
             "（Run workflow でブランチを選び、上の2つを貼る。他の欄はそのまま）", "",
             "**できたファイル**", "", "| | パス |", "|---|---|"]
    for label, tpl in FILES:
        rel = tpl.format(name=name)
        if (root / rel).exists():
            lines.append(f"| {label} | [{rel}]({base}{rel}) |")
    try:
        tl = title_lines(name, root)
    except Exception as exc:  # noqa: BLE001 - 題名の案が作れなくても案内は出す
        tl = [f"（題名の案を作れなかった: {exc}）"]
    if tl:
        lines += [""] + tl
    report = root / f"reports/{name}_report.txt"
    if report.exists():
        got = verdict_lines(report.read_text(encoding="utf-8"))
        if got:
            lines += ["", "**判定**", "", "```"] + got + ["```"]
            if any("不合格" in g for g in got):
                lines.append("")
                lines.append("**不合格の台本は動画にしない。** 判定ファイルの「直しきれなかった点」を見て、資料を足すか書き直す。")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="script_engine.announce")
    p.add_argument("--name", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--branch", required=True)
    p.add_argument("--root", default=".")
    a = p.parse_args(argv)
    print(render(a.name, a.subject, repo=a.repo, branch=a.branch, root=a.root), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
