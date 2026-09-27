"""台本から題名の候補を起こす。

参考chの実測（3本）で、当たった題と外れた題の形が違う。

  140万回  【AI解析でどこまで分かったのか】奇書ヴォイニッチ手稿解読の600年
   4.7万回  ピラミッドの謎を、論文と1次資料でひも解く【AIが発見した？地下がある？宇宙人が作った？】
   1.3万回  橋本環奈の息分子を175億個吸ってた件【分子論×確率論】

当たった方だけが持っているもの:
  1. 括弧の中が「どこまで分かったのか」という、知識の限界についての問い
  2. 固有名詞が題の中にある（検索で拾われる）
  3. 数字が入っている（600年）

外れた方は、括弧の中が問いの列挙（？が3つ）か、分野名だけだった。

ここで作るのは候補で、選ぶのは人。台本が結論していないことは書かない。
「4つが崩れた」と出すには、台本の締めで4つ崩れている必要がある。
"""
from __future__ import annotations

import re

# 締めで主張が退けられている言い回し。数えて題に使う。
_REFUTED = re.compile(
    r"(根拠を失|裏付(?:け)?が(?:ない|無い)|ではなく|確認されていない|"
    r"否定され|成り立たない|支持されていない|誤りだ|事実ではな)")
# 締めで主張が残っている言い回し。
_HELD = re.compile(r"(と分かった|と判明|確かめられた|裏付けられた|一致した)")

# 題材の分野。【分野×分野】の形に使う。台本に出てくる語だけ拾う。
_FIELDS = (
    ("年代測定", re.compile(r"放射性炭素|年代測定|炭素14")),
    ("言語統計", re.compile(r"統計|エントロピー|語頻度|言語学")),
    ("古文書学", re.compile(r"写本|筆跡|インク|羊皮紙|古文書")),
    ("植物学", re.compile(r"植物|薬草|図譜")),
    ("考古学", re.compile(r"発掘|遺跡|出土|考古")),
    ("地質学", re.compile(r"岩石|地質|鉱物|組成")),
    ("天文学", re.compile(r"天文|星|日の出|夏至")),
    ("工学", re.compile(r"歯車|機構|加工|冶金|鋳造")),
)


def closing(script: str, n: int = 3) -> str:
    """台本の締め。結論はここに書かれている。"""
    parts = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]
    return "\n".join(parts[-n:])


def tally(script: str) -> tuple[int, int]:
    """締めで、退けられた主張と残った主張をそれぞれ数える。"""
    down = up = 0
    for line in closing(script).splitlines():
        if not line.strip():
            continue
        if _REFUTED.search(line):
            down += 1
        elif _HELD.search(line):
            up += 1
    return down, up


def fields(script: str, limit: int = 3, least: int = 2) -> list[str]:
    """台本で2回以上触れている分野だけ。

    1回出ただけの語を拾うと、題に無関係な分野が入る。実測で巨石遺跡の題に
    「植物学」が入った。通りすがりの一語で分野を名乗ることになる。
    """
    return [name for name, pat in _FIELDS
            if len(pat.findall(script)) >= least][:limit]


# 題材を一言で評する語。台本の冒頭に出ていればそれを使う。
# 参考chの当たった題は「奇書」を付けていた。評価語が1つあるだけで、
# 題材の名前が「物」から「見るべきもの」になる。
_EPITHET = (
    ("奇書", re.compile(r"奇書|謎の書物|書物")),
    ("未解読の", re.compile(r"未解読(?!部分|の部分|の断片)")),   # 「未解読部分が残る」では付けない
    ("謎の", re.compile(r"謎|不可解|説明がつかない")),
)

# 期間。「未解読のまま600年近く」のような、題材が抱えている時間の長さ。
# 参考chの当たった題は「解読の600年」で締めていた。
#
# 期間の印（近く・以上・間・前…）を必須にする。印が無い4桁は西暦で、
# 期間ではない。実測で「1912年に発見され」から「1912年、誰も読めていない」
# という題が出た。西暦を期間として出すと、題が事実と食い違う。
_SPAN = re.compile(
    r"([0-9０-９]{2,4})\s*年(?:近く|以上|間|余り|にわたって|もの間|前)"
    r"(?=[^。]{0,20}(?:残|経|続|未解読|不明|解けて|読めて|分かって|わたって))")

