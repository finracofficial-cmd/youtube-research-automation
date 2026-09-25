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
    text = "最大の石は1000トンある〔3〕。\n継ぎ目に紙一枚入らない。\n石壁が3枚ある。"
    assert C.uncited(text) == ["石壁が3枚ある。"]
    # 言い回しの数字と主張文の数字には番号を求めない（求めて章を無駄に書き直していた）
    assert C.uncited("15世紀初頭という推定である。1章で保留にした問いだ。ルドルフ2世の元にあった。") == []
    assert C.uncited("16世紀のプラハで1612年まで所有した。", claim="16世紀のプラハで皇帝の元にあった。") == ["16世紀のプラハで1612年まで所有した。"]
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
    assert 2 + 4 <= fac.calls <= 2 + 2 * 4        # 設計図2本 + 塊4つ（2本目は点が低いときだけ）
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
    assert "文体が参考のレンジ内" not in PL.gate("x", a, style, [])   # 尺は品質の門に入れない
    ok, mins = PL.enough_material(style, 900)
    assert not ok and mins < 5
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



def test_plant_and_callback_are_guaranteed_even_if_the_writer_drops_them():
    """設計図には必ずあるのに、3本に1本は書き手が落とした（bench 実測）。機械的に置く。"""
    opening = "巨石遺跡。\n1000トンの石がある。\n\nそれでは私と共に、巨石遺跡へと迫っていこう。"
    got = C.ensure_plant(opening, "そもそも誰が運んだのか")
    assert "そもそも誰が運んだのか。この問いは最後の章で扱う。" in got
    assert got.index("最後の章で扱う") < got.index("私と共に")
    assert C.ensure_plant(got, "そもそも誰が運んだのか") == got        # 二重に入れない
    last = "巨石は宇宙人が運んだ。\nそう語られている。\n出どころはある。"
    got = C.ensure_callback(last, "そもそも誰が運んだのか", "運んだ人の名は記録に無い。")
    assert got.startswith("1章で保留にした問いだ。そもそも誰が運んだのか。運んだ人の名は記録に無い。\n巨石は")
    assert C.ensure_callback(got, "そもそも誰が運んだのか", "x") == got


def test_verdict_is_placed_after_the_claim_is_voiced_when_the_writer_skips_it():
    """束ね型の章は「通説→結論→なぜ」。書き手は3本中 1〜3章しか守らない（bench 実測）。"""
    ch = "巨石は現代の重機でも運べない。\nそう語られている。\n最大の石は1000トンある。\n石切り場に途中の石が残る。"
    got = C.ensure_verdict(ch, "運べないのではなく、運ぶ理由が無い。")
    assert got.splitlines()[2] == "結論から言う。運べないのではなく、運ぶ理由が無い。"
    assert C.ensure_verdict(got, "運べないのではなく、運ぶ理由が無い。") == got   # 二重に置かない
    already = "結論から言う。これは正しい。\n理由はこうだ。"
    assert C.ensure_verdict(already, "x") == already


def test_counted_units_with_single_digits_are_checked_against_the_material():
    """「皇帝は1名だけ」と、数えていないものを数字にした。1桁でも数えた体の単位は見る。"""
    from script_engine.devices import unsourced_numbers
    assert "1名" in unsourced_numbers("所有者として伝えられる皇帝は1名だけである。", "資料には名前が無い。")
    assert unsourced_numbers("3つの説がある。", "") == []                 # 言い回しの1桁は見ない


def test_fragments_like_tanbun_are_padding():
    from script_engine.devices import padding
    assert any(x.startswith("断片") for x in padding(["結論から言う。", "短文。", "短文。", "正しい。"]))
    assert not any(x.startswith("断片") for x in padding(["結論から言う。", "正しい。", "無い。"]))



