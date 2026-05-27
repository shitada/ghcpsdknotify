"""feature_b モジュールのユニットテスト。"""

from unittest.mock import MagicMock, patch

from app.config import AppConfig, NotificationConfig
from app.feature_b import run
from app.state_manager import AppState, StateManager


def _make_sm() -> StateManager:
    sm = StateManager.__new__(StateManager)
    sm._state = AppState()
    sm._path = None  # type: ignore[assignment]
    return sm


def _make_config(**kwargs) -> AppConfig:
    defaults = dict(
        input_folders=["/test"],
        notification=NotificationConfig(enabled=False),
    )
    defaults.update(kwargs)
    return AppConfig(**defaults)


class TestRunFeatureB:
    def test_skips_when_input_folders_empty(self):
        config = _make_config(input_folders=[])
        sm = _make_sm()
        with patch("app.feature_b.notify_processing"):
            run(config, sm)
        assert sm.state.run_count_b == 0

    @patch("app.feature_b.scan_folders", return_value=[])
    @patch("app.feature_b.notify_processing")
    def test_skips_when_no_scanned_files(self, mock_notify, mock_scan):
        config = _make_config()
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_b == 0

    @patch("app.feature_b.notify_briefing")
    @patch("app.feature_b.write_briefing", return_value="/out/quiz.md")
    @patch("app.feature_b.get_output_folder", return_value="/out")
    @patch("app.feature_b.asyncio")
    @patch("app.feature_b.get_user_prompt_b", return_value=MagicMock(format=MagicMock(return_value="user")))
    @patch("app.feature_b.build_quiz_schedule_info", return_value="info")
    @patch("app.feature_b.build_file_contents", return_value="contents")
    @patch("app.feature_b.build_file_list_with_metadata", return_value="list")
    @patch("app.feature_b.get_system_prompt_b", return_value="system")
    @patch("app.feature_b.select_files")
    @patch("app.feature_b.scan_folders")
    @patch("app.feature_b.notify_processing")
    @patch("app.feature_b.process_unanswered")
    @patch("app.feature_b.extract_topic_keys", return_value=[{"topic_key": "t1", "pattern": "learning"}])
    @patch("app.feature_b.get_random_picked_paths", return_value=[])
    def test_full_flow_registers_pending_quiz(
        self, mock_random, mock_extract, mock_process, mock_notify_proc,
        mock_scan, mock_select, mock_sys, mock_list, mock_contents,
        mock_quiz_info, mock_user, mock_asyncio, mock_get_output,
        mock_write, mock_notify_briefing,
    ):
        config = _make_config()
        sm = _make_sm()
        mock_file = MagicMock()
        mock_scan.return_value = [mock_file]
        mock_selection = MagicMock()
        mock_selection.selected_files = [mock_file]
        mock_selection.is_discovery = False
        mock_select.return_value = mock_selection
        mock_asyncio.run = MagicMock(return_value="# Quiz content")

        run(config, sm)

        assert sm.state.run_count_b == 1
        assert len(sm.state.pending_quizzes) == 1
        assert sm.state.pending_quizzes[0].topic_key == "t1"
        mock_process.assert_called_once()

    @patch("app.feature_b.asyncio")
    @patch("app.feature_b.select_files")
    @patch("app.feature_b.scan_folders")
    @patch("app.feature_b.notify_processing")
    @patch("app.feature_b.process_unanswered")
    @patch("app.feature_b.get_system_prompt_b", return_value="sys")
    @patch("app.feature_b.build_file_list_with_metadata", return_value="")
    @patch("app.feature_b.build_file_contents", return_value="")
    @patch("app.feature_b.build_quiz_schedule_info", return_value="")
    @patch("app.feature_b.get_user_prompt_b", return_value=MagicMock(format=MagicMock(return_value="")))
    def test_skips_when_sdk_returns_empty(
        self, mock_user, mock_quiz, mock_contents, mock_list, mock_sys,
        mock_process, mock_notify, mock_scan, mock_select, mock_asyncio,
    ):
        config = _make_config()
        sm = _make_sm()
        mock_file = MagicMock()
        mock_scan.return_value = [mock_file]
        mock_selection = MagicMock()
        mock_selection.selected_files = [mock_file]
        mock_selection.is_discovery = False
        mock_select.return_value = mock_selection
        mock_asyncio.run = MagicMock(return_value="")

        run(config, sm)
        assert sm.state.run_count_b == 0

    @patch("app.feature_b.scan_folders")
    @patch("app.feature_b.notify_processing")
    @patch("app.feature_b.process_unanswered")
    def test_calls_process_unanswered(self, mock_process, mock_notify, mock_scan):
        config = _make_config()
        sm = _make_sm()
        mock_scan.return_value = [MagicMock()]
        with patch("app.feature_b.select_files") as mock_select:
            mock_selection = MagicMock()
            mock_selection.selected_files = []
            mock_select.return_value = mock_selection
            run(config, sm)
        mock_process.assert_called_once()
