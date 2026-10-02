# Changelog

All notable changes to the Costanza Notari v2 proof pack. Synthetic project: every entity is fictitious.

## [2.3.0] - 2026-10-02

A model that proposes, a gate that decides. When the v2.2.1 rules leave a record's driving deadline
RECUPERARE, and only then, an optional classifier - Claude Opus 5.5 (`claude-opus-5-5`), effort `medium` by
default - proposes a date. A deterministic gate decides whether the date may be committed. **The
classifier is OFF by default.** It runs only with `--llm anthropic` and an `ANTHROPIC_API_KEY`. No test and
no CI step calls the API. Ordered by the Rector on 2026-10-02 (approval reference
`chat-2026-10-02-classifier`), after the D14 measure (below) showed 0 wrong committed deadlines at every
effort.

### Added - `pipeline/llm_classifier.py` (rewritten)
- `propose()` sends what the D14 measure sent:
  - the system prompt: the "proposals only" contract, `docs/TERMS.md` verbatim and the term table;
  - the user message: the record's text (subject, body, every attachment text).

  Only two sentences of the system prompt differ from D14: the gate sentence, and the evidence bullet
  ("ONE contiguous passage ... no fragments joined by "...""). The user message is byte-identical to D14
  on all 110 records.
- The answer follows a strict JSON schema: deadline, nature, act type, evidence, computation, confidence.
- How each non-answer is handled:
  - a refusal, `max_tokens`, no text block, invalid JSON or an off-schema answer is an abstention;
  - a transport error (connection, timeout, rate limit, overload, 5xx) leaves RECUPERARE;
  - any other API error (a 4xx) **fails the run** (exit 3).
- No temperature or thinking parameter, no forced tool choice, no fallbacks. Streaming; the system
  prompt is cached.
- The request id of each call is recorded. It is the header of the stream's response (`e004f08`); D14
  could not record it.
- Effort knob: `--llm-effort low|medium|high` or `COSTANZA_LLM_EFFORT`. The flag wins; the default is
  `medium`, and any other value is refused. `--llm-effort` without `--llm` is a usage error.
- **Why medium.** The selection rule of the D14 protocol (rule 6: lowest cost per correct answer among
  the efforts with 0 wrong committed) picks `low`. `medium` is the Dean's decision, on the Rector's
  delegation: on the same 110 records low left 5 more dated deadlines (of 46) to human review, and saved
  0.16 USD per 110 records. The rule's metric gives human review no price.

### Added - the gate: `pipeline/classifier_gate.py` + `rules/classifier_gate.json`
- Version `2026.10.02-1`, G-01..G-15 in order; the first refusal wins.
- A proposed date is committed only if all of the following hold:
  - the call gave a usable answer (G-01) and the model answered with a date (G-02);
  - the date parses (G-03);
  - the nature is one the rules know, actionable or computed (G-04);
  - the evidence is present (G-05) and is ONE verbatim passage of the record. Whitespace is the only
    tolerance; fragments joined by "..." are refused (G-06, G-07);
  - an actionable date is written in the record (G-08), and the rules did not read it as historical or
    conditional (G-09);
  - for a computed term: the notification date is known (G-10); the act type is in `rules/terms.json` and
    equals the rules' own type when they committed one (G-11); the date falls after the notification
    (G-12);
  - the date recounts with the rules' own day-walker from the term stated in the evidence, or else from
    the statutory term (G-13). If the evidence states a number of days that differs from the statutory
    term, the date is refused;
  - the driving deadline stays consistent (G-14);
  - the confidence is not low (G-15).
- Each record keeps `classifier.gate` (rule, kind, reason) and the gate's version.

### Changed
- `s5_classify`:
  - calls the classifier only on records whose `recuperare_fields` hold `deadline`;
  - commits a passed date as a deadline entry with source `classifier` and rule id
    `classifier claude-opus-5-5 (medium), gate passed`;
  - recomputes the driving deadline and urgency;
  - keeps the rules' own reason as `rules_reason`.
- The stage report counts calls, commits, model abstentions, gate refusals by rule, and usage.
- `s7_ledger` carries the `classifier` block.
- `s8_build`:
  - the index marks a committed date `(classifier)`;
  - the RECUPERARE sheet appends the gate's reason.
