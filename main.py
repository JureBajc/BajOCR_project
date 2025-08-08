"""CLI entry-point for BajOCR (PDF export)."""
from __future__ import annotations

import logging
from pathlib import Path

from bajocr.core import BajOCR
from bajocr.constants import DEFAULT_SCAN_FOLDER  # optional convenience


def interactive_menu() -> None:
    """Interactive terminal menu for OCR operations (with PDF export)."""
    processor = BajOCR()
    scan_folder: Path = DEFAULT_SCAN_FOLDER  # change if you want

    while True:
        print("\nBajOCR PROCESSOR v1.2 (PDF)")
        print("=" * 60)
        print("1. Procesiraj vse datoteke (tekst OCR)")
        print("2. Procesiraj z izbiro števila delavcev (tekst OCR)")
        print("3. Testiraj eno datoteko (tekst OCR)")
        print("4. Nastavi pot do Tesseract")
        print("5. Nastavi mapo za skeniranje")
        print("6. Pokaži trenutno konfiguracijo")
        print("7. Izvozi mapo v PDF (searchable)  ← NOVO")
        print("0. Izhod")

        choice = input("\nIzbira: ").strip()
        try:
            if choice == "1":
                if not scan_folder.exists():
                    print("Najprej nastavi mapo (opcija 5)."); continue
                results = processor.process_folder(scan_folder)
                print(f"Opravljen OCR za {len(results)} datotek.")
            elif choice == "2":
                if not scan_folder.exists():
                    print("Najprej nastavi mapo (opcija 5)."); continue
                try:
                    workers = int(input("Število delavcev: ").strip())
                except ValueError:
                    print("Neveljavno število."); continue
                results = processor.process_folder(scan_folder, workers=workers)
                print(f"Opravljen OCR za {len(results)} datotek.")
            elif choice == "3":
                p = Path(input("Vnesi pot do slike: ").strip())
                if not p.exists():
                    print("Datoteka ne obstaja."); continue
                res = processor.process_file(p)
                print("\n=== REZULTAT OCR ===\n")
                print(res.text)
                print("\n====================\n")
            elif choice == "4":
                tpath = input("Vnesi pot do Tesseract (Enter za preklic): ").strip()
                if not tpath:
                    print("Preklicano."); continue
                processor = BajOCR(tesseract_path=tpath, lang=processor.lang)
                print(f"Nastavljeno: {processor.tesseract_cmd}")
            elif choice == "5":
                p = Path(input("Vnesi pot do mape: ").strip())
                if not p.exists() or not p.is_dir():
                    print("Mapa ne obstaja."); continue
                scan_folder = p
                print(f"Nastavljena mapa: {scan_folder}")
            elif choice == "6":
                print("\n--- KONFIGURACIJA ---")
                print(f"Mapa: {scan_folder or '[ni nastavljena]'}")
                print(f"Tesseract: {processor.tesseract_cmd or '[ni najden]'}")
                print(f"Jezik: {processor.lang}")
                print("---------------------")
            elif choice == "7":
                if not scan_folder.exists():
                    print("Najprej nastavi mapo (opcija 5)."); continue
                out = input("Izhodni .pdf (npr. ocr_export.pdf): ").strip() or "ocr_export.pdf"
                lang = input(f"Jezik (privzeto {processor.lang}): ").strip() or processor.lang
                psm = int(input("PSM (privzeto 6): ").strip() or "6")
                oem = int(input("OEM 0/1/2/3 (privzeto 1): ").strip() or "1")
                w = input("Število delavcev (Enter za samodejno): ").strip()
                workers = int(w) if w else None
                processor.lang = lang
                try:
                    result = processor.export_folder_to_pdf(
                        scan_folder, out, workers=workers, psm=psm, oem=oem
                    )
                    print(f"Ustvarjeno: {result.resolve()}")
                except Exception as exc:
                    print(f"Napaka pri izvozu: {exc}")
            elif choice == "0":
                print("Nasvidenje!")
                break
            else:
                print("Neveljavna izbira!")
        except KeyboardInterrupt:
            print("\nPreklicano s strani uporabnika.")
        except Exception as exc:
            logging.exception("Kritična napaka")
            print(f"Kritična napaka: {exc}")
        input("\nPritisni Enter za nadaljevanje...")


if __name__ == "__main__":
    interactive_menu()