"""copilot_client モジュールのユニットテスト。

CopilotClient (SDK) はモックし、ラッパーのロジックをテストする。
"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.config import CopilotSdkConfig, WorkIQMcpConfig
from app.copilot_client import CopilotClientWrapper


# ────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────

@pytest.fixture
def sdk_config() -> CopilotSdkConfig:
    return CopilotSdkConfig(sdk_timeout=10)


@pytest_asyncio.fixture
async def wrapper(sdk_config: CopilotSdkConfig):
    """モック化した CopilotClient を内部にもつ wrapper。"""
    w = CopilotClientWrapper(sdk_config)
    mock_client = AsyncMock()
    mock_client.start = AsyncMock()
    mock_client.stop = AsyncMock()
    w._client = mock_client
    yield w


# ────────────────────────────────────────────
# __aenter__ / __aexit__
# ────────────────────────────────────────────

class TestContextManager:
    async def test_enter_exit(self, sdk_config: CopilotSdkConfig):
        with patch("app.copilot_client.CopilotClient") as MockCls:
            mock_instance = AsyncMock()
            MockCls.return_value = mock_instance
            async with CopilotClientWrapper(sdk_config) as w:
                assert w._client is mock_instance
                mock_instance.start.assert_awaited_once()
            mock_instance.stop.assert_awaited_once()

    async def test_start_retries_on_failure(self, sdk_config: CopilotSdkConfig):
        """start() が失敗しても最大3回リトライして成功する。"""
        call_count = 0

        async def start_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("ping timeout")

        with patch("app.copilot_client.CopilotClient") as MockCls:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock(side_effect=start_side_effect)
            MockCls.return_value = mock_instance
            async with CopilotClientWrapper(sdk_config) as w:
                assert w._client is mock_instance
            assert call_count == 3

    async def test_start_raises_after_max_retries(self, sdk_config: CopilotSdkConfig):
        """start() が全リトライ失敗した場合、例外が発生する。"""
        with patch("app.copilot_client.CopilotClient") as MockCls:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock(side_effect=TimeoutError("ping timeout"))
            MockCls.return_value = mock_instance
            with pytest.raises(TimeoutError, match="ping timeout"):
                async with CopilotClientWrapper(sdk_config):
                    pass
            assert mock_instance.start.await_count == 3


# ────────────────────────────────────────────
# _ensure_client
# ────────────────────────────────────────────

class TestEnsureClient:
    def test_raises_when_not_started(self, sdk_config: CopilotSdkConfig):
        w = CopilotClientWrapper(sdk_config)
        with pytest.raises(RuntimeError, match="起動されていません"):
            w._ensure_client()


# ────────────────────────────────────────────
# _call_with_retry
# ────────────────────────────────────────────

class TestCallWithRetry:
    async def test_success_first_try(self, wrapper: CopilotClientWrapper):
        factory = AsyncMock(return_value="ok")
        result = await wrapper._call_with_retry(factory, timeout=5, operation_name="test")
        assert result == "ok"
        assert factory.call_count == 1

    async def test_retries_on_failure(self, wrapper: CopilotClientWrapper):
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("fail")
            return "recovered"

        result = await wrapper._call_with_retry(factory, timeout=5, operation_name="test")
        assert result == "recovered"
        assert call_count == 3

    async def test_raises_after_max_retries(self, wrapper: CopilotClientWrapper):
        factory = AsyncMock(side_effect=RuntimeError("always fail"))
        with pytest.raises(RuntimeError, match="always fail"):
            await wrapper._call_with_retry(factory, timeout=5, operation_name="test")
        assert factory.call_count == 3

    async def test_custom_max_retries_1(self, wrapper: CopilotClientWrapper):
        """max_retries=1 の場合、リトライせず即座に失敗する。"""
        factory = AsyncMock(side_effect=RuntimeError("fail once"))
        with pytest.raises(RuntimeError, match="fail once"):
            await wrapper._call_with_retry(
                factory, timeout=5, operation_name="test", max_retries=1
            )
        assert factory.call_count == 1

    async def test_custom_max_retries_2(self, wrapper: CopilotClientWrapper):
        """max_retries=2 の場合、最大2回試行する。"""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "recovered"

        result = await wrapper._call_with_retry(
            factory, timeout=5, operation_name="test", max_retries=2
        )
        assert result == "recovered"
        assert call_count == 2


# ────────────────────────────────────────────
# check_license
# ────────────────────────────────────────────

class TestCheckLicense:
    async def test_license_ok(self, wrapper: CopilotClientWrapper):
        mock_status = MagicMock()
        mock_status.login = "testuser"
        wrapper._client.get_auth_status = AsyncMock(return_value=mock_status)
        assert await wrapper.check_license() is True

    async def test_license_no_login(self, wrapper: CopilotClientWrapper):
        mock_status = MagicMock()
        mock_status.login = ""
        mock_status.statusMessage = "No license"
        wrapper._client.get_auth_status = AsyncMock(return_value=mock_status)
        assert await wrapper.check_license() is False

    async def test_license_exception(self, wrapper: CopilotClientWrapper):
        wrapper._client.get_auth_status = AsyncMock(side_effect=Exception("network error"))
        assert await wrapper.check_license() is False


# ────────────────────────────────────────────
# score_quiz (JSON パース)
# ────────────────────────────────────────────

class TestScoreQuiz:
    async def test_parses_plain_json(self, wrapper: CopilotClientWrapper):
        expected = {
            "q1_correct": True,
            "q1_correct_answer": "B",
            "q1_explanation": "解説",
            "q2_evaluation": "good",
            "q2_feedback": "良い回答",
        }

        # _send_prompt をモック
        wrapper._send_prompt = AsyncMock(return_value=json.dumps(expected))
        result = await wrapper.score_quiz("prompt")
        assert result == expected

    async def test_parses_json_in_code_block(self, wrapper: CopilotClientWrapper):
        raw = '```json\n{"q1_correct": false, "q1_correct_answer": "A", "q1_explanation": "x", "q2_evaluation": "poor", "q2_feedback": "y"}\n```'
        wrapper._send_prompt = AsyncMock(return_value=raw)
        result = await wrapper.score_quiz("prompt")
        assert result["q1_correct"] is False

    async def test_parses_json_with_extra_text(self, wrapper: CopilotClientWrapper):
        raw = 'Here is the result: {"q1_correct": true, "q1_correct_answer": "C", "q1_explanation": "z", "q2_evaluation": "partial", "q2_feedback": "w"} end'
        wrapper._send_prompt = AsyncMock(return_value=raw)
        result = await wrapper.score_quiz("prompt")
        assert result["q2_evaluation"] == "partial"

    async def test_raises_on_invalid_json(self, wrapper: CopilotClientWrapper):
        wrapper._send_prompt = AsyncMock(return_value="not json at all")
        with pytest.raises(ValueError, match="JSON パースに失敗"):
            await wrapper.score_quiz("prompt")


# ────────────────────────────────────────────
# _send_prompt (セッション管理)
# ────────────────────────────────────────────

class TestSendPrompt:
    async def test_session_created_and_destroyed(self, wrapper: CopilotClientWrapper):
        mock_session = AsyncMock()
        mock_response = MagicMock()
        mock_response.data.content = "response text"
        mock_session.send_and_wait = AsyncMock(return_value=mock_response)
        mock_session.destroy = AsyncMock()
        wrapper._client.create_session = AsyncMock(return_value=mock_session)

        result = await wrapper._send_prompt("sys", "user", timeout=10)
        assert result == "response text"
        mock_session.destroy.assert_awaited_once()

    async def test_session_destroyed_on_error(self, wrapper: CopilotClientWrapper):
        mock_session = AsyncMock()
        mock_session.send_and_wait = AsyncMock(side_effect=RuntimeError("fail"))
        mock_session.destroy = AsyncMock()
        wrapper._client.create_session = AsyncMock(return_value=mock_session)

        with pytest.raises(RuntimeError):
            await wrapper._send_prompt("sys", "user", timeout=10)
        mock_session.destroy.assert_awaited()


# ────────────────────────────────────────────
# generate_briefing_a (WorkIQ MCP 設定)
# ────────────────────────────────────────────

class TestGenerateBriefingA:
    async def test_workiq_disabled_skips_mcp(self, wrapper: CopilotClientWrapper):
        """WorkIQ 無効時は mcp_servers なしで _send_prompt が呼ばれる。"""
        wrapper._send_prompt = AsyncMock(return_value="briefing")
        config = WorkIQMcpConfig(enabled=False)
        result = await wrapper.generate_briefing_a("sys", "user", config)
        assert result == "briefing"
        # mcp_servers 引数がないこと（デフォルト None）
        call_kwargs = wrapper._send_prompt.call_args.kwargs
        assert call_kwargs.get("mcp_servers") is None

    async def test_workiq_enabled_uses_npx_cmd_on_windows(self, wrapper: CopilotClientWrapper):
        """Windows 環境では npx.cmd が MCP コマンドに設定される。"""
        wrapper._send_prompt = AsyncMock(return_value="briefing with workiq")
        config = WorkIQMcpConfig(enabled=True)
        with patch("app.copilot_client.platform") as mock_platform:
            mock_platform.system.return_value = "Windows"
            result = await wrapper.generate_briefing_a("sys", "user", config)
        assert result == "briefing with workiq"
        call_kwargs = wrapper._send_prompt.call_args.kwargs
        mcp = call_kwargs["mcp_servers"]
        assert mcp["workiq"]["command"] == "npx.cmd"

    async def test_workiq_enabled_uses_npx_on_non_windows(self, wrapper: CopilotClientWrapper):
        """非 Windows 環境では npx が MCP コマンドに設定される。"""
        wrapper._send_prompt = AsyncMock(return_value="briefing with workiq")
        config = WorkIQMcpConfig(enabled=True)
        with patch("app.copilot_client.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            result = await wrapper.generate_briefing_a("sys", "user", config)
        assert result == "briefing with workiq"
        call_kwargs = wrapper._send_prompt.call_args.kwargs
        mcp = call_kwargs["mcp_servers"]
        assert mcp["workiq"]["command"] == "npx"

    async def test_workiq_fallback_on_timeout(self, wrapper: CopilotClientWrapper):
        """WorkIQ 付きがタイムアウトした場合、MCP なしでフォールバックする。"""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("mcp_servers"):
                raise TimeoutError("timeout")
            return "fallback result"

        wrapper._send_prompt = AsyncMock(side_effect=side_effect)
        config = WorkIQMcpConfig(enabled=True)
        result = await wrapper.generate_briefing_a("sys", "user", config)
        assert result == "fallback result"
        assert call_count == 2

    async def test_workiq_uses_dedicated_timeout(self, wrapper: CopilotClientWrapper):
        """WorkIQ 有効時は workiq_config.timeout が使われる。"""
        wrapper._send_prompt = AsyncMock(return_value="briefing with workiq")
        config = WorkIQMcpConfig(enabled=True, timeout=45)
        with patch("app.copilot_client.platform") as mock_platform:
            mock_platform.system.return_value = "Windows"
            await wrapper.generate_briefing_a("sys", "user", config)
        # WorkIQ 付き呼び出しの timeout が 45 であること
        call_kwargs = wrapper._send_prompt.call_args.kwargs
        assert call_kwargs["timeout"] == 45

    async def test_workiq_uses_dedicated_max_retries(self, wrapper: CopilotClientWrapper):
        """WorkIQ 有効時は workiq_config.max_retries が使われる。"""
        wrapper._send_prompt = AsyncMock(return_value="briefing with workiq")
        config = WorkIQMcpConfig(enabled=True, max_retries=2)
        with patch("app.copilot_client.platform") as mock_platform:
            mock_platform.system.return_value = "Windows"
            await wrapper.generate_briefing_a("sys", "user", config)
        call_kwargs = wrapper._send_prompt.call_args.kwargs
        assert call_kwargs["max_retries"] == 2

    async def test_workiq_single_retry_fallback_fast(self, wrapper: CopilotClientWrapper):
        """max_retries=1 の場合、WorkIQ 失敗後すぐにフォールバックする。"""
        calls = []

        async def side_effect(*args, **kwargs):
            calls.append(kwargs.get("operation_name", ""))
            if kwargs.get("mcp_servers"):
                raise TimeoutError("timeout")
            return "fallback result"

        wrapper._send_prompt = AsyncMock(side_effect=side_effect)
        config = WorkIQMcpConfig(enabled=True, timeout=30, max_retries=1)
        result = await wrapper.generate_briefing_a("sys", "user", config)
        assert result == "fallback result"
        # WorkIQ 付き1回 + フォールバック1回 = 合計2回
        assert len(calls) == 2
        assert "WorkIQ" in calls[0]
        assert "フォールバック" in calls[1]
