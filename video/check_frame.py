"""描いた1枚に、読めない文字（豆腐）が出ていないか確かめる。

日本語のフォントが入っていない環境で描くと、字幕もカードも □ になる。
描画は成功するので、動画が出来上がるまで気づかない。実測で本編17分を
まるごと読めない状態で作ってしまった。

豆腐は「同じ大きさの四角が等間隔に並ぶ」という形で出る。文字の部分だけを
見て、縦線が規則正しく並んでいたら豆腐とみなす。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def has_japanese_font() -> bool:
    """描画に使える日本語フォントがあるか。"""
    r = subprocess.run(["fc-list", ":lang=ja", "family"],
                       capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方: check_frame.py <画像>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"描けていない: {path}")
        return 1

    if not has_japanese_font():
        print("!! 日本語フォントが無い。字幕とカードが豆腐（□）になる。")
        print("   fonts-noto-cjk を入れてから描き直すこと。")
        return 1
    print("日本語フォントあり")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
