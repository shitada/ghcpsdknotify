"""folder_scanner モジュールのユニットテスト。"""

from pathlib import Path

from app.folder_scanner import (
    FileMetadata,
    ScannedFile,
    _extract_frontmatter,
    _count_checkboxes,
    scan_folder,
    scan_folders,
)


# ────────────────────────────────────────────
# _extract_frontmatter
# ────────────────────────────────────────────

class TestExtractFrontmatter:
    def test_valid_frontmatter(self):
        raw = "---\ntitle: Hello\npriority: high\n---\nBody text"
        fm, body = _extract_frontmatter(raw)
        assert fm["title"] == "Hello"
        assert fm["priority"] == "high"
        assert body == "Body text"

    def test_no_frontmatter(self):
        raw = "Just body text"
        fm, body = _extract_frontmatter(raw)
        assert fm == {}
        assert body == "Just body text"

    def test_empty_frontmatter(self):
        raw = "---\n---\nBody text"
        fm, body = _extract_frontmatter(raw)
        # yaml.safe_load of empty string returns None → not dict → {}, raw
        assert fm == {}

    def test_frontmatter_with_list(self):
        raw = "---\ntags:\n  - python\n  - ml\n---\nContent"
        fm, body = _extract_frontmatter(raw)
        assert fm["tags"] == ["python", "ml"]
        assert body == "Content"

    def test_frontmatter_with_date(self):
        raw = "---\ndeadline: 2026-06-01\n---\nContent"
        fm, body = _extract_frontmatter(raw)
        assert fm["deadline"] is not None

    def test_invalid_yaml_returns_empty(self):
        raw = "---\n: invalid: yaml: [[[\n---\nBody"
        fm, body = _extract_frontmatter(raw)
        # 不正な YAML → パース失敗 → 空辞書 + 全文
        assert fm == {}


# ────────────────────────────────────────────
# _count_checkboxes
# ────────────────────────────────────────────

class TestCountCheckboxes:
    def test_no_checkboxes(self):
        assert _count_checkboxes("hello world") == (0, 0)

    def test_unchecked_only(self):
        text = "- [ ] task1\n- [ ] task2\n"
        assert _count_checkboxes(text) == (2, 0)

    def test_checked_only(self):
        text = "- [x] done1\n- [X] done2\n"
        assert _count_checkboxes(text) == (0, 2)

    def test_mixed(self):
        text = "- [ ] todo\n- [x] done\n- [ ] todo2\n"
        assert _count_checkboxes(text) == (2, 1)


# ────────────────────────────────────────────
# scan_folder (tmp_path)
# ────────────────────────────────────────────

class TestScanFolder:
    def test_empty_folder(self, tmp_path: Path):
        result = scan_folder(tmp_path)
        assert result == []

    def test_single_md_file(self, tmp_path: Path):
        md_file = tmp_path / "test.md"
        md_file.write_text("---\npriority: high\n---\n# Hello\n", encoding="utf-8")
        result = scan_folder(tmp_path)
        assert len(result) == 1
        assert result[0].metadata.priority == "high"
        assert "# Hello" in result[0].content

    def test_non_md_files_ignored(self, tmp_path: Path):
        (tmp_path / "test.txt").write_text("text file", encoding="utf-8")
        (tmp_path / "test.py").write_text("print(1)", encoding="utf-8")
        result = scan_folder(tmp_path)
        assert result == []

    def test_nested_folders(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.md").write_text("# Nested", encoding="utf-8")
        result = scan_folder(tmp_path)
        assert len(result) == 1
        assert "sub" in result[0].metadata.relative_path

    def test_briefings_folder_skipped(self, tmp_path: Path):
        briefings = tmp_path / "_briefings"
        briefings.mkdir()
        (briefings / "out.md").write_text("# Output", encoding="utf-8")
        result = scan_folder(tmp_path)
        assert result == []

    def test_checkbox_count(self, tmp_path: Path):
        md = tmp_path / "todo.md"
        md.write_text("- [ ] task1\n- [x] done\n- [ ] task2\n", encoding="utf-8")
        result = scan_folder(tmp_path)
        assert result[0].metadata.unchecked_count == 2
        assert result[0].metadata.checked_count == 1

    def test_nonexistent_folder(self):
        result = scan_folder("/nonexistent/path/12345")
        assert result == []

    def test_custom_extensions(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("md", encoding="utf-8")
        (tmp_path / "b.txt").write_text("txt", encoding="utf-8")
        result = scan_folder(tmp_path, target_extensions=[".txt"])
        assert len(result) == 1
        assert result[0].metadata.relative_path.endswith(".txt")


# ────────────────────────────────────────────
# scan_folders (tmp_path)
# ────────────────────────────────────────────

class TestScanFolders:
    def test_multiple_folders(self, tmp_path: Path):
        f1 = tmp_path / "folder1"
        f2 = tmp_path / "folder2"
        f1.mkdir()
        f2.mkdir()
        (f1 / "a.md").write_text("A", encoding="utf-8")
        (f2 / "b.md").write_text("B", encoding="utf-8")
        result = scan_folders([str(f1), str(f2)])
        assert len(result) == 2

    def test_deduplicates_same_file(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("A", encoding="utf-8")
        # 同じフォルダを2回指定
        result = scan_folders([str(tmp_path), str(tmp_path)])
        assert len(result) == 1
