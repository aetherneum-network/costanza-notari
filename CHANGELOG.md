# Changelog

All notable changes to the Costanza Notari v2 proof pack. Synthetic project: every entity is fictitious.

## [2.1.0] - 2026-09-30

Goal: fewer abstentions on deadline reading, **without one wrong committed deadline**. v2.0 abstained on
92-115 of ~254 dated deadlines of the perturbed corpora (0 wrong); v2.1 abstains on 0 of them, still 0 wrong
(`eval/history.json`, key `v2_1_before_blind`, before/after per suite). None of the five corpora is blind
for v2.1; the blind run on a new seed is described in `eval/BLIND_PROTOCOL_v2.1.md` and has **not** been
made at the time of this entry.

### Added - each mechanism abstains when it is not sure
- **Structural term-clause reader** (`pipeline/termclauses.py`, `rules/term_clauses.json`, rules
  TC-L01..TC-M02). A relative term is read slot by slot: lead-in (*entro / nel termine di / non oltre /
  nei*), quantity (number + unit, digits or words, either order: *dieci giorni*, *giorni 10*,
  *10 (dieci) giorni*), qualifier, anchor event (*notifica / ricevimento*), complement, mood.
  The quantity is read by **two independent readers** - a regular-expression grammar whose number words come
  from a generated table, and a token scanner that walks left from the anchor and parses the cardinal
  compositionally; a clause is committed only when both give the same number of days (exhaustive test on
  1..999 in five shapes). Every slot value is decided by a rule; a value no rule knows makes the clause
  *unread*: months / weeks, *lavorativi / liberi / utili*, a term running from the notification of another
  act, a recital in the past, a term modified by the rest of the sentence, an unknown lead-in or anchor. An unread clause makes the deadline RECUPERARE
  with a reason code and is never replaced by the statutory default. Two loose detectors surface anything
  that looks like a term from an event and was not read.
- **Numeric date formats** (`pipeline/deadlines.py`, `_DATE_NUM`): `dd/mm/yyyy`, `dd.mm.yyyy`, `dd-mm-yyyy`,
  one separator used twice, four-digit year, not glued to a letter-hyphen code. Mixed separators,
  two-digit years and impossible dates stay unparsed (and are still caught by the v2.0 net).
- **N-008, structural nature rule** (`rules/deadline_nature.json`): term noun + future, deontic or
  *è fissata* verb + linker + date later than the reference (*l'udienza si terrà il*, *la rata dovrà essere
  corrisposta il*, *il termine è fissato al*) = actionable. *Pagamento / versamento / adempimento / saldo*
  count only with a deontic verb (*il pagamento avverrà il* does not say who pays). Negations, conditions
  and *potrà* are stop words. Its reading is accepted only as the **sole candidate** (`then.sole_candidate`,
  `classify.competing_written_dates`): if the text writes another future date that is or may be a term, an
  enumeration cannot be told from a postponement and the deadline is RECUPERARE.
- **N-009, dateline rule**: a line made of a place and a date is the date of the document (historical),
  also when the transport timestamp is earlier - only if the date is at most 7 days after the notification
  and no time of day follows it. This rule closes the single dev abstention of v2.0 (0.996 -> 1.000).
- **Document type by agreement** (`pipeline/typeagree.py`, `title_families` in `rules/doc_type.json`,
  TF-001..TF-013): used only where the strict title rules do not match. The upper-case title line must name
  a family inside a neutral frame (*ATTO DI, LETTERA DI, ... E ...*); the type is committed only when exactly
  one named family is confirmed by an independent reading - the PEC subject or the term the text states
  (`rules/terms.json`, days + event). No confirmation, two confirmed families, or a foreign word in the
  title (*OPPOSIZIONE A PRECETTO*, *PREAVVISO DI*, *RISCONTRO A*) = RECUPERARE, **and the subject-only
  fallback of v2.0 is vetoed**: v2.1 abstains on titles where v2.0 committed on the subject alone.
- **A-003, generalised amount label** (`rules/amounts.json`, `pipeline/amounts.py`): *importo / somma /
  totale* + up to three qualifiers from an allow-list (*complessivo, dovuto, a debito, da pagare...*) +
  `:` or `di`, committed only if the document contains exactly one money figure (`unique_amount`).
- **Generic evaluation path** (`eval/score.py --seed N --perturb [--history-key K]`): any seed without a
  code change, fresh directory enforced, aggregate numbers only on stdout, append-only `eval/history.json`.

### Safety pass before the freeze - nets around the new readings
Made by running v2.0 and v2.1 side by side on about ninety hand-written texts that are **not** in the
perturbation pool (postponements, cancellations, recitals, modified terms, paid or credited amounts) and
looking for answers that v2.0 abstained on and v2.1 committed wrongly. Every item below only turns a
committed answer into RECUPERARE; on the five corpora the aggregates are identical with and without them.
- **Removed: relevance shortcut for unknown dates.** A development build ignored a date of unknown nature
  when it fell after the driving deadline. On *"l'udienza del 12/11/2026 ... Proroga concessa fino al
  15/12/2026"* it committed the old date. v2.1 keeps the v2.0 net: any written future date of unknown
  nature makes the deadline RECUPERARE.
