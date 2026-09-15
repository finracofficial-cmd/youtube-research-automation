"""検索結果1トピック分から特徴量を作る。"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict

from .classify import Tagged

BIG_HIT = 100_000  # 「この題材は人を引っ張れる」とみなす再生数の線


@dataclass
class TopicFeatures:
    query: str
    n_videos: int
    views_p50: float
    views_p75: float
    views_max: int
    n_over_100k: int
    distinct_channels_over_100k: int
    low_effort_ratio: float
    median_duration: int
    n_serious_longform: int
    best_serious_views: int
    ai_angle_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(q * (len(s) - 1) + 0.5), len(s) - 1)
    return float(s[idx])


def build(query: str, tagged: list[Tagged], *,
          exclude_channel_ids: set[str] | None = None) -> TopicFeatures:
    """特徴量を組み立てる。

    exclude_channel_ids に自チャンネルを渡すと、自分の動画を競合から外す。
    既に出した動画を含めたまま採点すると「自分がいるから空白なし」と
    判定されてしまうため、バックテストでは必ず渡す。
    """
    excl = exclude_channel_ids or set()
    items = [t for t in tagged if t.video.channel_id not in excl]
    if not items:
        return TopicFeatures(query, 0, 0.0, 0.0, 0, 0, 0, 0.0, 0, 0, 0, 0.0)

    views = [t.video.view_count for t in items]
    durations = [t.video.duration for t in items]
    hits = [t for t in items if t.video.view_count >= BIG_HIT]
    serious = [t for t in items if t.is_serious_longform]

    return TopicFeatures(
        query=query,
        n_videos=len(items),
        views_p50=_pct(views, 0.50),
        views_p75=_pct(views, 0.75),
        views_max=max(views),
        n_over_100k=len(hits),
        distinct_channels_over_100k=len({t.video.channel_id for t in hits}),
        low_effort_ratio=sum(t.is_low_effort for t in items) / len(items),
        median_duration=int(statistics.median(durations)),
        n_serious_longform=len(serious),
        best_serious_views=max((t.video.view_count for t in serious), default=0),
        ai_angle_ratio=sum(t.has_ai_angle for t in items) / len(items),
    )
