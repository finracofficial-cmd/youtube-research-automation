"""視聴者を離脱させない仕掛け（装置）の監査。

style.py は文長・話速・数字密度を測る。それは「型から外れていないか」の
検査であって、「見続けられるか」の検査ではない。実際にヴォイニッチの台本は
style の検査に合格していたが、読むと平板だった。原因を参考2本の本文と
突き合わせて数えたところ、無いものがはっきりした。

  装置                参考(ヴォイニッチ52分 / ピラミッド38分)   うちの4本
  語り手の判断 私は〜        0.21 / 0.03 /分                  0.00（4本とも）
  章末の引き では〜のか      0.42 / 0.77 /分                  0.27〜0.55
  留保 ただし               0.19 / 0.53 /分                  0.00〜0.40
  専門語の着地 つまり        0.25 / 0.21 /分                  0.00（ヴォイニッチ）
  反転 だが/しかし           0.53 / 0.26 /分                  1.40（ヴォイニッチ）

反転だけが参考の2.6倍ある。振り子（肯定→反転→再反転→留保）ではなく、
否定の連打になっていた。

ここの数値は analysis/transcripts/ の2本から測った値で、好みではない。
変えるときは測り直すこと（tests/test_devices.py が参考2本を自身の監査に
通している）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .style import split_sentences

# ---- 文の型 ------------------------------------------------------------

# 問いで引く。「?」は参考2本とも0件。「〜のか。」「では〜」で引いている
OPEN = re.compile(r"^では|^じゃあ|^そもそも|のか[。？]$|のだろうか|のか、|どうなのか")
# 語り手の判断。行為の捏造（「私は全部読んだ」）は禁じるので、判断語だけ数える
PRIVATE = re.compile(r"私[はもが].*?(判断|保留|思う|考え|採らない|疑|見る|読む|読ん|数え|測|述べ|言|置いて)")
RESERVE = re.compile(r"ただし|ただ、")
PIVOT = re.compile(r"^(だが|しかし|ところが|それなのに|にもかかわらず)")
LANDING = re.compile(r"^つまり|^要するに|^言い換え|^要は|ようなものだ|に似ている|例えるなら|たとえるなら|身近な|"
                     r"平たく言えば|簡単に言えば|難しそうな名前だが|中身は|と同じである|と同じだ|"
                     r"という粒子|という量|というもの|のことだ|のことである|のことで")
RESET = re.compile(r"ここまでが|ここまでの|ここからが|ここから先")
DEFEAT = re.compile(r"皆敗れ|全員が負け|誰も|誰一人|誰にも|決着していない|決まっていない|入れていない|分かっていない")
# 考察の印。事実と考察を分ける
SPEC_START = re.compile(r"ここからは資料に無い|私の考えだ")
SPEC_END = re.compile(r"ここまでが考察")
# 章末で残る候補を数える
NARROW = re.compile(r"残る(のは|候補)|残った|消えた|潰れた|絞られ|絞れ|消える")

# 伏線と回収
PLANT = re.compile(r"後の章で|最後の章で|最後に扱う|後で扱う|あとで扱う|後ほど|保留にする|保留する|その話は後")
CALLBACK = re.compile(r"章で保留|保留にした|冒頭で|冒頭に|最初に述べ|最初に言っ|先ほどの|さきほどの|冒頭の問い|1章で|序盤で")
# 確かめた結果を先に言う（束ね型の章頭）
VERDICT = re.compile(r"結論から|正しい|当たっている|当たりである|当たっていた|決まっていない|"
                     r"裏が取れ|根拠がない|根拠が無い|根拠を失|正しくない|間違い|半分|跡形|"
                     r"確かめられていない|証明されていない|分かっていない|そのまま当たり|"
                     r"確かに存在|確かにある|一件も出てこない|一つも出てこない|見つからない|論文ではない|"
                     r"確定している|ほぼ確定|判断を保留|決着していない|証拠はない|証拠は無い|証拠がない")
# 「誰が・何年に言い出したか」
ORIGIN = re.compile(r"(最初に|初めて|言い出し|出どころ|出所|発端|起点|由来|起源|始ま)")
YEAR = re.compile(r"(紀元前)?\d{3,4}年")
PERSON = re.compile(r"[ァ-ヶー]{2,}(?:・[ァ-ヶー]{2,})+|(?:氏|博士|教授|大尉|技師|医師|学者|著者|という人物|という男|という女)")
# 出どころが辿れる形。年と、それを残した人・媒体が同じ文にある
PROVENANCE = re.compile(r"書いた|書き残し|記録|手紙|書簡|論文|報告|本に|書物|『|記者会見|出どころ|出所|出典|発表|公表|刊行")

# 専門語。着地（日常の言い換え）が3文以内に無いと、ここで視聴者が落ちる
JARGON = re.compile(
    r"エントロピー|アルゴリズム|標準偏差|ハフマン|LZ77|マルコフ|冗長度|熱ルミネッセンス|"
    r"ミューオン|フーリエ|ベイズ|p値|信頼区間|ジップの法則|n-gram|符号化|ニューラル|"
    r"トランスフォーマー|層序|分光|ライダー|LiDAR|加速器質量分析|同位体比|較正曲線|"
    r"多重アルファベット|条件付き|ヒドゥンマルコフ|隠れマルコフ")

# 水増し。字数を要求されると出る形
ENUM_FILLER = re.compile(r"^(?:[0-9０-９]+|[一二三四五六七八九十])(?:点目|つ目|番目|本目|枚目)[はがも]")


def _norm(s: str) -> str:
    # 語尾を先に落とす。助詞と同じ一括だと「である」の「で」が助詞として先に消え、
    # 「ある」が残って似ていない判定になる（実測で 0.64 < 0.72）。
    s = re.sub(r"[、。「」『』〔〕\s]", "", s)
    s = re.sub(r"(である|だった|であった|だ)$", "", s)
    return re.sub(r"[はがのもをにでと]", "", s)


def _lcs(a: str, b: str) -> int:
    """最長の共通部分文字列の長さ。"""
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _similar(a: str, b: str, drop: tuple[str, ...] = ()) -> bool:
    """同じ事実を言い直しているか。助詞・語尾・題材名を落としたうえで、
    短いほうの8割（8字以上）が共通部分として入っていれば言い直しとみなす。

    文字2連の集合で比べると、「材料は15世紀初頭のものだ」と「物理的に見て
    材料は15世紀初頭のものだ」のように前置きが付いた言い直しを取り逃がす
    （実測で 0.64）。共通の塊そのものを見る。題材名は「ヴォイニッチ手稿」で
    8字あり、これを含むだけで似てしまうので先に落とす。
    """
    x, y = _norm(a), _norm(b)
    for d in drop:
        if d:
            x, y = x.replace(d, ""), y.replace(d, "")
    if not x or not y:
        return False
    return _lcs(x, y) >= max(8, 0.8 * min(len(x), len(y)))


# ---- 参照レンジ -----------------------------------------------------------
# 2本の実測の [小さい方, 大きい方]。下限は小さい方の8割に置く（2本でも幅が
# あるので、どちらかに寄せた台本を落とさないため）。
REFERENCE_PER_MIN = {
    "open":     (0.42, 0.79),
    "private":  (0.03, 0.13),   # 判断だけ数える。「私は」全体なら 0.21
    "reserve":  (0.19, 0.53),
    "pivot":    (0.26, 0.53),
    "landing":  (0.37, 0.49),
    "short":    (0.65, 1.24),   # 6字以下の文。緩急（自動字幕の〔?〕印を外して測り直した値）
}
FLOOR = {k: v[0] * 0.8 for k, v in REFERENCE_PER_MIN.items()}
CEIL_PIVOT = 0.53 * 1.5        # 反転がこれを超えると振り子でなく否定の連打


@dataclass
class ChapterAudit:
    index: int
    n_sentences: int
    hooks_out: bool          # 末尾が次への引きになっている
    verdict_first: bool      # 冒頭4文で結論を言っている
    origin: bool             # 誰が何年に言い出したか
    swings: int              # 立場の切り替わり回数（肯定/反転/留保の交代）
    padding: list[str] = field(default_factory=list)
    unlanded: list[str] = field(default_factory=list)


@dataclass
class Audit:
    minutes: float
    per_min: dict[str, float]
    chapters: list[ChapterAudit]
    plant: bool
    callback: bool
    opening_images: int
    opening_defeat: bool
    subject_free_run: int    # 終盤で題材名が出ない連続文数（一般化の代理）
    unlanded: list[str]
    padding: list[str]
    notes: list[str] = field(default_factory=list)
    chapter_notes: dict[int, list[str]] = field(default_factory=dict)  # 塊番号 -> 指摘
    speculation: bool = False          # 考察が印で囲まれている
    speculation_loose: list[str] = field(default_factory=list)   # 考察の中の、資料に無い数字
    origin_invented: list[str] = field(default_factory=list)     # 資料に無い出どころ（年代・媒体の推測）
    narrowing: int = 0                 # 章末で残る候補を数えた章の数

    @property
    def global_notes(self) -> list[str]:
        """章に紐づかない指摘。書き直しは章単位なので、分けて持つ。"""
        return [n for n in self.notes if not re.match(r"^第\d+章: ", n)]

    @property
    def ok(self) -> bool:
        return not self.notes


LAUNCH = re.compile(r"私と共に|迫っていこう")


def guess_chapters(blocks: list[list[str]]) -> list[int]:
    """本編の章にあたる塊。出発の合図（私と共に〜迫っていこう）の次から、
    末尾の4塊（一般化・回収・条件・CTA）の手前まで。合図が無ければ、
    12文以上ある塊を章とみなす。"""
    start = 0
    for i, b in enumerate(blocks):
        if any(LAUNCH.search(s) for s in b):
            start = i + 1
            break
    end = len(blocks) - 4 if len(blocks) > start + 4 else len(blocks)
    body = list(range(start, end))
    if start == 0:
        body = [i for i in body if len(blocks[i]) >= 12]
    return body


def split_blocks(text: str) -> list[list[str]]:
    """空行で区切った塊ごとに文へ切る。台本は塊=ビートで書かれている。"""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        sents = split_sentences(para.replace("\n", ""))
        if sents:
            out.append(sents)
    return out


def _is_noun_stop(s: str) -> bool:
    """体言止めか。動詞・形容詞・助動詞で終わっていない短い文。"""
    body = s.rstrip("。？！?!")
    if not body or len(body) > 24:
        return False
    return not re.search(r"(だ|である|た|る|う|い|ない|いる|ある|する|なる|です|ます)$", body)


NEGATE = re.compile(r"^(だが|しかし|ところが|それなのに|それでも|にもかかわらず)|否定|食い違|一致しない|"
                    r"見つかっていない|見つからない|出てこない|ではない。$|ない。$|無い。$|ゼロ|違う。$|"
                    r"崩れ|失って|消え|残っていない|書いていない")
AFFIRM = re.compile(r"^(確かに|実際|事実|じつは|本当に)|裏づけ|裏付け|一致する|一致した|残っている|確認でき|"
                    r"正しい|当たって|存在する|実在|本物|ちゃんとあ|付いている|出てくる|ある。$|あった。$|"
                    r"書いている|書き残し|示している|分かっている")


def _stance(s: str) -> str | None:
    """文の立場。反転を先に見る（「ない」で終わる文は肯定語を含んでいても反転）。"""
    if RESERVE.search(s):
        return "留保"
    if NEGATE.search(s):
        return "反転"
    if AFFIRM.search(s):
        return "肯定"
    return None


def _swings(sents: list[str]) -> int:
    last, n = None, 0
    for s in sents:
        st = _stance(s)
        if st and st != last:
            if last is not None:
                n += 1
            last = st
    return n


def unlanded_jargon(sents: list[str], window: int = 5) -> list[str]:
    """一度も言い換えられていない専門語を挙げる。

    参考はエントロピーを最初の1回だけ「スマホの予測変換だ」と言い換え、
    あとは裸で使う。だから出るたびに着地を求めず、どこか1回あればよい。
    """
    landed: set[str] = set()
    seen: list[str] = []
    for i, s in enumerate(sents):
        for m in JARGON.finditer(s):
            term = m.group(0)
            if term not in seen:
                seen.append(term)
            if LANDING.search(s) or any(LANDING.search(t) for t in sents[i + 1:i + 1 + window]):
                landed.add(term)
    return [t for t in seen if t not in landed]


def padding(sents: list[str], subject: str = "") -> list[str]:
    """水増しの形を挙げる。列挙の穴埋めと、言い直しの繰り返し。"""
    drop = (subject, subject[:3] if len(subject) > 3 else "")
    out = []
    run = 0
    for s in sents:
        if ENUM_FILLER.search(s):
            run += 1
            if run == 2:
                out.append(f"列挙の穴埋め: 「{s[:24]}」")
        else:
            run = 0
    # 断片。指示の語をそのまま文にする（「短文。短文。」と書かれた。bench 実測）
    # 参考にも「16年。」「ひりだ。」のような短い文はある。同じ断片が2回以上出るときだけ
    frag_counts: dict[str, int] = {}
    for s in sents:
        k = _norm(s)
        if 1 <= len(k) <= 2:
            frag_counts[k] = frag_counts.get(k, 0) + 1
    for k, n in frag_counts.items():
        if n >= 2:
            out.append(f"断片: 「{k}」×{n}")
    # 同じ短文を穴埋めに使う形（「記録はない。」が1章に5回）。短文を求めると出る
    counts: dict[str, int] = {}
    for s in sents:
        k = _norm(s)
        if 4 <= len(k) <= 10:
            counts[k] = counts.get(k, 0) + 1
    for k, n in counts.items():
        if n >= 3:
            out.append(f"同じ短文の反復×{n}: 「{k}」")
    # 離れた繰り返しは回収（「奴隷なのか。協力的な国民だったのか。」を1章と
    # 9章で言う）なので数えない。8文以内の言い直しだけ水増しとみなす。
    # 短い文の反復（「査読誌には載っていない。」→次の文で広げる）は参考の
    # 手口なので、両方が12字以上あるときだけ見る。
    for i, s in enumerate(sents):
        if len(_norm(s)) < 12:
            continue
        if any(len(_norm(t)) >= 12 and _similar(s, t, drop) for t in sents[max(0, i - 8):i]):
            out.append(f"言い直し: 「{s[:28]}」")
    return out


HOOK = re.compile(r"という説|語られている|そういう説|次の章|次は|もう一人|もう1人|ここからが|ここまでが|"
                  r"では[^。]{0,20}のか|のか。$|どうなのか|^ところが|壁が|なんと|事情が違う|ちゃんとあった|"
                  r"最後の話|保留|そしてプロ|が来る|それなのに")


def _hooks_out(sents: list[str], nxt: list[str] | None = None) -> bool:
    tail = sents[-3:]
    head = (nxt or [])[:3]
    return any(OPEN.search(t) or HOOK.search(t) for t in tail + head)


def speculation_span(text: str) -> str:
    """考察の区間（印の間）。無ければ空。"""
    m0 = SPEC_START.search(text)
    if not m0:
        return ""
    m1 = SPEC_END.search(text, m0.end())
    return text[m0.start(): m1.end()] if m1 else ""


def speculation_numbers(text: str, material: str) -> list[str]:
    """考察の中で使った、資料に無い数字。考察でも数字は作らない。"""
    span = speculation_span(text)
    return unsourced_numbers(span, material) if span else []


def unsourced_numbers(text: str, material: str) -> list[str]:
    """資料に無い数字。裏の取れていない数字を出さないのが番組の約束なので、
    人が最後に見るために列挙する。年と件数を粗く見るだけで、判定はしない。"""
    have = set(re.findall(r"\d+(?:\.\d+)?", material))
    out = []
    for m in re.finditer(r"(紀元前)?(\d+(?:\.\d+)?)(年|人|名|点|枚|個|件|本|冊|通|ページ|メートル|センチ|キロ|トン|%|パーセント|倍|回|種|語|世紀)", text):
        num = m.group(2)
        # 1桁は「1つ」「3段」のような言い回しに多いので見ないが、数えた体の単位
        # （名・人・件・冊・通・回）は見る。「皇帝は1名だけ」と数えていないものを数字にした（実測）
        if num in have or (len(num) == 1 and m.group(3) not in ("名", "人", "件", "冊", "通", "回")):
            continue
        tok = m.group(0)
        if tok not in out:
            out.append(tok)
    return out


def audit(text: str, duration_sec: float, *, subject: str = "",
          kind: str = "bundle", chapter_blocks: list[int] | None = None,
          ours: bool = True) -> Audit:
    """台本を、参考2本から測った装置のレンジに照らす。

    chapter_blocks は本編の章にあたる塊の番号。無ければ、冒頭2塊と末尾4塊を
    除いた真ん中を章とみなす（ビートシートの並びがそうなっている）。
    """
    if duration_sec <= 0:
        raise ValueError("duration_sec must be positive")
    minutes = duration_sec / 60
    blocks = split_blocks(text)
    sents = [s for b in blocks for s in b]
    if not sents:
        raise ValueError("text contains no sentences")

    def rate(p: re.Pattern) -> float:
        return sum(bool(p.search(s)) for s in sents) / minutes

    per_min = {
        "open": rate(OPEN),
        "private": rate(PRIVATE),
        "reserve": rate(RESERVE),
        "pivot": rate(PIVOT),
        "landing": rate(LANDING),
        "short": sum(len(s.rstrip("。")) <= 6 for s in sents) / minutes,
    }

    # 章の切り出し
    if chapter_blocks is None:
        chapter_blocks = guess_chapters(blocks)
    chapters = []
    for k, i in enumerate(chapter_blocks):
        cs = blocks[i]
        nxt = blocks[chapter_blocks[k + 1]] if k + 1 < len(chapter_blocks) else None
        origin = any(YEAR.search(s) and (ORIGIN.search(s) or PERSON.search(s) or PROVENANCE.search(s))
                     for s in cs)
        chapters.append(ChapterAudit(
            index=i, n_sentences=len(cs),
            hooks_out=True if nxt is None else _hooks_out(cs, nxt),
            verdict_first=any(VERDICT.search(s) for s in cs[:10]),
            origin=origin,
            swings=_swings(cs),
            padding=padding(cs, subject),
            unlanded=unlanded_jargon(cs)))

    # 伏線と回収: 前半4割に植えて、後半3割で拾う
    n = len(sents)
    plant = any(PLANT.search(s) for s in sents[: int(n * 0.4)])
    callback = any(CALLBACK.search(s) for s in sents[int(n * 0.7):])

    first = chapter_blocks[0] if chapter_blocks else min(3, len(blocks))
    opening = [s for b in blocks[:max(first, 1)] for s in b]
    opening_images = sum(_is_noun_stop(s) for s in opening[:12])
    opening_defeat = any(DEFEAT.search(s) for s in opening)

    # 一般化: 終盤で題材名が出ない連続文数
    run = best = 0
    aliases = [a for a in (subject, subject[:3] if len(subject) > 3 else "") if a]
    for s in sents[int(n * 0.75):]:
        if aliases and any(a in s for a in aliases):
            run = 0
        else:
            run += 1
            best = max(best, run)

    closing_pad = []
    if chapter_blocks and chapter_blocks[-1] + 1 < len(blocks):
        closing_sents = [s for b in blocks[chapter_blocks[-1] + 1:] for s in b]
        closing_pad = [x for x in padding(closing_sents, subject) if x.startswith("言い直し")]

    spec_span = speculation_span(text)
    narrowing = sum(1 for i in chapter_blocks if any(NARROW.search(x) for x in blocks[i][-5:]))

    a = Audit(minutes=minutes, per_min=per_min, chapters=chapters,
              plant=plant, callback=callback, opening_images=opening_images,
              opening_defeat=opening_defeat, subject_free_run=best,
              unlanded=unlanded_jargon(sents), padding=padding(sents, subject),
              speculation=bool(spec_span), narrowing=narrowing)

    # ---- 指摘 ----
    names = {"open": "章末や節目の問い（では〜のか）", "private": "語り手の判断（私は〜と考える／判断を保留する）",
             "reserve": "留保（ただし）", "landing": "専門語の言い換え（つまり〜のようなものだ）",
             "short": "6字以下の短文"}
    for k, floor in FLOOR.items():
        if k == "pivot":
            continue
        if per_min[k] < floor:
            a.notes.append(f"{names[k]}が {per_min[k]:.2f}/分。参考は {REFERENCE_PER_MIN[k][0]:.2f}〜{REFERENCE_PER_MIN[k][1]:.2f}/分")
    if per_min["pivot"] > CEIL_PIVOT:
        a.notes.append(f"文頭の反転（だが・しかし）が {per_min['pivot']:.2f}/分。参考は最大 0.53/分。"
                       "否定の連打になっている。肯定→反転→留保の振り子にする")
    if len(a.unlanded) >= 3:
        a.notes.append("言い換えの無い専門語: " + "、".join(a.unlanded[:6])
                       + "。5文以内に「つまり〜のようなものだ」で日常語に着地させる")
    if opening_images < 3:
        a.notes.append(f"冒頭の体言止めの具体が {opening_images} 文。画で見せられる具体を3つ並べる")
    if not opening_defeat:
        a.notes.append("冒頭に「挑んだ者は皆敗れた」「決着していない」型の一文が無い")
    if not plant:
        a.notes.append("前半に伏線（「この問いは最後の章で扱う」）が無い")
    if not callback:
        a.notes.append("終盤に回収（「1章で保留にした問いだ」「冒頭で私はこう述べた」）が無い")
    if best < 5:
        a.notes.append(f"終盤で題材を離れた一般化が短い（題材名の出ない連続文が {best}）。"
                       "題材を知らない人にも効く結論を5文以上つづける")
    # 考察の印と「残る候補」は自作台本の型。参考2本には無いので、参考には掛けない
    if ours and not spec_span:
        a.notes.append("考察が無い、または印で囲まれていない（「ここからは資料に無い。私の考えだ。」〜「ここまでが考察だ。」）")
    if ours and chapters and narrowing * 2 < len(chapters):
        a.notes.append(f"章末で残る候補を数えている章が {narrowing}/{len(chapters)}。"
                       "「これでAは消えた。残るのはBとC」で締める")
    if len(closing_pad) >= 2:
        a.notes.append("着地で同じ結論を言い直している: " + " / ".join(closing_pad[:3])
                       + "。回収は「〜と分かった」を1回ずつ、決着していないことは最後に1回")
    # 章ごとの装置。参考も全章では踏んでいない（ピラミッド回で結論先出しは
    # 9章中5章）ので、半数を下回ったときだけ、無い章を名指しする。
    n_ch = len(chapters)
    for c in chapters:
        tag = f"第{chapter_blocks.index(c.index) + 1}章"
        if not c.hooks_out:
            a.chapter_notes.setdefault(c.index, []).append(
                "末尾が次への引きになっていない（問い、または次の説をそのまま提示して終える）")
        if c.n_sentences >= 15 and c.swings < 2:
            a.chapter_notes.setdefault(c.index, []).append(
                f"立場の切り替わりが {c.swings} 回。肯定→反転→留保で少なくとも2回振る")
        # 参考にも1章に1件程度はある（並列の反復）。3件からを水増しとみなす。断片は1つで
        if len(c.padding) >= 3 or any(x.startswith("断片") for x in c.padding):
            a.chapter_notes.setdefault(c.index, []).append("水増し: " + " / ".join(c.padding[:3]))
    if kind == "bundle" and n_ch:
        lacking = [c for c in chapters if not c.verdict_first]
        if len(lacking) > n_ch / 2:
            for c in lacking:
                a.chapter_notes.setdefault(c.index, []).append(
                    "冒頭10文で結論を言っていない（「結論から言う。これは正しい／決まっていない」）")
        lacking = [c for c in chapters if not c.origin]
        if len(lacking) > n_ch / 2:
            for c in lacking:
                a.chapter_notes.setdefault(c.index, []).append(
                    "「誰が・何年に言い出したか」が無い（年と、それを残した人か媒体を同じ文に）")
    for i, ns in a.chapter_notes.items():
        tag = f"第{chapter_blocks.index(i) + 1}章"
        a.notes += [f"{tag}: {n_}" for n_ in ns]
    return a


def report(a: Audit) -> list[str]:
    out = [f"{'装置':<10}{'実測/分':>8}   参考レンジ"]
    for k, (lo, hi) in REFERENCE_PER_MIN.items():
        out.append(f"  {k:<8}{a.per_min[k]:>8.2f}   {lo:.2f}〜{hi:.2f}")
    out.append(f"  伏線 {'有' if a.plant else '無'} / 回収 {'有' if a.callback else '無'}"
               f" / 冒頭の具体 {a.opening_images} / 一般化の連続 {a.subject_free_run}文")
    for i, c in enumerate(a.chapters):
        out.append(f"  第{i+1}章 {c.n_sentences:>3}文  引き{'○' if c.hooks_out else '×'}"
                   f" 結論先{'○' if c.verdict_first else '×'} 出どころ{'○' if c.origin else '×'}"
                   f" 振り{c.swings}")
    return out
