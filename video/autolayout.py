"""台本から、どこに何のオーバーレイを出すかを自動で決める。

台本自身の言い回しが、出すべき部品を示している。
「〜という論文が出た」なら論文カード、「主張はこうだ」なら引用カード、
「4つに分かれる」ならカード列。分析で数えた修辞の型をそのまま規則にする。

実測では15分の台本でオーバーレイは10〜20個。大半のカットは画と字幕だけで、
要所にだけ部品が出る。出しすぎると読めなくなるので、密度は抑える方に倒す。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_DURATION = 3.5   # これより短いと読めない
MAX_DURATION = 8.0   # これより長いと画が死ぬ
MIN_GAP = 1.2        # 部品どうしの最低間隔

# チャンネル宣言は「論文」を含むが論文への言及ではない。先に除外する。
_DECLARATION = re.compile(r"当チャンネル")

# 年号つきで論文・掲載誌に触れている＝出典を見せる場面
_PAPER = re.compile(
    r"(?P<year>[0-9０-９]{4})年[^。]{0,24}?(?P<venue>ネイチャー|サイエンス|"
    r"学術誌|論文|報告書|査読)|(?P<venue2>ネイチャー|サイエンス)[^。]{0,12}?(載|出)")

# 「〜はこうだ」「〜はこうだった」。直後の文が引用の中身になる
_QUOTE_LEAD = re.compile(r"(主張|説明|話|結論|言い分|見方)は(こうだ|こうである|こうだった)[。]?$")

# 「4つに分かれる」「5つを並べた」
_LIST_LEAD = re.compile(r"(?P<n>[0-9０-９一二三四五六七八九]+)\s*(つ|種類|点|件)[^。]{0,8}"
                        r"(に分かれる|を並べた|ある|を挙げ)")

_CAVEAT = re.compile(r"^ただし")
_NUM = re.compile(r"[0-9０-９]+(?:\.[0-9０-９]+)?\s*(?:年|月|日|トン|メートル|キロ|センチ|"
                  r"ボルト|パーセント|％|平方キロ|点|本|人|個|倍|世紀|万|億)?")

_KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}


def _to_int(text: str) -> int:
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if text.isdigit():
        return int(text)
    return _KANJI_NUM.get(text, 0)


@dataclass
class Line:
    """字幕1枚ぶん。build_props が作ったものをそのまま受け取る。"""
    startSec: float
    durationSec: float
    text: str


@dataclass
class Cue:
    kind: str            # document / quote / cardrow / chips / caveat
    startSec: float
    durationSec: float
    payload: dict = field(default_factory=dict)


def _window(lines: list[Line], i: int, n: int) -> tuple[float, float]:
    """i番目から n文ぶんの開始時刻と長さ。"""
    start = lines[i].startSec
    end = lines[min(i + n - 1, len(lines) - 1)]
    span = end.startSec + end.durationSec - start
    return start, max(MIN_DURATION, min(MAX_DURATION, span))


def classify(lines: list[Line]) -> list[Cue]:
    """字幕列から候補キューを拾う。ここでは重なりを気にしない。"""
    cues: list[Cue] = []
    for i, line in enumerate(lines):
        text = line.text
        if _DECLARATION.search(text):
            continue

        m = _PAPER.search(text)
        if m:
            start, dur = _window(lines, i, 2)
            cues.append(Cue("document", start, dur, {
                "venue": (m.group("venue") or m.group("venue2") or "").strip(),
                "year": m.group("year") or "",
                "title": text.rstrip("。"),
            }))
            continue

        if _QUOTE_LEAD.search(text) and i + 1 < len(lines):
            start, dur = _window(lines, i + 1, 2)
            body = " ".join(l.text for l in lines[i + 1:i + 3]).rstrip("。")
            cues.append(Cue("quote", start, dur, {
                "heading": text.rstrip("。"), "translation": body,
            }))
            continue

        m = _LIST_LEAD.search(text)
        if m:
            n = _to_int(m.group("n"))
            if 2 <= n <= 9:
                start, dur = _window(lines, i, 2)
                cues.append(Cue("cardrow", start, dur, {"count": n, "caption": text.rstrip("。")}))
            continue

        if _CAVEAT.search(text):
            start, dur = _window(lines, i, 2)
            cues.append(Cue("caveat", start, dur, {"text": text.rstrip("。")}))
            continue

        nums = _NUM.findall(text)
        if len(nums) >= 3:
            start, dur = _window(lines, i, 1)
            cues.append(Cue("chips", start, dur, {"items": nums[:3]}))
    return cues


def schedule(cues: list[Cue]) -> list[Cue]:
    """重なりを解く。画面中央を占める部品は同時に1つだけにする。

    出しすぎると読めない。後から来たものを捨てるのではなく、
    先に始まるものを優先し、間隔が足りないものを落とす。
    """
    kept: list[Cue] = []
    for cue in sorted(cues, key=lambda c: c.startSec):
        if kept:
            last = kept[-1]
            if cue.startSec < last.startSec + last.durationSec + MIN_GAP:
                continue
        kept.append(cue)
    return kept


def to_props(cues: list[Cue], codes: list[str] | None = None) -> dict:
    """キューを Remotion の props の各配列に振り分ける。"""
    out: dict[str, list] = {
        "quoteCards": [], "chipStacks": [], "cardRows": [], "documentCards": [],
    }
    for idx, cue in enumerate(cues):
        base = {"startSec": round(cue.startSec, 3), "durationSec": round(cue.durationSec, 3)}
        if cue.kind == "document":
            out["documentCards"].append({**base,
                "venue": f"{cue.payload['venue']} {cue.payload['year']}".strip(),
                "title": cue.payload["title"], "badge": "一次資料"})
        elif cue.kind == "quote":
            out["quoteCards"].append({**base, "side": "left",
                "heading": cue.payload["heading"], "translation": cue.payload["translation"]})
        elif cue.kind == "caveat":
            out["quoteCards"].append({**base, "side": "right",
                "heading": "留保", "translation": cue.payload["text"]})
        elif cue.kind == "chips":
            out["chipStacks"].append({**base, "items": cue.payload["items"]})
        elif cue.kind == "cardrow":
            n = cue.payload["count"]
            labels = (codes or [])[:n]
            cards = [{"code": labels[i] if i < len(labels) else f"{i+1}",
                      "dimmed": False} for i in range(n)]
            out["cardRows"].append({**base, "cards": cards, "caption": cue.payload["caption"]})
    return out


def build(lines: list[Line], codes: list[str] | None = None) -> dict:
    return to_props(schedule(classify(lines)), codes)
