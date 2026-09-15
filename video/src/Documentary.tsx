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
