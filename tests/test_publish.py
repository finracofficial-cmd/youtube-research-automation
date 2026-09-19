"""概要欄の組み立て。

出典はCC BYの表示義務があるので、章だけ出して落とすと違反になる。
"""
import publish


def test_chapters_sources_and_footer_are_all_present():
    out = publish.build(
        "題名", [{"startSec": 0.0, "title": "はじめに"},
                 {"startSec": 65.0, "title": "第1の主張"}],
        "【画像・資料の出典】\n・Someone — CC BY 4.0")
    assert out.startswith("題名\n")
    assert "0:00 はじめに" in out and "1:05 第1の主張" in out
    assert "CC BY 4.0" in out
    assert publish.FOOTER in out


def test_sources_survive_even_with_no_chapters():
    """章が取れなかったときに出典まで落とすとライセンス違反になる。"""
    out = publish.build("", [], "【画像・資料の出典】\n・Someone — CC BY 4.0")
    assert "CC BY 4.0" in out
    assert "目次" not in out


def test_tags_are_prefixed_once():
    out = publish.build("", [], "", tags=["未解決", "#一次資料"])
    assert "#未解決 #一次資料" in out
    assert "##" not in out


def test_refresh_moves_chapters_onto_the_real_speech():
    """build_props の時刻は字数割りの概算。読み上げに貼り直したら取り直す。"""
    props = {"subtitles": [{"startSec": 0.0, "durationSec": 1.0, "text": "導入。"},
                           {"startSec": 42.0, "durationSec": 1.0,
                            "text": "モアイ" * 30 + "。"},
                           {"startSec": 99.0, "durationSec": 1.0,
                            "text": "ギョベクリ" * 30 + "。"}],
             "outline": [], "chapters": [{"startSec": 152.0, "durationSec": 3.0,
                                          "label": "第1主張", "title": ""}]}
    script = "導入。\n\n" + "モアイ" * 30 + "。\n\n" + "ギョベクリ" * 30 + "。"
    got = publish.refresh(props, script, ["モアイは歩いて運ばれた",
                                          "ギョベクリ・テペは文明より古い"])
    assert [c["startSec"] for c in got["outline"]] == [0.0, 42.0, 99.0]
    # 画面のカードは0秒の「はじめに」を出さない
    assert [c["startSec"] for c in got["chapters"]] == [42.0, 99.0]
    assert got["chapters"][0]["label"].startswith("モアイ")


def test_refresh_keeps_the_old_chapters_when_it_cannot_do_better():
    props = {"subtitles": [{"startSec": 0.0, "durationSec": 1.0, "text": "本文"}],
             "chapters": [{"startSec": 152.0, "durationSec": 3.0,
                           "label": "第1主張", "title": ""}]}
    got = publish.refresh(props, "本文", [])
    assert got["chapters"] == [{"startSec": 152.0, "durationSec": 3.0,
                                "label": "第1主張", "title": ""}]


def test_the_topic_tag_comes_first():
    """YouTubeは先頭3つを題名の上に出す。

    看板のタグだけだと、どの動画も同じ3つが並ぶ。題材固有の語を先頭に置く。
    """
    got = publish.tags_for("オーパーツ", ["都市伝説", "一次資料"])
    assert got[0] == "オーパーツ"


def test_a_topic_already_in_the_brand_tags_is_not_repeated():
    assert publish.tags_for("一次資料", ["都市伝説", "一次資料"]) \
        == ["一次資料", "都市伝説"]


def test_hashes_and_spaces_are_stripped_before_use():
    assert publish.tags_for("#未 解決", ["#都市伝説"]) == ["未解決", "都市伝説"]


def test_a_missing_brand_file_does_not_break_the_description(tmp_path):
    """看板が無くても、目次と出典は出す。"""
    assert publish.brand(tmp_path / "nope.yaml") == {}


def test_the_real_brand_file_has_what_the_description_needs():
    b = publish.brand()
    assert b.get("name") and b.get("lead") and b.get("hashtags")
    assert len(b["hashtags"]) >= 3
