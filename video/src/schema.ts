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
  /** 画を内側に嵌めて左右を落とす。縦長の資料や、話を切り替えるときに使う */
  inset: z.number().min(0).max(0.35).default(0),
  /** "video" なら動画として再生する。Img で動画を指すと黒い枠になる。 */
  kind: z.enum(["image", "video"]).default("image"),
});

export const telopSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  text: z.string(),
  /** impact = 赤の大字、plain = 白の中字 */
  variant: z.enum(["impact", "plain"]).default("plain"),
  /** 空き時間を埋める語句テロップは upper に置き、画の中心を塞がない */
  zone: z.enum(["center", "upper", "lower"]).default("center"),
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
  /** 動画全体の中でこの章がどこか（0〜1）。章カードに進捗バーを出す。
   *  参考chは画面下に位置を示すバーと「ここから最後の話」の印を出していた。 */
  progress: z.number().min(0).max(1).default(0),
  /** その章が全体のどれだけを占めるか（0〜1） */
  span: z.number().min(0).max(1).default(0),
  /** 最後の章だけ言い方を変える */
  last: z.boolean().default(false),
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
  zone: z.enum(["left", "right", "center", "upper", "lower", "corner"]).default("left"),
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
    /** 札の状態。参考chは研究者5人を並べて ✓ と ? を切り替えていた。
     *  none は印なし。色だけで区別せず、記号と語で示す。 */
    mark: z.enum(["none", "ok", "unknown", "no"]).default("none"),
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

/** 画面のどこを占めるか。同じゾーンの部品は同時に出さない。 */
export const zoneSchema = z.enum(["left", "right", "center", "upper", "lower", "corner"]);

/** 大きな数値の単独提示。「600枚」「約4,726万円」のような見せ方。 */
export const statSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  value: z.string(),
  label: z.string().optional(),
  note: z.string().optional(),
  zone: zoneSchema.default("right"),
});

/** 人物のインサート。肖像が無いときは氏名と肩書だけで出す。 */
export const portraitSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  name: z.string(),
  role: z.string().optional(),
  year: z.string().optional(),
  src: z.string().optional(),
  zone: zoneSchema.default("left"),
});

/** 簡易チャート。値は 0..1 の系列。減衰や推移の提示に使う。 */
export const chartSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  series: z.array(z.number().min(0).max(1)).min(2),
  /** 各点の軸ラベルと読み値。1点ずつ増えながら値が添えられる。
   *  参考chはピラミッド6基の写真を軸ラベルにして折れ線を1点ずつ伸ばしていた。
   *  1系列なので凡例は置かない。見出しが系列の名前になる。 */
  points: z.array(z.object({
    label: z.string(),
    readout: z.string().default(""),
  })).default([]),
  readout: z.string().optional(),
  caption: z.string().optional(),
  zone: zoneSchema.default("right"),
});

/** 区切りのある横バー。年代の推移や工程の段階を示す。 */
/** 「10トンから15トン」のような幅のある量。棒の上に区間として出す */
export const rangeBarSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  /** 目盛りの下端・上端に対する区間の位置（0〜1） */
  from: z.number().min(0).max(1),
  to: z.number().min(0).max(1),
  lowLabel: z.string(),
  highLabel: z.string(),
  caption: z.string().optional(),
  zone: zoneSchema.default("right"),
});

export const timelineSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  marks: z.array(z.object({
    label: z.string(),
    active: z.boolean().default(false),
  })).min(2),
  zone: zoneSchema.default("lower"),
});

/** 1文字・1記号を画面いっぱいに出す。 */
export const glyphSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  glyph: z.string(),
  caption: z.string().optional(),
  zone: zoneSchema.default("center"),
});

/** 格子。文字頻度表や対応表の見せ方。 */
export const gridSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  cols: z.number().int().min(2).max(24).default(12),
  rows: z.number().int().min(2).max(16).default(6),
  filled: z.number().min(0).max(1).default(0.6),
  caption: z.string().optional(),
  zone: zoneSchema.default("center"),
});

/** 画面いっぱいの解説パネル。素材の写真を隠し、これだけで語る区間。
 *
 * 参考chは、写真の上に札を載せるだけでなく、作図だけで構成された区間を
 * 挟んでいる。こちらは全フレームが「写真＋札」で、その状態が無かった。 */
export const explainerSchema = z.object({
  startSec: z.number().min(0),
  durationSec: z.number().positive(),
  kind: z.enum(["contrast", "timeline", "scale", "model"]),
  heading: z.string(),
  /** contrast: 言われていること / 資料が言っていること */
  claim: z.string().optional(),
  evidence: z.string().optional(),
  /** timeline: 年と出来事 */
  marks: z.array(z.object({
    year: z.string(),
    text: z.string().default(""),
  })).default([]),
  /** scale: 並べて比べる量。value は最大値に対する比 0〜1 */
  bars: z.array(z.object({
    label: z.string(),
    value: z.number().min(0).max(1),
    readout: z.string(),
  })).default([]),
  /** model: 寸法を入れた立体。参考chは "3D model · 146 m" と出典を添えて
   *  自作の立体を出している。素材に無い画をここで作る。 */
  shape: z.enum(["pyramid", "block", "column", "disc"]).default("block"),
  dimension: z.object({
    label: z.string(),
    readout: z.string(),
    /** 数え上げの到達値。単位はラベル側に持たせる */
    value: z.number().default(0),
  }).optional(),
  /** 比較用の人。物の高さに対する背丈の比（0 なら置かない）。
   *  固定の大きさで描くと縮尺の嘘になる。実測で5mの柱の横に、比率でいえば
   *  0.9mにあたる人が立っていた。 */
  humanRatio: z.number().min(0).max(1).default(0),
  note: z.string().optional(),
});

export const documentarySchema = z.object({
  /** ナレーション音声。無い場合は無音で尺だけ確保する */
  narration: z.string().optional(),
  bgm: z.string().optional(),
  bgmVolume: z.number().min(0).max(1).default(0.12),
  /** BGM1周の長さ（秒）。尺より短いので繰り返して敷く */
  bgmLoopSec: z.number().positive().optional(),
  shots: z.array(shotSchema).default([]),
  telops: z.array(telopSchema).default([]),
  subtitles: z.array(subtitleSchema).default([]),
  chapters: z.array(chapterSchema).default([]),
  sourceLabels: z.array(sourceLabelSchema).default([]),
  quoteCards: z.array(quoteCardSchema).default([]),
  chipStacks: z.array(chipStackSchema).default([]),
  cardRows: z.array(cardRowSchema).default([]),
  documentCards: z.array(documentCardSchema).default([]),
  stats: z.array(statSchema).default([]),
  portraits: z.array(portraitSchema).default([]),
  charts: z.array(chartSchema).default([]),
  timelines: z.array(timelineSchema).default([]),
  rangeBars: z.array(rangeBarSchema).default([]),
  glyphs: z.array(glyphSchema).default([]),
  grids: z.array(gridSchema).default([]),
  explainers: z.array(explainerSchema).default([]),
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
export type Zone = z.infer<typeof zoneSchema>;
export type Stat = z.infer<typeof statSchema>;
export type Portrait = z.infer<typeof portraitSchema>;
export type Chart = z.infer<typeof chartSchema>;
export type Timeline = z.infer<typeof timelineSchema>;
export type RangeBar = z.infer<typeof rangeBarSchema>;
export type Glyph = z.infer<typeof glyphSchema>;
export type Grid = z.infer<typeof gridSchema>;
export type Explainer = z.infer<typeof explainerSchema>;
