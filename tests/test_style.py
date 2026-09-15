import re
from pathlib import Path

import pytest

from script_engine.style import analyze, validate

TRANSCRIPT = Path("analysis/transcripts/voynich_AE6JGXXEBQU.md")


def _reference_body() -> str:
    text = TRANSCRIPT.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"^`\d\d:\d\d` ", "", l)
                     for l in text.splitlines() if re.match(r"^`\d\d:\d\d`", l))


def test_reference_video_passes_its_own_profile():
    """型の出どころである動画が、その型のバリデータを通ること。
    ここが落ちたら閾値か抽出のどちらかが壊れている。"""
    m = validate(_reference_body(), 3159)
    assert m.ok, m.violations


def test_reference_metrics_match_the_documented_measurements():
    m = analyze(_reference_body(), 3159)
    assert 20.0 <= m.avg_sentence_len <= 23.0     # 文書上 21.6
    assert 340 <= m.chars_per_min <= 375          # 文書上 358
    assert m.plain_form_ratio > 0.95              # 常体161 : 敬体2
    assert m.numerics_per_min > 7.0               # 文書上 7.9


def test_polite_form_script_is_rejected():
    text = "これはペンです。" * 200
    m = validate(text, 600)
    assert not m.ok
    assert any("常体率" in v for v in m.violations)


def test_chatty_narration_is_rejected():
    text = ("皆さんはどう思いますか。" * 4) + ("事実である。" * 300)
    m = validate(text, 600)
    assert any("馴れ合い" in v for v in m.violations)


def test_long_winded_script_is_rejected():
    text = ("この非常に長い一文は事実を詰め込みすぎており読み上げても頭に入らない構造になっているのである。" * 60)
    m = validate(text, 600)
    assert any("平均文長" in v for v in m.violations)


def test_zero_duration_is_an_error():
    with pytest.raises(ValueError):
        analyze("事実である。", 0)


def test_reference_scores_near_perfect_fidelity():
    """参照動画自身の忠実度は1.0に近いこと（指標の定義が壊れていないかの確認）。"""
    m = analyze(_reference_body(), 3159)
    assert m.fidelity > 0.97


def test_fidelity_falls_when_density_drops():
    """レンジ内でも、数字が薄い台本は忠実度が下がること。"""
    dense = "1901年に30個の歯車が出た。" * 120
    thin = "歯車が出たのである。" * 150
    from script_engine.style import analyze as a
    assert a(dense, 600).fidelity > a(thin, 600).fidelity
