"""題材ごとに「いま語られている話」を集める。量産chの動画タイトルから。

参考chは「この本を扱った動画のコメント欄を1700件読んだ」「いま語られている
話を集めて、多く語られている順に並べた」と言っている。検証する主張は
教科書の事実ではなく、市場で語られている話でなければ、潰す物語にならない。

死海文書の台本は「クムラン洞窟で発見された」「紀元前3世紀〜」「エッセネ派」
「最古の写本」「聖書研究に影響」の5主張で、全部が教科書の事実だった。
一方で量産chのタイトルは「バチカンが隠した」「聖書に消えた記述」「DNAを解読」
「救世主の正体」と言っている。視聴者が気になっているのは後者で、そこから
始めないと「謎に迫る」形にならない。

  python -m topic_scout.told out/channel_titles.json --subjects 死海文書 ヴォイニッチ手稿 \\
      --out analysis/told_2026-09-25.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# 題材名の短い形。「ヴォイニッチ手稿」は「ヴォイニッチ」でも当てる
def _stems(subject: str) -> list[str]:
    s = subject.strip()
    out = [s]
    for suffix in ("手稿", "文書", "遺跡", "文明", "事件", "計画", "帝国", "王国", "人"):
        if s.endswith(suffix) and len(s) - len(suffix) >= 3:
            out.append(s[: -len(suffix)])
    return out


_NOISE = re.compile(r"【[^】]*】|\[[^\]]*\]|#\S+")


def told(titles: list[str], subject: str, *, limit: int = 20) -> list[str]:
    """題材を含むタイトル。装飾（【ゆっくり解説】など）は落とし、重複は畳む。"""
    stems = _stems(subject)
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        if not any(st in t for st in stems):
            continue
        clean = _NOISE.sub("", t).strip(" 　…")
        key = re.sub(r"\s+", "", clean)
        if not clean or key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def told_for(subjects: list[str], cache: Path) -> dict[str, list[str]]:
    if not cache.exists():
        return {s: [] for s in subjects}
    by_channel = json.loads(cache.read_text(encoding="utf-8"))
    titles = [t for ts in by_channel.values() for t in ts]
    return {s: told(titles, s) for s in subjects}


def latest(analysis: Path = Path("analysis")) -> Path | None:
    files = sorted(analysis.glob("told_*.json"))
    return files[-1] if files else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="topic_scout.told")
    p.add_argument("cache", help="out/channel_titles.json")
    p.add_argument("--subjects", nargs="*", default=[])
    p.add_argument("--from-csv", help="題材のランキングCSV（1列目が題材）")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    subjects = list(a.subjects)
    if a.from_csv:
        import csv
        with open(a.from_csv, encoding="utf-8") as fh:
            for i, row in enumerate(csv.reader(fh)):
                if i == 0 or not row:
                    continue
                subjects.append(row[0].strip())
    got = told_for(subjects, Path(a.cache))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(1 for v in got.values() if v)
    print(f"語られている話: {n}/{len(got)} 題材で見つかった -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
