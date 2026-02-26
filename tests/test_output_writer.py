"""output_writer モジュールのユニットテスト。"""

from datetime import datetime
from pathlib import Path

from app.output_writer import (
    _generate_filename,
    _determine_output_folder,
    get_output_folder,
    write_briefing,
    append_quiz_result,
    format_quiz_result_section,
)


# ────────────────────────────────────────────
# _generate_filename
# ────────────────────────────────────────────

class TestGenerateFilename:
    def test_feature_a(self):
        now = datetime(2026, 3, 15, 9, 30, 0)
        name = _generate_filename("a", now=now)
        assert name == "briefing_news_2026-03-15_093000.md"

    def test_feature_b(self):
        now = datetime(2026, 3, 15, 9, 30, 0)
        name = _generate_filename("b", now=now)
        assert name == "briefing_quiz_2026-03-15_093000.md"

    def test_unknown_feature(self):
        now = datetime(2026, 3, 15, 9, 30, 0)
        name = _generate_filename("x", now=now)
        assert name == "briefing_2026-03-15_093000.md"


# ────────────────────────────────────────────
# _determine_output_folder
# ────────────────────────────────────────────

class TestDetermineOutputFolder:
    def test_uses_existing_path(self, tmp_path: Path):
        out = tmp_path / "existing_output"
        out.mkdir()
        result = _determine_output_folder(
            input_folders=[str(tmp_path)],
            output_folder_name="_briefings",
            existing_output_path=str(out),
        )
        assert result == out

    def test_creates_new_folder(self, tmp_path: Path):
        result = _determine_output_folder(
            input_folders=[str(tmp_path)],
            output_folder_name="_briefings",
            existing_output_path="",
        )
        assert result.name == "_briefings"
        assert result.exists()

    def test_raises_on_empty_input_folders(self):
        import pytest
        with pytest.raises(ValueError):
            _determine_output_folder(
                input_folders=[],
                output_folder_name="_briefings",
                existing_output_path="",
            )

    def test_collision_adds_suffix(self, tmp_path: Path):
        (tmp_path / "_briefings").mkdir()
        result = _determine_output_folder(
            input_folders=[str(tmp_path)],
            output_folder_name="_briefings",
            existing_output_path="",
        )
        assert result.name == "_briefings_2"


# ────────────────────────────────────────────
# write_briefing
# ────────────────────────────────────────────

class TestWriteBriefing:
    def test_writes_file(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        now = datetime(2026, 1, 1, 10, 0, 0)
        path = write_briefing("# Test", "a", str(out_dir), now=now)
        assert Path(path).exists()
        assert Path(path).read_text(encoding="utf-8") == "# Test"

    def test_creates_output_dir_if_missing(self, tmp_path: Path):
        out_dir = tmp_path / "new_output"
        now = datetime(2026, 1, 1, 10, 0, 0)
        path = write_briefing("content", "b", str(out_dir), now=now)
        assert Path(path).exists()


# ────────────────────────────────────────────
# append_quiz_result
# ────────────────────────────────────────────

class TestAppendQuizResult:
    def test_appends_to_existing(self, tmp_path: Path):
        f = tmp_path / "briefing.md"
        f.write_text("# Original", encoding="utf-8")
        append_quiz_result(str(f), "## Quiz Result\n- Correct")
        content = f.read_text(encoding="utf-8")
        assert "# Original" in content
        assert "## Quiz Result" in content

    def test_nonexistent_file_noop(self, tmp_path: Path):
        # 存在しないファイルへの追記は何もしない
        append_quiz_result(str(tmp_path / "nope.md"), "result")


# ────────────────────────────────────────────
# format_quiz_result_section
# ────────────────────────────────────────────

class TestFormatQuizResultSection:
    def test_auto_mode(self):
        results = [
            {
                "topic_title": "テスト",
                "pattern_emoji": "📘",
            }
        ]
        section = format_quiz_result_section(results, is_auto=True)
        assert "自動処理" in section
        assert "未回答" in section

    def test_manual_mode_correct(self):
        now = datetime(2026, 3, 1, 12, 0)
        results = [
            {
                "topic_title": "Topic A",
                "pattern_emoji": "📗",
                "q1_correct": True,
                "q2_evaluation": "good",
                "q2_feedback": "素晴らしい",
                "next_quiz_info": "2026-03-08",
            }
        ]
        section = format_quiz_result_section(results, is_auto=False, now=now)
        assert "✅ 正解" in section
        assert "good" in section
        assert "素晴らしい" in section
        assert "2026-03-08" in section

    def test_manual_mode_incorrect_poor(self):
        now = datetime(2026, 3, 1, 12, 0)
        results = [
            {
                "topic_title": "Topic B",
                "pattern_emoji": "📘",
                "q1_correct": False,
                "q1_correct_answer": "C",
                "q2_evaluation": "poor",
                "q2_feedback": "要復習",
            }
        ]
        section = format_quiz_result_section(results, is_auto=False, now=now)
        assert "❌ 不正解" in section
        assert "正解: C" in section
        assert "poor" in section

    def test_empty_results(self):
        section = format_quiz_result_section([])
        assert "クイズ結果" in section
