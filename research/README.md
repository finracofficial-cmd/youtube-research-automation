# research — 一次資料の収集（台本生成の前段）

台本の数字密度は文体ではなく**調査の深さ**で決まる。
工程Bの実測で、記憶だけで書くと `numerics_per_min` が参照動画の72%で頭打ちになった。
だから台本を書く前に、必ずここを通す。

```bash
python -m research dossier  seeds/topics/oparts.yaml            # 取材メモを作る
python -m research pipeline seeds/topics/oparts.yaml --duration 900  # 調査→台本プロンプト
python -m script_engine check drafts/draft.txt --duration 900   # 書いたものを検証
```

## 題材の仕様（seeds/topics/*.yaml）

```yaml
subject: オーパーツ
subject_en: out-of-place artifact archaeology   # 学術DBに投げる英語
genre: 古代の謎
claims:
  - ja: デリーの鉄柱は1600年錆びていない
    en: Delhi iron pillar corrosion              # 主張ごとに英語クエリを持たせる
```

**`en` は学術文献で実際に使われている語にすること。** 日本語では学術DBが引けない。
また「オーパーツ」のような通俗語は学術用語ではないので、題材レベルの検索は
無関係な論文を拾う（実測: `out-of-place artifact archaeology` で `Archaeology of Place` が上位）。
**精度が出るのは主張別のクエリなので、そちらを先にプロンプトへ入れている。**

## 引いている先

| 系統 | ソース | 状況 |
|---|---|---|
| 査読論文 | OpenAlex → 失敗時 Crossref | OpenAlexは抄録が取れるが、環境によってはプロキシが恒常的に429を返す |
| パブリックドメイン原典 | archive.org | 安定。元チャンネルもここを多用している |

OpenAlexが落ちると一度で諦める（サーキットブレーカー）。
毎回リトライすると1クエリあたり90秒を捨てるため。

## 文献の厚みが、束ね型の並び順を決める

主張ごとに `evidence_level` を出す。

| 査読文献 | 判定 | 束ね型での位置 |
|---|---|---|
| 5件以上 | 厚い | **当たっている**側 |
| 1〜4件 | 薄い | **理由が違う**側 |
| 0件 | 文献なし | **跡形もなくなる**側。近代の創作を疑う |

**学術文献がまったく出ないことは、収集の失敗ではなく主張の性質を表す信号。**
実測で、バグダッド電池とコソ加工物がここで0件になった。
どちらも台本では「跡形もなくなるもの」に置いており、判定と一致している。

## 実測での検証

`seeds/topics/oparts.yaml` を流したとき、デリーの鉄柱の主張に対して
査読文献が正しく返ってきた:

```
2000 On the corrosion resistance of the Delhi iron pillar
2000 Characterization of Delhi iron pillar rust by X-ray diffraction
1970 The "rustless" iron pillar at Delhi
```

archive.org からは
`Antikythera mechanism (analog computer) identified by Archaeologist Valerios Stais - May 17, 1902`
が返り、台本に書いた「1902年・スタイス」の裏が取れた。

## 既知の限界

- **数字入り記述が取れていない**。抄録が要るが、Crossrefは抄録の収録率が低く
  （実測 35件中3件）、抄録が充実しているOpenAlexはこの環境では429で通らない。
  通常のIPからなら機能する
- 収集されるのは**候補**であって、裏取り済みの事実ではない。
  本文に当たる工程は人間に残る。`check` が通ることは文体と構造の保証であって、
  事実の保証ではない
