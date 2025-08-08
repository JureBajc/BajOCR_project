import logging
import sys
from PIL import Image, ImageEnhance

try:
    from .constants import LOG_FILE
except ImportError:
    LOG_FILE = 'ocr_processor.log'

# Cache for setup_logging to avoid multiple setups
_logging_setup = False

def setup_logging(log_level):
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

def preprocess_image(image, max_size=2000):
    """Optimized image preprocessing with caching and early returns"""
    try:
        width, height = image.size
        
        # Only resize if necessary
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int(height * max_size / width)
            else:
                new_height = max_size
                new_width = int(width * max_size / height)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to grayscale only if needed
        if image.mode != 'L':
            image = image.convert('L')
        
        # Apply enhancements in one pass
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        sharpness_enhancer = ImageEnhance.Sharpness(image)
        image = sharpness_enhancer.enhance(1.2)
        
        return image
    except Exception as e:
        logging.getLogger(__name__).error(f"Napaka pri predprocesiranju slike: {e}")
        return image