# 締めで一番強い否定。これが題の先頭に立つと、何が崩れたかが一目で分かる。
_STRONG = re.compile(r"^(?P<head>[^、。]{2,22})(?:は|が)[^。]*?"
                     r"(?P<verdict>根拠を失|ではなく|裏付(?:け)?が(?:ない|無い)"
                     r"|確認されていない|実在するものではな)")


def epithet(script: str) -> str:
    head = "\n".join(script.splitlines()[:12])
    for word, pat in _EPITHET:
        if pat.search(head):
            return word
    return ""


def span(script: str) -> str:
    """台本が言っている期間のうち、一番長いもの。"""
    got = [int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
           for m in _SPAN.finditer(script)]
    return f"{max(got)}年" if got else ""


def strongest(script: str) -> tuple[str, str]:
    """締めで一番はっきり否定されている主張。(主語, 何と分かったか)"""
    for line in closing(script).splitlines():
        m = _STRONG.search(line.strip())
        if m:
            return m.group("head"), m.group("verdict")
    return "", ""


def propose(subject: str, claims: list, script: str) -> list[str]:
    """題名の候補。上ほど参考chの当たった型に近い。"""
    n = len(claims)
    down, up = tally(script)
    name = f"{epithet(script)}{subject}"
    years = span(script)
    out: list[str] = []

    # 1. 当たった型。括弧に「その時間ずっと解けていない」、本体に評価語と
    #    固有名詞、締めに残ったものの少なさ
    if years and up:
        out.append(f"【{years}、誰も読めていない】{name}に残った"
                   + ("唯一の確かなこと" if up == 1 else f"{up}つの確かなこと"))
    elif years:
        out.append(f"【{years}、答えが出ていない】{name}はどこまで分かったのか")
    else:
        out.append(f"【どこまで分かっているのか】{name}、{n}つの通説を確かめる")

    # 2. 一番はっきり崩れた話を先頭に立てる型
    head, verdict = strongest(script)
    # 括弧が長いと題として読めない。実測で51字の題が出た
    if len(head) > 14:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
        from chapters import subject_of
        head = subject_of(head, limit=14)
    lead = {"根拠を失": f"{head}は根拠を失った",
            "ではなく": f"{head}は思われていたものではなかった",
            "実在するものではな": f"{head}は実在しなかった",
            "裏付が": f"{head}に裏付けはなかった",
            "裏付けが": f"{head}に裏付けはなかった",
            "確認されていない": f"{head}は確認されていない"}.get(verdict, "")
    if lead and down:
        out.append(f"【{lead}】{name}、{years or str(n) + 'つ'}で崩れた{down}つの通説")
    elif lead:
        out.append(f"【{lead}】{name}をもう一度確かめる")
    else:
        out.append(f"【一次資料で確かめる】{name}はどこまで本当か")

    # 3. このchの既存の型（〜のか【分野×分野】）。「解けていない」は台本がそう言っている
    #    題材だけ。死海文書（読まれている写本）に「なぜ解けていないのか」と付けた（実測）
    fs = fields(script)
    tail = f"【{'×'.join(fs)}】" if len(fs) >= 2 else "【論文と一次資料】"
    if _UNSOLVED.search(script):
        out.append(f"{name}は{'なぜ' if not years else years + 'も'}解けていないのか{tail}")
    else:
        out.append(f"{name}の噂はどこまで本当か{tail}")
    return out


# 題材そのものが解けていないと言う形だけ。「未解読部分が残る」（断片の一部が読めていない）は
# 題材が解けていないことにはならない（死海文書）
_UNSOLVED = re.compile(r"未解読(?!部分|の部分|の断片)|解読されていない|誰も読めていない|誰も読めない|解けていない")


def held_fact(script: str, limit: int = 30) -> str:
    """締めで「分かった」と言い切っている中身。冒頭の逆説に使う。"""
    for line in closing(script).splitlines():
        line = line.strip()
        if not line or _REFUTED.search(line) or not _HELD.search(line):
            continue
        body = re.sub(r"^(?:調べた結果|検証の結果|その結果)[、,]?", "", line)
        body = re.sub(r"(?:と(?:分かった|判明した|確かめられた))。?$", "", body)
        return body.rstrip("。 ")[:limit]
    return ""


