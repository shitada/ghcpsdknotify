"""quiz_scorer モジュールのユニットテスト。

純粋関数（_read_source_content, _extract_quiz_questions）をテスト。
SDK 連携系は copilot_client テストでカバー済み。
"""

from pathlib import Path

from app.quiz_scorer import _read_source_content, _extract_quiz_questions


# ────────────────────────────────────────────
# _read_source_content
# ────────────────────────────────────────────

class TestReadSourceContent:
    def test_finds_file(self, tmp_path: Path):
        md = tmp_path / "topic.md"
        md.write_text("# Source content", encoding="utf-8")
        result = _read_source_content("topic.md", [str(tmp_path)])
        assert result == "# Source content"

    def test_topic_key_with_hash(self, tmp_path: Path):
        md = tmp_path / "doc.md"
        md.write_text("# Doc", encoding="utf-8")
        result = _read_source_content("doc.md#section1", [str(tmp_path)])
        assert result == "# Doc"

    def test_missing_file_returns_empty(self, tmp_path: Path):
        result = _read_source_content("nope.md", [str(tmp_path)])
        assert result == ""

    def test_searches_multiple_folders(self, tmp_path: Path):
        f1 = tmp_path / "f1"
        f2 = tmp_path / "f2"
        f1.mkdir()
        f2.mkdir()
        (f2 / "found.md").write_text("in f2", encoding="utf-8")
        result = _read_source_content("found.md", [str(f1), str(f2)])
        assert result == "in f2"


# ────────────────────────────────────────────
# _extract_quiz_questions
# ────────────────────────────────────────────

class TestExtractQuizQuestions:
    def test_extracts_q1_q2(self):
        content = """
<!-- topic_key: doc.md#s1 -->
### トピック

**Q1:** 正しいものは？
A) aaa
B) bbb
C) ccc
D) ddd

**Q2:** 要約してください。
ヒント: 重要なポイントを含めること

<!-- topic_key: doc.md#s2 -->
"""
        q1, q2 = _extract_quiz_questions(content, "doc.md#s1")
        assert "Q1" in q1
        assert "A)" in q1
        assert "Q2" in q2
        assert "要約" in q2

    def test_topic_key_not_found(self):
        q1, q2 = _extract_quiz_questions("# Nothing here", "missing_key")
        assert q1 == ""
        assert q2 == ""

    def test_single_topic(self):
        content = """
<!-- topic_key: single.md -->
### Topic

**Q1:** Which?
A) X
B) Y

**Q2:** Explain.
"""
        q1, q2 = _extract_quiz_questions(content, "single.md")
        assert "Q1" in q1
        assert "Q2" in q2
