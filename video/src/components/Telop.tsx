import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Telop as TelopType } from "../schema";
import { zoneStyle } from "./Infographics";
import { theme } from "../theme";

/** 強調したい一言を出す。center は結論の提示、upper は空き時間を埋める語句。 */
export const Telop: React.FC<{ telop: TelopType }> = ({ telop }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(telop.durationSec * fps));

  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: Math.round(fps * 0.35) });
  const exit = interpolate(frame, [total - Math.round(fps * 0.25), total], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const impact = telop.variant === "impact";

  return (
    <AbsoluteFill
      style={{
        ...zoneStyle(telop.zone),
        opacity: Math.min(enter, exit),
      }}
    >
      <div
        style={{
          fontFamily: theme.fontFamily,
          fontWeight: 900,
          fontSize: impact ? 128 : 72,
          color: impact ? theme.accent : theme.text,
          textShadow: theme.textShadow,
          letterSpacing: "0.04em",
          textAlign: "center",
          padding: "0 80px",
          transform: `scale(${interpolate(enter, [0, 1], [0.94, 1])})`,
          WebkitTextStroke: impact ? "3px rgba(0,0,0,.85)" : "2px rgba(0,0,0,.7)",
        }}
      >
        {telop.text}
      </div>
    </AbsoluteFill>
  );
};
