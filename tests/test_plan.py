"""設計図の形の検査。書き始めてから足りないと分かると、章を全部書き直すことになる。"""
import json

import pytest

from script_engine import plan as P


def good_plan(n=2):
    ch = {
        "claim": "巨石は現代の重機でも運べない", "verdict": "半分当たり",
        "verdict_line": "結論から言う。運べないのではなく、運ぶ理由が無い。",
        "why": "重機は重量ではなく道と時間の制約で選ばれる",
        "origin": {"who": "ある観光ガイド", "year": "1980", "how": "旅行記に載った"},
        "swings": [{"stance": "肯定", "fact": "最大の石は1000トンある"},
                   {"stance": "反転", "fact": "同じ石切り場に切り出し途中の石が残っている"},
                   {"stance": "留保", "fact": "運搬の記録そのものは無い"}],
        "evidence": {"year": "2015", "where": "石切り場", "who": "調査団", "what": "傾斜路"},
        "numbers": [{"value": "1000トン", "caveat": "推定値で実測ではない"}],
        "jargon": [{"term": "層序", "landing": "地層の重なり順"}],
        "narrator": "私はこの推定値を疑っている",
        "scope": "運べないとは言えない、というところまでだ",
        "question": "巨石は本当に運べなかったのか",
        "method": "石切り場に切り出し途中の石が残っているかを見ればいい",
        "means": "つまり、当時の人間の力では動かせなかったということだ",
        "basis": "石切り場に、切り出し途中で放置された巨石が今も残っている",
        "bearing": "少なくとも、人間には運べなかったから別の誰かが運んだ、という線は消えた",
        "figure": {"kind": "scale", "heading": "石の重さ", "items": [{"label": "最大の石", "value": "1000トン"}, {"label": "普通の石", "value": "300トン"}]},
        "hook_out": "では、なぜ運ばなかったのか。",
    }
    return {
        "thesis": "分からないことは、分からない人が最初に書き残している",
        "mystery": "巨石は誰が、どうやって運んだのか",
        "opening": {"what": "2000年前に造られた神殿の土台に、1000トンの石が使われている",
                    "significance": "現代の最大級のクレーンでも持ち上げるのが難しい重さだ",
                    "curious": "どれも、人間には運べなかったと言っている",
                    "map": "3つの説を順に確かめる"},
        "basics": {"found": "1898年にドイツの調査団が測った", "contents": "土台に3つの巨石が並ぶ",
                   "dating": "", "after": "", "seeds": ["石切り場に、もっと大きな石が残っている"],
                   "terms": [{"term": "石切り場", "landing": "石を切り出した場所"}]},
        "planted_question": {"text": "そもそも誰が運んだのか", "opened_in": 1},
        "chapters": [dict(ch) for _ in range(n)],
        "closing": {"generalization": ["a", "b", "c"], "callback": "回収",
                    "answer": "残るのは「運ばなかった」だけだ",
                    "found": ["x"], "not_found": "だが誰が運んだかは分かっていない",
                    "open_questions": ["q"], "condition": "石切り場の記録が出れば",
                    "opening_callback": "冒頭でこう述べた",
                    "speculation": {"claim": "運ぶ気が無かったのだと思う", "reasons": ["坂の跡が無い", "切り出しが途中で止まっている"],
                                    "weakness": "運搬の道具が出土すれば"}},
    }


def test_a_good_plan_validates():
    p = P.validate(good_plan(), n_claims=2)
    assert len(p.chapters) == 2 and p.thesis


def test_json_is_pulled_out_of_a_code_fence():
    d = P.parse("設計図です。\n```json\n" + json.dumps(good_plan()) + "\n```\n以上")
    assert d["thesis"]


def test_consecutive_same_stances_are_rejected():
    d = good_plan()
    d["chapters"][0]["swings"][1]["stance"] = "肯定"
    with pytest.raises(P.PlanError, match="同じ立場"):
        P.validate(d)


def test_a_chapter_without_a_hook_is_rejected():
    d = good_plan()
    d["chapters"][1]["hook_out"] = ""
    with pytest.raises(P.PlanError, match="hook_out"):
        P.validate(d)


def test_fabricated_narrator_deeds_are_rejected():
    """語り手の行為は捏造になる。判断だけ通す。"""
    d = good_plan()
    d["chapters"][0]["narrator"] = "私はこの論文を全部読んだ"
    with pytest.raises(P.PlanError, match="行為"):
        P.validate(d)


