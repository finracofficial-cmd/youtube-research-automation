"""束ね型の切り口を機械生成する。

実測で分かったこと（analysis/cadence_and_inventory.md）:
- アイテム単体（デンデラの電球など）は需要が無く、0.28以上が4/20、「狙う」は0件
- 束ね（脈）レベルにすると 0.28以上が80/104、「狙う」が48件

つまり動画1本の単位は「脈 × 切り口」であって、個別アイテムではない。
個別アイテムは素材として束ねの中に配置する（seeds/items/ 参照）。

104件生成して48件が「狙う」＝歩留まり46%。本数が要るときは軸を足して生成数を増やす。
"""
from __future__ import annotations

# 脈。量産系が擦っていて、かつ一次資料が存在する主題。
SUBJECTS = [
    "古代文明", "超古代文明", "巨石遺跡", "オーパーツ", "未解読文書", "古代技術",
    "未解決事件", "失踪事件", "怪奇現象", "古代生物", "消えた文明", "古代兵器",
    "地下遺跡", "海底遺跡", "古代宗教", "ミイラ", "呪い", "予言", "暗号",
    "古代の巨人", "未確認生物",
]

# 切り口。「謎」は需要、「真相」「捏造」は検証フォーマットとの相性が良い。
ANGLES = ["謎", "真相", "捏造", "未解明"]

# 地域・時代。SUBJECT と掛けると索引上は別スロットになる（実測: 結果の重なり中央値0.00）。
REGIONS = [
    "古代エジプト", "マヤ文明", "インカ帝国", "古代中国", "古代日本", "メソポタミア",
    "古代ギリシャ", "古代ローマ", "縄文時代", "アステカ", "古代インド", "シュメール",
]


def generate(*, subjects=None, angles=None, regions=None,
             cross_region: bool = True) -> list[str]:
    """検索クエリとして成立する形で切り口を組み上げる。

    cross_region=True で「マヤ文明 オーパーツ」のような地域×脈の掛け合わせも出す。
    生成数を増やしたいときはここを広げる。
    """
    # 空リストを渡された場合に既定へ落ちないよう None で判定する
    subjects = SUBJECTS if subjects is None else subjects
    angles = ANGLES if angles is None else angles
    regions = REGIONS if regions is None else regions

    out: list[str] = []
    for s in subjects:
        out.append(s)
        out += [f"{s} {a}" for a in angles]
    for r in regions:
        out += [f"{r} {a}" for a in ("謎", "未解明")]
        if cross_region:
            # 地域 × 脈。索引上の別スロットを作る主力
            out += [f"{r} {s}" for s in ("オーパーツ", "巨石遺跡", "未解読文書", "古代技術")]

    seen: set[str] = set()
    uniq = []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq
