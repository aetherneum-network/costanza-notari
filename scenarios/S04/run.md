# S04 - Version conflict on publish

*Company (synthetic): Fornace Aurelia S.r.l. - Lesson L4 "A failed write must be loud".*

**Failure reproduced.** Yesterday's run (as of 2026-10-20 03:05) published store version v1. Today's
run (as of 2026-10-21 09:40) reads v1, classifies, builds - and meanwhile another writer republishes
the store (v2, still carrying yesterday's data). Today's `publish(if_version=1)` is rejected.

**Pass criterion.** Exit code 3 and run status `FAILED` (never "OK"); the red banner is in
`run_report.md` and in the draft index header; readers of the shared store see v2 with yesterday's
`as_of`, explicitly flagged `STALE DATA`.

```
python scenarios/S04/check.py
```

The subset (20 envelopes) is copied from the generated corpus at run time; `input/scenario.json`
describes it.
