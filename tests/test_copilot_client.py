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
