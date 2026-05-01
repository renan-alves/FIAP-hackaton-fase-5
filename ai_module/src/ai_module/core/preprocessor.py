"""File preprocessing: size validation, type detection, PDF rendering, and image normalisation."""

from __future__ import annotations

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
    Renderiza a primeira página de um PDF como uma imagem PNG.
    Registra um aviso se o PDF tiver mais de uma página.
    Gera uma exceção InvalidInputError se o PDF não puder ser lido.
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
            return cast(bytes, pixmap.tobytes("png"))
    except Exception as e:
        logger.error(
            "Failed to process PDF file",
            extra={"event": "pdf_processing_error", "details": {"error": str(e)}},
        )
        raise InvalidInputError("Unable to read the PDF file. It may be corrupted.") from e


def _normalize_image(image_bytes: bytes) -> bytes:
    """
    Abre uma imagem com o Pillow, converte-a para RGB e retorna os bytes do PNG.
    Gera uma exceção InvalidInputError se a imagem não puder ser decodificada.
    """
    try:
        img: Image.Image = Image.open(BytesIO(image_bytes))
        img = img.convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as e:
        logger.error(
            "Falha ao processar o arquivo de imagem",
            extra={"event": "image_processing_error", "details": {"error": str(e)}},
        )
        raise InvalidInputError(f"Não foi possível decodificar o arquivo de imagem: {e}") from e


def preprocess(file_bytes: bytes) -> tuple[bytes, str]:
    """
    Fluxo completo de pré-processamento para um arquivo enviado.

    Etapas:
      1. Validar o tamanho do arquivo em relação a MAX_FILE_SIZE_MB.
      2. Detectar o tipo real do arquivo por meio de bytes mágicos.
      3. Se for PDF: converter a primeira página em imagem.
      4. Normalizar a imagem para PNG RGB.

    Retorna:
      (normalized_image_bytes, input_type), onde input_type é "image" ou "pdf".

    Gera:
      InvalidInputError: arquivo muito grande ou ilegível.
      UnsupportedFormatError: tipo de arquivo não suportado.



    """
    _validate_size(file_bytes)
    file_type = _detect_file_type(file_bytes)

    if file_type == "pdf":
        processed_bytes = _pdf_to_image(file_bytes)
        normalized = _normalize_image(processed_bytes)
        return normalized, "pdf"

    normalized = _normalize_image(file_bytes)
    return normalized, "image"
