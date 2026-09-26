"""台本の設計図。書く前に、章ごとの仕掛けを決める。

一気に書かせると、事実を並べただけの平板な台本になる（ヴォイニッチの
初稿がそうだった。style の検査は通っていた）。参考2本は章ごとに同じ手順を
踏んでいる。ピラミッド回の第5章を分解するとこうなる。

  問い          石をどうやって積み上げたのか。
  結論を先に    じつは、決まっていない。これも正しい。
  なぜか        なぜ決まらないのか。理由は、意外なほど単純だ。
  着地          つまり、いちばん知りたいものが、いちばん残らない。
  候補と留保    候補はいくつもある。〜。ただし角で向きを変えなければならず〜
  伏線          その話は後の章でする。
  通説を言わせる ここから、いつもの一言が出る。決まらないのは、人間の力では〜
  反転          だが、並んでいる候補は、全部人力である。
  新しい証拠    そして2018年、その坂の実物が出た。場所はギザではない。
  前提が崩れる  そう思われていた前提が、ここで崩れた。
  数字と断り    中央値で13.8年から20.6年。ただし、この数字には断りが三つ要る。
  結論の範囲    つまり「答えが出た」ではない。「人力でも数字が合う」というところまでだ。
  次への引き    石は、音で浮かせて運ばれた。そういう説が、いま語られている。

この順番を、事実を当てはめる前に決めておく。それが設計図。
書くのは compose.py で、設計図の1章ぶんずつ書かせる。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

STANCES = ("肯定", "反転", "留保", "再反転")

PLAN_INSTRUCTIONS = """\
あなたは、都市伝説として語られている話を一次資料まで戻って確かめる
ドキュメンタリーの構成作家です。台本を書く前に、設計図をJSONで作ります。

設計図には事実を入れます。事実は下の資料にあるものだけを使い、資料に無い
数字・人名・年は書きません。分からない項目は空文字にします（"不明" と書かない）。

## いちばん大事なこと: 初めて見る人が、話についていけること
視聴者はこの題材を名前しか知らない。途中で「何の話？」「なぜその話になった？」と
思った瞬間に離れる。だから順番を守る。

  1. それは何か        題材を一文で（いつ・どこで・何が）。そのあと、なぜ大事なのかを一文。
  2. なぜ気になるのか   いま語られている話の例と、それらに共通する点（みんなが何を気にしているか）。
  3. 問いを一つ         この動画が答える問い（mystery）を、視聴者の言葉で。
  4. 基本（basics）     発見・中身・年代・その後。語られている話の元になった事実もここで出す。
  5. 章                1章に1つの話。話を平たく言う → なぜそう語られるのか（元の事実）→
                       結論 → どう確かめるか → 証拠 → この章で大きな問いについて分かったこと → 次の話への問い。
  6. 着地               大きな問いに答える。答えられない部分は、分からないと言い、考察を事実と分けて置く。

どの文も、前の文から自然につながること。新しい語・人・場所は、出したその場で何かを言う。
「隠した」のように二通りに読める語は、どちらの意味かを言う（隠蔽した／洞窟にしまった）。

## 章の中の順番（ピラミッド回の章を分解したもの）
話を言う → 元の事実 → 結論を先に（「結論から言う。これは正しい」）→ 何を見れば決まるか →
証拠を振り子で（肯定 → 反転 → 留保）→ 数字と断り → 結論の範囲を限定 →
大きな問いにとっての意味 → 次の章への問い

## 守ること
- 語り手の行為を作らない。「私は全部読んだ」「1700件数えた」のような行為は書かない。
  語り手が出るのは判断だけ（「私は判断を保留する」「私はこの説を採らない」）。
- 各章の verdict は「当たり／半分当たり（理由が違う）／跡形なし／決まっていない」のどれか。
- swings は肯定→反転→留保の順で最低3つ。同じ立場を続けない。
- 章どうしで同じ事実を使い回さない。2つの章が同じ証拠で決まるなら、その事実は片方の章にだけ置く。
- means は、その話を平たく言い直した一文と、本当なら何が言えるか
  （別の題材の例: 「つまり、ピラミッドは墓ではなく、電気を作る施設だったということだ」）。
