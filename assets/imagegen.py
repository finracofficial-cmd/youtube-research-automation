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
- Keep it under 40 words. Output the prompt only, nothing else."""

_STYLE = ("Cinematic documentary background plate, muted earth tones, "
          "soft directional light, shallow depth of field, no text, "
          "no lettering, no watermark.")


def _chat(text: str, *, timeout: int = 60) -> str | None:
    """ナレーション1行から、情景の指示文を起こす。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise GenerationUnavailable(
            "OPENAI_API_KEY が未設定。環境変数で渡すこと（会話やコードに書かない）")
    body = json.dumps({
        "model": PROMPT_MODEL,
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": text[:600]}],
        "temperature": 0.7,
        "max_tokens": 120,
    }).encode()
    req = urllib.request.Request(
        CHAT_URL, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
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
    """生成で埋めたい区間。直前の画を引き継いでいるところ。"""
    return [e["segment"] for e in manifest if e.get("carried")]


def fill(manifest: list[dict], segments: list[str], out_dir: Path,
         *, limit: int = 30, pause: float = 1.0) -> list[dict]:
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
            prompt = _chat(text)
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
    print(f"\n{made}枚を生成で補った（引き継ぎだった {len(want)}区間のうち）")
    return [by_segment[k] for k in sorted(by_segment)]
