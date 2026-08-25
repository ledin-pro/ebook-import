from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from pro.ledin.ebook_import import main

from .helpers import make_epub, make_fb2


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pro.ledin.ebook_import", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_module_entrypoint_help_and_doctor() -> None:
    help_result = run_module("--help")
    assert help_result.returncode == 0
    assert "import" in help_result.stdout
    assert "doctor" in help_result.stdout
    assert "apply-image-text" not in help_result.stdout
    doctor_result = run_module("doctor", "--json")
    assert doctor_result.returncode == 0
    report = json.loads(doctor_result.stdout)
    assert "fb2" in report["supported_formats"]


def test_cli_error_is_json_and_has_stable_exit(tmp_path: Path) -> None:
    source = tmp_path / "book.kfx"
    source.write_bytes(b"kfx")
    result = run_module("import", "--vault-root", str(tmp_path / "vault"), "--input", str(source))
    assert result.returncode == 3
    error = json.loads(result.stderr)
    assert error["error"]["code"] == "unsupported_format"
    assert not result.stdout


def test_mixed_format_import_and_title_collision(tmp_path: Path) -> None:
    epub = tmp_path / "same.epub"
    fb2 = tmp_path / "same.fb2"
    vault = tmp_path / "vault"
    make_epub(epub, title="Same title", image=False)
    make_fb2(fb2)
    assert main(["import", "--vault-root", str(vault), "--input", str(epub), str(fb2)]) == 0
    manifests = sorted((vault / "05-sources/books").glob("*/manifest.json"))
    assert len(manifests) == 2
    assert {json.loads(path.read_text())["format"] for path in manifests} == {"epub", "fb2"}

    second_epub = tmp_path / "other.epub"
    make_epub(second_epub, title="Same title", image=False)
    with zipfile.ZipFile(second_epub, "a") as archive:
        archive.writestr("edition.txt", "second")
    assert main(["import", "--vault-root", str(vault), "--input", str(second_epub)]) == 0
    assert (vault / "05-sources/books/same-title-epub/manifest.json").is_file()


def test_removed_apply_image_text_command_is_rejected() -> None:
    result = run_module("apply-image-text")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_missing_input_has_stable_error(tmp_path: Path) -> None:
    result = run_module("import", "--vault-root", str(tmp_path / "vault"), "--input", str(tmp_path / "missing.epub"))
    assert result.returncode == 8
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
