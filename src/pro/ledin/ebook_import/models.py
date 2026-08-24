from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content import Block, render_markdown


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
    blocks: tuple[Block, ...]
    images: list[str] = field(default_factory=list)
    media_files: list[str] = field(default_factory=list)

    @property
    def markdown(self) -> str:
        return render_markdown(self.blocks)


@dataclass
class ParsedBook:
    format: str
    metadata: dict[str, Any]
    chapters: list[ParsedChapter]
    assets: dict[str, ParsedAsset] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    cover_image: str = ""
    conversion: dict[str, str] | None = None
