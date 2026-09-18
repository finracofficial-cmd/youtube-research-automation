"""台本と尺から Remotion の props.json を組む。

字幕の割り付けは文字数按分。ナレーションは一定の速さで読まれる前提なので、
文の長さの比がそのまま表示時間の比になる。読み上げ音声が用意できたら、
--narration で渡して実測の尺に合わせる。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from autolayout import Line, build as build_overlays  # noqa: E402
from autolayout import hold, schedule, to_props  # noqa: E402
from script_engine.beats import get  # noqa: E402

MAX_SUB_CHARS = 26  # 1枚の字幕に載せる上限。これを超えると読めない


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。？！?!])", text) if s.strip()]


def wrap(sentence: str) -> list[str]:
    """長い文を字幕1枚ぶんに割る。読点を優先して切る。"""
    if len(sentence) <= MAX_SUB_CHARS:
        return [sentence]
    parts, cur = [], ""
    for chunk in re.split(r"(?<=、)", sentence):
        if len(cur) + len(chunk) > MAX_SUB_CHARS and cur:
            parts.append(cur)
            cur = chunk
        else:
            cur += chunk
    if cur:
        parts.append(cur)
    # 読点が無くて割れなかった場合は、やむを得ず機械的に割る
    out = []
    for p in parts:
        while len(p) > MAX_SUB_CHARS:
            out.append(p[:MAX_SUB_CHARS])
            p = p[MAX_SUB_CHARS:]
        if p:
            out.append(p)
    return out


def _audio_seconds(path: Path) -> float | None:
    """音声の長さ。取れなければ None。"""
    if not path.exists():
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def load_manifest(path: Path | None) -> list[dict]:
    """assets fetch が出した manifest.json。実ファイル名とライセンスが入っている。"""
    if not path or not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def source_labels(manifest: list[dict], shots: list[dict]) -> list[dict]:
    """各カットの表示中、左上に出典を出しっぱなしにする。

    CC BY / CC BY-SA は表示が条件なので、ここを自動化しないと
    素材を機械で集めた意味がなくなる。

    カットと manifest を並び順で突き合わせてはいけない。画は時間で
    引き当てているので、位置で組むと画面に出ている画と違う作者名が出る。
    表示義務のあるライセンスでそれをやると、表示していないのと同じになる。
    """
    by_file = {m["file"]: m for m in manifest if m.get("file")}
    out = []
    for shot in shots:
        entry = by_file.get(str(shot.get("src", "")).rsplit("/", 1)[-1])
        if not entry:
            continue
        author = entry.get("author") or ""
        lic = entry.get("license") or ""
        text = f"{author} / {lic}".strip(" /") if author != "不明" else lic
        if not text:
            continue
        # 同じ画が続く間は1枚の帯にまとめる。同じ文字が点滅しないように
        if out and out[-1]["text"] == text and \
                abs(out[-1]["startSec"] + out[-1]["durationSec"] - shot["startSec"]) < 0.05:
            out[-1]["durationSec"] = round(
                out[-1]["durationSec"] + shot["durationSec"], 3)
            continue
        out.append({"startSec": shot["startSec"],
                    "durationSec": shot["durationSec"], "text": text})
    return out


def overlays_from_llm(lines: list[Line], duration: float,
                      codes: list[str]) -> tuple[dict, str] | None:
    """LLMで抽出を試す。キーが無い／失敗したら None を返して正規表現に任せる。

    LLMは文脈が読めるので、否定文や組織名の取り違えを避けられる。
    ただし台本に無い値を書くことがあるので llm_extract 側で検証している。
    """
    try:
        import llm_extract
    except ImportError:
        return None
    if not llm_extract.available():
        return None
    try:
        r = llm_extract.extract(lines)
    except Exception as exc:  # noqa: BLE001 - 失敗したら正規表現で続行する
        print(f"  ! LLM抽出に失敗、正規表現で続行: {str(exc)[:90]}")
        return None
    if not r.cues:
        return None
    props = to_props(hold(schedule(r.cues), duration), codes)
    return props, f"LLM抽出（検証で{r.rejected}件を棄却）"


FRAME_AR = 16 / 9


def _inset(entry: dict | None) -> float:
    """縦長の画を左右に余白を取って収める割合。

    16:9に高さで合わせると、縦長の画は横が足りない。埋めようと拡大すると
    肖像画の顔が切れる。7カットごとに機械的に入れていたのを、実寸で決める。
    """
    if not entry:
        return 0.0
    w, h = entry.get("width") or 0, entry.get("height") or 0
    if not w or not h:
        return 0.0
    ar = w / h
    # 4:3（1.33）を16:9に切ると高さを25%失うが、写真なら破綻しない。
    # 実測の素材26枚のうち11枚が縦長で、そこを切ると人物の頭や写本の欄外が
    # 落ちる。境目は正方形の少し手前に置く。
    if ar >= 1.2:
        return 0.0
    return round(min(0.35, (1 - ar / FRAME_AR) / 2), 3)


def _avoid_repeat(shots: list[dict], manifest: list[dict]) -> None:
    """隣り合うカットが同じ画にならないようにする。

    画は時間で引き当てているので、1つの区間に複数のカットが入ると同じ画が
    続く。実測で129カット中66箇所（51%）が直前と同じ画で、最長4カット
    続いていた。切り替わったのに絵が変わらないので、見ていて飽きる。

    近い区間の画から、直前と違うものを選び直す。題材が離れすぎないよう、
    区間の近い順に探す。
    """
    by_file = {}
    for e in manifest:
        by_file.setdefault(e["file"], e.get("segment", 0))
    if len(by_file) < 2:
        return  # 選び直す先が無い

    for i in range(1, len(shots)):
        prev = shots[i - 1]["src"]
        if shots[i]["src"] != prev:
            continue
        want = by_file.get(shots[i]["src"].removeprefix("shots/").split("/")[-1], 0)
        # 区間が近く、直前と違う画を選ぶ
        best = min(
            (f for f in by_file if f != prev.split("/")[-1]),
            key=lambda f: abs(by_file[f] - want),
            default=None)
        if best:
            shots[i]["src"] = shots[i]["src"].rsplit("/", 1)[0] + "/" + best


def _for_time(pos: float, manifest: list[dict], n_seg: int) -> dict | None:
    """画面上の時刻（0-1）に対応する素材を返す。

    素材は台本を等分した区間ごとに選んである。カット数は区間数と一致しない
    ので、並び順ではなく時間で引き当てないと、語っている話題と画がずれる。
    """
    if not manifest:
        return None
    if not n_seg:
        return manifest[min(int(pos * len(manifest)), len(manifest) - 1)]
    want = pos * n_seg
    return min(manifest, key=lambda m: abs((m.get("segment", 0)) - want))


def build(script: str, duration: float, kind: str, n_claims: int,
          shot_sec: float, narration: str | None, bgm: str | None,
          manifest: list[dict] | None = None, use_llm: bool = False,
          shots_dir: str = "shots") -> dict:
    lines = [w for s in split_sentences(script) for w in wrap(s)]
    total_chars = sum(len(l) for l in lines) or 1

    # 1フレームに満たない字幕は描画側で長さ0として弾かれ、描画そのものが
    # 落ちる。実測で「る。」が0.025秒になり、60秒尺の確認が通らなかった。
    # 短すぎる字幕は読めもしないので、下限を置く。
    MIN_SUBTITLE_SEC = 0.35
    subtitles, t = [], 0.0
    for line in lines:
        dur = duration * len(line) / total_chars
        subtitles.append({"startSec": round(t, 3),
                          "durationSec": round(max(MIN_SUBTITLE_SEC, dur), 3),
                          "text": line})
        t += dur

    sheet = get(kind, n_claims=n_claims)
    chapters, at = [], 0.0
    for beat, sec in sheet.allocate(int(duration)):
        # 幕・主張の頭にだけカードを出す。導入や締めには出さない
        if beat.key.startswith(("act", "claim")):
            chapters.append({
                "startSec": round(at, 3), "durationSec": 3.0,
                "label": beat.name, "title": "",
            })
        at += sec

    # 画は等間隔の枠。manifest があれば実ファイル名（拡張子つき）を使う
    manifest = manifest or []
    shots = []
    n = max(1, int(duration // shot_sec))
    n_seg = max((m.get("n_segments") or 0) for m in manifest) if manifest else 0
    for i in range(n):
        start = i * duration / n
        zoom_in = i % 2 == 0
        entry = _for_time((start + duration / n / 2) / duration, manifest, n_seg)
        src = (f"{shots_dir}/{entry['file']}" if entry
               else f"{shots_dir}/{i:03d}.jpg")
        shots.append({
            "startSec": round(start, 3),
            "durationSec": round(duration / n, 3),
            "src": src,
            "inset": _inset(entry),
            "from": {"scale": 1.0 if zoom_in else 1.18, "x": 0, "y": 0},
            "to": {"scale": 1.18 if zoom_in else 1.0, "x": 0.2 if zoom_in else -0.2, "y": 0},
        })

    _avoid_repeat(shots, manifest)

    lines = [Line(**{k: s[k] for k in ("startSec", "durationSec", "text")})
             for s in subtitles]
    codes = [str(i + 1) for i in range(9)]
    overlays, how = None, "正規表現抽出"
    if use_llm:
        got = overlays_from_llm(lines, duration, codes)
        if got:
            overlays, how = got
    if overlays is None:
        overlays = build_overlays(lines, codes=codes, duration=duration)
    print(f"  抽出方法: {how}")

    props: dict = {
        "bgmVolume": 0.12, "backgroundDim": 0.5, "shots": shots, "telops": [],
        "subtitles": subtitles, "chapters": chapters,
        "sourceLabels": source_labels(manifest, shots),
        **overlays,
    }
    if narration:
        props["narration"] = narration
    if bgm:
        props["bgm"] = bgm
        # 曲1周の長さ。動画の方が長いので、この長さで繰り返して敷く。
        # 渡さないと1回鳴って以降が無音になる。
        loop = _audio_seconds(Path("video/public") / bgm)
        if loop:
            props["bgmLoopSec"] = round(loop, 3)
    return props


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--duration", type=float, required=True, help="尺（秒）")
    ap.add_argument("--kind", choices=["flagship", "bundle"], default="bundle")
    ap.add_argument("--claims", type=int, default=5)
    ap.add_argument("--shot-sec", type=float, default=8.0, help="1カットの長さ")
    ap.add_argument("--narration", help="public/ からの相対パス")
    ap.add_argument("--bgm")
    ap.add_argument("--out", default="video/props.json")
    ap.add_argument("--manifest", help="assets fetch が出した manifest.json")
    ap.add_argument("--llm", action="store_true",
                    help="オーバーレイ抽出にLLMを使う（OPENAI_API_KEY が要る）")
    a = ap.parse_args()

    props = build(Path(a.script).read_text(encoding="utf-8"), a.duration,
                  a.kind, a.claims, a.shot_sec, a.narration, a.bgm,
                  manifest=load_manifest(Path(a.manifest) if a.manifest else None),
                  use_llm=a.llm,
                  # 素材の置き場は manifest の場所から決める。決め打ちだと
                  # 題材を並行して扱えない（public/shots_nazca を指せない）。
                  shots_dir=(Path(a.manifest).parent.name if a.manifest else "shots"))
    Path(a.out).write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    # 部品を足したらここも増やすこと（4種のときの数え漏らしで9件と誤表示した）
    OVERLAY_KEYS = ("quoteCards", "chipStacks", "cardRows", "documentCards",
                    "stats", "portraits", "charts", "timelines", "glyphs", "grids")
    n_ov = sum(len(props[k]) for k in OVERLAY_KEYS)
    print(f"字幕 {len(props['subtitles'])}枚 / カット {len(props['shots'])} / 章 {len(props['chapters'])}")
    print(f"オーバーレイ {n_ov}件 / 出典ラベル {len(props['sourceLabels'])}件")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
