import pytest

from research.dossier import (Claim, discriminators, extract_numeric_facts,
                              on_topic)
from research.sources import Source, relevance_filter, _deinvert


def src(title, kind="paper", abstract="", year=2020):
    return Source(kind=kind, title=title, year=year, url="", identifier="x",
                  open_access=False, cited_by=0, abstract=abstract)


def test_relevance_filter_keeps_multiword_matches():
    """全語一致を求めると4語クエリがほぼ全滅する（実際に全滅した）。"""
    items = [src("On the corrosion resistance of the Delhi iron pillar"),
             src("High Court of Delhi - judgment 2007")]
    kept = relevance_filter(items, "Delhi iron pillar corrosion")
    assert len(kept) == 1
    assert "corrosion resistance" in kept[0].title


def test_relevance_filter_ignores_weak_words():
    """ancient / study のような語はどの題材にも出るので判定に使わない。"""
    kept = relevance_filter([src("Antikythera mechanism reconsidered")],
                            "ancient Antikythera mechanism study")
    assert len(kept) == 1


def test_numeric_facts_skip_bare_years_and_short_fragments():
    items = [src("t", abstract="Published in 1974. The device has 30 bronze gears "
                               "and a tooth count of 223 on the largest wheel.")]
    facts = extract_numeric_facts(items)
    assert len(facts) == 1
    assert "223" in facts[0]


def test_numeric_facts_are_tagged_with_their_source():
    items = [src("t", abstract="The pillar contains about 1 percent phosphorus by weight.")]
    assert "[x]" in extract_numeric_facts(items)[0]


@pytest.mark.parametrize("n_papers,expected", [(6, "厚い"), (2, "薄い"), (0, "文献なし")])
def test_evidence_level_tracks_literature_depth(n_papers, expected):
    c = Claim(ja="j", en="e", sources=[src(f"p{i}") for i in range(n_papers)])
    assert c.evidence_level.startswith(expected)


def test_claim_with_only_books_is_not_treated_as_well_supported():
    c = Claim(ja="j", en="e", sources=[src("b", kind="book") for _ in range(8)])
    assert "文献なし" in c.evidence_level


def test_deinvert_restores_word_order():
    assert _deinvert({"the": [0], "gear": [1], "turns": [2]}) == "the gear turns"


def test_deinvert_handles_missing_index():
    assert _deinvert(None) == ""


def test_claim_sources_come_before_background():
    """題材レベルの検索は通俗語だと無関係な論文を拾うので、後ろに回す。"""
    from research.dossier import Dossier
    d = Dossier(subject="オーパーツ", subject_en="out-of-place artifact",
                background=[src("Archaeology of Place")],
                claims=[Claim(ja="j", en="e", sources=[src("Antikythera mechanism")])])
    assert d.all_sources[0].title == "Antikythera mechanism"


def test_all_sources_dedupes_by_identifier():
    from research.dossier import Dossier
    dup = src("same paper")
    d = Dossier(subject="s", subject_en="s", background=[dup],
                claims=[Claim(ja="j", en="e", sources=[dup])])
    assert len(d.all_sources) == 1


def test_head_keyword_is_mandatory():
    """先頭の固有名詞を落とした一致は題材違い。実測でイランの論文を拾っていた。"""
    items = [src("The Re-evaluation of Kerman Neolithic Chronology"),
             src("Gobekli Tepe and the Neolithic chronology of Anatolia")]
    kept = relevance_filter(items, "Gobekli Tepe Neolithic chronology")
    assert len(kept) == 1
    assert kept[0].title.startswith("Gobekli")


def test_single_keyword_query_still_matches():
    assert len(relevance_filter([src("Stonehenge revisited")], "Stonehenge")) == 1


def test_long_query_is_not_over_constrained():
    """先頭語に加えて残りにも高い一致率を課すと長いクエリが全滅する。
    実測で Nazca の4主張すべてが0件になった回帰。"""
    items = [src("Nazca geoglyphs: new insights from aerial survey")]
    kept = relevance_filter(items, "Nazca geoglyph construction desert pavement")
    assert len(kept) == 1


def test_head_alone_is_not_enough_when_other_terms_exist():
    items = [src("Delhi metro expansion plan")]
    assert relevance_filter(items, "Delhi iron pillar corrosion") == []


def test_exclude_drops_homonym_fields():
    """Nazca は地上絵とナスカプレート（地質学）で衝突する。"""
    items = [src("Subduction of the Nazca plate beneath central Peru"),
             src("Nazca geoglyphs and their construction")]
    kept = relevance_filter(items, "Nazca geoglyph construction",
                            exclude=("plate", "subduction"))
    assert len(kept) == 1
    assert "geoglyph" in kept[0].title


