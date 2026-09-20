"""台本の主張が、実際のナレーションのどこから始まるかを割り出す。

これまで章は尺を等分して置いていた（実測で152秒ごと）。台本の主張がその
時刻から始まる保証は無く、画面の「第2主張」が主張の途中で出ていた。
YouTubeの概要欄に貼る時刻としても使えない。

割り出し方:
  1. 何を語るかは seeds/topics/<題材>.yaml の claims に書いてある。台本は
     これを元に書かせたので、同じ語が本文に出る。段落の切れ方は台本ごとに
     違う（実測で15段落と112段落）ので、段落は手掛かりにしない。
  2. 字幕は読み上げの実時間に貼り直してある（assets.tts.retime）。字幕の
     本文を順に繋げば台本と同じ文字列になるので、主張が何文字目から
     始まるかを数えれば、それを含む字幕の開始時刻が主張の開始時刻になる。

台本は主張の順を入れ替えることがある（実測でオーパーツの第3と第4が逆）。
見つけた位置で並べ直すので、指定の順には依らない。
"""
from __future__ import annotations

import re

# YouTubeが章として認めるための条件。満たさないと章そのものが出ない。
MIN_CHAPTER_SEC = 10.0
MIN_CHAPTERS = 3
# 締めがこれより短ければ、章にせず本編に含める
MIN_CLOSING_SEC = 30.0

# 主張文の言い回し。題には要らない。
_TAIL = re.compile(
    r"(?:という|との)?(?:説|主張|見方|指摘|話)?(?:が(?:ある|あった))?"
    r"(?:と(?:される|されている|されてきた|いわれる|言われる|みられる))?"
    r"(?:のだろうか|だろうか|である|です|だ)?。?$")
_LEAD = re.compile(r"^(?:しかし|だが|ところが|一方|さらに|また|そして|では|第\d+幕\s*)、?")
# 切ったところに助詞が残ると「鉄剣は」で宙に浮く。体言で止める。
_HANG = re.compile(r"(?:は|が|を|も|に|で|と|へ|や|の|から|より|まで|という)$")

# 締めの合図。ここから先を「まとめ」にする。
_CLOSING = ("今回扱った", "まとめると", "ここまで見てきた", "最後に",
            "振り返る", "振り返ると", "改めて", "確かめる順番")

# 主張を本文から探すための手掛かり。片仮名3字以上と漢字2字以上を拾う。
_TERM = re.compile(r"[ァ-ヶー・]{3,}|[一-龥]{2,}|[A-Za-z]{3,}")


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text)


def claim_text(claim) -> str:
    """主張は {ja, en} の形でも素の文字列でも来る。日本語の方を使う。"""
    if isinstance(claim, dict):
        return str(claim.get("ja") or claim.get("text") or "")
    return str(claim or "")


