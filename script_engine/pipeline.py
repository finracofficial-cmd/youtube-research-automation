"""設計図モードの一本道。CLI と bench の両方から呼ぶ。

  資料 + 題材の仕様 → 設計図（複数作って選ぶ）→ 塊ごとに執筆（候補を作って選ぶ）
  → 監査 → 外れた塊だけ直す → 合格判定

戻り値の Result に、台本と一緒に「測った数」を全部持たせる。
安定しているかは1本では分からない。同じ資料で何本か書かせて、
数の幅を見る（bench.py）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

import meter

from . import plan as planmod
from .compose import compose
from .devices import Audit, speculation_numbers as devices_spec_numbers, unsourced_numbers
from .style import Metrics, validate


@dataclass
class Result:
    text: str
    plan: planmod.Plan
    audit: Audit
    style: Metrics
    left: list[str]                 # 直しきれなかった指摘
    loose: list[str]                # 資料に無い数字
    plans_tried: int
    calls: int
    tokens: int
    seconds: float
    gate: dict = field(default_factory=dict)   # 品質の合格条件ごとの真偽
    enough: bool = True                          # 指定の尺に資料が足りたか
    minutes: float = 0.0                         # この資料で書けた尺

    @property
    def passed(self) -> bool:
        return all(self.gate.values())


def _usage() -> tuple[int, int]:
    calls = tokens = 0
    for row in meter.tally():
        calls += int(row.get("calls") or 0)
        tokens += int(row.get("tokens_in") or 0) + int(row.get("tokens_out") or 0) \
            + int(row.get("tokens") or 0)
    return calls, tokens


def load_spec(spec_path: Path) -> tuple[str, str, list[str], list[float] | None]:
    """題材名・ジャンル・主張・章の重み（出典の数）。"""
    subject, genre, claims, weights, _ = load_spec_full(spec_path)
    return subject, genre, claims, weights


def load_spec_full(spec_path: Path) -> tuple[str, str, list[str], list[float] | None, dict]:
    """load_spec に加えて、謎・候補・主張の付帯情報（語り手・視聴者が気にする理由）。"""
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    subject = spec["subject"]
    genre = spec.get("genre", "未解決の謎")
    claims = [c["ja"] for c in spec.get("claims", [])]
    extra = {"mystery": str(spec.get("mystery") or "").strip(),
             "claims_meta": [c for c in spec.get("claims", []) if isinstance(c, dict)],
             "told": [str(x) for x in (spec.get("told") or [])]}
    weights = None
    src_path = spec_path.with_name(f"{spec_path.stem}_sources.json")
    if src_path.exists():
        srcs = json.loads(src_path.read_text(encoding="utf-8"))
        by_ja = {c.get("ja"): len(c.get("sources") or []) for c in (srcs.get("claims") or [])}
        weights = [float(by_ja.get(c, 0)) for c in claims]
    return subject, genre, claims, weights, extra


def pick_told(told: list[str], claims: list[str], *, k: int = 2, limit: int = 40) -> list[str]:
    """冒頭で見せる動画タイトルを k 本選ぶ。主張の順に、その主張にいちばん重なるもの。

    長すぎるもの（「〜テレビでは放送できない歴史の異常現象と本当の意味、DNAが〜」）は
    読み上げると何の話か分からなくなるので外す。重なりが薄ければ当てない。"""
    from .compose import _grams, spoken_title
    pool = [t for t in told if 8 <= len(spoken_title(t)) <= limit + 4]
    out: list[str] = []
    for c in claims:
        g = _grams(c)
        rest = [t for t in pool if t not in out]
        best = max(rest, key=lambda t: len(g & _grams(t)), default="")
        if best and len(g & _grams(best)) >= max(3, len(g) // 4):
            out.append(best)
        if len(out) >= k:
            break
    return out


def make_plan(material: str, *, subject: str, claims: list[str], duration_sec: float,
              kind: str, ask: Callable[[list[dict]], str], tries: int = 1,
              extra: dict | None = None) -> tuple[planmod.Plan, int]:
    """設計図を tries 本作って、いちばん資料に沿ったものを採る。

    1本だと当たり外れがそのまま台本に乗る（実測: 出どころが全章不明の回と
    半分埋まる回があった）。形の検査に落ちたものは1回だけ直させる。
    """
    extra = extra or {}
    prompt = planmod.prompt(material, subject=subject, claims=claims,
                            duration_sec=duration_sec, kind=kind,
                            mystery=extra.get("mystery", ""), claims_meta=extra.get("claims_meta"),
                            told=extra.get("told"))
    best, best_score, made = None, None, 0
    for _ in range(max(1, tries)):
        msgs = [{"role": "user", "content": prompt}]
        raw = ask(msgs)
        try:
            p = planmod.validate(planmod.parse(raw), n_claims=len(claims))
        except planmod.PlanError as exc:
            msgs += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"設計図に不備がある。直したJSONだけを出す。\n{exc}"}]
            p = planmod.validate(planmod.parse(ask(msgs)), n_claims=len(claims))
        made += 1
        planmod.strip_unsourced(p, material)
        s = planmod.score(p, material, subject=subject)
        if best is None or s > best_score:
            best, best_score = p, s
    return best, made


def invented_origins(text: str, audit: Audit, plan: planmod.Plan) -> list[str]:
    """設計図に出どころが無い章で、年代や媒体を付けて出どころを書いた文。

    「2014年ごろからYouTubeやネット記事で広まった」と書いた（死海文書、4文）。
    年は論文の発行年とたまたま一致して、数字の検査を抜けていた。"""
    from .compose import origin_invented
    from .devices import split_blocks
    blocks = split_blocks(text)
    out = []
    for k, ch in enumerate(audit.chapters):
        if k < len(plan.chapters) and ch.index < len(blocks):
            out += origin_invented("".join(blocks[ch.index]), plan.chapters[k])
    return out


def gate(text: str, audit: Audit, style: Metrics, loose: list[str]) -> dict:
    """品質の合格条件。ここを通らない台本は動画にしない。

    率の不足（ただしが少ない等）は指摘に留め、門にはしない。門にするのは
    「嘘をつく」「途中で離脱される」に直結するものだけ。尺（話速・文の密度）は
    資料の厚みで決まるので、品質とは分けて enough_material で見る。
    bench で3本とも門を落とした主因が話速だったが、それは資料が薄いという
    別の事実で、台本の出来ではない。
    """
    ch = audit.chapters
    long_ok = 17.0 <= style.avg_sentence_len <= 26.0
    return {
        "資料に無い数字が無い": not loose,
        "伏線と回収がある": audit.plant and audit.callback,
        "全章が引きで終わる": all(c.hooks_out for c in ch) if ch else False,
        "半数以上の章が結論を先に言う": (sum(c.verdict_first for c in ch) * 2 >= len(ch)) if ch else False,
        "水増しが無い": not any(len(c.padding) >= 3 or any(x.startswith("断片") for x in c.padding) for c in ch),
        "1文の長さが参考のレンジ内": long_ok,
        "常体で書けている": style.plain_form_ratio >= 0.8,
        "考察が事実と分かれている": audit.speculation and not audit.speculation_loose,
        "資料に無い出どころが無い": not getattr(audit, "origin_invented", []),
        # 初見の視聴者として読ませて、筋が追えたか（点7以上、意味不明・ずれ・未説明が残っていない）。
        # 読ませていない（テストや --no-read）ときは門にしない
        "初見で分かる": audit.reading.clear if getattr(audit, "reading", None) is not None else True,
    }


def enough_material(style: Metrics, duration_sec: float, chars_per_min: float = 360.0) -> tuple[bool, float]:
    """指定の尺に対して、書けた字数が足りているか。足りなければ資料が薄い。"""
    mins = style.n_chars / chars_per_min
    return mins >= duration_sec / 60 * 0.85, mins


def run_planned(material: str, spec_path: Path, *, duration_sec: float, model: str,
                rounds: int = 2, kind: str = "bundle", plans: int = 1, candidates: int = 1,
                cite: bool = True, read: bool = True, chat_factory=None, log=print) -> Result:
    """一本道。chat_factory(model, json_mode, temperature) -> chat。テストは偽物を渡す。"""
    from .write import chat_fn
    factory = chat_factory or chat_fn
    subject, genre, claims, weights, extra = load_spec_full(spec_path)
    c0, t0 = _usage()
    started = time.time()

    ask = factory(model, json_mode=True, temperature=0.5)
    plan, made = make_plan(material, subject=subject, claims=claims, duration_sec=duration_sec,
                           kind=kind, ask=ask, tries=plans, extra=extra)
    plan.told = pick_told(extra.get("told") or [], [c.claim for c in plan.chapters])
    log("設計図:")
    for line in planmod.describe(plan):
        log(f"  {line}")
    if weights is not None:
        log("章の重み（出典の数）: " + " / ".join(f"{int(w)}" for w in weights))

    text, audit, left = compose(plan, subject=subject, genre=genre, claims=claims,
                                duration_sec=duration_sec, chat=factory(model),
                                rounds=rounds, kind=kind, material=material,
                                weights=weights, candidates=candidates, cite=cite,
                                reader=factory(model, json_mode=True, temperature=0.2) if read else None)
    style = validate(text, duration_sec)
    loose = unsourced_numbers(text, material)
    audit.speculation_loose = devices_spec_numbers(text, material)
    audit.origin_invented = invented_origins(text, audit, plan)
    c1, t1 = _usage()
    r = Result(text=text, plan=plan, audit=audit, style=style, left=left, loose=loose,
               plans_tried=made, calls=c1 - c0, tokens=t1 - t0, seconds=time.time() - started)
    r.gate = gate(text, audit, style, loose)
    r.enough, r.minutes = enough_material(style, duration_sec)
    return r


def measures(r: Result) -> dict:
    """bench が並べる数。名前は devices / style の語に揃える。"""
    a, s = r.audit, r.style
    ch = a.chapters
    out = {
        "chars": s.n_chars,
        "chars_per_min": round(s.chars_per_min, 1),
        "avg_sentence_len": round(s.avg_sentence_len, 1),
        "numerics_per_min": round(s.numerics_per_min, 2),
        "fidelity": round(s.fidelity, 2),
        "open": round(a.per_min["open"], 2),
        "private": round(a.per_min["private"], 2),
        "reserve": round(a.per_min["reserve"], 2),
        "pivot": round(a.per_min["pivot"], 2),
        "landing": round(a.per_min["landing"], 2),
        "short": round(a.per_min["short"], 2),
        "plant_and_callback": int(a.plant and a.callback),
        "verdict_first": sum(c.verdict_first for c in ch),
        "hooks_out": sum(c.hooks_out for c in ch),
        "origin": sum(c.origin for c in ch),
        "padding_items": sum(len(c.padding) for c in ch),
        "unsourced_numbers": len(r.loose),
        "notes_left": len(r.left),
        "gate_passed": int(r.passed),
        "enough_material": int(r.enough),
        "speculation": int(bool(a.speculation)),
        "narrowing": a.narrowing,
        "invented_origins": len(getattr(a, "origin_invented", []) or []),
        "reader_score": getattr(getattr(a, "reading", None), "score", -1),
        "reader_problems": len(getattr(getattr(a, "reading", None), "problems", []) or []),
        "calls": r.calls,
        "tokens": r.tokens,
    }
    return out
