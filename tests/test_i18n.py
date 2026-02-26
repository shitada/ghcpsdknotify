"""i18n モジュールのテスト。"""

from __future__ import annotations

import pytest

from app.i18n import SUPPORTED_LANGUAGES, get_language, set_language, t


@pytest.fixture(autouse=True)
def _reset_language():
    """各テストの前後で言語設定をデフォルト（ja）にリセットする。"""
    set_language("ja")
    yield
    set_language("ja")


class TestGetSetLanguage:
    """言語の取得・設定テスト。"""

    def test_default_language_is_ja(self):
        assert get_language() == "ja"

    def test_set_language_to_en(self):
        set_language("en")
        assert get_language() == "en"

    def test_set_language_to_ja(self):
        set_language("en")
        set_language("ja")
        assert get_language() == "ja"

    def test_unsupported_language_falls_back_to_ja(self):
        set_language("fr")
        assert get_language() == "ja"


class TestTranslation:
    """翻訳取得テスト。"""

    def test_t_returns_japanese_by_default(self):
        assert t("app.name") == "パーソナル AI デイリーブリーフィング Agent"

    def test_t_returns_english_after_switch(self):
        set_language("en")
        assert t("app.name") == "Personal AI Daily Briefing Agent"

    def test_t_common_save_ja(self):
        assert t("common.save") == "保存"

    def test_t_common_save_en(self):
        set_language("en")
        assert t("common.save") == "Save"

    def test_t_missing_key_returns_key_itself(self):
        result = t("nonexistent.key.that.does.not.exist")
        assert result == "nonexistent.key.that.does.not.exist"

    def test_t_kwargs_formatting(self):
        # _STRINGS に直接テスト用キーはないので、存在しないキーで
        # フォーマットが試行されることを確認（キー自体が返る）
        result = t("nonexistent.{name}", name="test")
        # キーがそのまま返りフォーマットされる
        assert result == "nonexistent.test"

    def test_t_fallback_to_ja_when_en_key_missing(self):
        """英語カタログにないキーは日本語にフォールバックする。"""
        # 一時的に日本語のみのキーを追加してテスト
        from app import i18n

        i18n._STRINGS["ja"]["_test_only"] = "テスト値"
        set_language("en")
        assert t("_test_only") == "テスト値"
        # クリーンアップ
        del i18n._STRINGS["ja"]["_test_only"]


class TestSupportedLanguages:
    """サポート言語定数のテスト。"""

    def test_supported_languages_contains_ja(self):
        assert "ja" in SUPPORTED_LANGUAGES
        assert SUPPORTED_LANGUAGES["ja"] == "日本語"

    def test_supported_languages_contains_en(self):
        assert "en" in SUPPORTED_LANGUAGES
        assert SUPPORTED_LANGUAGES["en"] == "English"
