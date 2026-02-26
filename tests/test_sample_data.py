"""sample_data モジュールのユニットテスト。"""

from pathlib import Path

from app.sample_data import _SAMPLES, generate_sample_data


# ────────────────────────────────────────────
# _SAMPLES 定義の整合性
# ────────────────────────────────────────────

class TestSamplesDefinition:
    def test_sample_count(self):
        """サンプルは 10 ファイル分定義されている。"""
        assert len(_SAMPLES) == 10

    def test_all_samples_have_required_keys(self):
        """各サンプルに filename, ja, en キーがある。"""
        for i, sample in enumerate(_SAMPLES):
            assert "filename" in sample, f"sample[{i}] missing 'filename'"
            assert "ja" in sample, f"sample[{i}] missing 'ja'"
            assert "en" in sample, f"sample[{i}] missing 'en'"

    def test_filenames_are_unique(self):
        """ファイル名が重複していない。"""
        filenames = [s["filename"] for s in _SAMPLES]
        assert len(filenames) == len(set(filenames))

    def test_filenames_end_with_md(self):
        """全ファイル名が .md で終わる。"""
        for sample in _SAMPLES:
            assert str(sample["filename"]).endswith(".md")

    def test_content_contains_heading(self):
        """ja/en コンテンツに Markdown 見出し (#) が含まれる。"""
        for i, sample in enumerate(_SAMPLES):
            assert "#" in str(sample["ja"]), f"sample[{i}] ja has no heading"
            assert "#" in str(sample["en"]), f"sample[{i}] en has no heading"


# ────────────────────────────────────────────
# generate_sample_data — 日本語
# ────────────────────────────────────────────

class TestGenerateSampleDataJa:
    def test_creates_all_files(self, tmp_path: Path):
        """ja で 10 ファイル全て生成される。"""
        created = generate_sample_data(tmp_path, "ja")
        assert len(created) == 10
        for p in created:
            assert p.exists()
            assert p.suffix == ".md"

    def test_content_is_japanese(self, tmp_path: Path):
        """生成されたファイルに日本語文字が含まれる。"""
        generate_sample_data(tmp_path, "ja")
        first_file = tmp_path / _SAMPLES[0]["filename"]
        content = first_file.read_text(encoding="utf-8")
        # 日本語のひらがな・カタカナ・漢字が含まれる
        assert any("\u3040" <= c <= "\u9fff" for c in content)

    def test_creates_target_directory(self, tmp_path: Path):
        """存在しないディレクトリを自動作成する。"""
        target = tmp_path / "sub" / "deep"
        created = generate_sample_data(target, "ja")
        assert len(created) == 10
        assert target.is_dir()


# ────────────────────────────────────────────
# generate_sample_data — 英語
# ────────────────────────────────────────────

class TestGenerateSampleDataEn:
    def test_creates_all_files(self, tmp_path: Path):
        """en で 10 ファイル全て生成される。"""
        created = generate_sample_data(tmp_path, "en")
        assert len(created) == 10

    def test_content_is_english(self, tmp_path: Path):
        """生成されたファイルに英語テキストが含まれる。"""
        generate_sample_data(tmp_path, "en")
        first_file = tmp_path / _SAMPLES[0]["filename"]
        content = first_file.read_text(encoding="utf-8")
        # 英語のアルファベットが含まれ、日本語文字を含まない
        assert any(c.isascii() and c.isalpha() for c in content)


# ────────────────────────────────────────────
# generate_sample_data — スキップ動作
# ────────────────────────────────────────────

class TestGenerateSampleDataSkip:
    def test_skips_existing_files(self, tmp_path: Path):
        """既存ファイルはスキップし、上書きしない。"""
        first_filename = str(_SAMPLES[0]["filename"])
        existing = tmp_path / first_filename
        existing.write_text("original content", encoding="utf-8")

        created = generate_sample_data(tmp_path, "ja")
        assert len(created) == 9
        # 既存ファイルの内容が変わっていない
        assert existing.read_text(encoding="utf-8") == "original content"

    def test_all_exist_returns_empty(self, tmp_path: Path):
        """全ファイル既存の場合は空リストを返す。"""
        generate_sample_data(tmp_path, "ja")
        created_second = generate_sample_data(tmp_path, "ja")
        assert created_second == []


# ────────────────────────────────────────────
# generate_sample_data — フォールバック
# ────────────────────────────────────────────

class TestGenerateSampleDataFallback:
    def test_unsupported_language_falls_back_to_ja(self, tmp_path: Path):
        """未対応言語は ja にフォールバックして生成される。"""
        created = generate_sample_data(tmp_path, "fr")
        assert len(created) == 10
        first_file = tmp_path / _SAMPLES[0]["filename"]
        content = first_file.read_text(encoding="utf-8")
        # ja コンテンツが書き込まれていることを確認
        assert any("\u3040" <= c <= "\u9fff" for c in content)
