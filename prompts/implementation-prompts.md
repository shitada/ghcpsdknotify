# 実装依頼プロンプト集（GitHub Copilot 向け）

> **前提**: GitHub Copilot（Opus 4.6）で実行する。ワークスペース内のファイルは直接読み込めるため、
> 仕様書や生成済みコードの貼り付けは不要。SDK ドキュメントは URL で参照する。
>
> **使い方**: Step 1 から順に Copilot Chat に投げる。各 Step で生成されたコードがワークスペースに
> 保存されていれば、次の Step では自動的に参照される。
>
> **分割**: 全 4 Step に分割。ローカルファイル参照により 8 Step → 4 Step に圧縮。

---

## Step 1: データ層 + 入力層（5 モジュール）

```
ワークスペース内の app-specification.md を読み込み、その仕様に基づいて以下の 5 モジュールを実装してください。

## 対象モジュール
1. app/utils.py — アトミック書き込み等の共通ユーティリティ
2. app/config.py — config.yaml の読み書き・デフォルト生成
3. app/state_manager.py — state.json の読み書き・各種更新メソッド
4. app/folder_scanner.py — フォルダ再帰走査・MD ファイル読み込み・frontmatter 抽出
5. app/file_selector.py — 関心度スコアリング・通常回/ディスカバリー回のファイル選定

## 参照すべき仕様書セクション
- utils.py → 3.9「ファイル書き込み安全性」
- config.py → 5章「設定ファイル（config.yaml 案）」+ 3.9「ファイル書き込み安全性」
- state_manager.py → 3.3「内部状態ファイル（state.json）」+ 3.12「state.json 拡張」+ 3.9「ファイル書き込み安全性」
- folder_scanner.py → 3.2「フォルダ読み込み」
- file_selector.py → 3.3「ファイル選定戦略（関心度スコアリング + ディスカバリー機構）」

## 実装上の指示
- Python 3.11+、型ヒント必須、logging.getLogger(__name__) でログ出力
- docstring を全 public メソッドに記述
- テストコードは不要
- config.py と state_manager.py のアトミック書き込み（write-then-rename + .bak + フォールバック）は
  app/utils.py に共通ユーティリティ関数として定義し、両モジュールから import して共有すること
- 全フィールドを dataclass で型定義すること（IDE 補完・型チェックが効くようにする）
- app/__init__.py も空ファイルとして作成すること

## ディレクトリ構成
app/
├── __init__.py
├── utils.py
├── config.py
├── state_manager.py
├── folder_scanner.py
└── file_selector.py
```

---

## Step 2: Copilot SDK 連携 + 出力層（2 モジュール）

