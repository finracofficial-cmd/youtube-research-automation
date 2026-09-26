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

from . import devices, plan as planmod, readability
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


def spoken_title(title: str) -> str:
    """動画タイトルを読み上げる形に。「！」「？」「…」で文が割れて、字幕が
    「「死海文書最大の謎！」になった（実測）。記号は読点にして、括弧で囲む。"""
    t = re.sub(r"[！!？?…]+", "、", (title or "").strip()).strip("、 　「」『』")
    t = re.sub(r"[「」『』【】]", "", t)
    return f"「{t}」。" if t else ""


def _opening_brief(p: planmod.Plan, subject: str, genre: str, claims: list[str]) -> str:
    o = p.opening
    titles = [spoken_title(t) for t in p.told[:2] if spoken_title(t)]
    lines = [
        "## 冒頭（挨拶も自己紹介もしない。1文目から本題）",
        "初めて見る人が「それは何か」→「なぜ今みんなが気にしているのか」→「この動画で何が分かるのか」を",
        "この順で掴めるように書く。どの文も前の文から自然につながること。",
        f"1. 体言止めの一撃: 「{subject}。」",
        f"2. それが何なのかを一文で（いつ・どこで・何が）: {o.get('what', '')}",
        f"3. なぜ大事なのかを一文で（数字か比較で）: {o.get('significance', '')}",
        f"4. 話を今に移す一文（「この{subject[:6]}には、いまも色々な話がついて回る。」のように）。",
    ]
    if titles:
        lines += [f"5. 語られている形を見せる。前置き（固定文）: 「動画サイトで『{subject}』と検索すると、こんな題名が並ぶ。」",
                  "   そのあと次の題名を、この形のまま1つずつ別の文で読み上げる:"]
        lines += [f"   {t}" for t in titles]
    else:
        lines += ["5. （見せる題名が無いので飛ばす）"]
    lines += [
        f"6. それらに共通する点を一文（みんなが何を気にしているか）: {o.get('curious', '')}",
        f"7. 問いを一つ、はっきり言う。前に「本当にそうなのか。」を置く: 「{p.mystery}」"
        "。すぐ後に伏線（固定文）: 「この問いの答えは、最後に出す。」",
        f"8. チャンネル宣言（ほぼ固定文）: 「当チャンネルでは、こうした{genre}を、都市伝説として"
        "語るのではなく、論文と一次資料からひも解いていく。」",
        f"9. 地図（ほぼ固定文）: 「この動画では、いま語られている話を{len(claims)}つ取り上げ、"
        "当たっていたものから順に確かめる。」続けて「その前に、まず"
        f"{subject}とは何なのかを押さえておく。」",
        f"10. 出発の合図（固定文）: 「それでは私と共に、{subject}へと迫っていこう。」",
        "",
        "書かないこと:",
        "・「単に〜というわけではない」のような否定の前置き（何の答えなのかが分からない）。",
        "・答えの候補や、検証する話の一覧（まだ何も確かめていない段階で並べても頭に入らない）。",
        "・「最初に言い出した人がいる」「記録に残っている」のような、この動画で確かめていない約束。",
    ]
    return "\n".join(lines)


def _basics_brief(p: planmod.Plan, subject: str, claims: list[str]) -> str:
    b = p.basics
    seeds = "\n".join(f"   ・{x}" for x in (b.get("seeds") or []) if str(x).strip()) or "   （無し）"
    terms = "\n".join(f"   ・{t.get('term')} → {t.get('landing')}" for t in (b.get("terms") or [])
                      if str(t.get("term") or "").strip()) or "   （無し）"
    return "\n".join([
        f"## 基本の章: {subject}とは何か",
        "初めて見る人が、このあとの話を理解するのに要る基本だけを、物語として書く。事実の一覧にしない。",
        "この順で書く。前の文が次の文の理由か前提になるように並べる。",
        f"1. 入り（固定文）: 「まず、{subject}とは何なのか。」",
        f"2. 発見の話を、いつ・どこで・誰が・どうやって、の順で: {b.get('found', '')}",
        f"3. 中身。何が書かれているか。分けられるなら「1つ目は〜。2つ目は〜。」と数えて言う: {b.get('contents', '')}",
        f"4. いつのものか。それがどうして分かるのかも一言: {b.get('dating', '') or '（資料に無ければ書かない）'}",
        f"5. その後どうなったか（公開・管理）: {b.get('after', '') or '（資料に無ければ書かない）'}"
        "。保管場所や所蔵先は、ここに書いていなければ書かない",
        "6. いま語られている話の元になった事実。「ここが、いま語られている話の出どころになる。」のように、"
        "このあとの章につなげる:",
        seeds,
        "7. 専門語は、この章の文に出てくるものだけ。中身を先に言い、名前を後に言う"
        "（別の題材の例: 「聖書に入らなかった古い書物もある。外典と呼ばれる。」）。"
        "あとの章で使う語や宗派の名前を、ここで先回りして並べない:",
        terms,
        "8. 最後の文（固定文）: 「では、いま語られている話を、一つずつ確かめていく。」"
        "（最初の話の中身は次の章で言う。ここで言うと章の頭と二重になる）",
        "",
        "書かないこと: 資料に無い数字・人名・年。このあとの章で確かめる話の中身と答え"
        "（" + "／".join(c.claim for c in p.chapters) + "）。ここで言うと章の結論を先に明かすことになる。",
    ])


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
        elif in_wiki and t and not t.startswith(("見た目", "出典と", "使い方", "#")):
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


def _ordinal(i: int, n: int) -> str:
    return "最初" if i == 1 else "最後" if i == n else f"{i}つ目"


