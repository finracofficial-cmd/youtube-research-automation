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
