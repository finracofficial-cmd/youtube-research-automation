"""初めて見る人として台本を読み、話についていけなくなる所を挙げさせる。

装置の数（結論を先に・引き・伏線）はそろっていても、死海文書の台本は「何を
言っているのか分からない」と言われた。題材が何なのかを言う前に噂の真偽に入り、
前置きの無い動画タイトルが差し込まれ、同じ結論が3回続いていた。どれも正規表現
では拾えない。聞き手の側から読ませて、分からない所を塊ごとに返させる。

  read(blocks, chat)          題材を名前しか知らない視聴者として1回読む
  notes_by_block(reading)     直しの指示にして塊へ配る
  repeats_across(blocks)      前の章と同じ事実の言い直し（これは機械で拾える）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from . import devices

Chat = Callable[[list[dict]], str]

KINDS = ("未説明", "飛躍", "宙づり", "重複", "ずれ", "意味不明")
# 直しても残ったら門を落とすもの。話の筋が追えなくなる種類
# 直しても残ったら門を落とす種類。話の筋が追えなくなるもの。
# 「未説明」は直しの指示には使うが門にはしない。点も数も、分かりにくいと言われた
# 旧台本と新台本で差が出なかった（どちらも 6〜7 点。人名や宗派名の指摘ばかり）
SEVERE = ("意味不明", "ずれ", "宙づり")

READER = """\
あなたは、この題材について名前しか知らない視聴者です。以下は動画のナレーション台本です。
上から順に、一度だけ耳で聞いたつもりで読んでください（読み返しはできません）。

## 1. 聞き終えたあとの理解を確かめる
次の問いに、台本に書かれていたことだけで答えてください。あなた自身の知識で補わない。
台本から分からなければ空文字にする。
found・contents・why_care・question は、第1章に入る前（[冒頭] と [基本]）だけを聞いた時点で答える。
章の中で初めて分かったことは使わない。視聴者は最初の数分で「何の話か」が掴めなければ離れる。
- found: この題材は、いつ・どこで見つかった（できた）ものか
- contents: 中に何が書かれている（何でできている）ものか
- why_care: なぜ今、人々が気にしているのか
- question: この動画が答えようとしている問い
- chapters: 章ごとに、何の話をしたか（topic）、その話は結局どうだったか（result）、
  次の章に移る理由が分かったか（why_next、最後の章は true）
- answer: 最後に出た、問いへの答え

## 2. 話についていけなくなる箇所を挙げる
挙げるのは次の種類だけです。
- 未説明: 何なのか言われる前に出てきた語・人・物・場所・出来事
- 飛躍: 前の文から話がつながらない。なぜその話になったのか分からない
- 宙づり: 「それ」「この話」「そのうちの一本」が何を指すか分からない
- 重複: 前に言ったことを同じ意味でもう一度言っている（別の章も含む）
- ずれ: 問いと、その後の答えが合っていない。章で言うと予告した話と中身が合っていない
- 意味不明: 文そのものの意味が取れない
細かい言い回しの好みは挙げない。1つの箇所は1回だけ挙げる。多くても15個まで。
説明の文そのもの（「〜とは〜のことだ」「〜と呼ばれる」）や、その場で説明が付いている語、
役割を添えて出てきた人名（「発掘を率いた考古学者の〜」）は「未説明」に挙げない。
「ここからは資料に無い。私の考えだ。」「ここまでが考察だ。」は番組の決まりなので挙げない。

出力はJSONだけ:
{"quiz": {"found": "", "contents": "", "why_care": "", "question": "",
          "chapters": [{"block": "第1章", "topic": "", "result": "", "why_next": true}], "answer": ""},
 "problems": [{"block": "段落の見出し（[第2章] なら 第2章）", "quote": "該当の文をそのまま（30字まで）",
  "kind": "未説明|飛躍|宙づり|重複|ずれ|意味不明", "why": "聞いていて何が分からないか",
  "fix": "どう言えば分かるか（具体的に）"}],
 "score": 0〜10 の数（初見で最後までついていけたか）,
 "summary": "全体の感想を一文"}
