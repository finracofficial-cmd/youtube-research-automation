import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Chart, Glyph, Grid, Portrait, Stat, Timeline, Zone } from "../schema";
import { theme } from "../theme";

/** ゾーンごとの置き場所。同じゾーンの部品は同時に出さない前提。 */
export const zoneStyle = (zone: Zone): React.CSSProperties => {
  switch (zone) {
    case "left":
      return { alignItems: "flex-start", justifyContent: "center", padding: "0 0 0 72px" };
    case "right":
      return { alignItems: "flex-end", justifyContent: "center", padding: "0 72px 0 0" };
    case "lower":
      return { alignItems: "center", justifyContent: "flex-end", padding: "0 0 190px 0" };
    case "corner":
      return { alignItems: "flex-end", justifyContent: "flex-start", padding: "56px 72px 0 0" };
    default:
      return { alignItems: "center", justifyContent: "center" };
  }
};

const useFade = (durationSec: number, inSec = 0.3, outSec = 0.28) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(durationSec * fps));
  return Math.min(
    interpolate(frame, [0, Math.round(fps * inSec)], [0, 1], { extrapolateRight: "clamp" }),
    interpolate(frame, [total - Math.round(fps * outSec), total], [1, 0], { extrapolateLeft: "clamp" })
  );
};

