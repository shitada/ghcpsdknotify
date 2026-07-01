"""feature_d モジュールのユニットテスト。"""

from datetime import date
from unittest.mock import MagicMock, patch

from app.config import AppConfig, FeatureDConfig, NotificationConfig, WorkIQMcpConfig
from app.feature_d import _most_recent_working_day, run
from app.state_manager import AppState, StateManager


def _make_sm() -> StateManager:
    sm = StateManager.__new__(StateManager)
    sm._state = AppState()
    sm._path = None  # type: ignore[assignment]
    return sm


def _make_config(feature_d_enabled=True, workiq_enabled=True, **kwargs) -> AppConfig:
    defaults = dict(
        input_folders=["/test"],
        notification=NotificationConfig(enabled=True),
        workiq_mcp=WorkIQMcpConfig(enabled=workiq_enabled),
        feature_d=FeatureDConfig(enabled=feature_d_enabled),
    )
    defaults.update(kwargs)
    return AppConfig(**defaults)


# ────────────────────────────────────────────
# _most_recent_working_day（前営業日ロジック）
# ────────────────────────────────────────────
# 2026-01-01 は木曜日。2026-01-05 は月曜日。


class TestMostRecentWorkingDay:
    def test_monday_returns_previous_friday(self):
        # 月曜 2026-01-05 → 金曜 2026-01-02
        assert _most_recent_working_day(date(2026, 1, 5)) == date(2026, 1, 2)

    def test_tuesday_returns_monday(self):
        # 火曜 2026-01-06 → 月曜 2026-01-05
        assert _most_recent_working_day(date(2026, 1, 6)) == date(2026, 1, 5)

    def test_friday_returns_thursday(self):
        # 金曜 2026-01-09 → 木曜 2026-01-08
        assert _most_recent_working_day(date(2026, 1, 9)) == date(2026, 1, 8)

    def test_saturday_returns_friday(self):
        # 土曜 2026-01-10 → 金曜 2026-01-09
        assert _most_recent_working_day(date(2026, 1, 10)) == date(2026, 1, 9)

    def test_sunday_returns_friday(self):
        # 日曜 2026-01-11 → 金曜 2026-01-09
        assert _most_recent_working_day(date(2026, 1, 11)) == date(2026, 1, 9)

    def test_result_is_always_weekday(self):
        for day in range(1, 15):
            result = _most_recent_working_day(date(2026, 1, day))
            assert result.weekday() < 5


# ────────────────────────────────────────────
# run（スキップ条件）
# ────────────────────────────────────────────


class TestRunFeatureDSkip:
    def test_skips_when_feature_disabled(self):
        config = _make_config(feature_d_enabled=False)
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_d == 0

    @patch("app.feature_d.notify_workiq_setup")
    def test_skips_and_notifies_when_workiq_disabled(self, mock_setup):
        config = _make_config(feature_d_enabled=True, workiq_enabled=False)
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_d == 0
        mock_setup.assert_called_once()

    @patch("app.feature_d.notify_workiq_setup")
    def test_workiq_disabled_respects_suppress_prompt(self, mock_setup):
        config = _make_config(
            feature_d_enabled=True,
            workiq_enabled=False,
            workiq_mcp=WorkIQMcpConfig(enabled=False, suppress_setup_prompt=True),
        )
        sm = _make_sm()
        run(config, sm)
        assert sm.state.run_count_d == 0
        mock_setup.assert_not_called()


# ────────────────────────────────────────────
# run（正常系）
# ────────────────────────────────────────────


class TestRunFeatureDHappyPath:
    @patch("app.feature_d.notify_briefing")
    @patch("app.feature_d.write_briefing", return_value="/out/briefing_meetings.md")
    @patch("app.feature_d.get_output_folder", return_value="/out")
    @patch("app.feature_d.get_user_prompt_d", return_value="{current_datetime} {target_date} {target_weekday}")
    @patch("app.feature_d.get_system_prompt_d", return_value="system")
    @patch("app.feature_d.notify_processing")
    def test_generates_report_and_updates_state(
        self, mock_processing, mock_sys, mock_user, mock_get_output,
        mock_write, mock_notify_brief, tmp_path,
    ):
        config = _make_config()
        sm = _make_sm()
        sm._path = tmp_path / "state.json"  # type: ignore[assignment]

        with patch("app.feature_d._generate_report"), \
                patch("app.feature_d.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(return_value="# Meeting Digest")
            run(config, sm)

        assert sm.state.run_count_d == 1
        assert sm.state.last_run_d_at != ""
        mock_write.assert_called_once()
        # write_briefing の第2引数は feature="d"
        assert mock_write.call_args.args[1] == "d"
        mock_notify_brief.assert_called_once()

    @patch("app.feature_d.notify_error")
    @patch("app.feature_d.get_user_prompt_d", return_value="{current_datetime} {target_date} {target_weekday}")
    @patch("app.feature_d.get_system_prompt_d", return_value="system")
    @patch("app.feature_d.notify_processing")
    def test_empty_report_does_not_increment(
        self, mock_processing, mock_sys, mock_user, mock_error,
    ):
        config = _make_config()
        sm = _make_sm()

        with patch("app.feature_d._generate_report"), \
                patch("app.feature_d.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(return_value="")
            run(config, sm)

        assert sm.state.run_count_d == 0

    @patch("app.feature_d.notify_error")
    @patch("app.feature_d.get_user_prompt_d", return_value="{current_datetime} {target_date} {target_weekday}")
    @patch("app.feature_d.get_system_prompt_d", return_value="system")
    @patch("app.feature_d.notify_processing")
    def test_exception_triggers_error_notification(
        self, mock_processing, mock_sys, mock_user, mock_error,
    ):
        config = _make_config()
        sm = _make_sm()

        with patch("app.feature_d._generate_report"), \
                patch("app.feature_d.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(side_effect=RuntimeError("boom"))
            run(config, sm)

        assert sm.state.run_count_d == 0
        mock_error.assert_called_once()
