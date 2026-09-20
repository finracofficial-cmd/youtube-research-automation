import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Explainer as ExplainerType } from "../schema";
import { theme } from "../theme";

/* 画面いっぱいの解説パネル。
 *
 * 参考chは、写真の上に札を載せるだけでなく、作図だけで構成された区間を
 * 挟んでいる。こちらは全フレームが「写真＋札」で、その状態が無かった。
 * ここは素材を隠して不透明に覆う。出典ラベルも一緒に消す（写真が出て
 * いないのに帰属を出すと、出所の表示として誤りになる）。 */

/** 段階的に出す。i 番目が step(i) で立ち上がる。 */
const useStep = (holdSec = 0.55) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (i: number) =>
    spring({
      frame: frame - Math.round(fps * (0.35 + i * holdSec)),
      fps,
      config: { damping: 200, stiffness: 120 },
    });
};

const useFade = (durationSec: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(durationSec * fps));
  return Math.min(
    interpolate(frame, [0, Math.round(fps * 0.35)], [0, 1], { extrapolateRight: "clamp" }),
    interpolate(frame, [total - Math.round(fps * 0.35), total], [1, 0], { extrapolateLeft: "clamp" })
  );
};

/** 方眼。資料を広げた面に見せる。無地だとスライドに見える。 */
const Paper: React.FC = () => (
  <AbsoluteFill
    style={{
      backgroundColor: theme.bg,
      backgroundImage:
        "linear-gradient(rgba(244,241,234,.045) 1px, transparent 1px)," +
        "linear-gradient(90deg, rgba(244,241,234,.045) 1px, transparent 1px)",
      backgroundSize: "64px 64px",
    }}
  />
);

const Heading: React.FC<{ text: string; at: number }> = ({ text, at }) => (
  <div style={{ opacity: at, transform: `translateY(${(1 - at) * 14}px)` }}>
    <div
      style={{
        fontFamily: theme.fontFamily,
        fontSize: 58,
        letterSpacing: ".06em",
        color: theme.text,
      }}
    >
      {text}
    </div>
    <div
      style={{
        marginTop: 18,
        height: 2,
        width: `${at * 100}%`,
        backgroundColor: theme.accent,
      }}
    />
  </div>
);

/** 言われていること / 資料が言っていること。このchの型そのもの。 */
const Contrast: React.FC<{ e: ExplainerType; step: (i: number) => number }> = ({ e, step }) => {
  const rows: { tag: string; body: string; accent: boolean }[] = [
    { tag: "言われていること", body: e.claim ?? "", accent: false },
    { tag: "資料が言っていること", body: e.evidence ?? "", accent: true },
  ].filter((r) => r.body);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 56, marginTop: 72 }}>
      {rows.map((r, i) => {
        const at = step(i + 1);
        return (
          <div
            key={r.tag}
            style={{
              opacity: at,
              transform: `translateX(${(1 - at) * (i % 2 ? 40 : -40)}px)`,
              borderLeft: `4px solid ${r.accent ? theme.accent : "rgba(244,241,234,.28)"}`,
              paddingLeft: 32,
            }}
          >
            <div
              style={{
                fontFamily: theme.subtitleFontFamily,
                fontSize: 30,
                letterSpacing: ".18em",
                color: r.accent ? theme.accent : "rgba(244,241,234,.6)",
                marginBottom: 16,
              }}
            >
              {r.tag}
            </div>
            <div
              style={{
                fontFamily: theme.fontFamily,
                fontSize: 58,
                lineHeight: 1.5,
                color: theme.text,
              }}
            >
              {r.body}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** 年表。線が引かれ、印が順に立つ。 */
const TimelineFull: React.FC<{ e: ExplainerType; step: (i: number) => number }> = ({ e, step }) => {
  const line = step(1);
  return (
    <div style={{ marginTop: 84, position: "relative" }}>
      <div
        style={{
          height: 2,
          width: `${line * 100}%`,
          backgroundColor: "rgba(244,241,234,.35)",
        }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: -1 }}>
        {e.marks.map((m, i) => {
          const at = step(i + 2);
          return (
            <div
              key={`${m.year}-${i}`}
              style={{ flex: 1, opacity: at, transform: `translateY(${(1 - at) * 18}px)` }}
            >
              <div
                style={{
                  width: 2,
                  height: 34,
                  backgroundColor: theme.accent,
                  transform: "translateY(-14px)",
                }}
              />
              <div
                style={{
                  fontFamily: theme.fontFamily,
                  fontSize: 52,
                  color: theme.text,
                  marginTop: 18,
                }}
              >
                {m.year}
              </div>
              <div
                style={{
                  fontFamily: theme.subtitleFontFamily,
                  fontSize: 28,
                  lineHeight: 1.55,
                  color: "rgba(244,241,234,.72)",
                  marginTop: 10,
                  paddingRight: 28,
                }}
              >
                {m.text}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** 量を並べて比べる。棒が伸びる。 */
const Scale: React.FC<{ e: ExplainerType; step: (i: number) => number }> = ({ e, step }) => {
  // 強調は最大の棒に付ける。並び順の1本目に付けると、話の要点でない方が
  // 赤くなる（実測で 25キロ が赤、250キロ が灰色になった）。
  const top = e.bars.reduce((best, b, i) => (b.value > (e.bars[best]?.value ?? -1) ? i : best), 0);
  return (
  <div style={{ display: "flex", flexDirection: "column", gap: 48, marginTop: 76 }}>
    {e.bars.map((b, i) => {
      const at = step(i + 1);
      return (
        <div key={`${b.label}-${i}`} style={{ opacity: Math.min(1, at * 1.6) }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: 12,
            }}
          >
            <span
              style={{
                fontFamily: theme.subtitleFontFamily,
                fontSize: 32,
                color: "rgba(244,241,234,.8)",
              }}
            >
              {b.label}
            </span>
            <span style={{ fontFamily: theme.fontFamily, fontSize: 56, color: theme.text }}>
              {b.readout}
            </span>
          </div>
          <div style={{ height: 24, backgroundColor: "rgba(244,241,234,.1)" }}>
            <div
              style={{
                height: "100%",
                width: `${at * Math.max(b.value, 0.02) * 100}%`,
                backgroundColor: i === top ? theme.accent : "rgba(244,241,234,.5)",
              }}
            />
          </div>
        </div>
      );
    })}
  </div>
  );
};

export const ExplainerPanel: React.FC<{ explainer: ExplainerType }> = ({ explainer }) => {
  const fade = useFade(explainer.durationSec);
  const step = useStep(explainer.kind === "timeline" ? 0.4 : 0.6);
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <Paper />
      <AbsoluteFill style={{ padding: "120px 128px 230px 128px", justifyContent: "center" }}>
        <Heading text={explainer.heading} at={step(0)} />
        {explainer.kind === "contrast" && <Contrast e={explainer} step={step} />}
        {explainer.kind === "timeline" && <TimelineFull e={explainer} step={step} />}
        {explainer.kind === "scale" && <Scale e={explainer} step={step} />}
        {explainer.note && (
          <div
            style={{
              position: "absolute",
              left: 124,
              bottom: 150,
              fontFamily: theme.subtitleFontFamily,
              fontSize: 26,
              color: "rgba(244,241,234,.55)",
              opacity: step(6),
            }}
          >
            {explainer.note}
          </div>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
