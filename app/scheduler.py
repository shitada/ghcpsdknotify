"""APScheduler による定期実行制御モジュール。

CronTrigger で機能 A / 機能 B のジョブを独立登録し、
同時刻重複時の避譲ロジック（3 分遅延）を実装する。
手動実行とスケジュール更新もサポートする。
"""

from __future__ import annotations

import logging
import threading
import time
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

# スリープ復帰後にジョブを実行する猶予時間（15 時間）
# 朝9時のジョブが深夜0時までにスリープ復帰すれば実行される
_MISFIRE_GRACE_TIME = 54000

# ジョブ ID
_JOB_A_PREFIX = "job_a"
_JOB_B_PREFIX = "job_b"

# スリープ復帰監視の間隔（秒）
# Windows の WaitForSingleObjectEx はスリープ中の時間をカウントしないため、
# APScheduler の Event.wait() が長時間スリープ後に復帰しない問題を回避する。
# 30 秒ごとに壁時計の飛びを検査し、スリープ復帰を検知したら APScheduler を起床させる。
_WATCHDOG_INTERVAL = 30
_WATCHDOG_TOLERANCE = _WATCHDOG_INTERVAL * 3  # この秒数以上の空白でスリープ復帰と判定

# 曜日名 → weekday() の数値マッピング
_DAY_NAME_TO_NUM: dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
    "0": 0, "1": 1, "2": 2, "3": 3,
    "4": 4, "5": 5, "6": 6,
}


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
        # スリープ復帰監視
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._on_sleep_wake: Callable[[], None] | None = None

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
        self._start_watchdog()
        logger.info(
            "スケジューラを開始しました (タイムゾーン: %s, misfire猶予: %d秒)",
            self._local_tz,
            _MISFIRE_GRACE_TIME,
        )

    def stop(self) -> None:
        """スケジューラを停止する。"""
        if self._started:
            self._stop_watchdog()
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
            minute=entry.minute,
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

    # ─── スリープ復帰監視（ウォッチドッグ） ───

    def set_on_sleep_wake(self, callback: Callable[[], None]) -> None:
        """スリープ復帰検知時に呼ばれるコールバックを設定する。

        Args:
            callback: スリープ復帰時に呼ばれる関数。
        """
        self._on_sleep_wake = callback

    def _start_watchdog(self) -> None:
        """スリープ復帰監視スレッドを開始する。"""
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="sleep-wake-watchdog",
        )
        self._watchdog_thread.start()
        logger.debug("スリープ復帰監視を開始しました (間隔: %d秒)", _WATCHDOG_INTERVAL)

    def _stop_watchdog(self) -> None:
        """スリープ復帰監視スレッドを停止する。"""
        self._watchdog_stop.set()
        self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        """スリープ復帰監視のメインループ。

        30秒ごとに壁時計をチェックし、大きな飛び（= スリープ復帰）を
        検知したら APScheduler を強制起床させる。
        Windows の WaitForSingleObjectEx はスリープ中の時間をカウントしないため、
        APScheduler の Event.wait() が長時間タイムアウトの場合に復帰しない問題を回避する。
        """
        last_check = time.time()
        while not self._watchdog_stop.wait(timeout=_WATCHDOG_INTERVAL):
            now = time.time()
            elapsed = now - last_check
            if elapsed > _WATCHDOG_TOLERANCE:
                logger.info(
                    "スリープ復帰を検知しました (%.0f秒の空白)。"
                    "スケジューラを起床させます",
                    elapsed,
                )
                self._scheduler.wakeup()
                if self._on_sleep_wake:
                    try:
                        self._on_sleep_wake()
                    except Exception:
                        logger.exception("スリープ復帰コールバックでエラーが発生しました")
            last_check = now

    # ─── 起動時キャッチアップ ───

    def check_and_run_missed_jobs(
        self,
        config: AppConfig,
        last_run_a_at: str,
        last_run_b_at: str,
    ) -> None:
        """起動時に見逃されたジョブをチェックし、misfire 猶予内であれば即実行する。

        PC スリープやアプリ未起動でスケジュール時刻を逃した場合に、
        起動後に自動で実行するためのメソッド。

        Args:
            config: アプリケーション設定。
            last_run_a_at: 機能 A の最終実行日時（ISO 形式）。空文字は未実行。
            last_run_b_at: 機能 B の最終実行日時（ISO 形式）。空文字は未実行。
        """
        now = datetime.now()
        today = now.date()
        today_weekday = today.weekday()

        # 機能 A のキャッチアップ
        if self._on_job_a and _should_catchup(
            config.schedule.feature_a, today_weekday, now, last_run_a_at,
        ):
            logger.info(
                "起動時キャッチアップ: 機能 A のスケジュール時刻を逃しています。即時実行します"
            )
            self._scheduler.add_job(
                self._on_trigger_a,
                trigger=DateTrigger(run_date=now + timedelta(seconds=10)),
                id="job_a_catchup",
                replace_existing=True,
                name="機能A (起動時キャッチアップ)",
            )

        # 機能 B のキャッチアップ
        if self._on_job_b and _should_catchup(
            config.schedule.feature_b, today_weekday, now, last_run_b_at,
        ):
            # 機能 A のキャッチアップがある場合は 5 分遅延して重複を回避
            a_has_catchup = self._on_job_a and _should_catchup(
                config.schedule.feature_a, today_weekday, now, last_run_a_at,
            )
            delay = _DEFER_SECONDS + 10 if a_has_catchup else 10
            logger.info(
                "起動時キャッチアップ: 機能 B のスケジュール時刻を逃しています。%d秒後に実行します",
                delay,
            )
            self._scheduler.add_job(
                self._on_trigger_b,
                trigger=DateTrigger(run_date=now + timedelta(seconds=delay)),
                id="job_b_catchup",
                replace_existing=True,
                name="機能B (起動時キャッチアップ)",
            )


