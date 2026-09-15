from topic_scout.classify import tag
from topic_scout.fetch import Video


def mk(title, duration=1800, channel="テストch", views=100_000, desc=""):
    return Video(video_id="x", title=title, channel=channel, channel_id="c",
                 view_count=views, duration=duration, description=desc, verified=False)


def test_yukkuri_detected_in_title_and_channel():
    assert tag(mk("ヴォイニッチ手稿の謎【ゆっくり解説】")).is_yukkuri
    assert tag(mk("普通のタイトル", channel="世界の未解明ミステリー【ゆっくり解説】")).is_yukkuri


def test_claims_solved_marks_low_effort():
    t = tag(mk("ついに解読！600年の謎が判明した"))
    assert t.claims_solved and t.is_low_effort


def test_serious_longform_requires_duration_and_clean_framing():
    assert tag(mk("ヴォイニッチ写本の謎 この本はデタラメなのか？", duration=1800)).is_serious_longform
    # 25分未満は対象外
    assert not tag(mk("ヴォイニッチ写本の謎", duration=900)).is_serious_longform
    # 煽りが付いていれば長尺でも対象外
    assert not tag(mk("ついに解読！ヴォイニッチ手稿", duration=3000)).is_serious_longform
    assert not tag(mk("【ゆっくり解説】ヴォイニッチ手稿", duration=3000)).is_serious_longform


def test_channel_own_title_is_not_flagged_as_sensational():
    """自チャンネルの実タイトルが煽り判定されないこと（過検出の回帰テスト）。"""
    t = tag(mk("【AI解析でどこまで分かったのか】奇書ヴォイニッチ手稿解読の600年", duration=3159))
    assert not t.claims_solved
    assert not t.is_low_effort
    assert t.is_serious_longform
    assert t.has_ai_angle
