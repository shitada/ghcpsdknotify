"""プロンプトテンプレートの読み込み・組み立てモジュール。

prompts/ フォルダ配下の .md ファイルからプロンプトテンプレートを読み込み、
言語切り替え・条件分岐・変数挿入を行う。
ビルダー関数（ファイル一覧・ファイル内容・クイズスケジュール）も提供する。
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from app.config import AppConfig
from app.i18n import get_language, t
from app.state_manager import StateManager
from app.utils import estimate_tokens

logger = logging.getLogger(__name__)

# prompts/ ディレクトリのルート
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=64)
def _load_file(path: str) -> str:
    """ファイルを読み込んでキャッシュする。"""
    return Path(path).read_text(encoding="utf-8")


def load_prompt(feature: str, name: str) -> str:
    """言語に応じたプロンプトファイルを読み込む。

    Args:
        feature: フィーチャー名 ("feature_a", "feature_b", "feature_c", "scoring")。
        name: プロンプト名（拡張子・言語サフィックスなし, e.g. "system", "user"）。

    Returns:
        プロンプトテンプレート文字列。
    """
    lang = get_language()
    path = _PROMPTS_DIR / feature / f"{name}_{lang}.md"
    if not path.exists():
        # フォールバック: 日本語
        path = _PROMPTS_DIR / feature / f"{name}_ja.md"
    return _load_file(str(path))


# ══════════════════════════════════════════════════════════════════════
#  システムプロンプト組み立て
# ══════════════════════════════════════════════════════════════════════


def get_system_prompt_a(config: AppConfig) -> str:
    """機能 A のシステムプロンプトを構築する。

    WorkIQ MCP が有効な場合にツールルールを挿入する。
    """
    if config.workiq_mcp.enabled:
        workiq_rules = load_prompt("feature_a", "workiq_rules")
    else:
        workiq_rules = ""

    base = load_prompt("feature_a", "system")
    return base.format(workiq_tool_rules=workiq_rules)


def get_system_prompt_b(run_count: int = 0) -> str:
    """機能 B のシステムプロンプトを構築する。

    run_count の偶奇で学習中/振り返りを交互に切り替える。
    """
    is_en = get_language() == "en"
    if run_count % 2 == 1:
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

    template = load_prompt("feature_b", "system")
    return template.format(
        quiz_pattern=quiz_pattern,
        quiz_pattern_instruction=quiz_pattern_instruction,
    )


def get_system_prompt_c() -> str:
    """機能 C のシステムプロンプトを返す。"""
    return load_prompt("feature_c", "system")


def get_user_prompt_a() -> str:
    """機能 A のユーザープロンプトテンプレートを返す。"""
    return load_prompt("feature_a", "user")


def get_user_prompt_b() -> str:
    """機能 B のユーザープロンプトテンプレートを返す。"""
    return load_prompt("feature_b", "user")


def get_discovery_appendix() -> str:
    """ディスカバリー回の追加指示テキストを返す。"""
    return load_prompt("feature_a", "discovery")


def get_scoring_prompt_template() -> str:
    """採点プロンプトテンプレートを返す。"""
    return load_prompt("scoring", "scoring")


# ══════════════════════════════════════════════════════════════════════
#  プロンプト構築ヘルパー（ファイル一覧・内容・スケジュール）
# ══════════════════════════════════════════════════════════════════════


def build_file_list_with_metadata(files: list) -> str:
    """ファイル一覧とメタデータのテキストを構築する。

    Args:
        files: ScannedFile リスト。

    Returns:
        ファイル一覧のフォーマット済みテキスト。
    """
    lines: list[str] = []
    for f in files:
        meta = f.metadata
        modified = (
            meta.modified_at.strftime("%Y-%m-%d %H:%M")
            if meta.modified_at
            else t("common.unknown")
        )
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


def build_file_contents(files: list, max_tokens: int) -> str:
    """ファイル内容テキストを構築する（トークン上限考慮）。

    Args:
        files: ScannedFile リスト。
        max_tokens: 最大トークン数。

    Returns:
        ファイル内容のフォーマット済みテキスト。
    """
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
                truncate_ratio = remaining / section_tokens
                truncated_len = int(len(section) * truncate_ratio)
                section = section[:truncated_len] + "\n\n" + t("main.truncated")
                result_parts.append(section)
            break

        result_parts.append(section)
        current_tokens += section_tokens

    return "\n---\n\n".join(result_parts)


def build_quiz_schedule_info(state_manager: StateManager) -> str:
    """間隔反復情報（quiz_schedule_info）を構築する。

    Args:
        state_manager: 状態マネージャ。

    Returns:
        クイズスケジュール情報テキスト。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    due_topics: list[str] = []

    for topic_key, entry in state_manager.state.quiz_history.items():
        if entry.next_quiz_at and entry.next_quiz_at <= today:
            last_result = ""
            if entry.results:
                last = entry.results[-1]
                q1 = (
                    t("main.q1_result_correct")
                    if last.q1_correct
                    else t("main.q1_result_incorrect")
                )
                last_result = t("main.last_result", q1=q1, q2=last.q2_evaluation)

            due_topics.append(
                f"- **{topic_key}** — Level {entry.level}, "
                f"{t('main.interval', days=entry.interval_days)}, {last_result}"
            )

    if due_topics:
        return t("main.topics_due_header") + "\n" + "\n".join(due_topics)
    else:
        return t("main.no_topics_due")
