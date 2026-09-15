import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Chapter } from "../schema";
import { theme } from "../theme";

/**
 * 幕・章の切り替わりに挟むカード。
 * 台本側のオープンループ連鎖（「ここまでが〜」「では〜」）と同じ位置に置く。
 */
export const ChapterCard: React.FC<{ chapter: Chapter }> = ({ chapter }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(chapter.durationSec * fps));
  const fade = Math.min(
    interpolate(frame, [0, Math.round(fps * 0.4)], [0, 1], { extrapolateRight: "clamp" }),
    interpolate(frame, [total - Math.round(fps * 0.4), total], [1, 0], { extrapolateLeft: "clamp" })
  );
  const line = interpolate(frame, [0, Math.round(fps * 0.8)], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "rgba(11,11,13,.86)",
        justifyContent: "center",
        alignItems: "center",
        opacity: fade,
      }}
    >
      <div style={{ fontFamily: theme.fontFamily, color: theme.accent, fontSize: 40, letterSpacing: "0.3em" }}>
        {chapter.label}
      </div>
      <div
        style={{
          width: `${line * 46}%`,
          height: 2,
          backgroundColor: theme.accent,
          margin: "28px 0",
        }}
      />
      <div
        style={{
          fontFamily: theme.fontFamily,
          color: theme.text,
          fontSize: 76,
          fontWeight: 700,
          textAlign: "center",
          padding: "0 80px",
        }}
      >
        {chapter.title}
      </div>
    </AbsoluteFill>
  );
};