def intro(subject: str, claims: list, script: str, duration_sec: float = 0.0) -> str:
    """概要欄の冒頭。YouTubeが「もっと見る」の前に出す数行。

    参考chの概要欄は4拍だった:
      1 逆説の提示        600年のあいだ、誰も一文字も読めていない本があります
      2 それでも分かっている事  それなのに、羊皮紙の年も、書いた人数も分かっています
      3 方法と尺          一次資料だけで52分かけて辿りました
      4 成果の予告        都市伝説で語られている内容のほとんどは否定されます

    ここが一番読まれる場所なのに、どの動画でも同じ定型文を置いていた。
    台本が結論していないことは書かない。
    """
    n = len(claims)
    down, up = tally(script)
    name = f"{epithet(script)}{subject}"
    years = span(script)
    held = held_fact(script)
    mins = int(round(duration_sec / 60)) if duration_sec else 0

    lines: list[str] = []
    # 1 逆説
    if years:
        lines.append(f"{years}のあいだ、答えの出ていない{name}があります。")
    else:
        lines.append(f"{name}をめぐっては、いくつもの説が語られてきました。")
    # 2 それでも分かっていること
    if held:
        lines.append(f"それでも、{held}ことは分かっています。")
    # 3 方法と尺
    how = "一次資料と論文だけで"
    lines.append(f"何が分かっていて、何が分かっていないのか。"
                 + (f"{how}{mins}分かけて辿りました。" if mins else f"{how}辿りました。"))
    # 4 成果の予告。台本が結論を書いていなければ、数だけ言って結果は言わない。
    # 説の数は題材の仕様から来るが、「いくつ崩れたか」は締めからしか取れない。
    if n:
        lines.append("")
        if down:
            lines.append(f"見ていくと分かりますが、広く語られている{n}つの説のうち"
                         f"{down}つは、資料と食い違います。")
        else:
            lines.append(f"広く語られている{n}つの説を、資料に当たって"
                         f"一つずつ確かめています。")
    return "\n".join(lines)


def render(subject: str, claims: list, script: str, *, plan: dict | None = None,
           market: dict | None = None) -> str:
    if market and market.get("lifts"):
        return render_market(subject, claims, script, plan, market)
    got = propose(subject, claims, script)
    lines = ["── 題名の候補 ──"]
    for i, t in enumerate(got, 1):
        mark = "  ← 参考chで当たった型に一番近い" if i == 1 else ""
        lines.append(f"{i}. {t}{mark}")
        lines.append(f"   {len(t)}字（スマホは28字前後で切れる）")
    lines.append("※選ぶのは人。台本が結論していないことは書いていない。")
    return "\n".join(lines)


# ---- 市場の数字を使う題名 ------------------------------------------------------
# 台本だけから作ると、市場で伸びている語を知らない（死海文書の自動案は
# 「【どこまで分かっているのか】死海文書、6つの通説を確かめる」で、伸びる語が一つも無かった）。
# topic_scout.market が数えた語の効き（平常比）を使い、台本が答えている語だけで組む。
#
#   どの案も「台本で言っていること」しか約束しない:
#     ・効く語は、台本の本文に出てくるものだけ使う
#     ・「判明しました」のような言い切りは使わない。問いの形にする（参考chの当たり
#       「【AI解析でどこまで分かったのか】…」も知識の限界を問う形）
#   点 = 入っている効く語の log(効き) の和 − 下がる語の分 + 型の点 − 長さの減点

import math as _math
from collections import Counter

_ASSERTIVE = re.compile(r"判明し(?:た|ました)|解明され|発見され|証明され|遂に|ついに明か")
_DOKOMADE = "どこまで分かったのか"
# 「〜の正体」「〜の真実」のように、効く語の前後の名詞まで含めてかぎ括弧で囲む
_NOUN = r"[一-龥ァ-ヶーA-Z]"


def _mterms(market: dict) -> tuple[list[dict], list[dict]]:
    from topic_scout.market import cold, hot
    return hot(market), cold(market)


def _hits(title: str, items: list[dict]) -> list[dict]:
    return [x for x in items if re.search(x["pattern"], title)]


