# i18n�E�多言語対応）�Eロンプト実行計画

## 概要E

こ�Eアプリを日本語�E英語�E2言語対応にするための、スチE��プバイスチE��プ�Eプロンプト雁E��す、E
**吁E�EロンプトめEつずつ頁E��に実衁E*し、毎回チE��ト完亁E��確認してから次に進んでください、E

## 共通ルール

- ログメチE��ージ�E�Elogger.info/warning/error/debug`�E��E **翻訳不要E*。英語�Eままにする�E�現状の日本語ログは英語に統一してもよぁE��E
- ドキュメント文字�E�E�Eocstring�E�、コメント�E翻訳不要E
- 吁E��チE��プ完亁E��、忁E�� **チE��ト実衁E* と **アプリ起動確誁E* を行う

---

## Step 1: i18n 基盤の構篁E+ config 対忁E

```
以下�E作業を行ってください、E

### 1. `app/i18n.py` を新規作�E
辞書ベ�Eスの多言語対応モジュールを作�Eしてください、E

要件:
- `_STRINGS` 辞書に `"ja"` と `"en"` のキーを持ち、各キーの値はフラチE�� or ドット区刁E��のキーで斁E���Eを管琁E��る辞書
- `set_language(lang: str)` 関数: 現在の言語を刁E��替える�E�Eja" or "en"�E�E
- `get_language() -> str` 関数: 現在の言語を返す
- `t(key: str, **kwargs) -> str` 関数: 現在の言語に対応する文字�Eを返す。kwargs があれ�E `.format(**kwargs)` で埋め込む。キーが見つからなぁE��合�E日本語にフォールバックし、それもなければキー自体を返す
- モジュールレベル変数 `_current_language = "ja"` をデフォルトとする
- サポ�Eト言語一覧を返す `SUPPORTED_LANGUAGES` 定数も定義: `{"ja": "日本誁E, "en": "English"}`

### 2. `app/config.py` に `language` フィールドを追加
- `AppConfig` dataclass に `language: str = "ja"` フィールドを追加
- `_dict_to_app_config` で `language` を読み込むように修正
- `_app_config_to_dict` で `language` を�E力するよぁE��修正

### 3. `config.yaml` に `language: ja` を追加
- 既存�E `config.yaml` のトップレベルに `language: ja` を追加�E�Elog_level` の前あたり�E�E

### 4. i18n 斁E���Eの初期登録
こ�E段階では、以下�EカチE��リの斁E���Eキーだけ登録してください�E�後続スチE��プで吁E��ァイルの斁E���Eを追加してぁE��ため、ここでは基盤のみ�E�E
- `app.name`: アプリ名（日:"パ�Eソナル AI チE��リーブリーフィング Agent" / 英:"Personal AI Daily Briefing Agent"�E�E
- `common.unknown`: 不�E�E�日:"不�E" / 英:"Unknown"�E�E
- `common.save`: 保存（日:"保孁E / 英:"Save"�E�E 
- `common.cancel`: キャンセル�E�日:"キャンセル" / 英:"Cancel"�E�E
- `common.close`: 閉じる（日:"閉じめE / 英:"Close"�E�E

### 5. `tests/test_i18n.py` を新規作�E
以下�EチE��トケースを含めてください:
- チE��ォルト言語が "ja" であること
- `set_language("en")` で刁E��替えた後、`get_language()` ぁE"en" を返すこと
- `t("app.name")` が日本語で正しい斁E���Eを返すこと
- `set_language("en")` 後に `t("app.name")` が英語文字�Eを返すこと
- 存在しなぁE��ーを渡した場合にキー斁E���E自体が返ること
- `t("key", name="test")` の kwargs 埋め込みが動作すること

### 6. チE��ト実行と動作確誁E
以下�Eコマンドを頁E��に実行してすべて成功することを確認してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```
両方とも�E功（テスト�Eパス、アプリぁEExit Code 0 で起動�E終亁E��することを確認してから完亁E��してください、E
チE��トが失敗した場合やアプリが起動しなぁE��合�E原因を修正してから再実行してください、E
```

---

## Step 2: 設定画面�E�Eettings_ui.py�E��E多言語化 + 言語�E替UI

```
以下�E作業を行ってください、E

### 前提
- Step 1 で作�Eした `app/i18n.py` の `t()` 関数と `set_language()` を使用してください
- `app/i18n.py` に忁E��な斁E���Eを追加登録してください

