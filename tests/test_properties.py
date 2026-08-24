from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings, strategies as st

from pro.ledin.ebook_import.utils import original_extension, slugify


@given(st.text())
@settings(max_examples=150, deadline=None)
def test_slugify_is_deterministic_and_path_safe(value: str) -> None:
    first = slugify(value)
    assert first == slugify(value)
    assert first
    assert first == first.lower()
    assert set(first) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")
    assert "/" not in first and "\\" not in first and ".." not in first


def test_original_extension_preserves_compound_fb2_suffix() -> None:
    assert original_extension(Path("Book.FB2.ZIP")) == ".fb2.zip"
    assert original_extension(Path("Book.FBZ")) == ".fbz"
    assert original_extension(Path("Book.AZW3")) == ".azw3"
