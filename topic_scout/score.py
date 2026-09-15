"""題材スコア。

分析で出た勝ち条件「需要が実証済み × 供給が低品質 × 時流ワード」を数式にする。

需要(D)と空白(G)は幾何平均で掛ける。どちらかがゼロなら題材として死ぬ、
という実測（橋本環奈回=需要ゼロ、ピラミッド回=空白ゼロ）を反映するため、
加算ではなく乗算にしている。

時流ワード(T)は増幅器として扱う。3本の実測ではTを外して失敗した例が無く、
「Tがゼロなら死ぬ」という証拠が無いため、下限を設けた係数にとどめている。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .features import TopicFeatures

T_FLOOR = 0.6  # 時流ワードが無くても、ここまでしか減点しない


def _log_scale(x: float, lo: float, hi: float) -> float:
    if x <= 0:
        return 0.0
    v = (math.log10(x) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    return max(0.0, min(1.0, v))


def _lin_scale(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


@dataclass
class TopicScore:
    query: str
    demand: float
    gap: float
    trend: float
    score: float
    verdict: str
    reasons: list[str]


def demand(f: TopicFeatures) -> float:
    """この題材はチャンネル抜きで人を引っ張れるか。

    1本だけ突出しているケースを需要と誤認しないよう、上位25%の再生数と
    「100k超えを出したチャンネルの数」を併用する。複数チャンネルが当てて
    いるほど、チャンネル力ではなく題材の引力である可能性が高い。
    """
    volume = _log_scale(f.views_p75, 3_000, 1_000_000)
    breadth = _lin_scale(f.distinct_channels_over_100k, 0, 6)
    return 0.6 * volume + 0.4 * breadth


def gap(f: TopicFeatures) -> float:
    """まともな長尺解説が空いているか。

    量産・煽り系の比率が高いほど空白が大きい。そこから、既存の真面目な長尺に
    よる飽和を差し引く。

    飽和は「本数」を主、「最高到達点」を従で見る。実測では、ヴォイニッチ手稿に
    62万再生の良質番組（ガリレオX）が既にあったが、それでも133万再生を取れた。
    1本の成功作は題材を占有しない。一方でピラミッドのように真面目な長尺が
    何本も並んでいる題材は埋まっている。この差を本数で捉える。
    """
    openness = _lin_scale(f.low_effort_ratio, 0.15, 0.75)
    saturation_count = _lin_scale(f.n_serious_longform, 1, 6)
    saturation_peak = _log_scale(f.best_serious_views, 300_000, 3_000_000)
    saturation = max(saturation_count, 0.5 * saturation_peak)
    return openness * (1.0 - saturation)


def trend(f: TopicFeatures) -> float:
    """時流ワード（現状はAI）が既に使われ、機能しているか。"""
    return T_FLOOR + (1.0 - T_FLOOR) * _lin_scale(f.ai_angle_ratio, 0.0, 0.30)


def score_topic(f: TopicFeatures) -> TopicScore:
    d, g, t = demand(f), gap(f), trend(f)
    s = math.sqrt(max(d, 0.0) * max(g, 0.0)) * t

    reasons = []
    if d < 0.25:
        reasons.append(f"需要が薄い（上位25%再生={f.views_p75:,.0f}／100k超えCh={f.distinct_channels_over_100k}）")
    if g < 0.25:
        if f.n_serious_longform >= 3 or f.best_serious_views >= 300_000:
            reasons.append(f"真面目な長尺が既に埋めている（{f.n_serious_longform}本・最高{f.best_serious_views:,}再生）")
        else:
            reasons.append(f"量産系の比率が低く差別化しにくい（低品質率={f.low_effort_ratio:.0%}）")
    if d >= 0.5 and g >= 0.5:
        reasons.append(f"需要あり×空白あり（低品質率={f.low_effort_ratio:.0%}／中央値{f.median_duration//60}分）")
    if f.ai_angle_ratio >= 0.2:
        reasons.append(f"AI切り口が既に使われている（{f.ai_angle_ratio:.0%}）")

    if s >= 0.45:
        verdict = "狙う"
    elif s >= 0.28:
        verdict = "条件付き"
    else:
        verdict = "見送り"
    return TopicScore(f.query, d, g, t, s, verdict, reasons)
