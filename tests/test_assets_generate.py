"""生成画像の画質。

明細の "gpt-image-1 image, output" が $16.39 になっていた。画質を渡して
おらず、既定の auto が high に倒れていたため。実測の出力トークンは
low 400 / medium 1568 / high 6208 で、high は medium の3.96倍。
"""
import json

from assets import generate as g


def test_quality_is_sent_and_defaults_to_medium(monkeypatch, tmp_path):
    sent = {}

    class Resp:
        def read(self):
            return json.dumps({"data": [{"b64_json": ""}],
                               "usage": {"input_tokens": 65,
                                         "output_tokens": 1568}}).encode()

    def fake_urlopen(req, timeout=0):
        sent.update(json.loads(req.data))
        return Resp()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(g.urllib.request, "urlopen", fake_urlopen)
    try:
        g.generate("a field", tmp_path / "x.png")
    except Exception:  # 保存まで通す必要はない。送った中身だけ見る
        pass
    assert sent["quality"] == "medium"
    assert sent["size"] == "1536x1024"


def test_quality_can_be_raised_or_lowered(monkeypatch, tmp_path):
    sent = {}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_urlopen(req, timeout=0):
        sent.update(json.loads(req.data))
        raise RuntimeError("ここまでで十分")

    monkeypatch.setattr(g.urllib.request, "urlopen", fake_urlopen)
    for want in ("low", "high"):
        try:
            g.generate("a field", tmp_path / "x.png", quality=want)
        except Exception:
            pass
        assert sent["quality"] == want


# ---- 動画素材 ----

def test_video_containers_are_recognised_by_their_bytes():
    """拡張子ではなく中身で決める。Commons は名前と中身が食い違う。"""
    from assets.cli import _sniff_ext
    assert _sniff_ext(b"\x1aE\xdf\xa3" + b"\x00" * 20) == ".webm"
    assert _sniff_ext(b"OggS" + b"\x00" * 20) == ".ogv"
    assert _sniff_ext(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 8) == ".mp4"
    assert _sniff_ext(b"\xff\xd8\xff" + b"\x00" * 20) == ".jpg"
    assert _sniff_ext(b"not media") == ""


def test_the_contact_string_is_a_real_address():
    """Wikimedia は実在の連絡先を求める。

    research@example.com のような置き場所の文字列だと、APIは通っても
    実体の取得が403で弾かれる（実測で動画が落ちた）。
    """
    from assets.sources import UA
    assert "example.com" not in UA
    assert "github.com" in UA


def test_a_video_shot_is_marked_so_the_renderer_plays_it(tmp_path):
    """Img で動画を指すと黒い枠になる。種別を描画側へ渡す。"""
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "s.txt"
    script.write_text("石の話をする。\n\n石は重い。\n", encoding="utf-8")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps([
        {"file": "clip.webm", "segment": 0, "width": 1280, "height": 720,
         "license": "CC BY-SA 2.0", "author": "Someone", "source": "commons",
         "title": "clip.webm", "url": "", "page_url": ""},
    ]), encoding="utf-8")
    out = tmp_path / "p.json"
    subprocess.run([sys.executable, "video/build_props.py", str(script),
                    "--duration", "16", "--claims", "1",
                    "--manifest", str(man), "--out", str(out)],
                   cwd=root, check=True, capture_output=True)
    shots = json.loads(out.read_text(encoding="utf-8"))["shots"]
    assert shots and all(s["kind"] == "video" for s in shots)


# ---- イメージ映像 ----

def test_broll_is_marked_as_illustrative():
    """題材そのものではない映像。印が無いと、見た人は題材だと受け取る。"""
    from assets.sources import Asset
    a = Asset(source="commons", title="x.webm", url="", page_url="",
              license="CC BY 3.0", author="Someone", kind="video")
    assert a.illustrative is False
    a.illustrative = True
    assert a.to_dict()["illustrative"] is True


