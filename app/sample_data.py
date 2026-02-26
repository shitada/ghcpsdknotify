"""サンプルデータ生成モジュール。

ユーザーがコンテキスト用 .md ファイルを持っていない場合に、
技術学習メモ・読書ノート・TIL 等のサンプル Markdown を自動生成する。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
#  サンプルコンテンツ定義 (ja / en)
# ──────────────────────────────────────────────────────────────────────

_SAMPLES: list[dict[str, str | dict[str, str]]] = [
    # ── 1. 技術学習メモ: Python 基礎 ──
    {
        "filename": "python-basics.md",
        "ja": """\
# Python 基礎まとめ

学習日: 2025-05-10

## 基本データ型

- `int` — 整数型。任意精度。
- `float` — 浮動小数点数。IEEE 754 倍精度。
- `str` — 文字列。イミュータブル。
- `bool` — `True` / `False`。`int` のサブクラス。
- `None` — null に相当する唯一のオブジェクト。

## リスト内包表記

```python
squares = [x ** 2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
pairs = [(x, y) for x in range(3) for y in range(3)]
```

### 辞書内包表記

```python
word_lengths = {w: len(w) for w in ["hello", "world", "python"]}
```

## デコレータ

デコレータは関数を引数に取り、新しい関数を返す高階関数。

```python
import functools

def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import time
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

@timer
def slow_function():
    import time
    time.sleep(1)
```

## コンテキストマネージャ

```python
with open("data.txt", "r", encoding="utf-8") as f:
    content = f.read()
```

カスタムコンテキストマネージャ:

```python
from contextlib import contextmanager

@contextmanager
def managed_resource():
    print("Acquiring resource")
    yield "resource"
    print("Releasing resource")
```

## 型ヒント (Type Hints)

Python 3.5+ で導入。3.10+ では `X | Y` 構文が使える。

```python
def greet(name: str, times: int = 1) -> list[str]:
    return [f"Hello, {name}!"] * times
```

## ポイント

- Python はインデントでブロックを表す
- すべてがオブジェクト（関数もクラスも）
- GIL（Global Interpreter Lock）により CPU バウンドは `multiprocessing` 推奨
- `pip` / `uv` でパッケージ管理
""",
        "en": """\
# Python Basics Summary

Study date: 2025-05-10

## Basic Data Types

- `int` — Integer type. Arbitrary precision.
- `float` — Floating point. IEEE 754 double precision.
- `str` — String. Immutable.
- `bool` — `True` / `False`. Subclass of `int`.
- `None` — The sole null-like object.

## List Comprehensions

```python
squares = [x ** 2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
pairs = [(x, y) for x in range(3) for y in range(3)]
```

### Dictionary Comprehensions

```python
word_lengths = {w: len(w) for w in ["hello", "world", "python"]}
```

## Decorators

A decorator is a higher-order function that takes a function and returns a new one.

```python
import functools

def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import time
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

@timer
def slow_function():
    import time
    time.sleep(1)
```

## Context Managers

```python
with open("data.txt", "r", encoding="utf-8") as f:
    content = f.read()
```

Custom context manager:

```python
from contextlib import contextmanager

@contextmanager
def managed_resource():
    print("Acquiring resource")
    yield "resource"
    print("Releasing resource")
```

## Type Hints

Introduced in Python 3.5+. `X | Y` syntax available from 3.10+.

```python
def greet(name: str, times: int = 1) -> list[str]:
    return [f"Hello, {name}!"] * times
```

## Key Points

- Python uses indentation for blocks
- Everything is an object (functions, classes, etc.)
- GIL (Global Interpreter Lock) — use `multiprocessing` for CPU-bound tasks
- Package management via `pip` / `uv`
""",
    },
    # ── 2. 技術学習メモ: Git ワークフロー ──
    {
        "filename": "git-workflow.md",
        "ja": """\
# Git ワークフローまとめ

学習日: 2025-05-15

## ブランチ戦略

### GitHub Flow

1. `main` から feature ブランチを作成
2. 変更をコミット・プッシュ
3. Pull Request を作成
4. レビュー・CI パス後にマージ

### Git Flow

- `main` — 本番リリース用
- `develop` — 開発統合ブランチ
- `feature/*` — 機能開発
- `release/*` — リリース準備
- `hotfix/*` — 緊急修正

## よく使うコマンド

```bash
# ブランチ作成 & 切り替え
git switch -c feature/new-feature

# 変更のステージング
git add -p  # 対話的に選択

# rebase（履歴を整理）
git rebase -i HEAD~3

# cherry-pick（特定コミットだけ取り込む）
git cherry-pick abc1234

# stash（一時退避）
git stash push -m "WIP: login feature"
git stash pop
```

## コミットメッセージ規約 (Conventional Commits)

```
feat: ユーザー認証機能を追加
fix: ログイン時のNullPointerExceptionを修正
docs: README にセットアップ手順を追加
refactor: 認証ロジックをサービス層に分離
test: ユーザーAPI のユニットテストを追加
chore: CI パイプラインを更新
```

## マージ vs リベース