def as_question(claim: str) -> str:
    """主張の文を問いにする。「〜とされている」「〜という説がある」は外してから。"""
    c = re.sub(r"[。．\s]+$", "", claim or "")
    c = re.sub(r"(?:とされている|とされる|という説がある|と言われている|と語られている)$", "", c)
    c = re.sub(r"である$", "", c)
    return c + ("なのか" if re.search(r"[一-龥ァ-ヶー]$", c) else "のか")


def _chapter_question(ch: dict) -> str:
    q = re.sub(r"[？?。]+$", "", str(ch.get("question") or "").strip())
    return q if q.endswith(("のか", "か")) else as_question(str(ch.get("claim") or ""))


def _quote_hot(q: str, hot: list[dict], subject: str) -> str:
    """問いの中のいちばん効く語を、前後の名詞ごと「」で囲む（「救世主の正体」）。"""
    stems = [subject] + [subject[:k] for k in range(len(subject) - 1, 2, -1)]
    for x in hot:
        if not re.search(r"[一-龥ァ-ヶーA-Z]", x["term"]) or any(s in x["term"] for s in stems):
            continue
        # 前後に続く名詞ごと取る。「未解読」の「解読」だけ囲むと「未「解読…」」になった（実測）
        m = re.search(rf"(?:{_NOUN}{{1,6}}の)?{_NOUN}*(?:{x['pattern']}){_NOUN}*(?:の{_NOUN}{{1,4}})?", q)
        if not m:
            continue
        phrase = m.group(0)
        for s in stems:
            if phrase.startswith(s + "の"):
                phrase = phrase[len(s) + 1:]
        if 2 <= len(phrase) <= 10 and "「" not in q and not any(phrase == s for s in stems):
            return q.replace(phrase, f"「{phrase}」", 1)
    return q


def _lead_subject(q: str, subject: str) -> str:
    """問いの頭を題材名にする。「手稿は〜」のように題材名の後ろ半分で始まっていれば
    題材名に置き換え、どこにも無ければ「題材名、」を前に付ける。"""
    if q.startswith(subject):
        return q
    for k in range(1, len(subject) - 1):
        tail = subject[k:]
        if len(tail) >= 2 and q.startswith(tail):
            return subject + q[len(tail):]
    return q if subject in q else f"{subject}、{q}"


def _methods(script: str, plan: dict, hot: list[dict]) -> str:
    """題の括弧に入れる方法（AI・DNA）。章の主張に出てくる略語を、効く順に2つまで。"""
    claims = " ".join(str(c.get("claim") or "") for c in (plan or {}).get("chapters") or [])
    acr = []
    for w in re.findall(r"[A-Z]{2,}", claims):
        if w not in acr and w in script:
            acr.append(w)
    rank = {x["term"]: x.get("adj", x["lift"]) for x in hot}
    acr.sort(key=lambda w: -rank.get(w, 1.0))
    return "・".join(acr[:2])


def _label(claim: str, subject: str, limit: int = 10) -> str | None:
    """括弧に並べる短い名前（「救世主の正体」「バチカンが隠した」）。語の途中で切るくらいなら
    None（「手稿は未解読の自然言」のような切れ端が出た）。"""
    c = re.sub(r"[。．]+$", "", claim)
    c = re.sub(r"(?:とされている|とされる|という説がある|と言われている)$", "", c)
    for k in range(0, len(subject) - 1):
        c = re.sub(re.escape(subject[k:]) + r"(?:には|に|の|を|は|が|で)?", "", c) if len(subject[k:]) >= 2 else c
    c = c.strip("、 ")
    if len(c) > limit and "のは" in c:
        c = c.split("のは", 1)[1]
    if len(c) > limit and "が" in c:
        c = c.split("が", 1)[0]
    c = re.sub(r"(?:である|だ)$", "", c)
    return c if 2 <= len(c) <= limit else None


def _hook_chapter(plan: dict, hot: list[dict]) -> int | None:
    """市場でいちばん効く語を含む章。題で約束する話になる。"""
    from topic_scout.market import hook_index
    texts = [f"{c.get('claim', '')} {c.get('question', '')}" for c in (plan or {}).get("chapters") or []]
    return hook_index(texts, {"lifts": hot})


