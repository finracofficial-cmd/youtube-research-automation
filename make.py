"""台本1本から、動画1本を作る。

  python3 make.py drafts/oparts_v1.txt --name oparts

途中の工程（検索語の割り出し、素材の収集、部品の配置、描画）は全部この中で
順に走る。工程ごとにコマンドが分かれていると、引数の食い違いで素材と
台本がずれる。実際に、素材の置き場を決め打ちしていて別テーマを並行して
扱えなかったり、manifest の指定漏れで前のテーマの画で描画したことがある。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import meter

ROOT = Path(__file__).resolve().parent


def _claims(topic: Path) -> list:
    """題材の主張。章の位置決めに使う。"""
    if not topic.exists():
        return []
    import yaml
    return (yaml.safe_load(topic.read_text(encoding="utf-8")) or {}).get("claims") or []


def run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"失敗: {' '.join(cmd)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="台本から動画を1本作る")
    ap.add_argument("script", help="台本のテキストファイル")
    ap.add_argument("--name", help="出力名。省略すると台本のファイル名")
    ap.add_argument("--duration", type=float, default=900.0, help="尺（秒）")
    ap.add_argument("--claims", type=int, default=5, help="取り上げる主張の数")
    ap.add_argument("--kind", default="bundle", choices=["bundle", "flagship"])
    ap.add_argument("--segments", type=int, default=80, help="画を切り替える回数の目安")
    ap.add_argument("--skip-assets", action="store_true",
                    help="素材の収集を飛ばす（手元の素材で作り直すとき）")
    ap.add_argument("--still", type=int, help="動画の代わりに指定フレームの静止画を出す")
    ap.add_argument("--generate-images", action="store_true",
                    help="同じ画が続く区間を生成画像で埋める（OPENAI_API_KEY が要る）")
    ap.add_argument("--broll", action="store_true",
                    help="繰り返している区間にCommonsのイメージ映像を入れる")
    ap.add_argument("--max-broll", type=int, default=24,
                    help="入れるイメージ映像の本数")
    ap.add_argument("--image-quality", default="medium",
                    choices=["low", "medium", "high"],
                    help="生成画像の画質。高いほど出力トークンが増え費用が上がる")
    ap.add_argument("--voice", help="ElevenLabs の voice_id。渡すと読み上げが入る"
                                    "（ELEVENLABS_API_KEY が要る）")
    ap.add_argument("--bgm", help="public/ からの相対パス")
    ap.add_argument("--tts-model", help="ElevenLabs のモデル。既定は eleven_v3")
    a = ap.parse_args()

    script = Path(a.script)
    if not script.exists():
        raise SystemExit(f"台本が無い: {script}")
    # 出力名は台本のファイル名から決める。手で合わせる欄が2つあると、
    # 食い違ったまま1時間半かけて別の題材の動画ができる。
    name = a.name or re.sub(r"_v\d+$", "", script.stem)
    shots_dir = f"shots_{name}"
    spec = ROOT / "seeds" / "shots" / f"{name}.yaml"
    props = ROOT / "video" / f"props_{name}.json"
    out = ROOT / "out" / (f"{name}.png" if a.still else f"{name}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    began = time.time()
    meter.share(ROOT / "out" / f".meter_{name}.jsonl")
    if not a.skip_assets:
        spec.parent.mkdir(parents=True, exist_ok=True)
        print("■ 1/4 台本から検索語を割り出す")
        run([sys.executable, "-m", "assets.plan_shots", str(script),
             "--segments", str(a.segments), "--out", str(spec)])

        print("\n■ 2/4 素材を集める")
        run([sys.executable, "-m", "assets", "fetch", str(spec),
             "--out", f"video/public/{shots_dir}", "--limit", "12"])
    elif not spec.exists():
        raise SystemExit(f"--skip-assets だが検索語が無い: {spec}")

    shots_path = ROOT / "video" / "public" / shots_dir
    manifest_path = shots_path / "manifest.json"
    if (a.broll or a.generate_images) and not manifest_path.exists():
        # --skip-assets と併用すると素材の目録が無い。落ちる前に断る
        print(f"  素材の目録が無いので差し込みを飛ばす: {manifest_path}")
        a.broll = a.generate_images = False

    if a.broll:
        print("\n■ 同じ画が続く区間にイメージ映像を入れる")
        from assets.imagegen import fill_broll
        man = manifest_path
        entries = json.loads(man.read_text(encoding="utf-8"))
        entries = fill_broll(entries, shots_path, limit=a.max_broll)
        man.write_text(json.dumps(entries, ensure_ascii=False, indent=1),
                       encoding="utf-8")

    if a.generate_images:
        print("\n■ 同じ画が続く区間を生成で埋める")
        from assets.imagegen import fill
        from assets.plan_shots import split_script
        man = manifest_path
        entries = json.loads(man.read_text(encoding="utf-8"))
        segs = split_script(script.read_text(encoding="utf-8"),
                            max((e.get("n_segments") or 0) for e in entries) or a.segments)
        entries = fill(entries, segs, shots_path, quality=a.image_quality)
        man.write_text(json.dumps(entries, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        # 生成が入ったらクレジットを作り直す（概要欄の申告が要る）
        from assets.credits import build as build_credits
        from assets.sources import Asset
        keys = {f.name for f in __import__("dataclasses").fields(Asset)}
        assets_ = [Asset(**{k: v for k, v in e.items() if k in keys}) for e in entries]
        (shots_path / "credits.txt").write_text(build_credits(assets_), encoding="utf-8")

    duration, marks, narration = a.duration, [], None
    if a.voice:
        print("\n■ 読み上げる")
        from assets import tts
        mp3 = shots_path / "narration.mp3"
        marks = tts.synthesize(script.read_text(encoding="utf-8"), mp3, a.voice,
                               model=a.tts_model or tts.DEFAULT_MODEL)
        duration = tts._duration(mp3)
        narration = f"{shots_dir}/narration.mp3"
        print(f"  音声 {duration / 60:.1f}分 -> {mp3}")

    print("\n■ 3/4 部品を配置する")
    topic = ROOT / "seeds" / "topics" / f"{name}.yaml"
    cmd = [sys.executable, "video/build_props.py", str(script),
           "--duration", str(duration), "--kind", a.kind,
           "--claims", str(a.claims),
           "--manifest", f"video/public/{shots_dir}/manifest.json",
           "--out", str(props)]
    if topic.exists():
        cmd += ["--topic", str(topic)]
    else:
        print(f"  主張の元データが無い: {topic}（章は尺の等分になる）")
    if narration:
        cmd += ["--narration", narration]
    if a.bgm:
        cmd += ["--bgm", a.bgm]
    run(cmd)

    if marks:
        # 字幕の時刻は文字数から割った概算。実際の発話に貼り直す
        from assets.tts import retime
        data = json.loads(props.read_text(encoding="utf-8"))
        data["subtitles"] = retime(data["subtitles"], marks)
        # 章も取り直す。字幕だけ直すと、画面のカードと概要欄の時刻が
        # 概算のまま残り、読み上げとずれる
        import publish
        from video.chapters import render as render_chapters  # noqa: F401
        claims_now = _claims(topic)
        sys.path.insert(0, str(ROOT / "video"))
        import chapters as _ch
        data = publish.refresh(data, script.read_text(encoding="utf-8"),
                               claims_now,
                               card_labels=_ch.card_labels(claims_now))
        props.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print(f"  字幕を実際の発話に合わせ直した（章 {len(data.get('outline') or [])}件）")

    print("\n■ 4/4 描画する（尺が長いと時間がかかる）")
    render = ["./render.sh", "still" if a.still else "render",
              "Documentary", str(out)]
    if a.still:
        render.append(f"--frame={a.still}")
    subprocess.run(render, cwd=ROOT / "video",
                   env={**__import__("os").environ, "PROPS": props.name}, check=True)

    mins = (time.time() - began) / 60
    print(f"\n完成 -> {out}  （{mins:.1f}分）")
    print(meter.report())
    # 概要欄。章・出典・定型文を1つのファイルにまとめる
    import publish
    data = json.loads(props.read_text(encoding="utf-8"))
    credits = ROOT / "video" / "public" / shots_dir / "credits.txt"
    b = publish.brand()
    subject = ""
    if topic.exists():
        import yaml
        subject = (yaml.safe_load(topic.read_text(encoding="utf-8")) or {}).get("subject", "")
    desc = out.with_name(f"{name}_description.txt")
    desc.write_text(
        publish.build("", data.get("outline") or [],
                      credits.read_text(encoding="utf-8") if credits.exists() else "",
                      lead=b.get("lead", ""),
                      tags=publish.tags_for(subject, b.get("hashtags"))),
        encoding="utf-8")
    print(f"概要欄に貼る文 -> {desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
