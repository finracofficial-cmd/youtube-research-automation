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

_SYSTEM = """You plan a Japanese documentary that takes the stories people tell
about a historical or archaeological subject and checks them against
primary sources, one by one, until only what survives is left.

Return JSON only, shaped exactly like this:
{"subject_en": "...", "genre": "...",
 "mystery": {"ja": "...", "candidates": ["...", "...", "..."]},
 "claims": [{"ja": "...", "en": "...", "told_by": "...", "stakes": "..."}, ...]}

- subject_en: English search terms for finding primary literature.
- genre: a short Japanese label, e.g. 古代の謎 / 未解読文字 / 科学史.
- mystery: THE question the audience keeps asking about this subject, as a
  concrete yes/no or who/why question in Japanese (e.g. 「バチカンは死海文書を
  隠したのか」, not 「なぜ謎が残るのか」). candidates: 2-4 possible answers,
  short, mutually exclusive. The video eliminates them one by one.
- claims: the stories being told right now, most-told first. Use the video
  titles given (that is what the market says) before anything else.
  - ja: the claim AS IT IS POPULARLY STATED, with its sensational framing kept
    (「バチカンが死海文書を隠した」, not 「死海文書は非公開だった」). It must be
    ONE declarative Japanese sentence of at most 30 characters that ends in
    a verb or noun (〜した／〜である／〜がある／〜だ). It is NOT a video title:
    no 「徹底解説」「判明しました」「衝撃」「とは」, no ！ … ？ or brackets.
    Rewrite titles into the claim they make: 「AIが暴いた死海文書の真実！聖書に
    消えた記述はあったのか？」 → 「聖書から消えた記述が死海文書に残っている」.
  - en: English keywords that find the scholarly work that can settle it.
  - told_by: who tells it (YouTube解説 / 書籍 / 観光ガイド / ニュース / 教科書).
  - stakes: one short Japanese sentence on why a viewer cares.
- At least half of the claims must be 都市伝説・陰謀論・俗説 that primary
  sources can overturn or cut down to size. The rest are 定説 people repeat
  that have a twist when checked. Never list encyclopedia facts that nobody
  disputes (発見場所, 年代, 分類) as claims.
- Every claim must be settleable with real scholarly work; the script must
  cite it."""


def told_titles(subject: str, root: Path = Path(".")) -> list[str]:
    """量産chが語っている話（動画タイトル）。無ければ空。

    analysis/told_*.json（pick-topics が残す）を先に見て、無ければ
    out/channel_titles.json（同じ環境で discover を回した直後）を見る。
    """
    from topic_scout.told import latest, told, told_for

    path = latest(root / "analysis")
    if path:
        got = json.loads(path.read_text(encoding="utf-8")).get(subject) or []
        if got:
            return got
    cache = root / "out" / "channel_titles.json"
    if cache.exists():
        return told_for([subject], cache).get(subject) or []
    return []


# 動画タイトルをそのまま主張にした（「バチカンが…キリストの秘密を徹底解説」）。
# 主張は章の題や札にそのまま出るので、言い切りの一文でなければならない
_TITLE_LIKE = re.compile(r"[！!…？?【】\[\]「」]|徹底解説|判明しました|判明した|衝撃|とは$|新事実|真実$|解説$")


def claim_problems(ja: str) -> list[str]:
    out = []
    if _TITLE_LIKE.search(ja):
        out.append("動画タイトルの言い回しが残っている")
    if len(ja) > 34:
        out.append(f"長い（{len(ja)}字。30字まで）")
    if not re.search(r"(た|る|だ|である|がある|ない|いる|された|できる|できない)[。]?$", ja.rstrip("。")):
        out.append("言い切りの文で終わっていない")
    return out


def _chat_json(messages: list[dict], *, model: str, timeout: int) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not os.environ.get("OPENAI_VIA_PROXY"):
        raise SystemExit("OPENAI_API_KEY が未設定。環境変数で渡すこと")
    body = json.dumps({"model": model, "response_format": {"type": "json_object"},
                       "messages": messages, "temperature": 0.6}).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(API, data=body, headers=headers)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        note_usage("chat", model, d)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    return json.loads(d["choices"][0]["message"]["content"])


def build(subject: str, n_claims: int, *, model: str = "gpt-4.1",
          timeout: int = 180, told: list[str] | None = None) -> dict:
    told = told if told is not None else told_titles(subject)
    user = f"題材: {subject}\n主張の数: {n_claims}"
    if told:
        user += "\n\nいま語られている話（量産chの動画タイトル。多い順ではない）:\n" + "\n".join(f"- {t}" for t in told)
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
    spec = _chat_json(messages, model=model, timeout=timeout)
    # 主張がタイトルのままなら、1回だけ言い直させる
    bad = {c.get("ja"): claim_problems(c.get("ja") or "") for c in (spec.get("claims") or [])}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        messages += [{"role": "assistant", "content": json.dumps(spec, ensure_ascii=False)},
                     {"role": "user", "content":
                      "claims.ja が動画タイトルのままになっている。各主張を、その動画が主張している内容の"
                      "言い切りの一文（30字まで、記号なし）に書き直したJSON全体を出す。\n"
                      + "\n".join(f"- {k}: {', '.join(v)}" for k, v in bad.items())}]
        spec = _chat_json(messages, model=model, timeout=timeout)

    claims = [{"ja": c["ja"], "en": c["en"], "told_by": c.get("told_by", ""),
               "stakes": c.get("stakes", "")}
              for c in (spec.get("claims") or []) if c.get("ja") and c.get("en")][:n_claims]
    if not claims:
        raise SystemExit("主張が組めなかった。題材を具体的にして試す")
    mystery = spec.get("mystery") or {}
    cands = [str(x).strip() for x in (mystery.get("candidates") or []) if str(x).strip()][:4]
    return {"subject": subject,
            "subject_en": spec.get("subject_en") or subject,
            "genre": spec.get("genre") or "古代の謎",
            "mystery": str(mystery.get("ja") or "").strip(),
            "candidates": cands,
            "told": told[:12],
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
