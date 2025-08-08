import json
import os
import sys
import time
import logging
import multiprocessing
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple

import pytesseract
from PIL import Image

from .constants import (
    DEFAULT_TESSERACT_PATHS,
    FILENAME_TEMPLATE,
    IMAGE_EXTENSIONS,
    DATE_PATTERNS,
    NAME_PATTERNS,
    NAME_INDICATORS,
    MONTH_MAP,
)
from .utils import setup_logging, preprocess_image

_LOGGER = logging.getLogger(__name__)

def _convert_image_to_pdf(
    img_path: str,
    tesseract_path: Optional[str],
    lang: str,
    extra_args: List[str]
) -> Tuple[str, bool, str, float]:  # <--- Dodan čas
    start = time.time()
    try:
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        img = Image.open(img_path)
        processed_img = preprocess_image(img.copy())

        # Extract text for naming
        text = pytesseract.image_to_string(processed_img, lang=lang, config=' '.join(extra_args))
        from .core import extract_date_worker, extract_name_worker
        date = extract_date_worker(text)
        entity = extract_name_worker(text)

        # Construct filename
        new_filename = FILENAME_TEMPLATE.replace('.png', '.pdf').format(date=date, entity=entity)
        pdf_path = Path(img_path).with_name(new_filename)

        # Generate PDF
        pdf_bytes = pytesseract.image_to_pdf_or_hocr(
            img, extension='pdf', lang=lang, config=' '.join(extra_args)
        )
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)

        elapsed = time.time() - start
        return img_path, True, str(pdf_path), elapsed

    except Exception as e:
        return img_path, False, str(e), 0.0
    
