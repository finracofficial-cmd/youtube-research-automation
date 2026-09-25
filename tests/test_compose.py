"""塊ごとの執筆と、外れた章だけの直し。LLMは偽物で通す。"""
from script_engine import compose as C
from script_engine import plan as P
from tests.test_plan import good_plan


def _fake_chat(log):
    """呼ばれた内容を記録し、指示の塊名に応じた本文を返す。"""
    def chat(messages):
        user = messages[-1]["content"]
        log.append(user)
        if "## 冒頭" in messages[1]["content"]:
            return "巨石遺跡。\n1000トンの石がある。\n継ぎ目に紙一枚入らない石壁。\n切り出し途中の巨石。\n誰も入っていない地下室。\n運び方は決まっていない。\nそれでは私と共に、巨石遺跡へと迫っていこう。"
        if "## 着地" in messages[1]["content"]:
            return "一般化の話。\n\n回収の話。\n\n事実はここまでだ。ここからは資料に無い。私の考えだ。運ぶ気が無かった。ここまでが考察だ。\n\n条件の話。\n\nCTAです。"
        # 章。直しの依頼には「ただし」を足して返す
        base = ("巨石は現代の重機でも運べない。そう語られている。結論から言う。運べないのではなく、運ぶ理由が無い。"
                "最大の石は1000トンある。だが同じ石切り場に切り出し途中の石が残っている。"
                "1980年にある観光ガイドが旅行記に書いた。私はこの推定値を疑っている。"
                "では、なぜ運ばなかったのか。")
        if "直した全文" in user:
            base = base.replace("だが同じ", "ただし同じ")
        return base
    return chat


def test_blocks_follow_the_plan_in_order():
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    assert [b.key for b in blocks] == ["opening", "chapter1", "chapter2", "closing"]
    assert sum(b.target_chars for b in blocks) > 900 / 60 * 300
    assert "1章で保留にした問いだ" in blocks[2].brief      # 最終章が回収に入る
    assert "1章で保留にした問い" not in blocks[3].brief     # 着地では繰り返さない（実測で二重になった）
    assert "最後の章で扱う" not in blocks[1].brief         # 伏線は冒頭で置く。章に書かせると次章の引きに付いた


def test_chapter_paragraphs_are_located_after_assembly():
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    blocks[0].text = "冒頭。\n\n具体。\n\n合図。"
    blocks[1].text = "第1章。"
    blocks[2].text = "第2章。"
    blocks[3].text = "一般化。\n\n回収。\n\n考察。\n\n条件。\n\nCTA。"
    assert C.paragraph_index(blocks, "chapter1") == 3
    assert C.paragraph_index(blocks, "chapter2") == 4
    assert C.paragraph_index(blocks, "closing") == 5


def test_only_flagged_blocks_are_rewritten():
    log = []
    p = P.validate(good_plan(2))
    text, audit, left = C.compose(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"],
                                  duration_sec=60, chat=_fake_chat(log), rounds=1)
    first_pass = 4
    rewrites = [u for u in log if "直した全文" in u]
    assert len(log) >= first_pass
    # 直しの依頼は、指摘のある塊にだけ届く。全塊ではない
    assert 0 < len(rewrites) <= 4
    assert "ただし" in text                      # 直しが本文に反映されている
    assert text.count("\n\n") >= 4               # 塊が空行で区切られている


def test_route_sends_opening_notes_to_the_opening_and_rates_to_chapters():
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    for b in blocks:
        b.text = "文。"
    from script_engine.devices import Audit
    a = Audit(minutes=15, per_min={}, chapters=[], plant=False, callback=True,
              opening_images=0, opening_defeat=True, subject_free_run=9, unlanded=[], padding=[],
              notes=["前半に伏線が無い", "留保（ただし）が 0.00/分。参考は 0.19〜0.53/分", "終盤に回収が無い"])
    C.route(blocks, a, ["話速 200字/分 が 320〜410 の外", "平均文長 28.0字 が 17.0〜26.0 の外"])
    assert any("伏線" in n for n in blocks[0].notes)
    assert any("回収" in n for n in blocks[-1].notes)
    # 率と話速は書き直しの引き金にしない（報告だけ）。文長は章へ
    assert not any("留保" in n or "話速" in n for b in blocks for n in b.notes)
    assert all(any("平均文長" in n for n in b.notes) for b in blocks[1:-1])



