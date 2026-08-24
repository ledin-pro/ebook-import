from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedAsset:
    source_id: str
    filename: str
    media_type: str
    data: bytes


@dataclass
class ParsedChapter:
    title: str
    source_href: str
    markdown: str
    images: list[str] = field(default_factory=list)
    media_files: list[str] = field(default_factory=list)


@dataclass
class ParsedBook:
    format: str
    metadata: dict[str, Any]
    chapters: list[ParsedChapter]
    assets: dict[str, ParsedAsset] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    cover_image: str = ""
    conversion: dict[str, str] | None = None
