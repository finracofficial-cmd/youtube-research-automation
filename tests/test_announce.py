"""Issue コメントの案内。Make video に入れる値と、できたファイルのパスを全部出す。"""
from pathlib import Path

from script_engine import announce as A


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "drafts").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "seeds/topics").mkdir(parents=True)
    (tmp_path / "drafts/dead-sea.txt").write_text("台本。", encoding="utf-8")
    (tmp_path / "reports/dead-sea_report.txt").write_text(
        "4104字 / 忠実度 58%\n\n品質の合格条件:\n  ○ 資料に無い数字が無い\n  → 合格\n"
        "尺: 約11分（指定 15分）→ 資料不足\n\n初見の読み: 8/10  ついていけた\n  [第2章] 飛躍: 「x」 — y\n\n"
        "装置 …\n資料に無い数字（人が確かめる）: 1921年\n", encoding="utf-8")
    (tmp_path / "seeds/topics/dead-sea.yaml").write_text("subject: 死海文書\n", encoding="utf-8")
    return tmp_path


def test_make_video_values_and_every_existing_file_are_listed_with_links(tmp_path):
    md = A.render("dead-sea", "死海文書", repo="o/r", branch="claude/x", root=_repo(tmp_path))
    assert "| script | `drafts/dead-sea.txt` |" in md and "| name | `dead-sea` |" in md
    assert "https://github.com/o/r/actions/workflows/make-video.yml" in md
    assert "[drafts/dead-sea.txt](https://github.com/o/r/blob/claude/x/drafts/dead-sea.txt)" in md
    assert "[reports/dead-sea_report.txt](" in md and "[seeds/topics/dead-sea.yaml](" in md
    assert "drafts/ の台本だけ" in md
    assert "_plan.json" not in md and "_sources.json" not in md      # 無いファイルは並べない


def test_verdict_block_carries_gate_length_and_loose_numbers(tmp_path):
    md = A.render("dead-sea", "死海文書", repo="o/r", branch="b", root=_repo(tmp_path))
    assert "品質の合格条件:" in md and "→ 合格" in md
    assert "尺: 約11分" in md and "資料に無い数字（人が確かめる）: 1921年" in md
    assert "初見の読み: 8/10" in md and "[第2章] 飛躍" not in md      # 点だけ。指摘の一覧は判定ファイルで
    assert "不合格の台本は動画にしない" not in md


def test_a_failed_gate_is_called_out(tmp_path):
    root = _repo(tmp_path)
    (root / "reports/dead-sea_report.txt").write_text(
        "品質の合格条件:\n  × 資料に無い数字が無い\n  → 不合格（動画にしない）\n", encoding="utf-8")
    md = A.render("dead-sea", "死海文書", repo="o/r", branch="b", root=root)
    assert "不合格の台本は動画にしない" in md



def test_guard_rejects_reports_and_plans_and_names_the_real_scripts(tmp_path):
    """判定ファイルを台本として渡され、それを読み上げる動画ができた（Make video #5）。"""
    from script_engine import guard as G
    d = tmp_path / "drafts"; d.mkdir()
    (d / "dead-sea.txt").write_text("死海文書。\n" + "乾いた洞窟に壷が並ぶ。\n" * 120, encoding="utf-8")
    (d / "dead-sea_report.txt").write_text("4104字\n\n品質の合格条件:\n  ○ 資料に無い数字が無い\n" * 40, encoding="utf-8")
    (d / "short.txt").write_text("短い。", encoding="utf-8")
    assert G.problems(d / "dead-sea.txt") == []
    got = G.problems(d / "dead-sea_report.txt")
    assert any("名前が台本ではない" in x for x in got) and any("合格条件" in x for x in got)
    assert any("短すぎる" in x for x in G.problems(d / "short.txt"))
    assert G.candidates(d) == [d / "dead-sea.txt"]
    assert G.main([str(d / "dead-sea_report.txt")]) == 1
    assert G.main([str(d / "dead-sea.txt")]) == 0
