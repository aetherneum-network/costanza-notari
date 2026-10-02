"""The runner: nine stages chained in ONE process (L9), loud failures (L4).

    python -m pipeline.run --input corpus/out --work build/work --ledger build/ledger \
        --store build/store --as-of 2026-10-21T09:40:00+02:00

Exit codes: 0 = OK, 2 = BLOCKED (sentinel mismatch: nothing published),
3 = FAILED (reconciliation, ledger integrity, publish conflict, crash).
The words "RUN OK" are printed only when the run is OK.

Guards between stages: every stage writes only its own files; after each
stage the runner re-hashes the outputs of all previous stages and the input
evidence, and fails the run if anything upstream changed.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

from . import (__version__, publish as pub, s1_enumerate, s2_envelope, s3_signature, s4_text, s5_classify,
               s6_consolidate, s7_ledger, s8_build, s9_distribution)
from . import llm_classifier
from .lib import jsonio, tzrome
from .rules_engine import RULES_DIR

ROOT = Path(__file__).resolve().parent.parent


class UpstreamModified(RuntimeError):
    pass


def _hash_tree(paths: list[Path]) -> dict:
    out = {}
    for base in paths:
        base = Path(base)
        if base.is_file():
            out[str(base)] = hashlib.sha256(base.read_bytes()).hexdigest()
        elif base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class Guard:
    def __init__(self):
        self.frozen: list[Path] = []
        self.snapshot: dict = {}

    def freeze(self, *paths: Path):
        self.frozen.extend(paths)
        self.snapshot = _hash_tree(self.frozen)

    def verify(self, stage: str):
        """Every frozen file must still exist with the same bytes. New files may be added."""
        changed = []
        for k, h in self.snapshot.items():
            p = Path(k)
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
                changed.append(k)
        if changed:
            raise UpstreamModified(f"{stage} modified upstream state: {changed[:3]}")


def judgement_lines(rows_state: dict, ledger_state: dict, sentinel: dict, sig_state: dict, as_of) -> list[str]:
    view = ledger_state["view"]
    exp = [u for u in view if u["facts"].get("deadline") == "RECUPERARE"]
    rec_units = [u for u in view if u["facts"].get("recuperare_fields")]
    counts = rows_state.get("urgency_counts", {})
    by_cp = {}
    for u in view:
        by_cp[u["facts"].get("party_entity")] = by_cp.get(u["facts"].get("party_entity"), 0) + 1
    top = sorted(((n, k) for k, n in by_cp.items() if k not in ("RECUPERARE", None)), key=lambda x: (-x[0], x[1]))[:3]
    unverified = sum(1 for r in sig_state["records"] for a in r["attachments"] if not a["signer_chain_verified"])
    return [
        f"Reading as of {tzrome.to_rome(as_of).strftime('%Y-%m-%d %H:%M')} (Europe/Rome): {len(view)} current documentary "
        f"units; urgency MAXIMUM {counts.get('MAXIMUM', 0)}, HIGH {counts.get('HIGH', 0)}, MEDIUM {counts.get('MEDIUM', 0)}, "
        f"LOW {counts.get('LOW', 0)}, INFORMATIONAL {counts.get('INFORMATIONAL', 0)}.",
        f"{len(exp)} unit(s) carry a term that could not be established (deadline RECUPERARE): they are shown as "
        "MAXIMUM on purpose - an unknown term is treated as the worst case, not ignored.",
        f"{len(rec_units)} unit(s) have at least one RECUPERARE field; each has a written reason in the RECUPERARE sheet.",
        "Most active counterparties: " + "; ".join(f"{k} ({n})" for n, k in top) + ".",
        f"Handoff sentinel: {sentinel['handoffs_checked']} handoffs, {len(sentinel['mismatches'])} mismatch(es); "
        f"release {sentinel['release']}.",
        f"Signatures: {unverified} attachment signature(s) whose signer chain is NOT verified against the test trust "
        "list. This says we could not verify who signed; it does not say the document is false.",
        f"Superseded values in register: {len(ledger_state['superseded_values'])}.",
    ]


def run(args, llm=None) -> dict:
    """``llm``: an already built classifier (tests and measurements inject one); otherwise ``--llm``."""
    as_of = tzrome.parse_iso(args.as_of) if args.as_of else (
        _dt.datetime.fromtimestamp(int(os.environ["SOURCE_DATE_EPOCH"]), _dt.timezone.utc)
        if os.environ.get("SOURCE_DATE_EPOCH") else _dt.datetime.now(_dt.timezone.utc))
    config = jsonio.read(Path(args.config))
    work, ledger_dir, store = Path(args.work), Path(args.ledger), Path(args.store)
    state = work / "state"
    state.mkdir(parents=True, exist_ok=True)
    inp = Path(args.input)
    trust = Path(args.trust) if args.trust else (ROOT / config["trust_anchors"])
    run_id = "RUN-" + as_of.astimezone(tzrome.UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{args.mode}"
    report = {"run_id": run_id, "pipeline_version": __version__, "as_of": as_of.isoformat(), "mode": args.mode,
              "status": "RUNNING", "stages": {}, "problems": []}
    guard = Guard()
    store_version_at_start = pub.read_version(store)
    report["store_version_read"] = store_version_at_start
    try:
        # v2.3: the classifier is built before any stage - '--llm anthropic' without a key FAILS here
        llm = llm if llm is not None else llm_classifier.get(getattr(args, "llm", None),
                                                       effort=getattr(args, "llm_effort", None))
        s1 = s1_enumerate.run(inp, state / "01_enumeration.json",
                              manifest=Path(args.manifest) if args.manifest else (inp / "manifest.json"),
                              robocopy_log=(work / "robocopy.log") if args.robocopy else None)
        report["stages"]["s1_enumerate"] = {"status": s1["status"], **{k: v for k, v in s1["reconciliation"].items()
                                                                      if not isinstance(v, list)}}
        report["problems"] += s1["problems"]
        if s1["status"] != "OK":
            raise RuntimeError("; ".join(s1["problems"]))
        evidence = [inp / r["envelope"] for r in s1["records"]]
        guard.freeze(state / "01_enumeration.json", *evidence)
        s2 = s2_envelope.run(inp, s1, work, state / "02_envelopes.json")
        guard.verify("s2_envelope")
        report["stages"]["s2_envelope"] = {"records": len(s2["records"]), "with_errors": s2["errors"]}
        guard.freeze(state / "02_envelopes.json", work / "att")
        s3 = s3_signature.run(s2, work, trust, state / "03_signatures.json")
        guard.verify("s3_signature")
        report["stages"]["s3_signature"] = s3["summary"]
        guard.freeze(state / "03_signatures.json", work / "att")  # now including the extracted .p7m contents
        engine = None
        s4 = s4_text.run(s3, work, state / "04_text.json", engine=engine)
        guard.verify("s4_text")
        report["stages"]["s4_text"] = {**s4["summary"], "ocr": s4["ocr_note"] or s4["ocr_engine"]}
        guard.freeze(state / "04_text.json")
        s5 = s5_classify.run(s2, s3, s4, config, as_of, work / "fanout", state / "05_classification.json",
                             chunk_size=config.get("chunk_size", 40), llm=llm)
        guard.verify("s5_classify")
        report["stages"]["s5_classify"] = {"chunks": len(s5["chunks"]), "records": len(s5["records"]),
                                           "llm": s5["llm"]["enabled"]}
        if s5["llm"]["enabled"]:
            report["stages"]["s5_classify"]["classifier"] = s5["llm"]["classifier"]
        guard.freeze(state / "05_classification.json", work / "fanout" / "chunks", work / "fanout" / "handoffs")
        fi = jsonio.read(Path(args.fault_injection)) if args.fault_injection else None
        s6 = s6_consolidate.run(s5, work / "fanout", state / "06_consolidation.json", fault_injection=fi)
        guard.verify("s6_consolidate")
        sentinel = s6["sentinel"]
        report["stages"]["s6_consolidate"] = {"handoffs_checked": sentinel["handoffs_checked"],
                                              "mismatches": len(sentinel["mismatches"]), "release": sentinel["release"],
                                              "json_repairs": len(sentinel["json_repairs"])}
        from .attribution import assert_debtor_excluded
        from .entities import Debtor
        assert_debtor_excluded(s6["records"], Debtor(config["debtor"]))
        guard.freeze(state / "06_consolidation.json", work / "fanout" / "receipts")
        s7 = s7_ledger.run(s6, ledger_dir, state / "07_ledger.json", as_of=as_of.isoformat(),
                           release=sentinel["release"])
        guard.verify("s7_ledger")
        report["stages"]["s7_ledger"] = {"appended": s7["appended"], "pending": s7["pending"], **s7["counts"],
                                         "current_units": s7["current_units"],
                                         "superseded_values": len(s7["superseded_values"])}
        guard.freeze(state / "07_ledger.json", ledger_dir)
        blocked = sentinel["release"] != "OK"
        if blocked:
            mm = sentinel["mismatches"][0]
            banner = (f"RELEASE BLOCKED - handoff/receipt mismatch on {len(sentinel['mismatches'])} anchor(s): "
                      f"{mm['id']} {mm['anchor']} sent {mm['sent']} by {mm['handoff_from']} ({mm['handoff_file']}), "
                      f"understood {mm['understood']} by {mm['receipt_by']} ({mm['receipt_file']})")
            kind = "blocked"
        else:
            banner = (f"RELEASE: OK - {s7['current_units']} documentary units; {sentinel['handoffs_checked']} "
                      "handoffs restated identically")
            kind = "ok"
        rules_versions = {n: jsonio.read(RULES_DIR / n).get("version") for n in
                          ("doc_type.json", "area.json", "sender_class.json", "terms.json", "urgency.json")}
        draft = work / "build"
        pre = s8_build.rows_from_view(s7["view"], as_of, {})
        pre_counts = {lv: sum(1 for x in pre if x["urgency"] == lv) for lv in s8_build.LEVELS}
        judgement = None
        if args.mode == "full":
            judgement = judgement_lines({"urgency_counts": pre_counts}, s7, sentinel, s3, as_of)
            jsonio.write(state / "judgement.json", {"as_of": as_of.isoformat(), "judgement": judgement})
        s8 = s8_build.run(s7, s3, sentinel, config, as_of, draft, run_status="BLOCKED" if blocked else "OK",
                          banner=banner, banner_kind=kind, judgement=judgement, mode=args.mode,
                          ocr_note=s4["ocr_note"], rule_versions=rules_versions)
        guard.verify("s8_build")
        report["stages"]["s8_build"] = {"rows": s8["rows"], "urgency": s8["urgency_counts"],
                                        "recuperare_units": s8["recuperare_units"],
                                        "sha256": {n: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                                   for n, p in sorted(s8["files"].items())}}
        known = sorted({u["facts"].get("party_entity") for u in s7["view"]} - {None, "RECUPERARE", "@DEBTOR"})
        outgoing = [Path(p) for p in (args.outgoing or [])] + [draft]
        responses = jsonio.read(Path(args.owner_responses)) if args.owner_responses else None
        s9 = s9_distribution.run(s7["superseded_values"], outgoing, known, state / "09_distribution.json", responses)
        guard.verify("s9_distribution")
        report["stages"]["s9_distribution"] = {"scanned": s9["scanned"], "flags_open": s9["flags_open"]}
        # publish ------------------------------------------------------------------------------
        if blocked:
            report["status"] = "BLOCKED"
            report["published"] = None
            report["problems"].append("release blocked by the handoff sentinel: nothing published; ledger not advanced")
        else:
            if args.simulate_concurrent_publish:
                # another writer republishes the store between our read and our write (S04)
                other = work / "_concurrent_writer"
                other.mkdir(parents=True, exist_ok=True)
                (other / "note.txt").write_text("republished by another writer\n", encoding="utf-8")
                prev = pub.reader_view(store, as_of)
                pub.publish(store, {"note.txt": other / "note.txt"}, if_version=pub.read_version(store),
                            as_of=prev.get("as_of") or (as_of - _dt.timedelta(days=1)).isoformat(),
                            run_id="OTHER-WRITER")
            files = {n: Path(p) for n, p in s8["files"].items()}
            res = pub.publish(store, files, if_version=store_version_at_start, as_of=as_of.isoformat(), run_id=run_id)
            report["published"] = res
            report["status"] = "OK"
    except pub.PublishConflict as exc:
        report["status"], report["failure"] = "FAILED", f"publish rejected: {exc}"
        try:  # the draft on disk must not say OK either
            s8_build.run(s7, s3, sentinel, config, as_of, work / "build", run_status="FAILED",
                         banner=f"RUN FAILED - publish rejected ({exc}); the shared store still holds older data",
                         banner_kind="failed", judgement=judgement, mode=args.mode, ocr_note=s4["ocr_note"],
                         rule_versions=rules_versions)
        except Exception:  # noqa: BLE001 - the failure is already recorded
            pass
    except Exception as exc:  # loud: any failure is a FAILED run, never "OK"
        report["status"] = "FAILED"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc().splitlines()[-6:]
    report["reader_view"] = pub.reader_view(store, as_of)
    write_report(work, report, store)
    return report


def write_report(work: Path, report: dict, store: Path) -> None:
    jsonio.write(work / "run_report.json", report)
    st = report["status"]
    lines = [f"# Run report - {st}", ""]
    if st == "FAILED":
        cur = jsonio.read(store / "version.json") if (store / "version.json").exists() else {}
        lines += [f"> **[RED BANNER] RUN FAILED - {report.get('failure')}.**",
                  f"> Readers still see store version v{cur.get('version', 0)} (data as of {cur.get('as_of', 'never')}): "
                  "treat it as STALE.", ""]
    elif st == "BLOCKED":
        lines += ["> **[RED BANNER] RELEASE BLOCKED - handoff/receipt mismatch. Nothing was published; the ledger "
                  "was not advanced.**", ""]
    else:
        lines += [f"Status: RUN OK - published store version v{report['published']['version']}.", ""]
    lines += [f"- run_id: `{report['run_id']}`", f"- as_of: `{report['as_of']}`", f"- mode: `{report['mode']}`"]
    for s, v in report["stages"].items():
        lines.append(f"- {s}: `{json.dumps(v, ensure_ascii=False, sort_keys=True)}`")
    for p in report["problems"]:
        lines.append(f"- problem: {p}")
    (work / "run_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m pipeline.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(ROOT / "corpus" / "out"))
    ap.add_argument("--config", default=str(ROOT / "corpus" / "config.json"))
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--trust", default=None, help="trust-anchor directory (default: the TEST CA only)")
    ap.add_argument("--work", default=str(ROOT / "build" / "work"))
    ap.add_argument("--ledger", default=str(ROOT / "build" / "ledger"))
    ap.add_argument("--store", default=str(ROOT / "build" / "store"))
    ap.add_argument("--as-of", default=None, help="ISO timestamp with offset; default SOURCE_DATE_EPOCH or now")
    ap.add_argument("--mode", choices=("full", "light"), default="full")
    ap.add_argument("--outgoing", action="append", help="directory of outgoing documents to scan (repeatable)")
    ap.add_argument("--owner-responses", default=None)
    ap.add_argument("--fault-injection", default=None, help="TEST ONLY: JSON fault plan for the consolidator")
    ap.add_argument("--simulate-concurrent-publish", action="store_true", help="TEST ONLY (S04)")
    ap.add_argument("--robocopy", action="store_true", help="also count with robocopy /L (Windows)")
    ap.add_argument("--llm", default=None,
                    help="optional deadline classifier: 'anthropic' (OFF by default; needs ANTHROPIC_API_KEY, "
                         "otherwise the run FAILS)")
    ap.add_argument("--llm-effort", choices=("low", "medium", "high"), default=None,
                    help="with --llm: effort of the classifier (default: $COSTANZA_LLM_EFFORT, else medium)")
    return ap


def main(argv=None, llm=None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    if args.llm_effort and not args.llm and llm is None:
        ap.error("--llm-effort needs --llm anthropic")
    rep = run(args, llm=llm)
    if rep["status"] == "OK":
        print(f"RUN OK - {rep['run_id']} - store v{rep['published']['version']} - as_of {rep['as_of']}")
        return 0
    if rep["status"] == "BLOCKED":
        print(f"RELEASE BLOCKED - {rep['run_id']} - see {Path(args.work) / 'run_report.md'}")
        return 2
    print(f"RUN FAILED - {rep['run_id']} - {rep.get('failure')}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
