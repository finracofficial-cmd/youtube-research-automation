"""台本と尺から Remotion の props.json を組む。

字幕の割り付けは文字数按分。ナレーションは一定の速さで読まれる前提なので、
文の長さの比がそのまま表示時間の比になる。読み上げ音声が用意できたら、
--narration で渡して実測の尺に合わせる。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from script_engine.beats import get  # noqa: E402

MAX_SUB_CHARS = 26  # 1枚の字幕に載せる上限。これを超えると読めない


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。？！?!])", text) if s.strip()]


def wrap(sentence: str) -> list[str]:
    """長い文を字幕1枚ぶんに割る。読点を優先して切る。"""
    if len(sentence) <= MAX_SUB_CHARS:
        return [sentence]
    parts, cur = [], ""
    for chunk in re.split(r"(?<=、)", sentence):
        if len(cur) + len(chunk) > MAX_SUB_CHARS and cur:
            parts.append(cur)
            cur = chunk
        else:
            cur += chunk
    if cur:
        parts.append(cur)
    # 読点が無くて割れなかった場合は、やむを得ず機械的に割る
    out = []
    for p in parts:
        while len(p) > MAX_SUB_CHARS:
            out.append(p[:MAX_SUB_CHARS])
            p = p[MAX_SUB_CHARS:]
        if p:
            out.append(p)
    return out


def build(script: str, duration: float, kind: str, n_claims: int,
          shot_sec: float, narration: str | None, bgm: str | None) -> dict:
    lines = [w for s in split_sentences(script) for w in wrap(s)]
    total_chars = sum(len(l) for l in lines) or 1

    subtitles, t = [], 0.0
    for line in lines:
        dur = duration * len(line) / total_chars
        subtitles.append({"startSec": round(t, 3), "durationSec": round(dur, 3), "text": line})
        t += dur

    sheet = get(kind, n_claims=n_claims)
    chapters, at = [], 0.0
    for beat, sec in sheet.allocate(int(duration)):
        # 幕・主張の頭にだけカードを出す。導入や締めには出さない
        if beat.key.startswith(("act", "claim")):
            chapters.append({
                "startSec": round(at, 3), "durationSec": 3.0,
                "label": beat.name, "title": "",
            })
        at += sec

    # 画は等間隔の枠として置く。src は後で素材に差し替える前提
    shots = []
    n = max(1, int(duration // shot_sec))
    for i in range(n):
        start = i * duration / n
        zoom_in = i % 2 == 0
        shots.append({
            "startSec": round(start, 3),
            "durationSec": round(duration / n, 3),
            "src": f"shots/{i:03d}.jpg",
            "from": {"scale": 1.0 if zoom_in else 1.18, "x": 0, "y": 0},
            "to": {"scale": 1.18 if zoom_in else 1.0, "x": 0.2 if zoom_in else -0.2, "y": 0},
        })

    props: dict = {
        "bgmVolume": 0.12, "shots": shots, "telops": [],
        "subtitles": subtitles, "chapters": chapters,
    }
    if narration:
        props["narration"] = narration
    if bgm:
        props["bgm"] = bgm
    return props


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--duration", type=float, required=True, help="尺（秒）")
    ap.add_argument("--kind", choices=["flagship", "bundle"], default="bundle")
    ap.add_argument("--claims", type=int, default=5)
    ap.add_argument("--shot-sec", type=float, default=8.0, help="1カットの長さ")
    ap.add_argument("--narration", help="public/ からの相対パス")
    ap.add_argument("--bgm")
    ap.add_argument("--out", default="video/props.json")
    a = ap.parse_args()

    props = build(Path(a.script).read_text(encoding="utf-8"), a.duration,
                  a.kind, a.claims, a.shot_sec, a.narration, a.bgm)
    Path(a.out).write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"字幕 {len(props['subtitles'])}枚 / カット {len(props['shots'])} / 章 {len(props['chapters'])}")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
