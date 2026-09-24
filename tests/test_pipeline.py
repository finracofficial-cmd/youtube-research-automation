"""一本道と、候補の選び方と、合格条件。LLMは偽物。"""
import json

from script_engine import bench as B
from script_engine import compose as C
from script_engine import pipeline as PL
from script_engine import plan as P
from tests.test_plan import good_plan

MATERIAL = """# 題材: 巨石遺跡
## 使う一次資料（これ以外を出典として書かない）
- 2015 Jane Doe The Megalithic Quarry of Baalbek https://doi.org/10.1/x
- 1980 Old Guide Travel notes https://example.invalid

## 一次資料から拾った数字（可能な限りこれを使う）
- 最大の石は1000トンある。  [10.1/x]

## 題材の記述（Wikipedia日本語版の冒頭）
見た目の具体（色・形・数・場所）と、説の出どころ（誰が・何年に）の手がかりに使う。
出典としては書かない。ここにある数字も、上の資料に無ければ裏の取れていない数字として扱う。
継ぎ目に紙一枚入らない石壁が3段ある。
"""


def test_facts_are_numbered_from_sources_numbers_and_description():
    facts = C.facts_from_material(MATERIAL)
    assert facts[0].startswith("2015 Jane Doe")
    assert "最大の石は1000トンある。  [10.1/x]" in facts
    assert "継ぎ目に紙一枚入らない石壁が3段ある。" in facts
    assert not any(f.startswith("見た目") or f.startswith("出典と") for f in facts)
    block = C.facts_block(facts)
    assert "〔1〕 2015 Jane Doe" in block and "〔3〕" in block


def test_citation_markers_are_checked_then_stripped():
    text = "最大の石は1000トンある〔3〕。\n継ぎ目に紙一枚入らない。\n石壁が3段ある。"
    assert C.uncited(text) == ["石壁が3段ある。"]
    assert "〔" not in C.strip_cites(text) and "1000トンある。" in C.strip_cites(text)


def test_chapter_score_prefers_the_grounded_structured_candidate():
    good = ("結論から言う。これは正しい。1980年に旅行記が書いた。最大の石は1000トンある〔3〕。"
            "だが同じ石切り場に切り出し途中の石が残っている。ただし記録そのものは無い。"
            "私はこの推定値を疑っている。では、なぜ運ばなかったのか。")
    bad = ("石は大きい。石は重い。石は運べない。石は大きい。石は重い。石は運べない。"
           "石の重さは2500トンで、高さは17メートルある。以上である。")
    hi = C.chapter_score(good, material=MATERIAL, target_chars=400, subject="巨石遺跡")
    lo = C.chapter_score(bad, material=MATERIAL, target_chars=400, subject="巨石遺跡")
    assert hi > lo


def test_plan_score_rewards_grounding_and_penalises_a_thesis_about_the_subject():
    p = P.validate(good_plan(2))
    base = P.score(p, MATERIAL, subject="巨石遺跡")
    p2 = P.validate(good_plan(2))
    p2.thesis = "巨石遺跡は謎である"
    assert P.score(p2, MATERIAL, subject="巨石遺跡") < base
    p3 = P.validate(good_plan(2))
    for c in p3.chapters:
        c.origin = {"who": "不明", "year": "不明"}
    assert P.score(p3, MATERIAL, subject="巨石遺跡") < base


