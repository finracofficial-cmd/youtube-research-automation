"""装置の監査が、参考2本を通し、うちの台本の欠けを言い当てること。"""
import re
from pathlib import Path

import pytest

from script_engine import devices as D

PYRAMID = Path("analysis/transcripts/pyramid_60rpcKkB7d0.md")
VOYNICH = Path("analysis/transcripts/voynich_AE6JGXXEBQU.md")
OURS = Path("analysis/drafts_flat/voynich-manuscript_2026-09-21.txt")  # 一気書きの記録


def from_transcript(path: Path) -> str:
    """文字起こし（`MM:SS` 文 / ## 章）を、空行区切りの塊に戻す。"""
    blocks, cur = [], []
    for l in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^`\d\d:\d\d` (.*)$", l)
        if m:
            # 〔?...〕 は自動字幕の聞き取りが確定しなかった印。本文ではない
            cur.append(m.group(1).replace("〔?", "").replace("〕", ""))
        elif l.startswith("## "):
            if cur:
                blocks.append("".join(cur))
            cur = []
    if cur:
        blocks.append("".join(cur))
    return "\n\n".join(blocks)


def test_the_pyramid_video_passes_its_own_audit():
    """型の出どころが、その型の監査を通ること。投稿者の手動字幕なので本文は正確。
    ここが落ちたら閾値か検出のどちらかが壊れている。"""
    a = D.audit(from_transcript(PYRAMID), 2272, subject="ピラミッド", kind="bundle",
                chapter_blocks=list(range(1, 10)))
    assert a.ok, a.notes


def test_the_voynich_video_passes_except_for_caption_artifacts():
    """自動字幕は文の切れ目が消える（冒頭の3つの具体が1文に潰れている）。
    それ以外は通ること。"""
    a = D.audit(from_transcript(VOYNICH), 3159, subject="ヴォイニッチ手稿", kind="flagship",
                chapter_blocks=[1, 2, 3, 4])
    assert all("冒頭の体言止め" in n for n in a.notes), a.notes


def test_reference_rates_are_the_documented_ones():
    """REFERENCE_PER_MIN は参考2本をこの検出器で測った値。検出器を変えたら測り直す。"""
    p = D.audit(from_transcript(PYRAMID), 2272, subject="ピラミッド", chapter_blocks=list(range(1, 10)))
    v = D.audit(from_transcript(VOYNICH), 3159, subject="ヴォイニッチ手稿", kind="flagship",
                chapter_blocks=[1, 2, 3, 4])
    for k, (lo, hi) in D.REFERENCE_PER_MIN.items():
        got = sorted([p.per_min[k], v.per_min[k]])
        assert got[0] == pytest.approx(lo, abs=0.02), (k, got)
        assert got[1] == pytest.approx(hi, abs=0.02), (k, got)


def test_our_flat_draft_is_caught_on_the_devices_it_lacks():
    """style の検査には通っていた台本。読むと平板だった理由が、ここで数字になる。"""
    a = D.audit(OURS.read_text(encoding="utf-8"), 900, subject="ヴォイニッチ手稿")
    assert a.per_min["private"] == 0            # 語り手が一度も出ない
    assert a.per_min["reserve"] == 0            # 「ただし」が無い
    assert a.per_min["pivot"] > D.CEIL_PIVOT    # 否定の連打
    assert not a.plant and not a.callback       # 伏線も回収も無い
    joined = "\n".join(a.notes)
    assert "語り手の判断" in joined and "留保" in joined and "否定の連打" in joined


def test_chapters_are_found_from_the_launch_line():
    """出発の合図（私と共に〜迫っていこう）の次から、末尾4塊の手前までが章。"""
    blocks = D.split_blocks(OURS.read_text(encoding="utf-8"))
    idx = D.guess_chapters(blocks)
    assert len(idx) == 5
    assert all(len(blocks[i]) >= 15 for i in idx)


def test_enumeration_filler_is_padding():
    sents = ["測定は4点行われた。", "1点目は1404年の値を示している。", "2点目が1438年の値だった。",
             "3点目と4点目もこの範囲内だった。"]
    assert any("列挙の穴埋め" in x for x in D.padding(sents))


def test_near_repeats_are_padding_but_distant_callbacks_are_not():
    near = ["ヴォイニッチ手稿の材料は15世紀初頭のものである。", "インクの年代は測っていない。",
            "物理的に見て材料は15世紀初頭のものだ。"]
    assert any("言い直し" in x for x in D.padding(near, "ヴォイニッチ手稿"))
    far = ["奴隷なのか、国民だったのか。"] + [f"第{i}の事実が出た。" for i in range(12)] \
        + ["奴隷なのか、国民だったのか。"]
    assert not D.padding(far)


def test_jargon_counts_as_landed_once_it_is_explained_anywhere():
    """参考はエントロピーを最初の1回だけ言い換え、あとは裸で使う。"""
    sents = ["エントロピーという量がある。", "難しそうな名前だが中身は皆さんが毎日使っているものと同じである。",
             "スマホの予測変換だ。"] + ["エントロピーは2.2だった。"] * 5
    assert D.unlanded_jargon(sents) == []
    assert D.unlanded_jargon(["エントロピーは2.2だった。", "それは高い。"]) == ["エントロピー"]


def test_narrator_presence_counts_judgments_not_fabricated_deeds():
    """「私は全部読んだ」は検出しない。判断だけ数える。"""
    assert D.PRIVATE.search("この点について私は判断を保留する。")
    assert D.PRIVATE.search("私はこの数字を疑っている。")
    assert not D.PRIVATE.search("私の家の近くにある。")


def test_hook_is_accepted_at_the_start_of_the_next_chapter():
    """参考は締め直しを次の章の頭に置くことがある（「ここまでが〜。では〜」）。"""
    cur = ["事実がある。", "記録はない。"]
    nxt = ["ここまでが絵の話だ。", "では文字はどうなのか。"]
    assert D._hooks_out(cur, nxt)
    assert not D._hooks_out(cur, ["文字は3万ある。", "多い。"])


def test_unsourced_numbers_lists_what_the_material_does_not_have():
    got = D.unsourced_numbers("1404年の羊皮紙。全長30センチ。4点を測った。", "1404年から1438年。")
    assert "30センチ" in got and "1404年" not in got and "4点" not in got


def test_the_same_short_sentence_used_as_filler_is_padding():
    """短文を求めると「記録はない。」を穴埋めに繰り返す（実測で1章に5回）。"""
    sents = ["署名はない。", "記録はない。", "日付もない。", "記録はない。", "端が欠けている。", "記録はない。"]
    assert any("同じ短文の反復" in x for x in D.padding(sents))
    assert not any("同じ短文の反復" in x for x in D.padding(sents[:4]))
