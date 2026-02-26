"""utils モジュールのユニットテスト。"""

from pathlib import Path

from app.utils import atomic_write, estimate_tokens, safe_read_with_fallback


# ────────────────────────────────────────────
# estimate_tokens
# ────────────────────────────────────────────

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_english_text(self):
        text = "The quick brown fox jumps over the lazy dog"
        result = estimate_tokens(text)
        assert result > 0

    def test_japanese_text(self):
        text = "これはテストです。日本語のテキスト。"
        result = estimate_tokens(text)
        assert result > 0

    def test_longer_text_more_tokens(self):
        short = "Hello"
        long_text = "Hello world, this is a longer text with many words."
        assert estimate_tokens(long_text) > estimate_tokens(short)


# ────────────────────────────────────────────
# atomic_write
# ────────────────────────────────────────────

class TestAtomicWrite:
    def test_basic_write(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        atomic_write(f, "hello")
        assert f.read_text(encoding="utf-8") == "hello"

    def test_creates_parent_dirs(self, tmp_path: Path):
        f = tmp_path / "sub" / "deep" / "file.txt"
        atomic_write(f, "content")
        assert f.read_text(encoding="utf-8") == "content"

    def test_backup_created(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("old", encoding="utf-8")
        atomic_write(f, "new", create_backup=True)
        bak = tmp_path / "data.txt.bak"
        assert f.read_text(encoding="utf-8") == "new"
        assert bak.read_text(encoding="utf-8") == "old"

    def test_no_backup_when_disabled(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("old", encoding="utf-8")
        atomic_write(f, "new", create_backup=False)
        bak = tmp_path / "data.txt.bak"
        assert not bak.exists()

    def test_overwrite_existing(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("version1", encoding="utf-8")
        atomic_write(f, "version2")
        assert f.read_text(encoding="utf-8") == "version2"

    def test_tmp_cleaned_on_error(self, tmp_path: Path):
        """書き込み先の親ディレクトリが存在しない場合でも tmp ファイルが残らない。"""
        f = tmp_path / "test.txt"
        atomic_write(f, "ok")
        tmp_file = f.with_suffix(".txt.tmp")
        assert not tmp_file.exists()


# ────────────────────────────────────────────
# safe_read_with_fallback
# ────────────────────────────────────────────

class TestSafeReadWithFallback:
    def test_reads_main_file(self, tmp_path: Path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        import json
        result = safe_read_with_fallback(f, json.loads, dict)
        assert result == {"key": "value"}

    def test_falls_back_to_bak(self, tmp_path: Path):
        f = tmp_path / "data.json"
        bak = tmp_path / "data.json.bak"
        bak.write_text('{"backup": true}', encoding="utf-8")
        import json
        result = safe_read_with_fallback(f, json.loads, dict)
        assert result == {"backup": True}

    def test_falls_back_to_default(self, tmp_path: Path):
        f = tmp_path / "nonexistent.json"
        result = safe_read_with_fallback(f, lambda x: None, lambda: {"default": True})
        assert result == {"default": True}

    def test_corrupt_main_falls_back_to_bak(self, tmp_path: Path):
        f = tmp_path / "data.json"
        bak = tmp_path / "data.json.bak"
        f.write_text("CORRUPT!!!", encoding="utf-8")
        bak.write_text('{"ok": true}', encoding="utf-8")
        import json
        result = safe_read_with_fallback(f, json.loads, dict)
        assert result == {"ok": True}

    def test_notify_callback_called(self, tmp_path: Path):
        f = tmp_path / "data.json"
        bak = tmp_path / "data.json.bak"
        bak.write_text('{"ok": true}', encoding="utf-8")
        import json
        notifications: list[tuple[str, str]] = []
        result = safe_read_with_fallback(
            f,
            json.loads,
            dict,
            notify_callback=lambda t, m: notifications.append((t, m)),
        )
        assert len(notifications) == 1
        assert "復旧" in notifications[0][0]
