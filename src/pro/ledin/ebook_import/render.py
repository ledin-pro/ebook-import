from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .models import ParsedBook
from .utils import IMAGE_PATTERN, IMPORTER_VERSION, original_extension, render_frontmatter, sha256, slugify, yaml_string


def read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def generated_output_complete(book_dir: Path, manifest: dict[str, Any]) -> bool:
    if not (book_dir / "book.md").is_file():
        return False
    original_file = manifest.get("original_file", "original/book.epub")
    if not (book_dir / original_file).is_file():
        return False
    cover_image = manifest.get("cover_image")
    if cover_image and not (book_dir / cover_image).is_file():
        return False
    for asset_path in manifest.get("assets", {}).values():
        if not (book_dir / asset_path).is_file():
            return False
    if manifest.get("image_mode", "import") == "skip" and (book_dir / "media").exists():
        return False
    for chapter in manifest.get("chapters", []):
        chapter_path = book_dir / chapter["file"]
        if not chapter_path.is_file():
            return False
        text = chapter_path.read_text(encoding="utf-8")
        for _, link in IMAGE_PATTERN.findall(text):
            if not (chapter_path.parent / link).is_file():
                return False
    return True


def remove_duplicate_copies(book_dir: Path, manifest: dict[str, Any]) -> int:
    """Remove older macOS-style copies left beside generated files."""
    expected: set[Path] = {book_dir / chapter["file"] for chapter in manifest.get("chapters", [])}
    expected_by_source = {
        chapter.get("source_href"): book_dir / chapter["file"]
        for chapter in manifest.get("chapters", [])
        if chapter.get("source_href")
    }
    for chapter_path in expected.copy():
        if chapter_path.is_file():
            text = chapter_path.read_text(encoding="utf-8")
            expected.update((chapter_path.parent / link).resolve() for _, link in IMAGE_PATTERN.findall(text))
    removed = 0
    for directory in (book_dir / "chapters", book_dir / "media"):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path in expected:
                continue
            match = re.fullmatch(r"(.+) ([2-9][0-9]*)", path.stem)
            if not match:
                continue
            canonical = path.with_name(f"{match.group(1)}{path.suffix}")
            source_duplicate = False
            if path.suffix.lower() == ".md":
                try:
                    source_match = re.search(r'^source_href:\s+"([^"]+)"$', path.read_text(encoding="utf-8"), re.MULTILINE)
                except OSError:
                    source_match = None
                if source_match:
                    mapped = expected_by_source.get(source_match.group(1))
                    if mapped:
                        canonical = mapped
                        source_duplicate = True
            if canonical not in expected or not canonical.is_file():
                continue
            try:
                if path.stat().st_mtime > canonical.stat().st_mtime:
                    continue
                if source_duplicate:
                    identical = True
                elif path.suffix.lower() == ".md":
                    identical = " ".join(path.read_text(encoding="utf-8").split()) == " ".join(canonical.read_text(encoding="utf-8").split())
                else:
                    identical = path.read_bytes() == canonical.read_bytes()
            except OSError:
                identical = False
            if identical:
                path.unlink()
                removed += 1
    return removed


def set_book_frontmatter(path: Path, values: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Book file has no YAML frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"Book file has unterminated YAML frontmatter: {path}")
    frontmatter = text[4:end]
    for key, value in values.items():
        rendered = f"{key}: {yaml_string(value)}"
        pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
        if pattern.search(frontmatter):
            frontmatter = pattern.sub(rendered, frontmatter)
        else:
            frontmatter += f"\n{rendered}"
    path.write_text("---\n" + frontmatter + "\n---\n" + text[end + len("\n---\n"):], encoding="utf-8")


