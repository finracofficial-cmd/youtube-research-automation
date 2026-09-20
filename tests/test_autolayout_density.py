"""札の密度と重なり。

参考chのストーリーボードを数えたら54コマ中51コマに札が出ていた（94%）。
こちらは実測64%で、原因は語句が取れる行が30%しか無かったこと。
漢字2文字まで受けて上げたが、上げた結果いくつか壊れたので、そこを縛る。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))

from autolayout import (  # noqa: E402
    Cue, MIN_DURATION, cap_concurrent, phrase, schedule, _phrases,
)


def cue(kind, start, dur, zone, **payload):
    return Cue(kind=kind, startSec=start, durationSec=dur, zone=zone, payload=payload)


def test_a_centre_piece_is_never_shown_with_anything_else():
    """中央の部品は画面いっぱいに文字を出す。

    実測で巨大な「パロ」が「約10メートル」と「82トン」の上に乗っていた。
    """
    got = schedule([cue("glyph", 10.0, 6.0, "center"),
                    cue("stat", 11.0, 5.0, "left"),
                    cue("stat", 12.0, 5.0, "right")])
    zones = [c.zone for c in got]
    assert "center" in zones
    assert zones.count("center") == 1 and len(got) == 1


def test_pieces_in_different_zones_still_share_the_screen():
    got = schedule([cue("stat", 10.0, 5.0, "left"),
                    cue("stat", 10.5, 5.0, "right")])
    assert len(got) == 2


def test_holding_a_piece_does_not_push_past_the_concurrency_limit():
    """hold() は同じゾーンの次の部品までしか見ない。

    実測で4つが同時に出て画面が埋まっていた。落とさず、終わりを早める。
    """
    got = cap_concurrent([cue("stat", 0.0, 60.0, "left"),
                          cue("stat", 5.0, 20.0, "right"),
                          cue("stat", 6.0, 20.0, "corner"),
                          cue("stat", 7.0, 20.0, "upper")], max_concurrent=3)
    worst = 0
    for t in [x / 4 for x in range(0, 300)]:
        worst = max(worst, sum(1 for c in got if c.startSec <= t < c.endSec))
    assert worst <= 3
    # 落としていない。全部残っている
    assert len(got) == 4
    assert all(c.durationSec >= MIN_DURATION for c in got)


def test_two_kanji_words_are_available_now():
    """漢字3文字以上に絞っていたら、語句が取れる行が30%しか無かった。"""
    assert "人力" in _phrases("人力では動かせないはずの石が、")
    assert "石柱" in _phrases("高さ5メートルの石柱。")


def test_words_that_only_point_at_a_position_or_time_are_not_shown():
    """大書きしても何も言っていない語。

    漢字2文字を受けるようにしたら「場所」「最後」「近年」「内側」が
    大字で並んだ。
    """
    for weak in ("場所", "最後", "近年", "内側", "議論", "候補"):
        assert weak not in _phrases(f"その{weak}については後で話す。")


def test_a_telop_is_always_verbatim_from_the_line():
    """言い換えると音声と食い違う余地ができる。"""
    text = "サーセン石の産地も、近年になって特定された。"
    got = phrase(text)
    assert got is None or got in text


# ---- 章カードの進捗 ----

def test_a_chapter_card_knows_where_it_is_in_the_video():
    """参考chは画面下に位置を示すバーと「ここから最後の話」の印を出していた。"""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "video"))
    import chapters as ch

    got = ch.cards([{"startSec": 0.0, "title": "はじめに"},
                    {"startSec": 100.0, "title": "第一の話"},
                    {"startSec": 500.0, "title": "まとめ"}], 1000.0)
    # 0秒の「はじめに」は画面に出さない
    assert [c["startSec"] for c in got] == [100.0, 500.0]
    assert got[0]["progress"] == 0.1 and got[0]["span"] == 0.4
    assert got[1]["last"] is True


def test_the_big_line_is_the_title_and_the_small_one_is_the_label():
    """入れ違えると大見出しが空になる。実測で章カードの中央が空白になった。"""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "video"))
    import chapters as ch

    got = ch.cards([{"startSec": 0.0, "title": "はじめに"},
                    {"startSec": 60.0, "title": "モアイは歩いて運ばれた"},
                    {"startSec": 900.0, "title": "まとめ"}], 1000.0)
    assert got[0]["label"] == "第1章"
    assert got[0]["title"] == "モアイは歩いて運ばれた"
    # 締めは番号を振らない
    assert got[1]["label"] == "まとめ" and got[1]["title"] == ""


def test_cards_under_a_chapter_card_are_removed():
    """章カードは画面を覆う。実測で「巨石」の大字が突き抜けていた。"""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "video"))
    import explainers as ex

    props = {"chapters": [{"startSec": 60.0, "durationSec": 3.0}],
             "telops": [{"startSec": 61.0, "durationSec": 4.0},
                        {"startSec": 200.0, "durationSec": 4.0}],
             "subtitles": [{"startSec": 61.0, "durationSec": 2.0}]}
    got = ex.clear_for_chapters(props)
    assert [t["startSec"] for t in got["telops"]] == [200.0]
    assert len(got["subtitles"]) == 1   # 語りは続いている
