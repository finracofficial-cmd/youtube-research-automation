"""写真を隠して作図だけで語る区間を決める。

参考chは、素材の上に札を載せるだけでなく、作図だけで構成された区間を挟む。
こちらは全フレームが「写真＋札」で、その状態が存在しなかった。

作るのは台本から取れるものに限る。無い話を図にすると、絵のために事実を
足すことになる。取れるのは3種類:

  contrast  言われていること / 資料が言っていること。このchの型そのもの。
  timeline  年が3つ以上並ぶところ。
  scale     同じ単位の量が2つ以上並ぶところ。

区間に入ったら、そこに重なる札と出典ラベルは外す。写真が見えていないのに
帰属を出すと、出所の表示として誤りになる。
"""
from __future__ import annotations

import re

from autolayout import Line, _RANGE, _STAT, _clip, _is_trivial, _to_float

# パネル1枚の長さ。短いと読み切れず、長いと語りから浮く。
PANEL_SEC = 9.0
MIN_GAP_SEC = 55.0          # パネル同士の間隔。続けて出すと図解動画になる
MAX_PANELS = 9
# 型ごとの上限。scale は候補が桁違いに多く（実測で37対9対2）、任せると
# 全部棒グラフになる。対比を水増しして数を揃えるのは、資料が言っていない
# ことを言わせることになるので、そちらはやらない。
PER_KIND = 3
# 棒で並べて差が見える最小の比。これ未満は並べても読み取れない。
MIN_RATIO = 1.5

# 主張の言い回し。ここが「言われていること」になる。
_CLAIM = re.compile(r"(とされ(る|ている|てきた)|という説があ(る|った)|"
                    r"と(いわ|言わ)れて(いる|きた)|と考えられてきた|"
                    r"という主張があ(る|った)|とされた)")
# 資料の側。論文・調査・実験・測定に触れた文。
_EVIDENCE = re.compile(r"(論文|査読|報告書|学術誌|ネイチャー|サイエンス|"
                       r"調査|発掘|実験|測定|年代測定|分析|検証|研究チーム)")
# 並べて比べられない単位。世紀は順序であって量ではない。実測で
# 「14世紀」と「紀元前3世紀」が 1.00 対 0.21 の棒になった。
_NOT_SCALAR = {"世紀", "度", "度目"}

# 年号。紀元前を落とすと順序が逆になる。実測で「紀元前3000年頃」が
# 「3000年」として2006年の後ろに並んだ。
_ERA_YEAR = re.compile(r"(?P<bc>紀元前)?\s*(?P<n>[0-9０-９]{3,5})\s*年"
                       r"(?P<post>かけて|間|以上|以内|後|ぶり|余り|ほど|近く|に一度|に1度)?")


def sentences(lines: list[Line]) -> list[Line]:
    """折り返された字幕を文に戻す。

    字幕は画面幅で折ってあるので、1行が文の断片になっている。そのままだと
    「〜とされる」の行と、それを受ける資料の行が別々の窓に落ちて組にならない
    （実測で対比の候補が全台本で0〜1件しか出なかった）。
    """
    out: list[Line] = []
    buf: list[str] = []
    start = 0.0
    end = 0.0
    for line in lines:
        body = (line.text or "").strip()
        if not buf:
            start = line.startSec
        buf.append(body)
        end = line.startSec + line.durationSec
        if body.endswith(("。", "！", "？")):
            out.append(Line(start, max(0.1, end - start), "".join(buf)))
            buf = []
    if buf:
        out.append(Line(start, max(0.1, end - start), "".join(buf)))
    return out


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


def _text(line: Line) -> str:
    return (line.text or "").strip()


def contrast_at(lines: list[Line], i: int) -> dict | None:
    """主張の文と、その後の資料の文を組にする。"""
    claim = _text(lines[i])
    if not _CLAIM.search(claim) or len(claim) < 12:
        return None
    for j in range(i + 1, min(i + 6, len(lines))):
        body = _text(lines[j])
        if len(body) < 12:
            continue
        # 否定語だけでは足りない。実測で「石の角は3つや4つではない」が
        # 「剃刀の刃も入らない」への反証として組まれた。あれは説明文で
        # あって反証ではない。資料に触れた文だけを「資料が言っていること」
        # として出す。資料を誤って引くのが、このchでは一番重い間違いになる。
        if _EVIDENCE.search(body):
            return {"kind": "contrast", "heading": "説と資料",
                    "claim": _clip(claim, 46), "evidence": _clip(body, 46)}
    return None


