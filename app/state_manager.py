"""内部状態ファイル（state.json）の読み書き・各種更新メソッドモジュール。

state.json の読み込み・書き込み・各フィールドの更新メソッドを提供する。
アトミック書き込みと .bak バックアップは utils モジュールを使用する。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.utils import atomic_write, safe_read_with_fallback

logger = logging.getLogger(__name__)

# デフォルトの state.json パス（settings ディレクトリ配下）
DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "settings" / "state.json"


@dataclass
class QuizResult:
    """クイズ1回分の回答結果。"""

    date: str = ""
    q1_correct: bool = False
    q2_evaluation: str = "poor"  # "good" | "partial" | "poor"
    pattern: str = ""  # "learning" | "review"


@dataclass
class QuizHistoryEntry:
    """トピックごとのクイズ履歴エントリ。"""

    last_quizzed_at: str = ""
    interval_days: int = 1
    level: int = 0
    next_quiz_at: str = ""
    results: list[QuizResult] = field(default_factory=list)


@dataclass
class PendingQuiz:
    """出題済み・未回答のクイズ情報。"""

    briefing_file: str = ""
    topic_key: str = ""
    pattern: str = ""  # "learning" | "review"
    created_at: str = ""


@dataclass
class AppState:
    """アプリケーション内部状態。"""

    run_count_a: int = 0
    run_count_b: int = 0
    last_run_at: str = ""
    output_folder_path: str = ""
    random_pick_history: list[str] = field(default_factory=list)
    pending_quizzes: list[PendingQuiz] = field(default_factory=list)
    quiz_history: dict[str, QuizHistoryEntry] = field(default_factory=dict)


# ── パース / シリアライズヘルパー ──


def _dict_to_quiz_result(d: dict[str, Any]) -> QuizResult:
    """辞書から QuizResult を生成する。"""
    return QuizResult(
        date=str(d.get("date", "")),
        q1_correct=bool(d.get("q1_correct", False)),
        q2_evaluation=str(d.get("q2_evaluation", "poor")),
        pattern=str(d.get("pattern", "")),
    )


def _dict_to_quiz_history_entry(d: dict[str, Any]) -> QuizHistoryEntry:
    """辞書から QuizHistoryEntry を生成する。"""
    results_raw = d.get("results", [])
    return QuizHistoryEntry(
        last_quizzed_at=str(d.get("last_quizzed_at", "")),
        interval_days=int(d.get("interval_days", 1)),
        level=int(d.get("level", 0)),
        next_quiz_at=str(d.get("next_quiz_at", "")),
        results=[_dict_to_quiz_result(r) for r in results_raw] if isinstance(results_raw, list) else [],
    )


def _dict_to_pending_quiz(d: dict[str, Any]) -> PendingQuiz:
    """辞書から PendingQuiz を生成する。"""
    return PendingQuiz(
        briefing_file=str(d.get("briefing_file", "")),
        topic_key=str(d.get("topic_key", "")),
        pattern=str(d.get("pattern", "")),
        created_at=str(d.get("created_at", "")),
    )


def _dict_to_app_state(d: dict[str, Any]) -> AppState:
    """辞書から AppState を生成する。"""
    pending_raw = d.get("pending_quizzes", [])
    history_raw = d.get("quiz_history", {})

    return AppState(
        run_count_a=int(d.get("run_count_a", 0)),
        run_count_b=int(d.get("run_count_b", 0)),
        last_run_at=str(d.get("last_run_at", "")),
        output_folder_path=str(d.get("output_folder_path", "")),
        random_pick_history=list(d.get("random_pick_history", [])),
        pending_quizzes=[_dict_to_pending_quiz(p) for p in pending_raw] if isinstance(pending_raw, list) else [],
        quiz_history={
            k: _dict_to_quiz_history_entry(v)
            for k, v in history_raw.items()
        } if isinstance(history_raw, dict) else {},
    )


def _quiz_result_to_dict(result: QuizResult) -> dict[str, Any]:
    """QuizResult を辞書に変換する。"""
    return {
        "date": result.date,
        "q1_correct": result.q1_correct,
        "q2_evaluation": result.q2_evaluation,
        "pattern": result.pattern,
    }


def _quiz_history_entry_to_dict(entry: QuizHistoryEntry) -> dict[str, Any]:
    """QuizHistoryEntry を辞書に変換する。"""
    return {
        "last_quizzed_at": entry.last_quizzed_at,
        "interval_days": entry.interval_days,
        "level": entry.level,
        "next_quiz_at": entry.next_quiz_at,
        "results": [_quiz_result_to_dict(r) for r in entry.results],
    }


def _pending_quiz_to_dict(pq: PendingQuiz) -> dict[str, Any]:
    """PendingQuiz を辞書に変換する。"""
    return {
        "briefing_file": pq.briefing_file,
        "topic_key": pq.topic_key,
        "pattern": pq.pattern,
        "created_at": pq.created_at,
    }


def _app_state_to_dict(state: AppState) -> dict[str, Any]:
    """AppState を辞書に変換する。"""
    return {
        "run_count_a": state.run_count_a,
        "run_count_b": state.run_count_b,
        "last_run_at": state.last_run_at,
        "output_folder_path": state.output_folder_path,
        "random_pick_history": state.random_pick_history,
        "pending_quizzes": [_pending_quiz_to_dict(p) for p in state.pending_quizzes],
        "quiz_history": {
            k: _quiz_history_entry_to_dict(v) for k, v in state.quiz_history.items()
        },
    }


def _parse_json(raw: str) -> AppState:
    """JSON 文字列をパースして AppState を返す。"""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("state.json のルートが辞書ではありません")
    return _dict_to_app_state(data)


# ── 公開 API ──


class StateManager:
    """state.json の読み書きと各種更新メソッドを提供するクラス。"""

    def __init__(self, state_path: Path | None = None) -> None:
        """StateManager を初期化する。

        Args:
            state_path: state.json のパス。None の場合はデフォルトパスを使用。
        """
        self._path = state_path or DEFAULT_STATE_PATH
        self._state = AppState()

    @property
    def state(self) -> AppState:
        """現在の AppState を返す。"""
        return self._state

    def load(
        self,
        *,
        notify_callback: Callable[[str, str], None] | None = None,
    ) -> AppState:
        """state.json を読み込む。失敗時は .bak → 初期状態の順でフォールバックする。

        Args:
            notify_callback: 警告通知コールバック（title, message）。

        Returns:
            読み込んだ AppState。
        """
        result = safe_read_with_fallback(
            file_path=self._path,
            parser=_parse_json,
            default_factory=AppState,
            notify_callback=notify_callback,
        )
        assert isinstance(result, AppState)
        self._state = result
        logger.info("状態ファイルを読み込みました: %s", self._path)
        return self._state

    def save(self) -> None:
        """現在の AppState を state.json に書き込む（アトミック書き込み + .bak バックアップ）。"""
        data = _app_state_to_dict(self._state)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        atomic_write(self._path, content, create_backup=True)
        logger.debug("状態ファイルを保存しました: %s", self._path)

    def increment_run_count(self, feature: str) -> None:
        """実行カウンタをインクリメントする。

        Args:
            feature: "a" または "b"。
        """
        if feature == "a":
            self._state.run_count_a += 1
            logger.debug("run_count_a = %d", self._state.run_count_a)
        elif feature == "b":
            self._state.run_count_b += 1
            logger.debug("run_count_b = %d", self._state.run_count_b)
        else:
            raise ValueError(f"不正な feature 値: {feature!r} （'a' または 'b' を指定）")

    def update_last_run(self) -> None:
        """最終実行日時を現在時刻に更新する。"""
        self._state.last_run_at = datetime.now().isoformat(timespec="seconds")
        logger.debug("last_run_at = %s", self._state.last_run_at)

    def set_output_folder_path(self, path: str) -> None:
        """出力フォルダパスを設定する。

        Args:
            path: 出力フォルダの絶対パス。
        """
        self._state.output_folder_path = path
        logger.debug("output_folder_path = %s", path)

    def update_random_pick_history(self, picked_files: list[str]) -> None:
        """ランダム選出履歴を更新する（直近3回分を保持）。

        Args:
            picked_files: 今回ランダム選出されたファイルの相対パスリスト。
        """
        self._state.random_pick_history = (
            picked_files + self._state.random_pick_history
        )[:3 * len(picked_files)] if picked_files else self._state.random_pick_history
        # 直近3回分 = 各回のランダム選出数 × 3 回分。簡略化して最大60件に制限
        self._state.random_pick_history = self._state.random_pick_history[:60]
        logger.debug("random_pick_history 更新: %d 件", len(self._state.random_pick_history))

    def add_pending_quiz(self, pending: PendingQuiz) -> None:
        """出題済みクイズを pending_quizzes に追加する。

        Args:
            pending: 追加する PendingQuiz。
        """
        self._state.pending_quizzes.append(pending)
        logger.debug("pending_quizzes に追加: %s", pending.topic_key)

    def remove_pending_quiz(self, topic_key: str) -> PendingQuiz | None:
        """指定トピックの pending_quizzes を削除して返す。

        Args:
            topic_key: 削除するトピックキー。

        Returns:
            削除した PendingQuiz。見つからない場合は None。
        """
        for i, pq in enumerate(self._state.pending_quizzes):
            if pq.topic_key == topic_key:
                removed = self._state.pending_quizzes.pop(i)
                logger.debug("pending_quizzes から削除: %s", topic_key)
                return removed
        logger.debug("pending_quizzes に該当なし: %s", topic_key)
        return None

    def clear_pending_quizzes(self) -> list[PendingQuiz]:
        """pending_quizzes をすべてクリアし、クリアした内容を返す。

        Returns:
            クリアした PendingQuiz のリスト。
        """
        cleared = list(self._state.pending_quizzes)
        self._state.pending_quizzes.clear()
        logger.debug("pending_quizzes をクリア: %d 件", len(cleared))
        return cleared

    def update_quiz_history(
        self,
        topic_key: str,
        result: QuizResult,
        new_level: int,
        new_interval_days: int,
        next_quiz_at: str,
    ) -> None:
        """クイズ履歴を更新する。

        Args:
            topic_key: トピックキー。
            result: 今回の QuizResult。
            new_level: 更新後のレベル。
            new_interval_days: 更新後の間隔日数。
            next_quiz_at: 次回出題日（YYYY-MM-DD 形式）。
        """
        if topic_key not in self._state.quiz_history:
            self._state.quiz_history[topic_key] = QuizHistoryEntry()

        entry = self._state.quiz_history[topic_key]
        entry.last_quizzed_at = result.date
        entry.level = new_level
        entry.interval_days = new_interval_days
        entry.next_quiz_at = next_quiz_at
        entry.results.append(result)
        logger.debug(
            "quiz_history 更新: %s (Level %d, 次回 %s)",
            topic_key,
            new_level,
            next_quiz_at,
        )

    def get_quiz_history(self, topic_key: str) -> QuizHistoryEntry | None:
        """指定トピックのクイズ履歴を取得する。

        Args:
            topic_key: トピックキー。

        Returns:
            QuizHistoryEntry。見つからない場合は None。
        """
        return self._state.quiz_history.get(topic_key)

    def get_pending_quizzes(self) -> list[PendingQuiz]:
        """未回答のクイズ一覧を取得する。

        Returns:
            PendingQuiz のリスト。
        """
        return list(self._state.pending_quizzes)
