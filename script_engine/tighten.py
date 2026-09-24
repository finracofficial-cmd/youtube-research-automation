"""読み上げに耐える形に台本を整える。

書かせた台本を実測に照らすと、平均文長が基準を超えていた。当初は文法が
複雑なせいだと考えて接続助詞で切ろうとしたが、長文272件を数えたところ
接続助詞は10箇所しかなく、57/82は読点すら無かった。

実際の原因は、英語の論文タイトルが本文に埋め込まれていたことだった。

  2006年の論文「Archaeological theory and Japanese methodology in
  Jomon research」では、銅鐸の用途について議論されている。

英語部分だけで70字あり、これが文長を押し上げていた。それ以上に、
読み上げると日本語の途中で英語の題名が読まれる。文長の問題ではなく、
ナレーションとして成立しない。出典は概要欄に置くもので、声に出すものではない。

そのうえで、残る長文は接続助詞で切る。切ってよい形だけを対象にする。
日本語は雑に切ると非文になるため、述語で終わっていることが確かめられる
場合に限る。「歯車が、回る」の「が」は主語の印なので切ってはいけない。
"""
from __future__ import annotations

import re

# 鉤括弧の中がほぼラテン文字なら、英語の題名とみなす
_LATIN_QUOTE = re.compile(r"「([^」]{12,})」")


def _is_latin(s: str) -> bool:
    letters = [c for c in s if not c.isspace()]
    if not letters:
        return False
    latin = sum(1 for c in letters if c.isascii())
    return latin / len(letters) >= 0.8


# 題名を抜いたあと、直前が連体形のままだと修飾先が消えて非文になる
# （「今回扱った「A」や「B」も」->「今回扱ったも」）。名詞を補って繋ぐ。
_NEEDS_NOUN = re.compile(r"(?:った|した|扱う|挙げた|示した|の|な)$")


def _replace_title(text: str, start: int, end: int) -> str:
    """題名を抜く。抜くと修飾先が消える場合は「論文」を置く。"""
    before = text[:start]
    return before + ("論文" if _NEEDS_NOUN.search(before) else "") + text[end:]


def drop_foreign_titles(text: str) -> str:
    """本文に埋め込まれた英語の題名を外す。

    「2006年の論文「…」では」のように、題名を抜いても文が成立する形で
    使われている。並列（「A」や「B」）も、まとめて1つに畳む。
    """
    # 日本語の引用は残す。見つけた位置から先へ進めて次を探す。
    # 打ち切ると、日本語の引用が先にある台本で英語の題名に届かない
    # （実測で12件中5件が残った）。
    def sweep(pattern: re.Pattern, group_index: int) -> None:
        nonlocal text
        at = 0
        while True:
            m = pattern.search(text, at)
            if not m:
                return
            if not _is_latin(m.group(group_index)):
                at = m.end()
                continue
            text = _replace_title(text, m.start(), m.end())
            at = m.start()

    # 並列で複数並んでいる場合、間の「や」「と」「、」ごと畳む
    sweep(re.compile(r"「[^」]{12,}」(?:\s*[やと、]\s*「[^」]{12,}」)+"), 0)
    sweep(_LATIN_QUOTE, 1)
    # 題名を抜いた跡の重なりを均す
    text = re.sub(r"[、]{2,}", "、", text)
    text = re.sub(r"\s+、", "、", text)
    return text


# 切ってよい接続。左側が述語で終わっていることを形で確かめる。
# 「が」は主語の印にもなるので、述語の語尾が直前にある場合だけ切る。
_TERMINAL = r"(?:だ|である|ある|いる|した|する|れる|られる|ない|た|る|う)"
_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # 〜ており、 -> 〜ている。
    (re.compile(r"ており、"), "ている。"),
    (re.compile(r"であり、"), "である。"),
    (re.compile(r"ではあるが、"), "ではある。しかし"),
    # 文頭の「だが、」は接続詞なので切らない。切ると「だ。しかし」になる（実測）
    (re.compile(rf"(?<=[^。！？\n])({_TERMINAL})が、"), r"\1。しかし"),
    (re.compile(rf"({_TERMINAL})ので、"), r"\1。そのため"),
    (re.compile(rf"({_TERMINAL})ため、"), r"\1。そのため"),
)


def split_long(text: str, max_len: int = 26) -> str:
    """長すぎる文だけ、切ってよい形で切る。

    短い文には触らない。切れる形が無ければそのまま残す。
    """
    out = []
    for sent in re.split(r"(?<=[。？！])", text):
        while len(sent.strip()) > max_len:
            before = sent
            for pat, rep in _RULES:
                sent = pat.sub(rep, sent, count=1)
                if sent != before:
                    break
            if sent == before:
                break
        out.append(sent)
    return "".join(out)


def tighten(text: str, max_len: int = 26) -> str:
    """読み上げに耐える形にする。"""
    return split_long(drop_foreign_titles(text), max_len)
