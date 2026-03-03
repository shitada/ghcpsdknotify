"""エントリーポイント + メイン処理オーケストレーションモジュール。

起動フロー（ログ→設定→前提チェック→状態読み込み→スケジューラ→システムトレイ常駐）と、
機能 A / 機能 B のメイン処理コールバックを実装する。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any

from pathlib import Path as _Path

import pystray
from PIL import Image

# ── アセットフォルダ ──
_ASSETS_DIR = _Path(__file__).resolve().parent.parent / "assets"

from app import config as config_module
from app.config import AppConfig
from app.copilot_client import CopilotClientWrapper
from app.file_selector import (
    get_random_picked_paths,
    select_files,
)
from app.folder_scanner import ScannedFile, scan_folders
from app.i18n import get_language, set_language, t
from app.logger import get_log_file_path, setup_logging
from app.notifier import (
    notify_briefing,
    notify_error,
    notify_processing,
    notify_warning,
    notify_workiq_setup,
    open_workiq_setup_dialog,
)
from app.output_writer import (
    get_output_folder,
    write_briefing,
)
from app.quiz_scorer import process_unanswered
from app.scheduler import Scheduler
from app.settings_ui import open_settings
from app.setup_wizard import run_wizard
from app.state_manager import PendingQuiz, StateManager
from app.utils import estimate_tokens
from app.viewer import open_viewer

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  プロンプトテンプレート
# ══════════════════════════════════════════════════════════════════════

# ── システムプロンプト: 機能 A（最新情報の取得）──

SYSTEM_PROMPT_A_BASE = """\
あなたは「パーソナル AI デイリーブリーフィング Agent」です。
ユーザーのローカルフォルダにある Markdown ファイル群を分析し、
ノートに含まれるトピックについて最新のニュース・技術アップデート・
ブログ記事・社内ナレッジを取得し、要約してください。
必ずソース URL を付記してください。

## ツール使い分けルール
- **Web 検索（Bing）を使うべきケース**:
  - 技術名・製品名・OSS プロジェクト名に関する最新情報
  - 公式ドキュメント・ブログ・リリースノートの確認
  - 業界ニュース・トレンド
{workiq_tool_rules}
- **判断に迷う場合**: 両方のツールで検索してください。
- **WorkIQ MCP で結果が見つからない場合**: そのセクションを省略してください。

## 出力ルール
- 出力は Markdown 形式で、日本語で記述してください。
- 各セクションに見出し（##）を付けてください。
- 情報がないセクションは省略してください（無理に埋めない）。
- ユーザーが朝の5分で読める分量を目安にしてください。
"""

_WORKIQ_TOOL_RULES = """\
- **WorkIQ MCP を使うべきケース**:
  - 社内プロジェクト名・顧客名・チーム名が含まれるトピック
  - 社内事例・テンプレート・ナレッジ記事の検索
  - 社内アナウンス・ディスカッションの確認"""

# ── システムプロンプト: 機能 B（復習・クイズ）──

SYSTEM_PROMPT_B_TEMPLATE = """\
あなたは「パーソナル AI デイリーブリーフィング Agent」です。
ユーザーのローカルフォルダにある Markdown ファイル群を分析し、
ノートの最終更新日を考慮して復習・クイズを生成してください。

## 出題ルール
- **1回の実行で出題するトピックは 1 つだけ**（Q1 + Q2 の計2問）です。
- 今回の出題パターン: **{quiz_pattern}**
{quiz_pattern_instruction}
- 対象ノートがない場合は、もう一方のパターンから出題してください。

## topic_key ルール
- 各トピックの見出し（### の行）の **直前** に、以下の形式で HTML コメントを挿入してください:
  `<!-- topic_key: {{ソースファイルの相対パス}}#{{セクション識別子}} -->`
- `{{ソースファイルの相対パス}}` はユーザープロンプトの「ファイル一覧」に記載されたパスをそのまま使用してください。
- `{{セクション識別子}}` はトピックを一意に識別できる短い英数字・ハイフンの文字列を付けてください（例: `hosting-plans`, `hybrid-connectivity`）。
- 例: `<!-- topic_key: learning/azure-functions.md#hosting-plans -->`

