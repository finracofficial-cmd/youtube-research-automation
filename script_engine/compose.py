"""設計図から、塊ごとに台本を書かせて組み立てる。

一気に書かせると初稿は必ず薄く（実測で目標の0.63〜0.72倍）、直しは全文の
書き直しになる。塊ごとに書けば、足りない塊だけ直せる。直す理由も
devices.audit が塊（章）単位で出す。

流れ:
  plan.prompt → LLM → plan.validate     設計図
  塊ごとに write_block                   冒頭 / 各章 / 着地
  devices.audit + style.validate         監査
  指摘のある章だけ rewrite_block          直し（既定2回まで）

LLM の呼び出しは chat(messages) -> str の関数として受け取る。
テストでは偽の chat を渡す。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import devices, plan as planmod
from .style import validate
from .tighten import tighten
from .write import _SYSTEM as STYLE_SYSTEM, CHARS_PER_MIN, clean

Chat = Callable[[list[dict]], str]

# 章ごとに書かせるときも、初稿は薄い。塊が小さいぶん一気書きより外れは
# 小さいが、字数を言わないと短く切った文の分だけ全体が縮む。
BLOCK_INFLATION = 1.1   # 1.25 だと 430字/分（上限410）まで膨らんだ（v4 実測）


@dataclass
class Block:
    key: str            # opening / chapter{i} / closing
    brief: str          # この塊に書く内容（設計図から起こした指示）
    target_chars: int
    text: str = ""
    notes: list[str] = field(default_factory=list)


def _chars(sec: float) -> int:
    return int(sec / 60 * CHARS_PER_MIN * BLOCK_INFLATION)


def _opening_brief(p: planmod.Plan, subject: str, genre: str, claims: list[str]) -> str:
    o = p.opening
    cands = [c for c in p.candidates if c]
    cheap = [str(x) for x in (o.get("cheap_answers") or []) if str(x).strip()]
    lines = [
        "## 冒頭（挨拶も自己紹介もしない。1文目から本題）",
        f"1. 体言止めの一撃: 「{subject}。」",
        f"2. 逆説を1文で: {o.get('paradox', '')}（成り立たないはずのことが成り立っている。数字か物で言う）",
        "3. 異様さの具体を3つ、体言止めで並べる（形容詞でなく、画で見せられる物）:",
    ] + [f"   ・{x}" for x in (o.get("images") or [])[:3]] + [
        f"4. 「挑んだ者は皆敗れた／決着していない」型の一文: {o.get('defeat', '')}",
        f"5. チャンネル宣言（ほぼ固定文）: 「当チャンネルでは、こうした{genre}を、都市伝説として"
        "語るのではなく、論文と一次資料からひも解いていく。」",
        "6. 「いま語られている話には、最初に言い出した人がいる。その名前も、言った年も、記録に残っている。」",
        f"7. 追う問いを一つだけ、はっきり言う: 「いま一番語られているのはこれだ。{p.mystery}」",
        "8. 安易な答えを先に潰す（問いの直後に置く。何について言っているか分かる形で）:"
        + "".join(f"\n   ・「単に{x.rstrip('。')}、というわけではない。」" for x in cheap[:2]),
        (f"9. 答えの候補を全部見せる: 「答えは{len(cands)}つに絞れる。" + "。".join(cands) + "。一つずつ潰していく。」"
         if len(cands) >= 2 else "9. （候補が無いので飛ばす）"),
        "10. 全体の地図: 語られている話を、当たっていたもの → 理由が違うもの → 跡形もなくなるものの順に"
        f"{len(claims)}つ確かめる、と言う。{o.get('map', '')}",
        f"11. 伏線: 「{p.mystery or p.planted_question.get('text', '')}」の答えは最後の章で出す、と先に言う。",
        f"12. 出発の合図（固定文）: 「それでは私と共に、{subject}へと迫っていこう。」",
        "", "検証する主張:"] + [f"  {i}. {c}" for i, c in enumerate(claims, 1)]
    return "\n".join(lines)


_CITE = re.compile(r"〔\s*\d+(?:\s*[,、]\s*\d+)*\s*〕")
_DIGIT = re.compile(r"\d")


def facts_from_material(material: str) -> list[str]:
    """資料の中の、事実として使える行。出典の行と数字入り記述と題材の記述。
    章を書かせるときに番号付きで渡す。番号が無いと、書き手は設計図に圧縮された
    事実しか持たず、細部を作る（v4 実測: 「葉が7枚、茎が17センチ」）。"""
    out: list[str] = []
    in_wiki = False
    for line in material.splitlines():
        t = line.strip()
        if t.startswith("## "):
            in_wiki = "題材の記述" in t
            continue
        if t.startswith("- "):
            out.append(t[2:].strip())
        elif in_wiki and t and not t.startswith(("見た目", "出典と", "#")):
            out.append(t)
    return out


_FACT_HEAD = ["## 使える事実（番号付き）",
              "数字・年・人名を含む文の末尾に、根拠の番号を〔n〕で付ける（例:「1404年から1438年の値だった〔3〕」）。",
              "番号を付けられない数字・年・人名は書かない。事実の題名（英語）は書かない。"]


def facts_block(facts: list[str]) -> str:
    return "\n".join(_FACT_HEAD + [f"〔{i}〕 {f}" for i, f in enumerate(facts, 1)])


def _grams(text: str) -> set[str]:
    t = re.sub(r"[\s、。「」『』（）()〔〕\[\]]", "", text)
    words = set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", text))
    return {t[i:i + 2] for i in range(len(t) - 1)} | words


def facts_for(brief: str, facts: list[str], *, limit: int = 14, describe: int = 8) -> str:
    """章に関係する事実だけを、全体の通し番号のまま渡す。

    全部渡すと1回 4,000〜5,000 トークンで、章ごと・候補ごと・直しごとに
    かかる（1本 15万トークンの大半）。関係の薄い行は読まれもしない。
    題材の記述（短い平文）と出典・数字入り記述は、章の指示との重なりで上位だけ。
    番号を振り直さないので、〔n〕は章をまたいで同じ意味。
    """
    if not facts:
        return ""
    want = _grams(brief)
    desc, scored = [], []
    for i, f in enumerate(facts, 1):
        is_source = bool(re.match(r"^(\d{4}|----)\s", f)) or "http" in f or "[" in f
        (scored if is_source else desc).append((len(want & _grams(f)), i, f))
    scored.sort(key=lambda x: (-x[0], x[1]))
    desc.sort(key=lambda x: (-x[0], x[1]))          # 題材の記述も、関係する上位だけ
    keep = sorted([(i, f) for _, i, f in desc[:describe]] + [(i, f) for _, i, f in scored[:limit]],
                  key=lambda x: x[0])
    return "\n".join(_FACT_HEAD + [f"〔{i}〕 {f}" for i, f in keep])


# 根拠番号を求めない数字: 世紀・章・世（ルドルフ2世）・つ・段・回目 のような言い回し。
# 「15世紀初頭」「1章で保留にした問いだ」「ルドルフ2世」に番号を求めて、章を無駄に
# 書き直していた（実測で1本 2回・約1万トークン）
_NOT_A_FACT = re.compile(r"\d+(?:世紀|章|世|つ|段|回目|番目|人称|次|割)")


def uncited(text: str, claim: str = "") -> list[str]:
    """数字を含むのに根拠番号の無い文。主張文にある数字と言い回しの数字は除く。"""
    known = set(re.findall(r"\d+", claim or ""))
    out = []
    for sent in re.split(r"(?<=[。？！])", text):
        if _CITE.search(sent):
            continue
        body = _NOT_A_FACT.sub("", sent)
        nums = [n for n in re.findall(r"\d+", body) if n not in known]
        if nums and sent.strip():
            out.append(sent.strip()[:30])
    return out


def strip_cites(text: str) -> str:
    return _CITE.sub("", text)


def _known(*parts: str) -> str:
    """不明の項目は書かない。「不明」と渡すと本文に「著者は不明」と書かれる（実測）。"""
    return " / ".join(str(x) for x in parts if str(x or "").strip() and str(x).strip() != "不明")


def _chapter_brief(i: int, c: planmod.Chapter, n: int, p: planmod.Plan) -> str:
    swings = "\n".join(f"   {k+1}. [{s.get('stance')}] {s.get('fact')}" for k, s in enumerate(c.swings))
    numbers = "\n".join(f"   ・{x.get('value')} — 断り: {x.get('caveat', '')}" for x in c.numbers) \
        or "   （資料に数字が無い。数字を作らない。「この数字には断りが要る」も書かない）"
    jargon = "\n".join(f"   ・{j.get('term')} → {j.get('landing')}" for j in c.jargon) or "   （無し）"
    ev = c.evidence or {}
    lines = [
        f"## 第{i}章（全{n}章）: {c.claim}",
        "この順で書く。順番を入れ替えない。事実を並べるだけにしない。文と文の理由を",
        "「なぜか」「ならば」「つまり」「だとすれば」「ここで」でつなぐ。",
        f"0. この章の問い: {c.question or c.claim}。大きな問い「{p.mystery}」のうち、{c.tests or '候補'}を試す。",
        f"1. 通説を、通説の言葉でそのまま言う（「{c.claim}」「そう語られている。」）。",
        f"2. 結論を先に言う: {c.verdict_line}",
        f"3. 何を見れば決まるかを先に言う（「ならば、確かめられる。○○を見ればいい」）: {c.method or c.why}",
        f"4. なぜそう言えるか: {c.why}",
        "5. 誰が・何年に言い出したか: " + (
            _known(c.origin.get('who', ''), c.origin.get('year', ''), c.origin.get('how', ''))
            or ((f"資料に無い。代わりに、いま語られている形をそのまま示す: 「そのうちの一本は、"
                 f"タイトルそのものがこうなっている。{p.told.get(c.claim)}」。"
                 if p.told.get(c.claim) else "資料に無い。")
                + "誰が最初に言い出したかは、記録が見つかっていない、と正直に言う。"
                  "年・年代・媒体（YouTube・ネット記事・書籍・テレビ）で広まった時期を推測して書かない")),
        "6. 振り子。立場ごとに事実を置き、反転は「だが」で、留保は「ただし」で入れる:",
        swings,
        f"7. 証拠（年・場所・誰・何）: {_known(ev.get('year', ''), ev.get('where', ''), ev.get('who', ''), ev.get('what', ''))}",
        "8. 数字と、その数字が何を示し何を示さないか（断り）。数字が無い章では断りの文も書かない:",
        numbers,
        "9. 専門語は出した5文以内に「つまり〜のようなものだ」で着地させる:",
        jargon,
        f"10. 語り手の判断（行為は書かない。判断が要る箇所に1文だけ）: {c.narrator or '（無ければ書かない）'}",
        f"11. 結論の範囲を限定する: {c.scope}",
        f"12. 残る候補を、候補の名前で数える（主張の名前で数えない）: {c.so_far}"
        + (f"（残る候補: {'、'.join(c.remaining)}）" if c.remaining else ""),
        f"13. 最後の1文は次章の問いで終える（「では、〜なのか。」。平叙文で「次は〜を確かめる」としない）: {c.hook_out}",
    ]
    if i == n:
        lines.append(f"※ 最終章。冒頭で「1章で保留にした問いだ」と回収に入る: {p.closing.get('callback', '')}"
                     f"\n※ 答え: {p.closing.get('answer', '')}")
    return "\n".join(lines)


def _closing_brief(p: planmod.Plan, subject: str) -> str:
    cl = p.closing
    sp = cl.get("speculation") or {}
    gen = "\n".join(f"   ・{g}" for g in cl.get("generalization") or [])
    found = "\n".join(f"   ・{f}" for f in cl.get("found") or [])
    openq = "\n".join(f"   ・{q}" for q in cl.get("open_questions") or [])
    reasons = "\n".join(f"   ・{r}" for r in (sp.get("reasons") or []))
    return "\n".join([
        "## 着地（5つの塊を、空行で区切って順に書く）",
        f"### 一般化（題材名を出さずに5文以上つづける。主題: {p.thesis}）",
        gen,
        "### 回収（「〜と分かった」を反復し、最後に「だが〜は分かっていない」で落とす。"
        "章で言った事実だけを繰り返す。ここで新しい事実・年・数字を出さない）",
        f"   答え（候補のどれが残ったか）: {cl.get('answer', '')}",
        found,
        f"   最後の一文: {cl.get('not_found', '')}",
        "   まだ分からないことを、分からないまま置く:",
        openq,
        "### 考察（事実と分ける。印を付ける。数字を作らない）",
        "   最初の文: 「事実はここまでだ。ここからは資料に無い。私の考えだ。」",
        f"   考え: {sp.get('claim', '')}",
        "   理由:",
        reasons,
        f"   崩れる条件: {sp.get('weakness', '')}",
        "   最後の文: 「ここまでが考察だ。」",
        f"### 条件の提示（願望でなく条件）: {cl.get('condition', '')}",
        f"   そして冒頭に戻る: {cl.get('opening_callback', '')}",
        "### CTA（ここだけ敬体）",
        "   この動画で参照した論文やデータは誰でも見られること、概要欄に一次資料のリンクがあること、",
        "   調べてほしい題材の募集、を敬体で3〜4文。",
    ])


NO_SOURCE_NOTE = ("※ この主張には当たれる一次資料が無い。埋めない。短く書き、無いことを具体で言って"
                  "結論にする（別の題材の例: 「宮廷の台帳にも、契約書にも、この本は出てこない」）。"
                  "この注意書きの言葉をそのまま本文に写さない。「記録は無い」を言い換えて"
                  "繰り返さない（1回で足りる）。")


def chapter_shares(weights: list[float]) -> list[float]:
    """章の尺を資料の厚みで配る。等分すると、資料の無い章を「記録は無い」の
    言い換えで埋める（v4 実測: 第5章61文のうち十数文が同じ意味）。参考も章の長さは
    47〜88文と揺れている。薄い章は平均の6割、厚い章は1.5倍まで。"""
    if not weights:
        return []
    mean = sum(weights) / len(weights)
    clipped = [min(max(w, mean * 0.6), mean * 1.5) for w in weights]
    total = sum(clipped)
    return [w / total for w in clipped]


def hints_for_shots(p: planmod.Plan) -> list[list[str]]:
    """章ごとの、画を探す手がかり。証拠の場所・人・物と専門語と具体の画。
    台本が題材名ばかりだと検索語が1つに潰れて同じ画が続く（実測: 死海文書）。"""
    out: list[list[str]] = []
    for c in p.chapters:
        ev = c.evidence or {}
        h = [str(ev.get(k) or "") for k in ("where", "who", "what")]
        h += [str(j.get("term") or "") for j in c.jargon]
        h += [str(s.get("fact") or "")[:40] for s in c.swings[:2]]
        out.append([x for x in h if x and x != "不明"])
    return out


def blocks_from_plan(p: planmod.Plan, *, subject: str, genre: str, claims: list[str],
                     duration_sec: float, weights: list[float] | None = None) -> list[Block]:
    """設計図を、書かせる塊の列にする。尺は参考の比率で配る。

    冒頭 4.0% / 着地 11.5% / 残りを章で割る（束ね型の実測）。
    weights は章ごとの資料の厚み（出典の数など）。無ければ等分。
    """
    n = len(p.chapters)
    open_sec = duration_sec * 0.040
    close_sec = duration_sec * 0.115
    body = duration_sec - open_sec - close_sec
    weights = list(weights) if weights and len(weights) == n else [1.0] * n
    shares = chapter_shares([1.0 + w for w in weights])
    out = [Block("opening", _opening_brief(p, subject, genre, claims), _chars(open_sec))]
    for i, c in enumerate(p.chapters, 1):
        brief = _chapter_brief(i, c, n, p)
        if weights[i - 1] <= 0:
            brief += "\n" + NO_SOURCE_NOTE
        out.append(Block(f"chapter{i}", brief, _chars(body * shares[i - 1])))
    out.append(Block("closing", _closing_brief(p, subject), _chars(close_sec)))
    return out


_BLOCK_RULES = """\
この塊だけを書く。前後の塊は別に書くので、ここで全体を締めない。
段落は空行で区切る。章は1つの段落にまとめる（着地だけ5段落）。
指示の番号や見出しは書かない。読み上げる文だけを書く。
同じ意味の文を言い換えて繰り返さない。「記録はない」「証拠は無い」「決まっていない」は
塊に1回ずつで足りる。同じ結論を章の中で3回言わない。
専門語（統計・化学・年代測定の用語）を出したら、5文以内に「つまり〜のことだ」で日常語に
着地させる。日常語（署名・著作・手稿・記録）は説明しない。
反転の接続は「だが」だけに寄せない。「ところが」「それなのに」「一方で」「実際には」を混ぜ、
文頭の「だが」は塊に2回まで。
指示に無い項目は書かない。数字は指示にあるものだけを使い、作らない。
「否定した論者は1人」のように、数えたわけではないものを数字にしない。
論文の著者に触れるのは、指示に名前があるときだけ。無ければ「著者は不明」とも
「著者は特定できていない」とも書かず、「1928年の資料」のように年と種別で指す。
英語の人名は片仮名で書く（Manly → マンリー、Brumbaugh → ブラムボー）。読み上げるため。"""


_ADVERSATIVE = re.compile(r"^(だが|しかし|ところが|それなのに|にもかかわらず)[、]?")
_LANDING = re.compile(r"^(つまり|要するに)[、]?")


def thin_connectives(text: str, *, keep_adversative: int = 3, keep_landing: int = 4) -> str:
    """文頭の逆接と「つまり」を、章ごとに上限まで間引く。

    書き直しを頼んでも減らない（v3 0.93/分、v4 1.00/分。参考は最大0.53）。
    逆接の接続詞は省いても文は成立し、対比は残る。参考も「語はある。
    意味が違う。」と接続詞なしで対比する。上限を超えたぶんは接続詞だけ落とす。
    """
    out = []
    n_adv = n_land = 0
    for sent in re.split(r"(?<=[。？！])", text):
        m = _ADVERSATIVE.match(sent)
        if m:
            n_adv += 1
            if n_adv > keep_adversative:
                sent = sent[m.end():]
        m = _LANDING.match(sent)
        if m:
            n_land += 1
            if n_land > keep_landing:
                sent = sent[m.end():]
        out.append(sent)
    return "".join(out)


def _fold(key: str, text: str) -> str:
    """章は1段落に畳む。指示しても段落を分けてくる（実測で第1章が7段落）。
    段落=章として監査するので、ここで確実に畳む。冒頭と着地は段落のまま。"""
    if not key.startswith("chapter"):
        return text
    text = "\n".join(l for l in text.splitlines() if l.strip())
    return thin_connectives(dedupe_adjacent(text))


def write_block(b: Block, previous_tail: str, chat: Chat, facts: str = "") -> str:
    """1塊を書かせる。直前の塊の末尾を渡して、つなぎを合わせる。
    facts（番号付きの資料）を渡すと、数字の文に根拠番号を付けさせる。"""
    messages = [
        {"role": "system", "content": STYLE_SYSTEM + "\n\n" + _BLOCK_RULES},
        {"role": "user", "content":
         (f"直前の塊の末尾:\n{previous_tail}\n\n" if previous_tail else "")
         + b.brief
         + (f"\n\n{facts}" if facts else "")
         + f"\n\n## 分量\n{b.target_chars:,}字まで。上限であって目標ではない。"
         "事実が尽きたら、そこで塊を終える。言い換え・要約・同じ結論の再掲で埋めない。"
         "1文に1つ、新しい事実か判断を置く。"},
    ]
    return _fold(b.key, tighten(clean(chat(messages))))


_ORIGIN_GUESS = re.compile(r"(\d{4}年代?|YouTube|ネット記事|SNS|テレビ|新聞|書籍|雑誌)[^。]{0,20}(広まっ|言い出し|始ま|由来|出所|発端)")


def origin_invented(text: str, c: planmod.Chapter) -> list[str]:
    """出どころが資料に無いのに、年代や媒体を付けて出どころを書いた文。

    「バチカン隠蔽説は、2000年代のYouTubeやネット記事で広まった」と書いた（実測）。
    資料には無い。数字の検査（unsourced_numbers）は年代の「2000年代」を拾えず、
    媒体は数字ですらない。設計図の origin が空の章では、この形の文を指摘する。"""
    o = c.origin or {}
    if any(str(o.get(k) or "").strip() not in ("", "不明") for k in ("who", "year")):
        return []
    return [m.group(0)[:30] for m in _ORIGIN_GUESS.finditer(text.replace("\n", ""))]


def chapter_score(text: str, *, material: str, target_chars: int, subject: str = "") -> float:
    """章の候補を選ぶ物差し。装置があるほど高く、嘘と水増しがあるほど低い。
    人の好みではなく devices の検出を点にしただけ。"""
    sents = devices.split_sentences(text.replace("\n", ""))
    if not sents:
        return -99.0
    pts = 0.0
    pts += 2.0 if any(devices.VERDICT.search(x) for x in sents[:10]) else 0.0
    pts += 2.0 if devices._hooks_out(sents) else 0.0
    pts += 1.0 if any(devices.YEAR.search(x) and (devices.ORIGIN.search(x) or devices.PERSON.search(x)
                                                    or devices.PROVENANCE.search(x)) for x in sents) else 0.0
    pts += 1.0 if devices._swings(sents) >= 2 else 0.0
    pts += 0.5 if any(devices.PRIVATE.search(x) for x in sents) else 0.0
    pts += 0.5 if any(devices.RESERVE.search(x) for x in sents) else 0.0
    pts -= 1.0 * len(devices.padding(sents, subject))
    pts -= 2.0 * len(devices.unsourced_numbers(text, material)) if material else 0.0
    pts -= 1.0 * len(devices.unlanded_jargon(sents))
    pts -= 1.0 * len(uncited(text)) if _CITE.search(text) or material else 0.0
    n_chars = sum(len(x) for x in sents)
    avg = n_chars / len(sents)
    if not 17.0 <= avg <= 26.0:
        pts -= 1.0
    if n_chars > target_chars * 1.15:
        pts -= 2.0
    if n_chars < target_chars * 0.35:
        pts -= 1.0
    adv = sum(bool(devices.PIVOT.search(x)) for x in sents)
    pts -= max(0, adv - 3) * 0.5
    return pts


def opening_score(text: str) -> float:
    sents = devices.split_sentences(text.replace("\n", ""))
    pts = float(sum(devices._is_noun_stop(x) for x in sents[:12]))
    pts += 2.0 if any(devices.DEFEAT.search(x) for x in sents) else 0.0
    pts += 2.0 if any(devices.PLANT.search(x) for x in sents) else 0.0
    pts += 1.0 if any(devices.LAUNCH.search(x) for x in sents) else 0.0
    return pts


def closing_score(text: str, subject: str) -> float:
    sents = devices.split_sentences(text.replace("\n", ""))
    pts = 2.0 if any(devices.CALLBACK.search(x) for x in sents) else 0.0
    run = best = 0
    for x in sents:
        if subject and subject in x:
            run = 0
        else:
            run += 1
            best = max(best, run)
    pts += min(best, 8) * 0.25
    pts += 1.0 if any(re.search(r"と分かった", x) for x in sents) else 0.0
    return pts


def rewrite_block(b: Block, previous_tail: str, chat: Chat, facts: str = "") -> str:
    messages = [
        {"role": "system", "content": STYLE_SYSTEM + "\n\n" + _BLOCK_RULES},
        {"role": "user", "content":
         (f"直前の塊の末尾:\n{previous_tail}\n\n" if previous_tail else "")
         + b.brief + (f"\n\n{facts}" if facts else "")},
        {"role": "assistant", "content": b.text},
        {"role": "user", "content":
         "この塊は参考動画の実測から外れている。内容と事実は変えず、指摘された点だけ"
         "直した全文を出す。\n\n" + "\n".join(f"- {n}" for n in b.notes)
         + f"\n\n{b.target_chars:,}字を超えない。短くなるぶんは構わない。"},
    ]
    return _fold(b.key, tighten(clean(chat(messages))))


def assemble(blocks: list[Block]) -> str:
    return "\n\n".join(strip_cites(b.text).strip() for b in blocks if b.text.strip()) + "\n"


def _tail(text: str, n: int = 3) -> str:
    sents = [s for s in re.split(r"(?<=[。？！])", text.strip()) if s.strip()]
    return "".join(sents[-n:])


def paragraph_index(blocks: list[Block], key: str) -> int | None:
    """組み立てた台本の中で、この塊が先頭から何番目の段落かを数える。
    章は1段落、冒頭は複数段落、着地は4段落なので、段落数を足していく。"""
    pos = 0
    for b in blocks:
        n = len([p for p in re.split(r"\n\s*\n", b.text.strip()) if p.strip()])
        if b.key == key:
            return pos if n else None
        pos += n
    return None


# 「これ以上は2本目を作らない」点。章は結論(2)+引き(2)+出どころ(1)+振り子(1) の7点満点で4点、
# 冒頭は具体3つ+皆敗れた(2) で5点、着地は一般化の連続文で1.5点
_ENOUGH = {"chapter": 4.0, "opening": 5.0, "closing": 1.5}


def _score(b: Block, text: str, material: str, subject: str) -> float:
    if b.key == "opening":
        return opening_score(text)
    if b.key == "closing":
        return closing_score(text, subject)
    return chapter_score(text, material=material, target_chars=b.target_chars, subject=subject)


def _pick(b: Block, texts: list[str], *, material: str, subject: str) -> str:
    """候補の中から、装置の点がいちばん高いものを採る。"""
    if len(texts) == 1:
        return texts[0]
    return max(texts, key=lambda t: _score(b, t, material, subject))


def _sents(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[。？！])", text.replace("\n", "")) if x.strip()]


def _insert_after(text: str, pattern: re.Pattern, line: str, *, default: int = 1) -> str:
    """pattern に当たる最初の文の直後に line を入れる。章は1行で返ってくることがある
    ので、行ではなく文で数える（行で数えたら結論が章の最後に入った。実測）。"""
    sents = _sents(text)
    at = next((i + 1 for i, x in enumerate(sents) if pattern.search(x)), min(default, len(sents)))
    sents.insert(at, line)
    return "\n".join(sents)


_VOICED = re.compile(r"そう語られて|そう言われて|語られてきた")


def ensure_told(text: str, title: str) -> str:
    """出どころが資料に無い章で、その主張の元になった動画タイトルを示す。

    参考chのピラミッド回「そのうちの一本は、タイトルそのものがこうなっている。」と同じ手。
    書き手の決まり（出典の題名を本文に書かない）がこの指示を打ち消すので、機械的に置く。"""
    title = (title or "").strip()
    if not title or "タイトルそのもの" in text:
        return text
    # 読み上げる形に。「！」「？」「…」で文が割れて、字幕が「「死海文書最大の謎！」になった
    spoken = re.sub(r"[！!？?…]+", "、", title).strip("、 　「」") + "。"
    line = "そのうちの一本は、タイトルそのものがこうなっている。\n" + spoken
    return _insert_after(text, _VOICED, line)


def drop_invented_origins(text: str, c: planmod.Chapter) -> str:
    """設計図に出どころが無い章で、年代・媒体を付けた出どころの文を消す。
    消したところに「記録が見つかっていない」が無ければ、1回だけ置く。"""
    if not origin_invented(text, c):
        return text
    out, placed = [], "記録が見つかっていない" in text
    for x in _sents(text):
        if _ORIGIN_GUESS.search(x):
            if not placed:
                out.append("誰が最初に言い出したかは、記録が見つかっていない。")
                placed = True
            continue
        out.append(x)
    return "\n".join(out)


_QUESTION = re.compile(r"(のか|だろうか|か)[。？?]$")


def ensure_hook(text: str, hook: str) -> str:
    """章の最後の2文に問いが無ければ、設計図の引き（問い）で締める。"""
    hook = (hook or "").strip()
    sents = _sents(text)
    if not hook or not _QUESTION.search(hook) or any(_QUESTION.search(x) for x in sents[-2:]):
        return text
    return "\n".join(sents + [hook if hook.endswith(("。", "？", "?")) else hook + "。"])


def ensure_plant(text: str, planted: str) -> str:
    """冒頭に伏線が無ければ、出発の合図の文の直前に入れる。

    設計図には必ずあるのに、3本に1本は書き手が落とす（bench 実測）。伏線と回収は
    対で初めて効く装置なので、書き手の気分に任せず機械的に置く。"""
    if not planted or any(devices.PLANT.search(x) for x in _sents(text)):
        return text
    line = f"{planted.rstrip('。？?')}。この問いは最後の章で扱う。"
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    for i, q in enumerate(paras):
        if devices.LAUNCH.search(q):
            sents = _sents(q)
            k = next(j for j, x in enumerate(sents) if devices.LAUNCH.search(x))
            if k == 0:
                paras.insert(i, line)
            else:
                paras[i] = "\n".join(sents[:k] + [line] + sents[k:])
            return "\n\n".join(paras)
    return text.rstrip() + "\n\n" + line


def ensure_callback(text: str, planted: str, answer: str) -> str:
    """最終章に回収が無ければ、章の頭に置く（参考も最終章の頭で拾う。
    ピラミッド回: 「1章で、三つの選択肢を並べた。」）。"""
    if not planted or any(devices.CALLBACK.search(x) for x in devices.split_sentences(text.replace("\n", ""))):
        return text
    line = f"1章で保留にした問いだ。{planted.rstrip('。？?')}。{answer.strip()}"
    return line + "\n" + text.lstrip()


def ensure_speculation(text: str, sp: dict) -> str:
    """着地の考察を、印で囲まれた形にする。無ければ設計図から作って条件の段落の前に置く。

    考察は視聴者が求める「解決」の代わりになる。事実と混ざると番組の約束が
    崩れるので、印（ここからは資料に無い／ここまでが考察だ）で必ず囲む。"""
    claim = str(sp.get("claim") or "").strip()
    if not claim:
        return text
    if devices.SPEC_START.search(text):
        if not devices.SPEC_END.search(text):
            # 印の始まりがある段落の末尾に閉じを足す
            paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
            for k, q in enumerate(paras):
                if devices.SPEC_START.search(q):
                    paras[k] = q.rstrip() + "\nここまでが考察だ。"
                    break
            return "\n\n".join(paras)
        return text
    reasons = [str(r).strip().rstrip("。") for r in (sp.get("reasons") or []) if str(r).strip()]
    weak = str(sp.get("weakness") or "").strip().rstrip("。")
    para = "\n".join(["事実はここまでだ。ここからは資料に無い。私の考えだ。",
                      claim.rstrip("。") + "。"]
                     + [f"{r}。" for r in reasons[:3]]
                     + ([f"ただし、{weak}なら、この考えは崩れる。"] if weak else [])
                     + ["ここまでが考察だ。"])
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    # 条件の段落（最後から2番目）の前。段落が少なければ末尾の1つ前
    at = max(0, len(paras) - 2)
    paras.insert(at, para)
    return "\n\n".join(paras)


def dedupe_adjacent(text: str, window: int = 3) -> str:
    """直前3文と同じ文を落とす。「結論から言う。Xである。Xである。」と書いた（実測）。"""
    out: list[str] = []
    recent: list[str] = []
    for sent in re.split(r"(?<=[。？！])", text):
        key = devices._norm(sent)
        if key and key in recent:
            continue
        out.append(sent)
        if key:
            recent.append(key)
            recent = recent[-window:]
    return "".join(out)


def ensure_verdict(text: str, verdict_line: str) -> str:
    """章の冒頭10文に結論が無ければ、通説を言わせた直後に置く。

    束ね型の章は「通説→結論→なぜ」の順が型で、参考は9章中6章がそう。
    書き手は3本中で 1〜3章しか守らない（bench 実測）。設計図の verdict_line は
    形の検査を通っているので、機械的に置いてよい。"""
    if not verdict_line.strip():
        return text
    if any(devices.VERDICT.search(x) for x in _sents(text)[:10]):
        return text
    line = "結論から言う。" + verdict_line.strip().rstrip("。") + "。"
    return _insert_after(text, _VOICED, line)

def _claim_of(b: Block, p: planmod.Plan) -> str:
    i = int(b.key[len("chapter"):]) - 1 if b.key.startswith("chapter") else -1
    return p.chapters[i].claim if 0 <= i < len(p.chapters) else ""


def _guarantee(b: Block, p: planmod.Plan, planted: str, answer: str) -> str:
    """書き手が落としがちな装置を、塊ごとに機械的に置く。"""
    if b.key == "opening":
        return ensure_plant(b.text, planted)
    if b.key.startswith("chapter"):
        i = int(b.key[len("chapter"):]) - 1
        if i >= len(p.chapters):
            return b.text
        c = p.chapters[i]
        text = ensure_verdict(b.text, c.verdict_line)
        o = c.origin or {}
        if not any(str(o.get(k) or "").strip() not in ("", "不明") for k in ("who", "year")):
            text = ensure_told(text, p.told.get(c.claim, ""))
        text = drop_invented_origins(text, c)
        if i == len(p.chapters) - 1:
            text = ensure_callback(text, planted, answer)
        else:
            text = ensure_hook(text, c.hook_out)
        return text
    if b.key == "closing":
        return ensure_speculation(b.text, p.closing.get("speculation") or {})
    return b.text


def compose(p: planmod.Plan, *, subject: str, genre: str, claims: list[str],
            duration_sec: float, chat: Chat, rounds: int = 2,
            kind: str = "bundle", material: str = "",
            weights: list[float] | None = None, candidates: int = 1,
            cite: bool = True) -> tuple[str, devices.Audit, list[str]]:
    """設計図から台本を書き、監査して、外れた章だけ直す。

    material を渡すと、資料に無い数字を章の指摘にして消させる。cite なら
    資料を番号付きで章に渡し、数字の文に根拠番号を付けさせる（採るときに剥がす）。
    candidates が2以上なら塊ごとに候補を作り、装置の点で選ぶ。
    戻り値は (台本, 最後の監査, 残った指摘)。
    """
    blocks = blocks_from_plan(p, subject=subject, genre=genre, claims=claims,
                              duration_sec=duration_sec, weights=weights)
    all_facts = facts_from_material(material) if (cite and material) else []
    facts = facts_block(all_facts) if all_facts else ""
    tail = ""
    planted = str(p.planted_question.get("text") or "")
    answer = str(p.closing.get("callback") or "")
    for b in blocks:
        f = facts_for(b.brief, all_facts) if (all_facts and b.key.startswith("chapter")) else ""
        # 候補は必要なときだけ。1本目が閾値を超えていれば2本目は作らない
        # （常に2本作ると章の呼び出しが倍になる。bench では選択の効果は構造より小さかった）
        texts = [write_block(b, tail, chat, f)]
        while len(texts) < max(1, candidates) and _score(b, texts[-1], material, subject) < _ENOUGH.get(b.key[:7], 4.0):
            texts.append(write_block(b, tail, chat, f))
        b.text = _pick(b, texts, material=material, subject=subject)
        b.text = _guarantee(b, p, planted, answer)
        tail = _tail(strip_cites(b.text))

    left: list[str] = []
    audit = None
    for r in range(rounds + 1):
        text = assemble(blocks)
        chapter_idx = [i for i in (paragraph_index(blocks, b.key) for b in blocks
                                   if b.key.startswith("chapter")) if i is not None]
        audit = devices.audit(text, duration_sec, subject=subject, kind=kind,
                              chapter_blocks=chapter_idx or None)
        style = validate(text, duration_sec)
        loose = {b.key: devices.unsourced_numbers(strip_cites(b.text), material)
                 for b in blocks if material}
        loose_notes = [f"{k}: 資料に無い数字 " + "、".join(v) for k, v in loose.items() if v]
        bare = {b.key: uncited(b.text, _claim_of(b, p)) for b in blocks
                if all_facts and b.key.startswith("chapter")}
        made_up = {b.key: origin_invented(b.text, p.chapters[int(b.key[7:]) - 1])
                   for b in blocks if b.key.startswith("chapter") and int(b.key[7:]) - 1 < len(p.chapters)}
        made_up_notes = [f"{k}: 資料に無い出どころ " + " / ".join(v) for k, v in made_up.items() if v]
        bare_notes = [f"{k}: 根拠番号の無い数字の文 " + " / ".join(v[:3]) for k, v in bare.items() if v]
        left = list(audit.notes) + list(style.violations) + loose_notes + bare_notes + made_up_notes
        if not left or r == rounds:
            break
        route(blocks, audit, list(style.violations))
        for b in blocks:
            if loose.get(b.key):
                b.notes.append("資料に無い数字を消すか、資料にある数字に置き換える: "
                               + "、".join(loose[b.key]) + "。数字を作らない")
            if bare.get(b.key):
                b.notes.append("数字を含む文に根拠番号〔n〕が無い。番号を付けるか、その文を消す: "
                               + " / ".join(bare[b.key][:3]))
            if made_up.get(b.key):
                b.notes.append("出どころ（年代・媒体）は資料に無い。消して「誰が最初に言い出したかは、"
                               "記録が見つかっていない」にする: " + " / ".join(made_up[b.key][:2]))
        prev = ""
        for b in blocks:
            if b.notes:
                f = facts_for(b.brief, all_facts) if (all_facts and b.key.startswith("chapter")) else ""
                b.text = rewrite_block(b, prev, chat, f)
                b.text = _guarantee(b, p, planted, answer)
            prev = _tail(strip_cites(b.text))
    return assemble(blocks), audit, left


# 全体の指摘をどの塊に渡すか。装置は住んでいる場所が決まっている
_TO_OPENING = re.compile(r"冒頭|伏線")
_TO_CLOSING = re.compile(r"回収|一般化")
# 書き直しの引き金にしない指摘。率（私は・ただし・つまり・短文・逆接）は書き直しても
# 揃わない（bench 実測）。話速と文の密度と数字の密度は資料の厚みで決まる。
# これらで全章を書き直すと、1回の直しで章の呼び出しが5回増える。報告だけにする
_REPORT_ONLY = re.compile(r"/分。参考は|文頭の反転|6字以下|話速|文の密度|数字 [0-9.]+個/分")


def route(blocks: list[Block], audit: devices.Audit, style_notes: list[str]) -> None:
    """指摘を塊に配る。章の指摘はその章へ。率の不足は章へ（冒頭と着地は
    固定文が多く、そこで数を稼ぐと型が崩れる）。冒頭・着地の装置は各々へ。"""
    for b in blocks:
        b.notes = []
    by_para = {paragraph_index(blocks, b.key): b for b in blocks if b.key.startswith("chapter")}
    for idx, notes in audit.chapter_notes.items():
        if idx in by_para:
            by_para[idx].notes += notes
    chapters = [b for b in blocks if b.key.startswith("chapter")]
    for n in audit.global_notes + style_notes:
        if _REPORT_ONLY.search(n):
            continue
        if _TO_OPENING.search(n):
            blocks[0].notes.append(n)
        elif _TO_CLOSING.search(n):
            blocks[-1].notes.append(n)
        else:
            for b in chapters:
                b.notes.append(n)