| 項目 | マージ | リベース |
|------|--------|---------|
| 履歴 | マージコミットが残る | 直線的な履歴 |
| 安全性 | 安全（共有ブランチ向き） | 強制プッシュが必要な場合あり |
| 適用場面 | main への統合 | feature ブランチの更新 |

## .gitignore のベストプラクティス

- OS 固有ファイル（`.DS_Store`, `Thumbs.db`）
- IDE 設定（`.vscode/`, `.idea/`）
- ビルド成果物（`dist/`, `build/`, `__pycache__/`）
- 環境変数ファイル（`.env`）
""",
        "en": """\
# Git Workflow Summary

Study date: 2025-05-15

## Branching Strategies

### GitHub Flow

1. Create a feature branch from `main`
2. Commit and push changes
3. Open a Pull Request
4. Merge after review and CI passes

### Git Flow

- `main` — Production releases
- `develop` — Integration branch
- `feature/*` — Feature development
- `release/*` — Release preparation
- `hotfix/*` — Emergency fixes

## Common Commands

```bash
# Create & switch branch
git switch -c feature/new-feature

# Interactive staging
git add -p

# Interactive rebase (clean up history)
git rebase -i HEAD~3

# Cherry-pick (apply specific commit)
git cherry-pick abc1234

# Stash (save work temporarily)
git stash push -m "WIP: login feature"
git stash pop
```

## Commit Message Convention (Conventional Commits)

```
feat: add user authentication
fix: resolve NullPointerException on login
docs: add setup instructions to README
refactor: extract auth logic to service layer
test: add unit tests for user API
chore: update CI pipeline
```

## Merge vs Rebase

| Aspect | Merge | Rebase |
|--------|-------|--------|
| History | Merge commit preserved | Linear history |
| Safety | Safe for shared branches | May require force push |
| Use case | Integrating into main | Updating feature branches |

## .gitignore Best Practices

- OS-specific files (`.DS_Store`, `Thumbs.db`)
- IDE settings (`.vscode/`, `.idea/`)
- Build artifacts (`dist/`, `build/`, `__pycache__/`)
- Environment files (`.env`)
""",
    },
    # ── 3. 技術学習メモ: Docker 入門 ──
    {
        "filename": "docker-intro.md",
        "ja": """\
# Docker 入門メモ

学習日: 2025-05-20

## Docker の基本概念

- **イメージ**: アプリケーションの実行に必要なファイルをパッケージ化した読み取り専用テンプレート
- **コンテナ**: イメージから起動する実行インスタンス
- **レジストリ**: イメージの保管場所（Docker Hub, GitHub Container Registry 等）
- **ボリューム**: データの永続化に使うストレージ

## Dockerfile の書き方

```dockerfile
# ベースイメージ
FROM python:3.12-slim

# 作業ディレクトリ
WORKDIR /app

# 依存関係を先にインストール（キャッシュ活用）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ポート公開
EXPOSE 8000

# 実行コマンド
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## よく使うコマンド

```bash
# イメージのビルド
docker build -t myapp:latest .

# コンテナの起動
docker run -d -p 8000:8000 --name myapp myapp:latest

# 実行中コンテナの確認
docker ps

# ログの確認
docker logs -f myapp

# コンテナに入る
docker exec -it myapp /bin/bash

# クリーンアップ
docker system prune -a
```

## Docker Compose

```yaml
version: "3.9"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    depends_on:
      - db
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=pass

volumes:
  pgdata:
```

## マルチステージビルド

ビルドツールを最終イメージに含めずサイズを削減:

```dockerfile
FROM node:20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

## ネットワーク

- `bridge` — デフォルト。同一ホスト上のコンテナ間通信
- `host` — ホストのネットワークスタックを直接使用
- `none` — ネットワーク無効
""",
        "en": """\
# Docker Introduction Notes

Study date: 2025-05-20

## Core Concepts

- **Image**: A read-only template packaging everything needed to run an app
- **Container**: A running instance created from an image
- **Registry**: Image storage (Docker Hub, GitHub Container Registry, etc.)
- **Volume**: Persistent storage for data

## Writing a Dockerfile

```dockerfile
# Base image
FROM python:3.12-slim

# Working directory
WORKDIR /app

# Install dependencies first (leverage caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Common Commands

```bash
# Build image
docker build -t myapp:latest .

# Run container
docker run -d -p 8000:8000 --name myapp myapp:latest

# List running containers
docker ps

# Follow logs
docker logs -f myapp

# Shell into container
docker exec -it myapp /bin/bash

# Cleanup
docker system prune -a
```

## Docker Compose

```yaml
version: "3.9"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    depends_on:
      - db
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=pass

volumes:
  pgdata:
```

## Multi-stage Builds

Keep build tools out of the final image to reduce size:

```dockerfile
FROM node:20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

## Networking

- `bridge` — Default. Communication between containers on the same host
- `host` — Uses the host's network stack directly
- `none` — Networking disabled
""",
    },
    # ── 4. 読書ノート: Clean Code ──
    {
        "filename": "book-clean-code.md",
        "ja": """\
# 読書ノート: Clean Code（Robert C. Martin）

読了日: 2025-04-20

## 概要

ソフトウェアの品質を高めるための実践的なガイドライン集。
「動くコード」ではなく「読みやすいコード」を書くことの重要性を説く。

