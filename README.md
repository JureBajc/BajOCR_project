
# BajOCR Project

**BajOCR** is an internal-use Python-based OCR processor designed to scan image files, extract relevant metadata (date, name, etc.), and convert images to searchable PDF files.

## Features

- Detects dates and full names using OCR and regex
- Automatically renames image files based on content
- Batch image processing with parallelization
- Converts individual images to searchable PDFs
- Language customization for Tesseract OCR
- Interactive CLI menu for setup and testing
- Configurable via `config.json`

## Requirements

- Python 3.8+
- Tesseract OCR installed and accessible via path

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

The application uses a `config.json` file to store persistent settings, including:
- Tesseract path
- Max parallel workers
- OCR language
- Input folder for processing

You can configure these via the interactive menu or edit the JSON file directly.

## Usage

Start the processor via terminal:

```bash
python -m bajocr.main
```

Menu options include:
- Process all files in a folder
- Convert images to searchable PDFs
- Test processing a single image
- Configure system settings interactively

## File Naming Convention

Processed files are renamed using the format:

```
DD-MM-YYYY_Ime_Priimek[_Dodatno].png
```

Searchable PDFs maintain this naming scheme.

## Folder Structure

```
bajocr/
├── __init__.py
├── config.py
├── constants.py
├── core.py
├── main.py
├── utils.py
```

## License

This project is for internal company use and is not licensed for public distribution.

---

© 2025 BajOCR Team
