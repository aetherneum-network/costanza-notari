"""The ten scenario checks of Appendix A (A.3) as unit tests."""
import unittest

from tests._util import ensure_corpus
from scenarios.run_all import IDS, load_check


class Scenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpus()


def _make(sid):
    def test(self):
        ok, line, _ = load_check(sid)()
        self.assertTrue(ok, line)
    test.__doc__ = f"{sid} passes its one-line check"
    return test


for _sid in IDS:
    setattr(Scenarios, f"test_{_sid}", _make(_sid))


if __name__ == "__main__":
    unittest.main()