- basis は、その話が語られるようになった元の事実。資料の「話の元」の節から取る
  （別の題材の例: 「テスラは無線で電気を送る塔を実際に建てていた」）。資料に無ければ空。
  元が分からないとき、本文で「誰が言い出したかは分からない」とは言わせない。黙って飛ばす。
- bearing は、この章の結果が大きな問い（mystery）にとって何を意味するかを平たく一文
  （別の題材の例: 「少なくとも、テスラがピラミッドについて何かを明かした、という線は消えた」）。
- hook_out は次の章の話につながる問い（「では、〜なのか。」）。次の章の claim の中身を問いの形で予告する。
- mystery は視聴者が本当に気にしている具体的な問い。「なぜ謎が残るのか」のような抽象は不可。
  話し言葉で、はい／いいえで答えられる形がよい。
- opening.curious は、語られている話に共通する点を一文で
  （別の題材の例: 「どれも、ピラミッドは人間が建てたものではない、と言っている」）。
- basics は資料の「題材の記述」から。発見（found）、中身（contents）、年代とその分かり方（dating）、
  その後（after: 公開・管理・現在の場所）、話の元になった事実（seeds）。
  専門語（terms）は、出すなら言い換えを付ける。
- 人名は、話に欠かせない人だけ。1章に2人まで。役割で足りるなら名前を出さない（「発掘を率いた考古学者」）。
- jargon は、中学生が知らない専門語だけ（1章に2つまで）。AI・DNA・隠蔽・救世主・断片のような
  日常語は入れない。前の章や basics で説明した語は入れない。日常の言い換えを1つ付ける。
- basics.terms は、基本の章の文に実際に出る語だけ、3つまで。あとの章で使う語をここで先回りして並べない
  （並べると、何の話か分からないまま定義だけが続く）。
- numbers は、その章の結論に関わる数字だけ。題材全体の数（写本の総数など）を章に入れない。
- figure は、その章の資料の数字で描ける図。年が3つ以上なら timeline、同じ単位の量が
  2つ以上なら scale。無ければ kind を "none"。資料に無い数字を図にしない。
- closing.answer は mystery への答えを一文で。はっきり言えるところまで言う。
  not_found は答えとは別の「まだ分かっていないこと」。答えを言い直さない。
- 設計図の文は常体（だ・である）で書く。敬体（です・ます）は使わない。
- closing.speculation は資料に無い私の考え。claim と reasons（2つ以上）と weakness（崩れる条件）。
  claim は「私は〜だと考える」と言い切れる一つの主張にする。「可能性がある」「かもしれない」で逃げない。
- thesis は「なぜそうなるのか」への答えで、仕組みを言う一文。教訓や感想ではない。
  参考の形: 「AIの限界は賢さではない。答え合わせができるかどうかで決まっている。」題材名を含めない。
- origin（誰が・何年に言い出したか）は資料から分かる範囲で。分からなければ空。
- closing.open_questions は「まだ分からないこと」を分からないまま置く。
- 例の文をそのまま写さない。
- 出力はJSONのみ。前後に文章を付けない。

