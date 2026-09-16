import { z } from "zod";

/** Ken Burns の始点・終点。scale=1 が等倍、x/y は -1..1 で画面比の移動量。 */
const frame = z.object({
  scale: z.number().min(1).max(2.5),
  x: z.number().min(-1).max(1),
  y: z.number().min(-1).max(1),
});

export const shotSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  /** staticFile() で解決する相対パス、または http(s) URL */
  src: z.string(),
  from: frame,
  to: frame,
  /** 画面隅に出す出典表記。CC素材は表示が要件になることが多い */
  credit: z.string().optional(),
});

export const telopSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  text: z.string(),
  /** impact = 赤の大字、plain = 白の中字 */
  variant: z.enum(["impact", "plain"]).default("plain"),
});

export const subtitleSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  text: z.string(),
});

export const chapterSchema = z.object({
  startSec: z.number().min(0),
  /** 章タイトルの表示秒数 */
  durationSec: z.number().positive().default(3),
  label: z.string(),
  title: z.string(),
});

/** 画面左上に出しっぱなしにする出典表記。CC BY の表示義務もここで満たす。 */
export const sourceLabelSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  text: z.string(),
});

/** 引用パネル。見出し / 原文 / 訳 / 出典 の4段。 */
export const quoteCardSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  side: z.enum(["left", "right", "center"]).default("left"),
  heading: z.string().optional(),
  original: z.string().optional(),
  translation: z.string().optional(),
  source: z.string().optional(),
});

/** 小さなトークンの縦積み。対応関係や候補の提示に使う。 */
export const chipStackSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  items: z.array(z.string()).min(1),
});

/** 横並びのカード。dimmed で「今回は使わない」を表す。 */
export const cardRowSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  cards: z.array(z.object({
    code: z.string(),
    label: z.string().optional(),
    dimmed: z.boolean().default(false),
  })).min(1),
  caption: z.string().optional(),
});

/** 論文や資料の1ページ目を紙色で再現するカード。 */
export const documentCardSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  venue: z.string().optional(),
  title: z.string(),
  authors: z.string().optional(),
  badge: z.string().optional(),
  badgeNote: z.string().optional(),
});

export const documentarySchema = z.object({
  /** ナレーション音声。無い場合は無音で尺だけ確保する */
  narration: z.string().optional(),
  bgm: z.string().optional(),
  bgmVolume: z.number().min(0).max(1).default(0.12),
  shots: z.array(shotSchema).default([]),
  telops: z.array(telopSchema).default([]),
  subtitles: z.array(subtitleSchema).default([]),
  chapters: z.array(chapterSchema).default([]),
  sourceLabels: z.array(sourceLabelSchema).default([]),
  quoteCards: z.array(quoteCardSchema).default([]),
  chipStacks: z.array(chipStackSchema).default([]),
  cardRows: z.array(cardRowSchema).default([]),
  documentCards: z.array(documentCardSchema).default([]),
  /** 背景の落とし込み。0 で素のまま、1 で真っ暗 */
  backgroundDim: z.number().min(0).max(1).default(0.45),
});

export type DocumentaryProps = z.infer<typeof documentarySchema>;
export type Shot = z.infer<typeof shotSchema>;
export type Telop = z.infer<typeof telopSchema>;
export type Subtitle = z.infer<typeof subtitleSchema>;
export type Chapter = z.infer<typeof chapterSchema>;
export type SourceLabel = z.infer<typeof sourceLabelSchema>;
export type QuoteCard = z.infer<typeof quoteCardSchema>;
export type ChipStack = z.infer<typeof chipStackSchema>;
export type CardRow = z.infer<typeof cardRowSchema>;
export type DocumentCard = z.infer<typeof documentCardSchema>;
