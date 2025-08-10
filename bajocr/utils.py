import logging
import sys
import re
from pathlib import Path
from PIL import Image, ImageEnhance
try:
    from .constants import LOG_FILE
except ImportError:
    LOG_FILE = 'ocr_processor.log'

_logging_setup = False

def setup_logging(log_level):
    """conf root logger na file + stdout."""
    global _logging_setup
    if _logging_setup:
        return

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    _logging_setup = True

def sanitize_filename(name: str) -> str:
    """sanitize filename chars; keep it simple."""
    # replace path separators and illegal chars on common OS
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    # collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # avoid empty
    return name or 'NEZNANO'

def ensure_unique_path(path: Path) -> Path:
    """ensure path uniqueness by appending counters."""
    if not path.exists():
        return path
    base = path.with_suffix('')
    ext = path.suffix
    for i in range(1, 101):
        candidate = Path(f"{base}_{i}{ext}")
        if not candidate.exists():
            return candidate
    # last resort timestamp
    return Path(f"{base}_{int(__import__('time').time()*1000)%10000}{ext}")

def preprocess_image(image, max_size=2000):
    """preprocesing giga pocasno."""
    try:
        width, height = image.size
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int(height * max_size / width)
            else:
                new_height = max_size
                new_width = int(width * max_size / height)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        if image.mode != 'L':
            image = image.convert('L')
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = ImageEnhance.Sharpness(image).enhance(1.2)
        return image
    except Exception as e:
        logging.getLogger(__name__).error(f"Napaka pri predprocesiranju slike: {e}")
        return image
