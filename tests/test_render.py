from script_engine.render import Topic, build_prompt
from script_engine.style import validate, analyze


def test_prompt_fills_fixed_line_placeholders():
    p = build_prompt(Topic("巨石遺跡", genre="古代の謎"))
    assert "こうした古代の謎を" in p
    assert "巨石遺跡へと迫っていこう" in p
    assert "{genre}" not in p and "{subject}" not in p


def test_bundle_uses_one_beat_per_claim():
    claims = ("主張A", "主張B", "主張C", "主張D")
    p = build_prompt(Topic("巨石遺跡", claims=claims), kind="bundle")
    for i in range(1, 5):
        assert f"### 第{i}主張" in p
    assert "### 第5主張" not in p


def test_per_beat_char_budget_is_emitted():
    """LLMに尺ではなく字数で渡さないと、長さが合わない。"""
    p = build_prompt(Topic("巨石遺跡"), duration_sec=1800)
    assert "秒 / 約" in p and "字）" in p


def test_sources_restrict_citations():
    p = build_prompt(Topic("巨石遺跡", sources=("Nature 552, 386 (2017)",)))
    assert "これ以外を出典として書かない" in p
    assert "Nature 552, 386 (2017)" in p


def test_prompt_bans_the_competitor_vocabulary():
    p = build_prompt(Topic("巨石遺跡"))
    assert "「ついに解読」「衝撃の真実」は使わない" in p


def test_char_budget_is_inflated_against_measured_shortfall():
    """初稿は実測で目標の約0.7倍にしかならないので、要求側を割り増しする。"""
    from script_engine.render import DRAFT_INFLATION
    assert DRAFT_INFLATION > 1.0
    p = build_prompt(Topic("巨石遺跡"), duration_sec=900)
    # 900秒 × 365字/分 = 5475字。割り増し後はそれより多いこと
    import re
    total = int(re.search(r"目安の総文字数: (\d+)字", p).group(1))
    assert total > 5475
