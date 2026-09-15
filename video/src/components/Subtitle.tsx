import React from "react";
import { AbsoluteFill } from "remotion";
import type { Subtitle as SubtitleType } from "../schema";
import { theme } from "../theme";

/**
 * 画面下の字幕。ナレーションと1対1で出す。
 * 1文が短い台本なので、1枚あたり20字前後に収まる前提。
 */
export const Subtitle: React.FC<{ subtitle: SubtitleType }> = ({ subtitle }) => (
  <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 72 }}>
    <div
      style={{
        fontFamily: theme.subtitleFontFamily,
        fontWeight: 700,
        fontSize: 46,
        lineHeight: 1.4,
        color: theme.text,
        textShadow: theme.textShadow,
        WebkitTextStroke: "1.5px rgba(0,0,0,.8)",
        textAlign: "center",
        maxWidth: "84%",
      }}
    >
      {subtitle.text}
    </div>
  </AbsoluteFill>
);
