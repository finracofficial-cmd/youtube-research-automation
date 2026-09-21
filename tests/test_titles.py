"""題名の候補。

参考chの実測3本で、当たった題と外れた題の形が違った。

  140万回  【AI解析でどこまで分かったのか】奇書ヴォイニッチ手稿解読の600年
   4.7万回  ピラミッドの謎を、論文と1次資料でひも解く【AIが発見した？…】
   1.3万回  橋本環奈の息分子を175億個吸ってた件【分子論×確率論】

当たった方だけが、括弧の中に「どこまで分かったのか」という知識の限界に
ついての問いを持っていた。
"""
import titles


CLOSING_MIXED = """本文です。

調べた結果、材料は15世紀初頭のものであると分かった。
著者がロジャー・ベーコンだという説は根拠を失っていると分かった。
本文は自然言語ではなく符号化の可能性が高いと分かった。
描かれた植物は実在するものではなく空想画であると分かった。
皇帝所有説も直接の裏付けがないと分かった。

締めの挨拶です。
"""


def test_it_counts_what_the_script_actually_concluded():
    down, up = titles.tally(CLOSING_MIXED)
    assert (down, up) == (4, 1)


def test_without_a_span_the_first_candidate_falls_back_to_the_question():
    """期間が書いていない台本では、数字を作らない。"""
    got = titles.propose("ヴォイニッチ手稿", ["a", "b", "c", "d", "e"], CLOSING_MIXED)
    assert got[0].startswith("【どこまで分かっているのか】")
    assert "ヴォイニッチ手稿" in got[0]   # 固有名詞は検索で拾われる
    assert "年" not in got[0]            # 台本に無い期間を書かない


def test_counts_are_not_claimed_when_the_script_does_not_conclude_them():
    """台本が結論していないことは題に書かない。"""
    plain = "本文です。\n\nいろいろな話をした。\n\n締めです。"
    got = titles.propose("巨石遺跡", ["a", "b"], plain)
    assert "消えた" not in got[0] and "残った" not in got[0]


def test_a_field_named_once_in_passing_is_not_claimed():
    """実測で巨石遺跡の題に「植物学」が入った。通りすがりの一語だった。"""
    once = "石の話。植物がそこに生えていた。年代測定をした。年代測定の結果。"
    assert "植物学" not in titles.fields(once)
    assert "年代測定" in titles.fields(once)


def test_every_candidate_names_the_subject():
    for t in titles.propose("オーパーツ", ["鉄剣は本物である"], CLOSING_MIXED):
        assert "オーパーツ" in t


def test_the_report_shows_how_long_each_one_is():
    body = titles.render("巨石遺跡", ["a"], CLOSING_MIXED)
    assert "字（スマホは28字前後で切れる）" in body


# ---- 当たった題が持っていた装置 ----

VOYNICH_HEAD = """ヴォイニッチ手稿。
240ページを超える謎の書物。

本文は独自の文字体系で記されている。
未解読のまま600年近く残っている。
1912年に古書商ヴォイニッチが入手した。

""" + CLOSING_MIXED


def test_an_evaluative_word_is_taken_from_the_script():
    """参考chの当たった題は「奇書」を付けていた。

    評価語が1つあるだけで、題材の名前が「物」から「見るべきもの」になる。
    """
    assert titles.epithet(VOYNICH_HEAD) == "奇書"
    assert titles.epithet("石の話をする。") == ""


def test_a_calendar_year_is_not_a_span():
    """実測で「1912年に発見され」から「1912年、誰も読めていない」が出た。

    西暦を期間として出すと、題が事実と食い違う。期間の印を必須にする。
    """
    assert titles.span(VOYNICH_HEAD) == "600年"
    assert titles.span("1912年に入手された。今も不明だ。") == ""


def test_the_bracket_stays_short_enough_to_read():
    """実測で括弧が51字の題が出た。"""
    for t in titles.propose("ヴォイニッチ手稿", ["a"] * 5, VOYNICH_HEAD):
        if not t.startswith("【"):
            continue  # 3案目は括弧が末尾（分野名）なので対象外
        assert len(t.split("】")[0]) <= 18, t


def test_the_first_candidate_carries_all_four_devices():
    """評価語・大きい数字・限界の問い・固有名詞。"""
    got = titles.propose("ヴォイニッチ手稿", ["a"] * 5, VOYNICH_HEAD)[0]
    assert "奇書" in got            # 評価語
    assert "600年" in got           # 大きい数字
    assert "読めていない" in got     # 限界の問い
    assert "ヴォイニッチ手稿" in got  # 固有名詞


# ---- 概要欄の冒頭 ----

def test_the_intro_is_specific_to_this_video():
    """YouTubeが「もっと見る」の前に出すのはここだけ。

    一番読まれる場所に、どの動画でも同じ定型文を置いていた。
    """
    got = titles.intro("ヴォイニッチ手稿", ["a"] * 5, VOYNICH_HEAD,
                       duration_sec=15 * 60)
    assert "600年" in got            # 題名と同じ材料 (1 逆説)
    assert "奇書" in got
    assert "分かっています" in got    # (2 それでも分かっていること)
    assert "15分" in got             # (3 方法と尺)
    assert "5つ" in got              # (4 成果の予告) 確かめた数


def test_the_intro_does_not_claim_counts_the_script_did_not_conclude():
    plain = "石の話。\n\nいろいろ調べた。\n\n締め。"
    got = titles.intro("巨石遺跡", ["a", "b"], plain)
    assert "残ったのは" not in got and "崩れ" not in got
    assert "食い違います" not in got   # 締めが結論していない
    assert "2つの説" in got           # 説の数は仕様から来るので言ってよい


def test_the_intro_comes_first_in_the_description():
    out = __import__("publish").build(
        "", [], "", lead="定型文です。", intro="この動画の話です。")
    assert out.index("この動画の話です。") < out.index("定型文です。")
