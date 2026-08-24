from __future__ import annotations

import base64
import binascii
import html
import mimetypes
import re
import zipfile
import xml.etree.ElementTree as StdET
from pathlib import Path, PurePosixPath
from typing import Any

from defusedxml import ElementTree as ET

from .models import ParsedAsset, ParsedBook, ParsedChapter
from .utils import EbookImportError, element_text, local_name, slugify


XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
NOTE_BODY_NAMES = {"notes", "footnotes", "comments", "примечания", "комментарии"}
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1000
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_ASSET_BYTES = 50 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 200 * 1024 * 1024
MAX_ELEMENTS = 1_000_000
MAX_DEPTH = 256


def child(element: Any, name: str) -> Any | None:
    return next((item for item in element if local_name(item.tag) == name), None)


def children(element: Any, name: str) -> list[Any]:
    return [item for item in element if local_name(item.tag) == name]


def attr_by_name(element: Any, name: str) -> str:
    for key, value in element.attrib.items():
        if local_name(key) == name:
            return value
    return ""


def read_fb2_bytes(source: Path) -> bytes:
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise EbookImportError(f"FB2 source exceeds {MAX_SOURCE_BYTES} bytes", code="unsafe_input", exit_code=4)
    name = source.name.lower()
    if not (name.endswith(".fb2.zip") or name.endswith(".fbz")):
        return source.read_bytes()
    try:
        archive_context = zipfile.ZipFile(source)
    except zipfile.BadZipFile as error:
        raise EbookImportError(f"Invalid compressed FB2 archive: {source}", code="unsafe_input", exit_code=4) from error
    with archive_context as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise EbookImportError("Compressed FB2 has too many archive members", code="unsafe_input", exit_code=4)
        total_size = 0
        fb2_infos: list[zipfile.ZipInfo] = []
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise EbookImportError(f"Unsafe archive member path: {info.filename}", code="unsafe_input", exit_code=4)
            if info.flag_bits & 0x1:
                raise EbookImportError("Encrypted FB2 archives are unsupported", code="unsafe_input", exit_code=4)
            total_size += info.file_size
            if total_size > MAX_ARCHIVE_BYTES:
                raise EbookImportError("Compressed FB2 expands beyond the safety limit", code="unsafe_input", exit_code=4)
            if info.file_size and info.compress_size == 0:
                raise EbookImportError("Compressed FB2 has an invalid compression ratio", code="unsafe_input", exit_code=4)
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise EbookImportError("Compressed FB2 exceeds the compression-ratio limit", code="unsafe_input", exit_code=4)
            if not info.is_dir() and info.filename.lower().endswith(".fb2"):
                fb2_infos.append(info)
        if len(fb2_infos) != 1:
            raise EbookImportError("Compressed FB2 must contain exactly one .fb2 file", code="unsafe_input", exit_code=4)
        return archive.read(fb2_infos[0])


def validate_tree(root: Any) -> None:
    count = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > MAX_ELEMENTS:
            raise EbookImportError("FB2 exceeds the element-count safety limit", code="unsafe_input", exit_code=4)
        if depth > MAX_DEPTH:
            raise EbookImportError("FB2 exceeds the nesting-depth safety limit", code="unsafe_input", exit_code=4)
        stack.extend((item, depth + 1) for item in element)


def author_name(author: Any) -> str:
    parts = [
        element_text(child(author, "first-name")),
        element_text(child(author, "middle-name")),
        element_text(child(author, "last-name")),
    ]
    full = " ".join(part for part in parts if part).strip()
    return full or element_text(child(author, "nickname"))


