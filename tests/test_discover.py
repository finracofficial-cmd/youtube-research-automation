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


def test_checked_topics_round_trip():
    """Issueに出した題材を、チェックされた状態から正しく読み戻せるか。

    ここがずれると、選んでいない題材の台本を書いてしまう。1本あたり
    取材と描画で1時間半かかるので、取り違えの代償が大きい。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from topic_scout.review import checked_subjects, to_checklist

    rows = [
        {"query": "ヴォイニッチ手稿", "verdict": "狙う", "score": "0.76",
         "demand": "0.95", "gap": "1.0", "trend": "0.78",
         "views_max": "5717338", "reasons": "需要あり×空白あり"},
        {"query": "地上絵", "verdict": "狙う", "score": "0.61",
         "demand": "0.97", "gap": "0.81", "trend": "0.69",
         "views_max": "5724500", "reasons": ""},
        {"query": "スフィンクス", "verdict": "狙う", "score": "0.58",
         "demand": "0.92", "gap": "1.0", "trend": "0.60",
         "views_max": "10560169", "reasons": ""},
    ]
    body = to_checklist(rows)
    # 出した直後は、どれも選ばれていない
    assert checked_subjects(body) == []

    # 1件目と3件目にチェックを入れる
    picked = body.replace("- [ ] **ヴォイニッチ手稿**", "- [x] **ヴォイニッチ手稿**")
    picked = picked.replace("- [ ] **スフィンクス**", "- [X] **スフィンクス**")
    assert checked_subjects(picked) == ["ヴォイニッチ手稿", "スフィンクス"]


def test_unscored_topics_still_get_listed():
    """「狙う」が1件も無い回でも、候補は出す。空のIssueは判断材料にならない。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from topic_scout.review import to_checklist

    rows = [{"query": "見送り題材", "verdict": "見送り", "score": "0.1",
             "demand": "0.2", "gap": "0.0", "trend": "0.5",
             "views_max": "1000", "reasons": ""}]
    assert "見送り題材" in to_checklist(rows)
