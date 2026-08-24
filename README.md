# pro-ledin-ebook-import

[![skills.sh](https://skills.sh/b/ledin-pro/ebook-import)](https://skills.sh/ledin-pro/ebook-import)

Deterministic ebook-to-Markdown importing for Obsidian vaults and AI-agent
workflows. The importer preserves source order and text, copies each original
ebook into the generated book directory, extracts referenced media when chosen,
and records SHA-256 metadata for repeatable rebuilds.

- Input formats: EPUB, FB2, FB2.ZIP/FBZ, DRM-free MOBI, AZW, and AZW3
- Import name: `pro.ledin.ebook_import`
- Console script: `ebook-import`
- PyPI: `pro-ledin-ebook-import`
- Skill: [`skills/ebook-import/SKILL.md`](skills/ebook-import/SKILL.md)

## Install

```bash
pip install pro-ledin-ebook-import
```

EPUB and FB2 imports work after the Python package is installed. FB2 parsing
uses the small `defusedxml` dependency to reject XML entity and DTD attacks.

MOBI, AZW, and AZW3 require one separately installed converter. The importer
prefers `mobitool` and falls back to Calibre:

```bash
brew install libmobi                    # macOS, preferred
sudo apt install libmobi-tools          # Debian/Ubuntu, preferred when available
```

Calibre is available for macOS, Linux, and Windows from
https://calibre-ebook.com/download. The package invokes these tools as separate
processes and does not bundle or import their LGPL/GPL code.

Check the current machine:

```bash
ebook-import doctor --json
```

## Parser API

The package also exposes a filesystem-independent typed parsing API for other
renderers and document systems:

```python
from pro.ledin.ebook_import import Heading, Paragraph, parse_book

book = parse_book("/path/to/book.fb2")
for chapter in book.chapters:
    print(chapter.title, len(chapter.blocks))
    print(chapter.markdown)
```

`ParsedChapter.blocks` contains immutable headings, paragraphs, groups, quotes,
poems, tables, images, links, and footnotes. `chapter.markdown` is generated from
the same typed model for compatibility with the Obsidian corpus renderer.

## Import

Preview without writing to the vault:

```bash
ebook-import import \
  --vault-root "/path/to/vault" \
  --output-dir "05-sources/books" \
  --image-mode import \
  --dry-run \
  --input "/path/to/book.epub" "/path/to/book.fb2" "/path/to/book.mobi"
```

Run the import after reviewing the JSON result:

```bash
ebook-import import \
  --vault-root "/path/to/vault" \
  --output-dir "05-sources/books" \
  --image-mode import \
  --input "/path/to/book.epub" "/path/to/book.fb2" "/path/to/book.mobi"
```

Choose a MOBI backend explicitly when needed:

```bash
ebook-import import \
  --vault-root "/path/to/vault" \
  --mobi-backend mobitool \
  --input "/path/to/book.azw3"
```

`--mobi-backend` accepts `auto`, `mobitool`, or `calibre`. `auto` prefers
`mobitool`, then retries with Calibre for ordinary conversion failures. It does
not retry or bypass DRM/encryption failures.

## Image policy

Use `--image-mode import` to extract referenced images or `--image-mode skip`
to omit image files and Markdown image markers.

After an image import, an AI agent can replace chapter image links with a
complete recognized-text mapping:

```bash
ebook-import apply-image-text \
  --book-dir "/path/to/vault/05-sources/books/book-slug" \
  --mapping "/tmp/book-image-text.json"
```

```json
{
  "image_text": {
    "media/page-001.png": "Recognized text from the image",
    "media/page-002.png": ""
  }
}
```

`apply-image-text` validates completeness before mutation. An incomplete
mapping leaves chapters and media unchanged. A retained FB2 cover remains in
`media/` when the same image also appears in a chapter.

## Format behavior

### EPUB

EPUB spine order defines chapter order. OPF metadata, NCX chapter titles,
common XHTML formatting, links, and referenced images are converted using the
package's deterministic standard-library serializer.

### FB2

Each top-level content section becomes one chapter file. Nested sections remain
headings. The parser preserves common inline formatting, epigraphs, citations,
poem stanza/verse lines, localized notes bodies, links, tables, embedded binary
images, and cover metadata. Compressed `.fb2.zip` and `.fbz` inputs must contain
exactly one `.fb2` payload and pass archive safety limits.

### MOBI, AZW, and AZW3

The selected external converter creates a temporary EPUB, which is passed
through the native EPUB parser. The corpus keeps the original MOBI-family file,
hashes the original bytes, records converter/version provenance, and removes the
temporary EPUB.

DRM-protected books, KFX, AZW4 Print Replica, and PRC are unsupported. The tool
does not remove DRM and does not provide instructions for doing so.

## Output

```text
05-sources/books/
├── index.md
└── <book-slug>/
    ├── book.md
    ├── manifest.json
    ├── original/book.<source-extension>
    ├── chapters/*.md
    └── media/*
```

The manifest records input format, original path, source hash, image mode,
chapters, media, warnings, and MOBI converter provenance when applicable.
Repeated imports with the same source hash, importer version, and image mode are
no-ops. Changing image mode or importer output version rebuilds generated files.

Books with the same metadata title do not overwrite one another: later
collisions receive a deterministic format suffix.

## Docling integration

Install [`pro-ledin-docling-ebook`](https://github.com/ledin-pro/docling-ebook)
when a workflow needs a native `DoclingDocument` or Docling Markdown, JSON, and
HTML export:

```bash
pip install pro-ledin-docling-ebook
docling-ebook book.fb2 --to md --output-dir ./out
```

The integration is kept in a separate package so this parser and Obsidian
importer remain lightweight.

## Development

```bash
uv sync --extra dev
uv run --extra dev pytest -q -m "not external"
uv run --extra dev pytest \
  --cov=pro.ledin.ebook_import --cov-branch --cov-report=json
uv run python scripts/check_coverage.py coverage.json
uv build
```

Real MOBI integration requires both converters:

```bash
EBOOK_IMPORT_EXTERNAL_TESTS=1 \
  uv run --extra dev pytest -q tests/test_real_mobi_tools.py
```

CI tests Python 3.10-3.14, enforces at least 90% statement and 85% branch
coverage, runs hostile-input and property tests, builds both distributions, and
runs a dedicated real-converter integration job.

## License

MIT
