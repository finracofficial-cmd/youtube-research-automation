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
    # 小さく出るのが label、大きく出るのが title。入れ違えると大見出しが空になる
    assert got["chapters"][0]["label"] == "第1章"
    assert got["chapters"][0]["title"].startswith("モアイ")
    # どこまで来たかを持たせる
    assert 0 < got["chapters"][0]["progress"] < got["chapters"][1]["progress"]
    assert got["chapters"][-1]["last"] is True


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


def test_cards_are_rebuilt_from_the_real_speech_not_the_estimate():
    """貼り直していたのは字幕だけで、札は字数割りの概算に残っていた。

    実測で、数値札31枚のうち21枚が「その時に読まれていない数字」を
    出していた。語りと絵と文字がずれて見える原因がこれ。
    """
    est = [{"startSec": 0.0, "durationSec": 10.0, "text": "石は250キロ運ばれた。"},
           {"startSec": 10.0, "durationSec": 10.0, "text": "重さは30トンある。"}]
    # 実際の発話は前半が速く、後半が遅かった
    real = [{"startSec": 0.0, "durationSec": 4.0, "text": "石は250キロ運ばれた。"},
            {"startSec": 4.0, "durationSec": 16.0, "text": "重さは30トンある。"}]
    props = {"subtitles": list(real), "stats": [
        {"startSec": 10.0, "durationSec": 6.0, "value": "30トン", "label": "", "zone": "right"}]}
    got = publish.refresh(props, "石は250キロ運ばれた。\n\n重さは30トンある。", [])
    # 30トンの札は、30トンが読まれている区間（4秒〜）に移っている
    tons = [s for s in got["stats"] if "30" in s["value"]]
    assert tons, got["stats"]
    assert 3.0 <= tons[0]["startSec"] <= 8.0, tons[0]


def test_refresh_without_subtitles_changes_nothing():
    props = {"subtitles": [], "stats": [{"startSec": 5.0, "durationSec": 3.0,
                                         "value": "1", "label": "", "zone": "right"}]}
    got = publish.refresh(dict(props), "本文", [])
    assert got["stats"] == props["stats"]


# ---- 情報の出典 ----

def test_information_sources_are_listed_without_urls():
    """画像の出典とは別。何を読んで書いたのかを載せる。

    URLは載せない。読み上げるものでも押すものでもなく、行が長くなって
    一覧性が落ちる。
    """
    got = publish.sources_block([
        {"kind": "paper", "title": "The Radiocarbon Dating", "year": 2011,
         "venue": "Radiocarbon", "identifier": "10.x/y"},
        {"kind": "book", "title": "Quarried Away", "year": 2008},
    ])
    assert "【情報の出典】" in got
    assert "2011 The Radiocarbon Dating（Radiocarbon／論文）" in got
    assert "2008 Quarried Away（書籍）" in got
    assert "http" not in got and "10.x/y" not in got


def test_html_entities_in_titles_are_decoded():
    """文献APIは題名を実体参照のまま返す（実測で E&amp;G）。"""
    got = publish.sources_block([{"kind": "paper", "title": "A &amp; B", "year": 2024}])
    assert "A & B" in got and "&amp;" not in got


def test_the_same_paper_is_not_listed_twice():
    got = publish.sources_block([{"kind": "paper", "title": "同じ題", "year": 2020},
                                 {"kind": "paper", "title": "同じ題", "year": 2020}])
    assert got.count("同じ題") == 1


def test_no_sources_means_no_section_rather_than_an_empty_heading():
    assert publish.sources_block([]) == ""
    out = publish.build("", [], "【画像・資料の出典】\n・x — CC BY 4.0", sources=[])
    assert "情報の出典" not in out
    # 画像の出典は残す。CC BY は表示が条件なので落とせない
    assert "CC BY 4.0" in out


def test_information_sources_come_before_the_image_credits():
    out = publish.build("", [], "【画像・資料の出典】\n・x — CC BY 4.0",
                        sources=[{"kind": "paper", "title": "論文題", "year": 2020}])
    assert out.index("情報の出典") < out.index("画像・資料の出典")
