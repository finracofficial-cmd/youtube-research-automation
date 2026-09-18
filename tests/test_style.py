import re
from pathlib import Path

import pytest

from script_engine.style import analyze, validate

TRANSCRIPT = Path("analysis/transcripts/voynich_AE6JGXXEBQU.md")


def _reference_body() -> str:
    text = TRANSCRIPT.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"^`\d\d:\d\d` ", "", l)
                     for l in text.splitlines() if re.match(r"^`\d\d:\d\d`", l))


def test_reference_video_passes_its_own_profile():
    """型の出どころである動画が、その型のバリデータを通ること。
    ここが落ちたら閾値か抽出のどちらかが壊れている。"""
    m = validate(_reference_body(), 3159)
    assert m.ok, m.violations


def test_reference_metrics_match_the_documented_measurements():
    m = analyze(_reference_body(), 3159)
    assert 20.0 <= m.avg_sentence_len <= 23.0     # 文書上 21.6
    assert 340 <= m.chars_per_min <= 375          # 文書上 358
    assert m.plain_form_ratio > 0.95              # 常体161 : 敬体2
    assert m.numerics_per_min > 7.0               # 文書上 7.9


def test_polite_form_script_is_rejected():
    text = "これはペンです。" * 200
    m = validate(text, 600)
    assert not m.ok
    assert any("常体率" in v for v in m.violations)


def test_chatty_narration_is_rejected():
    text = ("皆さんはどう思いますか。" * 4) + ("事実である。" * 300)
    m = validate(text, 600)
    assert any("馴れ合い" in v for v in m.violations)


def test_long_winded_script_is_rejected():
    text = ("この非常に長い一文は事実を詰め込みすぎており読み上げても頭に入らない構造になっているのである。" * 60)
    m = validate(text, 600)
    assert any("平均文長" in v for v in m.violations)


def test_zero_duration_is_an_error():
    with pytest.raises(ValueError):
        analyze("事実である。", 0)


def test_reference_scores_near_perfect_fidelity():
    """参照動画自身の忠実度は1.0に近いこと（指標の定義が壊れていないかの確認）。"""
    m = analyze(_reference_body(), 3159)
    assert m.fidelity > 0.97


def test_fidelity_falls_when_density_drops():
    """レンジ内でも、数字が薄い台本は忠実度が下がること。"""
    dense = "1901年に30個の歯車が出た。" * 120
    thin = "歯車が出たのである。" * 150
    from script_engine.style import analyze as a
    assert a(dense, 600).fidelity > a(thin, 600).fidelity


def test_markdown_is_stripped_from_written_scripts():
    """構成ブロックの名前が見出しとして出力に混ざる。

    指示で禁じても従わないことがあり、実測で15個混入した。読み上げると
    「シャープシャープ 体言止めの一撃」と読まれるので、後処理で落とす。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_engine.write import clean

    raw = (
        "## 体言止めの一撃\n\n"
        "オーパーツ。  \n"
        "2024年現在、報告は16件を超える。\n\n"
        "### 第1主張\n\n"
        "- 与那国島の海底に階段状の構造がある。\n"
        "**重要**なのは年代である。\n"
    )
    out = clean(raw)
    assert "#" not in out
    assert "**" not in out
    assert not any(l.startswith(("- ", "* ")) for l in out.splitlines())
    # 本文は残る
    assert "オーパーツ。" in out
    assert "与那国島の海底に階段状の構造がある。" in out
    assert "重要なのは年代である。" in out
    # 行末の空白（Markdownの改行指示）も落ちる
    assert not any(l != l.rstrip() for l in out.splitlines())


def test_foreign_titles_are_dropped_from_narration():
    """英語の題名は読み上げると日本語の途中で英語が読まれる。

    実測で1つ70字あり、長文272件のうち57件は読点すら無く、
    文が長い原因は文法ではなく埋め込まれた題名だった。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_engine.tighten import drop_foreign_titles as drop

    assert drop("2006年の論文「Archaeological theory and Japanese methodology」では、"
                "銅鐸の用途が議論されている。") == \
        "2006年の論文では、銅鐸の用途が議論されている。"
    # 抜くと修飾先が消える形は、名詞を補う
    assert drop("今回扱った「Archaeological theory in Jomon research」や"
                "「The evaluation of survey」も原文を参照できます。") == \
        "今回扱った論文も原文を参照できます。"


def test_japanese_quotes_survive():
    """日本語の引用は台本の中身。落としてはいけない。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_engine.tighten import drop_foreign_titles as drop

    for text in ["彼は「未解読である」と述べた。",
                 "「与那国島海底遺跡は人工的に作られたものだ」という主張がある。"]:
        assert drop(text) == text


def test_every_foreign_title_is_found_not_just_the_first():
    """日本語の引用が先にある台本で打ち切ると、英語の題名に届かない。

    実測で12件中5件が残った。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_engine.tighten import drop_foreign_titles as drop

    text = ("「与那国島海底遺跡は人工的に作られたものだ」という主張がある。"
            "2006年の論文「Archaeological theory in Jomon research」では否定された。"
            "2018年の論文「The evaluation of archaeological survey」も同じである。")
    out = drop(text)
    assert "Archaeological" not in out and "evaluation" not in out
    assert "与那国島海底遺跡は人工的に作られたものだ" in out


def test_long_sentences_split_only_at_safe_joints():
    """「歯車が、回る」の「が」は主語の印。切ると非文になる。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_engine.tighten import split_long

    # 述語で終わっているので切ってよい
    got = split_long("この装置は1901年に引き上げられたが、当初は腐食した塊と見なされていた。", 26)
    assert "。しかし" in got
    # 主語の印。短い文なのでそもそも触らない
    assert split_long("歯車が、回る。", 26) == "歯車が、回る。"
