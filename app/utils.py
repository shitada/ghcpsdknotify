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


def _is_question_title(title: str) -> bool:
    """タイトルが Q1/Q2 問題見出しかどうかを判定する。

    LLM が Q1 / Q2 にも ``<!-- topic_key: ... -->`` マーカーを付ける場合があり、
    それらをトピックとして扱わないためのフィルタ。
    """
    import re
    return bool(re.match(r"Q[12]\b", title.strip()))


def extract_topic_keys(md_content: str) -> list[dict[str, str]]:
    """ブリーフィング MD から topic_key を抽出する。

    <!-- topic_key: ... --> 形式の HTML コメントを検索する。
    直後の ### 行からトピックタイトル、Q1 / Q2 問題文もあわせて取得する。
    タイトルが Q1/Q2 で始まるマーカーは問題見出しとみなしスキップする。

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

    # 全マーカーを収集
    all_matches = list(topic_block_pattern.finditer(md_content))

    # トピックマーカー (Q1/Q2 見出しでないもの) のみ抽出
    topic_matches = [
        m for m in all_matches if not _is_question_title(m.group(2).strip())
    ]

    for i, match in enumerate(topic_matches):
        topic_key = match.group(1).strip()
        title = match.group(2).strip()

        # ブロック終端: 次のトピックマーカー（Q1/Q2 でない）まで、または文末
        # Quiz Results セクションがあればそこで終了
        block_end = (
            topic_matches[i + 1].start()
            if i + 1 < len(topic_matches)
            else len(md_content)
        )
        # Quiz Results セクションより後ろは含めない
        results_marker = re.search(
            r"^## 📝 Quiz Results", md_content[match.start():block_end], re.MULTILINE
        )
        if results_marker:
            block_end = match.start() + results_marker.start()

        block = md_content[match.start(): block_end]

        # Q1 問題文を抽出
        # 日本語: **Q1（4択）** 〜 選択肢 "- A)" の手前
        # 英語: ## Q1 — Multiple Choice / ### Q1 — ... 等
        q1_text = ""
        q1_match = re.search(
            r"(?:\*\*Q1（4択）\*\*|(?:#{1,4}\s+)?Q1[^\n]*)"
            r"\s*\n+(.+?)(?=\n-\s*A[)）]|\n\*\*A[.)）]|\n---)",
            block,
            re.DOTALL,
        )
        if q1_match:
            q1_text = q1_match.group(1).strip()
            q1_text = re.sub(r"^>\s?", "", q1_text, flags=re.MULTILINE).strip()

        # Q2 問題文を抽出
        q2_text = ""
        q2_match = re.search(
            r"(?:\*\*Q2（記述）\*\*|(?:#{1,4}\s+)?Q2[^\n]*)"
            r"\s*\n+(.+?)(?=\n---|\.\n\n|$)",
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
