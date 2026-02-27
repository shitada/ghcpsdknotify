"""GitHub Copilot SDK 呼び出しの集約ラッパーモジュール。

他モジュールは copilot-sdk を直接 import しない。
すべての SDK 呼び出しをこのクラスに集約する。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from copilot import CopilotClient

from app.config import CopilotSdkConfig, WorkIQMcpConfig
from app.i18n import get_language

logger = logging.getLogger(__name__)

# リトライ設定
_MAX_RETRIES = 3
_RETRY_DELAYS = [5, 15, 45]  # 指数バックオフ（秒）


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
        """非同期コンテキストマネージャのエントリ。CopilotClient を起動する。"""
        self._client = CopilotClient()
        await self._client.start()
        logger.info("CopilotClient を起動しました")
        return self

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
    ) -> Any:
        """リトライ付きで非同期コルーチンを実行する。

        指数バックオフ（5s→15s→45s、最大3回）でリトライする。

        Args:
            coro_factory: リトライごとに呼ばれるコルーチンファクトリ（引数なし）。
            timeout: タイムアウト（秒）。
            operation_name: ログ用の操作名。

        Returns:
            コルーチンの戻り値。

        Raises:
            Exception: 全リトライ失敗時。
        """
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
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
                    _MAX_RETRIES,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "%s: エラー (試行 %d/%d) — %s",
                    operation_name,
                    attempt + 1,
                    _MAX_RETRIES,
                    e,
                )

            # 最終試行以外はバックオフ待機
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.info("%s: %d秒後にリトライします", operation_name, delay)
                await asyncio.sleep(delay)

        logger.error("%s: 全 %d 回のリトライに失敗しました", operation_name, _MAX_RETRIES)
        raise last_error  # type: ignore[misc]

    async def _send_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float,
        mcp_servers: dict[str, Any] | None = None,
        operation_name: str = "ブリーフィング生成",
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

            # セッション作成・メッセージ送信
            session = await client.create_session(session_config)  # type: ignore[arg-type]
            try:
                response = await session.send_and_wait(
                    {"prompt": user_prompt},
                    timeout=timeout,
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

        # WorkIQ MCP 付きで試行
        mcp_servers: dict[str, Any] = {
            "workiq": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@microsoft/workiq", "mcp"],
                "tools": ["*"],
            },
        }
        logger.info("WorkIQ MCP を登録 (stdio)")

        try:
            return await self._send_prompt(
                system_prompt,
                user_prompt,
                timeout=self._sdk_config.sdk_timeout,
                mcp_servers=mcp_servers,
                operation_name="機能A ブリーフィング生成 (WorkIQ付き)",
            )
        except (TimeoutError, Exception) as e:
            logger.warning(
                "WorkIQ MCP 付きの生成に失敗しました (%s)。"
                "WorkIQ MCP なしでフォールバックします",
                e,
            )

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
