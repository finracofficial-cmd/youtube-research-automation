import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Chart, Glyph, Grid, Portrait, RangeBar as RangeBarType, Stat, Timeline, Zone } from "../schema";
import { theme } from "../theme";

/** ゾーンごとの置き場所。同じゾーンの部品は同時に出さない前提。 */
export const zoneStyle = (zone: Zone): React.CSSProperties => {
  switch (zone) {
    case "left":
      return { alignItems: "flex-start", justifyContent: "center", padding: "0 0 0 72px" };
    case "right":
      return { alignItems: "flex-end", justifyContent: "center", padding: "0 72px 0 0" };
    case "upper":
      return { alignItems: "center", justifyContent: "flex-start", padding: "150px 90px 0 90px" };
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

/** 「約250キロ」のような値を、数だけ digit を上げながら出す。
 *
 * 文字を先頭から送るだけだと「2」「25」「250」が途中の値として読めて
 * しまい、間違った数を一瞬見せることになる。数は0から目標値へ上げ、
 * 前後の語（約・以上・単位）はそのまま置く。 */
export const countUp = (value: string, p: number): string => {
  const m = value.match(/^(\D*)([0-9０-９][0-9０-９,，.．]*)(.*)$/s);
  if (!m) return value;
  const [, pre, digits, post] = m;
  const n = Number(digits.replace(/[,，]/g, "").replace(/[０-９]/g,
    (d) => String("０１２３４５６７８９".indexOf(d))));
  if (!Number.isFinite(n)) return value;
  const dec = (digits.split(/[.．]/)[1] || "").length;
  const at = n * Math.min(1, Math.max(0, p));
  const text = dec ? at.toFixed(dec) : Math.round(at).toLocaleString("ja-JP");
  return `${pre}${text}${post}`;
};

const panel: React.CSSProperties = {
  backgroundColor: "rgba(14,14,17,.82)",
  border: "1px solid rgba(244,241,234,.14)",
};

/** 大きな数値の単独提示。数字は末尾から繰り上がるように出す。 */
export const StatCallout: React.FC<{ stat: Stat }> = ({ stat }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = useFade(stat.durationSec);
  const p = useProgress(stat.durationSec, 0.8);
  // 数の部分は桁を上げながら出す。文字送りだけだと「2」「25」「250」が
  // 途中の値として読めてしまい、間違った数を一瞬見せることになる。
  const shown = countUp(stat.value, p);
  // 札そのものも、下からわずかに持ち上げて置く
  const rise = spring({ frame, fps, config: { damping: 200, stiffness: 140 },
                        durationInFrames: Math.round(fps * 0.4) });
  const rule = interpolate(frame, [Math.round(fps * 0.25), Math.round(fps * 0.75)],
                           [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // 「40メートルを超える」のように、限定を含む値は長くなる。限定を削ると
  // 断定になってしまうので、削らずに字の方を詰める。
  const size = stat.value.length <= 5 ? 92 : stat.value.length <= 8 ? 66 : 46;
  return (
    <AbsoluteFill style={{ ...zoneStyle(stat.zone), opacity }}>
      <div style={{
        ...panel, padding: "26px 38px", minWidth: 320, maxWidth: 620,
        transform: `translateY(${(1 - rise) * 16}px)`,
      }}>
        {stat.label ? (
          <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 21, color: "rgba(244,241,234,.62)", marginBottom: 10 }}>
            {stat.label}
          </div>
        ) : null}
        <div style={{ fontFamily: theme.fontFamily, fontWeight: 900, fontSize: size, lineHeight: 1.1, color: theme.text }}>
          {shown}
        </div>
        {/* 値の下に線を引く。引ききる動きが、置かれたことを示す */}
        <div style={{
          height: 2, marginTop: 14, width: `${rule * 100}%`,
          backgroundColor: theme.accent, opacity: 0.85,
        }} />
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
/** 折れ線。1点ずつ増える。
 *
 * 1系列なので凡例は置かない（見出しが系列の名前になる）。線は細く、点は
 * 見える大きさで、目盛りは控えめ。値は点が立つのに合わせて添える。
 * 文字は文字の色で、系列の色は点と線だけが持つ。 */
export const DataChart: React.FC<{ chart: Chart }> = ({ chart }) => {
  const opacity = useFade(chart.durationSec);
  const p = useProgress(chart.durationSec, Math.min(2.4, chart.durationSec * 0.55));
  const W = 470, H = 215, PAD = 26;
  const n = chart.series.length;
  const xy = chart.series.map((v, i) => ({
    x: PAD + (i / Math.max(1, n - 1)) * (W - PAD * 2),
    y: PAD + (1 - v) * (H - PAD * 2),
  }));
  // 何点目まで立っているか。線はその手前まで引く
  const grown = p * (n - 1);
  const upto = Math.floor(grown + 1e-6);
  const frac = grown - upto;
  const path = xy.slice(0, upto + 1).map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`);
  if (upto < n - 1 && frac > 0) {
    const a = xy[upto], b = xy[upto + 1];
    path.push(`${(a.x + (b.x - a.x) * frac).toFixed(1)},${(a.y + (b.y - a.y) * frac).toFixed(1)}`);
  }
  return (
    <AbsoluteFill style={{ ...zoneStyle(chart.zone), opacity }}>
      <div style={{ ...panel, padding: "24px 28px" }}>
        {chart.readout ? (
          <div style={{ fontFamily: theme.fontFamily, fontSize: 30, color: theme.text, marginBottom: 14 }}>
            {chart.readout}
          </div>
        ) : null}
        <svg width={W} height={H + 34} style={{ display: "block" }}>
          {/* 目盛りは控えめに。読ませたいのは線の向き */}
          {[0.25, 0.5, 0.75].map((g) => (
            <line key={g} x1={PAD} x2={W - PAD} y1={PAD + (H - PAD * 2) * g}
                  y2={PAD + (H - PAD * 2) * g}
                  stroke="rgba(244,241,234,.10)" strokeWidth={1} />
          ))}
          <polyline points={path.join(" ")} fill="none" stroke={theme.accent}
                    strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {xy.map((q, i) => {
            if (i > upto) return null;
            const pt = chart.points[i];
            return (
              <g key={i}>
                {/* 地の色の輪。線と重なっても点が沈まない */}
                <circle cx={q.x} cy={q.y} r={6} fill="#0e0e11" />
                <circle cx={q.x} cy={q.y} r={4.5} fill={theme.accent} />
                {pt?.readout ? (
                  <text x={q.x} y={q.y - 14} textAnchor="middle"
                        fill={theme.text} fontFamily={theme.subtitleFontFamily}
                        fontSize={18}>
                    {pt.readout}
                  </text>
                ) : null}
                {pt?.label ? (
                  <text x={q.x} y={H + 14} textAnchor="middle"
                        fill="rgba(244,241,234,.55)"
                        fontFamily={theme.subtitleFontFamily} fontSize={16}>
                    {pt.label}
                  </text>
                ) : null}
              </g>
            );
          })}
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
/** 幅のある量を、目盛りの上の区間として見せる。
 *
 * 「重さは10トンから15トン」のような、1つの数に定まらない量に使う。
 * 大書きの数字にすると幅が消えて、確定値のように見えてしまう。
 *
 * 1系列なので凡例は置かない。区間の両端だけに値を添える（全点に数字を
 * 振らない）。目盛りは控えめにして、区間そのものを読ませる。 */
export const RangeBarCard: React.FC<{ range: RangeBarType }> = ({ range }) => {
  const opacity = useFade(range.durationSec);
  const p = useProgress(range.durationSec, 0.7);
  const left = Math.min(range.from, range.to) * 100;
  const width = Math.abs(range.to - range.from) * 100 * p;
  return (
    <AbsoluteFill style={{ ...zoneStyle(range.zone), opacity }}>
      <div style={{ ...panel, padding: "26px 34px", minWidth: 380, maxWidth: 560 }}>
        {range.caption ? (
          <div style={{
            fontFamily: theme.subtitleFontFamily, fontSize: 20,
            color: "rgba(244,241,234,.62)", marginBottom: 18,
          }}>
            {range.caption}
          </div>
        ) : null}
        {/* 目盛り。数値そのものではなく幅を読ませるので、線は細く暗く */}
        <div style={{
          position: "relative", height: 12, borderRadius: 6,
          background: "rgba(244,241,234,.12)",
        }}>
          <div style={{
            position: "absolute", left: `${left}%`, width: `${width}%`,
            top: 0, bottom: 0, borderRadius: 6,
            background: theme.accent,
          }} />
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between", marginTop: 14,
          fontFamily: theme.fontFamily, fontWeight: 900, fontSize: 34,
          color: theme.text,
        }}>
          <span>{range.lowLabel}</span>
          <span style={{ opacity: 0.55, fontSize: 24, alignSelf: "center" }}>〜</span>
          <span>{range.highLabel}</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

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
