# S01 - Transposed amount at handoff

*Company (synthetic): Fornace Aurelia S.r.l. - Lesson L1 "Every handoff has a receipt".*

**Failure reproduced.** 200 classified records (ARC-0301..ARC-0500) go through the fan-out in chunks of 40.
Record ARC-0412 carries the Appendix A figures (notice of assessment, 12,380.00, 2026-11-14,
AGENZIA ESEMPIO RISCOSSIONE). The fault plan makes the consolidator transcribe **12830.00**.

**Pass criterion.** Release `BLOCKED`; exactly one mismatch, reported with both ids and both authors
(`handoff_ARC-0412.json` from `chunk-03`, `receipt_ARC-0412.json` by `consolidator`); zero false blocks
on the other 199. End to end, the same kind of fault in a real run on a 40-envelope subset of the
corpus exits with code 2, publishes nothing, does not advance the ledger, and the draft index shows the
red `RELEASE BLOCKED` banner.

```
python scenarios/S01/make_input.py     # regenerates input/ (deterministic, already committed)
python scenarios/S01/check.py          # one line: S01 PASS / S01 FAIL
```

Inputs: `input/records.jsonl`, `input/fault_plan.json` (TEST ONLY). Expected: `expected/expected.json`.
