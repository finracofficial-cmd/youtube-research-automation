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
        if "## 基本の章" in messages[1]["content"]:
            return "まず、巨石遺跡とは何なのか。1898年に調査団が測った。土台に巨石が並ぶ。では、いま語られている話を、一つずつ確かめていく。"
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
    """冒頭 → 基本（それは何か）→ 章 → 着地。基本の章が無いと、初めて見る人は
    題材が何なのか分からないまま噂の真偽を聞かされる（死海文書）。"""
    p = P.validate(good_plan(2))
    p.told = ["巨石は宇宙人が運んだ！？古代の謎"]
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    assert [b.key for b in blocks] == ["opening", "basics", "chapter1", "chapter2", "closing"]
    assert sum(b.target_chars for b in blocks) > 900 / 60 * 300
    o = blocks[0].brief
    # それは何か → なぜ大事か → 語られている形（前置き付き）→ 共通点 → 問い、の順
    order = [o.index(x) for x in (p.opening["what"], p.opening["significance"], "こんな題名が並ぶ",
                                  "「巨石は宇宙人が運んだ、古代の謎」。", p.opening["curious"], p.mystery)]
    assert order == sorted(order)
    assert "巨石遺跡とは何なのかを押さえておく" in o
    assert "まず、巨石遺跡とは何なのか。" in blocks[1].brief and p.basics["found"] in blocks[1].brief
    ch = blocks[2].brief
    order = [ch.index(x) for x in ("という話だ", p.chapters[0].means, p.chapters[0].basis, "結論から言う",
                                   "どうすれば確かめられるか", p.chapters[0].bearing, p.chapters[0].hook_out)]
    assert order == sorted(order)
    assert "冒頭の問いの答えは何か" in blocks[3].brief                 # 最終章は着地へ渡す
    assert "冒頭の問いに戻る" in blocks[4].brief
    assert "タイトルそのもの" not in ch                                 # 章には題名を差し込まない


def test_chapter_paragraphs_are_located_after_assembly():
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    blocks[0].text = "冒頭。\n\n具体。\n\n合図。"
    blocks[1].text = "基本。"
    blocks[2].text = "第1章。"
    blocks[3].text = "第2章。"
    blocks[4].text = "答え。\n\n考察。\n\n条件。\n\nCTA。"
    assert C.paragraph_index(blocks, "chapter1") == 4
    assert C.paragraph_index(blocks, "chapter2") == 5
    assert C.paragraph_index(blocks, "closing") == 6


def test_only_flagged_blocks_are_rewritten():
    log = []
    p = P.validate(good_plan(2))
    text, audit, left = C.compose(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"],
                                  duration_sec=60, chat=_fake_chat(log), rounds=1)
    first_pass = 5
    rewrites = [u for u in log if "直した全文" in u]
    assert len(log) >= first_pass
    # 直しの依頼は、指摘のある塊にだけ届く。全塊ではない
    assert 0 < len(rewrites) <= 5
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
    assert all(any("平均文長" in n for n in b.notes) for b in blocks[2:-1])
    assert not blocks[1].notes                        # 基本の章には率の指摘を配らない



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
    assert C.NO_SOURCE_NOTE not in blocks[2].brief
    assert C.NO_SOURCE_NOTE in blocks[3].brief
    assert blocks[2].target_chars > blocks[3].target_chars


def test_excess_adversatives_and_tsumari_are_thinned():
    """書き直しでは減らない（v3 0.93/分、v4 1.00/分）。章2回を超えた接続詞だけ落とす。"""
    text = "".join(f"だが、事実{i}がある。" for i in range(5)) + "".join(f"つまり、要点{i}だ。" for i in range(6))
    out = C.thin_connectives(text)
    assert out.count("だが、") == 2 and out.count("つまり、") == 4
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
    closing = "答え。\n\n条件と一般化。\n\nCTAです。"
    got = C.ensure_speculation(closing, sp)
    paras = got.split("\n\n")
    # 答えの段落のすぐあと。視聴者は答えを聞いてから考察を聞く
    assert paras[1].startswith("事実はここまでだ。ここからは資料に無い。私の考えだ。")
    assert paras[1].endswith("ここまでが考察だ。") and "ただし、運搬の道具が出土すればなら" in paras[1]
    assert paras[2] == "条件と一般化。"
    # 始まりの印だけ書かれていたら、閉じを足す
    half = "答え。\n\nここからは資料に無い。私の考えだ。運ぶ気が無かった。\n\n条件。\n\nCTA。"
    got = C.ensure_speculation(half, sp)
    assert got.split("\n\n")[1].endswith("ここまでが考察だ。")
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


