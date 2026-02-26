"""設定メニュー（GUI）モジュール。

システムトレイの「設定」メニューから呼び出される tkinter ダイアログ。
スケジュール（A/B 独立）、読み込みフォルダ、通知 ON/OFF を変更できる。
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

from app import config as config_module
from app.config import AppConfig, ScheduleEntry
from app.i18n import SUPPORTED_LANGUAGES, get_language, set_language, t
from app.sample_data import generate_sample_data

logger = logging.getLogger(__name__)


def _log_setting_changes(
    config: AppConfig,
    *,
    old_language: str,
    old_schedule_a: list[tuple[str, str]],
    old_schedule_b: list[tuple[str, str]],
    old_folders: list[str],
    old_notif_enabled: bool,
    old_notif_click: bool,
) -> None:
    """変更された設定項目をログに記録する。"""
    changes: list[str] = []

    if old_language != config.language:
        changes.append(f"language: {old_language} -> {config.language}")

    new_schedule_a = [(e.day_of_week, e.hour) for e in config.schedule.feature_a]
    if old_schedule_a != new_schedule_a:
        changes.append(f"schedule.feature_a: {old_schedule_a} -> {new_schedule_a}")

    new_schedule_b = [(e.day_of_week, e.hour) for e in config.schedule.feature_b]
    if old_schedule_b != new_schedule_b:
        changes.append(f"schedule.feature_b: {old_schedule_b} -> {new_schedule_b}")

    if old_folders != list(config.input_folders):
        changes.append(f"input_folders: {old_folders} -> {list(config.input_folders)}")

    if old_notif_enabled != config.notification.enabled:
        changes.append(f"notification.enabled: {old_notif_enabled} -> {config.notification.enabled}")

    if old_notif_click != config.notification.open_file_on_click:
        changes.append(f"notification.open_file_on_click: {old_notif_click} -> {config.notification.open_file_on_click}")

    if changes:
        for change in changes:
            logger.info("Setting changed: %s", change)
    else:
        logger.info("Settings saved (no changes)")


# 曜日ラベルキー → APScheduler 用文字列のマッピング
_WEEKDAY_KEYS = [
    ("settings.day.mon", "mon"),
    ("settings.day.tue", "tue"),
    ("settings.day.wed", "wed"),
    ("settings.day.thu", "thu"),
    ("settings.day.fri", "fri"),
    ("settings.day.sat", "sat"),
    ("settings.day.sun", "sun"),
]


def _parse_day_of_week(day_str: str) -> list[str]:
    """day_of_week 文字列を個別の曜日リストに展開する。

    Args:
        day_str: "mon-fri" や "mon,wed,fri" 形式。

    Returns:
        曜日文字列のリスト。
    """
    result: list[str] = []
    all_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    for part in day_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start = start.strip()
            end = end.strip()
            try:
                start_idx = all_days.index(start)
                end_idx = all_days.index(end)
                if start_idx <= end_idx:
                    result.extend(all_days[start_idx : end_idx + 1])
                else:
                    result.extend(all_days[start_idx:] + all_days[: end_idx + 1])
            except ValueError:
                result.append(part)
        else:
            if part in all_days:
                result.append(part)

    return result


def _days_to_string(selected_days: list[str]) -> str:
    """選択された曜日リストを day_of_week 文字列に変換する。

    Args:
        selected_days: 曜日文字列のリスト。

    Returns:
        カンマ区切りの曜日文字列。
    """
    return ",".join(selected_days) if selected_days else "mon-fri"


def open_settings(
    config: AppConfig,
    on_save: Callable[[AppConfig], None] | None = None,
) -> bool:
    """設定ダイアログを開く。

    Args:
        config: 現在のアプリケーション設定。
        on_save: 保存時のコールバック（設定変更後に呼ばれる）。

    Returns:
        True の場合、言語変更によりアプリの再起動が必要。
    """
    needs_restart = False
    try:
        root = tk.Tk()
        root.title(t("settings.title"))
        root.geometry("650x600")
        root.resizable(False, False)

        # ウィンドウアイコン設定
        _icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon_normal.png"
        if _icon_path.exists():
            try:
                _icon_img = tk.PhotoImage(file=str(_icon_path))
                root.iconphoto(True, _icon_img)
            except Exception:
                pass  # アイコン設定失敗は無視

        # ノートブック（タブ）
        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ─── タブ 0: 一般（言語選択） ───
        general_tab = ttk.Frame(notebook, padding=10)
        notebook.add(general_tab, text=t("settings.tab.general"))

        ttk.Label(general_tab, text=t("settings.language_label"), font=("", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        # 言語ドロップダウン
        lang_codes = list(SUPPORTED_LANGUAGES.keys())
        lang_labels = list(SUPPORTED_LANGUAGES.values())
        current_lang_idx = lang_codes.index(config.language) if config.language in lang_codes else 0

        lang_var = tk.StringVar(master=root, value=lang_labels[current_lang_idx])
        lang_combo = ttk.Combobox(general_tab, textvariable=lang_var, values=lang_labels, state="readonly", width=20)
        lang_combo.pack(anchor=tk.W, pady=(0, 10))

        # ─── タブ1: スケジュール ───
        schedule_tab = ttk.Frame(notebook, padding=10)
        notebook.add(schedule_tab, text=t("settings.tab.schedule"))

        # 機能 A スケジュール
        ttk.Label(schedule_tab, text=t("settings.feature_a_header"), font=("", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        a_frame = ttk.LabelFrame(schedule_tab, text=t("settings.feature_a_schedule"), padding=8)
        a_frame.pack(fill=tk.X, pady=(0, 15))

        # 曜日チェックボックス（機能 A）
        ttk.Label(a_frame, text=t("settings.days_label")).pack(anchor=tk.W)
        a_day_frame = ttk.Frame(a_frame)
        a_day_frame.pack(anchor=tk.W, pady=3)

        a_day_vars: dict[str, tk.BooleanVar] = {}
        # 既存設定から曜日を取得
        a_existing_days: list[str] = []
        for entry in config.schedule.feature_a:
            a_existing_days.extend(_parse_day_of_week(entry.day_of_week))
        a_existing_days = list(set(a_existing_days))

        for i18n_key, key in _WEEKDAY_KEYS:
            var = tk.BooleanVar(master=root, value=key in a_existing_days)
            a_day_vars[key] = var
            ttk.Checkbutton(a_day_frame, text=t(i18n_key), variable=var).pack(side=tk.LEFT, padx=3)

        # ショートカットボタン
        a_shortcut_frame = ttk.Frame(a_frame)
        a_shortcut_frame.pack(anchor=tk.W, pady=3)

        def a_select_weekdays() -> None:
            for d in ["mon", "tue", "wed", "thu", "fri"]:
                a_day_vars[d].set(True)
            for d in ["sat", "sun"]:
                a_day_vars[d].set(False)

        def a_select_everyday() -> None:
            for var in a_day_vars.values():
                var.set(True)

        ttk.Button(a_shortcut_frame, text=t("settings.weekdays_only"), command=a_select_weekdays, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(a_shortcut_frame, text=t("settings.every_day"), command=a_select_everyday, width=10).pack(side=tk.LEFT, padx=3)

        # 時刻選択（機能 A）
        ttk.Label(a_frame, text=t("settings.hour_label")).pack(anchor=tk.W, pady=(5, 0))
        a_hours_frame = ttk.Frame(a_frame)
        a_hours_frame.pack(anchor=tk.W, pady=3)

        a_existing_hours = [entry.hour for entry in config.schedule.feature_a]
        a_hour_var = tk.StringVar(master=root, value=", ".join(a_existing_hours))
        a_hour_entry = ttk.Entry(a_hours_frame, textvariable=a_hour_var, width=30)
        a_hour_entry.pack(side=tk.LEFT)
        ttk.Label(a_hours_frame, text=t("settings.hour_hint"), foreground="gray").pack(side=tk.LEFT, padx=5)

        # 機能 B スケジュール
        ttk.Label(schedule_tab, text=t("settings.feature_b_header"), font=("", 11, "bold")).pack(anchor=tk.W, pady=(10, 5))

        b_frame = ttk.LabelFrame(schedule_tab, text=t("settings.feature_b_schedule"), padding=8)
        b_frame.pack(fill=tk.X, pady=(0, 10))

        # 曜日チェックボックス（機能 B）
        ttk.Label(b_frame, text=t("settings.days_label")).pack(anchor=tk.W)
        b_day_frame = ttk.Frame(b_frame)
        b_day_frame.pack(anchor=tk.W, pady=3)

        b_day_vars: dict[str, tk.BooleanVar] = {}
        b_existing_days: list[str] = []
        for entry in config.schedule.feature_b:
            b_existing_days.extend(_parse_day_of_week(entry.day_of_week))
        b_existing_days = list(set(b_existing_days))

        for i18n_key, key in _WEEKDAY_KEYS:
            var = tk.BooleanVar(master=root, value=key in b_existing_days)
            b_day_vars[key] = var
            ttk.Checkbutton(b_day_frame, text=t(i18n_key), variable=var).pack(side=tk.LEFT, padx=3)

        # ショートカットボタン
        b_shortcut_frame = ttk.Frame(b_frame)
        b_shortcut_frame.pack(anchor=tk.W, pady=3)

        def b_select_weekdays() -> None:
            for d in ["mon", "tue", "wed", "thu", "fri"]:
                b_day_vars[d].set(True)
            for d in ["sat", "sun"]:
                b_day_vars[d].set(False)

        def b_select_everyday() -> None:
            for var in b_day_vars.values():
                var.set(True)

        ttk.Button(b_shortcut_frame, text=t("settings.weekdays_only"), command=b_select_weekdays, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(b_shortcut_frame, text=t("settings.every_day"), command=b_select_everyday, width=10).pack(side=tk.LEFT, padx=3)

        # 時刻選択（機能 B）
        ttk.Label(b_frame, text=t("settings.hour_label")).pack(anchor=tk.W, pady=(5, 0))
        b_hours_frame = ttk.Frame(b_frame)
        b_hours_frame.pack(anchor=tk.W, pady=3)

        b_existing_hours = [entry.hour for entry in config.schedule.feature_b]
        b_hour_var = tk.StringVar(master=root, value=", ".join(b_existing_hours))
        b_hour_entry = ttk.Entry(b_hours_frame, textvariable=b_hour_var, width=30)
        b_hour_entry.pack(side=tk.LEFT)
        ttk.Label(b_hours_frame, text=t("settings.hour_hint"), foreground="gray").pack(side=tk.LEFT, padx=5)

        # ─── タブ2: フォルダ ───
        folder_tab = ttk.Frame(notebook, padding=10)
        notebook.add(folder_tab, text=t("settings.tab.folders"))

        ttk.Label(folder_tab, text=t("settings.target_folders"), font=("", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        folder_list_frame = ttk.Frame(folder_tab)
        folder_list_frame.pack(fill=tk.BOTH, expand=True)

        folder_listbox = tk.Listbox(folder_list_frame, height=10)
        folder_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        folder_scrollbar = ttk.Scrollbar(folder_list_frame, orient=tk.VERTICAL, command=folder_listbox.yview)
        folder_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        folder_listbox.config(yscrollcommand=folder_scrollbar.set)

        # 既存フォルダを表示
        for folder in config.input_folders:
            folder_listbox.insert(tk.END, folder)

        folder_btn_frame = ttk.Frame(folder_tab)
        folder_btn_frame.pack(fill=tk.X, pady=(5, 0))

        def add_folder() -> None:
            """フォルダ選択ダイアログで追加する。"""
            folder = filedialog.askdirectory(title=t("settings.select_folder"))
            if folder:
                # 重複チェック
                existing = list(folder_listbox.get(0, tk.END))
                if folder not in existing:
                    folder_listbox.insert(tk.END, folder)

        def remove_folder() -> None:
            """選択中のフォルダを削除する。"""
            selection = folder_listbox.curselection()
            if selection:
                folder_listbox.delete(selection[0])

        ttk.Button(folder_btn_frame, text=t("settings.add"), command=add_folder, width=10).pack(side=tk.LEFT, padx=3)
        ttk.Button(folder_btn_frame, text=t("settings.remove"), command=remove_folder, width=10).pack(side=tk.LEFT, padx=3)

        def create_sample() -> None:
            """サンプルデータを生成してフォルダ一覧に追加する。"""
            folder = filedialog.askdirectory(title=t("sample.select_folder"))
            if not folder:
                return
            try:
                created = generate_sample_data(Path(folder), get_language())
                if created:
                    existing = list(folder_listbox.get(0, tk.END))
                    if folder not in existing:
                        folder_listbox.insert(tk.END, folder)
                    messagebox.showinfo(
                        t("sample.success_title"),
                        t("sample.success_message", count=len(created)),
                    )
                else:
                    messagebox.showinfo(
                        t("sample.success_title"),
                        t("sample.all_exist_message"),
                    )
            except Exception as exc:
                logger.exception("サンプルデータ生成に失敗")
                messagebox.showerror(
                    t("sample.error_title"),
                    t("sample.error_message", error=str(exc)),
                )

        ttk.Button(folder_btn_frame, text=t("sample.button_label"), command=create_sample, width=18).pack(side=tk.LEFT, padx=3)

        # ─── タブ3: 通知 ───
        notif_tab = ttk.Frame(notebook, padding=10)
        notebook.add(notif_tab, text=t("settings.tab.notifications"))

        ttk.Label(notif_tab, text=t("settings.notification_header"), font=("", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        notif_enabled_var = tk.BooleanVar(master=root, value=config.notification.enabled)
        ttk.Checkbutton(
            notif_tab,
            text=t("settings.enable_toast"),
            variable=notif_enabled_var,
        ).pack(anchor=tk.W, pady=3)

        open_on_click_var = tk.BooleanVar(master=root, value=config.notification.open_file_on_click)
        ttk.Checkbutton(
            notif_tab,
            text=t("settings.open_viewer_on_click"),
            variable=open_on_click_var,
        ).pack(anchor=tk.W, pady=3)

        # ─── ボタンフレーム ───
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        def on_save_click() -> None:
            """設定を保存して閉じる。"""
            # 変更前の値を保存
            old_schedule_a = [(e.day_of_week, e.hour) for e in config.schedule.feature_a]
            old_schedule_b = [(e.day_of_week, e.hour) for e in config.schedule.feature_b]
            old_folders = list(config.input_folders)
            old_notif_enabled = config.notification.enabled
            old_notif_click = config.notification.open_file_on_click

            # スケジュール A
            a_selected_days = [k for k, v in a_day_vars.items() if v.get()]
            a_hours = [h.strip() for h in a_hour_var.get().split(",") if h.strip()]
            a_day_str = _days_to_string(a_selected_days)

            config.schedule.feature_a = [
                ScheduleEntry(day_of_week=a_day_str, hour=h) for h in a_hours
            ] if a_hours else [ScheduleEntry(day_of_week=a_day_str, hour="9")]

            # スケジュール B
            b_selected_days = [k for k, v in b_day_vars.items() if v.get()]
            b_hours = [h.strip() for h in b_hour_var.get().split(",") if h.strip()]
            b_day_str = _days_to_string(b_selected_days)

            config.schedule.feature_b = [
                ScheduleEntry(day_of_week=b_day_str, hour=h) for h in b_hours
            ] if b_hours else [ScheduleEntry(day_of_week=b_day_str, hour="8")]

            # フォルダ
            config.input_folders = list(folder_listbox.get(0, tk.END))

            # 通知
            config.notification.enabled = notif_enabled_var.get()
            config.notification.open_file_on_click = open_on_click_var.get()

            # 言語
            old_language = config.language
            selected_label = lang_var.get()
            for code, label in SUPPORTED_LANGUAGES.items():
                if label == selected_label:
                    config.language = code
                    set_language(code)
                    break

            language_changed = old_language != config.language

            # 変更内容をログに記録
            _log_setting_changes(
                config,
                old_language=old_language,
                old_schedule_a=old_schedule_a,
                old_schedule_b=old_schedule_b,
                old_folders=old_folders,
                old_notif_enabled=old_notif_enabled,
                old_notif_click=old_notif_click,
            )

            # config.yaml に保存
            config_module.save(config)

            # コールバック
            if on_save is not None:
                on_save(config)

            root.destroy()

            # 言語が変更された場合、再起動を通知
            if language_changed:
                nonlocal needs_restart
                needs_restart = True
                messagebox.showinfo(
                    t("settings.restart_title"),
                    t("settings.restart_message"),
                )

        def on_cancel_click() -> None:
            """キャンセルして閉じる。"""
            root.destroy()

        ttk.Button(btn_frame, text=t("common.save"), command=on_save_click, width=12).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text=t("common.cancel"), command=on_cancel_click, width=12).pack(side=tk.RIGHT)

        root.mainloop()

    except Exception:
        logger.exception("設定ダイアログの表示に失敗しました")

    return needs_restart