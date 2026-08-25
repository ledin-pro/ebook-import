from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from pro.ledin.ebook_import import epub, fb2, mobi, render
from pro.ledin.ebook_import import core
from pro.ledin.ebook_import.models import ParsedAsset
from pro.ledin.ebook_import.utils import EbookImportError

from .helpers import fb2_xml, make_epub


def write_epub_members(path: Path, members: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


@pytest.mark.parametrize(
    "members,message",
    [
        ({}, "container"),
        ({"META-INF/container.xml": "<container/>"}, "rootfile"),
        ({"META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="missing.opf"/></rootfiles></container>'}, "rootfile is missing"),
        ({
            "META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>',
            "book.opf": '<package xmlns="http://www.idpf.org/2007/opf"><manifest/><spine/></package>',
        }, "metadata"),
        ({
            "META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>',
            "book.opf": '<package xmlns="http://www.idpf.org/2007/opf"><metadata/><manifest/><spine/></package>',
        }, "spine"),
    ],
)
def test_epub_structural_errors(tmp_path: Path, members: dict[str, str | bytes], message: str) -> None:
    source = tmp_path / "bad.epub"
    write_epub_members(source, members)
    with pytest.raises(EbookImportError, match=message):
        epub.parse_epub(source)


def test_invalid_epub_zip_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "bad.epub"
    source.write_bytes(b"not a zip")
    with pytest.raises(EbookImportError, match="Invalid EPUB"):
        epub.parse_epub(source)


def test_epub_markdown_parser_exercises_inline_blocks_and_missing_images(tmp_path: Path) -> None:
    source = tmp_path / "assets.epub"
    write_epub_members(source, {"OPS/images/a.png": b"a", "OPS/images/A.png": b"b"})
    with zipfile.ZipFile(source) as archive:
        assets: dict[str, ParsedAsset] = {}
        parser = epub.MarkdownParser("OPS/chapter.xhtml", archive, "OPS", "import", assets, {})
        parser.feed(
            "<html><head><style>x</style><title>x</title></head><body>"
            "<h2>Heading</h2><p><b>Bold </b><i>italic</i> <code>code</code> "
            "<a href='target'>link</a><br/>next</p><ul><li>One</li></ul>"
            "<blockquote>Quote</blockquote><img src='images/a.png' alt='A'/>"
            "<img src='images/A.png' alt='B'/><img src='images/missing.png'/></body></html>"
        )
        text = parser.markdown()
    assert "## Heading" in text
    assert "**Bold** *italic* `code` [link](target)" in text
    assert "- One" in text and "> Quote" in text
    assert len(assets) == 2
    assert len({asset.filename for asset in assets.values()}) == 2


def test_epub_metadata_defaults_and_title_fallback(tmp_path: Path) -> None:
    source = tmp_path / "minimal.epub"
    container = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>'
    opf = '<package xmlns="http://www.idpf.org/2007/opf"><metadata/><manifest><item id="c" href="untitled.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>'
    write_epub_members(source, {"META-INF/container.xml": container, "OPS/book.opf": opf, "OPS/untitled.xhtml": "<html><body><p>Text</p></body></html>"})
    parsed = epub.parse_epub(source)
    assert parsed.metadata["title"] == "Untitled book"
    assert parsed.metadata["authors"] == ["Unknown author"]
    assert parsed.chapters[0].title == "Untitled"


def minimal_fb2(body: str, *, title_info: str = "<book-title>Simple</book-title><lang>en</lang>") -> bytes:
    return f'''<?xml version="1.0"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:xlink="http://www.w3.org/1999/xlink"><description><title-info>{title_info}</title-info></description>{body}</FictionBook>'''.encode()


def test_fb2_body_without_sections_and_inline_fallbacks(tmp_path: Path) -> None:
    source = tmp_path / "simple.fb2"
    source.write_bytes(minimal_fb2('<body name="main"><p>A <strikethrough>strike</strikethrough> <code>code</code> H<sub>2</sub>O x<sup>2</sup> <a xlink:href="https://example.com">link</a>.</p><empty-line/><table><tr><td colspan="2">wide</td></tr></table></body>'))
    parsed = fb2.parse_fb2(source)
    assert len(parsed.chapters) == 1
    text = parsed.chapters[0].markdown
    assert "~~strike~~" in text and "`code`" in text
    assert "<sub>2</sub>" in text and "<sup>2</sup>" in text
    assert "[link](https://example.com)" in text
    assert "<table>" in text


def test_fb2_metadata_fallbacks_and_missing_binary_warning(tmp_path: Path) -> None:
    source = tmp_path / "fallback.fb2"
    source.write_bytes(minimal_fb2('<body><section><image xlink:href="#missing"/><p>Text</p></section></body>', title_info='<author><nickname>Nick</nickname></author><book-title></book-title>'))
    parsed = fb2.parse_fb2(source)
    assert parsed.metadata["title"] == "Untitled book"
    assert parsed.metadata["authors"] == ["Nick"]
    assert parsed.metadata["language"] == "und"
    assert parsed.warnings == ["Missing FB2 binary: missing"]


def test_fb2_missing_required_structure(tmp_path: Path) -> None:
    no_info = tmp_path / "no-info.fb2"
    no_info.write_bytes(b'<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><body/></FictionBook>')
    with pytest.raises(EbookImportError, match="title-info"):
        fb2.parse_fb2(no_info)
    no_body = tmp_path / "no-body.fb2"
    no_body.write_bytes(minimal_fb2(""))
    with pytest.raises(EbookImportError, match="no readable content"):
        fb2.parse_fb2(no_body)


def test_fb2_configured_safety_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "book.fb2"
    source.write_bytes(fb2_xml())
    monkeypatch.setattr(fb2, "MAX_SOURCE_BYTES", 1)
    with pytest.raises(EbookImportError, match="source exceeds"):
        fb2.parse_fb2(source)

    monkeypatch.setattr(fb2, "MAX_SOURCE_BYTES", 100 * 1024 * 1024)
    monkeypatch.setattr(fb2, "MAX_ELEMENTS", 2)
    with pytest.raises(EbookImportError, match="element-count"):
        fb2.parse_fb2(source)

    monkeypatch.setattr(fb2, "MAX_ELEMENTS", 1_000_000)
    monkeypatch.setattr(fb2, "MAX_DEPTH", 2)
    with pytest.raises(EbookImportError, match="nesting-depth"):
        fb2.parse_fb2(source)


def test_fb2_asset_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "book.fb2"
    source.write_bytes(fb2_xml())
    monkeypatch.setattr(fb2, "MAX_ASSET_BYTES", 1)
    with pytest.raises(EbookImportError, match="asset safety"):
        fb2.parse_fb2(source)


def test_fb2_zip_member_and_size_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "book.fbz"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("book.fb2", fb2_xml())
        archive.writestr("extra.txt", "x")
    monkeypatch.setattr(fb2, "MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(EbookImportError, match="too many"):
        fb2.parse_fb2(source)
    monkeypatch.setattr(fb2, "MAX_ARCHIVE_MEMBERS", 1000)
    monkeypatch.setattr(fb2, "MAX_ARCHIVE_BYTES", 1)
    with pytest.raises(EbookImportError, match="expands beyond"):
        fb2.parse_fb2(source)


def test_fb2_zip_allows_harmless_extra_member(tmp_path: Path) -> None:
    source = tmp_path / "book.fbz"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("folder/", "")
        archive.writestr("README.txt", "metadata")
        archive.writestr("folder/book.fb2", fb2_xml())
    assert fb2.parse_fb2(source).metadata["title"] == "Тестовая FB2 книга"


def test_invalid_fb2_zip_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "book.fbz"
    source.write_bytes(b"not a zip")
    with pytest.raises(EbookImportError, match="Invalid compressed"):
        fb2.parse_fb2(source)


def test_fb2_missing_note_and_multiple_bodies_warn_without_dropping_content(tmp_path: Path) -> None:
    source = tmp_path / "notes.fb2"
    source.write_bytes(
        minimal_fb2(
            '<body><section id="a"><title><p>A</p></title><p>One<a type="note" xlink:href="#missing">n</a></p></section></body>'
            '<body name="appendix"><section id="b"><title><p>B</p></title><p>Two</p></section></body>'
        )
    )
    parsed = fb2.parse_fb2(source)
    assert [chapter.title for chapter in parsed.chapters] == ["A", "B"]
    assert "Missing note." in parsed.chapters[0].markdown
    assert parsed.warnings == ["Missing FB2 note target: missing"]


def test_fb2_colliding_note_ids_get_unique_labels(tmp_path: Path) -> None:
    source = tmp_path / "notes.fb2"
    source.write_bytes(
        minimal_fb2(
            '<body><section><title><p>A</p></title><p><a type="note" xlink:href="#a_b">1</a><a type="note" xlink:href="#a-b">2</a></p></section></body>'
            '<body name="notes"><section id="a_b"><p>One</p></section><section id="a-b"><p>Two</p></section></body>'
        )
    )
    text = fb2.parse_fb2(source).chapters[0].markdown
    assert "[^a-b]" in text and "[^a-b-2]" in text
    assert "[^a-b]: One" in text and "[^a-b-2]: Two" in text


def test_mobi_converter_low_level_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(args[0], 1)),
    )
    with pytest.raises(EbookImportError, match="timed out"):
        mobi.run_converter(["tool"])

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")))
    with pytest.raises(EbookImportError, match="Could not start"):
        mobi.run_converter(["tool"])


def test_mobitool_requires_exactly_one_epub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mobi, "run_converter", lambda args: None)
    with pytest.raises(EbookImportError, match="0 EPUB"):
        mobi.convert_with_mobitool(tmp_path / "book.mobi", tmp_path, "mobitool")
    (tmp_path / "one.epub").write_bytes(b"1")
    (tmp_path / "two.epub").write_bytes(b"2")
    with pytest.raises(EbookImportError, match="2 EPUB"):
        mobi.convert_with_mobitool(tmp_path / "book.mobi", tmp_path, "mobitool")


def test_calibre_requires_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mobi, "run_converter", lambda args: None)
    with pytest.raises(EbookImportError, match="did not produce"):
        mobi.convert_with_calibre(tmp_path / "book.mobi", tmp_path, "ebook-convert")


