import pytest

from topic_scout.features import TopicFeatures
from topic_scout.score import demand, gap, score_topic


def feats(**kw):
    base = dict(query="q", n_videos=30, views_p50=50_000.0, views_p75=300_000.0,
                views_max=1_000_000, n_over_100k=10, distinct_channels_over_100k=8,
                low_effort_ratio=0.7, median_duration=1200, n_serious_longform=1,
                best_serious_views=200_000, ai_angle_ratio=0.2)
    base.update(kw)
    return TopicFeatures(**base)


def test_no_demand_kills_the_score():
    """需要ゼロなら他がどれだけ良くても死ぬ（橋本環奈回の教訓）。"""
    f = feats(views_p75=0.0, views_max=0, n_over_100k=0, distinct_channels_over_100k=0)
    assert demand(f) == pytest.approx(0.0)
    assert score_topic(f).score == pytest.approx(0.0)
    assert score_topic(f).verdict == "見送り"


def test_saturated_supply_kills_the_score():
    """真面目な長尺が並んでいる題材は空白ゼロ（ピラミッド回の教訓）。"""
    f = feats(n_serious_longform=9, best_serious_views=2_150_000)
    assert gap(f) == pytest.approx(0.0)
    assert score_topic(f).score == pytest.approx(0.0)


def test_single_successful_serious_video_does_not_close_the_gap():
    """62万再生の良質番組が1本あっても、まだ空白は残る（ヴォイニッチの実測）。"""
    f = feats(n_serious_longform=1, best_serious_views=620_000)
    assert gap(f) > 0.5


def test_gap_shrinks_as_serious_competitors_accumulate():
    g = [gap(feats(n_serious_longform=n, best_serious_views=200_000)) for n in (1, 3, 6)]
    assert g[0] > g[1] > g[2]
    assert g[2] == pytest.approx(0.0)


def test_trend_is_an_amplifier_not_a_gate():
    """時流ワードが無くても score はゼロにならない（T には下限がある）。"""
    s = score_topic(feats(ai_angle_ratio=0.0))
    assert s.trend == pytest.approx(0.6)
    assert s.score > 0.0
