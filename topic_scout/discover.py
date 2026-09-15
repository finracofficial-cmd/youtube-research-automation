"""題材候補の自動発掘。

手書きのシードは書いた人間の思いつきに偏るしスケールしない。
代わりに、量産系（ゆっくり・都市伝説）チャンネルそのものを需要センサーとして使う。
彼らは「再生が取れる題材」を毎週出し続けているので、その題材名を吸い上げれば
需要が実証済みの候補プールになる。

チャンネルタブの一覧では再生数が取れない（NA）ため、需要の代理指標には
「何チャンネルがその題材を扱ったか」を使う。実際の需要は後段の score.py が測る。
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .fetch import EXTRACTOR_ARGS

# タイトルの定型・煽り語。題材名ではないので落とす。
STOPWORDS = {
    "ゆっくり", "解説", "徹底", "検証", "考察", "雑学", "都市伝説", "ミステリー", "オカルト",
    "真相", "真実", "正体", "謎", "秘密", "衝撃", "驚愕", "戦慄", "禁断", "封印", "閲覧注意",
    "世界", "日本", "人類", "歴史", "科学", "最新", "最大", "最強", "最恐", "史上", "古代",
    "意外", "不思議", "有力", "発見", "判明", "解明", "解読", "存在", "理由", "原因", "結果",
    "研究", "学者", "博士", "教授", "専門", "可能", "話題", "紹介", "一覧", "選", "総集編",
    "前編", "後編", "完全版", "実話", "事実", "内容", "場所", "人物", "時代", "現代", "未来",
    "過去", "今回", "本当", "結論", "疑問", "問題", "状況", "関係", "影響", "変化", "記録",
    "報告", "情報", "証拠", "説明", "理論", "仮説", "議論", "方法", "技術", "文明", "文化",
    "生物", "動物", "植物", "人間", "女性", "男性", "子供", "自然", "地球", "宇宙", "生活",
    # --- 実走査（28ch / 1559タイトル）で実際に上位に出てきたノイズ ---
    "不可解", "決定的", "共通点", "超高度", "シナリオ", "メッセージ", "スキャン", "教科書",
    "異常現象", "建造物", "生命体", "人工物", "異星人", "エイリアン", "予言者", "飛行士",
    "考古学", "ミステリ", "未解決", "衝撃的", "驚異的", "圧倒的", "絶対的", "本格的",
    "徹底的", "科学的", "歴史的", "世界的", "決定版", "完全解説", "最終回", "第一部",
}

# 「語全体がこれ」のときだけ落とす。接尾辞として剥がすと
# ロストテクノロジー → ロスト のように題材名を壊すため、STOPWORDS とは分けている。
EXACT_ONLY = {
    "ミステリー", "エネルギー", "テクノロジー", "ストーリー", "エピソード", "ランキング",
    "巨大構造", "巨大都市", "設計図", "共通言語", "最終兵器", "未解決事件", "超古代文明",
}

# 現代の国名・広域地名。単体では題材にならない。
GEO_STOPWORDS = {
    "アメリカ", "フランス", "ヨーロッパ", "イギリス", "ドイツ", "イタリア", "スペイン",
    "ロシア", "アフリカ", "アジア", "オーストラリア", "カナダ", "ブラジル", "インド",
    "中国", "韓国", "北朝鮮", "エジプト", "ギリシャ", "トルコ", "メキシコ", "アメリカ人",
}

# 語の末尾に来ない束縛形態素。「再現不(可能)」「超高(度)」のような切れ端を弾く。
INCOMPLETE_END = re.compile(r"[不非未無超高低大小全半多少的性化被対反前後上下中内外]$")

# 「1万年前」「5億年前」のような年代表現。題材名ではない。
TIME_EXPR = re.compile(r"^[0-9０-９〇一二三四五六七八九十百千万億兆]*(?:万|億|千)?年前$|^[0-9０-９]+世紀$")

# 題材名になりやすい形
KATAKANA = re.compile(r"[ァ-ヶー]{4,}")
KANJI = re.compile(r"[一-龥]{3,8}")
SUFFIXED = re.compile(r"[ァ-ヶー一-龥A-Za-z0-9]{2,12}(?:事件|事故|遺跡|神殿|手稿|写本|文書|伝説|現象|生物|計画|実験)")
BRACKETS = re.compile(r"[【〖\[（(][^】〗\]）)]*[】〗\]）)]")


@dataclass
class Candidate:
    term: str
    n_channels: int
    n_videos: int
    examples: list[str]


def list_channel_titles(channel_id: str, limit: int = 60, timeout: int = 240) -> list[str]:
    cmd = ["yt-dlp", "--skip-download", "--no-warnings", "--flat-playlist",
           "--extractor-args", EXTRACTOR_ARGS, "--playlist-end", str(limit),
           "--print", "%(title)s",
           f"https://www.youtube.com/channel/{channel_id}/videos"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return [l.strip() for l in proc.stdout.splitlines() if l.strip()]


def _strip_stopword_affixes(term: str) -> str:
    """語頭・語末にくっついた定型語を削る。

    漢字の連続を貪欲に拾うと「死海文書最大」「徹底解説」のような塊になる。
    端から定型語を剥がすと「死海文書」が残り、「徹底解説」は消える。
    """
    changed = True
    while changed and term:
        changed = False
        for w in STOPWORDS:
            if len(term) > len(w) and term.startswith(w):
                term, changed = term[len(w):], True
            if len(term) > len(w) and term.endswith(w):
                term, changed = term[: -len(w)], True
        if term in STOPWORDS or term in GEO_STOPWORDS:
            return ""
    if term in EXACT_ONLY:
        return ""
    if TIME_EXPR.match(term):
        return ""
    if INCOMPLETE_END.search(term):
        return ""
    # 末尾の「ー」は語の一部（ロストテクノロジー）なので削らない。
    # 区切り記号だけ落とし、実体のある文字が残らなければ捨てる。
    term = term.strip("・-—　 ")
    if not re.search(r"[ァ-ヶ一-龥A-Za-z0-9]", term):
        return ""
    return term


def extract_terms(title: str) -> set[str]:
    """1本のタイトルから題材名になりうる語を抜く。"""
    t = BRACKETS.sub(" ", title)
    raw: set[str] = set()
    for m in SUFFIXED.finditer(t):      # 「〜事件」「〜手稿」は題材名である確度が高い
        raw.add(m.group())
    for m in KATAKANA.finditer(t):
        raw.add(m.group())
    for m in KANJI.finditer(t):
        raw.add(m.group())

    cleaned = {c for c in (_strip_stopword_affixes(r) for r in raw) if len(c) >= 3}
    # 同じタイトル内で他の語に完全に含まれる断片は落とす（「峠事件」より「ディアトロフ峠事件」）
    return {c for c in cleaned if not any(c != o and c in o for o in cleaned)}


def discover(channel_ids: list[str], *, per_channel: int = 60,
             cache: Path | None = None) -> list[Candidate]:
    """複数チャンネルを走査して候補語をランキングする。"""
    titles_by_channel: dict[str, list[str]] = {}
    if cache and cache.exists():
        titles_by_channel = json.loads(cache.read_text(encoding="utf-8"))

    for cid in channel_ids:
        if cid in titles_by_channel:
            continue
        try:
            titles_by_channel[cid] = list_channel_titles(cid, per_channel)
        except Exception:  # noqa: BLE001 - 取れないチャンネルは飛ばす
            titles_by_channel[cid] = []
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(titles_by_channel, ensure_ascii=False), encoding="utf-8")

    chans = collections.defaultdict(set)
    vids = collections.Counter()
    examples = collections.defaultdict(list)
    for cid, titles in titles_by_channel.items():
        for title in titles:
            for term in extract_terms(title):
                chans[term].add(cid)
                vids[term] += 1
                if len(examples[term]) < 2:
                    examples[term].append(title)

    out = [Candidate(t, len(chans[t]), vids[t], examples[t]) for t in chans]
    out.sort(key=lambda c: (-c.n_channels, -c.n_videos))
    return out