def _chapter_brief(i: int, c: planmod.Chapter, n: int, p: planmod.Plan) -> str:
    # 立場の名前（肯定・反転・留保）を見せると、「肯定の立場は、〜を挙げる」と本文に写した（死海文書）。
    # 役割だけを括弧で添え、名前は書かせない
    role = {"肯定": "そうだと言える事実", "反転": "それを崩す事実", "留保": "まだ言えないこと",
            "再反転": "もう一度ひっくり返す事実"}
    swings = "\n".join(f"   {k+1}. {s.get('fact')}（{role.get(str(s.get('stance')), '')}）"
                       for k, s in enumerate(c.swings))
    numbers = "\n".join(f"   ・{x.get('value')} — 断り: {x.get('caveat', '')}" for x in c.numbers) \
        or "   （資料に数字が無い。数字を作らない。「この数字には断りが要る」も書かない）"
    jargon = "\n".join(f"   ・{j.get('term')} → {j.get('landing')}" for j in c.jargon) or "   （無し）"
    ev = c.evidence or {}
    origin = _known(c.origin.get('who', ''), c.origin.get('year', ''), c.origin.get('how', ''))
    lead = ("前の章の最後の問いを受けて入る。" if i > 1 else "基本の章の最後で予告した話から入る。")
    lines = [
        f"## 第{i}章（全{n}章）: {c.claim}",
        "初めて見る人が「なぜこの話をするのか」「何が分かったのか」を追えるように、この順で書く。",
        "順番を入れ替えない。事実を並べるだけにしない。文と文を「なぜか」「では」「つまり」「ところが」",
        f"「だから」でつなぎ、前の文から次の文が出てくるようにする。{lead}",
        f"1. 話を出す（固定の形）: 「{_ordinal(i, n)}は、{c.claim.rstrip('。')}、という話だ。」",
        f"2. 平たく言う（「つまり、〜ということだ。」）: {c.means}",
        ("3. なぜそう語られるのか。元になった事実を言う（「この話には元がある。」から入ってよい）: "
         + c.basis + (f"（誰が・いつ: {origin}）" if origin else ""))
        if c.basis else
        ("3. なぜそう語られるのか: " + origin if origin else
         "3. （元になった事実が資料に無い。この項は書かない。「誰が言い出したかは分からない」とも書かない）"),
        f"4. 結論を先に一度だけ: 「結論から言う。{c.verdict_line.rstrip('。')}。」"
        "直後に同じ結論を言い直さない（「だが、〜」で繰り返さない）。",
        f"5. どう確かめるか（「では、どうすれば確かめられるか。」から入る）: {c.method or c.why}",
        f"6. なぜそう言えるのか（「なぜか。」と問い、「〜からだ。」で答える2文）: {c.why}",
        "7. 証拠。事実を1つずつ置き、その事実が何を示すかを一言添える。崩す事実は「ところが」「だが」、"
        "まだ言えないことは「ただし」で入れる。括弧の中の役割の言葉は本文に書かない:",
        swings,
        f"8. 証拠の年・場所・誰・何: {_known(ev.get('year', ''), ev.get('where', ''), ev.get('who', ''), ev.get('what', ''))}",
        "9. 数字と、その数字が何を示さないか（断り）。「135は〜の数を表す」のように数字を言い直す文は"
        "書かない。数字が無い章では断りの文も書かない:",
        numbers,
        "10. 専門語は、出てくる文で中身を先に言い、名前を後に言う。前の章や基本の章で説明した語は"
        "もう説明しない。日常語（AI・DNA・救世主など）は説明しない:",
        jargon,
        f"11. 語り手の判断（行為は書かない。判断が要る箇所に1文だけ）: {c.narrator or '（無ければ書かない）'}",
        f"12. 結論の範囲を限定する: {c.scope}",
        f"13. 大きな問い「{p.mystery}」に戻り、この章で分かったことを平たく言う: {c.bearing}",
        (f"14. 最後の1文は次の話への問い（「では、〜なのか。」）: {c.hook_out}" if i < n else
         "14. 最終章。次の話は無い。最後は「では、冒頭の問いの答えは何か。」で終える。"),
        "",
        "書かないこと: 動画のタイトルの引用。前の章で使った事実の繰り返し。「記録が見つかっていない」の繰り返し。",
    ]
    return "\n".join(lines)


def _closing_brief(p: planmod.Plan, subject: str) -> str:
    cl = p.closing
    sp = cl.get("speculation") or {}
    gen = "\n".join(f"   ・{g}" for g in cl.get("generalization") or [])
    found = "\n".join(f"   ・{f}" for f in cl.get("found") or [])
    openq = "\n".join(f"   ・{q}" for q in cl.get("open_questions") or [])
    reasons = "\n".join(f"   ・{r}" for r in (sp.get("reasons") or []))
    return "\n".join([
        "## 着地（4つの塊を、空行で区切って順に書く）",
        "### 答え（最初の段落。視聴者がいちばん知りたいのはここ）",
        f"   入り（固定文）: 「冒頭の問いに戻る。{p.mystery.rstrip('。？?')}。」",
        f"   答えを一文で、はっきり: {cl.get('answer', '')}",
        "   分かったことを、章で言った事実だけで「〜と分かった」と1回ずつ。新しい事実・年・数字を出さない:",
        found,
        f"   まだ分かっていないこと（答えの文を言い直さない）: {cl.get('not_found', '')}",
        "   まだ分からないことを、問いの形で並べず「まだ分からないことがある。〜だ。」と平叙で置く:",
        openq,
        "### 考察（事実と分ける。印を付ける。数字を作らない）",
        "   最初の文: 「事実はここまでだ。ここからは資料に無い。私の考えだ。」",
        f"   考え（「私は〜だと考える」と言い切る。「可能性がある」「かもしれない」で逃げない）: {sp.get('claim', '')}",
        "   理由:",
        reasons,
        f"   崩れる条件: {sp.get('weakness', '')}",
        "   最後の文: 「ここまでが考察だ。」",
        f"### 条件と一般化",
        f"   何が見つかれば決着するか（願望でなく条件。「〜が見つかれば、〜は決着する。」の一文で）: "
        f"{cl.get('condition', '')}",
        f"   題材を離れて、仕組みを言う（3文。抽象語だけで書かず、章の具体を1つ使う。主題: {p.thesis}）:",
        gen,
        f"   冒頭に戻る一文: {cl.get('opening_callback', '')}",
        "### CTA（ここだけ敬体）",
        "   この動画で参照した論文やデータは誰でも見られること、概要欄に一次資料のリンクがあること、",
        "   調べてほしい題材の募集、を敬体で3〜4文。",
    ])