def title_of(claim: str, *, limit: int = 30) -> str:
    """主張文を章の題に詰める。"""
    head = re.split(r"[。\n]", claim.strip(), 1)[0]
    head = _LEAD.sub("", head).strip()
    cut = _TAIL.sub("", head).rstrip("、。 ")
    if len(cut) < 6:
        cut = head.rstrip("、。 ")
    if len(cut) > limit:
        part = cut[:limit]
        comma = part.rfind("、")
        cut = (part[:comma] if comma >= limit // 2 else part).rstrip("、 ")
        for _ in range(3):  # 「〜されたもので」のように二重に垂れる
            trimmed = _HANG.sub("", cut).rstrip("、。 ")
            if trimmed == cut or len(trimmed) < 4:
                break
            cut = trimmed
    return cut


def subject_of(claim, *, limit: int = 16) -> str:
    """主張の主語だけを返す。並べる札に入れる短い語。

    題名の詰め方（title_of）で短くすると語の途中で切れる。実測で
    「バールベックの巨石は現代のクレーンでも運べない」が
    「バールベックの巨石は現代のク」になった。主題の印（は・が・も）の
    手前で切れば、語として成立する。
    """
    text = re.split(r"[。\n]", claim_text(claim).strip(), 1)[0]
    text = _LEAD.sub("", text).strip()
    m = re.search(r"^(.{2,%d}?)(?:は|が|も)(?=[^。]{2,})" % limit, text)
    head = m.group(1) if m else text
    if len(head) > limit:
        head = title_of(head, limit=limit)
    return head.rstrip("、。 ")


def offsets(subtitles: list[dict]) -> tuple[str, list[tuple[int, float]]]:
    """字幕を繋いだ本文と、各字幕が本文の何文字目から始まるかを返す。"""
    text, marks, at = [], [], 0
    for s in subtitles:
        body = s.get("text") or ""
        marks.append((at, float(s.get("startSec") or 0.0)))
        text.append(body)
        at += len(body)
    return ("".join(text), marks)


def _at_char(marks: list[tuple[int, float]], pos: int) -> float:
    best = 0.0
    for start, sec in marks:
        if start > pos:
            break
        best = sec
    return best


# 主張1つ分の本文の目安。話速360字/分なので600字でおよそ100秒。
_WINDOW = 600


def terms_of(claim: str) -> list[str]:
    """主張から手掛かりの語を起こす。

    最長の連なりだけでは当たらない。主張が「遮光器土偶」でも本文は
    「遮光器の土偶」と書く。長い語は頭から詰めた形も候補に入れる。
    3字を下限にする。2字まで落とすと関係ない所に当たる。
    """
    out: set[str] = set()
    for term in _TERM.findall(claim):
        if len(term) < 2:
            continue
        out.add(term)
        for n in range(len(term) - 1, 2, -1):
            out.add(term[:n])
    return sorted(out, key=len, reverse=True)


def hits(claim: str, body: str) -> list[int]:
    """主張に含まれる語が本文に出る位置を、すべて集めて並べる。

    同じ位置を重ねて数えない。「遮光器土偶」と「遮光器」は同じ所に当たり、
    語を詰めた分だけ密度が水増しされる。
    """
    found: set[int] = set()
    for term in terms_of(claim):
        at = 0
        while True:
            pos = body.find(term, at)
            if pos < 0:
                break
            found.add(pos)
            at = pos + 1
    return sorted(found)


def find(claim: str, body: str, *, after: int = 0) -> int:
    """主張が本文のどこから語られ始めるかを返す。見つからなければ -1。

    最初に出た所では取れない。導入で主張を一通り予告する台本があり、実測で
    オーパーツの章が全部0〜1分台に寄った。本編では同じ語が繰り返し出るので、
    語が最も密集する塊の先頭を本編の 頭 と見なす。
    """
    pts = [p for p in hits(claim, body) if p >= after]
    if not pts:
        return -1
    best, at = -1, pts[0]
    for i, p in enumerate(pts):
        j = i
        while j < len(pts) and pts[j] - p <= _WINDOW:
            j += 1
        if j - i > best:
            best, at = j - i, p
    return at


def locate(script: str, subtitles: list, claims: list,
           *, intro_ratio: float = 0.04) -> list[dict]:
    """主張ごとに {startSec, title} を返す。"""
    if not subtitles or not claims:
        return []
    body, marks = offsets(subtitles)
    flat = _flat(script)
    # 導入では題材名が一通り読み上げられる。そこを主張の頭と取り違える。
    skip = int(len(flat) * intro_ratio)

    found = []
    for claim in claims:
        text = claim_text(claim)
        if not text:
            continue
        pos = find(_flat(text), flat, after=skip)
        if pos >= 0:
            found.append((pos, title_of(text)))
    # 台本は主張の順を入れ替えることがある。見つけた位置で並べ直す
    found.sort()
    # 同じ位置に寄った主張は、先に出た方だけ残す
    out = [{"startSec": 0.0, "title": "はじめに"}]
    for pos, title in found:
        out.append({"startSec": round(_at_char(marks, pos), 3), "title": title})

    close = _closing_at(flat, claims, after=found[-1][0] if found else skip)
    if close >= 0:
        sec = _at_char(marks, close)
        # 締めが短すぎると章として意味を成さない。残りの尺で確かめる
        if marks and marks[-1][1] - sec >= MIN_CLOSING_SEC:
            out.append({"startSec": round(sec, 3), "title": "まとめ"})
    return prune(out)


def _closing_at(flat: str, claims: list, *, after: int) -> int:
    """締めが始まる位置。決まり文句か、主張の話が尽きた所。"""
    for cue in _CLOSING:
        pos = flat.find(cue, after + 40)
        if pos >= 0:
            return pos
    # 決まり文句は台本ごとに違う（実測で「ご視聴ありがとうございました」）。
    # 言い回しを数え上げるのは切りが無いので、主張の語が出なくなる所で切る。
    tail = -1
    for claim in claims:
        pts = hits(_flat(claim_text(claim)), flat)
        if pts:
            tail = max(tail, pts[-1])
    if tail < 0:
        return -1
    end = flat.find("。", tail)
    return end + 1 if end >= 0 else tail


def cards(outline: list[dict], duration: float) -> list[dict]:
    """画面に出す章カード。0秒の「はじめに」は出さない。

    進捗も一緒に持たせる。参考chは画面下に位置を示すバーと
    「ここから最後の話」の印を出していた。どこまで来たかが見えると、
    先を見る理由になる。
    """
    out = []
    n = 0
    for i, c in enumerate(outline):
        if c["startSec"] <= 0:
            continue
        nxt = outline[i + 1]["startSec"] if i + 1 < len(outline) else duration
        closing = c["title"] in ("まとめ", "おわりに")
        if not closing:
            n += 1
        out.append({
            "startSec": c["startSec"], "durationSec": 3.0,
            # 小さく出るのが label、大きく出るのが title。入れ違えると
            # 大見出しが空になる（実測で章カードの中央が空白になった）。
            "label": "まとめ" if closing else f"第{n}章",
            "title": "" if closing else c["title"],
            "progress": round(min(1.0, c["startSec"] / max(duration, 1.0)), 4),
            "span": round(max(0.0, min(1.0, (nxt - c["startSec"]) / max(duration, 1.0))), 4),
            "last": i == len(outline) - 1,
        })
    return out


def prune(chapters: list[dict], *, min_sec: float = MIN_CHAPTER_SEC) -> list[dict]:
    """YouTubeが章として認める形に整える。

    先頭は0秒、間隔は10秒以上、3つ以上。どれを欠いても章は表示されない。
    """
    out: list[dict] = []
    for c in sorted(chapters, key=lambda c: c["startSec"]):
        if not out:
            out.append({**c, "startSec": 0.0})
        elif c["startSec"] - out[-1]["startSec"] >= min_sec:
            out.append(dict(c))
    return out if len(out) >= MIN_CHAPTERS else []


def stamp(sec: float) -> str:
    """0:00 / 1:02:03。YouTubeが読む形。"""
    sec = max(0, int(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def render(chapters: list[dict]) -> str:
    return "\n".join(f"{stamp(c['startSec'])} {c['title']}" for c in chapters)
