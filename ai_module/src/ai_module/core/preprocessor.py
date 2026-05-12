"""File preprocessing: size validation, type detection, PDF rendering, and image normalisation."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import cast

import fitz  # type: ignore[import-untyped]  # PyMuPDF has no stubs
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


@dataclass(frozen=True, slots=True)
class PreprocessResult:
    """Immutable result of the preprocessing step."""

    image_bytes: bytes
    input_type: str
    downsampling_applied: bool


def _detect_file_type(file_bytes: bytes) -> str:
    """
    Detecta o tipo real do arquivo analisando os bytes mágicos.
    Retorna 'png', 'jpeg' ou 'pdf'.
    Gera uma exceção UnsupportedFormatError para qualquer outro tipo de conteúdo.
    """
    for file_type, magic in _MAGIC_BYTES.items():
        if file_bytes[: len(magic)] == magic:
            return file_type
    raise UnsupportedFormatError("File format not supported. Accepted formats: PNG, JPEG, PDF.")


def _validate_size(file_bytes: bytes) -> None:
    """Gera um InvalidInputError se o arquivo exceder MAX_FILE_SIZE_MB."""
    limit = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > limit:
        msg = f"O tamanho do arquivo excede o limite de {settings.MAX_FILE_SIZE_MB} MB."
        raise InvalidInputError(msg)


def _pdf_to_image(file_bytes: bytes) -> bytes:
    """
    Renderiza até PDF_MAX_PAGES páginas de um PDF e as concatena verticalmente.
    Gera uma exceção InvalidInputError se o PDF não puder ser lido ou estiver vazio.
    """
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.page_count == 0:
                raise InvalidInputError("The PDF has no pages to process.")

            pages_to_render = min(doc.page_count, settings.PDF_MAX_PAGES)
            if doc.page_count > settings.PDF_MAX_PAGES:
                logger.warning(
                    "PDF exceeds page limit; rendering first %d of %d pages.",
                    pages_to_render,
                    doc.page_count,
                    extra={
                        "event": "pdf_page_cap",
                        "details": {
                            "page_count": doc.page_count,
                            "pages_rendered": pages_to_render,
                            "limit": settings.PDF_MAX_PAGES,
                        },
                    },
                )

            matrix = fitz.Matrix(2, 2)
            page_images: list[Image.Image] = []
            for page_idx in range(pages_to_render):
                page = doc.load_page(page_idx)
                pixmap = page.get_pixmap(matrix=matrix)
                page_img = Image.open(BytesIO(cast(bytes, pixmap.tobytes("png"))))
                page_images.append(page_img.convert("RGB"))

            if len(page_images) == 1:
                buffer = BytesIO()
                page_images[0].save(buffer, format="PNG")
                return buffer.getvalue()

            max_width = max(img.width for img in page_images)
            total_height = sum(img.height for img in page_images)
            stitched = Image.new("RGB", (max_width, total_height))
            y_offset = 0
            for img in page_images:
                stitched.paste(img, (0, y_offset))
                y_offset += img.height

            buffer = BytesIO()
            stitched.save(buffer, format="PNG")
            return buffer.getvalue()

    except InvalidInputError:
        raise
    except Exception as e:
        logger.error(
            "Failed to process PDF file",
            extra={"event": "pdf_processing_error", "details": {"error": str(e)}},
        )
        raise InvalidInputError("Unable to read the PDF file. It may be corrupted.") from e


def _normalize_image(image_bytes: bytes, max_side: int | None = None) -> tuple[bytes, bool]:
    """
    Abre uma imagem com o Pillow, converte-a para RGB e retorna (png_bytes, downsampled).

    Se ``max_side`` for fornecido e qualquer dimensão exceder esse valor, a imagem é
    redimensionada com ``Image.thumbnail`` usando o filtro LANCZOS.

    Returns:
        (png_bytes, downsampling_applied) — downsampling_applied é True se a imagem
        foi redimensionada.
    """
    if max_side is None:
        max_side = settings.MAX_IMAGE_SIDE_PX
    try:
        img: Image.Image = Image.open(BytesIO(image_bytes))
        img = img.convert("RGB")
        original_size = (img.width, img.height)
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        downsampled = (img.width, img.height) != original_size
        if downsampled:
            logger.info(
                "Image downsampled to fit within max_side limit.",
                extra={
                    "event": "image_downsampled",
                    "details": {
                        "original_size": original_size,
                        "new_size": (img.width, img.height),
                        "max_side": max_side,
                    },
                },
            )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue(), downsampled
    except Exception as e:
        logger.error(
            "Falha ao processar o arquivo de imagem",
            extra={"event": "image_processing_error", "details": {"error": str(e)}},
        )
        raise InvalidInputError(f"Não foi possível decodificar o arquivo de imagem: {e}") from e


def preprocess(file_bytes: bytes) -> PreprocessResult:
    """
    Fluxo completo de pré-processamento para um arquivo enviado.

    Etapas:
      1. Validar o tamanho do arquivo em relação a MAX_FILE_SIZE_MB.
      2. Detectar o tipo real do arquivo por meio de bytes mágicos.
      3. Se for PDF: converter páginas em imagem stitched.
      4. Normalizar a imagem para PNG RGB (com downsampling se necessário).

    Retorna:
      PreprocessResult com image_bytes, input_type e downsampling_applied.

    Gera:
      InvalidInputError: arquivo muito grande ou ilegível.
      UnsupportedFormatError: tipo de arquivo não suportado.
    """
    _validate_size(file_bytes)
    file_type = _detect_file_type(file_bytes)

    if file_type == "pdf":
        processed_bytes = _pdf_to_image(file_bytes)
        normalized_bytes, downsampled = _normalize_image(processed_bytes)
        return PreprocessResult(
            image_bytes=normalized_bytes,
            input_type="pdf",
            downsampling_applied=downsampled,
        )

    normalized_bytes, downsampled = _normalize_image(file_bytes)
    return PreprocessResult(
        image_bytes=normalized_bytes,
        input_type="image",
        downsampling_applied=downsampled,
    )
