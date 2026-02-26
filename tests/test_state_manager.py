"""state_manager モジュールのユニットテスト。"""

import json
from pathlib import Path

from app.state_manager import (
    AppState,
    PendingQuiz,
    QuizHistoryEntry,
    QuizResult,
    StateManager,
    _dict_to_app_state,
    _app_state_to_dict,
)


# ────────────────────────────────────────────
# dict ↔ AppState ラウンドトリップ
# ────────────────────────────────────────────

class TestDictRoundTrip:
    def test_default_roundtrip(self):
        state = AppState()
        d = _app_state_to_dict(state)
        restored = _dict_to_app_state(d)
        assert restored.run_count_a == 0
        assert restored.quiz_history == {}
        assert restored.pending_quizzes == []

    def test_with_data(self):
        state = AppState(
            run_count_a=5,
            run_count_b=3,
            last_run_at="2026-01-01T09:00:00",
            quiz_history={
                "topic1": QuizHistoryEntry(
                    level=2,
                    next_quiz_at="2026-02-01",
                    results=[QuizResult(date="2026-01-01", q1_correct=True, q2_evaluation="good")],
                )
            },
            pending_quizzes=[
                PendingQuiz(topic_key="t2", pattern="learning", created_at="2026-01-01"),
            ],
        )
        d = _app_state_to_dict(state)
        restored = _dict_to_app_state(d)
        assert restored.run_count_a == 5
        assert restored.quiz_history["topic1"].level == 2
        assert len(restored.quiz_history["topic1"].results) == 1
        assert restored.pending_quizzes[0].topic_key == "t2"


# ────────────────────────────────────────────
# StateManager mutation methods
# ────────────────────────────────────────────

class TestStateManagerMutations:
    def _make_sm(self) -> StateManager:
        sm = StateManager.__new__(StateManager)
        sm._state = AppState()
        sm._path = None  # type: ignore[assignment]
        return sm

    def test_increment_run_count_a(self):
        sm = self._make_sm()
        sm.increment_run_count("a")
        assert sm.state.run_count_a == 1

    def test_increment_run_count_b(self):
        sm = self._make_sm()
        sm.increment_run_count("b")
        assert sm.state.run_count_b == 1

    def test_increment_invalid_feature_raises(self):
        sm = self._make_sm()
        import pytest
        with pytest.raises(ValueError):
            sm.increment_run_count("c")

    def test_update_last_run(self):
        sm = self._make_sm()
        sm.update_last_run()
        assert sm.state.last_run_at != ""

    def test_set_output_folder_path(self):
        sm = self._make_sm()
        sm.set_output_folder_path("/out")
        assert sm.state.output_folder_path == "/out"

    def test_add_and_remove_pending_quiz(self):
        sm = self._make_sm()
        pq = PendingQuiz(topic_key="t1", pattern="learning")
        sm.add_pending_quiz(pq)
        assert len(sm.get_pending_quizzes()) == 1

        removed = sm.remove_pending_quiz("t1")
        assert removed is not None
        assert removed.topic_key == "t1"
        assert len(sm.get_pending_quizzes()) == 0

    def test_remove_nonexistent_returns_none(self):
        sm = self._make_sm()
        assert sm.remove_pending_quiz("nope") is None

    def test_clear_pending_quizzes(self):
        sm = self._make_sm()
        sm.add_pending_quiz(PendingQuiz(topic_key="a"))
        sm.add_pending_quiz(PendingQuiz(topic_key="b"))
        cleared = sm.clear_pending_quizzes()
        assert len(cleared) == 2
        assert sm.get_pending_quizzes() == []

    def test_update_quiz_history(self):
        sm = self._make_sm()
        result = QuizResult(date="2026-01-01", q1_correct=True, q2_evaluation="good")
        sm.update_quiz_history("topic1", result, new_level=2, new_interval_days=7, next_quiz_at="2026-01-08")
        entry = sm.get_quiz_history("topic1")
        assert entry is not None
        assert entry.level == 2
        assert entry.next_quiz_at == "2026-01-08"
        assert len(entry.results) == 1

    def test_get_quiz_history_missing(self):
        sm = self._make_sm()
        assert sm.get_quiz_history("nonexistent") is None

    def test_update_random_pick_history(self):
        sm = self._make_sm()
        sm.update_random_pick_history(["a.md", "b.md"])
        assert "a.md" in sm.state.random_pick_history
        assert "b.md" in sm.state.random_pick_history


# ────────────────────────────────────────────
# StateManager load / save (ファイル I/O)
# ────────────────────────────────────────────

class TestStateManagerIO:
    def test_save_and_load(self, tmp_path: Path):
        path = tmp_path / "state.json"
        sm = StateManager(path)
        sm.increment_run_count("a")
        sm.increment_run_count("a")
        sm.save()

        sm2 = StateManager(path)
        sm2.load()
        assert sm2.state.run_count_a == 2

    def test_load_nonexistent_returns_default(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        sm = StateManager(path)
        sm.load()
        assert sm.state.run_count_a == 0

    def test_load_corrupt_returns_default(self, tmp_path: Path):
        path = tmp_path / "state.json"
        path.write_text("NOT JSON!!!", encoding="utf-8")
        sm = StateManager(path)
        sm.load()
        assert sm.state.run_count_a == 0

    def test_roundtrip_with_quiz_history(self, tmp_path: Path):
        path = tmp_path / "state.json"
        sm = StateManager(path)
        result = QuizResult(date="2026-01-01", q1_correct=True, q2_evaluation="good")
        sm.update_quiz_history("t1", result, 3, 14, "2026-01-15")
        sm.save()

        sm2 = StateManager(path)
        sm2.load()
        entry = sm2.get_quiz_history("t1")
        assert entry is not None
        assert entry.level == 3
        assert entry.next_quiz_at == "2026-01-15"