NO_SOURCE_NOTE = ("※ この主張には当たれる論文が少ない。埋めない。短く書き、題材の記述にある事実で"
                  "確かめる。無いことは具体で言って結論にする（別の題材の例: 「宮廷の台帳にも、契約書にも、"
                  "この本は出てこない」）。この注意書きの言葉をそのまま本文に写さない。「記録は無い」を"
                  "言い換えて繰り返さない（1回で足りる）。")


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


def _weights_by_chapter(p: planmod.Plan, claims: list[str], weights: list[float] | None) -> list[float]:
    """設計図は主張を信頼度の順に並べ替える。重み（出典の数）は仕様の順なので、主張の文で引く。
    文で引けなければ（設計図が主張を言い換えた）、並びの位置で当てる。"""
    n = len(p.chapters)
    if not weights or len(weights) != len(claims):
        return [1.0] * n
    out = []
    for i, c in enumerate(p.chapters):
        if c.claim in claims:
            out.append(weights[claims.index(c.claim)])
            continue
        g = _grams(c.claim)
        hits = [len(g & _grams(x)) for x in claims]
        k = max(range(len(claims)), key=lambda j: hits[j])
        out.append(weights[k] if hits[k] >= 3 else (weights[i] if i < len(weights) else 1.0))
    return out


def blocks_from_plan(p: planmod.Plan, *, subject: str, genre: str, claims: list[str],
                     duration_sec: float, weights: list[float] | None = None) -> list[Block]:
    """設計図を、書かせる塊の列にする。

    冒頭 5.5% / 基本 11% / 着地 12% / 残りを章で割る。基本の章は参考の旗艦回
    （ヴォイニッチ第1幕「この本は何なのか」）に当たる。無いと、初めて見る人は
    題材が何なのか分からないまま噂の真偽を聞かされる（死海文書で実際にそうなった）。
    weights は主張ごとの資料の厚み（出典の数など）。無ければ等分。
    """
    n = len(p.chapters)
    open_sec = duration_sec * 0.055
    basics_sec = duration_sec * 0.11
    close_sec = duration_sec * 0.12
    body = duration_sec - open_sec - basics_sec - close_sec
    w_by_claim = _weights_by_chapter(p, claims, weights)
    shares = chapter_shares([1.0 + w for w in w_by_claim])
    out = [Block("opening", _opening_brief(p, subject, genre, claims), _chars(open_sec)),
           Block("basics", _basics_brief(p, subject, claims), _chars(basics_sec))]
    for i, c in enumerate(p.chapters, 1):
        brief = _chapter_brief(i, c, n, p)
        if w_by_claim[i - 1] <= 0:
            brief += "\n" + NO_SOURCE_NOTE
        out.append(Block(f"chapter{i}", brief, _chars(body * shares[i - 1])))
    out.append(Block("closing", _closing_brief(p, subject), _chars(close_sec)))
    return out


