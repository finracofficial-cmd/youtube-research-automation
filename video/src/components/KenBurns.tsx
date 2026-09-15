import React from "react";
import { AbsoluteFill, Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Shot } from "../schema";
import { theme } from "../theme";

/**
 * 静止画に緩やかな寄り引きを付ける。
 * 素材が静止画中心の構成なので、ここが動きのほぼ全てになる。
 */
export const KenBurns: React.FC<{ shot: Shot; resolve: (s: string) => string }> = ({
  shot,
  resolve,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(shot.durationSec * fps));
  const t = interpolate(frame, [0, total], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const scale = interpolate(t, [0, 1], [shot.from.scale, shot.to.scale]);
  const x = interpolate(t, [0, 1], [shot.from.x, shot.to.x]);
  const y = interpolate(t, [0, 1], [shot.from.y, shot.to.y]);

  // カット頭と尻に短いフェード。静止画の切り替わりが硬くなりすぎるのを防ぐ
  const fade = Math.min(
    interpolate(frame, [0, Math.round(fps * 0.3)], [0, 1], { extrapolateRight: "clamp" }),
    interpolate(frame, [total - Math.round(fps * 0.3), total], [1, 0], {
      extrapolateLeft: "clamp",
    })
  );

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg, opacity: fade }}>
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <Img
          src={resolve(shot.src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale}) translate(${x * 5}%, ${y * 5}%)`,
          }}
        />
      </AbsoluteFill>
      {shot.credit ? (
        <div
          style={{
            position: "absolute",
            right: 24,
            bottom: 18,
            fontSize: 18,
            color: "rgba(244,241,234,.75)",
            fontFamily: theme.subtitleFontFamily,
            textShadow: theme.textShadow,
          }}
        >
          {shot.credit}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
