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
        "tests": "「人間には運べない」という候補",
        "so_far": "これで「人間ではない」を支える話が崩れた。残るのは2つ",
        "remaining": ["人間が坂で運んだ", "運ばなかった（その場で切った）"],
        "figure": {"kind": "scale", "heading": "石の重さ", "items": [{"label": "最大の石", "value": "1000トン"}, {"label": "普通の石", "value": "300トン"}]},
        "hook_out": "では、なぜ運ばなかったのか。",
    }
    return {
        "thesis": "分からないことは、分からない人が最初に書き残している",
        "mystery": "巨石は誰が、どうやって運んだのか",
        "candidates": ["人間が坂で運んだ", "運ばなかった（その場で切った）", "人間ではない"],
        "opening": {"paradox": "1000トンの石が、道の無い丘の上にある",
                    "images": ["継ぎ目に紙一枚入らない石壁", "切り出し途中で放置された巨石", "誰も入っていない地下室"],
                    "defeat": "運び方は決まっていない", "cheap_answers": ["技術が失われたから", "記録が燃えたから"],
                    "map": "3つの説を順に確かめる"},
        "planted_question": {"text": "そもそも誰が運んだのか", "opened_in": 1},
        "chapters": [dict(ch) for _ in range(n)],
        "closing": {"generalization": ["a", "b", "c", "d", "e"], "callback": "回収",
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
    d["chapters"][0]["so_far"] = ""
    with pytest.raises(P.PlanError, match="so_far"):
        P.validate(d)


def test_figures_with_unsourced_numbers_are_dropped():
    p = P.validate(good_plan(1))
    P.strip_unsourced(p, "最大の石は1000トンある。普通の石は300トンだ。")
    assert p.chapters[0].figure["kind"] == "scale"
    p2 = P.validate(good_plan(1))
    P.strip_unsourced(p2, "最大の石は1000トンある。")
    assert p2.chapters[0].figure == {}          # 2本に足りなくなった図は消える



def test_remaining_must_be_candidates_and_never_grow():
    """死海文書の設計図は2章目から主張の名前（AI発見説・DNA説…）で数えていた。"""
    d = good_plan(2)
    d["chapters"][1]["remaining"] = ["AI発見説", "DNA説"]
    with pytest.raises(P.PlanError, match="候補でないもの"):
        P.validate(d)
    d = good_plan(2)
    d["chapters"][0]["remaining"] = ["人間が坂で運んだ"]
    d["chapters"][1]["remaining"] = ["人間が坂で運んだ", "人間ではない"]
    with pytest.raises(P.PlanError, match="増えている"):
        P.validate(d)
