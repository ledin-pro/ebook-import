from __future__ import annotations

from pathlib import Path

from .epub import parse_epub
from .fb2 import parse_fb2
from .mobi import parse_mobi
from .models import ParsedBook
from .utils import detect_source_format


def parse_book(
    source: str | Path,
    *,
    image_mode: str = "import",
    mobi_backend: str = "auto",
) -> ParsedBook:
    """Parse an ebook without writing persistent output."""
    path = Path(source).expanduser().resolve()
    source_format = detect_source_format(path)
    if source_format == "epub":
        return parse_epub(path, image_mode)
    if source_format == "fb2":
        return parse_fb2(path, image_mode)
    return parse_mobi(path, source_format, image_mode, mobi_backend)
