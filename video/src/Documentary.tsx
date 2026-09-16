import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
  useVideoConfig,
} from "remotion";
import type { DocumentaryProps } from "./schema";
import { KenBurns } from "./components/KenBurns";
import { Telop } from "./components/Telop";
import { Subtitle } from "./components/Subtitle";
import { ChapterCard } from "./components/ChapterCard";
import {
  BackgroundPlate, CardRow, ChipStack, DocumentCard, QuoteCard, SourceLabel,
} from "./components/Overlays";
import { theme } from "./theme";

/** http(s) はそのまま、それ以外は public/ からの相対パスとして解決する。 */
const resolve = (src: string) =>
  /^https?:\/\//.test(src) ? src : staticFile(src);

const secToFrames = (sec: number, fps: number) => Math.round(sec * fps);

export const Documentary: React.FC<DocumentaryProps> = ({
  narration,
  bgm,
  bgmVolume,
  shots,
  telops,
  subtitles,
  chapters,
  sourceLabels,
  quoteCards,
  chipStacks,
  cardRows,
  documentCards,
  backgroundDim,
}) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {/* 画（静止画のKen Burns） */}
      {shots.map((shot, i) => (
        <Sequence
          key={`shot-${i}`}
          from={secToFrames(shot.startSec, fps)}
          durationInFrames={secToFrames(shot.durationSec, fps)}
        >
          <KenBurns shot={shot} resolve={resolve} />
        </Sequence>
      ))}

      {/* 画の上に下地を敷く。ここから上は全部この上に載る */}
      <BackgroundPlate dim={backgroundDim} />

      {/* 構造化オーバーレイ */}
      {cardRows.map((row, i) => (
        <Sequence key={`row-${i}`} from={secToFrames(row.startSec, fps)}
          durationInFrames={secToFrames(row.durationSec, fps)}>
          <CardRow row={row} />
        </Sequence>
      ))}
      {documentCards.map((card, i) => (
        <Sequence key={`doc-${i}`} from={secToFrames(card.startSec, fps)}
          durationInFrames={secToFrames(card.durationSec, fps)}>
          <DocumentCard card={card} />
        </Sequence>
      ))}
      {quoteCards.map((card, i) => (
        <Sequence key={`quote-${i}`} from={secToFrames(card.startSec, fps)}
          durationInFrames={secToFrames(card.durationSec, fps)}>
          <QuoteCard card={card} />
        </Sequence>
      ))}
      {chipStacks.map((stack, i) => (
        <Sequence key={`chips-${i}`} from={secToFrames(stack.startSec, fps)}
          durationInFrames={secToFrames(stack.durationSec, fps)}>
          <ChipStack stack={stack} />
        </Sequence>
      ))}

      {/* 出典ラベルは常に上。CC BY の表示義務を隠さないため */}
      {sourceLabels.map((label, i) => (
        <Sequence key={`src-${i}`} from={secToFrames(label.startSec, fps)}
          durationInFrames={secToFrames(label.durationSec, fps)}>
          <SourceLabel label={label} />
        </Sequence>
      ))}

      {/* 章カード。画より上、字幕より下 */}
      {chapters.map((chapter, i) => (
        <Sequence
          key={`chapter-${i}`}
          from={secToFrames(chapter.startSec, fps)}
          durationInFrames={secToFrames(chapter.durationSec, fps)}
        >
          <ChapterCard chapter={chapter} />
        </Sequence>
      ))}

      {/* 強調テロップ */}
      {telops.map((telop, i) => (
        <Sequence
          key={`telop-${i}`}
          from={secToFrames(telop.startSec, fps)}
          durationInFrames={secToFrames(telop.durationSec, fps)}
        >
          <Telop telop={telop} />
        </Sequence>
      ))}

      {/* 字幕は常に最前面 */}
      {subtitles.map((subtitle, i) => (
        <Sequence
          key={`sub-${i}`}
          from={secToFrames(subtitle.startSec, fps)}
          durationInFrames={secToFrames(subtitle.durationSec, fps)}
        >
          <Subtitle subtitle={subtitle} />
        </Sequence>
      ))}

      {bgm ? <Audio src={resolve(bgm)} volume={bgmVolume} /> : null}
      {narration ? <Audio src={resolve(narration)} /> : null}
    </AbsoluteFill>
  );
};
