"""台本を読み上げ、字幕を実際の発話に合わせ直す。

字幕の時刻はこれまで文字数から割っていた。一定速度で読まれる前提だが、
実際は句点で間が空き、数字や固有名詞で速度が落ちる。音声を入れた時点で
ずれが見えるようになるので、合成と同時に文字単位の時刻をもらって
字幕を貼り直す。

ElevenLabs の with-timestamps を使うのはそのため。音声だけなら
通常の合成で足りるが、それだと字幕を合わせる手がかりが残らない。
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://api.elevenlabs.io/v1"
# 日本語を読ませるので多言語モデル。英語専用モデルは読みが崩れる。
DEFAULT_MODEL = "eleven_multilingual_v2"
# 1回に送る長さ。長すぎると落ちるので文の切れ目で割る。
CHUNK_CHARS = 1200


class TTSUnavailable(RuntimeError):
    """キーが無い、またはAPIが応答しない。"""


@dataclass
class Word:
    text: str
    startSec: float
    endSec: float


def available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def _key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise TTSUnavailable(
            "ELEVENLABS_API_KEY が未設定。環境変数で渡すこと（会話やコードに書かない）")
    return key


def voices() -> list[dict]:
    """使える声の一覧。voice_id を選ぶのに使う。"""
    req = urllib.request.Request(f"{API}/voices", headers={"xi-api-key": _key()})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return [{"voice_id": v["voice_id"], "name": v.get("name", ""),
             "labels": v.get("labels", {})} for v in d.get("voices", [])]


def split(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """文の切れ目で分ける。文の途中で切ると読みの抑揚が壊れる。"""
    sents = [s for s in re.split(r"(?<=[。？！\n])", text) if s.strip()]
    out, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur += s
    if cur:
        out.append(cur)
    return out


def _speak(chunk: str, voice_id: str, model: str, *, retries: int = 4) -> tuple[bytes, dict]:
    body = json.dumps({
        "text": chunk,
        "model_id": model,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75,
                           "style": 0.0, "use_speaker_boost": True},
    }).encode()
    url = f"{API}/text-to-speech/{voice_id}/with-timestamps"
    for a in range(retries):
        req = urllib.request.Request(
            url, data=body,
            headers={"xi-api-key": _key(), "Content-Type": "application/json"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=180).read())
            return base64.b64decode(d["audio_base64"]), d.get("alignment") or {}
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and a < retries - 1:
                time.sleep(2 ** a * 3)
                continue
            raise TTSUnavailable(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    raise TTSUnavailable("応答が得られなかった")


def synthesize(script: str, out_mp3: Path, voice_id: str, *,
               model: str = DEFAULT_MODEL, pause: float = 0.4) -> list[Word]:
    """台本を読み上げて1本のmp3にし、文字ごとの時刻を返す。

    分割して合成するので、2本目以降の時刻に先行ぶんの長さを足す。
    """
    chunks = split(script)
    parts, marks, offset = [], [], 0.0
    tmp = out_mp3.parent / "_tts"
    tmp.mkdir(parents=True, exist_ok=True)
    for i, chunk in enumerate(chunks):
        audio, align = _speak(chunk, voice_id, model)
        part = tmp / f"{i:03d}.mp3"
        part.write_bytes(audio)
        parts.append(part)

        chars = align.get("characters") or []
        starts = align.get("character_start_times_seconds") or []
        ends = align.get("character_end_times_seconds") or []
        for c, s, e in zip(chars, starts, ends):
            marks.append(Word(c, offset + s, offset + e))
        offset += (ends[-1] if ends else _duration(part))
        print(f"  {i + 1}/{len(chunks)}  {offset / 60:.1f}分", flush=True)
        time.sleep(pause)

    _concat(parts, out_mp3)
    for p in parts:
        p.unlink(missing_ok=True)
    tmp.rmdir()
    return marks


def _duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _concat(parts: list[Path], dst: Path) -> None:
    lst = dst.parent / "_concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", str(lst), "-c", "copy", str(dst)],
                   check=True)
    lst.unlink(missing_ok=True)


def retime(subtitles: list[dict], marks: list[Word]) -> list[dict]:
    """字幕を実際の発話に合わせ直す。

    字幕の文字列を台本の頭から順に探して、その範囲の文字時刻を使う。
    読み上げに含まれない記号があるので、照合は字を1つずつ進めて行う。
    """
    if not marks:
        return subtitles
    spoken = "".join(m.text for m in marks)
    out, at = [], 0
    for sub in subtitles:
        text = sub["text"]
        # 読み上げに出ない字（空白など）を飛ばしながら、先頭位置を探す
        want = re.sub(r"\s", "", text)
        if not want:
            out.append(sub)
            continue
        start = spoken.find(want[0], at)
        if start < 0:
            out.append(sub)
            continue
        i, j = start, 0
        while i < len(spoken) and j < len(want):
            if spoken[i] == want[j]:
                j += 1
            i += 1
        if j < len(want):  # 見つからなかった行はそのまま
            out.append(sub)
            continue
        out.append({**sub,
                    "startSec": round(marks[start].startSec, 3),
                    "durationSec": round(
                        max(0.4, marks[min(i, len(marks)) - 1].endSec
                            - marks[start].startSec), 3)})
        at = i
    return out
