"""Per-record classification. Rule-first, deterministic, every field traceable.

The function takes the upstream state of one record (envelope, signatures,
text) and returns a classification with a ``rule_trace`` and an explicit list
of ``recuperare_fields``. It never writes shared state: dictionary aliases are
returned as proposals and merged by the ledger stage.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from functools import lru_cache

from . import amounts, attribution as attr, deadlines as dl, entities as ent, terms, typeagree, urgency
from .lib import jsonio, tzrome
from .rules_engine import RULES_DIR, RuleFile

RECUPERARE = "RECUPERARE"
_PRATICA = re.compile(r"Rif\.\s*pratica:\s*([A-Z0-9][A-Z0-9-]+)", re.I)
# the edition reference must not depend on the format of its date (found by the blind stress run)
_EDITION = re.compile(r"Rif\.\s*atto:\s*(EX-\d+)(?:\s+del\s+([^\s,;]+(?:\s+\w+\s+\d{4})?))?", re.I)
_SUPERSEDES = re.compile(r"annulla e sostituisce l['’]atto n\.\s*(EX-\d+)", re.I)


@dataclass
class Context:
    debtor: ent.Debtor
    as_of: _dt.datetime
    doc_rules: RuleFile
    area_rules: RuleFile
    terms_cfg: dict
    calendar: terms.Calendar
    expects_amount: set
    title_families: tuple = ()


def build_context(config: dict, as_of: _dt.datetime, rules_dir=None) -> Context:
    rd = rules_dir or RULES_DIR
    amounts_cfg = jsonio.read(rd / "amounts.json")
    return Context(
        debtor=ent.Debtor(config["debtor"]), as_of=as_of,
        doc_rules=RuleFile.load("doc_type.json", rd), area_rules=RuleFile.load("area.json", rd),
        terms_cfg=jsonio.read(rd / "terms.json"), calendar=terms.Calendar(jsonio.read(rd / "holidays.json")),
        expects_amount=set(amounts_cfg.get("expects_amount", [])),
        title_families=typeagree.compile_families(jsonio.read(rd / "doc_type.json")),
    )


def _term_for(ctx: Context, doc_type: str) -> dict:
    for t in ctx.terms_cfg["terms"]:
        if t["doc_type"] == doc_type:
            return t
    return {"id": "T-NONE", "days": None, "feriale_suspension": False, "saturday_rollover": False,
            "pec_after_21_rule": False, "legal_basis": "no statutory term modelled",
            "to_confirm": "[TO CONFIRM with counsel]"}


def competing_written_dates(found: list[dict], reference_iso: str | None) -> list[dict]:
    """v2.1 net for the structural nature rules (flag ``sole_candidate`` in rules/deadline_nature.json).

    Such a rule reads wordings the strict cue rules of v2.0 did not, so its reading is accepted only when
    it has no competitor: if the text writes another future date that is a term or may be one (actionable
    by any rule, or of unknown nature), the pipeline cannot tell an enumeration (the earliest drives) from
    a postponement (the latest replaces the earliest). Returns the competing dates; empty = no ambiguity."""
    sole = dl.sole_candidate_rules()
    cands = {}
    for d in found:
        if d["nature"] in ("actionable", RECUPERARE) and (reference_iso is None or d["date"] > reference_iso):
            cands.setdefault(d["date"], []).append(d)
    if len(cands) < 2 or not any(d["rule"] in sole for ds in cands.values() for d in ds):
        return []
    return [ds[0] for _, ds in sorted(cands.items())]


def _date_from_text(s: str) -> str | None:
    found = dl.find_dates(s)
    return found[0]["date"] if found else None


def classify_record(env: dict, sig: dict, txt: dict, ctx: Context) -> dict:
    rid = env["record_id"]
    dc = env.get("daticert") or {}
    inner = env.get("inner") or {}
    docs = {d["name"]: d for d in txt.get("documents", [])}
    principal = docs.get(txt.get("principal")) or {}
    text = principal.get("text", "")
    all_text = "\n".join(d.get("text", "") for d in txt.get("documents", []))
    subject = dc.get("oggetto") or inner.get("subject") or ""
    body = inner.get("body") or ""
    sender_addr = (dc.get("mittente") or inner.get("from_addr") or "").lower()
    sender_domain = sender_addr.rsplit("@", 1)[-1]
    display = inner.get("from_display") or ""
    transport = sig.get("transport") or {}
    transport_ok = transport.get("signature_integrity") == "ok"
    pdoc = next((d for d in sig.get("documents", []) if d["name"] == txt.get("principal")), {})
    trace, rec_fields, reasons = {}, [], {}

    # relative terms stated by the text (v2.1: read before the type, which may need them as a second reading)
    text_terms = dl.relative_terms(text)
    unread_terms = dl.unread_term_clauses(text)

    # sender class ---------------------------------------------------------------------------
    sc = attr.classify_sender(sender_addr, display, "\n".join([subject, body, text]), ctx.debtor)
    sender_class = sc["class"]
    trace["sender_class"] = sc["basis"]
    if sender_class == RECUPERARE:
        rec_fields.append("sender_class")
        reasons["sender_class"] = sc["basis"]

    # doc type / area ------------------------------------------------------------------------
    feats = {"subject": subject, "body": body, "text": text, "sender_domain": sender_domain,
             "sender_class": sender_class}
    then, rule = ctx.doc_rules.apply(feats)
    doc_type = then["doc_type"] if then else RECUPERARE
    trace["doc_type"] = rule or "no rule matched"
    doc_reason = "no title/subject rule matched" + (" (no readable text)" if not text else "")
    if text and (then is None or then.get("basis") in ("subject", "title_exclusive")):
        # no strict title rule. v2.2: two title readers - the title-exclusive rule that may have matched
        # (arm B's reading) and the agreement reader (arm A's) - merged by the table 'title_merge' of
        # rules/doc_type.json; None = both silent, the result of the ordered rules stands (pipeline/typeagree.py)
        merged, basis, _ = typeagree.resolve(then, rule, text, subject, text_terms, ctx.title_families, ctx.terms_cfg)
        if merged is not None:
            doc_type, trace["doc_type"], doc_reason = merged, basis, basis
    if doc_type == RECUPERARE:
        rec_fields.append("doc_type")
        reasons["doc_type"] = doc_reason
    feats["doc_type"] = doc_type
    then, rule = ctx.area_rules.apply(feats)
    area = then["area"] if then else RECUPERARE
    trace["area"] = rule or "no rule matched"
    if area == RECUPERARE:
        rec_fields.append("area")

    # entities (L5) --------------------------------------------------------------------------
    tr = attr.transmitter_entity(sender_class, display, sender_addr, ctx.debtor)
    signer_cn = pdoc.get("signer_cn") if pdoc.get("signature_integrity") == "ok" else None
    au = attr.author_entity(text, signer_cn, ctx.debtor)
    pa = attr.party_entity(text + "\n" + body, sender_class, au["value"], tr["value"], ctx.debtor)
    for f, v in (("transmitter_entity", tr), ("author_entity", au), ("party_entity", pa)):
        trace[f] = v["basis"]
        if v["value"] == RECUPERARE:
            rec_fields.append(f)
    cands = attr.collect_candidates(dc.get("mittente"), inner.get("from_addr"), inner.get("reply_to"), body, all_text)
    ch = attr.contact_channel(pa["value"], cands, sender_addr, sender_class, ctx.debtor)
    trace["counterparty_channel"] = ch["basis"]
    if ch["value"] == RECUPERARE:
        rec_fields.append("counterparty_channel")

    # notification ---------------------------------------------------------------------------
    pec_time = tzrome.parse_iso(dc["data"]) if dc.get("data") else None
    known_notif = bool(pec_time) and transport_ok and sender_class not in ctx.terms_cfg[
        "notification_date_unknown_for_sender_class"]
    term = _term_for(ctx, doc_type)
    notif_date = terms.notification_date(pec_time, term.get("pec_after_21_rule", False)) if known_notif else None
    notif_reason = None if known_notif else (
        "internal forward: act received by post, notification date unknown" if sender_class == "TARGET"
        else "transport signature not verified: daticert timestamp untrusted" if pec_time else "no daticert timestamp")

    # amounts (edition-bound) ----------------------------------------------------------------
    # v2.2: two readers (arm A's labels, arm B's label grammar) merged by 'agreement' in rules/amounts.json
    reading = amounts.read_amount(text, doc_type)
    amount, arule = reading.value, reading.rule
    trace["amount_due"] = arule or "no label matched"
    if amount and pdoc.get("signature_integrity") == "failed":
        reasons["amount_due"] = "signed document failed integrity: figure not trusted"
        amount = None
    if reading.reason:
        # the readers saw a labelled figure and do not agree on it: RECUPERARE for every document type -
        # a silent null would hide that the document states a sum
        rec_fields.append("amount_due")
        reasons["amount_due"] = reading.reason
    if amount is None and (doc_type in ctx.expects_amount or doc_type == RECUPERARE):
        rec_fields.append("amount_due")
        reasons.setdefault("amount_due", "no readable amount")
    m = _PRATICA.search(text)
    pratica = m.group(1) if m else None
    m = _EDITION.search(re.sub(r"\s+", " ", text))
    edition_ref, edition_date = (m.group(1), _date_from_text(m.group(2) or "")) if m else (None, None)
    m = _SUPERSEDES.search(re.sub(r"\s+", " ", text))
    supersedes_ref = m.group(1) if m else None

    # dates and deadlines (L6) ---------------------------------------------------------------
    # Natures need only "when was this document sent": the PEC date serves even when it is not trusted
    # enough to compute a legal term (computed terms stay RECUPERARE in that case).
    ref_iso = notif_date.isoformat() if notif_date else (
        tzrome.to_rome(pec_time).date().isoformat() if pec_time else None)
    found = []
    for d in dl.find_dates(text):
        nature, nrule = dl.classify_nature(d.get("before", ""), d.get("after", ""), d["date"], ref_iso,
                                           d.get("before_local"))
        found.append({"date": d["date"], "raw": d["raw"], "nature": nature, "rule": nrule,
                      "context": d.get("sentence", "")[:160]})
    deadlines = [{"date": d["date"], "nature": "actionable", "rule": d["rule"]} for d in found
                 if d["nature"] == "actionable"]
    rels = [r for r in text_terms if not r["conditional"]]
    conditional_rels = [r for r in text_terms if r["conditional"]]
    if not rels and term.get("days") and ctx.terms_cfg.get("statutory_defaults_used_when_text_is_silent"):
        rels = [{"days": term["days"], "raw": "statutory default", "statutory": True}]
    computed_unknown = False
    policy_unknown = doc_type == RECUPERARE and bool(rels)
    for r in rels:
        if policy_unknown:
            # act type unknown -> its term policy (suspension, roll-over, 21:00 rule) is unknown: never compute
            computed_unknown = True
            notif_reason = "act type unknown: the term's legal policy cannot be chosen"
        elif known_notif:
            c = terms.compute(ctx.calendar, term, pec_time, r["days"])
            c["source"] = r.get("raw")
            deadlines.append(c)
        else:
            computed_unknown = True
    driving = dl.driving_deadline(deadlines, ctx.as_of.date()) if deadlines else None
    expects = doc_type in ctx.terms_cfg["expects_deadline"] or doc_type == RECUPERARE
    unparsed_terms = len(unread_terms)
    unparsed_dates = dl.unparsed_date_like(text)
    # any written date of unknown nature forces RECUPERARE, as in v2.0: it may be a term, or replace one
    unknown_future = [d for d in found if d["nature"] == "RECUPERARE"]
    competing = competing_written_dates(found, ref_iso)
    deadline_rec = ((driving is None and (expects or computed_unknown)) or bool(unparsed_terms) or bool(unparsed_dates)
                    or bool(unknown_future) or bool(competing))
    if deadline_rec:
        rec_fields.append("deadline")
        if unparsed_terms:
            reasons["deadline"] = (f"{unparsed_terms} term phrase(s) could not be parsed with certainty: " + "; ".join(
                f"'{u['raw'][:60]}' ({u['why']})" for u in unread_terms[:3]))
        elif unparsed_dates:
            reasons["deadline"] = "date-like text in an unsupported format: " + ", ".join(unparsed_dates[:3])
        elif unknown_future:
            reasons["deadline"] = ("future date(s) without a recognisable cue: " + ", ".join(
                d["raw"] + ("" if d["rule"] == "N-FALLBACK" else f" ({d['rule']}: the sentence says more than the cue)")
                for d in unknown_future[:3]))
        elif competing:
            reasons["deadline"] = ("more than one future date, one of them read structurally - enumeration or "
                                   "postponement cannot be told apart: " + ", ".join(d["raw"] for d in competing[:3]))
        else:
            reasons["deadline"] = notif_reason if computed_unknown else "no actionable or computed term found"
    level, urule, days_left = urgency.compute(doc_type, driving, deadline_rec, ctx.as_of.date())
    trace["urgency"] = urule
    trace["deadline"] = (driving or {}).get("rule_id") or (driving or {}).get("rule") or ("RECUPERARE" if deadline_rec else None)
    if txt.get("text_status") in ("PARTIAL", "RECUPERARE"):
        rec_fields.append("text")
        reasons["text"] = "pages without a text layer and no OCR: " + ",".join(
            f"{d['name']}:p{p}" for d in txt.get("documents", []) for p in d.get("recuperare_pages", []))

    return {
        "record_id": rid, "envelope": env["envelope"], "content_sha256": env["sha256"],
        "subject": subject, "sender_addr": sender_addr, "sender_class": sender_class,
        "sender_scores": sc.get("scores", {}), "doc_type": doc_type, "area": area,
        "transmitter_entity": tr["value"], "author_entity": au["value"], "party_entity": pa["value"],
        "party_rejected": pa.get("rejected", []), "counterparty_channel": ch["value"],
        "channel_scores": ch.get("scored", [])[:6],
        "amount_due": amount, "pratica": pratica, "edition_ref": edition_ref, "edition_date": edition_date,
        "supersedes_ref": supersedes_ref,
        "pec_time": pec_time.isoformat() if pec_time else None,
        "notification_date": notif_date.isoformat() if notif_date else None, "notification_note": notif_reason,
        "dates": found, "conditional_terms": [{"days": r["days"], "raw": r["raw"]} for r in conditional_rels],
        "deadlines": deadlines,
        "deadline": RECUPERARE if deadline_rec else (driving or {}).get("date"),
        "deadline_nature": None if deadline_rec else (driving or {}).get("nature"),
        "deadline_status": None if deadline_rec else (driving or {}).get("status"),
        "days_left": days_left, "urgency": level,
        "transport_signature_integrity": transport.get("signature_integrity", "not_signed"),
        "principal_signature_integrity": pdoc.get("signature_integrity", "not_signed"),
        "principal_signer_chain_verified": bool(pdoc.get("signer_chain_verified")),
        "text_status": txt.get("text_status"),
        "recuperare_fields": sorted(set(rec_fields)), "recuperare_reasons": reasons, "rule_trace": trace,
    }
