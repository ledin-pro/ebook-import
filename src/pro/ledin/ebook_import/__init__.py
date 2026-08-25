"""Deterministic ebook parsing and Obsidian-compatible Markdown importing."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .content import (
    Block,
    CodeBlock,
    Emphasis,
    EmptyLine,
    FootnoteDefinition,
    FootnoteRef,
    Group,
    HardBreak,
    Heading,
    ImageBlock,
    ImageInline,
    Inline,
    InlineCode,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    Poem,
    Quote,
    Stanza,
    Strike,
    Strong,
    Subscript,
    Superscript,
    Table,
    TableCell,
    TableRow,
    Text,
    Verse,
    render_markdown,
)
from .core import main
from .models import ParsedAsset, ParsedBook, ParsedChapter
from .parsing import parse_book
from .utils import EbookImportError

try:
    __version__ = version("pro-ledin-ebook-import")
except PackageNotFoundError:
    __version__ = "0.4.0"

__all__ = [
    "__version__",
    "Block",
    "CodeBlock",
    "Emphasis",
    "EbookImportError",
    "EmptyLine",
    "FootnoteDefinition",
    "FootnoteRef",
    "Group",
    "HardBreak",
    "Heading",
    "ImageBlock",
    "ImageInline",
    "Inline",
    "InlineCode",
    "Link",
    "ListBlock",
    "ListItem",
    "Paragraph",
    "ParsedAsset",
    "ParsedBook",
    "ParsedChapter",
    "Poem",
    "Quote",
    "Stanza",
    "Strike",
    "Strong",
    "Subscript",
    "Superscript",
    "Table",
    "TableCell",
    "TableRow",
    "Text",
    "Verse",
    "main",
    "parse_book",
    "render_markdown",
]
