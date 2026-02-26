"""MD プレビューア（アプリ内簡易ビューア）モジュール。

tkinter + tkinterweb で Markdown ファイルを HTML レンダリング表示する。
復習・クイズブリーフィングの場合はフォーム要素を自動挿入し、
ローカル HTTP サーバー経由で採点する。

**スレッド安全設計**:
tkinter は単一スレッドでしか安全に動作しない。複数の tk.Tk() を
別スレッドから生成するとセグフォルトを起こす。
そのため、専用の「ビューアスレッド」で唯一の tk.Tk() を保持し、
新しいウィンドウは tk.Toplevel() で開く。
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any

import markdown2
from tkinterweb import HtmlFrame

from app.copilot_client import CopilotClientWrapper
from app.i18n import t
from app.output_writer import append_quiz_result, format_quiz_result_section
from app.quiz_scorer import build_result_item, score_async

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.copilot_client import CopilotClientWrapper
    from app.state_manager import StateManager

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  シングルスレッド tkinter マネージャ
# ══════════════════════════════════════════════════════════════════════

_tk_root: tk.Tk | None = None
_tk_thread: threading.Thread | None = None
_tk_lock = threading.Lock()
_tk_queue: queue.Queue[tuple[Any, ...]] = queue.Queue()


def _ensure_tk_thread() -> None:
    """ビューア用の専用 tkinter スレッドを起動する（まだなければ）。"""
    global _tk_root, _tk_thread

    with _tk_lock:
        if _tk_thread is not None and _tk_thread.is_alive():
            return  # 既に稼働中

        _tk_thread = threading.Thread(
            target=_tk_main_loop,
            daemon=True,
            name="ViewerTkThread",
        )
        _tk_thread.start()


def _tk_main_loop() -> None:
    """専用スレッドで唯一の tk.Tk() を作成し mainloop を回す。"""
    global _tk_root

    _tk_root = tk.Tk()
    _tk_root.withdraw()  # ルートウィンドウは非表示

    def _poll_queue() -> None:
        """キューに入っている open_viewer リクエストを処理する。"""
        try:
            while not _tk_queue.empty():
                args = _tk_queue.get_nowait()
                try:
                    _open_viewer_in_tk(*args)
                except Exception:
                    logger.exception("ビューア表示に失敗しました（キュー処理）")
        except Exception:
            pass
        if _tk_root is not None:
            _tk_root.after(200, _poll_queue)

    _tk_root.after(200, _poll_queue)

    try:
        _tk_root.mainloop()
    except Exception:
        logger.exception("tkinter mainloop が異常終了しました")
    finally:
        _tk_root = None

# ── システムダークモード検出 ──

def _is_dark_mode() -> bool:
    """» Windows のシステム設定がダークモードかどうかを返す。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0  # 0 = ダーク, 1 = ライト
    except Exception:
        return False  # デフォルトはライト


# ── 日本語フォントスタック ──

_JP_FONT_STACK = '"Yu Gothic UI", "Meiryo UI", "Segoe UI", sans-serif'
_JP_MONO_STACK = '"Cascadia Code", "Consolas", "MS Gothic", monospace'


# ── CSS スタイル ──

