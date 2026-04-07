"""File preprocessing: size validation, type detection, PDF rendering, and image normalisation."""

from __future__ import annotations

from io import BytesIO

import fitz  # PyMuPDF
from PIL import Image

from ai_module.core.exceptions import InvalidInputError, UnsupportedFormatError
from ai_module.core.logger import get_logger
from ai_module.core.settings import settings

logger = get_logger("ai_module.core.preprocessor")

_MAGIC_BYTES = {
    "pdf": b"%PDF-",
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
}

def _detect_file_type(file_bytes: bytes) -> str:
    """
    Detects the real file type by inspecting magic bytes.
    Returns 'png', 'jpeg', or 'pdf'.
    Raises UnsupportedFormatError for any other content.
    """
    for file_type, magic in _MAGIC_BYTES.items():
        if file_bytes[: len(magic)] == magic:
            return file_type
    raise UnsupportedFormatError(
        "File format not supported. Accepted formats: PNG, JPEG, PDF."
    )


def _validate_size(file_bytes: bytes) -> None:
    """Raises InvalidInputError if the file exceeds MAX_FILE_SIZE_MB."""
    limit = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > limit:
        raise InvalidInputError(
            f"File size exceeds the {settings.MAX_FILE_SIZE_MB} MB limit."
        )


def _pdf_to_image(file_bytes: bytes) -> bytes:
    """
    Renders the first page of a PDF as a PNG image.
    Logs a warning if the PDF has more than one page.
    Raises InvalidInputError if the PDF cannot be read.
    """
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.page_count == 0:
                raise InvalidInputError("The PDF has no pages to process.")

            if doc.page_count > 1:
                logger.warning(
                    "PDF has multiple pages; only the first page will be analysed.",
                    extra={
                        "event": "pdf_multipage_warning",
                        "details": {"page_count": doc.page_count},
                    },
                )

            page = doc.load_page(0)
            matrix = fitz.Matrix(2, 2)
            pixmap = page.get_pixmap(matrix=matrix)
            return pixmap.tobytes("png")
    except Exception as e:
        logger.error(
            "Failed to process PDF file",
            extra={"event": "pdf_processing_error", "details": {"error": str(e)}},
        )
        raise InvalidInputError("Unable to read the PDF file. It may be corrupted.") from e

def _normalize_image(image_bytes: bytes) -> bytes:
    """
    Opens an image with Pillow, converts to RGB, and returns PNG bytes.
    Raises InvalidInputError if the image cannot be decoded.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        img = img.convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as e:
        logger.error(
            "Failed to process image file",
            extra={"event": "image_processing_error", "details": {"error": str(e)}},
        )
        raise InvalidInputError(f"Could not decode image file: {e}") from e


def preprocess(file_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """
    Full preprocessing pipeline for an uploaded file.
 
    Steps:
      1. Validate file size against MAX_FILE_SIZE_MB.
      2. Detect real file type via magic bytes.
      3. If PDF: convert first page to image.
      4. Normalize image to RGB PNG.
 
    Returns:
      (normalized_image_bytes, input_type) where input_type is "image" or "pdf".
 
    Raises:
      InvalidInputError: file too large or unreadable.
      UnsupportedFormatError: file type not supported.
    """
    _validate_size(file_bytes)
    file_type = _detect_file_type(file_bytes)

    if file_type == "pdf":
        processed_bytes = _pdf_to_image(file_bytes)
        normalized = _normalize_image(processed_bytes)
        return normalized, "pdf"
    
    normalized = _normalize_image(file_bytes)
    return normalized, "image"

