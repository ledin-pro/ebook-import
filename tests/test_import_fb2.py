from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pro.ledin.ebook_import import main
from pro.ledin.ebook_import.fb2 import MAX_COMPRESSION_RATIO

from .helpers import fb2_xml, make_fb2, make_fb2_zip


def book_dir(vault: Path) -> Path:
    return vault / "05-sources/books/testovaya-fb2-kniga"


def test_fb2_import_preserves_structure_metadata_notes_and_images(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    vault = tmp_path / "vault"
    make_fb2(source)

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    output = book_dir(vault)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    chapters = sorted((output / "chapters").glob("*.md"))
    first = chapters[0].read_text(encoding="utf-8")

    assert manifest["format"] == "fb2"
    assert manifest["authors"] == ["Иван Иванович Авторов"]
    assert manifest["genres"] == ["science"]
    assert manifest["series"] == "Серия"
    assert manifest["series_number"] == "2"
    assert manifest["cover_image"] == "media/cover.png"
    assert manifest["original_file"] == "original/book.fb2"
    assert len(chapters) == 2
    assert "# Глава первая" in first
    assert "## Подраздел" in first
    assert "> Эпиграф." in first
    assert "Строка один  \nСтрока два" in first
    assert "[^n1]" in first
    assert "[^n1]: Текст примечания." in first
    assert "| А | Б |" in first
    assert "![" in first and "../media/cover.png" in first
    assert (output / "media/cover.png").read_bytes() == b"png-fixture"
    assert not (output / "media/unused.jpg").exists()
    assert (output / "original/book.fb2").read_bytes() == source.read_bytes()


def test_fb2_skip_mode_avoids_media_and_binary_decoding(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    vault = tmp_path / "vault"
    make_fb2(source, binary="not-valid-base64")

    assert main(["import", "--vault-root", str(vault), "--image-mode", "skip", "--input", str(source)]) == 0
    output = book_dir(vault)
    chapter = next((output / "chapters").glob("*.md")).read_text(encoding="utf-8")
    assert "../media/" not in chapter
    assert not (output / "media").exists()


def test_fb2_invalid_referenced_binary_is_rejected_atomically(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    vault = tmp_path / "vault"
    make_fb2(source, binary="not-valid-base64")

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 4
    assert not (vault / "05-sources/books").exists()


def test_fb2_zip_and_fbz_are_supported(tmp_path: Path) -> None:
    for suffix in ("fb2.zip", "fbz"):
        source = tmp_path / f"book.{suffix}"
        vault = tmp_path / f"vault-{suffix.replace('.', '-')}"
        make_fb2_zip(source)
        assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
        output = book_dir(vault)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        expected = "original/book.fb2.zip" if suffix == "fb2.zip" else "original/book.fbz"
        assert manifest["original_file"] == expected
        assert (output / expected).is_file()


def test_fb2_windows_1251_encoding(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    vault = tmp_path / "vault"
    make_fb2(source, encoding="windows-1251")
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    text = "\n".join(path.read_text(encoding="utf-8") for path in (book_dir(vault) / "chapters").glob("*.md"))
    assert "Глава первая" in text


def test_fb2_doctype_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    source.write_bytes(
        b'''<?xml version="1.0"?><!DOCTYPE FictionBook [<!ENTITY x "boom">]><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><book-title>&x;</book-title></title-info></description><body><section><p>x</p></section></body></FictionBook>'''
    )
    assert main(["import", "--vault-root", str(tmp_path / "vault"), "--input", str(source)]) == 8


def test_fb2_archive_rejects_traversal_and_multiple_payloads(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.fbz"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../book.fb2", fb2_xml())
    assert main(["import", "--vault-root", str(tmp_path / "vault-a"), "--input", str(traversal)]) == 4

    multiple = tmp_path / "multiple.fbz"
    with zipfile.ZipFile(multiple, "w") as archive:
        archive.writestr("one.fb2", fb2_xml())
        archive.writestr("two.fb2", fb2_xml())
    assert main(["import", "--vault-root", str(tmp_path / "vault-b"), "--input", str(multiple)]) == 4


def test_fb2_archive_rejects_excessive_compression_ratio(tmp_path: Path) -> None:
    source = tmp_path / "bomb.fbz"
    payload = fb2_xml().replace("Описание книги.".encode(), b"A" * 2_000_000)
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("book.fb2", payload)
    info = zipfile.ZipFile(source).getinfo("book.fb2")
    assert info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
    assert main(["import", "--vault-root", str(tmp_path / "vault"), "--input", str(source)]) == 4


def test_fb2_same_hash_is_noop_and_mode_change_rebuilds(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    vault = tmp_path / "vault"
    make_fb2(source)
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    output = book_dir(vault)
    chapter = next((output / "chapters").glob("*.md"))
    chapter.write_text(chapter.read_text(encoding="utf-8") + "\nUser note\n", encoding="utf-8")
    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    assert "User note" in chapter.read_text(encoding="utf-8")
    assert main(["import", "--vault-root", str(vault), "--image-mode", "skip", "--input", str(source)]) == 0
    assert "User note" not in chapter.read_text(encoding="utf-8")
    assert not (output / "media").exists()


def test_fb2_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    vault = tmp_path / "vault"
    make_fb2(source)
    assert main(["import", "--vault-root", str(vault), "--dry-run", "--input", str(source)]) == 0
    assert not vault.exists()
