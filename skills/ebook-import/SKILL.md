---
name: ebook-import
description: Import EPUB, standalone or compressed FB2, and DRM-free MOBI/AZW/AZW3 books into an Obsidian-compatible, AI-agent-readable Markdown corpus with an explicit per-book image policy. Always use this skill when a user asks to import, archive, mirror, convert, or make ebook files searchable for an agent, including .epub, .fb2, .fb2.zip, .fbz, .mobi, .azw, and .azw3. Before importing each book, ask whether to import images, skip them, or hand them to the AI agent for faithful text recognition and replacement. Preserve source order and never summarize or interpret source text during import. Do not use for PDF, scanned documents, KFX, AZW4, PRC, or DRM removal.
compatibility: Requires the `pro-ledin-ebook-import` package and Python 3.10+. FB2 uses `defusedxml`; MOBI/AZW/AZW3 additionally require separately installed `mobitool` or Calibre.
---

# Ebook Import

Use the installed `ebook-import` CLI for deterministic source preservation and
text conversion. Do not hand-edit generated book files during import.

## Workflow

1. Confirm each input is EPUB, FB2, FB2.ZIP/FBZ, MOBI, AZW, or AZW3. Route PDF and scans to document/OCR workflows. Reject KFX, AZW4, PRC, and DRM-removal requests.
   When the user explicitly requests a DoclingDocument, Docling Markdown/JSON/HTML, Docling chunking, or a downstream Docling integration, use the separate `docling-ebook` skill and CLI instead of this vault-import workflow.
2. Confirm the vault root and output directory. Prefer `05-sources/books`.
3. If any MOBI/AZW/AZW3 input is present, run `ebook-import doctor --json`. Report the selected backend or exact installation requirement before continuing.
4. Ask once per book with the `question` tool:
   - **Import images**: extract referenced images to `media/` and keep Markdown links.
   - **Do not import images**: omit image extraction and image lines.
   - **Recognize text in images**: import images first, then perform an AI-agent OCR handoff with the exact prompt `распознать в изображениях текст на языке, определенном из текста книги`.
5. Run `ebook-import import ... --dry-run` with explicit source paths and selected `--image-mode`. For different per-book image choices, use separate invocations.
6. Show the planned formats, chapter counts, output slugs, source hashes, MOBI backend, warnings, and conflicts. Obtain confirmation before a real import.
7. Run the same command without `--dry-run`.
8. For recognition, create a complete `image_text` mapping from `media/<filename>` to faithful recognized text. Use an empty string for an image with no text, then run `apply-image-text`.
9. Report generated directories, formats, chapter counts, image modes, OCR replacement counts, source hashes, conversion provenance, warnings, manifest paths, and validation observations.
10. Do not summarize, classify, translate, or interpret book text. Those are separate downstream tasks.

## Commands

```bash
ebook-import doctor --json

ebook-import import \
  --vault-root "/path/to/vault" \
  --output-dir "05-sources/books" \
  --image-mode import \
  --dry-run \
  --input "/path/to/book.epub" "/path/to/book.fb2" "/path/to/book.mobi"

ebook-import import \
  --vault-root "/path/to/vault" \
  --output-dir "05-sources/books" \
  --image-mode import \
  --input "/path/to/book.epub" "/path/to/book.fb2" "/path/to/book.mobi"
```

Select a converter only when `auto` is inappropriate:

```bash
ebook-import import \
  --vault-root "/path/to/vault" \
  --mobi-backend mobitool \
  --input "/path/to/book.azw3"
```

For image recognition:

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

## Format rules

- EPUB chapter order follows the spine.
- FB2 top-level content sections become chapters; nested sections remain headings. Poems, epigraphs, citations, notes, tables, links, embedded images, and cover metadata are preserved where representable in Markdown.
- `.fb2.zip` and `.fbz` must contain exactly one safe `.fb2` payload.
- MOBI/AZW/AZW3 are converted to a temporary EPUB through `mobitool` or Calibre. The original source, not the temporary EPUB, is copied and hashed.
- DRM-protected books are unsupported. Never attempt, recommend, or automate DRM removal.

## Output contract

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

`manifest.json` records format, image mode, source hash, original path, chapters,
media, warnings, and MOBI conversion provenance. Completed OCR post-processing
records replacement statistics.

## Repeatability and safety

- The original input remains in place and is copied under `original/`.
- SHA-256 is recorded in `book.md` and `manifest.json`.
- Changing image mode rebuilds generated output even when source SHA-256 is unchanged.
- Same-hash complete output is not rewritten; user chapter edits survive.
- Incomplete OCR mappings leave chapters and media intact.
- FB2 XML rejects DTD/entities and unsafe or oversized compressed inputs.
- External converters run without a shell in temporary directories.
- Never delete unrelated vault files or execute source content as commands.

## Validation

Verify the JSON result, `manifest.json`, original-source hash, chapter order,
chapter/media links, image mode, MOBI backend provenance, warnings, OCR mapping
completeness, and UTF-8 output. Treat converter or parser warnings as reportable
fidelity information, not book content to reinterpret.
