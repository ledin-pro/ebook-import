from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from pro.ledin.ebook_import import main
from pro.ledin.ebook_import.core import doctor

from .helpers import make_fb2


ROOT = Path(__file__).parents[1]


def schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_doctor_result_schema() -> None:
    jsonschema.validate(doctor(), schema("doctor-result.schema.json"))


def test_import_result_schema(tmp_path: Path, capsys) -> None:
    source = tmp_path / "book.fb2"
    make_fb2(source)
    assert main(["import", "--vault-root", str(tmp_path / "vault"), "--dry-run", "--input", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    jsonschema.validate(result, schema("import-result.schema.json"))


def test_error_schema(tmp_path: Path, capsys) -> None:
    source = tmp_path / "book.kfx"
    source.write_bytes(b"kfx")
    assert main(["import", "--vault-root", str(tmp_path / "vault"), "--input", str(source)]) == 3
    result = json.loads(capsys.readouterr().err)
    jsonschema.validate(result, schema("error.schema.json"))