def test_chapter_length_follows_the_material():
    """等分すると資料の無い章を「記録は無い」の言い換えで埋める。厚みで配る。"""
    shares = C.chapter_shares([1.0, 7.0, 1.0])
    assert shares[1] > shares[0] == shares[2]
    assert abs(sum(shares) - 1.0) < 1e-9
    # 薄い章は平均の6割で止まり、厚い章は1.5倍で止まる
    lo, hi = C.chapter_shares([0.0, 100.0])
    assert abs(lo / hi - 0.6 / 1.5) < 1e-9


def test_a_chapter_without_sources_is_told_not_to_pad():
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"],
                                duration_sec=900, weights=[3.0, 0.0])
    assert C.NO_SOURCE_NOTE not in blocks[1].brief
    assert C.NO_SOURCE_NOTE in blocks[2].brief
    assert blocks[1].target_chars > blocks[2].target_chars


def test_excess_adversatives_and_tsumari_are_thinned():
    """書き直しでは減らない（v3 0.93/分、v4 1.00/分）。上限を超えた接続詞だけ落とす。"""
    text = "".join(f"だが、事実{i}がある。" for i in range(5)) + "".join(f"つまり、要点{i}だ。" for i in range(6))
    out = C.thin_connectives(text)
    assert out.count("だが、") == 3 and out.count("つまり、") == 4
    assert "事実4がある。" in out and "要点5だ。" in out      # 文は残る


def test_unsourced_numbers_in_the_plan_are_dropped_before_writing():
    p = P.validate(good_plan(1))
    p.chapters[0].numbers = [{"value": "1000トン", "caveat": ""}, {"value": "葉が7枚で茎が17センチ", "caveat": ""}]
    dropped = P.strip_unsourced(p, "最大の石は1000トンある。")
    assert dropped[0] == "葉が7枚で茎が17センチ"
    assert [n["value"] for n in p.chapters[0].numbers] == ["1000トン"]



def test_writable_minutes_reports_what_the_material_supported():
    """字数を上限にしたので、資料が薄いと台本は短く出る（v6: 3,383字 ≈ 9分）。"""
    from script_engine.cli import writable_minutes
    assert round(writable_minutes(3383)) == 9
    assert round(writable_minutes(5400)) == 15



def test_speculation_is_wrapped_in_markers_or_built_from_the_plan():
    sp = {"claim": "運ぶ気が無かったのだと思う", "reasons": ["坂の跡が無い", "切り出しが途中で止まっている"],
          "weakness": "運搬の道具が出土すれば"}
    closing = "一般化。\n\n回収。\n\n条件。\n\nCTAです。"
    got = C.ensure_speculation(closing, sp)
    paras = got.split("\n\n")
    assert paras[2].startswith("事実はここまでだ。ここからは資料に無い。私の考えだ。")
    assert paras[2].endswith("ここまでが考察だ。") and "ただし、運搬の道具が出土すればなら" in paras[2]
    assert paras[3] == "条件。"
    # 始まりの印だけ書かれていたら、閉じを足す
    half = "一般化。\n\n回収。\n\nここからは資料に無い。私の考えだ。運ぶ気が無かった。\n\n条件。\n\nCTA。"
    got = C.ensure_speculation(half, sp)
    assert got.split("\n\n")[2].endswith("ここまでが考察だ。")
    assert C.ensure_speculation(got, sp) == got


def test_adjacent_duplicate_sentences_are_dropped():
    text = "結論から言う。写本群である。\n写本群である。\n別の事実だ。"
    assert C.dedupe_adjacent(text).count("写本群である。") == 1
    far = "写本群である。" + "".join(f"第{i}の事実だ。" for i in range(4)) + "写本群である。"
    assert C.dedupe_adjacent(far).count("写本群である。") == 2      # 離れた反復は残す


def test_shot_hints_come_from_evidence_jargon_and_swings():
    p = P.validate(good_plan(2))
    hints = C.hints_for_shots(p)
    assert len(hints) == 2 and "石切り場" in hints[0] and "層序" in hints[0]



def test_invented_origins_are_flagged_when_the_plan_has_none():
    """「2000年代のYouTubeやネット記事で広まった」と書いた。資料に無い。"""
    p = P.validate(good_plan(1))
    c = p.chapters[0]
    c.origin = {"who": "不明", "year": "不明"}
    got = C.origin_invented("バチカン隠蔽説は、2000年代のYouTubeやネット記事で広まった。証拠は無い。", c)
    assert got and "2000年代" in got[0]
    c.origin = {"who": "ベイジェント", "year": "1991"}
    assert C.origin_invented("1991年の書籍で広まった。", c) == []
