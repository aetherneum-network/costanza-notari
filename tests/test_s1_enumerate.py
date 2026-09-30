import json
import os
import unittest

from tests._util import tmpdir
from pipeline import s1_enumerate as s1


def _write(root, rel, data=b"x"):
    p = s1.extended(os.path.join(str(root), rel))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data)


class EnumerateTests(unittest.TestCase):
    def test_long_paths_are_enumerated_and_counts_reconcile(self):
        root = tmpdir("s1-long")
        deep = "/".join(["cartella_molto_lunga_di_archivio_" + str(i) for i in range(8)])
        rels = ["a.eml", f"{deep}/Società Agricola Valle dell’Èrto - atto.eml"]
        for r in rels:
            _write(root, r)
        self.assertGreater(len(os.path.abspath(os.path.join(str(root), rels[1]))), 260)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"expected_envelopes": 2, "files": [{"path": r} for r in rels]}),
                            encoding="utf-8")
        st = s1.run(root, root / "_state.json", manifest=manifest)
        self.assertEqual(st["status"], "OK")
        self.assertEqual(st["reconciliation"]["long_path_safe"], 2)
        self.assertIn("Società Agricola Valle dell’Èrto - atto.eml", st["records"][1]["envelope"])
        if os.name == "nt":  # the failure mode L8 describes; informational, never used downstream
            self.assertLessEqual(st["reconciliation"]["naive_os_walk"], 2)

    def test_missing_file_fails_the_stage_loudly(self):
        root = tmpdir("s1-missing")
        _write(root, "a.eml")
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"expected_envelopes": 2, "files": [{"path": "a.eml"}, {"path": "b.eml"}]}),
                            encoding="utf-8")
        st = s1.run(root, root / "_state.json", manifest=manifest)
        self.assertEqual(st["status"], "FAILED")
        self.assertEqual(st["reconciliation"]["missing_vs_manifest"], ["b.eml"])

    def test_record_ids_follow_sorted_paths(self):
        root = tmpdir("s1-ids")
        for r in ("b/2.eml", "a/1.eml", "notes.txt"):
            _write(root, r)
        st = s1.run(root, root / "_state.json")
        self.assertEqual([(r["record_id"], r["envelope"]) for r in st["records"]],
                         [("ARC-0001", "a/1.eml"), ("ARC-0002", "b/2.eml")])


if __name__ == "__main__":
    unittest.main()
