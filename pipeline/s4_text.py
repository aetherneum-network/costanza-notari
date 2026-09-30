"""Stage 4 - text recovery: text layer first, OCR fallback per page (A.1).

Per page: ``method`` (text_layer | ocr | none), ``confidence`` and
``status`` (OK | RECUPERARE). A page with fewer than ``min_text_chars_per_page``
characters is treated as a scan; OCR below ``ocr_min_confidence`` - or no
OCR engine at all - leaves the page ``RECUPERARE``.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pypdf

from . import ocr as ocr_mod
from .lib import jsonio
from .rules_engine import RULES_DIR

_RELATA = re.compile(r"relata|ricevuta|daticert", re.I)


def extract_pdf(path: Path, engine, min_chars: int, min_conf: float) -> dict:
    pages, texts = [], []
    try:
        reader = pypdf.PdfReader(io.BytesIO(path.read_bytes()))
        n = len(reader.pages)
    except Exception as exc:  # unreadable PDF: recorded, never guessed
        return {"pages": [], "text": "", "status": "RECUPERARE", "error": f"{type(exc).__name__}: {exc}"}
    for i in range(n):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception:
            t = ""
        if len(t.strip()) >= min_chars:
            pages.append({"page": i + 1, "method": "text_layer", "confidence": 1.0, "status": "OK", "chars": len(t)})
            texts.append(t)
            continue
        if engine.available():
            res = engine.recognize(path, i)
            ok = res.confidence is not None and res.confidence >= min_conf
            pages.append({"page": i + 1, "method": "ocr", "engine": res.engine, "confidence": res.confidence,
                          "status": "OK" if ok else "RECUPERARE", "chars": len(res.text)})
            if ok:
                texts.append(res.text)
        else:
            pages.append({"page": i + 1, "method": "none", "confidence": None, "status": "RECUPERARE",
                          "chars": len(t.strip()), "note": ocr_mod.UnavailableOcr.reason})
    bad = [p["page"] for p in pages if p["status"] != "OK"]
    status = "OK" if not bad else ("RECUPERARE" if len(bad) == len(pages) else "PARTIAL")
    return {"pages": pages, "text": "\n".join(texts), "status": status, "recuperare_pages": bad}


def run(sig_state: dict, work_dir: Path, out_path: Path, engine=None) -> dict:
    cfg = jsonio.read(RULES_DIR / "misc.json")["text_recovery"]
    engine = engine or ocr_mod.default_engine()
    records = []
    for r in sig_state["records"]:
        docs = []
        for d in r["documents"]:
            res = extract_pdf(work_dir / d["path"], engine, cfg["min_text_chars_per_page"], cfg["ocr_min_confidence"])
            docs.append({"name": d["name"], **res})
        principal = next((d for d in docs if not _RELATA.search(d["name"])), docs[0] if docs else None)
        if principal is None:
            text_status = "RECUPERARE"
        elif principal["status"] == "OK" and all(d["status"] == "OK" for d in docs):
            text_status = "OK"
        elif principal["status"] == "RECUPERARE":
            text_status = "RECUPERARE"
        else:
            text_status = "PARTIAL"
        records.append({"record_id": r["record_id"], "documents": docs,
                        "principal": principal["name"] if principal else None, "text_status": text_status})
    state = {"stage": "s4_text", "ocr_engine": engine.name,
             "ocr_available": engine.available(),
             "ocr_note": None if engine.available() else ocr_mod.UnavailableOcr.reason,
             "policy": cfg, "records": records,
             "summary": {s: sum(1 for x in records if x["text_status"] == s) for s in ("OK", "PARTIAL", "RECUPERARE")}}
    jsonio.write(out_path, state)
    return state
