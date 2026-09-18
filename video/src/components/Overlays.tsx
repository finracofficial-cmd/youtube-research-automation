import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type {
  CardRow as CardRowType,
  ChipStack as ChipStackType,
  DocumentCard as DocumentCardType,
  QuoteCard as QuoteCardType,
  SourceLabel as SourceLabelType,
} from "../schema";
import { theme } from "../theme";

/** 出てから消えるまでの不透明度。全オーバーレイで共通。 */
const useFade = (durationSec: number, inSec = 0.35, outSec = 0.3) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(1, Math.round(durationSec * fps));
  return Math.min(
    interpolate(frame, [0, Math.round(fps * inSec)], [0, 1], { extrapolateRight: "clamp" }),
    interpolate(frame, [total - Math.round(fps * outSec), total], [1, 0], {
      extrapolateLeft: "clamp",
    })
  );
};

const panel: React.CSSProperties = {
  backgroundColor: "rgba(14,14,17,.82)",
  border: "1px solid rgba(244,241,234,.14)",
  padding: "22px 26px",
};

/** 左上に出しっぱなしの出典表記。CC BY の表示義務もこれで満たす。 */
export const SourceLabel: React.FC<{ label: SourceLabelType }> = ({ label }) => {
  const opacity = useFade(label.durationSec, 0.5, 0.5);
  return (
    <AbsoluteFill style={{ opacity }}>
      {/* 画像の出典。何の文字列か分かるよう「出典」を添える。
          添えないと、作者名とライセンス名だけが並んで暗号に見える
          （実測で「よく分からない」という指摘を受けた）。
          表示義務があるので消せない。控えめにして邪魔をしない形にする。 */}
      <div style={{
        position: "absolute", left: 40, top: 32,
        display: "flex", alignItems: "baseline", gap: 10,
        textShadow: theme.textShadow,
      }}>
        <span style={{
          fontFamily: theme.subtitleFontFamily,
          fontSize: 15, letterSpacing: "0.08em",
          color: "rgba(244,241,234,.38)",
        }}>
          出典
        </span>
        <span style={{
          fontFamily: theme.subtitleFontFamily,
          fontSize: 16, letterSpacing: "0.02em",
          color: "rgba(244,241,234,.48)",
        }}>
          {label.text}
        </span>
      </div>
    </AbsoluteFill>
  );
};

