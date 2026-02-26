"""フォルダ再帰走査・MD ファイル読み込み・frontmatter 抽出モジュール。

指定フォルダを再帰的に走査し、対象拡張子のファイルを読み込む。
YAML frontmatter からメタデータ（priority, deadline, tags 等）を抽出する。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# frontmatter の正規表現パターン（--- で囲まれた YAML ブロック）
_FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\n(.*?\n)---\s*\n",
    re.DOTALL,
)

# チェックボックスのパターン
_CHECKBOX_UNCHECKED = re.compile(r"- \[ \]")
_CHECKBOX_CHECKED = re.compile(r"- \[x\]", re.IGNORECASE)


@dataclass
class FileMetadata:
    """MD ファイルのメタデータ。"""

    relative_path: str = ""
    absolute_path: str = ""
    modified_at: datetime | None = None
    created_at: datetime | None = None
    file_size: int = 0
    priority: str = ""  # "high" | "medium" | "low" | ""
    deadline: str = ""  # YYYY-MM-DD 形式
    tags: list[str] = field(default_factory=list)
    unchecked_count: int = 0
    checked_count: int = 0
    frontmatter: dict[str, Any] = field(default_factory=dict)
    folder_name: str = ""  # 所属フォルダ名（カテゴリ分けの手がかり）


@dataclass
class ScannedFile:
    """走査済みファイルの情報（メタデータ + 本文）。"""

    metadata: FileMetadata
    content: str = ""  # ファイル本文（frontmatter を除く）
    raw_content: str = ""  # ファイル全文（frontmatter 含む）


def _extract_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """ファイル内容から YAML frontmatter を抽出する。

    Args:
        raw: ファイルの全内容。

    Returns:
        (frontmatter 辞書, frontmatter を除いた本文) のタプル。
        frontmatter がない場合は空辞書と全文を返す。
    """
    match = _FRONTMATTER_PATTERN.match(raw)
    if not match:
        return {}, raw

    try:
        fm = yaml.safe_load(match.group(1))
        if not isinstance(fm, dict):
            return {}, raw
        body = raw[match.end():]
        return fm, body
    except yaml.YAMLError as e:
        logger.warning("frontmatter のパースに失敗: %s", e)
        return {}, raw


def _count_checkboxes(content: str) -> tuple[int, int]:
    """本文中のチェックボックスをカウントする。

    Args:
        content: ファイル本文。

    Returns:
        (未完了数, 完了数) のタプル。
    """
    unchecked = len(_CHECKBOX_UNCHECKED.findall(content))
    checked = len(_CHECKBOX_CHECKED.findall(content))
    return unchecked, checked


def _read_file_safe(file_path: Path) -> str | None:
    """ファイルを安全に読み込む。失敗時は None を返す。

    Args:
        file_path: 読み込むファイルパス。

    Returns:
        ファイル内容。読み込み失敗時は None。
    """
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("エンコーディングエラー（非 UTF-8）: %s", file_path)
        return None
    except PermissionError:
        logger.warning("ファイル読み取り権限なし: %s", file_path)
        return None
    except OSError as e:
        logger.warning("ファイル読み込みエラー: %s — %s", file_path, e)
        return None


def scan_folder(
    folder_path: str | Path,
    target_extensions: list[str] | None = None,
    *,
    base_folder: str | Path | None = None,
) -> list[ScannedFile]:
    """指定フォルダを再帰的に走査し、対象ファイルを読み込む。

    Args:
        folder_path: 走査対象の親フォルダパス。
        target_extensions: 対象ファイル拡張子のリスト（例: [".md"]）。
            None の場合は [".md"] をデフォルトとする。
        base_folder: 相対パス計算の基準フォルダ。
            None の場合は folder_path を基準とする。

    Returns:
        ScannedFile のリスト。
    """
    if target_extensions is None:
        target_extensions = [".md"]

    folder = Path(folder_path).resolve()
    base = Path(base_folder).resolve() if base_folder else folder

    if not folder.exists():
        logger.warning("フォルダが存在しません: %s", folder)
        return []

    if not folder.is_dir():
        logger.warning("ディレクトリではありません: %s", folder)
        return []

    results: list[ScannedFile] = []

    try:
        for root, _dirs, files in os.walk(folder):
            root_path = Path(root)
            # _briefings フォルダはスキップ（出力先のため）
            if root_path.name.startswith("_briefings"):
                continue

            for filename in sorted(files):
                file_path = root_path / filename
                ext = file_path.suffix.lower()

                if ext not in target_extensions:
                    continue

                raw = _read_file_safe(file_path)
                if raw is None:
                    continue

                # frontmatter 抽出
                frontmatter, body = _extract_frontmatter(raw)

                # チェックボックスカウント
                unchecked, checked = _count_checkboxes(body)

                # ファイル情報取得
                try:
                    stat = file_path.stat()
                    modified_at = datetime.fromtimestamp(stat.st_mtime)
                    created_at = datetime.fromtimestamp(stat.st_ctime)
                    file_size = stat.st_size
                except OSError as e:
                    logger.warning("ファイル情報取得失敗: %s — %s", file_path, e)
                    modified_at = None
                    created_at = None
                    file_size = 0

                # 相対パス計算
                try:
                    rel_path = file_path.relative_to(base).as_posix()
                except ValueError:
                    rel_path = file_path.name

                # メタデータ組み立て
                metadata = FileMetadata(
                    relative_path=rel_path,
                    absolute_path=str(file_path),
                    modified_at=modified_at,
                    created_at=created_at,
                    file_size=file_size,
                    priority=str(frontmatter.get("priority", "")),
                    deadline=str(frontmatter.get("deadline", "")) if frontmatter.get("deadline") else "",
                    tags=list(frontmatter.get("tags", [])) if isinstance(frontmatter.get("tags"), list) else [],
                    unchecked_count=unchecked,
                    checked_count=checked,
                    frontmatter=frontmatter,
                    folder_name=root_path.name,
                )

                results.append(ScannedFile(
                    metadata=metadata,
                    content=body,
                    raw_content=raw,
                ))

    except PermissionError:
        logger.warning("フォルダ読み取り権限なし: %s", folder)
    except OSError as e:
        logger.warning("フォルダ走査エラー: %s — %s", folder, e)

    logger.info("フォルダ走査完了: %s — %d ファイル検出", folder, len(results))
    return results


def scan_folders(
    folder_paths: list[str],
    target_extensions: list[str] | None = None,
) -> list[ScannedFile]:
    """複数のフォルダを走査し、結果を統合して返す。

    Args:
        folder_paths: 走査対象の親フォルダパスのリスト。
        target_extensions: 対象ファイル拡張子のリスト。

    Returns:
        全フォルダから検出した ScannedFile のリスト。
    """
    all_files: list[ScannedFile] = []
    seen_paths: set[str] = set()

    for folder_path in folder_paths:
        files = scan_folder(folder_path, target_extensions, base_folder=folder_path)
        for f in files:
            abs_path = f.metadata.absolute_path
            if abs_path not in seen_paths:
                seen_paths.add(abs_path)
                all_files.append(f)
            else:
                logger.debug("重複ファイルをスキップ: %s", abs_path)

    logger.info("全フォルダ走査完了: %d フォルダ, %d ファイル", len(folder_paths), len(all_files))
    return all_files