## JSONの形
{
  "thesis": "題材より大きい一文（題材名を含めない）",
  "mystery": "この動画が答える問い（視聴者の言葉で）",
  "opening": {
    "what": "題材が何なのかを一文（いつ・どこで・何が）",
    "significance": "なぜ大事なのかを一文（数字か比較で）",
    "curious": "語られている話に共通する点。みんなが何を気にしているか",
    "map": "何を何の順で確かめるか"
  },
  "basics": {
    "found": "発見（いつ・どこで・誰が・どうやって）",
    "contents": "中身（何が書かれているか、どう分けられるか）",
    "dating": "いつのものか、それがどうして分かるか",
    "after": "その後（公開・管理・いまどこにあるか）",
    "seeds": ["語られている話の元になった事実"],
    "terms": [{"term": "専門語", "landing": "日常の言い換え"}]
  },
  "planted_question": {"text": "最後まで保留する問い（mystery と同じでよい）", "opened_in": 1},
  "chapters": [
    {
      "claim": "語られている主張",
      "means": "平たく言うと何か。本当なら何が言えるか",
      "basis": "この話の元になった事実（資料にあるもの。無ければ空）",
      "question": "この章の問い",
      "method": "何を見れば決まるか",
      "verdict": "当たり|半分当たり|跡形なし|決まっていない",
      "verdict_line": "章の前半で言う結論の一文",
      "why": "なぜそう言えるかの一文",
      "origin": {"who": "最初に言い出した人", "year": "年", "how": "どう広まったか"},
      "swings": [
        {"stance": "肯定", "fact": "資料にある事実"},
        {"stance": "反転", "fact": "..."},
        {"stance": "留保", "fact": "..."}
      ],
      "evidence": {"year": "年", "where": "場所か媒体", "who": "誰", "what": "何が出たか"},
      "numbers": [{"value": "数字と単位", "caveat": "その数字への断り"}],
      "jargon": [{"term": "専門語", "landing": "日常の言い換え"}],
      "narrator": "私は〜（判断のみ、無ければ空）",
      "scope": "結論の範囲を限定する一文",
      "bearing": "大きな問いにとって、この章で分かったこと（平たく一文）",
      "figure": {"kind": "timeline|scale|none", "heading": "図の題", "items": [{"label": "...", "value": "数字と単位", "year": "年"}]},
      "hook_out": "次の章の話への問い（「では、〜なのか。」）"
    }
  ],
  "closing": {
    "answer": "mystery への答えを一文で",
    "generalization": ["題材を離れた文", "...", "..."],
    "callback": "planted_question への答え、または答えが出ない理由",
    "speculation": {"claim": "資料に無い私の考え", "reasons": ["理由1", "理由2"], "weakness": "この考察が崩れる条件"},
    "found": ["〜と分かった", "..."],
    "not_found": "だが〜は分かっていない",
    "open_questions": ["まだ分からないこと", "..."],
    "condition": "何が見つかれば決着するか（願望でなく条件）",
    "opening_callback": "冒頭の一文に戻る一文"
  }
}
"""


class PlanError(ValueError):
    """設計図の形が崩れている。"""


@dataclass
class Chapter:
    claim: str
    verdict: str
    verdict_line: str
    why: str
    origin: dict
    swings: list[dict]
    evidence: dict
    numbers: list[dict]
    jargon: list[dict]
    narrator: str
    scope: str
    hook_out: str
    question: str = ""
    method: str = ""
    means: str = ""          # 平たく言うと何か
    basis: str = ""          # 話の元になった事実
    bearing: str = ""        # 大きな問いにとって、この章で分かったこと
    figure: dict = field(default_factory=dict)


@dataclass
class Plan:
    thesis: str
    opening: dict
    planted_question: dict
    chapters: list[Chapter]
    closing: dict
    raw: dict = field(default_factory=dict)
    mystery: str = ""
    basics: dict = field(default_factory=dict)
    told: list[str] = field(default_factory=list)   # 冒頭で見せる、いま語られている形（動画タイトル）


def parse(text: str) -> dict:
    """LLMの出力からJSONを取り出す。囲みや前置きが付くことがある。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise PlanError("JSONが見つからない")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise PlanError(f"JSONとして読めない: {exc}") from exc


# 説明しない語。「AIは人工知能のことだ」「救世主とは、救い主のことだ」と書いた（死海文書）。
# 聞く側には分かりきっていて、説明の文が話の流れを切る
EVERYDAY = {"AI", "人工知能", "DNA", "遺伝子", "隠蔽", "救世主", "断片", "聖書", "写本", "巻物",
            "論文", "記録", "証拠", "陰謀", "陰謀論", "暗号", "解読", "宗教", "教会"}


def plain_terms(items: list, *, limit: int) -> list[dict]:
    """専門語の一覧から日常語を外し、limit 個までにする。"""
    out = []
    for j in items or []:
        t = _s((j or {}).get("term"))
        if t and t not in EVERYDAY:
            out.append(j)
    return out[:limit]


