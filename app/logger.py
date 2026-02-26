"""ログ設定モジュール。

Python 標準 logging + RotatingFileHandler を使用したログ出力設定。
出力先は logs/app.log（自動作成）、5MB×5世代ローテーション。
コンソール出力なし（GUI アプリのため）。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ログ出力先ディレクトリ（アプリディレクトリ直下の logs/）
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "app.log"

# ローテーション設定
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 5  # 5世代

# ログフォーマット
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def setup_logging(log_level: str = "INFO") -> None:
    """アプリケーション全体のログ設定を行う。

    RotatingFileHandler を使用し、logs/app.log に出力する。
    logs/ ディレクトリは自動作成される。
    コンソール（stdout）への出力は行わない。

    Args:
        log_level: ログレベル文字列（"DEBUG" / "INFO" / "WARNING" / "ERROR"）。
    """
    # ログディレクトリの自動作成
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 数値レベルへの変換
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # ルートロガーの設定
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 既存のハンドラをクリア（多重登録防止）
    root_logger.handlers.clear()

    # RotatingFileHandler の設定
    file_handler = RotatingFileHandler(
        filename=str(_LOG_FILE),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)

    # フォーマッタの設定
    formatter = logging.Formatter(_LOG_FORMAT)
    file_handler.setFormatter(formatter)

    # ルートロガーにハンドラを追加
    root_logger.addHandler(file_handler)

    logging.getLogger(__name__).info(
        "ログ設定完了: level=%s, file=%s", log_level, _LOG_FILE
    )


def get_log_file_path() -> str:
    """ログファイルのパスを返す。

    Returns:
        ログファイルの絶対パス文字列。
    """
    return str(_LOG_FILE)
