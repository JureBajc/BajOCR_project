import json, os, time, logging, multiprocessing, re, hashlib
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import pytesseract
from PIL import Image

from .constants import (
    DEFAULT_TESSERACT_PATHS, FILENAME_TEMPLATE, IMAGE_EXTENSIONS,
    DATE_PATTERNS, NAME_PATTERNS, NAME_INDICATORS, MONTH_MAP,
    PAGE_NUMBER_PATTERNS, PAGE_BOTTOM_STRIP,
    PHASH_HASH_SIZE, PHASH_DISTANCE_THRESHOLD, HEADER_STRIP, DOC_TYPE_PATTERNS
)
from .utils import (setup_logging, preprocess_image, sanitize_filename,
                    ensure_unique_path, merge_pdfs, natural_sort_key,
                    average_hash, hamming)

_LOGGER = logging.getLogger(__name__)

# ---- Textual fingerprint helpers ----
DOC_TITLE_RE = re.compile(r'\bPOGODB[AO]\b.*', re.IGNORECASE)
COMPANY_RE   = re.compile(r'\b[A-ZČŠŽ][A-Za-zČŠŽĆĐčšžćđ0-9\-. ]+\bd\.o\.o\.\b', re.IGNORECASE)

def _normalize_key(s: str) -> str:
    s = " ".join(s.split())
    s = re.sub(r'[^A-Za-z0-9ČŠŽĆĐčšžćđ \.-]+', '', s)
    return s.lower().strip()

def extract_doc_title_worker(text: str) -> str:
    for ln in text.splitlines():
        if DOC_TITLE_RE.search(ln):
            return _normalize_key(ln)
    return "neznan_naslov"

