"""明細の読み取り。

費用を推測で語って2度外した。ここでは、返ってきた数字をそのまま並べる
ことと、読めなかったときに読めなかったと言うことを縛る。
"""
import json
import urllib.error
import io

import pytest

import cost


def _payload(results):
    return {"data": [{"results": results}]}


def test_sums_line_items_and_orders_by_size(monkeypatch):
    monkeypatch.setattr(cost, "_get", lambda p, q: _payload([
        {"line_item": "gpt-4.1", "amount": {"value": 1.25}},
        {"line_item": "gpt-image-1", "amount": {"value": 9.0}},
        {"line_item": "gpt-4.1", "amount": {"value": 0.75}},
    ]))
    assert cost.costs(0) == [("gpt-image-1", 9.0), ("gpt-4.1", 2.0)]


def test_an_amount_with_no_line_item_is_still_shown(monkeypatch):
    """品目が付かない分を落とすと、合計が明細と合わなくなる。"""
    monkeypatch.setattr(cost, "_get", lambda p, q: _payload([
        {"amount": {"value": 3.5}}]))
    assert cost.costs(0) == [("(品目の記載なし)", 3.5)]


def test_images_and_completions_add_up_across_days(monkeypatch):
    monkeypatch.setattr(cost, "_get", lambda p, q: {"data": [
        {"results": [{"model": "gpt-image-1", "images": 20,
                      "num_model_requests": 20}]},
        {"results": [{"model": "gpt-image-1", "images": 6,
                      "num_model_requests": 6}]}]})
    assert cost.images(0) == [("gpt-image-1", 26, 26)]

    monkeypatch.setattr(cost, "_get", lambda p, q: _payload([
        {"model": "gpt-4.1", "input_tokens": 9000,
         "output_tokens": 4000, "num_model_requests": 3}]))
    assert cost.completions(0) == [("gpt-4.1", 9000, 4000, 3)]


def test_no_admin_key_says_so_instead_of_guessing(monkeypatch):
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    with pytest.raises(cost.Denied) as e:
        cost._get("costs", {})
    assert "OPENAI_ADMIN_KEY" in str(e.value)
    assert "admin-keys" in str(e.value)


def test_a_403_explains_which_key_is_needed(monkeypatch):
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "sk-admin-test")

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(
            "u", 403, "Forbidden", {},
            io.BytesIO(json.dumps({"error": "Missing scopes: api.usage.read"}).encode()))

    monkeypatch.setattr(cost.urllib.request, "urlopen", boom)
    with pytest.raises(cost.Denied) as e:
        cost._get("costs", {})
    assert "api.usage.read" in str(e.value) and "Admin key" in str(e.value)


def test_main_reports_failure_rather_than_printing_a_number(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    assert cost.main([]) == 1
    out = capsys.readouterr().out
    assert "読めなかった" in out and "$" not in out