## 出力ルール
- 出力は Markdown 形式で、日本語で記述してください。
- 各セクションに見出し（##）を付けてください。
- 情報がないセクションは省略してください（無理に埋めない）。
- **Q1 の正解・解説、Q2 の模範解答は出力に含めないでください。**
  採点はユーザーの回答後に別途行います。
- ユーザーが朝の5分で読める分量を目安にしてください。
"""

# ── ディスカバリー回追記 ──

DISCOVERY_APPENDIX = """

## 追加指示（ディスカバリー回）
今回はディスカバリー回です。普段見ていないファイルが含まれています。
新しい発見や忘れていたトピックを優先的に取り上げてください。
"""

# ── ユーザープロンプト: 機能 A ──

USER_PROMPT_A_TEMPLATE = """\
## 実行情報
- 現在日時: {current_datetime}
- 対象フォルダ: {input_folders}

## ファイル一覧と概要
{file_list_with_metadata}

## ファイル内容
{file_contents}

上記のローカルファイルの内容を踏まえて、今日のデイリーブリーフィングを
生成してください。
"""

# ── ユーザープロンプト: 機能 B ──

USER_PROMPT_B_TEMPLATE = """\
## 実行情報
- 現在日時: {current_datetime}
- 対象フォルダ: {input_folders}

## ファイル一覧と概要
{file_list_with_metadata}

## ファイル内容
{file_contents}

## 間隔反復情報（クイズ出題の参考）
{quiz_schedule_info}

上記のローカルファイルの内容を踏まえて、今日の復習・クイズを
生成してください。期限到来トピックがあればそちらを優先してください。
"""


# ══════════════════════════════════════════════════════════════════════
#  英語版プロンプトテンプレート
# ══════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_A_BASE_EN = """\
You are a "Personal AI Daily Briefing Agent".
Analyze the Markdown files in the user's local folders,
and for topics found in the notes, retrieve and summarize the latest news,
technical updates, blog posts, and internal knowledge.
Always include source URLs.

## Tool Usage Rules
- **When to use Web Search (Bing)**:
  - Latest information on technology names, product names, OSS project names
  - Checking official documentation, blogs, release notes
  - Industry news and trends
{workiq_tool_rules}
- **When in doubt**: Search with both tools.
- **If WorkIQ MCP returns no results**: Omit that section.