def parse_metadata(root: Any) -> tuple[dict[str, Any], str]:
    description = child(root, "description")
    title_info = child(description, "title-info") if description is not None else None
    document_info = child(description, "document-info") if description is not None else None
    publish_info = child(description, "publish-info") if description is not None else None
    if title_info is None:
        raise EbookImportError("FB2 has no description/title-info")
    authors = [author_name(item) for item in children(title_info, "author")]
    authors = [item for item in authors if item] or ["Unknown author"]
    identifiers: list[str] = []
    document_id = element_text(child(document_info, "id")) if document_info is not None else ""
    if document_id:
        identifiers.append(document_id)
    isbn = element_text(child(publish_info, "isbn")) if publish_info is not None else ""
    if isbn:
        identifiers.append(isbn)
    sequence = child(title_info, "sequence")
    coverpage = child(title_info, "coverpage")
    cover_image = ""
    if coverpage is not None:
        image = child(coverpage, "image")
        if image is not None:
            cover_image = (image.attrib.get(XLINK_HREF) or attr_by_name(image, "href")).lstrip("#")
    metadata: dict[str, Any] = {
        "title": element_text(child(title_info, "book-title")) or "Untitled book",
        "authors": authors,
        "language": element_text(child(title_info, "lang")) or "und",
        "year": element_text(child(title_info, "date")),
        "publisher": element_text(child(publish_info, "publisher")) if publish_info is not None else "",
        "description": element_text(child(title_info, "annotation")),
        "identifiers": identifiers,
        "isbn": isbn,
        "genres": [element_text(item) for item in children(title_info, "genre") if element_text(item)],
        "series": sequence.attrib.get("name", "") if sequence is not None else "",
        "series_number": sequence.attrib.get("number", "") if sequence is not None else "",
    }
    return metadata, cover_image


