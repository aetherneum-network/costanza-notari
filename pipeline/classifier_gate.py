"""Deterministic gate between the deadline classifier and the record (v2.3).

The model never commits on its own. Its answer (``pipeline/llm_classifier.py``) reaches the record only
if every rule of ``rules/classifier_gate.json`` lets it through; the rules are ordered and the first one
that refuses wins (L7). A refused answer is an abstention: the deadline stays RECUPERARE and the record
keeps, in ``classifier.gate``, the id of the rule that refused it and why.

Each rule names a ``check``; the checks below only extract and compare, they do not interpret:

    answer_usable           the call returned a schema-valid answer (no refusal, no truncation, no error)
    model_answered          the model did not answer RECUPERARE itself
    date_parses             "YYYY-MM-DD" and a real calendar day ("NONE" is not a date)
    nature_known            actionable or computed: the only natures that drive a deadline in the rules
    evidence_present        the evidence is not empty
    evidence_not_joined     the evidence is not several passages joined by "..." (a refusal of its own,
                            to count it apart)
    evidence_verbatim       the evidence is ONE verbatim passage of the record (whitespace-insensitive)
    actionable_date_written an actionable date is written in the evidence
    actionable_not_contradicted
                            the rules did not read that written date as historical or conditional
    computed_notification_known
                            a computed term needs a notification date the rules trust
    computed_act_type_known the act type has a term policy in rules/terms.json and agrees with the rules'
    computed_after_notification
                            a computed term ends after the notification
    computed_recount        the pipeline counts the term itself (pipeline/terms.py, the act type's policy):
                            the term stated in the evidence when the term reader parses it, otherwise
                            the statutory term of rules/terms.json - and the proposed date must be that
                            count. Evidence writing another number of days refuses the statutory count.
    driving_consistent      together with the deadlines the rules already found, the proposal is the
                            driving deadline (earliest on/after as_of, else the latest)
    confidence_not_low      the model's own confidence is medium or high
"""
from __future__ import annotations

import datetime as _dt
import re
from functools import lru_cache

from . import deadlines as dl, termclauses, terms
from .lib import jsonio, tzrome
from .rules_engine import RULES_DIR

RECUPERARE = "RECUPERARE"
GATE_FILE = "classifier_gate.json"
DRIVING_NATURES = ("actionable", "computed")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ELLIPSIS = re.compile(r"\.\.\.|…")


@lru_cache(maxsize=None)
def _load(rules_dir: str) -> dict:
    return jsonio.read(rules_dir + "/" + GATE_FILE)


def load(rules_dir=None) -> dict:
    return _load(str(rules_dir or RULES_DIR))


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def source_text(env: dict, txt: dict) -> str:
    """The words of the record the model was shown: PEC subject, e-mail body, text of every document."""
    dc = env.get("daticert") or {}
    inner = env.get("inner") or {}
    parts = [dc.get("oggetto") or inner.get("subject") or "", inner.get("body") or ""]
    parts += [d.get("text") or "" for d in txt.get("documents", [])]
    return "\n".join(parts)


# ------------------------------------------------------------------------------------------------ checks
# Every check takes (answer, rec, source, ctx) and returns None (passes) or the reason it refuses.

def _answer_usable(c):
    if c["status"] != "ok" or not isinstance(c["answer"], dict):
        return f"no usable answer ({c['status']})"
    return None


def _model_answered(c):
    if str(c["answer"].get("deadline", "")).strip() == RECUPERARE:
        return "the model answered RECUPERARE"
    return None


def _date_parses(c):
    d = str(c["answer"].get("deadline", "")).strip()
    if d == "NONE":
        return "NONE is not a date: only the rules decide that an act has no deadline"
    if not _DATE.match(d):
        return f"'{d[:40]}' is not a YYYY-MM-DD date"
    try:
        _dt.date.fromisoformat(d)
    except ValueError:
        return f"'{d}' is not a calendar day"
    return None


def _nature_known(c):
    n = c["answer"].get("nature")
    if n not in DRIVING_NATURES:
        return f"nature '{n}' does not drive a deadline in the rules (actionable or computed only)"
    return None


def _evidence_present(c):
    if not norm(c["answer"].get("evidence")):
        return "empty evidence"
    return None


def _evidence_not_joined(c):
    ev = norm(c["answer"].get("evidence"))
    if ev not in norm(c["source"]) and _ELLIPSIS.search(ev):
        n = len([p for p in _ELLIPSIS.split(ev) if p.strip()])
        return f"the evidence joins {n} passages with '...': not one verbatim passage of the record"
    return None


def _evidence_verbatim(c):
    if norm(c["answer"].get("evidence")) not in norm(c["source"]):
        return "the evidence is not a verbatim passage of the record"
    return None


def _actionable_date_written(c):
    a = c["answer"]
    if a["nature"] != "actionable":
        return None
    written = {d["date"] for d in dl.find_dates(norm(a["evidence"]))}
    if a["deadline"].strip() not in written:
        return "the actionable date is not written in the evidence"
    return None


def _actionable_not_contradicted(c):
    a = c["answer"]
    if a["nature"] != "actionable":
        return None
    d = a["deadline"].strip()
    read = [x for x in c["rec"].get("dates") or [] if x.get("date") == d]
    if read and all(x.get("nature") in ("historical", "conditional") for x in read):
        return (f"the rules read this written date as {read[0]['nature']} ({read[0].get('rule')}): "
                "it cannot drive a deadline")
    return None


def _term(ctx, doc_type):
    return next((t for t in ctx.terms_cfg["terms"] if t["doc_type"] == doc_type), None)