def test_verdict_goes_after_the_claim_even_when_the_chapter_is_one_line():
    """章が1行で返ると、行で数える挿入は章の最後に結論を置いた（実測）。"""
    one_line = "バチカンが死海文書を隠した。そう語られている。公開時期を見ればいい。記録は残る。"
    got = C.ensure_verdict(one_line, "隠した証拠は無い。")
    sents = [x for x in got.splitlines() if x]
    assert sents[2] == "結論から言う。隠した証拠は無い。"


def test_video_titles_are_shown_in_the_opening_with_a_setup_sentence():
    """章の中に前置き無しで題名を差し込んだら「流れがよく分からない」と言われた。
    冒頭の「なぜ気になるのか」に、前置き付きでまとめて置く。"""
    opening = ("死海文書。\n1947年に見つかった巻物だ。\n\n"
               "本当にそうなのか。\n死海文書に秘密は書かれているのか。\n\n"
               "それでは私と共に、死海文書へと迫っていこう。")
    got = C.ensure_told_opening(opening, ["死海文書最大の謎！バチカンが隠した秘密"], "死海文書")
    paras = got.split("\n\n")
    assert paras[1] == "動画サイトで『死海文書』と検索すると、こんな題名が並ぶ。\n「死海文書最大の謎、バチカンが隠した秘密」。"
    assert paras[2].startswith("本当にそうなのか。")
    assert C.ensure_told_opening(got, ["死海文書最大の謎！バチカンが隠した秘密"], "死海文書") == got


def test_origin_guesses_and_the_unknown_origin_line_are_removed():
    """「誰が最初に言い出したかは、記録が見つかっていない」を全章に入れていた。
    初見の人には意味の無い文だった。"""
    p = P.validate(good_plan(1))
    c = p.chapters[0]
    c.origin, c.basis = {}, ""
    text = ("バチカンが死海文書を隠した、という話だ。誰が最初に言い出したかは、記録が見つかっていない。"
            "この説は、2014年ごろからYouTubeやネット記事で広まったとされる。証拠は無い。")
    got = C.drop_invented_origins(text, c)
    assert "記録が見つかっていない" not in got and "2014年ごろ" not in got and "証拠は無い。" in got


def test_chapter_ends_on_the_planned_question_when_the_writer_ends_flat():
    text = "証拠は無い。次は、聖書から消えた記述を確かめる。"
    got = C.ensure_hook(text, "では、聖書から消えた記述は本当にあるのか。")
    assert got.splitlines()[-1] == "では、聖書から消えた記述は本当にあるのか。"
    already = "証拠は無い。では、聖書から消えた記述はあるのか。"
    assert C.ensure_hook(already, "では、別の問いなのか。") == already


def test_plant_goes_right_before_the_launch_sentence_in_a_one_paragraph_opening():
    opening = "巨石遺跡。1000トンの石がある。それでは私と共に、巨石遺跡へと迫っていこう。"
    got = C.ensure_plant(opening, "誰が運んだのか")
    lines = [x for x in got.splitlines() if x]
    assert lines[0] == "巨石遺跡。" and lines[-2] == "この問いの答えは、最後に出す。"



def test_the_verdict_is_said_once_not_three_times():
    """「結論から言う。Xだが、Yはない。だが、Xである。Yは報告されていない。」（死海文書の全章）"""
    text = ("AI解析で不自然な痕跡が見つかった、という話だ。結論から言う。"
            "AI解析で見つかったのは複数の筆写者の存在で、偽造の証拠はない。"
            "だが、AI解析で見つかったのは複数の筆写者がいるという事実だ。"
            "偽造の証拠はない。"
            "では、どうすれば確かめられるか。")
    got = C.drop_restated_verdict(text, "AI解析で見つかったのは複数の筆写者の存在で、偽造の証拠はない。")
    lines = [x for x in got.splitlines() if x]
    assert lines == ["AI解析で不自然な痕跡が見つかった、という話だ。", "結論から言う。",
                     "AI解析で見つかったのは複数の筆写者の存在で、偽造の証拠はない。",
                     "では、どうすれば確かめられるか。"]


