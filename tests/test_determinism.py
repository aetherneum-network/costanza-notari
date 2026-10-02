"""Rebuild, never hand-edit: the same ledger + the same as_of must give byte-identical artefacts."""
import hashlib
import subprocess
import sys
import unittest

from tests._util import ROOT, main_run, run_pipeline, tmpdir


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Determinism(unittest.TestCase):
    def test_two_independent_runs_give_identical_xlsx_and_docx(self):
        a = main_run()
        code, b = run_pipeline("determinism-second")  # different directories, fresh ledger and store
        self.assertEqual(code, 0)
        for name in ("master_index.xlsx", "report.docx"):
            ha, hb = sha(a / "work" / "build" / name), sha(b / "work" / "build" / name)
            self.assertEqual(ha, hb, name)
            self.assertEqual(sha(b / "store" / "current" / name), hb, f"published {name}")
        print(f"\n  master_index.xlsx sha256 {sha(b / 'work' / 'build' / 'master_index.xlsx')}"
              f"\n  report.docx       sha256 {sha(b / 'work' / 'build' / 'report.docx')}")

    def test_rebuilding_from_the_same_ledger_is_identical(self):
        a = main_run()
        code, b = run_pipeline("determinism-rebuild")
        self.assertEqual(code, 0)
        before = sha(b / "work" / "build" / "master_index.xlsx")
        # second run on the SAME ledger and store: nothing appended, artefacts identical, new store version
        code2, _ = run_pipeline("determinism-rebuild", fresh=False)
        self.assertEqual(code2, 0)
        self.assertEqual(sha(b / "work" / "build" / "master_index.xlsx"), before)
        self.assertEqual(sha(a / "work" / "build" / "master_index.xlsx"), before)

    def test_corpus_regenerates_bit_for_bit(self):
        r = subprocess.run([sys.executable, str(ROOT / "corpus" / "generate.py"), "--check"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("mismatches vs MANIFEST.sha256: 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
