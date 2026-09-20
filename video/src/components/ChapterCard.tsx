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

      {/* 進捗バー。参考chは画面下に位置を示すバーと「ここから最後の話」の
          印を出していた。どこまで来たかが見えると、先を見る理由になる。 */}
      {chapter.span > 0 && (
        <div style={{ position: "absolute", left: "12%", right: "12%", bottom: 208 }}>
          <div style={{ position: "relative", height: 4, background: "rgba(244,241,234,.16)" }}>
            {/* ここまで来た分 */}
            <div style={{
              position: "absolute", left: 0, top: 0, bottom: 0,
              width: `${chapter.progress * 100}%`,
              background: "rgba(244,241,234,.42)",
            }} />
            {/* この章の区間 */}
            <div style={{
              position: "absolute", top: -3, bottom: -3,
              left: `${chapter.progress * 100}%`,
              width: `${Math.max(0.01, chapter.span) * 100 * line}%`,
              background: theme.accent,
            }} />
          </div>
          <div style={{
            marginTop: 16, textAlign: "center",
            fontFamily: theme.subtitleFontFamily, fontSize: 22,
            letterSpacing: ".08em", color: "rgba(244,241,234,.5)",
            opacity: line,
          }}>
            {chapter.last ? "ここから最後の話" : `全体の ${Math.round(chapter.progress * 100)}% 地点`}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
