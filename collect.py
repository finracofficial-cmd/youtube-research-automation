import sys, time, json, yaml
sys.path.insert(0, ".")
from topic_scout.fetch import search, dump

cfg = yaml.safe_load(open("seeds/candidates.yaml", encoding="utf-8"))
queries = [v["query"] for v in cfg["validation"]] + cfg["candidates"]
results = {}
for i, q in enumerate(queries, 1):
    try:
        vids = search(q, limit=30)
        results[q] = dump(vids)
        print(f"[{i}/{len(queries)}] OK   {q}: {len(vids)}件", flush=True)
    except Exception as e:
        print(f"[{i}/{len(queries)}] FAIL {q}: {str(e)[:120]}", flush=True)
    time.sleep(4)
json.dump(results, open("out/search_raw.json", "w"), ensure_ascii=False, indent=1)
print("WROTE out/search_raw.json", len(results), "topics")
