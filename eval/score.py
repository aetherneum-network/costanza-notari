"""Evaluation against gold: precision / recall per document type and sender class, RECUPERARE rate,
deadline accuracy, attribution, signatures, dedup and editions.

    python eval/score.py                 # all three suites -> eval/results.json
    python eval/score.py --suite dev     # only the development corpus

Suites (honesty first):
  dev                corpus/out, seed 20260930 - the corpus the rules were developed and adjusted against.
  holdout            seed 20261001 - same generator, never inspected while writing rules.
  stress-diag-a      seed 20261002 + phrasing perturbations (corpus/perturb.py). Its FIRST run exposed
                     10 wrong committed deadlines and was used to design generic safety nets (first-pass
                     figures are kept in CHANGELOG.md): no longer blind.
  stress-diag-b      seed 20261003 + same perturbations: exposed a bug in one safety net: no longer blind.
  stress-blind       seed 20261004 + same perturbations, run once, after the code was frozen and all tests
                     passed: the headline robustness number. Not blind to the perturbation *list* itself.

A RECUPERARE prediction is an abstention: it lowers recall, never precision. Precision is computed
over committed (non-RECUPERARE) predictions. All three suites are synthetic and share templates, so
high numbers here are evidence of internal consistency, not of real-world accuracy.
"""
from __future__ import annotations

import argparse
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
SUITES = {"dev": (20260930, False), "holdout": (20261001, False), "stress-diag-a": (20261002, True),
          "stress-diag-b": (20261003, True), "stress-blind": (20261004, True)}
R = "RECUPERARE"


def build_corpus(suite: str) -> tuple[Path, Path]:
    seed, perturb = SUITES[suite]
    if suite == "dev":
        out, gold = ROOT / "corpus" / "out", ROOT / "corpus" / "gold" / "labels.jsonl"
        if not (out / "manifest.json").exists():
            subprocess.run([sys.executable, str(ROOT / "corpus" / "generate.py")], check=True, cwd=ROOT)
        return out, gold
    base = ROOT / "build" / "eval" / suite
    out, gold = base / "corpus", base / "gold.jsonl"
    if not (out / "manifest.json").exists():
        cmd = [sys.executable, str(ROOT / "corpus" / "generate.py"), "--seed", str(seed), "--out", str(out),
               "--gold", str(gold)] + (["--perturb"] if perturb else [])
        subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
    return out, gold


def run_pipeline(suite: str, corpus: Path) -> Path:
    from pipeline import run as runner
    base = ROOT / "build" / "eval" / suite / "run"
    if base.exists():
        shutil.rmtree(base)
    trust = corpus / "testca" / "trust"
    with redirect_stdout(io.StringIO()):
        code = runner.main(["--input", str(corpus), "--work", str(base / "work"), "--ledger", str(base / "ledger"),
                            "--store", str(base / "store"), "--as-of", AS_OF, "--trust", str(trust)])
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


def score(suite: str) -> dict:
    corpus, gold_path = build_corpus(suite)
    base = run_pipeline(suite, corpus)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", choices=["all", *SUITES], default="all")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.json"))
    a = ap.parse_args(argv)
    suites = list(SUITES) if a.suite == "all" else [a.suite]
    res = {s: score(s) for s in suites}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"as_of": AS_OF, "note": __doc__.strip().splitlines()[-2].strip(), "results": res},
                                      indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8",
                           newline="\n")
    print(table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