def _year(body: str) -> tuple[int, str] | None:
    """年号を1つ取る。並べ替え用の値と、表示用の文字列を返す。

    「500年かけて」は期間であって年号ではない。西暦は1000年以降だけ
    通し、それ未満は紀元前の表記があるときだけ年号とみなす。
    """
    for m in _ERA_YEAR.finditer(body):
        if m.group("post"):
            continue
        n = _to_float(m.group("n"))
        if m.group("bc"):
            return (int(-n), f"紀元前{int(n)}年")
        if 1000 <= n <= 2100:
            return (int(n), f"{int(n)}年")
    return None


def timeline_at(lines: list[Line], i: int) -> dict | None:
    """年が3つ以上並ぶところを年表にする。古い順に並べ直す。"""
    marks: list[tuple[int, dict]] = []
    seen: set[int] = set()
    for j in range(i, min(i + 8, len(lines))):
        body = _text(lines[j])
        got = _year(body)
        if not got or got[0] in seen:
            continue
        seen.add(got[0])
        marks.append((got[0], {"year": got[1], "text": _clip(body, 30)}))
    if len(marks) < 3:
        return None
    marks.sort(key=lambda kv: kv[0])
    return {"kind": "timeline", "heading": "分かっている順番",
            "marks": [m for _, m in marks[:4]]}


def scale_at(lines: list[Line], i: int) -> dict | None:
    """同じ単位の量が2つ以上並ぶところを、棒で並べて比べる。"""
    # 1文につき1つだけ取る。「2トンから4トン」は幅であって比較ではなく、
    # 実測で 0.07 と 0.13 のほぼ見えない棒が2本並んだ。幅は rangeBars の受け持ち。
    found: list[tuple[float, str, str]] = []
    unit = ""
    seen: set[float] = set()
    from_lines: set[int] = set()
    for j in range(i, min(i + 8, len(lines))):
        body = _text(lines[j])
        if j in from_lines:
            continue
        # 「1本2トンから4トン」は幅。端の片方だけ取ると値を取り違える。
        # 幅は rangeBars が受け持つ。
        if _RANGE.search(body):
            continue
        for m in _STAT.finditer(body):
            u = m.group("u")
            # 「1本あたり25トン」の「1本」を量として並べると、同じ長さの棒が
            # 2本並ぶだけになる。助数詞と小さい数は比べる対象ではない。
            if u in _NOT_SCALAR or _is_trivial(m.group("v"), u):
                continue
            if unit and u != unit:
                continue
            value = _to_float(m.group("v"))
            if value <= 0 or value in seen:
                continue
            unit = unit or u
            seen.add(value)
            from_lines.add(j)
            found.append((value, f"{m.group('v')}{u}", _clip(body, 26)))
            break  # この文からは1つ
    # 1つの文から2本取ると「10トンから15トンほど」が棒2本になる。あれは幅で
    # あって比較ではない（rangeBars が受け持つ）。別々の文から取れたときだけ。
    if len(found) < 2 or len(from_lines) < 2:
        return None
    top = max(v for v, _, _ in found)
    low = min(v for v, _, _ in found)
    # 差が小さいと棒を並べる意味が無い。実測で「7メートル」と「7.2メートル」が
    # ほぼ同じ長さの棒2本になった。
    if low <= 0 or top / low < MIN_RATIO:
        return None
    bars = [{"label": label, "value": round(v / top, 4), "readout": readout}
            for v, readout, label in found[:4]]
    return {"kind": "scale", "heading": f"{unit}で並べる", "bars": bars}


# 立体にできる形。台本に出てくる語から決める。
_SHAPE = (
    ("pyramid", re.compile(r"ピラミッド|角錐")),
    ("column", re.compile(r"柱|石柱|オベリスク|塔|支柱|モアイ")),
    ("disc", re.compile(r"円盤|円板|歯車|ディスク|皿")),
    ("block", re.compile(r"石|岩|ブロック|直方体|箱|台座|壁")),
)
# 立体に入れる寸法。キロは入れない。実測で「250キロ運ばれた」から
# 高さ250キロの石を立てようとした。あれは距離であって物の寸法ではない。
_LENGTH = ("メートル", "センチ", "ミリ")
# 物の寸法として上限。これを超える値は地形か距離で、立体に載らない。
_MAX_METERS = 500.0
# 比較に置く人の背丈（メートル）
HUMAN_M = 1.7
_DIM_LABEL = (("高さ", re.compile(r"高さ|標高|背丈")),
              ("長さ", re.compile(r"長さ|全長")),
              ("厚さ", re.compile(r"厚さ|厚み")),
              ("直径", re.compile(r"直径|差し渡し")),
              ("幅", re.compile(r"幅")))


