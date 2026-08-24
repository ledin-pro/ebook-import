from __future__ import annotations

import os
import json
import shutil
import zipfile
from pathlib import Path

from pro.ledin.ebook_import import main
from .helpers import make_epub


def test_import_generates_agent_corpus(tmp_path: Path) -> None:
    source = tmp_path / "author_title.fb2.epub"
    vault = tmp_path / "vault"
    make_epub(source)

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    book_dir = vault / "05-sources/books/testovaya-kniga"
    book = (book_dir / "book.md").read_text(encoding="utf-8")
    chapter = next((book_dir / "chapters").glob("*.md")).read_text(encoding="utf-8")

    assert "Тестовая книга" in book
    assert "Глава 1" in chapter
    assert "Привет, **мир**." in chapter
    assert "![Иллюстрация](../media/picture.png)" in chapter
    assert (book_dir / "original/book.epub").is_file()
    assert (book_dir / "media/picture.png").read_bytes() == b"png-fixture"
    assert "testovaya-kniga/book.md" in (vault / "05-sources/books/index.md").read_text(encoding="utf-8")


def test_same_hash_is_a_noop(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    vault = tmp_path / "vault"
    make_epub(source)
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    book_dir = vault / "05-sources/books/testovaya-kniga"
    chapter = next((book_dir / "chapters").glob("*.md"))
    chapter.write_text(chapter.read_text(encoding="utf-8") + "\nUser note\n", encoding="utf-8")
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    assert "User note" in chapter.read_text(encoding="utf-8")


def test_same_hash_removes_duplicate_copies(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    vault = tmp_path / "vault"
    make_epub(source)
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    book_dir = vault / "05-sources/books/testovaya-kniga"
    chapter = next((book_dir / "chapters").glob("*.md"))
    media = book_dir / "media/picture.png"
    duplicate_chapter = chapter.with_name(f"{chapter.stem} 2{chapter.suffix}")
    duplicate_media = media.with_name(f"{media.stem} 2{media.suffix}")
    legacy_duplicate = chapter.with_name("legacy-title 3.md")
    shutil.copy2(chapter, duplicate_chapter)
    shutil.copy2(media, duplicate_media)
    legacy_duplicate.write_text(chapter.read_text(encoding="utf-8").replace("Глава 1", "Legacy title"), encoding="utf-8")
    os.utime(legacy_duplicate, (chapter.stat().st_atime, chapter.stat().st_mtime - 1))

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    assert not duplicate_chapter.exists()
    assert not duplicate_media.exists()
    assert not legacy_duplicate.exists()


def test_skip_image_mode_omits_media_and_rebuilds_when_changed(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    vault = tmp_path / "vault"
    make_epub(source)

    assert main(["import", "--vault-root", str(vault), "--image-mode", "skip", "--input", str(source)]) == 0
    book_dir = vault / "05-sources/books/testovaya-kniga"
    chapter = next((book_dir / "chapters").glob("*.md"))
    assert "![Иллюстрация]" not in chapter.read_text(encoding="utf-8")
    assert not (book_dir / "media").exists()
    assert json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))["image_mode"] == "skip"

    (book_dir / "media").mkdir()
    (book_dir / "media/stale.png").write_bytes(b"stale")
    assert main(["import", "--vault-root", str(vault), "--image-mode", "skip", "--input", str(source)]) == 0
    assert not (book_dir / "media").exists()

    assert main(["import", "--vault-root", str(vault), "--image-mode", "import", "--input", str(source)]) == 0
    assert (book_dir / "media/picture.png").is_file()
    assert "![Иллюстрация](../media/picture.png)" in chapter.read_text(encoding="utf-8")


def test_apply_agent_image_text_replaces_and_removes_media(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    vault = tmp_path / "vault"
    mapping = tmp_path / "image-text.json"
    make_epub(source)
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    book_dir = vault / "05-sources/books/testovaya-kniga"
    mapping.write_text(json.dumps({"image_text": {"media/picture.png": "Распознанный текст"}}), encoding="utf-8")

    assert main(["apply-image-text", "--book-dir", str(book_dir), "--mapping", str(mapping)]) == 0
    chapter = next((book_dir / "chapters").glob("*.md")).read_text(encoding="utf-8")
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "Распознанный текст" in chapter
    assert "../media/" not in chapter
    assert not (book_dir / "media").exists()
    assert manifest["image_mode"] == "ocr"
    assert manifest["ocr"]["replaced"] == 1
    assert 'image_mode: "ocr"' in (book_dir / "book.md").read_text(encoding="utf-8")


def test_apply_agent_image_text_without_text_removes_marker(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    vault = tmp_path / "vault"
    mapping = tmp_path / "image-text.json"
    make_epub(source)
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    book_dir = vault / "05-sources/books/testovaya-kniga"
    mapping.write_text(json.dumps({"image_text": {"media/picture.png": ""}}), encoding="utf-8")

    assert main(["apply-image-text", "--book-dir", str(book_dir), "--mapping", str(mapping)]) == 0
    chapter = next((book_dir / "chapters").glob("*.md")).read_text(encoding="utf-8")
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "![Иллюстрация]" not in chapter
    assert not (book_dir / "media").exists()
    assert manifest["ocr"]["without_text"] == 1
