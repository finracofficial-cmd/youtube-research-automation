"""動画1本を「どういう供給か」に分類する。

「供給が低品質」という空白を測るのが目的なので、
量産系（ゆっくり・オカルト煽り・総集編）と真面目な長尺を切り分ける。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .fetch import Video

# 合成音声・量産フォーマット
YUKKURI = re.compile(
    r"ゆっくり|霊夢|魔理沙|ずんだもん|VOICEVOX|ボイスロイド|ボイロ|"
    r"CeVIO|A\.?I\.?VOICE|ゆっくり解説|ゆっくり雑学", re.I)

# オカルト・煽りフレーミング
OCCULT = re.compile(
    r"都市伝説|オカルト|衝撃|ヤバ|やばい|閲覧注意|禁断|封印|恐ろし|震撼|驚愕|"
    r"戦慄|ゾッと|怖い|不思議|ミステリー|超古代|宇宙人|エイリアン|陰謀|"
    r"...だった|判明した真実|隠された", re.I)

# 「未解決のはずの謎を解決した」と言い張るタイプ。
# 真面目な解説はこの言い方をしないので、量産系を切り分ける強い手掛かりになる。
CLAIMS_SOLVED = re.compile(
    r"ついに(解読|判明|解明|決着)|解読成功|解き明かし|暴いた|暴かれ|"
    r"衝撃の真実|驚愕の真実|判明した|正体|真相|明かされた|読めた|"
    r"解読！|解読!|全貌|禁断", re.I)

# 尺稼ぎ・回遊用（トピックそのものの競合ではない）
COMPILATION = re.compile(r"総集編|まとめ|睡眠用|作業用|聞き流し|傑作選|一挙|詰め合わせ", re.I)

# 一次資料に当たっている兆候
SCHOLARLY = re.compile(r"論文|一次資料|原典|査読|検証|文献|出典|Nature|Science|DOI", re.I)

# 時流フック
AI_ANGLE = re.compile(r"\bAI\b|人工知能|機械学習|ChatGPT|LLM|生成AI|AI解析|AI解読", re.I)

SERIOUS_MIN_DURATION = 25 * 60  # これ未満は「腰を据えた解説」とみなさない


@dataclass(frozen=True)
class Tagged:
    video: Video
    is_yukkuri: bool
    is_occult: bool
    is_compilation: bool
    is_scholarly: bool
    has_ai_angle: bool
    claims_solved: bool

    @property
    def is_low_effort(self) -> bool:
        """量産・煽り系。ここが多いほど空白が大きい。"""
        return (self.is_yukkuri or self.is_occult
                or self.is_compilation or self.claims_solved)

    @property
    def is_serious_longform(self) -> bool:
        """本チャンネルが作ろうとしているものの直接競合。"""
        return (
            self.video.duration >= SERIOUS_MIN_DURATION
            and not self.is_yukkuri
            and not self.is_compilation
            and not self.is_occult
            and not self.claims_solved
        )


def tag(video: Video) -> Tagged:
    haystack = f"{video.title}\n{video.channel}"
    return Tagged(
        video=video,
        is_yukkuri=bool(YUKKURI.search(haystack)),
        is_occult=bool(OCCULT.search(haystack)),
        is_compilation=bool(COMPILATION.search(video.title)),
        is_scholarly=bool(SCHOLARLY.search(f"{haystack}\n{video.description}")),
        has_ai_angle=bool(AI_ANGLE.search(haystack)),
        claims_solved=bool(CLAIMS_SOLVED.search(video.title)),
    )


def tag_all(videos: list[Video]) -> list[Tagged]:
    return [tag(v) for v in videos]
