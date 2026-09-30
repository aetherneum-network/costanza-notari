import json
import unittest

from tests._util import ROOT, ensure_corpus, tmpdir
from pipeline import s2_envelope as s2
from pipeline.lib import cms


def _gold():
    return [json.loads(l) for l in (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8").splitlines()]


class EnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = ensure_corpus()

    def test_daticert_and_postacert_are_parsed(self):
        g = next(x for x in _gold() if x["kind"] == "cartella" and not x["duplicate_of"])
        raw = (self.corpus / g["envelope"]).read_bytes()
        out = s2.parse_envelope(raw, tmpdir("s2-one"))
        self.assertEqual(out["errors"], [])
        dc = out["daticert"]
        self.assertEqual(dc["tipo"], "posta-certificata")
        self.assertEqual(dc["mittente"], "notifica.cartelle@pec.agenzia-riscossione.example")
        self.assertTrue(dc["identificativo"].startswith("opec-syn."))
        self.assertTrue(dc["data"].endswith("+02:00"))
        self.assertEqual(out["inner"]["from_addr"], dc["mittente"])
        self.assertTrue(any(a["name"].endswith(".pdf") for a in out["attachments"]))

    def test_transport_signed_bytes_are_the_signed_bytes(self):
        g = next(x for x in _gold() if x["transport_signature_integrity"] == "ok")
        raw = (self.corpus / g["envelope"]).read_bytes()
        content, _ = s2.signed_part_bytes(raw)
        d = tmpdir("s2-sig")
        out = s2.parse_envelope(raw, d, d)
        info = cms.parse((d / out["transport"]["signature"]).read_bytes())
        self.assertTrue(cms.verify_integrity(info, content)[0])

    def test_evidence_is_not_modified(self):
        g = _gold()[0]
        p = self.corpus / g["envelope"]
        before = p.read_bytes()
        s2.parse_envelope(before, tmpdir("s2-evidence"))
        self.assertEqual(p.read_bytes(), before)

    def test_malformed_envelope_is_recorded_not_guessed(self):
        out = s2.parse_envelope(b"Subject: nothing\r\n\r\nplain text only\r\n", tmpdir("s2-bad"))
        self.assertIn("no multipart/signed transport envelope", out["errors"])
        self.assertIn("daticert.xml missing", out["errors"])
        self.assertIsNone(out["inner"])


if __name__ == "__main__":
    unittest.main()
