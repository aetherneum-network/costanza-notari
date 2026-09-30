"""OCR fallback interface.

OCR fallback: not available in this environment (no ``tesseract`` and no
``pdftoppm`` on PATH). The interface is implemented; the pipeline then marks
scanned-only pages ``RECUPERARE`` - an honest null instead of a guessed text.

Engines:
* ``UnavailableOcr``  - default when nothing is installed; ``available() is False``.
* ``TesseractOcr``    - shells out to ``pdftoppm`` (render) + ``tesseract ... tsv``
                        (mean word confidence / 100). Untested here: no binaries.
* ``FixtureOcr``      - canned results, for tests of the confidence threshold.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OcrResult:
    text: str
    confidence: float | None
    engine: str


class UnavailableOcr:
    name = "none"
    reason = "OCR fallback: not available in this environment"

    def available(self) -> bool:
        return False

    def recognize(self, pdf_path: Path, page_index: int) -> OcrResult:
        return OcrResult("", None, self.name)


class TesseractOcr:
    name = "tesseract"

    def __init__(self, lang: str = "ita"):
        self.lang = lang
        self.tesseract, self.pdftoppm = shutil.which("tesseract"), shutil.which("pdftoppm")

    def available(self) -> bool:
        return bool(self.tesseract and self.pdftoppm)

    def recognize(self, pdf_path: Path, page_index: int) -> OcrResult:  # pragma: no cover - no binaries here
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "page"
            subprocess.run([self.pdftoppm, "-r", "300", "-gray", "-png", "-f", str(page_index + 1), "-l",
                            str(page_index + 1), str(pdf_path), str(base)], check=True, capture_output=True)
            png = next(Path(td).glob("page*.png"))
            tsv = subprocess.run([self.tesseract, str(png), "stdout", "-l", self.lang, "tsv"], check=True,
                                 capture_output=True, text=True).stdout
        words, confs = [], []
        for line in tsv.splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) == 12 and cols[11].strip() and cols[10] not in ("-1", ""):
                words.append(cols[11])
                confs.append(float(cols[10]))
        conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        return OcrResult(" ".join(words), conf, self.name)


class FixtureOcr:
    """For tests: {(file_name, page_index): (text, confidence)}."""
    name = "fixture"

    def __init__(self, table: dict):
        self.table = table

    def available(self) -> bool:
        return True

    def recognize(self, pdf_path: Path, page_index: int) -> OcrResult:
        text, conf = self.table.get((Path(pdf_path).name, page_index), ("", 0.0))
        return OcrResult(text, conf, self.name)


def default_engine():
    t = TesseractOcr()
    return t if t.available() else UnavailableOcr()
