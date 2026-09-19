"""題材名から取材仕様（spec）を組む。

pipeline は spec を要る。spec には主張と、その英語の検索語が並ぶ。
手で書くと1本あたり10分かかり、月15本の運用では詰まる。

英語の検索語が要るのは、一次資料（論文・報告書）が英語で書かれているため。
日本語の題材名だけでは Crossref も OpenAlex も引けない。

  python3 -m research.spec_from_subject "ヴォイニッチ手稿" --claims 5 \
      --out seeds/topics/voynich.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from meter import note_usage

API = "https://api.openai.com/v1/chat/completions"

_SYSTEM = """You plan a Japanese documentary about a historical or
archaeological subject.

Return JSON only, shaped exactly like this:
{"subject_en": "...", "genre": "...",
 "claims": [{"ja": "...", "en": "..."}, ...]}

- subject_en: English search terms for finding primary literature.
- genre: a short Japanese label, e.g. 古代の謎 / 未解読文字 / 科学史.
- claims: the specific popular claims the video will examine, one per entry.
  - ja: the claim as it is popularly stated, in Japanese, one sentence.
  - en: English keywords that would find the scholarly work on that claim.
- Pick claims that primary sources can actually settle. Avoid claims that
  are purely speculative, because the script must cite real work."""


def build(subject: str, n_claims: int, *, model: str = "gpt-4.1",
          timeout: int = 180) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not os.environ.get("OPENAI_VIA_PROXY"):
        raise SystemExit("OPENAI_API_KEY が未設定。環境変数で渡すこと")
    body = json.dumps({
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user",
                      "content": f"題材: {subject}\n主張の数: {n_claims}"}],
        "temperature": 0.6,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(API, data=body, headers=headers)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        note_usage("chat", model, d)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    spec = json.loads(d["choices"][0]["message"]["content"])

    claims = [c for c in (spec.get("claims") or [])
              if c.get("ja") and c.get("en")][:n_claims]
    if not claims:
        raise SystemExit("主張が組めなかった。題材を具体的にして試す")
    return {"subject": subject,
            "subject_en": spec.get("subject_en") or subject,
            "genre": spec.get("genre") or "古代の謎",
            "claims": claims}


def slug(spec: dict) -> str:
    """ファイル名に使う短い名前。

    題材名は日本語なので、そのままではファイル名に使いにくい。かといって
    ハッシュにすると、どの台本か分からなくなる（実測で tbfd74af4 という
    名前になり、中身を開くまで題材が分からなかった）。英語の検索語から
    読める名前を作る。
    """
    src = (spec.get("subject_en") or spec.get("subject") or "topic")
    # 最初の意味のある語を2つ取る。長い題名をそのまま使うと扱いにくい
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", src)
             if w.lower() not in {"the", "and", "for", "with", "japanese",
                                  "ancient", "archaeological", "archaeology"}]
    name = "-".join(words[:2]) or "topic"
    return name[:40]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="題材名から取材仕様を組む")
    ap.add_argument("subject")
    ap.add_argument("--claims", type=int, default=5)
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--out", help="書き出し先。省略すると seeds/topics/<名前>.yaml")
    ap.add_argument("--print-slug", action="store_true",
                    help="ファイル名に使う名前だけを出す")
    a = ap.parse_args(argv)

    spec = build(a.subject, a.claims, model=a.model)
    name = slug(spec)
    if a.print_slug:
        print(name)
    out = Path(a.out or f"seeds/topics/{name}.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    print(f"主張 {len(spec['claims'])}件 / 名前 {name} -> {out}")
    for c in spec["claims"]:
        print(f"  {c['ja']}")
        print(f"    {c['en']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