def test_the_screen_says_it_is_illustrative(tmp_path):
    """テレビが同じ理由で同じ断りを入れている。"""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "video"))
    from build_props import source_labels

    man = [{"file": "broll007.webm", "author": "Someone", "license": "CC BY 3.0",
            "illustrative": True},
           {"file": "003.jpg", "author": "Other", "license": "CC BY 2.0"}]
    shots = [{"src": "s/broll007.webm", "startSec": 0.0, "durationSec": 8.0},
             {"src": "s/003.jpg", "startSec": 8.0, "durationSec": 8.0}]
    got = source_labels(man, shots)
    # 「出典 イメージ映像 …」と1本の文字列にすると「出典＝イメージ映像」と
    # 読めて断りにならない。別の札として持たせる。
    assert got[0]["illustrative"] is True
    assert got[0]["text"] == "Someone / CC BY 3.0"
    # 題材そのものの画には付けない
    assert got[1]["illustrative"] is False


def test_broll_terms_do_not_repeat_immediately():
    """同じ映像が続くと、直そうとしていた「飽き」がそのまま残る。"""
    from assets.imagegen import BROLL_TERMS
    assert len(BROLL_TERMS) >= 8
    assert len(set(BROLL_TERMS)) == len(BROLL_TERMS)


def _repeating_manifest(n):
    """区間0だけ固有の画で、残りは全部その繰り返し（＝生成の対象が n-1 区間）。"""
    return [{"segment": i, "file": "a.jpg", "n_segments": n} for i in range(n)]


def test_generation_stops_at_the_cap_and_spreads_over_the_whole_video(monkeypatch, tmp_path):
    """上限が無いと繰り返す区間の数だけ（最大60枚）作り、1枚ごとに課金される。
    頭から上限まで作ると後半だけ繰り返しが残るので、全体に散らす。"""
    from assets import imagegen as ig
    from assets.sources import Asset
    calls = []
    monkeypatch.setattr(ig, "_chat", lambda text, look="": "a quiet desert at noon")

    def fake_generate(prompt, dst, quality="medium"):
        calls.append(dst.name)
        return Asset(source="generated", title=prompt[:80], url="", page_url="",
                     license="AI生成", author="gpt-image-1")
    monkeypatch.setattr(ig, "generate", fake_generate)
    texts = ["これは区間のナレーションで、二十字を超える長さがある。"] * 41
    out = ig.fill(_repeating_manifest(41), texts, tmp_path, limit=5, pause=0)
    made = sorted(e["segment"] for e in out if e.get("generated"))
    assert len(calls) == 5 and made == [1, 11, 21, 30, 40]
    assert ig.fill(_repeating_manifest(5), texts, tmp_path, limit=0, pause=0) == _repeating_manifest(5)


def test_a_segment_that_cannot_be_drawn_is_replaced_by_another(monkeypatch, tmp_path):
    from assets import imagegen as ig
    from assets.sources import Asset
    monkeypatch.setattr(ig, "_chat", lambda text, look="": "storm over hills")
    monkeypatch.setattr(ig, "generate", lambda prompt, dst, quality="medium": Asset(
        source="generated", title="x", url="", page_url="", license="AI生成", author="m"))
    texts = ["短い"] + ["これは区間のナレーションで、二十字を超える長さがある。"] * 9
    texts[1] = "短い"                                      # 散らした最初の区間は短くて作れない
    out = ig.fill(_repeating_manifest(10), texts, tmp_path, limit=3, pause=0)
    assert sum(bool(e.get("generated")) for e in out) == 3


def test_running_out_of_credit_stops_generation_instead_of_skipping_silently(monkeypatch, tmp_path):
    """残高切れも 429 で返る。混雑と同じに扱うと区間ごとに黙って飛ばし、生成0枚で進む（dead-sea-9）。"""
    import io
    import urllib.error
    from assets import imagegen as ig
    from assets.generate import GenerationUnavailable
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def no_credit(req, timeout=60):
        raise urllib.error.HTTPError(ig.CHAT_URL, 429, "Too Many Requests", {},
                                     io.BytesIO(b'{"error": {"code": "insufficient_quota"}}'))
    monkeypatch.setattr(ig.urllib.request, "urlopen", no_credit)
    import pytest
    with pytest.raises(GenerationUnavailable, match="残高"):
        ig._chat("ナレーション", "noon")

    def busy(req, timeout=60):
        raise urllib.error.HTTPError(ig.CHAT_URL, 429, "Too Many Requests", {},
                                     io.BytesIO(b'{"error": {"code": "rate_limit_exceeded"}}'))
    monkeypatch.setattr(ig.urllib.request, "urlopen", busy)
    assert ig._chat("ナレーション", "noon") is None          # 混雑はその区間だけ飛ばす
