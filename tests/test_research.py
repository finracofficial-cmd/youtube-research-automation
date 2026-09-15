import pytest

from research.dossier import Claim, extract_numeric_facts
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