## 第1章: きれいなコードとは

- きれいなコードは **他の開発者が読んで理解できる** コード
- 「ボーイスカウトの規則」— コードを見つけた時よりもきれいにして去る
- 悪いコードは技術的負債として蓄積する

## 第2章: 意味のある名前

- 意図が伝わる名前をつける: `d` → `elapsedTimeInDays`
- 検索しやすい名前にする: マジックナンバーは定数化
- クラス名は名詞、メソッド名は動詞

### 悪い例 vs 良い例

```python
# Bad
def calc(l):
    t = 0
    for i in l:
        t += i.p * i.q
    return t

# Good
def calculate_total_price(order_items):
    total = 0
    for item in order_items:
        total += item.price * item.quantity
    return total
```

## 第3章: 関数

- 関数は **小さく** すべき（20行以下が理想）
- 引数は少なく（0〜2個が理想、3個以上はオブジェクトにまとめる）
- 1つの関数は1つのことだけを行う
- 副作用を避ける

## 第7章: エラー処理

- 戻り値でエラーを示すのではなく例外を使う
- `try-except` ブロックは独立した関数に抽出する
- `None` を返さない、引数に渡さない

## 第9章: ユニットテスト

- テストコードも本番コードと同じ品質基準を適用する
- F.I.R.S.T. 原則:
  - **Fast**: 高速に実行できる
  - **Independent**: テスト間に依存関係がない
  - **Repeatable**: どの環境でも同じ結果
  - **Self-Validating**: Pass/Fail が明確
  - **Timely**: 本番コードの直前に書く

## 感想

- 命名規則の章が最も実践的ですぐに活かせる
- 「関数は小さく」は理想だが、実務ではバランスが必要
- テスト駆動開発 (TDD) の章をもっと深掘りしたい
""",
        "en": """\
# Book Notes: Clean Code (Robert C. Martin)

Finished: 2025-04-20

## Overview

A practical guide to improving software quality.
Emphasizes writing **readable code** over merely working code.

## Chapter 1: What is Clean Code?

- Clean code is code that **other developers can read and understand**
- "Boy Scout Rule" — Leave code cleaner than you found it
- Bad code accumulates as technical debt

## Chapter 2: Meaningful Names

- Use intention-revealing names: `d` → `elapsedTimeInDays`
- Use searchable names: replace magic numbers with constants
- Class names = nouns, method names = verbs

### Bad vs Good Example

```python
# Bad
def calc(l):
    t = 0
    for i in l:
        t += i.p * i.q
    return t

# Good
def calculate_total_price(order_items):
    total = 0
    for item in order_items:
        total += item.price * item.quantity
    return total
```

## Chapter 3: Functions

- Functions should be **small** (ideally under 20 lines)
- Minimize arguments (0–2 ideal; 3+ should be wrapped in an object)
- Each function should do one thing only
- Avoid side effects

## Chapter 7: Error Handling

- Use exceptions rather than error return codes
- Extract `try-except` blocks into separate functions
- Don't return `None`; don't pass `None`

## Chapter 9: Unit Tests

- Apply the same quality standards to test code as production code
- F.I.R.S.T. principles:
  - **Fast**: Run quickly
  - **Independent**: No dependencies between tests
  - **Repeatable**: Same result in any environment
  - **Self-Validating**: Clear pass/fail
  - **Timely**: Written just before production code

## Impressions

- The naming chapter is the most immediately practical
- "Keep functions small" is ideal but requires balance in practice
- Want to explore the TDD chapter in more depth
""",
    },
    # ── 5. 読書ノート: チームマネジメント ──
    {
        "filename": "book-team-management.md",
        "ja": """\
# 読書ノート: エンジニアリングマネージャーのしごと

読了日: 2025-04-28

## 概要

エンジニアリングマネージャーの役割と実践スキルを体系的に解説した一冊。
技術力だけでなく、人・プロセス・文化の管理について学べる。

## 第1部: マネージャーの基本

### 1on1 ミーティング

- 週1回30分が基本
- アジェンダは部下が主導する
- 話すべきトピック:
  - 進捗の確認ではなく **キャリア・成長** の話
  - ブロッカーや困りごと
  - チームの雰囲気・人間関係

### フィードバックの SBI モデル

- **Situation（状況）**: いつ、どこで
- **Behavior（行動）**: 何をしたか（事実ベース）
- **Impact（影響）**: どんな影響があったか

例: 「昨日のスプリントレビューで（S）、デモを丁寧に説明してくれて（B）、ステークホルダーの理解が深まった（I）」

## 第2部: チーム運営

### 委譲のレベル

1. **Tell** — 指示を出す
2. **Sell** — 理由を説明して指示
3. **Consult** — 意見を聞いてから決定
4. **Agree** — 合議で決定
5. **Advise** — アドバイスのみ
6. **Inquire** — 結果を聞く
7. **Delegate** — 完全に委譲

### 心理的安全性

- 失敗を責めない文化を作る
- 「わからない」と言える環境
- ポストモーテムは blame-free で実施

## 第3部: 組織とプロセス

### アジャイル開発のポイント

- スプリントの長さは2週間が多い
- レトロスペクティブで継続的改善
- ベロシティは予測ツールであり評価ツールではない

