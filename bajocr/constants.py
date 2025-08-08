"""Constants for the BajOCR package."""

from __future__ import annotations

from pathlib import Path

DEFAULT_TESSERACT_PATHS: list[str] = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]

FILENAME_TEMPLATE: str = "{date}_{entity}.png"

IMAGE_EXTENSIONS: list[str] = [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]

LOG_FILE: str = "ocr_processor.log"

DEFAULT_LOG_LEVEL: str = "INFO"

DEFAULT_LANG: str = "slv"

# Preprocessing config
MAX_IMAGE_SIZE: int = 2000  # max width/height for resize
CONTRAST_FACTOR: float = 1.5
SHARPNESS_FACTOR: float = 1.2
DEFAULT_SCAN_FOLDER: Path = Path.home() / "Desktop" / "pyTest" / "TestData"