```
ワークスペース内の app-specification.md と、app/ 配下の生成済みコードを読み込んでください。
その上で以下の 2 モジュールを実装してください。

## GitHub Copilot SDK リファレンス
以下の URL を参照し、正確な API（クラス名・メソッド・イベント型・ツール定義）に従って実装すること。
想像で API を書かないでください:
- Python SDK README: https://github.com/github/copilot-sdk/blob/main/python/README.md
- Getting Started: https://github.com/github/copilot-sdk/blob/main/docs/getting-started.md
- MCP Overview: https://github.com/github/copilot-sdk/blob/main/docs/mcp/overview.md
- Custom Instructions: https://github.com/github/awesome-copilot/blob/main/instructions/copilot-sdk-python.instructions.md

## 対象モジュール
1. app/copilot_client.py — Copilot SDK 呼び出しの集約ラッパー
2. app/output_writer.py — MD ファイル出力・クイズ結果追記

## copilot_client.py の要件（仕様書 2.1, 3.3, 3.9, 3.11）
- 他モジュールは copilot-sdk を直接 import しない。全 SDK 呼び出しをこのクラスに集約する
- SDK は全て async/await。APScheduler の同期ジョブからは asyncio.run() で呼び出す
- CopilotClient 初期化時の設定:
  - async with CopilotClient() as client で自動ライフサイクル管理
- create_session() 時の設定（config.yaml の copilot_sdk セクションから読み込み）:
  - model: config の copilot_sdk.model（デフォルト: "claude-sonnet-4.6"）
  - system_message: {"mode": config の copilot_sdk.system_message_mode, "content": system_prompt}
  - reasoning_effort: config の copilot_sdk.reasoning_effort（デフォルト: "medium"）
  - streaming: False（ハードコード）
  - infinite_sessions: {"enabled": False}（ハードコード）
- レスポンス取得: session.send_and_wait() を使用（手動イベントハンドリング不要）
- 公開メソッド:
  1. generate_briefing_a(system_prompt, user_prompt, workiq_config) → str
     - Web 検索は SDK 組み込み機能に委譲
     - workiq_config.enabled=True かつ url が設定済みの場合、create_session() の mcp_servers パラメータで WorkIQ を HTTP MCP として登録:
       mcp_servers={"workiq": {"type": "http", "url": workiq_config.url, "tools": ["*"]}}
     - 未設定の場合は mcp_servers を省略（Web 検索のみ）
  2. generate_briefing_b(system_prompt, user_prompt) → str
     - ツール登録なし（ローカルファイルのみで完結するため）
  3. score_quiz(scoring_prompt) → dict
     - JSON レスポンスをパースして返す
  4. check_license() → bool
     - 簡単なプロンプトで接続テスト
- 全メソッド共通リトライ: 指数バックオフ（5s→15s→45s、最大3回）
- タイムアウト: config の sdk_timeout（120秒）/ quiz_scoring_timeout（30秒）

## output_writer.py の要件（仕様書 3.4）
- 出力先: state.json の output_folder_path → 未設定なら _briefings を新規作成（名前衝突時は連番）
- ファイル名: briefing_news_YYYY-MM-DD_HHmmss.md / briefing_quiz_YYYY-MM-DD_HHmmss.md
- アトミック書き込み（Step 1 の共通ユーティリティを使用）
- クイズ結果追記メソッド: 既存 MD 末尾に「📝 クイズ結果」セクション追記

## 共通ルール
- Python 3.11+、型ヒント必須、logging でログ出力、テスト不要

## ディレクトリ構成（追加分）
app/
├── copilot_client.py
└── output_writer.py
```

---

## Step 3: 実行制御（スケジューラ + メイン処理 + ログ — 3 モジュール）

```
ワークスペース内の app-specification.md と、app/ 配下の生成済みコードを読み込んでください。
その上で以下の 3 モジュールを実装してください。

## 対象モジュール
1. app/logger.py — ログ設定
2. app/scheduler.py — APScheduler による定期実行制御
3. app/main.py — エントリーポイント + メイン処理オーケストレーション

## logger.py（仕様書 3.10）
- Python 標準 logging + RotatingFileHandler
- 出力先: logs/app.log（logs/ は自動作成）、5MB×5世代
- フォーマット: %(asctime)s [%(levelname)s] %(name)s - %(message)s
- コンソール出力なし（GUI アプリのため）
- 公開: setup_logging(log_level: str) → None

## scheduler.py（仕様書 3.1）
- APScheduler CronTrigger で job_a / job_b を登録
- config の schedule.feature_a / feature_b からスケジュール読み込み
- 同時刻重複の避譲: 他方が実行中なら自身を 3 分後にリスケジュール（threading.Lock 等）
- 手動実行: 指定機能を即座に実行。両方の場合は A→B 順次。
- 公開: start(), stop(), update_schedule(config), run_manual(features, on_job_a, on_job_b)

## main.py（仕様書 6章「処理フロー」全体）

### 起動フロー
1. logger.setup_logging()
2. config.load()
3. setup_wizard 呼び出し（※ Step 4 で実装。今回は TODO コメント）
4. state_manager.load()
5. scheduler.start()
6. pystray でシステムトレイ常駐

### メイン処理（job_a / job_b コールバック）
仕様書 6章の Step 1〜10 を実装する:
1. folder_scanner.scan() でフォルダ走査
2. B ジョブのみ: pending_quizzes の未回答分を自動不正解処理（quiz_history 更新）
3. file_selector.select_files() でファイル選定
4. プロンプト構築（仕様書 3.3 のテンプレートに変数埋め込み）
   - {file_contents} は config の copilot_sdk.max_context_tokens を目安にトークン数を推定し、超過する場合は古いファイルから切り詰める
   - A: ツール使い分けルールを含む。WorkIQ MCP 未設定時は社内検索ルールを除外
   - B: topic_key ルール含む、{quiz_schedule_info} 埋め込み
   - ディスカバリー回はシステムプロンプトに追記
5. copilot_client で SDK 呼び出し
6. output_writer.write_briefing() で MD 出力
7. A の場合: WorkIQ MCP 未設定検知（仕様書 3.3「WorkIQ MCP が未設定の場合の動作」）
   - config.yaml の workiq_mcp.enabled=false または url が空の場合、
     初回起動時および5回に1回の頻度で notify_workiq_setup() で通知
   - suppress_setup_prompt=true の場合はスキップ
8. B の場合: MD から <!-- topic_key: ... --> を抽出 → pending_quizzes に登録
9. state.json 更新（run_count, random_pick_history, pending_quizzes 等）
10. 通知（※ Step 4 で実装。今回は TODO コメント）

### システムトレイ（pystray）
- メニュー: 手動実行（A/B チェックボックス付き）、設定（TODO）、ログを開く、終了
- 終了時 scheduler.stop()

### プロンプトテンプレート
仕様書 3.3 のシステムプロンプト（A用・B用）+ ユーザープロンプト（A用・B用）を
Python 文字列定数として定義する。

## 共通ルール
- Python 3.11+、型ヒント必須、logging でログ出力、テスト不要

## ディレクトリ構成（追加分）
app/
├── logger.py
├── scheduler.py
└── main.py
```

