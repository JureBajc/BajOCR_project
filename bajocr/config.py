import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional
from .constants import DEFAULT_TESSERACT_PATHS

_LOGGER = logging.getLogger(__name__)
_CONFIG_FILE = Path("config.json")

@dataclass
class Config:
    """Persistent configuration for BajOCR processor."""
    tesseract_path: Optional[str] = None
    max_workers: int = 1
    ocr_lang: str = "eng"
    scan_folder: str = ""
    extra_args: List[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Config":
        """
        Naloži konfiguracijo iz datoteke ali uporabi privzete nastavitve.

        Če datoteka ne obstaja, uporabi prvi veljaven Tesseract path število jeder CPU
        za procesiranje in prazno mapo za skeniranje
        """
        if _CONFIG_FILE.exists():
            try:
                data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                cfg = cls(**data)
                _LOGGER.info("Configuration loaded from %s", _CONFIG_FILE)
                return cfg
            except Exception as e:
                _LOGGER.error("Failed to load config: %s", e)
        # Fallback defaults
        valid = next((p for p in DEFAULT_TESSERACT_PATHS if Path(p).exists()), None)
        import multiprocessing
        return cls(
            tesseract_path=valid,
            max_workers=multiprocessing.cpu_count(),
            ocr_lang="eng",
            scan_folder="",
            extra_args=[],
        )

    def save(self) -> None:
        """Shrane trenutn config JSON"""
        try:
            _CONFIG_FILE.write_text(
                json.dumps(asdict(self), indent=2),
                encoding="utf-8"
            )
            _LOGGER.info("Configuration saved to %s", _CONFIG_FILE)
        except Exception as e:
            _LOGGER.error("Failed to save config: %s", e)