### 1. `app/settings_ui.py` の全日本誁EUI 斁E���EめEi18n 匁E
以下�E斁E���EめE`app/i18n.py` の `_STRINGS` に日英両方で登録し、コード�Eの直書きを `t()` 呼び出しに置き換えてください:

- ウィンドウタイトル: "設宁E / "Settings"
- タブ名: "スケジュール" / "Schedule", "フォルダ" / "Folders", "通知" / "Notifications"
- 曜日ラベル�E�E_WEEKDAYS` リスト！E ("朁E,"mon") ↁEt() 対応。英語�E "Mon","Tue","Wed","Thu","Fri","Sat","Sun"
- ショートカチE��ボタン: "平日のみ" / "Weekdays only", "毎日" / "Every day"
- セクションヘッダー: "機�E A: 最新惁E��の取征E / "Feature A: News Briefing", "機�E B: 復習�Eクイズ" / "Feature B: Review & Quiz"
- ラベル: "曜日:" / "Days:", "時刻�E�時�E�E" / "Hour:", "�E�カンマ区刁E��で褁E��持E��可�E�E / "(comma-separated)"
- フォルダタチE "読み込み対象フォルダ" / "Target Folders", "追加" / "Add", "削除" / "Remove"
- 通知タチE "ト�Eスト通知を有効にする" / "Enable toast notifications", "通知クリチE��時にビューアを開ぁE / "Open viewer on notification click"
- ボタン: "保孁E / "Save", "キャンセル" / "Cancel"

### 2. 「一般」タブを追加して言語選択UIを�E置
- 既存�E3つのタブ�E **先頭** に「一般 / General」タブを新設
- 言語選択ドロチE�Eダウン�E�Etk.Combobox�E�を配置
  - ラベル: "言誁E/ Language:"
  - 選択肢: `i18n.SUPPORTED_LANGUAGES` の値�E�E日本誁E, "English"�E�E
  - 現在の設定値をデフォルト選抁E
- 保存時に `config.language` を更新し、`i18n.set_language()` も呼び出ぁE

### 3. チE��ト更新
- `tests/test_config.py` ぁElanguage フィールド�E追加で壊れてぁE��ぁE��確認し、忁E��に応じて修正

### 4. チE��ト実行と動作確誁E
以下�Eコマンドを頁E��に実行してすべて成功することを確認してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```
両方とも�E功（テスト�Eパス、アプリぁEExit Code 0 で起動�E終亁E��することを確認してから完亁E��してください、E
チE��トが失敗した場合やアプリが起動しなぁE��合�E原因を修正してから再実行してください、E
```

---

## Step 3: セチE��アチE�EウィザーチE+ 通知の多言語化

```
以下�E作業を行ってください、E

### 前提
- `app/i18n.py` の `t()` 関数を使用してください
- 忁E��な斁E���Eをすべて `app/i18n.py` の `_STRINGS` に日英両方で追加登録してください

### 1. `app/setup_wizard.py` の全日本誁EUI 斁E���EめEi18n 匁E
以下を含む全てのハ�Eドコードされた日本語文字�EめE`t()` に置き換えてください:
- ウィンドウタイトル・アプリ名表示
- 前提条件チェチE��のメチE��ージ�E�EitHub CLI、認証、Copilot ライセンス、フォルダ設定等！E
- セクションラベル�E�E前提条件チェチE��"、E対処方況E 等！E
- ボタンラベル�E�Ewinget でインスト�Eル"、Eダウンロード�Eージを開ぁE、Eログイン"、Eフォルダを選抁E、E再チェチE��"、E続衁E、E終亁E 等！E
- 警告ダイアログ�E�E前提条件が未完亁E��ぁE 等！E
- スチE�EタスメチE��ージ�E�E起動に忁E��な設定を確認してぁE��す…" 等！E

### 2. `app/notifier.py` の全日本誁EUI 斁E���EめEi18n 匁E
以下を含む全てのハ�Eドコードされた日本語文字�EめE`t()` に置き換えてください:
- アプリ ID 斁E���E
- 通知タイトル�E�E📰 最新惁E��ブリーフィング"、E📝 復習�Eクイズブリーフィング" 等！E
- 通知本斁E��E今日のチE��リーブリーフィングが生成されました。クリチE��して確認してください、E 等！E
- 処琁E��通知�E�E⏳ 最新惁E��を取得中…" 等！E
- エラー通知�E�E❁E{label} 実行エラー" 等！E
- WorkIQ セチE��アチE�E関連�E�ダイアログタイトル、説明文、�Eタン等！E
- ボタンラベル�E�E開く"、E設定すめE、E後で設定すめE 等！E

