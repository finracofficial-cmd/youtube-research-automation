"""採点した題材を、人が選べる形にする。

自動で選んで自動で台本にすると、外した題材に取材と描画の時間を丸ごと
使ってしまう。1本あたり1時間半かかるので、作る前に人が見る工程を挟む。

GitHubのIssueのチェックリストにするのは、スマホから見て選べるため。
選んだものだけを次の工程が読む。

  python3 -m topic_scout.review analysis/topics_2026-09-17.csv --limit 20
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# チェックされた項目から題材名を取り出す。太字で囲ってある
_CHECKED = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*\*\*(?P<name>[^*]+)\*\*")


def to_checklist(rows: list[dict], limit: int = 20) -> str:
    """採点結果を、選べるチェックリストにする。"""
    keep = [r for r in rows if r.get("verdict") == "狙う"][:limit]
    if not keep:
        keep = rows[:limit]

    lines = [
        "作る題材を選んでください。チェックした題材だけ台本を書きます。",
        "",
        "選び終えたら Actions の **Write approved** を、このIssueの番号を指定して実行してください。",
        "",
        "| 記号 | 意味 |",
        "|---|---|",
        "| 需要 | その題材が実際に再生されているか |",
        "| 空白 | 丁寧に作った動画がまだ無いか（高いほど空いている） |",
        "| 時流 | 最近も再生が伸びているか |",
        "",
    ]
    for r in keep:
        def num(k: str) -> float:
            try:
                return float(r.get(k) or 0)
            except ValueError:
                return 0.0

        views = int(num("views_max"))
        lines.append(f"- [ ] **{r['query']}**")
        lines.append(
            f"  総合 {num('score'):.2f} ／ 需要 {num('demand'):.2f} ／ "
            f"空白 {num('gap'):.2f} ／ 時流 {num('trend'):.2f} ／ "
            f"最高再生 {views:,}")
        if r.get("reasons"):
            lines.append(f"  {r['reasons']}")
    lines += ["", f"（候補 {len(rows)}件のうち上位 {len(keep)}件）"]
    return "\n".join(lines)


def checked_subjects(issue_body: str) -> list[str]:
    """Issueの本文から、チェックされた題材名を拾う。"""
    out = []
    for line in issue_body.splitlines():
        m = _CHECKED.match(line)
        if m:
            out.append(m.group("name").strip())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="採点結果をIssue本文にする")
    ap.add_argument("csv")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    with open(a.csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    body = to_checklist(rows, a.limit)
    if a.out:
        Path(a.out).write_text(body, encoding="utf-8")
        print(f"-> {a.out}")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
