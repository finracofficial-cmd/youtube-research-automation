import json, sys, collections
from pathlib import Path
sys.path.insert(0, ".")
from topic_scout.fetch import Video
from topic_scout.classify import tag
from topic_scout.discover import discover

TOP_N_CHANNELS = 28
raw = json.load(open("out/search_raw.json", encoding="utf-8"))
agg = collections.defaultdict(lambda: {"topics": set(), "name": ""})
for topic, vids in raw.items():
    for d in vids:
        v = Video(**d)
        if tag(v).is_low_effort:
            agg[v.channel_id]["topics"].add(topic)
            agg[v.channel_id]["name"] = v.channel
ranked = sorted(agg.items(), key=lambda kv: -len(kv[1]["topics"]))[:TOP_N_CHANNELS]
cids = [c for c, _ in ranked]
print(f"走査対象 {len(cids)} チャンネル", flush=True)

cands = discover(cids, per_channel=60, cache=Path("out/channel_titles.json"))
json.dump([c.__dict__ for c in cands], open("out/candidates_raw.json", "w"), ensure_ascii=False, indent=1)
print(f"\n抽出語 {len(cands)} 種\n")
print(f"{'ch数':>4}{'本数':>5}  題材候補")
print("-" * 70)
for c in cands[:60]:
    print(f"{c.n_channels:>4}{c.n_videos:>5}  {c.term}")