### 採用面接

- 構造化面接で公平性を担保
- 技術力 + 文化フィット + 成長ポテンシャルを見る
- 面接後すぐにフィードバックを記録

## 感想

- 1on1 の進め方が最も参考になった
- 委譲レベルの概念は意識的に使い分けたい
- 日本の組織文化との違いも考慮が必要
""",
        "en": """\
# Book Notes: The Manager's Path

Finished: 2025-04-28

## Overview

A systematic guide to the role and practical skills of an engineering manager.
Covers managing people, processes, and culture beyond just technical ability.

## Part 1: Manager Basics

### 1-on-1 Meetings

- Weekly, 30 minutes as a baseline
- The report drives the agenda
- Topics to discuss:
  - **Career and growth** — not just status updates
  - Blockers and concerns
  - Team dynamics and relationships

### SBI Feedback Model

- **Situation**: When and where
- **Behavior**: What was done (fact-based)
- **Impact**: What effect it had

Example: "In yesterday's sprint review (S), you explained the demo thoroughly (B), which helped stakeholders understand the feature much better (I)."

## Part 2: Team Operations

### Delegation Levels

1. **Tell** — Give instructions
2. **Sell** — Explain reasons, then instruct
3. **Consult** — Gather input before deciding
4. **Agree** — Decide together
5. **Advise** — Only provide advice
6. **Inquire** — Ask about the outcome
7. **Delegate** — Fully hand off

### Psychological Safety

- Build a culture that doesn't blame failures
- Create an environment where "I don't know" is acceptable
- Run blameless postmortems

## Part 3: Organization & Process

### Agile Key Points

- Sprint length: commonly 2 weeks
- Retrospectives for continuous improvement
- Velocity is a forecasting tool, not an evaluation metric

### Hiring Interviews

- Use structured interviews for fairness
- Evaluate: technical skill + culture fit + growth potential
- Record feedback immediately after interviews

## Impressions

- The 1-on-1 section was the most immediately useful
- Delegation levels should be consciously applied
- Cultural differences in organizations should be considered
""",
    },
    # ── 6. TIL: 2025年6月 ──
    {
        "filename": "til-2025-06.md",
        "ja": """\
# TIL — 2025年6月

## 2025-06-02: Python の `match` 文

Python 3.10 で導入された構造的パターンマッチング。

```python
match command:
    case "quit":
        exit()
    case "hello" | "hi":
        print("Hello!")
    case str(s) if s.startswith("/"):
        handle_command(s)
    case _:
        print("Unknown command")
```

`case` でガード条件 (`if ...`) も使える。

## 2025-06-05: CSS の `container` クエリ

`@media` はビューポート基準だが、`@container` は親要素基準でスタイル変更できる。

```css
.card-container {
    container-type: inline-size;
}
@container (min-width: 400px) {
    .card { display: flex; }
}
```

## 2025-06-10: `jq` でJSON操作

```bash
# 特定フィールドを抽出
cat data.json | jq '.users[] | {name, email}'

# 条件フィルタ
cat data.json | jq '.items[] | select(.price > 100)'

# 長さを取得
cat data.json | jq '.items | length'
```

## 2025-06-15: HTTP キャッシュヘッダ

- `Cache-Control: max-age=3600` — 1時間キャッシュ
- `ETag` — コンテンツのハッシュ値で変更検知
- `304 Not Modified` — キャッシュが有効な場合に返す
- `Vary: Accept-Encoding` — 圧縮方式ごとにキャッシュを分離

## 2025-06-20: PostgreSQL の EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'test@example.com';
```

- `Seq Scan` — 全件スキャン（遅い）
- `Index Scan` — インデックス使用（速い）
- `actual time` — 実際の処理時間（ミリ秒）

インデックスがない場合は `CREATE INDEX idx_users_email ON users(email);` で改善。

## 2025-06-25: GitHub Actions の `matrix` 戦略

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
    python-version: ["3.11", "3.12"]
```

組み合わせごとにジョブが並列実行される。`exclude` / `include` で調整可能。
""",
        "en": """\
# TIL — June 2025

## 2025-06-02: Python `match` Statement

Structural pattern matching introduced in Python 3.10.

```python
match command:
    case "quit":
        exit()
    case "hello" | "hi":
        print("Hello!")
    case str(s) if s.startswith("/"):
        handle_command(s)
    case _:
        print("Unknown command")
```

Guard conditions (`if ...`) can be used within `case` clauses.

## 2025-06-05: CSS Container Queries

`@media` is viewport-based; `@container` styles based on the parent element.

```css
.card-container {
    container-type: inline-size;
}
@container (min-width: 400px) {
    .card { display: flex; }
}
```

## 2025-06-10: JSON Manipulation with `jq`

```bash
# Extract specific fields
cat data.json | jq '.users[] | {name, email}'

# Filter by condition
cat data.json | jq '.items[] | select(.price > 100)'

# Get length
cat data.json | jq '.items | length'
```

## 2025-06-15: HTTP Caching Headers

- `Cache-Control: max-age=3600` — Cache for 1 hour
- `ETag` — Content hash for change detection
- `304 Not Modified` — Returned when cache is still valid
- `Vary: Accept-Encoding` — Separate cache per encoding