def test_only_the_relevant_facts_are_sent_to_a_chapter_with_original_numbers():
    facts = ["1931 John Manly Roger Bacon and the Voynich MS https://doi.org/10.2307/2848508",
             "1974 Robert Brumbaugh Botany and the Voynich Manuscript https://doi.org/10.2307/2851756",
             "手稿の植物の絵は全体の7割を占める。"]
    block = C.facts_for("手稿に描かれている植物は実在する植物に基づいている。Botany の指摘。", facts, limit=1)
    assert "〔2〕 1974 Robert Brumbaugh" in block          # 関係する行が、通し番号のまま
    assert "〔3〕 手稿の植物の絵" in block                   # 題材の記述は常に入る
    assert "〔1〕" not in block                              # 関係の薄い出典は落ちる


def test_a_second_candidate_is_written_only_when_the_first_scores_low(tmp_path):
    """常に2本作ると章の呼び出しが倍になる。1本目が閾値を超えたら作らない。"""
    spec = tmp_path / "m.yaml"
    spec.write_text("subject: 巨石遺跡\nsubject_en: megalith\ngenre: 古代の謎\nclaims:\n- ja: a\n  en: a\n- ja: b\n  en: b\n",
                    encoding="utf-8")
    fac = FakeFactory()
    r = PL.run_planned(MATERIAL, spec, duration_sec=120, model="fake", rounds=0, plans=1,
                       candidates=2, chat_factory=fac, log=lambda *a, **k: None)
    # 設計図1 + 冒頭1 + 章2（偽の章は結論・引き・出どころ・振り子が揃い閾値を超える）+ 着地（点が低く2本）
    assert fac.calls <= 1 + 1 + 2 + 2
    assert r.text


def test_rate_notes_do_not_trigger_rewrites():
    from script_engine.devices import Audit
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    for b in blocks:
        b.text = "文。"
    a = Audit(minutes=15, per_min={}, chapters=[], plant=True, callback=True, opening_images=3,
              opening_defeat=True, subject_free_run=9, unlanded=[], padding=[],
              notes=["留保（ただし）が 0.00/分。参考は 0.19〜0.53/分",
                     "文頭の反転（だが・しかし）が 1.40/分。参考は最大 0.53/分。否定の連打になっている",
                     "前半に伏線（「この問いは最後の章で扱う」）が無い"])
    C.route(blocks, a, ["話速 200字/分 が 320.0〜410.0 の外", "平均文長 28.0字 が 17.0〜26.0 の外"])
    assert not any("留保" in n or "反転" in n or "話速" in n for b in blocks for n in b.notes)
    assert any("伏線" in n for n in blocks[0].notes)
    assert all(any("平均文長" in n for n in b.notes) for b in blocks[1:-1])



def test_claims_are_matched_back_to_the_video_titles_they_came_from():
    told = ["死海文書最大の謎！バチカンが隠したとされるキリストの秘密を徹底解説",
            "死海文書に記された救世主の正体が判明しました…古代文書に隠された謎と禁断の真実"]
    got = PL.match_told(["バチカンが死海文書を隠した", "死海文書に救世主の正体が書かれている", "月は石でできている"], told)
    assert got["バチカンが死海文書を隠した"].startswith("死海文書最大の謎")
    assert got["死海文書に救世主の正体が書かれている"].startswith("死海文書に記された救世主")
    assert "月は石でできている" not in got


def test_spec_links_every_claim_to_a_candidate():
    from research.spec_from_subject import spec_problems
    ok = {"mystery": {"ja": "秘密はあるか", "candidates": ["ある", "無い"]},
          "claims": [{"ja": "バチカンが死海文書を隠した", "supports": "ある"}]}
    assert spec_problems(ok) == []
    bad = {"mystery": {"ja": "秘密はあるか", "candidates": ["ある", "無い"]},
           "claims": [{"ja": "バチカンが死海文書を隠した", "supports": "DNA説"}]}
    assert any("supports" in x for x in spec_problems(bad))
