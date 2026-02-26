"""関心度スコアリング・通常回/ディスカバリー回のファイル選定モジュール。

フォルダ走査結果に対して関心度スコアを算出し、
通常回またはディスカバリー回に応じてファイルを選定する。
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from app.folder_scanner import ScannedFile

logger = logging.getLogger(__name__)

# スコアリング定数
_SCORE_MODIFIED_TODAY = 50
_SCORE_MODIFIED_WEEK = 30
_SCORE_MODIFIED_MONTH = 10
_SCORE_PRIORITY_HIGH = 30
_SCORE_PRIORITY_MEDIUM = 15
_SCORE_DEADLINE_3DAYS = 25
_SCORE_DEADLINE_7DAYS = 15
_SCORE_HAS_UNCHECKED = 10

# 選定定数
_DEFAULT_MAX_FILES = 20
_NORMAL_TOP_COUNT = 17
_NORMAL_RANDOM_COUNT = 3
_DISCOVERY_TOP_COUNT = 5
_DISCOVERY_RANDOM_COUNT = 15

# ランダム重み付け: 未更新30日以上のファイルを優先する閾値
_OLD_FILE_THRESHOLD_DAYS = 30
_OLD_FILE_WEIGHT_MULTIPLIER = 3.0


@dataclass
class ScoredFile:
    """スコアリング結果を付与した ScannedFile。"""

    file: ScannedFile
    score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class SelectionResult:
    """ファイル選定の結果。"""

    selected_files: list[ScannedFile] = field(default_factory=list)
    top_files: list[ScannedFile] = field(default_factory=list)
    random_files: list[ScannedFile] = field(default_factory=list)
    is_discovery: bool = False
    total_candidates: int = 0


def calculate_score(file: ScannedFile, now: datetime | None = None) -> ScoredFile:
    """ファイルの関心度スコアを算出する。

    スコアリングルール:
    - 更新日時: 今日・昨日 +50 / 1週間以内 +30 / 1ヶ月以内 +10
    - priority: high +30 / medium +15
    - deadline: 3日以内 +25 / 7日以内 +15
    - 未完了チェックボックス: 1つ以上 +10

    Args:
        file: 走査済みファイル。
        now: 現在時刻（テスト用）。None の場合は datetime.now() を使用。

    Returns:
        スコアリング結果。
    """
    if now is None:
        now = datetime.now()

    score = 0
    breakdown: dict[str, int] = {}
    meta = file.metadata

    # S1: 更新日時スコア
    if meta.modified_at:
        delta = now - meta.modified_at
        if delta <= timedelta(days=1):
            score += _SCORE_MODIFIED_TODAY
            breakdown["modified_today"] = _SCORE_MODIFIED_TODAY
        elif delta <= timedelta(days=7):
            score += _SCORE_MODIFIED_WEEK
            breakdown["modified_week"] = _SCORE_MODIFIED_WEEK
        elif delta <= timedelta(days=30):
            score += _SCORE_MODIFIED_MONTH
            breakdown["modified_month"] = _SCORE_MODIFIED_MONTH

    # S3: priority スコア
    priority = meta.priority.lower()
    if priority == "high":
        score += _SCORE_PRIORITY_HIGH
        breakdown["priority_high"] = _SCORE_PRIORITY_HIGH
    elif priority == "medium":
        score += _SCORE_PRIORITY_MEDIUM
        breakdown["priority_medium"] = _SCORE_PRIORITY_MEDIUM

    # S4: deadline スコア
    if meta.deadline:
        try:
            deadline_dt = datetime.strptime(meta.deadline, "%Y-%m-%d")
            days_until = (deadline_dt - now).days
            if 0 <= days_until <= 3:
                score += _SCORE_DEADLINE_3DAYS
                breakdown["deadline_3days"] = _SCORE_DEADLINE_3DAYS
            elif 0 <= days_until <= 7:
                score += _SCORE_DEADLINE_7DAYS
                breakdown["deadline_7days"] = _SCORE_DEADLINE_7DAYS
        except ValueError:
            logger.debug("deadline のパースに失敗: %s", meta.deadline)

    # S6: 未完了チェックボックス
    if meta.unchecked_count > 0:
        score += _SCORE_HAS_UNCHECKED
        breakdown["has_unchecked"] = _SCORE_HAS_UNCHECKED

    return ScoredFile(file=file, score=score, score_breakdown=breakdown)


def _calculate_random_weights(
    files: list[ScannedFile],
    now: datetime | None = None,
) -> list[float]:
    """ランダム抽出の重みを計算する。

    最終更新が古いほど重みが高い（未更新30日以上のファイルを優先）。

    Args:
        files: 対象ファイルリスト。
        now: 現在時刻。

    Returns:
        各ファイルの重みリスト。
    """
    if now is None:
        now = datetime.now()

    weights: list[float] = []
    for f in files:
        if f.metadata.modified_at:
            days_since = (now - f.metadata.modified_at).days
            if days_since >= _OLD_FILE_THRESHOLD_DAYS:
                weights.append(float(days_since) * _OLD_FILE_WEIGHT_MULTIPLIER)
            else:
                weights.append(max(1.0, float(days_since)))
        else:
            # 更新日時不明の場合は中程度の重み
            weights.append(15.0)

    return weights


def is_discovery_round(run_count: int, discovery_interval: int) -> bool:
    """ディスカバリー回かどうかを判定する。

    Args:
        run_count: 現在の実行カウント。
        discovery_interval: ディスカバリー間隔（N回に1回）。

    Returns:
        ディスカバリー回の場合 True。
    """
    if discovery_interval <= 0:
        return False
    return run_count > 0 and run_count % discovery_interval == 0


def select_files(
    files: list[ScannedFile],
    *,
    run_count: int,
    discovery_interval: int = 5,
    max_files: int = _DEFAULT_MAX_FILES,
    random_pick_history: Sequence[str] = (),
    now: datetime | None = None,
) -> SelectionResult:
    """ファイルを選定する（関心度スコアリング + 通常回/ディスカバリー回のハイブリッド選定）。

    通常回: スコア上位17件 + ランダム3件
    ディスカバリー回: スコア上位5件 + ランダム15件

    Args:
        files: 走査済み全ファイルリスト。
        run_count: 現在の実行カウント（ディスカバリー回の判定に使用）。
        discovery_interval: ディスカバリー間隔（N回に1回）。
        max_files: 選定最大ファイル数。
        random_pick_history: 直近のランダム選出履歴（重複抑止用）。
        now: 現在時刻（テスト用）。

    Returns:
        SelectionResult。
    """
    if now is None:
        now = datetime.now()

    if not files:
        logger.warning("選定対象ファイルが0件です")
        return SelectionResult(total_candidates=0)

    # ファイル数が max_files 以下なら全件返す
    if len(files) <= max_files:
        logger.info("全ファイル数 (%d) が max_files (%d) 以下のため全件選定", len(files), max_files)
        return SelectionResult(
            selected_files=list(files),
            top_files=list(files),
            random_files=[],
            is_discovery=False,
            total_candidates=len(files),
        )

    # 全ファイルをスコアリング
    scored = [calculate_score(f, now) for f in files]
    scored.sort(key=lambda sf: sf.score, reverse=True)

    # ディスカバリー回の判定
    discovery = is_discovery_round(run_count, discovery_interval)
    if discovery:
        top_count = _DISCOVERY_TOP_COUNT
        random_count = _DISCOVERY_RANDOM_COUNT
        logger.info("ディスカバリー回（run_count=%d）: 上位%d + ランダム%d", run_count, top_count, random_count)
    else:
        top_count = _NORMAL_TOP_COUNT
        random_count = _NORMAL_RANDOM_COUNT
        logger.info("通常回（run_count=%d）: 上位%d + ランダム%d", run_count, top_count, random_count)

    # 合計が max_files を超えないように調整
    top_count = min(top_count, max_files)
    random_count = min(random_count, max_files - top_count)

    # 上位ファイル選出
    top_scored = scored[:top_count]
    top_files = [sf.file for sf in top_scored]
    top_paths = {sf.file.metadata.relative_path for sf in top_scored}

    # ランダム候補（上位選出外 + 直近履歴除外）
    history_set = set(random_pick_history)
    random_candidates = [
        sf.file
        for sf in scored[top_count:]
        if sf.file.metadata.relative_path not in history_set
    ]

    # 履歴除外で候補が足りない場合は履歴ありも含める
    if len(random_candidates) < random_count:
        additional = [
            sf.file
            for sf in scored[top_count:]
            if sf.file.metadata.relative_path in history_set
            and sf.file.metadata.relative_path not in top_paths
        ]
        random_candidates.extend(additional)

    # ランダム重み付け抽出
    random_files: list[ScannedFile] = []
    if random_candidates and random_count > 0:
        weights = _calculate_random_weights(random_candidates, now)
        actual_count = min(random_count, len(random_candidates))
        try:
            random_files = random.choices(
                random_candidates,
                weights=weights,
                k=actual_count,
            )
            # 重複排除（random.choices は重複あり）
            seen: set[str] = set()
            unique_random: list[ScannedFile] = []
            for f in random_files:
                if f.metadata.relative_path not in seen:
                    seen.add(f.metadata.relative_path)
                    unique_random.append(f)
            random_files = unique_random

            # 不足分を補充
            if len(random_files) < actual_count:
                remaining = [
                    c for c in random_candidates
                    if c.metadata.relative_path not in seen
                    and c.metadata.relative_path not in top_paths
                ]
                for f in remaining[:actual_count - len(random_files)]:
                    random_files.append(f)

        except ValueError:
            # 重みが全て0等の場合、単純ランダムにフォールバック
            random_files = random.sample(random_candidates, min(actual_count, len(random_candidates)))

    # 結果統合
    selected = top_files + random_files

    logger.info(
        "ファイル選定完了: 上位%d件 + ランダム%d件 = 合計%d件 (候補%d件中)",
        len(top_files),
        len(random_files),
        len(selected),
        len(files),
    )

    return SelectionResult(
        selected_files=selected,
        top_files=top_files,
        random_files=random_files,
        is_discovery=discovery,
        total_candidates=len(files),
    )


def get_random_picked_paths(result: SelectionResult) -> list[str]:
    """選定結果からランダム選出されたファイルの相対パスリストを返す。

    state.json の random_pick_history 更新用。

    Args:
        result: ファイル選定結果。

    Returns:
        ランダム選出されたファイルの相対パスリスト。
    """
    return [f.metadata.relative_path for f in result.random_files]