- `pipeline/run.py`:
  - the classifier is built before stage 1, so a missing key fails before any stage;
  - `--llm-effort` is added.
- `eval/score.py`:
  - `--llm` and `--llm-effort` are added; the classifier run goes to the directory `run-llm`;
  - with named suites `--out` is mandatory, because `eval/results.json` keeps the OFF numbers.
- `pipeline.__version__` 2.3.0.
- `packaging/SKILL.md`, model assignment: the stale Haiku 4.5 worker line is replaced by the classifier.

### Tests (308, v2.2.1 had 273)
- `tests/test_v23_classifier.py` adds 34 tests. They run offline, with sockets blocked and a fake client.
  They cover:
  - OFF by default: the parser, the factory, and a run with a key and an effort in the environment; the
    xlsx/docx stay byte-identical;
  - refusal without a key (exit 3, no stage run);
  - the effort knob;
  - the prompt content: model, streaming, cache, no forbidden parameter, the strict schema, contract and
    TERMS.md, the record text, the request id;
  - one refusal case per gate rule;
  - the 12 D14 answers whose evidence joined fragments, at all three efforts (36 cases): every one
    abstains (G-06), while one of their fragments alone passes;
  - end to end through the runner, on a simulated rule abstention;
  - loud failures (a 4xx, and a caller's stop).
- `tests/test_rules.py` adds the gate's inline tests to the structure check.
- `tests/fixtures/classifier_d14_joined.json` holds the 12 records (synthetic) and their D14 answers.

### Numbers
With the classifier OFF, nothing moves:
- `eval/results.json` regenerates byte-identical to v2.2.1;
- the determinism hashes are unchanged;
- scenarios 10/10.

The same 110 records were measured three ways. They are the unique records whose deadline v2.2.1 leaves
RECUPERARE, across nine corpora: the five named suites and seeds 20261006, 20261007, 20261009 and
20261010, all perturbed. None of them is blind. Gold: 46 dated deadlines and 64 RECUPERARE.

| measure (2026-10-02) | effort | correct | abstained | wrong committed | dates recovered of 46 | cost USD |
|---|---|---|---|---|---|---|
| D14: classifier alone, no gate, outside the pipeline | low | 102 | 8 | 0 | 38 | 0.73 |
| D14: classifier alone, no gate, outside the pipeline | medium | 107 | 3 | 0 | 43 | 0.89 |
| D14: classifier alone, no gate, outside the pipeline | high | 108 | 2 | 0 | 44 | 1.00 |
| D14 answers replayed offline through the gate | low / medium / high | 90 / 95 / 96 | 20 / 15 / 14 | 0 | 26 / 31 / 32 | - |
| **v2.3, real code path** (`eval/history.json`, `classifier_v2_3_medium_real_path_20261002`) | medium | 107 | 3 | **0** | 43 | 0.89 |

Through the pipeline at medium there were 112 calls (the 110 records plus 2 duplicates), costing 0.8877 USD.
- **Committed:** the gate committed 43 dates, all correct.
- **Refused:** the gate refused one correct date, `seed-20261010-perturbed:ARC-0131` (G-13). It is a
  *diffida* whose quoted term stops at "dal ricevimento della", which the term reader does not parse,
  and the act has no statutory term.
- **Model abstentions:** the model abstained on 66 records, the 64 RECUPERARE golds and 2 dated ones.
- **The 12 joined-evidence records of D14:** 11 now quote one passage and pass; the twelfth is the G-13
  refusal.
- **Across the nine corpora:** 0 wrong committed in each one, and every record not sent to the model is
  identical to the OFF run. Dated abstentions fall from 22 to 1 on seed 20261007 (deadline exact 0.913 ->
  0.996) and from 24 to 2 on seed 20261010 (0.905 -> 0.992). OFF numbers: `eval/history.json`,
  `fix_check_v2_2_1_seed_20261007` and `out_of_pool_v2_2_1_seed_20261010`. The other seven corpora had none.
- **Cost:** before the run, `count_tokens` gave 573,346 input tokens over 112 requests, a projection of
  1.09 USD with cache, against a cap of 5 USD. An earlier attempt was stopped after 7 calls (0.0469 USD)
  because it recorded no request id (fixed in `e004f08`). Total spent: 0.9345 USD.

### Not changed (open)
- `resolve_dispute` is unchanged from v2.2: it still uses the server-side fallback beta, and it is not
  wired into the pipeline.
- G-13 refuses a correct computed date when the quoted term stops before the words the term reader needs
  (`seed-20261010-perturbed:ARC-0131`: "entro quindici giorni dal ricevimento della" is refused, while
  "... dal ricevimento della presente" passes on ARC-0079). The result is an abstention, never a wrong
  value. Widening the term reader changes the gate, and that needs a new measure.
- One pass per measure: the variance is not measured.
- Only the driving deadline is measured. No other field is sent to the model.
- The cost is computed from each response's `usage` at list prices. It is not reconciled with billing.

## [2.2.1] - 2026-09-30

A fix of one never-event, not a new reader. **Inherited from v2.0** (the scorer came with stage 5,
`0015de7`; present in v2.1 arm A, in arm B and in v2.2). **Found by the evaluator on blind seeds 20261006
and 20261007, 3 records** (2 + 1; aggregates in `eval/history.json`, `stress_blind_v2_1_seed_20261006` and
`out_of_pool_B_seed_20261007`, `channel_wrong_committed` 2 and 1). **Never caught by the pack's own
suites or tests.** All three records are the same case: a `pignoramento_presso_terzi` sent by the garnishee
bank (`BANK_THIRD_PARTY`: a third party that holds the debtor's funds, author and transmitter, not the
counterparty), and the bank's own PEC committed as `counterparty_channel` of the attaching creditor.
Expected: RECUPERARE. A wrong committed channel is a never-event.

**Root cause** (v2.2 line numbers). `pipeline/attribution.py`, `collect_candidates` (l. 226-230) always puts
the envelope's own addresses (daticert sender, From, Reply-To) among the channel candidates; `contact_channel`
(l. 178-223) scores them like any other address and, for a sender class outside `party_sends_itself_for`
(l. 187), only subtracts 30 (`same_domain_as_sender`, l. 209-210). The domain keyword is a substring test of
the party's name tokens of four letters or more (l. 201). When a token of the creditor's name sits inside the
bank's domain - in the generator's world *RITA*, from *Ceramiche Pontalba S.a.s. di Rita Morlacchi & C.*,
inside *creditovalfiorita* - the bank's PEC scores 60 + 15 + 30 - 30 = 75, exactly the accept threshold, and
a garnishee letter states no other address. Structurally: a penalty where an exclusion was needed.

**Why the suites were blind to it.** The generator writes 8 garnishee letters per corpus (9 with a
duplicate), each from one of 2 banks for one of 10 creditors: the triggering pair has probability 1/20 per
letter, about 0.4 records per corpus. The four corpora I may open hold 33 garnishee letters and 0 triggering
pairs (`eval/history.json`, `v2_2_1_before_blind`, `case`); on the holdout `channel_wrong_committed` was 0 in
every version. No unit test had a third-party sender whose domain contains a token of the party's name.

### Fixed - ordered table `channel_sender_side` in `rules/attribution.json` (first match wins, exception on top)
Read by `attribution.sender_side_rule` before any scoring; `contact_channel` applies it.
- **CS-001** `CORPORATE_PEC`, `BANK_CORPORATE` -> *admit*: the sender is the counterparty itself; its own
  addresses stay candidates, scored exactly as in v2.2. Same list as `party_is_sender_for` and
  `party_sends_itself_for` (a test keeps the three equal).
- **CS-002** `BANK_THIRD_PARTY`, `LAWYER`, `TRANSMIT`, `COURT`, `TARGET` -> *exclude*: the sender is a third
  party. Its addresses (daticert sender, From, Reply-To) and every address on its organisational domain
  (leading `pec.` label dropped when two labels remain; sub-domains included) are never candidates. A
  channel is committed only from an address stated in the text that carries the party's own name (domain or
  local part) and wins by the margin; otherwise RECUPERARE.