## 2025-06-20: PostgreSQL EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'test@example.com';
```

- `Seq Scan` — Full table scan (slow)
- `Index Scan` — Uses index (fast)
- `actual time` — Real processing time (ms)

If no index exists: `CREATE INDEX idx_users_email ON users(email);`

## 2025-06-25: GitHub Actions `matrix` Strategy

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
    python-version: ["3.11", "3.12"]
```

Jobs run in parallel for each combination. Fine-tune with `exclude` / `include`.
""",
    },
    # ── 7. TIL: 2025年7月 ──
    {
        "filename": "til-2025-07.md",
        "ja": """\
# TIL — 2025年7月

## 2025-07-01: `asyncio.TaskGroup` (Python 3.11+)

複数の非同期タスクを構造化して管理できる。

```python
import asyncio

async def fetch(url: str) -> str:
    await asyncio.sleep(1)
    return f"Result from {url}"

async def main():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(fetch("https://api.example.com/a"))
        task2 = tg.create_task(fetch("https://api.example.com/b"))
    # TaskGroup を抜けると全タスク完了が保証される
    print(task1.result(), task2.result())
```

1つでもタスクが例外を投げると、他のタスクもキャンセルされる。

## 2025-07-05: SSH ポートフォワーディング

```bash
# ローカルフォワード（リモートの DB にローカルから接続）
ssh -L 5432:db.internal:5432 bastion-host

# リモートフォワード（ローカルサーバーを外部公開）
ssh -R 8080:localhost:3000 remote-host
```

## 2025-07-10: TypeScript の `satisfies` 演算子

型の推論を保持しつつ、型制約を検証できる。

```typescript
type Colors = Record<string, [number, number, number] | string>;

const palette = {
    red: [255, 0, 0],
    green: "#00ff00",
} satisfies Colors;

// palette.red は [number, number, number] 型として推論される
palette.red.map(x => x / 255);
```

## 2025-07-15: Linux の `systemd` タイマー

cron の代替として `systemd` タイマーを使う方法。

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Daily backup timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now backup.timer
systemctl list-timers
```

## 2025-07-20: Rust の所有権モデル

- 各値には **所有者** が1つだけ存在する
- 所有者がスコープを抜けると値は自動的に解放される
- 参照は不変参照 (`&T`) か可変参照 (`&mut T`) のどちらか
- 可変参照は同時に1つだけ

```rust
fn main() {
    let s1 = String::from("hello");
    let s2 = s1; // s1 の所有権が s2 に移動（move）
    // println!("{}", s1); // コンパイルエラー！
    println!("{}", s2);
}
```

## 2025-07-28: WebSocket vs Server-Sent Events (SSE)

| 特性 | WebSocket | SSE |
|------|-----------|-----|
| 通信方向 | 双方向 | サーバー→クライアントのみ |
| プロトコル | ws:// / wss:// | HTTP |
| 再接続 | 手動実装 | 自動 |
| バイナリ | 対応 | テキストのみ |
| ユースケース | チャット、ゲーム | 通知、ライブフィード |
""",
        "en": """\
# TIL — July 2025

## 2025-07-01: `asyncio.TaskGroup` (Python 3.11+)

Manage multiple async tasks in a structured way.

```python
import asyncio

async def fetch(url: str) -> str:
    await asyncio.sleep(1)
    return f"Result from {url}"

async def main():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(fetch("https://api.example.com/a"))
        task2 = tg.create_task(fetch("https://api.example.com/b"))
    # All tasks are guaranteed complete when exiting the group
    print(task1.result(), task2.result())
```

If any task raises an exception, all other tasks are cancelled.

## 2025-07-05: SSH Port Forwarding

```bash
# Local forward (access remote DB from local)
ssh -L 5432:db.internal:5432 bastion-host

# Remote forward (expose local server externally)
ssh -R 8080:localhost:3000 remote-host
```

## 2025-07-10: TypeScript `satisfies` Operator

Validates type constraints while preserving type inference.

```typescript
type Colors = Record<string, [number, number, number] | string>;

const palette = {
    red: [255, 0, 0],
    green: "#00ff00",
} satisfies Colors;

// palette.red is inferred as [number, number, number]
palette.red.map(x => x / 255);
```

## 2025-07-15: Linux `systemd` Timers

Using `systemd` timers as an alternative to cron.

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Daily backup timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now backup.timer
systemctl list-timers
```

## 2025-07-20: Rust Ownership Model

- Each value has exactly one **owner**
- When the owner goes out of scope, the value is dropped
- References are either immutable (`&T`) or mutable (`&mut T`)
- Only one mutable reference at a time

```rust
fn main() {
    let s1 = String::from("hello");
    let s2 = s1; // ownership moves from s1 to s2
    // println!("{}", s1); // compile error!
    println!("{}", s2);
}
```

## 2025-07-28: WebSocket vs Server-Sent Events (SSE)

| Feature | WebSocket | SSE |
|---------|-----------|-----|
| Direction | Bidirectional | Server → Client only |
| Protocol | ws:// / wss:// | HTTP |
| Reconnection | Manual | Automatic |
| Binary | Supported | Text only |
| Use case | Chat, games | Notifications, live feeds |
""",
    },
    # ── 8. 技術調査レポート: CI/CD ツール比較 ──
    {
        "filename": "comparison-ci-cd-tools.md",
        "ja": """\
