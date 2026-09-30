import datetime as dt
import json
import subprocess
import unittest

from tests._util import ROOT, ensure_corpus, openssl, tmpdir
from pipeline import s2_envelope as s2, s3_signature as s3
from pipeline.lib import rsa, x509

TRUST = ROOT / "corpus" / "out" / "testca" / "trust"
UTC = dt.timezone.utc


def _gold():
    return [json.loads(l) for l in (ROOT / "corpus" / "gold" / "labels.jsonl").read_text(encoding="utf-8").splitlines()]


def _process(g, name):
    work = tmpdir(name)
    raw = (ROOT / "corpus" / "out" / g["envelope"]).read_bytes()
    env = {"record_id": "ARC-T", "envelope": g["envelope"], "sha256": "", **s2.parse_envelope(raw, work / "att" / "ARC-T", work)}
    st = s3.run({"records": [env]}, work, TRUST, work / "03.json")
    return st["records"][0], work


class SignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_corpus()
        cls.gold = _gold()

    def _find(self, pred):
        for g in self.gold:
            if not g["duplicate_of"]:
                for s in g["signatures"]:
                    if pred(s):
                        return g, s
        self.fail("no such case in corpus")

    def test_integrity_and_chain_are_separate_fields(self):
        g, s = self._find(lambda s: s["chain_status"] == "untrusted_issuer" and s["format"] == "CAdES-attached")
        rec, _ = _process(g, "s3-untrusted")
        a = next(x for x in rec["attachments"] if x["file"] == s["file"])
        self.assertEqual(a["signature_integrity"], "ok")
        self.assertIs(a["signer_chain_verified"], False)
        self.assertEqual(a["chain_status"], "untrusted_issuer")
        self.assertEqual(rec["documents"][0]["source"], "extracted from .p7m")  # extracted, NOT verified

    def test_tampered_p7m_fails_integrity(self):
        g, s = self._find(lambda s: s["signature_integrity"] == "failed")
        rec, _ = _process(g, "s3-tampered")
        a = next(x for x in rec["attachments"] if x["file"] == s["file"])
        self.assertEqual(a["signature_integrity"], "failed")
        self.assertTrue(any("messageDigest mismatch" in n for n in a["notes"]))

    def test_expired_signer_at_validation_time(self):
        g, s = self._find(lambda s: s["chain_status"] == "expired_at_validation_time")
        rec, _ = _process(g, "s3-expired")
        a = next(x for x in rec["attachments"] if x["file"] == s["file"])
        self.assertEqual((a["signature_integrity"], a["signer_chain_verified"], a["chain_status"]),
                         ("ok", False, "expired_at_validation_time"))
        self.assertEqual(a["validation_time_source"], s3.VALIDATION_TIME_SOURCE)
        self.assertFalse(a["revocation_checked"])

    def test_verified_chain_goes_through_the_intermediate(self):
        g, s = self._find(lambda s: s["chain_status"] == "verified" and s["format"] == "CAdES-attached")
        rec, _ = _process(g, "s3-ok")
        a = next(x for x in rec["attachments"] if x["file"] == s["file"])
        self.assertTrue(a["signer_chain_verified"])
        self.assertEqual(len(a["chain_path"]), 3)  # signer -> Firme CA -> Root

    def test_broken_transport_signature_voids_validation_time(self):
        g = next(x for x in self.gold if x["transport_signature_integrity"] == "failed")
        rec, _ = _process(g, "s3-transport")
        self.assertEqual(rec["transport"]["signature_integrity"], "failed")

    def test_only_the_test_root_is_trusted(self):
        anchors = s3.load_trust_anchors(TRUST)
        self.assertEqual([a.subject["CN"] for a in anchors], ["Aetherneum TEST Root CA - NOT FOR PRODUCTION"])

    def test_self_signed_foreign_root_is_untrusted(self):
        k = rsa.generate("foreign", 3, bits=1024)
        n = x509.name("Foreign Root")
        c = x509.parse_certificate(x509.build_certificate(
            serial=1, issuer=n, subject=n, not_before=dt.datetime(2025, 1, 1, tzinfo=UTC),
            not_after=dt.datetime(2030, 1, 1, tzinfo=UTC), subject_key=k.public, issuer_key=k, issuer_pub=k.public,
            is_ca=True))
        ok, status, _ = s3.validate_chain(c, [], s3.load_trust_anchors(TRUST), dt.datetime(2026, 10, 1, tzinfo=UTC))
        self.assertEqual((ok, status), (False, "untrusted_issuer"))

    def test_openssl_agrees_extracted_is_not_verified(self):
        ossl = openssl()
        if not ossl:
            self.skipTest("openssl not available")
        g, s = self._find(lambda s: s["chain_status"] == "untrusted_issuer" and s["format"] == "CAdES-attached")
        _, work = _process(g, "s3-openssl")
        p7m = next((work / "att" / "ARC-T").glob("*.p7m"))
        noverify = subprocess.run([ossl, "cms", "-verify", "-noverify", "-binary", "-inform", "DER", "-in", str(p7m),
                                   "-out", str(work / "x.pdf")], capture_output=True, text=True)
        chain = subprocess.run([ossl, "cms", "-verify", "-binary", "-inform", "DER", "-in", str(p7m), "-CAfile",
                                str(TRUST / "test-root-ca.pem"), "-purpose", "any", "-out", str(work / "y.pdf")],
                               capture_output=True, text=True)
        self.assertEqual(noverify.returncode, 0, noverify.stderr)   # integrity ok + content extracted
        self.assertNotEqual(chain.returncode, 0)                     # chain NOT verifiable


if __name__ == "__main__":
    unittest.main()
