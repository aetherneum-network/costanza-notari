# Signature stage - semantics

*Contributed by Adèle Maurique (synthetic alumna, via Claude Opus 5.5). Code: `pipeline/s3_signature.py`.*

> SYNTHETIC. The only certificates in this repository come from a TEST PKI derived from the public
> corpus seed (`corpus/testca.py`). No real certification authority, signer or trust list is involved.

## Two facts, two fields

| field | question it answers | values |
|---|---|---|
| `signature_integrity` | Do the signed bytes match what the signer's key signed? | `ok`, `failed`, `unparseable`, `not_signed` |
| `signer_chain_verified` | Does the signer certificate chain to a trust anchor we accept, valid at the validation time? | `true` / `false` + `chain_status` |

They are never merged. `openssl cms -verify -noverify -binary -inform DER -in X.p7m -out X` checks
integrity and extracts the content but does **not** validate the chain (Appendix A, L8). Our stage
records exactly that distinction: a `.p7m` can be `signature_integrity: "ok"` with
`signer_chain_verified: false` (scenario S09). *Extracted* never implies *verified*.

`chain_status` values: `verified`, `untrusted_issuer`, `expired_at_validation_time`,
`not_yet_valid_at_validation_time`, `bad_certificate_signature`, `issuer_not_ca`,
`no_signer_certificate`, `no_validation_time`, `path_too_long`.

## Trust

* Exactly one trust anchor: `corpus/out/testca/trust/test-root-ca.pem` (the synthetic TEST root).
* Path building: signer -> certificates embedded in the CMS -> trust anchor, verifying each RSA
  signature, the CA flag of every issuer and the validity window of every certificate.
* The `Esempio UNTRUSTED Test CA` is deliberately absent from the trust list.

## Time of signing

| time | where it comes from | trusted? | used for |
|---|---|---|---|
| `claimed_signing_time` | CMS `signingTime` signed attribute | **No** - asserted by the signer; no RFC 3161 timestamp token | reported; `valid_at_claimed_signing_time` shown for information |
| `validation_time` | `daticert.xml` `<data>` of the PEC provider | Yes, as third-party evidence, *if* the provider's transport signature verifies | chain validity is evaluated at this instant |

Rationale: the signed attachment travels inside `postacert.eml`, which is covered by the provider's
transport signature; the provider's timestamp is therefore the earliest third-party evidence that the
signed object existed. If the transport signature fails, `validation_time` is `null` and the chain
status becomes `no_validation_time` - we do not fall back to the signer's own claim.

Consequence (tested): a signer certificate that expired on 2026-07-31 23:59:59 UTC yields
`expired_at_validation_time` for any PEC delivered after that instant, even if the signer's
`signingTime` claims an earlier moment.

## What is NOT done

* No CRL / OCSP: `revocation_checked: false`.
* No assessment of qualified status (eIDAS / CAD): `qualified_status: "not_assessed"`.
* No legal conclusion is drawn from any of these fields. **[TO CONFIRM with counsel]** the validation-time
  policy (PEC timestamp vs. signing time) and the evidentiary value of a verified chain before any real use.
