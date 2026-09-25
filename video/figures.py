"""設計図（reports/<name>_plan.json）から、動画側に足すもの。

  図      章ごとの figure（年表・棒）を、既存の作図パネル（Explainer）として置く。
          台本の数字から自動で拾うパネル（explainers.plan）は、年が3つ並ぶ・同じ
          単位が2つ並ぶ箇所にしか出ない。設計図は章ごとに「この章の数字で描ける図」を
          決めているので、それを章の頭に置く。数字は資料に無いものを落としてある。
  考察    「ここからは資料に無い。私の考えだ。」の文が読まれる時刻にテロップを出す。
          事実と考察を画面でも分ける。
  検索語  章ごとの証拠の場所・人・物を、画を探す手がかりとして plan_shots に渡す。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PANEL_SEC = 9.0
OFFSET_SEC = 12.0     # 章カード（3秒）と冒頭の通説の直後に置く


def load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _num(s: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group(0)) if m else None


def panel_of(fig: dict) -> dict | None:
    """設計図の figure を Explainer の形にする。描けなければ None。"""
    kind = fig.get("kind")
    items = [it for it in (fig.get("items") or []) if it]
    heading = str(fig.get("heading") or "").strip()
    if kind == "timeline":
        marks = []
        for it in items:
            y = str(it.get("year") or "").strip() or str(it.get("value") or "").strip()
            if not _num(y):
                continue
            marks.append((_num(y), {"year": y, "text": str(it.get("label") or "")[:30]}))
        if len(marks) < 3:
            return None
        marks.sort(key=lambda kv: kv[0])
        return {"kind": "timeline", "heading": heading or "分かっている順番",
                "marks": [m for _, m in marks[:4]]}
    if kind == "scale":
        vals = []
        for it in items:
            v = _num(str(it.get("value") or ""))
            if v and v > 0:
                vals.append((v, str(it.get("value") or ""), str(it.get("label") or "")[:26]))
        if len(vals) < 2:
            return None
        top = max(v for v, _, _ in vals)
        low = min(v for v, _, _ in vals)
        if low <= 0 or top / low < 1.5:
            return None
        return {"kind": "scale", "heading": heading or "並べて比べる",
                "bars": [{"label": label, "value": round(v / top, 4), "readout": readout}
                         for v, readout, label in vals[:4]]}
    return None


def panels_from_plan(plan: dict, outline: list[dict], duration: float) -> list[dict]:
    """章 i の図を、章 i の頭から OFFSET_SEC 後に置く。outline[0] は「はじめに」。"""
    chapters = plan.get("chapters") or []
    starts = [c["startSec"] for c in outline if c.get("startSec", 0) > 0]
    out = []
    for i, ch in enumerate(chapters):
        if i >= len(starts):
            break
        panel = panel_of(ch.get("figure") or {})
        if not panel:
            continue
        start = starts[i] + OFFSET_SEC
        if start + PANEL_SEC > duration - 4:
            continue
        out.append({**panel, "startSec": round(start, 3), "durationSec": PANEL_SEC})
    return out


SPEC_START = re.compile(r"ここからは資料に無い|私の考えだ")
SPEC_END = re.compile(r"ここまでが考察")


def speculation_telops(subtitles: list[dict]) -> list[dict]:
    """考察の始まりと終わりの字幕の時刻に、印のテロップを出す。"""
    out = []
    for s in subtitles:
        t = s.get("text") or ""
        if SPEC_START.search(t) and not any(o["text"].startswith("ここから") for o in out):
            out.append({"startSec": round(s["startSec"], 3), "durationSec": 6.0,
                        "text": "ここからは考察（資料に無い）", "variant": "plain", "zone": "upper"})
        elif SPEC_END.search(t) and out:
            out.append({"startSec": round(s["startSec"], 3), "durationSec": 4.0,
                        "text": "考察はここまで", "variant": "plain", "zone": "upper"})
            break
    return out


_SENTENCE = re.compile(r"[。、]|無い|ない|記録|されている|された|分析$|検討$|関係")


def _hint_ok(x: str) -> bool:
    """画像の検索に使える語か。文・否定・論文の題名は落とす。

    設計図の証拠欄には「AIによる痕跡発見の記録は無い」や英語の論文題名が入っていた。
    そのまま検索語にすると、その語で画像は見つからないか、関係の無い画が出る。"""
    x = x.strip()
    if not x or x == "不明" or len(x) > 20:
        return False
    if _SENTENCE.search(x):
        return False
    latin = sum(c.isascii() and c.isalpha() for c in x)
    return not (latin > 12 and " " in x and len(x.split()) > 3)   # 題名らしい長い英語


def hints(plan: dict) -> list[list[str]]:
    """章ごとの、画を探す手がかり。証拠の場所・人・物と専門語。"""
    out: list[list[str]] = []
    for c in plan.get("chapters") or []:
        ev = c.get("evidence") or {}
        h = [str(ev.get(k) or "") for k in ("who", "where", "what")]
        h += [str(j.get("term") or "") for j in (c.get("jargon") or [])]
        seen, keep = set(), []
        for x in h:
            x = x.strip()
            if _hint_ok(x) and x not in seen:
                seen.add(x)
                keep.append(x)
        out.append(keep)
    return out


BOARD_SEC = 6.0
_NARROW = re.compile(r"残る(のは|候補)|残った|消えた|崩れた|絞られ|絞れ")
_LISTED = re.compile(r"つに絞れる|候補は|答えは")


def _remaining_by_chapter(plan: dict) -> list[list[str]] | None:
    """章ごとの残る候補。設計図の remaining が候補の文字列で揃っているときだけ使う。"""
    cands = [str(x) for x in (plan.get("candidates") or [])]
    rows = [[str(x) for x in (c.get("remaining") or [])] for c in (plan.get("chapters") or [])]
    if len(cands) < 2 or not rows or not all(rows):
        return None
    if any(x not in cands for r in rows for x in r):
        return None           # 主張の名前で数えている設計図は、ボードにしない（誤った表示になる）
    return rows


def _board(cands: list[str], remaining: list[str] | None, *, final: bool = False,
           caption: str = "") -> dict:
    codes = "ABCD"
    cards = []
    for i, c in enumerate(cands):
        gone = remaining is not None and c not in remaining
        card = {"code": codes[i] if i < len(codes) else str(i + 1), "label": c, "dimmed": gone}
        if gone:
            card["mark"] = "no"
        elif final and remaining is not None:
            card["mark"] = "ok"
        cards.append(card)
    return {"caption": caption, "cards": cards}


def candidate_boards(plan: dict, subtitles: list[dict], outline: list[dict]) -> list[dict]:
    """答えの候補を並べ札で出す。冒頭で全部、章の終わりで消えたものに×。

    数字の無い題材でも候補は必ずあるので、図の出ない題材でも毎回出せる。
    視聴者が「いま何が残っているか」を見失うと、章がばらばらの話に見える
    （死海文書の初稿で言われた「すっと入ってこない」）。"""
    cands = [str(x) for x in (plan.get("candidates") or [])]
    rows = _remaining_by_chapter(plan)
    if not rows or not subtitles:
        return []
    starts = [c["startSec"] for c in outline if c.get("startSec", 0) > 0]
    end = max(s["startSec"] + s["durationSec"] for s in subtitles)
    out = []
    # 冒頭: 候補を並べる文が読まれる時刻
    first = starts[0] if starts else end
    for s in subtitles:
        if s["startSec"] < first and _LISTED.search(s.get("text") or ""):
            out.append({"startSec": round(s["startSec"], 3), "durationSec": BOARD_SEC,
                        **_board(cands, None, caption=str(plan.get("mystery") or ""))})
            break
    # 章の終わり: 章の中で最後に「残る／消えた」が読まれる時刻。消えた候補が変わった章だけ
    prev = list(cands)
    for k, rem in enumerate(rows):
        if k >= len(starts):
            break
        a, b = starts[k], (starts[k + 1] if k + 1 < len(starts) else end)
        hit = [s for s in subtitles if a <= s["startSec"] < b and _NARROW.search(s.get("text") or "")]
        last = k == len(rows) - 1
        if set(rem) != set(prev) or last:
            at = hit[-1]["startSec"] if hit else max(a, b - BOARD_SEC - 1)
            cap = "残るのは " + "、".join(rem) if not last else "答え: " + "、".join(rem)
            out.append({"startSec": round(at, 3), "durationSec": BOARD_SEC,
                        **_board(cands, rem, final=last, caption=cap)})
        prev = rem
    return out


def inject(props: dict, plan: dict) -> tuple[int, int, int]:
    """props に図・候補ボード・考察の印を足す。戻り値は (図, ボード, テロップ) の数。"""
    import explainers as ex  # video/ にある

    outline = props.get("outline") or []
    subs = props.get("subtitles") or []
    duration = max((s["startSec"] + s["durationSec"]) for s in subs) if subs else 0.0
    panels = panels_from_plan(plan, outline, duration)
    if panels:
        have = props.get("explainers") or []
        # 自動で拾ったパネルと重なるものは、設計図のほうを優先して置き換える
        keep = [p for p in have if not any(ex._overlaps(p["startSec"], p["startSec"] + p["durationSec"],
                                                        q["startSec"], q["startSec"] + q["durationSec"])
                                           for q in panels)]
        props["explainers"] = sorted(keep + panels, key=lambda p: p["startSec"])
        props = ex.clear(props, panels)

    boards = candidate_boards(plan, subs, outline)
    # 作図パネルと重なるボードは出さない（全画面の図の上に札が載る）
    spans = [(p["startSec"], p["startSec"] + p["durationSec"]) for p in props.get("explainers") or []]
    boards = [b for b in boards if not any(ex._overlaps(b["startSec"], b["startSec"] + b["durationSec"], x, y)
                                           for x, y in spans)]
    if boards:
        # ボードの間は他の札を外す。並べ札が2つ重なると読めない
        props = ex.clear(props, boards, keys=("stats", "quoteCards", "chipStacks", "cardRows",
                                              "documentCards", "portraits", "charts", "timelines",
                                              "rangeBars", "glyphs", "grids", "telops"))
        props.setdefault("cardRows", []).extend(boards)
        props["cardRows"].sort(key=lambda r: r["startSec"])

    telops = speculation_telops(subs)
    if telops:
        props.setdefault("telops", []).extend(telops)
    return len(panels), len(boards), len(telops)
