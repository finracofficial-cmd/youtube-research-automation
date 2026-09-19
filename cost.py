"""OpenAIの明細を品目別に引く。

費用を推測で語って2度外した。原因は、こちらに計測が無く、画面の
読み取りを推測で埋めたこと。ここでは推測をしない。OpenAIが返した数字を
そのまま並べる。返ってこなければ、返ってこないと書く。

制作に使う鍵（sk-proj-…）では明細を読めない。api.usage.read は
Admin key にしか付かない。OPENAI_ADMIN_KEY に入れて渡すこと。
  https://platform.openai.com/settings/organization/admin-keys

  python3 cost.py                # 直近7日
  python3 cost.py --days 30
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://api.openai.com/v1/organization"
HINT = ("明細を読むには Admin key が要る（制作用の sk-proj-… では読めない）。\n"
        "  https://platform.openai.com/settings/organization/admin-keys で作り、\n"
        "  OPENAI_ADMIN_KEY に入れて渡すこと。")


class Denied(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    key = os.environ.get("OPENAI_ADMIN_KEY")
    if not key:
        raise Denied("OPENAI_ADMIN_KEY が未設定。\n" + HINT)
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{BASE}/{path}?{q}",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        if exc.code in (401, 403):
            raise Denied(f"HTTP {exc.code}: {body}\n\n" + HINT) from exc
        raise Denied(f"HTTP {exc.code}: {body}") from exc


def _rows(payload: dict) -> list[dict]:
    out = []
    for bucket in payload.get("data") or []:
        out += bucket.get("results") or []
    return out


def costs(since: int) -> list[tuple[str, float]]:
    """品目別の金額。$17.29 が何に消えたかはここで決まる。"""
    got: dict[str, float] = {}
    for r in _rows(_get("costs", {"start_time": since, "bucket_width": "1d",
                                  "group_by[]": "line_item", "limit": 180})):
        name = r.get("line_item") or "(品目の記載なし)"
        got[name] = got.get(name, 0.0) + float((r.get("amount") or {}).get("value") or 0)
    return sorted(got.items(), key=lambda kv: -kv[1])


def images(since: int) -> list[tuple[str, int, int]]:
    got: dict[str, list[int]] = {}
    for r in _rows(_get("usage/images", {"start_time": since, "bucket_width": "1d",
                                         "group_by[]": "model", "limit": 180})):
        m = r.get("model") or "(不明)"
        a = got.setdefault(m, [0, 0])
        a[0] += int(r.get("images") or 0)
        a[1] += int(r.get("num_model_requests") or 0)
    return [(m, v[0], v[1]) for m, v in sorted(got.items())]


def completions(since: int) -> list[tuple[str, int, int, int]]:
    got: dict[str, list[int]] = {}
    for r in _rows(_get("usage/completions", {"start_time": since, "bucket_width": "1d",
                                              "group_by[]": "model", "limit": 180})):
        m = r.get("model") or "(不明)"
        a = got.setdefault(m, [0, 0, 0])
        a[0] += int(r.get("input_tokens") or 0)
        a[1] += int(r.get("output_tokens") or 0)
        a[2] += int(r.get("num_model_requests") or 0)
    return [(m, v[0], v[1], v[2]) for m, v in sorted(got.items())]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OpenAIの明細を品目別に引く")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args(argv)
    since = int(time.time()) - a.days * 86400

    try:
        items = costs(since)
    except Denied as exc:
        print(f"明細を読めなかった:\n{exc}")
        return 1

    print(f"── 直近{a.days}日の費用（品目別）──")
    for name, amount in items:
        print(f"  {name:<40}${amount:>9.2f}")
    print(f"  {'合計':<38}  ${sum(v for _, v in items):>9.2f}")

    try:
        rows = images(since)
        print("\n── 画像生成 ──")
        print("  " + ("無し" if not rows else ""))
        for m, n, req in rows:
            print(f"  {m:<20}{n:>6}枚{req:>8}回")
        rows = completions(since)
        print("\n── 文章 ──")
        for m, i, o, req in rows:
            print(f"  {m:<20}{req:>6}回  入力{i:>10,}  出力{o:>10,}")
    except Denied as exc:
        print(f"\n内訳は読めなかった: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
