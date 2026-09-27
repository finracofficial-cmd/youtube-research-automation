"""題材ごとに、市場（YouTube の日本語動画）でどの題の言葉が伸びているかを数える。

題名の案を台本だけから作っていた頃は、市場を知らなかった。死海文書で手で調べたら
（analysis/titles_dead-sea_2026-09-27.md）、伸びている言葉は「禁断」「解読」「判明」
「救世主の正体」「AI」で、「謎」「隠された」「真実」「ゆっくり」は差がつかないか
下がっていた。これを題材ごとに自動で取る。

  1. 題材名で検索し、題によく出る語を拾って、その語を足してもう一度検索する
  2. 各チャンネルのページから、ふだんの再生数（直近の動画の中央値）と登録者数を取る
  3. 平常比 = 再生数 ÷ チャンネルのふだんの再生数。登録者の多さで伸びたのか、
     題と題材で伸びたのかを分ける
  4. 語ごとに、その語がある題とない題の平常比の中央値を比べる（効き）

1チャンネルが同じ語を量産すると効きが歪む（死海文書ではエヴァのパロディを量産する
1チャンネルが上位を占めた）。語ごとに、違うチャンネル3つ以上で使われていることを
条件にする。

  python -m topic_scout.market 死海文書 --out reports/dead-sea_market.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

from .fetch import search
from .told import _stems

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
KANA = re.compile(r"[ぁ-んァ-ヶ]")
MIN_N = 4             # 語の効きを出す最少の本数
MIN_CHANNELS = 3      # 語を使っているチャンネルの最少数
MIN_BASELINE = 1000   # ふだんの再生数がこれ未満のチャンネルは比べない（数十回の平常比は揺れすぎる）

# 題によく出る「釣り」の言い回し。題材によらず数える。題材の固有の語（救世主・バチカン・AI）は
# 題から拾う（terms）
HOOKS = {
    "禁断": r"禁断|禁書|禁忌", "絶対に〜てはいけない": r"てはいけない|ではいけない|ならない",
    "判明": r"判明", "解読": r"解読", "正体": r"正体", "最新": r"最新", "衝撃": r"衝撃|驚愕|震撼",
    "ヤバい": r"ヤバ|やば", "真実": r"真実", "真相": r"真相", "謎": r"謎", "秘密": r"秘密",
    "隠された": r"隠", "予言": r"予言|預言", "滅亡": r"滅亡|破滅|終末", "実在": r"実在",
    "発見": r"発見", "暴いた": r"暴", "怖い": r"怖|恐ろし|閲覧注意", "科学": r"科学|論文|研究",
    "都市伝説": r"都市伝説", "ゆっくり": r"ゆっくり", "総集編": r"総集編",
    # 【】は「ジャンルの札」（【ゆっくり解説】【都市伝説】）だけ数える。参考chの140万回の題
    # 「【AI解析でどこまで分かったのか】…」の括弧は問いで、札とは別物
    "【ジャンル札】": r"【[^】]*(?:ゆっくり|都市伝説|総集編|予言|衝撃|閲覧注意|ミステリー|作業用|睡眠用|オカルト|解説)[^】]*】",
    "？": r"[？?]", "！": r"[！!]", "…": r"…|\.\.\.", "数字": r"[0-9０-９]", "とは": r"とは",
}
# 題から語を拾うときに捨てるもの
_STOP = {"解説", "動画", "チャンネル", "シリーズ", "ミステリー", "作業用", "睡眠用", "聞き流し", "雑学",
         "歴史", "世界", "人類", "日本", "本当", "理由", "意味", "結果", "存在", "内容", "話題",
         "ショート", "パート", "PART", "Part", "part"}
_TERM = re.compile(r"[ァ-ヶー]{3,}|[一-龥]{2,}|[A-Z]{2,}[a-z]*")


def _num(s: str) -> int | None:
    m = re.match(r"([\d.]+)(万|億)?", s.replace(",", ""))
    if not m:
        return None
    return int(float(m.group(1)) * {"万": 1e4, "億": 1e8}.get(m.group(2) or "", 1))


def channel_baseline(channel_id: str, *, timeout: int = 30) -> dict:
    """チャンネルの登録者数と、ふだんの再生数（公開2週間以上の直近動画の中央値）。
    ページが取れなければ空の値。YouTube の検索は通るが動画ページは429になることがある。"""
    req = urllib.request.Request(f"https://www.youtube.com/channel/{channel_id}/videos",
                                 headers={"Accept-Language": "ja", "User-Agent": UA})
    try:
        html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - 取れなければ比べないだけ
        return {"subs": None, "median": None, "n": 0}
    m = re.search(r"チャンネル登録者数 ([\d.,]+(?:万|億)?)人", html)
    rows = re.findall(r'"accessibilityLabel":"([\d,]+)回視聴".{0,300}?\{"text":\{"content":"([^"]+)"', html)
    old = [int(v.replace(",", "")) for v, age in rows
           if not re.search(r"(時間|分|秒)前|^([1-9]|1[0-3]) 日前", age)]
    return {"subs": _num(m.group(1)) if m else None,
            "median": statistics.median(old) if old else None, "n": len(rows)}


def relevant(title: str, subject: str) -> bool:
    return bool(KANA.search(title)) and any(s in title for s in _stems(subject))


def terms(titles: list[str], subject: str, *, top: int = 12) -> list[str]:
    """題によく出る、題材に固有の語（救世主・バチカン・AI…）。題材名とその一部、
    釣りの言い回し（HOOKS。予言と預言のような表記ゆれも）、数字にくっついた切れ端
    （「2000年隠されていた」の「年隠」）は除く。"""
    stems = _stems(subject)
    c: Counter = Counter()
    for t in titles:
        t2 = re.sub(r"[0-9０-９]+[年月日人回本個件つ]", " ", t)
        for s in stems:
            t2 = t2.replace(s, " ")
        for w in set(_TERM.findall(t2)):
            if w in _STOP or any(w in s or s in w for s in stems):
                continue
            if any(re.fullmatch(f"(?:{pat})", w) for pat in HOOKS.values()):
                continue
            c[w] += 1
    return [w for w, n in c.most_common(top) if n >= 3]


SHRINK = 4   # 本数の少ない語の効きを1倍に寄せる強さ（本数 n のとき n/(n+SHRINK) だけ効かせる）


def adjusted(lift: float, n: int) -> float:
    """本数が少ない語の効きを1倍に寄せる。4本で7.4倍（メシア）は、2.7倍として扱う。
    効きの順位が数本の当たりで入れ替わると、題名の案が回ごとにぶれる。"""
    return round(math.exp(math.log(lift) * n / (n + SHRINK)), 2) if lift > 0 else 0.0


def collect(subject: str, *, per_query: int = 80, extra_queries: int = 6,
            baseline=channel_baseline, searcher=search, pause: float = 0.6, log=print) -> list[dict]:
    """題材の動画を集め、平常比を付けて返す。"""
    videos: dict[str, dict] = {}

    def add(query: str) -> None:
        try:
            got = searcher(query, limit=per_query)
        except Exception as exc:  # noqa: BLE001 - 1つの語で落ちても残りで数える
            log(f"  検索に失敗: {query}: {str(exc)[:80]}")
            return
        for v in got:
            if v.video_id not in videos and relevant(v.title, subject):
                videos[v.video_id] = {"id": v.video_id, "title": v.title, "views": v.view_count,
                                      "minutes": v.duration // 60, "channel": v.channel,
                                      "channel_id": v.channel_id}

    add(subject)
    for w in terms([v["title"] for v in videos.values()], subject)[:extra_queries]:
        add(f"{subject} {w}")
    log(f"  {subject}: 動画 {len(videos)}本")
    chans: dict[str, dict] = {}
    for cid in sorted({v["channel_id"] for v in videos.values() if v["channel_id"]}):
        chans[cid] = baseline(cid)
        time.sleep(pause)
    rows = []
    for v in videos.values():
        c = chans.get(v["channel_id"]) or {}
        med = c.get("median")
        rows.append({**v, "subs": c.get("subs"), "baseline": med,
                     "ratio": round(v["views"] / med, 2) if med and med >= MIN_BASELINE and v["views"] else None})
    return sorted(rows, key=lambda r: -r["views"])


def lifts(rows: list[dict], subject: str) -> list[dict]:
    """語ごとの効き。その語がある題の平常比の中央値 ÷ ない題の中央値。"""
    scored = [r for r in rows if r.get("ratio") is not None]
    if len(scored) < 12:
        return []
    words = dict(HOOKS)
    for w in terms([r["title"] for r in scored], subject, top=30):
        words.setdefault(w, re.escape(w))
    out = []
    for name, pat in words.items():
        w = [r for r in scored if re.search(pat, r["title"])]
        wo = [r["ratio"] for r in scored if not re.search(pat, r["title"])]
        if len(w) < MIN_N or len({r["channel_id"] for r in w}) < MIN_CHANNELS or not wo:
            continue
        a, b = statistics.median(r["ratio"] for r in w), statistics.median(wo)
        if b <= 0:
            continue
        out.append({"term": name, "pattern": pat, "n": len(w), "channels": len({r["channel_id"] for r in w}),
                    "with": round(a, 2), "without": round(b, 2), "lift": round(a / b, 2),
                    "adj": adjusted(a / b, len(w))})
    return sorted(out, key=lambda x: -x["adj"])


def analyze(subject: str, **kw) -> dict:
    rows = collect(subject, **kw)
    scored = [r for r in rows if r.get("ratio") is not None]
    return {
        "subject": subject,
        "collected": datetime.date.today().isoformat(),
        "n_videos": len(rows),
        "n_scored": len(scored),
        "median_ratio": round(statistics.median(r["ratio"] for r in scored), 2) if scored else None,
        "lifts": lifts(rows, subject),
        "top_views": rows[:15],
        "top_ratio": sorted(scored, key=lambda r: -r["ratio"])[:15],
        "videos": rows,
    }


def hot(market: dict, *, at_least: float = 1.3) -> list[dict]:
    """伸びている語。本数で寄せた効きが at_least 倍以上。"""
    return [x for x in (market or {}).get("lifts") or [] if x.get("adj", x["lift"]) >= at_least]


def cold(market: dict, *, at_most: float = 0.9) -> list[dict]:
    """使っても差がつかないか、下がる語。"""
    return [x for x in (market or {}).get("lifts") or [] if x.get("adj", x["lift"]) <= at_most]


def _content(x: dict) -> bool:
    """記号や数字でなく、中身のある語か（救世主・AI）。題の約束になるのはこちらだけ。"""
    return bool(re.search(r"[一-龥ァ-ヶーA-Z]", x["term"])) and x["term"] not in ("【ジャンル札】",)


def hook_index(texts: list[str], market: dict) -> int | None:
    """いちばん効く語を多く含む文の番号（章の主張と問いを渡す）。題で約束する話になる。
    効く語をどれも含まなければ None。"""
    best, at = 0.0, None
    for i, t in enumerate(texts):
        s = sum(math.log(x.get("adj", x["lift"])) for x in hot(market) if _content(x) and re.search(x["pattern"], t))
        if s > best:
            best, at = s, i
    return at


def ranked_titles(market: dict, *, limit: int = 12) -> list[str]:
    """平常比の高い順の題（重複と装飾を畳む）。仕様の「いま語られている話」に使う。"""
    from .told import _NOISE
    seen, out = set(), []
    for r in sorted((market or {}).get("videos") or [], key=lambda r: -(r.get("ratio") or 0)):
        t = _NOISE.sub("", r["title"]).strip(" 　…")
        k = re.sub(r"\s+", "", t)
        if t and k not in seen:
            seen.add(k)
            out.append(t)
        if len(out) >= limit:
            break
    return out


def summary(market: dict) -> list[str]:
    """人が読む要約。"""
    out = [f"市場: {market.get('subject')}  動画 {market.get('n_videos')}本 / 平常比を出せた "
           f"{market.get('n_scored')}本（中央 {market.get('median_ratio')}倍）"]
    h, c = hot(market), cold(market)
    if h:
        out.append("伸びている語: " + "、".join(f"{x['term']} {x['adj']}倍（{x['n']}本）" for x in h[:10]))
    if c:
        out.append("差がつかない・下がる語: " + "、".join(f"{x['term']} {x['adj']}倍（{x['n']}本）" for x in c[:8]))
    for r in (market.get("top_ratio") or [])[:5]:
        out.append(f"  {r['ratio']}倍 {r['views']:,}回 {r['title'][:60]}")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="topic_scout.market")
    p.add_argument("subject")
    p.add_argument("--out", required=True)
    p.add_argument("--per-query", type=int, default=80)
    a = p.parse_args(argv)
    m = analyze(a.subject, per_query=a.per_query, log=lambda s: print(s, file=sys.stderr))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(summary(m)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
