"""Canonical entity dictionary (thesis pattern 3) with structural debtor exclusion.

Canonical form: NFC, UPPERCASE, uniform legal-form suffixes (S.R.L., S.P.A.,
S.A.S., S.N.C., S.S., SOC. COOP.), apostrophes unified to the typographic ’,
professional qualifications moved into parentheses (``ILARIA MOSCARDINI (AVV.)``).

The dictionary is *always read before classifying*; aliases accumulate, the
canonical of an entry never changes once written.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .lib import jsonio

DEBTOR_SENTINEL = "@DEBTOR"

_LEGAL_FORMS = [
    (re.compile(r"\bS\.?\s?R\.?\s?L\.?\s?S\.?(?=\W|$)"), "S.R.L.S."),
    (re.compile(r"\bS\.?\s?R\.?\s?L\.?(?=\W|$)"), "S.R.L."),
    (re.compile(r"\bS\.?\s?P\.?\s?A\.?(?=\W|$)"), "S.P.A."),
    (re.compile(r"\bS\.?\s?A\.?\s?S\.?(?=\W|$)"), "S.A.S."),
    (re.compile(r"\bS\.?\s?N\.?\s?C\.?(?=\W|$)"), "S.N.C."),
    (re.compile(r"\bSOC(?:IETÀ|IETA'|\.)?\s+COOP(?:ERATIVA|\.)?(?=\W|$)"), "SOC. COOP."),
    (re.compile(r"\bS\.\s?S\.?(?=\W|$)"), "S.S."),
    (re.compile(r"&\s*C\.?(?=\W|$)"), "& C."),
]
_QUALIFICATIONS = [
    (re.compile(r"^(?:L['’]\s?)?AVV(?:OCATO|OCATESSA|\.)?\s+", re.I), "AVV."),
    (re.compile(r"^DOTT(?:\.|ORE|ORESSA|\.SSA)\s+", re.I), "DOTT."),
]
_APOSTROPHES = str.maketrans({"'": "’", "`": "’", "ʼ": "’", "´": "’", "‘": "’"})
_STOP = {"esempio", "società", "societa", "della", "dell", "degli", "delle", "del", "di", "dei", "e",
         "srl", "spa", "sas", "snc", "soc", "coop", "agricola", "semplice", "studio", "legale", "avv"}


def canonical(name: str) -> str:
    if name is None:
        return None
    s = unicodedata.normalize("NFC", name).translate(_APOSTROPHES)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-–")
    qual = None
    for rx, q in _QUALIFICATIONS:
        if rx.search(s):
            s, qual = rx.sub("", s), q
            break
    s = s.upper()
    for rx, form in _LEGAL_FORMS:
        s = rx.sub(form, s)
    s = re.sub(r"\s+", " ", s).strip(" ,;:")
    if qual:
        s = f"{s} ({qual})"
    return s


def match_key(name: str) -> str:
    """Key used to recognise aliases: canonical form without punctuation/spaces."""
    c = canonical(name) or ""
    c = unicodedata.normalize("NFD", c)
    c = "".join(ch for ch in c if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", c)


def name_tokens(name: str) -> list[str]:
    """Significant lowercase tokens (accents stripped) for domain matching."""
    c = unicodedata.normalize("NFD", canonical(name) or "")
    c = "".join(ch for ch in c if unicodedata.category(ch) != "Mn").lower()
    toks = re.split(r"[^a-z0-9]+", c)
    return [t for t in toks if len(t) >= 4 and t not in _STOP]


class Debtor:
    """The entity the corpus is about. Never a counterparty - enforced here."""

    def __init__(self, cfg: dict):
        self.canonical = canonical(cfg["canonical"])
        self.keys = {match_key(cfg["canonical"])} | {match_key(a) for a in cfg.get("aliases", [])}
        self.domains = {d.lower() for d in cfg.get("domains", [])}
        self.addresses = {a.lower() for a in cfg.get("pec", [])} if isinstance(cfg.get("pec"), list) \
            else {cfg.get("pec", "").lower()}

    def is_debtor_name(self, name: str | None) -> bool:
        return bool(name) and match_key(name) in self.keys

    def is_debtor_address(self, addr: str | None) -> bool:
        if not addr:
            return False
        a = addr.lower()
        dom = a.rsplit("@", 1)[-1]
        return a in self.addresses or any(dom == d or dom.endswith("." + d) for d in self.domains)


class EntityDictionary:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.entries: dict[str, dict] = {}
        self._by_key: dict[str, str] = {}
        if path and path.exists():
            for canon, e in jsonio.read(path).items():
                self.entries[canon] = e
                self._by_key[match_key(canon)] = canon
                for a in e.get("aliases_seen", []):
                    self._by_key.setdefault(match_key(a), canon)

    def resolve(self, raw: str, *, seen_on: str | None = None, role: str | None = None) -> str:
        """Return the stable canonical for ``raw``, registering aliases."""
        key = match_key(raw)
        canon = self._by_key.get(key)
        if canon is None:
            canon = canonical(raw)
            self.entries[canon] = {"aliases_seen": [], "first_date": seen_on, "last_date": seen_on,
                                   "roles_seen": []}
            self._by_key[key] = canon
        e = self.entries[canon]
        if raw != canon and raw not in e["aliases_seen"]:
            e["aliases_seen"] = sorted(set(e["aliases_seen"]) | {raw})
        if seen_on:
            e["first_date"] = min(filter(None, [e.get("first_date"), seen_on]))
            e["last_date"] = max(filter(None, [e.get("last_date"), seen_on]))
        if role and role not in e["roles_seen"]:
            e["roles_seen"] = sorted(set(e["roles_seen"]) | {role})
        return canon

    def known(self) -> list[str]:
        return sorted(self.entries)

    def save(self, path: Path | None = None) -> None:
        jsonio.write(path or self.path, dict(sorted(self.entries.items())))
