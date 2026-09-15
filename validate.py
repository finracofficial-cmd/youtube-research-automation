"""既知の3本で逆算検証する。

自チャンネルの動画は競合から除外し、「投稿する前の状態」で採点したときに
実際の結果（hit / miss）と順序が一致するかを見る。
"""
import sys
sys.path.insert(0, ".")
import yaml
from topic_scout.fetch import search
from topic_scout.classify import tag_all
from topic_scout.features import build
from topic_scout.score import score_topic

OWN = {"UCUnrqhR-Zy5uPtberKdCH0A"}  # 大人の自由研究

cfg = yaml.safe_load(open("seeds/candidates.yaml", encoding="utf-8"))
print(f"{'題材':<22}{'実績再生':>12} {'実際':<6}{'判定':<8}{'score':>7}{'需要':>7}{'空白':>7}{'時流':>7}")
print("-" * 92)
rows = []
for v in cfg["validation"]:
    vids = search(v["query"], limit=30)
    f = build(v["query"], tag_all(vids), exclude_channel_ids=OWN)
    sc = score_topic(f)
    rows.append((v, f, sc))
    print(f"{v['query'][:21]:<22}{v['actual_views']:>12,} {v['outcome']:<6}{sc.verdict:<8}"
          f"{sc.score:>7.3f}{sc.demand:>7.2f}{sc.gap:>7.2f}{sc.trend:>7.2f}")

print("\n### 内訳")
for v, f, sc in rows:
    print(f"\n-- {v['query']} （実績 {v['actual_views']:,}再生／{v['outcome']}）")
    print(f"   上位25%再生={f.views_p75:,.0f} 最高={f.views_max:,} 100k超Ch={f.distinct_channels_over_100k} "
          f"低品質率={f.low_effort_ratio:.0%} 中央尺={f.median_duration//60}分")
    print(f"   真面目長尺={f.n_serious_longform}本 最高{f.best_serious_views:,}再生  AI切り口={f.ai_angle_ratio:.0%}")
    for r in sc.reasons:
        print(f"   - {r}")

order_ok = rows[0][2].score == max(r[2].score for r in rows)
print(f"\n順序判定: バズ題材が最高スコア = {order_ok}")
