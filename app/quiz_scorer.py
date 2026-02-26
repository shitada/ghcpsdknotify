"""クイズ採点モジュール。

copilot_client.score_quiz() 経由で Q1+Q2 を一括採点し、
結果を state_manager と output_writer に反映する。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import AppConfig
from app.copilot_client import CopilotClientWrapper
from app.i18n import get_language, t
from app.output_writer import append_quiz_result, format_quiz_result_section
from app.spaced_repetition import update_after_scoring
from app.state_manager import PendingQuiz, QuizResult, StateManager

logger = logging.getLogger(__name__)

# 採点プロンプトテンプレート（仕様書 3.11 準拠）
_SCORING_PROMPT_TEMPLATE = """\
以下のクイズの採点を行ってください。
ソース資料と問題文に基づいて、ユーザーの回答を評価してください。

## ソース資料
{source_content}

## Q1（4択）
### 問題
{q1_question_text}
### ユーザーの選択
{q1_user_choice}

## Q2（記述）
### 問題
{q2_question_text}
### ユーザーの回答
{q2_user_answer}

## 採点基準
- Q1: 正解/不正解を判定し、正解の選択肢と解説を付けてください。
- Q2:
  - good: 核心的なポイントを正しく説明できている
  - partial: 方向性は合っているが重要な要素が欠けている
  - poor: 根本的に誤っている、または回答になっていない

## 出力形式（JSON のみ出力）
{{
  "q1_correct": true,
  "q1_correct_answer": "B",
  "q1_explanation": "解説文…",
  "q2_evaluation": "good|partial|poor",
  "q2_feedback": "フィードバックコメント"
}}
"""

_SCORING_PROMPT_TEMPLATE_EN = """\
Please score the following quiz.
Evaluate the user's answers based on the source material and questions.

## Source Material
{source_content}

## Q1 (Multiple Choice)
### Question
{q1_question_text}
### User's Choice
{q1_user_choice}

## Q2 (Free-form)
### Question
{q2_question_text}
### User's Answer
{q2_user_answer}

## Scoring Criteria
- Q1: Determine correct/incorrect, and provide the correct choice with an explanation.
- Q2:
  - good: Correctly explains the core points
  - partial: On the right track but missing important elements
  - poor: Fundamentally wrong or not an answer