class Fb2Renderer:
    def __init__(self, root: Any, image_mode: str):
        self.root = root
        self.image_mode = image_mode
        self.assets: dict[str, ParsedAsset] = {}
        self.image_names: dict[str, str] = {}
        self.total_asset_bytes = 0
        self.warnings: list[str] = []
        self.note_labels: dict[str, str] = {}
        self.used_note_labels: set[str] = set()
        self.binaries = {
            item.attrib.get("id", ""): item
            for item in root
            if local_name(item.tag) == "binary" and item.attrib.get("id")
        }
        self.notes: dict[str, Any] = {}
        for body in children(root, "body"):
            if body.attrib.get("name", "").strip().lower() in NOTE_BODY_NAMES:
                for section in body.iter():
                    if local_name(section.tag) == "section" and section.attrib.get("id"):
                        self.notes[section.attrib["id"]] = section

    @staticmethod
    def text(value: str | None) -> str:
        return re.sub(r"\s+", " ", html.unescape(value or ""))

    def binary_asset(self, binary_id: str) -> ParsedAsset | None:
        if self.image_mode == "skip":
            return None
        if binary_id in self.assets:
            return self.assets[binary_id]
        element = self.binaries.get(binary_id)
        if element is None:
            self.warnings.append(f"Missing FB2 binary: {binary_id}")
            return None
        encoded = re.sub(r"\s+", "", element.text or "")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise EbookImportError(f"Invalid base64 data for FB2 binary: {binary_id}", code="unsafe_input", exit_code=4) from error
        if len(data) > MAX_ASSET_BYTES or self.total_asset_bytes + len(data) > MAX_TOTAL_ASSET_BYTES:
            raise EbookImportError(f"FB2 binary exceeds the asset safety limit: {binary_id}", code="unsafe_input", exit_code=4)
        media_type = element.attrib.get("content-type", "application/octet-stream").lower()
        suffix = mimetypes.guess_extension(media_type) or Path(binary_id).suffix.lower() or ".bin"
        stem = slugify(Path(binary_id).stem, fallback="image")
        filename = f"{stem}{suffix}"
        index = 2
        while filename in self.image_names.values():
            filename = f"{stem}-{index}{suffix}"
            index += 1
        asset = ParsedAsset(binary_id, filename, media_type, data)
        self.assets[binary_id] = asset
        self.image_names[binary_id] = filename
        self.total_asset_bytes += len(data)
        return asset

    def image_markdown(self, element: Any, alt: str = "") -> tuple[str, str, str]:
        binary_id = (element.attrib.get(XLINK_HREF) or attr_by_name(element, "href")).lstrip("#")
        if not binary_id or self.image_mode == "skip":
            return "", "", ""
        asset = self.binary_asset(binary_id)
        if asset is None:
            return "", "", ""
        label = alt or element.attrib.get("title", "")
        return f"![{label}](../media/{asset.filename})", binary_id, asset.filename

    def note_label(self, note_id: str) -> str:
        if note_id in self.note_labels:
            return self.note_labels[note_id]
        base = slugify(note_id, fallback=f"note-{len(self.note_labels) + 1}")
        label = base
        index = 2
        while label in self.used_note_labels:
            label = f"{base}-{index}"
            index += 1
        self.note_labels[note_id] = label
        self.used_note_labels.add(label)
        return label

    def render_inline(self, element: Any, note_ids: list[str], images: list[str], media_files: list[str]) -> str:
        parts: list[str] = [self.text(element.text)]
        for item in element:
            tag = local_name(item.tag)
            content = self.render_inline(item, note_ids, images, media_files)
            if tag == "emphasis":
                rendered = f"*{content.strip()}*"
            elif tag == "strong":
                rendered = f"**{content.strip()}**"
            elif tag == "strikethrough":
                rendered = f"~~{content.strip()}~~"
            elif tag == "code":
                rendered = f"`{content.strip()}`"
            elif tag == "sub":
                rendered = f"<sub>{content.strip()}</sub>"
            elif tag == "sup":
                rendered = f"<sup>{content.strip()}</sup>"
            elif tag == "a":
                href = item.attrib.get(XLINK_HREF) or attr_by_name(item, "href")
                link_type = item.attrib.get("type", "").lower()
                target = href.lstrip("#")
                if link_type == "note" or target in self.notes:
                    if target and target not in note_ids:
                        note_ids.append(target)
                    label = self.note_label(target)
                    rendered = f"[^{label}]"
                else:
                    rendered = f"[{content.strip()}]({href})" if href else content
            elif tag == "image":
                rendered, source_id, filename = self.image_markdown(item)
                if source_id:
                    images.append(source_id)
                    media_files.append(filename)
            else:
                rendered = content
            parts.append(rendered)
            parts.append(self.text(item.tail))
        return "".join(parts)

    @staticmethod
    def quote(text: str) -> str:
        return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())

    def render_table(self, element: Any, note_ids: list[str], images: list[str], media_files: list[str]) -> str:
        rows: list[list[str]] = []
        complex_table = False
        for row in [item for item in element if local_name(item.tag) == "tr"]:
            cells: list[str] = []
            for cell in row:
                if local_name(cell.tag) not in {"td", "th"}:
                    continue
                if cell.attrib.get("rowspan") or cell.attrib.get("colspan"):
                    complex_table = True
                cells.append(self.render_inline(cell, note_ids, images, media_files).strip())
            rows.append(cells)
        width = max((len(row) for row in rows), default=0)
        if not rows or not width:
            return ""
        if complex_table or any(len(row) != width for row in rows):
            html_rows = ["<table>"]
            for row in rows:
                html_rows.append("  <tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>")
            html_rows.append("</table>")
            return "\n".join(html_rows)
        lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines)

    def render_blocks(
        self,
        element: Any,
        heading_level: int,
        note_ids: list[str],
        images: list[str],
        media_files: list[str],
        *,
        include_section_title: bool = True,
    ) -> str:
        blocks: list[str] = []
        for item in element:
            tag = local_name(item.tag)
            if tag == "title":
                if include_section_title:
                    title = element_text(item)
                    if title:
                        blocks.append(f"{'#' * min(heading_level, 6)} {title}")
            elif tag in {"p", "subtitle", "text-author", "annotation"}:
                text = self.render_inline(item, note_ids, images, media_files).strip()
                if not text:
                    continue
                if tag == "subtitle":
                    blocks.append(f"{'#' * min(heading_level, 6)} {text}")
                elif tag == "text-author":
                    blocks.append(self.quote(text))
                else:
                    blocks.append(text)
            elif tag == "empty-line":
                blocks.append("")
            elif tag == "section":
                blocks.append(self.render_blocks(item, heading_level + 1, note_ids, images, media_files))
            elif tag in {"epigraph", "cite"}:
                content = self.render_blocks(item, heading_level, note_ids, images, media_files)
                if content:
                    blocks.append(self.quote(content))
            elif tag == "poem":
                poem: list[str] = []
                poem_title = child(item, "title")
                if poem_title is not None and element_text(poem_title):
                    poem.append(f"{'#' * min(heading_level, 6)} {element_text(poem_title)}")
                for part in item:
                    part_tag = local_name(part.tag)
                    if part_tag == "stanza":
                        verses = [self.render_inline(v, note_ids, images, media_files).strip() for v in part if local_name(v.tag) == "v"]
                        poem.append("  \n".join(verse for verse in verses if verse))
                    elif part_tag == "text-author":
                        poem.append(self.quote(element_text(part)))
                blocks.append("\n\n".join(item for item in poem if item))
            elif tag == "table":
                table = self.render_table(item, note_ids, images, media_files)
                if table:
                    blocks.append(table)
            elif tag == "image":
                rendered, source_id, filename = self.image_markdown(item)
                if rendered:
                    images.append(source_id)
                    media_files.append(filename)
                    blocks.append(rendered)
            elif tag not in {"binary"}:
                nested = self.render_blocks(item, heading_level, note_ids, images, media_files)
                if nested:
                    blocks.append(nested)
        return "\n\n".join(block for block in blocks if block is not None).strip()

    def render_note(self, note_id: str) -> str:
        note = self.notes.get(note_id)
        if note is None:
            self.warnings.append(f"Missing FB2 note target: {note_id}")
            return "Missing note."
        return self.render_blocks(note, 2, [], [], [], include_section_title=False).strip()

    def render_chapter(self, section: Any, index: int) -> ParsedChapter:
        section_id = section.attrib.get("id", "")
        title_element = child(section, "title")
        title = element_text(title_element) or f"Section {index}"
        note_ids: list[str] = []
        self.note_labels = {}
        self.used_note_labels = set()
        images: list[str] = []
        media_files: list[str] = []
        markdown = self.render_blocks(section, 2, note_ids, images, media_files, include_section_title=False)
        if note_ids:
            definitions: list[str] = []
            for note_id in note_ids:
                label = self.note_label(note_id)
                content = self.render_note(note_id)
                lines = content.splitlines() or [""]
                definitions.append(f"[^{label}]: {lines[0]}" + "".join(f"\n    {line}" for line in lines[1:]))
            markdown = markdown.rstrip() + "\n\n" + "\n\n".join(definitions)
        source_href = f"fb2:#{section_id}" if section_id else f"fb2:section-{index}"
        return ParsedChapter(title, source_href, markdown.strip() + "\n", images, media_files)


