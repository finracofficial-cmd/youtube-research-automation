"""設計図に渡す資料の側。見た目と出どころの手がかり、著者名、章の畳み込み。"""
from script_engine import compose as C
from script_engine.tighten import split_long, tighten
from research import wiki


def test_chapters_are_folded_into_one_paragraph():
    """指示しても章が7段落で返ってくる（実測）。段落=章として監査するので畳む。"""
    raw = "通説だ。\nそう語られている。\n\n結論から言う。\n\n\nただし断りが要る。"
    assert C._fold("chapter1", raw) == "通説だ。\nそう語られている。\n結論から言う。\nただし断りが要る。"
    # 冒頭と着地は段落のまま
    assert C._fold("closing", "一般化。\n\n回収。") == "一般化。\n\n回収。"


def test_sentence_initial_daga_is_not_split():
    """「〜による。だが、しかし〜」を「だ。しかし」にしていた。文頭の「だが、」は接続詞。"""
    text = "理由は測定の結果が一致したことによる。だが、手稿の内容には別の時代の要素も指摘されてきたのである。"
    out = split_long(text)
    assert "だ。しかし" not in out
    # 述語のあとの「が、」は今まで通り切る
    assert "見なされていた。しかし" in tighten("当初は腐食した青銅の塊と見なされていたが、内部に歯車機構があると判明したのは70年後のことだった。")


def test_unknown_fields_are_left_out_of_the_brief():
    """「不明」と渡すと本文に「著者は不明」と書かれる（実測）。項目ごと落とす。"""
    assert C._known("不明", "1912", "") == "1912"
    assert C._known("不明", "不明") == ""


def test_wiki_lead_is_cleaned_into_sentences():
    raw = "ヴォイニッチ手稿（ヴォイニッチしゅこう、英: Voynich manuscript）は、[1] 1912年に発見された。 == 概要 == 全240ページ。"
    got = wiki.clean(raw)
    assert "（" not in got and "[1]" not in got and "==" not in got
    assert got.splitlines() == ["ヴォイニッチ手稿は、 1912年に発見された。", "全240ページ。"]


def test_wiki_section_says_what_it_is_for_and_not_for():
    s = wiki.section("ヴォイニッチ手稿", "240枚の羊皮紙。")
    assert "出典としては書かない" in s and "240枚の羊皮紙。" in s
    assert wiki.section("x", "") == ""


def test_first_author_is_kept_with_ra_for_several():
    from research.sources import first_author
    assert first_author(["G. Hodgins", "A. Other"]) == "G. Hodginsら"
    assert first_author(["Only One"]) == "Only One"
    assert first_author(["", None]) == ""


def test_openalex_and_crossref_carry_the_first_author(monkeypatch):
    from research import sources as S
    payloads = {
        "openalex": {"results": [{"title": "T", "publication_year": 2011, "doi": "https://doi.org/10.1/x",
                                  "authorships": [{"author": {"display_name": "Greg Hodgins"}},
                                                  {"author": {"display_name": "B"}}]}]},
        "crossref": {"message": {"items": [{"title": ["U"], "issued": {"date-parts": [[1931]]}, "DOI": "10.2/y",
                                            "author": [{"given": "John", "family": "Manly"}]}]}},
    }
    monkeypatch.setattr(S, "get_json", lambda url, **kw: payloads["openalex" if "openalex" in url else "crossref"])
    S._OPENALEX_DOWN = False
    assert S.openalex("q")[0].authors == "Greg Hodginsら"
    assert S.crossref("q")[0].authors == "John Manly"


def test_description_shows_the_author_when_known():
    import publish
    got = publish.sources_block({"claims": [{"ja": "主張。", "sources": [
        {"kind": "paper", "title": "Roger Bacon and the Voynich MS", "year": 1931,
         "venue": "Speculum", "authors": "John Manly"}]}]})
    assert "John Manly　Speculum　(1931)　論文" in got