def apply_image_text(book_dir: Path, mapping_path: Path) -> dict[str, Any]:
    manifest_path = book_dir / "manifest.json"
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise ValueError(f"Book manifest is missing or invalid: {manifest_path}")
    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping = mapping_data.get("image_text") if isinstance(mapping_data, dict) else None
    if not isinstance(mapping, dict):
        raise ValueError("OCR mapping must be an object with an image_text object")
    changes: dict[Path, str] = {}
    referenced_media: set[Path] = set()
    retained_media: set[Path] = set()
    retained_sources: set[str] = set()
    missing: set[str] = set()
    replaced = 0
    without_text = 0
    cover_path = (book_dir / manifest["cover_image"]).resolve() if manifest.get("cover_image") else None
    for source_id, asset_path in manifest.get("assets", {}).items():
        if cover_path and (book_dir / asset_path).resolve() == cover_path:
            retained_sources.add(source_id)
            retained_media.add(cover_path)
    for chapter in manifest.get("chapters", []):
        chapter_path = book_dir / chapter["file"]
        text = chapter_path.read_text(encoding="utf-8")
        for source_id, filename in zip(chapter.get("images", []), chapter.get("media_files", [])):
            media_path = (book_dir / "media" / filename).resolve()
            if cover_path and media_path == cover_path:
                retained_media.add(media_path)
                retained_sources.add(source_id)

        def replace_image(match: re.Match[str]) -> str:
            nonlocal replaced, without_text
            href = match.group(2)
            media_path = (chapter_path.parent / href).resolve()
            media_key = media_path.relative_to(book_dir.resolve()).as_posix()
            referenced_media.add(media_path)
            if media_key not in mapping:
                missing.add(media_key)
                return match.group(0)
            value = mapping[media_key]
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ValueError(f"OCR mapping value must be text or empty: {media_key}")
            value = value.strip()
            if value:
                replaced += 1
                return value
            without_text += 1
            return ""

        changes[chapter_path] = IMAGE_PATTERN.sub(replace_image, text)
    if missing:
        raise ValueError(f"OCR mapping is incomplete; missing: {', '.join(sorted(missing))}")
    for chapter_path, text in changes.items():
        chapter_path.write_text(text, encoding="utf-8")
    for media_path in referenced_media:
        if media_path not in retained_media and media_path.is_file():
            media_path.unlink()
    media_dir = book_dir / "media"
    if media_dir.is_dir() and not any(media_dir.iterdir()):
        media_dir.rmdir()
    for chapter in manifest.get("chapters", []):
        chapter["images"] = []
        chapter["media_files"] = []
    manifest["image_mode"] = "ocr"
    manifest["media"] = sorted(retained_sources)
    manifest["assets"] = {
        source_id: asset_path
        for source_id, asset_path in manifest.get("assets", {}).items()
        if source_id in retained_sources
    }
    manifest["ocr"] = {
        "status": "completed",
        "images_processed": replaced + without_text,
        "replaced": replaced,
        "without_text": without_text,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    set_book_frontmatter(book_dir / "book.md", {"image_mode": "ocr", "ocr_status": "completed"})
    return manifest


def resolve_book_dir(books_root: Path, parsed: ParsedBook, source: Path, source_hash: str) -> tuple[str, Path]:
    base_slug = slugify(parsed.metadata["title"])
    candidates = [books_root / base_slug, *sorted(books_root.glob(f"{base_slug}-*"))] if books_root.exists() else [books_root / base_slug]
    for candidate in candidates:
        manifest = read_manifest(candidate / "manifest.json")
        if not manifest:
            continue
        if manifest.get("sha256") == source_hash:
            return candidate.name, candidate
        if manifest.get("source_filename") == source.name and manifest.get("format", "epub") == parsed.format:
            return candidate.name, candidate
    if not (books_root / base_slug).exists():
        return base_slug, books_root / base_slug
    suffix = parsed.format
    candidate_slug = f"{base_slug}-{suffix}"
    index = 2
    while (books_root / candidate_slug).exists():
        candidate_slug = f"{base_slug}-{suffix}-{index}"
        index += 1
    return candidate_slug, books_root / candidate_slug


def render_book(parsed: ParsedBook, source: Path, books_root: Path, image_mode: str, dry_run: bool = False) -> dict[str, Any]:
    source_hash = sha256(source)
    slug, book_dir = resolve_book_dir(books_root, parsed, source, source_hash)
    existing = read_manifest(book_dir / "manifest.json")
    if (
        not dry_run
        and existing
        and existing.get("importer_version") == IMPORTER_VERSION
        and existing.get("sha256") == source_hash
        and existing.get("image_mode", "import") == image_mode
        and generated_output_complete(book_dir, existing)
    ):
        remove_duplicate_copies(book_dir, existing)
        return existing
    if dry_run:
        return {
            "slug": slug,
            "title": parsed.metadata["title"],
            "authors": parsed.metadata["authors"],
            "format": parsed.format,
            "sha256": source_hash,
            "chapters": len(parsed.chapters),
            "conversion_backend": (parsed.conversion or {}).get("backend", ""),
            "warnings": parsed.warnings,
        }

    books_root.mkdir(parents=True, exist_ok=True)
    source_date = date.fromtimestamp(source.stat().st_mtime).isoformat()
    original_file = f"original/book{original_extension(source)}"
    with tempfile.TemporaryDirectory(prefix=".ebook-import-", dir=books_root) as temporary:
        stage = Path(temporary)
        chapter_dir = stage / "chapters"
        media_dir = stage / "media"
        original_dir = stage / "original"
        chapter_dir.mkdir()
        original_dir.mkdir()
        if image_mode == "import" and parsed.assets:
            media_dir.mkdir()
            for asset in sorted(parsed.assets.values(), key=lambda item: item.filename):
                (media_dir / asset.filename).write_bytes(asset.data)
        shutil.copy2(source, stage / original_file)

        chapters: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for number, chapter in enumerate(parsed.chapters, start=1):
            base_name = slugify(chapter.title, fallback=f"section-{number:03d}")
            file_name = f"{number:03d}-{base_name}.md"
            collision = 2
            while file_name in used_names:
                file_name = f"{number:03d}-{base_name}-{collision}.md"
                collision += 1
            used_names.add(file_name)
            chapter_frontmatter = render_frontmatter(
                {
                    "type": "source",
                    "source": "ebook",
                    "format": parsed.format,
                    "book": parsed.metadata["title"],
                    "author": parsed.metadata["authors"],
                    "chapter": chapter.title,
                    "chapter_number": number,
                    "source_href": chapter.source_href,
                    "language": parsed.metadata["language"],
                }
            )
            chapter_body = f"# {chapter.title}\n"
            if chapter.markdown.strip():
                chapter_body += f"\n{chapter.markdown}"
            (chapter_dir / file_name).write_text(chapter_frontmatter + chapter_body, encoding="utf-8")
            chapters.append(
                {
                    "number": number,
                    "title": chapter.title,
                    "file": f"chapters/{file_name}",
                    "source_href": chapter.source_href,
                    "images": chapter.images,
                    "media_files": chapter.media_files,
                }
            )

        metadata = parsed.metadata
        manifest_data: dict[str, Any] = {
            "importer_version": IMPORTER_VERSION,
            "slug": slug,
            "format": parsed.format,
            "title": metadata["title"],
            "authors": metadata["authors"],
            "language": metadata["language"],
            "year": metadata["year"],
            "publisher": metadata["publisher"],
            "description": metadata["description"],
            "isbn": metadata["isbn"],
            "identifiers": metadata["identifiers"],
            "source_filename": source.name,
            "original_file": original_file,
            "sha256": source_hash,
            "imported": source_date,
            "image_mode": image_mode,
            "chapters": chapters,
            "media": sorted(parsed.assets),
            "assets": {source_id: f"media/{asset.filename}" for source_id, asset in sorted(parsed.assets.items())},
            "warnings": parsed.warnings,
        }
        for key in ("genres", "series", "series_number"):
            if metadata.get(key):
                manifest_data[key] = metadata[key]
        if parsed.cover_image:
            manifest_data["cover_image"] = parsed.cover_image
        if parsed.conversion:
            manifest_data["conversion"] = parsed.conversion

        book_values: dict[str, Any] = {
            "type": "book",
            "source": "ebook",
            "format": parsed.format,
            "title": metadata["title"],
            "author": metadata["authors"],
            "language": metadata["language"],
            "year": metadata["year"],
            "isbn": metadata["isbn"],
            "sha256": source_hash,
            "imported": source_date,
            "image_mode": image_mode,
        }
        if parsed.cover_image:
            book_values["cover_image"] = parsed.cover_image
        book_lines = [render_frontmatter(book_values), f"# {metadata['title']}", "", f"**Author:** {', '.join(metadata['authors'])}"]
        if metadata["publisher"]:
            book_lines.append(f"**Publisher:** {metadata['publisher']}")
        if metadata["description"]:
            book_lines.extend(["", metadata["description"]])
        book_lines.extend(["", "## Chapters", ""])
        book_lines.extend(f"{chapter['number']}. [{chapter['title']}]({chapter['file']})" for chapter in chapters)
        book_lines.append("")
        (stage / "book.md").write_text("\n".join(book_lines), encoding="utf-8")
        (stage / "manifest.json").write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        book_dir.mkdir(parents=True, exist_ok=True)
        for name in ("chapters", "media", "original"):
            target = book_dir / name
            if target.exists():
                shutil.rmtree(target)
            staged = stage / name
            if staged.exists():
                shutil.move(str(staged), target)
        for name in ("book.md", "manifest.json"):
            target = book_dir / name
            target.unlink(missing_ok=True)
            shutil.move(str(stage / name), target)
    return manifest_data


def build_index(books_root: Path) -> None:
    entries: list[dict[str, Any]] = []
    for manifest_path in sorted(books_root.glob("*/manifest.json")):
        manifest = read_manifest(manifest_path)
        if manifest:
            entries.append(manifest)
    lines = ["---", 'type: "index"', 'source: "ebook-import"', "---", "", "# Books", "", "| Title | Author | Language | Format | Chapters | Source |", "| --- | --- | --- | --- | ---: | --- |"]
    for entry in entries:
        author = ", ".join(entry.get("authors", []))
        title = entry.get("title", entry.get("slug", "book"))
        slug = entry.get("slug", slugify(title))
        lines.append(f"| [{title}]({slug}/book.md) | {author} | {entry.get('language', '')} | {entry.get('format', 'epub')} | {len(entry.get('chapters', []))} | `{entry.get('source_filename', '')}` |")
    lines.extend(["", "## Reading notes", "", "The imported Markdown preserves source order and text. Use chapter files for focused retrieval; each original ebook is kept under its book directory's `original/` folder.", ""])
    books_root.mkdir(parents=True, exist_ok=True)
    (books_root / "index.md").write_text("\n".join(lines), encoding="utf-8")
