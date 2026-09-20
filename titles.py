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
    ("未解読の", re.compile(r"未解読")),
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

    # 3. このchの既存の型（〜のか【分野×分野】）
    fs = fields(script)
    tail = f"【{'×'.join(fs)}】" if len(fs) >= 2 else "【論文と一次資料】"
    out.append(f"{name}は{'なぜ' if not years else years + 'も'}解けていないのか{tail}")
    return out


def render(subject: str, claims: list, script: str) -> str:
    got = propose(subject, claims, script)
    lines = ["── 題名の候補 ──"]
    for i, t in enumerate(got, 1):
        mark = "  ← 参考chで当たった型に一番近い" if i == 1 else ""
        lines.append(f"{i}. {t}{mark}")
        lines.append(f"   {len(t)}字（スマホは28字前後で切れる）")
    lines.append("※選ぶのは人。台本が結論していないことは書いていない。")
    return "\n".join(lines)