"""

_LABEL = {"opening": "冒頭", "basics": "基本", "closing": "着地"}
_DEFINING = re.compile(r"とは、?|と呼ばれ|のことだ|のことである|を指す")


def label(key: str) -> str:
    if key.startswith("chapter"):
        return f"第{key[len('chapter'):]}章"
    return _LABEL.get(key, key)


def key_of(lab: str, keys: list[str]) -> str | None:
    lab = re.sub(r"[\[\]［］\s]", "", lab or "")
    for k in keys:
        if label(k) == lab:
            return k
    m = re.search(r"(\d+)", lab)
    if m and f"chapter{m.group(1)}" in keys:
        return f"chapter{m.group(1)}"
    return None


@dataclass
class Problem:
    block: str          # 塊の key（opening / basics / chapter3 / closing）
    quote: str
    kind: str
    why: str
    fix: str


QUIZ = (("found", "いつ・どこで見つかったか"), ("contents", "何が書かれているか"),
        ("why_care", "なぜ人々が気にしているのか"), ("question", "動画が答える問い"),
        ("answer", "問いへの答え"))


@dataclass
class Reading:
    score: float
    problems: list[Problem] = field(default_factory=list)
    summary: str = ""
    quiz: dict = field(default_factory=dict)
    n_chapters: int = 0

    def severe(self) -> list[Problem]:
        return [p for p in self.problems if p.kind in SEVERE]

    def gaps(self) -> list[str]:
        """聞き終えた人が答えられなかった問い。これが空なら話の筋は伝わっている。"""
        if not self.quiz:
            return ["理解の確認が返ってこなかった"]
        out = [f"{what}が分からない" for key, what in QUIZ if not str(self.quiz.get(key) or "").strip()]
        chs = [c for c in self.quiz.get("chapters") or [] if isinstance(c, dict)]
        blank = [str(c.get("block") or i + 1) for i, c in enumerate(chs)
                 if not str(c.get("topic") or "").strip() or not str(c.get("result") or "").strip()]
        if self.n_chapters and len(chs) < self.n_chapters:
            out.append(f"章の中身を{len(chs)}/{self.n_chapters}章しか言えない")
        if blank:
            out.append("何の話で結局どうだったかが言えない章: " + "、".join(blank))
        jumps = [str(c.get("block") or i + 1) for i, c in enumerate(chs[:-1]) if c.get("why_next") is False]
        if len(jumps) >= 2:
            out.append("次の章に移る理由が分からない: " + "、".join(jumps))
        return out

    @property
    def clear(self) -> bool:
        """門。問いに答えられ（筋が伝わり）、意味の取れない文と問いのずれが残っていない。
        点（0〜10）は参考に出すだけ。旧台本と新台本で差が出なかった。"""
        return not self.gaps() and not self.severe()

    def lines(self) -> list[str]:
        out = [f"初見の読み: {self.score:.0f}/10  {self.summary}"]
        q = self.quiz or {}
        for key, what in QUIZ:
            out.append(f"  {what}: {str(q.get(key) or '（言えない）')[:60]}")
        for c in q.get("chapters") or []:
            if isinstance(c, dict):
                out.append(f"  {c.get('block', '')}: {str(c.get('topic') or '（言えない）')[:30]} → "
                           f"{str(c.get('result') or '（言えない）')[:40]}")
        gaps = self.gaps()
        if gaps:
            out.append("  伝わっていないこと: " + " / ".join(gaps))
        out += [f"  [{label(p.block)}] {p.kind}: 「{p.quote}」 — {p.why}" for p in self.problems]
        return out


def labelled(blocks) -> str:
    """塊を見出し付きで並べる。見出しは読み上げない前提で渡す。"""
    out = []
    for b in blocks:
        text = devices_text(b.text)
        if text.strip():
            out.append(f"[{label(b.key)}]\n{text.strip()}")
    return "\n\n".join(out)


def devices_text(text: str) -> str:
    return re.sub(r"〔\s*\d+(?:\s*[,、]\s*\d+)*\s*〕", "", text)


def _parse(raw: str) -> dict:
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0) if m else raw)
    except (json.JSONDecodeError, AttributeError):
        return {}


def read(blocks, chat: Chat, *, subject: str = "") -> Reading:
    """題材を名前しか知らない視聴者として1回読ませる。読めなければ点を付けない（0点）。"""
    keys = [b.key for b in blocks]
    msgs = [{"role": "system", "content": READER},
            {"role": "user", "content": (f"題材: {subject}\n\n" if subject else "") + labelled(blocks)}]
    d = _parse(chat(msgs))
    probs = []
    for x in d.get("problems") or []:
        k = key_of(str(x.get("block") or ""), keys)
        kind = str(x.get("kind") or "").strip()
        if not k or kind not in KINDS:
            continue
        quote = str(x.get("quote") or "")
        if kind == "未説明" and _DEFINING.search(quote):
            continue          # 説明している文を「未説明」と返してきた（実測で4件）
        probs.append(Problem(block=k, quote=quote[:40], kind=kind,
                             why=str(x.get("why") or "").strip(), fix=str(x.get("fix") or "").strip()))
    try:
        score = float(d.get("score"))
    except (TypeError, ValueError):
        score = 0.0
    quiz = d.get("quiz") if isinstance(d.get("quiz"), dict) else {}
    return Reading(score=score, problems=probs, summary=str(d.get("summary") or "").strip(),
                   quiz=quiz, n_chapters=sum(k.startswith("chapter") for k in keys))


def notes_by_block(reading: Reading, *, per_block: int = 5) -> dict[str, list[str]]:
    """指摘を、書き直しの指示として塊ごとに配る。理解の確認で答えられなかった所は、
    それを言うべき塊（見つかった経緯と中身は基本の章、気にする理由と問いは冒頭、
    答えは着地、章の中身と結論はその章）へ。"""
    out: dict[str, list[str]] = {}
    q = reading.quiz or {}
    if q:
        where = {"found": "basics", "contents": "basics", "why_care": "opening",
                 "question": "opening", "answer": "closing"}
        for key, what in QUIZ:
            if not str(q.get(key) or "").strip():
                out.setdefault(where[key], []).append(
                    f"初見の視聴者が、聞き終えても「{what}」を言えなかった。はっきり一文で言う")
        for i, c in enumerate(q.get("chapters") or []):
            if not isinstance(c, dict):
                continue
            k = key_of(str(c.get("block") or ""), [f"chapter{j}" for j in range(1, 30)])
            if k and (not str(c.get("topic") or "").strip() or not str(c.get("result") or "").strip()):
                out.setdefault(k, []).append("初見の視聴者が、この章が何の話で結局どうだったのかを言えなかった。"
                                             "章の頭で話を、章の終わりで結論を、はっきり一文ずつ言う")
    for p in reading.problems:
        notes = out.setdefault(p.block, [])
        if len(notes) < per_block:
            notes.append(f"初見の視聴者が分からなかった所（{p.kind}）: 「{p.quote}」— {p.why}"
                         + (f"。直し方: {p.fix}" if p.fix else ""))
    return out


def repeats_across(blocks, subject: str = "") -> dict[str, list[str]]:
    """前の塊（基本の章・前の章）と同じ事実を言い直している文。

    死海文書では「2021年のAI解析で、同じ巻物に2人の筆写者がいた」が2つの章に
    ほぼ同じ文で出た。聞き手には同じ話が戻ってきたように聞こえる。"""
    seen: list[str] = []
    out: dict[str, list[str]] = {}
    for b in blocks:
        if not (b.key == "basics" or b.key.startswith("chapter")):
            continue
        # 章の頭（「〜は、〜という話だ」）は前の章の引き（「では、〜なのか」）と同じ語になる。
        # それは言い直しではなく、つなぎ目なので見ない
        sents = [s for s in devices.split_sentences(devices_text(b.text).replace("\n", ""))
                 if len(s) >= 12 and "という話だ" not in s and not re.search(r"のか[。？]$", s)]
        if b.key.startswith("chapter"):
            dup = [s for s in sents if any(devices._similar(s, x, (subject,)) for x in seen)]
            if dup:
                out[b.key] = dup
        seen += sents
    return out
