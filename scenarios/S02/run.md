# S02 - Revised instalment; stale figure in cover letter

*Company (synthetic): Cantine Belvedere S.p.A. - Lesson L2 "A value carries its edition".*

**Failure reproduced.** Notice EX-2210 of 2026-10-02 sets the instalment of plan PR-RAT-0077 at
**3,415.20**; revised notice EX-2231 of 2026-10-20 sets it at **3,154.20**. The ledger records the
supersession (`superseded_values.json`: old 3415.20, new 3154.20, since 2026-10-20, proof EX-2231,
owners). The office's outgoing documents are then scanned.

**Planted:** 5 stale values (cover letter DOCX, e-mail summary EML, cash forecast XLSX with the raw
numeric `3415.2`, treasury notes MD, board memo DOCX table) + 1 stale value its owner already fixed
(`already_fixed` in `owner_responses.json`) + 10 decoys (untouched snapshot, snapshot/archive names,
quoted reply, side-by-side comparison, historical total, other counterparty, other dossier, near
numbers, same number in another sense). File modification dates come from `input/file_dates.json`.

**Pass criterion.** 5/5 stale values found, at most 1 false positive; findings grouped by owner; the
owner-closed flag does not count as open. Scanner precision is printed.

```
python scenarios/S02/make_input.py
python scenarios/S02/check.py
```
