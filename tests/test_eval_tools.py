"""eval/score.py: the generic --seed path, the aggregate view and the history file (v2.1).

No corpus is generated here: the generic path itself is exercised by hand on the already burned seed
20261004 (eval/BLIND_PROTOCOL_v2.1.md); these tests pin the parts that protect a blind run - only
aggregate numbers are printed, a used directory is refused, history entries are never rewritten."""
from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stderr
from unittest import mock

from tests._util import ROOT, tmpdir

_spec = importlib.util.spec_from_file_location("eval_score", ROOT / "eval" / "score.py")
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)

RESULTS = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))["results"]


class Aggregates(unittest.TestCase):
    def test_no_record_level_data(self):
        agg = score.aggregates(RESULTS["stress-blind"])
        text = json.dumps(agg)
        for leak in ("ARC-", "error_examples", "hard_cases", "record", ".eml", "per_class"):
            self.assertNotIn(leak, text)
        for v in agg.values():                                   # numbers, short strings, one flat dict of 'n/m'
            self.assertIsInstance(v, (int, float, str, bool, dict, type(None)))
            if isinstance(v, dict):
                self.assertTrue(all(isinstance(x, str) and "/" in x for x in v.values()))

    def test_the_numbers_the_hard_constraint_is_about_are_there(self):
        agg = score.aggregates(RESULTS["stress-blind"])
        for k in ("deadline_wrong_committed", "deadline_abstained", "deadline_n", "deadline_exact",
                  "amount_wrong_committed", "party_wrong_committed", "author_wrong_committed",
                  "doc_type_wrong_committed", "sender_class_wrong_committed", "recuperare_rate_predicted",
                  "recuperare_rate_expected", "editions_linked", "seed", "perturbed"):
            self.assertIn(k, agg)
        self.assertEqual(agg["seed"], 20261004)
        self.assertEqual(agg["deadline_wrong_committed"], RESULTS["stress-blind"]["deadline"]["wrong_date_committed"])


class History(unittest.TestCase):
    def setUp(self):
        self.path = tmpdir("eval-history") / "history.json"
        self.before = (ROOT / "eval" / "history.json").read_bytes()
        self.path.write_bytes(self.before)

    def test_append_keeps_every_existing_byte(self):
        score.append_history("new_key", {"seed": 1, "deadline_wrong_committed": 0}, path=self.path)
        after = self.path.read_bytes()
        self.assertTrue(after.startswith(self.before[:-3]))       # everything but the closing '\n}\n'
        data = json.loads(after)
        self.assertEqual(list(data)[-1], "new_key")
        self.assertEqual(data["new_key"], {"seed": 1, "deadline_wrong_committed": 0})
        self.assertNotIn(b"\r", after)

    def test_existing_key_is_never_overwritten(self):
        first = next(k for k in json.loads(self.before) if k != "note")
        with self.assertRaises(SystemExit):
            score.append_history(first, {"seed": 1}, path=self.path)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_hand_edited_file_is_not_rewritten(self):
        self.path.write_bytes(self.before.replace(b"  ", b"    ", 1))
        edited = self.path.read_bytes()
        with self.assertRaises(SystemExit):
            score.append_history("new_key", {"seed": 1}, path=self.path)
        self.assertEqual(self.path.read_bytes(), edited)


class GenericSeedPath(unittest.TestCase):
    def test_used_directory_is_refused(self):
        root = tmpdir("eval-fresh")
        (root / "build" / "eval" / "seed-1-perturbed").mkdir(parents=True)
        with mock.patch.object(score, "ROOT", root), mock.patch.dict(score.SUITES, {"seed-1-perturbed": (1, True)}), \
                mock.patch.object(score, "FRESH", {"seed-1-perturbed"}), \
                mock.patch.object(score.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as cm:
                score.build_corpus("seed-1-perturbed")
            self.assertIn("fresh directory", str(cm.exception))
            run.assert_not_called()                                # nothing was generated

    def test_existing_history_key_fails_before_anything_runs(self):
        first = next(k for k in json.loads((ROOT / "eval" / "history.json").read_text(encoding="utf-8")) if k != "note")
        with mock.patch.object(score, "score") as sc:
            with self.assertRaises(SystemExit):
                score.run_seed(1, True, False, first, None, None)
            sc.assert_not_called()

    def test_a_new_seed_needs_no_code_change(self):
        """The suite name and its directory derive from the parameters; nothing is looked up in SUITES."""
        seen = {}

        def fake_score(suite):
            seen["suite"], seen["spec"] = suite, score.SUITES[suite]
            return RESULTS["stress-blind"]

        root = tmpdir("eval-generic")
        with mock.patch.object(score, "ROOT", root), mock.patch.dict(score.SUITES), \
                mock.patch.object(score, "FRESH", set()), mock.patch.object(score, "score", fake_score), \
                mock.patch("builtins.print") as out:
            self.assertEqual(score.run_seed(123, True, False, None, None, None), 0)
        self.assertEqual(seen, {"suite": "seed-123-perturbed", "spec": (123, True)})
        self.assertTrue((root / "build" / "eval" / "seed-123-perturbed" / "result.json").exists())
        printed = "".join(str(c.args[0]) for c in out.call_args_list)
        self.assertNotIn("error_examples", printed)
        self.assertNotIn("ARC-", printed)
        self.assertIn('"deadline_wrong_committed"', printed)

    def test_seed_options_need_a_seed(self):
        for argv in (["--perturb"], ["--history-key", "k"], ["--reuse-corpus"], ["--seed", "5", "--suite", "dev"]):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                score.main(argv)


if __name__ == "__main__":
    unittest.main()
