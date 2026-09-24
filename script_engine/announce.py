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
    ("判定", "drafts/{name}_report.txt"),
    ("設計図", "drafts/{name}_plan.json"),
    ("題材の仕様", "seeds/topics/{name}.yaml"),
    ("出典の一覧", "seeds/topics/{name}_sources.json"),
)


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
        if re.match(r"^(尺:|資料に無い数字)", line):
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
             f"→ [Make video を実行する](https://github.com/{repo}/actions/workflows/make-video.yml)"
             "（Run workflow でブランチを選び、上の2つを貼る。他の欄はそのまま）", "",
             "**できたファイル**", "", "| | パス |", "|---|---|"]
    for label, tpl in FILES:
        rel = tpl.format(name=name)
        if (root / rel).exists():
            lines.append(f"| {label} | [{rel}]({base}{rel}) |")
    report = root / f"drafts/{name}_report.txt"
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
