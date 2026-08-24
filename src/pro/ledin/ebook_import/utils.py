from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


IMPORTER_VERSION = "5"
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((\.\./media/[^)]+)\)")

CYRILLIC = str.maketrans(
    {
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E",
        "Ё": "Yo", "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K",
        "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R",
        "С": "S", "Т": "T", "У": "U", "Ф": "F", "Х": "Kh", "Ц": "Ts",
        "Ч": "Ch", "Ш": "Sh", "Щ": "Shch", "Ъ": "", "Ы": "Y", "Ь": "",
        "Э": "E", "Ю": "Yu", "Я": "Ya",
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
)


class EbookImportError(Exception):
    def __init__(self, message: str, *, code: str = "invalid_input", exit_code: int = 8):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def slugify(value: str, fallback: str = "book") -> str:
    transliterated = value.translate(CYRILLIC)
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or fallback


def yaml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def element_text(element: Any | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def render_frontmatter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(yaml_string(item) for item in value) + "]"
        elif value is None or value == "":
            rendered = "null"
        else:
            rendered = yaml_string(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def detect_source_format(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".fb2.zip") or name.endswith(".fbz"):
        return "fb2"
    suffix = path.suffix.lower()
    formats = {
        ".epub": "epub",
        ".fb2": "fb2",
        ".mobi": "mobi",
        ".azw": "azw",
        ".azw3": "azw3",
    }
    if suffix in formats:
        return formats[suffix]
    if suffix in {".kfx", ".azw4", ".prc"}:
        raise EbookImportError(
            f"Unsupported ebook format: {suffix}. Supported formats are EPUB, FB2, MOBI, AZW, and AZW3.",
            code="unsupported_format",
            exit_code=3,
        )
    raise EbookImportError(
        f"Unsupported ebook format: {path.name}", code="unsupported_format", exit_code=3
    )


def original_extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".fb2.zip"):
        return ".fb2.zip"
    return path.suffix.lower()
