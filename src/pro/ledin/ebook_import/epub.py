from __future__ import annotations

import html
import mimetypes
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from defusedxml import ElementTree as ET

from .models import ParsedAsset, ParsedBook, ParsedChapter
from .utils import EbookImportError, element_text, local_name, slugify


CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


def normalize_href(value: str) -> str:
    path = unquote(value.split("#", 1)[0])
    return posixpath.normpath(path)


def first_metadata(metadata: Any, name: str) -> str:
    for child in metadata:
        if local_name(child.tag) == name:
            value = element_text(child)
            if value:
                return value
    return ""


def all_metadata(metadata: Any, name: str) -> list[str]:
    return [element_text(child) for child in metadata if local_name(child.tag) == name and element_text(child)]


def parse_epub_metadata(archive: zipfile.ZipFile) -> tuple[dict[str, Any], str, dict[str, dict[str, str]], list[str]]:
    try:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
    except KeyError as error:
        raise EbookImportError("EPUB has no META-INF/container.xml") from error
    rootfile = container.find(f".//{{{CONTAINER_NS}}}rootfile")
    if rootfile is None or not rootfile.attrib.get("full-path"):
        raise EbookImportError("EPUB has no rootfile in META-INF/container.xml")

    opf_path = rootfile.attrib["full-path"]
    try:
        opf = ET.fromstring(archive.read(opf_path))
    except KeyError as error:
        raise EbookImportError(f"EPUB rootfile is missing: {opf_path}") from error
    metadata_element = opf.find(f"{{{OPF_NS}}}metadata")
    if metadata_element is None:
        raise EbookImportError("EPUB has no OPF metadata")

    identifiers = all_metadata(metadata_element, "identifier")
    isbn = next(
        (value for value in identifiers if "isbn" in value.lower() or re.fullmatch(r"[0-9Xx-]{10,17}", value)),
        "",
    )
    metadata: dict[str, Any] = {
        "title": first_metadata(metadata_element, "title") or "Untitled book",
        "authors": all_metadata(metadata_element, "creator") or ["Unknown author"],
        "language": first_metadata(metadata_element, "language") or "und",
        "year": first_metadata(metadata_element, "date"),
        "publisher": first_metadata(metadata_element, "publisher"),
        "description": first_metadata(metadata_element, "description"),
        "identifiers": identifiers,
        "isbn": isbn,
    }

    manifest: dict[str, dict[str, str]] = {}
    for item in opf.findall(f"{{{OPF_NS}}}manifest/{{{OPF_NS}}}item"):
        if item.attrib.get("id"):
            manifest[item.attrib["id"]] = dict(item.attrib)

    spine = [
        ref.attrib["idref"]
        for ref in opf.findall(f"{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref")
        if ref.attrib.get("idref") in manifest
    ]
    if not spine:
        raise EbookImportError("EPUB has no readable spine items")
    return metadata, opf_path, manifest, spine


def parse_ncx_titles(archive: zipfile.ZipFile, opf_path: str, manifest: dict[str, dict[str, str]]) -> dict[str, str]:
    ncx_item = next((item for item in manifest.values() if item.get("media-type") == "application/x-dtbncx+xml"), None)
    if ncx_item is None:
        return {}
    opf_dir = posixpath.dirname(opf_path)
    ncx_path = posixpath.normpath(posixpath.join(opf_dir, ncx_item["href"]))
    try:
        root = ET.fromstring(archive.read(ncx_path))
    except (KeyError, ET.ParseError):
        return {}
    titles: dict[str, str] = {}
    for nav_point in root.findall(f".//{{{NCX_NS}}}navPoint"):
        label = nav_point.find(f"{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text")
        content = nav_point.find(f"{{{NCX_NS}}}content")
        if label is None or content is None or not content.attrib.get("src"):
            continue
        href = normalize_href(posixpath.join(posixpath.dirname(ncx_path), content.attrib["src"]))
        titles.setdefault(href, element_text(label))
    return titles