# CI/CD ツール比較レポート

作成日: 2025-06-01
更新日: 2025-06-15

## 目的

チームの CI/CD パイプラインを刷新するにあたり、主要ツールを比較検討する。

## 比較対象

1. **GitHub Actions**
2. **Azure Pipelines**
3. **GitLab CI/CD**

## 比較表

| 項目 | GitHub Actions | Azure Pipelines | GitLab CI/CD |
|------|---------------|-----------------|-------------|
| 設定ファイル | `.github/workflows/*.yml` | `azure-pipelines.yml` | `.gitlab-ci.yml` |
| 無料枠 | 2,000分/月 (public無制限) | 1,800分/月 | 400分/月 |
| セルフホストランナー | ✅ 対応 | ✅ 対応 | ✅ 対応 |
| マトリクスビルド | ✅ `strategy.matrix` | ✅ `strategy.matrix` | ✅ `parallel:matrix` |
| キャッシュ | ✅ `actions/cache` | ✅ 組み込み | ✅ 組み込み |
| シークレット管理 | Repository/Org secrets | Variable groups | CI/CD Variables |
| コンテナサポート | ✅ `container:` | ✅ Container jobs | ✅ `image:` |
| 承認ゲート | Environments | Approvals & Checks | Protected environments |
| マーケットプレイス | 豊富 (20,000+) | 中程度 | 少なめ |

## Pros / Cons

### GitHub Actions

**Pros:**
- GitHub との統合が最もシームレス
- マーケットプレイスが充実
- YAML がシンプルで学習コストが低い
- Dependabot / CodeQL との連携

**Cons:**
- 複雑なパイプラインの表現に限界がある
- ログの UI がやや見づらい
- Organization 横断の共有がやや面倒

### Azure Pipelines

**Pros:**
- 大規模エンタープライズ向け機能が豊富
- テンプレート機能が強力
- Azure DevOps の他サービス（Boards 等）と統合
- YAML / Classic の両方に対応

**Cons:**
- YAML の構文がやや複雑
- 初期セットアップの手間が大きい
- GitHub との連携は設定が必要

### GitLab CI/CD

**Pros:**
- ソースコード管理と CI/CD が一体化
- Auto DevOps で設定なしの CI/CD が可能
- セキュリティスキャンが組み込み

**Cons:**
- 無料枠が少ない
- マーケットプレイスが小規模
- パフォーマンスがやや劣る場合がある

## 結論

チームの状況を考慮すると **GitHub Actions** を推奨:
- 既にソースコードは GitHub で管理しておりシームレスに統合可能
- 学習コストが低くチーム全員がすぐに使い始められる
- 必要に応じてセルフホストランナーを追加して拡張可能
""",
        "en": """\
# CI/CD Tool Comparison Report

Created: 2025-06-01
Updated: 2025-06-15

## Purpose

Evaluate major CI/CD tools for modernizing our team's pipeline.

## Tools Compared

1. **GitHub Actions**
2. **Azure Pipelines**
3. **GitLab CI/CD**

## Comparison Table

| Feature | GitHub Actions | Azure Pipelines | GitLab CI/CD |
|---------|---------------|-----------------|-------------|
| Config file | `.github/workflows/*.yml` | `azure-pipelines.yml` | `.gitlab-ci.yml` |
| Free tier | 2,000 min/mo (public unlimited) | 1,800 min/mo | 400 min/mo |
| Self-hosted runner | ✅ Supported | ✅ Supported | ✅ Supported |
| Matrix builds | ✅ `strategy.matrix` | ✅ `strategy.matrix` | ✅ `parallel:matrix` |
| Caching | ✅ `actions/cache` | ✅ Built-in | ✅ Built-in |
| Secret management | Repository/Org secrets | Variable groups | CI/CD Variables |
| Container support | ✅ `container:` | ✅ Container jobs | ✅ `image:` |
| Approval gates | Environments | Approvals & Checks | Protected environments |
| Marketplace | Extensive (20,000+) | Moderate | Limited |

## Pros / Cons

### GitHub Actions

**Pros:**
- Most seamless integration with GitHub
- Rich marketplace of actions
- Simple YAML with low learning curve
- Dependabot / CodeQL integration

**Cons:**
- Limited expressiveness for complex pipelines
- Log UI could be improved
- Cross-organization sharing is somewhat cumbersome

### Azure Pipelines

**Pros:**
- Rich enterprise-scale features
- Powerful templating system
- Integration with Azure DevOps (Boards, etc.)
- Both YAML and Classic UI supported

**Cons:**
- YAML syntax can be complex
- Higher initial setup effort
- GitHub integration requires extra configuration

### GitLab CI/CD

**Pros:**
- Source management and CI/CD in one platform
- Auto DevOps for zero-config CI/CD
- Built-in security scanning

**Cons:**
- Smaller free tier
- Smaller marketplace
- Performance may lag in some cases

## Conclusion

