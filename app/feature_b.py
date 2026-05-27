"""機能 B（復習・クイズ）のジョブ実行モジュール。

フォルダ走査 → 未回答処理 → ファイル選定 → プロンプト構築 →
Copilot SDK 呼び出し → MD 出力 → topic_key 登録 → 通知 の一連のフローを実行する。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime

from typing import Callable

from app.config import AppConfig
from app.copilot_client import CopilotClientWrapper
from app.file_selector import get_random_picked_paths, select_files
from app.folder_scanner import scan_folders
from app.notifier import notify_briefing, notify_error, notify_processing
from app.output_writer import get_output_folder, write_briefing
from app.prompts import (
    build_file_contents,
    build_file_list_with_metadata,
    build_quiz_schedule_info,
    get_discovery_appendix,
    get_system_prompt_b,
    get_user_prompt_b,
)
from app.quiz_scorer import process_unanswered
from app.state_manager import PendingQuiz, StateManager
from app.utils import extract_topic_keys
from app.viewer import open_viewer

logger = logging.getLogger(__name__)


async def _generate_briefing(
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """機能 B のブリーフィングを非同期で生成する。"""
    async with CopilotClientWrapper(config.copilot_sdk) as client:
        return await client.generate_briefing_b(system_prompt, user_prompt)


def run(
    config: AppConfig,
    state_manager: StateManager,
    *,
    on_tray_processing: Callable[[], None] | None = None,
    on_tray_normal: Callable[[], None] | None = None,
) -> None:
    """機能 B のメイン処理を実行する。"""
    sm = state_manager

    logger.info("=== 機能 B 実行開始 ===")
    if on_tray_processing:
        on_tray_processing()
    notify_processing("b", notification_config=config.notification)

    try:
        if not config.input_folders:
            logger.warning("input_folders が空です。機能 B をスキップします")
            return

        scanned_files = scan_folders(config.input_folders, config.target_extensions)
        if not scanned_files:
            logger.warning("走査結果が0件です。機能 B をスキップします")
            return

        # 未回答分の自動不正解処理
        process_unanswered(sm, sr_config=config.quiz.spaced_repetition)

        run_count = sm.state.run_count_b + 1
        selection = select_files(
            scanned_files,
            run_count=run_count,
            discovery_interval=config.file_selection.discovery_interval,
            max_files=config.file_selection.max_files,
            random_pick_history=sm.state.random_pick_history,
        )
        if not selection.selected_files:
            logger.warning("選定ファイルが0件です。機能 B をスキップします")
            return

        # プロンプト構築
        system_prompt = get_system_prompt_b(run_count)
        if selection.is_discovery:
            system_prompt += get_discovery_appendix()

        file_list = build_file_list_with_metadata(selection.selected_files)
        file_contents = build_file_contents(
            selection.selected_files, config.copilot_sdk.max_context_tokens
        )
        quiz_schedule_info = build_quiz_schedule_info(sm)

        user_prompt = get_user_prompt_b().format(
            current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
            input_folders=", ".join(config.input_folders),
            file_list_with_metadata=file_list,
            file_contents=file_contents,
            quiz_schedule_info=quiz_schedule_info,
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
        briefing_file = write_briefing(briefing_text, "b", output_folder)
        logger.info("機能 B ブリーフィング出力: %s", briefing_file)

        # topic_key 抽出 → pending_quizzes 登録
        topic_keys = extract_topic_keys(briefing_text)
        now_iso = datetime.now().isoformat(timespec="seconds")
        for tk in topic_keys:
            sm.add_pending_quiz(
                PendingQuiz(
                    briefing_file=briefing_file,
                    topic_key=tk["topic_key"],
                    pattern=tk["pattern"],
                    created_at=now_iso,
                )
            )
            logger.info("pending_quiz 登録: %s (%s)", tk["topic_key"], tk["pattern"])

        # 状態更新
        sm.increment_run_count("b")
        sm.update_last_run()
        sm.update_last_run_feature("b")
        random_picked = get_random_picked_paths(selection)
        if random_picked:
            sm.update_random_pick_history(random_picked)
        sm.save()

        # 通知
        if config.notification.enabled:
            def _launch_viewer(
                bf: str = briefing_file,
                _sm: StateManager = sm,
                _cfg: AppConfig = config,
            ) -> None:
                try:
                    open_viewer(bf, _sm, _cfg)
                except Exception:
                    logger.exception("ビューア起動に失敗しました: %s", bf)

            notify_briefing(
                briefing_file, "b",
                on_click=lambda: threading.Thread(target=_launch_viewer, daemon=True).start(),
                notification_config=config.notification,
            )

        logger.info("機能 B 完了: %s", briefing_file)

    except Exception as exc:
        logger.exception("機能 B の実行中にエラーが発生しました")
        notify_error("b", str(exc), notification_config=config.notification)
    finally:
        if on_tray_normal:
            on_tray_normal()
