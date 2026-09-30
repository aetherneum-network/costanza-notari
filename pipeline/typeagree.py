"""Document type by agreement of two independent readings (v2.1).

Used only when no strict title/text rule of ``rules/doc_type.json`` matched and the text is readable
(v2.0 answered RECUPERARE there, or fell back to the PEC subject alone).

Reading 1 - the title. Upper-case lines of the heading are searched for the act *families* listed in
``title_families``. A family name counts only inside a *neutral frame*: apart from family names the
line may hold nothing but ``title_neutral_words`` (ATTO DI, LETTERA DI, AVVISO DI, ...) and reference
numbers. "LETTERA DI DIFFIDA" names the family *diffida*; "ATTO DI PRECETTO E INTIMAZIONE" names two;
"ATTO DI OPPOSIZIONE A PRECETTO" names a family together with a word that may turn the act into a
different one: that title is *not understood*.

Reading 2 - independent of the title: (a) the PEC subject names the same family, or (b) the text states
a relative term that equals the term of that act in ``rules/terms.json`` (same start event, and the
same number of days where the act has a statutory one).

The type is committed only when the title is understood and exactly one family is confirmed.
No family on any title line: no opinion (the caller keeps the v2.0 behaviour). Otherwise - title not
understood, no confirmed family, several confirmed families - RECUPERARE, which also vetoes the
subject-only fallback: the title says something that the subject alone does not explain.

A PEC subject that names ANOTHER act does not veto a title confirmed by the stated term: the subject is
typed by the sender's office and may mislead (the v2.0 strict rules already let the title win over it,
e.g. DT-014). It simply does not count as a confirmation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

RECUPERARE = "RECUPERARE"
HEADING_CHARS = 600   # same window as the strict 'heading_matches' rules
MAX_TITLE_LEN = 90
_REFERENCE = re.compile(r"\S*\d\S*")           # "12/2026", "SYN-DI-0101": a reference, not a word
_WORD = re.compile(r"[A-ZÀ-Ý]+")


@dataclass(frozen=True)
class Families:
    items: tuple            # (family id, doc_type, title regex, subject regex)
    neutral: frozenset


def compile_families(doc_type_rules: dict) -> Families:
    items = tuple((f["id"], f["doc_type"], re.compile(f["title"]), re.compile(f["subject"], re.I))
                  for f in doc_type_rules.get("title_families", []))
    return Families(items, frozenset(doc_type_rules.get("title_neutral_words", [])))


def title_lines(text: str) -> list[str]:
    """Upper-case lines of the heading: the way a title is typeset. Running text is never a title."""
    out = []
    for line in (text or "")[:HEADING_CHARS].splitlines():
        s = line.strip()
        if s and len(s) <= MAX_TITLE_LEN and any(c.isalpha() for c in s) and s == s.upper():
            out.append(s)
    return out


def read_title(text: str, fam: Families) -> tuple[list, list]:
    """Return (candidates, not_understood): candidates = [(family id, doc_type, subject regex)] named inside
    a neutral frame; not_understood = [(line, [foreign words])] for lines that name a family among other words."""
    candidates, not_understood = [], []
    for line in title_lines(text):
        rest, named = line, []
        for item in fam.items:
            if item[2].search(rest):
                named.append(item)
                rest = item[2].sub(" ", rest)
        if not named:
            continue  # letterhead, court name, ...: says nothing about the act
        foreign = [w for w in _WORD.findall(_REFERENCE.sub(" ", rest)) if w not in fam.neutral]
        if foreign:
            not_understood.append((line, foreign))
        else:
            candidates.extend((i[0], i[1], i[3]) for i in named if (i[0], i[1], i[3]) not in candidates)
    return candidates, not_understood


def _term_confirms(doc_type: str, terms: list[dict], terms_cfg: dict) -> str | None:
    legal = next((t for t in terms_cfg.get("terms", []) if t["doc_type"] == doc_type), None)
    if legal is None:
        return None
    for r in terms:
        if r.get("conditional"):
            continue
        if r.get("from_event") == legal.get("event") and (legal.get("days") is None or r.get("days") == legal["days"]):
            return legal["id"]
    return None


def read(text: str, subject: str, terms: list[dict], fam: Families, terms_cfg: dict) -> tuple[str | None, str]:
    """Return (doc_type | 'RECUPERARE' | None, basis). None = no title line names a known family."""
    candidates, not_understood = read_title(text, fam)
    if not candidates and not not_understood:
        return None, "no act family on a title line"
    if not_understood:
        line, foreign = not_understood[0]
        return RECUPERARE, f"title '{line}' names an act family together with {', '.join(foreign)}: not understood"
    confirmed = []
    for fid, doc_type, rx_subject in candidates:
        by = []
        if rx_subject.search(subject or ""):
            by.append("subject")
        term_id = _term_confirms(doc_type, terms, terms_cfg)
        if term_id:
            by.append(f"stated term = {term_id}")
        if by:
            confirmed.append((fid, doc_type, " + ".join(by)))
    names = ", ".join(f"{fid} {dt}" for fid, dt, _ in candidates)
    if len(confirmed) == 1:
        fid, doc_type, by = confirmed[0]
        return doc_type, f"{fid} title family confirmed by {by}"
    if not confirmed:
        return RECUPERARE, f"title names {names}: no independent reading (subject, stated term) confirms it"
    return RECUPERARE, (f"title names {names}: " + " and ".join(f"{fid} confirmed by {by}" for fid, _, by in confirmed)
                        + " - more than one confirmed family")


def run_inline_tests(doc_type_rules: dict, terms_cfg: dict) -> list[str]:
    """Tests carried by each family. They exercise this second path alone (no strict rule in front)."""
    fam = compile_families(doc_type_rules)
    failures = []
    for f in doc_type_rules.get("title_families", []):
        for t in f["tests"]:
            i = t["input"]
            terms = [{"days": d, "from_event": e, "conditional": False} for d, e in i.get("terms", [])]
            got, basis = read(i.get("text", ""), i.get("subject", ""), terms, fam, terms_cfg)
            want = t["expect"]["doc_type"]
            if got != want:
                failures.append(f"doc_type.json:{f['id']}:{t['id']}: got {got!r} ({basis}), expected {want!r}")
            elif want == f["doc_type"] and not basis.startswith(f["id"] + " "):
                failures.append(f"doc_type.json:{f['id']}:{t['id']}: decided by another family ({basis})")
    return failures
