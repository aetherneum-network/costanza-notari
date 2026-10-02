"""Evaluation against gold: precision / recall per document type and sender class, RECUPERARE rate,
deadline accuracy, attribution, signatures, dedup and editions.

    python eval/score.py                 # all named suites -> eval/results.json
    python eval/score.py --suite dev     # only the development corpus
    python eval/score.py --seed N --perturb --history-key KEY
                                         # any other seed, no code change: fresh corpus under
                                         # build/eval/seed-N-perturbed, pipeline, AGGREGATE numbers only on
                                         # stdout, one new entry in eval/history.json (eval/BLIND_PROTOCOL_v2.2.md)
    python eval/score.py --suite holdout --llm anthropic --out FILE [--llm-effort medium]
                                         # v2.3: the same with the deadline classifier ON (needs
                                         # ANTHROPIC_API_KEY, spends money; run directory .../run-llm)

Suites (honesty first):
  dev                corpus/out, seed 20260930 - the corpus the rules were developed and adjusted against.
  holdout            seed 20261001 - same generator, never inspected while writing rules.
  stress-diag-a      seed 20261002 + phrasing perturbations (corpus/perturb.py). Its FIRST run exposed
                     10 wrong committed deadlines and was used to design generic safety nets (first-pass
                     figures are kept in CHANGELOG.md): no longer blind.
  stress-diag-b      seed 20261003 + same perturbations: exposed a bug in one safety net: no longer blind.
  stress-blind       seed 20261004 + same perturbations, run once, after the v2.0 code was frozen and all
                     tests passed. Burned since: v2.1 was developed looking at it. The name is kept so that
                     the history stays readable; it is NOT a blind number any more.

A seed that is not in the list above goes through --seed and is never added to SUITES: the code does not
change between the freeze and the blind run. Blind only with respect to the seed - the perturbation *list*
of corpus/perturb.py is known to whoever wrote the rules.

A RECUPERARE prediction is an abstention: it lowers recall, never precision. Precision is computed
over committed (non-RECUPERARE) predictions. All suites are synthetic and share templates, so
high numbers here are evidence of internal consistency, not of real-world accuracy.
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AS_OF = "2026-10-21T09:40:00+02:00"
NOTE = ("A RECUPERARE prediction is an abstention: it lowers recall, never precision. All suites are synthetic "
        "and share templates: high numbers are evidence of internal consistency, not of real-world accuracy.")
SUITES = {"dev": (20260930, False), "holdout": (20261001, False), "stress-diag-a": (20261002, True),
          "stress-diag-b": (20261003, True), "stress-blind": (20261004, True)}
R = "RECUPERARE"
FRESH: set[str] = set()      # ad-hoc suites (--seed) that must start from a directory that does not exist yet
HISTORY = ROOT / "eval" / "history.json"


def build_corpus(suite: str) -> tuple[Path, Path]:
    seed, perturb = SUITES[suite]
    if suite == "dev":
        out, gold = ROOT / "corpus" / "out", ROOT / "corpus" / "gold" / "labels.jsonl"
        if not (out / "manifest.json").exists():
            subprocess.run([sys.executable, str(ROOT / "corpus" / "generate.py")], check=True, cwd=ROOT)
        return out, gold
    base = ROOT / "build" / "eval" / suite
    out, gold = base / "corpus", base / "gold.jsonl"
    if suite in FRESH and base.exists():
        raise SystemExit(f"{base} already exists: a blind run wants a fresh directory. Pass --reuse-corpus to "
                         f"score the corpus that is there (the generator is deterministic), or use another seed.")
    if not (out / "manifest.json").exists():
        cmd = [sys.executable, str(ROOT / "corpus" / "generate.py"), "--seed", str(seed), "--out", str(out),
               "--gold", str(gold)] + (["--perturb"] if perturb else [])
        subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
    return out, gold


def run_pipeline(suite: str, corpus: Path, llm=None) -> Path:
    """``llm``: a built classifier (pipeline/llm_classifier.py) or None (OFF, the default). ON runs use their
    own directory, so an OFF result is never overwritten by an ON one."""
    from pipeline import run as runner
    base = ROOT / "build" / "eval" / suite / ("run" if llm is None else "run-llm")
    if base.exists():
        shutil.rmtree(base)
    trust = corpus / "testca" / "trust"
    with redirect_stdout(io.StringIO()):
        code = runner.main(["--input", str(corpus), "--work", str(base / "work"), "--ledger", str(base / "ledger"),
                            "--store", str(base / "store"), "--as-of", AS_OF, "--trust", str(trust)], llm=llm)
    if code not in (0, 2):
        raise SystemExit(f"{suite}: pipeline failed with exit code {code}")
    return base


def prf(pairs: list[tuple[str, str]]) -> dict:
    """pairs of (gold, predicted). Returns per-class precision/recall/F1 + totals."""
    classes = sorted({g for g, _ in pairs} - {R})
    per = {}
    for c in classes:
        tp = sum(1 for g, p in pairs if g == c and p == c)
        pred = sum(1 for _, p in pairs if p == c)
        gold = sum(1 for g, _ in pairs if g == c)
        prec = tp / pred if pred else None
        rec = tp / gold if gold else None
        f1 = (2 * prec * rec / (prec + rec)) if prec and rec else 0.0
        per[c] = {"support": gold, "precision": _r(prec), "recall": _r(rec), "f1": _r(f1)}
    committed = [(g, p) for g, p in pairs if p != R]
    n = len(pairs)
    return {"per_class": per,
            "accuracy": _r(sum(1 for g, p in pairs if g == p) / n),
            "precision_committed": _r(sum(1 for g, p in committed if g == p) / len(committed)) if committed else None,
            "abstained_RECUPERARE": sum(1 for _, p in pairs if p == R),
            "wrong_committed": sum(1 for g, p in committed if g != p),
            "macro_f1": _r(sum(v["f1"] for v in per.values()) / len(per)) if per else None, "n": n}


def _r(x):
    return None if x is None else round(x, 4)


def score(suite: str, llm=None) -> dict:
    corpus, gold_path = build_corpus(suite)
    base = run_pipeline(suite, corpus, llm)
    from pipeline.lib import jsonio
    gold = {g["envelope"]: g for g in jsonio.read_jsonl(gold_path)}
    cons = jsonio.read(base / "work" / "state" / "06_consolidation.json")["records"]
    sigs = {r["record_id"]: r for r in jsonio.read(base / "work" / "state" / "03_signatures.json")["records"]}
    ledger = jsonio.read(base / "work" / "state" / "07_ledger.json")
    report = jsonio.read(base / "work" / "run_report.json")
    uniq = [r for r in cons if not gold[r["envelope"]]["duplicate_of"]]
    out = {"suite": suite, "seed": SUITES[suite][0], "perturbed": SUITES[suite][1], "envelopes": len(cons),
           "scored_unique": len(uniq), "run_status": report["status"]}
    out["doc_type"] = prf([(gold[r["envelope"]]["doc_type"], r["doc_type"]) for r in uniq])
    out["sender_class"] = prf([(gold[r["envelope"]]["sender_class"], r["sender_class"]) for r in uniq])
    out["area"] = prf([(gold[r["envelope"]]["area"], r["area"]) for r in uniq])
    attrib = {}
    for f in ("transmitter_entity", "author_entity", "party_entity", "counterparty_channel", "urgency"):
        pairs = [(gold[r["envelope"]][f], r[f]) for r in uniq]
        committed = [(g, p) for g, p in pairs if p != R]
        attrib[f] = {"accuracy": _r(sum(1 for g, p in pairs if g == p) / len(pairs)),
                     "precision_committed": _r(sum(1 for g, p in committed if g == p) / len(committed)) if committed else None,
                     "abstained": len(pairs) - len(committed), "wrong_committed": sum(1 for g, p in committed if g != p)}
    out["attribution"] = attrib
    # amounts
    am = []
    for r in uniq:
        g = gold[r["envelope"]]
        gv = R if (g["amount_due"] is None and "amount_due" in g["expected_recuperare"]) else g["amount_due"]
        pv = R if (r["amount_due"] in (None, R) and "amount_due" in r["recuperare_fields"]) else r["amount_due"]
        am.append((gv, pv))
    out["amount_due"] = {"accuracy": _r(sum(1 for g, p in am if g == p) / len(am)),
                         "wrong_committed": sum(1 for g, p in am if p not in (None, R) and g != p),
                         "abstained": sum(1 for _, p in am if p == R)}
    # deadlines
    dated = [(gold[r["envelope"]], r) for r in uniq if gold[r["envelope"]]["deadline"] not in (None, R)]
    rec_gold = [(gold[r["envelope"]], r) for r in uniq if gold[r["envelope"]]["deadline"] == R]
    none_gold = [(gold[r["envelope"]], r) for r in uniq if gold[r["envelope"]]["deadline"] is None]
    nat_pairs = []
    for r in uniq:
        g = gold[r["envelope"]]
        if g["dates"]:
            gd = Counter((d["date"], d["nature"]) for d in g["dates"])
            pd = Counter((d["date"], d["nature"]) for d in r["dates"])
            nat_pairs.append((sum((gd & pd).values()), sum(gd.values()), sum(pd.values())))
    out["deadline"] = {
        "driving_deadline_exact": _r(sum(1 for g, r in dated if r["deadline"] == g["deadline"]) / len(dated)),
        "driving_deadline_n": len(dated),
        "driving_nature_exact": _r(sum(1 for g, r in dated if r["deadline"] == g["deadline"] and
                                       r["deadline_nature"] == g["deadline_nature"]) / len(dated)),
        "wrong_date_committed": sum(1 for g, r in dated if r["deadline"] not in (R, g["deadline"])),
        "abstained_RECUPERARE": sum(1 for g, r in dated if r["deadline"] == R),
        "expected_RECUPERARE_n": len(rec_gold),
        "expected_RECUPERARE_hit": sum(1 for g, r in rec_gold if r["deadline"] == R),
        "no_deadline_expected_n": len(none_gold),
        "no_deadline_correct": sum(1 for g, r in none_gold if r["deadline"] is None),
        "written_dates_nature_recall": _r(sum(a for a, _, _ in nat_pairs) / max(1, sum(b for _, b, _ in nat_pairs))),
        "written_dates_nature_precision": _r(sum(a for a, _, _ in nat_pairs) / max(1, sum(c for _, _, c in nat_pairs))),
        "urgency_exact": attrib["urgency"]["accuracy"],
    }
    # RECUPERARE flags
    fields = ("doc_type", "area", "author_entity", "party_entity", "counterparty_channel", "amount_due", "deadline", "text")
    per_field = {}
    for f in fields:
        exp = {r["envelope"] for r in uniq if f in gold[r["envelope"]]["expected_recuperare"]}
        got = {r["envelope"] for r in uniq if f in r["recuperare_fields"]}
        tp = len(exp & got)
        per_field[f] = {"expected": len(exp), "flagged": len(got), "precision": _r(tp / len(got)) if got else None,
                        "recall": _r(tp / len(exp)) if exp else None}
    out["recuperare"] = {
        "rate_records_predicted": _r(sum(1 for r in uniq if r["recuperare_fields"]) / len(uniq)),
        "rate_records_expected": _r(sum(1 for r in uniq if gold[r["envelope"]]["expected_recuperare"]) / len(uniq)),
        "per_field": per_field}
    # signatures, dedup, editions
    s_ok = s_n = 0
    env_of = {r["record_id"]: r["envelope"] for r in cons}
    for rid, srec in sigs.items():
        gs = {s["file"]: s for s in gold[env_of[rid]]["signatures"]}
        for a in srec["attachments"]:
            s_n += 1
            g = gs.get(a["file"], {})
            s_ok += (g.get("signature_integrity"), g.get("signer_chain_verified"), g.get("chain_status")) == \
                (a["signature_integrity"], a["signer_chain_verified"], a["chain_status"])
    out["signatures"] = {"attachment_signatures": s_n, "agreement": _r(s_ok / s_n) if s_n else None,
                         "transport_agreement": _r(sum(1 for r in cons if sigs[r["record_id"]]["transport"]["signature_integrity"]
                                                       == gold[r["envelope"]]["transport_signature_integrity"]) / len(cons))}
    out["ledger"] = {"duplicates_expected": sum(1 for g in gold.values() if g["duplicate_of"]),
                     "duplicate_ignored": ledger["counts"]["duplicate_ignored"],
                     "revisions_expected": sum(1 for g in gold.values() if g["supersedes"] and not g["duplicate_of"]),
                     "supersede_events": ledger["counts"]["supersede"]}
    errs = defaultdict(list)
    for r in uniq:
        g = gold[r["envelope"]]
        for f in ("doc_type", "sender_class", "deadline"):
            if r[f] != g[f]:
                errs[f].append({"record": r["record_id"], "kind": g["kind"], "gold": g[f], "pred": r[f],
                                "hard_cases": g["hard_cases"]})
    out["error_examples"] = {k: v[:8] for k, v in sorted(errs.items())}
    out["error_counts"] = {k: len(v) for k, v in sorted(errs.items())}
    return out


def table(res: dict) -> str:
    lines = ["suite             | doc_type acc / prec(committed) / abst | sender_class acc / prec / abst | deadline exact | "
             "RECUPERARE rate pred/exp | signatures"]
    for s, r in res.items():
        d, c = r["doc_type"], r["sender_class"]
        lines.append(f"{s:17} | {d['accuracy']:.3f} / {d['precision_committed']:.3f} / {d['abstained_RECUPERARE']:3d} "
                     f"| {c['accuracy']:.3f} / {c['precision_committed']:.3f} / {c['abstained_RECUPERARE']:3d} "
                     f"| {r['deadline']['driving_deadline_exact']:.3f} | {r['recuperare']['rate_records_predicted']:.3f}/"
                     f"{r['recuperare']['rate_records_expected']:.3f} | {r['signatures']['agreement']}")
    return "\n".join(lines)


def aggregates(r: dict) -> dict:
    """The numbers of one suite that say nothing about any single record (safe to read on a blind corpus)."""
    d, dt, sc, am, led = r["deadline"], r["doc_type"], r["sender_class"], r["amount_due"], r["ledger"]
    pf, at = r["recuperare"]["per_field"], r["attribution"]
    return {
        "seed": r["seed"], "perturbed": r["perturbed"], "scored_unique": r["scored_unique"],
        "run_status": r["run_status"],
        "deadline_exact": d["driving_deadline_exact"], "deadline_n": d["driving_deadline_n"],
        "deadline_wrong_committed": d["wrong_date_committed"], "deadline_abstained": d["abstained_RECUPERARE"],
        "deadline_expected_recuperare_hit": f"{d['expected_RECUPERARE_hit']}/{d['expected_RECUPERARE_n']}",
        "no_deadline_correct": f"{d['no_deadline_correct']}/{d['no_deadline_expected_n']}",
        "written_dates_nature_recall": d["written_dates_nature_recall"],
        "written_dates_nature_precision": d["written_dates_nature_precision"],
        "recuperare_rate_predicted": r["recuperare"]["rate_records_predicted"],
        "recuperare_rate_expected": r["recuperare"]["rate_records_expected"],
        "recuperare_flagged_vs_expected": {f: f"{v['flagged']}/{v['expected']}" for f, v in sorted(pf.items())},
        "doc_type_accuracy": dt["accuracy"], "doc_type_precision_committed": dt["precision_committed"],
        "doc_type_wrong_committed": dt["wrong_committed"], "doc_type_abstained": dt["abstained_RECUPERARE"],
        "sender_class_accuracy": sc["accuracy"], "sender_class_precision_committed": sc["precision_committed"],
        "sender_class_wrong_committed": sc["wrong_committed"], "sender_class_abstained": sc["abstained_RECUPERARE"],
        "area_wrong_committed": r["area"]["wrong_committed"],
        "amount_wrong_committed": am["wrong_committed"], "amount_abstained": am["abstained"],
        "party_wrong_committed": at["party_entity"]["wrong_committed"],
        "author_wrong_committed": at["author_entity"]["wrong_committed"],
        "transmitter_wrong_committed": at["transmitter_entity"]["wrong_committed"],
        "channel_wrong_committed": at["counterparty_channel"]["wrong_committed"],
        "editions_linked": f"{led['supersede_events']}/{led['revisions_expected']}",
        "duplicates_ignored": f"{led['duplicate_ignored']}/{led['duplicates_expected']}",
        "signatures_agreement": r["signatures"]["agreement"],
    }


def code_version() -> str:
    """`git describe` of the code that produced a number; 'unknown' outside a checkout."""
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                             text=True, check=True)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def append_history(key: str, entry: dict, path: Path = HISTORY) -> None:
    """Add ONE new key at the end of history.json. Existing entries are re-written byte for byte; an existing
    key is never overwritten."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw, object_pairs_hook=collections.OrderedDict)
    if key in data:
        raise SystemExit(f"{path.name}: key '{key}' already exists - history entries are never overwritten")
    if json.dumps(data, indent=2, ensure_ascii=False) + "\n" != raw:
        raise SystemExit(f"{path.name} is not in its canonical form: refusing to rewrite it")
    data[key] = entry
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def run_seed(seed: int, perturb: bool, reuse: bool, history_key: str | None, when: str | None, out: str | None,
             llm=None) -> int:
    if history_key is not None:                     # fail before the run, not after it
        if history_key in json.loads(HISTORY.read_text(encoding="utf-8")):
            raise SystemExit(f"{HISTORY.name}: key '{history_key}' already exists - choose a new key")
    suite = f"seed-{seed}" + ("-perturbed" if perturb else "")
    SUITES[suite] = (seed, perturb)
    if not reuse:
        FRESH.add(suite)
    res = score(suite) if llm is None else score(suite, llm)
    base = ROOT / "build" / "eval" / suite
    full = Path(out) if out else base / ("result.json" if llm is None else "result-llm.json")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(json.dumps({"as_of": AS_OF, "results": {suite: res}}, indent=2, ensure_ascii=False,
                               sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    agg = aggregates(res)
    agg["code"] = code_version()
    agg["as_of"] = AS_OF
    if when:
        agg["when"] = when
    print(json.dumps({suite: agg}, indent=2, ensure_ascii=False))
    if history_key is not None:
        append_history(history_key, agg)
        print(f"appended to eval/history.json under '{history_key}'")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", choices=["all", *SUITES], default="all")
    ap.add_argument("--out", default=None, help="named suites: eval/results.json; --seed: build/eval/<dir>/result.json")
    ap.add_argument("--seed", type=int, default=None, help="score an ad-hoc corpus generated with this seed")
    ap.add_argument("--perturb", action="store_true", help="with --seed: apply corpus/perturb.py")
    ap.add_argument("--reuse-corpus", action="store_true",
                    help="with --seed: accept an existing build/eval/seed-N[-perturbed] directory")
    ap.add_argument("--history-key", default=None, help="with --seed: append the aggregates to eval/history.json")
    ap.add_argument("--when", default=None, help="with --history-key: free text stored with the entry")
    ap.add_argument("--llm", default=None, help="v2.3 deadline classifier: 'anthropic' (OFF by default; spends money)")
    ap.add_argument("--llm-effort", choices=("low", "medium", "high"), default=None, help="with --llm")
    a = ap.parse_args(argv)
    if a.llm_effort and not a.llm:
        ap.error("--llm-effort needs --llm anthropic")
    llm = None
    if a.llm:
        from pipeline import llm_classifier
        llm = llm_classifier.get(a.llm, effort=a.llm_effort)
    if a.seed is not None:
        if a.suite != "all":
            ap.error("--seed and --suite are alternatives")
        return run_seed(a.seed, a.perturb, a.reuse_corpus, a.history_key, a.when, a.out, llm)
    if a.perturb or a.reuse_corpus or a.history_key or a.when:
        ap.error("--perturb, --reuse-corpus, --history-key and --when need --seed")
    if llm is not None and not a.out:
        ap.error("--llm with named suites needs --out: eval/results.json holds the OFF numbers")
    a.out = a.out or str(ROOT / "eval" / "results.json")
    suites = list(SUITES) if a.suite == "all" else [a.suite]
    res = {s: score(s, llm) for s in suites}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"as_of": AS_OF, "note": NOTE, "results": res},
                                      indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8",
                           newline="\n")
    print(table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