def css_heading_level(tag: str, classes: set[str]) -> int | None:
    for class_name in classes:
        match = re.fullmatch(r"title([1-6]?)", class_name)
        if match:
            return int(match.group(1) or "1")
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return int(tag[1])
    return None


class MarkdownParser(HTMLParser):
    """Small XHTML-to-Markdown serializer tuned for common ebook XHTML."""

    BLOCK_TAGS = {"address", "article", "aside", "blockquote", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ol", "p", "pre", "section", "table", "tr", "ul"}
    SKIP_TAGS = {"head", "style", "script", "title", "meta", "link"}

    def __init__(
        self,
        source_href: str,
        archive: zipfile.ZipFile,
        opf_dir: str,
        image_mode: str,
        assets: dict[str, ParsedAsset],
        image_names: dict[str, str],
    ):
        super().__init__(convert_charrefs=True)
        self.source_href = source_href
        self.archive = archive
        self.opf_dir = opf_dir
        self.image_mode = image_mode
        self.assets = assets
        self.image_names = image_names
        self.lines: list[str] = []
        self.current: list[str] = []
        self.stack: list[tuple[str, str, bool]] = []
        self.skip_depth = 0
        self.image_files: list[str] = []
        self.image_outputs: list[str] = []
        self.link_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs = dict(attrs_list)
        classes = set((attrs.get("class") or "").split())
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            self.stack.append((tag, "", True))
            return
        if self.skip_depth:
            self.stack.append((tag, "", True))
            return
        level = css_heading_level(tag, classes)
        block = tag in self.BLOCK_TAGS or level is not None or tag == "br"
        if block:
            self.flush()
        prefix = ""
        if level is not None:
            prefix = f"{'#' * level} "
        elif tag == "li":
            prefix = "- "
        elif tag == "blockquote" or "cite" in classes or "text-author" in classes:
            prefix = "> "
        if prefix:
            self.current.append(prefix)
        if tag in {"strong", "b"}:
            self.current.append("**")
        elif tag in {"em", "i"}:
            self.current.append("*")
        elif tag in {"code", "kbd", "samp"}:
            self.current.append("`")
        elif tag == "a":
            self.link_stack.append(attrs.get("href") or "")
            self.current.append("[")
        elif tag == "img":
            self.add_image(attrs.get("src") or "", attrs.get("alt") or "")
        elif tag == "br":
            self.current.append("  ")
            self.flush()
        self.stack.append((tag, prefix, False))

    def handle_startendtag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs_list)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.stack:
            return
        stored_tag, _, skipped = self.stack.pop()
        if skipped:
            if stored_tag in self.SKIP_TAGS:
                self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in {"strong", "b"}:
            self.close_inline("**")
        elif tag in {"em", "i"}:
            self.close_inline("*")
        elif tag in {"code", "kbd", "samp"}:
            self.close_inline("`")
        elif tag == "a":
            href = self.link_stack.pop() if self.link_stack else ""
            self.current.append(f"]({href})" if href else "]")
        if tag in self.BLOCK_TAGS or css_heading_level(tag, set()) is not None:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth or not data:
            return
        normalized = re.sub(r"\s+", " ", html.unescape(data))
        if normalized.strip():
            self.current.append(normalized)
        elif normalized and self.current and not self.current[-1].endswith(" "):
            self.current.append(" ")

    def add_image(self, src: str, alt: str) -> None:
        if not src or self.image_mode == "skip":
            return
        source_path = normalize_href(posixpath.join(posixpath.dirname(self.source_href), src))
        if source_path not in self.image_names:
            original_name = Path(source_path).name or "image"
            stem = slugify(Path(original_name).stem, fallback="image")
            suffix = Path(original_name).suffix.lower() or mimetypes.guess_extension(mimetypes.guess_type(original_name)[0] or "") or ".bin"
            candidate = f"{stem}{suffix}"
            index = 2
            while candidate in self.image_names.values():
                candidate = f"{stem}-{index}{suffix}"
                index += 1
            archive_path = source_path if source_path.startswith(self.opf_dir + "/") else posixpath.join(self.opf_dir, source_path)
            try:
                data = self.archive.read(archive_path)
            except KeyError:
                return
            media_type = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
            self.image_names[source_path] = candidate
            self.assets[source_path] = ParsedAsset(source_path, candidate, media_type, data)
        self.image_files.append(source_path)
        self.image_outputs.append(self.image_names[source_path])
        self.current.append(f"![{alt}](../media/{self.image_names[source_path]})")

    def close_inline(self, marker: str) -> None:
        had_space = False
        if self.current and self.current[-1].endswith(" "):
            had_space = True
            self.current[-1] = self.current[-1].rstrip()
        self.current.append(marker)
        if had_space:
            self.current.append(" ")

    def flush(self) -> None:
        text = "".join(self.current).strip()
        self.current = []
        if re.fullmatch(r"(?:#{1,6}|>|-)\s*", text):
            return
        if not text:
            if self.lines and self.lines[-1] != "":
                self.lines.append("")
            return
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" +([,.;:!?])", r"\1", text)
        self.lines.append(text)

    def markdown(self) -> str:
        self.flush()
        output: list[str] = []
        previous_blank = False
        for line in self.lines:
            line = line.rstrip()
            if not line:
                if not previous_blank:
                    output.append("")
                previous_blank = True
                continue
            output.append(line)
            previous_blank = False
        return "\n".join(output).strip() + "\n"


