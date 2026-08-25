#!/usr/bin/env python3
"""Deterministic ebook to Markdown importer for agent-readable book sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .mobi import available_backends
from .parsing import parse_book
from .render import build_index, render_book
from .utils import EbookImportError


def import_book(
    source: Path,
    books_root: Path,
    image_mode: str = "import",
    dry_run: bool = False,
    mobi_backend: str = "auto",
) -> dict[str, Any]:
    parsed = parse_book(source, image_mode=image_mode, mobi_backend=mobi_backend)
    return render_book(parsed, source, books_root, image_mode, dry_run)


def doctor() -> dict[str, Any]:
    backends = available_backends()
    selected = ""
    if backends["mobitool"]["available"]:
        selected = "mobitool"
    elif backends["calibre"]["available"]:
        selected = "calibre"
    return {
        "supported_formats": ["epub", "fb2", "fb2.zip", "fbz", "mobi", "azw", "azw3"],
        "mobi_backends": backends,
        "auto_mobi_backend": selected,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    import_parser = subparsers.add_parser("import", help="Import one or more ebook files")
    import_parser.add_argument("--vault-root", type=Path, required=True)
    import_parser.add_argument("--input", type=Path, nargs="+", required=True)
    import_parser.add_argument("--output-dir", default="05-sources/books")
    import_parser.add_argument("--image-mode", choices=("import", "skip"), default="import")
    import_parser.add_argument("--mobi-backend", choices=("auto", "mobitool", "calibre"), default="auto")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (default output is JSON)")
    doctor_parser = subparsers.add_parser("doctor", help="Report optional MOBI converter availability")
    doctor_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (default output is JSON)")
    return parser.parse_args(argv)


def print_error(error: Exception) -> int:
    if isinstance(error, EbookImportError):
        code = error.code
        exit_code = error.exit_code
    else:
        code = "invalid_input"
        exit_code = 8
    print(json.dumps({"error": {"code": code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), ensure_ascii=False, indent=2))
            return 0
        books_root = (args.vault_root.expanduser() / args.output_dir).resolve()
        results: list[dict[str, Any]] = []
        for source_path in args.input:
            source = source_path.expanduser().resolve()
            if not source.is_file():
                raise EbookImportError(f"Input file does not exist: {source}")
            results.append(
                import_book(
                    source,
                    books_root,
                    image_mode=args.image_mode,
                    dry_run=args.dry_run,
                    mobi_backend=args.mobi_backend,
                )
            )
        if not args.dry_run:
            build_index(books_root)
        print(json.dumps({"books_root": str(books_root), "books": results, "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
        return 0
    except (EbookImportError, ValueError, OSError, json.JSONDecodeError) as error:
        return print_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
