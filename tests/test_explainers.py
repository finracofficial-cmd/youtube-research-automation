"""作図だけで語る区間。

参考chは素材の上に札を載せるだけでなく、作図だけの区間を挟む。こちらは
全フレームが「写真＋札」で、その状態が無かった。

ここで縛るのは主に「出さない条件」。図のために事実を曲げるのが一番重い。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))

from autolayout import Line  # noqa: E402
import explainers as ex  # noqa: E402


def lines(*texts, step=6.0):
    return [Line(i * step, step, t) for i, t in enumerate(texts)]


# ---- contrast ----

def test_a_claim_is_paired_with_a_sentence_that_cites_something():
    got = ex.contrast_at(lines(
        "島の言い伝えでは、モアイは歩いて行ったとされる。",
        "2012年、ハントとリポが実験をした。"), 0)
    assert got["kind"] == "contrast"
    assert "モアイ" in got["claim"] and "実験" in got["evidence"]


def test_a_negation_alone_is_not_treated_as_a_refutation():
    """実測で「石の角は3つや4つではない」が反証として組まれた。

    あれは説明文であって反証ではない。資料を誤って引くのが、このchでは
    一番重い間違いになる。
    """
    assert ex.contrast_at(lines(
        "剃刀の刃も入らないという主張がある。",
        "石の角は3つや4つではない。"), 0) is None


def test_a_sentence_with_no_claim_phrasing_makes_no_panel():
    assert ex.contrast_at(lines("石は重い。", "2012年に実験をした。"), 0) is None


# ---- timeline ----

def test_bc_years_sort_before_ad_and_keep_their_era():
    """紀元前を落とすと順序が逆になる。実測で紀元前3000年が2006年の後ろに並んだ。"""
    got = ex.timeline_at(lines(
        "2006年に石器が見つかった。",
        "紀元前3000年頃に立ち始める。",
        "紀元前9500年頃まで遡る。"), 0)
    assert [m["year"] for m in got["marks"]] == ["紀元前9500年", "紀元前3000年", "2006年"]


def test_a_span_of_years_is_not_a_date():
    """「500年かけて」は期間。年号として並べると嘘になる。"""
    got = ex.timeline_at(lines(
        "500年かけて作り替えられた。",
        "300年間そこにあった。",
        "1903年に生まれた。"), 0)
    assert got is None


def test_three_dates_are_needed():
    assert ex.timeline_at(lines("1900年に見つかった。", "1901年に回収した。"), 0) is None


# ---- scale ----

def test_two_quantities_from_different_sentences_make_bars():
    got = ex.scale_at(lines("北へ25キロほどの丘陵から来ている。",
                            "直線距離で約250キロある。"), 0)
    assert [b["readout"] for b in got["bars"]] == ["25キロ", "250キロ"]
    assert got["bars"][1]["value"] == 1.0


def test_a_range_in_one_sentence_is_not_a_comparison():
    """「2トンから4トン」は幅。端の片方だけ取ると値を取り違える。"""
    assert ex.scale_at(lines("1本2トンから4トンある。", "石を運んだ。"), 0) is None


def test_counters_and_small_numbers_are_not_quantities():
    """実測で「1本あたり25トン」の「1本」が棒になり、同じ長さが2本並んだ。"""
    assert ex.scale_at(lines("1本あたりの話だ。", "2本を並べた。"), 0) is None


def test_centuries_are_an_order_not_an_amount():
    """実測で「14世紀」と「紀元前3世紀」が 1.00 対 0.21 の棒になった。"""
    assert ex.scale_at(lines("14世紀に現れる。", "紀元前3世紀に作られた。"), 0) is None


def test_values_too_close_together_are_not_worth_bars():
    """実測で「7メートル」と「7.2メートル」がほぼ同じ長さの棒2本になった。"""
    assert ex.scale_at(lines("高さは約7メートル。", "地下を含めると7.2メートル。"), 0) is None


# ---- 置き方 ----

def test_panels_are_spaced_out_and_capped_per_kind():
    body = []
    for _ in range(40):
        body += ["北へ25キロほどの丘陵から来ている。", "直線距離で約250キロある。", "石を運んだ。"]
    got = ex.plan(lines(*body), 1000.0)
    assert len(got) <= ex.MAX_PANELS
    assert sum(1 for p in got if p["kind"] == "scale") <= ex.PER_KIND
    gaps = [b["startSec"] - a["startSec"] for a, b in zip(got, got[1:])]
    assert all(g >= ex.MIN_GAP_SEC for g in gaps)


def test_a_panel_never_runs_past_the_end():
    got = ex.plan(lines("北へ25キロほど。", "直線距離で約250キロある。"), 12.0)
    assert got == []


# ---- 重なりの除去 ----

def test_cards_and_source_labels_under_a_panel_are_removed():
    """写真が見えていないのに帰属を出すと、出所の表示として誤りになる。"""
    props = {
        "stats": [{"startSec": 10.0, "durationSec": 6.0},
                  {"startSec": 100.0, "durationSec": 6.0}],
        "sourceLabels": [{"startSec": 11.0, "durationSec": 4.0}],
        "subtitles": [{"startSec": 10.0, "durationSec": 2.0}],
        "chapters": [{"startSec": 10.0, "durationSec": 3.0}],
    }
    got = ex.clear(props, [{"startSec": 8.0, "durationSec": 9.0}])
    assert [s["startSec"] for s in got["stats"]] == [100.0]
    assert got["sourceLabels"] == []
    # 語りは続いているので字幕と章は残す
    assert len(got["subtitles"]) == 1 and len(got["chapters"]) == 1


def test_clearing_nothing_changes_nothing():
    props = {"stats": [{"startSec": 10.0, "durationSec": 6.0}]}
    assert ex.clear(dict(props), []) == props
