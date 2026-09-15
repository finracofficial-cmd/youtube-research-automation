"""YouTube 検索結果の取得層。

watch ページは高頻度でボット判定されるが、検索エンドポイントは
`--flat-playlist` 経由なら安定して通る。取得できるのは
title / view_count / duration / channel / channel_id / description(抜粋) のみ。
再生日時と登録者数は取れないため、features 側でそれらに依存しない設計にしている。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

CACHE_DIR = Path(os.environ.get("TOPIC_SCOUT_CACHE", ".cache/search"))
PLAYER_CLIENT = "android_vr"  # データセンター IP からはこれ以外ブロックされやすい
EXTRACTOR_ARGS = f"youtube:player_client={PLAYER_CLIENT};lang=ja"
# lang=ja は必須。付けないと自動翻訳されたタイトルが返り、
# 「ゆっくり解説」が "A slow explanation" になって分類が丸ごと壊れる。


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    channel: str
    channel_id: str
    view_count: int
    duration: int  # 秒
    description: str
    verified: bool

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def _cache_path(query: str, limit: int) -> Path:
    key = hashlib.sha256(f"{query}\x00{limit}\x00{EXTRACTOR_ARGS}".encode()).hexdigest()[:20]
    return CACHE_DIR / f"{key}.json"


def _run_ytdlp(query: str, limit: int, timeout: int) -> list[dict]:
    cmd = [
        "yt-dlp", "--skip-download", "--no-warnings", "--flat-playlist",
        "--dump-json", "--extractor-args", EXTRACTOR_ARGS,
        f"ytsearch{limit}:{query}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            rows.append(json.loads(line))
    if not rows and proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {query!r}: {proc.stderr.strip()[-300:]}")
    return rows


def search(query: str, limit: int = 30, *, use_cache: bool = True,
           retries: int = 4, timeout: int = 300) -> list[Video]:
    """検索して Video のリストを返す。結果はディスクにキャッシュする。"""
    path = _cache_path(query, limit)
    if use_cache and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        last: Exception | None = None
        raw = None
        for attempt in range(retries):
            try:
                raw = _run_ytdlp(query, limit, timeout)
                break
            except Exception as exc:  # noqa: BLE001 - ネットワーク起因を一律リトライ
                last = exc
                time.sleep(2 ** attempt * 5)
        if raw is None:
            raise RuntimeError(f"search failed after {retries} attempts: {last}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    out = []
    for d in raw:
        if d.get("live_status") in {"is_live", "is_upcoming"}:
            continue
        vid, dur = d.get("id"), d.get("duration")
        if not vid or not dur:  # ショート/取得失敗は除外
            continue
        out.append(Video(
            video_id=vid,
            title=d.get("title") or "",
            channel=d.get("channel") or d.get("uploader") or "",
            channel_id=d.get("channel_id") or "",
            view_count=int(d.get("view_count") or 0),
            duration=int(dur),
            description=d.get("description") or "",
            verified=bool(d.get("channel_is_verified")),
        ))
    return out


def dump(videos: list[Video]) -> list[dict]:
    return [asdict(v) for v in videos]