- **CS-003** any other class - an unclassified sender (RECUPERARE) or a class added later -> *exclude*, as
  CS-002: when in doubt, abstain.
- **Fail closed**: a missing, empty or malformed table, a malformed row, an unknown condition or verdict, a
  missing or non-compiling domain normaliser, or no matching row -> RECUPERARE for every class, the admitted
  ones included (tested).
- The -30 `same_domain_as_sender` weight and `party_sends_itself_for` are kept in the file for the record
  (R10) but no longer decide anything: the weight could only fire on addresses the table now removes.
- `rules/attribution.json` version `2026.09.30-1` -> `2026.10.03-1`; `pipeline.__version__` 2.2.1.

### Tests (273, v2.2 had 249)
- `tests/test_v221_channel.py`, 23 tests on wording written for them: third-party sender with no
  counterparty address -> RECUPERARE for every class; the counterparty's address stated in the text -> that
  address; two such addresses within the margin -> RECUPERARE; an address without the party's name is refused
  even with inflated weights; From / Reply-To / sibling mailbox / sub-domain of the sender are the sender;
  ordinary senders unchanged, scores included; twelve broken tables -> RECUPERARE; a never-event test that
  tries five sender addresses x five texts x seven classes to get a third party's address committed; end to
  end through `classify_record` (garnishee without and with the creditor's PEC, a bank writing for itself).
  Ten inline `tests` in the rows. With the v2.2 `contact_channel` swapped in, 13 of the 23 fail, among them
  the never-event and the end-to-end garnishee test.
- `tests/test_s5_classify.py`: the gateway test asserted that the gateway's own address was scored 30 - 30 = 0
  - the mechanism being replaced; it now asserts that CS-002 excludes it. `tests/test_rules.py`: the table
  joins the structure check and the inline-test runner. `tests/_records.py`: `record()` takes `display`,
  `body`, `reply_to` (defaults unchanged).

### Numbers
Every aggregate of the five named suites is identical to v2.2 (`eval/results.json` regenerates byte for
byte). On the four allowed suites, record by record, no committed value of any field changed; only the
channel trace now names the row that removed the sender's addresses (138 / 137 / 138 / 139 records; CS-002
124 / 127 / 124 / 123, CS-003 14 / 10 / 14 / 16). Determinism hashes unchanged (README). Scenarios 10/10.

