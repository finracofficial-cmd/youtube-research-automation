"""組み立てたプロンプトをLLMに渡して台本を書かせ、実測に照らして直す。

prompt サブコマンドはプロンプトを組むところまでで、書くのは人手だった。
月15本の運用ではそこが詰まるので、生成まで通す。

書かせた台本はそのまま採らない。文長・数値密度・1分あたりの文字数を
参照動画の実測と突き合わせ、外れていれば指摘つきで書き直させる。
一度で通らないのが普通なので、既定で2回まで直させる。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from meter import note_usage

from .tighten import tighten

API = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1"

_SYSTEM = """あなたは日本語のドキュメンタリー動画の構成作家です。
渡された指示に厳密に従って台本本文だけを書きます。

- 見出し、記号、話者名、ト書きは書かない。読み上げる文だけを書く。
- 断定できないことは断定しない。「〜とされる」「〜という説がある」を使う。
- 数字は出典にある値をそのまま使う。丸めない。「以上」「前後」を落とさない。
- 一次資料に当たった結果を語る口調にする。
- 出典の題名を本文に書かない。英語の題名は読み上げると日本語の途中で
  英語が読まれ、ナレーションとして成立しない。実測で1つ70字あり、
  文の長さも押し上げていた。「2006年の論文では」「ある調査では」のように
  年と種別だけで指し、題名は概要欄に回す。

文の長さが要点です。数値だけでは伝わらないので、書き方を示します。

避ける書き方（1文が長い）:
  この装置は1901年に沈没船から引き上げられたが、当初は腐食した青銅の塊と
  見なされており、内部に歯車機構があると判明したのは70年後のことだった。

とるべき書き方（短く切る）:
  1901年、沈没船から引き上げられた。
  当初は腐食した青銅の塊と見なされていた。
  内部に歯車があると分かったのは、70年後である。

後者は3文で、1文あたり20字前後です。主語と述語を1組だけ置き、
接続助詞（〜が、〜ので、〜ており）で続けずに切ります。
台本全体をこの調子で書いてください。

数字も要点です。1分あたり8個、つまり2〜3文に1つは具体的な数値
（年・点数・寸法・比率）を置きます。出典にある数字をそのまま使います。"""


# 構成ブロックの名前が見出しとして出力に混ざる。指示で禁じても従わない
# ことがあり、実測で15個混入した。読み上げると「シャープシャープ
# 体言止めの一撃」と読まれるので、指示ではなく後処理で確実に落とす。
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s.*$", re.M)
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+", re.M)
_EMPHASIS = re.compile(r"\*{1,3}([^*]+)\*{1,3}")
_FENCE = re.compile(r"^\s*```.*$", re.M)


def clean(text: str) -> str:
    """読み上げる文だけを残す。

    見出し・箇条書きの印・強調の記号・コードの囲みは、声に出すと
    そのまま読まれるか、不自然な間になる。
    """
    text = _FENCE.sub("", text)
    text = _HEADING.sub("", text)
    text = _BULLET.sub("", text)
    text = _EMPHASIS.sub(r"\1", text)
    # 行末の空白はMarkdownの改行指示。読み上げには要らない
    text = "\n".join(l.rstrip() for l in text.splitlines())
    # 見出しを抜いた跡に空行が続く
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class WriteFailed(RuntimeError):
    """鍵が無い、またはAPIが応答しない。"""


def _chat(messages: list[dict], model: str, *, timeout: int = 300) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not os.environ.get("OPENAI_VIA_PROXY"):
        raise WriteFailed("OPENAI_API_KEY が未設定。環境変数で渡すこと")
    body = json.dumps({"model": model, "messages": messages,
                       "temperature": 0.8}).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    for a in range(4):
        try:
            req = urllib.request.Request(API, data=body, headers=headers)
            d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            note_usage("chat", model, d)
            return (d["choices"][0]["message"]["content"] or "").strip()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and a < 3:
                time.sleep(2 ** a * 5)
                continue
            raise WriteFailed(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    raise WriteFailed("応答が得られなかった")


# 参照動画の実測の話速。必要な字数はここから決まる。
# 字数を言わずに書かせると、文を短く切るほど全体も短くなり、尺に足りない
# （実測で271字/分、必要な下限320を下回った）。
CHARS_PER_MIN = 360


def write(prompt: str, *, model: str = DEFAULT_MODEL, rounds: int = 2,
          checker=None, duration_sec: float = 900.0) -> tuple[str, list[str]]:
    """台本を書かせ、実測から外れていれば直させる。

    checker は台本を受けて「直すべき点の一覧」を返す関数。空なら合格。
    戻り値は (台本, 最後に残った指摘)。
    """
    need = int(duration_sec / 60 * CHARS_PER_MIN)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content":
         f"{prompt}\n\n## 分量\n"
         f"本文は {need:,} 字以上書いてください（{duration_sec / 60:.0f}分ぶん）。"
         f"文を短く切ると全体も短くなりがちですが、文の数を増やして"
         f"この字数に届かせてください。足りない場合は、各主張の"
         f"検証の過程をもう一段詳しく書きます。"},
    ]
    text = tighten(clean(_chat(messages, model)))
    notes: list[str] = []
    for _ in range(rounds):
        notes = checker(text) if checker else []
        if not notes:
            break
        messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content":
             "以下の点が参照動画の実測から外れています。"
             "内容は変えずに、指摘された点だけを直した全文を出してください。\n\n"
             + "\n".join(f"- {n}" for n in notes)
             + f"\n\n本文は {need:,} 字以上を保ってください。"
             + "\n文が長い場合は、接続助詞で切って2文に分けてください。"
             "要約して短くするのではなく、同じ内容のまま文の数を増やします。"
             "たとえば「Aだが、Bである」は「Aである。しかしBだ」に分けます。"},
        ]
        text = tighten(clean(_chat(messages, model)))
    return text, notes
