# Blind run protocol - v2.2

Synthetic project: every entity is fictitious. This file says how to measure `v2.2-freeze` on a corpus
nobody has looked at, without changing a line of code. It replaces `BLIND_PROTOCOL_v2.1.md` for v2.2; the
v2.1 file is kept as it was.

`<SEED>` is an integer that has never been used. **Burned, do not use:** 20260930 (dev), 20261001
(holdout), 20261002, 20261003 (diagnosis), 20261004 (blind for v2.0, then used to develop v2.1 and v2.2),
20261005, 20261006 (blind runs of v2.1), 20261007, 20261008 (out-of-pool runs of v2.1). The author of
v2.2 never generated, ran or opened 20261005-20261008; they are burned because their aggregates were
read when the merge was decided.

All commands run from the repository root with the project interpreter (Python 3.12, the three pinned
packages of `requirements.txt`, no network, no model or API call).

## 0. Check that the code is the frozen code

```bash
git describe --tags            # must print: v2.2-freeze
git status --porcelain         # must print nothing
```

## 1. The run, in one command: (a) generate, (b) run, (c) score, (d) record

```bash
python eval/score.py --seed <SEED> --perturb --history-key stress_blind_v2_2_seed_<SEED> --when "single blind run of v2.2-freeze"
```

* **(a)** generates the perturbed corpus into a fresh directory, `build/eval/seed-<SEED>-perturbed/`
  (`corpus/`, `gold.jsonl`). If the directory already exists the command stops before generating anything.
* **(b)** runs the nine stages on it (`build/eval/seed-<SEED>-perturbed/run/`), `as_of` 2026-10-21T09:40:00+02:00.
* **(c)** scores against gold and prints **aggregate numbers only** (one JSON object: counts and rates,
  no record id, no text). The full result, which does contain a few record-level error examples, is written
  to `build/eval/seed-<SEED>-perturbed/result.json` and is not printed.
* **(d)** appends the printed aggregates to `eval/history.json` under the key given with `--history-key`,
  together with `code` (`git describe`) and `when`. An existing key is refused *before* the run starts;
  existing entries are re-written byte for byte.

No code change is needed for a new seed: the suite name and its directory derive from `--seed` and
`--perturb`; nothing is added to `SUITES` in `eval/score.py`.

## 2. The same run, step by step

```bash
# (a) generate the perturbed corpus into a fresh directory
python corpus/generate.py --seed <SEED> --out build/eval/seed-<SEED>-perturbed/corpus --gold build/eval/seed-<SEED>-perturbed/gold.jsonl --perturb

# (b) run the pipeline (exit code 0 = OK, 2 = BLOCKED, 3 = FAILED)
python -m pipeline.run --input build/eval/seed-<SEED>-perturbed/corpus --work build/eval/seed-<SEED>-perturbed/manual/work --ledger build/eval/seed-<SEED>-perturbed/manual/ledger --store build/eval/seed-<SEED>-perturbed/manual/store --as-of 2026-10-21T09:40:00+02:00 --trust build/eval/seed-<SEED>-perturbed/corpus/testca/trust

# (c) score: aggregate numbers only on stdout
python eval/score.py --seed <SEED> --perturb --reuse-corpus

# (d) record the result under a new key
python eval/score.py --seed <SEED> --perturb --reuse-corpus --history-key stress_blind_v2_2_seed_<SEED> --when "single blind run of v2.2-freeze"
```

The scorer never scores a run it did not make: (c) and (d) run the pipeline again on the corpus of (a),
in `build/eval/seed-<SEED>-perturbed/run/`. The pipeline is deterministic (`tests/test_determinism.py`), so
(b), (c) and (d) produce the same records; (b) is there for whoever wants to see the runner's own exit code
and `run_report.json`.

## 3. A corpus with wording from outside this repository

This is the run that can say something about the port (section 6). The evaluator writes the rewrites,
keeps them outside the repository, and generates the corpus by their own means into the directory the
scorer expects:

```
build/eval/seed-<SEED>-perturbed/corpus/      # envelopes, manifest.json, testca/trust
build/eval/seed-<SEED>-perturbed/gold.jsonl
```

