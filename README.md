# pro-ledin-ebook-import

[![skills.sh](https://skills.sh/b/ledin-pro/ebook-import)](https://skills.sh/ledin-pro/ebook-import)

Deterministic EPUB-to-Markdown importing for Obsidian vaults and AI-agent
workflows. The importer preserves source order and text, copies each original
EPUB into the generated book directory, extracts referenced media when chosen,
and records SHA-256 metadata for repeatable rebuilds.

- Import name: `pro.ledin.ebook_import`
- Console script: `ebook-import`
- PyPI: `pro-ledin-ebook-import`
- Skill: [`skills/ebook-import/SKILL.md`](skills/ebook-import/SKILL.md)

## Install

```bash
pip install pro-ledin-ebook-import
```

The package uses only the Python standard library at runtime.

## CLI

```bash
ebook-import import \
  --vault-root "/path/to/vault" \
  --output-dir "05-sources/books" \
  --image-mode import \
  --input "/path/to/book-1.epub" "/path/to/book-2.epub"
```

Use `--image-mode skip` to omit image extraction, or run a second step after an
image import to replace image links with a complete agent-produced mapping:

```bash
ebook-import apply-image-text \
  --book-dir "/path/to/vault/05-sources/books/book-slug" \
  --mapping "/tmp/book-image-text.json"
```

The mapping shape is:

```json
{
  "image_text": {
    "media/page-001.png": "Recognized text from the image",
    "media/page-002.png": ""
  }
}
```

`apply-image-text` validates completeness before changing chapters or deleting
media. An incomplete mapping leaves the initial import intact.

## Output

Each book is written under the selected output directory:

```text
05-sources/books/
├── index.md
└── <book-slug>/
    ├── book.md
    ├── manifest.json
    ├── original/book.epub
    ├── chapters/*.md
    └── media/*
```

Repeated imports with the same source hash, importer version, and image mode
are no-ops. Changing image mode rebuilds generated output even when the source
hash is unchanged.

## Development

```bash
uv sync --extra dev
uv run --extra dev pytest
uv build
```

## License

MIT