Given our team's situation, **GitHub Actions** is recommended:
- Source code is already on GitHub — seamless integration
- Low learning curve — everyone can start immediately
- Self-hosted runners available for scaling as needed
""",
    },
    # ── 9. 業務手順書: デプロイ手順 ──
    {
        "filename": "runbook-deployment.md",
        "ja": """\
# デプロイ手順書 (Runbook)

最終更新: 2025-06-10
対象: 本番環境 (production)
担当: SRE チーム

## 前提条件

- [ ] `main` ブランチが最新であること
- [ ] CI が全てグリーンであること
- [ ] 変更内容のレビューが完了していること
- [ ] 影響範囲の確認が済んでいること

## デプロイ手順

### Step 1: メンテナンスモードの有効化

```bash
# ステータスページを更新
./scripts/set-maintenance.sh on

# ロードバランサーのヘルスチェックを確認
curl -s https://api.example.com/health | jq .
```

### Step 2: データベースマイグレーション

```bash
# マイグレーション内容の確認（ドライラン）
python manage.py migrate --plan

# マイグレーション実行
python manage.py migrate

# 結果確認
python manage.py showmigrations | grep "\\[X\\]" | tail -5
```

⚠️ **破壊的変更がある場合は DBA に事前確認すること**

### Step 3: アプリケーションのデプロイ

```bash
# 新バージョンのイメージをプル
docker pull ghcr.io/myorg/myapp:v2.3.0

# ローリングアップデート
kubectl set image deployment/myapp myapp=ghcr.io/myorg/myapp:v2.3.0

# デプロイ状況の監視
kubectl rollout status deployment/myapp --timeout=5m
```

### Step 4: 動作確認

- [ ] ヘルスチェックエンドポイントが正常レスポンスを返す
- [ ] 主要 API の応答時間が基準値以内（p99 < 500ms）
- [ ] エラーレートが閾値以下（< 0.1%）
- [ ] ログに致命的なエラーが出ていないこと

```bash
# ヘルスチェック
curl -s https://api.example.com/health

# エラーログの確認
kubectl logs -l app=myapp --since=5m | grep -i error | head -20
```

### Step 5: メンテナンスモードの解除

```bash
./scripts/set-maintenance.sh off
```

## ロールバック手順

問題が発生した場合:

```bash
# 前のバージョンに戻す
kubectl rollout undo deployment/myapp

# ロールバック確認
kubectl rollout status deployment/myapp
```

## 連絡先

- **SRE リーダー**: sre-lead@example.com
- **Slack チャンネル**: #deploy-notifications
- **PagerDuty**: Production Escalation Policy
""",
        "en": """\
# Deployment Runbook

Last updated: 2025-06-10
Target: Production environment
Owner: SRE Team

## Prerequisites

- [ ] `main` branch is up-to-date
- [ ] All CI checks are green
- [ ] Code review is complete
- [ ] Impact scope has been assessed

## Deployment Steps

### Step 1: Enable Maintenance Mode

```bash
# Update status page
./scripts/set-maintenance.sh on

# Verify load balancer health check
curl -s https://api.example.com/health | jq .
```

### Step 2: Database Migration

```bash
# Preview migrations (dry run)
python manage.py migrate --plan

# Run migrations
python manage.py migrate

# Verify results
python manage.py showmigrations | grep "\\[X\\]" | tail -5
```

⚠️ **For destructive changes, consult the DBA beforehand**

### Step 3: Deploy Application

```bash
# Pull new version image
docker pull ghcr.io/myorg/myapp:v2.3.0

# Rolling update
kubectl set image deployment/myapp myapp=ghcr.io/myorg/myapp:v2.3.0

# Monitor deployment
kubectl rollout status deployment/myapp --timeout=5m
```

### Step 4: Verification

- [ ] Health check endpoint returns OK
- [ ] Key API response times within bounds (p99 < 500ms)
- [ ] Error rate below threshold (< 0.1%)
- [ ] No critical errors in logs

```bash
# Health check
curl -s https://api.example.com/health

# Check error logs
kubectl logs -l app=myapp --since=5m | grep -i error | head -20
```

### Step 5: Disable Maintenance Mode

```bash
./scripts/set-maintenance.sh off
```

## Rollback Procedure

If issues are detected:

```bash
# Revert to previous version
kubectl rollout undo deployment/myapp

# Verify rollback
kubectl rollout status deployment/myapp
```

## Contacts

- **SRE Lead**: sre-lead@example.com
- **Slack channel**: #deploy-notifications
- **PagerDuty**: Production Escalation Policy
""",
    },
    # ── 10. 振り返り: 2025年 Q2 ──
    {
        "filename": "retrospective-2025-q2.md",
        "ja": """\
# 振り返り: 2025年 Q2（4月〜6月）

作成日: 2025-07-01

## 四半期の目標と達成状況

| 目標 | 達成度 | メモ |
|------|--------|------|
| API レスポンス改善 (p99 < 300ms) | ✅ 達成 | キャッシュ導入で p99 = 180ms に改善 |
| テストカバレッジ 80% 以上 | ⚠️ 75% | インテグレーションテストが不足 |
| チーム新メンバーのオンボーディング | ✅ 達成 | 2名が独力でタスクをこなせるレベルに |
| ドキュメント整備 | ❌ 未達 | API ドキュメントの更新が半分残り |