### 3. チE��ト実行と動作確誁E
以下�Eコマンドを頁E��に実行してすべて成功することを確認してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```
両方とも�E功（テスト�Eパス、アプリぁEExit Code 0 で起動�E終亁E��することを確認してから完亁E��してください、E
チE��トが失敗した場合やアプリが起動しなぁE��合�E原因を修正してから再実行してください、E
```

---

## Step 4: AI プロンプトチE��プレート�E多言語化

```
以下�E作業を行ってください、E

### 前提
- `app/i18n.py` の `t()` 関数、`get_language()` を使用してください
- AI プロンプトは長斁E�Eため、`t()` の辞書にそ�Eまま入れるのではなく、`app/main.py` 冁E��日英のプロンプト定数を両方定義し、`get_language()` の結果で刁E��替えるヘルパ�E関数を作�Eする方式を推奨しまぁE

### 1. `app/main.py` のプロンプトチE��プレートを多言語化
以下�E定数につぁE��英語バージョンを作�Eし、言語に応じて刁E��替えてください:

- `SYSTEM_PROMPT_A_BASE` ↁE英語版 `SYSTEM_PROMPT_A_BASE_EN` を作�E
  - "あなた�E..." ↁE"You are a 'Personal AI Daily Briefing Agent'..."
  - 出力ルールの「日本語で記述してください」�E「Write in English、E
  - チE�Eル使ぁE�Eけルールも英語化
- `_WORKIQ_TOOL_RULES` ↁE英語版を作�E
- `SYSTEM_PROMPT_B_TEMPLATE` ↁE英語版を作�E
  - topic_key ルール、�E題ルール、�E力ルールを英語化
  - `{quiz_pattern}` めE`{quiz_pattern_instruction}` のプレースホルダーはそ�Eまま維持E
- `DISCOVERY_APPENDIX` ↁE英語版を作�E
- `USER_PROMPT_A_TEMPLATE` ↁE英語版を作�E
- `USER_PROMPT_B_TEMPLATE` ↁE英語版を作�E

- 言語に応じてプロンプトを返すヘルパ�E関数を作�E:
  ```python
  def _get_prompt(ja: str, en: str) -> str:
      from app.i18n import get_language
      return en if get_language() == "en" else ja
  ```
  また�E同等�E仕絁E��で、�Eロンプトが使われる箁E��で現在の言語に対応する版が返るようにしてください、E

### 2. `app/main.py` のクイズパターン説明を多言語化
クイズパターンの instruction チE��スト！E📘 学習中のトピチE��"、E📗 振り返り" 等）も言語�E替に対応させてください、E

### 3. `app/quiz_scorer.py` の `_SCORING_PROMPT_TEMPLATE` を多言語化
- 英語版のスコアリングプロンプトを作�E
- `get_language()` で刁E��替ぁE

### 4. `app/copilot_client.py` のスコアリングシスチE��プロンプトを多言語化
- "あなた�Eクイズ採点シスチE��でぁE.." の英語版を作�E
- `get_language()` で刁E��替ぁE

### 5. チE��ト実行と動作確誁E
以下�Eコマンドを頁E��に実行してすべて成功することを確認してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```
両方とも�E功（テスト�Eパス、アプリぁEExit Code 0 で起動�E終亁E��することを確認してから完亁E��してください、E
チE��トが失敗した場合やアプリが起動しなぁE��合�E原因を修正してから再実行してください、E
```

---

## Step 5: ビューア�E�Eiewer.py�E��E多言語化

```
以下�E作業を行ってください、E

### 前提
- `app/i18n.py` の `t()` 関数を使用してください
- 忁E��な斁E���Eをすべて `app/i18n.py` の `_STRINGS` に日英両方で追加登録してください

### 1. `app/viewer.py` の全日本誁EUI 斁E���EめEi18n 匁E
以下を含む全てのハ�Eドコードされた日本語文字�EめE`t()` に置き換えてください:
- ウィンドウタイトル: "ブリーフィング  E{name}" / "Briefing  E{name}"
- チE�Eルバ�Eボタン: "ファイルを開ぁE / "Open File", "フォルダを開ぁE / "Open Folder"
- クイズパネルヘッダー: "📝 クイズ回筁E / "📝 Quiz Answers"
- クイズラベル: "Q1�E�E択！E" / "Q1 (Multiple Choice):", "Q2�E�記述�E�E" / "Q2 (Written):"
- 送信ボタン: "まとめて採点する" / "Score All", "採点中…" / "Scoring...", "採点済み" / "Scored"
- スチE�EタスメチE��ージ: "Copilot SDK に問い合わせ中…" / "Querying Copilot SDK...", "採点中… トピチE�� {idx}/{total}" / "Scoring... Topic {idx}/{total}", "採点完亁E✁E / "Scoring complete ✁E, "⚠�E�E採点失敁E {err}" / "⚠�E�EScoring failed: {err}"
- 結果表示: "✁E正解" / "✁ECorrect", "❁E不正解�E�正解: {answer}�E�E / "❁EIncorrect (Answer: {answer})", "次回�E顁E {date}" / "Next review: {date}"

