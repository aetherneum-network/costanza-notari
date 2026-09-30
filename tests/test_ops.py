import datetime as dt
import io
import json
import shutil
import unittest
from contextlib import redirect_stdout

from tests._util import CORPUS, ensure_corpus, tmpdir
from pipeline import heartbeat as hb, run as runner, status as st
from pipeline.lib import tzrome
from pipeline.s7_ledger import Ledger

UTC = dt.timezone.utc


class RunnerTests(unittest.TestCase):
    def test_guard_detects_upstream_modification(self):
        d = tmpdir("ops-guard")
        (d / "a.json").write_text("{}", encoding="utf-8")
        g = runner.Guard()
        g.freeze(d)
        (d / "new.json").write_text("{}", encoding="utf-8")   # adding files is allowed
        g.verify("s-add")
        (d / "a.json").write_text('{"edited": true}', encoding="utf-8")
        with self.assertRaises(runner.UpstreamModified):
            g.verify("s-edit")

    def test_reconciliation_failure_is_loud(self):
        ensure_corpus()
        d = tmpdir("ops-loud")
        inp = d / "input"
        envs = sorted((CORPUS / "envelopes" / "2026-06").glob("*.eml"))[:3]
        (inp / "envelopes").mkdir(parents=True)
        for e in envs:
            shutil.copyfile(e, inp / "envelopes" / e.name)
        man = {"expected_envelopes": 4, "files": [{"path": f"envelopes/{e.name}"} for e in envs] +
               [{"path": "envelopes/missing.eml"}]}
        (inp / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = runner.main(["--input", str(inp), "--work", str(d / "w"), "--ledger", str(d / "l"),
                                "--store", str(d / "s"), "--as-of", "2026-10-21T09:40:00+02:00"])
        self.assertEqual(code, 3)
        self.assertIn("RUN FAILED", buf.getvalue())
        self.assertNotIn("RUN OK", buf.getvalue())
        md = (d / "w" / "run_report.md").read_text(encoding="utf-8")
        self.assertIn("[RED BANNER] RUN FAILED", md)
        self.assertFalse((d / "l" / "ledger.jsonl").exists())  # nothing classified, nothing written


class StatusTests(unittest.TestCase):
    """L3: the answer is rebuilt from the ledger on every call."""

    def test_second_query_sees_the_change(self):
        d = tmpdir("ops-status")
        led = Ledger(d)
        for i in range(3):
            st.open_task(led, f"T-{i}", what="reply", ref=f"ARC-000{i}", at="2026-10-21T08:30:00+02:00", by="intake")
        t1 = tzrome.parse_iso("2026-10-21T09:02:00+02:00")
        a1 = st.status(d, lambda: t1)
        other = Ledger(d)  # another hand closes the tasks
        for i in range(3):
            st.close_task(other, f"T-{i}", at="2026-10-21T09:15:00+02:00", by="ufficio-legale")
        t2 = tzrome.parse_iso("2026-10-21T09:40:00+02:00")
        a2 = st.status(d, lambda: t2)
        self.assertEqual((a1["pending_count"], a2["pending_count"]), (3, 0))
        self.assertGreater(a2["as_of"], a1["as_of"])
        self.assertNotEqual(a1["ledger_sha256"], a2["ledger_sha256"])


class HeartbeatTests(unittest.TestCase):
    def test_utc_anchoring_across_dst(self):
        self.assertTrue(hb.should_run(dt.date(2026, 10, 20), "03:05"))    # CEST: 03:05 = 01:05Z
        self.assertFalse(hb.should_run(dt.date(2026, 10, 20), "02:05"))
        self.assertTrue(hb.should_run(dt.date(2026, 10, 26), "02:05"))    # CET: 02:05 = 01:05Z
        self.assertFalse(hb.should_run(dt.date(2026, 10, 26), "03:05"))
        # the night summer time ends: neither trigger lands in 01:xx UTC -> caught up the next night
        self.assertFalse(any(hb.should_run(dt.date(2026, 10, 25), t) for t in hb.LOCAL_TRIGGERS))

    def test_light_run_never_writes_judgement(self):
        d = tmpdir("ops-light")
        h = hb.Heartbeat(d)
        with self.assertRaises(hb.JudgementOverwriteError):
            h.write_judgement(dt.date(2026, 10, 20), ["x"], mode="light", catch_up=False, as_of="t")
        h.state["last_full_window"] = "2026-10-20"
        rep = h.run(dt.datetime(2026, 10, 21, 8, 0, tzinfo=UTC), mode="light",
                    do_window=lambda w: self.fail("no window should run"), do_refresh=lambda: {"refreshed": True})
        self.assertEqual((rep["windows"], rep["catch_up"]), ([], False))
        self.assertFalse((d / "judgement").exists())

    def test_catch_up_after_downtime(self):
        d = tmpdir("ops-catchup")
        h = hb.Heartbeat(d)
        h.state["last_full_window"] = "2026-10-18"
        rep = h.run(dt.datetime(2026, 10, 21, 1, 5, tzinfo=UTC), mode="full", do_window=lambda w: [f"read {w}"],
                    do_refresh=lambda: {})
        self.assertEqual([w["window"] for w in rep["windows"]], ["2026-10-19", "2026-10-20"])
        self.assertTrue(rep["catch_up"])
        self.assertIn("CATCH-UP", rep["message"])
        self.assertEqual(json.loads((d / "judgement" / "2026-10-19.json").read_text(encoding="utf-8"))["catch_up"], True)
        self.assertEqual(json.loads((d / "judgement" / "2026-10-20.json").read_text(encoding="utf-8"))["catch_up"], False)


if __name__ == "__main__":
    unittest.main()