## Output Rules
- Output in Markdown format, written in English.
- Add headings (##) for each section.
- Omit sections with no information (don't force-fill).
- Target a length readable in 5 minutes in the morning.
"""

_WORKIQ_TOOL_RULES_EN = """\
- **When to use WorkIQ MCP**:
  - Topics containing internal project names, customer names, or team names
  - Searching for internal case studies, templates, or knowledge articles
  - Checking internal announcements and discussions"""

SYSTEM_PROMPT_B_TEMPLATE_EN = """\
You are a "Personal AI Daily Briefing Agent".
Analyze the Markdown files in the user's local folders,
and generate review quizzes considering each note's last modification date.

## Quiz Rules
- **Only one topic per execution** (Q1 + Q2, total 2 questions).
- Quiz pattern for this run: **{quiz_pattern}**
{quiz_pattern_instruction}
- If no applicable notes are found, use the other pattern instead.

## topic_key Rules
- **Before** each topic heading (### line), insert an HTML comment in this format:
  `<!-- topic_key: {{relative path of source file}}#{{section identifier}} -->`
- `{{relative path of source file}}` — use the path exactly as listed in the user prompt's "File List".
- `{{section identifier}}` — a short alphanumeric/hyphen string that uniquely identifies the topic (e.g., `hosting-plans`, `hybrid-connectivity`).
- Example: `<!-- topic_key: learning/azure-functions.md#hosting-plans -->`

## Output Rules
- Output in Markdown format, written in English.
- Add headings (##) for each section.
- Omit sections with no information (don't force-fill).
- **Do NOT include Q1 correct answer/explanation or Q2 model answer in the output.**
  Scoring will be done separately after the user answers.
- Target a length readable in 5 minutes in the morning.
"""

DISCOVERY_APPENDIX_EN = """

## Additional Instructions (Discovery Run)
This is a discovery run. Files not usually reviewed are included.
Prioritize new discoveries and forgotten topics.
"""

USER_PROMPT_A_TEMPLATE_EN = """\
## Execution Info
- Current date/time: {current_datetime}
- Target folders: {input_folders}

## File List and Metadata
{file_list_with_metadata}

## File Contents
{file_contents}

Based on the local file contents above, generate today's daily briefing.
"""

USER_PROMPT_B_TEMPLATE_EN = """\
## Execution Info
- Current date/time: {current_datetime}
- Target folders: {input_folders}

## File List and Metadata
{file_list_with_metadata}

## File Contents
{file_contents}

## Spaced Repetition Info (for quiz scheduling)
{quiz_schedule_info}

Based on the local file contents above, generate today's review quiz.
Prioritize topics that are due for review.
"""


def _get_prompt(ja: str, en: str) -> str:
    """現在の言語設定に応じたプロンプト文字列を返す。"""
    return en if get_language() == "en" else ja


# ══════════════════════════════════════════════════════════════════════
#  グローバル状態（モジュールレベル）
# ══════════════════════════════════════════════════════════════════════

_app_config: AppConfig | None = None
_state_manager: StateManager | None = None
_scheduler: Scheduler | None = None
_tray_icon: pystray.Icon | None = None
_needs_soft_restart: bool = False

# トレイアイコン用画像（assets/ の PNG を読み込み、なければフォールバック）
try:
    _ICON_NORMAL = Image.open(_ASSETS_DIR / "icon_normal.png")
    _ICON_PROCESSING = Image.open(_ASSETS_DIR / "icon_processing.png")
except Exception:
    _ICON_NORMAL = Image.new("RGB", (64, 64), color=(0, 120, 212))
    _ICON_PROCESSING = Image.new("RGB", (64, 64), color=(255, 140, 0))


def _get_tray_title() -> str:
    """トレイアイコンの通常タイトルを返す（言語切り替え対応）。"""
    return t("app.name")


def _set_tray_processing(feature: str) -> None:
    """トレイアイコンを「処理中」状態に切り替える。

    アイコン色をオレンジに変更し、ツールチップを更新する。

    Args:
        feature: "a" または "b"。
    """
    if _tray_icon is None:
        return
    label = t("tray.feature_a") if feature == "a" else t("tray.feature_b")
    _tray_icon.icon = _ICON_PROCESSING
    _tray_icon.title = t("tray.processing", label=label)


def _set_tray_normal() -> None:
    """トレイアイコンを通常状態に戻す。"""
    if _tray_icon is None:
        return
    _tray_icon.icon = _ICON_NORMAL
    _tray_icon.title = _get_tray_title()


# ══════════════════════════════════════════════════════════════════════
#  プロンプト構築ヘルパー
# ══════════════════════════════════════════════════════════════════════


def _build_system_prompt_a(config: AppConfig) -> str:
    """機能 A のシステムプロンプトを構築する。

    WorkIQ MCP が未設定の場合は社内検索ルールを除外する。

    Args:
        config: アプリケーション設定。

    Returns:
        システムプロンプト文字列。
    """
    if config.workiq_mcp.enabled:
        workiq_rules = _get_prompt(_WORKIQ_TOOL_RULES, _WORKIQ_TOOL_RULES_EN)
    else:
        workiq_rules = ""

    base = _get_prompt(SYSTEM_PROMPT_A_BASE, SYSTEM_PROMPT_A_BASE_EN)
    return base.format(workiq_tool_rules=workiq_rules)


def _build_system_prompt_b(run_count: int = 0) -> str:
    """機能 B のシステムプロンプトを構築する。

    run_count の偶奇で📘学習中と📗振り返りを交互に出題する。

    Args:
        run_count: 機能 B の実行回数（今回分含む）。

    Returns:
        システムプロンプト文字列。
    """
    is_en = get_language() == "en"
    if run_count % 2 == 1:
        # 奇数回: 📘 学習中
        quiz_pattern = "📘 学習中のトピック" if not is_en else "📘 Active Learning Topic"
        quiz_pattern_instruction = (
            "- 最終更新 1〜2週間以内のノートから1トピック選び、\n"
            "  まず「💡 要点リマインド」として学習内容の要点を提示し、\n"
            "  その後にクイズを2問出題。Q1 は4択、Q2 は記述式。\n"
            "  応用シナリオやトラブルシューティングを含め、難易度はやや高め。"
        ) if not is_en else (
            "- Pick 1 topic from notes updated within the last 1-2 weeks.\n"
            "  First present a '💡 Key Points Reminder' summarizing the key points,\n"
            "  then pose 2 quiz questions: Q1 is multiple-choice, Q2 is free-form.\n"
            "  Include applied scenarios and troubleshooting; difficulty is moderately high."
        )
    else:
        # 偶数回: 📗 振り返り
        quiz_pattern = "📗 振り返り" if not is_en else "📗 Review"
        quiz_pattern_instruction = (
            "- 最終更新 1ヶ月以上のノートから1トピック選び、\n"
            "  まず「💡 要点リマインド」として学習内容の要約を提示し、\n"
            "  その後にクイズを2問出題。Q1 は4択、Q2 は記述式。\n"
            "  難易度は基本〜中程度。"
        ) if not is_en else (
            "- Pick 1 topic from notes last updated over 1 month ago.\n"
            "  First present a '💡 Key Points Reminder' summarizing the material,\n"
            "  then pose 2 quiz questions: Q1 is multiple-choice, Q2 is free-form.\n"
            "  Difficulty is basic to moderate."
        )

    template = _get_prompt(SYSTEM_PROMPT_B_TEMPLATE, SYSTEM_PROMPT_B_TEMPLATE_EN)
    return template.format(
        quiz_pattern=quiz_pattern,
        quiz_pattern_instruction=quiz_pattern_instruction,
    )


def _build_file_list_with_metadata(files: list[ScannedFile]) -> str:
    """ファイル一覧とメタデータのテキストを構築する。

    Args:
        files: 選定済みファイルリスト。

    Returns:
        ファイル一覧のフォーマット済みテキスト。
    """
    lines: list[str] = []
    for f in files:
        meta = f.metadata
        modified = meta.modified_at.strftime("%Y-%m-%d %H:%M") if meta.modified_at else t("common.unknown")
        parts = [f"- **{meta.relative_path}** ({t('main.modified', date=modified)})"]

        if meta.priority:
            parts.append(f"  priority: {meta.priority}")
        if meta.deadline:
            parts.append(f"  deadline: {meta.deadline}")
        if meta.tags:
            parts.append(f"  tags: {', '.join(meta.tags)}")
        if meta.unchecked_count > 0:
            parts.append(f"  {t('main.unchecked', count=meta.unchecked_count)}")

        lines.append("\n".join(parts))

    return "\n".join(lines)


def _build_file_contents(
    files: list[ScannedFile],
    max_tokens: int,
) -> str:
    """ファイル内容テキストを構築する（トークン上限考慮）。

    max_context_tokens を超過する場合は古いファイルから切り詰める。

    Args:
        files: 選定済みファイルリスト。
        max_tokens: 最大トークン数。

    Returns:
        ファイル内容のフォーマット済みテキスト。
    """
    # 更新日時でソート（新しい順）→ 新しいファイルを優先
    sorted_files = sorted(
        files,
        key=lambda f: f.metadata.modified_at or datetime.min,
        reverse=True,
    )

    result_parts: list[str] = []
    current_tokens = 0

    for f in sorted_files:
        section = f"### {f.metadata.relative_path}\n\n{f.content}\n"
        section_tokens = estimate_tokens(section)

        if current_tokens + section_tokens > max_tokens:
            remaining = max_tokens - current_tokens
            if remaining > 200:
                # 残りトークン分だけ部分的に含める
                truncate_ratio = remaining / section_tokens
                truncated_len = int(len(section) * truncate_ratio)
                section = section[:truncated_len] + "\n\n" + t("main.truncated")
                result_parts.append(section)
            break

        result_parts.append(section)
        current_tokens += section_tokens

    return "\n---\n\n".join(result_parts)


def _build_quiz_schedule_info(state_manager: StateManager) -> str:
    """間隔反復情報（quiz_schedule_info）を構築する。

    next_quiz_at <= today のトピック一覧を生成する。

    Args:
        state_manager: 状態マネージャ。

    Returns:
        クイズスケジュール情報テキスト。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    due_topics: list[str] = []

    for topic_key, entry in state_manager.state.quiz_history.items():
        if entry.next_quiz_at and entry.next_quiz_at <= today:
            # 前回の結果サマリ
            last_result = ""
            if entry.results:
                last = entry.results[-1]
                q1 = t("main.q1_result_correct") if last.q1_correct else t("main.q1_result_incorrect")
                last_result = t("main.last_result", q1=q1, q2=last.q2_evaluation)

            due_topics.append(
                f"- **{topic_key}** — Level {entry.level}, "
                f"{t('main.interval', days=entry.interval_days)}, {last_result}"
            )

    if due_topics:
        return t("main.topics_due_header") + "\n" + "\n".join(due_topics)
    else:
        return t("main.no_topics_due")


def _extract_topic_keys(md_content: str) -> list[dict[str, str]]:
    """ブリーフィング MD から topic_key を抽出する。

    utils.extract_topic_keys へ委譲する。
    """
    from app.utils import extract_topic_keys

    return extract_topic_keys(md_content)


# ══════════════════════════════════════════════════════════════════════
#  メイン処理（job_a / job_b コールバック）
# ══════════════════════════════════════════════════════════════════════


def _run_job_a() -> None:
    """機能 A（最新情報の取得）のメイン処理。

    仕様書 6章のステップ 1〜10 を実行する。
    """
    assert _app_config is not None
    assert _state_manager is not None
    config = _app_config
    sm = _state_manager

    logger.info("=== 機能 A 実行開始 ===")
    _set_tray_processing("a")
    notify_processing("a", notification_config=config.notification)

    try:
        # 1. フォルダ走査
        if not config.input_folders:
            logger.warning("input_folders が空です。機能 A をスキップします")
            return

        scanned_files = scan_folders(
            config.input_folders,
            config.target_extensions,
        )

        if not scanned_files:
            logger.warning("走査結果が0件です。機能 A をスキップします")
            return

        # 3. ファイル選定
        run_count = sm.state.run_count_a + 1  # 今回分を加算
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

        # 4. プロンプト構築
        system_prompt = _build_system_prompt_a(config)
        if selection.is_discovery:
            system_prompt += _get_prompt(DISCOVERY_APPENDIX, DISCOVERY_APPENDIX_EN)

        file_list = _build_file_list_with_metadata(selection.selected_files)
        file_contents = _build_file_contents(
            selection.selected_files,
            config.copilot_sdk.max_context_tokens,
        )

        user_prompt = _get_prompt(USER_PROMPT_A_TEMPLATE, USER_PROMPT_A_TEMPLATE_EN).format(
            current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
            input_folders=", ".join(config.input_folders),
            file_list_with_metadata=file_list,
            file_contents=file_contents,
        )

        # 5. Copilot SDK 呼び出し
        briefing_text = asyncio.run(_generate_briefing_a(config, system_prompt, user_prompt))

        if not briefing_text:
            logger.warning("ブリーフィング生成結果が空です")
            return

        # 6. MD ファイル出力
        output_folder = get_output_folder(
            config.input_folders,
            config.output_folder_name,
            sm.state.output_folder_path,
        )
        sm.set_output_folder_path(output_folder)

        briefing_file = write_briefing(briefing_text, "a", output_folder)
        logger.info("機能 A ブリーフィング出力: %s", briefing_file)

        # 7. WorkIQ MCP 未設定検知
        _check_workiq_setup(config, run_count)

        # 9. state.json 更新
        sm.increment_run_count("a")
        sm.update_last_run()
        sm.update_last_run_feature("a")
        random_picked = get_random_picked_paths(selection)
        if random_picked:
            sm.update_random_pick_history(random_picked)
        sm.save()

        # 10. 通知
        if config.notification.enabled:
            def _launch_viewer_a(bf: str = briefing_file) -> None:
                try:
                    open_viewer(bf)
                except Exception:
                    logger.exception("ビューア起動に失敗しました: %s", bf)

            notify_briefing(
                briefing_file,
                "a",
                on_click=lambda: threading.Thread(
                    target=_launch_viewer_a,
                    daemon=True,
                ).start(),
                notification_config=config.notification,
            )

        logger.info("機能 A 完了: %s", briefing_file)

    except Exception as exc:
        logger.exception("機能 A の実行中にエラーが発生しました")
        notify_error("a", str(exc), notification_config=config.notification)
    finally:
        _set_tray_normal()


def _run_job_b() -> None:
    """機能 B（復習・クイズ）のメイン処理。

    仕様書 6章のステップ 1〜10 を実行する。
    """
    assert _app_config is not None
    assert _state_manager is not None
    config = _app_config
    sm = _state_manager

    logger.info("=== 機能 B 実行開始 ===")
    _set_tray_processing("b")
    notify_processing("b", notification_config=config.notification)

    try:
        # 1. フォルダ走査
        if not config.input_folders:
            logger.warning("input_folders が空です。機能 B をスキップします")
            return

        scanned_files = scan_folders(
            config.input_folders,
            config.target_extensions,
        )

        if not scanned_files:
            logger.warning("走査結果が0件です。機能 B をスキップします")
            return

        # 2. pending_quizzes の未回答分を自動不正解処理
        process_unanswered(
            sm,
            sr_config=config.quiz.spaced_repetition,
        )

        # 3. ファイル選定
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

        # 4. プロンプト構築
        system_prompt = _build_system_prompt_b(run_count)
        if selection.is_discovery:
            system_prompt += _get_prompt(DISCOVERY_APPENDIX, DISCOVERY_APPENDIX_EN)

        file_list = _build_file_list_with_metadata(selection.selected_files)
        file_contents = _build_file_contents(
            selection.selected_files,
            config.copilot_sdk.max_context_tokens,
        )
        quiz_schedule_info = _build_quiz_schedule_info(sm)

        user_prompt = _get_prompt(USER_PROMPT_B_TEMPLATE, USER_PROMPT_B_TEMPLATE_EN).format(
            current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
            input_folders=", ".join(config.input_folders),
            file_list_with_metadata=file_list,
            file_contents=file_contents,
            quiz_schedule_info=quiz_schedule_info,
        )

        # 5. Copilot SDK 呼び出し
        briefing_text = asyncio.run(_generate_briefing_b(config, system_prompt, user_prompt))

        if not briefing_text:
            logger.warning("ブリーフィング生成結果が空です")
            return

        # 6. MD ファイル出力
        output_folder = get_output_folder(
            config.input_folders,
            config.output_folder_name,
            sm.state.output_folder_path,
        )
        sm.set_output_folder_path(output_folder)

        briefing_file = write_briefing(briefing_text, "b", output_folder)
        logger.info("機能 B ブリーフィング出力: %s", briefing_file)

        # 8. topic_key 抽出 → pending_quizzes 登録
        topic_keys = _extract_topic_keys(briefing_text)
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

        # 9. state.json 更新
        sm.increment_run_count("b")
        sm.update_last_run()
        sm.update_last_run_feature("b")
        random_picked = get_random_picked_paths(selection)
        if random_picked:
            sm.update_random_pick_history(random_picked)
        sm.save()

        # 10. 通知
        if config.notification.enabled:
            def _launch_viewer_b(
                bf: str = briefing_file,
                _sm: StateManager = sm,
                _cfg: AppConfig = config,
            ) -> None:
                try:
                    open_viewer(bf, _sm, _cfg)
                except Exception:
                    logger.exception("ビューア起動に失敗しました: %s", bf)

            notify_briefing(
                briefing_file,
                "b",
                on_click=lambda: threading.Thread(
                    target=_launch_viewer_b,
                    daemon=True,
                ).start(),
                notification_config=config.notification,
            )

        logger.info("機能 B 完了: %s", briefing_file)

    except Exception as exc:
        logger.exception("機能 B の実行中にエラーが発生しました")
        notify_error("b", str(exc), notification_config=config.notification)
    finally:
        _set_tray_normal()


# ══════════════════════════════════════════════════════════════════════
#  Copilot SDK 非同期呼び出しブリッジ
# ══════════════════════════════════════════════════════════════════════


async def _generate_briefing_a(
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """機能 A のブリーフィングを非同期で生成する。"""
    result = ""
    async with CopilotClientWrapper(config.copilot_sdk) as client:
        result = await client.generate_briefing_a(
            system_prompt, user_prompt, config.workiq_mcp
        )
    return result


async def _generate_briefing_b(
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """機能 B のブリーフィングを非同期で生成する。"""
    result = ""
    async with CopilotClientWrapper(config.copilot_sdk) as client:
        result = await client.generate_briefing_b(system_prompt, user_prompt)
    return result


# ══════════════════════════════════════════════════════════════════════
#  WorkIQ MCP 未設定通知
# ══════════════════════════════════════════════════════════════════════


def _check_workiq_setup(config: AppConfig, run_count: int) -> None:
    """WorkIQ MCP が未設定の場合に通知を行う。

    初回起動時および5回に1回の頻度で通知する。
    suppress_setup_prompt=true の場合はスキップ。

    Args:
        config: アプリケーション設定。
        run_count: 現在の実行カウント。
    """
    if config.workiq_mcp.enabled:
        return  # 設定済み

    if config.workiq_mcp.suppress_setup_prompt:
        return  # 非表示設定

    # 初回（run_count==1）または 5回に1回
    if run_count == 1 or run_count % 5 == 0:
        notify_workiq_setup(
            on_click=lambda: open_workiq_setup_dialog(_app_config),
            notification_config=config.notification,
        )


# ══════════════════════════════════════════════════════════════════════
#  システムトレイ（pystray）
# ══════════════════════════════════════════════════════════════════════


def _restart_app(icon: pystray.Icon) -> None:
    """言語変更後にトレイアイコンを再構築する（ソフトリスタート）。

    新しいプロセスを起動せず、同一プロセス内でトレイアイコンを
    停止→再作成することで、環境変数を維持したまま UI を更新する。
    """
    global _needs_soft_restart  # noqa: PLW0603

    logger.info("言語変更のためトレイアイコンを再構築します (soft restart)")
    _needs_soft_restart = True
    icon.stop()


def _create_tray_icon() -> pystray.Icon:
    """システムトレイアイコンを作成する。

    Returns:
        pystray.Icon インスタンス。
    """
    # 16x16 の簡易アイコン画像を生成
    icon_image = _ICON_NORMAL

    def on_manual_run_a(icon: pystray.Icon, item: Any) -> None:
        """手動実行: 機能 A。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["a"],),
            daemon=True,
        ).start()

    def on_manual_run_b(icon: pystray.Icon, item: Any) -> None:
        """手動実行: 機能 B。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["b"],),
            daemon=True,
        ).start()

    def on_manual_run_both(icon: pystray.Icon, item: Any) -> None:
        """手動実行: A + B（順次）。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["a", "b"],),
            daemon=True,
        ).start()

    def on_open_log(icon: pystray.Icon, item: Any) -> None:
        """ログファイルを OS デフォルトエディタで開く。"""
        log_path = get_log_file_path()
        try:
            os.startfile(log_path)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("ログファイルを開けませんでした: %s", log_path)

    def on_settings(icon: pystray.Icon, item: Any) -> None:
        """設定メニューを開く。"""
        assert _app_config is not None

        def _open_and_check_restart() -> None:
            needs_restart = open_settings(
                _app_config,
                lambda cfg: (
                    _scheduler.update_schedule(cfg) if _scheduler else None
                ),
            )
            if needs_restart:
                logger.info("Language changed — restarting application")
                _restart_app(icon)

        threading.Thread(
            target=_open_and_check_restart,
            daemon=True,
        ).start()

    def on_quit(icon: pystray.Icon, item: Any) -> None:
        """アプリを終了する。"""
        logger.info("アプリケーションを終了します")
        if _scheduler:
            _scheduler.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            t("tray.manual_run"),
            pystray.Menu(
                pystray.MenuItem(t("tray.run_a_only"), on_manual_run_a),
                pystray.MenuItem(t("tray.run_b_only"), on_manual_run_b),
                pystray.MenuItem(t("tray.run_both"), on_manual_run_both),
            ),
        ),
        pystray.MenuItem(t("tray.settings"), on_settings),
        pystray.MenuItem(t("tray.open_log"), on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("tray.quit"), on_quit),
    )

    icon = pystray.Icon(
        name="DailyBriefingAgent",
        icon=icon_image,
        title=_get_tray_title(),
        menu=menu,
    )

    return icon


# ══════════════════════════════════════════════════════════════════════
#  エントリーポイント
# ══════════════════════════════════════════════════════════════════════


def main() -> None:
    """アプリケーションのメインエントリーポイント。

    起動フロー:
    1. logger.setup_logging()
    2. config.load()
    3. setup_wizard 呼び出し（TODO）
    4. state_manager.load()
    5. scheduler.start()
    6. pystray でシステムトレイ常駐
    """
    global _app_config, _state_manager, _scheduler, _tray_icon, _needs_soft_restart

    # 1. ログ設定
    setup_logging()

    logger.info("========================================")
    logger.info("パーソナル AI デイリーブリーフィング Agent 起動")
    logger.info("========================================")

    try:
        # 2. config.yaml 読み込み
        _app_config = config_module.load()
        setup_logging(_app_config.log_level)  # ログレベルを反映
        logger.info("Config loaded: language=%s, log_level=%s", _app_config.language, _app_config.log_level)
        set_language(_app_config.language)  # 言語設定を反映

        # 3. setup_wizard 呼び出し
        if not run_wizard(_app_config):
            logger.info("セットアップウィザードが中断されました。終了します。")
            return

        # 4. state_manager.load()
        _state_manager = StateManager()
        _state_manager.load()

        # 5. scheduler.start()
        _scheduler = Scheduler()
        _scheduler.start(
            config=_app_config,
            on_job_a=_run_job_a,
            on_job_b=_run_job_b,
        )

        # 5.5. 起動時キャッチアップ（スリープ復帰・遅延起動対応）
        _scheduler.check_and_run_missed_jobs(
            config=_app_config,
            last_run_a_at=_state_manager.state.last_run_a_at,
            last_run_b_at=_state_manager.state.last_run_b_at,
        )

        # 6. pystray でシステムトレイ常駐
        logger.info("システムトレイに常駐します")
        while True:
            _tray_icon = _create_tray_icon()
            _tray_icon.run()
            if not _needs_soft_restart:
                break
            # ソフトリスタート: フラグをリセットしてトレイアイコンを再作成
            _needs_soft_restart = False
            logger.info("トレイアイコンを再作成しました")

    except KeyboardInterrupt:
        logger.info("Ctrl+C で終了します")
    except Exception:
        logger.exception("起動中に致命的なエラーが発生しました")
    finally:
        if _scheduler:
            _scheduler.stop()
        logger.info("アプリケーションを終了しました")


if __name__ == "__main__":
    main()
