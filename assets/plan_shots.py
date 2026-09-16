"""台本から、カットごとの検索語リスト（shots spec）を起こす。

素材が少ないと同じ画を何度も使い回すことになる。実測で112カットに対し
画像7枚、1枚あたり16回の再利用だった。台本を時間で区切り、
各区間に出てくる固有名詞から検索語を作ることで、区間ごとに違う画を当てる。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from .terms import queries_for_segments


def split_script(text: str, n_segments: int) -> list[str]:
    """台本を文字数で等分する。ナレーションは一定速度で読まれる前提。"""
    sents = [s.strip() for s in re.split(r"(?<=[。？！])", text) if s.strip()]
    total = sum(len(s) for s in sents)
    target = total / n_segments
    segs, cur, acc = [], [], 0
    for s in sents:
        cur.append(s); acc += len(s)
        if acc >= target and len(segs) < n_segments - 1:
            segs.append("".join(cur)); cur, acc = [], 0
    if cur:
        segs.append("".join(cur))
    return segs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--segments", type=int, default=45, help="いくつの画で構成するか")
    ap.add_argument("--fallback", nargs="*", default=[],
                    help="語が取れなかった区間に使う検索語")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    segs = split_script(Path(a.script).read_text(encoding="utf-8"), a.segments)
    print(f"{len(segs)}区間に分割。Wikipediaで英訳中…")
    per = queries_for_segments(segs, per_segment=2)

    shots, last, n_found = [], list(a.fallback), 0
    for i, qs in enumerate(per):
        if qs:
            last = qs; n_found += 1
        # 語が取れない区間は直前の語を引き継ぐ。話題が続いている可能性が高い
        shots.append({"query": (qs or last) or ["ancient artifact"]})
    Path(a.out).write_text(yaml.safe_dump({"shots": shots}, allow_unicode=True,
                                          sort_keys=False), encoding="utf-8")
    uniq = {tuple(s["query"]) for s in shots}
    print(f"語が取れた区間 {n_found}/{len(segs)} / 異なる検索語 {len(uniq)}種")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
