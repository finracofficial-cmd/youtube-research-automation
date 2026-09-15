import pytest

from script_engine.beats import FLAGSHIP, BUNDLE, get


@pytest.mark.parametrize("sheet", [FLAGSHIP, BUNDLE])
def test_shares_sum_to_one(sheet):
    """share の合計が1を外れると、端数を吸う最後のビートが潰れる（実際に潰れた）。"""
    assert sum(b.share for b in sheet.beats) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("sheet", [FLAGSHIP, BUNDLE])
def test_allocation_sums_to_exact_duration(sheet):
    alloc = sheet.allocate(1800)
    assert sum(sec for _, sec in alloc) == 1800


@pytest.mark.parametrize("sheet", [FLAGSHIP, BUNDLE])
def test_no_beat_is_starved(sheet):
    """どのビートも尺が正で、想定比率から大きく外れないこと。"""
    total = 3000
    for beat, sec in sheet.allocate(total):
        assert sec > 0, f"{beat.key} に尺が配られていない"
        assert abs(sec / total - beat.share) < 0.01, f"{beat.key} の配分が share と乖離"


def test_cta_is_the_only_polite_form_beat():
    cta = next(b for b in FLAGSHIP.beats if b.key == "cta")
    assert any("敬体" in r for r in cta.rules)


def test_bundle_claim_count_is_configurable():
    sheet = get("bundle", n_claims=9)
    assert sum(1 for b in sheet.beats if b.key.startswith("claim")) == 9
    assert sum(b.share for b in sheet.beats) == pytest.approx(1.0, abs=1e-6)


def test_fixed_lines_carry_placeholders():
    fixed = {b.key: b.fixed_line for b in FLAGSHIP.beats if b.fixed_line}
    assert "{genre}" in fixed["channel_claim"]
    assert "{subject}" in fixed["launch"]


def test_unknown_sheet_raises():
    with pytest.raises(ValueError):
        get("nope")
