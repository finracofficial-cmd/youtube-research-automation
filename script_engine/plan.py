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
数字・人名・年は書きません。分からないことは "不明" と書きます。

## 参考にする章の手順（ピラミッド回 第5章の分解）
1 問い → 2 結論を先に言う → 3 なぜそう言えるか → 4 専門語は日常語に着地 →
5 候補と留保（ただし） → 6 通説を通説の言葉で言わせる → 7 反転 →
8 新しい証拠（年・場所・誰） → 9 数字と、その数字への断り →
10 結論の範囲を限定（「答えが出た」ではなく「〜というところまで」）→
11 次の章への引き（問い、または次の説をそのまま提示）

## 守ること
- 語り手の行為を作らない。「私は全部読んだ」「1700件数えた」のような
  行為は書かない。語り手が出るのは判断だけ（「私は判断を保留する」
  「私はこの数字を疑っている」「私はこの説を採らない」）。
- 各章の verdict は「当たり／半分当たり（理由が違う）／跡形なし／決まっていない」
  のどれか。
- swings は肯定→反転→留保の順で最低3つ。同じ立場を続けない。
- jargon は本文に出す専門語ごとに、日常の言い換えを1つ付ける。
- planted_question は1章か2章で開き、最終章で回収する問い。
- thesis は「なぜそうなるのか」への答えで、仕組みを言う一文。教訓や感想ではない。
  参考の形: 「AIの限界は賢さではない。答え合わせができるかどうかで決まっている。」
  題材名を含めない。
- opening.images は、その物が実際にどう見えるか（色・形・数・場所）。
  参考の形: 「緑色の水に浸かった裸の女性たち」「同心円に描かれた星」。
  「謎の文書」「奇妙な絵」のような評価語は使わない。資料に見た目の記述が
  無ければ、数と物（「240枚の羊皮紙」「3万3千の文字」）で書く。
- origin は資料から分かる範囲で。分からなければ "不明" と書き、章では
  「誰が最初に言い出したかは、記録が見つかっていない」と正直に言う。
- closing.open_questions は「まだ分からないこと」を分からないまま置く。
- 出力はJSONのみ。前後に文章を付けない。

