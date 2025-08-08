import re

DEFAULT_TESSERACT_PATHS = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    '/usr/bin/tesseract',
    '/opt/homebrew/bin/tesseract',
]

FILENAME_TEMPLATE = "{date}_{entity}.png"
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']
LOG_FILE = 'ocr_processor.log'

# Pre-compiled regex patterns for better performance
DATE_PATTERNS = [
    re.compile(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})'),
    re.compile(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})'),
    re.compile(
        r'(\d{1,2})\s+'
        r'(januar|februar|marec|april|maj|junij|julij|avgust|'
        r'september|oktober|november|december)\s+(\d{4})',
        re.IGNORECASE
    ),
]

NAME_PATTERNS = [
    re.compile(
        r'^([A-ZČŠŽĆĐ][a-zčšžćđ]+)\s+([A-ZČŠŽĆĐ][a-zčšžćđ]+)'
        r'(?:\s+([A-ZČŠŽĆĐ][a-zčšžćđ]+))?$'
    ),
    re.compile(r'^([A-ZČŠŽĆĐ]{2,})\s+([A-ZČŠŽĆĐ]{2,})$'),
]

NAME_INDICATORS = [
    'priimek in ime', 'ime in priimek', 'ime:', 'priimek:',
    'podpisnik', 'podpisuje', 'izvršitelj', 'direktor', 'vodja'
]

MONTH_MAP = {
    'januar': '01', 'februar': '02', 'marec': '03', 'april': '04',
    'maj': '05', 'junij': '06', 'julij': '07', 'avgust': '08',
    'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
}