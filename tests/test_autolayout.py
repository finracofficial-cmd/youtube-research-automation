import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
from autolayout import (  # noqa: E402
    ZONE_GAP, Cue, Line, build, classify, schedule,
)


def lines(*texts, step=3.0):
    return [Line(startSec=i * step, durationSec=step, text=t) for i, t in enumerate(texts)]


def kinds(cues):
    return [c.kind for c in cues]


def test_paper_with_a_year_becomes_a_document_card():
    assert "document" in kinds(classify(lines("結果は2006年にネイチャーへ載る。")))


def test_channel_declaration_is_not_mistaken_for_a_paper():
    """宣言文は「論文」を含むが出典の提示ではない（実際に誤検出した）。"""
    assert classify(lines("当チャンネルでは、論文と一次資料からひも解いていく。")) == []


def test_quote_lead_pulls_the_following_sentences_as_the_body():
    cues = [c for c in classify(lines("語られている説明はこうだ。",
                                      "古代インドには失われた技術があった。"))
            if c.kind == "quote"]
    assert len(cues) == 1
    assert "失われた技術" in cues[0].payload["translation"]
    assert cues[0].startSec == pytest.approx(3.0)  # 引用の中身に合わせて出す


def test_quote_lead_without_a_following_line_is_dropped():
    assert "quote" not in kinds(classify(lines("主張はこうだ。")))


def test_list_declaration_becomes_a_card_row_with_that_count():
    cues = [c for c in classify(lines("この動画では、語られている5つを並べた。"))
            if c.kind == "cardrow"]
    assert cues[0].payload["count"] == 5


def test_kanji_numerals_are_understood():
    cues = [c for c in classify(lines("話は四つに分かれる。")) if c.kind == "cardrow"]
    assert cues[0].payload["count"] == 4


def test_implausible_counts_are_ignored():
    assert "cardrow" not in kinds(classify(lines("1900年代には20つに分かれる。")))


def test_caveat_line_becomes_a_side_note():
    assert "caveat" in kinds(classify(lines("ただし、決着はしていない。")))


def test_number_dense_line_produces_a_numeric_overlay():
    """単位つきなら stat、単位が無く数字が多ければ chips。どちらかは出る。"""
    cues = classify(lines("高さは146メートル、重さは6トン、建造は2500年前である。"))
    assert {"stat", "chips"} & set(kinds(cues))


def test_ordinary_narration_produces_nothing():
    """数値も引用も無い文からは何も出さない。"""
    assert classify(lines("石をどけると、下から明るい地面が出てくる。")) == []


def test_schedule_drops_overlapping_cues_in_the_same_zone():
    """ゾーン制に変えたので、重なり判定はゾーン単位になった。"""
    a = Cue("quote", 0.0, 5.0, "center")
    b = Cue("chips", 5.1, 4.0, "center")      # 同じゾーンで間隔が足りない
    c = Cue("document", 20.0, 4.0, "center")
    assert kinds(schedule([a, b, c])) == ["quote", "document"]


def test_schedule_keeps_cues_separated_by_the_zone_gap():
    a = Cue("quote", 0.0, 5.0, "center")
    b = Cue("chips", 5.0 + ZONE_GAP + 0.1, 4.0, "center")
    assert len(schedule([a, b])) == 2


def test_schedule_is_order_independent():
    a = Cue("quote", 30.0, 4.0, "center")
    b = Cue("document", 0.0, 4.0, "center")
    assert [c.startSec for c in schedule([a, b])] == [0.0, 30.0]


def test_build_routes_each_kind_to_its_own_props_array():
    props = build(lines("結果は2006年にネイチャーへ載る。", "……", "……", "……",
                        "ただし、決着はしていない。"))
    assert len(props["documentCards"]) == 1
    assert len(props["quoteCards"]) == 1
    assert props["quoteCards"][0]["side"] == "right"   # 留保は逆側に置く
