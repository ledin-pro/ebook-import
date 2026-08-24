from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pro.ledin.ebook_import import main

from .helpers import make_epub


pytestmark = pytest.mark.external


@pytest.mark.skipif(os.environ.get("EBOOK_IMPORT_EXTERNAL_TESTS") != "1", reason="external converter test")
def test_real_mobitool_and_calibre_backends(tmp_path: Path) -> None:
    mobitool = shutil.which("mobitool")
    calibre = shutil.which("ebook-convert")
    if not mobitool or not calibre:
        pytest.skip("mobitool and ebook-convert are both required")

    epub = tmp_path / "source.epub"
    mobi = tmp_path / "source.mobi"
    azw3 = tmp_path / "source.azw3"
    make_epub(epub, title="External Backend Test")
    subprocess.run([calibre, str(epub), str(mobi)], check=True, capture_output=True, text=True, timeout=300)
    subprocess.run([calibre, str(epub), str(azw3)], check=True, capture_output=True, text=True, timeout=300)

    cases = [
        (mobi, "mobitool", tmp_path / "mobitool-vault"),
        (mobi, "calibre", tmp_path / "calibre-vault"),
        (azw3, "auto", tmp_path / "auto-vault"),
    ]
    for source, backend, vault in cases:
        assert main(["import", "--vault-root", str(vault), "--mobi-backend", backend, "--input", str(source)]) == 0
        manifest_path = next((vault / "05-sources/books").glob("*/manifest.json"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["conversion"]["backend"] == ("mobitool" if backend == "auto" else backend)
        assert manifest["format"] == source.suffix[1:]
        assert (manifest_path.parent / manifest["original_file"]).read_bytes() == source.read_bytes()
        chapter = next((manifest_path.parent / "chapters").glob("*.md"))
        chapter.write_text(chapter.read_text(encoding="utf-8") + "\nUser note\n", encoding="utf-8")
        assert main(["import", "--vault-root", str(vault), "--mobi-backend", backend, "--input", str(source)]) == 0
        assert "User note" in chapter.read_text(encoding="utf-8")
