"""scheduler モジュールのユニットテスト。

スケジュールトリガー生成、起動時キャッチアップ判定、
曜日パース等をテストする。
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from app.config import AppConfig, ScheduleConfig, ScheduleEntry
from app.scheduler import (
    Scheduler,
    _parse_day_of_week_set,
    _should_catchup,
)


# ────────────────────────────────────────────
# _parse_day_of_week_set
# ────────────────────────────────────────────


class TestParseDayOfWeekSet:
    """曜日文字列 → 数値集合の変換テスト。"""

    def test_comma_separated(self):
        result = _parse_day_of_week_set("mon,wed,fri")
        assert result == {0, 2, 4}

    def test_range(self):
        result = _parse_day_of_week_set("mon-fri")
        assert result == {0, 1, 2, 3, 4}

    def test_full_week(self):
        result = _parse_day_of_week_set("mon-sun")
        assert result == {0, 1, 2, 3, 4, 5, 6}

    def test_mixed_range_and_single(self):
        result = _parse_day_of_week_set("mon-wed,fri")
        assert result == {0, 1, 2, 4}

    def test_numeric_format(self):
        result = _parse_day_of_week_set("0,2,4")
        assert result == {0, 2, 4}

    def test_wrap_around_range(self):
        """fri-mon は {4, 5, 6, 0} を返す。"""
        result = _parse_day_of_week_set("fri-mon")
        assert result == {0, 4, 5, 6}

    def test_single_day(self):
        result = _parse_day_of_week_set("tue")
        assert result == {1}

    def test_empty_or_invalid(self):
        result = _parse_day_of_week_set("invalid")
        assert result == set()


# ────────────────────────────────────────────
# _should_catchup
# ────────────────────────────────────────────


class TestShouldCatchup:
    """起動時キャッチアップ判定のテスト。"""

    def test_should_catchup_missed_today(self):
        """今日のスケジュール時刻を過ぎていて未実行 → True。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")]
        # 月曜 (weekday=0)、現在 10:30
        now = datetime(2026, 3, 2, 10, 30, 0)  # 月曜
        assert _should_catchup(entries, 0, now, "") is True

    def test_no_catchup_already_ran_today(self):
        """今日すでに実行済み → False。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")]
        now = datetime(2026, 3, 2, 10, 30, 0)
        last_run = "2026-03-02T09:05:00"
        assert _should_catchup(entries, 0, now, last_run) is False

    def test_no_catchup_before_scheduled_time(self):
        """スケジュール時刻がまだ来ていない → False。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="11", minute="0")]
        now = datetime(2026, 3, 2, 9, 0, 0)
        assert _should_catchup(entries, 0, now, "") is False

    def test_no_catchup_wrong_day(self):
        """今日がスケジュール対象曜日でない → False。"""
        entries = [ScheduleEntry(day_of_week="mon,wed,fri", hour="9", minute="0")]
        # 火曜 (weekday=1)
        now = datetime(2026, 3, 3, 10, 0, 0)  # 火曜
        assert _should_catchup(entries, 1, now, "") is False

    def test_no_catchup_grace_time_exceeded(self):
        """猶予時間（3時間）を超過 → False。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")]
        # 月曜 13:00 → 9:00 から 4 時間経過（猶予 3 時間超）
        now = datetime(2026, 3, 2, 13, 0, 0)
        assert _should_catchup(entries, 0, now, "") is False

    def test_catchup_within_grace_time(self):
        """猶予時間内（スケジュールから2時間後） → True。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")]
        # 月曜 11:00 → 9:00 から 2 時間経過（猶予 3 時間内）
        now = datetime(2026, 3, 2, 11, 0, 0)
        assert _should_catchup(entries, 0, now, "") is True

    def test_catchup_last_run_yesterday(self):
        """前日に実行済みだが今日は未実行 → True。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")]
        now = datetime(2026, 3, 3, 10, 0, 0)  # 火曜
        last_run = "2026-03-02T09:05:00"  # 前日
        assert _should_catchup(entries, 1, now, last_run) is True

    def test_multiple_entries_any_match(self):
        """複数エントリのうち1つが該当 → True。"""
        entries = [
            ScheduleEntry(day_of_week="mon-fri", hour="7", minute="0"),
            ScheduleEntry(day_of_week="mon-fri", hour="15", minute="0"),
        ]
        # 月曜 16:00 → hour=7 は猶予超過 (9h), hour=15 は猶予内 (1h)
        now = datetime(2026, 3, 2, 16, 0, 0)
        assert _should_catchup(entries, 0, now, "") is True

    def test_weekend_schedule(self):
        """土日スケジュールが土曜に動作する。"""
        entries = [ScheduleEntry(day_of_week="sat,sun", hour="10", minute="0")]
        now = datetime(2026, 3, 7, 11, 30, 0)  # 土曜
        assert _should_catchup(entries, 5, now, "") is True

    def test_minute_precision(self):
        """minute フィールドを考慮した判定。"""
        entries = [ScheduleEntry(day_of_week="mon-fri", hour="9", minute="30")]
        # 9:25 → スケジュール 9:30 はまだ来ていない → False
        now = datetime(2026, 3, 2, 9, 25, 0)
        assert _should_catchup(entries, 0, now, "") is False
        # 9:35 → スケジュール 9:30 から 5 分経過 → True
        now = datetime(2026, 3, 2, 9, 35, 0)
        assert _should_catchup(entries, 0, now, "") is True


# ────────────────────────────────────────────
# Scheduler._create_trigger
# ────────────────────────────────────────────


class TestCreateTrigger:
    """CronTrigger 生成のテスト。"""

    def test_trigger_includes_minute(self):
        """_create_trigger が minute=0 を含む CronTrigger を生成する。"""
        scheduler = Scheduler()
        entry = ScheduleEntry(day_of_week="mon-fri", hour="11", minute="0")
        trigger = scheduler._create_trigger(entry)
        # CronTrigger のフィールドを検証
        assert str(trigger.fields[5]) == "11"  # hour
        assert str(trigger.fields[6]) == "0"  # minute

    def test_trigger_custom_minute(self):
        """minute=30 が正しく反映される。"""
        scheduler = Scheduler()
        entry = ScheduleEntry(day_of_week="mon-fri", hour="9", minute="30")
        trigger = scheduler._create_trigger(entry)
        assert str(trigger.fields[6]) == "30"


# ────────────────────────────────────────────
# Scheduler.check_and_run_missed_jobs
# ────────────────────────────────────────────


class TestCheckAndRunMissedJobs:
    """起動時キャッチアップ実行のテスト。"""

    def test_schedules_catchup_when_missed(self):
        """スケジュール見逃し時に DateTrigger ジョブを追加する。"""
        scheduler = Scheduler()
        on_a = MagicMock()
        on_b = MagicMock()

        config = AppConfig(
            schedule=ScheduleConfig(
                feature_a=[ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")],
                feature_b=[ScheduleEntry(day_of_week="mon-fri", hour="15", minute="0")],
            )
        )

        # スケジューラを開始
        scheduler.start(config=config, on_job_a=on_a, on_job_b=on_b)

        try:
            # _should_catchup を直接モックして A のみキャッチアップ対象にする
            with patch("app.scheduler._should_catchup") as mock_catchup:
                mock_catchup.side_effect = lambda entries, wd, now, lr: (
                    entries == config.schedule.feature_a
                )

                scheduler.check_and_run_missed_jobs(
                    config=config,
                    last_run_a_at="",
                    last_run_b_at="",
                )

            # job_a_catchup が追加されているはず
            jobs = scheduler._scheduler.get_jobs()
            catchup_job_ids = [j.id for j in jobs if "catchup" in j.id]
            assert "job_a_catchup" in catchup_job_ids
            assert "job_b_catchup" not in catchup_job_ids
        finally:
            scheduler.stop()

    def test_no_catchup_when_already_ran(self):
        """今日すでに実行済みならキャッチアップしない。"""
        scheduler = Scheduler()
        on_a = MagicMock()
        on_b = MagicMock()

        config = AppConfig(
            schedule=ScheduleConfig(
                feature_a=[ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")],
                feature_b=[ScheduleEntry(day_of_week="mon-fri", hour="15", minute="0")],
            )
        )

        scheduler.start(config=config, on_job_a=on_a, on_job_b=on_b)

        try:
            # 両方ともキャッチアップ不要
            with patch("app.scheduler._should_catchup", return_value=False):
                scheduler.check_and_run_missed_jobs(
                    config=config,
                    last_run_a_at="2026-03-02T09:05:00",
                    last_run_b_at="",
                )

            jobs = scheduler._scheduler.get_jobs()
            catchup_ids = [j.id for j in jobs if "catchup" in j.id]
            assert "job_a_catchup" not in catchup_ids
            assert "job_b_catchup" not in catchup_ids
        finally:
            scheduler.stop()

    def test_both_features_catchup_with_delay(self):
        """A・B 両方キャッチアップ時は B に遅延を設ける。"""
        scheduler = Scheduler()
        on_a = MagicMock()
        on_b = MagicMock()

        config = AppConfig(
            schedule=ScheduleConfig(
                feature_a=[ScheduleEntry(day_of_week="mon-fri", hour="9", minute="0")],
                feature_b=[ScheduleEntry(day_of_week="mon-fri", hour="11", minute="0")],
            )
        )

        scheduler.start(config=config, on_job_a=on_a, on_job_b=on_b)

        try:
            with patch("app.scheduler._should_catchup", return_value=True):
                scheduler.check_and_run_missed_jobs(
                    config=config,
                    last_run_a_at="",
                    last_run_b_at="",
                )

            jobs = scheduler._scheduler.get_jobs()
            catchup_ids = [j.id for j in jobs if "catchup" in j.id]
            assert "job_a_catchup" in catchup_ids
            assert "job_b_catchup" in catchup_ids
        finally:
            scheduler.stop()
