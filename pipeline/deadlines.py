"""Dates, deadline natures (L6) and relative terms.

Not every date is a deadline. Each date found in a text is classified by an
ordered rule file (``rules/deadline_nature.json``) into one of

    actionable   "entro il 14/11/2026", "udienza del ..."      drives urgency
    computed     notification + N days (relative term)         drives urgency
    conditional  "qualora entro il ... non ..."                 only if triggered
    historical   "fattura del ...", "il termine ... è scaduto"  never
    RECUPERARE   a future date with no recognisable cue         surfaced, never driving
"""
from __future__ import annotations

import datetime as _dt
import re
from functools import lru_cache

from .lib import jsonio
from .rules_engine import RULES_DIR

MONTHS = {m: i for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                       "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1)}
NUM_WORDS = {"cinque": 5, "dieci": 10, "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
             "sessanta": 60, "novanta": 90, "centoventi": 120, "sette": 7, "otto": 8}

_DATE_NUM = re.compile(r"(?<!\d)(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?!\d)")
_DATE_WORD = re.compile(r"(?<!\d)(\d{1,2})(?:°|º)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})(?!\d)", re.I)
_DATE_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_REL_TERM = re.compile(r"entro\s+(?:il\s+termine\s+di\s+)?(\d{1,3}|" + "|".join(NUM_WORDS) + r")\s+giorni\s+"
                       r"(?:dalla|dal|dall['’])\s*(notifica|notificazione|ricevimento|ricezione)", re.I)
# Safety nets: text that LOOKS like a term or a date but was not parsed must not be ignored.
_TERM_MENTION = re.compile(r"giorni\s+(?:dalla|dal|dall['’])\s*(?:notifica|notificazione|ricevimento|ricezione)", re.I)
# lookarounds: a sentence-ending "." after the token is fine; a separator followed by a digit is not
_DATE_LIKE = re.compile(r"(?<!\d)(?<!\d[/.-])\d{1,2}\s?[-/.]\s?\d{1,2}\s?[-/.]\s?\d{2,4}(?!\d|[/.-]\d)|"
                        r"(?<!\d)\d{1,2}(?:°|º)?\s+(?:" + "|".join(MONTHS) + r")\s+\d{2}(?!\d)", re.I)
# A clause that talks about a term: an unreadable date inside it may be THE deadline.
_DEADLINE_CLAUSE = re.compile(r"\b(entro|udienza|scad(?!ut)\w*|termine|fissat\w*|rinvi\w*|versat\w*|corrispost\w*|"
                              r"pagament\w*|comparire|qualora|in caso di)\b[^.;]*$", re.I)
_ABBREV = {"n", "nr", "art", "artt", "c", "p", "civ", "proc", "ss", "prot", "rif", "avv", "dott", "sig", "pag",
           "lett", "co", "d", "lgs", "l", "dpr", "r", "g", "s", "a", "spa", "srl", "sas", "snc", "coop", "soc",
           "cod", "tel", "fax", "ord", "giud", "cfr", "u", "e", "ecc", "reg", "t", "f"}


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def sentences(text: str) -> list[tuple[int, int]]:
    """Abbreviation-aware sentence spans over whitespace-normalised text."""
    spans, start = [], 0
    for m in re.finditer(r"[.;:!?](?=\s+[A-ZÀ-Ý\"«(])|[;](?=\s)", text):
        end = m.end()
        tok = re.search(r"([A-Za-zÀ-ÿ]+)\.$", text[max(0, end - 12):end])
        if m.group(0) == "." and tok and tok.group(1).lower() in _ABBREV:
            continue
        spans.append((start, end))
        start = end
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def find_dates(text: str) -> list[dict]:
    t = normalize_ws(text)
    found = []
    for rx, kind in ((_DATE_NUM, "num"), (_DATE_WORD, "word"), (_DATE_ISO, "iso")):
        for m in rx.finditer(t):
            try:
                if kind == "num":
                    d = _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif kind == "word":
                    d = _dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
                else:
                    d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            found.append({"date": d.isoformat(), "start": m.start(), "end": m.end(), "raw": m.group(0)})
    found.sort(key=lambda x: x["start"])
    spans = sentences(t)
    for f in found:
        for a, b in spans:
            if a <= f["start"] < b:
                f["before"] = t[a:f["start"]][-120:]
                f["after"] = t[f["end"]:b][:60]
                f["sentence"] = t[a:b].strip()
                break
    return found


@lru_cache(maxsize=None)
def _nature_rules() -> tuple:
    data = jsonio.read(RULES_DIR / "deadline_nature.json")
    rules = []
    for r in data["rules"]:
        w = r["when"]
        rules.append((r["id"], re.compile(w["before"], re.I) if "before" in w else None,
                      re.compile(w["after"], re.I) if "after" in w else None,
                      w.get("date_vs_reference"), r["then"]["nature"]))
    return tuple(rules)


def classify_nature(before: str, after: str, date_iso: str, reference_iso: str | None) -> tuple[str, str]:
    for rid, rb, ra, dvr, nature in _nature_rules():
        hit = False
        if rb is not None and rb.search(before or ""):
            hit = True
        if ra is not None and ra.search(after or ""):
            hit = True
        if dvr is not None:
            if reference_iso is None:
                continue
            cond = {"before": date_iso < reference_iso, "on_or_before": date_iso <= reference_iso,
                    "after": date_iso > reference_iso}[dvr]
            hit = cond if (rb is None and ra is None) else (hit and cond)
        if hit:
            return nature, rid
    return "RECUPERARE", "N-FALLBACK"


def relative_terms(text: str) -> list[dict]:
    t = normalize_ws(text)
    out = []
    for m in _REL_TERM.finditer(t):
        raw = m.group(1).lower()
        days = int(raw) if raw.isdigit() else NUM_WORDS[raw]
        before = t[max(0, m.start() - 120):m.start()]
        conditional = re.search(r"\b(qualora|in caso di|nel caso in cui|laddove)\b[^.;]*$", before, re.I)
        out.append({"days": days, "raw": m.group(0), "from_event": m.group(2).lower(),
                    "conditional": bool(conditional), "start": m.start()})
    return out


def unparsed_term_mentions(text: str) -> int:
    """How many 'N giorni dalla notifica/ricevimento' mentions were NOT parsed as relative terms."""
    t = normalize_ws(text)
    return max(0, len(_TERM_MENTION.findall(t)) - len(relative_terms(t)))


def unparsed_date_like(text: str, deadline_clauses_only: bool = True) -> list[str]:
    """Date-looking tokens in a format the extractor does not support (e.g. 16-10-2026, 16/10/26).
    By default only those sitting in a clause that talks about a term (entro, udienza, scade, ...):
    an unreadable invoice date cannot hide a deadline; an unreadable date after "entro il" can."""
    t = normalize_ws(text)
    spans = [(f["start"], f["end"]) for f in find_dates(t)]
    sents = sentences(t)
    out = []
    for m in _DATE_LIKE.finditer(t):
        if any(a <= m.start() < b or a < m.end() <= b for a, b in spans):
            continue
        if deadline_clauses_only:
            start = next((a for a, b in sents if a <= m.start() < b), 0)
            if not _DEADLINE_CLAUSE.search(t[start:m.start()]):
                continue
        out.append(m.group(0))
    return out


def driving_deadline(deadlines: list[dict], as_of_date: _dt.date) -> dict | None:
    """Earliest actionable/computed deadline on or after as_of; else the latest expired."""
    cands = [d for d in deadlines if d.get("nature") in ("actionable", "computed") and d.get("date")]
    if not cands:
        return None
    iso = as_of_date.isoformat()
    upcoming = sorted((d for d in cands if d["date"] >= iso), key=lambda d: (d["date"], d.get("nature")))
    if upcoming:
        return {**upcoming[0], "status": "open"}
    past = sorted(cands, key=lambda d: (d["date"], d.get("nature")))
    return {**past[-1], "status": "expired"}
