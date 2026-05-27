"""エントリーポイント + メイン処理オーケストレーションモジュール。

起動フロー（ログ→設定→前提チェック→状態読み込み→スケジューラ→システムトレイ常駐）と、
機能 A / B / C のメイン処理コールバックを実装する。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from pathlib import Path as _Path

import pystray
from PIL import Image

# ── アセットフォルダ ──
_ASSETS_DIR = _Path(__file__).resolve().parent.parent / "assets"

from app import config as config_module
from app.config import AppConfig
from app.i18n import get_language, set_language, t
from app.logger import get_log_file_path, setup_logging
from app.scheduler import Scheduler
from app.settings_ui import open_settings
from app.setup_wizard import run_wizard
from app.state_manager import StateManager

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  グローバル状態（モジュールレベル）
# ══════════════════════════════════════════════════════════════════════

_app_config: AppConfig | None = None
_state_manager: StateManager | None = None
_scheduler: Scheduler | None = None
_tray_icon: pystray.Icon | None = None
_needs_soft_restart: bool = False

# トレイアイコン用画像（assets/ の PNG を読み込み、なければフォールバック）
try:
    _ICON_NORMAL = Image.open(_ASSETS_DIR / "icon_normal.png")
    _ICON_PROCESSING = Image.open(_ASSETS_DIR / "icon_processing.png")
except Exception:
    _ICON_NORMAL = Image.new("RGB", (64, 64), color=(0, 120, 212))
    _ICON_PROCESSING = Image.new("RGB", (64, 64), color=(255, 140, 0))


def _get_tray_title() -> str:
    """トレイアイコンの通常タイトルを返す（言語切り替え対応）。"""
    return t("app.name")


def _set_tray_processing(feature: str) -> None:
    """トレイアイコンを「処理中」状態に切り替える。

    アイコン色をオレンジに変更し、ツールチップを更新する。

    Args:
        feature: "a"、"b"、または "c"。
    """
    if _tray_icon is None:
        return
    label_map = {"a": "tray.feature_a", "b": "tray.feature_b", "c": "tray.feature_c"}
    label = t(label_map.get(feature, "tray.feature_a"))
    _tray_icon.icon = _ICON_PROCESSING
    _tray_icon.title = t("tray.processing", label=label)


def _set_tray_normal() -> None:
    """トレイアイコンを通常状態に戻す。"""
    if _tray_icon is None:
        return
    _tray_icon.icon = _ICON_NORMAL
    _tray_icon.title = _get_tray_title()


# ══════════════════════════════════════════════════════════════════════
#  メイン処理（job_a / job_b / job_c コールバック）
# ══════════════════════════════════════════════════════════════════════


def _run_job_a() -> None:
    """機能 A（最新情報の取得）のメイン処理。

    feature_a モジュールへ委譲する。
    """
    assert _app_config is not None
    assert _state_manager is not None

    from app.feature_a import run as run_feature_a

    run_feature_a(
        config=_app_config,
        state_manager=_state_manager,
        on_tray_processing=lambda: _set_tray_processing("a"),
        on_tray_normal=_set_tray_normal,
    )


def _run_job_b() -> None:
    """機能 B（復習・クイズ）のメイン処理。

    feature_b モジュールへ委譲する。
    """
    assert _app_config is not None
    assert _state_manager is not None

    from app.feature_b import run as run_feature_b

    run_feature_b(
        config=_app_config,
        state_manager=_state_manager,
        on_tray_processing=lambda: _set_tray_processing("b"),
        on_tray_normal=_set_tray_normal,
    )


def _run_job_c() -> None:
    """機能 C（ページモニター）のメイン処理。

    feature_c モジュールへ委譲する。
    """
    assert _app_config is not None
    assert _state_manager is not None

    from app.feature_c import run as run_feature_c

    run_feature_c(
        config=_app_config,
        state_manager=_state_manager,
        on_tray_processing=lambda: _set_tray_processing("c"),
        on_tray_normal=_set_tray_normal,
    )


# ══════════════════════════════════════════════════════════════════════
#  システムトレイ（pystray）
# ══════════════════════════════════════════════════════════════════════


def _restart_app(icon: pystray.Icon) -> None:
    """言語変更後にトレイアイコンを再構築する（ソフトリスタート）。

    新しいプロセスを起動せず、同一プロセス内でトレイアイコンを
    停止→再作成することで、環境変数を維持したまま UI を更新する。
    """
    global _needs_soft_restart  # noqa: PLW0603

    logger.info("言語変更のためトレイアイコンを再構築します (soft restart)")
    _needs_soft_restart = True
    icon.stop()


def _create_tray_icon() -> pystray.Icon:
    """システムトレイアイコンを作成する。

    Returns:
        pystray.Icon インスタンス。
    """
    # 16x16 の簡易アイコン画像を生成
    icon_image = _ICON_NORMAL

    def on_manual_run_a(icon: pystray.Icon, item: Any) -> None:
        """手動実行: 機能 A。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["a"],),
            daemon=True,
        ).start()

    def on_manual_run_b(icon: pystray.Icon, item: Any) -> None:
        """手動実行: 機能 B。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["b"],),
            daemon=True,
        ).start()

    def on_manual_run_c(icon: pystray.Icon, item: Any) -> None:
        """手動実行: 機能 C。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["c"],),
            daemon=True,
        ).start()

    def on_manual_run_both(icon: pystray.Icon, item: Any) -> None:
        """手動実行: A + B（順次）。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["a", "b"],),
            daemon=True,
        ).start()

    def on_manual_run_all(icon: pystray.Icon, item: Any) -> None:
        """手動実行: A + B + C（順次）。"""
        assert _scheduler is not None
        threading.Thread(
            target=_scheduler.run_manual,
            args=(["a", "b", "c"],),
            daemon=True,
        ).start()

    def on_open_log(icon: pystray.Icon, item: Any) -> None:
        """ログファイルを OS デフォルトエディタで開く。"""
        log_path = get_log_file_path()
        try:
            os.startfile(log_path)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("ログファイルを開けませんでした: %s", log_path)

    def on_settings(icon: pystray.Icon, item: Any) -> None:
        """設定メニューを開く。"""
        assert _app_config is not None

        def _open_and_check_restart() -> None:
            needs_restart = open_settings(
                _app_config,
                lambda cfg: (
                    _scheduler.update_schedule(cfg) if _scheduler else None
                ),
            )
            if needs_restart:
                logger.info("Language changed — restarting application")
                _restart_app(icon)

        threading.Thread(
            target=_open_and_check_restart,
            daemon=True,
        ).start()

    def on_quit(icon: pystray.Icon, item: Any) -> None:
        """アプリを終了する。"""
        logger.info("アプリケーションを終了します")
        if _scheduler:
            _scheduler.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            t("tray.manual_run"),
            pystray.Menu(
                pystray.MenuItem(t("tray.run_a_only"), on_manual_run_a),
                pystray.MenuItem(t("tray.run_b_only"), on_manual_run_b),
                pystray.MenuItem(t("tray.run_c_only"), on_manual_run_c),
                pystray.MenuItem(t("tray.run_both"), on_manual_run_both),
                pystray.MenuItem(t("tray.run_all"), on_manual_run_all),
            ),
        ),
        pystray.MenuItem(t("tray.settings"), on_settings),
        pystray.MenuItem(t("tray.open_log"), on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("tray.quit"), on_quit),
    )

    icon = pystray.Icon(
        name="DailyBriefingAgent",
        icon=icon_image,
        title=_get_tray_title(),
        menu=menu,
    )

    return icon


# ══════════════════════════════════════════════════════════════════════
#  エントリーポイント
# ══════════════════════════════════════════════════════════════════════


def main() -> None:
    """アプリケーションのメインエントリーポイント。

    起動フロー:
    1. logger.setup_logging()
    2. config.load()
    3. setup_wizard 呼び出し（TODO）
    4. state_manager.load()
    5. scheduler.start()
    6. pystray でシステムトレイ常駐
    """
    global _app_config, _state_manager, _scheduler, _tray_icon, _needs_soft_restart

    # 1. ログ設定
    setup_logging()

    logger.info("========================================")
    logger.info("パーソナル AI デイリーブリーフィング Agent 起動")
    logger.info("========================================")

    try:
        # 2. config.yaml 読み込み
        _app_config = config_module.load()
        setup_logging(_app_config.log_level)  # ログレベルを反映
        logger.info("Config loaded: language=%s, log_level=%s", _app_config.language, _app_config.log_level)
        set_language(_app_config.language)  # 言語設定を反映

        # 3. setup_wizard 呼び出し
        if not run_wizard(_app_config):
            logger.info("セットアップウィザードが中断されました。終了します。")
            return

        # 4. state_manager.load()
        _state_manager = StateManager()
        _state_manager.load()

        # 5. scheduler.start()
        _scheduler = Scheduler()
        _scheduler.start(
            config=_app_config,
            on_job_a=_run_job_a,
            on_job_b=_run_job_b,
            on_job_c=_run_job_c,
        )

        # 5.5. 起動時キャッチアップ（スリープ復帰・遅延起動対応）
        _scheduler.check_and_run_missed_jobs(
            config=_app_config,
            last_run_a_at=_state_manager.state.last_run_a_at,
            last_run_b_at=_state_manager.state.last_run_b_at,
            last_run_c_at=_state_manager.state.last_run_c_at,
        )

        # 5.6. スリープ復帰時のキャッチアップコールバックを登録
        def _on_sleep_wake() -> None:
            """スリープ復帰検知時にキャッチアップを再実行する。"""
            logger.info("スリープ復帰検知: キャッチアップを再実行します")
            _scheduler.check_and_run_missed_jobs(
                config=_app_config,
                last_run_a_at=_state_manager.state.last_run_a_at,
                last_run_b_at=_state_manager.state.last_run_b_at,
                last_run_c_at=_state_manager.state.last_run_c_at,
            )

        _scheduler.set_on_sleep_wake(_on_sleep_wake)

        # 6. pystray でシステムトレイ常駐
        logger.info("システムトレイに常駐します")
        while True:
            _tray_icon = _create_tray_icon()
            _tray_icon.run()
            if not _needs_soft_restart:
                break
            # ソフトリスタート: フラグをリセットしてトレイアイコンを再作成
            _needs_soft_restart = False
            logger.info("トレイアイコンを再作成しました")

    except KeyboardInterrupt:
        logger.info("Ctrl+C で終了します")
    except Exception:
        logger.exception("起動中に致命的なエラーが発生しました")
    finally:
        if _scheduler:
            _scheduler.stop()
        logger.info("アプリケーションを終了しました")


if __name__ == "__main__":
    main()
