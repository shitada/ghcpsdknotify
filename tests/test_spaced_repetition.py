"""spaced_repetition モジュールのユニットテスト。"""

from datetime import datetime

from app.spaced_repetition import (
    calculate_next_level,
    calculate_next_quiz_date,
    get_due_topics,
    get_interval_days,
    build_quiz_schedule_info,
    update_after_scoring,
)
from app.state_manager import AppState, QuizHistoryEntry, QuizResult, StateManager
from app.config import SpacedRepetitionConfig


# ────────────────────────────────────────────
# calculate_next_level
# ────────────────────────────────────────────

class TestCalculateNextLevel:
    def test_upgrade_on_q1_correct_q2_good(self):
        assert calculate_next_level(True, "good", 0) == 1
        assert calculate_next_level(True, "good", 3) == 4
        assert calculate_next_level(True, "good", 5) == 5  # max

    def test_downgrade_on_q1_incorrect(self):
        assert calculate_next_level(False, "good", 3) == 0
        assert calculate_next_level(False, "partial", 5) == 0

    def test_downgrade_on_q2_poor(self):
        assert calculate_next_level(True, "poor", 3) == 0

    def test_stay_on_q1_correct_q2_partial(self):
        assert calculate_next_level(True, "partial", 3) == 3

    def test_max_level_clamped(self):
        assert calculate_next_level(True, "good", 5, max_level=5) == 5
        assert calculate_next_level(True, "good", 2, max_level=3) == 3

    def test_custom_max_level(self):
        assert calculate_next_level(True, "good", 9, max_level=10) == 10


# ────────────────────────────────────────────
# calculate_next_quiz_date
# ────────────────────────────────────────────

class TestCalculateNextQuizDate:
    def test_level_0_default_intervals(self):
        now = datetime(2026, 1, 10)
        result = calculate_next_quiz_date(0, now=now)
        assert result == "2026-01-11"  # +1 day

    def test_level_3_default_intervals(self):
        now = datetime(2026, 1, 10)
        result = calculate_next_quiz_date(3, now=now)
        assert result == "2026-01-24"  # +14 days

    def test_custom_intervals(self):
        now = datetime(2026, 3, 1)
        result = calculate_next_quiz_date(1, [2, 5, 10], now=now)
        assert result == "2026-03-06"  # +5 days

    def test_level_beyond_intervals_uses_last(self):
        now = datetime(2026, 6, 1)
        result = calculate_next_quiz_date(100, [1, 3, 7], now=now)
        assert result == "2026-06-08"  # +7 (last entry)


# ────────────────────────────────────────────
# get_interval_days
# ────────────────────────────────────────────

class TestGetIntervalDays:
    def test_default_intervals(self):
        assert get_interval_days(0) == 1
        assert get_interval_days(1) == 3
        assert get_interval_days(5) == 60

    def test_custom_intervals(self):
        assert get_interval_days(0, [10, 20]) == 10
        assert get_interval_days(1, [10, 20]) == 20

    def test_clamped_to_last(self):
        assert get_interval_days(99, [5, 10]) == 10


# ────────────────────────────────────────────
# get_due_topics / build_quiz_schedule_info
# ────────────────────────────────────────────

def _make_state_manager_with_history(
    history: dict[str, QuizHistoryEntry],
) -> StateManager:
    """テスト用に quiz_history を持つ StateManager を作る。"""
    sm = StateManager.__new__(StateManager)
    sm._state = AppState(quiz_history=history)
    sm._path = None  # type: ignore[assignment]
    return sm


class TestGetDueTopics:
    def test_due_topic_returned(self):
        sm = _make_state_manager_with_history({
            "topic_a": QuizHistoryEntry(next_quiz_at="2026-01-01", level=1),
            "topic_b": QuizHistoryEntry(next_quiz_at="2026-12-31", level=2),
        })
        due = get_due_topics(sm, today="2026-06-01")
        keys = [d["topic_key"] for d in due]
        assert "topic_a" in keys
        assert "topic_b" not in keys

    def test_no_due_topics(self):
        sm = _make_state_manager_with_history({
            "topic_a": QuizHistoryEntry(next_quiz_at="2099-01-01"),
        })
        assert get_due_topics(sm, today="2026-01-01") == []

    def test_empty_history(self):
        sm = _make_state_manager_with_history({})
        assert get_due_topics(sm, today="2026-01-01") == []


class TestBuildQuizScheduleInfo:
    def test_no_due_returns_message(self):
        sm = _make_state_manager_with_history({})
        info = build_quiz_schedule_info(sm, today="2026-01-01")
        assert "期限到来トピックなし" in info

    def test_due_topics_formatted(self):
        sm = _make_state_manager_with_history({
            "topic_a": QuizHistoryEntry(
                next_quiz_at="2026-01-01", level=2, interval_days=7
            ),
        })
        info = build_quiz_schedule_info(sm, today="2026-06-01")
        assert "topic_a" in info
        assert "Level 2" in info


# ────────────────────────────────────────────
# update_after_scoring
# ────────────────────────────────────────────

class TestUpdateAfterScoring:
    def test_upgrade(self):
        sm = _make_state_manager_with_history({
            "t1": QuizHistoryEntry(level=1),
        })
        cfg = SpacedRepetitionConfig()
        result = update_after_scoring(
            sm, "t1", True, "good", cfg, now=datetime(2026, 1, 1)
        )
        assert result["level_change"] == "upgrade"
        assert result["new_level"] == 2

    def test_downgrade(self):
        sm = _make_state_manager_with_history({
            "t1": QuizHistoryEntry(level=3),
        })
        cfg = SpacedRepetitionConfig()
        result = update_after_scoring(
            sm, "t1", False, "good", cfg, now=datetime(2026, 1, 1)
        )
        assert result["level_change"] == "downgrade"
        assert result["new_level"] == 0

    def test_same(self):
        sm = _make_state_manager_with_history({
            "t1": QuizHistoryEntry(level=2),
        })
        cfg = SpacedRepetitionConfig()
        result = update_after_scoring(
            sm, "t1", True, "partial", cfg, now=datetime(2026, 1, 1)
        )
        assert result["level_change"] == "same"
        assert result["new_level"] == 2

    def test_new_topic(self):
        sm = _make_state_manager_with_history({})
        cfg = SpacedRepetitionConfig()
        result = update_after_scoring(
            sm, "new_topic", True, "good", cfg, now=datetime(2026, 1, 1)
        )
        assert result["new_level"] == 1
        assert result["level_change"] == "upgrade"
