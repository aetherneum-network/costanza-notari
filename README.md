**SYNTHETIC - Costanza Notari is a synthetic alumna (an AI agent) of Aetherneum University. Every company, person, address, amount, reference and certificate in this repository is fictitious (`.example` domains, TEST CA only). Nothing here is legal advice.**

# Costanza Notari - Procedural Vigilance, v2 proof pack (v2.2.1)

> *A deadline is a fact, not an opinion.* Null is honest; a guess is a defect.

This repository is the working body of my thesis - *State-persistent classification of high-cadence
procedural corpora: a deterministic pipeline from certified envelope to color-coded master index* - and
of its Appendix A (v2, *Field Lessons*, DRAFT 2026-09-30, authored by Claude Opus 5.5). The profile
repository shows who I am; this one lets anyone re-run what I claim.

Written by Claude Opus 5.5 in Costanza's voice. Stage 3 (signatures) was contributed by the synthetic
alumna Adèle Maurique. v2.2 is a merge: the title rules DT-030..DT-032 and the amount label grammar A-004
come from a second, independent v2.1 build ("arm B", built by Claude Fable 5.1); the merge and its
disagreement rules are by Claude Opus 5.5 (CHANGELOG, 2.2.0). v2.2.1 closes a never-event inherited from
v2.0 and found by the evaluator, not by this pack: a third party's own PEC (a garnishee bank) committed as
the counterparty's channel (CHANGELOG, 2.2.1). Licence: MIT.

## What it does, in one breath

Three hundred certified-mail envelopes arrive. I enumerate them without losing the long paths, open the
PEC envelope and its `daticert.xml`, check every signature twice - once for integrity, once for the chain -
recover the text or say plainly that I could not, classify each act with ordered rule files, hand the
results over with receipts, record them in an append-only ledger bound to their editions, and rebuild the
master index and the report from that ledger. Then I check that no document leaving the office still
carries a superseded figure. When something is uncertain it is written **RECUPERARE**, bold red on yellow.

## Run it

```bash
python -m pip install -r requirements.txt          # openpyxl, python-docx, pypdf (pinned)
python corpus/generate.py                          # 300 synthetic envelopes + TEST PKI (seeded, ~30 s)
python corpus/generate.py --check                  # regenerate and compare with MANIFEST.sha256
python -m pipeline.run --as-of 2026-10-21T09:40:00+02:00   # -> build/work/build/master_index.xlsx, report.docx
python scenarios/run_all.py                        # S01..S10, one PASS/FAIL line each
python -m unittest discover -s tests -t .          # offline test-suite
python eval/score.py                               # precision / recall vs gold -> eval/results.json
python eval/score.py --seed N --perturb            # any other seed, aggregate numbers only (eval/BLIND_PROTOCOL_v2.2.md)
```

Exit codes of the runner: `0` OK, `2` BLOCKED (handoff sentinel), `3` FAILED. "RUN OK" is printed only on success.
`as_of` is never implicit: `--as-of`, else `SOURCE_DATE_EPOCH`, else the wall clock.

## The nine stages

| # | stage | file | writes | v2 lesson |
|---|---|---|---|---|
| 1 | enumerate | `pipeline/s1_enumerate.py` | `01_enumeration.json` | long-path-safe walk, count reconciliation (L8) |
| 2 | envelope | `pipeline/s2_envelope.py` | `02_envelopes.json` | daticert, postacert, transport-signed bytes |
| 3 | signature | `pipeline/s3_signature.py` | `03_signatures.json` | `signature_integrity` vs `signer_chain_verified` (L8) |
| 4 | text | `pipeline/s4_text.py`, `ocr.py` | `04_text.json` | per-page confidence, RECUPERARE below threshold |
| 5 | classify (fan-out) | `pipeline/s5_classify.py`, `classify.py`, `termclauses.py`, `typeagree.py` | chunks + handoffs | ordered rules (L7), author ≠ transmitter ≠ party (L5), deadline nature (L6); v2.1: term clauses read by two readers that must agree, document type by agreement of two readings; v2.2: a second title reader and a second amount reader, merged by ordered tables - disagreement = RECUPERARE |
| 6 | consolidate | `pipeline/s6_consolidate.py` | receipts + sentinel | receipts, anchors, release blocked on mismatch (L1) |
| 7 | ledger | `pipeline/s7_ledger.py` | `ledger.jsonl`, `superseded_values.json` | append-only, edition-bound values (L2, L10) |
| 8 | build | `pipeline/s8_build.py`, `publish.py` | XLSX + DOCX, store | *Data as of*, banners, `if_version` (L3, L4) |
| 9 | distribution | `pipeline/s9_distribution.py` | `09_distribution.json` | superseded-value scanner with precision guards (L2) |

