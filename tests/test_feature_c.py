"""feature_c モジュールのユニットテスト。"""

from unittest.mock import MagicMock, patch

from app.config import AppConfig, MonitoredPage, NotificationConfig, PageMonitorConfig
from app.feature_c import run
from app.state_manager import AppState, StateManager


def _make_sm() -> StateManager:
    sm = StateManager.__new__(StateManager)
    sm._state = AppState()
    sm._path = None  # type: ignore[assignment]
    return sm


def _make_config(pages=None, enabled=True, **kwargs) -> AppConfig:
    if pages is None:
        pages = [MonitoredPage(url="https://example.com", name="Test", mode="links", link_selector="a", analyzed=True, enabled=True)]
    defaults = dict(
        input_folders=["/test"],
        notification=NotificationConfig(enabled=False),
        page_monitor=PageMonitorConfig(enabled=enabled, pages=pages),
    )
    defaults.update(kwargs)
    return AppConfig(**defaults)


class TestRunFeatureC:
    def test_skips_when_disabled(self):
        config = _make_config(enabled=False)
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_c == 0

    def test_skips_when_no_pages(self):
        config = _make_config(pages=[])
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_c == 0

    def test_skips_when_all_pages_disabled(self):
        page = MonitoredPage(url="https://example.com", enabled=False, analyzed=True)
        config = _make_config(pages=[page])
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_c == 0

    @patch("app.feature_c.config_module")
    @patch("app.feature_c.asyncio")
    @patch("app.feature_c.notify_processing")
    @patch("app.feature_c.fetch_page")
    @patch("app.feature_c.detect_changes")
    @patch("app.feature_c.extract_links", return_value=[])
    @patch("app.feature_c.compute_content_hash", return_value="h")
    def test_auto_analyzes_unanalyzed_pages(
        self, mock_hash, mock_links, mock_detect, mock_fetch,
        mock_notify, mock_asyncio, mock_config_mod,
    ):
        page = MonitoredPage(url="https://example.com", enabled=True, analyzed=False)
        analyzed = MonitoredPage(
            url="https://example.com", name="Analyzed", mode="links",
            link_selector="a", analyzed=True, enabled=True,
        )

        # asyncio.run returns analyzed page for analyze_page, then html for fetch_page
        call_count = [0]
        def fake_asyncio_run(coro):
            call_count[0] += 1
            if call_count[0] == 1:
                return analyzed  # analyze_page result
            return "<html><body></body></html>"  # fetch_page result
        mock_asyncio.run = fake_asyncio_run

        config = _make_config(pages=[page])
        sm = _make_sm()

        mock_result = MagicMock()
        mock_result.has_changes = False
        mock_detect.return_value = mock_result

        run(config, sm)

        mock_config_mod.save.assert_called_once()
        assert config.page_monitor.pages[0].analyzed is True

    @patch("app.feature_c.notify_processing")
    @patch("app.feature_c.fetch_page", return_value="<html><body></body></html>")
    @patch("app.feature_c.detect_changes")
    @patch("app.feature_c.extract_links", return_value=[])
    @patch("app.feature_c.compute_content_hash", return_value="hash1")
    def test_no_changes_updates_state_only(
        self, mock_hash, mock_links, mock_detect, mock_fetch, mock_notify,
    ):
        config = _make_config()
        sm = _make_sm()
        mock_result = MagicMock()
        mock_result.has_changes = False
        mock_detect.return_value = mock_result

        with patch("app.feature_c.asyncio") as mock_asyncio:
            mock_asyncio.run = lambda coro: coro
            run(config, sm)

        assert sm.state.run_count_c == 1
        assert sm.state.last_run_c_at != ""

    @patch("app.feature_c.notify_briefing")
    @patch("app.feature_c.write_briefing", return_value="/out/monitor.md")
    @patch("app.feature_c.get_output_folder", return_value="/out")
    @patch("app.feature_c.get_system_prompt_c", return_value="system")
    @patch("app.feature_c.build_report_prompt", return_value="report prompt")
    @patch("app.feature_c.notify_processing")
    @patch("app.feature_c.fetch_page", return_value="<html><body><a href='/new'>New</a></body></html>")
    @patch("app.feature_c.detect_changes")
    @patch("app.feature_c.extract_links", return_value=[{"url": "https://example.com/new", "text": "New"}])
    @patch("app.feature_c.compute_content_hash", return_value="hash1")
    def test_changes_detected_generates_report(
        self, mock_hash, mock_links, mock_detect, mock_fetch, mock_notify,
        mock_report, mock_sys, mock_get_output, mock_write, mock_notify_brief,
    ):
        config = _make_config()
        sm = _make_sm()
        mock_result = MagicMock()
        mock_result.has_changes = True
        mock_result.new_links = [{"url": "https://example.com/new", "text": "New"}]
        mock_result.content_changed = False
        mock_detect.return_value = mock_result

        with patch("app.feature_c.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(return_value="# Report")
            run(config, sm)

        assert sm.state.run_count_c == 1
        mock_write.assert_called_once()
