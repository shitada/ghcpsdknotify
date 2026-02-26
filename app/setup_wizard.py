"""起動時前提チェック（セットアップウィザード）モジュール。

アプリ起動時に動作に必要な前提条件を自動チェックし、
条件未達の場合はガイド付き GUI でユーザーを案内する。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from app import config as config_module

from app.config import AppConfig, CopilotSdkConfig
from app.copilot_client import CopilotClientWrapper
from app.i18n import get_language, t
from app.sample_data import generate_sample_data

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _check_gh_cli() -> tuple[bool, str]:
    """GitHub CLI (gh) のインストール状態を確認する。

    Returns:
        (成否, メッセージ) のタプル。
    """
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return True, f"GitHub CLI: {version}"
        return False, t("wizard.gh_cli_not_working")
    except FileNotFoundError:
        return False, t("wizard.gh_cli_not_installed")
    except subprocess.TimeoutExpired:
        return False, t("wizard.gh_cli_timeout")
    except Exception as e:
        return False, t("wizard.gh_cli_check_failed", error=e)


def _check_gh_auth() -> tuple[bool, str]:
    """GitHub 認証状態を確認する。

    Returns:
        (成否, メッセージ) のタプル。
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
        )
        if result.returncode == 0:
            return True, t("wizard.gh_auth_ok")
        return False, t("wizard.gh_auth_not_logged_in")
    except FileNotFoundError:
        return False, t("wizard.gh_cli_not_found_skip")
    except subprocess.TimeoutExpired:
        return False, t("wizard.gh_auth_timeout")
    except Exception as e:
        return False, t("wizard.gh_auth_check_failed", error=e)


async def _check_copilot_license_async(
    copilot_client: CopilotClientWrapper,
) -> tuple[bool, str]:
    """Copilot ライセンスを非同期で確認する。

    Args:
        copilot_client: Copilot クライアントラッパー。

    Returns:
        (成否, メッセージ) のタプル。
    """
    try:
        ok = await copilot_client.check_license()
        if ok:
            return True, t("wizard.copilot_license_ok")
        return False, t("wizard.copilot_license_not_assigned")
    except Exception as e:
        return False, t("wizard.copilot_license_check_failed", error=e)


def _check_copilot_license(
    copilot_client: CopilotClientWrapper,
) -> tuple[bool, str]:
    """Copilot ライセンスを確認する（同期ラッパー）。

    Args:
        copilot_client: Copilot クライアントラッパー。

    Returns:
        (成否, メッセージ) のタプル。
    """
    try:
        return asyncio.run(_check_copilot_license_async(copilot_client))
    except Exception as e:
        return False, t("wizard.copilot_license_check_failed", error=e)


def _check_copilot_license_standalone(
    sdk_config: CopilotSdkConfig,
) -> tuple[bool, str]:
    """一時的に Copilot クライアントを起動してライセンスを確認する。

    GitHub CLI と認証が OK の場合にのみ呼び出すこと。
    チェック完了後、一時クライアントは即座に停止される。

    Args:
        sdk_config: Copilot SDK の設定。

    Returns:
        (成否, メッセージ) のタプル。
    """
    async def _check() -> tuple[bool, str]:
        client = CopilotClientWrapper(sdk_config)
        await client.__aenter__()
        try:
            ok = await client.check_license()
            if ok:
                return True, t("wizard.copilot_license_ok")
            return False, t("wizard.copilot_license_not_assigned")
        finally:
            await client.__aexit__(None, None, None)

    try:
        return asyncio.run(_check())
    except Exception as e:
        return False, t("wizard.copilot_license_check_failed", error=e)


def _check_input_folders(config: AppConfig) -> tuple[bool, str]:
    """読み込み対象フォルダの設定を確認する。

    Args:
        config: アプリケーション設定。

    Returns:
        (成否, メッセージ) のタプル。
    """
    if config.input_folders:
        existing = [f for f in config.input_folders if Path(f).exists()]
        if existing:
            return True, t("wizard.folders_configured", count=len(existing))
        return False, t("wizard.folders_not_exist")
    return False, t("wizard.folders_not_set")


