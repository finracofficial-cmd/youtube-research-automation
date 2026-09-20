"""YouTubeの概要欄に貼る文を組み立てる。

中身は3つ。章の時刻、出典、定型文。どれも手で書き写すと取り違える。
出典はCC BYの表示義務があり、間違えるとライセンス違反になる。章は
読み上げの実時間から取る（assets.tts.retime のあとの字幕を使う）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "video"))

import chapters as ch  # noqa: E402
import explainers as ex  # noqa: E402

FOOTER = """\
取り上げてほしい題材があれば、コメント欄でご提案ください。"""

BRAND = ROOT / "brand.yaml"


def brand(path: Path | None = None) -> dict:
    """チャンネルの看板。無ければ空で通す（概要欄は目次と出典だけになる）。"""
    path = path or BRAND
    if not path.exists():
        return {}
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def tags_for(subject: str, brand_tags: list[str] | None) -> list[str]:
    """題材固有のタグを先頭に、看板のタグを続ける。

    YouTubeは先頭3つを題名の上に出す。固有名詞が先でないと、どの動画も
    同じ3つが並ぶ。重複は落とし、順序は保つ。
    """
    out: list[str] = []
    for t in [subject] + list(brand_tags or []):
        t = (t or "").strip().lstrip("#").replace(" ", "")
        if t and t not in out:
            out.append(t)
    return out


def build(title: str, outline: list[dict], credits: str, *,
          lead: str = "", tags: list[str] | None = None) -> str:
    """概要欄の全文。章 -> 出典 -> 定型文 の順。"""
    parts: list[str] = []
    if lead:
        parts.append(lead.strip())
    if outline:
        parts.append("── 目次 ──\n" + ch.render(outline))
    if credits.strip():
        parts.append(credits.strip())
    parts.append(FOOTER)
    if tags:
        parts.append(" ".join(t if t.startswith("#") else f"#{t}" for t in tags))
    return (f"{title}\n\n" if title else "") + "\n\n".join(parts) + "\n"


def refresh(props: dict, script: str, claims: list) -> dict:
    """読み上げに貼り直した字幕から、章を計算し直す。

    build_props は字幕の時刻を字数から割った概算で作る。そのあと実際の
    発話に貼り直すので、章もそこで取り直さないと画面と概要欄がずれる。
    """
    # パネルも引き直す。字幕の時刻が動いたので、置き場所も動く
    panels = ex.plan(
        [ex.Line(s["startSec"], s["durationSec"], s["text"])
         for s in props.get("subtitles") or []],
        max((s["startSec"] + s["durationSec"])
            for s in props.get("subtitles") or [{"startSec": 0, "durationSec": 1}]))
    props["explainers"] = panels
    props = ex.clear(props, panels)

    outline = ch.locate(script, props.get("subtitles") or [], claims)
    if outline:
        props["outline"] = outline
        props["chapters"] = [{"startSec": c["startSec"], "durationSec": 3.0,
                              "label": c["title"], "title": ""}
                             for c in outline if c["startSec"] > 0]
    return props


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="概要欄に貼る文を作る")
    ap.add_argument("props", help="build_props が出した props.json")
    ap.add_argument("--credits", help="assets が出した credits.txt")
    ap.add_argument("--title", default="")
    ap.add_argument("--lead", default="")
    ap.add_argument("--tags", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    props = json.loads(Path(a.props).read_text(encoding="utf-8"))
    credits = ""
    if a.credits and Path(a.credits).exists():
        credits = Path(a.credits).read_text(encoding="utf-8")
    text = build(a.title, props.get("outline") or [], credits,
                 lead=a.lead, tags=a.tags)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"概要欄 -> {a.out}  （章 {len(props.get('outline') or [])}件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
