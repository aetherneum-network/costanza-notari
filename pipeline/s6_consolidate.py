"""Stage 6 - consolidation with receipts and a sentinel (L1, L5, L6).

A handoff is two files written by two hands. The consolidator reads each
chunk, transcribes the records into the consolidated state, and writes
``receipt_<id>.json`` restating every anchor *as it understood it*, plus a
``dissent`` field. A sentinel compares handoff and receipt:

* any anchor mismatch -> that field becomes RECUPERARE, the release is
  BLOCKED, and the mismatch is reported with both ids and both authors;
* a missing or unparseable receipt is a mismatch too (an invisible handoff is
  the failure L1 exists to prevent). Single backslashes are repaired on read
  and the repair is logged (L8).

Authorship is taken from the ``from`` / ``by`` fields, never from file names (L5).
``fault_injection`` exists only for scenarios/tests (S01): it simulates the
transcription error of a real consolidator.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from .lib import jsonio
from .s5_classify import anchors_of

FIELD_OF_ANCHOR = {"doc_type": "doc_type", "amount_due": "amount_due", "deadline": "deadline",
                   "counterparty": "party_entity"}


def transpose_digits(v: str) -> str:
    """12380.00 -> 12830.00 (Appendix A, L1): swap the 3rd and 4th digits, else the next differing pair."""
    ch = list(v)
    idx = [i for i, c in enumerate(ch) if c.isdigit()]
    for a, b in zip(idx[2:], idx[3:]):
        if b == a + 1 and ch[a] != ch[b]:
            ch[a], ch[b] = ch[b], ch[a]
            return "".join(ch)
    return v


def classify_dissent(text: str | None) -> tuple[str, str]:
    cfg = jsonio.read(Path(__file__).resolve().parent.parent / "rules" / "misc.json")["dissent_nature"]
    for r in cfg["rules"]:
        if re.search(r["regex"], text or "", re.I):
            return r["nature"], r["id"]
    return "dissent", "DN-03"


def resolve_author(doc: dict) -> str:
    """L5: who wrote this file - from its fields, never from its name."""
    return doc.get("by") or doc.get("from") or "UNKNOWN"


def compare(handoff: dict, receipt: dict | None) -> list[dict]:
    if receipt is None:
        return [{"k": "*", "sent": "(handoff)", "understood": "(no receipt)"}]
    got = {a["k"]: a["v"] for a in receipt.get("anchors_as_understood", [])}
    out = []
    for a in handoff["anchors"]:
        if got.get(a["k"]) != a["v"]:
            out.append({"k": a["k"], "sent": a["v"], "understood": got.get(a["k"])})
    return out


def run(cls_state: dict, fanout_dir: Path, out_path: Path, *, fault_injection: dict | None = None) -> dict:
    fi = fault_injection or {}
    receipts_dir = fanout_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    consolidated, repairs, natures = [], [], {}
    for ch in cls_state["chunks"]:
        chunk = jsonio.load_lenient(fanout_dir / "chunks" / f"{ch['chunk']}.json", repairs)
        for rec in chunk["records"]:
            c = copy.deepcopy(rec)  # the transcription
            for f in fi.get("transpose", []):
                if f["record_id"] == c["record_id"] and c.get(f["field"]):
                    c[f["field"]] = transpose_digits(c[f["field"]])
            for f in fi.get("drop_receipt", []):
                if f == c["record_id"]:
                    c["_no_receipt"] = True
            dissent = next((d["text"] for d in fi.get("dissent", []) if d["record_id"] == c["record_id"]), "none")
            if dissent == "none" and c.get("recuperare_fields"):
                dissent = "No dissent on the merits, however fields left RECUPERARE: " + ", ".join(c["recuperare_fields"])
            nature, nrule = classify_dissent(dissent)
            natures[c["record_id"]] = nature
            if not c.pop("_no_receipt", False):
                jsonio.write(receipts_dir / f"receipt_{c['record_id']}.json",
                             {"id": c["record_id"], "by": "consolidator", "in_reply_to": f"handoff_{c['record_id']}.json",
                              "anchors_as_understood": anchors_of(c), "dissent": dissent,
                              "dissent_nature": nature, "dissent_rule": nrule})
            consolidated.append(c)
    # sentinel ------------------------------------------------------------------------------
    mismatches, checked = [], 0
    by_id = {c["record_id"]: c for c in consolidated}
    for hp in sorted((fanout_dir / "handoffs").glob("handoff_*.json")):
        h = jsonio.load_lenient(hp, repairs)
        rp = receipts_dir / f"receipt_{h['id']}.json"
        r = jsonio.load_lenient(rp, repairs) if rp.exists() else None
        checked += 1
        for mm in compare(h, r):
            mismatches.append({"id": h["id"], "anchor": mm["k"], "sent": mm["sent"], "understood": mm["understood"],
                               "handoff_file": hp.name, "handoff_from": resolve_author(h),
                               "receipt_file": rp.name if r else None, "receipt_by": resolve_author(r) if r else None})
            c = by_id.get(h["id"])
            if c is not None:
                fld = FIELD_OF_ANCHOR.get(mm["k"])
                if fld:
                    c[fld] = "RECUPERARE"
                c["recuperare_fields"] = sorted(set(c.get("recuperare_fields", [])) | {fld or "anchors"})
                c.setdefault("recuperare_reasons", {})[fld or "anchors"] = (
                    f"handoff/receipt mismatch on {mm['k']}: {mm['sent']} vs {mm['understood']}")
    disputes = [{"id": rid, "nature": n, "status": "open"} for rid, n in sorted(natures.items()) if n == "dissent"]
    release = "BLOCKED" if mismatches else "OK"
    state = {"stage": "s6_consolidate",
             "sentinel": {"handoffs_checked": checked, "mismatches": mismatches, "release": release,
                          "json_repairs": repairs},
             "dissent_natures": {n: sum(1 for v in natures.values() if v == n) for n in ("none", "note", "dissent")},
             "disputes": disputes, "records": consolidated}
    jsonio.write(out_path, state)
    return state
