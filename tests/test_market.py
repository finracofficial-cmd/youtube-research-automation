"""市場の集計と、それを使う題名の案。検索とチャンネルのページは偽物で通す。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import titles  # noqa: E402
from topic_scout import market as M  # noqa: E402
from topic_scout.fetch import Video  # noqa: E402


def _v(i, title, views, ch):
    return Video(video_id=f"v{i}", title=title, channel=f"ch{ch}", channel_id=f"C{ch}",
                 view_count=views, duration=600, description="", verified=False)


# 死海文書の実測の形をまねた偽の市場。「救世主の正体」「解読」の題が、そのチャンネルの
# ふだんの再生数より大きく伸び、「謎」「【ゆっくり解説】」の題は伸びていない
FAKE = ([_v(i, f"死海文書の救世主の正体が判明した{i}", 50000, i) for i in range(6)]
        + [_v(10 + i, f"死海文書を解読した結果{i}", 40000, 10 + i) for i in range(5)]
        + [_v(20 + i, f"【ゆっくり解説】死海文書の謎{i}", 3000, 20 + i) for i in range(8)]
        + [_v(30 + i, f"死海文書とは何か{i}", 5000, 30 + i) for i in range(6)]
        + [_v(40, "Dead Sea Scrolls in English", 900000, 40)])     # 仮名の無い題は数えない


def _analyze():
    return M.analyze("死海文書", searcher=lambda q, limit: FAKE,
                     baseline=lambda cid: {"subs": 10000, "median": 5000, "n": 30}, pause=0, log=lambda *a: None)


def test_words_that_beat_the_channels_usual_views_are_found():
    m = _analyze()
    assert m["n_videos"] == 25 and m["n_scored"] == 25
    lift = {x["term"]: x for x in m["lifts"]}
    assert lift["正体"]["lift"] > 2 and lift["解読"]["lift"] > 2
    assert lift["謎"]["lift"] < 1 and lift["【ジャンル札】"]["lift"] < 1
    # 本数の少ない語は1倍に寄せる（数本の当たりで順位が入れ替わらない）
    assert 1 < lift["正体"]["adj"] < lift["正体"]["lift"]
    assert [x["term"] for x in M.hot(m)][:2] and all(x["adj"] >= 1.3 for x in M.hot(m))


def test_one_channel_mass_producing_a_word_does_not_count():
    """死海文書ではエヴァのパロディを量産する1チャンネルが上位を占めた。"""
    rows = [{"title": f"死海文書 外典{i}", "ratio": 300.0, "channel_id": "X", "views": 1} for i in range(8)]
    rows += [{"title": f"死海文書 普通{i}", "ratio": 1.0, "channel_id": f"C{i}", "views": 1} for i in range(12)]
    assert "外典" not in {x["term"] for x in M.lifts(rows, "死海文書")}


def test_titles_are_ranked_by_how_much_they_beat_the_channel():
    m = _analyze()
    got = M.ranked_titles(m)
    assert got[0].startswith("死海文書の救世主の正体") and all("ゆっくり解説" not in t for t in got)


PLAN = {"mystery": "死海文書にキリスト教を覆す秘密はあるのか",
        "chapters": [{"claim": "バチカンが死海文書を隠した", "question": "バチカンは死海文書を隠したのか？", "verdict": "跡形なし"},
                     {"claim": "AIで死海文書が解読された", "question": "AIで死海文書は解読されたのか？", "verdict": "半分当たり"},
                     {"claim": "死海文書に救世主の正体が書かれている", "question": "死海文書に救世主の正体は書かれているのか？",
                      "verdict": "半分当たり"}]}
SCRIPT = ("死海文書。\n\nそれまで知られていた最も古い写本より、1,000年も古い。\n\n"
          "動画サイトで「死海文書」と検索すると、こんな題名が並ぶ。\n「バチカンが隠した」。\n\n"
          "それでは私と共に、死海文書へと迫っていこう。\n\n"
          "最初は、バチカンが死海文書を隠した、という話だ。\n\n"
          "2つ目は、AIで死海文書が解読された、という話だ。AIとDNAで調べた。\n\n"
          "最後は、死海文書に救世主の正体が書かれている、という話だ。正体は書かれていない。\n\n答え。")


def test_the_best_title_promises_the_chapter_the_market_wants_as_a_question():
    m = _analyze()
    got = titles.market_propose("死海文書", ["a", "b", "c"], SCRIPT, PLAN, m)
    top = got[0]["title"]
    assert top.startswith("死海文書") and "正体" in top and top.endswith("どこまで分かったのか】")
    assert "「救世主の正体」" in top                       # 効く語を前後の名詞ごと囲む
    assert not any("判明" in x["title"] for x in got)     # 言い切りは作らない
    assert all(x["score"] <= got[0]["score"] for x in got)


def test_a_hot_word_the_script_never_mentions_is_not_used():
    m = _analyze()
    no_decode = SCRIPT.replace("解読", "調査")
    plan = json.loads(json.dumps(PLAN))
    got = titles.market_propose("死海文書", [], no_decode, plan, m)
    assert not any("解読" in x["title"] for x in got)


def test_the_title_promise_must_show_up_in_the_opening():
    m = _analyze()
    gap = titles.opening_gap(SCRIPT, PLAN, m)
    assert "冒頭に出てこない" in gap and "第3章" in gap
    fixed = SCRIPT.replace("「バチカンが隠した」。", "「バチカンが隠した」。\n「死海文書の救世主の正体」。")
    assert titles.opening_gap(fixed, PLAN, m) == ""


def test_the_opening_shows_the_promised_story_first():
    from script_engine.pipeline import pick_told
    told = ["死海文書最大の謎！バチカンが隠したとされるキリストの秘密", "死海文書に記された救世主の正体が判明しました"]
    claims = ["バチカンが死海文書を隠した", "死海文書に救世主の正体が書かれている"]
    assert pick_told(told, claims)[0].startswith("死海文書最大の謎")
    assert pick_told(told, claims, first=1)[0].startswith("死海文書に記された救世主")


def test_the_titles_file_shows_the_numbers_behind_each_title():
    m = _analyze()
    body = titles.render("死海文書", ["a"], SCRIPT, plan=PLAN, market=m)
    assert "市場の数字つき" in body and "効く語:" in body and "倍" in body and "注意:" in body
    assert "市場の数字つき" not in titles.render("死海文書", ["a"], SCRIPT)   # 市場が無ければ従来の案


def test_quotes_do_not_split_a_word_and_the_subject_leads_once():
    """ヴォイニッチ手稿で「ヴォイニッチ手稿、手稿は未「解読の自然言語」で…」と出た。"""
    hot = [{"term": "解読", "pattern": "解読", "lift": 2.1, "adj": 2.0, "n": 36}]
    q = titles._lead_subject("手稿は未解読の自然言語で書かれているのか", "ヴォイニッチ手稿")
    assert q == "ヴォイニッチ手稿は未解読の自然言語で書かれているのか"
    assert titles._quote_hot(q, hot, "ヴォイニッチ手稿") == "ヴォイニッチ手稿は「未解読の自然言語」で書かれているのか"
    assert titles._lead_subject("バチカンは隠したのか", "死海文書") == "死海文書、バチカンは隠したのか"


def test_framing_words_are_added_only_where_they_work():
    """「？」「最新」は、その題材の市場で効いているときだけ足す（死海文書とヴォイニッチ手稿で逆だった）。"""
    m = _analyze()
    base = [t["title"] for t in titles.market_propose("死海文書", [], SCRIPT, PLAN, m, k=20)]
    assert not any("？【" in t for t in base)
    m2 = json.loads(json.dumps(m))
    m2["lifts"].append({"term": "？", "pattern": "[？?]", "lift": 4.0, "adj": 3.0, "n": 28, "channels": 20})
    got = [t["title"] for t in titles.market_propose("死海文書", [], SCRIPT, PLAN, m2, k=20)]
    assert any("のか？【" in t for t in got)


def test_list_titles_are_dropped_rather_than_cut_mid_word():
    assert titles._label("手稿は未解読の自然言語で書かれている", "ヴォイニッチ手稿") is None
    assert titles._label("死海文書に救世主の正体が書かれている", "死海文書") == "救世主の正体"