### Not changed (open)
- The domain keyword stays a substring test: after 2.2.1 it can no longer pick the sender's own address,
  but a short token can still match inside another stated address. Changing it moves other channel
  commits and was not asked for here.
- `rules/attribution.json` is not among the rule versions written into the artefacts (only doc_type, area,
  sender_class, terms, urgency are); the channel's row is in the ledger trace.
- A counterparty that writes for itself but whose sender class the pipeline cannot decide (RECUPERARE) now
  loses its own PEC as a candidate (CS-003): a possible abstention, never a wrong value; no committed value
  changed on the four allowed suites.

## [2.2.0] - 2026-09-30

A merge, not a new reader. Two independent v2.1 builds existed: **arm A** (this line, `v2.1-freeze` +
two commits, `04ae6b9`) and **arm B** (another worktree, commit `ad443ae`). Decision D12 of 2026-09-30:
adopt arm A as the base, port into it arm B's reading of the document type from the title and of the
amount, then freeze. Rule of the merge: **two readers of the same field that disagree -> RECUPERARE; one
reader that commits while the other has no opinion -> committed only if that reader's own safety
conditions hold.** The deadline / term reading of arm A is not touched: `pipeline/termclauses.py`,
`pipeline/deadlines.py`, `rules/term_clauses.json`, `rules/deadline_nature.json`, `rules/terms.json` are
byte-identical to `04ae6b9`.

**Who wrote what.** The ported mechanisms (title rules DT-030..DT-032, the label grammar of the amount,
and their tests) originate in **arm B, built by Claude Fable 5.1**. The merge - the agreement tables, the
nets around the ported rules, the engine conditions, the tests for every disagreement path - is by
**Claude Opus 5.5**, in Costanza's voice. No model or API is called by the code or by the tests.