---

## Step 4: UI・採点・補助機能 + 結合（7 モジュール + 結合 + 最終成果物）

```
ワークスペース内の app-specification.md と、app/ 配下の生成済みコードをすべて読み込んでください。
その上で以下の 7 モジュールの新規実装 + main.py の結合修正 + 最終成果物の生成を行ってください。

## GitHub Copilot SDK リファレンス（quiz_scorer で間接使用）
- Python SDK README: https://github.com/github/copilot-sdk/blob/main/python/README.md
- Getting Started: https://github.com/github/copilot-sdk/blob/main/docs/getting-started.md
※ quiz_scorer は copilot_client.score_quiz() 経由で SDK を呼び出す。SDK を直接 import しないこと。

## 対象モジュール（新規 7 つ）
1. app/notifier.py — winotify トースト通知
2. app/viewer.py — tkinter + tkinterweb MD プレビューア + クイズフォーム
3. app/quiz_server.py — 127.0.0.1 ローカル HTTP サーバー
4. app/quiz_scorer.py — Q1+Q2 一括採点 + 未回答自動不正解
5. app/spaced_repetition.py — 間隔反復アルゴリズム
6. app/setup_wizard.py — 起動時前提チェック GUI
7. app/settings_ui.py — 設定メニュー GUI

## 各モジュールの要件

### notifier.py（仕様書 3.5）
- winotify でトースト通知。通知クリック → viewer 起動
- 公開: notify_briefing(file_path, feature, on_click), notify_warning(title, message), notify_workiq_setup(on_click)
- notify_workiq_setup: WorkIQ MCP 未設定時にトースト通知を表示し、クリックでセットアップガイドダイアログ（tkinter）を開く
- セットアップガイドダイアログの内容（仕様書 3.3 に準拠）:
  - WorkIQ MCP の概要説明
  - MCP サーバー URL の入力フィールド（入力→ config.yaml の workiq_mcp.url に保存 + enabled=true に設定）
  - 「詳細な設定方法」リンク（社内 Wiki / Docs へのリンク）
  - 「後で設定する」ボタン（ダイアログを閉じる）
  - 「今後表示しない」チェックボックス（config.yaml の workiq_mcp.suppress_setup_prompt を true に設定）
- config の notification.enabled が false なら通知スキップ
- winotify 失敗は軽微エラー（ログのみ）

### viewer.py（仕様書 3.6）
- tkinter + tkinterweb で MD → HTML レンダリング表示
- markdown2 で変換（extras: fenced-code-blocks, tables, code-friendly）
- CSS スタイル適用。HTML ファイルは生成しない
- briefing_quiz_*.md の場合: クイズセクションにフォーム要素を自動挿入
  - Q1: ラジオボタン（A/B/C/D）、Q2: テキストエリア
  - 「まとめて採点する」ボタン → quiz_server に POST
  - 採点結果を動的に表示
- ビューア表示時に quiz_server を内部で起動し、閉じる時に停止する（ライフサイクルは viewer が管理）
- 公開: open_viewer(file_path, copilot_client, state_manager, output_writer)

### quiz_server.py（仕様書 3.6, 3.11）
- http.server で 127.0.0.1:ランダムポート、daemon スレッドで起動
- POST /quiz/submit → quiz_scorer で採点 → JSON レスポンス
- 公開: start(scorer) → int（ポート）, stop()

### quiz_scorer.py（仕様書 3.11）
- copilot_client.score_quiz() 経由で採点
- topic_key からソース MD を読み込み {source_content} に設定
- 採点プロンプトは仕様書 3.11 のテンプレートに変数埋め込み
- 結果を state_manager + output_writer に反映
- 公開: score(topic_key, q1_choice, q2_answer, briefing_file) → QuizScoreResult
- 公開: process_unanswered(pending_quizzes) → None

### spaced_repetition.py（仕様書 3.12）
- Level 0-5、間隔 [1,3,7,14,30,60] 日
- 昇格: Q1正解+Q2 good → +1。降格: Q1不正解 or Q2 poor → 0。据え置き: Q2 partial
- 公開: calculate_next_level(), calculate_next_quiz_date(), get_due_topics(), build_quiz_schedule_info()

### setup_wizard.py（仕様書 3.8）
- 4 項目チェック: gh CLI → gh auth → Copilot ライセンス → input_folders 空でないこと
- tkinter ダイアログで ✅/❌ 表示 + ガイド（ダウンロードリンク、ログインボタン等）
- 全パスで True を返す
- 公開: run_wizard(config, copilot_client) → bool

### settings_ui.py（仕様書 3.7）
- tkinter ダイアログ: スケジュール（A/B 独立、曜日チェックボックス+時刻）、フォルダ、通知 ON/OFF
- 保存で config.save() + scheduler.update_schedule()
- 公開: open_settings(config, on_save)

## 結合タスク（main.py の更新）
main.py の TODO コメント箇所を実コードに置き換える:
- setup_wizard の呼び出し
- notifier の呼び出し（ブリーフィング生成後の通知）
- settings_ui の呼び出し（トレイメニューの「設定」）

## 最終成果物（追加生成）
1. requirements.txt — 全依存ライブラリ + バージョン指定:
   github-copilot-sdk, APScheduler>=3.10, pystray>=0.19,
   winotify>=1.1, tkinterweb>=3.24, markdown2>=2.4, Pillow>=10.0, PyYAML>=6.0
2. README.md — アプリ概要、前提条件（Python, gh CLI, Copilot ライセンス）、
   インストール手順、起動方法（python -m app.main）、設定ファイル説明

## 共通ルール
- Python 3.11+、Windows 10/11 専用
- 型ヒント必須、logging でログ出力、テスト不要

## 最終ディレクトリ構成
ghcpsdknotify/
├── app/
│   ├── __init__.py
│   ├── main.py（更新）
│   ├── utils.py
│   ├── config.py
│   ├── state_manager.py
│   ├── folder_scanner.py
│   ├── file_selector.py
│   ├── copilot_client.py
│   ├── output_writer.py
│   ├── scheduler.py
│   ├── logger.py
│   ├── notifier.py
│   ├── viewer.py
│   ├── quiz_server.py
│   ├── quiz_scorer.py
│   ├── spaced_repetition.py
│   ├── setup_wizard.py
│   └── settings_ui.py
├── config.yaml
├── state.json
├── logs/
├── requirements.txt
└── README.md
```
