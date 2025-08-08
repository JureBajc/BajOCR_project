"""Core OCR processing: folder scanning, OCR, and exporting."""
from __future__ import annotations

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import pytesseract
from PIL import Image

from .constants import DEFAULT_LANG, IMAGE_EXTENSIONS
from .exporters import PdfExporter, ExportError
from .utils import preprocess_image, setup_logging, find_tesseract_executable


class OCRProcessingError(Exception):
    """Raised for fatal OCR processing errors."""


@dataclass(frozen=True)
class OCRResult:
    """Container for OCR results."""
    image: Path
    text: str


class BajOCR:
    """High-level OCR façade with Tesseract and export helpers.

    Attributes:
        tesseract_cmd: Path to tesseract executable (if found).
        lang: OCR language code (e.g., 'eng', 'slv').
        logger: Module logger.
    """

    def __init__(
        self,
        lang: str = DEFAULT_LANG,
        log_level: str = "INFO",
        tesseract_path: Optional[str | Path] = None
    ) -> None:
        """Initialize the processor.

        Args:
            lang: OCR language code.
            log_level: Logging level string.
            tesseract_path: Explicit path to Tesseract executable.
        """
        setup_logging(log_level)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.lang: str = lang
        self.tesseract_cmd: Optional[Path] = find_tesseract_executable(tesseract_path)
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = str(self.tesseract_cmd)
            self.logger.info("Using Tesseract at: %s", self.tesseract_cmd)
        else:
            self.logger.warning("Tesseract executable not found. OCR calls may fail.")

    # ------------------------ Discovery ------------------------

    def list_images(self, folder: str | Path) -> list[Path]:
        """List supported images in a folder.

        Args:
            folder: Directory to search.

        Returns:
            Sorted list of image paths.

        Raises:
            FileNotFoundError: If folder does not exist.
        """
        fpath = Path(folder)
        if not fpath.exists():
            raise FileNotFoundError(f"Input folder not found: {fpath}")
        images = [p for p in sorted(fpath.iterdir()) if p.suffix.lower() in IMAGE_EXTENSIONS]
        self.logger.debug("Found %d images in %s", len(images), fpath)
        return images

    # ------------------------ OCR (plain text, if needed) ------------------------

    def ocr_image(self, image: Image.Image) -> str:
        """Run OCR on a PIL.Image after preprocessing.

        Args:
            image: Image to OCR.

        Returns:
            Recognized text.

        Raises:
            OCRProcessingError: If OCR fails.
        """
        try:
            pre = preprocess_image(image)
            text = pytesseract.image_to_string(pre, lang=self.lang)
            return text
        except Exception as exc:
            self.logger.exception("OCR failed")
            raise OCRProcessingError(f"OCR failed: {exc}") from exc

    # ------------------------ Batch text OCR (optional) ------------------------

    def process_file(self, image_path: str | Path) -> OCRResult:
        """OCR a single image file to text (not used for PDF export)."""
        p = Path(image_path)
        self.logger.info("Processing (text OCR): %s", p)
        with Image.open(p) as im:
            text = self.ocr_image(im)
        return OCRResult(image=p, text=text)

    def process_folder(self, folder: str | Path, workers: Optional[int] = None) -> list[OCRResult]:
        """OCR all images in a folder to text, optionally in parallel."""
        images = self.list_images(folder)
        if not images:
            self.logger.warning("No images found in %s", folder)
            return []

        max_workers = workers or min(32, (os.cpu_count() or 2) * 5)
        self.logger.info("Starting OCR on %d images with %d workers", len(images), max_workers)

        results: list[OCRResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(self.process_file, img): img for img in images}
            for fut in as_completed(futs):
                try:
                    res = fut.result()
                    results.append(res)
                    self.logger.debug("Completed: %s", res.image)
                except Exception as exc:
                    img = futs[fut]
                    self.logger.exception("Failed processing %s: %s", img, exc)
                    results.append(OCRResult(image=img, text=f"[OCR failed: {exc}]"))
        return results

    # ------------------------ Export: Searchable PDF ------------------------

    def export_folder_to_pdf(
        self,
        input_dir: str | Path,
        output_pdf: str | Path,
        *,
        workers: Optional[int] = None,
        psm: int = 6,
        oem: int = 1,
        preserve_image_layout: bool = True,
        try_orientation: bool = True,
    ) -> Path:
        """Create a searchable PDF that preserves page appearance.

        This runs Tesseract's PDF renderer per page and merges all pages into a single PDF.

        Args:
            input_dir: Folder with images.
            output_pdf: Destination PDF path.
            workers: Thread pool size for per-page rendering (None => auto).
            psm: Tesseract page segmentation mode (6 is good baseline).
            oem: Tesseract OCR engine mode (1 = LSTM).
            preserve_image_layout: If True, use original image as raster layer.
            try_orientation: Use OSD to auto-rotate pages before OCR (best effort).

        Returns:
            Path to the generated PDF.

        Raises:
            FileNotFoundError: If input_dir does not exist.
            ExportError: On PDF export failure.
        """
        images = self.list_images(input_dir)
        if not images:
            self.logger.warning("No images found in %s", input_dir)
            # Still create empty PDF? We'll raise for clarity:
            raise FileNotFoundError(f"No images to export in {input_dir}")

        max_workers = workers or min(32, (os.cpu_count() or 2) * 5)
        config = f"--oem {oem} --psm {psm} -c preserve_interword_spaces=1"
        self.logger.info(
            "Exporting %d images to PDF via Tesseract (psm=%s, oem=%s)",
            len(images), psm, oem
        )

        def render_one(index: int, path: Path) -> tuple[int, bytes]:
            """Worker: load image, optional orientation fix, render PDF bytes."""
            with Image.open(path) as im:
                # Optional: orientation detection to rotate original image
                if try_orientation:
                    try:
                        osd = pytesseract.image_to_osd(im)
                        if "Rotate: 90" in osd:
                            im = im.rotate(270, expand=True)
                        elif "Rotate: 270" in osd:
                            im = im.rotate(90, expand=True)
                        elif "Rotate: 180" in osd:
                            im = im.rotate(180, expand=True)
                    except Exception:
                        pass
                # Preserve layout: use original image as raster layer.
                # (If you'd rather use heavy preprocessing on raster, apply here.)
                pdf_bytes = PdfExporter.render_page_pdf(im, lang=self.lang, config=config)
                return index, pdf_bytes

        # Parallel render to bytes
        page_bytes: list[tuple[int, bytes]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(render_one, i, p): i for i, p in enumerate(images)}
            for fut in as_completed(futs):
                try:
                    idx, data = fut.result()
                    page_bytes.append((idx, data))
                except Exception as exc:
                    self.logger.exception("Failed rendering a page: %s", exc)
                    # Insert a blank page stub so page count stays consistent?
                    # We'll re-raise to fail the export cleanly:
                    raise ExportError(f"Page rendering failed: {exc}") from exc

        # Merge in original order
        page_bytes.sort(key=lambda t: t[0])
        exporter = PdfExporter(output_pdf)
        for _, data in page_bytes:
            exporter.add_page_bytes(data)
        return exporter.save()