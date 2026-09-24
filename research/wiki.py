"""題材の記述を Wikipedia 日本語版の冒頭から取る。出典には使わない。

設計図を書かせると、冒頭の「画で見せられる具体」と、各章の「誰が最初に
言い出したか」が、5章中4章で「不明」になった（ヴォイニッチ、2026-09-24）。
資料が論文の題名と年だけで、その物がどう見えるか・説がどこから出たかを
持っていなかったため。

Wikipedia は一次資料ではないので出典としては書かせない。ここから取るのは
「見た目」と「手がかり」だけで、本文に書く事実の裏は論文と原典で取る。
"""
from __future__ import annotations

import re

from .http import get_json, q

JA_API = "https://ja.wikipedia.org/w/api.php"
EN_API = "https://en.wikipedia.org/w/api.php"

_PAREN = re.compile(r"（[^（）]*）|\([^()]*\)")
_REF = re.compile(r"\[[^\]]*\]")


def _extract(api: str, title: str, *, chars: int) -> str:
    d = get_json(api + "?" + q({
        "action": "query", "format": "json", "prop": "extracts",
        "exintro": 1, "explaintext": 1, "redirects": 1,
        "exchars": chars, "titles": title}))
    pages = ((d or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        text = (page.get("extract") or "").strip()
        if text:
            return text
    return ""


def clean(text: str) -> str:
    """読みの括弧と脚注の印を落とし、文ごとに改行する。"""
    text = _REF.sub("", _PAREN.sub("", text))
    text = re.sub(r"\s+", " ", text).strip()
    sents = [s.strip() for s in re.split(r"(?<=[。])", text) if s.strip()]
    return "\n".join(sents)


def lead(subject: str, subject_en: str = "", *, chars: int = 1600) -> str:
    """題材の冒頭。日本語版が無ければ英語版。どちらも無ければ空。"""
    text = _extract(JA_API, subject, chars=chars)
    if not text and subject_en:
        text = _extract(EN_API, subject_en.split(",")[0].strip(), chars=chars)
    return clean(text)


def section(subject: str, lead_text: str) -> str:
    """プロンプトに足す節。何に使い、何に使わないかを本文で言う。"""
    if not lead_text.strip():
        return ""
    return ("\n\n## 題材の記述（Wikipedia日本語版の冒頭）\n"
            "見た目の具体（色・形・数・場所）と、説の出どころ（誰が・何年に）の手がかりに使う。\n"
            "出典としては書かない。ここにある数字も、上の資料に無ければ裏の取れていない数字として扱う。\n"
            + lead_text)
