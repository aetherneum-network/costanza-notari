"""Amount extraction driven by ``rules/amounts.json`` (ordered label rules)."""
from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache

from .lib import jsonio
from .rules_engine import RULES_DIR

_AMOUNT = r"(?:€|euro|eur)?\s*(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?!\d)"


def normalize_amount(it: str) -> str:
    """'12.380,00' -> '12380.00' (string, never float)."""
    return str(Decimal(it.replace(".", "").replace(",", ".")).quantize(Decimal("0.01")))


def format_amount(v: str) -> str:
    """'3154.20' -> '3,154.20' (index/report style, as in Appendix A)."""
    q = Decimal(v).quantize(Decimal("0.01"))
    return f"{q:,.2f}"


def format_amount_it(v: str) -> str:
    return format_amount(v).replace(",", "_").replace(".", ",").replace("_", ".")


@lru_cache(maxsize=None)
def _rules():
    data = jsonio.read(RULES_DIR / "amounts.json")
    return tuple((r["id"], r["when"].get("doc_type"),
                  re.compile("(?:" + r["when"]["label"] + r")\W{0,6}" + _AMOUNT, re.I))
                 for r in data["rules"])


def extract_amount(text: str, doc_type: str | None) -> tuple[str | None, str | None]:
    t = re.sub(r"\s+", " ", text or "")
    for rid, dts, rx in _rules():
        if dts and doc_type not in (dts if isinstance(dts, list) else [dts]):
            continue
        m = rx.search(t)
        if m:
            return normalize_amount(m.group(m.lastindex)), rid
    return None, None