## JSONの形
{
  "thesis": "題材より大きい一文（題材名を含めない）",
  "opening": {
    "images": ["画で見せられる具体（体言止め）", "...", "..."],
    "defeat": "挑んだ者は皆敗れた／決着していない、型の一文",
    "map": "何を何の順で確かめるか"
  },
  "planted_question": {"text": "最後まで保留する問い", "opened_in": 1},
  "chapters": [
    {
      "claim": "語られている主張",
      "verdict": "当たり|半分当たり|跡形なし|決まっていない",
      "verdict_line": "章の冒頭で言う結論の一文",
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
      "hook_out": "次の章への引き（問い、または次の説をそのまま提示）"
    }
  ],
  "closing": {
    "generalization": ["題材を離れた文", "...", "...", "...", "..."],
    "callback": "planted_question への答え、または答えが出ない理由",
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


@dataclass
class Plan:
    thesis: str
    opening: dict
    planted_question: dict
    chapters: list[Chapter]
    closing: dict
    raw: dict = field(default_factory=dict)


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


def validate(d: dict, *, n_claims: int | None = None) -> Plan:
    """形を確かめる。足りない章や振り子の無い章はここで落とす。

    書き始めてから足りないと分かると、章を全部書き直すことになる。
    """
    problems: list[str] = []
    thesis = str(d.get("thesis") or "").strip()
    if not thesis:
        problems.append("thesis が無い")
    opening = d.get("opening") or {}
    if len([x for x in (opening.get("images") or []) if str(x).strip()]) < 3:
        problems.append("opening.images が3つ無い")
    if not str(opening.get("defeat") or "").strip():
        problems.append("opening.defeat が無い")
    pq = d.get("planted_question") or {}
    if not str(pq.get("text") or "").strip():
        problems.append("planted_question が無い")

    chapters: list[Chapter] = []
    for i, c in enumerate(d.get("chapters") or [], 1):
        swings = [s for s in (c.get("swings") or []) if str(s.get("fact") or "").strip()]
        stances = [s.get("stance") for s in swings]
        if len(swings) < 3:
            problems.append(f"第{i}章の swings が3つ無い")
        elif any(a == b for a, b in zip(stances, stances[1:])):
            problems.append(f"第{i}章の swings で同じ立場が続いている")
        if not str(c.get("verdict_line") or "").strip():
            problems.append(f"第{i}章の verdict_line が無い")
        if not str(c.get("hook_out") or "").strip():
            problems.append(f"第{i}章の hook_out が無い")
        for j in c.get("jargon") or []:
            if str(j.get("term") or "").strip() and not str(j.get("landing") or "").strip():
                problems.append(f"第{i}章の専門語「{j.get('term')}」に言い換えが無い")
        narrator = str(c.get("narrator") or "").strip()
        if re.search(r"私[はもが].*?(読んだ|見た|数えた|測った|調べた|集めた|確認した|試した)", narrator):
            problems.append(f"第{i}章の narrator が行為になっている（判断だけにする）: {narrator[:30]}")
        chapters.append(Chapter(
            claim=str(c.get("claim") or "").strip(),
            verdict=str(c.get("verdict") or "").strip(),
            verdict_line=str(c.get("verdict_line") or "").strip(),
            why=str(c.get("why") or "").strip(),
            origin=c.get("origin") or {},
            swings=swings,
            evidence=c.get("evidence") or {},
            numbers=[n for n in (c.get("numbers") or []) if str(n.get("value") or "").strip()],
            jargon=[j for j in (c.get("jargon") or []) if str(j.get("term") or "").strip()],
            narrator=narrator,
            scope=str(c.get("scope") or "").strip(),
            hook_out=str(c.get("hook_out") or "").strip()))
    if not chapters:
        problems.append("chapters が無い")
    if n_claims and len(chapters) != n_claims:
        problems.append(f"章が {len(chapters)} で主張の数 {n_claims} と違う")

    closing = d.get("closing") or {}
    gen = [g for g in (closing.get("generalization") or []) if str(g).strip()]
    if len(gen) < 5:
        problems.append("closing.generalization が5文無い")
    if any(re.search(r"[A-Za-z]{3,}", g) for g in gen) is False:
        pass
    for key in ("callback", "not_found", "condition", "opening_callback"):
        if not str(closing.get(key) or "").strip():
            problems.append(f"closing.{key} が無い")
    if problems:
        raise PlanError("; ".join(problems))
    return Plan(thesis=thesis, opening=opening, planted_question=pq,
                chapters=chapters, closing=closing, raw=d)


def prompt(material: str, *, subject: str, claims: list[str], duration_sec: float,
           kind: str = "bundle") -> str:
    """設計図を書かせるプロンプト。material は research pipeline が出した
    資料入りのプロンプト（出典と数字入り記述が入っている）。"""
    order = ("主張は信頼度の順に並べる: 当たっていたもの → 当たっているが理由が違うもの → "
             "跡形もなくなるもの。先に視聴者の信念を肯定してから反転させる。"
             if kind == "bundle" else
             "章は時系列。後半の章ほど長くする。")
    lines = [PLAN_INSTRUCTIONS, "",
             f"# 題材: {subject}",
             f"# 尺: {duration_sec/60:.0f}分",
             f"# 形式: {'束ね型' if kind == 'bundle' else '旗艦型'}。{order}",
             "", "## 検証する主張（この数だけ章を作る）"]
    lines += [f"{i}. {c}" for i, c in enumerate(claims, 1)]
    lines += ["", "## 資料（事実はここにあるものだけ）", material.strip()]
    return "\n".join(lines)


def describe(plan: Plan) -> list[str]:
    """人が設計図を一目で見るための要約。"""
    out = [f"主題: {plan.thesis}",
           f"伏線: {plan.planted_question.get('text', '')}"]
    for i, c in enumerate(plan.chapters, 1):
        stances = "→".join(str(s.get("stance")) for s in c.swings)
        out.append(f"第{i}章 [{c.verdict}] {c.claim[:30]}  振り子 {stances}"
                   f"  出どころ {c.origin.get('who', '不明')}/{c.origin.get('year', '不明')}")
    out.append(f"回収: {plan.closing.get('callback', '')[:60]}")
    return out