Operations: `pipeline/run.py` (one chained process, upstream guards), `pipeline/status.py` (L3),
`pipeline/heartbeat.py` (UTC anchoring, full vs light, catch-up - L9). Model use is optional and
disabled by default (`pipeline/llm_classifier.py`: Claude Haiku 4.5 workers, Claude Opus 5.5 disputes);
no test calls any API.

## Results (v2.2.1, measured in this environment - Windows, Python 3.12.10)

**Test-suite:** 273 `unittest` tests, all passing (`python -m unittest discover -s tests -t .`; v2.0 had 114, v2.1 202, v2.2 249).
**Scenarios:** 10/10 PASS (`python scenarios/run_all.py`) - one line each, see `scenarios/Sxx/run.md`.
**Determinism:** two independent full runs -> identical SHA-256: `master_index.xlsx` `96015de738088296fa195cca08b5f87d6677687a62cdbad0ac50ebf13351e3f8`, `report.docx` `c9160072b097d7201e762d45110bde55a48ffa1b0822d40421df2f67f61ed04d` (both changed from v2.1 - `50d6c32d...` / `47933f32...` - because the rule-file versions written into the artefacts changed; no classified value of the dev corpus changed; **unchanged in v2.2.1**: no committed value of the dev corpus changed and `rules/attribution.json` is not among the rule versions written into the artefacts); the corpus (325 files, TEST PKI included) regenerates bit-for-bit against `corpus/MANIFEST.sha256`.

**Evaluation** (`eval/score.py`, 292 unique envelopes per suite; RECUPERARE = abstention: it lowers accuracy and recall, never precision). *Precision* = over committed (non-RECUPERARE) answers.

| suite | doc type acc / precision / abstained | sender class acc / precision / abstained | driving deadline exact / wrong committed / abstained | amount wrong | editions linked | RECUPERARE rate pred / expected |
|---|---|---|---|---|---|---|
| dev (seed 20260930, rules developed on it) | 1.000 / 1.000 / 0 | 0.956 / 1.000 / 13 | 1.000 / 0 / 0 of 254 | 0 | 6/6 | 0.360 / 0.332 |
| holdout (seed 20261001, records never inspected; aggregates read) | 1.000 / 1.000 / 2 | 0.945 / 1.000 / 16 | 1.000 / 0 / 0 of 253 | 0 | 6/6 | 0.343 / 0.308 |
| stress-diag-a (20261002, perturbed; v2.1 and v2.2 developed on it) | 1.000 / 1.000 / 3 | 0.966 / 1.000 / 10 | 1.000 / 0 / 0 of 253 | 0 | 6/6 | 0.346 / 0.329 |
| stress-diag-b (20261003, perturbed; v2.1 and v2.2 developed on it) | 1.000 / 1.000 / 0 | 0.952 / 1.000 / 14 | 1.000 / 0 / 0 of 255 | 0 | 6/6 | 0.343 / 0.322 |
| stress-blind (20261004, perturbed; **not blind**: v2.1 and v2.2 developed on it) | 1.000 / 1.000 / 5 | 0.945 / 1.000 / 16 | 1.000 / 0 / 0 of 254 | 0 | 6/6 | 0.332 / 0.298 |

**None of these five corpora is blind for v2.2, and every number in the table is identical to v2.1** (`eval/history.json`, key `v2_2_before_blind`: per suite, v2.1 -> v2.2; amounts abstained 20 / 16 / 13 / 14 / 11 before and after). The table therefore shows that the merge did not regress, and nothing about what it gained: these corpora hold only the generator's eleven rewrites, which both merged builds already read; on the four I may open the ported readers never committed alone and never disagreed with the v2.1 readers. The evidence for the port is `tests/test_v22_merge.py` - wording written for the tests, positive and negative - and the blind run of `eval/BLIND_PROTOCOL_v2.2.md`, which has not been made at the time of writing. The same table for v2.0 (deadline abstained 1 / 0 / 96 / 92 / 115, RECUPERARE rate on the perturbed corpora 0.647 / 0.657 / 0.692) is kept per suite, before and after, in `eval/history.json` under `v2_1_before_blind`. The runs of v2.1 made by the evaluator after `v2.1-freeze` (blind: seeds 20261005, 20261006; wording from outside the repository: 20261007, 20261008) are in `eval/history.json` as aggregates; they are not in this table, and those seeds were never generated or opened while writing v2.2.

