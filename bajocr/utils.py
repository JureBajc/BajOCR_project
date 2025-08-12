import logging
import sys
import re
from pathlib import Path
from PIL import Image, ImageEnhance

try:
    from .constants import LOG_FILE, PHASH_HASH_SIZE
except ImportError:
    LOG_FILE = 'ocr_processor.log'
    PHASH_HASH_SIZE = 16

_logging_setup = False

def setup_logging(log_level):
    global _logging_setup
    if _logging_setup:
        return
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'),
                  logging.StreamHandler(sys.stdout)]
    )
    _logging_setup = True

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or 'NEZNANO'

def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    base = path.with_suffix('')
    ext = path.suffix
    for i in range(1, 101):
        cand = Path(f"{base}_{i}{ext}")
        if not cand.exists():
            return cand
    import time as _t
    return Path(f"{base}_{int(_t.time()*1000)%10000}{ext}")

def preprocess_image(image, max_size=2000):
    try:
        w, h = image.size
        if w > max_size or h > max_size:
            if w > h:
                nw, nh = max_size, int(h * max_size / w)
            else:
                nh, nw = max_size, int(w * max_size / h)
            image = image.resize((nw, nh), Image.Resampling.LANCZOS)
        if image.mode != 'L':
            image = image.convert('L')
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = ImageEnhance.Sharpness(image).enhance(1.2)
        return image
    except Exception as e:
        logging.getLogger(__name__).error(f"Napaka pri predprocesiranju slike: {e}")
        return image

# ---- Merge + sort helpers ----
def natural_sort_key(p: Path):
    s = p.name
    return [int(t) if t.isdigit() else t.lower() for t in re.findall(r'\d+|\D+', s)]

def merge_pdfs(pdf_paths, output_path: Path):
    from PyPDF2 import PdfMerger
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    m = PdfMerger()
    for p in pdf_paths:
        m.append(str(p))
    with open(output_path, "wb") as f:
        m.write(f)
    m.close()
    return output_path

# ---- Visual fingerprint (average-hash) ----
def average_hash(img: Image.Image, hash_size: int = PHASH_HASH_SIZE) -> str:
    try:
        g = img.convert('L').resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = list(g.getdata())
        avg = sum(pixels) / len(pixels)
        bits = ''.join('1' if px >= avg else '0' for px in pixels)
        # pack to hex
        return hex(int(bits, 2))[2:].rjust((hash_size*hash_size)//4, '0')
    except Exception:
        return '0' * ((hash_size*hash_size)//4)

def hamming(hex_a: str, hex_b: str) -> int:
    a = int(hex_a, 16)
    b = int(hex_b, 16)
    x = a ^ b
    # count bits
    cnt = 0
    while x:
        x &= x - 1
        cnt += 1
    return cnt