def chapter_title(markdown: str, nav_title: str, source_href: str) -> str:
    if nav_title:
        return nav_title
    basename = Path(source_href).name.lower()
    special_titles = {
        "cover.xhtml": "Обложка",
        "ch1.xhtml": "Титульный лист",
        "ch1-1.xhtml": "Выходные данные",
        "ch2.xhtml": "Примечания",
    }
    if basename in special_titles:
        return special_titles[basename]
    for line in markdown.splitlines():
        match = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if match:
            return match.group(1).strip()
    return Path(source_href).stem.replace("-", " ").title()


def remove_duplicate_leading_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    if lines and re.sub(r"^#+\s+", "", lines[0]).strip() == title.strip():
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip() + "\n"


def parse_epub(source: Path, image_mode: str = "import") -> ParsedBook:
    assets: dict[str, ParsedAsset] = {}
    image_names: dict[str, str] = {}
    try:
        archive_context = zipfile.ZipFile(source)
    except zipfile.BadZipFile as error:
        raise EbookImportError(f"Invalid EPUB archive: {source}") from error
    with archive_context as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise EbookImportError(f"EPUB has a corrupt archive member: {corrupt}")
        metadata, opf_path, manifest, spine = parse_epub_metadata(archive)
        opf_dir = posixpath.dirname(opf_path)
        nav_titles = parse_ncx_titles(archive, opf_path, manifest)
        chapters: list[ParsedChapter] = []
        for item_id in spine:
            item = manifest[item_id]
            href = normalize_href(posixpath.join(opf_dir, item["href"]))
            archive_path = href if href.startswith(opf_dir + "/") else posixpath.join(opf_dir, href)
            try:
                xhtml = archive.read(archive_path)
            except KeyError as error:
                raise EbookImportError(f"Spine item is missing from archive: {href}") from error
            parser = MarkdownParser(href, archive, opf_dir, image_mode, assets, image_names)
            parser.feed(xhtml.decode("utf-8", "replace"))
            content = parser.markdown()
            title = chapter_title(content, nav_titles.get(href, ""), href)
            content = remove_duplicate_leading_heading(content, title)
            chapters.append(ParsedChapter(title, href, content, parser.image_files, parser.image_outputs))
    return ParsedBook("epub", metadata, chapters, assets)