def _surprise(script: str, subject: str, limit: int = 34) -> str:
    """台本の前半にある、数字の入った意外な一文（「〜より、1,000年も古い」）。"""
    body = [p for p in re.split(r"\n\s*\n", script) if p.strip()]
    for para in body[: max(3, len(body) // 2)]:
        for s in re.split(r"(?<=。)", para.replace("\n", "")):
            s = s.strip()
            if re.search(r"\d", s) and re.search(r"だけ|しか|も古い|も前|倍|以上前", s) and len(s) <= limit:
                return re.sub(r"[。、]+$", "", s).replace("、", "")
    return ""


def score_title(title: str, market: dict, subject: str) -> tuple[float, list[dict], list[dict]]:
    hot, cold = _mterms(market)
    h, c = _hits(title, hot), _hits(title, cold)
    # 効く語を並べるほど足し算で点が上がるが、約束は1つのほうが強い。参考chで、括弧に問いを
    # 3つ並べた題（ピラミッド 3.3万回）は、問いが1つの題（ヴォイニッチ 140万回）に負けた。
    # 2つ目からは半分ずつしか数えない
    gains = sorted((_math.log(x.get("adj", x["lift"])) for x in h), reverse=True)
    pts = sum(g * 0.5 ** k for k, g in enumerate(gains))
    pts -= sum(abs(_math.log(max(x.get("adj", x["lift"]), 0.05))) for x in c)
    if any(inner.count("・") >= 2 or inner.count("？") >= 2 for inner in re.findall(r"【([^】]*)】", title)):
        pts -= 0.3          # 括弧の中の列挙
    if _DOKOMADE in title:
        pts += 0.4          # 参考chの140万回の型（市場の外の根拠なので、控えめに足す）
    if title.startswith(subject):
        pts += 0.2          # 検索で題材名が先頭に出る
    n = len(title)
    if n < 24:
        pts -= 0.3
    elif n > 60:
        pts -= 0.02 * (n - 60)
    return round(pts, 2), h, c


def market_propose(subject: str, claims: list, script: str, plan: dict | None,
                   market: dict | None, *, k: int = 5) -> list[dict]:
    """市場の効きで点を付けた題名の案。上ほど点が高い。

    戻り値の各要素: title / score / hot（入っている効く語）/ cold / basis（どの章が約束か）。
    台本に出てこない効く語を含む案と、言い切りの案は落とす。"""
    hot, _ = _mterms(market or {})
    plan = plan or {}
    chapters = plan.get("chapters") or []
    ideas: list[tuple[str, str]] = []
    methods = _methods(script, plan, hot)
    bracket = f"【{methods}解析で{_DOKOMADE}】" if methods else f"【論文と一次資料で{_DOKOMADE}】"
    at = _hook_chapter(plan, hot)
    hot_terms = {x["term"] for x in hot}
    # 題材ごとに効く言い回しが違う（死海文書では「謎」「？」は効かず、ヴォイニッチ手稿では効く）。
    # 効いている題材でだけ、問いの題に足した形も作り、点で選ばせる
    recent = [int(y) for y in re.findall(r"(20\d\d)年", script)]
    this_year = __import__("datetime").date.today().year
    brackets = [bracket]
    if "最新" in hot_terms and recent and max(recent) >= this_year - 3:
        # 「最新のAI・DNA解析」だと、6年前のDNAの研究まで最新に見える。研究全体に掛ける
        brackets.append(f"【最新研究で{_DOKOMADE}】")

    def variants(q: str, basis: str) -> None:
        heads = [q]
        if "謎" in hot_terms and not q.startswith(f"{subject}の謎"):
            heads.append(f"{subject}の謎、" + (q[len(subject):].lstrip("、はにのをが") if q.startswith(subject) else q))
        for h in heads:
            ends = [h] + ([h + "？"] if "？" in hot_terms else [])
            for e in ends:
                for b in brackets:
                    ideas.append((e + b, basis))

    if at is not None:
        q = _lead_subject(_chapter_question(chapters[at]), subject)
        variants(_quote_hot(q, hot, subject), f"第{at + 1}章「{chapters[at].get('claim', '')}」")
    mystery = re.sub(r"[？?。]+$", "", str(plan.get("mystery") or ""))
    if mystery:
        variants(_quote_hot(_lead_subject(mystery, subject), hot, subject), "動画全体の問い")
    if chapters:
        order = sorted(range(len(chapters)), key=lambda i: -sum(
            _math.log(x.get("adj", x["lift"])) for x in hot
            if re.search(r"[一-龥ァ-ヶーA-Z]", x["term"]) and re.search(x["pattern"], str(chapters[i].get("claim", "")))))
        labels = [lab for lab in (_label(str(chapters[i].get("claim", "")), subject) for i in order) if lab][:3]
        word = "都市伝説" if "都市伝説" in hot_terms else "噂"
        if len(labels) == 3:
            ideas.append((f"{subject}の{len(chapters)}つの{word}を論文で確かめる【{'・'.join(labels)}】", "全章"))
    fact = _surprise(script, subject)
    hook_label = _label(str(chapters[at].get("claim", "")), subject) if at is not None else None
    if fact and hook_label:
        ideas.append((f"{subject}、{fact}【{hook_label}は？】", "冒頭の事実と第%d章" % (at + 1)))
    ideas += [(t, "台本だけから作った型") for t in propose(subject, claims, script)]

    out, seen = [], set()
    for title, basis in ideas:
        if title in seen or _ASSERTIVE.search(title):
            continue
        seen.add(title)
        s, h, c = score_title(title, market or {}, subject)
        # 効く語は、台本が話しているものだけ（題が本文にない約束をしない）
        if any(not re.search(x["pattern"], script) for x in h if re.search(r"[一-龥ァ-ヶーA-Z]", x["term"])):
            continue
        out.append({"title": title, "score": s, "hot": [x["term"] for x in h],
                    "cold": [x["term"] for x in c], "basis": basis})
    out.sort(key=lambda x: -x["score"])
    # 同じ問いの言い回し違い（？の有無・括弧の違い）ばかりが並ぶと選べない。約束する話ごとに2つまで
    picked, per = [], Counter()
    for x in out:
        if per[x["basis"]] < 2:
            picked.append(x)
            per[x["basis"]] += 1
    return picked[:k]


def opening_gap(script: str, plan: dict | None, market: dict | None) -> str:
    """題で約束した話が冒頭に出てこなければ、その注意。最初の30秒で約束が見えないと離れる。"""
    hot, _ = _mterms(market or {})
    at = _hook_chapter(plan or {}, hot)
    if at is None or at == 0:
        return ""
    ch = (plan or {}).get("chapters")[at]
    paras = [p for p in re.split(r"\n\s*\n", script) if p.strip()]
    head = ""
    for p in paras:
        head += p
        if "迫っていこう" in p or "とは何なのか" in p:
            break
    words = [x for x in hot if re.search(r"[一-龥ァ-ヶーA-Z]", x["term"])
             and re.search(x["pattern"], f"{ch.get('claim', '')} {ch.get('question', '')}")]
    if words and not any(re.search(x["pattern"], head) for x in words):
        return (f"題で約束する「{'・'.join(x['term'] for x in words)}」が冒頭に出てこない（第{at + 1}章まで待たせる）。"
                "冒頭で見せる題名の例にこの話を入れる")
    return ""


def render_market(subject: str, claims: list, script: str, plan: dict | None, market: dict) -> str:
    """市場の数字つきの題名の案。どの語がどれだけ効くかと、どの章が約束かを添える。"""
    from topic_scout.market import summary
    rank = {x["term"]: x.get("adj", x["lift"]) for x in market.get("lifts") or []}
    lines = ["── 題名の候補（市場の数字つき。上ほど点が高い）──"]
    for i, x in enumerate(market_propose(subject, claims, script, plan, market), 1):
        lines.append(f"{i}. {x['title']}")
        why = [f"{t} {rank.get(t, 1.0)}倍" for t in x["hot"]]
        lines.append(f"   {len(x['title'])}字 / 点 {x['score']} / 効く語: {'・'.join(why) or 'なし'}"
                     + (f" / 下がる語: {'・'.join(x['cold'])}" if x["cold"] else "")
                     + f" / 約束する話: {x['basis']}")
    gap = opening_gap(script, plan, market)
    if gap:
        lines += ["", "注意: " + gap]
    lines += ["", *summary(market),
              "※選ぶのは人。台本が話していない語は使っていない。「判明しました」のような言い切りは作らない。"]
    return "\n".join(lines)
