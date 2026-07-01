"""Windows スタートアップ自動起動モジュール。

PC（Windows）ログオン時にアプリをサイレント起動するための
スタートアップフォルダのショートカット (.lnk) を作成・削除する。

- 起動方式: venv の ``pythonw.exe`` を直接呼び出し（コンソール非表示・高速）
- 登録方式: ``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup`` の .lnk
- 管理者権限不要（ユーザースコープ）。タスクマネージャーの
  「スタートアップ アプリ」に表示され、ユーザーが無効化できる。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# スタートアップショートカットのファイル名（タスクマネージャーに表示される名前）
_LNK_NAME = "AI Daily Briefing.lnk"

# PowerShell スクリプト: WScript.Shell COM でショートカットを作成する
_PS_CREATE_SHORTCUT = r"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{lnk_path}")
$sc.TargetPath = "{target_path}"
$sc.Arguments = "{arguments}"
$sc.WorkingDirectory = "{working_dir}"
$sc.Description = "{description}"
$sc.WindowStyle = 7
$icon = "{icon_location}"
if ($icon) {{ $sc.IconLocation = $icon }}
$sc.Save()
"""


def _project_root() -> Path:
    """プロジェクトルート（``app/`` の親）を返す。"""
    return Path(__file__).resolve().parent.parent


def _startup_dir() -> Path:
    """Windows スタートアップフォルダのパスを返す。"""
    return Path(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


def _shortcut_path() -> Path:
    """スタートアップ .lnk のフルパスを返す。"""
    return _startup_dir() / _LNK_NAME


def _resolve_target() -> Path:
    """サイレント起動用の実行ファイルを返す。

    現在動作中のインタプリタ（venv）の隣にある ``pythonw.exe`` を優先する。
    ``pythonw.exe`` はコンソールウィンドウを開かないため、起動時に黒い窓が
    表示されない。存在しない場合は ``python.exe``（``sys.executable``）に
    フォールバックする。
    """
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


def is_enabled() -> bool:
    """スタートアップ登録済みかどうかを返す。"""
    try:
        return _shortcut_path().exists()
    except OSError:
        logger.debug("スタートアップ状態の確認に失敗", exc_info=True)
        return False


def enable() -> bool:
    """スタートアップ登録（.lnk 作成）を行う。

    Returns:
        成功時 True、失敗時 False。
    """
    startup_dir = _startup_dir()
    if not startup_dir.exists():
        logger.warning("スタートアップフォルダが見つかりません: %s", startup_dir)
        return False

    lnk_path = _shortcut_path()
    target = _resolve_target()
    project_root = _project_root()
    icon_path = project_root / "assets" / "icon_normal.ico"
    icon_arg = str(icon_path) if icon_path.exists() else ""

    ps_script = _PS_CREATE_SHORTCUT.format(
        lnk_path=str(lnk_path),
        target_path=str(target),
        arguments="-m app.main",
        working_dir=str(project_root),
        description="Personal AI Daily Briefing Agent",
        icon_location=icon_arg,
    )

    # PowerShell をウィンドウ非表示で実行する
    si = None
    if hasattr(subprocess, "STARTUPINFO"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        result = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
            startupinfo=si,
        )
    except Exception:
        logger.exception("スタートアップ登録に失敗しました")
        return False

    if result.returncode == 0 and lnk_path.exists():
        logger.info("スタートアップ登録しました: %s", lnk_path)
        return True

    logger.warning(
        "スタートアップ登録失敗 (rc=%d): %s",
        result.returncode,
        result.stderr[:300] if result.stderr else "",
    )
    return False


def disable() -> bool:
    """スタートアップ登録を解除（.lnk 削除）する。

    Returns:
        成功時（または元々未登録）True、失敗時 False。
    """
    lnk_path = _shortcut_path()
    try:
        lnk_path.unlink(missing_ok=True)
        logger.info("スタートアップ登録を解除しました: %s", lnk_path)
        return True
    except OSError:
        logger.exception("スタートアップ登録の解除に失敗しました")
        return False


def set_enabled(enabled: bool) -> bool:
    """指定した有効/無効状態に設定する。

    Args:
        enabled: True で登録、False で解除。

    Returns:
        操作が成功した場合 True。
    """
    return enable() if enabled else disable()


def sync(desired: bool) -> None:
    """設定値と OS の実状態を一致させる（best-effort）。

    - ``desired=True`` で未登録 → 登録（手動削除された場合などに自己修復）
    - ``desired=False`` で登録済み → 解除

    例外は送出せず、ログのみに記録する。アプリ起動時に呼び出す想定。
    """
    try:
        currently = is_enabled()
        if desired and not currently:
            enable()
        elif not desired and currently:
            disable()
    except Exception:
        logger.debug("スタートアップ同期に失敗", exc_info=True)
