# Blind run protocol - v2.1

Synthetic project: every entity is fictitious. This file says how to measure `v2.1-freeze` on a corpus
nobody has looked at, without changing a line of code.

`<SEED>` is an integer that has never been used. **Burned, do not use:** 20260930 (dev), 20261001
(holdout), 20261002, 20261003 (diagnosis), 20261004 (blind for v2.0, then used to develop v2.1).

All commands run from the repository root with the project interpreter (Python 3.12, the three pinned
packages of `requirements.txt`, no network).

## 0. Check that the code is the frozen code

```bash
git describe --tags            # must print: v2.1-freeze
git status --porcelain         # must print nothing
```

## 1. The run, in one command: (a) generate, (b) run, (c) score, (d) record

```bash
python eval/score.py --seed <SEED> --perturb --history-key stress_blind_v2_1_seed_<SEED> --when "single blind run of v2.1-freeze"
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
python eval/score.py --seed <SEED> --perturb --reuse-corpus --history-key stress_blind_v2_1_seed_<SEED> --when "single blind run of v2.1-freeze"
```

The scorer never scores a run it did not make: (c) and (d) run the pipeline again on the corpus of (a),
in `build/eval/seed-<SEED>-perturbed/run/`. The pipeline is deterministic (`tests/test_determinism.py`), so
(b), (c) and (d) produce the same records; (b) is there for whoever wants to see the runner's own exit code
and `run_report.json`.

## 3. What to read, and in which order

1. The JSON printed by (c)/(d). Hard constraint of v2.1: `deadline_wrong_committed`, `amount_wrong_committed`,
   `party_wrong_committed`, `author_wrong_committed`, `transmitter_wrong_committed`, `channel_wrong_committed`,
   `doc_type_wrong_committed`, `sender_class_wrong_committed` must all be `0`.
2. Abstention: `deadline_abstained` of `deadline_n`; `recuperare_rate_predicted` against
   `recuperare_rate_expected`; `recuperare_flagged_vs_expected` per field (flagged/expected).
3. Only after the entry is in `eval/history.json`: `build/eval/seed-<SEED>-perturbed/result.json`
   (`error_examples`), the gold file and the run state, if something has to be understood.

## 4. Rules of the run

* One seed, one run. If the number is bad it is recorded as it is; a fix is a new version and needs a new seed.
* Nothing under `build/eval/seed-<SEED>-perturbed/` is opened before step 3.3.
* If the run is BLOCKED or FAILED, that is the result: record it by hand in `eval/history.json` under the
  same key, with the exit code and the message.
* After the run, `git status --porcelain` shows `eval/history.json` and nothing else. Commit it on top of
  the tag; the tag does not move.

## 5. What this number can and cannot show

The new corpus comes from the same generator and the same eleven rewrites of `corpus/perturb.py` as the
three perturbed corpora v2.1 was developed on. A new seed changes which envelopes are rewritten, the
dates, the amounts, the parties and the mix of hard cases; it does not contain a phrasing the rules have
not met. The blind number is therefore evidence that v2.1 did not over-fit three particular corpora,
**not** evidence of what happens on wording nobody anticipated. For that, the only evidence in this
repository is the paraphrase batteries in `tests/test_termclauses.py` and `tests/test_v21_mechanisms.py`
(wordings outside the perturbation pool, written by the same author as the rules): on the wordings they
contain, what is not read is abstained on. Wordings on which the pipeline is known to commit a doubtful
value are listed in `CHANGELOG.md` (*Known limits left as they were in v2.0*).

## 6. Check of this protocol on a burned seed

The generic path was exercised once on seed 20261004 (already burned), recorded in `eval/history.json`
under `generic_seed_path_check_seed_20261004`: the aggregates equal the `stress-blind` suite of
`eval/results.json`, which is the same seed through the named-suite path.
