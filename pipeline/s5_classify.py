"""Stage 5 - classification by chunked fan-out (~40 records per worker).

Each worker sees only its chunk, classifies rule-first (``pipeline.classify``)
and writes two things:

* ``chunks/chunk-NN.json``         - its full results;
* ``handoffs/handoff_<id>.json``   - per record, 1-5 *anchors*: the facts that
                                     must survive the passage to the consolidator (L1).

v2.3: an optional deadline classifier (``pipeline.llm_classifier``, OFF by default, tests never call
it) is asked about the records whose DEADLINE the rules left RECUPERARE, and only those. Its answer goes
through the deterministic gate (``pipeline.classifier_gate``): a value that passes every gate rule fills the
deadline, marked as the classifier's (``deadlines[].source == "classifier"``, rule_trace, ``classifier``
block); anything else abstains and the record keeps the gate rule that refused it. The rules' own reason
is moved, not lost, to ``classifier.rules_reason``. With the classifier OFF nothing here changes a byte.
"""
from __future__ import annotations

from pathlib import Path

from . import classifier_gate, classify, deadlines as dl, urgency
from .lib import jsonio

ANCHOR_KEYS = ("doc_type", "amount_due", "deadline", "counterparty")


def anchors_of(rec: dict) -> list[dict]:
    vals = {"doc_type": rec.get("doc_type"), "amount_due": rec.get("amount_due") or "RECUPERARE",
            "deadline": rec.get("deadline") or "NONE", "counterparty": rec.get("party_entity")}
    return [{"k": k, "v": vals[k]} for k in ANCHOR_KEYS]


def commit(rec: dict, cls: dict, ctx: classify.Context) -> None:
    """Fill the deadline with a gate-passed classifier answer. Rule outputs are never overwritten: the
    deadline was RECUPERARE, and the rules' reason is moved into the classifier block."""
    a = cls["answer"]
    d = a["deadline"].strip()
    basis = f"classifier {cls['model']} ({cls['effort']}), gate passed"
    entry = {"date": d, "nature": a["nature"], "rule_id": basis, "source": "classifier",
             "act_type": a.get("act_type"), "evidence": a.get("evidence"), "computation": a.get("computation")}
    rec["deadlines"] = list(rec.get("deadlines") or []) + [entry]
    drv = dl.driving_deadline(rec["deadlines"], ctx.as_of.date())   # == d: gate rule driving_consistent
    level, urule, days_left = urgency.compute(rec["doc_type"], drv, False, ctx.as_of.date())
    rec.update(deadline=drv["date"], deadline_nature=drv["nature"], deadline_status=drv["status"],
               days_left=days_left, urgency=level)
    rec["rule_trace"]["urgency"] = urule
    rec["rule_trace"]["deadline"] = basis
    rec["recuperare_fields"] = [f for f in rec["recuperare_fields"] if f != "deadline"]
    cls["rules_reason"] = rec["recuperare_reasons"].pop("deadline", None)


def worker(chunk_id: str, items: list[tuple[dict, dict, dict]], ctx: classify.Context, llm=None,
           rules_dir=None) -> list[dict]:
    out = []
    on = llm is not None and getattr(llm, "enabled", False)
    for env, sig, txt in items:
        rec = classify.classify_record(env, sig, txt, ctx)
        rec["worker"] = chunk_id
        if on and "deadline" in rec["recuperare_fields"]:
            cls = llm.propose(rec, env, txt, ctx.as_of)
            cls["gate"] = classifier_gate.evaluate(cls["status"], cls["answer"], rec,
                                                   classifier_gate.source_text(env, txt), ctx, rules_dir)
            cls["gate"]["version"] = classifier_gate.load(rules_dir)["version"]
            if cls["gate"]["passed"]:
                commit(rec, cls, ctx)
            rec["classifier"] = cls
        out.append(rec)
    return out


def classifier_summary(recs: list[dict], llm) -> dict:
    """Counts by gate outcome and summed token usage (no prices: cost is computed by whoever knows them)."""
    called = [r["classifier"] for r in recs if "classifier" in r]
    kinds = {}
    for c in called:
        kinds[c["gate"]["kind"]] = kinds.get(c["gate"]["kind"], 0) + 1
    usage = {}
    for c in called:
        for k, v in (c.get("usage") or {}).items():
            if isinstance(v, int):
                usage[k] = usage.get(k, 0) + v
    return {"model": getattr(llm, "model", None), "effort": getattr(llm, "effort", None), "called": len(called),
            "committed": kinds.get("passed", 0), "model_abstained": kinds.get("model_abstained", 0),
            "gate_refused": kinds.get("refusal", 0), "no_answer": kinds.get("no_answer", 0),
            "refused_by_rule": {k: sum(1 for c in called if c["gate"]["kind"] == "refusal" and c["gate"]["rule"] == k)
                                for k in sorted({c["gate"]["rule"] for c in called if c["gate"]["kind"] == "refusal"})},
            "usage": dict(sorted(usage.items()))}


def run(env_state: dict, sig_state: dict, txt_state: dict, config: dict, as_of, fanout_dir: Path,
        out_path: Path, *, chunk_size: int = 40, llm=None, rules_dir=None) -> dict:
    ctx = classify.build_context(config, as_of, rules_dir)
    sig = {r["record_id"]: r for r in sig_state["records"]}
    txt = {r["record_id"]: r for r in txt_state["records"]}
    envs = sorted(env_state["records"], key=lambda r: r["record_id"])
    (fanout_dir / "chunks").mkdir(parents=True, exist_ok=True)
    (fanout_dir / "handoffs").mkdir(parents=True, exist_ok=True)
    chunks, all_recs = [], []
    for n, i in enumerate(range(0, len(envs), chunk_size), start=1):
        cid = f"chunk-{n:02d}"
        items = [(e, sig[e["record_id"]], txt[e["record_id"]]) for e in envs[i:i + chunk_size]]
        recs = worker(cid, items, ctx, llm, rules_dir)
        jsonio.write(fanout_dir / "chunks" / f"{cid}.json", {"chunk": cid, "records": recs})
        for rec in recs:
            jsonio.write(fanout_dir / "handoffs" / f"handoff_{rec['record_id']}.json",
                         {"id": rec["record_id"], "from": cid, "to": "consolidator", "anchors": anchors_of(rec),
                          "chunk_file": f"chunks/{cid}.json"})
        chunks.append({"chunk": cid, "records": len(recs), "first": recs[0]["record_id"], "last": recs[-1]["record_id"]})
        all_recs.extend(recs)
    on = bool(llm is not None and getattr(llm, "enabled", False))
    state = {"stage": "s5_classify", "chunk_size": chunk_size, "chunks": chunks,
             "rules": {"doc_type": ctx.doc_rules.version, "area": ctx.area_rules.version},
             "llm": {"enabled": on, **({"classifier": classifier_summary(all_recs, llm)} if on else {})},
             "records": all_recs}
    jsonio.write(out_path, state)
    return state
