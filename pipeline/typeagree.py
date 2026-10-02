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

v2.2 - two title readers. The reader above (the *agreement* reader, arm A) now works next to the
*title-exclusive* reader ported from arm B: rules DT-030.. of ``rules/doc_type.json`` (``basis:
"title_exclusive"``), which commit on the title alone when it names ONE act and no other. ``resolve``
puts the two readings side by side and looks the pair up in the ordered table ``title_merge`` of the
same file: two readers that commit different types, or a committing reader facing two confirmed
families, give RECUPERARE; a reader that commits while the other has no opinion commits under its own
conditions. A pair the table does not list is RECUPERARE (fail closed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .rules_engine import HEADING_CHARS, MAX_TITLE_LEN, title_line_list  # one definition of a title line

RECUPERARE = "RECUPERARE"
# the five things the agreement reader can say, and the two the title-exclusive reader can say
AGREEMENT_STATES = ("silent", "not_understood", "unconfirmed", "committed", "conflict")
EXCLUSIVE_STATES = ("silent", "committed")
MERGE_OUTCOMES = ("exclusive", "agreement", "fallback", RECUPERARE)
_REFERENCE = re.compile(r"\S*\d\S*")           # "12/2026", "SYN-DI-0101": a reference, not a word
_WORD = re.compile(r"[A-ZÀ-Ý]+")


@dataclass(frozen=True)
class Families:
    items: tuple            # (family id, doc_type, title regex, subject regex)
    neutral: frozenset
    merge: tuple = ()       # v2.2: the ordered table 'title_merge' (id, exclusive, agreement states, same_type, outcome)


@dataclass(frozen=True)
class Reading:
    """What the agreement reader says about a text: one of AGREEMENT_STATES, the type when committed."""
    state: str
    doc_type: str | None
    basis: str


def compile_families(doc_type_rules: dict) -> Families:
    items = tuple((f["id"], f["doc_type"], re.compile(f["title"]), re.compile(f["subject"], re.I))
                  for f in doc_type_rules.get("title_families", []))
    merge = []
    for r in doc_type_rules.get("title_merge", []):
        w, outcome = r["when"], r["then"]["outcome"]
        states = tuple(w["agreement"])
        if w["exclusive"] not in EXCLUSIVE_STATES or outcome not in MERGE_OUTCOMES or not states or any(
                st not in AGREEMENT_STATES for st in states):
            raise ValueError(f"doc_type.json:{r['id']}: unknown reader state or outcome")
        merge.append((r["id"], w["exclusive"], states, w.get("same_type"), outcome))
    return Families(items, frozenset(doc_type_rules.get("title_neutral_words", [])), tuple(merge))


def title_lines(text: str) -> list[str]:
    """Upper-case lines of the heading: the way a title is typeset. Running text is never a title.
    (v2.2: the definition lives in rules_engine, shared with the title-exclusive rules.)"""
    return title_line_list(text, HEADING_CHARS)


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


def read_state(text: str, subject: str, terms: list[dict], fam: Families, terms_cfg: dict) -> Reading:
    """The agreement reader alone. States: silent (no title line names a known family), not_understood,
    unconfirmed, committed (exactly one confirmed family), conflict (several confirmed families)."""
    candidates, not_understood = read_title(text, fam)
    if not candidates and not not_understood:
        return Reading("silent", None, "no act family on a title line")
    if not_understood:
        line, foreign = not_understood[0]
        return Reading("not_understood", None,
                       f"title '{line}' names an act family together with {', '.join(foreign)}: not understood")
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
        return Reading("committed", doc_type, f"{fid} title family confirmed by {by}")
    if not confirmed:
        return Reading("unconfirmed", None,
                       f"title names {names}: no independent reading (subject, stated term) confirms it")
    return Reading("conflict", None,
                   f"title names {names}: " + " and ".join(f"{fid} confirmed by {by}" for fid, _, by in confirmed)
                   + " - more than one confirmed family")


def read(text: str, subject: str, terms: list[dict], fam: Families, terms_cfg: dict) -> tuple[str | None, str]:
    """The agreement reader alone, as in v2.1: (doc_type | 'RECUPERARE' | None, basis).
    None = no title line names a known family."""
    r = read_state(text, subject, terms, fam, terms_cfg)
    if r.state == "silent":
        return None, r.basis
    return (r.doc_type if r.state == "committed" else RECUPERARE), r.basis


def merge_rule(exclusive_type: str | None, agreement: Reading, fam: Families) -> tuple[str | None, str]:
    """First row of 'title_merge' that describes the pair of readings: (rule id, outcome).
    No row -> (None, RECUPERARE): a pair nobody has thought about is not committed."""
    exclusive = "committed" if exclusive_type else "silent"
    same = (exclusive_type == agreement.doc_type) if exclusive_type and agreement.state == "committed" else None
    for rid, excl, states, same_type, outcome in fam.merge:
        if excl == exclusive and agreement.state in states and (same_type is None or same_type == same):
            return rid, outcome
    return None, RECUPERARE


def resolve(then: dict | None, rule: str | None, text: str, subject: str, terms: list[dict], fam: Families,
            terms_cfg: dict) -> tuple[str | None, str, str | None]:
    """Put the two title readers side by side. ``then``/``rule`` are what the ordered rules of doc_type.json
    returned: a title-exclusive rule (basis 'title_exclusive'), a subject fallback, or nothing.

    Returns (doc_type | 'RECUPERARE' | None, basis, merge rule id). None = both title readers are silent:
    the caller keeps the result of the ordered rules (subject fallback, or no rule), as in v2.0."""
    exclusive_type = then["doc_type"] if then and then.get("basis") == "title_exclusive" else None
    a = read_state(text, subject, terms, fam, terms_cfg)
    rid, outcome = merge_rule(exclusive_type, a, fam)
    if outcome == "fallback" and exclusive_type is None and a.state == "silent":
        return None, a.basis, rid
    if outcome == "agreement" and a.state == "committed" and exclusive_type in (None, a.doc_type):
        # the agreement reader alone, or both readers on the same type: its basis, worded as in v2.1
        return a.doc_type, a.basis + (f" + {rule} (title names this act alone)" if exclusive_type else ""), rid
    if outcome == "exclusive" and exclusive_type and a.state != "conflict" and a.doc_type in (None, exclusive_type):
        if a.state == "committed":
            return exclusive_type, f"{a.basis} + {rule} (title names this act alone)", rid
        return exclusive_type, f"{rule} title names this act alone ({rid}; agreement reader: {a.state})", rid
    if outcome == RECUPERARE and rid is not None:
        if exclusive_type and a.state == "committed":
            return RECUPERARE, (f"{rid} the two title readers disagree: {rule} reads {exclusive_type}, "
                                f"{a.basis} reads {a.doc_type}"), rid
        if exclusive_type:
            return RECUPERARE, f"{rid} {rule} reads {exclusive_type}, but {a.basis}", rid
        return RECUPERARE, a.basis, rid      # the agreement reader's own abstention, worded as in v2.1
    # no row, or a row whose outcome the readings cannot support (it would let one reader override the
    # other, or commit a reading nobody made): fail closed
    return RECUPERARE, (f"title_merge {rid or 'has no rule'} for exclusive="
                        f"{'committed' if exclusive_type else 'silent'}, agreement={a.state} "
                        f"(outcome {outcome}): not committed"), rid


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


def run_merge_tests(doc_rules, doc_type_rules: dict, terms_cfg: dict) -> list[str]:
    """Tests carried by each row of 'title_merge'. They go through the ordered rules of doc_type.json first
    (``doc_rules``: the RuleFile), exactly as the pipeline does, so each test names a real pair of readings."""
    fam = compile_families(doc_type_rules)
    failures = []
    for r in doc_type_rules.get("title_merge", []):
        for t in r["tests"]:
            i = t["input"]
            terms = [{"days": d, "from_event": e, "conditional": False} for d, e in i.get("terms", [])]
            then, rule = doc_rules.apply({"subject": i.get("subject", ""), "text": i.get("text", "")})
            if then is not None and then.get("basis") not in ("subject", "title_exclusive"):
                failures.append(f"doc_type.json:{r['id']}:{t['id']}: strict rule {rule} matched, the readers never ran")
                continue
            got, basis, rid = resolve(then, rule, i.get("text", ""), i.get("subject", ""), terms, fam, terms_cfg)
            if got is None:                       # both silent: the pipeline keeps the ordered rules' result
                got = then["doc_type"] if then else RECUPERARE
            if rid != t.get("expect_rule", r["id"]):
                failures.append(f"doc_type.json:{r['id']}:{t['id']}: decided by {rid} ({basis})")
            elif got != t["expect"]["doc_type"]:
                failures.append(f"doc_type.json:{r['id']}:{t['id']}: got {got!r} ({basis}), "
                                f"expected {t['expect']['doc_type']!r}")
    return failures
