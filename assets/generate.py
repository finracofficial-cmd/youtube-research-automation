"""画像生成。写真が存在しない画だけに使う。

このチャンネルの堀は「一次資料に当たっていること」なので、
生成画像の扱いを間違えると差別化がそのまま消える。だから2つ縛りを置く:

  1. 生成は仕様で明示的に指定したカットだけ。
     検索が失敗したときの穴埋めには絶対に使わない。
     一次資料が見つからなかった穴を、捏造した画で埋めることになるため。
  2. 生成画像が1枚でも入ったら、概要欄に申告文が必ず出る。
     呼び出し側が忘れられない形にしてある（credits 側で強制）。

元チャンネルも概要欄で「一部の映像はAI生成。実写ではありません」と明記している。
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .sources import Asset

API_URL = "https://api.openai.com/v1/images/generations"
DEFAULT_MODEL = "gpt-image-1"

# 実在の資料に見える画を作らせない。ここを外すと「一次資料」の看板が嘘になる。
STYLE_GUARD = (
    "An original illustrative reconstruction, clearly stylized rather than photographic. "
    "Do not depict real documents, artifacts, manuscripts, artworks, logos, or identifiable people."
)


class GenerationUnavailable(RuntimeError):
    """キーが無い、またはAPIが応答しない。"""


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def generate(prompt: str, dst: Path, *, size: str = "1536x1024",
             model: str = DEFAULT_MODEL, timeout: int = 180) -> Asset:
    """1枚生成して保存し、生成物として印を付けた Asset を返す。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise GenerationUnavailable(
            "OPENAI_API_KEY が未設定。環境変数で渡すこと（会話やコードに書かない）")

    body = json.dumps({
        "model": model,
        "prompt": f"{prompt}\n\n{STYLE_GUARD}",
        "size": size,
        "n": 1,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as exc:
        raise GenerationUnavailable(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc

    item = payload["data"][0]
    if item.get("b64_json"):
        dst.write_bytes(base64.b64decode(item["b64_json"]))
    else:
        dst.write_bytes(urllib.request.urlopen(item["url"], timeout=timeout).read())

    return Asset(
        source="generated", title=prompt[:80], url="", page_url="",
        license="AI生成", author=model,
    )