def _computed_notification_known(c):
    if c["answer"]["nature"] != "computed":
        return None
    if not c["rec"].get("notification_date") or not c["rec"].get("pec_time"):
        return ("a computed term needs a notification date the rules trust: "
                + (c["rec"].get("notification_note") or "none"))
    return None


def _computed_act_type_known(c):
    a, rec = c["answer"], c["rec"]
    if a["nature"] != "computed":
        return None
    act = str(a.get("act_type", "")).strip()
    if _term(c["ctx"], act) is None:
        return f"act type '{act[:40]}' has no term policy in rules/terms.json"
    if rec.get("doc_type") not in (None, RECUPERARE) and rec["doc_type"] != act:
        return f"the rules read the act as {rec['doc_type']}, the answer as {act}"
    return None


def _computed_after_notification(c):
    a = c["answer"]
    if a["nature"] != "computed":
        return None
    if a["deadline"].strip() <= c["rec"]["notification_date"]:
        return f"a computed term cannot end on or before the notification date {c['rec']['notification_date']}"
    return None


_LOOSE_DAYS = re.compile(r"(?<![\w])(\d{1,3}|[a-zà-ÿ]+)\s+(?:\(\s*[\w]+\s*\)\s+)?(?:giorni|gg)\b", re.I)


def loose_days(text: str) -> set:
    """Every 'N giorni' quantity written in the text, parsed or not by the term reader (digits or words)."""
    out = set()
    for m in _LOOSE_DAYS.finditer(text):
        w = m.group(1)
        n = int(w) if w.isdigit() else termclauses.parse_cardinal(w)
        if n:
            out.add(n)
    return out


def _computed_recount(c):
    a = c["answer"]
    if a["nature"] != "computed":
        return None
    ev, act = norm(a["evidence"]), str(a.get("act_type", "")).strip()
    term = _term(c["ctx"], act)
    pec = tzrome.parse_iso(c["rec"]["pec_time"])
    stated = [t for t in dl.relative_terms(ev) if not t["conditional"] and t.get("days")]
    if stated:
        counted = sorted({terms.compute(c["ctx"].calendar, term, pec, t["days"])["date"] for t in stated})
        basis = "the term stated in the evidence"
    elif term.get("days"):
        written = loose_days(ev)
        if written and written != {term["days"]}:
            return (f"the evidence writes {', '.join(map(str, sorted(written)))} day(s) in words the term reader "
                    f"does not parse; the statutory term of {act} is {term['days']} days")
        counted = [terms.compute(c["ctx"].calendar, term, pec)["date"]]
        basis = f"the statutory term of {act} ({term['days']} days, {term['id']})"
    else:
        return (f"the evidence states no term the term reader parses and {act} has no statutory term "
                "to count from")
    if a["deadline"].strip() not in counted:
        return f"counting {basis} gives {', '.join(counted)}"
    return None


def _driving_consistent(c):
    a = c["answer"]
    d = a["deadline"].strip()
    drv = dl.driving_deadline(list(c["rec"].get("deadlines") or []) + [{"date": d, "nature": a["nature"]}],
                              c["ctx"].as_of.date())
    if drv is None or drv["date"] != d:
        return f"with the deadlines the rules found, the driving deadline would be {(drv or {}).get('date')}"
    return None


def _confidence_not_low(c):
    if c["answer"].get("confidence") not in ("medium", "high"):
        return f"the model's own confidence is {c['answer'].get('confidence')}"
    return None


CHECKS = {
    "answer_usable": _answer_usable, "model_answered": _model_answered, "date_parses": _date_parses,
    "nature_known": _nature_known, "evidence_present": _evidence_present,
    "evidence_not_joined": _evidence_not_joined, "evidence_verbatim": _evidence_verbatim,
    "actionable_date_written": _actionable_date_written,
    "actionable_not_contradicted": _actionable_not_contradicted,
    "computed_notification_known": _computed_notification_known,
    "computed_act_type_known": _computed_act_type_known,
    "computed_after_notification": _computed_after_notification,
    "computed_recount": _computed_recount, "driving_consistent": _driving_consistent,
    "confidence_not_low": _confidence_not_low,
}


def evaluate(status: str, answer: dict | None, rec: dict, source: str, ctx, rules_dir=None) -> dict:
    """Apply the ordered gate rules. Returns {"passed", "rule", "kind", "reason"}; the first refusal wins."""
    c = {"status": status, "answer": answer, "rec": rec, "source": source, "ctx": ctx}
    for r in load(rules_dir)["rules"]:
        why = CHECKS[r["check"]](c)
        if why:
            return {"passed": False, "rule": r["id"], "kind": r["kind"], "reason": why}
    return {"passed": True, "rule": None, "kind": "passed", "reason": "every gate rule passed"}


def run_inline_tests(ctx, rules_dir=None) -> list[str]:
    """Each test of a rule must be decided by that rule (or pass every rule when it expects 'passed')."""
    fails = []
    cfg = load(rules_dir)
    for r in cfg["rules"]:
        for t in r["tests"]:
            i = t["input"]
            rec = {"dates": [], "deadlines": [], "doc_type": RECUPERARE, "notification_date": None,
                   "notification_note": None, "pec_time": None, **i.get("rec", {})}
            got = evaluate(i.get("status", "ok"), i.get("answer"), rec, i.get("source", cfg.get("test_source", "")), ctx,
                           rules_dir)
            want = t["expect"]["rule"]
            if (got["rule"] or "passed") != want:
                fails.append(f"{r['id']}/{t['id']}: expected {want}, got {got['rule'] or 'passed'} ({got['reason']})")
    return fails
