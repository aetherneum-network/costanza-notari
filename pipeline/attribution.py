"""Who is who in a certified message (L5): transmitter, author, party - never collapsed.

* ``transmitter_entity``: owner of the PEC address that sent the message
  (a gateway, a lawyer's PEC, a court registry, the party itself);
* ``author_entity``: who signs the act (the lawyer, the court, the agency);
* ``party_entity`` (the counterparty): on whose behalf the act is made.

Sender class = the class of the *transmitting* address, decided by explicit
short-circuits and a weighted multi-class score with accept/margin thresholds
(``rules/sender_class.json``). Contact channel = the party's own PEC, chosen by
the weighted scorer of the thesis (+60/+30/+15/+30/-30/-50,
``rules/attribution.json``). Below threshold -> ``RECUPERARE``, never a guess.
v2.2.1: before scoring, the ordered table ``channel_sender_side`` decides whether the
sender's own addresses may be candidates at all; a third party's never are (fail closed).

The debtor is excluded *structurally*: any candidate that resolves to the
debtor is discarded before scoring, and ``assert_debtor_excluded`` fails the
run if the invariant is ever violated downstream.
"""
from __future__ import annotations

import re
from functools import lru_cache

from . import entities as ent
from .lib import jsonio
from .rules_engine import RULES_DIR

RECUPERARE = "RECUPERARE"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@lru_cache(maxsize=None)
def sender_rules() -> dict:
    return jsonio.read(RULES_DIR / "sender_class.json")


@lru_cache(maxsize=None)
def attribution_rules() -> dict:
    return jsonio.read(RULES_DIR / "attribution.json")


def _split(addr: str) -> tuple[str, str]:
    a = (addr or "").lower()
    lp, _, dom = a.partition("@")
    return lp, dom


def _any_in(hay: str, needles) -> bool:
    h = (hay or "").lower()
    return any(n.lower() in h for n in needles)


# ----------------------------------------------------------------- sender class
def classify_sender(addr: str, display: str, content: str, debtor: ent.Debtor) -> dict:
    cfg = sender_rules()
    lp, dom = _split(addr)
    for sc in cfg["short_circuits"]:
        w = sc["when"]
        if w.get("debtor_address") and debtor.is_debtor_address(addr):
            return {"class": sc["then"]["class"], "basis": sc["id"], "scores": {}}
        if "domain_suffix" in w and any(dom == s or dom.endswith("." + s) for s in w["domain_suffix"]):
            return {"class": sc["then"]["class"], "basis": sc["id"], "scores": {}}
    wts = cfg["weights"]
    scores = {}
    for cls, f in cfg["classes"].items():
        s = 0
        if f.get("domain_keywords") and _any_in(dom, f["domain_keywords"]):
            s += wts["domain_keyword"]
        if f.get("localpart_keywords") and _any_in(lp, f["localpart_keywords"]):
            s += wts["localpart_keyword"]
        if f.get("display_keywords") and _any_in(display, f["display_keywords"]):
            s += wts["display_keyword"]
        if f.get("content_cues") and any(re.search(c, content or "", re.I) for c in f["content_cues"]):
            s += wts["content_cue"]
        scores[cls] = s
    lf = cfg["classes"]["LAWYER"]
    # lawyer cues in the address or display name itself (not in the content)
    lawyer_cues = (_any_in(dom, lf.get("domain_keywords", [])) or _any_in(lp, lf.get("localpart_keywords", []))
                   or _any_in(display, lf.get("display_keywords", [])))
    corp = cfg["corporate"]
    s = 0
    if re.search(corp["pec_domain_regex"], dom):
        s += wts["corporate_pec_domain"]
    if _any_in(lp, corp["corporate_localparts"]):
        s += wts["corporate_localpart"]
    if lawyer_cues:
        s += wts["legal_class_penalty"]
    scores["CORPORATE_PEC"] = s
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    (best, bs), (_, second) = ranked[0], ranked[1]
    th = cfg["thresholds"]
    if bs >= th["accept"] and bs - second >= th["margin"]:
        return {"class": best, "basis": "score", "scores": scores}
    return {"class": RECUPERARE, "basis": f"below threshold (best {best}={bs}, margin {bs - second})",
            "scores": scores}


