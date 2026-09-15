"""動画からカット点を検出し、フレームを保存して編集のリズムを測る。

台本を字幕から解析したのと同じことを、映像側でやる。
知りたいのは「1カット何秒か」「1分あたり何カットか」で、
それが分かれば build_props.py の shot-sec を実測値に合わせられる。

参照動画から取り出すフレームは寸法の計測用。
映像そのものは制作者の著作物なので、自分の動画には使わない。
素材はPD/CCのものを別途集める。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def detect_cuts(path: Path, threshold: float = 0.30) -> list[float]:
    """シーン変化の時刻（秒）を返す。threshold が小さいほど敏感。

    注意: ffmpeg のシーン検出は輝度平面しか見ない。
    明るさが近い画どうしの切り替わりは、色がまったく違っても検出されない
    （ffmpeg の red と green はどちらも Y=81 なので差がゼロになる）。
    暗い写本画像が続くような構成では取りこぼすので、threshold を下げて調整する。
    """
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path), "-filter:v", f"select='gt(scene,{threshold})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True)
    times = []
    for m in re.finditer(r"pts_time:([0-9.]+)", proc.stderr):
        times.append(float(m.group(1)))
    return sorted(set(times))


def save_frames(path: Path, times: list[float], out_dir: Path, width: int = 640) -> int:
    """各カットの頭のフレームを1枚ずつ保存する。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for i, t in enumerate(times):
        dst = out_dir / f"cut_{i:04d}_{t:08.2f}.jpg"
        r = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path),
             "-frames:v", "1", "-vf", f"scale={width}:-1", "-q:v", "5", "-y", str(dst)],
            capture_output=True)
        if r.returncode == 0 and dst.exists():
            saved += 1
    return saved


def stats(cuts: list[float], duration: float) -> dict:
    """カット点から編集のリズムを出す。"""
    marks = [0.0] + cuts + [duration]
    lengths = [b - a for a, b in zip(marks, marks[1:]) if b > a]
    if not lengths:
        return {"duration_sec": duration, "n_cuts": 0}
    return {
        "duration_sec": round(duration, 2),
        "n_cuts": len(cuts),
        "cuts_per_min": round(len(cuts) / (duration / 60), 2),
        "shot_len_mean": round(statistics.mean(lengths), 2),
        "shot_len_median": round(statistics.median(lengths), 2),
        "shot_len_min": round(min(lengths), 2),
        "shot_len_max": round(max(lengths), 2),
        "shots_under_3s": sum(l < 3 for l in lengths),
        "shots_over_15s": sum(l > 15 for l in lengths),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--frames-dir", default=None, help="指定するとカット頭のフレームを保存")
    ap.add_argument("--out", default=None, help="統計のJSON出力先")
    a = ap.parse_args()

    path = Path(a.video)
    duration = probe_duration(path)
    cuts = detect_cuts(path, a.threshold)
    s = stats(cuts, duration)

    print(f"尺 {s['duration_sec']}秒 / カット {s['n_cuts']}箇所")
    for k in ("cuts_per_min", "shot_len_mean", "shot_len_median",
              "shot_len_min", "shot_len_max", "shots_under_3s", "shots_over_15s"):
        if k in s:
            print(f"  {k:<18}{s[k]}")

    if a.frames_dir:
        n = save_frames(path, cuts, Path(a.frames_dir))
        print(f"フレーム {n}枚 -> {a.frames_dir}")
    if a.out:
        Path(a.out).write_text(json.dumps({"stats": s, "cuts": cuts},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
