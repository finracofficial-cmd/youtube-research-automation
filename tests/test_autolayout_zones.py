import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
from autolayout import (  # noqa: E402
    MAX_HOLD, ZONE_GAP, Cue, Line, build, classify, coverage, hold, schedule,
)


def cue(kind, start, dur, zone):
    return Cue(kind, start, dur, zone)


def test_different_zones_can_show_at_the_same_time():
    """1画面1部品に絞ったせいで被覆率が6.6%しか出なかった。ゾーンが違えば同時に出す。"""
    kept = schedule([cue("stat", 0, 5, "right"), cue("quote", 0, 5, "left")])
    assert len(kept) == 2


def test_the_same_zone_does_not_overlap():
    kept = schedule([cue("stat", 0, 5, "right"), cue("chips", 2, 5, "right")])
    assert len(kept) == 1


def test_same_zone_reuse_needs_a_gap():
    a, b = cue("stat", 0, 5, "right"), cue("chips", 5 + ZONE_GAP + 0.1, 3, "right")
    assert len(schedule([a, b])) == 2


def test_concurrent_display_is_capped():
    zones = ["left", "right", "center", "lower", "corner"]
    kept = schedule([cue("stat", 0, 5, z) for z in zones], max_concurrent=3)
    assert len(kept) == 3


def test_hold_extends_a_cue_until_the_next_in_its_zone():
    """1文で消すと画面が寂しい。次の部品が来るまで出しっぱなしにする。"""
    a, b = cue("stat", 0, 3, "right"), cue("chips", 10, 3, "right")
    hold([a, b], duration=60)
    assert a.durationSec == pytest.approx(10 - ZONE_GAP)


def test_hold_is_capped():
    a = cue("stat", 0, 3, "right")
    hold([a], duration=600)
    assert a.durationSec == pytest.approx(MAX_HOLD)


def test_hold_does_not_shorten_a_cue():
    a = cue("stat", 0, 9.0, "right")
    b = cue("chips", 3.0, 3, "right")
    hold([a, b], duration=60)
    assert a.durationSec >= 9.0


def test_hold_keeps_zones_independent():
    a, b = cue("stat", 0, 3, "right"), cue("quote", 5, 3, "left")
    hold([a, b], duration=60)
    assert a.durationSec == pytest.approx(MAX_HOLD)   # right は他に無い


def test_coverage_merges_overlapping_spans():
    assert coverage([cue("a", 0, 10, "left"), cue("b", 5, 10, "right")], 30) == pytest.approx(0.5)


def test_coverage_of_nothing_is_zero():
    assert coverage([], 100) == 0.0


def test_numbers_are_spread_across_zones():
    """数値系を1ゾーンに積むと他が空く。交互に振る。"""
    lines = [Line(startSec=i * 6, durationSec=6, text=f"高さは{i+1}メートルである。")
             for i in range(6)]
    zones = {c.zone for c in classify(lines) if c.kind == "stat"}
    assert len(zones) >= 2


def test_build_emits_the_new_component_arrays():
    lines = [Line(startSec=0, durationSec=5, text="柱の高さは7メートルある。"),
             Line(startSec=5, durationSec=5, text="1600年から2000年までの記録が残る。")]
    props = build(lines, duration=30)
    assert props["stats"] and props["timelines"]


def test_bce_prefix_is_kept():
    """「紀元前1世紀」の接頭辞を落とすと2000年ずれた別の事実になる。実際に落とした。"""
    cues = [c for c in classify([Line(startSec=0, durationSec=5,
                                      text="沈没船の年代は紀元前1世紀である。")])
            if c.kind == "stat"]
    assert cues and cues[0].payload["value"] == "紀元前1世紀"


def test_trivial_counts_are_not_blown_up():
    """「潜水夫が1人死亡した」の1人を巨大表示すると滑稽になる。"""
    for text in ("潜水夫が1人死亡した。", "2枚の歯車を噛ませていた。"):
        kinds = [c.kind for c in classify([Line(startSec=0, durationSec=5, text=text)])]
        assert "stat" not in kinds, text


def test_large_counts_still_pass():
    cues = [c for c in classify([Line(startSec=0, durationSec=5, text="歯が223枚ある。")])
            if c.kind == "stat"]
    assert cues and cues[0].payload["value"] == "223枚"


def test_labels_do_not_cut_mid_word():
    cues = [c for c in classify([Line(startSec=0, durationSec=5,
        text="50万年前の岩に埋まっていたという点火プラグである。")]) if c.kind == "stat"]
    assert cues and not cues[0].payload["label"].endswith("点火プ")


def test_role_is_not_taken_from_a_negation():
    """「地質学者ではない」から役割を取ると逆の意味になる。実際に取った。"""
    kinds = [c.kind for c in classify([Line(startSec=0, durationSec=5,
        text="ハプグッド自身は地質学者ではない。")])]
    assert "portrait" not in kinds


def test_organisation_is_not_treated_as_a_person():
    """「オスマン帝国の提督ピリ・レイス」から「オスマン」を人名として拾った。"""
    kinds = [c.kind for c in classify([Line(startSec=0, durationSec=5,
        text="描いたのはオスマン帝国の提督ピリ・レイスである。")])]
    assert "portrait" not in kinds