# ----------------------------------------------------------------- entities
_CUT = re.compile(r"\s+(?:con sede|in persona|rappresentat|elettivamente|contro|nei confronti|avverso|quale|"
                  r"c\.f\.|p\.\s?iva|domiciliat|corrente in|in qualità|tramite|a mezzo|ai sensi|difes[oa])\b.*$"
                  r"|\s+dall['’]\s*avv.*$", re.I)


def _clean_party(raw: str) -> str | None:
    s = re.sub(r"\s*\(.*$", "", raw).strip()
    s = _CUT.sub("", s).strip(" ,;:")
    if s.endswith(".") and not re.search(r"\b[A-Z]\.$", s):
        s = s[:-1]  # sentence full stop, not the dot of S.R.L. / & C.
    if not s or len(s) < 4 or EMAIL.search(s):
        return None
    if not re.search(r"[A-ZÀ-Ý]{3,}", s):
        return None
    return s


def transmitter_entity(sender_class: str, display: str, addr: str, debtor: ent.Debtor) -> dict:
    if sender_class == "TARGET" or debtor.is_debtor_address(addr):
        return {"value": ent.DEBTOR_SENTINEL, "basis": "debtor's own PEC (internal forward)"}
    d = (display or "").strip().strip('"')
    if d.lower().startswith("per conto di:"):
        d = ""
    if sender_class == "COURT":
        d = re.split(r"\s+[-–]\s+", d)[0]
    if not d:
        return {"value": RECUPERARE, "basis": "no display name on transmitting address"}
    c = ent.canonical(d)
    if debtor.is_debtor_name(c):
        return {"value": ent.DEBTOR_SENTINEL, "basis": "display name is the debtor"}
    return {"value": c, "basis": "display name of transmitting PEC"}


def author_entity(text: str, signer_cn: str | None, debtor: ent.Debtor) -> dict:
    cfg = attribution_rules()["author_rules"]
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    tail = " ".join(lines[-cfg["tail_lines"]:])
    m = None
    for m in re.finditer(cfg["lawyer_signature_regex"], tail):
        pass
    if m:
        return {"value": ent.canonical("Avv. " + m.group(1)), "basis": "A-1 lawyer signature block"}
    head = lines[0] if lines else ""
    if head and re.search(cfg["letterhead_regex"], head):
        c = ent.canonical(re.split(r"\s+[-–]\s+", head)[0])
        if not debtor.is_debtor_name(c):
            return {"value": c, "basis": "A-2 letterhead"}
    if signer_cn:
        c = ent.canonical(re.split(r"\s+[-–]\s+", re.sub(r"\s*\(TEST\)\s*$", "", signer_cn))[0])
        if not debtor.is_debtor_name(c):
            return {"value": c, "basis": "A-3 CMS signer certificate CN"}
    return {"value": RECUPERARE, "basis": "no readable text and no signer" if not lines
            else "no signature block, letterhead or signer"}


def party_entity(text: str, sender_class: str, author: str, transmitter: str, debtor: ent.Debtor) -> dict:
    cfg = attribution_rules()
    t = re.sub(r"\s+", " ", text or "")
    rejected = []
    for p in cfg["party_patterns"]:
        for m in re.finditer(p["regex"], t, re.I):
            name = _clean_party(m.group(1))
            if not name:
                continue
            if debtor.is_debtor_name(name):
                rejected.append({"candidate": ent.canonical(name), "rule": p["id"], "why": "debtor exclusion"})
                continue
            c = ent.canonical(name)
            if c.endswith("(AVV.)"):
                continue
            return {"value": c, "basis": p["id"], "rejected": rejected}
    if sender_class in cfg["party_is_sender_for"]:
        for cand, why in ((author, "author"), (transmitter, "transmitter")):
            if cand and cand not in (RECUPERARE, ent.DEBTOR_SENTINEL) and not cand.endswith("(AVV.)") \
                    and not debtor.is_debtor_name(cand):
                return {"value": cand, "basis": f"P-SELF party is the {why} ({sender_class})", "rejected": rejected}
    return {"value": RECUPERARE, "basis": "no party pattern matched", "rejected": rejected}


# ----------------------------------------------------------------- contact channel
# The tags collect_candidates gives to the addresses of the envelope itself (the sender side).
SENDER_SIDE_SOURCES = ("daticert.mittente", "from", "reply-to")
_SENDER_SIDE_VERDICTS = ("admit", "exclude")
_NAME_EVIDENCE = ("domain_keyword", "localpart_keyword")


