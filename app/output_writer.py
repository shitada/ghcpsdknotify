"""MD ファイル出力・クイズ結果追記モジュール。

ブリーフィングの MD ファイルを出力フォルダに書き出し、
クイズ回答後の結果セクション追記を行う。
アトミック書き込みは utils モジュールの共通ユーティリティを使用する。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.i18n import t
from app.utils import atomic_write

logger = logging.getLogger(__name__)


def _determine_output_folder(
    input_folders: list[str],
    output_folder_name: str,
    existing_output_path: str,
) -> Path:
    """出力フォルダを決定する。

    state.json の output_folder_path が設定済みかつ存在する場合はそれを使用。
    未設定または存在しない場合は、最初の input_folder 直下に出力フォルダを新規作成する。
    名前衝突時は連番を付与する。

    Args:
        input_folders: 入力フォルダパスのリスト。
        output_folder_name: 出力フォルダ名（デフォルト: "_briefings"）。
        existing_output_path: state.json に記録済みの出力フォルダパス（空文字列の場合は未設定）。

    Returns:
        確定した出力フォルダの Path。

    Raises:
        ValueError: input_folders が空の場合。
    """
    # 既存パスが有効かつ、現在の input_folders 配下であればそのまま使用
    if existing_output_path:
        existing = Path(existing_output_path).resolve()
        if existing.exists() and existing.is_dir():
            # input_folders が変更されていないか確認
            if input_folders:
                current_base = Path(input_folders[0]).resolve()
                if existing.parent == current_base:
                    logger.debug("既存の出力フォルダを使用: %s", existing)
                    return existing
                else:
                    logger.info(
                        "input_folders が変更されたため出力フォルダを再決定します: "
                        "%s → %s",
                        existing.parent,
                        current_base,
                    )
            else:
                logger.debug("既存の出力フォルダを使用: %s", existing)
                return existing

    # 新規作成
    if not input_folders:
        raise ValueError("出力フォルダの作成に必要な input_folders が空です")

    base_dir = Path(input_folders[0])
    if not base_dir.exists():
        base_dir.mkdir(parents=True, exist_ok=True)

    # 名前衝突チェック + 連番付与
    candidate = base_dir / output_folder_name
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=True)
        logger.info("出力フォルダを作成: %s", candidate)
        return candidate

    # 衝突時: 連番を試行
    for i in range(2, 100):
        candidate = base_dir / f"{output_folder_name}_{i}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            logger.info("出力フォルダを作成（連番）: %s", candidate)
            return candidate

    # フォールバック（通常到達しない）
    candidate = base_dir / output_folder_name
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def get_output_folder(
    input_folders: list[str],
    output_folder_name: str,
    existing_output_path: str,
) -> str:
    """出力フォルダのパスを取得する（必要に応じて作成）。

    Args:
        input_folders: 入力フォルダパスのリスト。
        output_folder_name: 出力フォルダ名。
        existing_output_path: state.json に記録済みの出力フォルダパス。

    Returns:
        確定した出力フォルダの絶対パス文字列。
    """
    folder = _determine_output_folder(
        input_folders, output_folder_name, existing_output_path
    )
    return str(folder.resolve())


def _generate_filename(feature: str, now: datetime | None = None) -> str:
    """ブリーフィングのファイル名を生成する。

    Args:
        feature: "a" (最新情報) または "b" (復習・クイズ)。
        now: 現在時刻。None の場合は datetime.now() を使用。

    Returns:
        ファイル名文字列。
    """
    if now is None:
        now = datetime.now()

    timestamp = now.strftime("%Y-%m-%d_%H%M%S")

    if feature == "a":
        return f"briefing_news_{timestamp}.md"
    elif feature == "b":
        return f"briefing_quiz_{timestamp}.md"
    elif feature == "c":
        return f"briefing_monitor_{timestamp}.md"
    elif feature == "d":
        return f"briefing_meetings_{timestamp}.md"
    else:
        return f"briefing_{timestamp}.md"


def write_briefing(
    content: str,
    feature: str,
    output_folder: str,
    *,
    now: datetime | None = None,
) -> str:
    """ブリーフィング MD ファイルを出力フォルダに書き込む。

    アトミック書き込みを使用する。briefing_*.md は write-once のため
    バックアップは作成しない。

    Args:
        content: ブリーフィングの MD テキスト。
        feature: "a" (最新情報) または "b" (復習・クイズ)。
        output_folder: 出力フォルダのパス。
        now: 現在時刻（テスト用）。

    Returns:
        書き込んだファイルの絶対パス。
    """
    filename = _generate_filename(feature, now)
    file_path = Path(output_folder) / filename

    # 出力フォルダが存在しない場合は作成
    file_path.parent.mkdir(parents=True, exist_ok=True)

    atomic_write(file_path, content, create_backup=False)
    logger.info("ブリーフィング出力: %s", file_path)
    return str(file_path.resolve())


def append_quiz_result(
    briefing_file: str,
    result_section: str,
) -> None:
    """既存のブリーフィング MD ファイル末尾にクイズ結果セクションを追記する。

    アトミック書き込みを使用する。

    Args:
        briefing_file: 追記先のブリーフィング MD ファイルパス。
        result_section: 追記するクイズ結果セクションの MD テキスト。
    """
    file_path = Path(briefing_file)

    if not file_path.exists():
        logger.warning("追記先ファイルが存在しません: %s", file_path)
        return

    try:
        existing = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.error("ファイル読み込み失敗: %s — %s", file_path, e)
        return

    # 末尾に結果セクションを追加
    updated = existing.rstrip("\n") + "\n\n" + result_section.strip() + "\n"

    atomic_write(file_path, updated, create_backup=False)
    logger.info("クイズ結果を追記: %s", file_path)


def format_quiz_result_section(
    results: list[dict[str, str]],
    *,
    is_auto: bool = False,
    now: datetime | None = None,
) -> str:
    """クイズ結果セクションの MD テキストを構築する。

    Args:
        results: トピックごとの結果リスト。各要素は:
            - topic_title (str): トピックタイトル
            - pattern_emoji (str): パターン絵文字（📘 or 📗）
            - q1_correct (bool): Q1 正解かどうか
            - q1_correct_answer (str): Q1 正解の選択肢（例: "B"）
            - q1_explanation (str): Q1 の解説
            - q2_evaluation (str): "good" | "partial" | "poor"
            - q2_feedback (str): Q2 のフィードバック
            - next_quiz_info (str): 次回出題情報（例: "2026-02-29（Level 2 → 据え置き）"）
        is_auto: True の場合は「自動処理: 未回答」として記録。
        now: 現在時刻。

    Returns:
        MD フォーマットの結果セクション文字列。
    """
    if now is None:
        now = datetime.now()

    timestamp = now.strftime("%Y-%m-%d %H:%M")

    if is_auto:
        lines = [t("output.quiz_result_auto")]
    else:
        lines = [t("output.quiz_result_header", timestamp=timestamp)]

    for r in results:
        pattern_emoji = r.get("pattern_emoji", "📘")
        topic_title = r.get("topic_title", t("output.unknown_topic"))
        lines.append(f"### {pattern_emoji} {topic_title}")

        if is_auto:
            lines.append(t("output.q1_unanswered"))
            lines.append(t("output.q2_unanswered"))
        else:
            # Q1 結果
            q1_correct = r.get("q1_correct", False)
            if q1_correct:
                lines.append(t("output.q1_correct"))
            else:
                q1_answer = r.get("q1_correct_answer", "")
                lines.append(t("output.q1_incorrect", answer=q1_answer))

            # Q2 結果
            q2_eval = r.get("q2_evaluation", "poor")
            q2_feedback = r.get("q2_feedback", "")
            if q2_eval == "good":
                lines.append(t("output.q2_good", feedback=q2_feedback))
            elif q2_eval == "partial":
                lines.append(t("output.q2_partial", feedback=q2_feedback))
            else:
                lines.append(t("output.q2_poor", feedback=q2_feedback))

        # 次回出題情報
        next_info = r.get("next_quiz_info", "")
        if next_info:
            lines.append(t("output.next_quiz", info=next_info))

        lines.append("")  # 空行

    return "\n".join(lines)
