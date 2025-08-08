"""
PDF exporter for searchable PDFs (image + invisible text overlay).

This module assembles a multi-page PDF that preserves the original page
appearance (the raster image) while embedding recognized text so that
copy/paste and search work reliably.

Design:
- For each page, we use Tesseract's PDF renderer via pytesseract.
- We then merge all single-page PDFs into a single file using pypdf.

Note:
- We keep image appearance intact by default (no heavy preprocessing).
- Rotation (OSD) can be handled in the caller if desired.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image
from pypdf import PdfReader, PdfWriter


class ExportError(Exception):
    """Raised when exporting to PDF fails."""


@dataclass(frozen=True)
class PdfPage:
    """Single-page PDF payload."""
    index: int
    data: bytes


class PdfExporter:
    """Create a searchable multi-page PDF from images using Tesseract.

    Usage:
        writer = PdfExporter("out.pdf")
        writer.add_page_bytes(page_bytes)  # repeat
        writer.save()

    Attributes:
        output_path: Destination path for the merged PDF.
    """

    def __init__(self, output_path: str | Path) -> None:
        self.output_path: Path = Path(output_path)
        self._writer = PdfWriter()
        self._log = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def render_page_pdf(
        image: Image.Image,
        *,
        lang: str,
        config: str,
    ) -> bytes:
        """Render a single searchable-PDF page from a PIL image via Tesseract.

        Args:
            image: PIL image (ideally the original to preserve layout).
            lang: Tesseract language(s), e.g. "slv" or "slv+eng".
            config: Tesseract extra config, e.g. "--oem 1 --psm 6 -c preserve_interword_spaces=1".

        Returns:
            Bytes of a one-page PDF.
        """
        # Tesseract returns a full PDF in bytes for the given image
        return pytesseract.image_to_pdf_or_hocr(image, extension="pdf", lang=lang, config=config)

    def add_page_bytes(self, pdf_bytes: bytes) -> None:
        """Append a single-page PDF (bytes) into the cumulative writer.

        Args:
            pdf_bytes: A valid one-page PDF produced by Tesseract.

        Raises:
            ExportError: If the provided bytes are not a valid PDF page.
        """
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            if len(reader.pages) != 1:
                raise ExportError("Expected a single-page PDF from Tesseract.")
            self._writer.add_page(reader.pages[0])
        except Exception as exc:
            self._log.exception("Failed adding page to writer.")
            raise ExportError(f"Failed adding PDF page: {exc}") from exc

    def save(self) -> Path:
        """Write the merged PDF to disk.

        Returns:
            Path to the written PDF.

        Raises:
            ExportError: If writing fails.
        """
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("wb") as f:
                self._writer.write(f)
            self._log.info("Saved PDF to: %s", self.output_path)
            return self.output_path
        except Exception as exc:
            self._log.exception("Failed saving merged PDF.")
            raise ExportError(f"Failed to save PDF to {self.output_path}: {exc}") from exc