## Output Format (JSON only)
{{
  "q1_correct": true,
  "q1_correct_answer": "B",
  "q1_explanation": "Explanation text...",
  "q2_evaluation": "good|partial|poor",
  "q2_feedback": "Feedback comment"
}}
"""


@dataclass
class QuizScoreResult:
    """1トピック分の採点結果。"""

    topic_key: str
    q1_correct: bool
    q1_correct_answer: str
    q1_explanation: str
    q2_evaluation: str
    q2_feedback: str
    new_level: int
    new_interval_days: int
    next_quiz_at: str
    level_change: str  # "upgrade" | "downgrade" | "same"


def _read_source_content(topic_key: str, input_folders: list[str]) -> str:
    """topic_key からソース MD ファイルを読み込む。

    topic_key は "{ファイルの相対パス}#{セクション識別子}" 形式。
    ファイルの相対パス部分から元の MD ファイルを特定して読み込む。

    Args:
        topic_key: トピックキー。
        input_folders: 入力フォルダパスのリスト。

    Returns:
        ソース MD ファイルの内容。読み込み失敗時は空文字列。
    """
    # topic_key からファイルパスを抽出
    file_relative = topic_key.split("#")[0] if "#" in topic_key else topic_key

    # input_folders 配下でファイルを探索
    for folder in input_folders:
        candidate = Path(folder) / file_relative
        if candidate.exists() and candidate.is_file():
            try:
                content = candidate.read_text(encoding="utf-8")
                logger.debug("ソース MD 読み込み: %s", candidate)
                return content
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("ソース MD 読み込み失敗: %s — %s", candidate, e)
                return ""

    logger.warning("ソース MD が見つかりません: %s", file_relative)
    return ""


def _extract_quiz_questions(
    briefing_content: str,
    topic_key: str,
) -> tuple[str, str]:
    """ブリーフィング MD からトピックの Q1/Q2 問題文を抽出する。

    Args:
        briefing_content: ブリーフィング MD テキスト。
        topic_key: トピックキー。

    Returns:
        (Q1 問題文+選択肢, Q2 問題文) のタプル。
    """
    # topic_key コメントの位置を特定
    topic_pattern = re.escape(topic_key)
    marker = re.search(
        rf"<!--\s*topic_key:\s*{topic_pattern}\s*-->",
        briefing_content,
    )

    if not marker:
        logger.warning("topic_key が見つかりません: %s", topic_key)
        return ("", "")

    # マーカー以降のテキストを取得
    section_text = briefing_content[marker.end() :]

    # Quiz Results セクションがあればそこで区切る
    results_marker = re.search(r"^## 📝 Quiz Results", section_text, re.MULTILINE)
    if results_marker:
        section_text = section_text[: results_marker.start()]

    # 次の topic_key マーカーまでを対象範囲とするが、
    # Q1/Q2 見出し直前のマーカーはスキップして範囲に含める
    # （LLM が Q1/Q2 に個別マーカーを付ける場合がある）
    search_pos = 0
    while True:
        next_marker = re.search(
            r"<!--\s*topic_key:\s*(.+?)\s*-->",
            section_text[search_pos:],
        )
        if not next_marker:
            break
        # マーカー直後の ### 行を確認
        after_marker = section_text[search_pos + next_marker.end():]
        heading_match = re.match(r"\s*\n\s*###\s*(Q[12]\b)", after_marker)
        if heading_match:
            # Q1/Q2 見出しなのでスキップして続行
            search_pos += next_marker.end()
            continue
        # 別トピックのマーカー → ここで区切る
        section_text = section_text[: search_pos + next_marker.start()]
        break

    # Q1 と Q2 を分割
    q1_text = ""
    q2_text = ""

    # Q1 を探す（「Q1」「**Q1**」「## Q1」「### Q1」等のパターン）
    q1_match = re.search(
        r"(?:^|\n)\s*(?:#{1,4}\s+)?(?:\*\*)?Q1[^\n]*\n(.*?)(?=(?:\n\s*(?:#{1,4}\s+)?(?:\*\*)?Q2[^a-zA-Z0-9])|$)",
        section_text,
        re.DOTALL | re.IGNORECASE,
    )
    if q1_match:
        q1_text = q1_match.group(0).strip()

    # Q2 を探す
    q2_match = re.search(
        r"(?:^|\n)\s*(?:#{1,4}\s+)?(?:\*\*)?Q2[^\n]*\n(.*?)$",
        section_text,
        re.DOTALL | re.IGNORECASE,
    )
    if q2_match:
        q2_text = q2_match.group(0).strip()

    return (q1_text, q2_text)


async def _score_topic(
    copilot_client: CopilotClientWrapper,
    topic_key: str,
    q1_choice: str,
    q2_answer: str,
    briefing_file: str,
    input_folders: list[str],
) -> dict[str, Any]:
    """1トピックの採点を Copilot SDK 経由で行う。

    Args:
        copilot_client: Copilot クライアントラッパー。
        topic_key: トピックキー。
        q1_choice: ユーザーの Q1 選択（A/B/C/D）。
        q2_answer: ユーザーの Q2 回答テキスト。
        briefing_file: ブリーフィング MD ファイルパス。
        input_folders: 入力フォルダリスト。

    Returns:
        採点結果辞書。
    """
    # ソース MD 読み込み
    source_content = _read_source_content(topic_key, input_folders)
    if not source_content:
        source_content = t("scorer.source_not_found")

    # ブリーフィング MD から問題文を抽出
    briefing_content = ""
    try:
        briefing_content = Path(briefing_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("ブリーフィング MD 読み込み失敗: %s — %s", briefing_file, e)

    q1_question_text, q2_question_text = _extract_quiz_questions(
        briefing_content, topic_key
    )

    if not q1_question_text:
        q1_question_text = t("scorer.question_extraction_failed")
    if not q2_question_text:
        q2_question_text = t("scorer.question_extraction_failed")

    # 採点プロンプト構築
    template = (
        _SCORING_PROMPT_TEMPLATE_EN if get_language() == "en"
        else _SCORING_PROMPT_TEMPLATE
    )
    scoring_prompt = template.format(
        source_content=source_content,
        q1_question_text=q1_question_text,
        q1_user_choice=q1_choice,
        q2_question_text=q2_question_text,
        q2_user_answer=q2_answer,
    )

    # Copilot SDK で採点
    result = await copilot_client.score_quiz(scoring_prompt)
    return result


def score(
    topic_key: str,
    q1_choice: str,
    q2_answer: str,
    briefing_file: str,
    *,
    copilot_client: CopilotClientWrapper,
    state_manager: StateManager,
    app_config: AppConfig,
) -> QuizScoreResult:
    """1トピックの Q1+Q2 を一括採点し、結果を反映する。

    同期関数。内部で asyncio.run() を使用する。

    Args:
        topic_key: トピックキー。
        q1_choice: ユーザーの Q1 選択。
        q2_answer: ユーザーの Q2 回答テキスト。
        briefing_file: ブリーフィング MD ファイルパス。
        copilot_client: Copilot クライアントラッパー。
        state_manager: 状態マネージャ。
        app_config: アプリケーション設定。

    Returns:
        QuizScoreResult。

    Raises:
        Exception: 採点に失敗した場合。
    """
    logger.info("採点開始: %s", topic_key)

    # 非同期で採点を実行
    scoring_result = asyncio.run(
        _score_topic(
            copilot_client,
            topic_key,
            q1_choice,
            q2_answer,
            briefing_file,
            app_config.input_folders,
        )
    )

    q1_correct = bool(scoring_result.get("q1_correct", False))
    q1_correct_answer = str(scoring_result.get("q1_correct_answer", ""))
    q1_explanation = str(scoring_result.get("q1_explanation", ""))
    q2_evaluation = str(scoring_result.get("q2_evaluation", "poor"))
    q2_feedback = str(scoring_result.get("q2_feedback", ""))

    # 間隔反復の更新
    sr_config = app_config.quiz.spaced_repetition
    now = datetime.now()

    sr_update = update_after_scoring(
        state_manager, topic_key, q1_correct, q2_evaluation, sr_config, now=now
    )

    new_level = int(sr_update["new_level"])
    new_interval_days = int(sr_update["new_interval_days"])
    next_quiz_at = str(sr_update["next_quiz_at"])
    level_change = str(sr_update["level_change"])

    # pending_quizzes を取得して pattern を特定
    pending = state_manager.remove_pending_quiz(topic_key)
    pattern = pending.pattern if pending else "learning"

    # quiz_history に結果を記録
    quiz_result = QuizResult(
        date=now.strftime("%Y-%m-%d"),
        q1_correct=q1_correct,
        q2_evaluation=q2_evaluation,
        pattern=pattern,
    )
    state_manager.update_quiz_history(
        topic_key=topic_key,
        result=quiz_result,
        new_level=new_level,
        new_interval_days=new_interval_days,
        next_quiz_at=next_quiz_at,
    )
    state_manager.save()

    logger.info(
        "採点完了: %s — Q1=%s, Q2=%s, Level→%d (%s)",
        topic_key,
        q1_correct,
        q2_evaluation,
        new_level,
        level_change,
    )

    return QuizScoreResult(
        topic_key=topic_key,
        q1_correct=q1_correct,
        q1_correct_answer=q1_correct_answer,
        q1_explanation=q1_explanation,
        q2_evaluation=q2_evaluation,
        q2_feedback=q2_feedback,
        new_level=new_level,
        new_interval_days=new_interval_days,
        next_quiz_at=next_quiz_at,
        level_change=level_change,
    )


async def score_async(
    topic_key: str,
    q1_choice: str,
    q2_answer: str,
    briefing_file: str,
    *,
    copilot_client: CopilotClientWrapper,
    state_manager: StateManager,
    app_config: AppConfig,
) -> QuizScoreResult:
    """score() の非同期版。既存のイベントループ内で使用する。

    複数トピックをまとめて採点する際、ひとつの asyncio.run() 内で
    繰り返し呼び出すために使用する。

    Args:
        topic_key: トピックキー。
        q1_choice: ユーザーの Q1 選択。
        q2_answer: ユーザーの Q2 回答テキスト。
        briefing_file: ブリーフィング MD ファイルパス。
        copilot_client: Copilot クライアントラッパー。
        state_manager: 状態マネージャ。
        app_config: アプリケーション設定。

    Returns:
        QuizScoreResult。
    """
    logger.info("採点開始 (async): %s", topic_key)

    scoring_result = await _score_topic(
        copilot_client,
        topic_key,
        q1_choice,
        q2_answer,
        briefing_file,
        app_config.input_folders,
    )

    q1_correct = bool(scoring_result.get("q1_correct", False))
    q1_correct_answer = str(scoring_result.get("q1_correct_answer", ""))
    q1_explanation = str(scoring_result.get("q1_explanation", ""))
    q2_evaluation = str(scoring_result.get("q2_evaluation", "poor"))
    q2_feedback = str(scoring_result.get("q2_feedback", ""))

    # 間隔反復の更新
    sr_config = app_config.quiz.spaced_repetition
    now = datetime.now()

    sr_update = update_after_scoring(
        state_manager, topic_key, q1_correct, q2_evaluation, sr_config, now=now
    )

    new_level = int(sr_update["new_level"])
    new_interval_days = int(sr_update["new_interval_days"])
    next_quiz_at = str(sr_update["next_quiz_at"])
    level_change = str(sr_update["level_change"])

    # pending_quizzes を取得して pattern を特定
    pending = state_manager.remove_pending_quiz(topic_key)
    pattern = pending.pattern if pending else "learning"

    # quiz_history に結果を記録
    quiz_result = QuizResult(
        date=now.strftime("%Y-%m-%d"),
        q1_correct=q1_correct,
        q2_evaluation=q2_evaluation,
        pattern=pattern,
    )
    state_manager.update_quiz_history(
        topic_key=topic_key,
        result=quiz_result,
        new_level=new_level,
        new_interval_days=new_interval_days,
        next_quiz_at=next_quiz_at,
    )
    state_manager.save()

    logger.info(
        "採点完了 (async): %s — Q1=%s, Q2=%s, Level→%d (%s)",
        topic_key,
        q1_correct,
        q2_evaluation,
        new_level,
        level_change,
    )

    return QuizScoreResult(
        topic_key=topic_key,
        q1_correct=q1_correct,
        q1_correct_answer=q1_correct_answer,
        q1_explanation=q1_explanation,
        q2_evaluation=q2_evaluation,
        q2_feedback=q2_feedback,
        new_level=new_level,
        new_interval_days=new_interval_days,
        next_quiz_at=next_quiz_at,
        level_change=level_change,
    )


def build_result_item(
    result: QuizScoreResult,
    pending: PendingQuiz | None = None,
) -> dict[str, str]:
    """QuizScoreResult を format_quiz_result_section 用の辞書に変換する。

    Args:
        result: 採点結果。
        pending: 対応する PendingQuiz（pattern_emoji 判定用）。

    Returns:
        結果辞書。
    """
    pattern = pending.pattern if pending else "learning"
    pattern_emoji = "📘" if pattern == "learning" else "📗"

    # topic_key から短いタイトルを生成
    topic_title = result.topic_key.split("#")[-1] if "#" in result.topic_key else result.topic_key

    # レベル変動テキスト
    if result.level_change == "upgrade":
        level_text = t("scorer.level_upgrade", level=result.new_level)
    elif result.level_change == "downgrade":
        level_text = t("scorer.level_downgrade", level=result.new_level)
    else:
        level_text = t("scorer.level_unchanged", level=result.new_level)

    next_quiz_info = t("scorer.next_quiz_info", date=result.next_quiz_at, detail=level_text)

    return {
        "topic_key": result.topic_key,
        "topic_title": topic_title,
        "pattern_emoji": pattern_emoji,
        "q1_correct": result.q1_correct,  # type: ignore[dict-item]
        "q1_correct_answer": result.q1_correct_answer,
        "q1_explanation": result.q1_explanation,
        "q2_evaluation": result.q2_evaluation,
        "q2_feedback": result.q2_feedback,
        "next_quiz_info": next_quiz_info,
    }


def process_unanswered(
    state_manager: StateManager,
    sr_config: Any = None,
) -> None:
    """pending_quizzes の未回答分を自動不正解として処理する。

    B ジョブ実行時、ファイル選定の前に呼び出す。

    Args:
        state_manager: 状態マネージャ。
        sr_config: 間隔反復設定。None の場合はデフォルト値を使用。
    """
    from app.config import SpacedRepetitionConfig

    pending = state_manager.get_pending_quizzes()
    if not pending:
        return

    logger.info("未回答クイズの自動不正解処理: %d 件", len(pending))

    if sr_config is None:
        sr_config = SpacedRepetitionConfig()

    # ブリーフィングファイルごとにグルーピング
    by_file: dict[str, list[PendingQuiz]] = {}
    for pq in pending:
        by_file.setdefault(pq.briefing_file, []).append(pq)

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    for briefing_file, quizzes in by_file.items():
        result_items: list[dict[str, str]] = []

        for pq in quizzes:
            # 間隔反復の更新（不正解として処理）
            sr_update = update_after_scoring(
                state_manager,
                pq.topic_key,
                q1_correct=False,
                q2_evaluation="poor",
                sr_config=sr_config,
                now=now,
            )

            new_level = int(sr_update["new_level"])
            new_interval_days = int(sr_update["new_interval_days"])
            next_quiz_at = str(sr_update["next_quiz_at"])

            # quiz_history に不正解として記録
            result = QuizResult(
                date=today_str,
                q1_correct=False,
                q2_evaluation="poor",
                pattern=pq.pattern,
            )
            state_manager.update_quiz_history(
                topic_key=pq.topic_key,
                result=result,
                new_level=new_level,
                new_interval_days=new_interval_days,
                next_quiz_at=next_quiz_at,
            )

            result_items.append(
                {
                    "topic_key": pq.topic_key,
                    "topic_title": (
                        pq.topic_key.split("#")[-1]
                        if "#" in pq.topic_key
                        else pq.topic_key
                    ),
                    "pattern_emoji": "📘" if pq.pattern == "learning" else "📗",
                    "next_quiz_info": t("scorer.next_quiz_info", date=next_quiz_at, detail=t("scorer.level_downgrade", level=new_level)),
                }
            )

            logger.info("未回答不正解処理: %s", pq.topic_key)

        # ブリーフィング MD に結果追記
        if result_items and briefing_file:
            result_section = format_quiz_result_section(
                result_items, is_auto=True, now=now
            )
            append_quiz_result(briefing_file, result_section)

    # pending_quizzes をクリア
    state_manager.clear_pending_quizzes()
    state_manager.save()
