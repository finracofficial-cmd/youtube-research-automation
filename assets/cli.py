"""素材を集めて落とし、クレジットまで出す。

  python -m assets search "Voynich manuscript"
  python -m assets fetch shots.yaml --out video/public/shots
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

# 背景として使える最低限の明るさ。透明PNGと暗すぎる写真の両方をここで落とす。
MIN_MEAN_LUMA = 25

import yaml

from .credits import build as build_credits
from .credits import unlicensed
from .sources import UA, Asset, search_all


def mean_luma(path: Path) -> int | None:
    """画像をアルファごと黒へ落とし込んだときの平均輝度。

    透明なPNG（SVG由来のものに多い）は暗い背景の上で完全に消える。
    暗すぎる写真も同じで、どちらも「読み込めているのに黒い画面」になる。
    黒に合成してから測ると、両方まとめて弾ける。
    """
    if not shutil.which("ffmpeg"):
        return None
    r = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path),
         "-vf", "scale=1:1,format=gray", "-f", "rawvideo", "-"],
        capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    return r.stdout[0]


def _sniff_ext(data: bytes) -> str:
    """中身から拡張子を決める。

    Commons は .jpg というファイル名で PNG や WebP を返すことがある。
    拡張子が中身と食い違うと ffmpeg や画像ローダが躓くので、実体で判定する。
    """
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ""


def _download(asset: Asset, stem: Path) -> Path | None:
    """落とせたら、中身に合った拡張子を付けて保存し、そのパスを返す。"""
    try:
        req = urllib.request.Request(asset.url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=90).read()
    except Exception:  # noqa: BLE001 - 落とせない候補は静かに飛ばして次へ
        return None
    if len(data) < 5000:  # 実体のないプレースホルダを掴むことがある
        return None
    ext = _sniff_ext(data)
    if not ext:  # 画像と判定できないものは使わない
        return None
    dst = stem.with_suffix(ext)
    dst.write_bytes(data)

    luma = mean_luma(dst)
    if luma is not None and luma < MIN_MEAN_LUMA:
        dst.unlink(missing_ok=True)  # 暗すぎる／透明。背景に使えない
        return None
    return dst


def cmd_search(args) -> int:
    found, relaxed = search_all(args.query, per_source=args.limit)
    print(f"{len(found)}件" + ("（絞り込みを緩めた。要確認）" if relaxed else ""))
    for a in found:
        mark = "要表示" if a.needs_attribution else "　　　"
        print(f"  [{a.source:<7}] {mark} {a.license:<18} {a.title[:44]}")
    return 0


def _first_downloadable(candidates: list[Asset], stem: Path) -> tuple[Asset, Path] | None:
    """落とせるものが出るまで候補を順に試す。

    Wikimedia の巨大なスキャン画像は、サムネイルが用意できず403になることがある
    （thumburl でも Special:FilePath でも同じ）。URLの組み立て方では解決しないので、
    次の候補へ進む。1つの検索語に候補は十数件あるので、これで埋まる。
    """
    for asset in candidates:
        path = _download(asset, stem)
        if path:
            return asset, path
    return None


def cmd_fetch(args) -> int:
    """カットごとの検索語リストから、素材を1枚ずつ確保する。"""
    spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    chosen: list[Asset] = []
    files: list[dict] = []
    for i, shot in enumerate(spec.get("shots", [])):
        raw = shot.get("query") if isinstance(shot, dict) else shot
        # 1カットに検索語を複数書ける。タイトル一致は取りこぼすので、言い換えを順に試す
        queries = [str(q) for q in (raw if isinstance(raw, list) else [raw])]
        found: list[Asset] = []
        relaxed = False
        query = queries[0]
        for q in queries:
            found, relaxed = search_all(q, per_source=args.limit)
            if found:
                query = q
                break
        if not found:
            print(f"[{i:03d}] 見つからず: {' / '.join(queries)}")
            continue
        got = _first_downloadable(found, out / f"{i:03d}")
        if got:
            asset, path = got
            record = asset.to_dict()
            record["file"] = path.name  # 実際の拡張子を控える
            record["query"] = query
            record["needs_review"] = relaxed
            files.append(record)
            chosen.append(asset)
            flag = " ★要確認" if relaxed else ""
            print(f"[{i:03d}] {path.suffix[1:]:<5} {asset.license:<16} {query[:28]}{flag}")
        else:
            print(f"[{i:03d}] 候補{len(found)}件すべて取得失敗: {query}")
        time.sleep(0.4)

    review = [f for f in files if f.get("needs_review")]
    if review:
        print(f"\n★ 絞り込みを緩めて拾ったカットが {len(review)}件ある。画を必ず目で見ること:")
        for f in review:
            print(f"   {f['file']}  {f['title'][:52]}")

    bad = unlicensed(chosen)
    if bad:
        print(f"\n!! ライセンス不明が {len(bad)}件ある。公開前に外すこと")

    (out / "manifest.json").write_text(
        json.dumps(files, ensure_ascii=False, indent=1), encoding="utf-8")
    credits_path = Path(args.credits or (out / "credits.txt"))
    credits_path.write_text(build_credits(chosen), encoding="utf-8")
    print(f"\n{len(chosen)}枚確保 -> {out}")
    print(f"クレジット -> {credits_path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="assets")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="検索して候補を見る")
    s.add_argument("query"); s.add_argument("--limit", type=int, default=12)
    s.set_defaults(func=cmd_search)
    f = sub.add_parser("fetch", help="カット一覧から素材を落とす")
    f.add_argument("spec"); f.add_argument("--out", default="video/public/shots")
    f.add_argument("--limit", type=int, default=8); f.add_argument("--credits")
    f.set_defaults(func=cmd_fetch)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
