"""機能 A（最新情報の取得）のジョブ実行モジュール。

フォルダ走査 → ファイル選定 → プロンプト構築 → Copilot SDK 呼び出し →
MD 出力 → 通知 の一連のフローを実行する。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Callable

from app import config as config_module
from app.config import AppConfig
from app.copilot_client import CopilotClientWrapper
from app.file_selector import get_random_picked_paths, select_files
from app.folder_scanner import scan_folders
from app.notifier import (
    notify_briefing,
    notify_error,
    notify_processing,
    notify_workiq_setup,
    open_workiq_setup_dialog,
)
from app.output_writer import get_output_folder, write_briefing
from app.prompts import (
    build_file_contents,
    build_file_list_with_metadata,
    get_discovery_appendix,
    get_system_prompt_a,
    get_user_prompt_a,
)
from app.state_manager import StateManager
from app.viewer import open_viewer

logger = logging.getLogger(__name__)


async def _generate_briefing(
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """機能 A のブリーフィングを非同期で生成する。"""
    async with CopilotClientWrapper(config.copilot_sdk) as client:
        return await client.generate_briefing_a(
            system_prompt, user_prompt, config.workiq_mcp
        )


def _check_workiq_setup(
    config: AppConfig,
    run_count: int,
    app_config_ref: AppConfig | None = None,
) -> None:
    """WorkIQ MCP が未設定の場合に通知を行う。"""
    if config.workiq_mcp.enabled:
        return
    if config.workiq_mcp.suppress_setup_prompt:
        return
    if run_count == 1 or run_count % 5 == 0:
        notify_workiq_setup(
            on_click=lambda: open_workiq_setup_dialog(app_config_ref or config),
            notification_config=config.notification,
        )


def run(
    config: AppConfig,
    state_manager: StateManager,
    *,
    on_tray_processing: Callable[[], None] | None = None,
    on_tray_normal: Callable[[], None] | None = None,
) -> None:
    """機能 A のメイン処理を実行する。"""
    sm = state_manager

    logger.info("=== 機能 A 実行開始 ===")
    if on_tray_processing:
        on_tray_processing()
    notify_processing("a", notification_config=config.notification)

    try:
        if not config.input_folders:
            logger.warning("input_folders が空です。機能 A をスキップします")
            return

        scanned_files = scan_folders(config.input_folders, config.target_extensions)
        if not scanned_files:
            logger.warning("走査結果が0件です。機能 A をスキップします")
            return

        run_count = sm.state.run_count_a + 1
        selection = select_files(
            scanned_files,
            run_count=run_count,
            discovery_interval=config.file_selection.discovery_interval,
            max_files=config.file_selection.max_files,
            random_pick_history=sm.state.random_pick_history,
        )
        if not selection.selected_files:
            logger.warning("選定ファイルが0件です。機能 A をスキップします")
            return

        # プロンプト構築
        system_prompt = get_system_prompt_a(config)
        if selection.is_discovery:
            system_prompt += get_discovery_appendix()

        file_list = build_file_list_with_metadata(selection.selected_files)
        file_contents = build_file_contents(
            selection.selected_files, config.copilot_sdk.max_context_tokens
        )
        user_prompt = get_user_prompt_a().format(
            current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
            input_folders=", ".join(config.input_folders),
            file_list_with_metadata=file_list,
            file_contents=file_contents,
        )

        # Copilot SDK 呼び出し
        briefing_text = asyncio.run(
            _generate_briefing(config, system_prompt, user_prompt)
        )
        if not briefing_text:
            logger.warning("ブリーフィング生成結果が空です")
            return

        # MD 出力
        output_folder = get_output_folder(
            config.input_folders, config.output_folder_name, sm.state.output_folder_path
        )
        sm.set_output_folder_path(output_folder)
        briefing_file = write_briefing(briefing_text, "a", output_folder)
        logger.info("機能 A ブリーフィング出力: %s", briefing_file)

        # WorkIQ 未設定検知
        _check_workiq_setup(config, run_count)

        # 状態更新
        sm.increment_run_count("a")
        sm.update_last_run()
        sm.update_last_run_feature("a")
        random_picked = get_random_picked_paths(selection)
        if random_picked:
            sm.update_random_pick_history(random_picked)
        sm.save()

        # 通知
        if config.notification.enabled:
            def _launch_viewer(bf: str = briefing_file) -> None:
                try:
                    open_viewer(bf)
                except Exception:
                    logger.exception("ビューア起動に失敗しました: %s", bf)

            notify_briefing(
                briefing_file, "a",
                on_click=lambda: threading.Thread(target=_launch_viewer, daemon=True).start(),
                notification_config=config.notification,
            )

        logger.info("機能 A 完了: %s", briefing_file)

    except Exception as exc:
        logger.exception("機能 A の実行中にエラーが発生しました")
        notify_error("a", str(exc), notification_config=config.notification)
    finally:
        if on_tray_normal:
            on_tray_normal()
