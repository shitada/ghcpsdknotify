"""config モジュールのユニットテスト。"""

from pathlib import Path

import yaml

from app.config import (
    AppConfig,
    CopilotSdkConfig,
    ScheduleConfig,
    ScheduleEntry,
    SpacedRepetitionConfig,
    _dict_to_app_config,
    _app_config_to_dict,
    load,
    save,
    generate_default,
)


# ────────────────────────────────────────────
# dict ↔ AppConfig ラウンドトリップ
# ────────────────────────────────────────────

class TestDictRoundTrip:
    def test_default_roundtrip(self):
        config = AppConfig()
        d = _app_config_to_dict(config)
        restored = _dict_to_app_config(d)

        assert restored.output_folder_name == config.output_folder_name
        assert restored.copilot_sdk.model == config.copilot_sdk.model
        assert restored.quiz.spaced_repetition.intervals == config.quiz.spaced_repetition.intervals
        assert restored.log_level == config.log_level

    def test_custom_values_roundtrip(self):
        config = AppConfig(
            input_folders=["/a", "/b"],
            output_folder_name="output",
            copilot_sdk=CopilotSdkConfig(model="gpt-4o", sdk_timeout=60),
            log_level="DEBUG",
        )
        d = _app_config_to_dict(config)
        restored = _dict_to_app_config(d)

        assert restored.input_folders == ["/a", "/b"]
        assert restored.copilot_sdk.model == "gpt-4o"
        assert restored.copilot_sdk.sdk_timeout == 60
        assert restored.log_level == "DEBUG"

    def test_empty_dict_produces_defaults(self):
        config = _dict_to_app_config({})
        assert config.output_folder_name == "_briefings"
        assert config.copilot_sdk.model == "claude-sonnet-4.6"


# ────────────────────────────────────────────
# load / save (ファイル I/O)
# ────────────────────────────────────────────

class TestLoadSave:
    def test_save_and_load(self, tmp_path: Path):
        config = AppConfig(
            input_folders=["/test"],
            log_level="WARNING",
        )
        path = tmp_path / "config.yaml"
        save(config, path)
        loaded = load(path)

        assert loaded.input_folders == ["/test"]
        assert loaded.log_level == "WARNING"

    def test_load_nonexistent_returns_default(self, tmp_path: Path):
        path = tmp_path / "nope.yaml"
        loaded = load(path)
        assert isinstance(loaded, AppConfig)
        assert loaded.output_folder_name == "_briefings"

    def test_load_corrupt_returns_default(self, tmp_path: Path):
        path = tmp_path / "corrupt.yaml"
        path.write_text(":::invalid::: yaml {{{", encoding="utf-8")
        loaded = load(path)
        # YAML がパースできても dict でなければ ValueError
        assert isinstance(loaded, AppConfig)

    def test_load_from_bak(self, tmp_path: Path):
        path = tmp_path / "config.yaml"
        bak = tmp_path / "config.yaml.bak"
        config = AppConfig(input_folders=["/from_bak"])
        d = _app_config_to_dict(config)
        bak.write_text(
            yaml.dump(d, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        loaded = load(path)
        assert loaded.input_folders == ["/from_bak"]


# ────────────────────────────────────────────
# generate_default
# ────────────────────────────────────────────

class TestGenerateDefault:
    def test_generates_file(self, tmp_path: Path):
        path = tmp_path / "config.yaml"
        config = generate_default(path)
        assert path.exists()
        assert isinstance(config, AppConfig)