def run_wizard(
    config: AppConfig,
    copilot_client: CopilotClientWrapper | None = None,
) -> bool:
    """セットアップウィザードを実行する。

    4項目の前提チェックを行い、条件未達の場合は GUI で案内する。
    すべてのチェックをパスした場合のみ True を返す。

    Args:
        config: アプリケーション設定。
        copilot_client: Copilot クライアントラッパー。

    Returns:
        すべてのチェックにパスした場合は True。
    """
    logger.info("セットアップウィザードを開始します")

    # 各チェックの実行
    checks: list[dict[str, object]] = []

    # 1. gh CLI
    gh_ok, gh_msg = _check_gh_cli()
    checks.append({"name": "GitHub CLI", "ok": gh_ok, "message": gh_msg, "id": "gh"})

    # 2. gh auth
    auth_ok, auth_msg = _check_gh_auth()
    checks.append({"name": t("wizard.check_name_gh_auth"), "ok": auth_ok, "message": auth_msg, "id": "auth"})

    # 3. Copilot ライセンス
    if copilot_client is not None:
        license_ok, license_msg = _check_copilot_license(copilot_client)
    elif gh_ok and auth_ok:
        # gh + 認証 OK なら一時クライアントでライセンスチェック
        license_ok, license_msg = _check_copilot_license_standalone(config.copilot_sdk)
    else:
        license_ok, license_msg = False, t("wizard.complete_auth_first")
    checks.append({"name": t("wizard.check_name_copilot_license"), "ok": license_ok, "message": license_msg, "id": "license"})

    # 4. input_folders
    folders_ok, folders_msg = _check_input_folders(config)
    checks.append({"name": t("wizard.check_name_folders"), "ok": folders_ok, "message": folders_msg, "id": "folders"})

    # すべてパスしていれば GUI を表示せずに返す
    all_ok = all(c["ok"] for c in checks)
    if all_ok:
        logger.info("セットアップウィザード: すべてのチェックにパスしました")
        return True

    # GUI を表示
    logger.info("セットアップウィザード: 未達項目があるため GUI を表示します")
    return _show_wizard_dialog(config, checks, copilot_client)