- **N-V01 / N-V02, vetoes** (`rules/deadline_nature.json`, `vetoes`; applied to every actionable reading,
  v2.0 cue rules included): after the date, a negation or a predicate that is not a plain confirmation
  (*è rinviata al ..., è annullata, viene anticipata, non si terrà, si intende sostituita*); before the date,
  a negation in the same clause (*l'udienza non è più fissata al*; not *entro e non oltre*, *non prorogabile*).
  The date becomes of unknown nature. v2.0 committed `udienza del 12/11/2026 è rinviata a data da destinarsi`.
- **`across_a_date`** on N-002, N-007, N-008: a lead-in found only by reading across an earlier date of the
  same sentence is not trusted (*"originariamente prevista per il 12/11/2026, si terrà il 15/12/2026"*:
  v2.0 classed both dates as historical and answered "no deadline"; v2.1 answers RECUPERARE).
- **TC-M03, TC-M04, TC-M05** (`rules/term_clauses.json`, mood rules with `side: after`): a term clause that
  goes on as a recital (*non è stato effettuato alcun pagamento, è inutilmente decorso, avrebbe potuto
  proporre opposizione*) or modifies the term it has just stated (*ridotti a dieci, prorogati di ulteriori
  venti, termine sospeso*) is unread. v2.0 computed `entro venti giorni dalla notifica, ridotti a dieci`
  as twenty days.
- **Amounts**: `after_not` on A-002 and A-003 (*già corrisposto, da rimborsare a Voi, a Vostro favore, non
  dovuto* after the figure = not an amount due); the uniqueness check of A-003 also counts amounts written
  without decimals next to a currency word (*oltre euro 200 di spese*).
- **Tried and dropped - subject naming another act.** Making a PEC subject that names a different act veto
  a title confirmed by the stated term cost 2 / 4 / 3 correct document types (and their deadlines) on the
  three perturbed corpora: the corpus plants misleading subjects on purpose and its gold follows the title,
  as the v2.0 strict rules already do (DT-014). Not in the release; `pipeline/typeagree.py` says so.

### Known limits left as they were in v2.0 (seen in the same comparison, not changed)
- Two future dates both read by v2.0 cue rules: the earliest drives (a postponement is caught only when a
  predicate or a negation trips N-V01 / N-V02, or one of the two dates is of unknown nature).
- Two relative terms of different length in one text: both are computed and the earliest open one drives
  (v2.0 design, as in the *avviso di addebito* of the corpus: 40 and 60 days). v2.1 reads more wordings of
  such terms, so it reaches this rule more often.
- N-006 (*del*, *in data*) classes a future date as historical: *"la rata del 30/11/2026"* alone is not a term.
- *"L'udienza che si terrà il 12/11/2026 potrebbe subire rinvii"*, *"... salvo proroga"*: the date is committed.
- A term the text states in a wording that neither detector of `pipeline/termclauses.py` notices is
  replaced by the statutory default of the act (`rules/terms.json`) [TO CONFIRM with counsel].

### Changed
- `tests/test_safety_nets.py`: four v2.0 regression inputs are now *read* by v2.1 (that is the point of the
  release). The net tests keep their meaning with inputs v2.1 still cannot read; the old inputs moved to
  positive tests that pin the value v2.1 commits. No safety net was removed from the code.
- Determinism hashes of `master_index.xlsx` / `report.docx` changed (the dev index now carries one more
  committed deadline); the new values are in the README.
- `tests/test_rules.py` also runs the inline tests of the `vetoes` of `rules/deadline_nature.json`.
- `eval/results.json`: the `note` field is now a full sentence (it was a truncated docstring line).
- `pipeline.__version__` 2.1.0. `rules/terms.json`, `rules/holidays.json`, `corpus/generate.py` and
  `corpus/perturb.py` are untouched.

### What the numbers do and do not show
- Measured on the three perturbed corpora allowed for development (v2.0 abstentions on dated deadlines, by
  the reason v2.0 gave): unparsed term phrase 33 / 39 / 41, date format 28 / 24 / 37, future date without
  cue 19 / 14 / 16, unknown act type 16 / 14 / 21 (seeds 20261002 / 20261003 / 20261004). Each group is read
  by one mechanism above; together they are the whole gain.
- **All of that gain is on phrasings of the generator's own perturbation pool.** The perturbed corpora
  contain nothing else, so they cannot tell a structural reader from a table of eight phrasings; a new
  seed of the same generator cannot either. What is general is argued by construction and pinned by unit
  tests on wordings outside the pool (`tests/test_termclauses.py`, `tests/test_v21_mechanisms.py`) - written
  by the author of the rules.
- Still lists, not grammar: lead-ins, qualifiers and anchors of the term reader; the neutral words of a
  title (*LETTERA* is there because the corpus uses it); the qualifier allow-list of A-003; the noun and
  verb classes of N-008; the place pattern of N-009; the predicates of the vetoes and of `after_not`.
- The safety pass is evidence of what I thought of, not of what I did not: ninety texts written by the
  author of the rules. It found wrong commitments (postponements, recitals, paid amounts) in a build that scored 0 wrong on
  all five corpora.
- The two term readers are independent in how they find and compute the number, not in vocabulary: both
  read units and anchors from the same rule file.
- Record-level RECUPERARE stays 2-3.5 points above expected: sender-class abstentions by design, unchanged.

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
