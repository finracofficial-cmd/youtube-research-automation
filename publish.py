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


_KIND = {"paper": "論文", "book": "書籍", "report": "報告書",
         "dataset": "データ", "web": "資料"}


def sources_block(items: list[dict], *, limit: int = 30) -> str:
    """台本の根拠にした資料を並べる。

    画像の出典とは別。こちらは「何を読んで書いたのか」で、動画の中身の
    裏付けになる。URLは載せない（読み上げるものでも押すものでもなく、
    行が長くなって一覧性が落ちる）。identifier があれば DOI として出す。
    """
    import html as _html

    lines: list[str] = []
    seen: set[str] = set()
    for x in items:
        # 文献APIは題名をHTMLの実体参照のまま返す（実測で E&amp;G）
        title = _html.unescape(x.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        year = str(x.get("year") or "").strip()
        kind = _KIND.get(x.get("kind") or "", "")
        venue = _html.unescape(x.get("venue") or "").strip()
        head = " ".join(v for v in (year, title) if v)
        tail = "／".join(v for v in (venue, kind) if v)
        lines.append(f"・{head}" + (f"（{tail}）" if tail else ""))
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return "【情報の出典】\n" + "\n".join(lines)


def build(title: str, outline: list[dict], credits: str, *,
          lead: str = "", tags: list[str] | None = None,
          sources: list[dict] | None = None) -> str:
    """概要欄の全文。章 -> 情報の出典 -> 画像の出典 -> 定型文 の順。"""
    parts: list[str] = []
    if lead:
        parts.append(lead.strip())
    if outline:
        parts.append("── 目次 ──\n" + ch.render(outline))
    block = sources_block(sources or [])
    if block:
        parts.append(block)
    if credits.strip():
        parts.append(credits.strip())
    parts.append(FOOTER)
    if tags:
        parts.append(" ".join(t if t.startswith("#") else f"#{t}" for t in tags))
    return (f"{title}\n\n" if title else "") + "\n\n".join(parts) + "\n"


# 読み上げに貼り直したら作り直す札。build_props が字数割りの概算で置いた
# ものなので、そのままだと語りと合わない。
_TIMED = ("stats", "telops", "quoteCards", "chipStacks", "cardRows",
          "documentCards", "portraits", "charts", "timelines", "rangeBars",
          "glyphs", "grids")


def refresh(props: dict, script: str, claims: list,
            card_labels: list[str] | None = None) -> dict:
    """読み上げに貼り直した字幕から、札と章を計算し直す。

    build_props は字幕の時刻を字数から割った概算で作る。そのあと実際の
    発話に貼り直すのは字幕だけだったので、札はずっと概算の位置に残って
    いた。語りと絵と文字が少しずつずれる原因がこれ。

    ずらして合わせるのではなく、貼り直した字幕から作り直す。概算との差を
    補間すると、文の途中に置かれた札が別の文に移ることがある。
    """
    subs = props.get("subtitles") or []
    # 札を作り直す。字幕の時刻が動いたので、貼る位置も動く
    if subs:
        sys.path.insert(0, str(ROOT / "video"))
        from autolayout import Line as _L, build as _build
        total = max(s["startSec"] + s["durationSec"] for s in subs)
        rebuilt = _build([_L(s["startSec"], s["durationSec"], s["text"]) for s in subs],
                         codes=[str(i + 1) for i in range(9)], duration=total,
                         card_labels=card_labels or [])
        for key in _TIMED:
            if key in rebuilt:
                props[key] = rebuilt[key]

    # パネルも引き直す。字幕の時刻が動いたので、置き場所も動く
    panels = ex.plan(
        [ex.Line(s["startSec"], s["durationSec"], s["text"])
         for s in props.get("subtitles") or []],
        max((s["startSec"] + s["durationSec"])
            for s in props.get("subtitles") or [{"startSec": 0, "durationSec": 1}]))
    props["explainers"] = panels
    props = ex.clear(props, panels)

    props = ex.clear_for_chapters(props)

    outline = ch.locate(script, props.get("subtitles") or [], claims)
    if outline:
        props["outline"] = outline
        props["chapters"] = ch.cards(
            outline,
            max((s["startSec"] + s["durationSec"])
                for s in props.get("subtitles") or [{"startSec": 0, "durationSec": 1}]))
    return props


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="概要欄に貼る文を作る")
    ap.add_argument("props", help="build_props が出した props.json")
    ap.add_argument("--credits", help="assets が出した credits.txt")
    ap.add_argument("--title", default="")
    ap.add_argument("--lead", default="")
    ap.add_argument("--tags", nargs="*", default=[])
    ap.add_argument("--sources", help="research pipeline が出した *_sources.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    props = json.loads(Path(a.props).read_text(encoding="utf-8"))
    credits = ""
    if a.credits and Path(a.credits).exists():
        credits = Path(a.credits).read_text(encoding="utf-8")
    got = []
    if a.sources and Path(a.sources).exists():
        got = json.loads(Path(a.sources).read_text(encoding="utf-8"))
    text = build(a.title, props.get("outline") or [], credits,
                 lead=a.lead, tags=a.tags, sources=got)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"概要欄 -> {a.out}  （章 {len(props.get('outline') or [])}件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
