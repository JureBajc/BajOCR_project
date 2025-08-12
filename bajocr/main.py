import os
import sys
import logging
import multiprocessing
from typing import Optional
import pytesseract
from .config import Config
from .core import BajOCR
from .utils import setup_logging

# Initialize logging immediately
setup_logging(log_level=logging.INFO)
logger = logging.getLogger(__name__)

def prompt_int(prompt: str, default: int, min_val: int = 1, max_val: Optional[int] = None) -> int:
    """Read an int within bounds from console."""
    while True:
        resp = input(f"{prompt} [{default}]: ").strip()
        if not resp:
            return default
        try:
            val = int(resp)
            if val < min_val or (max_val and val > max_val):
                raise ValueError
            return val
        except ValueError:
            print(f"Vnesi število med {min_val} in {max_val or '∞'}.")

def konfiguriraj(cfg: Config) -> Config:
    """Config menu json nastavitve"""
    print("\n--- Konfiguriraj BajOCR ---")
    # Tesseract path
    path = input(f"Pot do Tesseract.exe [{cfg.tesseract_path or 'ni nastavljeno'}]: ").strip()
    if path:
        if os.path.exists(path):
            cfg.tesseract_path = path
            pytesseract.pytesseract.tesseract_cmd = path
        else:
            print("Datoteka ne obstaja, obdrži prejšnjo vrednost.")
    # Max workers
    max_cpu = multiprocessing.cpu_count()
    cfg.max_workers = prompt_int("Število procesov", cfg.max_workers, min_val=1, max_val=max_cpu)
    # OCR language
    lang = input(f"Jezik Tesseract (npr. 'eng' ali 'slv+eng') [{cfg.ocr_lang}]: ").strip()
    if lang:
        cfg.ocr_lang = lang
    # Scan folder
    folder = input(f"Mapa za skeniranje [{cfg.scan_folder or 'ni nastavljena'}]: ").strip()
    if folder:
        if os.path.isdir(folder):
            cfg.scan_folder = folder
        else:
            print("Mapa ne obstaja, obdrži prejšnjo vrednost.")

    # Extra args
    extra = input(f"Dodatni argumenti za Tesseract (ločeni z vejico) [{','.join(cfg.extra_args)}]: ").strip()
    if extra:
        cfg.extra_args = list({arg.strip() for arg in extra.split(",") if arg.strip()})

    cfg.save()
    return cfg

def build_processor(cfg: Config) -> BajOCR:
    """Zgradi bajocr blok z config setingi"""
    pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_path
    return BajOCR(
        tesseract_path=cfg.tesseract_path,
        ocr_lang=cfg.ocr_lang,
        extra_args=cfg.extra_args,
    )
def main() -> None:
    """Glavna funkcija menija."""
    cfg = Config.load()
    processor = build_processor(cfg)

    while True:
        print("\nBajOCR PROCESSOR v1.0 (Optimized)")
        print("=" * 50)
        print(f"1. Procesiraj vse datoteke (mapa: {cfg.scan_folder or '[ni nastavljena]'})")
        print(f"2. Shrani slike kot searchable PDF (posamezne datoteke)")
        print("3. Testiraj eno datoteko")
        print("4. Prikaži config.json")
        print("5. Spremeni mapo datotek")
        print(f"6. Konfiguriraj (vse nastavitve)")
        print("7. Samodejno združi strani v dokumente (PRSTNI ODTIS)")  # NOVO
        print("0. Izhod")
        print("=" * 50)
        choice = input("Vnesi izbiro (0-7): ").strip()

        if choice == "1":
            if not cfg.scan_folder:
                print("Najprej nastavi mapo za skeniranje (opcija 6).")
            else:
                processor.process_folder_parallel(cfg.scan_folder, max_workers=cfg.max_workers)

        elif choice == "2":
            if not cfg.scan_folder:
                print("Najprej nastavi mapo za skeniranje (opcija 6).")
            else:
                processor.convert_folder_to_searchable_pdf(
                    folder_path=cfg.scan_folder,
                    lang=processor.ocr_lang,
                    extra_args=processor.extra_args,
                    max_workers=cfg.max_workers
                )

        elif choice == "3":
            if not cfg.scan_folder:
                print("Najprej nastavi mapo za skeniranje (opcija 6).")
            else:
                processor.test_single_file(cfg.scan_folder)

        elif choice == "4":
            print(f"CPU jeder: {multiprocessing.cpu_count()}")
            print(f"Priporočeno procesov: {processor.get_optimal_workers()}")
            print(f"Tesseract pot: {cfg.tesseract_path}")
            print(f"Trenutna mapa: {cfg.scan_folder}")
            print(f"Jezik OCR: {processor.ocr_lang}")
            print(f"Dodatni args: {processor.extra_args}")

        elif choice == "5":
            new_folder = input("Vnesi novo pot do mape: ").strip()
            if os.path.isdir(new_folder):
                cfg.scan_folder = new_folder
                cfg.save()
                print("Mapa uspešno nastavljena!")
            else:
                print("Mapa ne obstaja!")

        elif choice == "6":
            cfg = konfiguriraj(cfg)
            processor = build_processor(cfg)

        elif choice == "7":
            if not cfg.scan_folder:
                print("Najprej nastavi mapo za skeniranje (opcija 6).")
            else:
                processor.group_folder_to_documents(
                    folder_path=cfg.scan_folder,
                    lang=processor.ocr_lang,
                    extra_args=processor.extra_args,
                    max_workers=cfg.max_workers
                )

        elif choice == "0":
            print("Zapri")
            break
        else:
            print("Neveljavno")

        input("\nPritisni Enter za nadaljevanje...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram prekinjen s strani uporabnika.")
    except Exception as e:
        logger.critical("Kritična napaka: %s", e, exc_info=True)
        sys.exit(1)
