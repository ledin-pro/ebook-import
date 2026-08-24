"""Deterministic EPUB import into an Obsidian-compatible Markdown corpus."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .core import main

try:
    __version__ = version("pro-ledin-ebook-import")
except PackageNotFoundError:
    __version__ = "0.2.0"

__all__ = ["__version__", "main"]