def _sender_side_table_ok(table) -> bool:
    """The whole table is checked before any row is used: one malformed row breaks the table."""
    if not isinstance(table, list) or not table:
        return False
    ids = set()
    for row in table:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in ids:
            return False
        ids.add(row["id"])
        when, then = row.get("when"), row.get("then")
        if not isinstance(when, dict) or not isinstance(then, dict):
            return False
        if when == {"any": True}:
            pass
        elif set(when) == {"sender_class_in"}:
            cls = when["sender_class_in"]
            if not isinstance(cls, list) or not cls or not all(isinstance(c, str) for c in cls):
                return False
        else:
            return False
        if then.get("sender_side") not in _SENDER_SIDE_VERDICTS:
            return False
        if not isinstance(then.get("body_address_needs_party_name", False), bool):
            return False
    return True


def sender_side_rule(sender_class: str, rules: dict | None = None) -> dict | None:
    """First row of ``channel_sender_side`` whose ``when`` holds (first match wins, the exception on top).

    ``None`` - and the caller abstains - when the table is missing, empty or malformed, when its domain
    normaliser is missing or does not compile, or when no row matches (fail closed)."""
    rules = attribution_rules() if rules is None else rules
    table = rules.get("channel_sender_side") if isinstance(rules, dict) else None
    strip = (rules.get("channel") or {}).get("sender_side_domain_strip_regex") if isinstance(rules, dict) else None
    if not _sender_side_table_ok(table) or not isinstance(strip, str) or not strip:
        return None
    try:
        re.compile(strip)
    except re.error:
        return None
    for row in table:
        if row["when"] == {"any": True} or sender_class in row["when"]["sender_class_in"]:
            return row
    return None


def _org_domain(dom: str, strip_regex: str) -> str:
    """Organisational domain: the leading PEC label is dropped when at least two labels remain
    (``pec.bancavalmarina.example`` -> ``bancavalmarina.example``; ``pec.it`` stays ``pec.it``)."""
    d = (dom or "").lower().strip(".")
    s = re.sub(strip_regex, "", d, count=1)
    return s if "." in s else d


