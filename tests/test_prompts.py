"""prompts モジュールのユニットテスト。"""

from unittest.mock import patch

from app.config import AppConfig, WorkIQMcpConfig
from app.prompts import (
    build_file_contents,
    build_file_list_with_metadata,
    get_discovery_appendix,
    get_scoring_prompt_template,
    get_system_prompt_a,
    get_system_prompt_b,
    get_system_prompt_c,
    get_system_prompt_d,
    get_user_prompt_a,
    get_user_prompt_b,
    get_user_prompt_d,
    load_prompt,
)


# ────────────────────────────────────────────
# load_prompt
# ────────────────────────────────────────────


class TestLoadPrompt:
    def test_loads_japanese_prompt(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = load_prompt("feature_a", "system")
            assert "パーソナル AI デイリーブリーフィング" in text

    def test_loads_english_prompt(self):
        with patch("app.prompts.get_language", return_value="en"):
            text = load_prompt("feature_a", "system")
            assert "Personal AI Daily Briefing" in text

    def test_fallback_to_japanese(self):
        with patch("app.prompts.get_language", return_value="fr"):
            text = load_prompt("feature_a", "system")
            assert "パーソナル AI デイリーブリーフィング" in text

    def test_loads_scoring_prompt(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = load_prompt("scoring", "scoring")
            assert "採点" in text

    def test_loads_feature_c_prompt(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = load_prompt("feature_c", "system")
            assert "モニター" in text

    def test_loads_feature_d_prompt_ja(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = load_prompt("feature_d", "system")
            assert "ミーティング" in text

    def test_loads_feature_d_prompt_en(self):
        with patch("app.prompts.get_language", return_value="en"):
            text = load_prompt("feature_d", "system")
            assert "Meeting" in text

    def test_get_system_prompt_d(self):
        with patch("app.prompts.get_language", return_value="ja"):
            assert "ミーティング" in get_system_prompt_d()

    def test_get_user_prompt_d_has_placeholders(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = get_user_prompt_d()
            assert "{target_date}" in text
            assert "{target_weekday}" in text
            assert "{current_datetime}" in text


# ────────────────────────────────────────────
# get_system_prompt_a (WorkIQ 分岐)
# ────────────────────────────────────────────


class TestGetSystemPromptA:
    def test_with_workiq_enabled(self):
        config = AppConfig(workiq_mcp=WorkIQMcpConfig(enabled=True))
        with patch("app.prompts.get_language", return_value="ja"):
            prompt = get_system_prompt_a(config)
            assert "WorkIQ" in prompt

    def test_without_workiq(self):
        config = AppConfig(workiq_mcp=WorkIQMcpConfig(enabled=False))
        with patch("app.prompts.get_language", return_value="ja"):
            prompt = get_system_prompt_a(config)
            assert "WorkIQ MCP を使うべき" not in prompt

    def test_contains_template_resolved(self):
        config = AppConfig(workiq_mcp=WorkIQMcpConfig(enabled=False))
        with patch("app.prompts.get_language", return_value="ja"):
            prompt = get_system_prompt_a(config)
            # テンプレート変数 {workiq_tool_rules} が解決されていること
            assert "{workiq_tool_rules}" not in prompt


# ────────────────────────────────────────────
# get_system_prompt_b (奇数/偶数パターン)
# ────────────────────────────────────────────


class TestGetSystemPromptB:
    def test_odd_run_learning_pattern(self):
        with patch("app.prompts.get_language", return_value="ja"):
            prompt = get_system_prompt_b(run_count=1)
            assert "📘" in prompt or "学習中" in prompt

    def test_even_run_review_pattern(self):
        with patch("app.prompts.get_language", return_value="ja"):
            prompt = get_system_prompt_b(run_count=2)
            assert "📗" in prompt or "振り返り" in prompt

    def test_english_odd_run(self):
        with patch("app.prompts.get_language", return_value="en"):
            prompt = get_system_prompt_b(run_count=3)
            assert "Active Learning" in prompt

    def test_english_even_run(self):
        with patch("app.prompts.get_language", return_value="en"):
            prompt = get_system_prompt_b(run_count=4)
            assert "Review" in prompt

    def test_template_resolved(self):
        with patch("app.prompts.get_language", return_value="ja"):
            prompt = get_system_prompt_b(run_count=1)
            assert "{quiz_pattern}" not in prompt
            assert "{quiz_pattern_instruction}" not in prompt


# ────────────────────────────────────────────
# get_system_prompt_c / get_user_prompt / discovery
# ────────────────────────────────────────────


class TestOtherPrompts:
    def test_system_prompt_c_ja(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = get_system_prompt_c()
            assert "モニター" in text

    def test_system_prompt_c_en(self):
        with patch("app.prompts.get_language", return_value="en"):
            text = get_system_prompt_c()
            assert "Monitor" in text

    def test_user_prompt_a_has_placeholders(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = get_user_prompt_a()
            assert "{current_datetime}" in text
            assert "{file_contents}" in text

    def test_user_prompt_b_has_placeholders(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = get_user_prompt_b()
            assert "{quiz_schedule_info}" in text

    def test_discovery_appendix_ja(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = get_discovery_appendix()
            assert "ディスカバリー" in text

    def test_scoring_prompt_has_placeholders(self):
        with patch("app.prompts.get_language", return_value="ja"):
            text = get_scoring_prompt_template()
            assert "{source_content}" in text
            assert "{q1_question_text}" in text
