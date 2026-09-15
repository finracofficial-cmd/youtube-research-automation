"""台本の文体制約。すべて元チャンネルの実測値から来ている。

出典: analysis/otonano-jiyukenkyu.md（ヴォイニッチ回52:39・ピラミッド回37:52の
字幕全文を解析した値）。ここの数値は好みではなく計測結果なので、
変えるときは元データを測り直すこと。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 常体（だ・である）。ナレーション本体はこれで統一されている（実測 161 : 2）。
PLAIN_END = re.compile(r"(だ|である|だった|であった|ない|いる|する|なる|た|う)[。]$")
POLITE_END = re.compile(r"(です|ます|ません|ました|でしょう|ください)[。]$")
NUMERIC = re.compile(r"[0-9０-９]+")
# 視聴者への馴れ合い。元チャンネルはほぼ使わない（38分で1件）。
CHATTY = re.compile(r"(どう思いますか|みなさんは|皆さんは|いかがでしょう|コメント欄で教えて|でしょうか\?)")


@dataclass(frozen=True)
class StyleProfile:
    """実測レンジ。下限・上限とも元動画2本が収まる幅に取っている。"""
    avg_sentence_len: tuple[float, float] = (17.0, 26.0)     # 実測 21.6 / 21.0
    sentences_per_min: tuple[float, float] = (13.0, 20.0)    # 実測 16.3
    chars_per_min: tuple[float, float] = (320.0, 410.0)      # 実測 358 / 380
    plain_form_ratio_min: float = 0.80                       # 常体の比率
    question_ratio_max: float = 0.05                         # 実測 1.0%
    numerics_per_min_min: float = 4.0                        # 実測 7.9
    max_chatty: int = 2                                      # 実測 0〜1


@dataclass
class Metrics:
    n_sentences: int
    n_chars: int
    avg_sentence_len: float
    sentences_per_min: float
    chars_per_min: float
    plain_form_ratio: float
    question_ratio: float
    numerics_per_min: float
    n_chatty: int
    short_sentence_ratio: float  # 10字以下。体言止めの緩急が入っているか
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。？！?!])", text) if s.strip()]


def analyze(text: str, duration_sec: float) -> Metrics:
    """台本テキストを実測プロファイルに照らして採寸する。"""
    if duration_sec <= 0:
        raise ValueError("duration_sec must be positive")
    sents = split_sentences(text)
    if not sents:
        raise ValueError("text contains no sentences")
    minutes = duration_sec / 60.0
    n_chars = sum(len(s) for s in sents)
    ended = [s for s in sents if s.endswith("。")]
    plain = sum(bool(PLAIN_END.search(s)) for s in ended)
    polite = sum(bool(POLITE_END.search(s)) for s in ended)
    return Metrics(
        n_sentences=len(sents),
        n_chars=n_chars,
        avg_sentence_len=n_chars / len(sents),
        sentences_per_min=len(sents) / minutes,
        chars_per_min=n_chars / minutes,
        plain_form_ratio=plain / max(plain + polite, 1),
        question_ratio=sum(bool(re.search(r"[？?]", s)) for s in sents) / len(sents),
        numerics_per_min=len(NUMERIC.findall(text)) / minutes,
        n_chatty=len(CHATTY.findall(text)),
        short_sentence_ratio=sum(len(s) <= 10 for s in sents) / len(sents),
    )


def validate(text: str, duration_sec: float, profile: StyleProfile | None = None) -> Metrics:
    """採寸したうえで、レンジを外れた項目を violations に積む。"""
    p = profile or StyleProfile()
    m = analyze(text, duration_sec)
    lo, hi = p.avg_sentence_len
    if not lo <= m.avg_sentence_len <= hi:
        m.violations.append(f"平均文長 {m.avg_sentence_len:.1f}字 が {lo}〜{hi} の外")
    lo, hi = p.sentences_per_min
    if not lo <= m.sentences_per_min <= hi:
        m.violations.append(f"文の密度 {m.sentences_per_min:.1f}文/分 が {lo}〜{hi} の外")
    lo, hi = p.chars_per_min
    if not lo <= m.chars_per_min <= hi:
        m.violations.append(f"話速 {m.chars_per_min:.0f}字/分 が {lo}〜{hi} の外")
    if m.plain_form_ratio < p.plain_form_ratio_min:
        m.violations.append(f"常体率 {m.plain_form_ratio:.0%} が下限 {p.plain_form_ratio_min:.0%} 未満")
    if m.question_ratio > p.question_ratio_max:
        m.violations.append(f"疑問文 {m.question_ratio:.1%} が上限 {p.question_ratio_max:.0%} 超")
    if m.numerics_per_min < p.numerics_per_min_min:
        m.violations.append(f"数字 {m.numerics_per_min:.1f}個/分 が下限 {p.numerics_per_min_min} 未満")
    if m.n_chatty > p.max_chatty:
        m.violations.append(f"視聴者への馴れ合い表現 {m.n_chatty}件 が上限 {p.max_chatty} 超")
    return m
