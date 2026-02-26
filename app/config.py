"""設定ファイル（config.yaml）の読み書き・デフォルト生成モジュール。

config.yaml の読み込み・書き込み・デフォルト値の生成を行う。
アトミック書き込みと .bak バックアップは utils モジュールを使用する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from app.utils import atomic_write, safe_read_with_fallback

logger = logging.getLogger(__name__)

# デフォルトの config.yaml パス（settings ディレクトリ配下）
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings" / "config.yaml"


@dataclass
class ScheduleEntry:
    """スケジュールの1エントリ（曜日+時刻）。"""

    day_of_week: str = "mon-fri"
    hour: str = "9"


@dataclass
class ScheduleConfig:
    """機能ごとのスケジュール設定。"""

    feature_a: list[ScheduleEntry] = field(default_factory=lambda: [ScheduleEntry(day_of_week="mon-fri", hour="9")])
    feature_b: list[ScheduleEntry] = field(default_factory=lambda: [ScheduleEntry(day_of_week="mon,wed,fri", hour="8")])


@dataclass
class CopilotSdkConfig:
    """GitHub Copilot SDK 設定。"""

    model: str = "claude-sonnet-4.6"
    system_message_mode: str = "replace"
    reasoning_effort: str = "medium"
    max_context_tokens: int = 100_000
    sdk_timeout: int = 120


@dataclass
class WorkIQMcpConfig:
    """WorkIQ MCP サーバー設定。"""

    enabled: bool = False
    suppress_setup_prompt: bool = False


@dataclass
class NotificationConfig:
    """通知設定。"""

    enabled: bool = True
    open_file_on_click: bool = True


@dataclass
class FileSelectionConfig:
    """ファイル選定設定。"""

    max_files: int = 20
    discovery_interval: int = 5


@dataclass
class SpacedRepetitionConfig:
    """間隔反復設定。"""

    enabled: bool = True
    max_level: int = 5
    intervals: list[int] = field(default_factory=lambda: [1, 3, 7, 14, 30, 60])


@dataclass
class QuizConfig:
    """クイズ・間隔反復設定。"""

    quiz_server_host: str = "127.0.0.1"
    quiz_server_port: int = 0
    quiz_scoring_timeout: int = 30
    spaced_repetition: SpacedRepetitionConfig = field(default_factory=SpacedRepetitionConfig)


@dataclass
class AppConfig:
    """アプリケーション全体の設定。"""

    input_folders: list[str] = field(default_factory=list)
    output_folder_name: str = "_briefings"
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    target_extensions: list[str] = field(default_factory=lambda: [".md"])
    copilot_sdk: CopilotSdkConfig = field(default_factory=CopilotSdkConfig)
    workiq_mcp: WorkIQMcpConfig = field(default_factory=WorkIQMcpConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    file_selection: FileSelectionConfig = field(default_factory=FileSelectionConfig)
    quiz: QuizConfig = field(default_factory=QuizConfig)
    language: str = "ja"
    log_level: str = "INFO"


def _dict_to_schedule_entry(d: dict[str, Any]) -> ScheduleEntry:
    """辞書から ScheduleEntry を生成する。"""
    return ScheduleEntry(
        day_of_week=str(d.get("day_of_week", "mon-fri")),
        hour=str(d.get("hour", "9")),
    )


def _dict_to_schedule_config(d: dict[str, Any]) -> ScheduleConfig:
    """辞書から ScheduleConfig を生成する。"""
    feature_a_raw = d.get("feature_a", [])
    feature_b_raw = d.get("feature_b", [])
    return ScheduleConfig(
        feature_a=[_dict_to_schedule_entry(e) for e in feature_a_raw] if feature_a_raw else [ScheduleEntry(day_of_week="mon-fri", hour="9")],
        feature_b=[_dict_to_schedule_entry(e) for e in feature_b_raw] if feature_b_raw else [ScheduleEntry(day_of_week="mon,wed,fri", hour="8")],
    )


def _dict_to_copilot_sdk_config(d: dict[str, Any]) -> CopilotSdkConfig:
    """辞書から CopilotSdkConfig を生成する。"""
    return CopilotSdkConfig(
        model=str(d.get("model", "claude-sonnet-4.6")),
        system_message_mode=str(d.get("system_message_mode", "replace")),
        reasoning_effort=str(d.get("reasoning_effort", "medium")),
        max_context_tokens=int(d.get("max_context_tokens", 100_000)),
        sdk_timeout=int(d.get("sdk_timeout", 120)),
    )


def _dict_to_workiq_mcp_config(d: dict[str, Any]) -> WorkIQMcpConfig:
    """辞書から WorkIQMcpConfig を生成する。"""
    return WorkIQMcpConfig(
        enabled=bool(d.get("enabled", False)),
        suppress_setup_prompt=bool(d.get("suppress_setup_prompt", False)),
    )


def _dict_to_notification_config(d: dict[str, Any]) -> NotificationConfig:
    """辞書から NotificationConfig を生成する。"""
    return NotificationConfig(
        enabled=bool(d.get("enabled", True)),
        open_file_on_click=bool(d.get("open_file_on_click", True)),
    )


def _dict_to_file_selection_config(d: dict[str, Any]) -> FileSelectionConfig:
    """辞書から FileSelectionConfig を生成する。"""
    return FileSelectionConfig(
        max_files=int(d.get("max_files", 20)),
        discovery_interval=int(d.get("discovery_interval", 5)),
    )


def _dict_to_spaced_repetition_config(d: dict[str, Any]) -> SpacedRepetitionConfig:
    """辞書から SpacedRepetitionConfig を生成する。"""
    return SpacedRepetitionConfig(
        enabled=bool(d.get("enabled", True)),
        max_level=int(d.get("max_level", 5)),
        intervals=list(d.get("intervals", [1, 3, 7, 14, 30, 60])),
    )


def _dict_to_quiz_config(d: dict[str, Any]) -> QuizConfig:
    """辞書から QuizConfig を生成する。"""
    sr_raw = d.get("spaced_repetition", {})
    return QuizConfig(
        quiz_server_host=str(d.get("quiz_server_host", "127.0.0.1")),
        quiz_server_port=int(d.get("quiz_server_port", 0)),
        quiz_scoring_timeout=int(d.get("quiz_scoring_timeout", 30)),
        spaced_repetition=_dict_to_spaced_repetition_config(sr_raw) if isinstance(sr_raw, dict) else SpacedRepetitionConfig(),
    )


def _dict_to_app_config(d: dict[str, Any]) -> AppConfig:
    """辞書から AppConfig を生成する。"""
    schedule_raw = d.get("schedule", {})
    copilot_raw = d.get("copilot_sdk", {})
    workiq_raw = d.get("workiq_mcp", {})
    notif_raw = d.get("notification", {})
    fs_raw = d.get("file_selection", {})
    quiz_raw = d.get("quiz", {})

    return AppConfig(
        input_folders=list(d.get("input_folders", [])),
        output_folder_name=str(d.get("output_folder_name", "_briefings")),
        schedule=_dict_to_schedule_config(schedule_raw) if isinstance(schedule_raw, dict) else ScheduleConfig(),
        target_extensions=list(d.get("target_extensions", [".md"])),
        copilot_sdk=_dict_to_copilot_sdk_config(copilot_raw) if isinstance(copilot_raw, dict) else CopilotSdkConfig(),
        workiq_mcp=_dict_to_workiq_mcp_config(workiq_raw) if isinstance(workiq_raw, dict) else WorkIQMcpConfig(),
        notification=_dict_to_notification_config(notif_raw) if isinstance(notif_raw, dict) else NotificationConfig(),
        file_selection=_dict_to_file_selection_config(fs_raw) if isinstance(fs_raw, dict) else FileSelectionConfig(),
        quiz=_dict_to_quiz_config(quiz_raw) if isinstance(quiz_raw, dict) else QuizConfig(),
        language=str(d.get("language", "ja")),
        log_level=str(d.get("log_level", "INFO")),
    )


def _app_config_to_dict(config: AppConfig) -> dict[str, Any]:
    """AppConfig を辞書に変換する（YAML 出力用）。"""
    return {
        "input_folders": config.input_folders,
        "output_folder_name": config.output_folder_name,
        "schedule": {
            "feature_a": [{"day_of_week": e.day_of_week, "hour": e.hour} for e in config.schedule.feature_a],
            "feature_b": [{"day_of_week": e.day_of_week, "hour": e.hour} for e in config.schedule.feature_b],
        },
        "target_extensions": config.target_extensions,
        "copilot_sdk": {
            "model": config.copilot_sdk.model,
            "system_message_mode": config.copilot_sdk.system_message_mode,
            "reasoning_effort": config.copilot_sdk.reasoning_effort,
            "max_context_tokens": config.copilot_sdk.max_context_tokens,
            "sdk_timeout": config.copilot_sdk.sdk_timeout,
        },
        "workiq_mcp": {
            "enabled": config.workiq_mcp.enabled,
            "suppress_setup_prompt": config.workiq_mcp.suppress_setup_prompt,
        },
        "notification": {
            "enabled": config.notification.enabled,
            "open_file_on_click": config.notification.open_file_on_click,
        },
        "file_selection": {
            "max_files": config.file_selection.max_files,
            "discovery_interval": config.file_selection.discovery_interval,
        },
        "quiz": {
            "quiz_server_host": config.quiz.quiz_server_host,
            "quiz_server_port": config.quiz.quiz_server_port,
            "quiz_scoring_timeout": config.quiz.quiz_scoring_timeout,
            "spaced_repetition": {
                "enabled": config.quiz.spaced_repetition.enabled,
                "max_level": config.quiz.spaced_repetition.max_level,
                "intervals": config.quiz.spaced_repetition.intervals,
            },
        },
        "language": config.language,
        "log_level": config.log_level,
    }


def _parse_yaml(raw: str) -> AppConfig:
    """YAML 文字列をパースして AppConfig を返す。"""
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("config.yaml のルートが辞書ではありません")
    return _dict_to_app_config(data)


def load(
    config_path: Path | None = None,
    *,
    notify_callback: Callable[[str, str], None] | None = None,
) -> AppConfig:
    """config.yaml を読み込む。失敗時は .bak → デフォルト値の順でフォールバックする。

    Args:
        config_path: config.yaml のパス。None の場合はデフォルトパスを使用。
        notify_callback: 警告通知コールバック（title, message）。

    Returns:
        読み込んだ AppConfig。
    """
    path = config_path or DEFAULT_CONFIG_PATH

    config = safe_read_with_fallback(
        file_path=path,
        parser=_parse_yaml,
        default_factory=AppConfig,
        notify_callback=notify_callback,
    )
    assert isinstance(config, AppConfig)
    logger.info("設定ファイルを読み込みました: %s", path)
    return config


def save(
    config: AppConfig,
    config_path: Path | None = None,
) -> None:
    """AppConfig を config.yaml に書き込む（アトミック書き込み + .bak バックアップ）。

    Args:
        config: 書き込む AppConfig。
        config_path: config.yaml のパス。None の場合はデフォルトパスを使用。
    """
    path = config_path or DEFAULT_CONFIG_PATH
    data = _app_config_to_dict(config)
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    atomic_write(path, content, create_backup=True)
    logger.info("設定ファイルを保存しました: %s", path)


def generate_default(config_path: Path | None = None) -> AppConfig:
    """デフォルトの config.yaml を生成して保存する。

    Args:
        config_path: config.yaml のパス。None の場合はデフォルトパスを使用。

    Returns:
        生成したデフォルトの AppConfig。
    """
    config = AppConfig()
    save(config, config_path)
    logger.info("デフォルト設定ファイルを生成しました")
    return config
