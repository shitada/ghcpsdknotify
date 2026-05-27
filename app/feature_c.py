"""機能 C（ページモニター）のジョブ実行モジュール。

監視対象ページの自動分析 → フェッチ → 変更検出 →
Copilot SDK 呼び出し → MD 出力 → 通知 の一連のフローを実行する。
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
from app.notifier import notify_briefing, notify_error, notify_processing
from app.output_writer import get_output_folder, write_briefing
from app.page_monitor import (
    PageMonitorEntry,
    analyze_page,
    build_report_prompt,
    compute_content_hash,
    detect_changes,
    extract_links,
    fetch_page,
    parse_rss_feed,
)
from app.prompts import get_system_prompt_c
from app.state_manager import StateManager
from app.viewer import open_viewer

logger = logging.getLogger(__name__)


async def _generate_briefing(
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """機能 C のブリーフィングを非同期で生成する。"""
    async with CopilotClientWrapper(config.copilot_sdk) as client:
        return await client.generate_briefing_c(system_prompt, user_prompt)


def run(
    config: AppConfig,
    state_manager: StateManager,
    *,
    on_tray_processing: Callable[[], None] | None = None,
    on_tray_normal: Callable[[], None] | None = None,
) -> None:
    """機能 C のメイン処理を実行する。"""
    sm = state_manager

    if not config.page_monitor.enabled:
        logger.debug("ページモニターが無効のためスキップ")
        return

    enabled_pages = [p for p in config.page_monitor.pages if p.enabled]
    if not enabled_pages:
        logger.debug("監視対象ページが0件のためスキップ")
        return

    logger.info("=== 機能 C 実行開始 ===")
    if on_tray_processing:
        on_tray_processing()
    notify_processing("c", notification_config=config.notification)

    try:
        # 0. 未分析ページの自動分析
        config_changed = False
        for i, page in enumerate(config.page_monitor.pages):
            if not page.analyzed and page.enabled:
                logger.info("ページ自動分析: %s", page.url)
                try:
                    analyzed = asyncio.run(analyze_page(page.url))
                    analyzed.enabled = page.enabled
                    config.page_monitor.pages[i] = analyzed
                    config_changed = True
                    logger.info(
                        "ページ分析完了: %s → mode=%s, name=%s",
                        page.url, analyzed.mode, analyzed.name,
                    )
                except Exception as e:
                    logger.warning("ページ分析失敗 (%s): %s", page.url, e)

        if config_changed:
            config_module.save(config)
            logger.info("分析結果を config.yaml に保存しました")

        # 再取得（分析後のフィルタ）
        enabled_pages = [p for p in config.page_monitor.pages if p.enabled and p.analyzed]
        if not enabled_pages:
            logger.debug("分析済みの監視対象ページが0件のためスキップ")
            return

        # 1. 全監視ページをフェッチ & 変更検出
        changes_with_updates = []
        all_page_states: dict[str, PageMonitorEntry] = {}
        failed_pages: list[str] = []

        for page in enabled_pages:
            try:
                fetch_url = page.feed_url if page.mode == "rss" and page.feed_url else page.url
                content = asyncio.run(fetch_page(fetch_url))
            except Exception as e:
                logger.warning("ページ取得失敗 (%s): %s", page.url, e)
                failed_pages.append(page.url)
                continue

            prev_state = sm.state.page_monitor_state.get(page.url, PageMonitorEntry())
            result = detect_changes(page, content, prev_state)

            # 状態更新
            if page.mode == "rss":
                entries = parse_rss_feed(content)
                new_entry = PageMonitorEntry(
                    known_links=[e["url"] for e in entries],
                    last_checked_at=datetime.now().isoformat(timespec="seconds"),
                )
            else:
                selector = page.link_selector or "a"
                current_links = extract_links(content, page.url, selector)
                current_hash = compute_content_hash(content, page.content_selector)
                new_entry = PageMonitorEntry(
                    content_hash=current_hash,
                    known_links=[link["url"] for link in current_links],
                    last_checked_at=datetime.now().isoformat(timespec="seconds"),
                )
            all_page_states[page.url] = new_entry

            if result.has_changes:
                changes_with_updates.append(result)
                logger.info(
                    "ページ変更検出: %s (新リンク=%d, コンテンツ変更=%s)",
                    page.name, len(result.new_links), result.content_changed,
                )

        # 1a. 全ページ取得失敗時はエラー通知して終了
        if failed_pages and not all_page_states:
            err_msg = f"全{len(failed_pages)}ページの取得に失敗しました: {', '.join(failed_pages)}"
            logger.error("機能 C: %s", err_msg)
            notify_error("c", err_msg, notification_config=config.notification)
            return

        # 1b. 一部ページ取得失敗時はログ警告（処理続行）
        if failed_pages:
            logger.warning(
                "機能 C: %d ページの取得に失敗しました（処理続行）: %s",
                len(failed_pages), ", ".join(failed_pages),
            )

        # 2. 変更なしならスキップ（状態は保存）
        if not changes_with_updates:
            logger.info("監視対象ページに変更はありませんでした")
            for url, entry in all_page_states.items():
                sm.update_page_monitor_state(url, entry)
            sm.increment_run_count("c")
            sm.update_last_run()
            sm.update_last_run_feature("c")
            sm.save()
            return

        # 3. プロンプト構築
        system_prompt = get_system_prompt_c()
        user_prompt = build_report_prompt(changes_with_updates)

        # 4. Copilot SDK 呼び出し
        briefing_text = asyncio.run(
            _generate_briefing(config, system_prompt, user_prompt)
        )
        if not briefing_text:
            logger.warning("ページモニターレポート生成結果が空です")
            return

        # 5. MD 出力
        output_folder = get_output_folder(
            config.input_folders, config.output_folder_name, sm.state.output_folder_path
        )
        sm.set_output_folder_path(output_folder)
        briefing_file = write_briefing(briefing_text, "c", output_folder)
        logger.info("機能 C ブリーフィング出力: %s", briefing_file)

        # 6. 状態更新
        for url, entry in all_page_states.items():
            sm.update_page_monitor_state(url, entry)
        sm.increment_run_count("c")
        sm.update_last_run()
        sm.update_last_run_feature("c")
        sm.save()

        # 7. 通知
        if config.notification.enabled:
            def _launch_viewer(bf: str = briefing_file) -> None:
                try:
                    open_viewer(bf)
                except Exception:
                    logger.exception("ビューア起動に失敗しました: %s", bf)

            notify_briefing(
                briefing_file, "c",
                on_click=lambda: threading.Thread(target=_launch_viewer, daemon=True).start(),
                notification_config=config.notification,
            )

        logger.info("機能 C 完了: %s", briefing_file)

    except Exception as exc:
        logger.exception("機能 C の実行中にエラーが発生しました")
        notify_error("c", str(exc), notification_config=config.notification)
    finally:
        if on_tray_normal:
            on_tray_normal()
