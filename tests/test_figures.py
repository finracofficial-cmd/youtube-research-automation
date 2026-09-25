"""設計図から動画側に足すもの: 図・考察の印・検索の手がかり。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
import figures as F  # noqa: E402

from assets.plan_shots import with_hints


def test_timeline_and_scale_figures_become_explainer_panels():
    tl = F.panel_of({"kind": "timeline", "heading": "発見の順", "items": [
        {"label": "最初の壺", "year": "1947年"}, {"label": "調査終了", "year": "1956年"},
        {"label": "全文公開", "year": "1991年"}]})
    assert tl["kind"] == "timeline" and [m["year"] for m in tl["marks"]] == ["1947年", "1956年", "1991年"]
    sc = F.panel_of({"kind": "scale", "heading": "写本の数", "items": [
        {"label": "断片", "value": "972点"}, {"label": "完本", "value": "10点"}]})
    assert sc["kind"] == "scale" and sc["bars"][0]["value"] == 1.0 and sc["bars"][1]["readout"] == "10点"
    assert F.panel_of({"kind": "timeline", "items": [{"year": "1947年"}, {"year": "1956年"}]}) is None
    assert F.panel_of({"kind": "scale", "items": [{"value": "7メートル"}, {"value": "7.2メートル"}]}) is None


def test_panels_sit_after_each_chapter_start_and_clear_overlapping_cards():
    plan = {"chapters": [
        {"figure": {"kind": "scale", "items": [{"label": "a", "value": "100点"}, {"label": "b", "value": "10点"}]}},
        {"figure": {}}]}
    props = {"outline": [{"startSec": 0, "title": "はじめに"}, {"startSec": 60, "title": "1"}, {"startSec": 200, "title": "2"}],
             "subtitles": [{"startSec": 0, "durationSec": 400, "text": "x"}],
             "explainers": [], "stats": [{"startSec": 75, "durationSec": 5, "value": "1"}],
             "telops": []}
    n_fig, n_board, n_tel = F.inject(props, plan)
    assert n_fig == 1 and props["explainers"][0]["startSec"] == 72.0
    assert props["stats"] == []          # パネルに重なる札は外れる


def test_speculation_markers_get_telops():
    subs = [{"startSec": 500, "durationSec": 3, "text": "事実はここまでだ。"},
            {"startSec": 503, "durationSec": 3, "text": "ここからは資料に無い。私の考えだ。"},
            {"startSec": 520, "durationSec": 3, "text": "ここまでが考察だ。"}]
    got = F.speculation_telops(subs)
    assert [t["text"] for t in got] == ["ここからは考察（資料に無い）", "考察はここまで"]
    assert got[0]["startSec"] == 503.0


def test_hints_are_spread_over_the_body_segments():
    segs = [f"文{i}。" for i in range(10)]
    got = with_hints(segs, [["クムラン洞窟"], ["放射性炭素"]])
    assert "クムラン洞窟" in "".join(got[1:5]) and "放射性炭素" in "".join(got[5:9])
    assert got[0] == "文0。" and got[9] == "文9。"        # 端は触らない



def _plan_with_board():
    return {"mystery": "死海文書に世に出せない秘密はあるか",
            "candidates": ["秘密がある", "秘密は無い", "未読の部分にある"],
            "chapters": [{"remaining": ["秘密は無い", "未読の部分にある"]},
                         {"remaining": ["秘密は無い", "未読の部分にある"]},
                         {"remaining": ["秘密は無い"]}]}


def test_candidate_board_opens_with_all_and_crosses_out_as_chapters_close():
    subs = [{"startSec": 20, "durationSec": 3, "text": "答えは3つに絞れる。"},
            {"startSec": 95, "durationSec": 3, "text": "これで一つ目は消えた。残るのは二つ。"},
            {"startSec": 190, "durationSec": 3, "text": "残る候補は変わらない。"},
            {"startSec": 290, "durationSec": 3, "text": "残るのは一つだけだ。"},
            {"startSec": 300, "durationSec": 20, "text": "着地。"}]
    outline = [{"startSec": 0}, {"startSec": 60}, {"startSec": 160}, {"startSec": 250}]
    b = F.candidate_boards(_plan_with_board(), subs, outline)
    assert [x["startSec"] for x in b] == [20.0, 95.0, 290.0]          # 変化の無い2章目は出さない
    assert all(not c["dimmed"] for c in b[0]["cards"])                # 冒頭は全部
    assert [c.get("mark") for c in b[1]["cards"]] == ["no", None, None]
    assert [c.get("mark") for c in b[2]["cards"]] == ["no", "ok", "no"] and b[2]["caption"] == "答え: 秘密は無い"


def test_no_board_when_the_plan_counts_claims_instead_of_candidates():
    plan = _plan_with_board()
    plan["chapters"][1]["remaining"] = ["AI発見説", "DNA説"]
    assert F.candidate_boards(plan, [{"startSec": 0, "durationSec": 1, "text": "答えは3つ"}],
                              [{"startSec": 0}, {"startSec": 60}]) == []


def test_hints_drop_sentences_negations_and_paper_titles():
    plan = {"chapters": [{"evidence": {"who": "Emanuel Tov",
                                       "where": "Emanuel Tov The Dead Sea Scrolls and the Textual History of the Masoretic Bible",
                                       "what": "AIによる痕跡発見の記録は無い"},
                          "jargon": [{"term": "マソラ本文"}]}]}
    assert F.hints(plan) == [["Emanuel Tov", "マソラ本文"]]
