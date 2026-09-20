import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Telop as TelopType } from "../schema";
import { zoneStyle } from "./Infographics";
import { theme } from "../theme";

/** 強調したい一言を出す。center は結論の提示、upper は空き時間を埋める語句。
 *
 * 1本に35枚以上出る。全部が同じ出方だと、画面が止まって見える。文字を1字ずつ
 * 立ち上げ、下に線を引く。参考chは札が1枚ずつ積み上がる作りで、こちらは
 * 出ては消えるだけだった。 */
export const Telop: React.FC<{ telop: TelopType }> = ({ telop }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(telop.durationSec * fps));

  const exit = interpolate(frame, [total - Math.round(fps * 0.25), total], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const impact = telop.variant === "impact";
  const chars = Array.from(telop.text);
  // 字送りは全体で0.5秒に収める。長い語でも遅れて読めなくならないように
  const each = Math.min(0.055, 0.5 / Math.max(1, chars.length));
  const rule = interpolate(
    frame,
    [Math.round(fps * (0.1 + chars.length * each)), Math.round(fps * (0.5 + chars.length * each))],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill style={{ ...zoneStyle(telop.zone), opacity: exit }}>
      <div style={{ padding: "0 80px", textAlign: "center" }}>
        <div
          style={{
            fontFamily: theme.fontFamily,
            fontWeight: 900,
            fontSize: impact ? 128 : 72,
            color: impact ? theme.accent : theme.text,
            textShadow: theme.textShadow,
            letterSpacing: "0.04em",
            WebkitTextStroke: impact ? "3px rgba(0,0,0,.85)" : "2px rgba(0,0,0,.7)",
          }}
        >
          {chars.map((c, i) => {
            const at = spring({
              frame: frame - Math.round(fps * (0.06 + i * each)),
              fps,
              config: { damping: 200, stiffness: 150 },
            });
            return (
              <span
                key={i}
                style={{
                  display: "inline-block",
                  opacity: at,
                  transform: `translateY(${(1 - at) * 18}px)`,
                }}
              >
                {c === " " ? "\u00a0" : c}
              </span>
            );
          })}
        </div>
        <div
          style={{
            height: 3,
            marginTop: 18,
            marginLeft: "auto",
            marginRight: "auto",
            width: `${rule * 72}%`,
            backgroundColor: impact ? theme.accent : "rgba(244,241,234,.55)",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
