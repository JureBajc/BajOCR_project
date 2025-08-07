import sys
from bajocr.core import BajOCR
import multiprocessing
import os
import pytesseract
from pathlib import Path

def interactive_menu():
    processor = BajOCR()
    scan_folder = None
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
        if not scan_folder:
            scan_folder = input("Vnesi pot do mape s slikami: ").strip() or r"C:\Users\praktikant\Desktop\pyTest\TestData"
        if choice == "1":
            processor.process_folder_parallel(scan_folder)
        elif choice == "2":
            max_cpu = multiprocessing.cpu_count()
            optimal = processor.get_optimal_workers()
            print(f"CPU jeder: {max_cpu}, Priporočeno: {optimal}")
            try:
                workers = int(input(f"Vnesi število delavcev (1-{max_cpu}): "))
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
