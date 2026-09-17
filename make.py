"""台本1本から、動画1本を作る。

  python3 make.py drafts/oparts_v1.txt --name oparts

途中の工程（検索語の割り出し、素材の収集、部品の配置、描画）は全部この中で
順に走る。工程ごとにコマンドが分かれていると、引数の食い違いで素材と
台本がずれる。実際に、素材の置き場を決め打ちしていて別テーマを並行して
扱えなかったり、manifest の指定漏れで前のテーマの画で描画したことがある。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"失敗: {' '.join(cmd)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="台本から動画を1本作る")
    ap.add_argument("script", help="台本のテキストファイル")
    ap.add_argument("--name", help="出力名。省略すると台本のファイル名")
    ap.add_argument("--duration", type=float, default=900.0, help="尺（秒）")
    ap.add_argument("--claims", type=int, default=5, help="取り上げる主張の数")
    ap.add_argument("--kind", default="bundle", choices=["bundle", "flagship"])
    ap.add_argument("--segments", type=int, default=80, help="画を切り替える回数の目安")
    ap.add_argument("--skip-assets", action="store_true",
                    help="素材の収集を飛ばす（手元の素材で作り直すとき）")
    ap.add_argument("--still", type=int, help="動画の代わりに指定フレームの静止画を出す")
    a = ap.parse_args()

    script = Path(a.script)
    if not script.exists():
        raise SystemExit(f"台本が無い: {script}")
    name = a.name or script.stem
    shots_dir = f"shots_{name}"
    spec = ROOT / "seeds" / "shots" / f"{name}.yaml"
    props = ROOT / "video" / f"props_{name}.json"
    out = ROOT / "out" / (f"{name}.png" if a.still else f"{name}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    began = time.time()
    if not a.skip_assets:
        spec.parent.mkdir(parents=True, exist_ok=True)
        print("■ 1/4 台本から検索語を割り出す")
        run([sys.executable, "-m", "assets.plan_shots", str(script),
             "--segments", str(a.segments), "--out", str(spec)])

        print("\n■ 2/4 素材を集める")
        run([sys.executable, "-m", "assets", "fetch", str(spec),
             "--out", f"video/public/{shots_dir}", "--limit", "12"])
    elif not spec.exists():
        raise SystemExit(f"--skip-assets だが検索語が無い: {spec}")

    print("\n■ 3/4 部品を配置する")
    run([sys.executable, "video/build_props.py", str(script),
         "--duration", str(a.duration), "--kind", a.kind,
         "--claims", str(a.claims),
         "--manifest", f"video/public/{shots_dir}/manifest.json",
         "--out", str(props)])

    print("\n■ 4/4 描画する（尺が長いと時間がかかる）")
    render = ["./render.sh", "still" if a.still else "render",
              "Documentary", str(out)]
    if a.still:
        render.append(f"--frame={a.still}")
    subprocess.run(render, cwd=ROOT / "video",
                   env={**__import__("os").environ, "PROPS": props.name}, check=True)

    mins = (time.time() - began) / 60
    print(f"\n完成 -> {out}  （{mins:.1f}分）")
    credits = ROOT / "video" / "public" / shots_dir / "credits.txt"
    if credits.exists():
        print(f"概要欄に貼るクレジット -> {credits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
