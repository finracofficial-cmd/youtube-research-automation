"""収集した素材から、概要欄に貼るクレジット文を組む。

CC BY / CC BY-SA は作者名とライセンス名の表示が条件。
PD / CC0 は法的な義務は無いが、元チャンネルは出典を画面に出している。
ここでは義務のあるものを個別に列挙し、義務の無いものは提供元をまとめて書く。
"""
from __future__ import annotations

import collections

from .sources import Asset


def build(assets: list[Asset], *, ai_generated_note: str | None = None) -> str:
    must = [a for a in assets if a.needs_attribution]
    free = [a for a in assets if not a.needs_attribution]

    lines = ["【画像・資料の出典】", ""]

    if must:
        lines += ["■ CC BY / CC BY-SA（表示が条件）"]
        for a in sorted(must, key=lambda x: x.author):
            lines.append(f"・{a.author} — {a.license}")
            lines.append(f"　{a.page_url}")
        lines.append("")

    if free:
        by_source = collections.Counter(a.source for a in free)
        where = "・".join(
            {"commons": "Wikimedia Commons", "met": "メトロポリタン美術館",
             "nasa": "NASA"}.get(s, s) + f"（{n}点）"
            for s, n in by_source.most_common()
        )
        lines += ["■ パブリックドメイン / CC0", f"　{where}", ""]

    if ai_generated_note:
        lines += ["■ AI生成", f"　{ai_generated_note}", ""]

    return "\n".join(lines).rstrip() + "\n"


def unlicensed(assets: list[Asset]) -> list[Asset]:
    """ライセンスが空のものを洗い出す。公開前にここが空であることを確認する。"""
    return [a for a in assets if not a.license.strip()]
