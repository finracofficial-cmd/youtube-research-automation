import sys, time
sys.path.insert(0, ".")
from topic_scout.fetch import search
from topic_scout.classify import tag_all
from topic_scout.features import build
from topic_scout.score import score_topic
items = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
rows = []
for q in items:
    try:
        f = build(q, tag_all(search(q, limit=25)))
        rows.append((score_topic(f), f))
    except Exception as e:
        print(f"FAIL {q}: {str(e)[:60]}", flush=True); continue
    time.sleep(2)
rows.sort(key=lambda r: -r[0].score)
print(f"{'アイテム':<24}{'判定':<7}{'score':>7}{'需要':>7}{'空白':>7}  {'上位25%再生':>11}{'量産率':>7}")
print("-" * 82)
for sc, f in rows:
    print(f"{sc.query[:23]:<24}{sc.verdict:<7}{sc.score:>7.3f}{sc.demand:>7.2f}{sc.gap:>7.2f}  {f.views_p75:>11,.0f}{f.low_effort_ratio:>7.0%}")
n = sum(1 for sc, _ in rows if sc.score >= 0.28)
print(f"\n0.28以上（条件付き以上）: {n}/{len(rows)} = {n/max(len(rows),1):.0%}")
