import logging
import sys
from PIL import Image, ImageEnhance, ImageFilter

try:
    from .constants import LOG_FILE
except ImportError:
    LOG_FILE = 'ocr_processor.log'

def setup_logging(log_level):
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def preprocess_image(image):
    try:
        width, height = image.size
        max_size = 2000
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
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        sharpness_enhancer = ImageEnhance.Sharpness(image)
        image = sharpness_enhancer.enhance(1.2)
        return image
    except Exception as e:
        logging.getLogger(__name__).error(f"Napaka pri predprocesiranju slike: {e}")
        return image