**What the numbers can and cannot show.** On the five corpora every aggregate of v2.2 is identical to
v2.1 arm A (`eval/history.json`, key `v2_2_before_blind`; `eval/results.json` regenerates byte for byte).
Those corpora hold only the generator's eleven rewrites, which both arms already read: on the four I may
open, the ported readers never committed alone and never disagreed with arm A's readers (both title
readers named the same type on 25 / 28 / 28 records of the three perturbed corpora, 0 on dev). So the
suites show that the merge did not regress and **nothing else**. The evidence for the port is
`tests/test_v22_merge.py`: wording written for the tests, positive and negative. No blind run of v2.2 has
been made at the time of this entry (`eval/BLIND_PROTOCOL_v2.2.md`).

### Ported from arm B
- **Title-exclusive reader** (`rules/doc_type.json`, DT-030 *atto_precetto*, DT-031
  *diffida_messa_in_mora*, DT-032 *sollecito_pagamento*; `then.basis = "title_exclusive"`). An upper-case
  title line names the act inside a wrapped title (*ATTO DI PRECETTO E INTIMAZIONE*, *LETTERA DI DIFFIDA*,
  *LETTERA DI SOLLECITO*) and no other act: arm B's exclusivity lists are kept verbatim. They sit after the
  strict title rules (DT-001..DT-024, unchanged, still first) and before the subject rules.
- **Label grammar of the amount** (`rules/amounts.json`, A-004, `reader: "grammar"`): head noun
  (*importo / somma / totale*) + any number of "owed" qualifiers + optional *di / pari a*; arm B's pattern
  verbatim inside a word boundary. It reads *importo pari a*, a label with no connector
  (*Totale da versare € 310,00*), *somma precettata*, more than three qualifiers.
- **Rule-engine conditions** (`pipeline/rules_engine.py`): `title_matches`, `title_not_matches` (arm B),
  over one shared definition of a title line (upper-case, with a letter, at most 90 characters, in the first
  600) now used by both title readers.
- Arm B's tests for these mechanisms, positive and negative (`TitleExclusiveReader`, `AmountTwoReaders`,
  `EndToEndInvariance` in `tests/test_v22_merge.py`; inline `tests` of the rules).

### Disagreement rules - ordered tables in the rule files, first match wins, abstentions on top
- **Title, `title_merge` in `rules/doc_type.json`** (`typeagree.resolve`). *exclusive* = what DT-030..032
  say; *agreement* = arm A's reader (title family in a neutral frame, confirmed by the subject or by the
  stated term).
  - TM-001 both commit, different types -> RECUPERARE.
  - TM-002 exclusive commits, agreement finds two confirmed families (conflict) -> RECUPERARE.
  - TM-003 both commit the same type -> committed (trace carries both).
  - TM-004 exclusive commits, agreement has no opinion (unconfirmed / not understood / silent) ->
    committed on the rule's own conditions. **This is the port**: v2.1 arm A abstained here.
  - TM-005 only the agreement reader commits -> committed, as in v2.1.
  - TM-006 exclusive silent, agreement abstains -> RECUPERARE, and the subject-only fallback stays vetoed,
    as in v2.1 (arm A's net, kept).
  - TM-007 both silent -> the ordered rules decide, as in v2.0.
  - A pair that no row describes, a missing or broken table -> RECUPERARE (fail closed, tested).
- **Amount, `agreement` in `rules/amounts.json`** (`amounts.read_amount`). *labels* = arm A's A-001..A-003
  with their nets; *grammar* = A-004 (A-001 belongs to both).
  - A-X01 the two read different figures -> RECUPERARE, flagged for every document type. To see a
    disagreement the grammar is read **without** its nets; that reading never commits.
  - A-X02 same figure -> committed under the labels rule id, as in v2.1.
  - A-X03 labels only -> committed, as in v2.1.
  - A-X04 grammar only -> committed only if the nets of A-004 hold: one money figure in the document
    (`unique_amount`), nothing after it that says the figure is not due (`after_not`: arm A's pattern
    plus *bonificato*, *nota di credito*, *a titolo di sconto / abbuono*), the word boundary
    (*sottototale*), and `label_not` - a bare *importo residuo* is not read.
  - A-X05 neither -> no amount, as in v2.0.

### Nets added by the merge around the ported title rules - each one only abstains
- **Head position** (`title_before_words`): on its title line the act name may be preceded only by frame
  words - arm A's neutral frame plus a short list (*STRAGIUDIZIALE, RACCOMANDATA, URGENTE, INVITO,
  RINNOVAZIONE*, ordinals). *RISCONTRO A VOSTRA DIFFIDA*, *MEMORIA SULL'ATTO DI PRECETTO*,
  *CHIARIMENTI SUL SOLLECITO* are not read. Arm B read them.
