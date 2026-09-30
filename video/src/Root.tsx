import React from "react";
import { Composition } from "remotion";
import { Documentary } from "./Documentary";
import { documentarySchema, type DocumentaryProps } from "./schema";

const FPS = 30;

/** props が空でもスタジオが開くように、最小限の既定値を置く。 */
const defaultProps: DocumentaryProps = {
  bgmVolume: 0.12,
  shots: [],
  telops: [{ startSec: 0, durationSec: 3, text: "props.json を渡してください", variant: "plain", zone: "center" }],
  subtitles: [],
  chapters: [],
  sourceLabels: [],
  quoteCards: [],
  chipStacks: [],
  cardRows: [],
  documentCards: [],
  stats: [],
  portraits: [],
  charts: [],
  timelines: [],
  rangeBars: [],
  glyphs: [],
  grids: [],
  explainers: [],
  backgroundDim: 0.45,
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Documentary"
    component={Documentary}
    schema={documentarySchema}
    fps={FPS}
    width={1920}
    height={1080}
    defaultProps={defaultProps}
    // 尺は props から決める。素材の最後尾＋余白を全体尺とする。
    // props はここで schema に通して既定値を埋めてから部品に渡す。--props で渡した JSON は
    // 既定値が埋まらないまま部品に届き、points の無い折れ線が 26,558 フレーム目（描画を
    // 70分回したあと）で落ちた（Make video #10）。形が schema と合わなければ、ここで
    // 1フレーム目より前に止まる
    calculateMetadata={({ props }) => {
      const parsed = documentarySchema.parse(props);
      const ends = [
        ...parsed.shots.map((s) => s.startSec + s.durationSec),
        ...parsed.subtitles.map((s) => s.startSec + s.durationSec),
        ...parsed.telops.map((t) => t.startSec + t.durationSec),
      ];
      const last = ends.length ? Math.max(...ends) : 3;
      return { durationInFrames: Math.max(1, Math.round((last + 1) * FPS)), props: parsed };
    }}
  />
);
