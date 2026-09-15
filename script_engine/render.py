"""題材とビートシートから、台本生成用のプロンプトを組み立てる。

台本そのものを書くのはLLMだが、構造・比率・文体はここで決め打ちにする。
自由に書かせると必ず元チャンネルの型から外れるため、
「何を書くか」だけをLLMに委ね、「どう書くか」はコード側で固定する。
"""
from __future__ import annotations

from dataclasses import dataclass

from .beats import Beat, BeatSheet, get
from .style import StyleProfile

# 初稿は必ず薄くなる。実測で、目標365字/分に対して
# オーパーツ回が262字/分、巨石遺跡回が253字/分。どちらも約0.70倍だった。
# ビート構成に沿って書くと骨だけ書いて肉を置き忘れる、という系統的な偏りなので、
# 要求字数のほうを割り増しして相殺する。
DRAFT_INFLATION = 1.4


@dataclass(frozen=True)
class Topic:
    subject: str              # 例: 「ヴォイニッチ手稿」「巨石遺跡」
    genre: str = "未解決の謎"  # チャンネル宣言に埋める語
    claims: tuple[str, ...] = ()   # 束ね型で検証する主張（語られている順）
    sources: tuple[str, ...] = ()  # 事前に当たった一次資料


def _beat_block(beat: Beat, sec: int, topic: Topic, chars_per_min: float) -> str:
    target_chars = int(sec / 60 * chars_per_min * DRAFT_INFLATION)
    lines = [f"### {beat.name}（{sec}秒 / 約{target_chars}字）",
             f"- 役割: {beat.purpose}"]
    for r in beat.rules:
        lines.append(f"- {r}")
    if beat.fixed_line:
        filled = beat.fixed_line.format(genre=topic.genre, subject=topic.subject)
        lines.append(f"- ほぼ固定文。これを題材に合わせて最小限だけ変えて使う:\n    「{filled}」")
    return "\n".join(lines)


def build_prompt(topic: Topic, *, kind: str = "flagship",
                 duration_sec: int | None = None,
                 profile: StyleProfile | None = None) -> str:
    sheet: BeatSheet = get(kind, n_claims=max(len(topic.claims), 3)) if kind == "bundle" else get(kind)
    p = profile or StyleProfile()
    total = duration_sec or sheet.typical_duration_sec
    cpm = sum(p.chars_per_min) / 2

    head = [
        "あなたは、都市伝説として語られている話を一次資料まで戻って確かめる",
        "ドキュメンタリーのナレーション台本を書く。",
        "",
        f"# 題材: {topic.subject}",
        f"# 形式: {sheet.name}",
        f"# 尺: {total//60}分{total%60:02d}秒",
        f"# 目安の総文字数: {int(total/60*cpm*DRAFT_INFLATION)}字",
        f"  （読み上げ {cpm:.0f}字/分ぶんより多めに要求している。"
        f"実測で初稿は目標の約0.7倍にしかならないため）",
        "",
        "## 文体（すべて必須。実測値なので守ること）",
        f"- 常体（だ・である）で書く。敬体はCTAの区間だけ",
        f"- 1文の平均を{p.avg_sentence_len[0]:.0f}〜{p.avg_sentence_len[1]:.0f}字に収める。1文=1事実",
        f"- 話速 {p.chars_per_min[0]:.0f}〜{p.chars_per_min[1]:.0f}字/分。1分あたり{p.sentences_per_min[0]:.0f}〜{p.sentences_per_min[1]:.0f}文",
        f"- 数字を1分あたり{p.numerics_per_min_min:.0f}個以上出す。年・件数・寸法・割合を具体で書く",
        "- 4〜6字の短文や体言止めを混ぜて緩急をつける",
        "- 「皆さんどう思いますか」のような視聴者への馴れ合いは書かない",
        "- 「ついに解読」「衝撃の真実」は使わない。確かめられていないことは確かめられていないと書く",
        "- 断定できない箇所は「ただし」で留保を付ける",
        "- 専門語は必ず日常の比喩に着地させる（例: エントロピー→スマホの予測変換）",
        "",
    ]
    if topic.sources:
        head += ["## 使う一次資料（これ以外を出典として書かない）"] + \
                [f"- {s}" for s in topic.sources] + [""]
    if topic.claims:
        head += ["## 検証する主張（語られている順。信頼度順に並べ替えて使う）"] + \
                [f"{i+1}. {c}" for i, c in enumerate(topic.claims)] + [""]

    body = ["## 構成（各ビートの尺と字数を守る）", ""]
    for beat, sec in sheet.allocate(total):
        body.append(_beat_block(beat, sec, topic, cpm))
        body.append("")

    tail = [
        "## 出力形式",
        "各ビートの見出しを `## ビート名` として、その下にナレーション本文だけを書く。",
        "ト書き・カメラ指示・話者名は書かない。読み上げればそのまま音声になる形にする。",
    ]
    return "\n".join(head + body + tail)