def _show_wizard_dialog(
    config: AppConfig,
    checks: list[dict[str, object]],
    copilot_client: CopilotClientWrapper | None,
) -> bool:
    """セットアップウィザードの GUI ダイアログを表示する。

    Args:
        config: アプリケーション設定。
        checks: チェック結果のリスト。
        copilot_client: Copilot クライアントラッパー。

    Returns:
        すべてのチェックにパスした場合は True。
    """
    result = {"passed": False}

    try:
        root = tk.Tk()
        root.title(t("wizard.title"))
        root.geometry("600x500")
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

        ttk.Label(
            main_frame,
            text=t("app.name"),
            font=("", 14, "bold"),
        ).pack(anchor=tk.W, pady=(0, 5))

        ttk.Label(
            main_frame,
            text=t("wizard.checking_status"),
        ).pack(anchor=tk.W, pady=(0, 15))

        # チェック結果表示フレーム
        check_frame = ttk.LabelFrame(main_frame, text=t("wizard.prerequisites_check"), padding=10)
        check_frame.pack(fill=tk.X, pady=(0, 10))

        status_labels: dict[str, ttk.Label] = {}
        msg_labels: dict[str, ttk.Label] = {}

        for check in checks:
            row = ttk.Frame(check_frame)
            row.pack(fill=tk.X, pady=3)

            icon = "✅" if check["ok"] else "❌"
            status_lbl = ttk.Label(row, text=f"{icon} {check['name']}", width=25)
            status_lbl.pack(side=tk.LEFT)
            status_labels[str(check["id"])] = status_lbl

            msg_lbl = ttk.Label(row, text=str(check["message"]), foreground="gray")
            msg_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            msg_labels[str(check["id"])] = msg_lbl

        # アクションフレーム
        action_frame = ttk.LabelFrame(main_frame, text=t("wizard.remediation"), padding=10)
        action_frame.pack(fill=tk.X, pady=(0, 10))

        # gh CLI 未インストール
        if not checks[0]["ok"]:
            gh_frame = ttk.Frame(action_frame)
            gh_frame.pack(fill=tk.X, pady=3)
            ttk.Label(gh_frame, text=t("wizard.gh_cli_label")).pack(side=tk.LEFT)

            def install_gh() -> None:
                """winget で gh をインストールする。"""
                try:
                    subprocess.Popen(
                        ["winget", "install", "GitHub.cli"],
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
                except Exception:
                    logger.exception("gh インストールコマンドの実行に失敗")

            def open_gh_download() -> None:
                """gh ダウンロードページをブラウザで開く。"""
                import webbrowser
                webbrowser.open("https://cli.github.com")

            ttk.Button(gh_frame, text=t("wizard.install_winget"), command=install_gh).pack(side=tk.LEFT, padx=5)
            ttk.Button(gh_frame, text=t("wizard.open_download_page"), command=open_gh_download).pack(side=tk.LEFT, padx=5)

        # gh auth 未ログイン
        if not checks[1]["ok"] and checks[0]["ok"]:
            auth_frame = ttk.Frame(action_frame)
            auth_frame.pack(fill=tk.X, pady=3)
            ttk.Label(auth_frame, text=t("wizard.gh_auth_label")).pack(side=tk.LEFT)

            def run_gh_login() -> None:
                """gh auth login --web を実行する。"""
                try:
                    subprocess.Popen(
                        ["gh", "auth", "login", "--web"],
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
                except Exception:
                    logger.exception("gh auth login の実行に失敗")

            ttk.Button(auth_frame, text=t("wizard.login"), command=run_gh_login).pack(side=tk.LEFT, padx=5)

        # Copilot ライセンス
        if not checks[2]["ok"]:
            license_frame = ttk.Frame(action_frame)
            license_frame.pack(fill=tk.X, pady=3)
            ttk.Label(
                license_frame,
                text=t("wizard.copilot_license_required"),
                foreground="red",
            ).pack(side=tk.LEFT)

        # input_folders
        if not checks[3]["ok"]:
            folder_frame = ttk.Frame(action_frame)
            folder_frame.pack(fill=tk.X, pady=3)
            ttk.Label(folder_frame, text=t("wizard.folders_action_label")).pack(side=tk.LEFT)

            def select_folder() -> None:
                """フォルダ選択ダイアログで input_folders を設定する。"""
                folder = filedialog.askdirectory(title=t("wizard.select_folder"))
                if folder:
                    if folder not in config.input_folders:
                        config.input_folders.append(folder)
                    config_module.save(config)

                    # 表示を更新
                    status_labels["folders"].config(text=f"✅ {t('wizard.check_name_folders')}")
                    msg_labels["folders"].config(text=t("wizard.folder_configured_msg", folder=folder))
                    checks[3]["ok"] = True
                    logger.info("input_folders を設定: %s", folder)

            ttk.Button(folder_frame, text=t("wizard.select_folder"), command=select_folder).pack(side=tk.LEFT, padx=5)

            def create_sample() -> None:
                """サンプルデータを生成して input_folders に設定する。"""
                folder = filedialog.askdirectory(title=t("sample.select_folder"))
                if not folder:
                    return
                try:
                    created = generate_sample_data(Path(folder), get_language())
                    if created:
                        if folder not in config.input_folders:
                            config.input_folders.append(folder)
                        config_module.save(config)
                        status_labels["folders"].config(text=f"✅ {t('wizard.check_name_folders')}")
                        msg_labels["folders"].config(
                            text=t("wizard.folder_configured_msg", folder=folder)
                        )
                        checks[3]["ok"] = True
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

            ttk.Button(folder_frame, text=t("sample.button_label"), command=create_sample).pack(side=tk.LEFT, padx=5)

        # ボタンフレーム
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        def on_recheck() -> None:
            """すべてのチェックを再実行する。"""
            gh_ok_new, gh_msg_new = _check_gh_cli()
            checks[0]["ok"] = gh_ok_new
            checks[0]["message"] = gh_msg_new

            auth_ok_new, auth_msg_new = _check_gh_auth()
            checks[1]["ok"] = auth_ok_new
            checks[1]["message"] = auth_msg_new

            if copilot_client is not None:
                lic_ok_new, lic_msg_new = _check_copilot_license(copilot_client)
            elif gh_ok_new and auth_ok_new:
                lic_ok_new, lic_msg_new = _check_copilot_license_standalone(config.copilot_sdk)
            else:
                lic_ok_new, lic_msg_new = False, t("wizard.complete_auth_first")
            checks[2]["ok"] = lic_ok_new
            checks[2]["message"] = lic_msg_new

            fld_ok_new, fld_msg_new = _check_input_folders(config)
            checks[3]["ok"] = fld_ok_new
            checks[3]["message"] = fld_msg_new

            # 表示を更新
            for check in checks:
                cid = str(check["id"])
                icon = "✅" if check["ok"] else "❌"
                status_labels[cid].config(text=f"{icon} {check['name']}")
                msg_labels[cid].config(text=str(check["message"]))

            # 全パスなら自動的に閉じる
            if all(c["ok"] for c in checks):
                result["passed"] = True
                root.destroy()

        def on_continue() -> None:
            """現在の状態で続行する。

            すべてのチェックをパスしている場合のみウィザードを閉じて通常起動に進む。
            未達項目がある場合は警告メッセージを表示し、ウィザードは閉じない。
            """
            if all(c["ok"] for c in checks):
                result["passed"] = True
                root.destroy()
            else:
                failed = [str(c["name"]) for c in checks if not c["ok"]]
                items_str = "\n".join(f"  ・{name}" for name in failed)
                messagebox.showwarning(
                    t("wizard.prerequisites_incomplete_title"),
                    t("wizard.prerequisites_incomplete_msg", items=items_str),
                )

        def on_quit() -> None:
            """アプリを終了する。"""
            result["passed"] = False
            root.destroy()

        ttk.Button(btn_frame, text=t("wizard.recheck"), command=on_recheck, width=12).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text=t("wizard.continue"), command=on_continue, width=12).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(btn_frame, text=t("wizard.quit"), command=on_quit, width=12).pack(
            side=tk.RIGHT
        )

        root.mainloop()

    except Exception:
        logger.exception("セットアップウィザードの表示に失敗しました")
        # GUI が失敗した場合は続行を許可
        return True

    return result["passed"]
