"""Unit tests for preprocessor module — Phase 3, tasks 3.3.6–3.3.11."""

from __future__ import annotations

from io import BytesIO

import fitz
import pytest  # type: ignore
from PIL import Image

from ai_module.core.exceptions import InvalidInputError, UnsupportedFormatError
from ai_module.core.preprocessor import (
    PreprocessResult,
    _normalize_image,
    _pdf_to_image,
    preprocess,
)
from ai_module.core.settings import settings

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png(width: int, height: int) -> bytes:
    """Create a minimal solid-colour PNG with the given dimensions."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# preprocess() — return type and basic assertions
# ---------------------------------------------------------------------------


def test_preprocess_png_returns_image_type(png_bytes: bytes) -> None:
    result = preprocess(png_bytes)

    assert isinstance(result, PreprocessResult)
    assert result.input_type == "image"
    assert result.image_bytes[:8] == _PNG_MAGIC


def test_preprocess_jpeg_returns_image_type(jpeg_bytes: bytes) -> None:
    result = preprocess(jpeg_bytes)

    assert isinstance(result, PreprocessResult)
    assert result.input_type == "image"
    assert len(result.image_bytes) > 0


def test_preprocess_pdf_returns_pdf_type_and_png_bytes(pdf_bytes: bytes) -> None:
    result = preprocess(pdf_bytes)

    assert isinstance(result, PreprocessResult)
    assert result.input_type == "pdf"
    assert result.image_bytes[:8] == _PNG_MAGIC


def test_preprocess_unsupported_format_raises_error() -> None:
    with pytest.raises(UnsupportedFormatError):
        preprocess(b"texto qualquer invalido")


def test_preprocess_oversized_file_raises_error() -> None:
    limit = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    oversized = b"x" * (limit + 1)

    with pytest.raises(InvalidInputError):
        preprocess(oversized)


def test_preprocess_corrupted_file_raises_error(corrupted_bytes: bytes) -> None:
    with pytest.raises(InvalidInputError):
        preprocess(corrupted_bytes)


# ---------------------------------------------------------------------------
# _normalize_image() — downsampling flag
# ---------------------------------------------------------------------------


def test_normalize_image_small_image_no_downsampling() -> None:
    """Images within the threshold must not be downsampled (flag=False)."""
    png = _make_png(100, 100)
    _, downsampled = _normalize_image(png, max_side=2048)

    assert downsampled is False


def test_normalize_image_large_image_downsampled() -> None:
    """Images exceeding max_side must be downsampled (flag=True)."""
    png = _make_png(4096, 4096)
    result_bytes, downsampled = _normalize_image(png, max_side=2048)

    assert downsampled is True
    img = Image.open(BytesIO(result_bytes))
    assert max(img.width, img.height) <= 2048


def test_normalize_image_returns_valid_png() -> None:
    """Output must always be a valid PNG regardless of downsampling."""
    png = _make_png(512, 256)
    result_bytes, _ = _normalize_image(png, max_side=2048)

    assert result_bytes[:8] == _PNG_MAGIC


def test_preprocess_small_image_downsampling_applied_false() -> None:
    """preprocess() must report downsampling_applied=False for a small image."""
    small_png = _make_png(100, 100)
    result = preprocess(small_png)

    assert result.downsampling_applied is False


def test_preprocess_large_image_downsampling_applied_true() -> None:
    """preprocess() must report downsampling_applied=True when image exceeds threshold."""
    large_png = _make_png(
        settings.MAX_IMAGE_SIDE_PX + 500,
        settings.MAX_IMAGE_SIDE_PX + 500,
    )
    result = preprocess(large_png)

    assert result.downsampling_applied is True


# ---------------------------------------------------------------------------
# _pdf_to_image() — multi-page rendering and limits
# ---------------------------------------------------------------------------


def _make_pdf(n_pages: int) -> bytes:
    """Create a blank n-page PDF using fitz."""
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page()
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_pdf_to_image_two_pages_stitched() -> None:
    """Two-page PDF must produce an image taller than a single-page render."""
    one_page_bytes = _pdf_to_image(_make_pdf(1))
    two_page_bytes = _pdf_to_image(_make_pdf(2))

    single_height = Image.open(BytesIO(one_page_bytes)).height
    stitched_height = Image.open(BytesIO(two_page_bytes)).height

    assert stitched_height > single_height


def test_pdf_to_image_exceeds_limit_renders_only_max_pages() -> None:
    """PDF with more pages than PDF_MAX_PAGES must not raise — renders only allowed pages."""
    excess_pdf = _make_pdf(settings.PDF_MAX_PAGES + 2)
    result = _pdf_to_image(excess_pdf)

    assert result[:8] == _PNG_MAGIC


def test_pdf_to_image_empty_pdf_raises_invalid_input_error() -> None:
    """An invalid/empty-like PDF payload must raise InvalidInputError."""
    # Minimal PDF header/trailer without a valid page tree.
    empty_pdf = b"%PDF-1.4\n%%EOF\n"

    with pytest.raises(InvalidInputError):
        _pdf_to_image(empty_pdf)
