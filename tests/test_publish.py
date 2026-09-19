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
