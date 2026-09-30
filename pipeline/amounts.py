"""Amount extraction driven by ``rules/amounts.json`` (ordered label rules)."""
from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache

from .lib import jsonio
from .rules_engine import RULES_DIR

_AMOUNT = r"(?:€|euro|eur)?\s*(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?!\d)"
_ANY_MONEY = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?!\d|[.,]\d)")


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


@lru_cache(maxsize=None)
def _rules():
    data = jsonio.read(RULES_DIR / "amounts.json")
    return tuple((r["id"], r["when"].get("doc_type"),
                  re.compile("(?:" + r["when"]["label"] + r")\W{0,6}" + _AMOUNT, re.I),
                  bool(r["when"].get("unique_amount")),
                  re.compile(r["when"]["after_not"], re.I) if "after_not" in r["when"] else None)
                 for r in data["rules"])


def distinct_amounts(text: str) -> set:
    """Every figure written as money: 1.234,56 / 1234,56 with or without a currency sign, and figures
    without decimals when a currency word stands next to them (euro 200, 1.500 €)."""
    t = re.sub(r"\s+", " ", text or "")
    out = {normalize_amount(m.group(1)) for m in _ANY_MONEY.finditer(t)}
    return out | {normalize_amount(m.group(1) or m.group(2)) for m in _INT_MONEY.finditer(t)}


def extract_amount(text: str, doc_type: str | None) -> tuple[str | None, str | None]:
    t = re.sub(r"\s+", " ", text or "")
    for rid, dts, rx, unique, after_not in _rules():
        if dts and doc_type not in (dts if isinstance(dts, list) else [dts]):
            continue
        m = rx.search(t)
        if m:
            if unique and len(distinct_amounts(t)) != 1:
                continue  # a generalised label is trusted only when the document states one amount
            if after_not is not None and after_not.search(_REST_OF_SENTENCE.split(t[m.end():m.end() + 160], maxsplit=1)[0]):
                continue  # the sentence goes on saying the figure is not a sum to pay (paid, refund, credit)
            return normalize_amount(m.group(m.lastindex)), rid
    return None, None
