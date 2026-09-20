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


def test_the_first_candidate_carries_the_pattern_that_worked():
    got = titles.propose("ヴォイニッチ手稿", ["a", "b", "c", "d", "e"], CLOSING_MIXED)
    assert got[0].startswith("【どこまで分かっているのか】")
    assert "ヴォイニッチ手稿" in got[0]        # 固有名詞は検索で拾われる
    assert "1つ" in got[0] and "4つ" in got[0]  # 数字が入る


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
