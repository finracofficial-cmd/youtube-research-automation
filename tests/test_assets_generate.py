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
