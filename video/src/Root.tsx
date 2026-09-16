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
  glyphs: [],
  grids: [],
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
    // 尺は props から決める。素材の最後尾＋余白を全体尺とする
    calculateMetadata={({ props }) => {
      const ends = [
        ...props.shots.map((s) => s.startSec + s.durationSec),
        ...props.subtitles.map((s) => s.startSec + s.durationSec),
        ...props.telops.map((t) => t.startSec + t.durationSec),
      ];
      const last = ends.length ? Math.max(...ends) : 3;
      return { durationInFrames: Math.max(1, Math.round((last + 1) * FPS)) };
    }}
  />
);
