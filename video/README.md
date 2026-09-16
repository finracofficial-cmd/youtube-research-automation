# video — 編集（工程C）

台本と素材から動画を組む Remotion プロジェクトと、参照動画の編集リズムを測る道具。

## 構成

```
video/
  src/            Remotion のコンポーネント
    Root.tsx        コンポジション登録。尺は props から自動計算
    Documentary.tsx 本体。画→章カード→テロップ→字幕の順に重ねる
    schema.ts       props の zod スキーマ
    theme.ts        色とフォント
    components/     KenBurns / Telop / Subtitle / ChapterCard
  build_props.py  台本 → props.json
  analyze_edit.py 動画 → カット点とリズムの統計
  public/         素材（shots/ に画像を置く）
```

## 使い方

```bash
# 1) 台本から props.json を組む
python3 video/build_props.py drafts/oparts_v1.txt --duration 900 --kind bundle --claims 5

# 2) 素材を public/shots/ に 000.jpg, 001.jpg ... と置く

# 3) 確認（ブラウザのスタジオが開く）
cd video && npm run studio

# 4) レンダリング
cd video && npx remotion render src/index.ts Documentary out/video.mp4 --props=props.json
```

字幕は台本の文字数按分で割り付ける。ナレーション音声ができたら
`--narration` で渡して、実測の尺に合わせる。

## 参照動画の編集リズムを測る

```bash
python3 video/analyze_edit.py <動画> --threshold 0.30 --frames-dir frames/ --out stats.json
```

カット点を検出して、1分あたりのカット数と1カットの長さを出す。
その実測値を `build_props.py --shot-sec` に入れれば、リズムを合わせられる。

**ffmpeg のシーン検出は輝度平面しか見ない。** 明るさが近い画どうしの切り替わりは、
色がまったく違っても検出されない（ffmpeg の `red` と `green` はどちらも Y=81 で差がゼロ）。
暗い写本画像が続く構成では取りこぼすので、`--threshold` を下げて調整する。
テストを書いたとき、まさにこれで落ちた。

参照動画から取り出したフレームは**寸法の計測用**。
映像そのものは制作者の著作物なので、自分の動画には使わない。
素材はPD/CCのものを別途集める（元チャンネルもそうしている）。

## オーバーレイ部品

背景（Ken Burns）と字幕だけでは、参照チャンネルの画面は作れない。
上に載る構造化された部品が要る。

| 部品 | props | 用途 |
|---|---|---|
| `SourceLabel` | `sourceLabels` | 左上に出しっぱなしの出典表記。**CC BY の表示義務もこれで満たす** |
| `QuoteCard` | `quoteCards` | 見出し／原文／訳／出典 の4段パネル。左右中央に配置できる |
| `ChipStack` | `chipStacks` | `a ⇄ o` のような小さなトークンの縦積み。対応関係の提示 |
| `CardRow` | `cardRows` | 横並びカード。`dimmed` で「今回は使わない」を表す |
| `DocumentCard` | `documentCards` | 論文の1ページ目を紙色で再現。出典を「見せる」 |
| `BackgroundPlate` | `backgroundDim` | 背景を落としてビネット。文字を載せる下地 |

重ね順は 画 → 下地 → カード類 → 出典ラベル → 章カード → テロップ → 字幕。
**出典ラベルを他のカードより上に置いている**のは、表示義務のあるものを隠さないため。

全部 HTML/CSS で、映像エフェクトではない。Remotion の得意分野なので、
新しい型の部品が要るときは同じ要領で足せる。

## 検証済みのこと

- `npx tsc --noEmit` が通る
- 静止画レンダリング成功（字幕の日本語表示とタイミングを目視確認）
- 動画レンダリング成功（241フレーム / 8秒 / 3.2MB）
- カット検出を合成動画（既知のカット2箇所）で検証（tests/test_edit_analysis.py）
- オーバーレイ部品を実素材の上に重ねて描画確認（`demo.json`）。
  引用カード・出典ラベル・チップ・カード列の減光状態まで目視で確認済み

## 未着手

- ナレーション音声（TTS）の生成と、それに合わせた字幕の再タイミング
- サムネイル生成
- 背景のピラーボックス（画を内側に嵌めて左右を暗く落とす表現）
- 図解・グラフの部品（数値を示すカット用）

## 台本からの自動組版（autolayout.py）

台本自身の言い回しが、出すべき部品を示している。修辞の型をそのまま規則にした。

| 台本の書き方 | 出る部品 |
|---|---|
| `2006年にネイチャーへ載る` | `DocumentCard`（年号＋掲載誌を抜く） |
| `主張はこうだ。` → 次の文 | `QuoteCard`（次の1〜2文を中身に） |
| `5つを並べた` / `四つに分かれる` | `CardRow`（個数ぶんのカード） |
| `ただし、決着はしていない` | `QuoteCard`（逆側に留保として） |
| 1文に数字が3つ以上 | `ChipStack` |
| それ以外 | 何も出さない（画と字幕だけ） |

```bash
python3 video/build_props.py drafts/oparts_v1.txt --duration 900 --kind bundle \
  --claims 5 --manifest video/public/shots/manifest.json
# -> 字幕320枚 / カット112 / 章5 / オーバーレイ10件 / 出典ラベル7件
```

**出典ラベルは manifest から自動生成される。** 素材の作者とライセンスが各カットの
表示中ずっと左上に出るので、CC BY の表示義務が構造的に満たされる。

密度は抑える方に倒している。15分でオーバーレイ10件。出しすぎると読めない。
`schedule()` が最低間隔 1.2秒 を守り、画面中央を占める部品は同時に1つだけにする。

## 描画するときの注意（実際に事故った）

**Remotion は `staticFile()` をプロセスの作業ディレクトリ基準で解決する。**
リポジトリ直下から `npx --prefix video remotion ...` と呼ぶと `public/` を見失い、
**エラーを出さずに画像が全部消えた黒い動画が出来上がる。**
`video/render.sh` 経由で叩けば必ず正しい場所で動く。

```bash
cd video && PROPS=props.json ./render.sh render src/index.ts Documentary out/video.mp4
```
