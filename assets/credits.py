"""収集した素材から、概要欄に貼るクレジット文を組む。

CC BY / CC BY-SA は作者名とライセンス名の表示が条件。
PD / CC0 は法的な義務は無いが、元チャンネルは出典を画面に出している。
ここでは義務のあるものを個別に列挙し、義務の無いものは提供元をまとめて書く。
"""
from __future__ import annotations

import collections

from .sources import Asset


def _unique(assets: list[Asset]) -> list[Asset]:
    """同じ素材は1行にまとめる。

    1枚の画は複数のカットで使う。渡されたまま並べると、概要欄に同じ
    作者名が使用回数ぶん並ぶ。出典ページで同一性を見るが、出典ページを
    持たない素材もあるので、表示に使う項目まで含めて鍵にする。
    """
    seen: set[tuple] = set()
    out = []
    for a in assets:
        key = (a.page_url, a.source, a.title, a.license, a.author)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def build(assets: list[Asset], *, ai_generated_note: str | None = None) -> str:
    assets = _unique(assets)
    generated = [a for a in assets if a.source == "generated"]
    rest = [a for a in assets if a.source != "generated"]
    must = [a for a in rest if a.needs_attribution]
    free = [a for a in rest if not a.needs_attribution]

    # 生成画像が入っていたら、申告は呼び出し側の任意ではなく必須にする。
    # 書き忘れると「一次資料でやっている」という看板が嘘になるため。
    if generated and not ai_generated_note:
        ai_generated_note = (
            f"一部の画像はAI生成です（{len(generated)}点）。実写・実物ではありません。")

    lines = ["■ 画像のクレジット", ""]

    if must:
        lines += ["● CC BY / CC BY-SA（表示が条件）"]
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
        lines += ["● パブリックドメイン / CC0", f"　{where}", ""]

    if ai_generated_note:
        lines += ["● AI生成", f"　{ai_generated_note}", ""]

    return "\n".join(lines).rstrip() + "\n"


def unlicensed(assets: list[Asset]) -> list[Asset]:
    """ライセンスが空のものを洗い出す。公開前にここが空であることを確認する。"""
    return [a for a in assets if not a.license.strip()]
