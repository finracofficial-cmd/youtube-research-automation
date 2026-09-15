"""束ね型の切り口を機械生成する。脈 × 切り口 × 地域。"""
SUBJECTS = ["古代文明","超古代文明","巨石遺跡","オーパーツ","未解読文書","古代技術",
            "未解決事件","失踪事件","怪奇現象","古代生物","消えた文明","古代兵器",
            "地下遺跡","海底遺跡","古代宗教","ミイラ","呪い","予言","暗号","古代の巨人",
            "未確認生物","심령"]
ANGLES = ["謎","真相","捏造"]
REGIONS = ["古代エジプト","マヤ文明","インカ帝国","古代中国","古代日本","メソポタミア",
           "古代ギリシャ","古代ローマ","縄文時代","アステカ"]
qs = []
for s in SUBJECTS:
    if any(ord(c) > 0xAC00 and ord(c) < 0xD7A3 for c in s):
        continue
    qs.append(s)
    for a in ANGLES:
        qs.append(f"{s} {a}")
for r in REGIONS:
    qs += [f"{r} 謎", f"{r} 未解明"]
seen, out = set(), []
for q in qs:
    if q not in seen:
        seen.add(q); out.append(q)
open("seeds/items/framings.txt","w",encoding="utf-8").write("\n".join(out))
print(len(out), "framings generated")
