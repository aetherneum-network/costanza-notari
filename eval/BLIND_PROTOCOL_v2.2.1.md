# Blind run protocol - v2.2.1

Synthetic project: every entity is fictitious. This file says how to measure `v2.2.1-freeze` on a corpus
nobody has looked at, without changing a line of code. It replaces `BLIND_PROTOCOL_v2.2.md` for any new
run; that file is kept as it was, with a pointer to this one. Sections 1, 2, 3, 5 and 7 of the v2.2 file
apply unchanged, with the three substitutions of section 1 below.

**Why a new protocol.** `v2.2-freeze` carries a never-event inherited from v2.0: a third party's own PEC
(a garnishee bank, `BANK_THIRD_PARTY`, `pignoramento_presso_terzi`) committed as the counterparty channel.
It was found by the evaluator on seeds 20261006 and 20261007 (3 records) and fixed in v2.2.1 (CHANGELOG
2.2.1). No blind seed should be spent on `v2.2-freeze`.

`<SEED>` is an integer that has never been used. **Burned, do not use:** 20260930 (dev), 20261001
(holdout), 20261002, 20261003 (diagnosis), 20261004 (blind for v2.0, then used to develop v2.1 and v2.2),
20261005, 20261006 (blind runs of v2.1), 20261007, 20261008 (out-of-pool runs of v2.1). **Reserved:**
20261009 and 20261010 were reserved by the coordinator; the author of v2.2.1 never generated, ran or opened
them. Whether they have been spent since is [TO CONFIRM with the evaluator]: do not use them either.

## 0. Check that the code is the frozen code

This file sits in the commit after the tag, so it is read from the branch; the run is made at the tag.

```bash
git checkout v2.2.1-freeze     # or a worktree at the tag
git describe --tags            # must print: v2.2.1-freeze
git status --porcelain         # must print nothing
```

Running from the branch head instead is equivalent only if
`git diff v2.2.1-freeze HEAD -- pipeline rules corpus eval/score.py requirements.txt` prints nothing; the
entry will then carry `code: v2.2.1-freeze-<n>-g<sha>`.

## 1. The run

As sections 1-3 of `BLIND_PROTOCOL_v2.2.md`, with:

* history key `stress_blind_v2_2_1_seed_<SEED>` (generator's own rewrites) or
  `out_of_pool_v2_2_1_seed_<SEED>` (wording from outside the repository);
* `--when "single blind run of v2.2.1-freeze"` (or `"out-of-pool phrasing, v2.2.1-freeze"`);
* `code` expected in the entry: `v2.2.1-freeze`.

```bash
python eval/score.py --seed <SEED> --perturb --history-key stress_blind_v2_2_1_seed_<SEED> --when "single blind run of v2.2.1-freeze"
```

## 2. What to read, and in which order

1. The JSON printed by the run. Hard constraint: `deadline_wrong_committed`, `doc_type_wrong_committed`,
   `amount_wrong_committed`, `party_wrong_committed`, `author_wrong_committed`,
   `transmitter_wrong_committed`, `channel_wrong_committed`, `sender_class_wrong_committed`,
   `area_wrong_committed` must all be `0`. The v2.2 note that a non-zero `channel_wrong_committed` would be
   inherited no longer applies: with v2.2.1 **any** wrong committed channel is a failure of this build.
2. As section 4.2 of the v2.2 file (document type, amounts, deadlines, RECUPERARE rates), then
   `recuperare_flagged_vs_expected` for `counterparty_channel`.
3. Only after the entry is in `eval/history.json`: `result.json`, gold and run state, as in section 4.3 of
   the v2.2 file. The channel trace (`rule_trace.counterparty_channel`) now names the sender-side row:
   `CS-001` = the sender is the counterparty, its addresses were scored; `CS-002` / `CS-003` = the sender is
   a third party (or unclassified), its addresses were removed before scoring; `fail closed` = the table
   was missing or broken.

## 3. What this number can and cannot show about the fix

The triggering case needs a token of the counterparty's name inside a third-party sender's domain. With the
repository's generator it occurs about 0.4 times per corpus (8 garnishee letters, probability 1/20 each):
about two corpora in three do not contain it at all (19/20 to the 8th = 0.66). A blind run of a new seed
of the same generator will therefore, most of the time, **not exercise the fix**: a `channel_wrong_committed`
of 0 there shows no regression, not the fix. Before any outside evidence, the evidence for the fix is
`tests/test_v221_channel.py`, which is not a measurement.

**Direct check, not blind (suggested to the evaluator).** The corpora in which the defect was found - seeds
20261006 and 20261007, already burned - can be re-scored with `v2.2.1-freeze` by whoever holds them, under a
new key (for example `fix_check_v2_2_1_seed_20261006`). Expected, not measured: `channel_wrong_committed` 0
where v2.1 recorded 2 and 1, those 3 records now RECUPERARE on `counterparty_channel`. Any other change of
an aggregate is a finding to report [TO CONFIRM: the author of v2.2.1 has not seen those corpora and cannot
predict it; in principle a record where the sender's address used to make two candidates ambiguous can now
commit the other one].

## 4. Rules of the run

As section 5 of the v2.2 file: one seed, one run; a bad number is recorded as it is; nothing under
`build/eval/seed-<SEED>-perturbed/` is opened before step 2.3; after the run `git status --porcelain` shows
`eval/history.json` and nothing else; commit it on top of the branch, the tags do not move
(`v2.1-freeze`, `v2.2-freeze`, `v2.2.1-freeze`).
