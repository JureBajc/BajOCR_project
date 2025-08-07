# BajOCR Processor v1.0

**BajOCR Processor** je enostavnejša, modularna verzija OCR procesorja za interno uporabo v podjetju. Projekt je razdeljen v štiri glavne komponente:

- `main.py`: interaktivni vmesnik in vodenje procesa
- `constants.py`: držanje konfiguracijskih konstant
- `core.py`: glavna logika OCR procesiranja (ekstrakcija besedila, datumov, imen)
- `utils.py`: pomožne funkcije za logiranje in predprocesiranje slik

## Tehnična zasnova

Projekt je zasnovan modularno, da omogoča enostavno vzdrževanje in razširljivost:

1. **Konfiguracija** (`constants.py`): vse ključne konstante so definirane na enem mestu:
   - `DEFAULT_TESSERACT_PATHS`: privzete poti do Tesseract-OCR
   - `FILENAME_TEMPLATE`: predloga imena preimenovanih datotek
   - `IMAGE_EXTENSIONS`: podprte končnice slik
   - `LOG_FILE`: ime log datoteke

2. **Pomožne funkcije** (`utils.py`):
   - `setup_logging(log_level)`: inicializira Python logging s prednastavljenimi handlerji
   - `preprocess_image(image)`: optimizirano predprocesiranje slike (resize, konverzija v sivinsko, kontrast, ostrina)

3. **Glavni modul** (`core.py`): implementira razred `BajOCR` s metodami:
   - `extract_date(text)`: prepozna različne formate datumov v besedilu
   - `extract_name_only(text)`: identificira in oblikuje ime podpisnika z upoštevanjem slovenskih znakov
   - `process_single_image(path)`, `process_folder_parallel(...)`: obdelava ene ali več slik hkrati z več nitmi
   - `print_summary_enhanced()`, `save_report(...)`: izpis in shranjevanje poročila o obdelavi
   - `get_optimal_workers()`: izbira števila delavcev glede na CPU jedra

4. **Vstopna točka** (`main.py`):
   - Interaktivni uporabniški meni z možnostmi za procesiranje slik, testiranje ene datoteke, prikaz sistemskih informacij, nastavitev poti do Tesseract in mape za obdelavo.
   - Uporablja `multiprocessing.cpu_count()` in `BajOCR` instanco za izvedbo.

## Zahteve

- Python 3.7+
- Tesseract-OCR z jezikovnimi paketi `slv` in `eng`
- Python knjižnice:
  ```bash
  pip install pillow pytesseract
  ```

## Namestitev

1. Klonirajte repozitorij:
   ```bash
   git clone https://github.com/vaš-uporabniški-nalog/BajOCR-Processor-v1.git
   cd BajOCR-Processor-v1
   ```
2. Ustvarite in aktivirajte virtualno okolje (priporočeno):
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/macOS
   venv\Scripts\activate    # Windows
   ```
3. Namestite odvisnosti:
   ```bash
   pip install -r requirements.txt
   ```

## Uporaba

### Kot modul v Python skripti

```python
from bajocr.core import BajOCR
# Inicializacija
processor = BajOCR(tesseract_path="/usr/bin/tesseract")
# Paralelna obdelava mape s privzetimi nastavitvami
processor.process_folder_parallel("/pot/do/mapa_s_slikami")
```

### Interaktivni način

Zaženite `main.py`:
```bash
python main.py
```
Sledite meniju za:
- Procesiranje vseh slik
- Izbiro števila delavcev
- Testiranje ene slike
- Prikaz CPU jeder in poti do Tesseract
- Spreminjanje delovne mape

## Struktura datotek

```plain
BajOCR-Processor-v1/
├── constants.py      # Konfiguracijske konstante
├── core.py           # Implementacija razreda BajOCR
├── utils.py          # Pomožne funkcije
├── main.py           # Interaktivni vmesnik
├── requirements.txt  # Seznam Python odvisnosti
└── LICENSE           # Licenca projekta
```

## Prispevanje

Prispevki so dobrodošli! Prosim za odprtje issue ali pull request za izboljšave.

## Licenca

Licencirano pod MIT licenco. Glej `LICENSE` za več informacij.

