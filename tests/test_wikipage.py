"""記事から画を引く経路の、通信しない部分の検査。

同名衝突（Archimedes が月のクレーターになる類）を止めるのが目的の module
なので、その判定に効く部分だけを固定する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assets.wikipage import _JUNK, _ABSTRACT_TYPE, _claim_ids  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video"))
import build_props  # noqa: E402


def test_junk_matches_wiki_furniture():
    """記事の体裁として貼られる画像を落とす。実際に混入したものを並べる。"""
    for name in ["Commons-logo.svg", "Semi-protection-shackle.svg",
                 "Cscr-featured.svg", "P vip.svg", "Question book-new.svg",
                 "Wiki letter w.svg", "Ambox current red.svg",
                 "Symbol list class.svg", "Flag of California.svg"]:
        assert _JUNK.search(name), name


def test_junk_keeps_real_subjects():
    """題材そのものの画は落とさない。"""
    for name in ["Domenico-Fetti Archimedes 1620.jpg",
                 "Antikythera Fragment A (Front).webp",
                 "Portrait of a Man, Said to be Christopher Columbus.jpg",
                 "Piri reis world map 01.jpg",
                 "Vishnu from Gita Govinda.jpg"]:
        assert not _JUNK.search(name), name


def test_claim_ids_skips_snaks_without_value():
    """somevalue/novalue の主張は datavalue を持たない。拾うと落ちる。"""
    claims = {"P31": [
        {"mainsnak": {"snaktype": "somevalue"}},
        {"mainsnak": {"snaktype": "value",
                      "datavalue": {"value": {"id": "Q5"}}}},
    ]}
    assert _claim_ids(claims, "P31") == ["Q5"]
    assert _claim_ids(claims, "P279") == []


def test_abstract_type_covers_units():
    """Percentage は P31 を持つので、型のラベル側で落とす必要がある。"""
    for label in ["parts-per notation", "dimensionless unit", "UCUM derived unit"]:
        assert any(w in label.lower() for w in _ABSTRACT_TYPE), label


def test_inset_only_for_tall_images():
    """左右の余白は縦横比で決める。横長の画に余白を入れる理由はない。"""
    assert build_props._inset({"width": 3000, "height": 2000}) == 0.0
    assert build_props._inset({"width": 1920, "height": 1080}) == 0.0
    assert build_props._inset({"width": 1364, "height": 1818}) > 0.2
    assert build_props._inset({"width": 800, "height": 800}) > 0.1
    # 寸法が無い／素材が無い場合に勝手に余白を作らない
    assert build_props._inset({"width": 0, "height": 0}) == 0.0
    assert build_props._inset(None) == 0.0


def test_inset_is_capped():
    """極端に縦長でも、画が消えるほど詰めない。"""
    assert build_props._inset({"width": 200, "height": 3000}) <= 0.35


def test_assets_follow_the_script_in_time():
    """素材は区間ごとに選んである。並び順ではなく時間で引き当てる。

    取得に失敗した区間があると manifest に穴が空く。穴を詰めて並べ直すと
    以降が全部ずれるので、区間番号で最も近いものを選ぶ。
    """
    manifest = [
        {"segment": 0, "file": "a.jpg", "n_segments": 10},
        {"segment": 5, "file": "f.jpg", "n_segments": 10},
        {"segment": 9, "file": "j.jpg", "n_segments": 10},
    ]
    assert build_props._for_time(0.0, manifest, 10)["file"] == "a.jpg"
    assert build_props._for_time(0.5, manifest, 10)["file"] == "f.jpg"
    assert build_props._for_time(1.0, manifest, 10)["file"] == "j.jpg"


def test_for_time_without_segment_info_falls_back_to_order():
    """区間番号を持たない古い manifest でも動く。"""
    manifest = [{"file": "a.jpg"}, {"file": "b.jpg"}]
    assert build_props._for_time(0.0, manifest, 0)["file"] == "a.jpg"
    assert build_props._for_time(0.99, manifest, 0)["file"] == "b.jpg"
    assert build_props._for_time(0.5, [], 0) is None


def test_credit_follows_the_image_on_screen():
    """出典表示は、そのとき画面に出ている画のものでなければならない。

    並び順で組むと、CC BY の画に別人の名前が付く。表示義務のある
    ライセンスでそれをやると、表示していないのと変わらない。
    """
    manifest = [
        {"file": "a.jpg", "author": "Alice", "license": "CC BY 4.0"},
        {"file": "b.jpg", "author": "Bob", "license": "CC BY-SA 3.0"},
    ]
    shots = [
        {"src": "shots/b.jpg", "startSec": 0.0, "durationSec": 5.0},
        {"src": "shots/a.jpg", "startSec": 5.0, "durationSec": 5.0},
    ]
    labels = build_props.source_labels(manifest, shots)
    assert labels[0]["text"].startswith("Bob")
    assert labels[1]["text"].startswith("Alice")


def test_credit_merges_while_the_image_holds():
    """同じ画が続く間は帯を1本にする。同じ文字を出し直さない。"""
    manifest = [{"file": "a.jpg", "author": "Alice", "license": "CC BY 4.0"}]
    shots = [{"src": "shots/a.jpg", "startSec": 0.0, "durationSec": 5.0},
             {"src": "shots/a.jpg", "startSec": 5.0, "durationSec": 5.0}]
    labels = build_props.source_labels(manifest, shots)
    assert len(labels) == 1 and labels[0]["durationSec"] == 10.0


def test_no_credit_invented_for_unknown_image():
    """manifest に無い画に、手近な作者名を付けてしまわない。"""
    manifest = [{"file": "a.jpg", "author": "Alice", "license": "CC BY 4.0"}]
    shots = [{"src": "shots/zz.jpg", "startSec": 0.0, "durationSec": 5.0}]
    assert build_props.source_labels(manifest, shots) == []


def test_junk_drops_dispute_and_navigation_icons():
    """記事の注意書きに貼られる図。題材の画ではない。

    実測で Baghdad Battery の記事から NPOV の天秤（Unbalanced scales.svg）が
    素材として通っていた。
    """
    for name in ["Unbalanced scales.svg", "Globe icon.svg",
                 "Split-arrows.svg", "Imbox scales.svg"]:
        assert _JUNK.search(name), name


def test_meta_needs_every_type_to_be_a_container():
    """型が1つでも器なら器、とすると取りこぼす。

    Stonehenge の P31 には併設の展示施設に由来する history museum が
    混ざっていて、cromlech / monument / archaeological site を
    押しのけて器と判定されていた。
    """
    from assets.wikipage import is_meta
    assert not is_meta(["cromlech", "monument", "archaeological site",
                        "history museum", "henge"])
    assert is_meta(["national museum"])
    assert is_meta(["scientific journal", "academic journal"])
    assert not is_meta([])


def test_media_files_are_not_used_as_images():
    """記事には読み上げ音声や動画も並ぶ。実測で Moai の記事から
    En-moai.oga（記事の読み上げ）が素材として通った。"""
    from assets.wikipage import _file_names
    import assets.wikipage as wp

    got = []
    for name in ["Moai.jpg", "En-moai.oga", "Clip.webm", "Scan.djvu", "Model.stl"]:
        if wp._JUNK.search(name):
            continue
        if name.lower().endswith((".ogg", ".oga", ".ogv", ".opus", ".flac", ".mp3",
                                  ".mp4", ".webm", ".mid", ".wav", ".pdf", ".djvu",
                                  ".stl", ".xcf")):
            continue
        got.append(name)
    assert got == ["Moai.jpg"]
