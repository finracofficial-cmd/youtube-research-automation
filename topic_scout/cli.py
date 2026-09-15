"""題材選定 CLI.

  python -m topic_scout scout                 # seeds を全部採点してランキング
  python -m topic_scout explain ロンゴロンゴ    # 1題材の内訳を見る
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

from .classify import tag, tag_all
from .discover import discover
from .features import build
from .fetch import search
from .score import score_topic

DEFAULT_SEEDS = Path("seeds/candidates.yaml")


def _load_queries(path: Path) -> list[str]:
    """seeds yaml か、discover が出した candidates.csv を読む。"""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8") as fh:
            return [r["term"] for r in csv.DictReader(fh) if r.get("term")]
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    qs = [v["query"] for v in cfg.get("validation", [])]
    qs += list(cfg.get("candidates", []))
    return qs


def _score(query: str, limit: int, exclude: set[str]):
    vids = search(query, limit=limit)
    feats = build(query, tag_all(vids), exclude_channel_ids=exclude)
    return feats, score_topic(feats)


def cmd_scout(args) -> int:
    queries = _load_queries(Path(args.seeds))
    exclude = set(args.exclude or [])
    rows = []
    for q in queries:
        try:
            feats, sc = _score(q, args.limit, exclude)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {q}: {exc}", file=sys.stderr)
            continue
        rows.append((sc, feats))
    rows.sort(key=lambda r: -r[0].score)

    print(f"{'題材':<22}{'判定':<7}{'score':>7}{'需要':>7}{'空白':>7}{'時流':>7}  {'上位25%再生':>11}{'低品質率':>7}{'中央尺':>7}")
    print("-" * 104)
    for sc, f in rows:
        print(f"{sc.query[:21]:<22}{sc.verdict:<7}{sc.score:>7.3f}{sc.demand:>7.2f}"
              f"{sc.gap:>7.2f}{sc.trend:>7.2f}  {f.views_p75:>11,.0f}{f.low_effort_ratio:>7.0%}{f.median_duration//60:>6}分")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["query", "verdict", "score", "demand", "gap", "trend",
                    "views_p75", "views_max", "n_over_100k", "distinct_channels_over_100k",
                    "low_effort_ratio", "median_duration_sec", "n_serious_longform",
                    "best_serious_views", "ai_angle_ratio", "reasons"])
        for sc, f in rows:
            w.writerow([sc.query, sc.verdict, f"{sc.score:.4f}", f"{sc.demand:.4f}",
                        f"{sc.gap:.4f}", f"{sc.trend:.4f}", int(f.views_p75), f.views_max,
                        f.n_over_100k, f.distinct_channels_over_100k,
                        f"{f.low_effort_ratio:.3f}", f.median_duration, f.n_serious_longform,
                        f.best_serious_views, f"{f.ai_angle_ratio:.3f}", " / ".join(sc.reasons)])
    print(f"\n-> {out}")
    return 0


def cmd_discover(args) -> int:
    """量産系チャンネルを需要センサーとして、題材候補を自動発掘する。"""
    raw = json.loads(Path(args.search_raw).read_text(encoding="utf-8"))
    from .fetch import Video
    seen: dict[str, set[str]] = {}
    for topic, vids in raw.items():
        for d in vids:
            v = Video(**d)
            if tag(v).is_low_effort:
                seen.setdefault(v.channel_id, set()).add(topic)
    channels = [c for c, t in sorted(seen.items(), key=lambda kv: -len(kv[1]))][: args.channels]
    print(f"需要センサーとして {len(channels)} チャンネルを走査", file=sys.stderr)

    cands = discover(channels, per_channel=args.per_channel,
                     cache=Path(args.cache) if args.cache else None)
    kept = [c for c in cands if c.n_channels >= args.min_channels]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["term", "n_channels", "n_videos", "example"])
        for c in kept:
            w.writerow([c.term, c.n_channels, c.n_videos, c.examples[0] if c.examples else ""])

    print(f"{'ch数':>4}{'本数':>5}  題材候補")
    for c in kept:
        print(f"{c.n_channels:>4}{c.n_videos:>5}  {c.term}")
    print(f"\n抽出 {len(cands)} 種 → {args.min_channels}ch以上 {len(kept)} 種 -> {out}", file=sys.stderr)
    return 0


def cmd_explain(args) -> int:
    exclude = set(args.exclude or [])
    vids = search(args.query, limit=args.limit)
    tagged = tag_all(vids)
    feats = build(args.query, tagged, exclude_channel_ids=exclude)
    sc = score_topic(feats)

    print(f"# {args.query}\n")
    print(f"判定: {sc.verdict}  score={sc.score:.3f}  (需要={sc.demand:.2f} 空白={sc.gap:.2f} 時流={sc.trend:.2f})")
    for r in sc.reasons:
        print(f"  - {r}")
    print(f"\n{json.dumps(feats.to_dict(), ensure_ascii=False, indent=1)}\n")
    print(f"{'再生':>10} {'尺':>5}  {'分類':<10} チャンネル / タイトル")
    print("-" * 100)
    for t in sorted(tagged, key=lambda x: -x.video.view_count):
        if t.video.channel_id in exclude:
            kind = "自分"
        elif t.is_serious_longform:
            kind = "★真面目長尺"
        elif t.is_low_effort:
            kind = "量産/煽り"
        else:
            kind = "その他"
        v = t.video
        print(f"{v.view_count:>10,} {v.duration//60:>4}分  {kind:<10} {v.channel[:16]:<16} {v.title[:42]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="topic_scout")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scout", help="seeds を採点してランキング")
    s.add_argument("--seeds", default=str(DEFAULT_SEEDS),
                   help="yaml、または discover が出した candidates.csv")
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--out", default="out/ranking.csv")
    s.add_argument("--exclude", nargs="*", help="競合から外す channel_id（自チャンネル）")
    s.set_defaults(func=cmd_scout)

    d = sub.add_parser("discover", help="量産系チャンネルから題材候補を自動発掘")
    d.add_argument("--search-raw", default="out/search_raw.json",
                   help="scout の検索結果。供給側チャンネルの特定に使う")
    d.add_argument("--channels", type=int, default=28, help="走査するチャンネル数")
    d.add_argument("--per-channel", type=int, default=60, help="1chあたり何本のタイトルを見るか")
    d.add_argument("--min-channels", type=int, default=3, help="何ch以上が扱った語を残すか")
    d.add_argument("--cache", default="out/channel_titles.json")
    d.add_argument("--out", default="out/candidates.csv")
    d.set_defaults(func=cmd_discover)

    e = sub.add_parser("explain", help="1題材の内訳を表示")
    e.add_argument("query")
    e.add_argument("--limit", type=int, default=30)
    e.add_argument("--exclude", nargs="*")
    e.set_defaults(func=cmd_explain)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
