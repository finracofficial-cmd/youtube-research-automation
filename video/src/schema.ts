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

export const documentarySchema = z.object({
  /** ナレーション音声。無い場合は無音で尺だけ確保する */
  narration: z.string().optional(),
  bgm: z.string().optional(),
  bgmVolume: z.number().min(0).max(1).default(0.12),
  shots: z.array(shotSchema).default([]),
  telops: z.array(telopSchema).default([]),
  subtitles: z.array(subtitleSchema).default([]),
  chapters: z.array(chapterSchema).default([]),
});

export type DocumentaryProps = z.infer<typeof documentarySchema>;
export type Shot = z.infer<typeof shotSchema>;
export type Telop = z.infer<typeof telopSchema>;
export type Subtitle = z.infer<typeof subtitleSchema>;
export type Chapter = z.infer<typeof chapterSchema>;
