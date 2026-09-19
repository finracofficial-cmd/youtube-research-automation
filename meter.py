"""API呼び出しを数える。

推測で費用を語って外したことがある。1回の制作で何を何回呼んだのかを、
走らせた本人がその場で見られるようにする。単価は変わるので掛け算はしない。
数えた事実だけ出し、金額はOpenAIの明細で突き合わせてもらう。
"""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_calls: dict[tuple[str, str], int] = defaultdict(int)
_tokens: dict[tuple[str, str], int] = defaultdict(int)


def record(kind: str, model: str, *, tokens_in: int = 0, tokens_out: int = 0) -> None:
    """1回分を足す。kind は "chat" か "image"。"""
    key = (kind, model)
    with _lock:
        _calls[key] += 1
        _tokens[key] += tokens_in + tokens_out


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


def tally() -> list[dict]:
    with _lock:
        return [{"kind": k, "model": m, "calls": _calls[(k, m)],
                 "tokens": _tokens[(k, m)]}
                for (k, m) in sorted(_calls)]


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
