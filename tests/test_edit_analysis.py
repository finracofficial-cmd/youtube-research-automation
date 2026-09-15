import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
from analyze_edit import detect_cuts, probe_duration, stats  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg が無い")


@pytest.fixture(scope="module")
def three_cut_video(tmp_path_factory) -> Path:
    """2秒ごとに色が変わる6秒の動画。カットは2箇所あるのが正解。

    ffmpeg のシーン検出は輝度平面しか見ない。red と green はどちらも Y=81 なので、
    色名で選ぶと検出できない組み合わせになる（最初それで落ちた）。
    輝度が明確に違う3色を使う。
    """
    d = tmp_path_factory.mktemp("edit")
    parts = []
    for i, color in enumerate(("black", "gray", "white")):
        p = d / f"p{i}.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c={color}:s=320x180:r=15:d=2",
             "-pix_fmt", "yuv420p", "-y", str(p)], check=True)
        parts.append(p)
    lst = d / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    out = d / "joined.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", "-y", str(out)], check=True)
    return out


def test_detects_the_known_cuts(three_cut_video):
    cuts = detect_cuts(three_cut_video, threshold=0.3)
    assert len(cuts) == 2, f"2箇所のはずが {cuts}"
    assert cuts[0] == pytest.approx(2.0, abs=0.3)
    assert cuts[1] == pytest.approx(4.0, abs=0.3)


def test_duration_is_read_correctly(three_cut_video):
    assert probe_duration(three_cut_video) == pytest.approx(6.0, abs=0.3)


def test_stats_derive_shot_lengths_from_cuts():
    s = stats([2.0, 4.0], 6.0)
    assert s["n_cuts"] == 2
    assert s["cuts_per_min"] == pytest.approx(20.0, abs=0.1)
    assert s["shot_len_mean"] == pytest.approx(2.0, abs=0.01)
    assert s["shot_len_median"] == pytest.approx(2.0, abs=0.01)


def test_stats_handle_a_video_with_no_cuts():
    s = stats([], 30.0)
    assert s["n_cuts"] == 0
    assert s["shot_len_mean"] == pytest.approx(30.0)


def test_stats_count_short_and_long_shots():
    s = stats([1.0, 2.0, 20.0], 40.0)
    assert s["shots_under_3s"] == 2   # 0-1, 1-2
    assert s["shots_over_15s"] == 2   # 2-20, 20-40
