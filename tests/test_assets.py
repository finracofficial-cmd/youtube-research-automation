import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assets.credits import build as build_credits  # noqa: E402
from assets.credits import unlicensed  # noqa: E402
from assets.sources import Asset, _clean, license_ok, title_matches  # noqa: E402
from assets.cli import _sniff_ext  # noqa: E402


def asset(license="CC BY-SA 4.0", author="Someone", source="commons"):
    return Asset(source=source, title="t", url="u", page_url="p",
                 license=license, author=author)


def test_irrelevant_hit_is_rejected():
    """実測で "Baghdad battery" にバグダッドの米兵の写真が返ってきた回帰。"""
    assert not title_matches("Flickr - The U.S. Army - Night patrol in Baghdad.jpg",
                             "Baghdad battery")
    assert title_matches("Baghdad Battery replica.jpg", "Baghdad battery")


def test_head_keyword_is_mandatory():
    assert not title_matches("Delhi metro station.jpg", "Iron pillar Delhi")
    assert title_matches("Iron Pillar Delhi closeup.jpg", "Iron pillar Delhi")


def test_relaxed_match_requires_only_the_head():
    assert title_matches("Ottoman Empire scenery.jpg", "Ottoman portolan chart", min_ratio=0.0)
    assert not title_matches("Ottoman Empire scenery.jpg", "Ottoman portolan chart")


@pytest.mark.parametrize("name,ok", [
    ("Public domain", True), ("CC0", True), ("CC BY 4.0", True), ("CC BY-SA 3.0", True),
    ("CC BY-NC 4.0", False), ("CC BY-ND 4.0", False), ("Fair use", False), ("", False),
])
def test_only_reusable_licenses_pass(name, ok):
    assert license_ok(name) is ok


def test_duplicated_metadata_text_is_folded():
    """extmetadata は同じ語を二重に返すことがある。"""
    assert _clean("<a>Unknown author</a>Unknown author") == "Unknown author"
    assert _clean("<span>Jane Doe</span>") == "Jane Doe"


def test_attribution_is_required_only_for_cc_by():
    assert asset("CC BY-SA 4.0").needs_attribution
    assert asset("CC BY 4.0").needs_attribution
    assert not asset("Public domain").needs_attribution
    assert not asset("CC0").needs_attribution


def test_credits_name_cc_authors_and_group_the_rest():
    text = build_credits([asset("CC BY-SA 4.0", "Aiwok"), asset("Public domain", "-"),
                          asset("CC0", "-")])
    assert "Aiwok — CC BY-SA 4.0" in text
    assert "Wikimedia Commons（2点）" in text


def test_credits_can_declare_ai_generated_footage():
    text = build_credits([asset("CC0", "-")], ai_generated_note="0章の再現映像はAI生成")
    assert "AI生成" in text and "0章の再現映像はAI生成" in text


def test_unlicensed_assets_are_surfaced():
    assert len(unlicensed([asset(""), asset("CC0")])) == 1


@pytest.mark.parametrize("head,ext", [
    (b"\xff\xd8\xff\xe0", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"RIFF????WEBPVP8 ", ".webp"),
    (b"GIF89a....", ".gif"),
    (b"not an image at all", ""),
])
def test_extension_comes_from_the_bytes_not_the_url(head, ext):
    """Commons は .jpg という名前で PNG や WebP を返す。"""
    assert _sniff_ext(head) == ext


def test_dark_and_transparent_images_are_rejected(tmp_path):
    """透明PNGと暗すぎる写真は、読み込めても黒い画面になる。落とす。"""
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg が無い")
    from assets.cli import MIN_MEAN_LUMA, mean_luma

    dark = tmp_path / "dark.png"
    bright = tmp_path / "bright.png"
    for path, color in ((dark, "black"), (bright, "white")):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi",
                        "-i", f"color=c={color}:s=64x64:d=0.1", "-frames:v", "1",
                        "-y", str(path)], check=True)
    assert mean_luma(dark) < MIN_MEAN_LUMA
    assert mean_luma(bright) >= MIN_MEAN_LUMA


def test_generated_images_force_a_declaration_in_the_credits():
    """申告を呼び出し側の任意にすると書き忘れる。生成物があれば必ず出す。"""
    gen = Asset(source="generated", title="reconstruction", url="", page_url="",
                license="AI生成", author="gpt-image-1")
    text = build_credits([gen, asset("CC0", "-")])
    assert "AI生成" in text
    assert "実写・実物ではありません" in text


def test_generated_images_are_not_mixed_into_the_licensed_list():
    gen = Asset(source="generated", title="x", url="", page_url="",
                license="AI生成", author="gpt-image-1")
    text = build_credits([gen])
    assert "パブリックドメイン" not in text


def test_generation_requires_an_explicit_key():
    from assets.generate import GenerationUnavailable, generate
    import os
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(GenerationUnavailable):
            generate("test", Path("/tmp/x.png"))
    finally:
        if saved:
            os.environ["OPENAI_API_KEY"] = saved


def test_credits_list_each_source_once():
    """1枚の画は複数カットで使う。概要欄に同じ作者名が使用回数ぶん並ばない。"""
    a = Asset(source="commons", title="X.jpg", url="u", page_url="https://c/X",
              license="CC BY-SA 4.0", author="Alice")
    text = build_credits([a, a, a])
    assert text.count("Alice") == 1


def test_credits_keep_distinct_authors_sharing_a_license():
    a = Asset(source="commons", title="X.jpg", url="u", page_url="https://c/X",
              license="CC BY 4.0", author="Alice")
    b = Asset(source="commons", title="Y.jpg", url="u", page_url="https://c/Y",
              license="CC BY 4.0", author="Bob")
    text = build_credits([a, b, a, b])
    assert text.count("Alice") == 1 and text.count("Bob") == 1


def test_place_names_keep_their_one_character_suffix():
    """地名の接尾辞は1文字。ここで切ると別の記事に当たる。

    実測で「イースター島」が「イースター」（復活祭）に切れ、
    復活祭の記事の画が素材として採られた。
    """
    from assets.terms import candidates
    assert "イースター島" in candidates("イースター島のモアイを見る。")
    assert "ナスカ台地" in candidates("ナスカ台地に描かれている。")


def test_compound_proper_nouns_are_kept_whole():
    """「ピリ・レイスの地図」を「レイスの地図」としか拾えない状態だった。"""
    from assets.terms import candidates
    assert "ピリ・レイスの地図" in candidates("ピリ・レイスの地図が見つかった。")
    assert "アンティキティラ島の機械" in candidates("アンティキティラ島の機械の話。")
    assert "コソ加工物" in candidates("コソ加工物は失われた。")
