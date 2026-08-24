from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pro.ledin.ebook_import import main
from pro.ledin.ebook_import import mobi
from pro.ledin.ebook_import.core import doctor

from .helpers import make_epub


def write_tool(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)


def success_tools(directory: Path, template: Path) -> None:
    quoted = repr(str(template))
    write_tool(
        directory / "mobitool",
        "import pathlib, shutil, sys\n"
        "if '-v' in sys.argv:\n    print('mobitool build test\\nlibmobi: 0.12')\n    raise SystemExit(0)\n"
        f"out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1]); out.mkdir(parents=True, exist_ok=True); shutil.copy2({quoted}, out / 'converted.epub')\n",
    )
    write_tool(
        directory / "ebook-convert",
        "import pathlib, shutil, sys\n"
        "if '--version' in sys.argv:\n    print('ebook-convert (calibre 9.0)')\n    raise SystemExit(0)\n"
        f"target = pathlib.Path(sys.argv[-1]); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2({quoted}, target)\n",
    )


def make_source(path: Path) -> None:
    path.write_bytes(b"synthetic drm-free mobi fixture")


def test_mobi_auto_prefers_mobitool_and_preserves_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools = tmp_path / "tools with spaces"
    tools.mkdir()
    template = tmp_path / "template.epub"
    make_epub(template, title="MOBI Test")
    success_tools(tools, template)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", tmp_path / "missing-calibre")
    source = tmp_path / "book.mobi"
    vault = tmp_path / "vault"
    make_source(source)

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    output = vault / "05-sources/books/mobi-test"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "mobi"
    assert manifest["conversion"]["backend"] == "mobitool"
    assert manifest["conversion"]["intermediate_format"] == "epub"
    assert manifest["original_file"] == "original/book.mobi"
    assert (output / "original/book.mobi").read_bytes() == source.read_bytes()
    assert not list(output.rglob("*.epub"))


@pytest.mark.parametrize("suffix", ["azw", "azw3"])
def test_calibre_backend_supports_azw_family(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    template = tmp_path / "template.epub"
    make_epub(template, title=f"Test {suffix}")
    success_tools(tools, template)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", tmp_path / "missing-calibre")
    source = tmp_path / f"book.{suffix}"
    make_source(source)
    vault = tmp_path / "vault"

    assert main(["import", "--vault-root", str(vault), "--mobi-backend", "calibre", "--input", str(source)]) == 0
    manifest = json.loads(next((vault / "05-sources/books").glob("*/manifest.json")).read_text(encoding="utf-8"))
    assert manifest["format"] == suffix
    assert manifest["conversion"]["backend"] == "calibre"


def test_auto_falls_back_to_calibre_on_mobitool_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    template = tmp_path / "template.epub"
    make_epub(template, title="Fallback Test")
    success_tools(tools, template)
    write_tool(
        tools / "mobitool",
        "import sys\nif '-v' in sys.argv:\n    print('mobitool 0.12')\n    raise SystemExit(0)\nprint('parse failed', file=sys.stderr)\nraise SystemExit(1)\n",
    )
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", tmp_path / "missing-calibre")
    source = tmp_path / "book.mobi"
    make_source(source)
    vault = tmp_path / "vault"

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 0
    manifest = json.loads(next((vault / "05-sources/books").glob("*/manifest.json")).read_text(encoding="utf-8"))
    assert manifest["conversion"]["backend"] == "calibre"


def test_auto_reports_last_error_when_both_converters_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, version_flag in (("mobitool", "-v"), ("ebook-convert", "--version")):
        write_tool(
            tools / name,
            f"import sys\nif '{version_flag}' in sys.argv:\n    print('{name} test')\n    raise SystemExit(0)\nprint('parse failed', file=sys.stderr)\nraise SystemExit(1)\n",
        )
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", tmp_path / "missing-calibre")
    source = tmp_path / "book.mobi"
    make_source(source)
    assert main(["import", "--vault-root", str(tmp_path / "vault"), "--input", str(source)]) == 6


def test_drm_error_does_not_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    template = tmp_path / "template.epub"
    make_epub(template)
    success_tools(tools, template)
    write_tool(
        tools / "mobitool",
        "import sys\nif '-v' in sys.argv:\n    print('mobitool 0.12')\n    raise SystemExit(0)\nprint('Book is encrypted', file=sys.stderr)\nraise SystemExit(1)\n",
    )
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", tmp_path / "missing-calibre")
    source = tmp_path / "book.mobi"
    make_source(source)
    vault = tmp_path / "vault"

    assert main(["import", "--vault-root", str(vault), "--input", str(source)]) == 7
    assert not vault.exists()


def test_missing_backends_and_doctor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(mobi, "MACOS_CALIBRE", tmp_path / "missing-calibre")
    source = tmp_path / "book.mobi"
    make_source(source)
    assert main(["import", "--vault-root", str(tmp_path / "vault"), "--input", str(source)]) == 5
    report = doctor()
    assert report["auto_mobi_backend"] == ""
    assert report["mobi_backends"]["mobitool"]["available"] is False
    assert report["mobi_backends"]["calibre"]["available"] is False


def test_unsupported_kfx_and_azw4_have_stable_exit(tmp_path: Path) -> None:
    for suffix in ("kfx", "azw4", "prc"):
        source = tmp_path / f"book.{suffix}"
        make_source(source)
        assert main(["import", "--vault-root", str(tmp_path / suffix), "--input", str(source)]) == 3