def detect_doc_type_worker(text: str) -> str:
    """
    Heuristic document-type detector.
    Prioritizes title/header lines, then full text. Returns 'NEZNANO' if none hit.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = "\n".join(lines[:20])
    for label, rx in DOC_TYPE_PATTERNS:
        if rx.search(head):
            return label
    for label, rx in DOC_TYPE_PATTERNS:
        if rx.search(text):
            return label
    return "NEZNANO"

def extract_parties_worker(text: str) -> Optional[str]:
    comps = COMPANY_RE.findall(text)
    if not comps:
        return None
    comps = [_normalize_key(c) for c in comps[:4]]
    comps = sorted(set(comps))[:2]
    return "__".join(comps) if comps else None

def header_signature_worker(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = " ".join(lines[:20])
    head = _normalize_key(head)
    return hashlib.md5(head.encode("utf-8")).hexdigest()[:8]

# ---- Enhanced date extraction (global, used by all flows) ----
def debug_date_extraction(text: str, file_path: str = "") -> None:
    print(f"\n=== DATE EXTRACTION DEBUG for {file_path} ===")
    print(f"Text length: {len(text)} characters")
    print(f"First 500 chars:\n{text[:500]}")
    print(f"Last 500 chars:\n{text[-500:]}")
    date_keywords = ['datum', 'date', 'kraj in datum', 'dne', 'dan']
    for keyword in date_keywords:
        if keyword.lower() in text.lower():
            print(f"Found keyword '{keyword}' in text")
            idx = text.lower().find(keyword.lower())
            start = max(0, idx - 50)
            end = min(len(text), idx + 100)
            print(f"Context: ...{text[start:end]}...")
    for i, pattern in enumerate(DATE_PATTERNS):
        matches = pattern.findall(text)
        if matches:
            print(f"Pattern {i} found matches: {matches}")
        else:
            print(f"Pattern {i}: No matches")
    print("=== END DEBUG ===\n")

def extract_date_enhanced(text: str, file_path: str = "") -> Optional[str]:
    """
    Enhanced date extraction tolerant to OCR noise.
    Returns DD-MM-YYYY. Falls back to today's date if none found.
    """
    current_date = datetime.today().strftime("%d-%m-%Y")
    current_year = datetime.today().year
    max_year = current_year + 1

    # Toggle this True only when debugging (it prints a lot)
    DEBUG = False
    if DEBUG:
        debug_date_extraction(text, file_path)

    # Normalize whitespace; keep common punctuation
    cleaned_text = re.sub(r'\s+', ' ', text)
    cleaned_text = re.sub(r'[^\w\s\.,/\-:]', ' ', cleaned_text, flags=re.UNICODE)

    found_dates: List[Tuple[str, int]] = []
    for i, pattern in enumerate(DATE_PATTERNS):
        matches = pattern.findall(cleaned_text)
        for match in matches:
            try:
                if i == 0:  # DD-MM-YYYY style (any sep)
                    day, month, year = match[0], match[1], match[2]
                elif i == 1:  # YYYY-MM-DD style
                    year, month, day = match[0], match[1], match[2]
                elif i == 2:  # DD month YYYY (incl. slovene abbrev)
                    day = match[0]
                    month_name = match[1].lower()
                    year = match[2]
                    month = MONTH_MAP.get(month_name, '01')
                else:        # other flexible patterns
                    day, month, year = match[0], match[1], match[2]

                # Year normalization
                year_int = int(year)
                if len(year) == 2:
                    year_int += 1900 if year_int > 50 else 2000

                if 1900 <= year_int <= max_year:
                    month_int = int(month)
                    day_int = int(day)
                    if 1 <= month_int <= 12 and 1 <= day_int <= 31:
                        formatted = f"{day.zfill(2)}-{month.zfill(2)}-{str(year_int)}"
                        found_dates.append((formatted, year_int))
            except (ValueError, IndexError):
                continue

    if found_dates:
        found_dates.sort(key=lambda x: x[1], reverse=True)  # prefer most recent year
        return found_dates[0][0]

    return current_date

def preprocess_image_for_date(image: Image.Image) -> Image.Image:
    """Special preprocessing for date subregions to help OCR."""
    try:
        if image.mode != 'L':
            image = image.convert('L')
        w, h = image.size
        if w < 200 or h < 50:
            scale = max(200 / max(1, w), 50 / max(1, h))
            image = image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        from PIL import ImageEnhance
        image = ImageEnhance.Contrast(image).enhance(2.0)
        image = ImageEnhance.Sharpness(image).enhance(1.8)
        return image
    except Exception as e:
        _LOGGER.error(f"Date preprocessing error: {e}")
        return image

def extract_date_with_targeted_ocr(img_path: str, full_text: str, lang: str, extra_args: list) -> str:
    """
    Global date extractor used by all flows.
    1) Try enhanced regex on full OCR text.
    2) If that fails or returns today's default, try multiple likely image regions with varied PSM.
    """
    date = extract_date_enhanced(full_text, img_path)
    today_str = datetime.today().strftime("%d-%m-%Y")
    if date and date != today_str:
        return date

    try:
        with Image.open(img_path) as img:
            w, h = img.size
            regions_to_try = [
                ("bottom_right", (int(w * 0.5), int(h * 0.7), w, h)),          # signatures area
                ("top_right",    (int(w * 0.5), 0, w, int(h * 0.3))),         # header dates
                ("bottom_left",  (0, int(h * 0.7), int(w * 0.5), h)),         # alt signature area
                ("center_bottom",(int(w * 0.25), int(h * 0.6), int(w * 0.75), h)),  # middle bottom
            ]
            for region_name, crop_box in regions_to_try:
                try:
                    region = img.crop(crop_box)
                    region = preprocess_image_for_date(region)
                    configs = [
                        "--psm 6",   # block
                        "--psm 8",   # single word
                        "--psm 13",  # raw line
                        "-c tessedit_char_whitelist=0123456789./-abcdefghijklmnopqrstuvwxyz ",
                    ]
                    for config in configs:
                        try:
                            rtext = pytesseract.image_to_string(
                                region, lang=lang, config=(config + " " + " ".join(extra_args)).strip()
                            )
                            if rtext.strip():
                                possible = extract_date_enhanced(rtext, f"{img_path}_{region_name}")
                                if possible and possible != today_str:
                                    return possible
                        except Exception:
                            continue
                except Exception:
                    continue
    except Exception as e:
        _LOGGER.warning(f"Targeted OCR failed for {img_path}: {e}")

    return today_str

# ---- PDF worker ----
def _convert_image_to_pdf(img_path: str, tesseract_path: Optional[str], lang: str, extra_args: List[str]) -> Tuple[str, bool, str, float]:
    start = time.time()
    try:
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        with Image.open(img_path) as img:
            processed_img = preprocess_image(img.copy())
            text = pytesseract.image_to_string(processed_img, lang=lang, config=" ".join(extra_args))
            date = extract_date_with_targeted_ocr(img_path, text, lang, extra_args)
            doc_type = detect_doc_type_worker(text)
            entity = extract_name_worker(text) or "NEZNANO_IME"

            filename_pdf = FILENAME_TEMPLATE.replace('.png', '.pdf').format(
                date=date, doc_type=doc_type, entity=entity
            )
            filename_pdf = sanitize_filename(filename_pdf)
            pdf_path = ensure_unique_path(Path(img_path).with_name(filename_pdf))

            pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                processed_img, extension='pdf', lang=lang, config=' '.join(extra_args)
            )
            with open(pdf_path, 'wb') as f:
                f.write(pdf_bytes)

        return img_path, True, str(pdf_path), time.time() - start
    except Exception as e:
        return img_path, False, str(e), 0.0

class BajOCR:
    def __init__(self, tesseract_path: Optional[str] = None, ocr_lang: str = "eng",
                 extra_args: Optional[List[str]] = None, log_level=logging.INFO):
        self.tesseract_path = self._setup_tesseract_path(tesseract_path)
        self.ocr_lang = ocr_lang or "eng"
        self.extra_args = list(extra_args or [])
        setup_logging(log_level)
        self.logger = logging.getLogger(__name__)
        self.processed_files = set()
        self._reset_stats()
        self._current_date = datetime.today().strftime("%d-%m-%Y")

    def _setup_tesseract_path(self, tesseract_path):
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            return tesseract_path
        for path in DEFAULT_TESSERACT_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return path
        return None

    def _reset_stats(self):
        self.stats = {'processed':0,'successful':0,'failed':0,'skipped':0,'start_time':None,'end_time':None}

    # ---------------------- Auto‑group to documents ----------------------
    def group_folder_to_documents(self, folder_path: str, lang: Optional[str]=None,
                                  extra_args: Optional[List[str]]=None, max_workers: Optional[int]=None,
                                  file_extensions: Optional[List[str]]=None, move_intermediate_pdfs: bool=True) -> bool:
        lang = lang or self.ocr_lang
        extra_args = list(extra_args if extra_args is not None else self.extra_args)
        exts = file_extensions or IMAGE_EXTENSIONS

        folder = Path(folder_path)
        if not folder.is_dir():
            _LOGGER.error("Folder not found: %s", folder); return False

        images = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]
        if not images:
            _LOGGER.warning("No images in folder: %s", folder); return False

        if max_workers is None:
            max_workers = self.get_optimal_workers()
        max_workers = max(1, min(max_workers, len(images), multiprocessing.cpu_count()))
        print(f"\nAnaliziram {len(images)} slik → OCR + PDF (do {max_workers} procesov)...")

        results: List[Dict[str, Any]] = []
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futs = { pool.submit(analyze_and_pdf_worker, str(img), self.tesseract_path, lang, extra_args): img for img in images }
            for fut in as_completed(futs):
                res = fut.result()
                if res.get('ok'):
                    results.append(res)
                    print(f"[OK] {Path(res['image']).name} → {Path(res['pdf']).name}  "
                          f"(grp={res.get('group','?')} | p={res.get('page') or '-'})")
                else:
                    print(f"[FAIL] {Path(res.get('image','?')).name}: {res.get('error')}")

        if not results:
            _LOGGER.error("Ni uspešnih OCR/PDF rezultatov."); return False

        # --- Hybrid grouping: textual group_id + visual header hash proximity
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for r in results:
            gid = r['group']  # textual
            hdr = r.get('header_hash')
            placed = False
            for key, arr in buckets.items():
                if arr and hdr and arr[0].get('header_hash'):
                    if hamming(hdr, arr[0]['header_hash']) <= PHASH_DISTANCE_THRESHOLD:
                        if gid.split('__')[0] == arr[0]['group'].split('__')[0]:
                            arr.append(r); placed = True; break
            if not placed:
                buckets.setdefault(gid, []).append(r)

        # sort inside buckets by page number then name
        for arr in buckets.values():
            arr.sort(key=lambda x: (x['page'] if isinstance(x['page'], int) else 10**9,
                                    natural_sort_key(Path(x['pdf']))))

        # merge, move
        made = 0
        for gid, arr in buckets.items():
            doc_folder = ensure_unique_path(folder / sanitize_filename(gid))
            doc_folder.mkdir(parents=True, exist_ok=True)
            merged = ensure_unique_path(doc_folder / (sanitize_filename(gid) + ".pdf"))
            merge_pdfs([Path(r['pdf']) for r in arr], merged)
            made += 1
            print(f"[MERGE] {merged.name} ({len(arr)} strani)")
            for r in arr:
                try:
                    if move_intermediate_pdfs:
                        Path(r['pdf']).rename(doc_folder / Path(r['pdf']).name)
                    Path(r['image']).rename(doc_folder / Path(r['image']).name)
                except Exception as e:
                    _LOGGER.warning("Move failed for %s: %s", r['image'], e)

        print(f"\nDokončano. Ustvarjenih dokumentov: {made}")
        return made > 0

    # --- Bulk convert to searchable PDF (per image) ---
    def convert_folder_to_searchable_pdf(self, folder_path: str, lang: Optional[str]=None,
                                         extra_args: Optional[List[str]]=None, max_workers: Optional[int]=None,
                                         file_extensions: Optional[List[str]]=None) -> bool:
        lang = lang or self.ocr_lang
        extra_args = list(extra_args if extra_args is not None else self.extra_args)
        folder = Path(folder_path)
        if not folder.is_dir(): _LOGGER.error("Folder not found: %s", folder); return False
        exts = file_extensions or IMAGE_EXTENSIONS
        images = [str(p) for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]
        if not images: _LOGGER.warning("No images in folder: %s", folder); return False
        workers = max_workers or None
        print(f"\nConverting {len(images)} images → PDF with up to {workers or 'all available'} processes...")
        success = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = { pool.submit(_convert_image_to_pdf, img, self.tesseract_path, lang, extra_args): img for img in images }
            for fut in as_completed(futs):
                img_path, ok, msg, elapsed = fut.result()
                name = Path(img_path).name
                if ok:
                    print(f"[OK] {name} → {Path(msg).name} ({elapsed:.2f}s)")
                    success += 1
                else:
                    print(f"[FAIL] {name}: {msg}")
        return success > 0

    def get_optimal_workers(self) -> int:
        cpu = multiprocessing.cpu_count()
        if cpu >= 8: return min(6, cpu - 2)
        if cpu >= 4: return max(2, cpu - 1)
        return max(1, cpu // 2)

    def process_folder_parallel(self, folder_path: str, max_workers: Optional[int]=None,
                                file_extensions: Optional[List[str]]=None) -> bool:
        if file_extensions is None: file_extensions = IMAGE_EXTENSIONS
        folder_path = Path(folder_path)
        if not folder_path.exists(): self.logger.error(f"Mapa ne obstaja: {folder_path}"); return False
        image_files = [f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in file_extensions]
        if not image_files: self.logger.warning(f"Ni najdenih slikovnih datotek v mapi: {folder_path}"); return False
        if max_workers is None: max_workers = self.get_optimal_workers()
        max_workers = max(1, min(max_workers, len(image_files), multiprocessing.cpu_count()))
        print(f"\nBajOCR PROCESSOR v1.0 (Optimized CPU Processing)")
        print(f"{'='*65}\nMapa: {folder_path}\nSkupno slik: {len(image_files)}\nUporabljam {max_workers} procesov hkrati\n{'='*65}")
        self.stats['start_time'] = time.time(); self.processed_files.clear()
        all_results = []; successful = failed = 0
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(process_image_worker, str(fp), self.tesseract_path, self.ocr_lang, self.extra_args): fp
                for fp in image_files
            }
            for future in as_completed(future_to_file):
                result = future.result(); all_results.append(result)
                if result.get('success'):
                    successful += 1
                    print(f"[OK]    {result['original']} → {result['new_name']} ({result['time']:.2f}s)")
                else:
                    failed += 1
                    print(f"[FAIL]  {result['original']}: {result['error']}")
        self.stats.update({'end_time': time.time(), 'processed': len(image_files), 'successful': successful, 'failed': failed})
        self.print_summary_enhanced(); self.save_report(folder_path, all_results); return successful > 0

    def print_summary_enhanced(self):
        total_time = self.stats['end_time'] - self.stats['start_time']
        avg = total_time / self.stats['processed'] if self.stats['processed'] > 0 else 0
        rate = (self.stats['successful'] / self.stats['processed'] * 100) if self.stats['processed'] > 0 else 0
        print(f"\nPOVZETEK PROCESIRANJA\n{'='*50}\nSkupni čas: {total_time:.1f}s\nPovprečni čas na datoteko: {avg:.2f}s\nUspešno: {self.stats['successful']}\nNeuspešno: {self.stats['failed']}\nUspešnost: {rate:.1f}%\n{'='*50}")

    def save_report(self, folder_path, results):
        report = {'timestamp': datetime.now().isoformat(), 'folder': str(folder_path), 'statistics': self.stats, 'results': results}
        report_path = folder_path / f"ocr_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_path, 'w', encoding='utf-8') as f: json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Poročilo shranjeno: {report_path}")
            print(f"Poročilo shranjeno: {report_path}")
        except Exception as e:
            self.logger.error(f"Napaka pri shranjevanju poročila: {e}")

    def test_single_file(self, folder_path):
        folder_path = Path(folder_path); test_file = None
        for ext in IMAGE_EXTENSIONS:
            files = list(folder_path.glob(f"*{ext}")) + list(folder_path.glob(f"*{ext.upper()}"))
            if files: test_file = files[0]; break
        if not test_file: print("Ni najdenih slikovnih datotek za test."); return
        print(f"\nTESTIRANJE ENE DATOTEKE\n{'='*40}\nTestiram: {test_file.name}")
        self.processed_files.clear()
        result = self.process_single_image(str(test_file), self.ocr_lang, self.extra_args)
        if result.get('success'):
            print("USPEH")
            print(f"   Originalno ime: {result['original']}")
            print(f"   Novo ime: {result['new_name']}")
            print(f"   Datum: {result['date']}")
            print(f"   Ime osebe: {result['entity']}")
            print(f"   Tip dokumenta: {result['doc_type']}")
            print(f"   Čas procesiranja: {result['time']:.2f}s")
            print("   CELOTNO OCR BESEDILO:")
            print(f"   {'-'*30}")
            print(result.get('ocr_text', '[OCR text ni na voljo]'))

            # Save JSON alongside the image
            json_path = Path(test_file).with_suffix(".ocr.json")
            try:
                with open(json_path, "w", encoding="utf-8") as jf:
                    json.dump(result, jf, ensure_ascii=False, indent=2)
                print(f"\nOCR JSON shranjen v: {json_path}")
            except Exception as e:
                print(f"NAPAKA pri shranjevanju OCR JSON: {e}")
        else:
            print(f"NAPAKA: {result.get('error')}")

    def process_single_image(self, file_path: str, lang: Optional[str]=None, extra_args: Optional[List[str]]=None):
        return process_image_worker(file_path, self.tesseract_path, lang or self.ocr_lang,
                                    list(extra_args if extra_args is not None else self.extra_args))

# ---- Workers ----
def analyze_and_pdf_worker(file_path, tesseract_path=None, lang="eng", extra_args=None):
    if extra_args is None: extra_args = []
    start = time.time()
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    else:
        for path in DEFAULT_TESSERACT_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path; break
    try:
        with Image.open(file_path) as im:
            prep = preprocess_image(im.copy())
            text = pytesseract.image_to_string(prep, lang=lang, config=" ".join(extra_args))

            doc_type = detect_doc_type_worker(text)
            title = extract_doc_title_worker(text)
            parties = extract_parties_worker(text)
            sig = header_signature_worker(text)

            entity = extract_name_worker(text)
            if not entity or entity == "NEZNANO_IME":
                entity = parties or "NEZNANO_IME"

            date = extract_date_with_targeted_ocr(file_path, text, lang, extra_args)
            group_id = _normalize_key(f"{doc_type}__{title}__{parties or entity}__{sig}")

            # header visual hash
            w, h = prep.size
            header_box = (0, 0, w, int(h * HEADER_STRIP))
            header_img = prep.crop(header_box)
            header_hash = average_hash(header_img, PHASH_HASH_SIZE)

            # page number (bottom strip OCR)
            page_no = extract_page_number_worker(text)
            if page_no is None:
                bh = int(h * PAGE_BOTTOM_STRIP)
                bottom_box = (0, h - bh, w, h)
                bottom_img = prep.crop(bottom_box)
                tsv = pytesseract.image_to_data(bottom_img, lang=lang, config=" ".join(extra_args),
                                                output_type=pytesseract.Output.DATAFRAME)
                try:
                    digits = [int(str(x)) for x in tsv['text'].fillna('') if str(x).strip().isdigit() and 1 <= len(str(x).strip()) <= 3]
                    if digits:
                        page_no = digits[-1]
                except Exception:
                    pass

            # build single-page searchable PDF
            pdf_name = sanitize_filename(f"{date}_{entity}_{Path(file_path).stem}.pdf")
            pdf_path = ensure_unique_path(Path(file_path).with_name(pdf_name))
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(prep, extension='pdf', lang=lang, config=' '.join(extra_args))
            with open(pdf_path, 'wb') as f: f.write(pdf_bytes)

        return {'ok': True, 'image': str(file_path), 'pdf': str(pdf_path),
                'date': date, 'entity': entity, 'doc_type': doc_type,
                'page': page_no, 'group': group_id, 'header_hash': header_hash,
                'time': time.time() - start}
    except Exception as e:
        return {'ok': False, 'image': str(file_path), 'error': str(e), 'time': time.time() - start}

def process_image_worker(file_path, tesseract_path=None, lang="eng", extra_args=None):
    if extra_args is None:
        extra_args = []
    start_time = time.time()
    filename = os.path.basename(file_path)

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    else:
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
        with Image.open(file_path) as image:
            prep = preprocess_image(image.copy())
            text = pytesseract.image_to_string(prep, lang=lang, config=" ".join(extra_args))

        doc_type = detect_doc_type_worker(text)
        date = extract_date_with_targeted_ocr(file_path, text, lang, extra_args)
        entity = extract_name_worker(text)

        from .constants import FILENAME_TEMPLATE
        new_name = sanitize_filename(FILENAME_TEMPLATE.format(date=date, doc_type=doc_type, entity=entity))
        new_path = ensure_unique_path(Path(file_path).with_name(new_name))
        os.rename(file_path, new_path)

        return {
            'success': True,
            'original': filename,
            'new_name': os.path.basename(new_path),
            'time': time.time() - start_time,
            'date': date,
            'entity': entity,
            'ocr_text': text,
            'doc_type': doc_type
        }

    except Exception as e:
        return {
            'success': False,
            'original': filename,
            'error': str(e),
            'time': time.time() - start_time
        }

# ---- Name & page number extractors ----
def extract_name_worker(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines[:20]):
        ll = line.lower()
        for ind in NAME_INDICATORS:
            if ind in ll:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    name = extract_name_from_text_worker(parts[1].strip())
                    if name != "NEZNANO_IME": return name
                if i + 1 < len(lines):
                    name = extract_name_from_text_worker(lines[i + 1])
                    if name != "NEZNANO_IME": return name
    for line in lines[:15]:
        name = extract_name_from_text_worker(line)
        if name != "NEZNANO_IME": return name
    for line in lines[-8:]:
        name = extract_name_from_text_worker(line)
        if name != "NEZNANO_IME": return name
    return "NEZNANO_IME"

def extract_name_from_text_worker(text):
    for pattern in NAME_PATTERNS:
        m = pattern.match(text)
        if m:
            if len(m.groups()) >= 3 and m.group(3):
                return f"{m.group(1)}_{m.group(3)}_{m.group(2)}"
            return f"{m.group(1)}_{m.group(2)}"
    return "NEZNANO_IME"

def extract_page_number_worker(text: str) -> Optional[int]:
    for pat in PAGE_NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            try: return int(m.group(1))
            except Exception: pass
    return None