def model_at(lines: list[Line], i: int) -> dict | None:
    """寸法の付いた立体を作る。

    参考chは "3D model · 146 m" と出典を添えて自作の立体を出している。
    Commons に動画はほぼ無く（実測で古代遺跡系242点中1点）、素材を探しても
    この画は埋まらない。台本に寸法が書いてあるときだけ作る。
    """
    body = _text(lines[i])
    shape = next((name for name, pat in _SHAPE if pat.search(body)), None)
    if not shape:
        return None
    for m in _STAT.finditer(body):
        u = m.group("u")
        if u not in _LENGTH:
            continue
        value = _to_float(m.group("v"))
        if value <= 0:
            continue
        # 寸法の語が無い数は、その物の大きさとは限らない。既定値を置かない
        label = next((name for name, pat in _DIM_LABEL if pat.search(body)), "")
        if not label:
            continue
        meters = value * {"メートル": 1.0, "センチ": 0.01, "ミリ": 0.001}[u]
        if meters > _MAX_METERS:
            continue
        return {"kind": "model", "heading": "大きさを置いてみる", "shape": shape,
                "dimension": {"label": label, "readout": f"{m.group('v')}{u}",
                              "value": value},
                # 人は物の高さに対する比で置く。固定の大きさで描くと
                # 縮尺の嘘になる。比べる意味が無い大きさでは置かない。
                "humanRatio": (round(HUMAN_M / meters, 4)
                               if 2.0 <= meters <= 200.0 else 0.0),
                "note": "台本の数値から起こした立体（実物の写しではない）"}
    return None


def plan(lines: list[Line], duration: float, *, panel_sec: float = PANEL_SEC,
         gap: float = MIN_GAP_SEC, limit: int = MAX_PANELS,
         per_kind: int = PER_KIND) -> list[dict]:
    """パネルを置く時刻と中身を決める。"""
    lines = sentences(lines)
    out: list[dict] = []
    used: dict[str, int] = {}
    last = -gap
    for i, line in enumerate(lines):
        if len(out) >= limit:
            break
        if line.startSec < last + gap:
            continue
        # 尺の終わりにかかるパネルは切れて読めない
        if line.startSec + panel_sec > duration - 4:
            break
        # 少ない型から先に試す。直前と同じ型は最後に回す
        makers = [("contrast", contrast_at), ("timeline", timeline_at),
                  ("model", model_at), ("scale", scale_at)]
        makers.sort(key=lambda kv: (used.get(kv[0], 0),
                                    kv[0] == (out[-1]["kind"] if out else "")))
        for kind, maker in makers:
            if used.get(kind, 0) >= per_kind:
                continue
            got = maker(lines, i)
            if got:
                out.append({**got, "startSec": round(line.startSec, 3),
                            "durationSec": panel_sec})
                used[kind] = used.get(kind, 0) + 1
                last = line.startSec
                break
    return out


def clear_for_chapters(props: dict) -> dict:
    """章カードに重なる札を外す。

    章カードは画面を覆う。実測で「巨石」の大字が章カードを突き抜けていた。
    字幕は残す（語りは続いている）。
    """
    spans = [(c["startSec"], c["startSec"] + c["durationSec"])
             for c in props.get("chapters") or []]
    if not spans:
        return props
    for key in ("stats", "quoteCards", "chipStacks", "cardRows", "documentCards",
                "portraits", "charts", "timelines", "rangeBars", "glyphs", "grids",
                "telops"):
        props[key] = [
            it for it in (props.get(key) or [])
            if not any(_overlaps(it.get("startSec", 0.0),
                                 it.get("startSec", 0.0) + it.get("durationSec", 0.0),
                                 a, b) for a, b in spans)
        ]
    return props


def clear(props: dict, panels: list[dict],
          keys: tuple[str, ...] = ("stats", "quoteCards", "chipStacks", "cardRows",
                                   "documentCards", "portraits", "charts",
                                   "timelines", "rangeBars", "glyphs", "grids",
                                   "sourceLabels", "telops")) -> dict:
    """パネルに重なる札を外す。

    出典ラベルも外す。写真が見えていないのに帰属を出すと、出所の表示として
    誤りになる。字幕と章カードは残す（語りは続いている）。
    """
    if not panels:
        return props
    spans = [(p["startSec"], p["startSec"] + p["durationSec"]) for p in panels]
    for key in keys:
        items = props.get(key) or []
        props[key] = [
            it for it in items
            if not any(_overlaps(it.get("startSec", 0.0),
                                 it.get("startSec", 0.0) + it.get("durationSec", 0.0),
                                 a, b) for a, b in spans)
        ]
    return props
