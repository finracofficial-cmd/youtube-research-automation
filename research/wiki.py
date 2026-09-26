"""題材の記述を Wikipedia 日本語版の冒頭から取る。出典には使わない。

設計図を書かせると、冒頭の「画で見せられる具体」と、各章の「誰が最初に
言い出したか」が、5章中4章で「不明」になった（ヴォイニッチ、2026-09-24）。
資料が論文の題名と年だけで、その物がどう見えるか・説がどこから出たかを
持っていなかったため。

Wikipedia は一次資料ではないので出典としては書かせない。ここから取るのは
「見た目」と「手がかり」だけで、本文に書く事実の裏は論文と原典で取る。
"""
from __future__ import annotations

import re

from .http import get_json, q

JA_API = "https://ja.wikipedia.org/w/api.php"
EN_API = "https://en.wikipedia.org/w/api.php"

_PAREN = re.compile(r"（[^（）]*）|\([^()]*\)")
_REF = re.compile(r"\[[^\]]*\]")
_HEAD = re.compile(r"=+\s*[^=]+?\s*=+")   # == 概要 == のような節の見出し


def _extract(api: str, title: str, *, chars: int) -> str:
    # exintro（導入部だけ）にしない。日本語版の導入部は2文しかなく、見た目の
    # 記述（「浴槽らしきものに浸かった女性の絵」）は「概要」の節にある（実測）
    d = get_json(api + "?" + q({
        "action": "query", "format": "json", "prop": "extracts",
        "explaintext": 1, "redirects": 1,
        "exchars": chars, "titles": title}))
    pages = ((d or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        text = (page.get("extract") or "").strip()
        if text:
            return text
    return ""


def clean(text: str) -> str:
    """読みの括弧と脚注の印を落とし、文ごとに改行する。"""
    text = _HEAD.sub(" ", _REF.sub("", _PAREN.sub("", text)))
    text = re.sub(r"\s+", " ", text).strip()
    sents = [s.strip() for s in re.split(r"(?<=[。])", text) if s.strip()]
    return "\n".join(sents)


def lead(subject: str, subject_en: str = "", *, chars: int = 1800) -> str:
    """題材の冒頭。日本語版が無ければ英語版。どちらも無ければ空。"""
    text = _extract(JA_API, subject, chars=chars)
    if not text and subject_en:
        text = _extract(EN_API, subject_en.split(",")[0].strip(), chars=chars)
    return clean(text)


# 台本に使わない節。出典・関連項目・外部リンクと、写本や洞窟の一覧のような目録
_SKIP_HEAD = re.compile(r"脚注|注釈|出典|参考文献|関連項目|外部リンク|関連書籍|ギャラリー|"
                        r"See also|Notes|References|Bibliography|Further reading|External links|"
                        r"Online Journals|Gallery|一覧|Collections holding", re.I)
# 題材の「何なのか」に当たる節
# 出版・公開の経緯も入れる。「なぜ気になるのか」の元はここにあることが多い
# （死海文書: 発見から40年以上、写本の多くが公開されなかった）
_BASICS_HEAD = re.compile(r"概要|歴史|発見|内容|意義|年代|構成|特徴|材料|言語|出版|公開|公刊|停滞|"
                          r"Discover|History|Overview|Description|Content|Dating|Significance|Materials|"
                          r"Languages|Publication", re.I)
_TERM = re.compile(r"[ァ-ヶー]{2,}|[一-龥]{2,}|[A-Za-z]{3,}|[A-Z]{2,}")


def article(title: str, api: str = JA_API) -> str:
    """記事の全文（平文、節の見出し付き）。無ければ空。"""
    d = get_json(api + "?" + q({"action": "query", "format": "json", "prop": "extracts",
                                "explaintext": 1, "redirects": 1, "titles": title}))
    pages = ((d or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        text = (page.get("extract") or "").strip()
        if text:
            return text
    return ""


def split_sections(text: str) -> list[tuple[str, str]]:
    """(見出し, 本文) の列。先頭の見出しの無い部分は「冒頭」。
    目録の節（短い行が並ぶだけ）と、出典・関連項目の節は落とす。"""
    out: list[tuple[str, str]] = []
    head, buf = "冒頭", []

    def flush():
        body = "\n".join(buf).strip()
        lines = [l for l in body.splitlines() if l.strip()]
        listy = lines and sum(len(l) < 25 for l in lines) > len(lines) * 0.6
        if body and not _SKIP_HEAD.search(head) and not listy:
            out.append((head, body))

    for line in text.splitlines():
        m = re.match(r"^(=+)\s*(.+?)\s*=+$", line.strip())
        if m:
            flush()
            head, buf = m.group(2), []
        else:
            buf.append(line)
    flush()
    return out


# 略語は記事の中で言い換えられている（英語版は AI を artificial intelligence と書く）
_SYNONYMS = {"AI": ("AI", "artificial intelligence", "machine learning", "人工知能"),
             "DNA": ("DNA", "遺伝子", "genetic")}


def _terms(claim: str, drop: tuple[str, ...]) -> set[str]:
    t = claim
    for d in drop:
        if d:
            t = t.replace(d, " ")
    out = {w for w in _TERM.findall(t) if w.lower() not in _EN_COMMON}
    for w in list(out):
        out |= set(_SYNONYMS.get(w, ()))
    return out


def _acronyms(claim: str) -> set[str]:
    return {w for w in re.findall(r"[A-Z]{2,}", claim) if w in _SYNONYMS}


_EN_COMMON = {"the", "and", "dead", "sea", "scrolls", "analysis", "identity", "texts", "passages"}


def _hits(term: str, text: str) -> int:
    """語の出現数。英語は語の境目で数える（「ai」を部分一致で数えると certain や
    again に当たり、関係の無い節が選ばれた。実測）。長い語は語幹で（forgery/forgeries）。"""
    if " " in term:
        return len(re.findall(re.escape(term), text, re.I))
    if re.fullmatch(r"[A-Za-z]+", term):
        stem = term[:6] if len(term) >= 7 else term
        flags = 0 if term.isupper() else re.I
        return len(re.findall(r"\b" + re.escape(stem) + (r"\w*" if stem != term else r"\b"), text, flags))
    return text.count(term)


def _score(head: str, body: str, terms: set[str]) -> float:
    """見出しに語があれば強く、本文は密度で。長い節ほど語が多く出るので、
    数だけ見ると長い節が勝つ（「発見と変転」が「意義」に勝った。実測）。"""
    in_head = sum(2.0 for t in terms if _hits(t, head))
    in_body = sum(min(6, _hits(t, body)) for t in terms)
    return in_head + in_body / (1.0 + len(body) / 3000)


def _trim(body: str, chars: int) -> str:
    """文の切れ目で chars まで。英語版は「。」が無いので、ピリオドでも切る
    （切らないと節がまるごと1文になり、5,000字の節がそのまま入った。実測）。"""
    body = clean(body)
    sents = [x for line in body.splitlines()
             for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", line) if x.strip()]
    out, n = [], 0
    for sent in sents:
        if n + len(sent) > chars and out:
            break
        out.append(sent)
        n += len(sent)
    return "\n".join(out)


def basics(sections: list[tuple[str, str]], *, chars: int = 3200) -> str:
    """題材が何なのか: 冒頭と、発見・内容・意義・年代の節。"""
    picked = [(h, b) for h, b in sections if h == "冒頭" or _BASICS_HEAD.search(h)]
    out, n = [], 0
    per = max(500, chars // max(1, len(picked)))
    for h, b in picked:
        part = _trim(b, min(per, chars - n))
        if not part:
            continue
        out.append(part)
        n += len(part)
        if n >= chars:
            break
    return "\n".join(out)


def passage_for(sections: list[tuple[str, str]], claim: str, *, drop: tuple[str, ...] = (),
                chars: int = 1100, used: set[str] | None = None) -> list[tuple[str, str]]:
    """主張に関係する節を2つまで選んで、(見出し, 本文の先頭) の列で返す。無ければ空。

    話の元（なぜそう語られるのか）は論文の題名からは取れない。百科事典の
    節には「1991年に作家が本を出して陰謀だと主張した」のような元がある。
    元の出来事（公開が40年遅れた）と、それを陰謀と言った本は別の節にある
    ことが多いので、2つ目も近い点なら取る。"""
    terms = _terms(claim, drop)
    if not terms:
        return []
    used = used if used is not None else set()
    pool = [(h, b) for h, b in sections if h not in used]
    # 芯が略語（AI・DNA）なら、その語（言い換え含む）が出る節だけから選ぶ。
    # 「text」「new」のような広い語で、関係の無い長い節が勝った（実測）
    core = {x for a in _acronyms(claim) for x in _SYNONYMS[a]}
    with_core = [(h, b) for h, b in pool if core and any(_hits(x, h + " " + b) for x in core)]
    if with_core:
        pool = with_core
    else:
        # 主張の語の過半が出る節だけ。「救世主の正体」に「正体」1語だけ当たる
        # 「サドカイ派説」の節が選ばれ、章が関係の無い話から始まった（実測）
        base = {w for w in terms if not any(w in syn and w != a for a, syn in _SYNONYMS.items())}
        need = len(base) // 2 + 1
        pool = [(h, b) for h, b in pool if sum(bool(_hits(w, h + " " + b)) for w in base) >= need]
    ranked = sorted(((_score(h, b, terms), h, b) for h, b in pool), key=lambda x: -x[0])
    if not ranked or ranked[0][0] < 0.9:
        return []
    top = ranked[0][0]
    keep = [(h, b) for sc, h, b in ranked[:2] if sc >= max(0.9, top * 0.6)]
    out = []
    for k, (h, b) in enumerate(keep):
        used.add(h)
        out.append((h, _trim(b, int(chars * (0.6 if len(keep) > 1 and k == 0 else 0.4 if len(keep) > 1 else 1.0)))))
    return out


def material(subject: str, subject_en: str, claims: list[tuple[str, str]]) -> str:
    """プロンプトに足す節。題材の基本と、主張ごとの「話の元」。

    日本語版を主にし、主張に当たる節が日本語版に無ければ英語版から取る。"""
    ja = split_sections(article(subject, JA_API))
    en_title = (subject_en or "").split(",")[0].strip()
    en: list[tuple[str, str]] | None = None

    def english() -> list[tuple[str, str]]:
        nonlocal en
        if en is None:
            en = split_sections(article(_en_title(subject_en), EN_API)) if subject_en else []
        return en

    base_from = ja if basics(ja) else english()
    base = basics(base_from)
    if not base.strip():
        return ""
    in_base = {h for h, _ in base_from if h == "冒頭" or _BASICS_HEAD.search(h)}
    lines = ["\n\n## 題材の記述（Wikipedia）",
             "使い方: 題材が何なのか（いつ・どこで・誰が見つけ・何が書かれ・なぜ大事か）と、各主張がなぜ"
             "語られるのか（話の元になった出来事）に使う。出典としては書かない。英語の節は日本語にして使う。",
             "### 基本", base]
    name_en = _en_title(subject_en)
    drop = tuple(x for x in (subject, name_en) if x)
    used_ja: set[str] = {"冒頭"}
    used_en: set[str] = {"冒頭"}
    for ja_claim, en_claim in claims:
        picked = passage_for(ja, ja_claim, drop=drop, used=used_ja)
        # 主張の芯が略語（AI・DNA）なのに、日本語版の節にその語が無ければ英語版を見る。
        # 日本語版の死海文書の記事には DNA 解析の節が無く、「エルサレム由来説」が選ばれた
        core = {x for a in _acronyms(ja_claim) for x in _SYNONYMS[a]}
        if picked and core and not any(_hits(x, b) for _, b in picked for x in core):
            en_pick = passage_for(english(), en_claim or ja_claim, drop=drop + tuple(name_en.split()),
                                  used=set(used_en))
            if en_pick and any(_hits(x, b) for _, b in en_pick for x in core):
                for h, _ in picked:
                    used_ja.discard(h)
                picked = en_pick
                used_en.update(h for h, _ in en_pick)
        if not picked:
            picked = passage_for(english(), en_claim or ja_claim, drop=drop + tuple(name_en.split()),
                                 used=used_en)
        for h, body in picked:
            if h in in_base:
                # 基本に入れた節を繰り返さない。どの節が元かだけ示す
                lines.append(f"### 話の元: {ja_claim} → 上の「基本」の「{h}」の節")
            elif body:
                lines += [f"### 話の元: {ja_claim}（節: {h}）", body]
    return "\n".join(lines)


def _en_title(subject_en: str) -> str:
    """subject_en は検索語の並び（"Dead Sea Scrolls authorship ..."）のことがある。
    英語版の記事名として、先頭の大文字で始まる語の並びだけ使う。"""
    words = []
    for w in (subject_en or "").split(",")[0].split():
        if w[:1].isupper():
            words.append(w)
        else:
            break
    return " ".join(words) or subject_en


def section(subject: str, lead_text: str) -> str:
    """プロンプトに足す節。何に使い、何に使わないかを本文で言う。"""
    if not lead_text.strip():
        return ""
    return ("\n\n## 題材の記述（Wikipedia日本語版の冒頭）\n"
            "見た目の具体（色・形・数・場所）と、説の出どころ（誰が・何年に）の手がかりに使う。\n"
            "出典としては書かない。ここにある数字も、上の資料に無ければ裏の取れていない数字として扱う。\n"
            + lead_text)
