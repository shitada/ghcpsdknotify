"""Windows トースト通知モジュール。

winotify を使用してデスクトップ通知を表示する。
通知クリック時のコールバックにより viewer を起動する。
"""

from __future__ import annotations

import logging
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from winotify import Notification, audio

from app import config as config_module
from app.config import AppConfig, NotificationConfig
from app.i18n import t

logger = logging.getLogger(__name__)


def _get_app_id() -> str:
    """通知用アプリ ID を返す。"""
    return t("app.name")


def _toast_show_with_clear(toast: Notification) -> None:
    """トースト通知を表示する（旧通知をクリアしてポップアップを確実に表示）。

    同一 Tag + Group の通知がアクションセンターに残っている場合、
    Windows は「サイレント更新」を行いバナーポップアップが出ない。
    Show() の直前に History.Clear() を実行することで常にポップアップを表示する。
    """
    # winotify show() と同等の前処理
    if toast.actions:
        toast.actions = "\n".join(toast.actions)
    else:
        toast.actions = ""
    if toast.audio == audio.Silent:
        toast.audio = '<audio silent="true" />'
    if toast.launch:
        toast.launch = 'activationType="protocol" launch="{}"'.format(toast.launch)

    from winotify import TEMPLATE

    script = TEMPLATE.format(**toast.__dict__)

    # $Notifier.Show($Toast) の前に History.Clear() を注入
    clear_cmd = (
        "[Windows.UI.Notifications.ToastNotificationManager]"
        '::History.Clear("{app_id}")\n'.format(app_id=toast.app_id)
    )
    script = script.replace(
        "$Notifier.Show($Toast);",
        clear_cmd + "$Notifier.Show($Toast);",
    )

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.Popen(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=si,
    )


def _show_notification(
    title: str,
    message: str,
    on_click: Callable[[], None] | None = None,
) -> None:
    """winotify でトースト通知を1回表示する。

    Args:
        title: 通知タイトル。
        message: 通知メッセージ。
        on_click: 通知クリック時のコールバック。
    """
    try:
        toast = Notification(
            app_id=_get_app_id(),
            title=title,
            msg=message,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)

        if on_click is not None:
            # winotify はクリック時にコマンドラインを起動する仕組みだが、
            # Python 内のコールバックを直接呼ぶことはできない。
            # launch で自プロセスのスクリプトを指定するか、
            # 代替としてクリックアクションを利用する必要がある。
            # ここではアクションボタンを追加する方式で対応。
            pass

        _toast_show_with_clear(toast)
        logger.debug("通知を表示: %s", title)
    except Exception:
        logger.exception("通知の表示に失敗しました（軽微エラー）")


def notify_briefing(
    file_path: str,
    feature: str,
    on_click: Callable[[], None] | None = None,
    *,
    notification_config: NotificationConfig | None = None,
) -> None:
    """ブリーフィング生成完了の通知を表示する。

    Args:
        file_path: 生成したブリーフィングファイルのパス。
        feature: "a"（最新情報）または "b"（復習・クイズ）。
        on_click: 通知クリック時のコールバック（ビューア起動）。
        notification_config: 通知設定。None の場合は通知を表示する。
    """
    if notification_config is not None and not notification_config.enabled:
        logger.debug("通知が無効のためスキップ: feature=%s", feature)
        return

    if feature == "a":
        title = t("notify.title_news")
        message = t("notify.body_news")
    elif feature == "b":
        title = t("notify.title_quiz")
        message = t("notify.body_quiz")
    else:
        title = t("notify.title_complete")
        message = t("notify.body_complete")

    try:
        toast = Notification(
            app_id=_get_app_id(),
            title=title,
            msg=message,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)

        # 通知の「開く」ボタンは OS デフォルトアプリでファイルを開く（フォールバック）
        toast.add_actions(label=t("notify.open"), launch=file_path)

        _toast_show_with_clear(toast)
        logger.info("ブリーフィング通知を表示: %s (%s)", feature, file_path)

        # winotify は Python コールバックを直接呼べないため、
        # 通知表示後に on_click（ビューア起動）を即座に実行する。
        if on_click is not None:
            try:
                on_click()
            except Exception:
                logger.exception("ビューア起動コールバックに失敗しました")
    except Exception:
        logger.exception("ブリーフィング通知の表示に失敗しました（軽微エラー）")


def notify_processing(
    feature: str,
    *,
    notification_config: NotificationConfig | None = None,
) -> None:
    """処理中であることを示すトースト通知を表示する。

    Args:
        feature: "a"（最新情報）または "b"（復習・クイズ）。
        notification_config: 通知設定。None の場合は通知を表示する。
    """
    if notification_config is not None and not notification_config.enabled:
        return

    if feature == "a":
        title = t("notify.processing_news_title")
        message = t("notify.processing_news_body")
    elif feature == "b":
        title = t("notify.processing_quiz_title")
        message = t("notify.processing_quiz_body")
    else:
        title = t("notify.processing_title")
        message = t("notify.processing_body")

    _show_notification(title, message)


def notify_warning(
    title: str,
    message: str,
    *,
    notification_config: NotificationConfig | None = None,
) -> None:
    """警告通知を表示する。

    Args:
        title: 通知タイトル。
        message: 通知メッセージ。
        notification_config: 通知設定。None の場合は通知を表示する。
    """
    if notification_config is not None and not notification_config.enabled:
        logger.debug("通知が無効のためスキップ: %s", title)
        return

    _show_notification(f"⚠️ {title}", message)


