"""機能 D（ミーティング フォローアップ ダイジェスト）のジョブ実行モジュール。

WorkIQ で前営業日のフォローアップフラグ付きミーティングを抽出 →
Copilot SDK 呼び出し → MD 出力 → 通知 の一連のフローを実行する。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Callable

from app.config import AppConfig
from app.copilot_client import CopilotClientWrapper
from app.i18n import get_language
from app.notifier import (
    notify_briefing,
    notify_error,
    notify_processing,
    notify_workiq_setup,
    open_workiq_setup_dialog,
)
from app.output_writer import get_output_folder, write_briefing
from app.prompts import get_system_prompt_d, get_user_prompt_d
from app.state_manager import StateManager
from app.viewer import open_viewer

logger = logging.getLogger(__name__)

# 曜日名（日本語 / 英語）。datetime.weekday(): 0=月 ... 6=日。
_WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]
_WEEKDAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _most_recent_working_day(today: date) -> date:
    """today の直近の稼働日（前営業日）を返す。

    前日を起点に、土日をスキップして直近の平日（月〜金）を返す。
    月曜に実行した場合は金曜を返す。（祝日は考慮しない。）
    """
    d = today - timedelta(days=1)
    while d.weekday() >= 5:  # 5=土, 6=日
        d -= timedelta(days=1)
    return d


def _format_weekday(d: date) -> str:
    """言語に応じた曜日名を返す。"""
    if get_language() == "en":
        return _WEEKDAY_EN[d.weekday()]
    return _WEEKDAY_JA[d.weekday()]


async def _generate_report(
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """機能 D のレポートを非同期で生成する。"""
    async with CopilotClientWrapper(config.copilot_sdk) as client:
        return await client.generate_briefing_d(
            system_prompt, user_prompt, config.workiq_mcp
        )


def run(
    config: AppConfig,
    state_manager: StateManager,
    *,
    on_tray_processing: Callable[[], None] | None = None,
    on_tray_normal: Callable[[], None] | None = None,
) -> None:
    """機能 D のメイン処理を実行する。"""
    sm = state_manager

    if not config.feature_d.enabled:
        logger.debug("機能 D が無効のためスキップ")
        return

    # WorkIQ MCP が必須。未設定ならセットアップ通知を出してスキップする。
    if not config.workiq_mcp.enabled:
        logger.info("機能 D: WorkIQ MCP が未設定のためスキップします")
        if not config.workiq_mcp.suppress_setup_prompt:
            notify_workiq_setup(
                on_click=lambda: open_workiq_setup_dialog(config),
                notification_config=config.notification,
            )
        return

    logger.info("=== 機能 D 実行開始 ===")
    if on_tray_processing:
        on_tray_processing()
    notify_processing("d", notification_config=config.notification)

    try:
        # 対象日（前営業日）を算出
        target = _most_recent_working_day(date.today())
        target_date = target.strftime("%Y-%m-%d")
        target_weekday = _format_weekday(target)
        logger.info("機能 D 対象日: %s (%s)", target_date, target_weekday)

        # プロンプト構築
        system_prompt = get_system_prompt_d()
        user_prompt = get_user_prompt_d().format(
            current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
            target_date=target_date,
            target_weekday=target_weekday,
        )

        # Copilot SDK 呼び出し（WorkIQ MCP 経由）
        report_text = asyncio.run(
            _generate_report(config, system_prompt, user_prompt)
        )
        if not report_text:
            logger.warning("機能 D レポート生成結果が空です")
            return

        # MD 出力
        output_folder = get_output_folder(
            config.input_folders, config.output_folder_name, sm.state.output_folder_path
        )
        sm.set_output_folder_path(output_folder)
        briefing_file = write_briefing(report_text, "d", output_folder)
        logger.info("機能 D レポート出力: %s", briefing_file)

        # 状態更新
        sm.increment_run_count("d")
        sm.update_last_run()
        sm.update_last_run_feature("d")
        sm.save()

        # 通知
        if config.notification.enabled:
            def _launch_viewer(bf: str = briefing_file) -> None:
                try:
                    open_viewer(bf)
                except Exception:
                    logger.exception("ビューア起動に失敗しました: %s", bf)

            notify_briefing(
                briefing_file, "d",
                on_click=lambda: threading.Thread(target=_launch_viewer, daemon=True).start(),
                notification_config=config.notification,
            )

        logger.info("機能 D 完了: %s", briefing_file)

    except Exception as exc:
        logger.exception("機能 D の実行中にエラーが発生しました")
        notify_error("d", str(exc), notification_config=config.notification)
    finally:
        if on_tray_normal:
            on_tray_normal()