_BLOCK_RULES = """\
この塊だけを書く。前後の塊は別に書くので、ここで全体を締めない。
段落は空行で区切る。章は1つの段落にまとめる（冒頭と着地だけ複数の段落）。
聞き手は題材を名前しか知らない。文は短く切るが、つながりは切らない。次の文は前の文の
理由・結果・具体・反対のどれかにする。「なぜか」「では」「つまり」「だから」「ところが」で
つなぎ目を見せる。新しい語・人・場所は、出したその文か次の文で何なのかを言う。
「それ」「この話」が何を指すか、聞いて分かるようにする。同じ結論を2回言わない。
数字は、意味が伝わるものだけ使う。数字のために文を足さない。
専門語や文書の名前は、あとでもう一度使うときだけ出す。一度しか出ないなら中身だけ言う
（「35%はマソラ本文と一致する」ではなく「35%は、いまの旧約聖書の元になった本文と一致する」）。
一般の日本人に通じる呼び方を使う（ヘブライ語聖書 → 旧約聖書）。
文末は常体（だ・である）。敬体（です・ます）を混ぜない。
人名は話に欠かせない人だけ。塊に2人まで。役割を先に言う（「発掘を率いた考古学者の〜」）。
役割だけで足りるなら名前を出さない。
「先ほど見たように」は、前の塊で本当に言ったことを指すときだけ使う。
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


def thin_connectives(text: str, *, keep_adversative: int = 2, keep_landing: int = 4) -> str:
    """文頭の逆接と「つまり」を、章ごとに上限まで間引く。

    書き直しを頼んでも減らない（v3 0.93/分、v4 1.00/分。参考は最大0.53）。
    逆接の接続詞は省いても文は成立し、対比は残る。参考も「語はある。
    意味が違う。」と接続詞なしで対比する。上限を超えたぶんは接続詞だけ落とす。
    """
    out = []
    n_adv = n_land = 0
    for sent in re.split(r"(?<=[。？！])", text):
        # 章は1文1行に畳むので、2文目以降は改行から始まる。先頭の空白を外して見ないと
        # 1文目にしか効かない（実測: 逆接が 1.40/分 から減らなかった）
        lead = sent[: len(sent) - len(sent.lstrip())]
        body = sent[len(lead):]
        m = _ADVERSATIVE.match(body)
        if m:
            n_adv += 1
            if n_adv > keep_adversative:
                body = body[m.end():]
        m = _LANDING.match(body)
        if m:
            n_land += 1
            if n_land > keep_landing:
                body = body[m.end():]
        out.append(lead + body)
    return "".join(out)


def _fold(key: str, text: str) -> str:
    """章は1段落に畳む。指示しても段落を分けてくる（実測で第1章が7段落）。
    段落=章として監査するので、ここで確実に畳む。基本の章も1段落。冒頭と着地は段落のまま。"""
    if not key.startswith(("chapter", "basics")):
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
    pts += 1.0 if (any(devices.YEAR.search(x) and (devices.ORIGIN.search(x) or devices.PERSON.search(x)
                                                     or devices.PROVENANCE.search(x)) for x in sents)
                   or any(re.search(r"元がある|元になった|きっかけは", x) for x in sents)) else 0.0
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
    """冒頭の候補を選ぶ物差し。それは何か → 語られている題名 → 問い → 伏線 → 合図。
    体言止め3つと「皆敗れた」で数えていた頃の物差しのままだと、新しい冒頭は必ず点が
    足りず、毎回2本目を書かせていた（呼び出しの無駄）。"""
    sents = devices.split_sentences(text.replace("\n", ""))
    if not sents:
        return -99.0
    pts = 1.0 if devices._is_noun_stop(sents[0]) else 0.0
    pts += 2.0 if any("題名" in x for x in sents) else 0.0
    pts += 2.0 if any(re.search(r"のか[。？]", x) for x in sents) else 0.0
    pts += 2.0 if any(devices.PLANT.search(x) for x in sents) else 0.0
    pts += 1.0 if any(devices.LAUNCH.search(x) for x in sents) else 0.0
    pts += 1.0 if any("とは何なのか" in x for x in sents) else 0.0
    return pts


def basics_score(text: str) -> float:
    sents = devices.split_sentences(text.replace("\n", ""))
    if not sents:
        return -99.0
    pts = 2.0 if any("とは何" in x for x in sents[:2]) else 0.0
    pts += 1.0 if any(devices.YEAR.search(x) for x in sents) else 0.0
    pts += 1.0 if len(sents) >= 8 else 0.0
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
         "この塊に指摘がある。事実は変えず、指摘された点だけ直した全文を出す。"
         "前後の文とのつながりが切れないように直す。\n\n" + "\n".join(f"- {n}" for n in b.notes)
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
_ENOUGH = {"chapter": 4.0, "opening": 5.0, "closing": 1.5, "basics": 2.0}


def _score(b: Block, text: str, material: str, subject: str) -> float:
    if b.key == "opening":
        return opening_score(text)
    if b.key == "basics":
        return basics_score(text)
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


_VOICED = re.compile(r"そう語られて|そう言われて|語られてきた|という話だ")


def _bigrams(text: str) -> set[str]:
    t = devices._norm(text)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _covers(sent: str, ref: str, ratio: float = 0.6) -> bool:
    """sent の中身が ref にほぼ含まれているか（言い直しか）。"""
    a, b = _bigrams(sent), _bigrams(ref)
    return bool(a) and len(a) >= 4 and len(a & b) >= ratio * len(a)


def ensure_told_opening(text: str, titles: list[str], subject: str) -> str:
    """冒頭で、いま語られている形（動画タイトル）を前置き付きで見せる。

    章の中で「そのうちの一本は、タイトルそのものがこうなっている」と前置き無しに
    差し込んだら、何の話か分からないと言われた（死海文書）。参考ch（ピラミッド回）は
    「何十分も割いて論じる動画がいくつもある」と置いてから題名を出している。
    冒頭の「なぜ気になるのか」に、前置き付きでまとめて置く。書き手の決まり
    （出典の題名を本文に書かない）がこれを消すので、無ければ機械的に置く。"""
    spoken = [spoken_title(t) for t in titles if spoken_title(t)]
    if not spoken:
        return text
    if any(_covers(x.strip("「」。"), text.replace("\n", ""), 0.8) for x in spoken):
        return text
    block = "\n".join([f"動画サイトで『{subject}』と検索すると、こんな題名が並ぶ。"] + spoken)
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    # 問い（「本当に」「〜のか。」）の段落の前。無ければ3段落目の前
    at = next((k for k, q in enumerate(paras) if re.search(r"本当に|のか[。？]", q)), min(2, len(paras)))
    paras.insert(at, block)
    return "\n\n".join(paras)


# 出どころの推測（年・媒体を付けて「広まった」）と、「誰が言い出したか分からない」の定型
_ORIGIN_UNKNOWN = re.compile(r"(誰が|最初に)[^。]{0,14}(言い出|語り始|広め)[^。]{0,24}(記録|分かって|不明|見つかって)")


def drop_invented_origins(text: str, c: planmod.Chapter) -> str:
    """出どころの推測の文と、「誰が最初に言い出したかは記録が見つかっていない」を消す。

    後者は全章に入れていたが、初めて見る人には意味の無い文だった（死海文書で
    「何を言っているのか分からない」と言われた一因）。元が分かっていれば basis で言う。"""
    known = any(str(c.origin.get(k) or "").strip() for k in ("who", "year"))
    out = []
    for x in _sents(text):
        if _ORIGIN_UNKNOWN.search(x):
            continue
        if not known and _ORIGIN_GUESS.search(x) and not (c.basis and _covers(x, c.basis, 0.5)):
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


def ensure_intro(text: str, claim: str, ordinal: str) -> str:
    """章の頭で、何の話をする章なのかを言う。言っていなければ「〜は、〜という話だ。」を置く。
    章の頭が証拠や判定から始まると、何の話が始まったのか分からない。"""
    claim = claim.strip().rstrip("。")
    sents = _sents(text)
    if not claim or any(_covers(claim, x, 0.5) for x in sents[:2]):
        return text
    return "\n".join([f"{ordinal}は、{claim}、という話だ。"] + sents)


def drop_restated_verdict(text: str, verdict_line: str) -> str:
    """結論の直後3文で、同じ結論を言い直している文を消す。

    「結論から言う。Xだが、Yはない。だが、Xである。Yは報告されていない。」と
    書いた（死海文書の全章）。聞く側には同じことが3回続く。"""
    sents = _sents(text)
    at = next((i for i, x in enumerate(sents) if "結論から" in x or _covers(x, verdict_line, 0.7)), None)
    if at is None or not verdict_line.strip():
        return text
    ref = verdict_line + (sents[at] if at < len(sents) else "")
    # 「結論から言う。」の単独文なら、その次の文が結論の本体
    body = at + 1 if re.fullmatch(r"結論から(言う|言おう)。", sents[at].strip()) else at
    keep = sents[:body + 1]
    for k, x in enumerate(sents[body + 1:], body + 1):
        if k <= body + 3 and _covers(re.sub(r"^(だが|しかし|ただ|つまり)、?", "", x), ref, 0.6):
            continue
        keep.append(x)
    return "\n".join(keep)


def ensure_bearing(text: str, bearing: str) -> str:
    """章末に、大きな問いにとっての意味が無ければ、最後の問いの直前に置く。
    章の結果が大きな問いとどうつながるかが無いと、事実の一覧で終わる。"""
    bearing = (bearing or "").strip()
    sents = _sents(text)
    if not bearing or any(_covers(bearing, x, 0.5) or _covers(x, bearing, 0.6) for x in sents[-5:]):
        return text
    at = len(sents) - 1 if sents and _QUESTION.search(sents[-1]) else len(sents)
    sents.insert(at, bearing if bearing.endswith("。") else bearing + "。")
    return "\n".join(sents)


def ensure_basics_intro(text: str, subject: str) -> str:
    """基本の章は「まず、〜とは何なのか。」で入る。画面の章カードもこの文で置く。"""
    if "とは何" in "".join(_sents(text)[:2]):
        return text
    return f"まず、{subject}とは何なのか。\n" + text.lstrip()


def ensure_plant(text: str, planted: str) -> str:
    """冒頭に伏線が無ければ、出発の合図の文の直前に入れる。

    設計図には必ずあるのに、3本に1本は書き手が落とす（bench 実測）。伏線と回収は
    対で初めて効く装置なので、書き手の気分に任せず機械的に置く。"""
    if not planted or any(devices.PLANT.search(x) for x in _sents(text)):
        return text
    line = "この問いの答えは、最後に出す。"
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    # 問いの直後。離れると「この問い」が何を指すか分からない
    ask = planted.rstrip("。？?")
    for i, q in enumerate(paras):
        sents = _sents(q)
        k = next((j for j, x in enumerate(sents) if ask and _covers(ask, x, 0.7)), None)
        if k is not None:
            paras[i] = "\n".join(sents[:k + 1] + [line] + sents[k + 1:])
            return "\n\n".join(paras)
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


def ensure_callback(text: str, mystery: str) -> str:
    """着地の頭で冒頭の問いに戻る。無ければ置く（参考も最後で冒頭に戻る。
    ピラミッド回: 「1章で、三つの選択肢を並べた。」）。"""
    if not mystery or any(devices.CALLBACK.search(x) for x in devices.split_sentences(text.replace("\n", ""))[:6]):
        return text
    return f"冒頭の問いに戻る。{mystery.rstrip('。？?')}。\n" + text.lstrip()


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
    # 答えの段落のあと。条件と CTA の前
    at = min(1, len(paras))
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
    """章の冒頭10文に結論が無ければ、話を出した直後に置く。

    束ね型の章は「通説→結論→なぜ」の順が型で、参考は9章中6章がそう。
    書き手は3本中で 1〜3章しか守らない（bench 実測）。設計図の verdict_line は
    形の検査を通っているので、機械的に置いてよい。"""
    if not verdict_line.strip():
        return text
    if any(devices.VERDICT.search(x) for x in _sents(text)[:10]):
        return text
    line = "結論から言う。" + verdict_line.strip().rstrip("。") + "。"
    return _insert_after(text, _VOICED, line, default=2)


# 「X は〜のことだ」の形の定義文
_DEF = re.compile(r"^(?:つまり、?)?(?P<t>[^、。「」]{1,16}?)(?:とは|というのは|は)、?[^。]{2,60}?"
                  r"(?:のことだ|のことである|のこと|を指す|を指す言葉だ|方法だ|方法である|"
                  r"一派である|一派だ|集団だ|集団である|という意味だ)。?$")


def tidy_terms(blocks: list[Block]) -> None:
    """定義の文を整える。塊をまたいで見るので、塊ごとの保証とは別に通す。

      ・前の塊で定義した語をもう一度定義している文を消す（「AIは人工知能のことだ」を2回）
      ・日常語の定義を消す（「救世主とは、救い主のことだ」）
      ・基本の章で、その章の他の文に出てこない語の定義を消す（「エッセネ派は古代ユダヤ教の
        一派である」が、何の話か分からないまま基本の章の最後に並んだ。死海文書）
    """
    defined: set[str] = set()
    for b in blocks:
        if not (b.key == "basics" or b.key.startswith("chapter")):
            continue
        sents = _sents(b.text)
        keep = []
        for k, x in enumerate(sents):
            m = _DEF.match(x.strip())
            if m:
                t = m.group("t").strip()
                others = "".join(sents[:k] + sents[k + 1:])
                if t in defined or t in planmod.EVERYDAY:
                    continue
                if b.key == "basics" and t not in others:
                    continue
                defined.add(t)
            keep.append(x)
        b.text = "\n".join(keep)


_BACKREF = re.compile(r"^(先ほど|さっき|前に|前の章で)見たように、?")


def fix_back_references(blocks: list[Block]) -> None:
    """「先ほど見たように」が、前に言っていないことを指していたら、その前置きだけ外す。
    前の章と同じ事実を言うなと指示したら、書き手が初出の事実にこれを付けた（死海文書）。"""
    earlier: list[str] = []
    for b in blocks:
        sents = _sents(b.text)
        if b.key == "basics" or b.key.startswith("chapter"):
            out = []
            for x in sents:
                m = _BACKREF.match(x)
                if m and not any(_covers(x[m.end():], e, 0.5) for e in earlier):
                    x = x[m.end():]
                out.append(x)
            b.text = "\n".join(out)
            sents = out
        earlier += sents


def dedupe_answer(text: str, answer: str) -> str:
    """着地の最初の段落で、答えの文を2回言っていたら後のほうを消す。
    「だが、〜は分かっていない」の枠に、答えそのものを入れて繰り返した（死海文書）。"""
    answer = (answer or "").strip()
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    if not answer or not paras:
        return text
    seen, keep = False, []
    for x in _sents(paras[0]):
        body = re.sub(r"^(だが|しかし|つまり)、?", "", x)
        if _covers(body, answer, 0.8) or _covers(answer, body, 0.8):
            if seen:
                continue
            seen = True
        keep.append(x)
    paras[0] = "\n".join(keep)
    return "\n\n".join(paras)


_NEG = re.compile(r"ない|無い|ず[、。]|ではない|しない|一致しない|違う")


def flipped_facts(before: str, after: str) -> list[str]:
    """書き直しで、数字の付いた事実の肯定・否定が入れ替わった文。

    読みやすく直させたら「35%はマソラ本文と一致する」が「35%は〜と一致しない独自の系統である」
    になった（死海文書）。数字の検査は数字が資料にあれば通るので、これを拾えない。
    同じ数字を含む文どうしで、否定の有無が変わったものを返す。"""
    old = [x for x in _sents(strip_cites(before)) if re.search(r"\d", x)]
    out = []
    for x in _sents(strip_cites(after)):
        nums = set(re.findall(r"\d+(?:\.\d+)?%?", x))
        if not nums:
            continue
        same = [y for y in old if nums & set(re.findall(r"\d+(?:\.\d+)?%?", y)) and _covers(y, x, 0.4)]
        if same and all(bool(_NEG.search(y)) != bool(_NEG.search(x)) for y in same):
            out.append(x)
    return out


def dedupe_within(text: str, subject: str = "") -> str:
    """塊の中で、前に言った文とほぼ同じ文を消す（隣り合っていなくても）。
    「5%は七十人訳の系統だ」が同じ章に2回出た（死海文書）。"""
    out: list[str] = []
    for x in _sents(text):
        if len(x) >= 12 and any(devices._similar(x, y, (subject,)) for y in out):
            continue
        out.append(x)
    return "\n".join(out)


def drop_spoilers(text: str, claims: list[str]) -> str:
    """基本の章から、あとの章で確かめる話を言い切ってしまう文を消す。
    「死海文書を書いたのはクムラン教団である」と基本の章で言い、最終章の結論を先に明かした。"""
    keep = []
    for x in _sents(text):
        if any(_covers(c.rstrip("。"), x, 0.6) for c in claims if c) and not re.search(r"とは何|話", x):
            continue
        keep.append(x)
    return "\n".join(keep)


_REASON_TAIL = re.compile(r"(ため|から)である。$|(ため|から)だ。$")


def fix_dangling_reasons(text: str) -> str:
    """「なぜか」の問いも前の文も無いのに「〜ためである。」で終わる文を、言い切りにする。
    設計図の why（「〜ため」）を1文として置き、理由だけが宙に浮いた（死海文書の5章）。"""
    sents = _sents(text)
    out = []
    for k, x in enumerate(sents):
        prev = sents[k - 1] if k else ""
        if _REASON_TAIL.search(x) and not re.search(r"なぜ|理由", prev):
            x = _REASON_TAIL.sub("。", x)
            x = re.sub(r"(ない|ある|いる|た|る)。$", r"\1。", x)
        out.append(x)
    return "\n".join(out)


def long_sentences(text: str, limit: int = 45) -> list[str]:
    return [x for x in _sents(strip_cites(text)) if len(x) > limit]


def _tidy(blocks: list[Block], subject: str = "") -> None:
    tidy_terms(blocks)
    fix_back_references(blocks)
    for b in blocks:
        if b.key == "basics" or b.key.startswith("chapter"):
            b.text = fix_dangling_reasons(dedupe_within(b.text, subject))


_LATIN = re.compile(r"(?<![A-Za-z])[A-Z][a-zà-ÿćčšžńłőúíé]{2,}(?:\s+[A-Z][a-zà-ÿćčšžńłőúíé]{2,})*")


def latin_words(text: str) -> list[str]:
    """読み上げると英語になる語（人名・誌名）。略語（AI・DNA）は見ない。"""
    return sorted(set(_LATIN.findall(strip_cites(text))))


# 敬体の文末を常体に。確実に言い換えられる形だけ（残りは直しの指示で）
_PLAIN = [
    (re.compile(r"ていません([。？])"), r"ていない\1"),
    (re.compile(r"ません([。？])"), r"ない\1"),
    (re.compile(r"でした([。？])"), r"だった\1"),
    (re.compile(r"(い)です([。？])"), r"\1\2"),
    (re.compile(r"です([。？])"), r"だ\1"),
    (re.compile(r"ています([。？])"), r"ている\1"),
    (re.compile(r"ていました([。？])"), r"ていた\1"),
    (re.compile(r"てあります([。？])"), r"てある\1"),
    (re.compile(r"あります([。？])"), r"ある\1"),
    (re.compile(r"ありました([。？])"), r"あった\1"),
    (re.compile(r"います([。？])"), r"いる\1"),
    (re.compile(r"なります([。？])"), r"なる\1"),
    (re.compile(r"なりました([。？])"), r"なった\1"),
    (re.compile(r"されます([。？])"), r"される\1"),
    (re.compile(r"されました([。？])"), r"された\1"),
    (re.compile(r"できます([。？])"), r"できる\1"),
    (re.compile(r"しました([。？])"), r"した\1"),
    (re.compile(r"します([。？])"), r"する\1"),
    (re.compile(r"進みました([。？])"), r"進んだ\1"),
    (re.compile(r"のぼります([。？])"), r"のぼる\1"),
]
_POLITE = re.compile(r"(です|ます|ました|ません|でした)[。？]")


def plain_form(text: str) -> str:
    """敬体の文末を常体にする。着地の CTA（最後の段落）だけは敬体のまま置く。
    冒頭と着地の本文に「〜です」「〜ています」が混ざった（死海文書）。"""
    out = text
    for pat, rep in _PLAIN:
        out = pat.sub(rep, out)
    return out


def _plain_block(key: str, text: str) -> str:
    if key != "closing":
        return plain_form(text)
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    return "\n\n".join([plain_form(q) for q in paras[:-1]] + paras[-1:])


def ensure_answer(text: str, answer: str) -> str:
    """着地の最初の段落に、問いへの答えの文が無ければ、問いの直後に置く。
    問いに戻ったのに答えを言わず、分かったことの列挙に入った（死海文書）。"""
    answer = plain_form((answer or "").strip())
    paras = [q for q in re.split(r"\n\s*\n", text.strip()) if q.strip()]
    if not answer or not paras:
        return text
    sents = _sents(paras[0])
    if any(_covers(answer, x, 0.6) or _covers(x, answer, 0.8) for x in sents):
        return text
    at = next((i + 1 for i, x in enumerate(sents) if re.search(r"のか[。？]", x)), min(1, len(sents)))
    sents.insert(at, answer if answer.endswith("。") else answer + "。")
    paras[0] = "\n".join(sents)
    return "\n\n".join(paras)


def _claim_of(b: Block, p: planmod.Plan) -> str:
    i = int(b.key[len("chapter"):]) - 1 if b.key.startswith("chapter") else -1
    return p.chapters[i].claim if 0 <= i < len(p.chapters) else ""


def _guarantee(b: Block, p: planmod.Plan, planted: str, subject: str = "") -> str:
    """書き手が落としがちな装置を、塊ごとに機械的に置き、文末を常体にそろえる。"""
    return _plain_block(b.key, _guarantee_devices(b, p, planted, subject))


def _guarantee_devices(b: Block, p: planmod.Plan, planted: str, subject: str = "") -> str:
    if b.key == "opening":
        return ensure_plant(ensure_told_opening(b.text, p.told[:2], subject), planted)
    if b.key == "basics":
        return ensure_basics_intro(drop_spoilers(b.text, [c.claim for c in p.chapters]), subject)
    if b.key.startswith("chapter"):
        i = int(b.key[len("chapter"):]) - 1
        if i >= len(p.chapters):
            return b.text
        c = p.chapters[i]
        n = len(p.chapters)
        text = ensure_intro(b.text, c.claim, _ordinal(i + 1, n))
        text = ensure_verdict(text, c.verdict_line)
        text = drop_restated_verdict(text, c.verdict_line)
        text = drop_invented_origins(text, c)
        text = ensure_bearing(text, c.bearing)
        text = ensure_hook(text, c.hook_out if i < n - 1 else "では、冒頭の問いの答えは何か。")
        # 機械的に置いた結論と、書き手の同じ文が並ぶことがある（実測）
        return dedupe_adjacent(text)
    if b.key == "closing":
        text = ensure_callback(b.text, p.mystery or planted)
        text = ensure_answer(text, str(p.closing.get("answer") or ""))
        text = dedupe_answer(text, str(p.closing.get("answer") or ""))
        return ensure_speculation(text, p.closing.get("speculation") or {})
    return b.text


def _facts(b: Block, all_facts: list[str]) -> str:
    """塊に渡す番号付きの資料。基本の章は題材の記述を多めに、冒頭は少しだけ。"""
    if not all_facts:
        return ""
    if b.key.startswith("chapter"):
        return facts_for(b.brief, all_facts)
    if b.key == "basics":
        return facts_for(b.brief, all_facts, limit=4, describe=26)
    if b.key == "opening":
        return facts_for(b.brief, all_facts, limit=2, describe=8)
    return ""


def compose(p: planmod.Plan, *, subject: str, genre: str, claims: list[str],
            duration_sec: float, chat: Chat, rounds: int = 2,
            kind: str = "bundle", material: str = "",
            weights: list[float] | None = None, candidates: int = 1,
            cite: bool = True, reader: Chat | None = None,
            read_rounds: int = 1) -> tuple[str, devices.Audit, list[str]]:
    """設計図から台本を書き、監査して、外れた章だけ直す。

    material を渡すと、資料に無い数字を章の指摘にして消させる。cite なら
    資料を番号付きで章に渡し、数字の文に根拠番号を付けさせる（採るときに剥がす）。
    candidates が2以上なら塊ごとに候補を作り、装置の点で選ぶ。
    reader（JSONで返す chat）を渡すと、最後に初見の視聴者として読ませ、分からないと
    言われた塊を直し、もう一度読ませる。結果は audit.reading に入る。
    戻り値は (台本, 最後の監査, 残った指摘)。
    """
    blocks = blocks_from_plan(p, subject=subject, genre=genre, claims=claims,
                              duration_sec=duration_sec, weights=weights)
    all_facts = facts_from_material(material) if (cite and material) else []
    tail = ""
    planted = str(p.planted_question.get("text") or "")
    for b in blocks:
        f = _facts(b, all_facts)
        # 候補は必要なときだけ。1本目が閾値を超えていれば2本目は作らない
        # （常に2本作ると章の呼び出しが倍になる。bench では選択の効果は構造より小さかった）
        texts = [write_block(b, tail, chat, f)]
        while len(texts) < max(1, candidates) and _score(b, texts[-1], material, subject) < _ENOUGH.get(b.key[:7], 4.0):
            texts.append(write_block(b, tail, chat, f))
        b.text = _pick(b, texts, material=material, subject=subject)
        b.text = _guarantee(b, p, planted, subject)
        tail = _tail(strip_cites(b.text))
    _tidy(blocks, subject)

    def check():
        text = assemble(blocks)
        chapter_idx = [i for i in (paragraph_index(blocks, b.key) for b in blocks
                                   if b.key.startswith("chapter")) if i is not None]
        audit = devices.audit(text, duration_sec, subject=subject, kind=kind,
                              chapter_blocks=chapter_idx or None)
        style = validate(text, duration_sec)
        loose = {b.key: devices.unsourced_numbers(strip_cites(b.text), material)
                 for b in blocks if material}
        bare = {b.key: uncited(b.text, _claim_of(b, p)) for b in blocks
                if all_facts and b.key.startswith("chapter")}
        made_up = {b.key: origin_invented(b.text, p.chapters[int(b.key[7:]) - 1])
                   for b in blocks if b.key.startswith("chapter") and int(b.key[7:]) - 1 < len(p.chapters)}
        repeats = readability.repeats_across(blocks, subject)
        latin = {b.key: latin_words(b.text) for b in blocks
                 if (b.key == "basics" or b.key.startswith("chapter")) and latin_words(b.text)}
        left = (list(audit.notes) + list(style.violations)
                + [f"{k}: 資料に無い数字 " + "、".join(v) for k, v in loose.items() if v]
                + [f"{k}: 根拠番号の無い数字の文 " + " / ".join(v[:3]) for k, v in bare.items() if v]
                + [f"{k}: 資料に無い出どころ " + " / ".join(v) for k, v in made_up.items() if v]
                + [f"{k}: 前の章と同じ事実 " + " / ".join(x[:24] for x in v[:2]) for k, v in repeats.items()]
                + [f"{k}: 英語の表記 " + "、".join(v[:4]) for k, v in latin.items()])
        return audit, style, loose, bare, made_up, repeats, latin, left

    left: list[str] = []
    audit = None
    for r in range(rounds + 1):
        audit, style, loose, bare, made_up, repeats, latin, left = check()
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
                b.notes.append("出どころ（年代・媒体）は資料に無い。その文を消す: " + " / ".join(made_up[b.key][:2]))
            if repeats.get(b.key):
                b.notes.append("前の章と同じ事実を言い直している。この章では言わない: "
                               + " / ".join(f"「{x[:30]}」" for x in repeats[b.key][:3]))
            if latin.get(b.key):
                b.notes.append("英語の表記が残っている。読み上げるので片仮名にする（人名は片仮名、"
                               "雑誌名は「科学誌」のように種別で）: " + "、".join(latin[b.key][:4]))
        _rewrite_noted(blocks, p, chat, all_facts, planted, subject)

    reading = None
    if reader is not None:
        # 読む → 分からないと言われた塊を直す → もう一度読む、を read_rounds 回まで。
        # 1回の直しでは 6/10 までしか上がらなかった（死海文書、構造を変えた初回）
        reading = readability.read(blocks, reader, subject=subject)
        for _ in range(max(0, read_rounds)):
            notes = readability.notes_by_block(reading)
            if reading.clear or not notes:
                break
            for b in blocks:
                b.notes = notes.get(b.key, [])
            _rewrite_noted(blocks, p, chat, all_facts, planted, subject)
            reading = readability.read(blocks, reader, subject=subject)
        audit, style, loose, bare, made_up, repeats, latin, left = check()
    audit.reading = reading
    return assemble(blocks), audit, left


def _rewrite_noted(blocks: list[Block], p: planmod.Plan, chat: Chat, all_facts: list[str],
                   planted: str, subject: str) -> None:
    prev = ""
    for b in blocks:
        if b.notes:
            before = b.text
            b.text = rewrite_block(b, prev, chat, _facts(b, all_facts))
            b.text = _guarantee(b, p, planted, subject)
            if flipped_facts(before, b.text):
                b.text = before          # 事実が裏返った直しは採らない
        prev = _tail(strip_cites(b.text))
    _tidy(blocks, subject)


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

    def avg_len(b: Block) -> float:
        ss = _sents(strip_cites(b.text))
        return sum(len(x) for x in ss) / len(ss) if ss else 0.0

    longest = sorted(chapters, key=avg_len, reverse=True)[:2]
    for n in audit.global_notes + style_notes:
        if _REPORT_ONLY.search(n):
            continue
        if _TO_OPENING.search(n):
            blocks[0].notes.append(n)
        elif _TO_CLOSING.search(n):
            blocks[-1].notes.append(n)
        elif "平均文長" in n:
            # 文のいちばん長い2章だけ直す。全章に配ると、1回の直しで呼び出しが6回増えた。
            # 「平均が長い」とだけ言っても縮まらない（26.4→26.9）。長い文を名指しする
            for b in longest:
                longs = long_sentences(b.text)
                b.notes.append(n + ("。次の文を2つか3つに切る（中身は変えない）: "
                                    + " / ".join(f"「{x}」" for x in longs[:6]) if longs else ""))
        else:
            for b in chapters:
                b.notes.append(n)
