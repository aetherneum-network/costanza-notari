"""Amount extraction driven by ``rules/amounts.json`` (ordered label rules).

v2.2 - two readers of ``amount_due``. The *labels* reader is arm A's (A-001..A-003, with their nets);
the *grammar* reader is arm B's label grammar (A-004), ported. Each reads the text by itself, first
match of its first matching rule, and the pair of readings is looked up in the ordered table
``agreement`` of the same file: two different figures are an abstention (A-X01); the labels reader
wins when the grammar agrees or is silent; the grammar alone commits only under the nets written in
its own rule (one monetary amount in the document, nothing after the figure that says it is not due,
no bare 'residuo').
"""
from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from typing import NamedTuple

from .lib import jsonio
from .rules_engine import RULES_DIR

_AMOUNT = r"(?:€|euro|eur)?\s*(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?!\d)"
_ANY_MONEY = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?!\d|[.,]\d)")
READERS = ("labels", "grammar")
OUTCOMES = ("labels", "grammar", "none", "RECUPERARE")


def normalize_amount(it: str) -> str:
    """'12.380,00' -> '12380.00' (string, never float)."""
    return str(Decimal(it.replace(".", "").replace(",", ".")).quantize(Decimal("0.01")))


def format_amount(v: str) -> str:
    """'3154.20' -> '3,154.20' (index/report style, as in Appendix A)."""
    q = Decimal(v).quantize(Decimal("0.01"))
    return f"{q:,.2f}"


def format_amount_it(v: str) -> str:
    return format_amount(v).replace(",", "_").replace(".", ",").replace("_", ".")


# v2.1: an amount without decimals is money only next to a currency word ("euro 200", "200 €")
_INT_MONEY = re.compile(r"(?:€|\beuro|\beur)\.?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?![.,]?\d)"
                        r"|(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:€|euro\b)", re.I)
_REST_OF_SENTENCE = re.compile(r"[.;!?](?=\s|$)")


class _Rule(NamedTuple):
    id: str
    doc_types: object          # None | str | list
    rx: re.Pattern             # label (group "label") + amount (last group)
    unique: bool
    after_not: re.Pattern | None
    label_not: re.Pattern | None
    readers: tuple             # who applies the rule: ("labels",), ("grammar",) or both


class AmountReading(NamedTuple):
    value: str | None          # normalised amount, or None
    rule: str | None           # label rule that read it; the agreement rule when the readers disagree
    agreement: str | None      # row of 'agreement' that decided
    reason: str | None         # set when the readers disagree: why nothing is committed


@lru_cache(maxsize=None)
def _config():
    data = jsonio.read(RULES_DIR / "amounts.json")
    rules = []
    for r in data["rules"]:
        w = r["when"]
        reader = w.get("reader", "labels")
        readers = READERS if reader == "both" else (reader,)
        if any(x not in READERS for x in readers):
            raise ValueError(f"amounts.json:{r['id']}: unknown reader {reader!r}")
        rules.append(_Rule(r["id"], w.get("doc_type"),
                           re.compile("(?P<label>" + w["label"] + r")\W{0,6}" + _AMOUNT, re.I),
                           bool(w.get("unique_amount")),
                           re.compile(w["after_not"], re.I) if "after_not" in w else None,
                           re.compile(w["label_not"], re.I) if "label_not" in w else None, readers))
    table = []
    for r in data.get("agreement", []):
        w, outcome = r["when"], r["then"]["outcome"]
        if outcome not in OUTCOMES or any(w[k] not in ("committed", "silent") for k in READERS):
            raise ValueError(f"amounts.json:{r['id']}: unknown reader state or outcome")
        table.append((r["id"], w["labels"], w["grammar"], w.get("same_value"), outcome))
    return tuple(rules), tuple(table)


def _rules():
    return _config()[0]


def distinct_amounts(text: str) -> set:
    """Every figure written as money: 1.234,56 / 1234,56 with or without a currency sign, and figures
    without decimals when a currency word stands next to them (euro 200, 1.500 €)."""
    t = re.sub(r"\s+", " ", text or "")
    out = {normalize_amount(m.group(1)) for m in _ANY_MONEY.finditer(t)}
    return out | {normalize_amount(m.group(1) or m.group(2)) for m in _INT_MONEY.finditer(t)}


def _read(t: str, doc_type: str | None, reader: str, nets: bool = True) -> tuple[str | None, str | None]:
    """One reader, on whitespace-normalised text: the first match of its first rule that accepts it.
    ``nets=False`` reads the label as written and ignores the rule's safety conditions: what the reader
    SEES, used only to detect a disagreement - never to commit."""
    for r in _rules():
        if reader not in r.readers:
            continue
        if r.doc_types and doc_type not in (r.doc_types if isinstance(r.doc_types, list) else [r.doc_types]):
            continue
        m = r.rx.search(t)
        if not m:
            continue
        if nets:
            if r.unique and len(distinct_amounts(t)) != 1:
                continue  # a generalised label is trusted only when the document states one amount
            if r.after_not is not None and r.after_not.search(
                    _REST_OF_SENTENCE.split(t[m.end():m.end() + 160], maxsplit=1)[0]):
                continue  # the sentence goes on saying the figure is not a sum to pay (paid, refund, credit)
            if r.label_not is not None and r.label_not.search(m.group("label")):
                continue  # the label itself says the figure is not (only) what is owed
        return normalize_amount(m.group(m.lastindex)), r.id
    return None, None


def read_amount(text: str, doc_type: str | None) -> AmountReading:
    """Both readers and the agreement table. Never commits a figure on which they differ."""
    t = re.sub(r"\s+", " ", text or "")
    a_value, a_rule = _read(t, doc_type, "labels")
    g_seen, g_seen_rule = _read(t, doc_type, "grammar", nets=False)
    state = ("committed" if a_value is not None else "silent", "committed" if g_seen is not None else "silent")
    same = (a_value == g_seen) if a_value is not None and g_seen is not None else None
    for rid, labels, grammar, same_value, outcome in _config()[1]:
        if (labels, grammar) != state or (same_value is not None and same_value != same):
            continue
        if outcome == "labels" and a_value is not None and same is not False:
            return AmountReading(a_value, a_rule, rid, None)
        if outcome == "grammar" and a_value is None:
            g_value, g_rule = _read(t, doc_type, "grammar")     # now under the nets of its own rule
            return AmountReading(g_value, g_rule, rid, None)
        if outcome == "none" and a_value is None and g_seen is None:
            return AmountReading(None, None, rid, None)
        if outcome == "RECUPERARE":
            return AmountReading(None, rid, rid, (
                f"{rid} two amount readers disagree: {a_rule} reads {a_value}, {g_seen_rule} reads {g_seen}"
                if same is False else f"{rid}: not committed"))
        break  # a row whose outcome the readings cannot support: a broken table is not a licence to commit
    if state == ("silent", "silent"):
        return AmountReading(None, None, None, None)
    return AmountReading(None, None, None, "no agreement rule for labels={}, grammar={}: not committed".format(*state))


def extract_amount(text: str, doc_type: str | None) -> tuple[str | None, str | None]:
    r = read_amount(text, doc_type)
    return r.value, r.rule
