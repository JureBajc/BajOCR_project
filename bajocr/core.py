import sys
import pytesseract
from PIL import Image
import os
import re
import time
import json
import threading
import logging
import multiprocessing
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageEnhance
from .constants import DEFAULT_TESSERACT_PATHS, FILENAME_TEMPLATE, IMAGE_EXTENSIONS
from .utils import setup_logging, preprocess_image



class BajOCR:
    """
    BAJO-grade OCR processor za interno uporabo v podjetju
    """
    
    def __init__(self, tesseract_path=None, log_level=logging.INFO):
        #Nastavi Tesseract path
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        else:
            default_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',   #Windows
                '/usr/bin/tesseract',  #Linux
                '/opt/homebrew/bin/tesseract'  #macOS
            ]
            for path in default_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break
        #Nastavi loging
        setup_logging(log_level)
        self.logger = logging.getLogger(__name__)
        #Format datoteke
        self.filename_template = "{date}_{entity}.png"
        #Thread-safe lock za file operations
        self.file_lock = threading.Lock()
        self.processed_files = set()
        self.stats = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'start_time': None,
            'end_time': None
        }

    def setup_logging(self, log_level):
        """Nastavi logging sistemc"""
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ocr_processor.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def preprocess_image(self, image):
        """Optimizirano predprocesiranje slike"""
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
            self.logger.error(f"Napaka pri predprocesiranju slike: {e}")
            return image

    def extract_date(self, text):
        """Izvleče datum iz besedila z več vzorci"""
        patterns = [
            r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})',
            r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})',
            r'(\d{1,2})\s+(januar|februar|marec|april|maj|junij|julij|avgust|september|oktober|november|december)\s+(\d{4})',
        ]
        month_map = {
            'januar': '01', 'februar': '02', 'marec': '03', 'april': '04',
            'maj': '05', 'junij': '06', 'julij': '07', 'avgust': '08',
            'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
        }
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if i == 0:
                    return f"{match.group(1).zfill(2)}-{match.group(2).zfill(2)}-{match.group(3)}"
                elif i == 1:
                    return f"{match.group(3).zfill(2)}-{match.group(2).zfill(2)}-{match.group(1)}"
                else:
                    month_num = month_map.get(match.group(2).lower(), '01')
                    return f"{match.group(1).zfill(2)}-{month_num}-{match.group(3)}"
        return datetime.today().strftime("%d-%m-%Y")

    def extract_name_only(self, text):
        """Izboljšana dobivanj imena"""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        name_patterns = [
            r'^([A-ZČŠŽĆĐ][a-zčšžćđ]+)\s+([A-ZČŠŽĆĐ][a-zčšžćđ]+)(?:\s+([A-ZČŠŽĆĐ][a-zčšžćđ]+))?$',
            r'^([A-ZČŠŽĆĐ]{2,})\s+([A-ZČŠŽĆĐ]{2,})$',
        ]
        name_indicators = [
            'priimek in ime', 'ime in priimek', 'ime:', 'priimek:',
            'podpisnik', 'podpisuje', 'izvršitelj', 'direktor', 'vodja'
        ]
        for i, line in enumerate(lines[:20]):
            for indicator in name_indicators:
                if indicator in line.lower():
                    parts = re.split(r'[:]\s*', line, 1)
                    if len(parts) > 1:
                        for pattern in name_patterns:
                            match = re.match(pattern, parts[1].strip())
                            if match:
                                if match.group(3):
                                    return f"{match.group(1)}_{match.group(3)}_{match.group(2)}"
                                return f"{match.group(1)}_{match.group(2)}"
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        for pattern in name_patterns:
                            match = re.match(pattern, next_line)
                            if match:
                                if match.group(3):
                                    return f"{match.group(1)}_{match.group(3)}_{match.group(2)}"
                                return f"{match.group(1)}_{match.group(2)}"
        for line in lines[:15]:
            for pattern in name_patterns:
                match = re.match(pattern, line)
                if match:
                    if match.group(3):
                        return f"{match.group(1)}_{match.group(3)}_{match.group(2)}"
                    return f"{match.group(1)}_{match.group(2)}"
        for line in lines[-8:]:
            for pattern in name_patterns:
                match = re.match(pattern, line)
                if match:
                    if match.group(3):
                        return f"{match.group(1)}_{match.group(3)}_{match.group(2)}"
                    return f"{match.group(1)}_{match.group(2)}"
        return "NEZNANO_IME"

    def is_file_available(self, file_path):
        """Preveri ali je datoteka dostopna"""
        with self.file_lock:
            file_str = str(file_path)
            if file_str in self.processed_files:
                return False
            if not os.path.exists(file_path):
                return False
            self.processed_files.add(file_str)
            return True

    def process_single_image(self, file_path):
        """Procesiraj eno sliko - thread-safe različica"""
        start_time = time.time()
        filename = os.path.basename(file_path)
        if not self.is_file_available(file_path):
            return {'success': False, 'original': filename, 'error': 'Datoteka je že bila procesirana ali ni dostopna', 'time': time.time() - start_time}
        try:
            with Image.open(file_path) as image:
                processed_image = self.preprocess_image(image.copy())
                text = pytesseract.image_to_string(processed_image, lang='slv+eng', config='--psm 6 --oem 3')
            date = self.extract_date(text)
            entity = self.extract_name_only(text)
            new_name = self.filename_template.format(date=date, entity=entity)
            new_path = os.path.join(os.path.dirname(file_path), new_name)
            with self.file_lock:
                counter = 1
                base, ext = os.path.splitext(new_path)
                while os.path.exists(new_path):
                    new_path = f"{base}_{counter}{ext}"
                    counter += 1
                    if counter > 100:
                        new_path = f"{base}_{int(time.time()*1000)%10000}{ext}"
                        break
                try:
                    os.rename(file_path, new_path)
                except (PermissionError, FileNotFoundError) as e:
                    self.processed_files.discard(str(file_path))
                    return {'success': False, 'original': filename, 'error': f'Napaka pri preimenovanju: {str(e)}', 'time': time.time() - start_time}
            processing_time = time.time() - start_time
            result = {'success': True, 'original': filename, 'new_name': os.path.basename(new_path), 'time': processing_time, 'date': date, 'entity': entity, 'text_preview': text[:200] + '...' if len(text) > 200 else text}
            self.logger.info(f"Uspešno procesiran: {filename} -> {os.path.basename(new_path)}")
            return result
        except Exception as e:
            with self.file_lock:
                self.processed_files.discard(str(file_path))
            processing_time = time.time() - start_time
            self.logger.error(f"Napaka pri procesiranju {filename}: {e}")
            return {'success': False, 'original': filename, 'error': str(e), 'time': processing_time}

    def get_optimal_workers(self):
        """Določi optimalno število delavcev glede na sistem"""
        cpu_count = multiprocessing.cpu_count()
        if cpu_count >= 8:
            return min(6, cpu_count - 2)
        elif cpu_count >= 4:
            return max(2, cpu_count - 1)
        else:
            return max(1, cpu_count // 2)

    def process_folder_parallel(self, folder_path, max_workers=None, file_extensions=None):
        """Paralelno procesiranje vseh slik kot posameznih opravil"""
        if file_extensions is None:
            file_extensions = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']
        folder_path = Path(folder_path)
        if not folder_path.exists():
            self.logger.error(f"Mapa ne obstaja: {folder_path}")
            return False
        image_files = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in file_extensions
        ]
        if not image_files:
            self.logger.warning(f"Ni najdenih slikovnih datotek v mapi: {folder_path}")
            return False
        if max_workers is None:
            max_workers = self.get_optimal_workers()
        max_workers = max(1, min(max_workers, len(image_files)))
        print(f"\nBajOCR PROCESSOR v1.0 (File-level paralelizacija)")
        print(f"{('=' * 65)}")
        print(f"Mapa: {folder_path}")
        print(f"Skupno slik: {len(image_files)}")
        print(f"Uporabljam {max_workers} delavcev (nit) hkrati")
        print(f"{('=' * 65)}")
        self.stats['start_time'] = time.time()
        self.processed_files.clear()
        all_results = []
        successful = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(self.process_single_image, str(fp)): fp for fp in image_files}
            for future in as_completed(future_to_file):
                result = future.result()
                all_results.append(result)
                if result.get('success'):
                    successful += 1
                    print(f"[OK]    {result['original']} → {result['new_name']} ({result['time']:.2f}s)")
                else:
                    failed += 1
                    print(f"[FAIL]  {result['original']}: {result['error']}")
        self.stats.update({'end_time': time.time(), 'processed': len(image_files), 'successful': successful, 'failed': failed})
        self.print_summary_enhanced()
        self.save_report(folder_path, all_results)
        return successful > 0

    def print_summary_enhanced(self):
        """Izpiši povzetek rezultatov"""
        total_time = self.stats['end_time'] - self.stats['start_time']
        avg_time = total_time / self.stats['processed'] if self.stats['processed'] > 0 else 0
        success_rate = (self.stats['successful'] / self.stats['processed'] * 100) if self.stats['processed'] > 0 else 0
        print(f"\nPOVZETEK PROCESIRANJA")
        print(f"{('=' * 50)}")
        print(f"Skupni čas: {total_time:.1f}s")
        print(f"Povprečni čas na datoteko: {avg_time:.2f}s")
        print(f"Uspešno procesiranih: {self.stats['successful']}")
        print(f"Neuspešnih: {self.stats['failed']}")
        print(f"Stopnja uspešnosti: {success_rate:.1f}%")
        if self.stats['failed'] > self.stats['successful']:
            print("PRIPOROČILO: Visoka stopnja napak - poskusite z manj delavci")
        elif success_rate > 95:
            print("ODLIČNO: Zelo visoka stopnja uspešnosti!")
        print(f"{('=' * 50)}")

    def save_report(self, folder_path, results):
        """Shrani podrobno poročilo"""
        report = {'timestamp': datetime.now().isoformat(), 'folder': str(folder_path), 'statistics': self.stats, 'results': results, 'worker_distribution': {}}
        for result in results:
            worker_id = result.get('worker_id', 0)
            if worker_id not in report['worker_distribution']:
                report['worker_distribution'][worker_id] = {'successful': 0, 'failed': 0}
            if result.get('success'):
                report['worker_distribution'][worker_id]['successful'] += 1
            else:
                report['worker_distribution'][worker_id]['failed'] += 1
        report_path = folder_path / f"ocr_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Poročilo shranjeno: {report_path}")
            print(f"Poročilo shranjeno: {report_path}")
        except Exception as e:
            self.logger.error(f"Napaka pri shranjevanju poročila: {e}")

    def test_single_file(self, folder_path):
        """Test ene datoteke z podrobnostmi"""
        folder_path = Path(folder_path)
        extensions = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']
        test_file = None
        for ext in extensions:
            files = list(folder_path.glob(f"*{ext}")) + list(folder_path.glob(f"*{ext.upper()}"))
            if files:
                test_file = files[0]
                break
        if not test_file:
            print("Ni najdenih slikovnih datotek za test.")
            return
        print(f"\nTESTIRANJE ENE DATOTEKE")
        print(f"{('=' * 40)}")
        print(f"Testiram: {test_file.name}")
        self.processed_files.clear()
        result = self.process_single_image(str(test_file))
        if result.get('success'):
            print("USPEH!")
            print(f"   Originalno ime: {result['original']}")
            print(f"   Novo ime: {result['new_name']}")
            print(f"   Datum: {result['date']}")
            print(f"   Ime osebe: {result['entity']}")
            print(f"   Čas procesiranja: {result['time']:.2f}s")
            print("   Predogled besedila:")
            print(f"   {('-' * 30)}")
            print(f"   {result['text_preview']}")
        else:
            print(f"NAPAKA: {result.get('error')}")


