from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from .epub import parse_epub
from .models import ParsedBook
from .utils import EbookImportError


CONVERTER_TIMEOUT = 300
MAX_CONVERTED_EPUB_BYTES = 500 * 1024 * 1024
DRM_MARKERS = ("encrypted", "drm", "locked book")
MACOS_CALIBRE = Path("/Applications/calibre.app/Contents/MacOS/ebook-convert")


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if name == "ebook-convert" and MACOS_CALIBRE.is_file():
        return str(MACOS_CALIBRE)
    return None


def tool_version(path: str, backend: str) -> str:
    args = [path, "-v"] if backend == "mobitool" else [path, "--version"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return output.splitlines()[0] if output else "unknown"


def available_backends() -> dict[str, dict[str, str | bool]]:
    result: dict[str, dict[str, str | bool]] = {}
    for backend, command in (("mobitool", "mobitool"), ("calibre", "ebook-convert")):
        path = find_tool(command)
        result[backend] = {
            "available": bool(path),
            "path": path or "",
            "version": tool_version(path, backend) if path else "",
        }
    return result


def missing_backend_error(backend: str = "auto") -> EbookImportError:
    requested = "mobitool or Calibre" if backend == "auto" else backend
    return EbookImportError(
        f"MOBI import requires {requested}. Install libmobi (`brew install libmobi` or your Linux package manager) "
        "or Calibre from https://calibre-ebook.com/download.",
        code="missing_dependency",
        exit_code=5,
    )


def run_converter(args: list[str]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as stdout, tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as stderr:
        try:
            completed = subprocess.run(
                args,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=CONVERTER_TIMEOUT,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise EbookImportError("MOBI conversion timed out", code="conversion_failed", exit_code=6) from error
        except OSError as error:
            raise EbookImportError(f"Could not start MOBI converter: {error}", code="conversion_failed", exit_code=6) from error
        stdout.seek(0, 2)
        stdout.seek(max(0, stdout.tell() - 2000))
        stdout_text = stdout.read()
        stderr.seek(0, 2)
        stderr.seek(max(0, stderr.tell() - 2000))
        stderr_text = stderr.read()
        result = subprocess.CompletedProcess(args, completed.returncode, stdout_text, stderr_text)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "converter failed").strip()
        lowered = message.lower()
        if any(marker in lowered for marker in DRM_MARKERS):
            raise EbookImportError(
                "DRM-protected ebooks are unsupported.", code="drm_unsupported", exit_code=7
            )
        raise EbookImportError(
            f"MOBI converter failed: {message[-2000:]}", code="conversion_failed", exit_code=6
        )
    return result


def convert_with_mobitool(source: Path, output_dir: Path, executable: str) -> Path:
    run_converter([executable, "-e", "-o", str(output_dir), str(source)])
    epubs = sorted(path for path in output_dir.rglob("*.epub") if path.is_file())
    if len(epubs) != 1:
        raise EbookImportError(
            f"mobitool produced {len(epubs)} EPUB files; expected exactly one",
            code="conversion_failed",
            exit_code=6,
        )
    epub = epubs[0]
    if epub.is_symlink() or not epub.resolve().is_relative_to(output_dir.resolve()):
        raise EbookImportError("mobitool produced an unsafe EPUB path", code="conversion_failed", exit_code=6)
    return epub


def convert_with_calibre(source: Path, output_dir: Path, executable: str) -> Path:
    target = output_dir / "converted.epub"
    run_converter([executable, str(source), str(target)])
    if not target.is_file():
        raise EbookImportError("Calibre did not produce an EPUB", code="conversion_failed", exit_code=6)
    return target


def parse_mobi(source: Path, source_format: str, image_mode: str = "import", backend: str = "auto") -> ParsedBook:
    tools = available_backends()
    order = [backend] if backend != "auto" else ["mobitool", "calibre"]
    attempted = False
    last_error: EbookImportError | None = None
    for candidate in order:
        tool = tools[candidate]
        if not tool["available"]:
            continue
        attempted = True
        with tempfile.TemporaryDirectory(prefix="ebook-import-mobi-") as temporary:
            output_dir = Path(temporary)
            try:
                if candidate == "mobitool":
                    epub = convert_with_mobitool(source, output_dir, str(tool["path"]))
                else:
                    epub = convert_with_calibre(source, output_dir, str(tool["path"]))
                if epub.stat().st_size > MAX_CONVERTED_EPUB_BYTES:
                    raise EbookImportError("Converted EPUB exceeds the safety limit", code="conversion_failed", exit_code=6)
                parsed = parse_epub(epub, image_mode)
                conversion = {
                    "backend": candidate,
                    "backend_version": str(tool["version"]),
                    "intermediate_format": "epub",
                }
                return replace(parsed, format=source_format, conversion=conversion)
            except EbookImportError as error:
                if error.code == "drm_unsupported" or backend != "auto":
                    raise
                last_error = error
    if not attempted:
        raise missing_backend_error(backend)
    if last_error:
        raise last_error
    raise missing_backend_error(backend)