class BajOCR:
    """
    Optimized BAJO-grade OCR processor za interno uporabo v podjetju.
    """

    def __init__(self, tesseract_path=None, log_level=logging.INFO):
        # Setup Tesseract path and store it
        self.tesseract_path = self._setup_tesseract_path(tesseract_path)
        # Setup logging
        setup_logging(log_level)
        self.logger = logging.getLogger(__name__)
        # Initialize stats and locks
        self.processed_files = set()
        self._reset_stats()
        # Cache current date for performance
        self._current_date = datetime.today().strftime("%d-%m-%Y")

    def _setup_tesseract_path(self, tesseract_path):
        """Setup Tesseract path with caching and return the path."""
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            return tesseract_path
        for path in DEFAULT_TESSERACT_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return path
        return None

    def _reset_stats(self):
        """Reset processing statistics."""
        self.stats = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'start_time': None,
            'end_time': None
        }

    def convert_folder_to_searchable_pdf(
        self,
        folder_path: str,
        lang: str,
        extra_args: List[str],
        max_workers: Optional[int] = None,
        file_extensions: Optional[List[str]] = None,
    ) -> bool:
        """
        Convert each image in `folder_path` into its own searchable PDF in parallel.
        Returns True if at least one PDF was created successfully.
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            _LOGGER.error("Folder not found: %s", folder)
            return False

        exts = file_extensions or IMAGE_EXTENSIONS
        images = [
            str(p) for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        ]
        if not images:
            _LOGGER.warning("No images in folder: %s", folder)
            return False

        workers = max_workers or None
        print(f"\nConverting {len(images)} images → PDF with up to "
            f"{workers or 'all available'} processes...")

        success_count = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _convert_image_to_pdf,
                    img,
                    self.tesseract_path,
                    lang,
                    extra_args
                ): img
                for img in images
            }
            for fut in as_completed(futures):
                img_path, ok, msg, elapsed = fut.result()
                original_name = Path(img_path).name
                new_pdf_name = Path(msg).name

                if ok:
                    print(f"[OK]    {original_name} → {new_pdf_name} ({elapsed:.2f}s)")
                    _LOGGER.info("PDF created: %s → %s", original_name, new_pdf_name)
                    success_count += 1
                else:
                    print(f"[FAIL]  {original_name}: {msg}")
                    _LOGGER.error("Failed PDF for %s: %s", original_name, msg)

        return success_count > 0


    def get_optimal_workers(self) -> int:
        """Pick a sensible default number of processes based on CPU count."""
        cpu = multiprocessing.cpu_count()
        if cpu >= 8:
            return min(6, cpu - 2)
        if cpu >= 4:
            return max(2, cpu - 1)
        return max(1, cpu // 2)

    def process_folder_parallel(
        self,
        folder_path: str,
        max_workers: Optional[int] = None,
        file_extensions: Optional[List[str]] = None
    ) -> bool:
        """Optimized parallel processing using ProcessPoolExecutor for CPU-bound tasks"""
        if file_extensions is None:
            file_extensions = IMAGE_EXTENSIONS

        folder_path = Path(folder_path)
        if not folder_path.exists():
            self.logger.error(f"Mapa ne obstaja: {folder_path}")
            return False

        # Get all image files
        image_files = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in file_extensions
        ]

        if not image_files:
            self.logger.warning(f"Ni najdenih slikovnih datotek v mapi: {folder_path}")
            return False

        if max_workers is None:
            max_workers = self.get_optimal_workers()
        max_workers = max(1, min(max_workers, len(image_files), multiprocessing.cpu_count()))

        print(f"\nBajOCR PROCESSOR v1.0 (Optimized CPU Processing)")
        print(f"{'=' * 65}")
        print(f"Mapa: {folder_path}")
        print(f"Skupno slik: {len(image_files)}")
        print(f"Uporabljam {max_workers} procesov hkrati")
        print(f"{'=' * 65}")

        self.stats['start_time'] = time.time()
        self.processed_files.clear()

        all_results = []
        successful = 0
        failed = 0

        # Use ProcessPoolExecutor for CPU-bound OCR tasks
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(process_image_worker, str(fp)): fp
                for fp in image_files
            }

            for future in as_completed(future_to_file):
                result = future.result()
                all_results.append(result)

                if result.get('success'):
                    successful += 1
                    print(f"[OK]    {result['original']} → {result['new_name']} ({result['time']:.2f}s)")
                else:
                    failed += 1
                    print(f"[FAIL]  {result['original']}: {result['error']}")

        self.stats.update({
            'end_time': time.time(),
            'processed': len(image_files),
            'successful': successful,
            'failed': failed
        })

        self.print_summary_enhanced()
        self.save_report(folder_path, all_results)
        return successful > 0

    def print_summary_enhanced(self):
        """Print enhanced processing summary"""
        total_time = self.stats['end_time'] - self.stats['start_time']
        avg_time = total_time / self.stats['processed'] if self.stats['processed'] > 0 else 0
        success_rate = (self.stats['successful'] / self.stats['processed'] * 100) if self.stats['processed'] > 0 else 0

        print(f"\nPOVZETEK PROCESIRANJA")
        print(f"{'=' * 50}")
        print(f"Skupni čas: {total_time:.1f}s")
        print(f"Povprečni čas na datoteko: {avg_time:.2f}s")
        print(f"Uspešno procesiranih: {self.stats['successful']}")
        print(f"Neuspešnih: {self.stats['failed']}")
        print(f"Stopnja uspešnosti: {success_rate:.1f}%")

        if self.stats['failed'] > self.stats['successful']:
            print("PRIPOROČILO: Visoka stopnja napak - preverite nastavitve")
        elif success_rate > 95:
            print("ODLIČNO: Zelo visoka stopnja uspešnosti!")

        print(f"{'=' * 50}")

    def save_report(self, folder_path, results):
        """Save detailed processing report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'folder': str(folder_path),
            'statistics': self.stats,
            'results': results
        }

        report_path = folder_path / f"ocr_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Poročilo shranjeno: {report_path}")
            print(f"Poročilo shranjeno: {report_path}")
        except Exception as e:
            self.logger.error(f"Napaka pri shranjevanju poročila: {e}")

    def test_single_file(self, folder_path):
        """Test single file with detailed output"""
        folder_path = Path(folder_path)
        test_file = None

        for ext in IMAGE_EXTENSIONS:
            files = list(folder_path.glob(f"*{ext}")) + list(folder_path.glob(f"*{ext.upper()}"))
            if files:
                test_file = files[0]
                break

        if not test_file:
            print("Ni najdenih slikovnih datotek za test.")
            return

        print(f"\nTESTIRANJE ENE DATOTEKE")
        print(f"{'=' * 40}")
        print(f"Testiram: {test_file.name}")

        self.processed_files.clear()
        result = self.process_single_image(str(test_file))

        if result.get('success'):
            print("USPEH")
            print(f"   Originalno ime: {result['original']}")
            print(f"   Novo ime: {result['new_name']}")
            print(f"   Datum: {result['date']}")
            print(f"   Ime osebe: {result['entity']}")
            print(f"   Čas procesiranja: {result['time']:.2f}s")
            print("   Predogled besedila:")
            print(f"   {'-' * 30}")
            print(f"   {result['text_preview']}")
        else:
            print(f"NAPAKA: {result.get('error')}")