def test_script_names_are_readable_not_hashes():
    """ハッシュ名だと、どの台本か中身を開くまで分からない。

    実測で「オーパーツ」の台本が tbfd74af4.txt になり、
    drafts/ を見ても題材が判別できなかった。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from research.spec_from_subject import slug

    assert slug({"subject_en": "Voynich manuscript radiocarbon dating"}) == \
        "voynich-manuscript"
    assert slug({"subject_en": "megalithic construction archaeology"}) == \
        "megalithic-construction"
    # 英語が無ければ落ちずに既定を返す
    assert slug({"subject": "謎の遺跡"}) == "topic"
    # ファイル名に使えない文字が混ざらない
    for spec in ({"subject_en": "Piri Reis map, 1513 Ottoman cartography"},
                 {"subject_en": "The Antikythera Mechanism (Greece)"}):
        name = slug(spec)
        assert name.replace("-", "").isalnum(), name


# ---- 主張への紐づけ ----

def test_discriminators_drop_the_words_every_claim_shares():
    """relevance_filter は題材の語で絞るので、同じ題材なら何でも通る。

    主張に紐づけるにはそれでは足りない。全主張に出てくる語は題材名なので引く。
    """
    claims = [("", "Voynich manuscript radiocarbon dating parchment"),
              ("", "Voynich manuscript Roger Bacon authorship"),
              ("", "Voynich manuscript botanical plants")]
    got = discriminators(claims)
    for keys in got:
        assert "voynich" not in keys and "manuscript" not in keys
    assert "radiocarbon" in got[0] and "bacon" in got[1] and "plants" in got[2]


def test_discriminators_drop_query_scaffolding():
    """"identification" や "real" はクエリの骨組みで、中身を指していない。

    実測で「手稿の植物は実在の植物か」という主張に、言語統計の論文3本が
    identification / real の一致だけで通った。見出しにその主張文を使う以上、
    これは概要欄が嘘をつくのと同じになる。
    """
    claims = [("", "Voynich manuscript botanical identification real plants"),
              ("", "Voynich manuscript linguistic language analysis")]
    keys = discriminators(claims)[0]
    assert "identification" not in keys and "real" not in keys
    assert "botanical" in keys and "plants" in keys


def test_on_topic_drops_papers_that_only_match_the_subject():
    got = on_topic(
        [src("Botanical identification in the Voynich manuscript"),
         src("Spectral analysis of the Voynich manuscript")],
        {"botanical", "plants"})
    assert [s.title for s in got] == [
        "Botanical identification in the Voynich manuscript"]


def test_on_topic_passes_everything_through_when_there_is_nothing_to_go_on():
    """主張が1本しかなければ固有の語が出ない。そのときは絞らない。"""
    items = [src("Anything at all")]
    assert on_topic(items, set()) == items



def test_previous_sources_are_kept_when_a_run_comes_back_thin(tmp_path):
    """学術APIは日によって429で痩せる。実測で17件→4件。前回のぶんを主張ごとに足す。"""
    import json
    from research.cli import merge_previous
    from research.dossier import Dossier

    prev = {"claims": [{"ja": "主張A。", "sources": [
                {"kind": "paper", "title": "Old Paper", "year": 1931, "identifier": "10.1/old", "authors": "Manly"},
                {"kind": "paper", "title": "Same Paper", "year": 2001, "identifier": "10.1/same"}]}],
            "background": [{"kind": "book", "title": "Old Book", "year": 1928, "identifier": "ark1"}]}
    path = tmp_path / "x_sources.json"
    path.write_text(json.dumps(prev), encoding="utf-8")
    d = Dossier(subject="s", subject_en="s")
    d.claims.append(Claim(ja="主張A。", en="a", sources=[src("Same Paper", year=2001)]))
    d.claims[0].sources[0].identifier = "10.1/same"
    added = merge_previous(d, path)
    assert added == 2
    titles = [s.title for s in d.claims[0].sources]
    assert titles == ["Same Paper", "Old Paper"]          # 今回のが先、前回のが後。重複は足さない
    assert d.claims[0].sources[1].authors == "Manly"
    assert [b.title for b in d.background] == ["Old Book"]



def test_authors_are_filled_from_crossref_for_doi_sources_without_one(monkeypatch):
    """引き継いだ出典は著者を持っていないことがある。DOI があれば1件ずつ引く。"""
    from research import cli as C
    from research.dossier import Dossier

    calls = []
    def fake_get(url, **kw):
        calls.append(url)
        return {"message": {"author": [{"given": "John", "family": "Manly"}, {"family": "Other"}]}}
    monkeypatch.setattr("research.http.get_json", fake_get)
    d = Dossier(subject="s", subject_en="s")
    a = src("With DOI"); a.identifier = "10.2307/2848508"
    b = src("Already"); b.identifier = "10.1/x"; b.authors = "Someone"
    c = src("No DOI"); c.identifier = "ark1"
    d.claims.append(Claim(ja="主張。", en="q", sources=[a, b, c]))
    assert C.enrich_authors(d) == 1
    assert a.authors == "John Manlyら" and b.authors == "Someone" and c.authors == ""
    assert calls == ["https://api.crossref.org/works/10.2307/2848508"]



def test_title_like_claims_are_caught():
    """主張は章の題や札にそのまま出る。動画タイトルの言い回しは通さない。"""
    from research.spec_from_subject import claim_problems
    assert claim_problems("バチカンが死海文書を隠したとされるキリストの秘密を徹底解説")
    assert claim_problems("AIが暴いた死海文書の真実！聖書に消えた記述はあったのか？")
    assert claim_problems("バチカンが死海文書を隠した") == []
    assert claim_problems("聖書から消えた記述が死海文書に残っている") == []


ARTICLE = """死海文書は、1947年以降に死海の北西の洞窟で見つかった写本群の総称。
主にヘブライ語聖書からなる。

