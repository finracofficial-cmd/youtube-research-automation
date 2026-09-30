"""書き始める前に、OpenAI の API が使えるかを確かめる。

Write approved #5（Issue #6、オーパーツ）は、残高切れで題材の仕様すら作れず台本が
1本も書けなかったのに、実行は「成功」で終わり、Issue にも何も返さなかった。見た側は
書けたと思って Make video を既定の台本のまま回し、70分かけて別の台本を描画した。
1トークンだけの問い合わせで、残高・鍵を先に確かめる。

  python -m script_engine.preflight      使えなければ理由を出して終了コード1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from .write import API, DEFAULT_MODEL

BILLING = "https://platform.openai.com/settings/organization/billing"


def openai_ready(model: str = DEFAULT_MODEL, *, timeout: int = 60, opener=urllib.request.urlopen) -> tuple[bool, str]:
    """(使えるか, 理由)。残高切れと鍵の不備だけを「使えない」とする。混雑（429の速度制限）や
    5xx は待てば通るので止めない。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not os.environ.get("OPENAI_VIA_PROXY"):
        return False, "OPENAI_API_KEY が設定されていない（リポジトリの Settings → Secrets に入れる）"
    body = json.dumps({"model": model, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "ok"}]}).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        opener(urllib.request.Request(API, data=body, headers=headers), timeout=timeout).read()
        return True, "OpenAI の API は使える"
    except urllib.error.HTTPError as exc:
        text = exc.read()[:400].decode("utf-8", "replace")
        if "insufficient_quota" in text or "no credits" in text.lower():
            return False, f"OpenAI の残高が無い。{BILLING} でクレジットを足してから再実行する"
        if exc.code == 401:
            return False, "OPENAI_API_KEY が無効（鍵を作り直して Secrets を差し替える）"
        return True, f"OpenAI が HTTP {exc.code} を返した（混雑とみなして続ける）"
    except Exception as exc:  # noqa: BLE001 - 通信の一時的な失敗では止めない
        return True, f"OpenAI に届かなかった（{str(exc)[:80]}）。続ける"


def main(argv=None) -> int:
    ok, why = openai_ready()
    print(why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
