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

# 1カットで試す候補の上限。候補を全部試すと、巨大なスキャン画像が並ぶ記事に
# 当たったとき1カットで何分も止まる（実測で Ancient Rome で停滞した）。
# 候補は代表画像から順に並んでいるので、上位で取れなければ下位でも取れない。
MAX_TRIES_PER_SHOT = 4
MAX_SECONDS_PER_SHOT = 45.0

import yaml

from .credits import build as build_credits
from .credits import unlicensed
from .sources import UA, Asset, search_all
from .wikipage import Unreachable, entity_types, page_images


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
        data = urllib.request.urlopen(req, timeout=30).read()
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


def _candidates(queries: list[str], limit: int) -> tuple[list[Asset], str, bool]:
    """検索語の並びから候補を作る。記事からの取得を先に試す。

    検索語はWikipediaの英語見出しなので、そのまま記事を引ける。記事に
    載っている画像は、定義上その記事の主題のものになる。キーワード検索は
    語義を区別せず、Archimedes に月のクレーターを返してくるので後回し。

    候補は語ごとに打ち切らず、全部つないで返す。1語目で候補が見つかっても、
    その全部が落とせないことがある（実測で Valerios Stais の記事に画像が
    無く、検索で拾った1件も403で、冒頭5カットが空になった）。
    """
    from_articles: list[Asset] = []
    from_search: list[Asset] = []
    first = ""
    # 人物の顔写真は、その人物を指す語のときだけ使う。題材が人物でないのに
    # 顔写真を全画面に出すと、その人が題材に関係しているように見える。
    types = entity_types(queries)
    unreachable = False
    for q in queries:
        human = "human" in (types.get(q) or {}).get("t", [])
        try:
            got = page_images(q, limit=limit, people_ok=human)
        except Unreachable:
            unreachable = True
            continue
        if got:
            from_articles += got
            first = first or q
    # APIに届かなかっただけなら検索に落とさない。検索は語義を区別しないので、
    # 通信が詰まったぶんだけ題材と食い違う画が増える。空のまま返して
    # 呼び出し側に直前の画を引き継がせる。
    if not from_articles and not unreachable:
        for q in queries:
            got, _ = search_all(q, per_source=limit)
            if got:
                from_search += got
                first = first or q
    seen: set[str] = set()
    uniq = [a for a in from_articles + from_search
            if not (a.title in seen or seen.add(a.title))]
    # 記事から1枚も取れなかった場合だけ、人の確認に回す
    return uniq, first or (queries[0] if queries else ""), not from_articles


def _carry(files: list[dict], segment: int) -> bool:
    """直前に取れた画をこの区間にも当てる。取れていなければ偽。

    空のカットは黒画面になる。素材が無い区間は、題材の合った直前の画を
    続けて使う方がよい。
    """
    if not files:
        return False
    files.append({**files[-1], "segment": segment, "carried": True})
    return True


def cmd_fetch(args) -> int:
    """カットごとの検索語リストから、素材を1枚ずつ確保する。"""
    spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cache: dict[str, tuple[list[Asset], str, bool]] = {}
    used_rank: dict[str, int] = {}   # 同じ記事が続くカットには別の画を回す
    downloaded: dict[str, str] = {}  # 同じファイルを二度落とさない
    chosen: list[Asset] = []
    files: list[dict] = []
    for i, shot in enumerate(spec.get("shots", [])):
        raw = shot.get("query") if isinstance(shot, dict) else shot
        queries = [str(q) for q in (raw if isinstance(raw, list) else [raw])]
        key = "|".join(queries)
        if key not in cache:
            cache[key] = _candidates(queries, args.limit)
            time.sleep(0.3)
        found, query, relaxed = cache[key]
        if not found:
            # 候補が1件も無い場合も引き継ぐ。ここを落とすと区間ごと消え、
            # 画の無い時間ができる（通信に失敗した回で20区間が欠けた）。
            if _carry(files, i):
                print(f"[{i:03d}] 候補なし。直前の画を引き継ぐ: {queries[0]}")
            else:
                print(f"[{i:03d}] 見つからず: {' / '.join(queries)}")
            continue

        # 記事の何枚目から試すかをずらす。同じ話題が続く区間で画が変わる
        start = used_rank.get(key, 0)
        ordered = found[start:] + found[:start]
        used_rank[key] = (start + 1) % len(found)

        asset = path = None
        began, tries = time.monotonic(), 0
        for cand in ordered:
            if cand.title in downloaded:  # 既に手元にある。落とし直さない
                asset, path = cand, Path(downloaded[cand.title])
                break
            if tries >= MAX_TRIES_PER_SHOT or \
                    time.monotonic() - began > MAX_SECONDS_PER_SHOT:
                break
            tries += 1
            got = _download(cand, out / f"{i:03d}")
            if got:
                asset, path = cand, got
                downloaded[cand.title] = str(got)
                break
        if not asset or not path:
            # 空のカットは黒画面になる。直前に取れた画を引き継ぐ
            if _carry(files, i):
                print(f"[{i:03d}] 取得失敗。直前の画を引き継ぐ: {query}")
            else:
                print(f"[{i:03d}] 候補{len(found)}件すべて取得失敗: {query}")
            continue

        record = asset.to_dict()
        record["file"] = path.name
        # どの区間のために選んだ画かを残す。カット数と区間数は一致しないので、
        # これが無いと並び順で割り当てるしかなく、語りと画がずれる。
        record["segment"] = i
        record["n_segments"] = len(spec.get("shots", []))
        record["query"] = query
        record["needs_review"] = relaxed
        files.append(record)
        chosen.append(asset)
        flag = " ★要確認" if relaxed else ""
        print(f"[{i:03d}] {path.name:<8} {asset.license:<16} {query[:26]}{flag}")
        time.sleep(0.2)

    # 冒頭の区間は題材の一般名しか含まず、語が取れないことが多い。
    # 引き継ぎは直前からしかできないので、最初に取れた画を遡って当てる。
    if files and files[0]["segment"] > 0:
        head = dict(files[0])
        for seg in range(files[0]["segment"]):
            files.insert(seg, {**head, "segment": seg, "carried": True})
        print(f"冒頭{files[0]['segment'] if False else head['segment']}区間に"
              f"最初の画を遡って当てた")

    review = [f for f in files if f.get("needs_review")]
    if review:
        print(f"\n★ 記事から引けず検索に落ちたカットが {len(review)}件ある。画を目で見ること:")
        for f in review:
            print(f"   {f['file']}  {f['title'][:52]}")

    bad = unlicensed(chosen)
    if bad:
        print(f"\n!! ライセンス不明が {len(bad)}件ある。公開前に外すこと")

    (out / "manifest.json").write_text(
        json.dumps(files, ensure_ascii=False, indent=1), encoding="utf-8")
    credits_path = Path(args.credits or (out / "credits.txt"))
    credits_path.write_text(build_credits(chosen), encoding="utf-8")
    distinct = len({f["file"] for f in files})
    print(f"\n{len(files)}カット / 異なる画像 {distinct}枚 -> {out}")
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
