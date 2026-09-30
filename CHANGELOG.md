# Changelog

All notable changes to the Costanza Notari v2 proof pack. Synthetic project: every entity is fictitious.

## [2.0.0] - 2026-09-30

First public proof pack of the pipeline (the thesis repository held only the profile).
Implements Appendix A (*Field Lessons for Procedural Vigilance*, DRAFT of 2026-09-30), lessons L1-L10,
table A.1 and scenarios S01-S10.

### Added
- `corpus/`: deterministic synthetic PEC corpus (300 envelopes, seed 20260930) with a TEST PKI derived from
  the seed, gold labels, `MANIFEST.sha256` and `generate.py --check` (bit-for-bit regeneration).
- `pipeline/`: nine stages reading/writing JSON state, chained by one runner with upstream-immutability
  guards, exit codes 0 / 2 (BLOCKED) / 3 (FAILED).
  - Stage 3 (signatures) contributed by **Adèle Maurique**: `signature_integrity` and
    `signer_chain_verified` as separate facts; chain validated only against the TEST root at the PEC
    provider's timestamp (`docs/SIGNATURES.md`).
- `rules/`: ordered, versioned rule files; every rule has `id`, `rationale`, `tests`.
- `scenarios/S01..S10/`: input, expected, run.md, one-line check; `scenarios/run_all.py`.
- `tests/`: stdlib `unittest`, offline; `eval/score.py` with five suites; `.github/workflows/ci.yml`.
- `docs/TERMS.md`: the procedural-term rule implemented, 9 hand-worked examples, every legal parameter
  marked **[TO CONFIRM with counsel]**.
- `packaging/SKILL.md`: design for an Agent Skill and an MCP server (parse_pec, verify_signature,
  classify_chunk, build_index). Design only.

### Changed during development - recorded because each one was decided after looking at output
- **Sender-class accept threshold 40 -> 30** (`rules/sender_class.json`) after the first run on the
  *development* corpus: a certified `pec.` domain with no competing cue is, by elimination, a corporate PEC.
  The holdout corpus (seed 20261001) was never used for tuning.
- **Urgency of expired terms** (`rules/urgency.json`, U-002 / U-002B) after the first full run showed
  189/286 units MAXIMUM: only terms expired in the last 15 days stay MAXIMUM; older expired terms are LOW
  with deadline status `expired` (if everything is red, nothing is).
- **Scanner guard G5 "other dossier"** after the self-scan of the pipeline's own outputs raised 10 false
  flags (superseded *dates* collide with other dossiers' dates far more than amounts do); build artefacts
  now carry `as_of` as their mtime (logical time, not wall clock).
- **Debtor-as-party trap** planted deterministically (the p=0.5 draw had planted none).

### Fixed after the stress suites - safety nets (null > guess)
First run of the perturbed corpus (seed 20261002, `eval/history.json`): **10 wrong committed deadlines**,
editions linked 1/6. Generic fixes, none of them teaches the parser a perturbed phrasing:
- natures use the PEC date as reference even when it is too untrusted to compute a legal term;
- a "... giorni dalla notifica" phrase that could not be parsed makes the deadline RECUPERARE;
- a date-like token in an unsupported format inside a term clause makes the deadline RECUPERARE
  (an unreadable invoice date does not); a lookaround bug in this net was found on seed 20261003;
- a parsed future date without a recognisable cue makes the deadline RECUPERARE;
- a notice that declares *"annulla e sostituisce l'atto n. EX-..."* is linked to that edition even
  without a dossier reference.

### Fixed after the single blind run (seed 20261004, measured with frozen code: 1 wrong deadline, editions 5/6)
- an unknown act type no longer computes a term with a default policy (it was one day early: the
  PEC-after-21:00 rule of the real act type was not applied) - the deadline is RECUPERARE;
- the edition reference is extracted whatever the format of its date.
Both have regression tests (`tests/test_safety_nets.py`). Post-fix numbers on seed 20261004 are reported
separately and are **no longer blind**.

### Known limitations
- OCR fallback: not available in this environment (no tesseract/pdftoppm) - scanned pages are RECUPERARE.
- No revocation checking; qualified status not assessed; TEST CA only.
- Backward terms (e.g. appearance 70 days before a hearing) and local patron-saint holidays are not modelled.
- All evaluation corpora share the generator's templates: the numbers are evidence of internal
  consistency and of honest abstention, not of real-world accuracy.
