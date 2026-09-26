"""読み上げのクレジットの事前確認と、合成した塊の控え。API は呼ばない。"""
import pytest

from assets import tts


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "CACHE", tmp_path / "tts")
    return tmp_path / "tts"


def test_a_run_stops_before_spending_when_credits_are_short(cache, monkeypatch):
    """#8: 残り226に対して最後の塊に326が要り、それまでの約4,400を払って落ちた。"""
    script = "死海文書。" * 400                       # 2,000字 → v3 で 2,000クレジット
    monkeypatch.setattr(tts, "remaining_credits", lambda: (226, "2026-10-17 13:05（日本時間）"))
    with pytest.raises(tts.TTSUnavailable) as e:
        tts.preflight(script, "voice", "eleven_v3")
    assert "要るのは 2,000" in str(e.value) and "残りは 226" in str(e.value) and "2026-10-17" in str(e.value)
    monkeypatch.setattr(tts, "remaining_credits", lambda: (5000, "x"))
    assert "2,000" in tts.preflight(script, "voice", "eleven_v3")
    assert tts.needed_credits(script, "voice", "eleven_flash_v2_5") == 1000   # 半額のモデル


def test_an_unknown_balance_does_not_block(cache, monkeypatch):
    monkeypatch.setattr(tts, "remaining_credits", lambda: None)
    assert "確かめられなかった" in tts.preflight("文。", "voice")


def test_synthesized_chunks_are_reused_and_not_paid_for_twice(cache, monkeypatch):
    calls = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

    import base64
    import json

    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        return Resp(json.dumps({"audio_base64": base64.b64encode(b"mp3").decode(),
                                "alignment": {"characters": ["文"]}}).encode())

    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    chunk = "文。"
    assert tts.needed_credits(chunk, "v", "eleven_v3") == 2
    assert tts._speak(chunk, "v", "eleven_v3") == (b"mp3", {"characters": ["文"]})
    assert tts._speak(chunk, "v", "eleven_v3") == (b"mp3", {"characters": ["文"]})
    assert len(calls) == 1                                   # 2回目は控えから
    assert tts.needed_credits(chunk, "v", "eleven_v3") == 0  # 控えにある塊は数えない
    assert tts._speak(chunk, "other-voice", "eleven_v3") and len(calls) == 2   # 声が違えば別
