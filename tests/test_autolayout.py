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


def test_stat_keeps_the_trailing_qualifier():
    """「以上」を落とすと断定になる。実測で「歯車は30個以上」を「30個」と出した。

    数字の後ろに付く一語で、下限が確定値に変わる。画面に出る以上、
    ナレーションより強いことを言ってはいけない。
    """
    cases = [
        ("判明したことを並べる。歯車は30個以上。", "30個以上"),
        ("重さは6トン前後とされる。", "6トン前後"),
        ("厚さは3センチ未満だった。", "3センチ未満"),
        ("最大のものは歯が223枚。", "223枚"),
    ]
    for text, want in cases:
        stats = [c for c in classify([Line(0.0, 5.0, text)]) if c.kind == "stat"]
        assert stats, text
        assert stats[0].payload["value"] == want, (text, stats[0].payload["value"])


def test_stat_value_is_contained_in_the_line():
    """大書きした値は、必ず台本のその行に現れている文字列でなければならない。"""
    for text in ["歯車は30個以上。", "約50万年前の岩に埋まっていた。",
                 "重さは6トン前後とされる。"]:
        for c in classify([Line(0.0, 5.0, text)]):
            if c.kind == "stat":
                assert c.payload["value"].replace(" ", "") in text.replace(" ", "")


def test_stat_label_is_a_readable_noun_phrase():
    """文をそのまま切ると、途中から始まって助詞で終わる断片になる。

    実測で「だから手元の20枚あまりを」がカードの見出しに出た。
    """
    cases = [
        ("だから手元の20枚あまりを、順に並べ直した。", "手元の20枚あまり"),
        ("判明したことを並べる。歯車は30個以上。", "歯車は30個以上"),
        ("つまり、最大のものは歯が223枚あった。", "最大のものは歯が223枚"),
        ("この柱は、高さが7メートルほどある。", "高さが7メートルほど"),
    ]
    for text, want in cases:
        stats = [c for c in classify([Line(0.0, 5.0, text)]) if c.kind == "stat"]
        assert stats, text
        assert stats[0].payload["label"] == want, (text, stats[0].payload["label"])


def test_stat_keeps_hiragana_qualifiers():
    """「あまり」「ほど」を落とすと、およその数が確定値になる。"""
    for text, want in [("20枚あまりを数えた。", "20枚あまり"),
                       ("高さは7メートルほどある。", "7メートルほど")]:
        stats = [c for c in classify([Line(0.0, 5.0, text)]) if c.kind == "stat"]
        assert stats and stats[0].payload["value"] == want, text


def test_caveat_needs_content_not_just_an_announcement():
    """留保があると予告するだけの文をカードに出さない。

    実測で「ただし、と付け加えておきたい」がそのまま画面に載った。
    """
    def has(text):
        return any(c.kind == "caveat" for c in classify([Line(0.0, 5.0, text)]))

    assert not has("ただし、と付け加えておきたい。")
    assert not has("ただし、と断っておく。")
    assert not has("ただし。")
    assert has("ただし、決着はしていない。")
    assert has("とはいえ、年代の根拠は薄い。")


def test_stat_label_is_dropped_when_it_repeats_the_value():
    """数値で始まる文だと見出しが値と同じ文字列になる。

    実測で「100メートル」が上下に二度並んだ。同じ語を重ねても情報が増えない。
    """
    stats = [c for c in classify([Line(0.0, 5.0, "100メートルを40分で進んだ。")])
             if c.kind == "stat"]
    assert stats and stats[0].payload["label"] == ""
    # 文脈のある見出しは残す
    stats = [c for c in classify([Line(0.0, 5.0, "高さ5メートルの石柱。")])
             if c.kind == "stat"]
    assert stats and stats[0].payload["label"] == "高さ5メートル"


def test_range_is_shown_as_a_span_not_a_single_number():
    """「10トンから15トン」を大書きの数字にすると幅が消え、確定値に見える。"""
    cues = [c for c in classify([Line(0.0, 5.0, "重さは10トンから15トンほど。")])
            if c.kind == "range"]
    assert cues
    p = cues[0].payload
    assert p["low"] == "10トン" and p["high"] == "15トン"
    assert 0 <= p["from"] < p["to"] <= 1


def test_a_range_sentence_does_not_also_emit_number_cards():
    """同じ数字が範囲バー・数値カード・字幕の3箇所に並ぶ。実測でそうなった。"""
    kinds = {c.kind for c in classify([Line(0.0, 5.0, "1本2トンから4トン。")])}
    assert "range" in kinds
    assert "stat" not in kinds and "chips" not in kinds


def test_a_backwards_range_is_ignored():
    """上限が下限より小さい並びは範囲ではない。棒が裏返る。"""
    cues = [c for c in classify([Line(0.0, 5.0, "15トンから10トンへ減った。")])
            if c.kind == "range"]
    assert not cues
