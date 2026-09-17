"""同じ画が続く区間に、生成した背景を差し込む。

素材をWikipediaから集めると、題材に固有の画は取れるが枚数が足りない。
実測で65区間に対し33枚、同じ画が3〜4回ずつ出ていて、見ていて飽きる。

生成画像の使いどころを限る。このチャンネルの堀は「一次資料に当たること」
なので、資料そのものを生成したら看板が嘘になる。だから:

  1. 生成するのは、素材が足りず直前の画を引き継いでいる区間だけ。
     固有の資料が取れている区間には触らない。
  2. 作らせるのは情景であって、資料ではない。実在の文書・遺物・人物を
     描かせない（STYLE_GUARD）。
  3. 1枚でも入ったら概要欄に申告が出る（credits 側で強制）。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .generate import GenerationUnavailable, generate

CHAT_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_MODEL = "gpt-4.1-mini"

# 情景だけを作らせるための指示。資料を描かせない。
_SYSTEM = """You turn a line of Japanese documentary narration into a short
English prompt for a BACKGROUND image.

Rules:
- Describe a SETTING or ATMOSPHERE only: landscape, weather, light, terrain,
  materials, time of day, era mood.
- Never depict a specific real document, manuscript, artifact, artwork,
  inscription, map, logo, or identifiable person. No text or lettering.
- No people in focus. Distant silhouettes at most.
- You are given a LOOK to use. Follow it exactly: it fixes the light, the
  weather and the camera. Do not substitute your own; in particular do not
  default to mist or dawn unless the LOOK says so.
- Keep it under 40 words. Output the prompt only, nothing else."""

# 画の条件を区間ごとに配る。指示を付けずに任せると、どの区間でも同じ答えが
# 返る。実測で6枚中5枚が「Misty」、4枚が「at dawn」で始まり、
# 枚数を増やしても見た目が変わらなかった。
_LOOKS = (
    "high noon, hard sunlight, deep short shadows, clear sky, wide vista",
    "overcast afternoon, flat grey light, low horizon, distant weather",
    "golden hour, long raking shadows, warm low sun, side lighting",
    "blue hour after sunset, cool deep shadows, first stars, still air",
    "close macro on stone surface texture, shallow focus, raking light",
    "heavy rain, wet dark rock, puddles, low cloud, muted colour",
    "clear night, moonlight, cold blue tones, silhouetted horizon",
    "dry midday heat, dust haze, bleached tones, shimmering air",
    "low aerial vantage looking down, geometric ground pattern, midday",
    "winter, bare ground, frost, pale flat light, long empty distance",
    "dense fog at dawn, shapes dissolving, near-monochrome",
    "storm light, dark sky with one bright break, dramatic contrast",
)

_STYLE = ("Cinematic documentary background plate, muted earth tones, "
          "soft directional light, shallow depth of field, no text, "
          "no lettering, no watermark.")


def _chat(text: str, look: str = "", *, timeout: int = 60) -> str | None:
    """ナレーション1行と画の条件から、情景の指示文を起こす。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not os.environ.get("OPENAI_VIA_PROXY"):
        raise GenerationUnavailable(
            "OPENAI_API_KEY が未設定。環境変数で渡すか、Claude Code の "
            "API credentials に登録して OPENAI_VIA_PROXY=1 を立てること")
    body = json.dumps({
        "model": PROMPT_MODEL,
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user",
                      "content": f"LOOK: {look}\n\nNARRATION: {text[:600]}"}],
        "temperature": 0.9,
        "max_tokens": 120,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(CHAT_URL, data=body, headers=headers)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 500, 502, 503):
            return None
        raise GenerationUnavailable(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    except Exception:  # noqa: BLE001
        return None
    out = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return out.strip() or None


def segments_needing_art(manifest: list[dict]) -> list[int]:
    """生成で埋めたい区間。

    同じ画が2回以上出ている箇所を対象にする。引き継ぎだけを埋めても、
    1枚が3〜4回ずつ出る状態は変わらず、見ていて飽きるのは解消しない。

    各画の1回目は資料として残し、2回目以降を生成に置き換える。こうすると
    題材に固有の画は必ず1度は出たうえで、繰り返しだけが消える。
    """
    seen: set[str] = set()
    out = []
    for e in sorted(manifest, key=lambda x: x.get("segment", 0)):
        if e.get("generated"):
            continue
        f = e.get("file")
        if not f:
            continue
        if f in seen or e.get("carried"):
            out.append(e["segment"])
        else:
            seen.add(f)
    return out


def fill(manifest: list[dict], segments: list[str], out_dir: Path,
         *, limit: int = 60, pause: float = 1.0) -> list[dict]:
    """引き継ぎで埋めていた区間に、生成した情景を入れる。

    manifest を書き換えて返す。生成に失敗した区間は引き継ぎのまま残す。
    """
    want = segments_needing_art(manifest)[:limit]
    if not want:
        return manifest
    by_segment = {e["segment"]: e for e in manifest}
    made = 0
    for seg in want:
        text = segments[seg] if seg < len(segments) else ""
        if len(text) < 20:
            continue
        try:
            prompt = _chat(text, _LOOKS[made % len(_LOOKS)])
            if not prompt:
                continue
            dst = out_dir / f"gen{seg:03d}.png"
            asset = generate(f"{prompt}\n\n{_STYLE}", dst)
        except GenerationUnavailable as exc:
            print(f"  [{seg:03d}] 生成できず: {exc}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  [{seg:03d}] 生成に失敗: {exc}")
            continue
        rec = asset.to_dict()
        rec.update({"file": dst.name, "segment": seg, "query": "(生成)",
                    "needs_review": False, "carried": False, "generated": True,
                    "width": 1536, "height": 1024,
                    "n_segments": by_segment[seg].get("n_segments")})
        by_segment[seg] = rec
        made += 1
        print(f"  [{seg:03d}] 生成 {dst.name}  {prompt[:56]}")
        time.sleep(pause)
    print(f"\n{made}枚を生成で補った（繰り返していた {len(want)}区間のうち）")
    return [by_segment[k] for k in sorted(by_segment)]
