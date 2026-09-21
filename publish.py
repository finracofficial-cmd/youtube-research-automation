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

RULE = "━" * 24


def _cite(x: dict) -> str:
    """1件ぶんの書誌。著者は持っていないので、掲載誌と年で示す。"""
    import html as _html
    title = _html.unescape(x.get("title") or "").strip()
    venue = _html.unescape(x.get("venue") or "").strip()
    year = str(x.get("year") or "").strip()
    kind = _KIND.get(x.get("kind") or "", "")
    tail = "　".join(v for v in (venue, f"({year})" if year else "", kind) if v)
    return f"{title}\n　{tail}".rstrip()


def _link(x: dict) -> str:
    """辿れる先。DOIがあればそれを優先する（URLより寿命が長い）。"""
    ident = (x.get("identifier") or "").strip()
    if ident.startswith("10."):
        return f"https://doi.org/{ident}"
    return (x.get("url") or "").strip()


def sources_block(data, *, limit: int = 24, links: bool = True) -> str:
    """台本の根拠にした資料を並べる。

    参考chの概要欄は、1件ごとに「何が分かるか」を先に日本語で書き、その下に
    書誌とリンクを置いていた。書誌だけ並べると、読む側はどれが何の根拠なのか
    分からない。主張ごとに束ねて、主張文をその見出しに使う。

    リンクは載せる。台本の締めが「概要欄に一次資料のリンクを掲載しています」と
    言っているので、外すと動画が嘘になる。DOIがあればそちらを使う。
    """
    if isinstance(data, list):           # 平らな旧形式
        data = {"claims": [], "background": data}
    claims = (data or {}).get("claims") or []
    background = (data or {}).get("background") or []

    lines: list[str] = ["■ 参考文献", ""]
    seen: set[str] = set()
    bare: list[str] = []
    n = 0
    for c in claims:
        got = [x for x in (c.get("sources") or [])
               if (x.get("title") or "").strip()
               and (x.get("title") or "").strip() not in seen]
        if not got:
            bare.append(str(c.get("ja") or "").rstrip("。"))
            continue
        lines.append(f"・{str(c.get('ja') or '').rstrip('。')}")
        for x in got[:3]:
            seen.add((x.get("title") or "").strip())
            lines.append("　" + _cite(x).replace("\n", "\n　"))
            url = _link(x) if links else ""
            if url:
                lines.append(f"　{url}")
            n += 1
            if n >= limit:
                break
        level = (c.get("evidence_level") or "").strip()
        if level.startswith("薄い"):
            lines.append("　※この説を支える査読文献はわずかです")
        lines.append("")
        if n >= limit:
            break

    extra = []
    for x in background:
        t = (x.get("title") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        extra.append(x)
        if len(extra) >= 4:
            break
    if extra and n < limit:
        lines.append("・題材全体の背景")
        for x in extra:
            lines.append("　" + _cite(x).replace("\n", "\n　"))
            url = _link(x) if links else ""
            if url:
                lines.append(f"　{url}")
        lines.append("")

    # 出典のつかなかった主張は、黙って消さずに残す。何が引けなかったかは
    # この番組では中身そのものなので。ただし「文献が存在しない」とは書かない。
    # 書けるのは「こちらの調べ方では出てこなかった」までで、検索が届かな
    # かっただけの可能性を潰せていない。
    if bare and (n or extra):
        lines.append("・以下は動画内で触れていますが、今回の調査では")
        lines.append("　裏づけになる査読文献にたどり着けませんでした")
        for ja in bare[:4]:
            lines.append(f"　・{ja}")
        lines.append("")
    return "\n".join(lines).rstrip() if n or extra else ""


def build(title: str, outline: list[dict], credits: str, *,
          lead: str = "", tags: list[str] | None = None,
          sources=None, intro: str = "") -> str:
    """概要欄の全文。冒頭 -> 定型文 -> 章 -> 情報の出典 -> 画像の出典 の順。

    冒頭はこの動画に固有の2〜3行。YouTubeが「もっと見る」の前に出すのは
    ここだけなので、どの動画でも同じ定型文を置いていたのを改める。
    """
    parts: list[str] = []
    if intro:
        parts.append(intro.strip())
    if lead:
        parts.append(lead.strip())
    if outline:
        parts.append(f"{RULE}\n目次\n" + ch.render(outline) + f"\n{RULE}")
    block = sources_block(sources or {})
    if block:
        parts.append(block)
    if credits.strip():
        parts.append(RULE + "\n\n" + credits.strip())
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
