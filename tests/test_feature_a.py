"""feature_a モジュールのユニットテスト。"""

from unittest.mock import MagicMock, patch, AsyncMock

from app.config import AppConfig, NotificationConfig, WorkIQMcpConfig
from app.feature_a import _check_workiq_setup, run
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


class TestCheckWorkiqSetup:
    def test_skip_when_enabled(self):
        config = _make_config(workiq_mcp=WorkIQMcpConfig(enabled=True))
        with patch("app.feature_a.notify_workiq_setup") as mock_notify:
            _check_workiq_setup(config, run_count=1)
            mock_notify.assert_not_called()

    def test_skip_when_suppressed(self):
        config = _make_config(workiq_mcp=WorkIQMcpConfig(enabled=False, suppress_setup_prompt=True))
        with patch("app.feature_a.notify_workiq_setup") as mock_notify:
            _check_workiq_setup(config, run_count=1)
            mock_notify.assert_not_called()

    def test_notifies_on_first_run(self):
        config = _make_config(workiq_mcp=WorkIQMcpConfig(enabled=False))
        with patch("app.feature_a.notify_workiq_setup") as mock_notify:
            _check_workiq_setup(config, run_count=1)
            mock_notify.assert_called_once()

    def test_notifies_every_5th_run(self):
        config = _make_config(workiq_mcp=WorkIQMcpConfig(enabled=False))
        with patch("app.feature_a.notify_workiq_setup") as mock_notify:
            _check_workiq_setup(config, run_count=5)
            mock_notify.assert_called_once()

    def test_no_notify_on_2nd_run(self):
        config = _make_config(workiq_mcp=WorkIQMcpConfig(enabled=False))
        with patch("app.feature_a.notify_workiq_setup") as mock_notify:
            _check_workiq_setup(config, run_count=2)
            mock_notify.assert_not_called()


class TestRunFeatureA:
    @patch("app.feature_a.scan_folders", return_value=[])
    @patch("app.feature_a.notify_processing")
    def test_skips_when_no_scanned_files(self, mock_notify, mock_scan):
        config = _make_config()
        sm = _make_sm()
        run(config, sm)
        mock_scan.assert_called_once()
        assert sm.state.run_count_a == 0  # not incremented

    def test_skips_when_input_folders_empty(self):
        config = _make_config(input_folders=[])
        sm = _make_sm()
        with patch("app.feature_a.notify_processing"):
            run(config, sm)
        assert sm.state.run_count_a == 0

    @patch("app.feature_a.notify_briefing")
    @patch("app.feature_a.write_briefing", return_value="/out/briefing.md")
    @patch("app.feature_a.get_output_folder", return_value="/out")
    @patch("app.feature_a.asyncio")
    @patch("app.feature_a.get_user_prompt_a", return_value=MagicMock(format=MagicMock(return_value="user prompt")))
    @patch("app.feature_a.build_file_contents", return_value="contents")
    @patch("app.feature_a.build_file_list_with_metadata", return_value="file list")
    @patch("app.feature_a.get_system_prompt_a", return_value="system prompt")
    @patch("app.feature_a.select_files")
    @patch("app.feature_a.scan_folders")
    @patch("app.feature_a.notify_processing")
    @patch("app.feature_a._check_workiq_setup")
    @patch("app.feature_a.get_random_picked_paths", return_value=[])
    def test_full_flow_increments_state(
        self, mock_random, mock_workiq, mock_notify_proc, mock_scan,
        mock_select, mock_sys_prompt, mock_file_list, mock_file_contents,
        mock_user_prompt, mock_asyncio, mock_get_output, mock_write,
        mock_notify_briefing,
    ):
        config = _make_config()
        sm = _make_sm()
        # Setup mocks
        mock_file = MagicMock()
        mock_file.metadata.modified_at = None
        mock_file.metadata.relative_path = "test.md"
        mock_scan.return_value = [mock_file]
        mock_selection = MagicMock()
        mock_selection.selected_files = [mock_file]
        mock_selection.is_discovery = False
        mock_select.return_value = mock_selection
        mock_asyncio.run = MagicMock(return_value="# Briefing content")

        run(config, sm)

        assert sm.state.run_count_a == 1
        assert sm.state.last_run_a_at != ""
        mock_write.assert_called_once()

    @patch("app.feature_a.asyncio")
    @patch("app.feature_a.select_files")
    @patch("app.feature_a.scan_folders")
    @patch("app.feature_a.notify_processing")
    @patch("app.feature_a.get_system_prompt_a", return_value="sys")
    @patch("app.feature_a.build_file_list_with_metadata", return_value="")
    @patch("app.feature_a.build_file_contents", return_value="")
    @patch("app.feature_a.get_user_prompt_a", return_value=MagicMock(format=MagicMock(return_value="")))
    def test_skips_when_sdk_returns_empty(
        self, mock_user, mock_contents, mock_list, mock_sys,
        mock_notify, mock_scan, mock_select, mock_asyncio,
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
        assert sm.state.run_count_a == 0  # not incremented on empty result
