"""Utility functions: logging setup, image preprocessing, and helpers."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageEnhance

from .constants import (
    LOG_FILE,
    DEFAULT_LOG_LEVEL,
    MAX_IMAGE_SIZE,
    CONTRAST_FACTOR,
    SHARPNESS_FACTOR,
    DEFAULT_TESSERACT_PATHS,
)


def setup_logging(level: str = DEFAULT_LOG_LEVEL) -> None:
    """Configure module-wide logging.

    Args:
        level: Logging level as a string, e.g. "INFO" or "DEBUG".
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def find_tesseract_executable(explicit_path: Optional[str | Path] = None) -> Optional[Path]:
    """Find a Tesseract executable path.

    Args:
        explicit_path: If provided, this path is validated and returned if executable.

    Returns:
        Path to Tesseract executable, or None if not found.
    """
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.extend(Path(p) for p in DEFAULT_TESSERACT_PATHS)

    for cand in candidates:
        if cand.exists() and os.access(cand, os.X_OK):
            return cand
    return None


def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess an image for OCR: resize, grayscale, contrast, sharpness.

    Args:
        image: PIL image.

    Returns:
        Preprocessed PIL image.
    """
    try:
        im = image
        # Resize if needed
        w, h = im.size
        if max(w, h) > MAX_IMAGE_SIZE:
            if w >= h:
                new_w = MAX_IMAGE_SIZE
                new_h = int(h * MAX_IMAGE_SIZE / w)
            else:
                new_h = MAX_IMAGE_SIZE
                new_w = int(w * MAX_IMAGE_SIZE / h)
            im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

        if im.mode != "L":
            im = im.convert("L")

        im = ImageEnhance.Contrast(im).enhance(CONTRAST_FACTOR)
        im = ImageEnhance.Sharpness(im).enhance(SHARPNESS_FACTOR)
        return im
    except Exception as exc:
        logging.getLogger(__name__).exception("Error during preprocessing: %s", exc)
        return image