def _s(x) -> str:
    x = str(x or "").strip()
    return "" if x == "不明" else x


def validate(d: dict, *, n_claims: int | None = None) -> Plan:
    """形を確かめる。足りない章や振り子の無い章はここで落とす。

    書き始めてから足りないと分かると、章を全部書き直すことになる。
    """
    problems: list[str] = []
    thesis = _s(d.get("thesis"))
    if not thesis:
        problems.append("thesis が無い")
    opening = d.get("opening") or {}
    for key, what in (("what", "題材が何なのか"), ("significance", "なぜ大事なのか"),
                      ("curious", "語られている話に共通する点")):
        if not _s(opening.get(key)):
            problems.append(f"opening.{key}（{what}）が無い")
    basics = d.get("basics") or {}
    for key, what in (("found", "発見"), ("contents", "中身")):
        if not _s(basics.get(key)):
            problems.append(f"basics.{key}（{what}）が無い")
    basics = {**basics, "terms": plain_terms(basics.get("terms") or [], limit=3)}
    for t in basics.get("terms") or []:
        if _s(t.get("term")) and not _s(t.get("landing")):
            problems.append(f"basics の専門語「{t.get('term')}」に言い換えが無い")
    pq = d.get("planted_question") or {}
    mystery = _s(d.get("mystery") or pq.get("text"))
    if not mystery:
        problems.append("mystery（追う問い）が無い")
    if re.search(r"なぜ.*(謎|不明|分からない).*(残|続)", mystery):
        problems.append(f"mystery が抽象的（{mystery[:20]}）。具体的な問いにする")
    if not _s(pq.get("text")):
        pq = {"text": mystery, "opened_in": 1}

    chapters: list[Chapter] = []
    raw_chapters = d.get("chapters") or []
    for i, c in enumerate(raw_chapters, 1):
        swings = [s for s in (c.get("swings") or []) if _s(s.get("fact"))]
        stances = [s.get("stance") for s in swings]
        if len(swings) < 3:
            problems.append(f"第{i}章の swings が3つ無い")
        elif any(a == b for a, b in zip(stances, stances[1:])):
            problems.append(f"第{i}章の swings で同じ立場が続いている")
        for key, what in (("verdict_line", "結論"), ("question", "章の問い"),
                          ("means", "話を平たく言った一文"), ("bearing", "大きな問いにとっての意味")):
            if not _s(c.get(key)):
                problems.append(f"第{i}章の {key}（{what}）が無い")
        if not _s(c.get("hook_out")):
            problems.append(f"第{i}章の hook_out が無い")
        elif i < len(raw_chapters) and not re.search(r"(のか|だろうか|か)[。？?]?$", _s(c.get("hook_out"))):
            problems.append(f"第{i}章の hook_out が問いになっていない（「では、〜なのか。」で書く）")
        fig = c.get("figure") or {}
        if str(fig.get("kind") or "none") not in ("timeline", "scale", "none"):
            problems.append(f"第{i}章の figure.kind が timeline/scale/none でない")
        for j in c.get("jargon") or []:
            if _s(j.get("term")) and not _s(j.get("landing")):
                problems.append(f"第{i}章の専門語「{j.get('term')}」に言い換えが無い")
        narrator = _s(c.get("narrator"))
        if re.search(r"私[はもが].*?(読んだ|見た|数えた|測った|調べた|集めた|確認した|試した)", narrator):
            problems.append(f"第{i}章の narrator が行為になっている（判断だけにする）: {narrator[:30]}")
        chapters.append(Chapter(
            claim=_s(c.get("claim")),
            verdict=_s(c.get("verdict")),
            verdict_line=_s(c.get("verdict_line")),
            why=_s(c.get("why")),
            origin={k: v for k, v in (c.get("origin") or {}).items() if _s(v)},
            swings=swings,
            evidence={k: v for k, v in (c.get("evidence") or {}).items() if _s(v)},
            numbers=[n for n in (c.get("numbers") or []) if _s(n.get("value"))],
            jargon=plain_terms(c.get("jargon") or [], limit=2),
            narrator=narrator,
            scope=_s(c.get("scope")),
            hook_out=_s(c.get("hook_out")),
            question=_s(c.get("question")),
            method=_s(c.get("method")),
            means=_s(c.get("means")),
            basis=_s(c.get("basis")),
            bearing=_s(c.get("bearing")),
            figure=fig if str(fig.get("kind") or "none") != "none" else {}))
    if not chapters:
        problems.append("chapters が無い")
    if n_claims and len(chapters) != n_claims:
        problems.append(f"章が {len(chapters)} で主張の数 {n_claims} と違う")

    closing = d.get("closing") or {}
    # 「だが〜は分かっていない」に答えそのものを入れて繰り返した（死海文書）。同じなら空にする
    nf, ans = _s(closing.get("not_found")), _s(closing.get("answer"))
    if nf and ans and len(set(nf) & set(ans)) >= 0.8 * min(len(set(nf)), len(set(ans))):
        closing = {**closing, "not_found": "（答えと同じなので書かない）"}
    gen = [g for g in (closing.get("generalization") or []) if _s(g)]
    if len(gen) < 3:
        problems.append("closing.generalization が3文無い")
    for key in ("answer", "callback", "not_found", "condition", "opening_callback"):
        if not _s(closing.get(key)):
            problems.append(f"closing.{key} が無い")
    spec_ = closing.get("speculation") or {}
    if not _s(spec_.get("claim")):
        problems.append("closing.speculation.claim（考察）が無い")
    if len([r for r in (spec_.get("reasons") or []) if _s(r)]) < 2:
        problems.append("closing.speculation.reasons が2つ無い")
    if problems:
        raise PlanError("; ".join(problems))
    return Plan(thesis=thesis, opening=opening, planted_question=pq,
                chapters=chapters, closing=closing, raw=d,
                mystery=mystery, basics=basics)