### 2. チE��ト実行と動作確誁E
以下�Eコマンドを頁E��に実行してすべて成功することを確認してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```
両方とも�E功（テスト�Eパス、アプリぁEExit Code 0 で起動�E終亁E��することを確認してから完亁E��してください、E
チE��トが失敗した場合やアプリが起動しなぁE��合�E原因を修正してから再実行してください、E
```

---

## Step 6: 出力ファイル・トレイメニュー・残りモジュールの多言語化

```
以下�E作業を行ってください、E

### 前提
- `app/i18n.py` の `t()` 関数を使用してください
- 忁E��な斁E���Eをすべて `app/i18n.py` の `_STRINGS` に日英両方で追加登録してください

### 1. `app/output_writer.py` の日本語文字�EめEi18n 匁E
以下を含む全てのハ�Eドコードされた日本語文字�EめE`t()` に置き換えてください:
- クイズ結果ヘッダー: "## 📝 クイズ結果�E��E動�E琁E 未回答！E / "## 📝 Quiz Results (Auto-processed: Unanswered)"
- "## 📝 クイズ結果�E�Etimestamp}�E�E / "## 📝 Quiz Results ({timestamp})"
- フォールバック: "不�EなトピチE��" / "Unknown Topic"
- 未回答表示: "Q1�E�E択！E ⬁E未回答（不正解扱ぁE��E / "Q1 (MC): ⬁EUnanswered (marked incorrect)"
- "Q2�E�記述�E�E ⬁E未回答！Eoor 扱ぁE��E / "Q2 (Written): ⬁EUnanswered (marked poor)"
- 結果表示: "✁E正解" / "✁ECorrect", "❁E不正解�E�正解: {answer}�E�E / "❁EIncorrect (Answer: {answer})"
- "✁Egood", "🟡 partial", "❁Epoor"�E�これらは英語�Eまま両言語�E通でもOK�E�E
- "次回�E顁E {info}" / "Next review: {info}"

### 2. `app/main.py` のトレイメニュー・スチE�Eタス斁E���EめEi18n 化（�Eロンプト以外！E
以下�Eハ�Eドコードされた日本語文字�EめE`t()` に置き換えてください:
- トレイアイコンチE�EルチッチE `_TITLE_NORMAL`�E�アプリ名�E `t("app.name")` を使用�E�E
- トレイ処琁E��表示: "⏳ {label} 生�E中…" / "⏳ Generating {label}..."
- 機�Eラベル: "最新惁E�� (A)" / "News (A)", "復習�Eクイズ (B)" / "Review & Quiz (B)"
- トレイメニュー頁E��: "手動実衁E / "Run Manually", "最新惁E���E�E�E��Eみ" / "News (A) Only", "復習�Eクイズ�E�E�E��Eみ" / "Review & Quiz (B) Only", "両方�E�E ↁEB�E�E / "Both (A ↁEB)", "設宁E / "Settings", "ログを開ぁE / "Open Log", "終亁E / "Exit"
- ト�Eクン省略マ�Eカー: "�E�E.. ト�Eクン上限のため省略 ...�E�E / "(... truncated due to token limit ...)"
- 期限惁E��: "期限到来トピチE��なぁE / "No topics due for review"
- "以下�EトピチE��は出題期限が到来してぁE��ぁE" / "The following topics are due for review:"
- クイズ結果ラベル: "正解" / "Correct", "不正解" / "Incorrect"
- ファイルメタ表示: "更新: {modified}" / "Updated: {modified}"
- 未完亁E��ェチE��ボックス表示: "未完亁E��ェチE��ボックス: {count}件" / "Unchecked items: {count}"

### 3. `app/spaced_repetition.py` の日本語文字�EめEi18n 匁E
- "正解" / "Correct", "不正解" / "Incorrect"
- "期限到来トピチE��なぁE / "No topics due for review"

### 4. `app/utils.py` の日本語文字�EめEi18n 匁E
- "ファイル復旧" / "File Recovery"
- "...をバチE��アチE�Eから復旧しました、E / "Restored ... from backup."
- "...をデフォルト値で再生成しました、E / "Regenerated ... with default values."

### 5. チE��ト実行と動作確誁E
以下�Eコマンドを頁E��に実行してすべて成功することを確認してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```
両方とも�E功（テスト�Eパス、アプリぁEExit Code 0 で起動�E終亁E��することを確認してから完亁E��してください、E
チE��トが失敗した場合やアプリが起動しなぁE��合�E原因を修正してから再実行してください、E
```

---

## Step 7: 全体検証 + 抜け漏れ修正

```
i18n 対応�E最終検証を行ってください、E