- **Inverting words** (`{INVERTING}`, any title line): *OPPOSIZIONE, REVOCA, RINUNCIA, SOSPENSIONE,
  RISCONTRO, BOZZA, FAC-SIMILE, NON, NULLO, PAGAMENTO EFFETTUATO, SALDATA...* -> not read.
- **Other acts under the names arm A knows** (`{OTHER_ACT_SYNONYMS}`): *INGIUNZIONE DI PAGAMENTO,
  RATEAZIONE, DILAZIONE* count as a second act name.
- **Closed tail for a reminder** (`title_after_words`): after *SOLLECITO* only payment words may follow
  (*SOLLECITO INVIO DOCUMENTAZIONE* is not a payment reminder).
- **Tail of a precetto / diffida line** (`{ABOUT_TAIL}`, `{NOT_A_DEMAND_TAIL}`, bound to the line of the
  act): *ATTO DI PRECETTO PERVENUTO*, *LETTERA DI DIFFIDA - RICHIESTA DI INCONTRO*, *MESSA IN MORA DEL
  CREDITORE*, *DIFFIDA ACCERTATIVA*, *DIFFIDA DAL PROSEGUIRE* are not read. Apart from these lists the
  tail of a precetto or diffida title is open: a tail outside them that changes the act is not caught.
  Which of these titles are the same act is **[TO CONFIRM with counsel]**.
- Rule files gain `defs` (named pattern fragments, `{NAME}`) and `"@list"` references, so that a net is
  written once and the code only extracts.

### Changed behaviour with respect to v2.1 arm A (each change is commented in the tests it touched)
- A wrapped title of a precetto, a diffida or a reminder is now committed **on the title alone** when arm
  A's reader has no confirmation (TM-004). For a precetto this also computes the statutory term
  (T-001) where v2.1 left type and deadline RECUPERARE. The deadline reader itself is unchanged: a stated
  term it cannot read is still RECUPERARE.
- An amount may now be committed by A-004 alone (A-X04), and two labels that give different figures are
  now RECUPERARE (A-X01) where v2.1 committed the first labels rule.
- Rule versions `2026.10.02-1` (`doc_type.json`, `amounts.json`). The versions and the type trace are
  written into the index, so the determinism hashes changed (README); no value in the dev index changed.

### Not ported, and why
- **Arm B's subject-only fallback when the title is not understood.** Arm A vetoes it (v2.1, TM-006) and an
  abstain-only net of arm A is not removed. If part of arm B's advantage on unseen titles came from this
  fallback and not from its title rules, v2.2 does not reproduce that part. I cannot tell the two apart
  without the evaluator's corpora, which I may not open.
- Title-alone reading for the other families of arm A (cartella, avviso, decreto...): arm B has no title
  rule for them; nothing to port.
- Arm B's grammar as an unconditioned reader: kept only as a detector of disagreement (A-X01).
- Arm B's deadline / term readers and its changes to `eval/score.py`: arm A's are the base.

### Known limits, unchanged
- The strict rules still win first: DT-022 reads any title line that **begins** with *DIFFIDA / MESSA IN
  MORA* (*DIFFIDA - REVOCA*, *MESSA IN MORA DEL CREDITORE*, *DIFFIDA ACCERTATIVA...*), as in v2.0 and v2.1.
  The nets above guard only the new path.
- A-002 / A-003 of arm A are unchanged: *importo di € 800,00 quale nota di credito* is still read by A-002.
- The PEC subject neither confirms nor vetoes a title-exclusive rule; only the agreement reader uses it.

### Verification
- 249 `unittest` tests (v2.1 arm A: 202), 10/10 scenarios, determinism test green.
- `eval/score.py --seed N --perturb` unchanged; checked once more on the burned seed 20261004
  (`eval/history.json`, `generic_seed_path_check_v2_2_seed_20261004`).

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
