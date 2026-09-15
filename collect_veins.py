import sys, time, json, yaml
sys.path.insert(0, ".")
from topic_scout.fetch import search, dump
cfg = yaml.safe_load(open("seeds/veins.yaml", encoding="utf-8"))
try:
    results = json.load(open("out/search_raw.json", encoding="utf-8"))
except Exception:
    results = {}
qs = cfg["candidates"]
for i, q in enumerate(qs, 1):
    if q in results:
        print(f"[{i}/{len(qs)}] skip {q}", flush=True); continue
    try:
        results[q] = dump(search(q, limit=30))
        print(f"[{i}/{len(qs)}] OK   {q}: {len(results[q])}件", flush=True)
    except Exception as e:
        print(f"[{i}/{len(qs)}] FAIL {q}: {str(e)[:100]}", flush=True)
    json.dump(results, open("out/search_raw.json", "w"), ensure_ascii=False, indent=1)
    time.sleep(4)
print("DONE", len(results), "topics total")
