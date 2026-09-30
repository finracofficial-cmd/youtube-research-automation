"""Make video に渡されたファイルが台本かどうかを、動画を作る前に確かめる。

判定ファイル（`_report.txt`）を台本として渡してしまい、23分かけて
「品質の合格条件 ○ ○ ○」を読み上げる動画ができた（Make video #5）。
台本の隣に似た名前で置いた側の落ち度だが、受け取る側でも弾く。

  python -m script_engine.guard drafts/dead-sea.txt
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 台本ではないファイルの印。判定・設計図・案内文・資料
_NOT_SCRIPT = re.compile(r"合格条件|装置\s+実測|設計図:|Make video に入れる値|^## |^\[\d+\]|^- \d{4} ", re.M)
_SUFFIXES = ("_report", "_plan", "_description", "_titles", "_prompt", "_sources", "_market")
MIN_CHARS = 1200


def problems(path: Path) -> list[str]:
    """台本として渡してよいか。空なら台本。"""
    out: list[str] = []
    if not path.exists():
        return [f"無い: {path}"]
    if path.suffix != ".txt":
        out.append(f"台本は .txt だが {path.suffix}")
    if any(path.stem.endswith(s) for s in _SUFFIXES):
        out.append(f"名前が台本ではない（{path.stem} は判定・設計図・案内の類）")
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _NOT_SCRIPT.search(text)
    if m:
        out.append(f"本文に台本ではない印がある: 「{m.group(0).strip()}」")
    if len(text) < MIN_CHARS:
        out.append(f"短すぎる（{len(text)}字。台本は{MIN_CHARS}字以上）")
    return out


def candidates(drafts: Path) -> list[Path]:
    """drafts/ にある、台本として通るファイル。"""
    return sorted(p for p in drafts.glob("*.txt") if not problems(p))


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("使い方: python -m script_engine.guard <台本>")
        return 2
    if not args[0].strip():
        # Make video の script 欄は空が既定。既定の台本のまま回して、別の台本を70分かけて
        # 描画した（#10）。何を描くかは毎回選ばせる
        print("script が空。描画する台本を drafts/ から選んで入れる")
        cands = candidates(Path("drafts"))
        if cands:
            print("台本として通るファイル（新しい順）:")
            for c in sorted(cands, key=lambda c: -c.stat().st_mtime):
                print(f"  {c}")
        return 1
    path = Path(args[0])
    got = problems(path)
    if not got:
        print(f"台本として通る: {path}")
        return 0
    print(f"これは台本ではない: {path}")
    for p in got:
        print(f"  - {p}")
    cands = candidates(path.parent if path.parent.exists() else Path("drafts"))
    if cands:
        print("台本として通るファイル:")
        for c in cands:
            print(f"  {c}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
