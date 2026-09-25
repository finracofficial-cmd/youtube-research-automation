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

## 物語の形（ここが無いと、事実の一覧になる。実測: 死海文書の台本は理解しづらかった）
動画は1つの謎（mystery）を追う。冒頭で謎と、答えの候補（candidates）を全部見せる。
各主張は、本当ならどれか1つの候補を支える（主張の「支える候補」）。各章は主張を1つ
確かめ、崩れたらその候補の支えが1本減る。支えが全部崩れた候補は消える。章の終わりに
残る候補を、候補の名前で数える（so_far と remaining）。主張の名前で数えない。最終章で答えを出す。答えが出なければ「出ない」と言い、
そのうえで考察（speculation）を事実と分けて置く。視聴者は気になったものが解決する
ことを求めている。考察は資料に無い私の考えで、理由と、崩れる条件を付ける。

章の中は「問い → 何を見れば決まるか（method）→ 証拠 → 判定 → 残る候補」の順。
事実を並べない。なぜそれを見るのか、それが分かると何が決まるのかを先に言う。

## 守ること
- 語り手の行為を作らない。「私は全部読んだ」「1700件数えた」のような
  行為は書かない。語り手が出るのは判断だけ（「私は判断を保留する」
  「私はこの数字を疑っている」「私はこの説を採らない」）。
- 各章の verdict は「当たり／半分当たり（理由が違う）／跡形なし／決まっていない」
  のどれか。
- swings は肯定→反転→留保の順で最低3つ。同じ立場を続けない。
- jargon は本文に出す専門語ごとに、日常の言い換えを1つ付ける。
- mystery は視聴者が本当に気にしている具体的な問い（「バチカンは死海文書を隠したのか」）。
  「なぜ謎が残るのか」のような抽象は不可。planted_question は mystery と同じでよい。
- candidates は互いに排他的な短い答え、2〜4個、それぞれ16字まで（冒頭で読み上げる）。
  題材の仕様の候補が長ければ、意味を変えずに短くする。例（別の題材）:
  「人間が坂で運んだ」「その場で切った」「人間ではない」。各章の remaining は、その章のあとに残る
  候補を candidates の文字列のまま並べる。前の章より増やさない。最終章の remaining が答え。
- opening.paradox は、その題材で成り立たないはずのことが成り立っている一文
  （別の題材の例: 「600年間、誰も一文字も読めていない」「人もカメラも、まだ入っていない」）。
  数字か物で言う。評価語は使わない。
- opening.cheap_answers は、視聴者が思いつく安易な説明を2つ（「単に〜だから」）。冒頭で先に潰す。
- 各章の question は「この章の問い」、method は「何を見れば決まるか」、tests は
  「どの候補を試すか」、so_far は「残る候補」。
- figure は、その章の資料の数字で描ける図。年が3つ以上なら timeline、同じ単位の量が
  2つ以上なら scale。無ければ kind を "none"。資料に無い数字を図にしない。
- closing.answer は候補のどれが残ったか。残らなければ「残らない」と書く。
- closing.speculation は資料に無い私の考え。claim と reasons（2つ以上）と weakness（崩れる条件）。
- thesis は「なぜそうなるのか」への答えで、仕組みを言う一文。教訓や感想ではない。
  参考の形: 「AIの限界は賢さではない。答え合わせができるかどうかで決まっている。」
  題材名を含めない。
- opening.images は、その物が実際にどう見えるか（色・形・数・場所）。
  参考の形（別の題材の例）: 「人もカメラも入れていない空間」「真北を指す四つの面」。
  「謎の文書」「奇妙な絵」のような評価語は使わない。資料に見た目の記述が
  無ければ、資料にある数と物で書く。例をそのまま写さない。
- origin は資料から分かる範囲で。分からなければ "不明" と書き、章では
  「誰が最初に言い出したかは、記録が見つかっていない」と正直に言う。
- closing.open_questions は「まだ分からないこと」を分からないまま置く。
- 出力はJSONのみ。前後に文章を付けない。