def strip_unsourced(plan: Plan, material: str) -> list[str]:
    """設計図の numbers から、資料に無い数字を落とす。落としたものを返す。

    設計図の段階で作られた数字（「葉の数が7枚、茎の長さが17センチ」）は、
    そのまま章の指示に入り、本文に書かれる（v4 実測）。指示に入る前に消す。
    """
    have = set(re.findall(r"\d+(?:\.\d+)?", material))
    dropped: list[str] = []
    for c in plan.chapters:
        kept = []
        for n in c.numbers:
            nums = re.findall(r"\d+(?:\.\d+)?", str(n.get("value") or ""))
            if nums and any(x not in have for x in nums if len(x) > 1):
                dropped.append(str(n.get("value")))
            else:
                kept.append(n)
        c.numbers = kept
        fig = c.figure or {}
        if fig:
            items = []
            for it in fig.get("items") or []:
                nums = re.findall(r"\d+(?:\.\d+)?", f"{it.get('value', '')} {it.get('year', '')}")
                if nums and any(x not in have for x in nums if len(x) > 1):
                    dropped.append(f"図: {it.get('label', '')} {it.get('value', '')}{it.get('year', '')}")
                else:
                    items.append(it)
            need = 3 if fig.get("kind") == "timeline" else 2
            c.figure = {**fig, "items": items} if len(items) >= need else {}
    return dropped


def score(plan: Plan, material: str, *, subject: str = "") -> float:
    """設計図の良さを、資料への沿い方で点数にする。複数作って選ぶための物差し。

    見るのは「資料にある事実で組めているか」と「初見の人に要るものが揃っているか」
    だけ。文章の巧さは見ない（それは書いたあとに見る）。
    """
    pts = 0.0
    for c in plan.chapters:
        if c.basis:
            pts += 1.0                                  # 話の元が分かっている
        if any(_s(c.origin.get(k)) for k in ("who", "year")):
            pts += 0.5
        pts += 0.5 * len(c.numbers)                     # 残った数字は資料にあるもの（strip 済み）
        if c.narrator:
            pts += 0.5                                  # 判断を置いている
        if len(c.swings) >= 3:
            pts += 0.5
        if _s(c.evidence.get("year")):
            pts += 0.5
    b = plan.basics
    pts += sum(1.0 for k in ("found", "contents", "dating", "after") if _s(b.get(k)))
    pts += min(2, len([x for x in b.get("seeds") or [] if _s(x)]))
    if re.search(r"\d", str(plan.opening.get("significance") or "")):
        pts += 0.5                                      # 大事さを数字か比較で言えている
    thesis = plan.thesis
    if subject and subject in thesis:
        pts -= 2.0                                      # 題材を離れていない
    if re.search(r"ではない。|ではなく|で決まる|によって決まる", thesis):
        pts += 1.0                                      # 仕組みを言う形
    return pts


