"""台本からオーバーレイを抜く工程を、正規表現ではなくLLMにやらせる。

正規表現では文脈が読めず、実際に画面へ事実誤りを出した:
  「紀元前1世紀」の接頭辞を落として2000年ずれた
  「地質学者ではない」という否定から役割を取って逆の意味にした
  「オスマン帝国の提督ピリ・レイス」から組織名を人名として拾った
どれも「その文が何を言っているか」が分かれば起きない誤りなので、LLMの領分。

ただしLLMは台本に無い値を書くことがある。だから戻り値は必ず検証する:
  1. 参照している文が実在すること
  2. 値・氏名・読み値が、その文に**そのまま出てくる**こと
  3. 種別が既知であること
検証を通らなかったものは捨てる。捨てた数は呼び出し側に返す。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from autolayout import MAX_DURATION, MIN_DURATION, Cue, Line

API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1"

KINDS = {"stat", "portrait", "chart", "timeline", "glyph", "grid",
         "quote", "caveat", "document", "cardrow", "chips"}
ZONES = {"left", "right", "center", "lower", "corner"}

# 値がその文に出てくるかを見るとき、表記ゆれを吸収する程度の正規化に留める。
# 緩めすぎると幻覚を通してしまう。
_NORM = str.maketrans("０１２３４５６７８９，．　", "0123456789,. ")


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class ExtractResult:
    cues: list[Cue]
    rejected: int
    reason: str = ""


SYSTEM = """あなたはドキュメンタリー動画の編集者です。
ナレーション台本を読み、各文に対して画面に出すべき情報グラフィックを決めます。

使える部品:
- stat: 数値の単独提示。value(単位と接頭辞を含む完全な表記), label(短い説明)
- portrait: 人物。name(氏名のみ。組織名は不可), role(肩書), year(西暦。無ければ空)
- chart: 割合の推移。readout(表示する値), caption
- timeline: 年代の並び。marks(年のリスト)
- glyph: 1〜2文字の記号や文字。glyph, caption
- grid: 総量の可視化。caption
- quote: 引用。heading(誰の何か), translation(引用の中身)
- caveat: 留保。text
- document: 論文や資料の提示。venue, title

厳守:
- 値は台本にそのまま書かれている表記を使う。言い換えたり補ったりしない
- 「紀元前」「約」などの接頭辞を落とさない
- 否定文（「〜ではない」）から属性を取らない
- 組織名を人名にしない
- 大書きに値しない小さな数（1人、2枚など）は stat にしない
- 出す価値が無い文には何も割り当てない。無理に埋めない

出力はJSONのみ。形式:
{"cues": [{"line": 12, "kind": "stat", "zone": "right", "payload": {...}}]}"""


def build_messages(lines: list[Line], start: int, count: int) -> list[dict]:
    body = "\n".join(f"{start + i}: {l.text}" for i, l in enumerate(lines[start:start + count]))
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"台本（行番号つき）:\n{body}"}]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text.translate(_NORM))


# 値の直前に付いていたら意味が変わる語。これを落とした値は不完全とみなす。
# 単純な部分文字列判定では「紀元前1世紀」から「1世紀」を取っても通ってしまう。
_QUALIFIERS = ("紀元前", "紀元後", "推定", "およそ", "約", "最大", "最小", "平均", "前")


def _drops_qualifier(value: str, source: str) -> bool:
    """値が、原文では接頭辞つきで書かれているのに、それを落としていないか。"""
    src, val = _norm(source), _norm(value)
    at = src.find(val)
    while at != -1:
        head = src[:at]
        if not any(head.endswith(q) for q in _QUALIFIERS):
            return False          # 接頭辞の付いていない出現がある＝そのままで正しい
        at = src.find(val, at + 1)
    return True                    # すべての出現が接頭辞つきだった＝落としている


def _grounded(payload: dict, source: str) -> bool:
    """値が台本の当該文に実在するか。幻覚を弾く最後の砦。"""
    src = _norm(source)
    for key in ("value", "name", "readout", "glyph"):
        v = payload.get(key)
        if not v:
            continue
        if _norm(str(v)) not in src:
            return False
        if key == "value" and _drops_qualifier(str(v), source):
            return False
    for mark in payload.get("marks") or []:
        label = mark.get("label") if isinstance(mark, dict) else mark
        if label and _norm(str(label).rstrip("年")) not in src:
            return False
    return True


def parse(raw: str, lines: list[Line]) -> ExtractResult:
    """LLMの出力をCueに変換し、検証を通らないものを捨てる。"""
    try:
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
    except json.JSONDecodeError:
        return ExtractResult([], 0, "JSONとして読めない")

    cues, rejected = [], 0
    for item in data.get("cues") or []:
        idx = item.get("line")
        kind = item.get("kind")
        zone = item.get("zone") or "center"
        payload = item.get("payload") or {}
        if not isinstance(idx, int) or not 0 <= idx < len(lines):
            rejected += 1; continue
        if kind not in KINDS:
            rejected += 1; continue
        if zone not in ZONES:
            zone = "center"
        if not _grounded(payload, lines[idx].text):
            rejected += 1; continue
        line = lines[idx]
        dur = max(MIN_DURATION, min(MAX_DURATION, line.durationSec * 2))
        cues.append(Cue(kind, line.startSec, dur, zone, payload))
    return ExtractResult(cues, rejected)


def call(messages: list[dict], *, model: str = DEFAULT_MODEL, timeout: int = 180) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise LLMUnavailable("OPENAI_API_KEY が未設定。環境変数で渡すこと")
    body = json.dumps({"model": model, "messages": messages,
                       "response_format": {"type": "json_object"},
                       "temperature": 0}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as exc:
        raise LLMUnavailable(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    return payload["choices"][0]["message"]["content"]


def extract(lines: list[Line], *, chunk: int = 60, model: str = DEFAULT_MODEL) -> ExtractResult:
    """台本を分割してLLMにかけ、検証を通ったCueだけ集める。"""
    all_cues: list[Cue] = []
    rejected = 0
    for start in range(0, len(lines), chunk):
        raw = call(build_messages(lines, start, chunk), model=model)
        r = parse(raw, lines)
        all_cues += r.cues
        rejected += r.rejected
    return ExtractResult(all_cues, rejected)


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))
