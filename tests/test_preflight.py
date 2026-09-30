"""書き始める前の確認と、描画の前の確認。"""
import io
import urllib.error

from script_engine import guard
from script_engine.preflight import openai_ready


def _http(code, body):
    def opener(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(body))
    return opener


def test_an_empty_openai_balance_stops_before_writing(monkeypatch):
    """#5: 残高切れで1本も書けないのに、実行は成功で終わった。"""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    ok, why = openai_ready(opener=_http(429, b'{"error":{"type":"insufficient_quota","message":"You have no credits remaining."}}'))
    assert not ok and "残高が無い" in why and "billing" in why
    ok, why = openai_ready(opener=_http(401, b"{}"))
    assert not ok and "無効" in why
    # 混雑（速度制限）は待てば通るので止めない
    ok, _ = openai_ready(opener=_http(429, b'{"error":{"type":"requests","message":"Rate limit"}}'))
    assert ok


def test_a_missing_key_stops(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_VIA_PROXY", raising=False)
    ok, why = openai_ready(opener=lambda *a, **k: None)
    assert not ok and "OPENAI_API_KEY" in why


def test_an_empty_script_field_is_stopped_with_the_choices(capsys):
    """#10: script 欄が既定の drafts/oparts_approved.txt のまま回り、別の台本を70分描画した。"""
    assert guard.main([""]) == 1
    out = capsys.readouterr().out
    assert "script が空" in out
