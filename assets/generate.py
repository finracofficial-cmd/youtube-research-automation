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

from meter import note_usage

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
    """鍵が手元にあるか、代理が付けてくれる設定になっているか。

    Claude Code の「API credentials」を使うと、鍵はこちらに渡らず、
    要求が出ていった後に代理が見出しを付ける。その場合は環境変数が空でも
    呼べるので、空を理由に止めない。
    """
    return bool(os.environ.get("OPENAI_API_KEY")
                or os.environ.get("OPENAI_VIA_PROXY"))


# 画質を渡していなかった。既定は auto で、gpt-image-1 はこれを high に倒す。
# 明細で "gpt-image-1 image, output" が $16.39 になっていた原因がこれ。
# 背景として動かす画で、拡大縮小しながら字幕と図表を重ねる。最高画質の
# 出力トークンを払う必要はない。
DEFAULT_QUALITY = "medium"


def generate(prompt: str, dst: Path, *, size: str = "1536x1024",
             model: str = DEFAULT_MODEL, quality: str = DEFAULT_QUALITY,
             timeout: int = 180) -> Asset:
    """1枚生成して保存し、生成物として印を付けた Asset を返す。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not os.environ.get("OPENAI_VIA_PROXY"):
        raise GenerationUnavailable(
            "OPENAI_API_KEY が未設定。環境変数で渡すか、Claude Code の "
            "API credentials に登録して OPENAI_VIA_PROXY=1 を立てること"
            "（会話やコードに書かない）")

    body = json.dumps({
        "model": model,
        "prompt": f"{prompt}\n\n{STYLE_GUARD}",
        "size": size,
        "quality": quality,
        "n": 1,
    }).encode()
    # 鍵が無いときは見出しを付けずに出す。代理が付ける設定のときの経路。
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(API_URL, data=body, headers=headers)
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        note_usage("image", model, payload)
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