# ── キャッチアップ判定ヘルパー ──


def _parse_day_of_week_set(day_of_week: str) -> set[int]:
    """APScheduler 形式の day_of_week 文字列を weekday 数値の集合に変換する。

    "mon,tue,wed" → {0, 1, 2}
    "mon-fri" → {0, 1, 2, 3, 4}

    Args:
        day_of_week: APScheduler 形式の曜日指定文字列。

    Returns:
        weekday() 数値の集合。
    """
    result: set[int] = set()
    for part in day_of_week.split(","):
        part = part.strip().lower()
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = _DAY_NAME_TO_NUM.get(start_str.strip())
            end = _DAY_NAME_TO_NUM.get(end_str.strip())
            if start is not None and end is not None:
                if start <= end:
                    result.update(range(start, end + 1))
                else:
                    # 例: fri-mon → {4, 5, 6, 0}
                    result.update(range(start, 7))
                    result.update(range(0, end + 1))
        else:
            num = _DAY_NAME_TO_NUM.get(part)
            if num is not None:
                result.add(num)
    return result


def _should_catchup(
    schedule_entries: list[ScheduleEntry],
    today_weekday: int,
    now: datetime,
    last_run_at: str,
) -> bool:
    """スケジュールエントリが今日見逃されたかを判定する。

    Args:
        schedule_entries: スケジュールエントリのリスト。
        today_weekday: 今日の曜日番号（0=月〜6=日）。
        now: 現在日時。
        last_run_at: 最終実行日時（ISO 形式、空文字＝未実行）。

    Returns:
        True ならキャッチアップ実行が必要。
    """
    today = now.date()

    # 今日すでに正常に実行済みならスキップ
    if last_run_at:
        try:
            last_run = datetime.fromisoformat(last_run_at)
            if last_run.date() == today:
                return False
        except ValueError:
            pass

    # いずれかのスケジュールエントリで「今日該当 & 時刻超過」ならTrue
    # 起動時キャッチアップは同一日であれば時間制限なし（APScheduler misfire とは独立）
    for entry in schedule_entries:
        days = _parse_day_of_week_set(entry.day_of_week)
        if today_weekday not in days:
            continue

        scheduled_hour = int(entry.hour)
        scheduled_minute = int(entry.minute)
        scheduled_dt = now.replace(
            hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0,
        )

        if now < scheduled_dt:
            continue  # まだ時刻が来ていない

        elapsed = (now - scheduled_dt).total_seconds()
        logger.debug(
            "キャッチアップ対象: day_of_week=%s, hour=%s, minute=%s "
            "(経過 %d 秒)",
            entry.day_of_week, entry.hour, entry.minute,
            int(elapsed),
        )
        return True

    return False