### 1. ハ�Eドコード日本語文字�Eの残存チェチE��
`app/` 配下�E全 `.py` ファイルに対して、`t()` を通してぁE��ぁE��ードコードされた日本誁EUI 斁E���Eが残ってぁE��ぁE�� grep で確認してください、E
- 確認対象: ユーザーに見える文字�E�E�EI ラベル、E��知チE��スト、�Eロンプト、�E力テキスト！E
- 除外対象: ログメチE��ージ�E�Elogger.xxx("...")`�E�、docstring、コメント、変数吁E
- 残ってぁE��日本誁EUI 斁E���Eがあれ�E `t()` に置き換え、`app/i18n.py` に日英を追加してください

### 2. 翻訳カバレチE��の確誁E
`app/i18n.py` の `_STRINGS` を確認して、以下をチェチE��してください:
- `"ja"` にあるキーぁE`"en"` にもすべて存在すること�E�抜けがなぁE��と�E�E
- `"en"` にあるキーぁE`"ja"` にもすべて存在すること
- 抜けがあれ�E追加してください

### 3. 起動時の言語�E期化確誁E
`app/main.py` のアプリ起動フロー冁E��、`config.yaml` から `language` を読み込んだ後に `i18n.set_language(config.language)` を呼んでぁE��ことを確認してください。呼んでぁE��ければ追加してください、E

### 4. 英語モードでのチE��チE
`config.yaml` の `language` を一時的に `en` に変更してからチE��トを実行してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```

### 5. 日本語モードに戻してチE��チE
`config.yaml` の `language` めE`ja` に戻してから同じチE��トを実行してください:
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 15
```
```
cd "c:\path\to\ghcpsdknotify"
$env:PYTHONUTF8="1"; uv run python -m app.main 2>&1
```

すべてのチE��トがパスし、アプリが正常に起動�E終亁E��Exit Code 0�E�することを確認してから完亁E��してください、E
問題があれば修正して再実行してください、E
```

---

## チェチE��リスト（�EスチE��プ完亁E���E確認用�E�E

| # | 確認頁E�� | 状慁E|
|---|---------|------|
| 1 | `app/i18n.py` が作�Eされ、`t()`, `set_language()`, `get_language()` が動作すめE| ⬁E|
| 2 | `config.yaml` に `language` キーが存在する | ⬁E|
| 3 | `AppConfig` に `language` フィールドがある | ⬁E|
| 4 | 設定画面に言語�E替ドロチE�EダウンがあめE| ⬁E|
| 5 | `settings_ui.py` の全 UI 斁E���EぁE`t()` 経由 | ⬁E|
| 6 | `setup_wizard.py` の全 UI 斁E���EぁE`t()` 経由 | ⬁E|
| 7 | `notifier.py` の全 UI 斁E���EぁE`t()` 経由 | ⬁E|
| 8 | AI プロンプト�E�EチE��プレート）が言語�E替対忁E| ⬁E|
| 9 | スコアリングプロンプトが言語�E替対忁E| ⬁E|
| 10 | `viewer.py` の全 UI 斁E���EぁE`t()` 経由 | ⬁E|
| 11 | `output_writer.py` の出力文字�EぁE`t()` 経由 | ⬁E|
| 12 | トレイメニュー頁E��ぁE`t()` 経由 | ⬁E|
| 13 | `spaced_repetition.py` の UI 斁E���EぁE`t()` 経由 | ⬁E|
| 14 | `utils.py` の通知斁E���EぁE`t()` 経由 | ⬁E|
| 15 | 全チE��トがパス�E�Ea モード！E| ⬁E|
| 16 | 全チE��トがパス�E�En モード！E| ⬁E|
| 17 | アプリが正常起動！Ea モード！E| ⬁E|
| 18 | アプリが正常起動！En モード！E| ⬁E|
