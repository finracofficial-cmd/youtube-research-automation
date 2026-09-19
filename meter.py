"""API呼び出しを数える。

推測で費用を語って外したことがある。1回の制作で何を何回呼んだのかを、
走らせた本人がその場で見られるようにする。単価は変わるので掛け算はしない。
数えた事実だけ出し、金額はOpenAIの明細で突き合わせてもらう。

制作は工程ごとに別プロセスへ分かれる（build_props.py は make.py から
subprocess で起動する）。プロセス内に貯めるだけだと、そこで数えた分が
最後の集計に届かない。MAKE_METER に控えの置き場が指してあれば、そこへ
1行ずつ足す。子は環境変数を継ぐので、1回の制作が1つの表にまとまる。
"""
from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from pathlib import Path

_lock = threading.Lock()
_calls: dict[tuple[str, str], int] = defaultdict(int)
_tokens: dict[tuple[str, str], int] = defaultdict(int)


def _sink() -> Path | None:
    p = os.environ.get("MAKE_METER")
    return Path(p) if p else None


def share(path: Path | str) -> None:
    """この制作の控えの置き場を決める。子プロセスも同じ場所へ足す。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    os.environ["MAKE_METER"] = str(path)


def record(kind: str, model: str, *, tokens_in: int = 0, tokens_out: int = 0) -> None:
    """1回分を足す。kind は "chat" か "image"。"""
    row = {"kind": kind, "model": model, "tokens": tokens_in + tokens_out}
    sink = _sink()
    if sink is None:
        with _lock:
            _calls[(kind, model)] += 1
            _tokens[(kind, model)] += row["tokens"]
        return
    # 控えがあるときは控えだけに足す。両方に入れると二重に数える。
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _lock:
        with open(sink, "a", encoding="utf-8") as fh:  # O_APPEND、行は短い
            fh.write(line)


def note_usage(kind: str, model: str, payload: dict | None) -> None:
    """APIの応答に入っている usage をそのまま受けて足す。"""
    u = (payload or {}).get("usage") or {}
    record(kind, model,
           tokens_in=int(u.get("prompt_tokens") or u.get("input_tokens") or 0),
           tokens_out=int(u.get("completion_tokens") or u.get("output_tokens") or 0))


def reset() -> None:
    with _lock:
        _calls.clear()
        _tokens.clear()
    sink = _sink()
    if sink is not None and sink.exists():
        sink.write_text("", encoding="utf-8")


def tally() -> list[dict]:
    with _lock:
        calls = dict(_calls)
        tokens = dict(_tokens)
    sink = _sink()
    if sink is not None and sink.exists():
        for line in sink.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:  # 書き込みの途中で読んだ行は捨てる
                continue
            key = (row.get("kind", "?"), row.get("model", "?"))
            calls[key] = calls.get(key, 0) + 1
            tokens[key] = tokens.get(key, 0) + int(row.get("tokens") or 0)
    return [{"kind": k, "model": m, "calls": calls[(k, m)],
             "tokens": tokens[(k, m)]} for (k, m) in sorted(calls)]


def report() -> str:
    rows = tally()
    if not rows:
        return "APIの呼び出しは無し"
    # 和文は表示幅が2倍で桁が揃わないので、並べる欄はすべて英数字にする。
    out = ["", "── この実行で呼んだAPI ──",
           "  モデル            呼んだ回数      トークン"]
    for r in rows:
        tok = f"{r['tokens']:,}" if r["tokens"] else "-"
        out.append(f"  {r['model']:<16}{r['calls']:>7}{tok:>14}")
    out.append("  ※単価は変わるので金額は出さない。"
               "platform.openai.com/usage のモデル別内訳と突き合わせること")
    return "\n".join(out)