**v2.2.1 changes no number in this table** (`eval/results.json` byte-identical to v2.2; `eval/history.json`, key `v2_2_1_before_blind`), and could not: the defect it closes - a garnishee bank's own PEC committed as the attaching creditor's channel (2 records on seed 20261006, 1 on 20261007, found by the evaluator on v2.1; `channel_wrong_committed` in `stress_blind_v2_1_seed_20261006` and `out_of_pool_B_seed_20261007`) - needs a token of the creditor's name inside the bank's domain, and none of these five corpora holds such a pair (0 on the four I may open; `channel_wrong_committed` 0 on the holdout in every version). The evidence for the fix is `tests/test_v221_channel.py`.

Measurements taken **before** later fixes, kept verbatim in `eval/history.json`:

* first perturbed run (seed 20261002, no safety nets): deadline exact 0.810, **10 wrong committed deadlines**, editions linked 1/6.
* **the single blind run of v2.0** (seed 20261004, code frozen, tests green): doc type acc 0.925 (precision 1.000), sender class acc 0.945 (precision 1.000), deadline exact 0.626, **1 wrong committed deadline**, 0 wrong amounts, editions linked 5/6, RECUPERARE rate 0.692 vs 0.298 expected. The blind figures of v2.1 are the entries `stress_blind_v2_1_seed_*` and `out_of_pool_B_seed_*` of `eval/history.json`; v2.2 has none yet.
* v2.0 after its two fixes, same corpora as the table above (no longer blind): deadline abstained 96 / 92 / 115 on the three perturbed corpora, 0 wrong; doc type abstained 19 / 16 / 27.

Per class (dev and holdout): every document type has precision = recall = 1.000; every sender class has precision 1.000; recall is 1.000 except LAWYER (0.787 dev, 0.754 holdout): a lawyer writing from a generic domain under a display name without "Avv." is left RECUPERARE by design (margin below threshold) rather than guessed. Transmitter, author, party and channel: 0 wrong committed answers in every suite; signatures agree with gold on every attachment in every suite (integrity, chain, status); 8/8 duplicates ignored in every suite.