def test_a_chapter_opens_by_naming_the_claim():
    text = "証拠は無い。では、どうすれば確かめられるか。"
    got = C.ensure_intro(text, "バチカンが死海文書を隠した", "最初")
    assert got.splitlines()[0] == "最初は、バチカンが死海文書を隠した、という話だ。"
    named = "バチカンが死海文書を隠した。そう語られている。証拠は無い。"
    assert C.ensure_intro(named, "バチカンが死海文書を隠した", "最初") == named


def test_a_chapter_links_back_to_the_big_question_before_its_hook():
    text = "証拠は無い。\nでは、聖書から消えた記述はあるのか。"
    got = C.ensure_bearing(text, "少なくとも、隠されていたから秘密がある、とは言えない")
    assert got.splitlines()[-2:] == ["少なくとも、隠されていたから秘密がある、とは言えない。",
                                     "では、聖書から消えた記述はあるのか。"]
    assert C.ensure_bearing(got, "少なくとも、隠されていたから秘密がある、とは言えない") == got


def test_basics_open_with_the_marker_the_video_uses_for_its_chapter_card():
    got = C.ensure_basics_intro("始まりは1947年。", "死海文書")
    assert got.startswith("まず、死海文書とは何なのか。")
    assert C.ensure_basics_intro(got, "死海文書") == got


def test_connectives_are_thinned_on_every_line_not_just_the_first():
    """章は1文1行。改行で始まる文に効いていなかった（逆接 1.40/分 のまま）。"""
    text = "\n".join(f"だが、事実{i}がある。" for i in range(5))
    out = C.thin_connectives(text)
    assert out.count("だが、") == 2 and out.splitlines()[4] == "事実4がある。"


def _named_blocks(texts):
    p = P.validate(good_plan(2))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b"], duration_sec=900)
    for b in blocks:
        b.text = texts.get(b.key, "文。")
    return blocks


def test_terms_are_defined_once_and_only_where_they_are_used():
    """「エッセネ派は古代ユダヤ教の一派である」が基本の章の最後に脈絡なく並び、
    「AIは人工知能のことだ」が章でもう一度出た（死海文書）。"""
    blocks = _named_blocks({
        "basics": "まず、死海文書とは何なのか。\n年代は放射性炭素年代測定で分かる。\n"
                  "放射性炭素年代測定とは、炭素の減り方で年代を測る方法だ。\nエッセネ派は古代ユダヤ教の一派である。",
        "chapter1": "AIは人工知能のことだ。\n放射性炭素年代測定とは、年代を測る方法だ。\n2025年に研究が出た。",
        "chapter2": "エッセネ派とは、財産を共有したユダヤ教の一派のことだ。\nエッセネ派の規則が一致する。",
    })
    C.tidy_terms(blocks)
    assert "放射性炭素年代測定とは、炭素の減り方" in blocks[1].text     # 使われている語の定義は残る
    assert "エッセネ派は古代ユダヤ教の一派である" not in blocks[1].text  # 基本の章で使われない語の定義は消える
    assert "人工知能" not in blocks[2].text and "年代を測る方法" not in blocks[2].text   # 日常語と再定義
    assert "財産を共有したユダヤ教の一派" in blocks[3].text           # 使う章で初めて定義するのは残る


def test_back_references_to_things_never_said_lose_the_prefix():
    blocks = _named_blocks({
        "basics": "まず、死海文書とは何なのか。\n写本の多くは断片で見つかった。",
        "chapter1": "先ほど見たように、写本の多くは断片で見つかった。\n先ほど見たように、教会を揺るがす記述は無かった。",
    })
    C.fix_back_references(blocks)
    lines = blocks[2].text.splitlines()
    assert lines[0].startswith("先ほど見たように") and lines[1] == "教会を揺るがす記述は無かった。"


def test_the_closing_does_not_repeat_its_answer():
    text = ("冒頭の問いに戻る。秘密はあるのか。\n秘密は見つかっていない。\nバチカン説は根拠がないと分かった。\n"
            "だが、秘密は見つかっていない。\n\n条件。")
    got = C.dedupe_answer(text, "秘密は見つかっていない。")
    assert got.count("秘密は見つかっていない。") == 1 and got.endswith("条件。")


def test_the_plant_follows_the_question_it_refers_to():
    opening = ("死海文書。\n\n本当にそうなのか。\n死海文書に秘密はあるのか。\n\n当チャンネルでは〜。\n\n"
               "それでは私と共に、死海文書へと迫っていこう。")
    got = C.ensure_plant(opening, "死海文書に秘密はあるのか")
    assert "死海文書に秘密はあるのか。\nこの問いの答えは、最後に出す。" in got


