"""空き時間を埋める語句テロップの検査。

データ由来の部品は台本に根拠がある所にしか出せず、被覆率が42%で止まった
（参考CHの実測は67%）。残りを逐語の語句で埋める。逐語であることが唯一の
安全性の根拠なので、そこを固定する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
from autolayout import Cue, Line, coverage, fill_gaps, phrase  # noqa: E402


def test_phrase_is_always_verbatim():
    """出す語句は必ず行の連続部分文字列。言い換えたら音声と食い違う。"""
    texts = [
        "ヴォイニッチ手稿は今も解読されていません。",
        "アンティキティラ島の機械が発見されたのは1901年です。",
        "ピリ・レイスの地図が話題になりました。",
        "デリーの鉄柱は錆びないと言われます。",
        "「未解読」という言葉が一人歩きしています。",
        "ナスカの地上絵を上空から撮影しました。",
    ]
    for t in texts:
        got = phrase(t)
        assert got, t
        assert got in t, (got, t)


def test_phrase_prefers_the_longer_compound():
    """「ヴォイニッチ」ではなく「ヴォイニッチ手稿」を出す。

    正規表現の交替は左から試され、先に当たった枝が位置を消費する。
    短い枝を前に置くと長い複合語を永久に取りこぼす。
    """
    assert phrase("ヴォイニッチ手稿は未解読です。") == "ヴォイニッチ手稿"
    assert phrase("アンティキティラ島の機械の話です。") == "アンティキティラ島の機械"
    assert phrase("ピリ・レイスの地図を見ます。") == "ピリ・レイスの地図"


def test_phrase_skips_contentless_lines():
    """どの台本にも出る語を大字で出しても、画面が埋まるだけで何も伝わらない。"""
    for t in ["これは重要な指摘です。", "つまり可能性が残るということです。",
              "そういう結果になりました。"]:
        assert phrase(t) is None, t


_SUBJECTS = ["ヴォイニッチ手稿", "アンティキティラ島の機械", "ピリ・レイスの地図",
             "デリーの鉄柱", "ナスカの地上絵", "バグダッドの電池"]


def _lines(n: int, step: float = 4.0) -> list[Line]:
    """語が毎行変わる台本。同じ語を続けて出さない規則に引っかからないように。"""
    return [Line(startSec=i * step, durationSec=step,
                 text=f"{_SUBJECTS[i % len(_SUBJECTS)]}の話をします。")
            for i in range(n)]


def test_fill_gaps_raises_coverage():
    lines = _lines(25)          # 100秒
    before = [Cue(kind="stat", startSec=0.0, durationSec=6.0, zone="left")]
    after = fill_gaps(before, lines, 100.0)
    assert coverage(after, 100.0) > coverage(before, 100.0) + 0.5


def test_fill_gaps_never_covers_an_occupied_stretch():
    """既にある部品の上に重ねない。埋めるのは空いている時間だけ。"""
    lines = _lines(25)
    busy = [Cue(kind="stat", startSec=10.0, durationSec=20.0, zone="left")]
    added = [c for c in fill_gaps(busy, lines, 100.0) if c.kind == "telop"]
    for c in added:
        assert c.endSec <= 10.0 + 1e-6 or c.startSec >= 30.0 - 1e-6, (c.startSec, c.endSec)


def test_fill_gaps_emits_only_verbatim_text():
    lines = _lines(25)
    by_time = {l.startSec: l.text for l in lines}
    for c in fill_gaps([], lines, 100.0):
        if c.kind != "telop":
            continue
        assert any(c.payload["text"] in t for t in by_time.values())


def test_fill_gaps_stops_when_no_phrase_is_available():
    """語句が取れない台本で、空文字のテロップを量産しない。"""
    flat = [Line(startSec=i * 4.0, durationSec=4.0, text="そういうことです。")
            for i in range(25)]
    assert [c for c in fill_gaps([], flat, 100.0) if c.kind == "telop"] == []


def test_fill_gaps_ignores_gaps_shorter_than_the_minimum():
    """一瞬だけ空いた隙間に文字を差し込んでも読めない。"""
    lines = _lines(25)
    dense = [Cue(kind="stat", startSec=0.0, durationSec=49.0, zone="left"),
             Cue(kind="stat", startSec=50.0, durationSec=50.0, zone="right")]
    added = [c for c in fill_gaps(dense, lines, 100.0) if c.kind == "telop"]
    assert added == []


def test_fill_gaps_stops_at_the_reference_density():
    """参考chのストーリーボードを取って数え直した値で止める。

    54コマ中51コマに札が出ていた（94%）。以前ここは67%で「参考動画の実測」
    と書いてあったが、フレームを見ずに出した数字だった。何も載っていないのは
    暗転などごく一部しかない。埋めきらないことだけは残す。
    """
    lines = _lines(60, step=5.0)   # 300秒
    got = fill_gaps([], lines, 300.0)
    assert 0.85 <= coverage(got, 300.0) <= 0.96


def test_fill_gaps_does_not_repeat_a_word_back_to_back():
    """同じ語が続けて出ると、画面が止まって見える。"""
    same = [Line(startSec=i * 4.0, durationSec=4.0, text="ヴォイニッチ手稿の話です。")
            for i in range(25)]
    texts = [c.payload["text"] for c in fill_gaps([], same, 100.0) if c.kind == "telop"]
    assert all(a != b for a, b in zip(texts, texts[1:]))


def test_phrase_rejects_words_cut_mid_token():
    """送り仮名のある語は、漢字だけ見るとどこで切っても語として成立する。

    実測で「比較的新しい」から「比較的新」が出た。
    """
    assert phrase("比較的新しい時代のものです。") is None
    # 副詞の語幹。漢字2文字を受けるようにした副作用（実測で「非常」が出た）
    assert phrase("非常に興味深い結果でした。") is None


def test_phrase_prefers_words_rare_in_the_script():
    """どの行にも出る語を大書きしても、画面が埋まるだけで何も伝わらない。

    実測で「観光客」が大書きされた。台本全体での出現回数で選び直す。
    """
    freq = {"歯車比": 1, "研究": 30}
    got = phrase("研究の結果、歯車比が判明した。", freq)
    assert got == "歯車比"


def test_phrase_rejects_fragments_split_off_a_number():
    """単位や助数詞を数から切り離した断片は語ではない。

    実測で「50万年前」から「万年前」、「30個以上」から「個以上」が出た。
    """
    assert "万年前" not in (phrase("50万年前の岩に埋まっていた。", {}) or "")
    assert "個以上" not in (phrase("歯車は30個以上あった。", {}) or "")
