/** 見た目の定数。全コンポーネントがここを見る。 */
export const theme = {
  bg: "#0b0b0d",
  text: "#f4f1ea",
  accent: "#c82b2b",
  /** 日本語のウェイトが出るフォントを優先。無ければ順に落ちる */
  fontFamily:
    '"Noto Serif JP", "Hiragino Mincho ProN", "Yu Mincho", "Source Han Serif JP", serif',
  subtitleFontFamily:
    '"Noto Sans JP", "Hiragino Sans", "Yu Gothic", "Source Han Sans JP", sans-serif',
  /** 素材の上に載せる文字は、縁取りが無いと必ず読めなくなる */
  textShadow:
    "0 0 8px rgba(0,0,0,.9), 0 2px 4px rgba(0,0,0,.9), 0 0 24px rgba(0,0,0,.7)",
} as const;
