"""file_selector モジュールのユニットテスト。"""

from datetime import datetime, timedelta

from app.file_selector import (
    ScoredFile,
    SelectionResult,
    calculate_score,
    is_discovery_round,
    select_files,
    get_random_picked_paths,
    _calculate_random_weights,
)
from app.folder_scanner import FileMetadata, ScannedFile


def _make_file(
    relative_path: str = "test.md",
    modified_at: datetime | None = None,
    priority: str = "",
    deadline: str = "",
    unchecked_count: int = 0,
) -> ScannedFile:
    """テスト用の ScannedFile を作る。"""
    return ScannedFile(
        metadata=FileMetadata(
            relative_path=relative_path,
            absolute_path=f"/abs/{relative_path}",
            modified_at=modified_at,
            priority=priority,
            deadline=deadline,
            unchecked_count=unchecked_count,
        ),
        content="test content",
        raw_content="test raw",
    )


# ────────────────────────────────────────────
# calculate_score
# ────────────────────────────────────────────

class TestCalculateScore:
    def test_zero_score_no_attributes(self):
        f = _make_file()
        result = calculate_score(f, now=datetime(2026, 1, 10))
        assert result.score == 0

    def test_modified_today(self):
        now = datetime(2026, 6, 1, 12, 0)
        f = _make_file(modified_at=now - timedelta(hours=5))
        result = calculate_score(f, now=now)
        assert result.score_breakdown.get("modified_today") == 50

    def test_modified_within_week(self):
        now = datetime(2026, 6, 10)
        f = _make_file(modified_at=datetime(2026, 6, 5))
        result = calculate_score(f, now=now)
        assert result.score_breakdown.get("modified_week") == 30

    def test_modified_within_month(self):
        now = datetime(2026, 6, 30)
        f = _make_file(modified_at=datetime(2026, 6, 5))
        result = calculate_score(f, now=now)
        assert result.score_breakdown.get("modified_month") == 10

    def test_priority_high(self):
        f = _make_file(priority="high")
        result = calculate_score(f, now=datetime(2026, 1, 1))
        assert result.score_breakdown.get("priority_high") == 30

    def test_priority_medium(self):
        f = _make_file(priority="medium")
        result = calculate_score(f, now=datetime(2026, 1, 1))
        assert result.score_breakdown.get("priority_medium") == 15

    def test_deadline_3days(self):
        now = datetime(2026, 6, 1)
        f = _make_file(deadline="2026-06-03")
        result = calculate_score(f, now=now)
        assert result.score_breakdown.get("deadline_3days") == 25

    def test_deadline_7days(self):
        now = datetime(2026, 6, 1)
        f = _make_file(deadline="2026-06-06")
        result = calculate_score(f, now=now)
        assert result.score_breakdown.get("deadline_7days") == 15

    def test_unchecked_checkbox(self):
        f = _make_file(unchecked_count=3)
        result = calculate_score(f, now=datetime(2026, 1, 1))
        assert result.score_breakdown.get("has_unchecked") == 10

    def test_combined_score(self):
        now = datetime(2026, 6, 1, 12, 0)
        f = _make_file(
            modified_at=now - timedelta(hours=2),
            priority="high",
            deadline="2026-06-02",
            unchecked_count=1,
        )
        result = calculate_score(f, now=now)
        assert result.score == 50 + 30 + 25 + 10  # today + high + 3days + unchecked


# ────────────────────────────────────────────
# is_discovery_round
# ────────────────────────────────────────────

class TestIsDiscoveryRound:
    def test_normal_round(self):
        assert is_discovery_round(1, 5) is False
        assert is_discovery_round(3, 5) is False

    def test_discovery_round(self):
        assert is_discovery_round(5, 5) is True
        assert is_discovery_round(10, 5) is True

    def test_zero_run_count(self):
        assert is_discovery_round(0, 5) is False

    def test_zero_interval(self):
        assert is_discovery_round(5, 0) is False

    def test_negative_interval(self):
        assert is_discovery_round(5, -1) is False


# ────────────────────────────────────────────
# _calculate_random_weights
# ────────────────────────────────────────────

class TestCalculateRandomWeights:
    def test_old_file_gets_higher_weight(self):
        now = datetime(2026, 6, 1)
        old = _make_file("old.md", modified_at=datetime(2026, 1, 1))  # > 30 days
        new = _make_file("new.md", modified_at=datetime(2026, 5, 28))  # 4 days
        weights = _calculate_random_weights([old, new], now)
        assert weights[0] > weights[1]

    def test_unknown_modified_gets_default(self):
        weights = _calculate_random_weights([_make_file()], now=datetime(2026, 1, 1))
        assert weights[0] == 15.0


# ────────────────────────────────────────────
# select_files
# ────────────────────────────────────────────

class TestSelectFiles:
    def test_empty_files(self):
        result = select_files([], run_count=1)
        assert result.total_candidates == 0
        assert result.selected_files == []

    def test_fewer_than_max(self):
        files = [_make_file(f"f{i}.md") for i in range(5)]
        result = select_files(files, run_count=1)
        assert len(result.selected_files) == 5
        assert result.random_files == []

    def test_normal_round_splits(self):
        now = datetime(2026, 6, 1)
        files = [
            _make_file(
                f"f{i}.md",
                modified_at=now - timedelta(days=i),
            )
            for i in range(30)
        ]
        result = select_files(files, run_count=1, now=now)
        assert result.is_discovery is False
        assert len(result.top_files) == 17
        assert len(result.selected_files) <= 20

    def test_discovery_round_splits(self):
        now = datetime(2026, 6, 1)
        files = [
            _make_file(
                f"f{i}.md",
                modified_at=now - timedelta(days=i),
            )
            for i in range(30)
        ]
        result = select_files(files, run_count=5, discovery_interval=5, now=now)
        assert result.is_discovery is True
        assert len(result.top_files) == 5


# ────────────────────────────────────────────
# get_random_picked_paths
# ────────────────────────────────────────────

class TestGetRandomPickedPaths:
    def test_returns_paths(self):
        files = [_make_file("r1.md"), _make_file("r2.md")]
        result = SelectionResult(random_files=files)
        paths = get_random_picked_paths(result)
        assert paths == ["r1.md", "r2.md"]

    def test_empty(self):
        result = SelectionResult()
        assert get_random_picked_paths(result) == []