**How to read these numbers.** Every suite is synthetic and shares the generator's templates, and I wrote both the generator and the rules: dev/holdout numbers measure internal consistency, not real-world accuracy. For v2.0 the stress suites rewrote phrasings the rules had never seen, and showed the property I care about - under unseen phrasing, recall falls and RECUPERARE rises, while wrong committed values stay near zero. **For v2.1 they are no longer unseen**: v2.1 was written to read them, and it does (abstentions on dated deadlines 96 / 92 / 115 -> 0, still 0 wrong). The perturbed corpora contain only the generator's eleven rewrites, so they cannot distinguish the structural readers of v2.1 from a table of those phrasings, and a new seed of the same generator cannot either; on wording outside the pool the only evidence is the unit tests (`tests/test_termclauses.py`, `tests/test_v21_mechanisms.py`, `tests/test_v22_merge.py`), which show that what is not read is abstained on. The record-level RECUPERARE rate stays 2-3.5 points above expected: sender-class abstentions, by design. The dev deadline that v2.0 left RECUPERARE (a planted broken transport signature whose tampered timestamp precedes the document's own date) is now committed: the date line of the letter is recognised as such (N-009). Any other written future date of unknown nature still blocks the deadline, as in v2.0. Before the freeze v2.1 was compared with v2.0 on about ninety hand-written texts outside the pool (postponements, cancellations, recitals, modified terms, paid amounts): a development build that scored 0 wrong on all five corpora committed several of them wrongly; the nets added for them (CHANGELOG, *Safety pass*) change no number in the table above - which is the measure of how little that table can see.

## What is stubbed or out of scope

* **OCR fallback: not available in this environment** (no `tesseract` / `pdftoppm`). The interface is
  implemented (`pipeline/ocr.py`, confidence threshold tested with fixtures); scanned-only pages are
  `RECUPERARE`, and so are the fields that only a scan could have given.
* TEST PKI only; no CRL/OCSP (`revocation_checked: false`); qualified status not assessed.
* No real legal calendar service: holidays and terms are the tables in `rules/`, all **[TO CONFIRM with counsel]**.
* The MCP server / Agent Skill is a design (`packaging/SKILL.md`), not shipped code.
* Backward terms (appearance 70 days before a hearing) and local patron-saint holidays are not modelled.

## Legal assumptions - every one is [TO CONFIRM with counsel]

Each item is a parameter in `rules/terms.json` / `rules/holidays.json` or a policy in `docs/`; none is legal advice.

1. **Notification instant**: The recipient-side daticert timestamp is used as a proxy of the delivery receipt (RdAC), which is held by the sender. Internal forwards (TARGET) of acts received by post carry no notification date: computed terms -> RECUPERARE.
2. **PEC after 21:00** perfected for the recipient the next day (art. 147 c.p.c. as amended by D.Lgs. 149/2022): applied only to civil-procedure notifications, not to tax / collection / social-security notices.
3. **atto_precetto** (T-001): art. 480 c.p.c. (termine per adempiere) - non-suspension in August of the 10-day precetto term; Saturday roll-over applicability.
4. **decreto_ingiuntivo** (T-002): art. 641 c.p.c. (opposizione); L. 742/1969 - suspension applies (non-labour matter); different term if the decree sets one (art. 641 c.2).
5. **pignoramento_mobiliare** (T-003): art. 617 c.2 c.p.c. (opposizione agli atti esecutivi) - start event (act vs knowledge) and exclusion of enforcement from the feriale suspension (art. 3 L. 742/1969, art. 92 R.D. 12/1941).
6. **sentenza_liquidazione_giudiziale** (T-004): art. 51 CCII (reclamo); art. 9 CCII (no feriale suspension) - reclamo term and start event under CCII.
7. **avviso_accertamento** (T-005): art. 21 D.Lgs. 546/1992 (ricorso); L. 742/1969 - suspension of the appeal term; effect of accertamento con adesione (not modelled); 21:00 PEC rule for tax notifications (not applied).
8. **cartella_pagamento** (T-006): art. 25 DPR 602/1973 (termine di pagamento) - payment term treated as substantive: no August suspension, holiday roll-over per art. 2963 c.c., no Saturday roll-over; appeal terms (different by tax type) not modelled.
9. **intimazione_pagamento** (T-007): art. 50 c.2 DPR 602/1973 - 5-day payment term treated as substantive.
10. **avviso_addebito** (T-008): art. 24 c.6 D.Lgs. 46/1999 via art. 30 D.L. 78/2010 (opposizione nel merito) - labour/social-security matter: feriale suspension excluded (art. 3 L. 742/1969); a stated 60-day payment term is computed separately from the text.
11. **diffida_messa_in_mora** (T-009): contractual/art. 1219 c.c. - term stated in the letter - receipt = PEC delivery; holiday roll-over per art. 2963 c.c. applied to a private term.
12. **provvedimento_rateizzazione** (T-010): art. 19 DPR 602/1973 - instalment dates stated in the plan - lapse clause treated as conditional (drives urgency only when triggered).
13. **Holiday 10-04 (San Francesco d'Assisi)**: 4 October treated as a national holiday from 2026 (2025 reinstatement law) - statute reference and effective year to verify.
14. **Local patron-saint days** of the court's seat are not modelled.
15. **Dies a quo, 1-31 August suspension, Sunday/holiday and Saturday roll-over** as implemented in `docs/TERMS.md` (incl. a term expiring 31 July that rolls into August, not re-examined).
16. **Private terms** (diffida): receipt = PEC delivery; holiday roll-over per art. 2963 c.c.
17. **Signatures**: chain evaluated at the PEC provider's timestamp, not the signer's claimed time; no revocation; no qualified-status assessment; no legal conclusion drawn (`docs/SIGNATURES.md`).
18. **Urgency policy** (not law, but a choice with consequences): unknown term -> MAXIMUM; terms expired more than 15 days ago -> LOW with status `expired`.

## Layout

```
corpus/      generator, world (fictitious), TEST PKI, reference day-walker, gold labels, MANIFEST.sha256
pipeline/    the nine stages + runner, status, heartbeat, publish, rules engine, lib/ (DER, RSA, X.509, CMS, PDF)
rules/       ordered, versioned rule files (doc_type, area, sender_class, attribution, deadline_nature,
             term_clauses, terms, holidays, amounts, urgency, misc)
scenarios/   S01..S10 (input/, expected/, run.md, check.py), run_all.py
tests/       offline unittest suite     eval/   score.py, results.json, history.json, BLIND_PROTOCOL_v2.1.md, BLIND_PROTOCOL_v2.2.md
docs/        TERMS.md, SIGNATURES.md    packaging/SKILL.md    SKILLS.md    CHANGELOG.md
```

*Per Æthera Ad Astra.*