## JSONの形
{
  "thesis": "題材より大きい一文（題材名を含めない）",
  "mystery": "視聴者が本当に気にしている具体的な問い",
  "candidates": ["答えの候補A", "答えの候補B", "答えの候補C"],
  "opening": {
    "paradox": "成り立たないはずのことが成り立っている一文（数字か物で）",
    "images": ["画で見せられる具体（体言止め）", "...", "..."],
    "defeat": "挑んだ者は皆敗れた／決着していない、型の一文",
    "cheap_answers": ["安易な説明1", "安易な説明2"],
    "map": "何を何の順で確かめるか"
  },
  "planted_question": {"text": "最後まで保留する問い（mystery と同じでよい）", "opened_in": 1},
  "chapters": [
    {
      "claim": "語られている主張",
      "question": "この章の問い",
      "method": "何を見れば決まるか",
      "tests": "どの候補を試すか",
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
      "so_far": "この章のあとに残る候補を候補の名前で（「これでAを支える話が1つ崩れた。残るのはBとC」）",
      "remaining": ["この章のあとに残る候補（candidates の文字列をそのまま。前の章より増やさない）"],
      "figure": {"kind": "timeline|scale|none", "heading": "図の題", "items": [{"label": "...", "value": "数字と単位", "year": "年"}]},
      "hook_out": "次の章への引き。問いで書く（「では、〜なのか。」）"
    }
  ],
  "closing": {
    "generalization": ["題材を離れた文", "...", "...", "...", "..."],
    "answer": "候補のどれが残ったか。残らなければ「残らない」",
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
    tests: str = ""
    so_far: str = ""
    figure: dict = field(default_factory=dict)
    remaining: list[str] = field(default_factory=list)


@dataclass
class Plan:
    thesis: str
    opening: dict
    planted_question: dict
    chapters: list[Chapter]
    closing: dict
    raw: dict = field(default_factory=dict)
    mystery: str = ""
    candidates: list[str] = field(default_factory=list)
    told: dict = field(default_factory=dict)      # 主張 -> いま語られている形（動画タイトル）


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
    mystery = str(d.get("mystery") or pq.get("text") or "").strip()
    if not mystery:
        problems.append("mystery（追う問い）が無い")
    if re.search(r"なぜ.*(謎|不明|分からない).*(残|続)", mystery):
        problems.append(f"mystery が抽象的（{mystery[:20]}）。具体的な問いにする")
    if not str(pq.get("text") or "").strip():
        pq = {"text": mystery, "opened_in": 1}
    candidates = [str(x).strip() for x in (d.get("candidates") or []) if str(x).strip()]
    if len(candidates) < 2:
        problems.append("candidates（答えの候補）が2つ無い")
    long_c = [c for c in candidates if len(c) > 16]
    if long_c:
        problems.append("candidates が長い（冒頭で読み上げる。16字まで）: " + "、".join(long_c)[:80])
    if not str(opening.get("paradox") or "").strip():
        problems.append("opening.paradox が無い")

    chapters: list[Chapter] = []
    prev_rem = list(candidates)
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
        elif i < len(d.get("chapters") or []) and not re.search(r"(のか|だろうか|か)[。？?]?$", str(c.get("hook_out")).strip()):
            problems.append(f"第{i}章の hook_out が問いになっていない（「では、〜なのか。」で書く）")
        if not str(c.get("so_far") or "").strip():
            problems.append(f"第{i}章の so_far（残る候補）が無い")
        if not str(c.get("question") or "").strip():
            problems.append(f"第{i}章の question が無い")
        rem = [str(x).strip() for x in (c.get("remaining") or [])]
        if candidates and any(x not in candidates for x in rem):
            problems.append(f"第{i}章の remaining に候補でないものがある（主張の名前で数えている）: "
                            + "、".join(x for x in rem if x not in candidates)[:60])
        if candidates and i > 1 and set(rem) - set(prev_rem):
            problems.append(f"第{i}章の remaining が前の章より増えている")
        prev_rem = rem if rem else prev_rem
        fig = c.get("figure") or {}
        if str(fig.get("kind") or "none") not in ("timeline", "scale", "none"):
            problems.append(f"第{i}章の figure.kind が timeline/scale/none でない")
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
            hook_out=str(c.get("hook_out") or "").strip(),
            question=str(c.get("question") or "").strip(),
            method=str(c.get("method") or "").strip(),
            tests=str(c.get("tests") or "").strip(),
            so_far=str(c.get("so_far") or "").strip(),
            figure=(c.get("figure") or {}) if str((c.get("figure") or {}).get("kind") or "none") != "none" else {},
            remaining=[str(x).strip() for x in (c.get("remaining") or []) if str(x).strip()]))
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
    for key in ("callback", "not_found", "condition", "opening_callback", "answer"):
        if not str(closing.get(key) or "").strip():
            problems.append(f"closing.{key} が無い")
    spec_ = closing.get("speculation") or {}
    if not str(spec_.get("claim") or "").strip():
        problems.append("closing.speculation.claim（考察）が無い")
    if len([r for r in (spec_.get("reasons") or []) if str(r).strip()]) < 2:
        problems.append("closing.speculation.reasons が2つ無い")
    if problems:
        raise PlanError("; ".join(problems))
    return Plan(thesis=thesis, opening=opening, planted_question=pq,
                chapters=chapters, closing=closing, raw=d,
                mystery=mystery, candidates=candidates)


