"""共通ユーティリティモジュール。

アトミック書き込み（write-then-rename + .bak + フォールバック）など、
複数モジュールで共有するユーティリティ関数を提供する。
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from app.i18n import t

logger = logging.getLogger(__name__)


def atomic_write(file_path: Path, content: str, *, create_backup: bool = True) -> None:
    """ファイルをアトミックに書き込む（write-then-rename 方式）。

    1. <ファイル名>.tmp に新しい内容を書き込む
    2. fsync でディスクにフラッシュ
    3. 既存ファイルがあれば .bak としてバックアップ
    4. .tmp → 本体にリネーム（OS レベルでアトミック）

    Args:
        file_path: 書き込み先のファイルパス。
        content: 書き込む内容（文字列）。
        create_backup: True の場合、書き込み前に既存ファイルの .bak を作成する。
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    bak_path = file_path.with_suffix(file_path.suffix + ".bak")

    try:
        # 1. 一時ファイルに書き込み
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            # 2. fsync でディスクにフラッシュ
            f.flush()
            os.fsync(f.fileno())

        # 3. バックアップ作成（既存ファイルがある場合）
        if create_backup and file_path.exists():
            try:
                shutil.copy2(str(file_path), str(bak_path))
                logger.debug("バックアップ作成: %s", bak_path)
            except OSError as e:
                logger.warning("バックアップ作成に失敗: %s — %s", bak_path, e)

        # 4. リネーム（Windows では os.replace がアトミック相当）
        os.replace(str(tmp_path), str(file_path))
        logger.debug("アトミック書き込み完了: %s", file_path)

    except Exception:
        # 一時ファイルが残っていれば削除
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def safe_read_with_fallback(
    file_path: Path,
    parser: Callable[[str], object],
    default_factory: Callable[[], object],
    *,
    notify_callback: Callable[[str, str], None] | None = None,
) -> object:
    """ファイルを読み込み、失敗時は .bak → デフォルト値の順でフォールバックする。

    Args:
        file_path: 読み込むファイルパス。
        parser: ファイル内容を受け取りパース結果を返す関数。
        default_factory: パース失敗時のデフォルト値を返すファクトリ関数。
        notify_callback: 警告通知を行うコールバック（title, message）。None なら通知スキップ。

    Returns:
        パース結果またはデフォルト値。
    """
    file_path = Path(file_path)
    bak_path = file_path.with_suffix(file_path.suffix + ".bak")

    # 1. 本体読み込み
    if file_path.exists():
        try:
            raw = file_path.read_text(encoding="utf-8")
            result = parser(raw)
            logger.debug("ファイル読み込み成功: %s", file_path)
            return result
        except Exception as e:
            logger.warning("ファイル読み込み/パース失敗: %s — %s", file_path, e)

    # 2. .bak から復元
    if bak_path.exists():
        try:
            raw = bak_path.read_text(encoding="utf-8")
            result = parser(raw)
            logger.warning(".bak から復元しました: %s", bak_path)
            if notify_callback:
                notify_callback(
                    t("utils.file_recovery"),
                    t("utils.restored_from_backup", name=file_path.name),
                )
            return result
        except Exception as e:
            logger.warning(".bak 読み込み/パース失敗: %s — %s", bak_path, e)

    # 3. デフォルト値にフォールバック
    logger.warning("デフォルト値にフォールバック: %s", file_path)
    if notify_callback:
        notify_callback(
            t("utils.file_recovery"),
            t("utils.regenerated_default", name=file_path.name),
        )
    return default_factory()


def estimate_tokens(text: str) -> int:
    """テキストのトークン数を推定する（簡易推定: 日英混在を考慮）。

    日本語テキストを多く含む場合を想定し、1文字≒1.5トークンで概算する。
    英単語ベースの推定（空白区切り÷0.75）と文字数ベースの推定の加重平均を取る。

    Args:
        text: トークン数を推定するテキスト。

    Returns:
        推定トークン数（整数）。
    """
    if not text:
        return 0
    # 英単語ベースの推定
    word_count = len(text.split())
    word_based = int(word_count / 0.75)
    # 文字数ベースの推定（日本語向け）
    char_based = int(len(text) * 0.5)
    # 大きい方を採用（安全側に倒す）
    return max(word_based, char_based)


def extract_topic_keys(md_content: str) -> list[dict[str, str]]:
    """ブリーフィング MD から topic_key を抽出する。

    <!-- topic_key: ... --> 形式の HTML コメントを検索する。
    直後の ### 行からトピックタイトル、**Q1（4択）** / **Q2（記述）** の
    直後にある問題文もあわせて取得する。

    Args:
        md_content: ブリーフィング MD テキスト。

    Returns:
        抽出結果のリスト。各要素は
        {"topic_key": ..., "title": ..., "pattern": ...,
         "q1_text": ..., "q2_text": ...}。
    """
    import re

    results: list[dict[str, str]] = []
    topic_block_pattern = re.compile(
        r"<!--\s*topic_key:\s*(.+?)\s*-->\s*\n\s*###\s*(.+)",
        re.MULTILINE,
    )

    # 各トピックの開始位置を収集してブロックに分割
    matches = list(topic_block_pattern.finditer(md_content))
    for i, match in enumerate(matches):
        topic_key = match.group(1).strip()
        title = match.group(2).strip()

        # ブロック終端（次のトピックコメントの手前、または文末）
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(md_content)
        block = md_content[match.start(): block_end]

        # Q1 問題文: **Q1（4択）** 〜 最初の選択肢 "- A)" の手前まで
        q1_text = ""
        q1_match = re.search(
            r"\*\*Q1（4択）\*\*\s*\n+(.+?)(?=\n-\s*A[)）]|\n---)",
            block,
            re.DOTALL,
        )
        if q1_match:
            q1_text = q1_match.group(1).strip()
            # 引用ブロックのマーカー ">" を除去して読みやすく
            q1_text = re.sub(r"^>\s?", "", q1_text, flags=re.MULTILINE).strip()

        # Q2 問題文: **Q2（記述）** 〜 次の "---" の手前まで
        q2_text = ""
        q2_match = re.search(
            r"\*\*Q2（記述）\*\*\s*\n+(.+?)(?=\n---)",
            block,
            re.DOTALL,
        )
        if q2_match:
            q2_text = q2_match.group(1).strip()
            q2_text = re.sub(r"^>\s?", "", q2_text, flags=re.MULTILINE).strip()

        # マッチ位置より前のテキストからパターンを判定
        preceding = md_content[: match.start()]
        if "📘" in preceding and ("📗" not in preceding or preceding.rfind("📘") > preceding.rfind("📗")):
            topic_pattern = "learning"
        elif "📗" in preceding:
            topic_pattern = "review"
        else:
            topic_pattern = "learning"

        results.append(
            {
                "topic_key": topic_key,
                "title": title,
                "pattern": topic_pattern,
                "q1_text": q1_text,
                "q2_text": q2_text,
            }
        )

    return results
