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

/* 寸法を入れた立体。
 *
 * 参考chは "3D model · 146 m · lettering after the written accounts only" と
 * 出典を添えて自作の立体を出している。Commons に動画はほぼ無く（実測で
 * 古代遺跡系242点中1点）、素材を探しても埋まらない。ここで作る。
 *
 * 地は明るい灰。参考chも立体だけ明るい背景に置いていて、写真の区間と
 * 見分けがつく。「これは資料ではなく、こちらで作った図」という合図になる。 */
const STUDIO = "#c9cdc8";
const SOLID = "#e8eae6";
const SOLID_DARK = "#b9bdb8";

const Silhouette: React.FC<{ h: number; x: number }> = ({ h, x }) => (
  <g transform={`translate(${x}, ${560 - h}) scale(${h / 100})`} opacity={0.55}>
    <circle cx={0} cy={12} r={11} fill="#5c6160" />
    <rect x={-9} y={26} width={18} height={44} rx={6} fill="#5c6160" />
    <rect x={-8} y={68} width={6} height={32} rx={3} fill="#5c6160" />
    <rect x={2} y={68} width={6} height={32} rx={3} fill="#5c6160" />
  </g>
);

const Model: React.FC<{ e: ExplainerType; step: (i: number) => number }> = ({ e, step }) => {
  const grow = step(1);
  const dim = step(2);
  const count = step(3);
  const H = 360 * grow;
  const base = 560;
  const cx = 420;
  const target = e.dimension?.value ?? 0;
  const shown = target
    ? Math.round(target * Math.min(1, count) * 100) / 100
    : 0;
  const unit = (e.dimension?.readout ?? "").replace(/^[0-9.,]+/, "");

  const body = () => {
    switch (e.shape) {
      case "pyramid":
        return (
          <>
            <polygon points={`${cx},${base - H} ${cx - 250},${base} ${cx + 250},${base}`} fill={SOLID} />
            <polygon points={`${cx},${base - H} ${cx + 250},${base} ${cx + 120},${base}`} fill={SOLID_DARK} />
          </>
        );
      case "column":
        return (
          <>
            <rect x={cx - 52} y={base - H} width={104} height={H} fill={SOLID} />
            <rect x={cx + 28} y={base - H} width={24} height={H} fill={SOLID_DARK} />
            <ellipse cx={cx} cy={base - H} rx={52} ry={14} fill="#f2f4f0" />
          </>
        );
      case "disc":
        return (
          <>
            <ellipse cx={cx} cy={base - H / 2} rx={210} ry={Math.max(10, H / 2)} fill={SOLID} />
            <ellipse cx={cx} cy={base - H / 2 - 6} rx={210} ry={Math.max(8, H / 2 - 6)} fill="#f2f4f0" />
          </>
        );
      default:
        return (
          <>
            <rect x={cx - 170} y={base - H} width={340} height={H} fill={SOLID} />
            <polygon points={`${cx - 170},${base - H} ${cx - 110},${base - H - 46} ${cx + 230},${base - H - 46} ${cx + 170},${base - H}`} fill="#f2f4f0" />
            <polygon points={`${cx + 170},${base - H} ${cx + 230},${base - H - 46} ${cx + 230},${base - 46} ${cx + 170},${base}`} fill={SOLID_DARK} />
          </>
        );
    }
  };

  return (
    <div style={{ marginTop: 40 }}>
      <svg viewBox="0 0 1100 620" style={{ width: "100%", height: 520 }}>
        <rect x={0} y={0} width={1100} height={620} fill={STUDIO} />
        <line x1={0} y1={base} x2={1100} y2={base} stroke="#a7aca6" strokeWidth={2} />
        {body()}
        {/* 人は物の高さに対する比で描く。固定値だと縮尺の嘘になる */}
        {e.humanRatio > 0 && (
          <Silhouette h={Math.max(14, H * e.humanRatio)} x={cx + 250} />
        )}
        {/* 寸法線。伸びきってから数字が上がる */}
        <g opacity={dim} stroke="#3c4140" strokeWidth={2}>
          <line x1={cx + 300} y1={base} x2={cx + 300} y2={base - H * dim} />
          <line x1={cx + 288} y1={base} x2={cx + 312} y2={base} />
          <line x1={cx + 288} y1={base - H} x2={cx + 312} y2={base - H} />
        </g>
        <text
          x={cx + 330}
          y={base - H / 2}
          fill="#23262a"
          fontFamily={theme.fontFamily}
          fontSize={52}
          opacity={count}
        >
          {shown.toLocaleString("ja-JP")}
          <tspan fontSize={30}>{unit}</tspan>
        </text>
        <text
          x={cx + 330}
          y={base - H / 2 + 42}
          fill="#4e5350"
          fontFamily={theme.subtitleFontFamily}
          fontSize={24}
          opacity={count}
        >
          {e.dimension?.label ?? ""}
        </text>
      </svg>
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
        {explainer.kind === "model" && <Model e={explainer} step={step} />}
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
