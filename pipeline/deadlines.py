"""Dates, deadline natures (L6) and relative terms.

Not every date is a deadline. Each date found in a text is classified by an
ordered rule file (``rules/deadline_nature.json``) into one of

    actionable   "entro il 14/11/2026", "udienza del ..."      drives urgency
    computed     notification + N days (relative term)         drives urgency
    conditional  "qualora entro il ... non ..."                 only if triggered
    historical   "fattura del ...", "il termine ... è scaduto"  never
    RECUPERARE   a future date with no recognisable cue         surfaced, never driving

Relative terms ("entro dieci giorni dalla notifica") are read by ``pipeline/termclauses.py``
(v2.1: slot-by-slot reading, two independent readers that must agree).
"""
from __future__ import annotations

import datetime as _dt
import re
from functools import lru_cache

from . import termclauses
from .lib import jsonio
from .rules_engine import RULES_DIR

MONTHS = {m: i for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                       "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1)}

# v2.1: dd/mm/yyyy, dd.mm.yyyy, dd-mm-yyyy - one separator, used twice (backreference). Mixed separators,
# two-digit years, impossible calendar dates and digits glued to a code ("PR-10-11-2026") stay unread and are
# caught by _DATE_LIKE below.
_DATE_NUM = re.compile(r"(?<!\d)(?<!\d[/.-])(?<![A-Za-z]-)(\d{1,2})([/.-])(\d{1,2})\2(\d{4})(?!\d|[/.-]\d)")
_DATE_WORD = re.compile(r"(?<!\d)(\d{1,2})(?:°|º)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})(?!\d)", re.I)
_DATE_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
# Safety net: text that LOOKS like a date but was not parsed must not be ignored.
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
                    d = _dt.date(int(m.group(4)), int(m.group(3)), int(m.group(1)))
                elif kind == "word":
                    d = _dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
                else:
                    d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            found.append({"date": d.isoformat(), "start": m.start(), "end": m.end(), "raw": m.group(0)})
    found.sort(key=lambda x: x["start"])
    spans = sentences(t)
    for k, f in enumerate(found):
        for a, b in spans:
            if a <= f["start"] < b:
                f["before"] = t[a:f["start"]][-120:]
                # v2.1: the lead-in that belongs to this date alone = what follows the previous date of the sentence
                prev_end = max([g["end"] for g in found[:k] if a <= g["start"] and g["end"] <= f["start"]], default=a)
                f["before_local"] = t[prev_end:f["start"]][-120:]
                f["after"] = t[f["end"]:b][:200]
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
                      w.get("date_vs_reference"), r["then"]["nature"],
                      re.compile(w["after_not"], re.I) if "after_not" in w else None,
                      w.get("max_days_after_reference"), w.get("across_a_date")))
    return tuple(rules)


@lru_cache(maxsize=None)
def _nature_vetoes() -> tuple:
    """v2.1: file-level vetoes. A veto turns a reading of the given nature into RECUPERARE when the rest of
    the sentence says something the reading rule did not read (a negation, a further predicate)."""
    data = jsonio.read(RULES_DIR / "deadline_nature.json")
    return tuple((v["id"], v["applies_to_nature"],
                  re.compile(v["when"]["before"], re.I) if "before" in v["when"] else None,
                  re.compile(v["when"]["after"], re.I) if "after" in v["when"] else None)
                 for v in data.get("vetoes", []))


@lru_cache(maxsize=None)
def sole_candidate_rules() -> frozenset:
    """Ids of the nature rules whose reading is accepted only when no other future written date competes."""
    data = jsonio.read(RULES_DIR / "deadline_nature.json")
    return frozenset(r["id"] for r in data["rules"] if r["then"].get("sole_candidate"))


def classify_nature(before: str, after: str, date_iso: str, reference_iso: str | None,
                    before_local: str | None = None) -> tuple[str, str]:
    """Nature of one written date: (nature, id of the rule or veto that decided).

    ``before`` = the sentence up to the date; ``before_local`` = the part of it that follows the previous
    date of the same sentence (default: the same text). A rule flagged ``across_a_date`` whose lead-in is
    found only by reading across that previous date answers RECUPERARE: the cue may belong to the other date."""
    local = before if before_local is None else before_local
    for rid, rb, ra, dvr, nature, ra_not, max_after, across in _nature_rules():
        hit = False
        if rb is not None and rb.search(before or ""):
            hit = True
            if across and not rb.search(local or ""):
                nature = across
        if ra is not None and ra.search(after or ""):
            hit = True
        if dvr is not None:
            if reference_iso is None:
                continue
            cond = {"before": date_iso < reference_iso, "on_or_before": date_iso <= reference_iso,
                    "after": date_iso > reference_iso}[dvr]
            hit = cond if (rb is None and ra is None) else (hit and cond)
        if hit and ra_not is not None and ra_not.search(after or ""):
            hit = False
        if hit and max_after is not None:
            if reference_iso is None:
                continue
            gap = (_dt.date.fromisoformat(date_iso) - _dt.date.fromisoformat(reference_iso)).days
            hit = gap <= max_after
        if hit:
            for vid, v_nature, v_before, v_after in _nature_vetoes():
                if nature == v_nature and ((v_before is not None and v_before.search(local or ""))
                                           or (v_after is not None and v_after.search(after or ""))):
                    return "RECUPERARE", vid
            return nature, rid
    return "RECUPERARE", "N-FALLBACK"


def relative_terms(text: str) -> list[dict]:
    """Relative terms read with certainty (both readers agree, every slot recognised by a rule)."""
    return [{"days": t["days"], "raw": t["raw"], "from_event": t["from_event"], "conditional": t["conditional"],
             "start": t["start"], "rules": t["rules"]} for t in termclauses.read(text)["terms"]]


def unread_term_clauses(text: str) -> list[dict]:
    """Text that looks like a relative term but was NOT read with certainty: [{raw, why, start}]."""
    return termclauses.read(text)["unread"]


def unparsed_term_mentions(text: str) -> int:
    """How many term-like mentions were NOT read as relative terms (each one forces RECUPERARE)."""
    return len(unread_term_clauses(text))


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
