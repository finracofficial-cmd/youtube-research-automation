"""台本から、どこに何のオーバーレイを出すかを自動で決める。

台本自身の言い回しが、出すべき部品を示している。修辞の型をそのまま規則にする。

密度について:
参考動画のストーリーボード324フレームを実測したところ、
構造化オーバーレイが載っているフレームは 67%、何も無いフレームは 9% だった
（analysis/reference_edit_density.md）。当初は「出しすぎると読めない」と考えて
1画面1部品・最低間隔1.2秒に絞り、被覆率6.6%しか出ていなかった。
これは設計判断の誤りだったので、ゾーン制に作り替えて密度を上げている。

ゾーン制:
部品は left / right / center / lower / corner のいずれかを占める。
同じゾーンは同時に1つまで。違うゾーンなら同時に出る。
画面全体で同時に出る数は MAX_CONCURRENT までに抑える。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_DURATION = 3.0
MAX_DURATION = 7.5
MAX_CONCURRENT = 3      # 同時に出す部品の上限。これ以上は読めない
ZONE_GAP = 0.4          # 同じゾーンを使い回すまでの最低間隔
MAX_HOLD = 16.0         # 1つの部品を出しっぱなしにできる上限
# 参考chのストーリーボードを取って数え直した値。54コマ中51コマに札が出て
# いた（ヴォイニッチ回4シート、ピラミッド回2シート）。
# 以前ここは 0.67 で「参考動画の実測」と書いてあったが、フレームを見ずに
# 出した数字だった。何も載っていないのは暗転などごく一部しかない。
TARGET_COVERAGE = 0.94

_DECLARATION = re.compile(r"当チャンネル")

_PAPER = re.compile(
    r"(?P<year>[0-9０-９]{4})年[^。]{0,24}?(?P<venue>ネイチャー|サイエンス|"
    r"学術誌|論文|報告書|査読)|(?P<venue2>ネイチャー|サイエンス)[^。]{0,12}?(載|出)")
_QUOTE_LEAD = re.compile(r"(主張|説明|話|結論|言い分|見方)は(こうだ|こうである|こうだった)[。]?$")
_LIST_LEAD = re.compile(r"(?P<n>[0-9０-９一二三四五六七八九]+)\s*(つ|種類|点|件)[^。]{0,8}"
                        r"(に分かれる|を並べた|ある|を挙げ)")
# 「10トンから15トン」のような幅のある量。大書きの数字にすると幅が消え、
# 確定値のように見えてしまう。区間として出す。
_RANGE = re.compile(
    r"(?P<lo>[0-9０-９][0-9０-９,.]*)\s*(?P<u1>トン|メートル|キロ|センチ|個|本|枚|人|年|%|パーセント)?"
    r"\s*(?:から|〜|～|-|–)\s*"
    r"(?P<hi>[0-9０-９][0-9０-９,.]*)\s*(?P<u2>トン|メートル|キロ|センチ|個|本|枚|人|年|%|パーセント)")

_CAVEAT = re.compile(r"^(ただし|とはいえ|もっとも)")
# 留保があると予告するだけで中身を言っていない文。カードに出すと
# 「ただし、と付け加えておきたい」がそのまま画面に載る。
_EMPTY_CAVEAT = re.compile(
    r"^(ただし|とはいえ|もっとも)[、。]?\s*$"
    r"|と(付け加え|断っ|注記し|言っ|added)"
    r"|^(ただし|とはいえ|もっとも)[、]?(である|だ|です)")

# 数値＋単位。大きな数字の単独提示に使う。
# 「紀元前1世紀」の「紀元前」を落とすと2000年ずれた別の事実になるので、
# 接頭辞ごと取り込む。実際に落として誤表示した。
_STAT = re.compile(
    r"(?P<pre>紀元前|前|約|およそ|推定)?\s*"
    r"(?P<v>[0-9０-９][0-9０-９,，.．]*(?:万|億|兆)?)\s*"
    r"(?P<u>年前|トン|メートル|キロ|センチ|ミリ|ボルト|パーセント|％|平方キロ|"
    r"点|本|人|個|倍|枚|冊|回|度|度目|世紀|語|字|ページ)"
    # 後ろに付く限定。落とすと断定になる。実測で台本の「歯車は30個以上」から
    # 「30個」を大書きしていた。「以上」の一語で意味が変わる。
    # 数値の後ろに付く限定。落とすと断定になる。実測で台本の
    # 「歯車は30個以上」から「30個」、「2000字を超える」から「2000字」を
    # 大書きしていた。「を超える」のように助詞を挟む形もある。
    r"(?P<post>以上|以下|超|未満|前後|程度|近く|余り|あまり|ほど|くらい|ぐらい"
    r"|弱|強|を超える|を上回る|を下回る|を割る|を切る|に満たない)?")

# 大書きに値しない小さな数。「2枚の歯車」「1人死亡」を巨大表示すると滑稽になる。
_TRIVIAL_UNITS = {"人", "枚", "本", "個", "点", "回", "冊", "度"}
_TRIVIAL_MAX = 9

# 否定文。「地質学者ではない」から役割を取ると逆の意味になる。実際に取った。
_NEGATION = re.compile(r"(ではない|ではなかった|でもない|とは言えない|わけではない)")

# 組織名。「オスマン帝国の提督ピリ・レイス」から「オスマン」を人名として
# 拾ってしまった。直後がこれらなら組織なので人物ではない。
_ORG_SUFFIX = re.compile(r"^(帝国|王国|王朝|共和国|大学|博物館|図書館|社|軍|教会|会|省|庁|州|島|山|川|海)")
# 割合。チャートの読み値になる
_RATIO = re.compile(r"([0-9０-９]+(?:\.[0-9０-９]+)?)\s*(パーセント|％)")
# 年号。2つ以上あれば推移としてタイムラインにする
_YEAR = re.compile(r"([0-9０-９]{3,4})年")
# 人物。カタカナの氏名か、漢字姓＋敬称なし＋役割語
_PERSON = re.compile(
    r"(?P<name>(?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{3,})|[一-龥]{2,4})"
    r"(?:という|は|が|も)?[^。]{0,10}?"
    r"(?P<role>考古学者|天文学者|数学者|物理学者|言語学者|歴史学者|研究者|教授|"
    r"技師|発明家|提督|探検家|軍人|司祭|作家|記者|学者)")
# 鉤括弧に入った短い語。1文字表示に使う
_GLYPH = re.compile(r"[「『]([^」』]{1,3})[」』]")
# 総量。格子で見せる
_GRID = re.compile(r"([0-9０-９][0-9０-９,，]*)\s*(ページ|枚|字|語|点)[^。]{0,6}(ある|超|に及)")

_KANJI_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}


def _clip(text: str, n: int) -> str:
    """ラベルを詰める。語の途中で切らず、直前の区切りまで戻す。"""
    text = text.rstrip("。")
    if len(text) <= n:
        return text
    cut = text[:n]
    for sep in ("、", "・", " ", "は", "を", "が"):
        i = cut.rfind(sep)
        if i >= n // 2:
            return cut[: i + 1].rstrip("、・ ")
    return cut


# 文頭の接続。カードの見出しに残ると、文の途中を切り出したように読める。
_LEAD = re.compile(r"^(?:だから|つまり|しかし|そして|また|ただし|なお|ところが|"
                   r"それでも|これは|その|この|さらに|やがて|やはり|むしろ)")
# 見出しの末尾に残る助詞。名詞句で止める。
_TAIL = re.compile(r"(?:を|は|が|に|で|と|も|へ|の|から|まで|より)$")


def _stat_label(text: str, start: int, end: int) -> str:
    """数字を含む名詞句を見出しにする。

    文をそのまま切ると、文の途中から始まって助詞で終わる断片になる
    （実測で「だから手元の20枚あまりを」が出た）。文頭の接続を外し、
    数値の直後で切って、末尾の助詞を落とす。
    """
    head = _LEAD.sub("", text[:start].lstrip("　 "))
    # 直前の区切りから後ろだけを見出しにする
    for sep in ("、", "。", "「", "）"):
        if sep in head:
            head = head.rsplit(sep, 1)[1]
    label = _TAIL.sub("", (head + text[start:end]).strip())
    return _clip(label, 22)


def _is_trivial(value: str, unit: str) -> bool:
    """小さすぎて大書きに値しない数かどうか。"""
    if unit not in _TRIVIAL_UNITS:
        return False
    digits = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    digits = digits.replace(",", "").replace("，", "")
    try:
        return float(digits) <= _TRIVIAL_MAX
    except ValueError:
        return False


def _to_float(text: str) -> float:
    t = text.translate(str.maketrans("０１２３４５６７８９", "0123456789")).replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _to_int(text: str) -> int:
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return int(text) if text.isdigit() else _KANJI_NUM.get(text, 0)


@dataclass
class Line:
    startSec: float
    durationSec: float
    text: str


@dataclass
class Cue:
    kind: str
    startSec: float
    durationSec: float
    zone: str = "center"
    payload: dict = field(default_factory=dict)

    @property
    def endSec(self) -> float:
        return self.startSec + self.durationSec


def _window(lines: list[Line], i: int, n: int) -> tuple[float, float]:
    start = lines[i].startSec
    end = lines[min(i + n - 1, len(lines) - 1)]
    span = end.startSec + end.durationSec - start
    return start, max(MIN_DURATION, min(MAX_DURATION, span))


def classify(lines: list[Line]) -> list[Cue]:
    """字幕列から候補キューを拾う。重なりはここでは気にしない。

    1文から複数の部品が出ることを許す。ゾーンが違えば同時に出せるため。
    """
    cues: list[Cue] = []
    # 数値系は件数が多い。1つのゾーンに積むと他が空くので、交互に振り分ける。
    stat_zones = ("right", "corner", "left")
    n_stat = 0
    for i, line in enumerate(lines):
        text = line.text
        if _DECLARATION.search(text):
            continue
        start, dur = _window(lines, i, 2)

        m = _PAPER.search(text)
        if m:
            cues.append(Cue("document", start, dur, "center", {
                "venue": (m.group("venue") or m.group("venue2") or "").strip(),
                "year": m.group("year") or "", "title": text.rstrip("。")}))

        if _QUOTE_LEAD.search(text) and i + 1 < len(lines):
            s2, d2 = _window(lines, i + 1, 2)
            cues.append(Cue("quote", s2, d2, "left", {
                "heading": text.rstrip("。"),
                "translation": " ".join(l.text for l in lines[i+1:i+3]).rstrip("。")}))

        m = _LIST_LEAD.search(text)
        if m:
            n = _to_int(m.group("n"))
            if 2 <= n <= 9:
                cues.append(Cue("cardrow", start, dur, "center",
                                {"count": n, "caption": text.rstrip("。")}))

        # 留保の中身が書かれている文だけ出す。予告だけの文は飛ばす
        if _CAVEAT.search(text) and not _EMPTY_CAVEAT.search(text) and len(text) >= 8:
            cues.append(Cue("caveat", start, dur, "right", {"text": text.rstrip("。")}))

        m = _RATIO.search(text)
        if m:
            pct = float(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
            cues.append(Cue("chart", start, dur, "right", {
                "readout": f"{m.group(1)}{m.group(2)}",
                "series": [1.0, 0.82, 0.55, 0.36, max(0.02, min(1.0, pct / 100))],
                "caption": _clip(text, 28)}))

        years = _YEAR.findall(text)
        if len(years) >= 2:
            cues.append(Cue("timeline", start, dur, "lower", {
                "marks": [{"label": f"{y}年", "active": True} for y in years[:4]]}))

        m = _GRID.search(text)
        if m:
            cues.append(Cue("grid", start, dur, "center", {
                "caption": f"{m.group(1)}{m.group(2)}"}))

        m = _PERSON.search(text)
        if (m and len(m.group("name")) >= 3 and not _NEGATION.search(text)
                and not _ORG_SUFFIX.match(text[m.end("name"):])):
            year = years[0] + "年" if years else ""
            cues.append(Cue("portrait", start, dur, "left", {
                "name": m.group("name"), "role": m.group("role"), "year": year}))

        m = _GLYPH.search(text)
        if m and len(m.group(1)) <= 2:
            cues.append(Cue("glyph", start, min(dur, 4.0), "center",
                            {"glyph": m.group(1), "caption": _clip(text, 24)}))

        ranged = False
        m = _RANGE.search(text)
        if m:
            unit = m.group("u2") or m.group("u1") or ""
            lo, hi = _to_float(m.group("lo")), _to_float(m.group("hi"))
            if hi > lo > 0:
                # 目盛りは下端0、上端を上限の1.3倍にして、区間を中ほどに置く
                top = hi * 1.3
                cues.append(Cue("range", start, dur,
                                stat_zones[n_stat % len(stat_zones)], {
                                    "from": lo / top, "to": hi / top,
                                    "low": f"{m.group('lo')}{unit}",
                                    "high": f"{m.group('hi')}{unit}",
                                    "caption": _stat_label(text, m.start(), m.end())}))
                n_stat += 1
                ranged = True

        # 範囲を出した文で数値カードも出すと、同じ数字が画面に3度並ぶ
        # （範囲バー・数値カード・字幕）。実測でそうなった。
        m = _STAT.search(text)
        if m and not ranged and not _is_trivial(m.group("v"), m.group("u")):
            pre = m.group("pre") or ""
            value = f"{pre}{m.group('v')}{m.group('u')}{m.group('post') or ''}"
            label = _stat_label(text, m.start(), m.end())
            # 数値で始まる文だと、見出しが値と同じ文字列になる。同じ語を
            # 上下に並べても情報が増えないので、そのときは見出しを出さない。
            if label == value:
                label = ""
            cues.append(Cue("stat", start, dur, stat_zones[n_stat % len(stat_zones)],
                            {"value": value,
                             "label": label}))
            n_stat += 1
        elif not ranged and len(re.findall(r"[0-9０-９]+", text)) >= 3:
            cues.append(Cue("chips", start, min(dur, 5.0),
                            stat_zones[n_stat % len(stat_zones)],
                            {"items": re.findall(r"[0-9０-９]+[^\s、。]{0,4}", text)[:3]}))
            n_stat += 1
    return cues


def schedule(cues: list[Cue], max_concurrent: int = MAX_CONCURRENT) -> list[Cue]:
    """ゾーンごとの占有と、同時表示数の上限で絞る。

    同じゾーンは同時に1つまで。違うゾーンなら同時に出す。
    画面全体で MAX_CONCURRENT を超えないようにする。

    中央だけは例外で、他と同時に出さない。中央の部品は画面いっぱいに文字を
    出すので、左右の札と重なる。実測で巨大な「パロ」が「約10メートル」と
    「82トン」の上に乗っていた。
    """
    kept: list[Cue] = []
    zone_free: dict[str, float] = {}
    for cue in sorted(cues, key=lambda c: (c.startSec, c.kind)):
        if cue.startSec < zone_free.get(cue.zone, -1e9):
            continue
        clash = [k for k in kept if k.startSec < cue.endSec and cue.startSec < k.endSec]
        if len(clash) >= max_concurrent:
            continue
        if cue.zone == "center" and clash:
            continue
        if any(k.zone == "center" for k in clash):
            continue
        kept.append(cue)
        zone_free[cue.zone] = cue.endSec + ZONE_GAP
    return kept


def cap_concurrent(cues: list[Cue], max_concurrent: int = MAX_CONCURRENT) -> list[Cue]:
    """出しっぱなしで増えた重なりを、終わりを早めて上限に戻す。

    hold() は同じゾーンの次の部品まで長さを伸ばすが、他のゾーンとの重なりを
    見ていない。実測で4つが同時に出て、画面が埋まっていた。落とすのではなく
    終わりを早める。落とすと、その語が一度も出ないことになる。
    """
    out = sorted(cues, key=lambda c: (c.startSec, c.zone))
    for i, cue in enumerate(out):
        for later in out[i + 1:]:
            if later.startSec >= cue.endSec:
                break
            here = [k for k in out if k.startSec <= later.startSec < k.endSec]
            over = len(here) - max_concurrent
            exclusive = any(k.zone == "center" for k in here) and len(here) > 1
            if over >= 0 or exclusive:
                # 先に出ている方を、後から出る方の手前で切る
                cue.durationSec = max(MIN_DURATION,
                                      round(later.startSec - ZONE_GAP - cue.startSec, 3))
                break
    return out


def hold(cues: list[Cue], duration: float, max_hold: float = MAX_HOLD) -> list[Cue]:
    """各部品を、同じゾーンの次の部品が来るまで出しっぱなしにする。

    1文ぶんで消すと画面が寂しくなる。実物を見ると、パネルは話題が続く間ずっと
    出ていて、次の話題で差し替わっている。被覆率67%はこの持続によるもので、
    部品を機関銃のように出しているわけではない。
    """
    by_zone: dict[str, list[Cue]] = {}
    for c in cues:
        by_zone.setdefault(c.zone, []).append(c)
    for zone, items in by_zone.items():
        items.sort(key=lambda c: c.startSec)
        for i, c in enumerate(items):
            limit = items[i + 1].startSec - ZONE_GAP if i + 1 < len(items) else duration
            c.durationSec = max(c.durationSec,
                                min(max_hold, max(0.0, limit - c.startSec)))
    return cues


def to_props(cues: list[Cue], codes: list[str] | None = None,
             card_labels: list[str] | None = None) -> dict:
    out: dict[str, list] = {
        "quoteCards": [], "chipStacks": [], "cardRows": [], "documentCards": [],
        "stats": [], "portraits": [], "charts": [], "timelines": [], "glyphs": [], "grids": [],
        "telops": [], "rangeBars": [],
    }
    for cue in cues:
        base = {"startSec": round(cue.startSec, 3), "durationSec": round(cue.durationSec, 3)}
        z = {"zone": cue.zone}
        p = cue.payload
        if cue.kind == "telop":
            out["telops"].append({**base, "text": p["text"],
                                  "variant": "plain", "zone": cue.zone})
        elif cue.kind == "document":
            out["documentCards"].append({**base, "venue": f"{p['venue']} {p['year']}".strip(),
                                         "title": p["title"], "badge": "一次資料"})
        elif cue.kind == "quote":
            out["quoteCards"].append({**base, **z, "side": "left",
                                      "heading": p["heading"], "translation": p["translation"]})
        elif cue.kind == "caveat":
            out["quoteCards"].append({**base, **z, "side": "right",
                                      "heading": "留保", "translation": p["text"]})
        elif cue.kind == "chips":
            out["chipStacks"].append({**base, "items": p["items"]})
        elif cue.kind == "cardrow":
            n = p["count"]
            labels = (codes or [])[:n]
            # 番号だけの札は中身が空で、未完成に見える。題材の主張が
            # 分かっていれば語を入れる（実測で「1」「2」と番号だけの
            # 黒い帯が並んでいた）。
            words = (card_labels or [])[:n]
            out["cardRows"].append({**base, "caption": p["caption"], "cards": [
                {"code": labels[i] if i < len(labels) else str(i + 1),
                 "label": words[i] if i < len(words) else "",
                 "dimmed": False}
                for i in range(n)]})
        elif cue.kind == "range":
            out["rangeBars"].append({**base, **z, "from": round(p["from"], 4),
                                     "to": round(p["to"], 4),
                                     "lowLabel": p["low"], "highLabel": p["high"],
                                     "caption": p["caption"]})
        elif cue.kind == "stat":
            out["stats"].append({**base, **z, "value": p["value"], "label": p["label"]})
        elif cue.kind == "portrait":
            out["portraits"].append({**base, **z, "name": p["name"],
                                     "role": p["role"], "year": p["year"]})
        elif cue.kind == "chart":
            out["charts"].append({**base, **z, "series": p["series"],
                                  "readout": p["readout"], "caption": p["caption"]})
        elif cue.kind == "timeline":
            out["timelines"].append({**base, **z, "marks": p["marks"]})
        elif cue.kind == "glyph":
            out["glyphs"].append({**base, **z, "glyph": p["glyph"], "caption": p["caption"]})
        elif cue.kind == "grid":
            out["grids"].append({**base, **z, "cols": 12, "rows": 6,
                                 "filled": 0.62, "caption": p["caption"]})
    return out


# 語句テロップ。ナレーションから切り出した連続部分文字列だけを出す。
_PHRASE = re.compile(
    r"「([^」]{2,16})」"                      # 鉤括弧はそのまま見出しになる
    # 長い複合語を先に試す。「ヴォイニッチ手稿」を「ヴォイニッチ」より優先する。
    # 交替は左から順に試され、先に当たった枝がその位置を消費してしまう。
    r"|((?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{3,})(?:島|山|川|海|人|語|族)?の[一-龥]{2,8})"
    r"|((?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{3,})[一-龥]{2,6})"
    r"|([一-龥]{2,8}(?:文書|手稿|写本|遺跡|神殿|地上絵|王朝|帝国|事件|鉄柱|電池|地図))"
    r"|((?:[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|[ァ-ヶー]{4,}))"
    # 漢字2文字まで受ける。3文字以上に絞っていたら、語句が取れる行が30%
    # しか無く、被覆率がそこで頭打ちになっていた（実測）。「人力」「石柱」
    # 「論文」「氷河」のような2文字語が全部落ちていた。
    r"|([一-龥]{2,6})")

# どの台本にも出るので、出しても情報が増えない語
_FLAT = {"可能性", "研究者", "専門家", "一次資料", "当チャンネル", "説明", "解説",
         "考古学", "実際", "結論", "以上", "以下", "現在", "当時", "重要", "存在",
         "報告", "確認", "指摘", "主張", "記録", "内容", "部分", "場合", "結果",
         "理由", "意味", "必要", "問題", "状態", "関係", "世界", "人間", "時代",
         # 単位。数から切り離して大書きしても何も言っていない
         "メートル", "センチ", "ミリ", "キロ", "グラム", "トン", "パーセント",
         "ボルト", "アンペア", "万年前", "個以上", "観光客", "研究チーム",
         "チャンネル", "当チャンネル", "再利用", "動画",
         # 位置・時点・程度だけを指す語。大書きしても何も言っていない。
         # 漢字2文字を受けるようにしたら一気に出てきた（実測で「場所」
         # 「最後」「近年」「内側」が大字で並んだ）。
         "場所", "地点", "付近", "周辺", "内側", "外側", "上部", "下部",
         "中央", "中心", "一部", "全体", "両側", "片側", "表面", "裏面",
         "最後", "最初", "最大", "最小", "最新", "最古", "近年", "過去",
         "以来", "当初", "今回", "今日", "現地", "現代", "後年", "前後",
         "議論", "検証", "調査", "分析", "検討", "考察", "判断", "評価",
         "候補", "対象", "手法", "方法", "方針", "形式", "種類", "程度",
         "本物", "偽物", "数字", "数値", "値段", "名前", "呼称",
         # 副詞の語幹。「非常に」「当然ながら」の頭だけを大書きしても
         # 語になっていない。漢字2文字を受けた副作用（実測で「非常」）。
         "非常", "相当", "結局", "当然", "絶対", "意外", "単純", "完全",
         "極端", "明確", "正確", "十分", "若干", "多少", "一気", "同時",
         "直接", "間接", "突然", "次第", "一応", "本来", "元来", "従来"}


# 語句の直後に来てよい文字。これ以外が続くなら語の途中で切れている。
# 実測で「比較的新しい」から「比較的新」が出た。漢字の連なりだけを見ると、
# 送り仮名のある語はどこで切っても漢字として成立してしまう。
_BOUNDARY = re.compile(r"[はがをにでとのもやへ、。！？「」（）\s]|という|によ|から|まで|など|だっ|であ|$")


def _ends_cleanly(text: str, end: int) -> bool:
    return bool(_BOUNDARY.match(text[end:end + 3]))


def _starts_cleanly(text: str, start: int) -> bool:
    """語の途中から始まっていないか。

    直前が数字なら、単位や助数詞を数から切り離した断片になる。
    直前が同じ字種（片仮名・漢字）なら、語の途中で切った断片になる。
    実測で「高さ5メートルの石柱。」から「ートルの石柱」が出た。弾いた候補の
    先を1文字進めて探し直すので、その位置から片仮名の途中で当たっていた。
    """
    if start == 0:
        return True
    prev, here = text[start - 1], text[start]
    if re.match(r"[0-9０-９]", prev):
        return False
    for cls in (r"[ァ-ヶー]", r"[一-龥]"):
        if re.match(cls, prev) and re.match(cls, here):
            return False
    return True


def _phrases(text: str) -> list[str]:
    """その行から取り出せる語句を全部返す。

    弾いた候補の範囲は、その先頭の1文字だけ進めてもう一度探す。finditer で
    回すと、弾いた候補がその範囲を食い潰して中の良い語まで消える。実測で
    「高さ5メートルの石柱。」から何も取れなかった。「メートルの石柱」が
    先に当たり、数字始まりで弾かれ、「石柱」を見る機会が無くなっていた。
    """
    out: list[str] = []
    at = 0
    while at < len(text):
        m = _PHRASE.search(text, at)
        if not m:
            break
        got = next((g for g in m.groups() if g), None)
        ok = bool(got) and got not in _FLAT and got in text
        if ok and m.group(1) is None:
            ok = _ends_cleanly(text, m.end()) and _starts_cleanly(text, m.start())
        if ok:
            out.append(got)
            at = m.end()
        else:
            at = m.start() + 1
    return out


def _best(text: str) -> str | None:
    """その行で一番長い語句。freq を渡さないときの選び方。"""
    got = _phrases(text)
    return max(got, key=len) if got else None


def phrase(text: str, freq: dict[str, int] | None = None) -> str | None:
    """その行から、画面に出す語句を選ぶ。

    行の連続部分文字列しか返さない。言い換えたり要約したりすると、
    音声と食い違う余地ができる。逐語なら、少なくとも矛盾はしない。

    freq を渡すと、台本全体で出現回数の少ない語を優先する。長さだけで
    選ぶと、どの行にも出る一般語が大書きされる（実測で「観光客」が出た）。
    """
    if freq is not None:
        got = sorted(_phrases(text), key=lambda w: (freq.get(w, 0), -len(w)))
        return got[0] if got else None
    best = _best(text)
    if best is None or best not in text:  # 念のため。逐語でなければ出さない
        return None
    return best


def fill_gaps(cues: list[Cue], lines: list[Line], duration: float,
              min_gap: float = MIN_DURATION,
              target: float = TARGET_COVERAGE) -> list[Cue]:
    """部品が何も無い時間帯に、語句テロップを置く。

    データ由来の部品は、台本に根拠となる値がある所にしか出せない。
    そこだけ埋めた結果、被覆率は42%で頭打ちになった。参考chは実測94%。
    残りを埋めているのは、参考動画では語りの語句そのものの大字だった。
    逐語なので音声と矛盾せず、密度だけを上げられる。
    """
    # 台本全体での出現回数。どの行にも出る語を大書きしないための重み
    freq: dict[str, int] = {}
    for line in lines:
        for w in set(_phrases(line.text)):
            freq[w] = freq.get(w, 0) + 1

    spans = sorted((c.startSec, c.endSec) for c in cues)
    merged: list[list[float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])

    gaps: list[tuple[float, float]] = []
    at = 0.0
    for a, b in merged:
        if a - at >= min_gap:
            gaps.append((at, a))
        at = max(at, b)
    if duration - at >= min_gap:
        gaps.append((at, duration))

    out = list(cues)
    # 参考chは実測94%。何も載っていないのは暗転などごく一部だけだった。
    filled = coverage(cues, duration) * duration
    budget = max(0.0, target * duration - filled)
    for gs, ge in gaps:
        if budget < min_gap:
            break
        cursor = gs
        while ge - cursor >= min_gap:
            # その時間帯に読まれている行から語句を採る
            here = [l for l in lines
                    if l.startSec < ge and l.startSec + l.durationSec > cursor]
            got = next((w for l in here if (w := phrase(l.text, freq))), None)
            if not got:
                break
            dur = min(MAX_DURATION, ge - cursor)
            dur = min(dur, budget)
            if dur < min_gap:
                break
            # 同じ語を続けて出さない。画面が止まって見える
            if out and out[-1].kind == "telop" and out[-1].payload["text"] == got:
                cursor += dur + ZONE_GAP
                continue
            out.append(Cue(kind="telop", startSec=round(cursor, 3),
                           durationSec=round(dur, 3), zone="upper",
                           payload={"text": got}))
            budget -= dur
            cursor += dur + ZONE_GAP
    return out


def coverage(cues: list[Cue], duration: float) -> float:
    """オーバーレイが載っている時間の割合。参考動画の実測は0.67。"""
    spans = sorted((c.startSec, c.endSec) for c in cues)
    merged: list[list[float]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(e - s for s, e in merged) / duration if duration else 0.0


def build(lines: list[Line], codes: list[str] | None = None,
          duration: float | None = None,
          card_labels: list[str] | None = None) -> dict:
    total = duration or (lines[-1].startSec + lines[-1].durationSec if lines else 0.0)
    cues = cap_concurrent(hold(schedule(classify(lines)), total))
    return to_props(fill_gaps(cues, lines, total), codes, card_labels)
