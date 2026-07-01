"""autostart モジュールのユニットテスト。

実際の PowerShell 実行やシステムのスタートアップフォルダを汚さないよう、
``APPDATA`` を tmp_path に向け、``subprocess.run`` をモックする。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import autostart


@pytest.fixture
def startup_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """APPDATA を tmp_path に向け、スタートアップフォルダを作成して返す。"""
    appdata = tmp_path / "AppData" / "Roaming"
    startup = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    return startup


class TestIsEnabled:
    def test_false_when_no_shortcut(self, startup_dir: Path):
        assert autostart.is_enabled() is False

    def test_true_when_shortcut_exists(self, startup_dir: Path):
        (startup_dir / autostart._LNK_NAME).write_text("x")
        assert autostart.is_enabled() is True


class TestEnable:
    def test_enable_creates_shortcut(self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch):
        captured: dict[str, list[str]] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            # PowerShell によるショートカット作成を模擬する
            autostart._shortcut_path().write_text("lnk")
            return SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(autostart.subprocess, "run", fake_run)

        assert autostart.enable() is True
        assert autostart.is_enabled() is True

        ps_script = captured["cmd"][-1]
        assert "-m app.main" in ps_script
        assert autostart._LNK_NAME in ps_script

    def test_enable_returns_false_when_startup_dir_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("APPDATA", str(tmp_path / "nonexistent"))
        assert autostart.enable() is False

    def test_enable_returns_false_on_nonzero_rc(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def fake_run(cmd, **kwargs):
            return SimpleNamespace(returncode=1, stderr="boom")

        monkeypatch.setattr(autostart.subprocess, "run", fake_run)
        assert autostart.enable() is False

    def test_enable_returns_false_on_exception(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def fake_run(cmd, **kwargs):
            raise OSError("powershell not found")

        monkeypatch.setattr(autostart.subprocess, "run", fake_run)
        assert autostart.enable() is False


class TestDisable:
    def test_disable_removes_shortcut(self, startup_dir: Path):
        lnk = startup_dir / autostart._LNK_NAME
        lnk.write_text("x")
        assert autostart.disable() is True
        assert not lnk.exists()

    def test_disable_noop_when_missing(self, startup_dir: Path):
        assert autostart.disable() is True


class TestSetEnabled:
    def test_set_enabled_true_calls_enable(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        calls: list[str] = []
        monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
        monkeypatch.setattr(autostart, "disable", lambda: calls.append("disable") or True)
        autostart.set_enabled(True)
        assert calls == ["enable"]

    def test_set_enabled_false_calls_disable(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        calls: list[str] = []
        monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
        monkeypatch.setattr(autostart, "disable", lambda: calls.append("disable") or True)
        autostart.set_enabled(False)
        assert calls == ["disable"]


class TestSync:
    def test_enables_when_desired_and_missing(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        calls: list[str] = []
        monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
        monkeypatch.setattr(autostart, "disable", lambda: calls.append("disable") or True)
        autostart.sync(True)
        assert calls == ["enable"]

    def test_disables_when_not_desired_and_present(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (startup_dir / autostart._LNK_NAME).write_text("x")
        calls: list[str] = []
        monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
        monkeypatch.setattr(autostart, "disable", lambda: calls.append("disable") or True)
        autostart.sync(False)
        assert calls == ["disable"]

    def test_noop_when_already_matching(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        calls: list[str] = []
        monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
        monkeypatch.setattr(autostart, "disable", lambda: calls.append("disable") or True)
        autostart.sync(False)  # 望ましい状態=無効、実状態=未登録 → 何もしない
        assert calls == []

    def test_sync_swallows_exceptions(
        self, startup_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def boom() -> bool:
            raise RuntimeError("fail")

        monkeypatch.setattr(autostart, "enable", boom)
        # 例外は送出されず握りつぶされる
        autostart.sync(True)


class TestResolveTarget:
    def test_prefers_pythonw_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        pythonw = tmp_path / "pythonw.exe"
        pythonw.write_text("")
        python = tmp_path / "python.exe"
        python.write_text("")
        monkeypatch.setattr(autostart.sys, "executable", str(python))
        assert autostart._resolve_target() == pythonw

    def test_falls_back_to_executable_when_no_pythonw(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        python = tmp_path / "python.exe"
        python.write_text("")
        monkeypatch.setattr(autostart.sys, "executable", str(python))
        assert autostart._resolve_target() == python
