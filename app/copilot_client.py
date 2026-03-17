"""GitHub Copilot SDK 呼び出しの集約ラッパーモジュール。

他モジュールは copilot-sdk を直接 import しない。
すべての SDK 呼び出しをこのクラスに集約する。
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import shutil
import subprocess
import time
from typing import Any

from copilot import CopilotClient

from app.config import CopilotSdkConfig, WorkIQMcpConfig
from app.i18n import get_language

logger = logging.getLogger(__name__)

# リトライ設定
_MAX_RETRIES = 3
_RETRY_DELAYS = [5, 15, 45]  # 指数バックオフ（秒）

# CopilotClient.start() リトライ設定
_START_MAX_RETRIES = 3
_START_RETRY_DELAY = 5  # 秒


def _diagnose_workiq_failure() -> None:
    """WorkIQ MCP 失敗時の診断情報をログに記録する。"""
    npx_cmd = "npx.cmd" if platform.system() == "Windows" else "npx"

    # 1. npx コマンドの存在確認
    npx_path = shutil.which(npx_cmd)
    if npx_path:
        logger.info("[WorkIQ診断] npx パス: %s", npx_path)
    else:
        logger.warning("[WorkIQ診断] npx がPATHに見つかりません")
        return

    # 2. npx --version で動作確認
    try:
        proc = subprocess.run(
            [npx_cmd, "--version"],
            capture_output=True, text=True, timeout=15,
        )
        logger.info(
            "[WorkIQ診断] npx --version: %s (exit=%d)",
            proc.stdout.strip(), proc.returncode,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[WorkIQ診断] npx --version がタイムアウト (15秒)")
    except Exception as e:
        logger.warning("[WorkIQ診断] npx --version 実行エラー: %s", e)

    # 3. ネットワーク接続テスト（GitHub API）
    try:
        import urllib.request
        start = time.monotonic()
        req = urllib.request.Request(
            "https://api.github.com/zen",
            headers={"User-Agent": "ghcpsdknotify-diag"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = time.monotonic() - start
            logger.info(
                "[WorkIQ診断] GitHub API 接続OK (%d, %.1f秒)",
                resp.status, elapsed,
            )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning(
            "[WorkIQ診断] GitHub API 接続失敗 (%.1f秒): %s",
            elapsed, e,
        )


class CopilotClientWrapper:
    """Copilot SDK 呼び出しを集約するラッパークラス。

    全 SDK 操作を非同期メソッドとして提供する。
    APScheduler の同期ジョブからは asyncio.run() で呼び出すこと。
    """

    def __init__(self, sdk_config: CopilotSdkConfig) -> None:
        """CopilotClientWrapper を初期化する。

        Args:
            sdk_config: Copilot SDK の設定。
        """
        self._sdk_config = sdk_config
        self._client: CopilotClient | None = None

    async def __aenter__(self) -> CopilotClientWrapper:
        """非同期コンテキストマネージャのエントリ。CopilotClient を起動する。

        start() が失敗した場合、最大3回リトライする（5秒間隔）。
        """
        last_error: Exception | None = None
        for attempt in range(_START_MAX_RETRIES):
            self._client = CopilotClient()
            try:
                await self._client.start()
                logger.info("CopilotClient を起動しました")
                return self
            except Exception as e:
                last_error = e
                logger.warning(
                    "CopilotClient 起動失敗 (試行 %d/%d): %s",
                    attempt + 1, _START_MAX_RETRIES, e,
                )
                # 失敗したクライアントを停止
                try:
                    await self._client.stop()
                except Exception:
                    pass
                self._client = None
                if attempt < _START_MAX_RETRIES - 1:
                    await asyncio.sleep(_START_RETRY_DELAY)

        raise last_error  # type: ignore[misc]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """非同期コンテキストマネージャのイグジット。CopilotClient を停止する。"""
        if self._client:
            await self._client.stop()
            self._client = None
            logger.info("CopilotClient を停止しました")
        return False

    def _ensure_client(self) -> CopilotClient:
        """クライアントが起動済みであることを確認する。"""
        if self._client is None:
            raise RuntimeError(
                "CopilotClient が起動されていません。"
                "async with CopilotClientWrapper(...) as client: の形式で使用してください。"
            )
        return self._client

    async def _call_with_retry(
        self,
        coro_factory: Any,
        *,
        timeout: float,
        operation_name: str = "SDK呼び出し",
        max_retries: int = _MAX_RETRIES,
    ) -> Any:
        """リトライ付きで非同期コルーチンを実行する。

        指数バックオフでリトライする。

        Args:
            coro_factory: リトライごとに呼ばれるコルーチンファクトリ（引数なし）。
            timeout: タイムアウト（秒）。
            operation_name: ログ用の操作名。
            max_retries: 最大リトライ回数（デフォルト: 3）。

        Returns:
            コルーチンの戻り値。

        Raises:
            Exception: 全リトライ失敗時。
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    coro_factory(),
                    timeout=timeout,
                )
                if attempt > 0:
                    logger.info(
                        "%s: リトライ %d 回目で成功", operation_name, attempt + 1
                    )
                return result
            except asyncio.TimeoutError:
                last_error = TimeoutError(
                    f"{operation_name}: タイムアウト ({timeout}秒)"
                )
                logger.warning(
                    "%s: タイムアウト (試行 %d/%d)",
                    operation_name,
                    attempt + 1,
                    max_retries,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "%s: エラー (試行 %d/%d) — %s",
                    operation_name,
                    attempt + 1,
                    max_retries,
                    e,
                )

            # 最終試行以外はバックオフ待機
            if attempt < max_retries - 1:
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                logger.info("%s: %d秒後にリトライします", operation_name, delay)
                await asyncio.sleep(delay)

        logger.error("%s: 全 %d 回のリトライに失敗しました", operation_name, max_retries)
        raise last_error  # type: ignore[misc]

    async def _send_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float,
        mcp_servers: dict[str, Any] | None = None,
        operation_name: str = "ブリーフィング生成",
        max_retries: int = _MAX_RETRIES,
    ) -> str:
        """プロンプトを送信してレスポンスのテキストを返す。

        Args:
            system_prompt: システムプロンプト。
            user_prompt: ユーザープロンプト。
            timeout: タイムアウト（秒）。
            mcp_servers: MCP サーバー設定。None の場合は使用しない。
            operation_name: ログ用の操作名。

        Returns:
            アシスタントのレスポンステキスト。
        """
        client = self._ensure_client()

        async def _execute() -> str:
            # セッション設定の構築
            session_config: dict[str, Any] = {
                "model": self._sdk_config.model,
                "system_message": {
                    "mode": self._sdk_config.system_message_mode,
                    "content": system_prompt,
                },
                "reasoning_effort": self._sdk_config.reasoning_effort,
                "streaming": False,
                "infinite_sessions": {"enabled": False},
            }

            # MCP サーバー設定の追加
            if mcp_servers:
                session_config["mcp_servers"] = mcp_servers

            # セッション作成・メッセージ送信（フェーズ別タイミング記録）
            t0 = time.monotonic()
            session = await client.create_session(session_config)  # type: ignore[arg-type]
            t1 = time.monotonic()
            logger.info(
                "%s: create_session 完了 (%.1f秒, MCP=%s)",
                operation_name, t1 - t0, "あり" if mcp_servers else "なし",
            )
            try:
                response = await session.send_and_wait(
                    {"prompt": user_prompt},
                    timeout=timeout,
                )
                t2 = time.monotonic()
                logger.info(
                    "%s: send_and_wait 完了 (%.1f秒)",
                    operation_name, t2 - t1,
                )

                if response and hasattr(response, "data") and hasattr(response.data, "content"):
                    return str(response.data.content)

                logger.warning("%s: レスポンスが空です", operation_name)
                return ""
            finally:
                await session.destroy()

        return await self._call_with_retry(
            _execute,
            timeout=timeout + 30,  # リトライ用にタイムアウトにマージンを追加
            operation_name=operation_name,
            max_retries=max_retries,
        )

    async def generate_briefing_a(
        self,
        system_prompt: str,
        user_prompt: str,
        workiq_config: WorkIQMcpConfig,
    ) -> str:
        """機能 A（最新情報の取得）のブリーフィングを生成する。

        Web 検索は SDK 組み込み機能に委譲する。
        WorkIQ MCP が有効の場合は stdio MCP サーバーとして登録する。
        WorkIQ MCP 付きでタイムアウトした場合は、MCP なしで自動フォールバックする。

        Args:
            system_prompt: 機能 A 用のシステムプロンプト。
            user_prompt: 機能 A 用のユーザープロンプト。
            workiq_config: WorkIQ MCP サーバー設定。

        Returns:
            生成されたブリーフィングテキスト。
        """
        if not workiq_config.enabled:
            logger.info("WorkIQ MCP は未設定。Web 検索のみで動作します")
            return await self._send_prompt(
                system_prompt,
                user_prompt,
                timeout=self._sdk_config.sdk_timeout,
                operation_name="機能A ブリーフィング生成",
            )

        # WorkIQ MCP 付きで試行（専用の短いタイムアウト・少ないリトライ回数）
        # Windows では npx.cmd を指定しないとサブプロセスが解決できない
        npx_cmd = "npx.cmd" if platform.system() == "Windows" else "npx"
        mcp_servers: dict[str, Any] = {
            "workiq": {
                "type": "stdio",
                "command": npx_cmd,
                "args": ["-y", "@microsoft/workiq", "mcp"],
                "tools": ["*"],
            },
        }
        workiq_timeout = workiq_config.timeout
        workiq_max_retries = workiq_config.max_retries
        logger.info(
            "WorkIQ MCP を登録 (stdio) — timeout=%ds, max_retries=%d",
            workiq_timeout,
            workiq_max_retries,
        )

        try:
            return await self._send_prompt(
                system_prompt,
                user_prompt,
                timeout=workiq_timeout,
                mcp_servers=mcp_servers,
                operation_name="機能A ブリーフィング生成 (WorkIQ付き)",
                max_retries=workiq_max_retries,
            )
        except (TimeoutError, Exception) as e:
            logger.warning(
                "WorkIQ MCP 付きの生成に失敗しました (%s)。"
                "WorkIQ MCP なしでフォールバックします",
                e,
            )
            # 診断情報を収集
            try:
                _diagnose_workiq_failure()
            except Exception as diag_err:
                logger.debug("WorkIQ 診断でエラー: %s", diag_err)

        # フォールバック: WorkIQ MCP なしで再試行
        return await self._send_prompt(
            system_prompt,
            user_prompt,
            timeout=self._sdk_config.sdk_timeout,
            operation_name="機能A ブリーフィング生成 (フォールバック)",
        )

    async def generate_briefing_b(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """機能 B（復習・クイズ）のブリーフィングを生成する。

        ツール登録なし（ローカルファイルのみで完結するため）。

        Args:
            system_prompt: 機能 B 用のシステムプロンプト。
            user_prompt: 機能 B 用のユーザープロンプト。

        Returns:
            生成されたブリーフィングテキスト。
        """
        return await self._send_prompt(
            system_prompt,
            user_prompt,
            timeout=self._sdk_config.sdk_timeout,
            operation_name="機能B ブリーフィング生成",
        )

    async def score_quiz(self, scoring_prompt: str) -> dict[str, Any]:
        """クイズを採点する。

        採点プロンプトを送信し、JSON レスポンスをパースして返す。

        Args:
            scoring_prompt: 採点用プロンプト（仕様書 3.11 のテンプレートに変数埋め込み済み）。

        Returns:
            採点結果の辞書。キー:
            - q1_correct (bool)
            - q1_correct_answer (str)
            - q1_explanation (str)
            - q2_evaluation (str): "good" | "partial" | "poor"
            - q2_feedback (str)

        Raises:
            ValueError: JSON パースに失敗した場合。
        """
        if get_language() == "en":
            system_prompt = (
                "You are a quiz scoring system. "
                "Output only JSON in the specified format. "
                "Do not output any extra text."
            )
        else:
            system_prompt = (
                "あなたはクイズ採点システムです。"
                "指定された形式の JSON のみを出力してください。"
                "余計なテキストは一切出力しないでください。"
            )

        raw_response = await self._send_prompt(
            system_prompt,
            scoring_prompt,
            timeout=self._sdk_config.sdk_timeout,
            operation_name="クイズ採点",
        )

        # JSON パース（レスポンスに余計なテキストが含まれる可能性を考慮）
        try:
            # まず全体をパースしてみる
            return json.loads(raw_response)
        except json.JSONDecodeError:
            pass

        # JSON ブロックを抽出（```json ... ``` 形式）
        import re
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # { から } までの最大範囲を抽出
        brace_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.error("採点レスポンスの JSON パースに失敗: %s", raw_response[:200])
        raise ValueError(f"採点レスポンスの JSON パースに失敗しました: {raw_response[:200]}")

    async def check_license(self) -> bool:
        """Copilot ライセンスの接続テストを行う。

        get_auth_status() で認証・ライセンス状態を確認する。

        Returns:
            接続成功時は True、失敗時は False。
        """
        client = self._ensure_client()

        try:
            status = await client.get_auth_status()
            if status and status.login:
                logger.info(
                    "Copilot ライセンス確認: OK (user=%s)", status.login
                )
                return True

            msg = getattr(status, "statusMessage", None) or "ステータス不明"
            logger.warning("Copilot ライセンス確認: NG (%s)", msg)
            return False

        except Exception as e:
            logger.warning("Copilot ライセンス確認に失敗: %s", e)
            return False
