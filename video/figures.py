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


def _starts(outline: list[dict]) -> list[float]:
    """主張の章の頭。「はじめに」（0秒）と基本の章（「〜とは何か」）は除く。"""
    return [c["startSec"] for c in outline if c.get("startSec", 0) > 0 and c.get("kind") != "basics"]


def panels_from_plan(plan: dict, outline: list[dict], duration: float) -> list[dict]:
    """章 i の図を、章 i の頭から OFFSET_SEC 後に置く。outline[0] は「はじめに」。"""
    chapters = plan.get("chapters") or []
    starts = _starts(outline)
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
_LISTED = re.compile(r"つ確かめる|つ取り上げ|つに絞れる|順に[0-9０-９一二三四五六七八九]つ")
MARK_OF = {"当たり": "ok", "半分当たり": "partial", "決まっていない": "unknown", "跡形なし": "no"}


def _labels(plan: dict) -> list[str]:
    """札に出す短い名前。全主張に共通する題材名（「死海文書に」など）を外す。

    章カードの作り方（主語か述部を切り出す）だと「死海文書に」「死海文書を隠したの」の
    ような切れ端になった（描いて確かめた）。札は幅が狭いので、主張の文から題材名だけ
    抜いて、22字までにする。"""
    claims = [str(c.get("claim") or "") for c in plan.get("chapters") or []]
    words = {}
    for c in claims:
        for w in set(re.findall(r"[一-龥ァ-ヶー]{3,}", c)):
            words[w] = words.get(w, 0) + 1
    common = max(words, key=lambda w: (words[w], len(w)), default="")
    out = []
    for c in claims:
        lab = c
        if common and words.get(common, 0) * 2 >= len(claims):
            lab = re.sub(re.escape(common) + r"(には|に|の|を|は|が|で)?", "", c)
        lab = re.sub(r"(である|だ)。?$", "", lab).strip("、。 ")
        out.append((lab if len(lab) >= 4 else c)[:22])
    return out


def _grams(t: str) -> set[str]:
    t = re.sub(r"[\s、。「」『』]", "", t or "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def verdict_boards(plan: dict, subtitles: list[dict], outline: list[dict]) -> list[dict]:
    """語られている話を並べ、章が終わるたびに判定の印を付けていく。

    参考chは「当たっていたもの → 理由が違うもの → 跡形もなくなるもの」の順に並べ、
    研究者を並べた札で ✓ と ? を切り替えていた。判定は章ごとに設計図で決まっていて
    本文にも機械的に入るので、画面と語りが食い違わない。帯には動画の問いを出し、
    最後の札だけ答えを出す。札は、章で「大きな問いにとっての意味」を語る所に出す。
    （答えの候補を数えて消していく札にしたら、候補の名前が抽象的で、何が残ったのか
    分からないと言われた。死海文書。）"""
    chapters = plan.get("chapters") or []
    if not chapters or not subtitles:
        return []
    labels = _labels(plan)
    marks = [MARK_OF.get(str(c.get("verdict") or ""), "unknown") for c in chapters]
    starts = _starts(outline)
    end = max(s["startSec"] + s["durationSec"] for s in subtitles)
    question = str(plan.get("mystery") or "")

    def board(upto: int, caption: str) -> dict:
        cards = []
        for i, lab in enumerate(labels):
            card = {"code": str(i + 1), "label": lab, "dimmed": i > upto}
            if i <= upto:
                card["mark"] = marks[i]
            cards.append(card)
        return {"caption": caption, "cards": cards}

    out = []
    first = starts[0] if starts else end
    for s in subtitles:
        if s["startSec"] < first and _LISTED.search(s.get("text") or ""):
            out.append({"startSec": round(s["startSec"], 3), "durationSec": BOARD_SEC,
                        **board(-1, question)})
            break
    for k, c in enumerate(chapters):
        if k >= len(starts):
            break
        a, b = starts[k], (starts[k + 1] if k + 1 < len(starts) else end)
        span = [s for s in subtitles if a <= s["startSec"] < b]
        want = _grams(str(c.get("bearing") or ""))
        best = max(span, key=lambda s: len(want & _grams(s.get("text") or "")), default=None)
        if best and want and len(want & _grams(best.get("text") or "")) >= 0.4 * min(len(want), 12):
            at = best["startSec"]
        else:
            at = max(a, b - BOARD_SEC - 1)
        last = k == len(chapters) - 1
        cap = str((plan.get("closing") or {}).get("answer") or "") if last else question
        out.append({"startSec": round(at, 3), "durationSec": BOARD_SEC, **board(k, cap)})
    return out


def inject(props: dict, plan: dict) -> tuple[int, int, int]:
    """props に図・判定表・考察の印を足す。戻り値は (図, ボード, テロップ) の数。"""
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

    boards = verdict_boards(plan, subs, outline)
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