def interactive_menu():
    """Interaktivni meni"""
    processor = BajOCR()
    while True:
        print(f"\nBajOCR PROCESSOR v1.0")
        print(f"{('=' * 50)}")
        print("1. Procesiraj vse datoteke")
        print("2. Procesiraj z izbiro števila delavcev")
        print("3. Testiraj eno datoteko")
        print("4. Prikaži sistemske informacije")
        print("5. Nastavi pot do Tesseract")
        print("6. Spremeni mapo za procesiranje")
        print("0. Izhod")
        print(f"{('=' * 50)}")
        choice = input("Vnesi izbiro (0-6): ").strip()
        if 'scan_folder' not in locals():
            scan_folder = input("Vnesi pot do mape s slikami: ").strip() or r"C:\Users\praktikant\Desktop\pyTest\TestData"
        if choice == "1":
            print("Procesiranje z optimalnim številom delavcev...")
            processor.process_folder_parallel(scan_folder)
        elif choice == "2":
            max_cpu = multiprocessing.cpu_count()
            optimal = processor.get_optimal_workers()
            print(f"CPU jeder: {max_cpu}, Priporočeno: {optimal}")
            try:
                workers = int(input(f"Vnesi število delavcev (1-{max_cpu}): "))
                workers = max(1, min(workers, max_cpu))
                processor.process_folder_parallel(scan_folder, max_workers=workers)
            except ValueError:
                print("Neveljavna vrednost!")
        elif choice == "3":
            processor.test_single_file(scan_folder)
        elif choice == "4":
            print(f"CPU jeder: {multiprocessing.cpu_count()}")
            print(f"Priporočeno delavcev: {processor.get_optimal_workers()}")
            print(f"Tesseract pot: {pytesseract.pytesseract.tesseract_cmd}")
            print(f"Trenutna mapa: {scan_folder}")
        elif choice == "5":
            new_path = input("Vnesi novo pot do Tesseract: ").strip()
            if os.path.exists(new_path):
                pytesseract.pytesseract.tesseract_cmd = new_path
                print("Pot uspešno nastavljena!")
            else:
                print("Datoteka ne obstaja!")
        elif choice == "6":
            new_folder = input("Vnesi novo pot do mape: ").strip()
            if os.path.exists(new_folder):
                scan_folder = new_folder
                print("Mapa uspešno nastavljena!")
            else:
                print("Mapa ne obstaja!")
        elif choice == "0":
            print("Nasvidenje!")
            break
        else:
            print("Neveljavna izbira!")
        input("\nPritisni Enter za nadaljevanje...")

if __name__ == "__main__":
    try:
        interactive_menu()
    except KeyboardInterrupt:
        print("\n\nProgram prekinjen s strani uporabnika.")
    except Exception as e:
        print(f"Kritična napaka: {e}")
        logging.exception("Kritična napaka v glavnem programu")