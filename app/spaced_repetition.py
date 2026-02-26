"""間隔反復（Spaced Repetition）アルゴリズムモジュール。

SM-2 を簡略化したレベル制（Level 0〜5）で、トピックごとの
出題間隔を動的に調整する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.config import SpacedRepetitionConfig
from app.i18n import t
from app.state_manager import QuizHistoryEntry, StateManager

logger = logging.getLogger(__name__)

# デフォルト間隔表（Level → 日数）
_DEFAULT_INTERVALS = [1, 3, 7, 14, 30, 60]


def calculate_next_level(
    q1_correct: bool,
    q2_evaluation: str,
    current_level: int,
    max_level: int = 5,
) -> int:
    """クイズ結果に基づいて次のレベルを計算する。

    - 昇格: Q1 正解 かつ Q2 good → Level +1（最大 max_level）
    - 降格: Q1 不正解 または Q2 poor → Level 0
    - 据え置き: Q2 partial → 現在の Level を維持

    Args:
        q1_correct: Q1（4択）が正解かどうか。
        q2_evaluation: Q2（記述）の評価（"good" | "partial" | "poor"）。
        current_level: 現在のレベル。
        max_level: レベル上限。

    Returns:
        次のレベル値。
    """
    # 降格条件: Q1 不正解 or Q2 poor
    if not q1_correct or q2_evaluation == "poor":
        logger.debug(
            "降格: Level %d → 0 (q1_correct=%s, q2=%s)",
            current_level,
            q1_correct,
            q2_evaluation,
        )
        return 0

    # 昇格条件: Q1 正解 かつ Q2 good
    if q1_correct and q2_evaluation == "good":
        new_level = min(current_level + 1, max_level)
        logger.debug(
            "昇格: Level %d → %d (q1_correct=%s, q2=%s)",
            current_level,
            new_level,
            q1_correct,
            q2_evaluation,
        )
        return new_level

    # 据え置き（Q2 partial 等）
    logger.debug(
        "据え置き: Level %d (q1_correct=%s, q2=%s)",
        current_level,
        q1_correct,
        q2_evaluation,
    )
    return current_level


def calculate_next_quiz_date(
    level: int,
    intervals: list[int] | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """指定レベルに基づいて次回出題日を計算する。

    Args:
        level: 現在のレベル（0〜5）。
        intervals: レベルごとの間隔日数リスト。None の場合はデフォルト値を使用。
        now: 基準日時。None の場合は datetime.now() を使用。

    Returns:
        次回出題日（YYYY-MM-DD 形式）。
    """
    if intervals is None:
        intervals = _DEFAULT_INTERVALS
    if now is None:
        now = datetime.now()

    # レベルが intervals の範囲外の場合は最後の値を使用
    idx = min(level, len(intervals) - 1)
    interval_days = intervals[idx]

    next_date = now + timedelta(days=interval_days)
    return next_date.strftime("%Y-%m-%d")


def get_interval_days(
    level: int,
    intervals: list[int] | None = None,
) -> int:
    """指定レベルの間隔日数を取得する。

    Args:
        level: レベル（0〜5）。
        intervals: 間隔日数リスト。

    Returns:
        間隔日数。
    """
    if intervals is None:
        intervals = _DEFAULT_INTERVALS

    idx = min(level, len(intervals) - 1)
    return intervals[idx]


def get_due_topics(
    state_manager: StateManager,
    *,
    today: str | None = None,
) -> list[dict[str, Any]]:
    """出題期限が到来したトピック一覧を取得する。

    Args:
        state_manager: 状態マネージャ。
        today: 基準日（YYYY-MM-DD 形式）。None の場合は今日。

    Returns:
        期限到来トピックのリスト。各要素は:
        - topic_key (str)
        - level (int)
        - interval_days (int)
        - last_result (QuizResult | None)
    """
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    due: list[dict[str, Any]] = []

    for topic_key, entry in state_manager.state.quiz_history.items():
        if entry.next_quiz_at and entry.next_quiz_at <= today:
            last_result = entry.results[-1] if entry.results else None
            due.append(
                {
                    "topic_key": topic_key,
                    "level": entry.level,
                    "interval_days": entry.interval_days,
                    "last_result": last_result,
                }
            )

    logger.debug("期限到来トピック: %d 件", len(due))
    return due


def build_quiz_schedule_info(
    state_manager: StateManager,
    *,
    today: str | None = None,
) -> str:
    """間隔反復情報テキストを構築する。

    next_quiz_at <= today のトピック一覧を生成する。

    Args:
        state_manager: 状態マネージャ。
        today: 基準日（YYYY-MM-DD 形式）。None の場合は今日。

    Returns:
        クイズスケジュール情報テキスト。
    """
    due_topics = get_due_topics(state_manager, today=today)

    if not due_topics:
        return t("sr.no_topics_due")

    lines = [t("sr.topics_due_header")]
    for topic in due_topics:
        topic_key = topic["topic_key"]
        level = topic["level"]
        interval_days = topic["interval_days"]

        # 前回結果サマリ
        last_result = topic["last_result"]
        result_str = ""
        if last_result is not None:
            q1 = t("sr.correct") if last_result.q1_correct else t("sr.incorrect")  # type: ignore[union-attr]
            result_str = t("sr.last_result", q1=q1, q2=last_result.q2_evaluation)  # type: ignore[union-attr]

        lines.append(
            f"- **{topic_key}** — Level {level}, "
            f"{t('sr.interval', days=interval_days)}, {result_str}"
        )

    return "\n".join(lines)


def update_after_scoring(
    state_manager: StateManager,
    topic_key: str,
    q1_correct: bool,
    q2_evaluation: str,
    sr_config: SpacedRepetitionConfig,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """採点結果に基づいて間隔反復の状態を更新する。

    state_manager.update_quiz_history() を呼び出して quiz_history を更新し、
    pending_quizzes から該当トピックを削除する。

    Args:
        state_manager: 状態マネージャ。
        topic_key: トピックキー。
        q1_correct: Q1 正解かどうか。
        q2_evaluation: Q2 評価。
        sr_config: 間隔反復設定。
        now: 基準日時。

    Returns:
        更新情報:
        - new_level (int)
        - new_interval_days (int)
        - next_quiz_at (str)
        - level_change (str): "upgrade" | "downgrade" | "same"
    """
    if now is None:
        now = datetime.now()

    # 現在のレベルを取得
    entry = state_manager.get_quiz_history(topic_key)
    current_level = entry.level if entry else 0

    # 新しいレベルを計算
    new_level = calculate_next_level(
        q1_correct, q2_evaluation, current_level, sr_config.max_level
    )

    # 間隔日数と次回出題日を計算
    new_interval_days = get_interval_days(new_level, sr_config.intervals)
    next_quiz_at = calculate_next_quiz_date(
        new_level, sr_config.intervals, now=now
    )

    # レベル変動の判定
    if new_level > current_level:
        level_change = "upgrade"
    elif new_level < current_level:
        level_change = "downgrade"
    else:
        level_change = "same"

    logger.info(
        "間隔反復更新: %s — Level %d → %d (%s), 次回 %s",
        topic_key,
        current_level,
        new_level,
        level_change,
        next_quiz_at,
    )

    return {
        "new_level": new_level,
        "new_interval_days": new_interval_days,
        "next_quiz_at": next_quiz_at,
        "level_change": level_change,
    }
