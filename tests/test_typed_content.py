from __future__ import annotations

from pathlib import Path

from pro.ledin.ebook_import import (
    Emphasis,
    FootnoteDefinition,
    FootnoteRef,
    Group,
    Heading,
    ImageBlock,
    Paragraph,
    Poem,
    Quote,
    Strong,
    Table,
    parse_book,
    render_markdown,
)

from .helpers import make_epub, make_fb2


def flatten(blocks):
    for block in blocks:
        yield block
        if isinstance(block, Group):
            yield from flatten(block.children)
        if isinstance(block, Quote):
            yield from flatten(block.children)


def test_public_parse_api_returns_typed_epub_content(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    book = parse_book(source)
    blocks = list(flatten(book.chapters[0].blocks))
    assert book.format == "epub"
    assert any(isinstance(block, Paragraph) for block in blocks)
    paragraph = next(block for block in blocks if isinstance(block, Paragraph) and any(isinstance(node, Strong) for node in block.children))
    assert any(isinstance(node, Strong) for node in paragraph.children)
    assert any(isinstance(block, Quote) for block in blocks)
    assert any(isinstance(block, ImageBlock) for block in blocks)
    assert render_markdown(book.chapters[0].blocks) == book.chapters[0].markdown


def test_public_parse_api_preserves_fb2_semantics(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    make_fb2(source)
    book = parse_book(source)
    blocks = list(flatten(book.chapters[0].blocks))
    assert book.format == "fb2"
    assert any(isinstance(block, Quote) and block.kind == "epigraph" for block in blocks)
    assert any(isinstance(block, Poem) for block in blocks)
    assert any(isinstance(block, Table) for block in blocks)
    assert any(isinstance(block, FootnoteDefinition) for block in blocks)
    assert any(isinstance(block, Group) and block.kind == "section" for block in blocks)
    paragraph = next(block for block in blocks if isinstance(block, Paragraph) and any(isinstance(node, FootnoteRef) for node in block.children))
    assert any(isinstance(node, FootnoteRef) for node in paragraph.children)


def test_typed_markdown_keeps_nested_inline_formatting(tmp_path: Path) -> None:
    source = tmp_path / "book.fb2"
    make_fb2(source)
    book = parse_book(source)
    paragraph = next(block for block in book.chapters[0].blocks if isinstance(block, Paragraph))
    assert any(isinstance(node, Strong) for node in paragraph.children)
    assert any(isinstance(node, Emphasis) for node in paragraph.children)
    assert "**жирный**" in book.chapters[0].markdown
    assert "*курсив*" in book.chapters[0].markdown
