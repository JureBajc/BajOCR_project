import sys
from pathlib import Path

DEFAULT_TESSERACT_PATHS = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    '/usr/bin/tesseract',
    '/opt/homebrew/bin/tesseract',
]

FILENAME_TEMPLATE = "{date}_{entity}.png"

IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']
LOG_FILE = 'ocr_processor.log'
