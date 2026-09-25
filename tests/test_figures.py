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
    n_fig, n_tel = F.inject(props, plan)
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
