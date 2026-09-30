"""Stage 5 - classification by chunked fan-out (~40 records per worker).

Each worker sees only its chunk, classifies rule-first (``pipeline.classify``)
and writes two things:

* ``chunks/chunk-NN.json``         - its full results;
* ``handoffs/handoff_<id>.json``   - per record, 1-5 *anchors*: the facts that
                                     must survive the passage to the consolidator (L1).

An optional LLM worker (``pipeline.llm_classifier``) may attach *proposals*
for fields left RECUPERARE. Proposals never overwrite a rule output and
never fill a RECUPERARE silently. Disabled by default; tests never call it.
"""
from __future__ import annotations

from pathlib import Path

from . import classify
from .lib import jsonio

ANCHOR_KEYS = ("doc_type", "amount_due", "deadline", "counterparty")


def anchors_of(rec: dict) -> list[dict]:
    vals = {"doc_type": rec.get("doc_type"), "amount_due": rec.get("amount_due") or "RECUPERARE",
            "deadline": rec.get("deadline") or "NONE", "counterparty": rec.get("party_entity")}
    return [{"k": k, "v": vals[k]} for k in ANCHOR_KEYS]


def worker(chunk_id: str, items: list[tuple[dict, dict, dict]], ctx: classify.Context, llm=None) -> list[dict]:
    out = []
    for env, sig, txt in items:
        rec = classify.classify_record(env, sig, txt, ctx)
        rec["worker"] = chunk_id
        if llm is not None and getattr(llm, "enabled", False) and rec["recuperare_fields"]:
            rec["llm_proposals"] = llm.propose(rec)  # proposals only; see llm_classifier.py
        out.append(rec)
    return out


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
        recs = worker(cid, items, ctx, llm)
        jsonio.write(fanout_dir / "chunks" / f"{cid}.json", {"chunk": cid, "records": recs})
        for rec in recs:
            jsonio.write(fanout_dir / "handoffs" / f"handoff_{rec['record_id']}.json",
                         {"id": rec["record_id"], "from": cid, "to": "consolidator", "anchors": anchors_of(rec),
                          "chunk_file": f"chunks/{cid}.json"})
        chunks.append({"chunk": cid, "records": len(recs), "first": recs[0]["record_id"], "last": recs[-1]["record_id"]})
        all_recs.extend(recs)
    state = {"stage": "s5_classify", "chunk_size": chunk_size, "chunks": chunks,
             "rules": {"doc_type": ctx.doc_rules.version, "area": ctx.area_rules.version},
             "llm": {"enabled": bool(llm is not None and getattr(llm, "enabled", False))},
             "records": all_recs}
    jsonio.write(out_path, state)
    return state