# Worker function for ProcessPoolExecutor (must be at module level)
def process_image_worker(file_path, tesseract_path=None):
    """Worker function for processing images in separate processes"""
    start_time = time.time()
    filename = os.path.basename(file_path)

    # Set up Tesseract path in each worker process
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    else:
        # Try default paths in each worker
        for path in DEFAULT_TESSERACT_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

    if not os.path.exists(file_path):
        return {
            'success': False,
            'original': filename,
            'error': 'Datoteka ne obstaja',
            'time': time.time() - start_time
        }

    try:
        # Process image
        with Image.open(file_path) as image:
            processed_image = preprocess_image(image.copy())
            text = pytesseract.image_to_string(
                processed_image,
                lang='slv+eng',
                config='--psm 6 --oem 3'
            )

        # Extract information using the same logic
        date = extract_date_worker(text)
        entity = extract_name_worker(text)

        # Generate new filename
        new_name = FILENAME_TEMPLATE.format(date=date, entity=entity)
        new_path = os.path.join(os.path.dirname(file_path), new_name)

        # Handle file conflicts
        if os.path.exists(new_path):
            base, ext = os.path.splitext(new_path)
            counter = 1
            while os.path.exists(new_path) and counter <= 100:
                new_path = f"{base}_{counter}{ext}"
                counter += 1
            if counter > 100:
                new_path = f"{base}_{int(time.time()*1000)%10000}{ext}"

        # Rename file
        os.rename(file_path, new_path)

        processing_time = time.time() - start_time
        return {
            'success': True,
            'original': filename,
            'new_name': os.path.basename(new_path),
            'time': processing_time,
            'date': date,
            'entity': entity,
            'text_preview': text[:200] + '...' if len(text) > 200 else text
        }

    except Exception as e:
        processing_time = time.time() - start_time
        return {
            'success': False,
            'original': filename,
            'error': str(e),
            'time': processing_time
        }

def extract_date_worker(text):
    """Worker function for date extraction"""
    current_date = datetime.today().strftime("%d-%m-%Y")

    for i, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(text)
        if match:
            if i == 0:
                return f"{match.group(1).zfill(2)}-{match.group(2).zfill(2)}-{match.group(3)}"
            elif i == 1:
                return f"{match.group(3).zfill(2)}-{match.group(2).zfill(2)}-{match.group(1)}"
            else:
                month_num = MONTH_MAP.get(match.group(2).lower(), '01')
                return f"{match.group(1).zfill(2)}-{month_num}-{match.group(3)}"

    return current_date

def extract_name_worker(text):
    """Worker function for name extraction"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Check lines with name indicators first
    for i, line in enumerate(lines[:20]):
        line_lower = line.lower()
        for indicator in NAME_INDICATORS:
            if indicator in line_lower:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    name = extract_name_from_text_worker(parts[1].strip())
                    if name != "NEZNANO_IME":
                        return name

                if i + 1 < len(lines):
                    name = extract_name_from_text_worker(lines[i + 1])
                    if name != "NEZNANO_IME":
                        return name

    # Check first 15 lines
    for line in lines[:15]:
        name = extract_name_from_text_worker(line)
        if name != "NEZNANO_IME":
            return name

    # Check last 8 lines
    for line in lines[-8:]:
        name = extract_name_from_text_worker(line)
        if name != "NEZNANO_IME":
            return name

    return "NEZNANO_IME"

def extract_name_from_text_worker(text):
    """Worker helper function to extract name from text"""
    for pattern in NAME_PATTERNS:
        match = pattern.match(text)
        if match:
            if len(match.groups()) >= 3 and match.group(3):
                return f"{match.group(1)}_{match.group(3)}_{match.group(2)}"
            return f"{match.group(1)}_{match.group(2)}"
    return "NEZNANO_IME"