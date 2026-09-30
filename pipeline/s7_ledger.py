"""Stage 7 - append-only ledger by ``base_id`` with edition-bound values (L2, L10).

* Append-only: ``ledger.jsonl`` is opened in append mode only; every line
  carries ``prev`` = SHA-256 of the previous line, so any rewrite of history
  is detected on the next load (and the run fails).
* Dedup: the same documentary unit arriving twice (byte-identical re-export)
  becomes a ``duplicate_ignored`` event, never a second dossier. Re-running
  the pipeline on the same corpus appends nothing (idempotent).
* Editions: a revised notice for the same ``base_id`` is a ``supersede`` event.
  Values are never "the current amount": each is bound to its source document
  and edition date - ``3,154.20 - per notice ref. EX-2231 of 2026-10-20``.
  Every superseded figure enters ``superseded_values.json``
  ``{old, new, since, proof, owners}``.
* Never delete; supersede (L10). A blocked run (L1 sentinel) does not advance
  the source of truth: its events go to ``pending_events.json`` only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import entities as ent
from .amounts import format_amount
from .lib import jsonio
from .rules_engine import RULES_DIR

RECUPERARE = "RECUPERARE"
FACT_FIELDS = ("record_id", "envelope", "content_sha256", "subject", "sender_addr", "sender_class", "doc_type", "area",
               "transmitter_entity", "author_entity", "party_entity", "counterparty_channel", "pratica",
               "edition_ref", "edition_date", "supersedes_ref", "pec_time", "notification_date", "deadlines",
               "deadline", "deadline_nature", "dates", "conditional_terms", "transport_signature_integrity",
               "principal_signature_integrity", "principal_signer_chain_verified", "text_status",
               "recuperare_fields", "recuperare_reasons", "rule_trace", "sender_scores")
TRACKED = ("amount_due", "deadline", "counterparty_channel", "party_entity", "doc_type")


class LedgerIntegrityError(RuntimeError):
    pass


def _h(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


class Ledger:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "ledger.jsonl"
        self.events: list[dict] = []
        self._last = "GENESIS"
        if self.path.exists():
            for n, raw in enumerate(self.path.read_bytes().splitlines(), start=1):
                if not raw.strip():
                    continue
                ev = json.loads(raw)
                if ev.get("prev") != self._last:
                    raise LedgerIntegrityError(f"ledger hash chain broken at line {n}: history was rewritten")
                self.events.append(ev)
                self._last = _h(raw)

    def append(self, ev: dict) -> dict:
        ev = {**ev, "seq": len(self.events) + 1, "prev": self._last}
        line = json.dumps(ev, ensure_ascii=False, sort_keys=True).encode("utf-8")
        with open(self.path, "ab") as fh:  # append mode only - never rewrite
            fh.write(line + b"\n")
        self.events.append(ev)
        self._last = _h(line)
        return ev

    def fresh(self) -> "Ledger":
        """Re-read from disk (L3: never answer from a stale in-memory copy)."""
        return Ledger(self.dir)


def base_id(rec: dict) -> str:
    party = rec.get("party_entity")
    if rec.get("pratica") and rec.get("doc_type") not in (None, RECUPERARE) and party not in (None, RECUPERARE, ent.DEBTOR_SENTINEL):
        key = f"{rec['doc_type']}|{party}|{rec['pratica']}"
    else:
        key = "content|" + rec["content_sha256"]
    return "B-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def edition_of(rec: dict) -> dict:
    return {"ref": rec.get("edition_ref") or rec.get("pratica") or rec["record_id"],
            "date": rec.get("edition_date") or rec.get("notification_date") or (rec.get("pec_time") or "")[:10] or None}


def bound(value, ed: dict, rec: dict) -> dict:
    return {"v": value, "per": ed["ref"], "edition_date": ed["date"], "source_record": rec["record_id"]}


def facts(rec: dict, ed: dict) -> dict:
    f = {k: rec.get(k) for k in FACT_FIELDS}
    f["amount_due"] = bound(rec.get("amount_due"), ed, rec)
    return f


def fold(events: list[dict]) -> dict:
    """Current view: base_id -> {facts, edition, history}. Duplicates and older editions never become current."""
    view: dict[str, dict] = {}
    for ev in events:
        op = ev.get("op")
        if op in ("insert", "supersede"):
            prev = view.get(ev["base_id"])
            view[ev["base_id"]] = {"base_id": ev["base_id"], "facts": ev["facts"], "edition": ev["edition"],
                                   "history": (prev["history"] if prev else []) + [
                                       {"seq": ev["seq"], "op": op, "edition": ev["edition"],
                                        "record_id": ev["facts"]["record_id"]}]}
        elif op in ("historical_edition", "duplicate_ignored"):
            if ev["base_id"] in view:
                view[ev["base_id"]]["history"].append({"seq": ev["seq"], "op": op, "record_id": ev.get("record_id")})
    return view


def edition_label(amount: dict | None) -> str | None:
    """'3,154.20 - per notice ref. EX-2231 of 2026-10-20' (Appendix A, L2)."""
    if not amount or amount.get("v") in (None, RECUPERARE):
        return None
    return f"{format_amount(amount['v'])} - per notice ref. {amount['per']} of {amount['edition_date']}"


def run(cons_state: dict, ledger_dir: Path, out_path: Path, *, as_of: str, release: str) -> dict:
    ledger = Ledger(ledger_dir)
    owners_by_area = jsonio.read(RULES_DIR / "misc.json")["owners"]["by_area"]
    dictionary = ent.EntityDictionary(Path(ledger_dir) / "entities.json")
    seen_content = {e["facts"]["content_sha256"]: e["facts"]["record_id"] for e in ledger.events
                    if e.get("op") in ("insert", "supersede", "historical_edition")}
    seen_dup = {(e.get("content_sha256"), e.get("envelope")) for e in ledger.events if e.get("op") == "duplicate_ignored"}
    view = fold(ledger.events)
    new_events = []
    for rec in sorted(cons_state["records"], key=lambda r: r["record_id"]):
        for f, role in (("party_entity", "party"), ("author_entity", "author"), ("transmitter_entity", "transmitter")):
            v = rec.get(f)
            if v and v not in (RECUPERARE, ent.DEBTOR_SENTINEL):
                rec[f] = dictionary.resolve(v, seen_on=(rec.get("pec_time") or "")[:10] or None, role=role)
        sha = rec["content_sha256"]
        if sha in seen_content:
            orig = seen_content[sha]
            if orig != rec["record_id"] and (sha, rec["envelope"]) not in seen_dup:
                ev = {"op": "duplicate_ignored", "at": as_of, "base_id": base_id(rec), "record_id": rec["record_id"],
                      "envelope": rec["envelope"], "content_sha256": sha, "duplicate_of": orig}
                new_events.append(ev)
                seen_dup.add((sha, rec["envelope"]))
            continue
        bid = base_id(rec)
        ed = edition_of(rec)
        cur = view.get(bid)
        if cur is None:
            ev = {"op": "insert", "at": as_of, "base_id": bid, "edition": ed, "facts": facts(rec, ed)}
        elif (ed["date"] or "", ed["ref"]) > (cur["edition"]["date"] or "", cur["edition"]["ref"]):
            old = cur["facts"]
            changes = {}
            for f in TRACKED:
                ov = old["amount_due"]["v"] if f == "amount_due" else old.get(f)
                nv = rec.get(f)
                if ov != nv:
                    changes[f] = {"old": ov, "new": nv}
            ev = {"op": "supersede", "at": as_of, "base_id": bid, "edition": ed, "supersedes": cur["edition"],
                  "supersedes_record": old["record_id"], "changes": changes, "facts": facts(rec, ed)}
        else:
            ev = {"op": "historical_edition", "at": as_of, "base_id": bid, "edition": ed, "record_id": rec["record_id"],
                  "facts": facts(rec, ed), "note": "older edition received after a newer one: kept, never current"}
        new_events.append(ev)
        seen_content[sha] = rec["record_id"]
        view = fold(ledger.events + [{**e, "seq": 10 ** 9 + i} for i, e in enumerate(new_events)])
    if release == "OK":
        for ev in new_events:
            ledger.append(ev)
        dictionary.save()
        pending = []
    else:
        pending = new_events
        jsonio.write(Path(out_path).parent / "07_pending_events.json",
                     {"why": "release BLOCKED by the handoff sentinel: the ledger was not advanced", "events": pending})
    all_events = ledger.events + [{**e, "seq": 10 ** 9 + i, "pending": True} for i, e in enumerate(pending)]
    view = fold(all_events)
    register = []
    for ev in all_events:
        if ev.get("op") != "supersede":
            continue
        area = ev["facts"].get("area")
        for f in ("amount_due", "deadline"):
            ch = ev["changes"].get(f)
            if not ch or ch["old"] in (None, RECUPERARE) or ch["new"] in (None, RECUPERARE):
                continue
            register.append({"id": f"SV-{ev['seq']:04d}-{f}" if ev["seq"] < 10 ** 9 else f"SV-PENDING-{f}",
                             "base_id": ev["base_id"], "field": f, "old": ch["old"], "new": ch["new"],
                             "since": ev["edition"]["date"], "counterparty": ev["facts"].get("party_entity"),
                             "pratica": ev["facts"].get("pratica"),
                             "proof": {"document": ev["edition"]["ref"], "supersedes": ev["supersedes"]["ref"],
                                       "record": ev["facts"]["record_id"],
                                       "supersedes_record": ev.get("supersedes_record"),
                                       "handoff": f"handoff_{ev['facts']['record_id']}.json"},
                             "owners": owners_by_area.get(area, ["amministrazione"])})
    jsonio.write(Path(ledger_dir) / "superseded_values.json", {"generated_from": "ledger.jsonl", "entries": register})
    counts = {op: sum(1 for e in all_events if e.get("op") == op) for op in
              ("insert", "supersede", "historical_edition", "duplicate_ignored")}
    state = {"stage": "s7_ledger", "release": release, "appended": len(new_events) if release == "OK" else 0,
             "pending": len(pending), "ledger_events": len(ledger.events), "counts": counts,
             "current_units": len(view), "superseded_values": register,
             "view": [view[k] for k in sorted(view)]}
    jsonio.write(out_path, state)
    return state