def _same_org(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def contact_channel(party: str, candidates: list[dict], transmitter_addr: str, sender_class: str,
                    debtor: ent.Debtor, rules: dict | None = None) -> dict:
    """candidates: [{"addr":..., "context": text before the address, "source": ...}]

    Before any scoring, ``channel_sender_side`` (ordered, first match wins) decides whether the sender's
    own addresses may be candidates. For a third-party sender they are not, nor is any address on the
    sender's organisational domain; a committed channel then needs the party's own name in the address.
    ``rules`` defaults to ``rules/attribution.json`` (tests pass a modified copy)."""
    rules = attribution_rules() if rules is None else rules
    cfg = rules["channel"]
    w, th = cfg["weights"], cfg["thresholds"]
    if party in (None, RECUPERARE, ent.DEBTOR_SENTINEL):
        return {"value": RECUPERARE, "basis": "party unknown", "scored": []}
    row = sender_side_rule(sender_class, rules)
    if row is None:
        return {"value": RECUPERARE, "basis": "sender-side table missing, broken or silent: fail closed",
                "scored": [], "sender_rule": None}
    admit = row["then"]["sender_side"] == "admit"
    needs_name = row["then"].get("body_address_needs_party_name", False)
    strip = cfg["sender_side_domain_strip_regex"]
    sender_addrs = {a for a in [(transmitter_addr or "").lower()]
                    + [c["addr"].lower() for c in candidates if c.get("source") in SENDER_SIDE_SOURCES] if "@" in a}
    sender_orgs = {_org_domain(_split(a)[1], strip) for a in sender_addrs}
    toks = ent.name_tokens(party)
    seen, scored, excluded = set(), [], []
    for c in candidates:
        a = c["addr"].lower()
        if a in seen:
            continue
        seen.add(a)
        if debtor.is_debtor_address(a):
            continue  # structural exclusion: never the debtor's channel
        if any(re.search(x, a) for x in cfg["excluded_address_regex"]):
            continue
        lp, dom = _split(a)
        if not admit and (a in sender_addrs or any(_same_org(_org_domain(dom, strip), o) for o in sender_orgs)):
            excluded.append(a)  # structural exclusion: a third party's address is never the party's channel
            continue
        s, why = 0, []
        compact_dom = dom.replace("-", "").replace(".", "")
        if toks and any(tk in compact_dom for tk in toks):
            s += w["domain_keyword"]; why.append("domain_keyword")
        if toks and any(tk in lp for tk in toks):
            s += w["localpart_keyword"]; why.append("localpart_keyword")
        if _any_in(lp, cfg["corporate_localparts"]):
            s += w["corporate_localpart"]; why.append("corporate_localpart")
        if re.search(cfg["pec_domain_regex"], dom):
            s += w["corporate_pec"]; why.append("corporate_pec")
        if _any_in(a, cfg["legal_keywords"]) or (sender_class == "LAWYER" and a == (transmitter_addr or "").lower()):
            s += w["legal_class"]; why.append("legal_class")
        if re.search(cfg["declared_contact_regex"], c.get("context", ""), re.I):
            s += w["declared_contact"]; why.append("declared_contact")
        scored.append({"addr": a, "score": s, "why": why, "source": c.get("source")})
    scored.sort(key=lambda x: (-x["score"], x["addr"]))
    note = f"; {row['id']} excluded {len(excluded)} sender-side address(es)" if excluded else ""
    accepted = [x for x in scored if x["score"] >= th["accept"]
                and (not needs_name or any(k in x["why"] for k in _NAME_EVIDENCE))]
    if not accepted:
        best = scored[0]["score"] if scored else None
        return {"value": RECUPERARE, "basis": f"no candidate >= {th['accept']} (best {best}){note}", "scored": scored,
                "sender_rule": row["id"], "excluded": excluded}
    if len(accepted) > 1 and accepted[0]["score"] - accepted[1]["score"] < th["margin"]:
        return {"value": RECUPERARE, "basis": f"ambiguous: two accepted candidates within margin{note}",
                "scored": scored, "sender_rule": row["id"], "excluded": excluded}
    return {"value": accepted[0]["addr"], "basis": f"score{note}", "scored": scored, "sender_rule": row["id"],
            "excluded": excluded}


def run_sender_side_tests(debtor: ent.Debtor, rules: dict | None = None) -> list[str]:
    """Inline ``tests`` of ``channel_sender_side``: each must be decided by its own row. Returns failures."""
    rules = attribution_rules() if rules is None else rules
    bad = []
    for row in rules.get("channel_sender_side") or []:
        for t in row.get("tests") or []:
            i = t["input"]
            cands = collect_candidates(i["sender"], i.get("from", i["sender"]), i.get("reply_to"), "", i["text"])
            got = contact_channel(i["party"], cands, i["sender"], i["sender_class"], debtor, rules)
            if (got["value"], got.get("sender_rule")) != (t["expect"]["channel"], row["id"]):
                bad.append(f"{t['id']}: got {got['value']} by {got.get('sender_rule')} ({got['basis']})")
    return bad


def collect_candidates(daticert_from: str, inner_from: str, reply_to: str | None, body: str, text: str) -> list[dict]:
    out = []
    for a, src in ((daticert_from, "daticert.mittente"), (inner_from, "from"), (reply_to, "reply-to")):
        if a:
            out.append({"addr": a, "context": "", "source": src})
    for blob, src in ((body, "body"), (text, "attachment")):
        t = re.sub(r"\s+", " ", blob or "")
        for m in EMAIL.finditer(t):
            out.append({"addr": m.group(0).rstrip("."), "context": t[max(0, m.start() - 60):m.start()],
                        "source": src})
    return out


def assert_debtor_excluded(records: list[dict], debtor: ent.Debtor) -> None:
    """Hard invariant. Raises (fails the run) - never a warning."""
    for r in records:
        for f in ("party_entity", "author_entity", "transmitter_entity"):
            v = r.get(f)
            if v and v != ent.DEBTOR_SENTINEL and debtor.is_debtor_name(v):
                raise AssertionError(f"debtor exclusion violated: {r['record_id']}.{f} = {v}")
        ch = r.get("counterparty_channel")
        if ch and ch != RECUPERARE and debtor.is_debtor_address(ch):
            raise AssertionError(f"debtor exclusion violated: {r['record_id']}.counterparty_channel = {ch}")
