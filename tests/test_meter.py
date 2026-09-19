"""API呼び出しの計数。

推測で費用を語って外したことがあるので、数えた事実が出ることを確かめる。
"""
import pathlib

import meter

ROOT = str(pathlib.Path(__file__).resolve().parent.parent)


def setup_function():
    meter.reset()


def test_tallies_calls_and_tokens_per_model():
    meter.record("chat", "gpt-4.1", tokens_in=9000, tokens_out=2000)
    meter.record("chat", "gpt-4.1", tokens_in=1000, tokens_out=500)
    meter.record("image", "gpt-image-1")
    rows = {(r["kind"], r["model"]): r for r in meter.tally()}
    assert rows[("chat", "gpt-4.1")] == {
        "kind": "chat", "model": "gpt-4.1", "calls": 2, "tokens": 12500}
    assert rows[("image", "gpt-image-1")]["calls"] == 1


def test_reads_usage_block_from_a_response():
    meter.note_usage("chat", "gpt-4.1-mini",
                     {"usage": {"prompt_tokens": 420, "completion_tokens": 90}})
    # gpt-image-1 は input_tokens / output_tokens で返す
    meter.note_usage("image", "gpt-image-1",
                     {"usage": {"input_tokens": 30, "output_tokens": 1500}})
    rows = {r["model"]: r for r in meter.tally()}
    assert rows["gpt-4.1-mini"]["tokens"] == 510
    assert rows["gpt-image-1"]["tokens"] == 1530


def test_missing_usage_still_counts_the_call():
    """usage を返さない応答でも、呼んだ回数は落とさない。"""
    meter.note_usage("image", "gpt-image-1", {"data": [{"url": "x"}]})
    meter.note_usage("image", "gpt-image-1", None)
    rows = {r["model"]: r for r in meter.tally()}
    assert rows["gpt-image-1"] == {
        "kind": "image", "model": "gpt-image-1", "calls": 2, "tokens": 0}


def test_report_names_the_models_and_refuses_to_guess_money():
    meter.record("chat", "gpt-4.1", tokens_in=100)
    meter.record("image", "gpt-image-1")
    text = meter.report()
    assert "gpt-4.1" in text and "gpt-image-1" in text
    assert "$" not in text and "ドル" not in text


def test_report_when_nothing_was_called():
    assert meter.report() == "APIの呼び出しは無し"


def test_children_add_into_the_same_tally(tmp_path, monkeypatch):
    """工程が別プロセスに分かれても、1回の制作は1つの表にまとまる。

    build_props.py は make.py から subprocess で起動する。プロセス内に
    貯めるだけだと、そこで数えた分が最後の集計に届かない。
    """
    import subprocess
    import sys

    sink = tmp_path / "run.jsonl"
    monkeypatch.setattr(meter.os, "environ", dict(meter.os.environ))
    meter.share(sink)

    parent_env = dict(meter.os.environ)
    subprocess.run(
        [sys.executable, "-c",
         "import meter; meter.note_usage('chat', 'gpt-4.1',"
         " {'usage': {'prompt_tokens': 700, 'completion_tokens': 30}})"],
        cwd=ROOT, env=parent_env, check=True)
    meter.record("image", "gpt-image-1")

    rows = {r["model"]: r for r in meter.tally()}
    assert rows["gpt-4.1"] == {"kind": "chat", "model": "gpt-4.1",
                               "calls": 1, "tokens": 730}
    assert rows["gpt-image-1"]["calls"] == 1


def test_a_half_written_line_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(meter.os, "environ", dict(meter.os.environ))
    sink = tmp_path / "run.jsonl"
    meter.share(sink)
    meter.record("chat", "gpt-4.1", tokens_in=100)
    with open(sink, "a", encoding="utf-8") as fh:
        fh.write('{"kind": "chat", "mod')  # 書き込みの途中を読んだ状態
    rows = {r["model"]: r for r in meter.tally()}
    assert rows["gpt-4.1"]["calls"] == 1


def test_image_usage_uses_the_image_token_spelling():
    """gpt-image-1 は input_tokens / output_tokens で返す。

    実測: 1536x1024 の出力トークンは low 400 / medium 1568 / high 6208。
    画質を渡さないと既定は high に倒れ、明細の大半をここが占める。
    """
    meter.note_usage("image", "gpt-image-1",
                     {"usage": {"input_tokens": 65, "output_tokens": 6208}})
    rows = {r["model"]: r for r in meter.tally()}
    assert rows["gpt-image-1"]["tokens"] == 6273
