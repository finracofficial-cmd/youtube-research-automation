from topic_scout.framings import generate


def test_generates_bundle_level_queries_not_bare_items():
    qs = generate()
    assert "オーパーツ" in qs and "オーパーツ 謎" in qs
    # アイテム単体は生成しない（実測で需要ゼロだったため）
    assert "デンデラの電球" not in qs


def test_region_cross_expands_the_pool():
    with_cross = generate(cross_region=True)
    without = generate(cross_region=False)
    assert len(with_cross) > len(without)
    assert "マヤ文明 オーパーツ" in with_cross
    assert "マヤ文明 オーパーツ" not in without


def test_no_duplicates():
    qs = generate()
    assert len(qs) == len(set(qs))


def test_custom_axes_are_respected():
    qs = generate(subjects=["古代文明"], angles=["謎"], regions=[], cross_region=False)
    assert qs == ["古代文明", "古代文明 謎"]