_CSS_LIGHT = f"""\
<style>
body {{
    font-family: {_JP_FONT_STACK};
    line-height: 1.8;
    color: #24292f;
    max-width: 1000px;
    margin: 0 auto;
    padding: 20px 28px;
    background-color: #ffffff;
}}
h1 {{ color: #1a5276; border-bottom: 2px solid #1a5276; padding-bottom: 6px; }}
h2 {{ color: #2e86c1; border-bottom: 1px solid #d4e6f1; padding-bottom: 4px; margin-top: 24px; }}
h3 {{ color: #2874a6; margin-top: 18px; }}
code {{
    background-color: #f0f0f0;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: {_JP_MONO_STACK};
    font-size: 0.9em;
}}
pre {{
    background-color: #f6f8fa;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    border: 1px solid #d0d7de;
}}
pre code {{ background: none; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #d0d7de; padding: 8px 12px; text-align: left; }}
th {{ background-color: #2e86c1; color: white; }}
tr:nth-child(even) {{ background-color: #f6f8fa; }}
blockquote {{
    border-left: 4px solid #2e86c1;
    margin: 12px 0;
    padding: 8px 16px;
    background-color: #eaf2f8;
    color: #555;
}}
a {{ color: #2e86c1; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
ul, ol {{ padding-left: 24px; }}
li {{ margin: 4px 0; }}
.quiz-form {{
    background: #eaf2f8;
    border: 2px solid #2e86c1;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
}}
.quiz-form label {{ display: block; margin: 4px 0; cursor: pointer; }}
.quiz-form textarea {{
    width: 95%;
    height: 80px;
    margin: 8px 0;
    padding: 8px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-family: {_JP_FONT_STACK};
    font-size: 0.95em;
}}
.quiz-submit-btn {{
    background-color: #2e86c1;
    color: white;
    border: none;
    padding: 10px 24px;
    border-radius: 6px;
    font-size: 1em;
    cursor: pointer;
    margin-top: 12px;
}}
.quiz-submit-btn:hover {{ background-color: #1a5276; }}
.quiz-result {{
    padding: 12px;
    margin: 8px 0;
    border-radius: 6px;
}}
.quiz-result.correct {{ background-color: #d4efdf; border: 1px solid #27ae60; }}
.quiz-result.partial {{ background-color: #fef9e7; border: 1px solid #f39c12; }}
.quiz-result.incorrect {{ background-color: #fadbd8; border: 1px solid #e74c3c; }}
</style>
"""

_CSS_DARK = f"""\
<style>
body {{
    font-family: {_JP_FONT_STACK};
    line-height: 1.8;
    color: #e6edf3;
    max-width: 1000px;
    margin: 0 auto;
    padding: 20px 28px;
    background-color: #0d1117;
}}
h1 {{ color: #58a6ff; border-bottom: 2px solid #58a6ff; padding-bottom: 6px; }}
h2 {{ color: #79c0ff; border-bottom: 1px solid #21262d; padding-bottom: 4px; margin-top: 24px; }}
h3 {{ color: #79c0ff; margin-top: 18px; }}
code {{
    background-color: #161b22;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: {_JP_MONO_STACK};
    font-size: 0.9em;
    color: #e6edf3;
}}
pre {{
    background-color: #161b22;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    border: 1px solid #30363d;
}}
pre code {{ background: none; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #30363d; padding: 8px 12px; text-align: left; }}
th {{ background-color: #1f6feb; color: #e6edf3; }}
tr:nth-child(even) {{ background-color: #161b22; }}
blockquote {{
    border-left: 4px solid #58a6ff;
    margin: 12px 0;
    padding: 8px 16px;
    background-color: #161b22;
    color: #8b949e;
}}
a {{ color: #58a6ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
ul, ol {{ padding-left: 24px; }}
li {{ margin: 4px 0; }}
.quiz-form {{
    background: #161b22;
    border: 2px solid #58a6ff;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
}}
.quiz-form label {{ display: block; margin: 4px 0; cursor: pointer; color: #e6edf3; }}
.quiz-form textarea {{
    width: 95%;
    height: 80px;
    margin: 8px 0;
    padding: 8px;
    border: 1px solid #30363d;
    border-radius: 4px;
    font-family: {_JP_FONT_STACK};
    font-size: 0.95em;
    background-color: #0d1117;
    color: #e6edf3;
}}
.quiz-submit-btn {{
    background-color: #1f6feb;
    color: white;
    border: none;
    padding: 10px 24px;
    border-radius: 6px;
    font-size: 1em;
    cursor: pointer;
    margin-top: 12px;
}}
.quiz-submit-btn:hover {{ background-color: #388bfd; }}
.quiz-result {{
    padding: 12px;
    margin: 8px 0;
    border-radius: 6px;
}}
.quiz-result.correct {{ background-color: #0d2818; border: 1px solid #238636; }}
.quiz-result.partial {{ background-color: #2a1f00; border: 1px solid #d29922; }}
.quiz-result.incorrect {{ background-color: #2d0a0e; border: 1px solid #da3633; }}
</style>
"""


def _get_css_style() -> str:
    """システム設定に応じた CSS を返す。"""
    return _CSS_DARK if _is_dark_mode() else _CSS_LIGHT

# Markdown2 変換用 extras
_MD_EXTRAS = [
    "fenced-code-blocks",
    "tables",
    "code-friendly",
    "cuddled-lists",
    "header-ids",
    "strike",
    "task_list",
]


