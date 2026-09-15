"""台本のビートシート。元チャンネル2本の構造を、題材非依存の骨として抜いたもの。

比率(share)は実測:
  旗艦型（ヴォイニッチ 52:39）: 導入2.6% / 第1幕19.8% / 第2幕22.2% / 第3幕25.2% / 第4幕30.1%
    → 幕は後半ほど長い。意図的な逓増で、終盤に向けて密度を上げている。
  束ね型（ピラミッド 37:52）: 導入2.9% / 各章7〜13% / 終章6.0%
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Beat:
    key: str
    name: str
    share: float          # 尺全体に対する比率
    purpose: str          # このビートが担う役割
    rules: tuple[str, ...] = ()   # 生成時に守らせる具体的な制約
    fixed_line: str | None = None  # ほぼ固定文のスロット（題材名だけ差し替える）


@dataclass(frozen=True)
class BeatSheet:
    key: str
    name: str
    beats: tuple[Beat, ...]
    typical_duration_sec: int

    def allocate(self, duration_sec: int | None = None) -> list[tuple[Beat, int]]:
        """尺を各ビートに配分する。合計は必ず duration に一致させる。"""
        total = duration_sec or self.typical_duration_sec
        out, acc = [], 0
        for b in self.beats[:-1]:
            sec = round(total * b.share)
            out.append((b, sec)); acc += sec
        out.append((self.beats[-1], total - acc))  # 端数は最後に寄せる
        return out


_OPENING = (
    Beat("cold_open", "体言止めの一撃", 0.004,
         "1秒目から本題。挨拶も自己紹介もしない",
         ("題材名を単独で言い切る（例:「ピラミッド。」）",
          "次の1文で、その題材の規模か年数を数字で出す")),
    Beat("strangeness", "異様さの具体3つ", 0.010,
         "抽象的な「謎」ではなく、映像で見せられる具体を3つ並べる",
         ("3つとも、画で示せる具体物にする",
          "形容詞ではなく事実で書く（「すごい」ではなく「誰も入っていない」）")),
    Beat("channel_claim", "チャンネル宣言", 0.004,
         "競合との違いをここで宣言する。ほぼ固定文",
         ("量産系の語彙（ついに解読・衝撃の真実）を否定する形で名乗る",),
         "当チャンネルでは、こうした{genre}を、都市伝説として語るのではなく、"
         "論文と一次資料からひも解いていく。"),
    Beat("core_question", "謎の核", 0.007,
         "何が決着していないのかを1文で言い切り、安易な理由を先に潰す",
         ("「単に難しいからではない」型で、凡庸な説明を先に否定する",)),
)

_LAUNCH = Beat("launch", "出発の合図", 0.003,
               "視聴者を連れて行く宣言。ほぼ固定文", (),
               "それでは私と共に、{subject}へと迫っていこう。")

_CLOSING = (
    Beat("generalization", "一般化", 0.055,
         "題材を離れた普遍的な洞察に着地させる。ここが拡散の動力",
         ("この動画の結論が、この題材より大きくなるようにする",
          "「なぜそうなるのか」を、題材を知らない人にも効く形で答える")),
    Beat("callback", "回収", 0.025,
         "序盤に開いたループを閉じ、分かったこと／分からないことを並べる",
         ("「〜と分かった」を反復し、最後に「だが〜は分かっていない」で落とす",)),
    Beat("future_condition", "条件の提示", 0.020,
         "いつ解決するのかを、願望ではなく条件で答える",
         ("「もっと優れた技術が出れば」ではなく、具体的に何が見つかれば良いかを言う",)),
    Beat("cta", "CTA", 0.015,
         "ここだけ敬体に切り替える。語り手から人間に戻る",
         ("敬体（です・ます）を使う唯一の区間",
          "一次資料への導線を出す（誰でも見られることを伝える）",
          "調べてほしい題材の募集をする")),
)


def _flagship() -> BeatSheet:
    roadmap = Beat("roadmap", "全体の地図", 0.012,
                   "何幕あるのか、各幕が何の話かを先に全部見せる",
                   ("幕の数と、各幕が扱う年数や範囲を先に開示する",
                    "長尺を最後まで見せるための約束として機能させる"))
    # 実測の幕比 19.8 / 22.2 / 25.2 / 30.1 を、本編に割り当てられる分へ按分。
    # 固定ビートの share を全部引いてから配ること（引き忘れると端数が最後のビートを潰す）
    body = (1.0 - sum(b.share for b in _OPENING) - roadmap.share
            - _LAUNCH.share - sum(b.share for b in _CLOSING))
    ratios = (0.198, 0.222, 0.252, 0.301)
    acts = tuple(
        Beat(f"act{i+1}", f"第{i+1}幕", body * r / sum(ratios),
             "時系列で1段階ぶん進める。幕は後半ほど長くする",
             ("幕の最後は必ず「ここまでが〜の話である」で閉じる",
              "閉じた直後に「では〜はどうなのか」で次の幕の問いを開く",
              "4〜5分に1回、同じ型で小さく締め直す"))
        for i, r in enumerate(ratios)
    )
    return BeatSheet("flagship", "旗艦型（単一題材の深掘り）",
                     _OPENING + (roadmap, _LAUNCH) + acts + _CLOSING, 3159)


def _bundle(n_claims: int = 6) -> BeatSheet:
    gradient = Beat("gradient", "検証順の宣言", 0.012,
                    "主張を信頼度順に並べることを先に宣言する",
                    ("「当たっていたもの→理由が違うもの→跡形もなくなるもの」の順にする",
                     "先に視聴者の信念を肯定してから反転させる。最初から否定しない"))
    body = 1.0 - sum(b.share for b in _OPENING) - gradient.share - _LAUNCH.share - sum(b.share for b in _CLOSING)
    claims = tuple(
        Beat(f"claim{i+1}", f"第{i+1}主張", body / n_claims,
             "語られている主張を1つ取り、最初に言い出した人まで戻って確かめる",
             ("誰が・何年に言い出したかを特定する",
              "一次資料に当たった結果、当たり／半分当たり／跡形なしのどれかを明示する",
              "章の最後の1文が、次の章の問いになるようにする"))
        for i in range(n_claims)
    )
    return BeatSheet("bundle", f"束ね型（{n_claims}主張の検証）",
                     _OPENING + (gradient, _LAUNCH) + claims + _CLOSING, 2272)


FLAGSHIP = _flagship()
BUNDLE = _bundle()


def get(kind: str, n_claims: int = 6) -> BeatSheet:
    if kind == "flagship":
        return FLAGSHIP
    if kind == "bundle":
        return _bundle(n_claims)
    raise ValueError(f"unknown beat sheet: {kind!r}")
