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
    title_matches       regex on the TITLE LINES of the heading: the upper-case lines among the first
                        600 chars (v2.2, ported from arm B: an act named inside a wrapped title)
    title_not_matches   negative regex (or list of regexes) on the same title lines (exclusivity: a title
                        naming two acts matches no rule)
    title_before_words  with title_matches (v2.2 merge): on EVERY title line where title_matches hits, each
                        word before the hit must be in this list - the act is the head of the title, not
                        the object of another noun ("RISCONTRO A VOSTRA DIFFIDA"). Reference tokens
                        (anything holding a digit) are not words. An entry "@key" stands for the word list
                        stored under that key at the top of the rule file.
    title_after_words   same, for the words after the hit
    text_matches        regex on the full principal-attachment text
    not_text_matches    negative regex on the full text
    subject_matches     regex on the PEC subject
    body_matches        regex on the e-mail body
    any_matches         regex on subject + body + text
    text_status         equality (e.g. "RECUPERARE")

A pattern may hold ``{NAME}``: it is replaced by the pattern stored under ``defs.NAME`` at the top of the
rule file, so that a list shared by several rules is written once.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .lib import jsonio

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

_FLAGS = re.IGNORECASE | re.MULTILINE
HEADING_CHARS = 600     # the heading region: same window as 'heading_matches'
MAX_TITLE_LEN = 90      # a longer upper-case line is a paragraph typed in capitals, not a title
_DEF = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
_REFERENCE = re.compile(r"\S*\d\S*")      # "12/2026", "SYN-DI-0101", "N.12": a reference, not a word
_WORD = re.compile(r"[^\W\d_]+")


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


def title_line_list(text: str | None, limit: int = HEADING_CHARS) -> list[str]:
    """The structural notion of a title, shared by the two title readers: the upper-case lines (with at
    least one letter, at most MAX_TITLE_LEN characters) of the heading region. Letterheads and verb lines
    ("INTIMA", "CITA") are included and harmless; running text is never upper-case, so an act name quoted
    in a recital never counts as a title."""
    out = []
    for ln in (text or "")[:limit].splitlines():
        s = ln.strip()
        if s and len(s) <= MAX_TITLE_LEN and any(c.isalpha() for c in s) and s == s.upper():
            out.append(s)
    return out


def title_lines(text: str | None, limit: int = HEADING_CHARS) -> str:
    """The title lines joined by newlines: what 'title_matches' / 'title_not_matches' search (arm B's API)."""
    return "\n".join(title_line_list(text, limit))


def title_words(fragment: str) -> list[str]:
    """The words of a piece of a title line; reference tokens (anything holding a digit) are dropped."""
    return _WORD.findall(_REFERENCE.sub(" ", fragment))


def _title_frame_ok(when: dict, text: str | None) -> bool:
    """title_before_words / title_after_words: every title line that names the act must name it inside the
    given frame. One line that names it outside the frame ("RISCONTRO A VOSTRA DIFFIDA") is enough to
    refuse: the rule is about the whole title, not about its most favourable line."""
    act = _rx(when["title_matches"])
    before = frozenset(when["title_before_words"]) if "title_before_words" in when else None
    after = frozenset(when["title_after_words"]) if "title_after_words" in when else None
    for line in title_line_list(text):
        m = act.search(line)
        if not m:
            continue
        if before is not None and any(w not in before for w in title_words(line[:m.start()])):
            return False
        if after is not None and any(w not in after for w in title_words(line[m.end():])):
            return False
    return True


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
        elif k == "title_matches":
            if not _rx(v).search(title_lines(f.get("text"))):
                return False
        elif k == "title_not_matches":
            titles = title_lines(f.get("text"))
            if any(_rx(p).search(titles) for p in _as_list(v)):
                return False
        elif k in ("title_before_words", "title_after_words"):
            if "title_matches" not in when:
                raise KeyError(f"{k!r} needs 'title_matches' in the same rule")
            if not _title_frame_ok(when, f.get("text")):
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


def expand_defs(value, defs: dict, lists: dict):
    """Resolve the two kinds of reference a condition may hold: ``{NAME}`` inside a pattern (replaced by
    ``defs[NAME]``; only names present in ``defs`` are touched, so quantifiers such as ``{0,3}`` are safe)
    and a list entry ``"@key"`` (replaced by the word list stored under ``key`` at the top of the file)."""
    if isinstance(value, list):
        out = []
        for v in value:
            if isinstance(v, str) and v.startswith("@"):
                out.extend(lists[v[1:]])          # KeyError = a rule points at a list that does not exist
            else:
                out.append(expand_defs(v, defs, lists))
        return out
    if not isinstance(value, str):
        return value
    return _DEF.sub(lambda m: defs[m.group(1)] if m.group(1) in defs else m.group(0), value)


class RuleFile:
    def __init__(self, data: dict, name: str = "?"):
        self.name = name
        self.version = data.get("version", "unversioned")
        defs = data.get("defs", {})
        lists = {k: v for k, v in data.items() if isinstance(v, list) and all(isinstance(x, str) for x in v)}
        # file-level patterns ('defs') and word lists are written once and resolved here: the rules stay
        # readable and a list shared by several rules (or by the two title readers) cannot drift apart
        self.rules = [{**r, "when": {k: expand_defs(v, defs, lists) for k, v in r["when"].items()}}
                      if "when" in r else r for r in data["rules"]]
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