_FALLS = ("跡形なし",)
_VERDICT_SHORT = {"当たり": "当たり", "半分当たり": "理由が違う", "決まっていない": "分かっていない", "跡形なし": "跡形なし"}


def _map_candidate(long: str, spec_cands: list[str], plan_cands: list[str]) -> str | None:
    """仕様の候補（長い）を、設計図の候補（短く言い直したもの）に対応させる。
    数が同じなら順番で、違えば文字2連の重なりで。"""
    long = (long or "").strip()
    if long in plan_cands:
        return long
    if long in spec_cands and len(spec_cands) == len(plan_cands):
        return plan_cands[spec_cands.index(long)]
    def grams(t: str) -> set[str]:
        t = re.sub(r"[\s、。「」『』]", "", t)
        return {t[i:i + 2] for i in range(len(t) - 1)}
    g = grams(long)
    best = max(plan_cands, key=lambda c: len(g & grams(c)), default=None)
    return best if best and g & grams(best) else None


def settle(plan: Plan, supports: dict[str, str], spec_candidates: list[str] | None = None) -> list[list[str]]:
    """章ごとの残る答えを、判定と「支える答え」から計算して設計図に書き込む。

    モデルに消させると判断がちぐはぐになった（死海文書: DNAの章で最も妥当な
    「内容は既知と同じ」を消し、最後の答えが俗説の「秘密の記述がある」になった）。
    判定は各章で安定して出ていて本文にも機械的に入るので、そこから数える。

      答えは、それを支える話が全部確かめられて全部「跡形なし」になったら消える。
      支える話が1つも無い答えは章では消えない。最後に何も残らなければ、支える話の
      無い答え（ふつうは「何も無い」側）が残る。
    戻り値は章ごとの残る答え。chapters[k].remaining / so_far と closing.answer を上書きする。
    """
    cands = list(plan.candidates)
    if len(cands) < 2:
        return []
    spec_candidates = list(spec_candidates or [])
    backs: dict[str, list[int]] = {c: [] for c in cands}
    for k, ch in enumerate(plan.chapters):
        target = _map_candidate(supports.get(ch.claim, ""), spec_candidates, cands)
        if target:
            backs[target].append(k)
    fell = [ch.verdict in _FALLS for ch in plan.chapters]
    rows: list[list[str]] = []
    prev = list(cands)
    for k, ch in enumerate(plan.chapters):
        alive = [c for c in cands
                 if not (backs[c] and all(j <= k for j in backs[c]) and all(fell[j] for j in backs[c]))]
        target = next((c for c in cands if k in backs[c]), None)
        gone = [c for c in prev if c not in alive]
        if gone:
            head = "これで" + "、".join(f"『{c}』" for c in gone) + "を支える話は、全て崩れた。"
        elif target and fell[k]:
            head = f"これで『{target}』を支える話が、1つ崩れた。"
        elif target:
            head = f"『{target}』を支える話は、{_VERDICT_SHORT.get(ch.verdict, ch.verdict)}として残った。"
        else:
            head = ""
        ch.remaining = alive
        ch.so_far = head + "残る答えは" + "、".join(f"『{c}』" for c in alive) + "だ。"
        rows.append(alive)
        prev = alive
    final = rows[-1] if rows else []
    standing = [c for c in final if backs[c] and not all(fell[j] for j in backs[c])]
    if not standing:
        standing = [c for c in final if not backs[c]] or final
    plan.closing["answer"] = ("答えは『" + standing[0] + "』だ。" if len(standing) == 1 else
                              "答えは一つに絞れない。残るのは" + "、".join(f"『{c}』" for c in standing) + "だ。")
    if rows:
        rows[-1] = standing
        plan.chapters[-1].remaining = standing
    for ch in plan.chapters:
        for c in plan.raw.get("chapters") or []:
            if c.get("claim") == ch.claim:
                c["remaining"], c["so_far"] = ch.remaining, ch.so_far
    plan.raw.setdefault("closing", {})["answer"] = plan.closing["answer"]
    return rows


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