/** 進行度 0..1。中身がアニメーションする部品はこれを使う。 */
const useProgress = (durationSec: number, overSec = 1.1) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return interpolate(frame, [0, Math.round(fps * Math.min(overSec, durationSec))], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

const panel: React.CSSProperties = {
  backgroundColor: "rgba(14,14,17,.82)",
  border: "1px solid rgba(244,241,234,.14)",
};

/** 大きな数値の単独提示。数字は末尾から繰り上がるように出す。 */
export const StatCallout: React.FC<{ stat: Stat }> = ({ stat }) => {
  const opacity = useFade(stat.durationSec);
  const p = useProgress(stat.durationSec, 0.8);
  const shown = stat.value.slice(0, Math.max(1, Math.ceil(stat.value.length * p)));
  return (
    <AbsoluteFill style={{ ...zoneStyle(stat.zone), opacity }}>
      <div style={{ ...panel, padding: "26px 38px", minWidth: 320 }}>
        {stat.label ? (
          <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 21, color: "rgba(244,241,234,.62)", marginBottom: 10 }}>
            {stat.label}
          </div>
        ) : null}
        <div style={{ fontFamily: theme.fontFamily, fontWeight: 900, fontSize: 92, lineHeight: 1, color: theme.text }}>
          {shown}
        </div>
        {stat.note ? (
          <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 19, color: "rgba(244,241,234,.55)", marginTop: 12 }}>
            {stat.note}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/** 人物のインサート。肖像が無ければ氏名と肩書だけで成立させる。 */
export const PortraitCard: React.FC<{ portrait: Portrait }> = ({ portrait }) => {
  const opacity = useFade(portrait.durationSec);
  const resolve = (s: string) => (/^https?:\/\//.test(s) ? s : staticFile(s));
  return (
    <AbsoluteFill style={{ ...zoneStyle(portrait.zone), opacity }}>
      <div style={{ ...panel, padding: 20, display: "flex", gap: 20, alignItems: "center", maxWidth: 640 }}>
        {portrait.src ? (
          <Img src={resolve(portrait.src)} style={{ width: 168, height: 210, objectFit: "cover", filter: "grayscale(.35)" }} />
        ) : (
          <div style={{ width: 168, height: 210, backgroundColor: "rgba(244,241,234,.06)",
                        border: "1px solid rgba(244,241,234,.16)" }} />
        )}
        <div>
          {portrait.year ? (
            <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 22, color: theme.accent, marginBottom: 8 }}>
              {portrait.year}
            </div>
          ) : null}
          <div style={{ fontFamily: theme.fontFamily, fontSize: 40, fontWeight: 700, color: theme.text }}>
            {portrait.name}
          </div>
          {portrait.role ? (
            <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 20, color: "rgba(244,241,234,.62)", marginTop: 10 }}>
              {portrait.role}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** 折れ線。系列は 0..1 で渡す。左から描き進む。 */
export const DataChart: React.FC<{ chart: Chart }> = ({ chart }) => {
  const opacity = useFade(chart.durationSec);
  const p = useProgress(chart.durationSec, 1.4);
  const W = 430, H = 210;
  const pts = chart.series.map((v, i) => {
    const x = (i / (chart.series.length - 1)) * W;
    const y = H - v * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const visible = Math.max(2, Math.ceil(pts.length * p));
  return (
    <AbsoluteFill style={{ ...zoneStyle(chart.zone), opacity }}>
      <div style={{ ...panel, padding: "24px 28px" }}>
        {chart.readout ? (
          <div style={{ fontFamily: theme.fontFamily, fontWeight: 900, fontSize: 52, color: theme.text, marginBottom: 12 }}>
            {chart.readout}
          </div>
        ) : null}
        <svg width={W} height={H} style={{ display: "block" }}>
          {[0.25, 0.5, 0.75].map((g) => (
            <line key={g} x1={0} x2={W} y1={H * g} y2={H * g} stroke="rgba(244,241,234,.12)" strokeWidth={1} />
          ))}
          <polyline points={pts.slice(0, visible).join(" ")} fill="none"
                    stroke={theme.accent} strokeWidth={3} />
        </svg>
        {chart.caption ? (
          <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 19, color: "rgba(244,241,234,.6)", marginTop: 12 }}>
            {chart.caption}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/** 区切りのある横バー。active の区間だけ色を入れる。 */
export const TimelineBar: React.FC<{ timeline: Timeline }> = ({ timeline }) => {
  const opacity = useFade(timeline.durationSec);
  const p = useProgress(timeline.durationSec, 1.0);
  return (
    <AbsoluteFill style={{ ...zoneStyle(timeline.zone), opacity }}>
      <div style={{ ...panel, padding: "18px 24px", display: "flex", gap: 10, alignItems: "stretch" }}>
        {timeline.marks.map((m, i) => {
          const reached = p >= (i + 1) / timeline.marks.length;
          return (
            <div key={i} style={{ minWidth: 150 }}>
              <div style={{
                height: 8,
                backgroundColor: m.active && reached ? theme.accent : "rgba(244,241,234,.2)",
              }} />
              <div style={{
                fontFamily: "ui-monospace, monospace", fontSize: 20, marginTop: 10,
                color: m.active ? theme.text : "rgba(244,241,234,.5)",
              }}>
                {m.label}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** 1文字を画面いっぱいに。 */
export const GlyphHero: React.FC<{ glyph: Glyph }> = ({ glyph }) => {
  const opacity = useFade(glyph.durationSec);
  const p = useProgress(glyph.durationSec, 1.2);
  return (
    <AbsoluteFill style={{ ...zoneStyle(glyph.zone), opacity, flexDirection: "column" }}>
      <div style={{
        fontFamily: theme.fontFamily, fontSize: 300, lineHeight: 1, color: theme.text,
        textShadow: theme.textShadow, transform: `scale(${interpolate(p, [0, 1], [0.86, 1])})`,
      }}>
        {glyph.glyph}
      </div>
      {glyph.caption ? (
        <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 26, color: "rgba(244,241,234,.7)", marginTop: 24 }}>
          {glyph.caption}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** 格子。filled の割合だけセルを点ける。左上から順に点灯する。 */
export const MatrixGrid: React.FC<{ grid: Grid }> = ({ grid }) => {
  const opacity = useFade(grid.durationSec);
  const p = useProgress(grid.durationSec, 1.5);
  const total = grid.cols * grid.rows;
  const lit = Math.round(total * grid.filled * p);
  return (
    <AbsoluteFill style={{ ...zoneStyle(grid.zone), opacity, flexDirection: "column" }}>
      <div style={{ ...panel, padding: 22 }}>
        <div style={{
          display: "grid", gap: 6,
          gridTemplateColumns: `repeat(${grid.cols}, 26px)`,
        }}>
          {Array.from({ length: total }, (_, i) => (
            <div key={i} style={{
              width: 26, height: 26,
              backgroundColor: i < lit ? "rgba(214,200,150,.82)" : "rgba(244,241,234,.09)",
            }} />
          ))}
        </div>
        {grid.caption ? (
          <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 20, color: "rgba(244,241,234,.66)", marginTop: 16 }}>
            {grid.caption}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
