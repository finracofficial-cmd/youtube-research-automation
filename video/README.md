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

## 検証済みのこと

- `npx tsc --noEmit` が通る
- 静止画レンダリング成功（字幕の日本語表示とタイミングを目視確認）
- 動画レンダリング成功（241フレーム / 8秒 / 3.2MB）
- カット検出を合成動画（既知のカット2箇所）で検証（tests/test_edit_analysis.py）

## 未着手

- ナレーション音声（TTS）の生成と、それに合わせた字幕の再タイミング
- サムネイル生成
- 素材の自動収集（PD/CC画像）