def notify_error(
    feature: str,
    error_message: str,
    *,
    notification_config: NotificationConfig | None = None,
) -> None:
    """実行エラーのトースト通知を表示し、ログ確認を促す。

    Args:
        feature: "a"（最新情報）または "b"（復習・クイズ）。
        error_message: エラーの概要メッセージ。
        notification_config: 通知設定。
    """
    label = t("notify.error_label_news") if feature == "a" else t("notify.error_label_quiz")
    title = t("notify.error_title", label=label)
    # エラーメッセージを短く切り詰め（トーストは表示領域が限られる）
    short_err = error_message[:120] if len(error_message) > 120 else error_message
    msg = f"{short_err}\n{t('notify.error_check_log')}"

    try:
        toast = Notification(
            app_id=_get_app_id(),
            title=title,
            msg=msg,
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        _toast_show_with_clear(toast)
        logger.info("エラー通知を表示: %s — %s", feature, short_err)
    except Exception:
        logger.exception("エラー通知の表示に失敗しました")


def notify_workiq_setup(
    on_click: Callable[[], None] | None = None,
    *,
    notification_config: NotificationConfig | None = None,
) -> None:
    """WorkIQ MCP 未設定の通知を表示する。

    クリックでセットアップガイドダイアログを開く。

    Args:
        on_click: 通知クリック時のコールバック。
        notification_config: 通知設定。None の場合は通知を表示する。
    """
    if notification_config is not None and not notification_config.enabled:
        logger.debug("通知が無効のためスキップ: WorkIQ セットアップ")
        return

    try:
        toast = Notification(
            app_id=_get_app_id(),
            title=t("notify.workiq_toast_title"),
            msg=t("notify.workiq_toast_body"),
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.add_actions(label=t("notify.workiq_setup_btn"), launch="")
        _toast_show_with_clear(toast)
        logger.info("WorkIQ セットアップ通知を表示")
    except Exception:
        logger.exception("WorkIQ セットアップ通知の表示に失敗しました（軽微エラー）")

    # 通知クリックで直接 Python コールバックを呼ぶことは winotify では困難なため、
    # セットアップガイドダイアログはトレイメニューからも開けるようにする。
    # ここでは通知表示後、別スレッドでダイアログを開く。
    if on_click is not None:
        threading.Thread(target=on_click, daemon=True).start()


def open_workiq_setup_dialog(
    app_config: AppConfig | None = None,
) -> None:
    """WorkIQ MCP セットアップガイドダイアログを開く。

    tkinter ダイアログで WorkIQ MCP の有効化を受け付け、
    config.yaml に保存する。stdio 方式のため URL は不要。

    Args:
        app_config: アプリケーション設定。None の場合は config.load() で読み込む。
    """
    if app_config is None:
        app_config = config_module.load()

    try:
        root = tk.Tk()
        root.title(t("notify.workiq_dialog_title"))
        root.geometry("500x320")
        root.resizable(False, False)

        # ウィンドウアイコン設定
        _icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon_normal.png"
        if _icon_path.exists():
            try:
                _icon_img = tk.PhotoImage(file=str(_icon_path))
                root.iconphoto(True, _icon_img)
            except Exception:
                pass  # アイコン設定失敗は無視

        # メインフレーム
        main_frame = ttk.Frame(root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 概要説明
        ttk.Label(
            main_frame,
            text=t("notify.workiq_dialog_heading"),
            font=("", 14, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))

        desc_text = t("notify.workiq_dialog_desc")
        ttk.Label(main_frame, text=desc_text, wraplength=450).pack(
            anchor=tk.W, pady=(0, 15)
        )

        # 有効化チェックボックス
        enabled_var = tk.BooleanVar(value=app_config.workiq_mcp.enabled)
        ttk.Checkbutton(
            main_frame,
            text=t("notify.workiq_enable"),
            variable=enabled_var,
        ).pack(anchor=tk.W, pady=(0, 10))

        # 「今後表示しない」チェックボックス
        suppress_var = tk.BooleanVar(
            value=app_config.workiq_mcp.suppress_setup_prompt
        )
        ttk.Checkbutton(
            main_frame,
            text=t("notify.workiq_suppress"),
            variable=suppress_var,
        ).pack(anchor=tk.W, pady=(0, 15))

        # ボタンフレーム
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        def on_save() -> None:
            """保存して閉じる。"""
            app_config.workiq_mcp.enabled = enabled_var.get()
            app_config.workiq_mcp.suppress_setup_prompt = suppress_var.get()
            if enabled_var.get():
                logger.info("WorkIQ MCP を有効化しました")
            config_module.save(app_config)
            root.destroy()

        def on_cancel() -> None:
            """キャンセルして閉じる。"""
            # 「今後表示しない」のみ反映
            if suppress_var.get() != app_config.workiq_mcp.suppress_setup_prompt:
                app_config.workiq_mcp.suppress_setup_prompt = suppress_var.get()
                config_module.save(app_config)
            root.destroy()

        ttk.Button(btn_frame, text=t("common.save"), command=on_save, width=12).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(
            btn_frame, text=t("notify.workiq_later"), command=on_cancel, width=14
        ).pack(side=tk.RIGHT)

        root.mainloop()

    except Exception:
        logger.exception("WorkIQ セットアップダイアログの表示に失敗しました")