== 歴史 ==

=== 最初の出版と委員会の「停滞」 ===
1950年に最初の公刊が行われた。
その後の作業は1960年代以降、遅々として進まなかった。

=== 「カトリック教会の陰謀」論の虚偽 ===
1991年に作家が本を出し、出版が進まないのはバチカンの陰謀だと主張した。
研究者はこれを根も葉もないと退けた。

== 意義 ==
聖書の最古の写本が一気に1,000年さかのぼった。
聖書テキストの一部は、現行の聖書と大きく違う。聖書の流動性が示された。

== 洞窟と発見された写本の一覧 ==
第1洞窟
第2洞窟

== 脚注 ==
[1] 何か
"""


def test_wiki_sections_drop_lists_and_notes():
    from research import wiki
    heads = [h for h, _ in wiki.split_sections(ARTICLE)]
    assert heads[0] == "冒頭"
    assert "「カトリック教会の陰謀」論の虚偽" in heads and "意義" in heads
    assert not any("一覧" in h or "脚注" in h for h in heads)


def test_wiki_passage_is_the_section_where_the_rumor_comes_from():
    """冒頭1,800字だけでは、死海文書の「バチカンが隠した」の元（1991年の本）が資料に無かった。"""
    from research import wiki
    secs = wiki.split_sections(ARTICLE)
    got = wiki.passage_for(secs, "バチカンが死海文書を隠した", drop=("死海文書",))
    assert got and got[0][0] == "「カトリック教会の陰謀」論の虚偽" and "1991年" in got[0][1]
    # 長い節ほど語が多く出るので、密度で選ぶ
    got = wiki.passage_for(secs, "死海文書の聖書テキストは現行と違う", drop=("死海文書",), used={"冒頭"})
    assert got[0][0] == "意義"
    # 主張の語の過半が出ない節は選ばない（「救世主の正体」に「正体」だけ当たる節）
    assert wiki.passage_for(secs, "死海文書に救世主の正体が書かれている", drop=("死海文書",)) == []


def test_wiki_english_terms_match_whole_words():
    """「AI」を部分一致で数えると certain や again に当たった。"""
    from research import wiki
    assert wiki._hits("AI", "certain again") == 0
    assert wiki._hits("AI", "an AI model dated the scroll") == 1
    assert wiki._hits("forgery", "many forgeries appeared") == 1


def test_wiki_english_sections_are_cut_into_sentences():
    from research import wiki
    body = "First sentence here. Second one follows. " * 40
    assert len(wiki._trim(body, 100)) <= 140


def test_wiki_basics_include_discovery_publication_and_significance():
    from research import wiki
    text = wiki.basics(wiki.split_sections(ARTICLE))
    assert "1947年" in text and "遅々として" in text and "1,000年" in text


def test_acronym_claims_only_pick_sections_that_mention_the_acronym():
    """英語版は AI を artificial intelligence と書く。「text」「new」のような広い語で
    関係の無い長い節が選ばれた（死海文書）。"""
    from research import wiki
    secs = [("Biblical significance", "The new text of the Bible. " * 20),
            ("Proposed older dates (2025)", "A new artificial intelligence model called Enoch dated the scrolls.")]
    got = wiki.passage_for(secs, "AI analysis new unrecovered text", drop=("Dead Sea Scrolls",))
    assert got[0][0] == "Proposed older dates (2025)"
