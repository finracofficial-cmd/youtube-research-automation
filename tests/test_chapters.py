"""章の位置決め。

これまで章は尺を等分して置いていた（実測で152秒ごと）。台本の主張が
その時刻から始まる保証は無く、画面のカードが主張の途中で出ていた。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))

import chapters as ch


def subs(pairs):
    """(開始秒, 本文) から字幕を作る。"""
    return [{"startSec": s, "durationSec": 1.0, "text": t} for s, t in pairs]


def test_stamp_matches_what_youtube_reads():
    assert ch.stamp(0) == "0:00"
    assert ch.stamp(65) == "1:05"
    assert ch.stamp(3725) == "1:02:05"
    assert ch.stamp(-3) == "0:00"


def test_a_claim_is_placed_where_it_is_actually_spoken():
    script = ("導入です。\n\n"
              "ストーンヘンジの石は遠くから運ばれた。石は運ばれた。石の話。\n\n"
              "モアイは歩いて運ばれたという。モアイの話。モアイの実験。")
    s = subs([(0.0, "導入です。"),
              (20.0, "ストーンヘンジの石は遠くから運ばれた。石は運ばれた。石の話。"),
              (60.0, "モアイは歩いて運ばれたという。モアイの話。モアイの実験。")])
    got = ch.locate(script, s, ["ストーンヘンジの石は250キロ運ばれた",
                                "モアイは歩いて運ばれた"])
    assert [c["startSec"] for c in got] == [0.0, 20.0, 60.0]
    assert got[0]["title"] == "はじめに"
    assert "ストーンヘンジ" in got[1]["title"]


def test_the_intro_preview_is_not_mistaken_for_the_section():
    """導入で主張を一通り予告する台本がある。

    最初の一致を取ると、実測でオーパーツの章が全部0〜1分台に寄った。
    本編では同じ語が繰り返し出るので、密集する方を本編と見なす。
    """
    script = ("鉄剣と土偶を扱う。\n\n" + "鉄剣" * 30 + "。\n\n" + "土偶" * 30 + "。")
    s = subs([(0.0, "鉄剣と土偶を扱う。"),
              (30.0, "鉄剣" * 30 + "。"),
              (90.0, "土偶" * 30 + "。")])
    got = ch.locate(script, s, ["鉄剣は当時の技術では作れない", "土偶は宇宙人を模した"])
    assert [c["startSec"] for c in got] == [0.0, 30.0, 90.0]


def test_claims_reordered_by_the_script_come_out_in_spoken_order():
    """台本は主張の順を入れ替える（実測でオーパーツの第3と第4が逆）。"""
    script = "導入。\n\n" + "与那国" * 20 + "。\n\n" + "遮光器" * 20 + "。"
    s = subs([(0.0, "導入。"), (30.0, "与那国" * 20 + "。"), (90.0, "遮光器" * 20 + "。")])
    got = ch.locate(script, s, ["遮光器土偶は宇宙服に似ている", "与那国島海底遺跡は人工物"])
    assert [c["title"][:3] for c in got[1:]] == ["与那国", "遮光器"]


def test_claims_given_as_dicts_are_read_from_ja():
    assert ch.claim_text({"ja": "モアイは歩いた", "en": "moai walked"}) == "モアイは歩いた"
    assert ch.claim_text("素の文字列") == "素の文字列"
    assert ch.claim_text(None) == ""


def test_titles_stop_at_a_noun():
    """助詞で終わると「鉄剣は」で宙に浮く。"""
    assert ch.title_of("土偶は宇宙人の姿を模して作られたという説がある。") \
        == "土偶は宇宙人の姿を模して作られた"
    long = ch.title_of("古墳から発見された鏡は中国から伝来したもので、"
                       "日本には製造技術がなかったとされている。")
    assert not long.endswith(("は", "が", "を", "で", "の", "、"))
    assert len(long) <= 30


def test_youtube_rules_are_enforced():
    """先頭0秒・10秒以上あけ・3つ以上。欠けると章そのものが出ない。"""
    assert ch.prune([{"startSec": 5.0, "title": "a"},
                     {"startSec": 30.0, "title": "b"},
                     {"startSec": 60.0, "title": "c"}])[0]["startSec"] == 0.0
    # 10秒未満で並んだ分は落とす -> 3つを切るので章にしない
    assert ch.prune([{"startSec": 0.0, "title": "a"},
                     {"startSec": 3.0, "title": "b"},
                     {"startSec": 6.0, "title": "c"}]) == []


def test_no_claims_means_no_chapters_rather_than_wrong_ones():
    assert ch.locate("本文", subs([(0.0, "本文")]), []) == []


def test_a_card_label_is_the_subject_not_a_truncated_sentence():
    """並べる札は番号だけだと中身が空で未完成に見える。

    かといって題名の詰め方で短くすると語の途中で切れる。実測で
    「バールベックの巨石は現代のクレーンでも運べない」が
    「バールベックの巨石は現代のク」になった。主題の印の手前で切る。
    """
    assert ch.subject_of("バールベックの巨石は現代のクレーンでも運べない") \
        == "バールベックの巨石"
    assert ch.subject_of("ストーンヘンジの石は250キロ運ばれた") == "ストーンヘンジの石"
    assert ch.subject_of("モアイは歩いて運ばれた") == "モアイ"
    assert ch.subject_of({"ja": "ギョベクリ・テペは文明より古い"}) == "ギョベクリ・テペ"


def test_a_subject_with_no_topic_marker_still_gives_something():
    got = ch.subject_of("第1幕 地上絵の実体と作り方")
    assert got and len(got) <= 16 and "第1幕" not in got


def test_card_labels_are_distinct_from_each_other():
    """主語だけ取ると、同じ題材の主張は全部同じ語になる。

    実測でヴォイニッチ手稿の5つが「ヴォイニッチ手稿／手稿の著者／手稿／
    手稿に描かれている植物／ヴォイニッチ手稿」になり、同じ語が3つ並んだ。
    札が5枚あっても中身が1つしか無いのと同じ。
    """
    claims = [
        "ヴォイニッチ手稿は15世紀初頭に作られたとされている。",
        "手稿の著者はロジャー・ベーコンであるという説がある。",
        "手稿は未解読の自然言語で書かれている。",
        "手稿に描かれている植物は実在する植物に基づいている。",
        "ヴォイニッチ手稿は16世紀のプラハにあった。",
    ]
    got = ch.card_labels(claims)
    assert len(set(got)) == len(got), got
    assert all(g for g in got)


def test_distinct_subjects_are_kept_as_they_are():
    """被らないなら主語のままでよい。述部に寄せると回りくどくなる。"""
    got = ch.card_labels(["モアイは歩いて運ばれた",
                          "ギョベクリ・テペは文明より古い",
                          "インカの石組みは剃刀の刃も通らない"])
    assert got == ["モアイ", "ギョベクリ・テペ", "インカの石組み"]


def test_the_basics_chapter_gets_its_own_card_before_the_claims():
    """参考の旗艦回の第1幕「この本は何なのか」に当たる。題材の説明が章として見える。"""
    import chapters as ch
    script = ("死海文書。1947年に見つかった巻物だ。それでは私と共に、死海文書へと迫っていこう。"
              "まず、死海文書とは何なのか。" + "羊飼いが洞窟で壺を見つけた。中には巻物が入っていた。" * 12
              + "最初は、バチカンが死海文書を隠した、という話だ。バチカンが隠したという証拠は無い。"
              "バチカンの委員会ではなかった。バチカンは隠していない。" * 3)
    subs, t = [], 0.0
    for s in [x + "。" for x in script.split("。") if x]:
        subs.append({"startSec": t, "durationSec": 6.0, "text": s})
        t += 6.0
    out = ch.locate(script, subs, [{"ja": "バチカンが死海文書を隠した"}])
    kinds = [(o.get("kind"), o["title"]) for o in out]
    assert (("basics", "死海文書とは何か")) in kinds
    assert [o["title"] for o in out].index("死海文書とは何か") < [o["title"] for o in out].index("バチカンが死海文書を隠した")