def test_english_words_left_in_the_narration_are_found():
    assert C.latin_words("2025年にMladen Popovićらが〔3〕AIで調べた。DNAも使った。") == ["Mladen Popović"]


def test_long_sentence_notes_go_only_to_the_two_wordiest_chapters():
    from script_engine.devices import Audit
    p = P.validate(good_plan(3))
    blocks = C.blocks_from_plan(p, subject="巨石遺跡", genre="古代の謎", claims=["a", "b", "c"], duration_sec=900)
    for b, t in zip(blocks, ["冒頭。", "基本。", "短い。", "とても長い文がここにずっと続いていく。", "これもかなり長めの文になっている。", "着地。"]):
        b.text = t
    a = Audit(minutes=15, per_min={}, chapters=[], plant=True, callback=True, opening_images=3,
              opening_defeat=True, subject_free_run=9, unlanded=[], padding=[])
    C.route(blocks, a, ["平均文長 28.0字 が 17.0〜26.0 の外"])
    assert [b.key for b in blocks if b.notes] == ["chapter2", "chapter3"]


def test_polite_endings_are_made_plain_except_the_cta():
    """冒頭と着地の本文に「〜です」「〜ています」が混ざった（死海文書）。"""
    assert C.plain_form("写本群です。多いです。分かっていません。進みました。135点でした。載せています。") == \
        "写本群だ。多い。分かっていない。進んだ。135点だった。載せている。"
    closing = "答えは無いです。\n\n考察です。\n\nご視聴ありがとうございます。コメントで教えてください。"
    got = C._plain_block("closing", closing)
    assert got.startswith("答えは無い。") and got.endswith("ご視聴ありがとうございます。コメントで教えてください。")


def test_the_closing_states_the_answer_right_after_the_question():
    text = "冒頭の問いに戻る。\n死海文書に秘密はあるのか。\n写本は全て公開された。\n\n条件。"
    got = C.ensure_answer(text, "秘密は見つかっていません。")
    assert got.splitlines()[:3] == ["冒頭の問いに戻る。", "死海文書に秘密はあるのか。", "秘密は見つかっていない。"]
    assert C.ensure_answer(got, "秘密は見つかっていない。") == got


def test_a_rewrite_that_flips_a_numbered_fact_is_caught():
    """「35%はマソラ本文と一致する」を直させたら「一致しない」になった（死海文書）。"""
    before = "死海文書の聖書本文の35%は、マソラ本文と一致する〔4〕。\n5%は七十人訳の系統だ。"
    after = "死海文書の35%は、マソラ本文と一致しない独自の系統である。\n5%は七十人訳の系統だ。"
    assert C.flipped_facts(before, after) == ["死海文書の35%は、マソラ本文と一致しない独自の系統である。"]
    assert C.flipped_facts(before, before) == []


def test_near_duplicates_inside_a_chapter_are_dropped():
    text = "5%は七十人訳聖書の系統だ。\n別の話がある。\n5%は、七十人訳聖書の系統である。"
    assert C.dedupe_within(text).splitlines() == ["5%は七十人訳聖書の系統だ。", "別の話がある。"]


def test_basics_do_not_give_away_a_later_chapter():
    text = "まず、死海文書とは何なのか。\n1947年に見つかった。\n死海文書を書いたのはクムラン教団である。"
    got = C.drop_spoilers(text, ["死海文書を書いたのはクムラン教団である"])
    assert "クムラン教団である" not in got and "1947年" in got


def test_a_reason_with_no_question_becomes_a_plain_statement():
    text = "結論から言う。\nDNAで動物種は分かった。\nしかし書いた人の集団までは特定できていないためである。"
    assert C.fix_dangling_reasons(text).splitlines()[-1] == "しかし書いた人の集団までは特定できていない。"
    asked = "なぜか。\n断片が多かったためである。"
    assert C.fix_dangling_reasons(asked) == asked


def test_stance_names_are_not_shown_to_the_writer():
    """「肯定の立場は、〜を挙げる」と本文に写した（死海文書）。"""
    p = P.validate(good_plan(1))
    brief = C._chapter_brief(1, p.chapters[0], 1, p)
    assert "[肯定]" not in brief and "（そうだと言える事実）" in brief
