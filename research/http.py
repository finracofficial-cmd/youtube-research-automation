"""各APIに共通の取得層。

このセッションのIPはプロキシ経由で頻繁に429を返す。上流の制限とは別物なので、
指数バックオフで粘る。返ってきたJSONはディスクにキャッシュして、
同じ問い合わせを二度投げない。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_DIR = Path(os.environ.get("RESEARCH_CACHE", ".cache/research"))
# API側の作法。連絡先を入れると polite pool に回してもらえる。
CONTACT = os.environ.get("RESEARCH_CONTACT", "research@example.com")
UA = f"youtube-research-automation/0.1 (mailto:{CONTACT})"


def get_json(url: str, *, retries: int = 5, timeout: int = 60,
             use_cache: bool = True) -> dict | None:
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    path = CACHE_DIR / f"{key}.json"
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            raw = urllib.request.urlopen(req, timeout=timeout).read()
            data = json.loads(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * 3)
                continue
            return None  # 404 などは粘っても無駄
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt * 2)
    print(f"  ! giving up on {url[:70]}: {last}")
    return None


def q(params: dict) -> str:
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