def _md_to_html(md_content: str) -> str:
    """Markdown を HTML に変換する。

    Args:
        md_content: Markdown テキスト。

    Returns:
        HTML 文字列（CSS 付き）。
    """
    html_body = markdown2.markdown(md_content, extras=_MD_EXTRAS)
    css = _get_css_style()
    meta = '<meta charset="utf-8">'
    return f"<html><head>{meta}{css}</head><body>{html_body}</body></html>"


def _build_quiz_panel(
    parent: tk.Tk | tk.Toplevel,
    quiz_topics: list[dict[str, str]],
    dark: bool,
    panel_height: int = 320,
) -> tuple[tk.Frame, dict[str, Any]]:
    """クイズ回答用の tkinter パネルを構築する。

    tkinterweb は JavaScript を実行できないため、ネイティブ tkinter
    ウィジェット（Radiobutton / Text / Button）で回答 UI を構成する。
    パネルは固定高さのスクロール可能な Canvas でラップされるため、
    トピック数に関わらず上部のコンテンツを圧迫しない。

    Args:
        parent: 親ウィジェット。
        quiz_topics: トピック情報のリスト。
        dark: ダークモードかどうか。
        panel_height: スクロールパネルの固定高さ（ピクセル）。

    Returns:
        (パネルフレーム, ウィジェット情報辞書) のタプル。
    """
    bg = "#1e1e1e" if dark else "#f5f5f5"
    fg = "#e0e0e0" if dark else "#333333"
    entry_bg = "#2d2d2d" if dark else "#ffffff"
    accent = "#58a6ff" if dark else "#2e86c1"
    muted = "#8b949e" if dark else "#888888"

    # ── 外枠（固定高さ） ──
    outer = tk.Frame(parent, bg=bg, bd=1, relief=tk.GROOVE, height=panel_height)
    outer.pack_propagate(False)  # 内部コンテンツによる高さ変動を抑制

    # ── ヘッダー（スクロール対象外） ──
    tk.Label(
        outer, text=t("viewer.quiz_header"),
        font=("Yu Gothic UI", 11, "bold"),
        bg=bg, fg=fg, anchor=tk.W, padx=8, pady=4,
    ).pack(fill=tk.X)

    # ── スクロール可能な内部エリア ──
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    panel = tk.Frame(canvas, bg=bg)
    canvas_win = canvas.create_window((0, 0), window=panel, anchor="nw")

    def _on_panel_configure(event: tk.Event) -> None:  # type: ignore[type-arg]
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event: tk.Event) -> None:  # type: ignore[type-arg]
        canvas.itemconfig(canvas_win, width=event.width)

    panel.bind("<Configure>", _on_panel_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    # マウスホイールスクロール — パネル上にいるときだけ有効にする
    def _on_mousewheel(event: tk.Event) -> None:  # type: ignore[type-arg]
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(event: tk.Event) -> None:  # type: ignore[type-arg]
        outer.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_wheel(event: tk.Event) -> None:  # type: ignore[type-arg]
        outer.unbind_all("<MouseWheel>")

    outer.bind("<Enter>", _bind_wheel)
    outer.bind("<Leave>", _unbind_wheel)

    # ── トピックごとのウィジェット ──
    topic_widgets: list[dict[str, Any]] = []

    for i, topic in enumerate(quiz_topics):
        pattern_emoji = "📘" if topic.get("pattern") == "learning" else "📗"
        title = topic.get("title", topic.get("topic_key", ""))

        topic_frame = tk.LabelFrame(
            panel,
            text=f" {pattern_emoji} {title} ",
            font=("Yu Gothic UI", 10, "bold"),
            bg=bg, fg=fg, padx=8, pady=6,
        )
        topic_frame.pack(fill=tk.X, padx=8, pady=4)

        # Q1（4択）
        tk.Label(
            topic_frame, text=t("viewer.q1_label"),
            font=("Yu Gothic UI", 10, "bold"),
            bg=bg, fg=fg, anchor=tk.W,
        ).pack(fill=tk.X)

        # Q1 問題文（あれば表示）
        q1_question = topic.get("q1_text", "")
        if q1_question:
            tk.Label(
                topic_frame, text=q1_question,
                font=("Yu Gothic UI", 10),
                bg=entry_bg, fg=fg,
                anchor=tk.W, justify=tk.LEFT,
                wraplength=700, padx=6, pady=4,
                relief=tk.FLAT, bd=0,
            ).pack(fill=tk.X, padx=4, pady=(0, 4))

        q1_var = tk.StringVar(master=topic_frame, value="")
        q1_row = tk.Frame(topic_frame, bg=bg)
        q1_row.pack(fill=tk.X, padx=16)
        for choice in ["A", "B", "C", "D"]:
            tk.Radiobutton(
                q1_row, text=choice, variable=q1_var, value=choice,
                bg=bg, fg=fg, selectcolor=entry_bg,
                activebackground=bg, activeforeground=fg,
                font=("Yu Gothic UI", 10),
            ).pack(side=tk.LEFT, padx=10)

        q1_result = tk.Label(
            topic_frame, text="", font=("Yu Gothic UI", 10),
            bg=bg, fg=fg, anchor=tk.W, wraplength=600, justify=tk.LEFT,
        )
        q1_result.pack(fill=tk.X, pady=(2, 4))

        # Q2（記述）
        tk.Label(
            topic_frame, text=t("viewer.q2_label"),
            font=("Yu Gothic UI", 10, "bold"),
            bg=bg, fg=fg, anchor=tk.W,
        ).pack(fill=tk.X)

        # Q2 問題文（あれば表示）
        q2_question = topic.get("q2_text", "")
        if q2_question:
            tk.Label(
                topic_frame, text=q2_question,
                font=("Yu Gothic UI", 10),
                bg=entry_bg, fg=fg,
                anchor=tk.W, justify=tk.LEFT,
                wraplength=700, padx=6, pady=4,
                relief=tk.FLAT, bd=0,
            ).pack(fill=tk.X, padx=4, pady=(0, 4))

        q2_text = tk.Text(
            topic_frame, height=3, wrap=tk.WORD,
            font=("Yu Gothic UI", 10),
            bg=entry_bg, fg=fg, insertbackground=fg,
            relief=tk.SOLID, bd=1,
        )
        q2_text.pack(fill=tk.X, padx=16, pady=4)

        q2_result = tk.Label(
            topic_frame, text="", font=("Yu Gothic UI", 10),
            bg=bg, fg=fg, anchor=tk.W, wraplength=600, justify=tk.LEFT,
        )
        q2_result.pack(fill=tk.X, pady=(2, 4))

        topic_widgets.append({
            "topic_key": topic.get("topic_key", ""),
            "q1_var": q1_var,
            "q2_text": q2_text,
            "q1_result": q1_result,
            "q2_result": q2_result,
        })

    # ── 送信セクション ──
    submit_frame = tk.Frame(panel, bg=bg)
    submit_frame.pack(fill=tk.X, pady=8)

    submit_btn = tk.Button(
        submit_frame, text=t("viewer.score_all"),
        font=("Yu Gothic UI", 10, "bold"),
        bg=accent, fg="white",
        activebackground=accent, activeforeground="white",
        relief=tk.FLAT, padx=20, pady=6, cursor="hand2",
    )
    submit_btn.pack()

    progress_bar = ttk.Progressbar(
        submit_frame, mode="indeterminate", length=300,
    )
    # 初期状態では非表示

    status_label = tk.Label(
        submit_frame, text="", font=("Yu Gothic UI", 10),
        bg=bg, fg=muted,
    )
    status_label.pack(pady=2)

    panel_info: dict[str, Any] = {
        "submit_btn": submit_btn,
        "progress_bar": progress_bar,
        "status_label": status_label,
        "topic_widgets": topic_widgets,
    }

    return outer, panel_info








def open_viewer(
    file_path: str,
    state_manager: Any | None = None,
    app_config: Any | None = None,
) -> None:
    """MD プレビューアウィンドウを開く。

    専用の tkinter スレッドにリクエストをキューイングし、
    tk.Toplevel() でウィンドウを作成する。複数ウィンドウでも安全。

    Args:
        file_path: 表示する MD ファイルのパス。
        state_manager: 状態マネージャ（クイズ採点用）。
        app_config: アプリケーション設定（クイズ採点用）。
    """
    logger.info("ビューアを起動します: %s", file_path)
    path = Path(file_path)
    if not path.exists():
        logger.error("ファイルが見つかりません: %s", file_path)
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("ファイルを開けませんでした: %s", file_path)
        return

    try:
        md_content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.error("ファイル読み込み失敗: %s — %s", file_path, e)
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("ファイルを開けませんでした: %s", file_path)
        return

    # 専用 tkinter スレッドを起動（まだなければ）
    _ensure_tk_thread()

    # リクエストをキューに入れる（tkinter スレッドで処理される）
    _tk_queue.put((file_path, md_content, state_manager, app_config))


def _open_viewer_in_tk(
    file_path: str,
    md_content: str,
    state_manager: Any | None = None,
    app_config: Any | None = None,
) -> None:
    """tkinter スレッド内でビューアウィンドウを作成する（内部用）。

    この関数は必ず _tk_main_loop のスレッドから呼び出される。
    tk.Toplevel() を使い、複数ウィンドウを安全に共存させる。
    """
    global _tk_root

    if _tk_root is None:
        logger.error("tk_root が存在しません。ビューアを開けません。")
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("フォールバック: ファイルを開けませんでした: %s", file_path)
        return

    path = Path(file_path)

    # クイズ付きブリーフィングかどうか判定
    is_quiz = path.name.startswith("briefing_quiz_")

    # MD → HTML 変換
    html = _md_to_html(md_content)

    # クイズトピックを抽出（表示目的では state_manager 不要）
    quiz_topics: list[dict[str, str]] = []
    if is_quiz:
        from app.utils import extract_topic_keys
        quiz_topics = extract_topic_keys(md_content)

    # tkinter ウィンドウを作成（Toplevel を使用）
    logger.info("ビューアウィンドウを作成します")
    dark = _is_dark_mode()
    try:
        root = tk.Toplevel(_tk_root)
        root.title(t("viewer.title", name=path.name))
        root.geometry("1100x750")

        # ウィンドウアイコン設定
        _icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon_normal.png"
        if _icon_path.exists():
            try:
                _icon_img = tk.PhotoImage(file=str(_icon_path))
                root.iconphoto(True, _icon_img)
            except Exception:
                pass  # アイコン設定失敗は無視

        bg_color = "#1e1e1e" if dark else "#f0f0f0"
        fg_color = "#e0e0e0" if dark else "#333333"
        btn_bg = "#2d2d2d" if dark else "#e0e0e0"
        root.configure(bg=bg_color)

        # ── ツールバー ──
        toolbar = tk.Frame(root, bg=bg_color, height=40)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        def open_in_editor() -> None:
            try:
                os.startfile(file_path)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("ファイルを開けませんでした: %s", file_path)

        def open_folder() -> None:
            try:
                os.startfile(str(path.parent))  # type: ignore[attr-defined]
            except Exception:
                logger.exception("フォルダを開けませんでした: %s", path.parent)

        tk.Button(
            toolbar, text=t("viewer.open_file"), command=open_in_editor,
            bg=btn_bg, fg=fg_color, relief=tk.FLAT, padx=8,
            font=("Yu Gothic UI", 9),
        ).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(
            toolbar, text=t("viewer.open_folder"), command=open_folder,
            bg=btn_bg, fg=fg_color, relief=tk.FLAT, padx=8,
            font=("Yu Gothic UI", 9),
        ).pack(side=tk.LEFT, padx=5, pady=5)

        # ── クイズ回答パネル（下部に配置、HtmlFrame より先に pack）──
        panel_info: dict[str, Any] | None = None
        if quiz_topics:
            quiz_panel, panel_info = _build_quiz_panel(root, quiz_topics, dark)
            quiz_panel.pack(fill=tk.X, side=tk.BOTTOM)

        # ── HTML レンダリングフレーム ──
        html_frame = HtmlFrame(root, messages_enabled=False)
        html_frame.load_html(html)
        html_frame.pack(fill=tk.BOTH, expand=True)

        # ── クイズ採点ハンドラ ──
        if panel_info is not None and app_config is not None and state_manager is not None:
            _scoring_active = threading.Event()

            def on_quiz_submit() -> None:
                """採点ボタンのクリックハンドラ。"""
                if _scoring_active.is_set():
                    return
                _scoring_active.set()

                submit_btn = panel_info["submit_btn"]
                progress_bar = panel_info["progress_bar"]
                status_label = panel_info["status_label"]
                widgets = panel_info["topic_widgets"]

                # 回答を収集
                answers = []
                for w in widgets:
                    q1 = w["q1_var"].get()
                    q2 = w["q2_text"].get("1.0", tk.END).strip()
                    answers.append({
                        "q1": q1,
                        "q2": q2,
                        "topic_key": w["topic_key"],
                    })

                # UI をローディング状態に切り替え
                submit_btn.configure(state=tk.DISABLED, text=t("viewer.scoring"))
                progress_bar.pack(pady=4)
                progress_bar.start(15)
                status_label.configure(text=t("viewer.querying_sdk"))
                logger.info("クイズ採点を開始します (%d トピック)", len(answers))

                def _run_scoring() -> None:
                    """バックグラウンドスレッドで採点を実行する。"""
                    try:
                        async def _score_all():
                            async with CopilotClientWrapper(
                                app_config.copilot_sdk
                            ) as client:
                                results = []
                                total = len(answers)
                                for j, a in enumerate(answers):
                                    root.after(
                                        0,
                                        lambda idx=j: status_label.configure(
                                            text=t("viewer.scoring_progress", idx=idx + 1, total=total)
                                        ),
                                    )
                                    result = await score_async(
                                        topic_key=a["topic_key"],
                                        q1_choice=a["q1"],
                                        q2_answer=a["q2"],
                                        briefing_file=file_path,
                                        copilot_client=client,
                                        state_manager=state_manager,
                                        app_config=app_config,
                                    )
                                    results.append(result)
                                return results

                        scored: list = asyncio.run(_score_all())  # type: ignore[arg-type]

                        # MD ファイルに結果セクションを追記
                        result_items = [build_result_item(r) for r in scored]
                        result_section = format_quiz_result_section(result_items)
                        append_quiz_result(file_path, result_section)

                        root.after(0, lambda res=scored: _show_results(res))
                    except Exception as e:
                        logger.exception("クイズ採点に失敗しました")
                        root.after(
                            0,
                            lambda err=str(e): _show_error(err),
                        )

                def _show_results(
                    results: list,
                ) -> None:
                    """採点結果を UI に反映する。"""
                    progress_bar.stop()
                    progress_bar.pack_forget()
                    status_label.configure(text=t("viewer.scoring_complete"))
                    submit_btn.configure(text=t("viewer.scored"))
                    logger.info("クイズ採点完了")

                    for i, result in enumerate(results):
                        w = widgets[i]
                        # Q1 結果
                        if result.q1_correct:
                            q1_txt = f"{t('viewer.correct')} — {result.q1_explanation}"
                            q1_clr = "#2ea043" if dark else "#27ae60"
                        else:
                            q1_txt = (
                                t("viewer.incorrect", answer=result.q1_correct_answer)
                                + f" — {result.q1_explanation}"
                            )
                            q1_clr = "#da3633" if dark else "#e74c3c"
                        w["q1_result"].configure(text=q1_txt, fg=q1_clr)

                        # Q2 結果
                        eval_map = {
                            "good": (
                                "✅ good",
                                "#2ea043" if dark else "#27ae60",
                            ),
                            "partial": (
                                "🟡 partial",
                                "#d29922" if dark else "#f39c12",
                            ),
                            "poor": (
                                "❌ poor",
                                "#da3633" if dark else "#e74c3c",
                            ),
                        }
                        emoji, q2_clr = eval_map.get(
                            result.q2_evaluation, ("❓", fg_color)
                        )
                        q2_txt = (
                            f"{emoji} — {result.q2_feedback}\n"
                            + t("viewer.next_review", date=result.next_quiz_at)
                        )
                        w["q2_result"].configure(text=q2_txt, fg=q2_clr)

                    # HTML を再読み込み（MD に結果が追記済み）
                    try:
                        updated_md = Path(file_path).read_text(encoding="utf-8")
                        html_frame.load_html(_md_to_html(updated_md))
                    except Exception:
                        logger.exception("結果反映後の HTML 再読み込みに失敗")

                    _scoring_active.clear()

                def _show_error(error_msg: str) -> None:
                    """採点エラーを UI に表示する。"""
                    progress_bar.stop()
                    progress_bar.pack_forget()
                    err_color = "#da3633" if dark else "#e74c3c"
                    status_label.configure(
                        text=t("viewer.scoring_failed", err=error_msg), fg=err_color
                    )
                    submit_btn.configure(
                        state=tk.NORMAL, text=t("viewer.score_all")
                    )
                    _scoring_active.clear()

                threading.Thread(
                    target=_run_scoring, daemon=True, name="QuizScoring"
                ).start()

            panel_info["submit_btn"].configure(command=on_quiz_submit)

        def on_close() -> None:
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

    except Exception:
        logger.exception("ビューアの表示に失敗しました（軽微エラー）")
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("フォールバック: ファイルを開けませんでした: %s", file_path)
