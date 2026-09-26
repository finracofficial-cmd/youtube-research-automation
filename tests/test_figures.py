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
            "closing": {"answer": "世に出せない秘密は書かれていない。"},
            "chapters": [{"claim": "バチカンが死海文書を隠した", "verdict": "跡形なし",
                          "bearing": "隠されていたから秘密がある、とは言えない"},
                         {"claim": "聖書から消えた記述が残っている", "verdict": "半分当たり",
                          "bearing": "違う記述はあるが、秘密ではなかった"},
                         {"claim": "救世主の正体が書かれている", "verdict": "決まっていない", "bearing": ""}]}


def test_verdict_board_marks_each_claim_as_its_chapter_closes():
    """札は、章で「大きな問いにとっての意味」を語る所に出す。帯は動画の問い、最後だけ答え。"""
    subs = [{"startSec": 20, "durationSec": 3, "text": "いま語られている話を3つ取り上げ、当たっていたものから順に確かめる。"},
            {"startSec": 30, "durationSec": 3, "text": "まず、死海文書とは何なのか。"},
            {"startSec": 95, "durationSec": 3, "text": "隠されていたから秘密がある、とは言えない。"},
            {"startSec": 150, "durationSec": 3, "text": "では、聖書から消えた記述はあるのか。"},
            {"startSec": 190, "durationSec": 3, "text": "違う記述はあるが、秘密ではなかった。"},
            {"startSec": 240, "durationSec": 3, "text": "では、救世主の正体は書かれているのか。"},
            {"startSec": 300, "durationSec": 20, "text": "着地。"}]
    # 基本の章（kind: basics）は、主張の章に数えない
    outline = [{"startSec": 0}, {"startSec": 30, "kind": "basics"}, {"startSec": 60}, {"startSec": 160},
               {"startSec": 250}]
    b = F.verdict_boards(_plan_with_board(), subs, outline)
    assert [x["startSec"] for x in b] == [20.0, 95.0, 190.0, 313.0]
    assert all(c["dimmed"] and "mark" not in c for c in b[0]["cards"])          # 冒頭は印なし
    assert [c.get("mark") for c in b[1]["cards"]] == ["no", None, None]
    assert [c.get("mark") for c in b[3]["cards"]] == ["no", "partial", "unknown"]
    assert b[1]["caption"] == "死海文書に世に出せない秘密はあるか"
    assert b[3]["caption"] == "世に出せない秘密は書かれていない。"


def test_hints_drop_sentences_negations_and_paper_titles():
    plan = {"chapters": [{"evidence": {"who": "Emanuel Tov",
                                       "where": "Emanuel Tov The Dead Sea Scrolls and the Textual History of the Masoretic Bible",
                                       "what": "AIによる痕跡発見の記録は無い"},
                          "jargon": [{"term": "マソラ本文"}]}]}
    assert F.hints(plan) == [["Emanuel Tov", "マソラ本文"]]



def test_board_labels_drop_the_shared_subject_name():
    plan = {"chapters": [{"claim": "バチカンが死海文書を隠した"},
                         {"claim": "死海文書には聖書から消えた記述が残っている"},
                         {"claim": "死海文書を隠したのはクムラン共同体である"},
                         {"claim": "AI解析で死海文書に不自然な痕跡が見つかった"}]}
    assert F._labels(plan) == ["バチカンが隠した", "聖書から消えた記述が残っている",
                               "隠したのはクムラン共同体", "AI解析で不自然な痕跡が見つかった"]