def test_jargon_needs_a_landing():
    d = good_plan()
    d["chapters"][0]["jargon"] = [{"term": "エントロピー", "landing": ""}]
    with pytest.raises(P.PlanError, match="言い換え"):
        P.validate(d)


def test_generalization_needs_five_sentences():
    d = good_plan()
    d["closing"]["generalization"] = ["a", "b"]
    with pytest.raises(P.PlanError, match="generalization"):
        P.validate(d)


def test_chapter_count_must_match_claims():
    with pytest.raises(P.PlanError, match="主張の数"):
        P.validate(good_plan(2), n_claims=3)


def test_prompt_carries_the_material_and_the_order_rule():
    txt = P.prompt("## 資料\n- 2015 論文", subject="巨石遺跡", claims=["a", "b"],
                   duration_sec=900, kind="bundle")
    assert "2015 論文" in txt and "跡形もなくなるもの" in txt and "1. a" in txt



def test_abstract_mysteries_and_missing_speculation_are_rejected():
    d = good_plan()
    d["mystery"] = "なぜ謎が今も残り続けるのか"
    with pytest.raises(P.PlanError, match="抽象的"):
        P.validate(d)
    d = good_plan()
    d["closing"]["speculation"]["reasons"] = ["一つだけ"]
    with pytest.raises(P.PlanError, match="reasons"):
        P.validate(d)
    d = good_plan()
    d["closing"]["answer"] = ""
    with pytest.raises(P.PlanError, match="closing.answer"):
        P.validate(d)


def test_figures_with_unsourced_numbers_are_dropped():
    p = P.validate(good_plan(1))
    P.strip_unsourced(p, "最大の石は1000トンある。普通の石は300トンだ。")
    assert p.chapters[0].figure["kind"] == "scale"
    p2 = P.validate(good_plan(1))
    P.strip_unsourced(p2, "最大の石は1000トンある。")
    assert p2.chapters[0].figure == {}          # 2本に足りなくなった図は消える



def test_hooks_must_be_questions():
    d = good_plan(2)
    d["chapters"][0]["hook_out"] = "次は、なぜ運ばなかったのかを確かめる。"
    with pytest.raises(P.PlanError, match="問いになっていない"):
        P.validate(d)


def test_a_plan_must_say_what_the_subject_is_and_why_people_care():
    """死海文書の台本は、死海文書が何なのかも、なぜみんな気にしているのかも言わずに
    噂の真偽に入った（「何を言っているのか分からない」）。設計図の段階で落とす。"""
    d = good_plan()
    d["opening"]["what"] = ""
    d["opening"]["curious"] = ""
    d["basics"]["found"] = ""
    with pytest.raises(P.PlanError) as e:
        P.validate(d)
    assert "opening.what" in str(e.value) and "opening.curious" in str(e.value) and "basics.found" in str(e.value)


def test_each_chapter_says_the_claim_plainly_and_what_it_means_for_the_question():
    d = good_plan()
    d["chapters"][0]["means"] = ""
    d["chapters"][1]["bearing"] = ""
    with pytest.raises(P.PlanError) as e:
        P.validate(d)
    assert "第1章の means" in str(e.value) and "第2章の bearing" in str(e.value)


def test_unknown_fields_are_dropped_not_written_as_unknown():
    """「不明」と渡すと本文に「著者は不明」と書かれた。"""
    d = good_plan(1)
    d["chapters"][0]["origin"] = {"who": "不明", "year": "1980"}
    d["chapters"][0]["basis"] = "不明"
    p = P.validate(d)
    assert p.chapters[0].origin == {"year": "1980"} and p.chapters[0].basis == ""


def test_prompt_carries_told_titles_and_no_candidates():
    txt = P.prompt("## 資料", subject="巨石遺跡", claims=["a"], duration_sec=900,
                   told=["巨石は宇宙人が運んだ！？"])
    assert "巨石は宇宙人が運んだ" in txt and "candidates" not in txt


def test_the_plan_sees_facts_not_the_old_beat_sheet():
    """資料ファイルには一気書き用の構成（「異様さの具体3つ」）が入っている。設計図の型とぶつかる。"""
    material = ("# 題材: 死海文書\n## 文体（すべて必須）\n- 短く切る\n## 構成（各ビート）\n### 異様さの具体3つ\n- 3つ並べる\n"
                "## 使う一次資料\n- 2021 論文\n## 題材の記述（Wikipedia）\n### 基本\n1947年に見つかった。\n")
    got = P.facts_only(material)
    assert "異様さ" not in got and "短く切る" not in got
    assert not any(line.startswith("# ") for line in got.splitlines())
    assert "2021 論文" in got and "1947年に見つかった。" in got