/** 引用パネル。原文と訳を上下に置き、出典を小さく添える。 */
export const QuoteCard: React.FC<{ card: QuoteCardType }> = ({ card }) => {
  const opacity = useFade(card.durationSec);
  const justify = card.side === "right" ? "flex-end" : card.side === "center" ? "center" : "flex-start";
  return (
    <AbsoluteFill style={{ opacity, alignItems: justify, justifyContent: "center", padding: "0 72px" }}>
      <div style={{ ...panel, maxWidth: 620 }}>
        {card.heading ? (
          <div style={{
            fontFamily: theme.subtitleFontFamily, fontSize: 19,
            color: "rgba(244,241,234,.66)", marginBottom: 14, letterSpacing: "0.06em",
          }}>
            {card.heading}
          </div>
        ) : null}
        {card.original ? (
          <div style={{
            fontFamily: theme.fontFamily, fontStyle: "italic", fontSize: 30,
            lineHeight: 1.45, color: theme.text, marginBottom: 14,
          }}>
            {card.original}
          </div>
        ) : null}
        {card.translation ? (
          <div style={{
            fontFamily: theme.subtitleFontFamily, fontSize: 24, lineHeight: 1.5,
            color: "rgba(244,241,234,.9)",
          }}>
            {card.translation}
          </div>
        ) : null}
        {card.source ? (
          <div style={{
            fontFamily: "ui-monospace, monospace", fontSize: 16, marginTop: 18,
            color: "rgba(244,241,234,.45)",
          }}>
            {card.source}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/** 小さなトークンを縦に積む。対応関係の提示に使う。 */
export const ChipStack: React.FC<{ stack: ChipStackType }> = ({ stack }) => {
  const opacity = useFade(stack.durationSec);
  return (
    <AbsoluteFill style={{ opacity, alignItems: "center", justifyContent: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {stack.items.map((item, i) => (
          <div key={i} style={{
            ...panel, padding: "10px 30px", minWidth: 190, textAlign: "center",
            fontFamily: "ui-monospace, monospace", fontSize: 38, color: theme.text,
          }}>
            {item}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

/** 横並びのカード。dimmed は「今回は使わない」の意思表示。 */
export const CardRow: React.FC<{ row: CardRowType }> = ({ row }) => {
  const opacity = useFade(row.durationSec);
  return (
    <AbsoluteFill style={{ opacity, alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "76%" }}>
        <div style={{ display: "flex", gap: 14 }}>
          {row.cards.map((card, i) => (
            <div key={i} style={{
              ...panel, flex: 1, padding: "18px 20px", opacity: card.dimmed ? 0.38 : 1,
            }}>
              <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 40, fontWeight: 700, color: theme.text }}>
                {card.code}
              </div>
              {card.label ? (
                <div style={{
                  fontFamily: theme.subtitleFontFamily, fontSize: 17, marginTop: 8,
                  color: "rgba(244,241,234,.62)",
                }}>
                  {card.label}
                </div>
              ) : null}
              <div style={{ height: 3, marginTop: 16, backgroundColor: "rgba(244,241,234,.22)" }} />
            </div>
          ))}
        </div>
        {row.caption ? (
          <div style={{
            ...panel, marginTop: 14, padding: "12px 20px",
            fontFamily: theme.subtitleFontFamily, fontSize: 21, color: "rgba(244,241,234,.86)",
          }}>
            {row.caption}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/** 論文の1ページ目を紙色で再現する。出典を「見せる」ための部品。 */
export const DocumentCard: React.FC<{ card: DocumentCardType }> = ({ card }) => {
  const opacity = useFade(card.durationSec);
  return (
    <AbsoluteFill style={{ opacity, alignItems: "center", justifyContent: "center" }}>
      <div style={{
        width: "64%", backgroundColor: "#efe9dc", color: "#1a1712",
        padding: "36px 44px", boxShadow: "0 24px 70px rgba(0,0,0,.6)",
      }}>
        {card.venue ? (
          <div style={{ fontFamily: theme.fontFamily, fontSize: 19, letterSpacing: "0.1em", marginBottom: 12 }}>
            {card.venue}
          </div>
        ) : null}
        <div style={{ fontFamily: theme.fontFamily, fontSize: 34, lineHeight: 1.3, marginBottom: 12 }}>
          {card.title}
        </div>
        {card.authors ? (
          <div style={{ fontFamily: theme.fontFamily, fontSize: 19, color: "#4a4438", marginBottom: 22 }}>
            {card.authors}
          </div>
        ) : null}
        {card.badge ? (
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div style={{
              border: "1px solid #6b6455", padding: "8px 22px",
              fontFamily: theme.subtitleFontFamily, fontSize: 19,
            }}>
              {card.badge}
            </div>
            {card.badgeNote ? (
              <div style={{ fontFamily: theme.subtitleFontFamily, fontSize: 18, color: "#4a4438" }}>
                {card.badgeNote}
              </div>
            ) : null}
          </div>
        ) : null}
        <div style={{ height: 6, marginTop: 28, backgroundColor: "rgba(26,23,18,.13)" }} />
        <div style={{ height: 6, marginTop: 10, width: "92%", backgroundColor: "rgba(26,23,18,.13)" }} />
      </div>
    </AbsoluteFill>
  );
};

/** 背景を暗く落とし、四隅を締める。上に文字を載せるための下地。 */
export const BackgroundPlate: React.FC<{ dim: number }> = ({ dim }) => (
  <AbsoluteFill style={{
    backgroundColor: `rgba(8,8,10,${dim})`,
    backgroundImage:
      "radial-gradient(ellipse at center, rgba(0,0,0,0) 38%, rgba(0,0,0,.72) 100%)",
  }} />
);
