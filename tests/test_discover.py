from topic_scout.discover import extract_terms, _strip_stopword_affixes


def test_strips_boilerplate_affixes_from_kanji_runs():
    """漢字を貪欲に拾うと定型語がくっつく。端から剥がして題材名だけ残す。"""
    assert _strip_stopword_affixes("死海文書最大") == "死海文書"
    assert _strip_stopword_affixes("徹底解説") == ""
    assert _strip_stopword_affixes("最新科学") == ""


def test_extracts_topic_name_and_drops_boilerplate():
    terms = extract_terms("【ゆっくり解説】死海文書最大の謎！バチカンが隠した秘密を徹底解説")
    assert "死海文書" in terms
    assert not any(t in {"徹底解説", "ゆっくり", "死海文書最大"} for t in terms)


def test_prefers_the_longest_form_within_a_title():
    """「峠事件」のような断片は、より長い語があるとき落とす。"""
    terms = extract_terms("なぜ裸足で外へ？ディアトロフ峠事件、60年後の真相")
    assert "ディアトロフ峠事件" in terms
    assert "峠事件" not in terms
    assert "ディアトロフ" not in terms


def test_bracketed_boilerplate_is_removed_before_extraction():
    assert "ゆっくり解説" not in extract_terms("ストーンヘンジの謎【ゆっくり解説】")
    assert "ストーンヘンジ" in extract_terms("ストーンヘンジの謎【ゆっくり解説】")


def test_short_and_stopword_only_terms_are_dropped():
    assert extract_terms("世界の謎を徹底解説【ゆっくり解説】") == set()


def test_exact_only_stopwords_are_not_stripped_as_suffixes():
    """「テクノロジー」単体は落とすが、ロストテクノロジーは壊さない（回帰テスト）。"""
    assert _strip_stopword_affixes("ロストテクノロジー") == "ロストテクノロジー"
    assert _strip_stopword_affixes("テクノロジー") == ""


def test_bound_morpheme_endings_are_rejected():
    """「再現不(可能)」のような切れ端を弾く。"""
    assert _strip_stopword_affixes("再現不") == ""
    assert _strip_stopword_affixes("超高") == ""
    assert _strip_stopword_affixes("ヴォイニッチ手稿") == "ヴォイニッチ手稿"