def parse_fb2(source: Path, image_mode: str = "import") -> ParsedBook:
    data = read_fb2_bytes(source)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise EbookImportError(f"Invalid FB2 XML: {error}") from error
    if local_name(root.tag) != "FictionBook":
        raise EbookImportError("Input XML is not a FictionBook document")
    validate_tree(root)
    metadata, cover_id = parse_metadata(root)
    renderer = Fb2Renderer(root, image_mode)
    chapters: list[ParsedChapter] = []
    main_bodies = [body for body in children(root, "body") if body.attrib.get("name", "").strip().lower() not in NOTE_BODY_NAMES]
    chapter_index = 1
    for body in main_bodies:
        sections = children(body, "section")
        if not sections:
            synthetic = StdET.Element("section", {"id": f"body-{chapter_index}"})
            title = StdET.SubElement(synthetic, "title")
            paragraph = StdET.SubElement(title, "p")
            paragraph.text = body.attrib.get("name") or metadata["title"]
            for item in list(body):
                synthetic.append(item)
            sections = [synthetic]
        for section in sections:
            chapters.append(renderer.render_chapter(section, chapter_index))
            chapter_index += 1
    if not chapters:
        raise EbookImportError("FB2 has no readable content bodies")
    cover_image = ""
    if cover_id and image_mode == "import":
        cover = renderer.binary_asset(cover_id)
        if cover:
            cover_image = f"media/{cover.filename}"
    return ParsedBook("fb2", metadata, chapters, renderer.assets, sorted(set(renderer.warnings)), cover_image)
