"""Unit tests for preprocessor module — Phase 3, tasks 3.3.6–3.3.11."""
from __future__ import annotations

import pytest

from ai_module.core.exceptions import InvalidInputError, UnsupportedFormatError
from ai_module.core.preprocessor import preprocess
from ai_module.core.settings import settings

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_preprocess_png_returns_image_type(png_bytes: bytes) -> None:
    result_bytes, input_type = preprocess(png_bytes, "img.png")

    assert input_type == "image"
    assert result_bytes[:8] == _PNG_MAGIC


def test_preprocess_jpeg_returns_image_type(jpeg_bytes: bytes) -> None:
    result_bytes, input_type = preprocess(jpeg_bytes, "img.jpg")

    assert input_type == "image"
    assert len(result_bytes) > 0


def test_preprocess_pdf_returns_pdf_type_and_png_bytes(pdf_bytes: bytes) -> None:
    result_bytes, input_type = preprocess(pdf_bytes, "doc.pdf")

    assert input_type == "pdf"
    assert result_bytes[:8] == _PNG_MAGIC


def test_preprocess_unsupported_format_raises_error() -> None:
    with pytest.raises(UnsupportedFormatError):
        preprocess(b"texto qualquer invalido", "arquivo.txt")


def test_preprocess_oversized_file_raises_error() -> None:
    limit = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    oversized = b"x" * (limit + 1)

    with pytest.raises(InvalidInputError):
        preprocess(oversized, "big.bin")


def test_preprocess_corrupted_file_raises_error(corrupted_bytes: bytes) -> None:
    with pytest.raises(InvalidInputError):
        preprocess(corrupted_bytes, "img.png")
