"""初見の視聴者として読ませる確認。LLMは偽物で通す。"""
import json

from script_engine import compose as C
from script_engine import plan as P
from script_engine import readability as R
from tests.test_compose import _fake_chat
from tests.test_plan import good_plan

QUIZ = {"found": "1898年に測られた", "contents": "巨石", "why_care": "人間に運べないと言われる",
        "question": "誰が運んだのか", "answer": "人間が運んだ",
        "chapters": [{"block": "第1章", "topic": "重機でも運べない話", "result": "運ぶ理由が無い", "why_next": True},
                     {"block": "第2章", "topic": "同じ話", "result": "同じ", "why_next": True}]}


def _blocks(texts: dict):
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    for b in blocks:
        b.text = texts.get(b.key, "文。")
    return blocks


def test_the_reader_sees_labelled_blocks_and_its_problems_are_routed_back():
    seen = []

    def reader(msgs):
        seen.append(msgs[-1]["content"])
        return json.dumps({"problems": [
            {"block": "第1章", "quote": "石切り場が", "kind": "未説明", "why": "石切り場が何か分からない",
             "fix": "石を切り出した場所だと言う"},
            {"block": "[着地]", "quote": "x", "kind": "好み", "why": "言い回し", "fix": ""},   # 種類外は捨てる
            {"block": "第9章", "quote": "x", "kind": "飛躍", "why": "", "fix": ""},           # 無い塊は捨てる
        ], "score": 6, "summary": "基本は分かる"}, ensure_ascii=False)

    blocks = _blocks({"chapter1": "石切り場が残る〔3〕。"})
    got = R.read(blocks, reader, subject="巨石遺跡")
    assert "[基本]" in seen[0] and "[第1章]" in seen[0] and "〔3〕" not in seen[0]
    assert [(p.block, p.kind) for p in got.problems] == [("chapter1", "未説明")]
    assert got.score == 6 and not got.clear
    notes = R.notes_by_block(got)
    assert list(notes) == ["chapter1"] and "石を切り出した場所" in notes["chapter1"][0]


def test_an_unreadable_answer_counts_as_not_clear():
    got = R.read(_blocks({}), lambda msgs: "読めませんでした")
    assert got.score == 0 and not got.clear


def test_the_same_fact_in_two_chapters_is_caught():
    """死海文書では「2021年のAI解析で、同じ巻物に2人の筆写者がいた」が2つの章に出た。"""
    blocks = _blocks({
        "basics": "まず、巨石遺跡とは何なのか。",
        "chapter1": "2021年のAI解析で、同じ巻物に2人の筆写者がいたと分かった。",
        "chapter2": "別の話だ。2021年のAI解析では、同じ巻物に2人の筆写者がいたと分かった。",
    })
    got = R.repeats_across(blocks, "巨石遺跡")
    assert list(got) == ["chapter2"] and "2人の筆写者" in got["chapter2"][0]


def test_compose_rewrites_only_what_the_reader_flagged_and_reads_again():
    log, reads = [], []

    def reader(msgs):
        reads.append(1)
        if len(reads) == 1:
            return json.dumps({"problems": [{"block": "基本", "quote": "調査団", "kind": "飛躍",
                                             "why": "なぜ調査団の話になったのか", "fix": "前の文とつなぐ"}],
                               "score": 5, "summary": ""}, ensure_ascii=False)
        return json.dumps({"problems": [], "score": 8, "summary": "ついていけた", "quiz": QUIZ},
                          ensure_ascii=False)

    p = P.validate(good_plan(2))
    text, audit, left = C.compose(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"],
                                  duration_sec=60, chat=_fake_chat(log), rounds=0, reader=reader)
    rewrites = [u for u in log if "直した全文" in u]
    assert len(reads) == 2
    assert len(rewrites) == 1 and "なぜ調査団の話になったのか" in rewrites[0]
    assert audit.reading.score == 8 and audit.reading.clear


def test_the_gate_includes_whether_a_first_time_viewer_could_follow():
    from script_engine.pipeline import gate
    from script_engine.style import validate
    from script_engine import devices
    text = "巨石遺跡。\n\nまず、巨石遺跡とは何なのか。\n\n結論から言う。正しい。では、なぜか。\n\n答え。"
    a = devices.audit(text, 60, subject="巨石遺跡")
    a.reading = R.Reading(score=9, quiz=QUIZ, n_chapters=2,
                          problems=[R.Problem("chapter1", "x", "意味不明", "", "")])
    assert gate(text, a, validate(text, 60), [])["初見で分かる"] is False
    a.reading = R.Reading(score=6, quiz=QUIZ, n_chapters=2,
                          problems=[R.Problem("chapter1", "x", "未説明", "", "")])   # 未説明と点は門にしない
    assert gate(text, a, validate(text, 60), [])["初見で分かる"] is True


def test_a_script_that_never_says_what_the_subject_is_fails_the_quiz():
    """旧台本（死海文書）は、第1章の前だけでは「いつ・どこで見つかったか」「何が書かれているか」
    「なぜ人々が気にしているのか」を言えなかった。見た人の指摘と同じ所で落ちる。"""
    quiz = dict(QUIZ, found="", contents="", why_care="")
    r = R.Reading(score=6, quiz=quiz, n_chapters=2)
    assert not r.clear and any("何が書かれているか" in g for g in r.gaps())
    notes = R.notes_by_block(r)
    assert any("いつ・どこで見つかったか" in n for n in notes["basics"])
    assert any("なぜ人々が気にしているのか" in n for n in notes["opening"])


def test_a_dangling_reference_fails_the_gate():
    """「そのうちの一本は、タイトルそのものがこうなっている」が何を指すか分からない（旧台本）。"""
    r = R.Reading(score=7, quiz=QUIZ, n_chapters=2,
                  problems=[R.Problem("chapter1", "そのうちの一本は", "宙づり", "", "")])
    assert not r.clear


def test_definition_sentences_are_not_reported_as_unexplained():
    """「外典と呼ばれる」「マソラ本文とは〜」を未説明と返してきた（実測4件）。"""
    def reader(msgs):
        return json.dumps({"problems": [
            {"block": "基本", "quote": "聖書に入っていない古い文書は「外典」と呼ばれる。", "kind": "未説明", "why": "", "fix": ""},
            {"block": "第1章", "quote": "マソラ本文とは、中世以降の本文だ。", "kind": "未説明", "why": "", "fix": ""},
            {"block": "第1章", "quote": "4QMMTに規定がある。", "kind": "未説明", "why": "4QMMTが何か", "fix": ""}],
            "score": 7}, ensure_ascii=False)
    got = R.read(_blocks({}), reader)
    assert [p.quote for p in got.problems] == ["4QMMTに規定がある。"]
