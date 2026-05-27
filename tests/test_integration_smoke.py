"""統合スモークテスト — 全機能モジュールの接続整合性を検証する。

新しい機能を追加したときに、インポート・メソッド・設定が
正しく接続されているかを自動検出する。
"""

import importlib


class TestFeatureModuleImports:
    """各機能モジュールが正常にインポートできることを検証する。"""

    def test_feature_a_imports(self):
        mod = importlib.import_module("app.feature_a")
        assert hasattr(mod, "run"), "feature_a.run が未定義"

    def test_feature_b_imports(self):
        mod = importlib.import_module("app.feature_b")
        assert hasattr(mod, "run"), "feature_b.run が未定義"

    def test_feature_c_imports(self):
        mod = importlib.import_module("app.feature_c")
        assert hasattr(mod, "run"), "feature_c.run が未定義"

    def test_prompts_module_imports(self):
        mod = importlib.import_module("app.prompts")
        assert hasattr(mod, "get_system_prompt_a")
        assert hasattr(mod, "get_system_prompt_b")
        assert hasattr(mod, "get_system_prompt_c")

    def test_main_module_imports(self):
        mod = importlib.import_module("app.main")
        assert hasattr(mod, "main"), "app.main.main が未定義"


class TestCopilotClientMethods:
    """CopilotClientWrapper に全機能の generate メソッドがあることを検証する。"""

    def test_has_generate_briefing_a(self):
        from app.copilot_client import CopilotClientWrapper
        assert hasattr(CopilotClientWrapper, "generate_briefing_a")

    def test_has_generate_briefing_b(self):
        from app.copilot_client import CopilotClientWrapper
        assert hasattr(CopilotClientWrapper, "generate_briefing_b")

    def test_has_generate_briefing_c(self):
        from app.copilot_client import CopilotClientWrapper
        assert hasattr(CopilotClientWrapper, "generate_briefing_c")

    def test_has_score_quiz(self):
        from app.copilot_client import CopilotClientWrapper
        assert hasattr(CopilotClientWrapper, "score_quiz")


class TestFeatureRunSignatures:
    """各機能 run() の引数シグネチャが統一されていることを検証する。"""

    def test_feature_a_run_accepts_required_args(self):
        import inspect
        from app.feature_a import run
        sig = inspect.signature(run)
        params = list(sig.parameters.keys())
        assert "config" in params
        assert "state_manager" in params

    def test_feature_b_run_accepts_required_args(self):
        import inspect
        from app.feature_b import run
        sig = inspect.signature(run)
        params = list(sig.parameters.keys())
        assert "config" in params
        assert "state_manager" in params

    def test_feature_c_run_accepts_required_args(self):
        import inspect
        from app.feature_c import run
        sig = inspect.signature(run)
        params = list(sig.parameters.keys())
        assert "config" in params
        assert "state_manager" in params


class TestScheduleConfigIntegrity:
    """スケジュール設定に全機能のエントリがあることを検証する。"""

    def test_schedule_config_has_feature_c(self):
        from app.config import ScheduleConfig
        sc = ScheduleConfig()
        assert hasattr(sc, "feature_a")
        assert hasattr(sc, "feature_b")
        assert hasattr(sc, "feature_c")

    def test_config_roundtrip_preserves_feature_c(self):
        from app.config import AppConfig, _app_config_to_dict, _dict_to_app_config
        config = AppConfig()
        d = _app_config_to_dict(config)
        assert "feature_c" in d.get("schedule", {})
        restored = _dict_to_app_config(d)
        assert len(restored.schedule.feature_c) > 0


class TestI18nKeysExist:
    """設定UI・トレイで使用する i18n キーが定義されていることを検証する。"""

    def test_tray_keys_exist(self):
        from app.i18n import get_language, set_language, t
        original_lang = get_language()
        try:
            for lang in ("ja", "en"):
                set_language(lang)
                for key in (
                    "tray.run_a_only",
                    "tray.run_b_only",
                    "tray.run_c_only",
                    "tray.run_all",
                    "tray.feature_a",
                    "tray.feature_b",
                    "tray.feature_c",
                ):
                    result = t(key)
                    assert result != key, f"i18n key '{key}' missing for lang={lang}"
        finally:
            set_language(original_lang)

    def test_settings_keys_exist(self):
        from app.i18n import get_language, set_language, t
        original_lang = get_language()
        try:
            for lang in ("ja", "en"):
                set_language(lang)
                for key in (
                    "settings.feature_a_header",
                    "settings.feature_b_header",
                    "settings.feature_c_header",
                    "settings.feature_a_schedule",
                    "settings.feature_b_schedule",
                    "settings.feature_c_schedule",
                    "settings.tab.page_monitor",
                    "settings.page_monitor_header",
                    "settings.page_url_label",
                    "settings.page_add",
                    "settings.page_remove",
                ):
                    result = t(key)
                    assert result != key, f"i18n key '{key}' missing for lang={lang}"
        finally:
            set_language(original_lang)


class TestDependenciesInstalled:
    """機能 C で必要な外部パッケージがインストールされていることを検証する。"""

    def test_beautifulsoup4_installed(self):
        from bs4 import BeautifulSoup  # noqa: F401

    def test_httpx_installed(self):
        import httpx  # noqa: F401
