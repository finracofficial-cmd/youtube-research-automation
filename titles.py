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


def propose(subject: str, claims: list, script: str) -> list[str]:
    """題名の候補。上ほど参考chの当たった型に近い。"""
    n = len(claims)
    down, up = tally(script)
    out: list[str] = []

    # 1. 当たった型そのもの。括弧に知識の限界の問い、本体に固有名詞と数字
    if down and up:
        out.append(f"【どこまで分かっているのか】{subject}、残った{up}つと消えた{down}つ")
    elif down:
        out.append(f"【どこまで分かっているのか】{subject}、{down}つの通説が消えた日")
    else:
        out.append(f"【どこまで分かっているのか】{subject}、{n}つの通説を確かめる")

    # 2. 問いを1つに絞る型。固有名詞は主張の主語から採る
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent / "video"))
    from chapters import subject_of

    heads = [subject_of(c) for c in claims]
    head = next((h for h in heads if h and h != subject), subject)
    out.append(f"【一次資料で確かめる】{subject}、{head}はどこまで本当か")

    # 3. このchの既存の型（なぜ〜のか【分野×分野】）
    fs = fields(script)
    tail = f"【{'×'.join(fs)}】" if len(fs) >= 2 else "【論文と一次資料】"
    out.append(f"{subject}の通説{n}つを一次資料で確かめた{tail}")
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