Then, with no code change:

```bash
python eval/score.py --seed <SEED> --perturb --reuse-corpus --history-key out_of_pool_v2_2_seed_<SEED> --when "out-of-pool phrasing, v2.2-freeze"
```

`--reuse-corpus` scores the corpus that is in the directory and does not call the generator when
`corpus/manifest.json` exists. If the rewrites were put in place by editing `corpus/perturb.py`, the entry
will carry `code: v2.2-freeze-dirty`: say in `--when` which file differed, and restore it afterwards.

## 4. What to read, and in which order

1. The JSON printed by the run. Hard constraint of v2.2, as of v2.1: `deadline_wrong_committed`,
   `doc_type_wrong_committed`, `amount_wrong_committed`, `party_wrong_committed`, `author_wrong_committed`,
   `transmitter_wrong_committed`, `channel_wrong_committed`, `sender_class_wrong_committed`,
   `area_wrong_committed` must all be `0`.
   **Known before the run:** v2.1 recorded `channel_wrong_committed` 2 on seed 20261006 and 1 on seed
   20261007 (`eval/history.json`). v2.2 does not touch the channel reading, and the cause has **not** been
   diagnosed: it needs those corpora, which the author of v2.2 may not open. A non-zero value of that
   counter is therefore possible and would be inherited, not produced by the merge; it still counts as a
   failure of the constraint.
2. What the merge was made for: `doc_type_accuracy` and `doc_type_abstained`; `amount_abstained`;
   `deadline_exact` and `deadline_abstained` of `deadline_n`. Then `recuperare_rate_predicted` against
   `recuperare_rate_expected`, and `recuperare_flagged_vs_expected` per field (flagged/expected).
3. Only after the entry is in `eval/history.json`: `build/eval/seed-<SEED>-perturbed/result.json`
   (`error_examples`), the gold file and the run state, if something has to be understood. In the run state
   (`run/work/state/06_consolidation.json`, `rule_trace`) the merge leaves its rule ids: `TM-004` = the
   ported title rule committed alone; `TM-001` / `TM-002` = the two title readers disagreed; `A-004` = the
   ported amount grammar committed alone; `A-X01` = the two amount readers disagreed.

## 5. Rules of the run

* One seed, one run. If the number is bad it is recorded as it is; a fix is a new version and needs a new seed.
* Nothing under `build/eval/seed-<SEED>-perturbed/` is opened before step 4.3.
* If the run is BLOCKED or FAILED, that is the result: record it by hand in `eval/history.json` under the
  same key, with the exit code and the message.
* After the run, `git status --porcelain` shows `eval/history.json` and nothing else. Commit it on top of
  the tag; the tag does not move.

## 6. What this number can and cannot show

A new seed of the repository's own generator (sections 1-2) uses the same eleven rewrites of
`corpus/perturb.py` as the corpora v2.1 and v2.2 were developed on. Both builds that were merged read
those rewrites already, and on the development corpora the ported readers never committed alone and never
disagreed with the v2.1 readers (`eval/history.json`, `v2_2_before_blind`, `after_v2_2_readers`). Such a
run can therefore show that v2.2 did not regress and did not over-fit particular corpora; it **cannot**
show that the port reads anything v2.1 did not.

Only wording from outside the repository (section 3) can show that. Before that run exists, the evidence
for the port is `tests/test_v22_merge.py` - wording written by the author of the merge, positive and
negative - which shows what the merged readers read and what they refuse; it is not a measurement.

One thing the merge knowingly does **not** reproduce from the other build: its commitment of the document
type on the PEC subject alone when the title is not understood (CHANGELOG 2.2.0, *Not ported*). If the
document-type abstentions of v2.2 on outside wording stay closer to v2.1's than to the other build's, this
is the first place to look.

## 7. Check of this protocol on a burned seed

The generic path was exercised once more on seed 20261004 (already burned), at the code of the freeze,
recorded in `eval/history.json` under `generic_seed_path_check_v2_2_seed_20261004`: the aggregates equal
the `stress-blind` suite of `eval/results.json`, which is the same seed through the named-suite path.
