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
import time
import urllib.error
import urllib.request

API = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1"

_SYSTEM = """あなたは日本語のドキュメンタリー動画の構成作家です。
渡された指示に厳密に従って台本本文だけを書きます。

- 見出し、記号、話者名、ト書きは書かない。読み上げる文だけを書く。
- 断定できないことは断定しない。「〜とされる」「〜という説がある」を使う。
- 数字は出典にある値をそのまま使う。丸めない。「以上」「前後」を落とさない。
- 一次資料に当たった結果を語る口調にする。"""


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
            return (d["choices"][0]["message"]["content"] or "").strip()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and a < 3:
                time.sleep(2 ** a * 5)
                continue
            raise WriteFailed(f"HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    raise WriteFailed("応答が得られなかった")


def write(prompt: str, *, model: str = DEFAULT_MODEL, rounds: int = 2,
          checker=None) -> tuple[str, list[str]]:
    """台本を書かせ、実測から外れていれば直させる。

    checker は台本を受けて「直すべき点の一覧」を返す関数。空なら合格。
    戻り値は (台本, 最後に残った指摘)。
    """
    messages = [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt}]
    text = _chat(messages, model)
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
             + "\n".join(f"- {n}" for n in notes)},
        ]
        text = _chat(messages, model)
    return text, notes
