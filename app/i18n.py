"""多言語対応（i18n）モジュール。

辞書ベースの翻訳システムを提供する。
`t(key)` 関数で現在の言語設定に対応する文字列を返す。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# サポートする言語の一覧（コード → 表示名）
SUPPORTED_LANGUAGES: dict[str, str] = {
    "ja": "日本語",
    "en": "English",
}

# 現在の言語（デフォルト: 日本語）
_current_language: str = "ja"

# ── 翻訳文字列カタログ ──
# キーはドット区切りの階層構造（例: "app.name", "common.save"）
_STRINGS: dict[str, dict[str, str]] = {
    "ja": {
        # アプリ全般
        "app.name": "パーソナル AI デイリーブリーフィング Agent",
        # 共通
        "common.unknown": "不明",
        "common.save": "保存",
        "common.cancel": "キャンセル",
        "common.close": "閉じる",
        # 設定画面
        "settings.title": "設定",
        "settings.tab.general": "一般",
        "settings.tab.schedule": "スケジュール",
        "settings.tab.folders": "フォルダ",
        "settings.tab.notifications": "通知",
        "settings.language_label": "言語 / Language:",
        "settings.feature_a_header": "機能 A: 最新情報の取得",
        "settings.feature_b_header": "機能 B: 復習・クイズ",
        "settings.feature_a_schedule": "機能 A スケジュール",
        "settings.feature_b_schedule": "機能 B スケジュール",
        "settings.days_label": "曜日:",
        "settings.hour_label": "時刻（時）:",
        "settings.hour_hint": "（カンマ区切りで複数指定可）",
        "settings.weekdays_only": "平日のみ",
        "settings.every_day": "毎日",
        "settings.target_folders": "読み込み対象フォルダ",
        "settings.add": "追加",
        "settings.remove": "削除",
        "settings.select_folder": "読み込み対象フォルダを選択",
        "settings.notification_header": "通知設定",
        "settings.enable_toast": "トースト通知を有効にする",
        "settings.open_viewer_on_click": "通知クリック時にビューアを開く",
        "settings.day.mon": "月",
        "settings.day.tue": "火",
        "settings.day.wed": "水",
        "settings.day.thu": "木",
        "settings.day.fri": "金",
        "settings.day.sat": "土",
        "settings.day.sun": "日",
        # セットアップウィザード
        "wizard.title": "セットアップウィザード",
        "wizard.checking_status": "起動に必要な設定を確認しています…",
        "wizard.prerequisites_check": "前提条件チェック",
        "wizard.remediation": "対処方法",
        "wizard.gh_cli_not_working": "GitHub CLI が正しく動作しません",
        "wizard.gh_cli_not_installed": "GitHub CLI (gh) がインストールされていません",
        "wizard.gh_cli_timeout": "GitHub CLI の応答がタイムアウトしました",
        "wizard.gh_cli_check_failed": "GitHub CLI の確認に失敗: {error}",
        "wizard.gh_auth_ok": "GitHub 認証済み",
        "wizard.gh_auth_not_logged_in": "GitHub に未ログインです",
        "wizard.gh_cli_not_found_skip": "GitHub CLI が見つかりません（認証チェックをスキップ）",
        "wizard.gh_auth_timeout": "認証確認がタイムアウトしました",
        "wizard.gh_auth_check_failed": "認証確認に失敗: {error}",
        "wizard.copilot_license_ok": "Copilot ライセンス確認済み",
        "wizard.copilot_license_not_assigned": "Copilot ライセンスが割り当てられていません",
        "wizard.copilot_license_check_failed": "Copilot ライセンス確認に失敗: {error}",
        "wizard.folders_configured": "読み込み対象フォルダ: {count} 件設定済み",
        "wizard.folders_not_exist": "設定済みのフォルダが存在しません",
        "wizard.folders_not_set": "読み込み対象フォルダが未設定です",
        "wizard.check_name_gh_auth": "GitHub 認証",
        "wizard.check_name_copilot_license": "Copilot ライセンス",
        "wizard.check_name_folders": "読み込み対象フォルダ",
        "wizard.complete_auth_first": "GitHub 認証を先に完了してください",
        "wizard.gh_cli_label": "GitHub CLI:",
        "wizard.install_winget": "winget でインストール",
        "wizard.open_download_page": "ダウンロードページを開く",
        "wizard.gh_auth_label": "GitHub 認証:",
        "wizard.login": "ログイン",
        "wizard.copilot_license_required": "Copilot ライセンスが必要です。管理者にお問い合わせください。",
        "wizard.folders_action_label": "読み込み対象フォルダ:",
        "wizard.select_folder": "読み込み対象フォルダを選択",
        "wizard.folder_configured_msg": "設定済み: {folder}",
        "wizard.prerequisites_incomplete_title": "前提条件が未完了です",
        "wizard.prerequisites_incomplete_msg": "以下の項目が未完了です:\n\n{items}\n\n対処後に『再チェック』を押してください。",
        "wizard.recheck": "再チェック",
        "wizard.continue": "続行",
        "wizard.quit": "終了",
        # 通知
        "notify.title_news": "📰 最新情報ブリーフィング",
        "notify.body_news": "今日のデイリーブリーフィングが生成されました。クリックして確認してください。",
        "notify.title_quiz": "📝 復習・クイズブリーフィング",
        "notify.body_quiz": "復習・クイズが生成されました。クリックして回答してください。",
        "notify.title_complete": "ブリーフィング生成完了",
        "notify.body_complete": "ブリーフィングが生成されました。",
        "notify.open": "開く",
        "notify.processing_news_title": "⏳ 最新情報を取得中…",
        "notify.processing_news_body": "Copilot SDK でブリーフィングを生成しています。完了するまでお待ちください。",
        "notify.processing_quiz_title": "⏳ 復習・クイズを生成中…",
        "notify.processing_quiz_body": "Copilot SDK でクイズを生成しています。完了するまでお待ちください。",
        "notify.processing_title": "⏳ 処理中…",
        "notify.processing_body": "ブリーフィングを生成しています。",
        "notify.error_label_news": "最新情報 (A)",
        "notify.error_label_quiz": "復習・クイズ (B)",
        "notify.error_title": "❌ {label} 実行エラー",
        "notify.error_check_log": "トレイアイコンの「ログを開く」で詳細を確認してください。",
        "notify.workiq_toast_title": "💡 社内情報検索を有効にしませんか？",
        "notify.workiq_toast_body": "WorkIQ MCP を設定すると、社内ナレッジも検索対象に含まれます。",
        "notify.workiq_setup_btn": "設定する",
        "notify.workiq_dialog_title": "WorkIQ MCP セットアップ",
        "notify.workiq_dialog_heading": "WorkIQ MCP セットアップ",
        "notify.workiq_dialog_desc": "WorkIQ MCP を有効にすると、デイリーブリーフィング生成時に\n社内ナレッジベースも検索対象に含まれるようになります。\n\nstdio 方式で自動起動されるため、URL の入力は不要です。\n※ npx がインストール済みである必要があります。",
        "notify.workiq_enable": "WorkIQ MCP を有効にする",
        "notify.workiq_suppress": "今後このダイアログを表示しない",
        "notify.workiq_later": "後で設定する",
        # ビューア
        "viewer.title": "ブリーフィング — {name}",
        "viewer.open_file": "ファイルを開く",
        "viewer.open_folder": "フォルダを開く",
        "viewer.quiz_header": "📝 クイズ回答",
        "viewer.q1_label": "Q1（4択）:",
        "viewer.q2_label": "Q2（記述）:",
        "viewer.score_all": "まとめて採点する",
        "viewer.scoring": "採点中…",
        "viewer.scored": "採点済み",
        "viewer.querying_sdk": "Copilot SDK に問い合わせ中…",
        "viewer.scoring_progress": "採点中… トピック {idx}/{total}",
        "viewer.scoring_complete": "採点完了 ✅",
        "viewer.scoring_failed": "⚠️ 採点失敗: {err}",
        "viewer.correct": "✅ 正解",
        "viewer.incorrect": "❌ 不正解（正解: {answer}）",
        "viewer.next_review": "次回出題: {date}",
        # 出力ファイル (output_writer)
        "output.quiz_result_auto": "## 📝 クイズ結果（自動処理: 未回答）\n",
        "output.quiz_result_header": "## 📝 クイズ結果（{timestamp}）\n",
        "output.unknown_topic": "不明なトピック",
        "output.q1_unanswered": "- Q1（4択）: ⬜ 未回答（不正解扱い）",
        "output.q2_unanswered": "- Q2（記述）: ⬜ 未回答（poor 扱い）",
        "output.q1_correct": "- Q1（4択）: ✅ 正解",
        "output.q1_incorrect": "- Q1（4択）: ❌ 不正解（正解: {answer}）",
        "output.q2_good": "- Q2（記述）: ✅ good — 「{feedback}」",
        "output.q2_partial": "- Q2（記述）: 🟡 partial — 「{feedback}」",
        "output.q2_poor": "- Q2（記述）: ❌ poor — 「{feedback}」",
        "output.next_quiz": "- 次回出題: {info}",
        # トレイメニュー
        "tray.manual_run": "手動実行",
        "tray.run_a_only": "最新情報（A）のみ",
        "tray.run_b_only": "復習・クイズ（B）のみ",
        "tray.run_both": "両方（A → B）",
        "tray.settings": "設定",
        "tray.open_log": "ログを開く",
        "tray.quit": "終了",
        "tray.feature_a": "最新情報 (A)",
        "tray.feature_b": "復習・クイズ (B)",
        "tray.processing": "⏳ {label} 生成中…",
        # メイン (ファイルメタ・クイズスケジュール)
        "main.modified": "更新: {date}",
        "main.unchecked": "未完了チェックボックス: {count}件",
        "main.truncated": "（... トークン上限のため省略 ...）",
        "main.q1_result_correct": "正解",
        "main.q1_result_incorrect": "不正解",
        "main.last_result": "前回: Q1={q1}, Q2={q2}",
        "main.interval": "間隔 {days}日",
        "main.topics_due_header": "以下のトピックは出題期限が到来しています:",
        "main.no_topics_due": "期限到来トピックなし",
        # 間隔反復 (spaced_repetition)
        "sr.correct": "正解",
        "sr.incorrect": "不正解",
        "sr.last_result": "前回: Q1={q1}, Q2={q2}",
        "sr.interval": "間隔 {days}日",
        "sr.topics_due_header": "以下のトピックは出題期限が到来しています:",
        "sr.no_topics_due": "期限到来トピックなし",
        # ユーティリティ (utils)
        "utils.file_recovery": "ファイル復旧",
        "utils.restored_from_backup": "{name} をバックアップから復旧しました。",
        "utils.regenerated_default": "{name} をデフォルト値で再生成しました。",
        # 採点 (quiz_scorer)
        "scorer.level_upgrade": "Level → {level} に昇格",
        "scorer.level_downgrade": "Level {level} に降格",
        "scorer.level_unchanged": "Level {level} 据え置き",
        "scorer.next_quiz_info": "{date}（{detail}）",
        "scorer.question_extraction_failed": "（問題文の抽出に失敗しました）",
        "scorer.source_not_found": "（ソース資料が見つかりませんでした）",
        # クイズサーバー (quiz_server)
        "server.error_empty_body": "リクエストボディが空です",
        "server.error_topic_key_required": "topic_key が必要です",
        "server.error_scorer_not_init": "採点機能が初期化されていません",
        "server.error_json_parse": "JSON パースエラー",
        "server.error_scoring_failed": "採点に失敗しました: {error}",
        "server.error_retry_later": "あとで再度お試しください。",
        # Restart
        "settings.restart_title": "言語変更",
        "settings.restart_message": "言語設定を反映するため、アプリを再起動します。",
        # Sample data
        "sample.button_label": "サンプルデータを作成",
        "sample.select_folder": "サンプルデータの保存先を選択",
        "sample.success_message": "サンプルデータを作成しました（{count} ファイル）",
        "sample.success_title": "サンプルデータ作成完了",
        "sample.all_exist_message": "サンプルファイルは既にすべて存在しています",
        "sample.error_title": "エラー",
        "sample.error_message": "サンプルデータの作成に失敗しました: {error}",
    },
    "en": {
        # App general
        "app.name": "Personal AI Daily Briefing Agent",
        # Common
        "common.unknown": "Unknown",
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.close": "Close",
        # Settings UI
        "settings.title": "Settings",
        "settings.tab.general": "General",
        "settings.tab.schedule": "Schedule",
        "settings.tab.folders": "Folders",
        "settings.tab.notifications": "Notifications",
        "settings.language_label": "言語 / Language:",
        "settings.feature_a_header": "Feature A: News Briefing",
        "settings.feature_b_header": "Feature B: Review & Quiz",
        "settings.feature_a_schedule": "Feature A Schedule",
        "settings.feature_b_schedule": "Feature B Schedule",
        "settings.days_label": "Days:",
        "settings.hour_label": "Hour:",
        "settings.hour_hint": "(comma-separated)",
        "settings.weekdays_only": "Weekdays only",
        "settings.every_day": "Every day",
        "settings.target_folders": "Target Folders",
        "settings.add": "Add",
        "settings.remove": "Remove",
        "settings.select_folder": "Select target folder",
        "settings.notification_header": "Notification Settings",
        "settings.enable_toast": "Enable toast notifications",
        "settings.open_viewer_on_click": "Open viewer on notification click",
        "settings.day.mon": "Mon",
        "settings.day.tue": "Tue",
        "settings.day.wed": "Wed",
        "settings.day.thu": "Thu",
        "settings.day.fri": "Fri",
        "settings.day.sat": "Sat",
        "settings.day.sun": "Sun",
        # Setup Wizard
        "wizard.title": "Setup Wizard",
        "wizard.checking_status": "Checking required settings for startup...",
        "wizard.prerequisites_check": "Prerequisites Check",
        "wizard.remediation": "Remediation",
        "wizard.gh_cli_not_working": "GitHub CLI is not working properly",
        "wizard.gh_cli_not_installed": "GitHub CLI (gh) is not installed",
        "wizard.gh_cli_timeout": "GitHub CLI response timed out",
        "wizard.gh_cli_check_failed": "Failed to check GitHub CLI: {error}",
        "wizard.gh_auth_ok": "GitHub authenticated",
        "wizard.gh_auth_not_logged_in": "Not logged in to GitHub",
        "wizard.gh_cli_not_found_skip": "GitHub CLI not found (skipping auth check)",
        "wizard.gh_auth_timeout": "Authentication check timed out",
        "wizard.gh_auth_check_failed": "Authentication check failed: {error}",
        "wizard.copilot_license_ok": "Copilot license verified",
        "wizard.copilot_license_not_assigned": "Copilot license is not assigned",
        "wizard.copilot_license_check_failed": "Failed to check Copilot license: {error}",
        "wizard.folders_configured": "Target folders: {count} configured",
        "wizard.folders_not_exist": "Configured folders do not exist",
        "wizard.folders_not_set": "Target folders are not configured",
        "wizard.check_name_gh_auth": "GitHub Auth",
        "wizard.check_name_copilot_license": "Copilot License",
        "wizard.check_name_folders": "Target Folders",
        "wizard.complete_auth_first": "Please complete GitHub authentication first",
        "wizard.gh_cli_label": "GitHub CLI:",
        "wizard.install_winget": "Install via winget",
        "wizard.open_download_page": "Open download page",
        "wizard.gh_auth_label": "GitHub Auth:",
        "wizard.login": "Login",
        "wizard.copilot_license_required": "Copilot license is required. Please contact your administrator.",
        "wizard.folders_action_label": "Target folders:",
        "wizard.select_folder": "Select target folder",
        "wizard.folder_configured_msg": "Configured: {folder}",
        "wizard.prerequisites_incomplete_title": "Prerequisites incomplete",
        "wizard.prerequisites_incomplete_msg": "The following items are incomplete:\n\n{items}\n\nPlease resolve and press 'Recheck'.",
        "wizard.recheck": "Recheck",
        "wizard.continue": "Continue",
        "wizard.quit": "Quit",
        # Notifications
        "notify.title_news": "📰 News Briefing",
        "notify.body_news": "Today's daily briefing has been generated. Click to view.",
        "notify.title_quiz": "📝 Review & Quiz Briefing",
        "notify.body_quiz": "A review quiz has been generated. Click to answer.",
        "notify.title_complete": "Briefing generated",
        "notify.body_complete": "Briefing has been generated.",
        "notify.open": "Open",
        "notify.processing_news_title": "⏳ Fetching news...",
        "notify.processing_news_body": "Generating briefing with Copilot SDK. Please wait.",
        "notify.processing_quiz_title": "⏳ Generating review quiz...",
        "notify.processing_quiz_body": "Generating quiz with Copilot SDK. Please wait.",
        "notify.processing_title": "⏳ Processing...",
        "notify.processing_body": "Generating briefing.",
        "notify.error_label_news": "News (A)",
        "notify.error_label_quiz": "Review & Quiz (B)",
        "notify.error_title": "❌ {label} execution error",
        "notify.error_check_log": "Check details via 'Open Log' in the tray icon.",
        "notify.workiq_toast_title": "💡 Enable internal knowledge search?",
        "notify.workiq_toast_body": "Setting up WorkIQ MCP includes internal knowledge base in search results.",
        "notify.workiq_setup_btn": "Set up",
        "notify.workiq_dialog_title": "WorkIQ MCP Setup",
        "notify.workiq_dialog_heading": "WorkIQ MCP Setup",
        "notify.workiq_dialog_desc": "When WorkIQ MCP is enabled, the internal knowledge base\nis included in daily briefing generation.\n\nIt launches automatically via stdio, so no URL input is needed.\n* npx must be installed.",
        "notify.workiq_enable": "Enable WorkIQ MCP",
        "notify.workiq_suppress": "Don't show this dialog again",
        "notify.workiq_later": "Set up later",
        # Viewer
        "viewer.title": "Briefing — {name}",
        "viewer.open_file": "Open File",
        "viewer.open_folder": "Open Folder",
        "viewer.quiz_header": "📝 Quiz Answers",
        "viewer.q1_label": "Q1 (Multiple Choice):",
        "viewer.q2_label": "Q2 (Written):",
        "viewer.score_all": "Score All",
        "viewer.scoring": "Scoring...",
        "viewer.scored": "Scored",
        "viewer.querying_sdk": "Querying Copilot SDK...",
        "viewer.scoring_progress": "Scoring... Topic {idx}/{total}",
        "viewer.scoring_complete": "Scoring complete ✅",
        "viewer.scoring_failed": "⚠️ Scoring failed: {err}",
        "viewer.correct": "✅ Correct",
        "viewer.incorrect": "❌ Incorrect (Answer: {answer})",
        "viewer.next_review": "Next review: {date}",
        # Output file (output_writer)
        "output.quiz_result_auto": "## 📝 Quiz Results (Auto-processed: Unanswered)\n",
        "output.quiz_result_header": "## 📝 Quiz Results ({timestamp})\n",
        "output.unknown_topic": "Unknown Topic",
        "output.q1_unanswered": "- Q1 (Multiple Choice): ⬜ Unanswered (marked incorrect)",
        "output.q2_unanswered": "- Q2 (Written): ⬜ Unanswered (marked poor)",
        "output.q1_correct": "- Q1 (Multiple Choice): ✅ Correct",
        "output.q1_incorrect": "- Q1 (Multiple Choice): ❌ Incorrect (Answer: {answer})",
        "output.q2_good": "- Q2 (Written): ✅ good — \"{feedback}\"",
        "output.q2_partial": "- Q2 (Written): 🟡 partial — \"{feedback}\"",
        "output.q2_poor": "- Q2 (Written): ❌ poor — \"{feedback}\"",
        "output.next_quiz": "- Next review: {info}",
        # Tray menu
        "tray.manual_run": "Manual Run",
        "tray.run_a_only": "News (A) Only",
        "tray.run_b_only": "Review & Quiz (B) Only",
        "tray.run_both": "Both (A → B)",
        "tray.settings": "Settings",
        "tray.open_log": "Open Log",
        "tray.quit": "Quit",
        "tray.feature_a": "News (A)",
        "tray.feature_b": "Review & Quiz (B)",
        "tray.processing": "⏳ Generating {label}...",
        # Main (file metadata / quiz schedule)
        "main.modified": "Updated: {date}",
        "main.unchecked": "Incomplete checkboxes: {count}",
        "main.truncated": "(... truncated due to token limit ...)",
        "main.q1_result_correct": "Correct",
        "main.q1_result_incorrect": "Incorrect",
        "main.last_result": "Previous: Q1={q1}, Q2={q2}",
        "main.interval": "Interval {days}d",
        "main.topics_due_header": "The following topics are due for review:",
        "main.no_topics_due": "No topics due for review",
        # Spaced repetition
        "sr.correct": "Correct",
        "sr.incorrect": "Incorrect",
        "sr.last_result": "Previous: Q1={q1}, Q2={q2}",
        "sr.interval": "Interval {days}d",
        "sr.topics_due_header": "The following topics are due for review:",
        "sr.no_topics_due": "No topics due for review",
        # Utilities (utils)
        "utils.file_recovery": "File Recovery",
        "utils.restored_from_backup": "{name} was restored from backup.",
        "utils.regenerated_default": "{name} was regenerated with default values.",
        # Quiz scorer
        "scorer.level_upgrade": "Level → {level} (upgraded)",
        "scorer.level_downgrade": "Level {level} (downgraded)",
        "scorer.level_unchanged": "Level {level} (unchanged)",
        "scorer.next_quiz_info": "{date} ({detail})",
        "scorer.question_extraction_failed": "(Question text extraction failed)",
        "scorer.source_not_found": "(Source material not found)",
        # Quiz server
        "server.error_empty_body": "Request body is empty",
        "server.error_topic_key_required": "topic_key is required",
        "server.error_scorer_not_init": "Scoring function is not initialized",
        "server.error_json_parse": "JSON parse error",
        "server.error_scoring_failed": "Scoring failed: {error}",
        "server.error_retry_later": "Please try again later.",
        # Restart
        "settings.restart_title": "Language Change",
        "settings.restart_message": "Restarting the app to apply language settings.",
        # Sample data
        "sample.button_label": "Create Sample Data",
        "sample.select_folder": "Select folder for sample data",
        "sample.success_message": "Sample data created ({count} files)",
        "sample.success_title": "Sample Data Created",
        "sample.all_exist_message": "All sample files already exist",
        "sample.error_title": "Error",
        "sample.error_message": "Failed to create sample data: {error}",
    },
}


def set_language(lang: str) -> None:
    """現在の言語を切り替える。

    Args:
        lang: 言語コード（"ja" or "en"）。
              サポート外の値が渡された場合は "ja" にフォールバックする。
    """
    global _current_language
    old = _current_language
    _current_language = lang if lang in SUPPORTED_LANGUAGES else "ja"
    if old != _current_language:
        logger.info("Language changed: %s -> %s", old, _current_language)
    else:
        logger.debug("Language set: %s (unchanged)", _current_language)


def get_language() -> str:
    """現在の言語コードを返す。"""
    return _current_language


def t(key: str, **kwargs: object) -> str:
    """翻訳済み文字列を返す。

    現在の言語に対応する文字列を検索し、見つからなければ日本語に
    フォールバックする。日本語にも存在しない場合はキー文字列を返す。

    Args:
        key: 翻訳キー（例: "app.name"）。
        **kwargs: `.format()` に渡す埋め込みパラメータ。

    Returns:
        翻訳済み文字列。
    """
    # 現在の言語 → 日本語フォールバック → キー自体
    text = _STRINGS.get(_current_language, {}).get(key)
    if text is None:
        text = _STRINGS.get("ja", {}).get(key, key)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass  # フォーマット失敗時はそのまま返す

    return text
