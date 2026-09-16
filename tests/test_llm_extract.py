import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
from autolayout import MAX_DURATION, MIN_DURATION, Line  # noqa: E402
from llm_extract import (  # noqa: E402
    LLMUnavailable, build_messages, call, parse,
)


LINES = [
    Line(startSec=0, durationSec=4, text="沈没船の年代は紀元前1世紀である。"),
    Line(startSec=4, durationSec=4, text="ハプグッド自身は地質学者ではない。"),
    Line(startSec=8, durationSec=4, text="歯車は30個以上ある。"),
]


def resp(cues):
    return json.dumps({"cues": cues}, ensure_ascii=False)


def test_value_present_in_the_line_is_accepted():
    r = parse(resp([{"line": 0, "kind": "stat", "zone": "right",
                     "payload": {"value": "紀元前1世紀", "label": "沈没船の年代"}}]), LINES)
    assert len(r.cues) == 1 and r.rejected == 0
    assert r.cues[0].payload["value"] == "紀元前1世紀"


def test_invented_value_is_rejected():
    """LLMが台本に無い数字を書くことがある。ここで止める。"""
    r = parse(resp([{"line": 2, "kind": "stat",
                     "payload": {"value": "300個", "label": "歯車"}}]), LINES)
    assert r.cues == [] and r.rejected == 1


def test_dropping_a_prefix_is_rejected():
    """「紀元前」を落とすと2000年ずれる。原文に無い表記なので落ちる。"""
    r = parse(resp([{"line": 0, "kind": "stat", "payload": {"value": "1世紀"}}]), LINES)
    assert r.rejected == 1


def test_invented_person_name_is_rejected():
    r = parse(resp([{"line": 1, "kind": "portrait",
                     "payload": {"name": "ピリ・レイス", "role": "提督"}}]), LINES)
    assert r.rejected == 1


def test_name_present_in_the_line_is_accepted():
    r = parse(resp([{"line": 1, "kind": "portrait",
                     "payload": {"name": "ハプグッド", "role": "著者"}}]), LINES)
    assert len(r.cues) == 1


def test_out_of_range_line_is_rejected():
    r = parse(resp([{"line": 99, "kind": "stat", "payload": {"value": "30個"}}]), LINES)
    assert r.rejected == 1


def test_unknown_kind_is_rejected():
    r = parse(resp([{"line": 2, "kind": "fireworks", "payload": {}}]), LINES)
    assert r.rejected == 1


def test_unknown_zone_falls_back_to_center():
    r = parse(resp([{"line": 2, "kind": "stat", "zone": "nowhere",
                     "payload": {"value": "30個"}}]), LINES)
    assert r.cues[0].zone == "center"


def test_timeline_marks_are_checked_against_the_line():
    lines = [Line(startSec=0, durationSec=4, text="1900年から1901年にかけて回収された。")]
    ok = parse(resp([{"line": 0, "kind": "timeline",
                      "payload": {"marks": [{"label": "1900年"}, {"label": "1901年"}]}}]), lines)
    bad = parse(resp([{"line": 0, "kind": "timeline",
                       "payload": {"marks": [{"label": "1950年"}]}}]), lines)
    assert len(ok.cues) == 1 and bad.rejected == 1


def test_full_width_digits_are_normalised():
    lines = [Line(startSec=0, durationSec=4, text="高さは１４６メートルある。")]
    r = parse(resp([{"line": 0, "kind": "stat", "payload": {"value": "146メートル"}}]), lines)
    assert len(r.cues) == 1


def test_payload_without_checkable_fields_passes():
    """caveat のように原文をそのまま載せる部品は、値の照合対象が無い。"""
    r = parse(resp([{"line": 1, "kind": "caveat", "payload": {"text": "地質学者ではない"}}]), LINES)
    assert len(r.cues) == 1


def test_broken_json_is_reported_not_raised():
    r = parse("これはJSONではない", LINES)
    assert r.cues == [] and "JSON" in r.reason


def test_fenced_json_is_unwrapped():
    raw = "```json\n" + resp([{"line": 2, "kind": "stat", "payload": {"value": "30個"}}]) + "\n```"
    assert len(parse(raw, LINES).cues) == 1


def test_duration_is_clamped():
    lines = [Line(startSec=0, durationSec=60, text="歯車は30個ある。")]
    r = parse(resp([{"line": 0, "kind": "stat", "payload": {"value": "30個"}}]), lines)
    assert MIN_DURATION <= r.cues[0].durationSec <= MAX_DURATION


def test_prompt_includes_line_numbers_and_the_rules():
    msgs = build_messages(LINES, 0, 3)
    assert "0: 沈没船" in msgs[1]["content"]
    assert "紀元前" in msgs[0]["content"]      # 接頭辞を落とすなという指示
    assert "組織名を人名にしない" in msgs[0]["content"]


def test_call_requires_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        call([{"role": "user", "content": "x"}])


def test_value_with_its_qualifier_still_passes():
    """接頭辞を含めて出していれば正しいので通す。"""
    r = parse(resp([{"line": 0, "kind": "stat", "payload": {"value": "紀元前1世紀"}}]), LINES)
    assert len(r.cues) == 1


def test_qualifier_check_does_not_block_plain_values():
    """原文に接頭辞が無い値は当然通る。"""
    lines = [Line(startSec=0, durationSec=4, text="高さは146メートルある。")]
    r = parse(resp([{"line": 0, "kind": "stat", "payload": {"value": "146メートル"}}]), lines)
    assert len(r.cues) == 1


def test_approx_prefix_must_be_kept():
    lines = [Line(startSec=0, durationSec=4, text="重さは約6トンである。")]
    assert parse(resp([{"line": 0, "kind": "stat",
                        "payload": {"value": "6トン"}}]), lines).rejected == 1
    assert len(parse(resp([{"line": 0, "kind": "stat",
                            "payload": {"value": "約6トン"}}]), lines).cues) == 1