# 資料のファイル（research pipeline の出力）には、一気書き用の文体と構成の指示も入っている。
# 構成は旧い型（「異様さの具体3つ」「謎の核」）で、設計図の型とぶつかる。設計図には事実だけ渡す
_NOT_MATERIAL = ("## 文体", "## 構成", "## 出力形式", "## 検証する主張")


def facts_only(material: str) -> str:
    out, skip = [], False
    for line in material.splitlines():
        if line.startswith("## "):
            skip = line.startswith(_NOT_MATERIAL)
        elif line.startswith("# "):
            continue                     # 題材・尺・形式は設計図のプロンプトが自分で言う
        if not skip:
            out.append(line)
    return "\n".join(out)


def prompt(material: str, *, subject: str, claims: list[str], duration_sec: float,
           kind: str = "bundle", mystery: str = "", claims_meta: list[dict] | None = None,
           told: list[str] | None = None) -> str:
    """設計図を書かせるプロンプト。material は research pipeline が出した
    資料入りのプロンプト（出典と数字入り記述と題材の記述が入っている）。"""
    order = ("主張は信頼度の順に並べる: 当たっていたもの → 当たっているが理由が違うもの → "
             "跡形もなくなるもの。先に視聴者の信念を肯定してから反転させる。"
             "ただし、前の章の結果から次の章の問いが自然に出る並びにする。"
             if kind == "bundle" else
             "章は時系列。後半の章ほど長くする。")
    lines = [PLAN_INSTRUCTIONS, "",
             f"# 題材: {subject}",
             f"# 尺: {duration_sec/60:.0f}分",
             f"# 形式: {'束ね型' if kind == 'bundle' else '旗艦型'}。{order}",
             "", "## 検証する主張（この数だけ章を作る）"]
    meta = {m.get("ja"): m for m in (claims_meta or [])}
    for i, c in enumerate(claims, 1):
        m = meta.get(c) or {}
        extra = "　".join(x for x in (f"語り手: {m.get('told_by')}" if m.get("told_by") else "",
                                    f"視聴者が気にする理由: {m.get('stakes')}" if m.get("stakes") else "") if x)
        lines.append(f"{i}. {c}" + (f"（{extra}）" if extra else ""))
    if mystery:
        lines += ["", "## 追う問い（題材の仕様から。これを mystery にする。話し言葉に直してよい）", mystery]
    if told:
        lines += ["", "## いま語られている形（動画のタイトル。opening.curious の手がかり）"]
        lines += [f"- {t}" for t in told[:10]]
    lines += ["", "## 資料（事実はここにあるものだけ）", facts_only(material).strip()]
    return "\n".join(lines)


def describe(plan: Plan) -> list[str]:
    """人が設計図を一目で見るための要約。"""
    out = [f"主題: {plan.thesis}",
           f"問い: {plan.mystery}",
           f"何なのか: {plan.opening.get('what', '')}",
           f"なぜ気になるのか: {plan.opening.get('curious', '')}"]
    for i, c in enumerate(plan.chapters, 1):
        stances = "→".join(str(s.get("stance")) for s in c.swings)
        out.append(f"第{i}章 [{c.verdict}] {c.claim[:30]}  振り子 {stances}"
                   f"  元 {'有' if c.basis else '無'}")
    out.append(f"答え: {plan.closing.get('answer', '')[:60]}")
    sp = plan.closing.get("speculation") or {}
    out.append(f"考察: {str(sp.get('claim', ''))[:60]}")
    return out
