from script_engine.render import Topic, build_prompt
from script_engine.style import validate, analyze


def test_prompt_fills_fixed_line_placeholders():
    p = build_prompt(Topic("巨石遺跡", genre="古代の謎"))
    assert "こうした古代の謎を" in p
    assert "巨石遺跡へと迫っていこう" in p
    assert "{genre}" not in p and "{subject}" not in p


def test_bundle_uses_one_beat_per_claim():
    claims = ("主張A", "主張B", "主張C", "主張D")
    p = build_prompt(Topic("巨石遺跡", claims=claims), kind="bundle")
    for i in range(1, 5):
        assert f"### 第{i}主張" in p
    assert "### 第5主張" not in p


def test_per_beat_char_budget_is_emitted():
    """LLMに尺ではなく字数で渡さないと、長さが合わない。"""
    p = build_prompt(Topic("巨石遺跡"), duration_sec=1800)
    assert "秒 / 約" in p and "字）" in p


def test_sources_restrict_citations():
    p = build_prompt(Topic("巨石遺跡", sources=("Nature 552, 386 (2017)",)))
    assert "これ以外を出典として書かない" in p
    assert "Nature 552, 386 (2017)" in p


def test_prompt_bans_the_competitor_vocabulary():
    p = build_prompt(Topic("巨石遺跡"))
    assert "「ついに解読」「衝撃の真実」は使わない" in p


def test_char_budget_is_inflated_against_measured_shortfall():
    """初稿は実測で目標の約0.7倍にしかならないので、要求側を割り増しする。"""
    from script_engine.render import DRAFT_INFLATION
    assert DRAFT_INFLATION > 1.0
    p = build_prompt(Topic("巨石遺跡"), duration_sec=900)
    # 900秒 × 365字/分 = 5475字。割り増し後はそれより多いこと
    import re
    total = int(re.search(r"目安の総文字数: (\d+)字", p).group(1))
    assert total > 5475


def test_no_subtitle_is_shorter_than_one_frame():
    """1フレームに満たない字幕があると、描画そのものが落ちる。

    実測で「る。」が0.025秒になり、60秒尺の確認で
    "durationInFrames must be positive, but got 0" が出た。
    短すぎる字幕は読めもしないので、下限を置く。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
    import build_props

    script = Path("drafts/megaliths_v1.txt").read_text(encoding="utf-8")
    # 尺を短くするほど1本あたりが短くなり、下限に当たりやすい
    for duration in (60.0, 300.0, 900.0):
        props = build_props.build(script, duration, "bundle", 1,
                                  shot_sec=8.0, narration=None, bgm=None)
        for key, items in props.items():
            if not isinstance(items, list) or not items:
                continue
            if not isinstance(items[0], dict) or "durationSec" not in items[0]:
                continue
            for item in items:
                assert item["durationSec"] * 30 >= 1, (duration, key, item)


def test_adjacent_cuts_never_show_the_same_image():
    """切り替わったのに絵が変わらないと、見ていて飽きる。

    実測で129カット中66箇所（51%）が直前と同じ画で、最長4カット続いていた。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
    import build_props

    shots = [{"src": f"shots/{f}"} for f in
             ["a.jpg", "a.jpg", "a.jpg", "b.jpg", "b.jpg", "c.jpg"]]
    manifest = [{"file": "a.jpg", "segment": 0},
                {"file": "b.jpg", "segment": 5},
                {"file": "c.jpg", "segment": 9}]
    build_props._avoid_repeat(shots, manifest)
    srcs = [s["src"] for s in shots]
    assert all(a != b for a, b in zip(srcs, srcs[1:])), srcs


def test_avoid_repeat_does_nothing_with_a_single_image():
    """画が1枚しか無ければ、選び直す先が無い。落ちずにそのまま返す。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
    import build_props

    shots = [{"src": "shots/a.jpg"}, {"src": "shots/a.jpg"}]
    build_props._avoid_repeat(shots, [{"file": "a.jpg", "segment": 0}])
    assert [s["src"] for s in shots] == ["shots/a.jpg", "shots/a.jpg"]