## KPT (Keep / Problem / Try)

### Keep（続けること）

- **デイリースタンドアップ**: 毎朝15分の同期で情報共有がスムーズ
- **ペアプログラミング**: 複雑な機能の品質が向上した
- **コードレビュー 24h ルール**: レビュー待ちのブロッキングが大幅に減少
- **週次でのメトリクス共有**: パフォーマンス意識がチーム全体で向上

### Problem（課題）

- **リリース後の不具合が3件発生**: テスト不足が原因
  - 原因1: エッジケースのテストが書かれていなかった
  - 原因2: ステージング環境と本番環境の差異
- **ドキュメント更新が後回しになりがち**: 優先度が下がる
- **会議が多すぎる**: 週のうち約30%が会議に消費
- **技術的負債の返済が遅れている**: リファクタリングのための時間が確保できない

### Try（次に試すこと）

- **E2E テストの自動化**: Playwright でクリティカルパスをカバー
- **ドキュメント Day**: 月1回、ドキュメント更新に専念する日を設ける
- **No Meeting Day**: 水曜日を会議なしの集中作業日にする
- **Tech Debt Friday**: 毎週金曜午後は技術的負債の返済に充てる

## 個人の振り返り

### うまくいったこと

- キャッシュ戦略の設計と実装をリードできた
- 新メンバーのメンターとして成長を支援できた
- TypeScript の型安全性についてチーム内で勉強会を開催

### 改善したいこと

- 見積もりの精度（オーバーコミットしがち）
- 非同期コミュニケーションの活用（Slack で即レスしすぎない）
- アウトプット（ブログ記事やLT）の頻度を上げる

## Q3 の目標

1. テストカバレッジ 85% 達成
2. API ドキュメントを完全更新
3. モノレポへの移行検討・PoC 実施
4. チーム満足度サーベイで 4.0 / 5.0 以上
""",
        "en": """\
# Retrospective: 2025 Q2 (April–June)

Created: 2025-07-01

## Quarterly Goals & Results

| Goal | Status | Notes |
|------|--------|-------|
| API response improvement (p99 < 300ms) | ✅ Achieved | Caching brought p99 down to 180ms |
| Test coverage ≥ 80% | ⚠️ 75% | Integration tests still lacking |
| Onboarding new team members | ✅ Achieved | 2 members now working independently |
| Documentation improvements | ❌ Not achieved | API docs update is half-done |

## KPT (Keep / Problem / Try)

### Keep

- **Daily standups**: 15-minute syncs each morning keep information flowing
- **Pair programming**: Improved quality on complex features
- **24-hour code review rule**: Significantly reduced review-wait blocking
- **Weekly metrics sharing**: Raised performance awareness team-wide

### Problem

- **3 post-release bugs**: Root cause was insufficient testing
  - Cause 1: Edge cases weren't tested
  - Cause 2: Staging/production environment differences
- **Documentation updates often deprioritized**: Always loses to feature work
- **Too many meetings**: ~30% of the week spent in meetings
- **Tech debt payoff is behind schedule**: No dedicated time for refactoring

### Try

- **Automate E2E tests**: Cover critical paths with Playwright
- **Documentation Day**: Dedicate one day per month to doc updates
- **No Meeting Day**: Reserve Wednesday for focused work
- **Tech Debt Friday**: Spend Friday afternoons on tech debt

## Personal Reflection

### What Went Well

- Led the design and implementation of the caching strategy
- Mentored new team members effectively
- Ran an internal study session on TypeScript type safety

### Areas for Improvement

- Estimation accuracy (tendency to overcommit)
- Better use of async communication (avoid instant Slack replies)
- Increase output frequency (blog posts, lightning talks)

## Q3 Goals

1. Reach 85% test coverage
2. Complete API documentation update
3. Evaluate and PoC monorepo migration
4. Team satisfaction survey ≥ 4.0 / 5.0
""",
    },
]


def generate_sample_data(target_dir: Path, language: str) -> list[Path]:
    """指定フォルダにサンプル Markdown ファイルを生成する。

    Args:
        target_dir: サンプルを書き出すディレクトリ。存在しなければ作成する。
        language: ``"ja"`` or ``"en"``。未対応値は ``"ja"`` にフォールバック。

    Returns:
        生成（書き込み）したファイルの Path リスト。
        既にファイルが存在していた場合はスキップし、リストには含まない。
    """
    if language not in ("ja", "en"):
        logger.warning(
            "Unsupported language '%s', falling back to 'ja'", language,
        )
        language = "ja"

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for sample in _SAMPLES:
        filename = sample["filename"]
        assert isinstance(filename, str)
        filepath = target_dir / filename

        if filepath.exists():
            logger.info("サンプルファイルをスキップ（既に存在）: %s", filepath)
            continue

        content = sample[language]
        assert isinstance(content, str)
        filepath.write_text(content, encoding="utf-8")
        logger.info("サンプルファイルを作成しました: %s", filepath)
        created.append(filepath)

    logger.info(
        "サンプルデータ生成完了: %d / %d ファイル作成",
        len(created),
        len(_SAMPLES),
    )
    return created