_EVALUATIVE = re.compile(r"謎|奇妙|不思議|驚|美し|神秘|異様|恐ろし|衝撃")


def score(plan: Plan, material: str, *, subject: str = "") -> float:
    """設計図の良さを、資料への沿い方で点数にする。複数作って選ぶための物差し。

    見るのは「資料にある事実で組めているか」だけ。文章の巧さは見ない
    （それは書いたあとに devices が見る）。
    """
    pts = 0.0
    for c in plan.chapters:
        o = c.origin or {}
        if any(str(o.get(k) or "").strip() not in ("", "不明") for k in ("who", "year")):
            pts += 1.0                                  # 出どころが分かっている
        pts += 0.5 * len(c.numbers)                     # 残った数字は資料にあるもの（strip 済み）
        if c.narrator:
            pts += 0.5                                  # 判断を置いている
        if len(c.swings) >= 3:
            pts += 0.5
        ev = c.evidence or {}
        if str(ev.get("year") or "").strip() not in ("", "不明"):
            pts += 0.5
    for img in (plan.opening.get("images") or [])[:3]:
        img = str(img)
        if not _EVALUATIVE.search(img):
            pts += 1.0                                  # 評価語でなく物で書けている
        if re.search(r"\d", img):
            pts += 0.5
    thesis = plan.thesis
    if subject and subject in thesis:
        pts -= 2.0                                      # 題材を離れていない
    if re.search(r"ではない。|ではなく|で決まる|によって決まる", thesis):
        pts += 1.0                                      # 仕組みを言う形
    return pts


def prompt(material: str, *, subject: str, claims: list[str], duration_sec: float,
           kind: str = "bundle", mystery: str = "", candidates: list[str] | None = None,
           claims_meta: list[dict] | None = None) -> str:
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
    meta = {m.get("ja"): m for m in (claims_meta or [])}
    for i, c in enumerate(claims, 1):
        m = meta.get(c) or {}
        extra = "　".join(x for x in (f"語り手: {m.get('told_by')}" if m.get("told_by") else "",
                                    f"視聴者が気にする理由: {m.get('stakes')}" if m.get("stakes") else "",
                                    f"本当なら支える候補: {m.get('supports')}" if m.get("supports") else "") if x)
        lines.append(f"{i}. {c}" + (f"（{extra}）" if extra else ""))
    if mystery:
        lines += ["", f"## 追う問い（題材の仕様から。これを mystery にする）", mystery]
        if candidates:
            lines += ["答えの候補: " + " / ".join(candidates)]
    lines += ["", "## 資料（事実はここにあるものだけ）", material.strip()]
    return "\n".join(lines)


def describe(plan: Plan) -> list[str]:
    """人が設計図を一目で見るための要約。"""
    out = [f"主題: {plan.thesis}",
           f"謎: {plan.mystery}  候補: {' / '.join(plan.candidates)}",
           f"伏線: {plan.planted_question.get('text', '')}"]
    for i, c in enumerate(plan.chapters, 1):
        stances = "→".join(str(s.get("stance")) for s in c.swings)
        out.append(f"第{i}章 [{c.verdict}] {c.claim[:30]}  振り子 {stances}"
                   f"  出どころ {c.origin.get('who', '不明')}/{c.origin.get('year', '不明')}")
    out.append(f"回収: {plan.closing.get('callback', '')[:60]}")
    sp = plan.closing.get("speculation") or {}
    out.append(f"考察: {str(sp.get('claim', ''))[:60]}")
    return out
