"""Ordered rule files: the first match wins, exceptions go at the top (L7).

The script extracts and applies; it does not interpret. Every rule carries an
``id``, a ``rationale`` and its own ``tests``. When a record is misclassified,
fix the rule, not the output; the next run realigns everything and
``diff_classifications`` reports exactly what moved.

Supported ``when`` keys (all must hold):

    sender_domain       suffix match on the transmitter's domain (str | list)
    sender_class        equality / membership
    doc_type            equality / membership
    area                equality / membership
    heading_matches     regex on the first 600 chars of the principal text
    text_matches        regex on the full principal-attachment text
    not_text_matches    negative regex on the full text
    subject_matches     regex on the PEC subject
    body_matches        regex on the e-mail body
    any_matches         regex on subject + body + text
    text_status         equality (e.g. "RECUPERARE")
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .lib import jsonio

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

_FLAGS = re.IGNORECASE | re.MULTILINE


@lru_cache(maxsize=4096)
def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, _FLAGS)


def _as_list(v):
    return v if isinstance(v, list) else [v]


def _domain_match(domain: str | None, suffixes) -> bool:
    if not domain:
        return False
    d = domain.lower()
    return any(d == s.lower() or d.endswith("." + s.lower()) for s in _as_list(suffixes))


def matches(when: dict, f: dict) -> bool:
    for k, v in when.items():
        if k == "sender_domain":
            if not _domain_match(f.get("sender_domain"), v):
                return False
        elif k in ("sender_class", "doc_type", "area", "text_status"):
            if f.get(k) not in _as_list(v):
                return False
        elif k == "heading_matches":
            if not _rx(v).search((f.get("text") or "")[:600]):
                return False
        elif k == "text_matches":
            if not _rx(v).search(f.get("text") or ""):
                return False
        elif k == "not_text_matches":
            if _rx(v).search(f.get("text") or ""):
                return False
        elif k == "subject_matches":
            if not _rx(v).search(f.get("subject") or ""):
                return False
        elif k == "body_matches":
            if not _rx(v).search(f.get("body") or ""):
                return False
        elif k == "any_matches":
            blob = "\n".join([f.get("subject") or "", f.get("body") or "", f.get("text") or ""])
            if not _rx(v).search(blob):
                return False
        else:
            raise KeyError(f"unknown rule condition {k!r}")
    return True


class RuleFile:
    def __init__(self, data: dict, name: str = "?"):
        self.name = name
        self.version = data.get("version", "unversioned")
        self.rules = data["rules"]
        ids = [r["id"] for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{name}: duplicate rule ids")
        for r in self.rules:
            for req in ("id", "when", "then", "rationale", "tests"):
                if req not in r:
                    raise ValueError(f"{name}: rule {r.get('id')} lacks {req!r}")

    @classmethod
    def load(cls, name: str, rules_dir: Path | None = None) -> "RuleFile":
        path = (rules_dir or RULES_DIR) / name
        return cls(jsonio.read(path), name)

    def apply(self, features: dict) -> tuple[dict | None, str | None]:
        for r in self.rules:
            if matches(r["when"], features):
                return r["then"], r["id"]
        return None, None

    def run_inline_tests(self) -> list[str]:
        """Return failures (empty list = all rule tests pass)."""
        failures = []
        for r in self.rules:
            for t in r["tests"]:
                if isinstance(t, str):
                    continue  # reference to a scenario / fixture id
                then, rid = self.apply(t["input"])
                exp_rule = t.get("expect_rule", r["id"])
                if rid != exp_rule:
                    failures.append(f"{self.name}:{r['id']}:{t['id']}: matched {rid}, expected {exp_rule}")
                    continue
                for k, v in t.get("expect", {}).items():
                    if (then or {}).get(k) != v:
                        failures.append(f"{self.name}:{r['id']}:{t['id']}: {k}={then and then.get(k)!r} != {v!r}")
        return failures


def diff_classifications(before: list[dict], after: list[dict], fields=("doc_type", "area", "sender_class",
                         "urgency")) -> list[dict]:
    b = {r["record_id"]: r for r in before}
    out = []
    for r in sorted(after, key=lambda x: x["record_id"]):
        old = b.get(r["record_id"])
        if old is None:
            out.append({"record_id": r["record_id"], "change": "added"})
            continue
        for f in fields:
            if old.get(f) != r.get(f):
                out.append({"record_id": r["record_id"], "field": f, "before": old.get(f), "after": r.get(f),
                            "rule_before": old.get("rule_trace", {}).get(f),
                            "rule_after": r.get("rule_trace", {}).get(f)})
    return out