class FakeFactory:
    """設計図はJSONで、塊は本文で返す。何回呼ばれたかを数える。"""

    def __init__(self, n_claims=2):
        self.calls = 0
        self.n = n_claims

    def __call__(self, model, json_mode=False, temperature=0.8):
        def chat(messages):
            self.calls += 1
            user = messages[-1]["content"]
            if json_mode:
                return json.dumps(good_plan(self.n))
            if "## 冒頭" in messages[1]["content"]:
                return ("巨石遺跡。\n1000トンの石がある。\n継ぎ目に紙一枚入らない石壁。\n切り出し途中の巨石。\n"
                        "誰も入っていない地下室。\n運び方は決まっていない。\n"
                        "そもそも誰が運んだのか。この問いは最後の章で扱う。\nそれでは私と共に、巨石遺跡へと迫っていこう。")
            if "## 着地" in messages[1]["content"]:
                return ("人は分からないものに、分かった人の名前を貼る。\n名前が貼られると、話は速く広がる。\n"
                        "速く広がった話ほど、断りが落ちる。\n断りが落ちた話だけが残る。\n残った話が、次の人の前提になる。\n\n"
                        "1章で保留にした問いだ。誰が運んだのかは分かっていない。\n最大の石は1000トンあると分かった。\n"
                        "だが誰が運んだかは分かっていない。\n\n石切り場の記録が出れば決着する。\n\nご視聴ありがとうございます。")
            return ("巨石は現代の重機でも運べない。そう語られている。結論から言う。運べないのではなく、運ぶ理由が無い。"
                    "最大の石は1000トンある〔3〕。だが同じ石切り場に切り出し途中の石が残っている。"
                    "1980年に旅行記に載った〔2〕。ただし運搬の記録そのものは無い。私はこの推定値を疑っている。"
                    "では、なぜ運ばなかったのか。")
        return chat


def test_run_planned_returns_measures_and_a_gate(tmp_path):
    spec = tmp_path / "megaliths.yaml"
    spec.write_text("subject: 巨石遺跡\nsubject_en: megalith\ngenre: 古代の謎\nclaims:\n"
                    "- ja: a\n  en: a\n- ja: b\n  en: b\n", encoding="utf-8")
    (tmp_path / "megaliths_sources.json").write_text(json.dumps(
        {"claims": [{"ja": "a", "sources": [{"title": "x"}]}, {"ja": "b", "sources": []}], "background": []}),
        encoding="utf-8")
    fac = FakeFactory()
    r = PL.run_planned(MATERIAL, spec, duration_sec=120, model="fake", rounds=1, plans=2,
                       candidates=2, chat_factory=fac, log=lambda *a, **k: None)
    assert r.plans_tried == 2
    assert "〔" not in r.text                     # 根拠番号は剥がしてある
    assert fac.calls >= 2 + 2 * 4                 # 設計図2本 + 塊4つ×候補2
    m = PL.measures(r)
    assert set(m) >= {"chars", "private", "pivot", "unsourced_numbers", "gate_passed", "calls"}
    assert m["unsourced_numbers"] == 0
    assert isinstance(r.gate, dict) and "資料に無い数字が無い" in r.gate


def test_gate_fails_on_unsourced_numbers_or_missing_loop():
    from script_engine.devices import Audit, ChapterAudit
    from script_engine.style import analyze
    ch = [ChapterAudit(index=1, n_sentences=20, hooks_out=True, verdict_first=True, origin=True, swings=3)]
    a = Audit(minutes=2, per_min={}, chapters=ch, plant=True, callback=True, opening_images=3,
              opening_defeat=True, subject_free_run=6, unlanded=[], padding=[])
    style = analyze("これは文である。" * 40, 120)
    assert PL.gate("x", a, style, [])["資料に無い数字が無い"]
    assert not PL.gate("x", a, style, ["17センチ"])["資料に無い数字が無い"]
    a.callback = False
    assert not PL.gate("x", a, style, [])["伏線と回収がある"]


def test_bench_table_flags_unstable_metrics():
    rows = [{"private": 0.0, "pivot": 1.0, "gate_passed": 1, "calls": 10},
            {"private": 0.3, "pivot": 1.0, "gate_passed": 1, "calls": 12},
            {"private": 0.1, "pivot": 1.0, "gate_passed": 1, "calls": 11}]
    lines = "\n".join(B.table(rows))
    assert "private" in lines and "← 不安定" in lines
    assert "不安定な指標: 1 /" in lines          # pivot と gate_passed は揃っている。calls は数えない
