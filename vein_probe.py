"""脈（オーパーツ等）の中に、個別エピソードが何本埋まっているかを測る。"""
import sys, time, json, collections
sys.path.insert(0, ".")
from topic_scout.fetch import search
from topic_scout.discover import extract_terms

VEINS = {
    "オーパーツ": ["オーパーツ", "オーパーツ 一覧", "オーパーツ 検証"],
    "ロストテクノロジー": ["ロストテクノロジー", "失われた技術 古代"],
    "地上絵": ["ナスカの地上絵", "地上絵 謎"],
    "スフィンクス": ["スフィンクス 謎", "スフィンクス 侵食"],
    "死海文書": ["死海文書", "死海文書 謎"],
    "シュメール": ["シュメール 粘土板", "シュメール 謎"],
}
out = {}
for vein, queries in VEINS.items():
    titles, terms = [], collections.Counter()
    for q in queries:
        try:
            vids = search(q, limit=30)
        except Exception as e:
            print(f"  FAIL {q}: {str(e)[:70]}", flush=True); continue
        for v in vids:
            titles.append(v.title)
            for t in extract_terms(v.title):
                if t != vein and vein not in t:
                    terms[t] += 1
        time.sleep(3)
    # 2回以上出た固有名詞っぽい語だけ残す
    items = [t for t, n in terms.most_common() if n >= 2]
    out[vein] = {"n_titles": len(titles), "items": items}
    print(f"\n== {vein} ==  タイトル{len(titles)}本 / 反復語 {len(items)}種", flush=True)
    print("   " + " / ".join(items[:28]), flush=True)
json.dump(out, open("out/veins_items.json", "w"), ensure_ascii=False, indent=1)
