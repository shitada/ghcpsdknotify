"""APScheduler による定期実行制御モジュール。

CronTrigger で機能 A / 機能 B のジョブを独立登録し、
同時刻重複時の避譲ロジック（3 分遅延）を実装する。
手動実行とスケジュール更新もサポートする。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from tzlocal import get_localzone

from app.config import AppConfig, ScheduleEntry

logger = logging.getLogger(__name__)

# 同時実行避譲の遅延秒数（3 分）
_DEFER_SECONDS = 180

# スリープ復帰後にジョブを実行する猶予時間（3 時間）
_MISFIRE_GRACE_TIME = 10800

# ジョブ ID
_JOB_A_PREFIX = "job_a"
_JOB_B_PREFIX = "job_b"


class Scheduler:
    """APScheduler ベースのジョブスケジューラ。

    機能 A・B のジョブを CronTrigger で登録し、
    スケジュール管理・手動実行・同時刻重複の避譲を行う。
    """

    def __init__(self) -> None:
        """Scheduler を初期化する。"""
        self._local_tz = get_localzone()
        self._scheduler = BackgroundScheduler(
            timezone=self._local_tz,
            job_defaults={
                "misfire_grace_time": _MISFIRE_GRACE_TIME,
                "coalesce": True,
            },
        )
        self._lock_a = threading.Lock()
        self._lock_b = threading.Lock()
        self._running_a = False
        self._running_b = False
        self._on_job_a: Callable[[], None] | None = None
        self._on_job_b: Callable[[], None] | None = None
        self._started = False

    def start(
        self,
        config: AppConfig,
        on_job_a: Callable[[], None],
        on_job_b: Callable[[], None],
    ) -> None:
        """スケジューラを開始する。

        config のスケジュール設定に基づき、機能 A・B のジョブを登録して開始する。

        Args:
            config: アプリケーション設定。
            on_job_a: 機能 A のジョブコールバック。
            on_job_b: 機能 B のジョブコールバック。
        """
        self._on_job_a = on_job_a
        self._on_job_b = on_job_b

        # スケジュールジョブの登録
        self._register_jobs(config)

        self._scheduler.start()
        self._started = True
        logger.info(
            "スケジューラを開始しました (タイムゾーン: %s, misfire猶予: %d秒)",
            self._local_tz,
            _MISFIRE_GRACE_TIME,
        )

    def stop(self) -> None:
        """スケジューラを停止する。"""
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("スケジューラを停止しました")

    def update_schedule(self, config: AppConfig) -> None:
        """スケジュール設定をリロードする。

        既存のジョブをすべて削除し、新しい設定で再登録する。

        Args:
            config: 更新後のアプリケーション設定。
        """
        # 既存ジョブの削除
        self._remove_all_jobs()

        # 新しいジョブの登録
        self._register_jobs(config)
        logger.info("スケジュールを更新しました")

    def run_manual(
        self,
        features: list[str],
        on_job_a: Callable[[], None] | None = None,
        on_job_b: Callable[[], None] | None = None,
    ) -> None:
        """指定機能を即座に手動実行する。

        両方の場合は A → B の順で順次実行する。

        Args:
            features: 実行する機能のリスト（"a", "b"）。
            on_job_a: 機能 A のコールバック（None の場合は登録済みを使用）。
            on_job_b: 機能 B のコールバック（None の場合は登録済みを使用）。
        """
        job_a = on_job_a or self._on_job_a
        job_b = on_job_b or self._on_job_b

        if "a" in features and job_a:
            logger.info("手動実行: 機能 A を開始")
            self._execute_job_a_wrapper(job_a)

        if "b" in features and job_b:
            logger.info("手動実行: 機能 B を開始")
            self._execute_job_b_wrapper(job_b)

    def _register_jobs(self, config: AppConfig) -> None:
        """config のスケジュール設定に基づきジョブを登録する。"""
        for i, entry in enumerate(config.schedule.feature_a):
            job_id = f"{_JOB_A_PREFIX}_{i}"
            trigger = self._create_trigger(entry)
            self._scheduler.add_job(
                self._on_trigger_a,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                name=f"機能A (schedule {i})",
            )
            logger.info(
                "機能A ジョブ登録: %s (day_of_week=%s, hour=%s)",
                job_id,
                entry.day_of_week,
                entry.hour,
            )

        for i, entry in enumerate(config.schedule.feature_b):
            job_id = f"{_JOB_B_PREFIX}_{i}"
            trigger = self._create_trigger(entry)
            self._scheduler.add_job(
                self._on_trigger_b,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                name=f"機能B (schedule {i})",
            )
            logger.info(
                "機能B ジョブ登録: %s (day_of_week=%s, hour=%s)",
                job_id,
                entry.day_of_week,
                entry.hour,
            )

    def _remove_all_jobs(self) -> None:
        """登録済みの A/B ジョブをすべて削除する。"""
        jobs = self._scheduler.get_jobs()
        for job in jobs:
            if job.id.startswith(_JOB_A_PREFIX) or job.id.startswith(_JOB_B_PREFIX):
                self._scheduler.remove_job(job.id)
                logger.debug("ジョブ削除: %s", job.id)

    def _create_trigger(self, entry: ScheduleEntry) -> CronTrigger:
        """ScheduleEntry から CronTrigger を生成する。

        Args:
            entry: スケジュールエントリ。

        Returns:
            CronTrigger インスタンス。
        """
        return CronTrigger(
            day_of_week=entry.day_of_week,
            hour=entry.hour,
            timezone=self._local_tz,
        )

    def _on_trigger_a(self) -> None:
        """機能 A のスケジュールトリガーハンドラ。

        機能 B が実行中の場合は 3 分後にリスケジュールする。
        """
        if self._running_b:
            defer_time = datetime.now() + timedelta(seconds=_DEFER_SECONDS)
            logger.info(
                "機能 B が実行中のため、機能 A を %s に遅延実行します",
                defer_time.strftime("%H:%M:%S"),
            )
            self._scheduler.add_job(
                self._on_trigger_a,
                trigger=DateTrigger(run_date=defer_time),
                id="job_a_deferred",
                replace_existing=True,
                name="機能A (遅延実行)",
            )
            return

        if self._on_job_a:
            self._execute_job_a_wrapper(self._on_job_a)

    def _on_trigger_b(self) -> None:
        """機能 B のスケジュールトリガーハンドラ。

        機能 A が実行中の場合は 3 分後にリスケジュールする。
        """
        if self._running_a:
            defer_time = datetime.now() + timedelta(seconds=_DEFER_SECONDS)
            logger.info(
                "機能 A が実行中のため、機能 B を %s に遅延実行します",
                defer_time.strftime("%H:%M:%S"),
            )
            self._scheduler.add_job(
                self._on_trigger_b,
                trigger=DateTrigger(run_date=defer_time),
                id="job_b_deferred",
                replace_existing=True,
                name="機能B (遅延実行)",
            )
            return

        if self._on_job_b:
            self._execute_job_b_wrapper(self._on_job_b)

    def _execute_job_a_wrapper(self, callback: Callable[[], None]) -> None:
        """機能 A のジョブを排他制御付きで実行する。"""
        with self._lock_a:
            self._running_a = True
            try:
                callback()
            except Exception:
                logger.exception("機能 A の実行中にエラーが発生しました")
            finally:
                self._running_a = False

    def _execute_job_b_wrapper(self, callback: Callable[[], None]) -> None:
        """機能 B のジョブを排他制御付きで実行する。"""
        with self._lock_b:
            self._running_b = True
            try:
                callback()
            except Exception:
                logger.exception("機能 B の実行中にエラーが発生しました")
            finally:
                self._running_b = False