def test_mobi_tool_discovery_and_version_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calibre = tmp_path / "ebook-convert"
    fake_calibre.write_text("x")
    monkeypatch.setattr(mobi.shutil, "which", lambda name: None)
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", fake_calibre)
    assert mobi.find_tool("ebook-convert") == str(fake_calibre)
    assert mobi.find_tool("mobitool") is None
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("bad")))
    assert mobi.tool_version(str(fake_calibre), "calibre") == "unknown"


def test_doctor_backend_selection_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "available_backends", lambda: {"mobitool": {"available": True}, "calibre": {"available": True}})
    assert core.doctor()["auto_mobi_backend"] == "mobitool"
    monkeypatch.setattr(core, "available_backends", lambda: {"mobitool": {"available": False}, "calibre": {"available": True}})
    assert core.doctor()["auto_mobi_backend"] == "calibre"


def test_direct_main_missing_input_branch(tmp_path: Path) -> None:
    assert core.main(["import", "--vault-root", str(tmp_path / "vault"), "--input", str(tmp_path / "missing.epub")]) == 8


def test_render_helpers_invalid_state(tmp_path: Path) -> None:
    invalid = tmp_path / "manifest.json"
    invalid.write_text("not json")
    assert render.read_manifest(invalid) is None
    assert render.generated_output_complete(tmp_path, {}) is False


def test_generated_output_completeness_branches(tmp_path: Path) -> None:
    book = tmp_path / "book.md"
    book.write_text("book")
    assert render.generated_output_complete(tmp_path, {"original_file": "original/book.fb2"}) is False
    original = tmp_path / "original/book.fb2"
    original.parent.mkdir()
    original.write_bytes(b"book")
    media = tmp_path / "media"
    media.mkdir()
    assert render.generated_output_complete(tmp_path, {"original_file": "original/book.fb2", "image_mode": "skip"}) is False
    media.rmdir()
    manifest = {"original_file": "original/book.fb2", "chapters": [{"file": "chapters/a.md"}]}
    assert render.generated_output_complete(tmp_path, manifest) is False
    chapter = tmp_path / "chapters/a.md"
    chapter.parent.mkdir()
    chapter.write_text("![x](../media/missing.png)")
    assert render.generated_output_complete(tmp_path, manifest) is False
    media.mkdir()
    (media / "missing.png").write_bytes(b"x")
    assert render.generated_output_complete(tmp_path, manifest) is True
