import re

DEFAULT_TESSERACT_PATHS = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    '/usr/bin/tesseract',
    '/opt/homebrew/bin/tesseract',
]

FILENAME_TEMPLATE = "{date}_{doc_type}_{entity}.png"
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']
LOG_FILE = 'ocr_processor.log'

DATE_PATTERNS = [
    # Standard formats: 5.9.2025, 05.09.2025, 5/9/2025, 5-9-2025
    re.compile(r'(\d{1,2})\s*[\.,/\-\s]+(\d{1,2})\s*[\.,/\-\s]+(\d{4})', re.MULTILINE),
    
    # ISO format: 2025-09-05, 2025.09.05
    re.compile(r'(\d{4})\s*[\.,/\-\s]+(\d{1,2})\s*[\.,/\-\s]+(\d{1,2})', re.MULTILINE),
    
    # Slovenian month names with more flexibility
    re.compile(
        r'(\d{1,2})\.?\s*'
        r'(januar|februar|marec|april|maj|junij|julij|avgust|'
        r'september|oktober|november|december|'
        r'jan|feb|mar|apr|maj|jun|jul|avg|sep|okt|nov|dec)'
        r'\s*(\d{4})',
        re.IGNORECASE | re.MULTILINE
    ),
    
    # More flexible date patterns
    re.compile(r'(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{2,4})', re.MULTILINE),
    re.compile(r'(\d{1,2})\s+(\d{1,2})\s+(\d{4})', re.MULTILINE),
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
    'januar': '01', 'jan': '01',
    'februar': '02', 'feb': '02', 
    'marec': '03', 'mar': '03',
    'april': '04', 'apr': '04',
    'maj': '05',
    'junij': '06', 'jun': '06',
    'julij': '07', 'jul': '07',
    'avgust': '08', 'avg': '08',
    'september': '09', 'sep': '09',
    'oktober': '10', 'okt': '10',
    'november': '11', 'nov': '11',
    'december': '12', 'dec': '12'
}


# ---- Document type detection ----
DOC_TYPE_PATTERNS = [
    ("IZJAVA",      re.compile(r"\bIZJAVA\b", re.IGNORECASE)),
    ("POGODBA",     re.compile(r"\bPOGODB[AO]\b", re.IGNORECASE)),
    ("RAČUN",       re.compile(r"\b(RAČUN|FAKTURA)\b", re.IGNORECASE)),
    ("PONUDBA",     re.compile(r"\bPONUDBA\b", re.IGNORECASE)),
    ("NAROČILNICA", re.compile(r"\bNAROČILNICA\b", re.IGNORECASE)),
    ("DOBAVNICA",   re.compile(r"\bDOBAVNICA\b", re.IGNORECASE)),
    ("SKLEP",       re.compile(r"\bSKLEP\b", re.IGNORECASE)),
    ("ODLOČBA",     re.compile(r"\bODLOČBA\b", re.IGNORECASE)),
    ("POTRDILO",    re.compile(r"\bPOTRDILO\b", re.IGNORECASE)),
    ("OBVESTILO",   re.compile(r"\bOBVESTILO\b", re.IGNORECASE)),
]


# Page-number detection
PAGE_NUMBER_PATTERNS = [
    re.compile(r'\bstran\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bstr\.\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bpage\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bpg\.\s*(\d+)\b', re.IGNORECASE),
]
PAGE_BOTTOM_STRIP = 0.25  # OCR only bottom 25% for "lonely digits"

# Visual fingerprint (average-hash) of header area
PHASH_HASH_SIZE = 16
PHASH_DISTANCE_THRESHOLD = 18  # <= this → same document header
HEADER_STRIP = 0.22  # top 22% of the page
