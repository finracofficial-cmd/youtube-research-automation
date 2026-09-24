"""同じ資料で何本か書かせて、数の幅を見る。

「品質が安定しているか」は1本では答えられない。設計図モードで6本書いた
とき、語り手の判断は 0.00〜0.27/分、結論先出しは 2/5〜5/5、資料に無い
数字は 2〜7件と揺れた。設定を変えるたびに1本ずつしか回していなかった
ので、その揺れが設定のせいか偶然かも分からなかった。

  python -m script_engine bench out/prompt_x.txt --spec seeds/topics/x.yaml --runs 3

幅の基準は compare と同じ 20%（それ未満を安定とみなす）。0/1 の項目は
全本で一致していれば安定。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from .pipeline import Result, measures, run_planned

# 参考2本の実測に対する目標。幅だけでなく、狙いに入っているかも見る
TARGET = {
    "private": (0.03, 0.13), "reserve": (0.19, 0.53), "pivot": (0.0, 0.53),
    "open": (0.42, 0.79), "landing": (0.37, 0.49), "short": (0.65, 1.24),
    "avg_sentence_len": (17.0, 26.0), "chars_per_min": (320.0, 410.0),
    "unsourced_numbers": (0, 0), "padding_items": (0, 2),
}


def spread(vals: list[float]) -> tuple[float, float, float, float]:
    """平均・最小・最大・幅（平均に対する比）。"""
    mean = statistics.fmean(vals)
    lo, hi = min(vals), max(vals)
    rel = (hi - lo) / mean if mean else (0.0 if hi == lo else 1.0)
    return mean, lo, hi, rel


def table(rows: list[dict]) -> list[str]:
    keys = list(rows[0]) if rows else []
    out = [f"{'指標':<20}{'平均':>8}{'最小':>8}{'最大':>8}{'幅':>7}   目標"]
    unstable: list[str] = []
    for k in keys:
        vals = [float(r[k]) for r in rows]
        mean, lo, hi, rel = spread(vals)
        tgt = TARGET.get(k)
        in_target = "" if not tgt else ("○" if tgt[0] <= mean <= tgt[1] else "×")
        mark = ""
        if k not in ("calls", "tokens", "chars") and rel >= 0.20 and hi != lo:
            mark = " ← 不安定"
            unstable.append(k)
        tgt_s = f"{tgt[0]}〜{tgt[1]} {in_target}" if tgt else ""
        out.append(f"{k:<20}{mean:>8.2f}{lo:>8.2f}{hi:>8.2f}{rel*100:>6.0f}%   {tgt_s}{mark}")
    out.append("")
    out.append(f"不安定な指標: {len(unstable)} / {len(keys)}"
               + (f"  （{', '.join(unstable)}）" if unstable else ""))
    return out


def run(material_path: Path, spec_path: Path, *, runs: int, duration_sec: float, model: str,
        rounds: int, kind: str, plans: int, candidates: int, out: Path | None,
        cite: bool = True, chat_factory=None, log=print) -> list[dict]:
    material = material_path.read_text(encoding="utf-8")
    rows: list[dict] = []
    texts: list[str] = []
    for i in range(runs):
        log(f"=== {i + 1}/{runs}")
        r: Result = run_planned(material, spec_path, duration_sec=duration_sec, model=model,
                                rounds=rounds, kind=kind, plans=plans, candidates=candidates,
                                cite=cite, chat_factory=chat_factory, log=lambda *a, **k: None)
        m = measures(r)
        rows.append(m)
        texts.append(r.text)
        log("  " + "  ".join(f"{k}={v}" for k, v in m.items()
                             if k in ("chars", "private", "pivot", "verdict_first", "unsourced_numbers", "gate_passed")))
    for line in table(rows):
        log(line)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"spec": str(spec_path), "runs": runs, "plans": plans,
                                   "candidates": candidates, "cite": cite, "rounds": rounds, "model": model,
                                   "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        for i, t in enumerate(texts, 1):
            out.with_name(f"{out.stem}_run{i}.txt").write_text(t, encoding="utf-8")
        log(f"-> {out}")
    return rows
