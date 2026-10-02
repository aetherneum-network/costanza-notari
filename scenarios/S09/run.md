# S09 - .p7m with valid integrity, unverifiable chain

*Company (synthetic): Officine Lagorai S.r.l. (the debtor) - Lesson L8 "Extracted must never imply verified".*

**Setup.** A precetto arrives as a CAdES-attached `.p7m` signed by Avv. Serena Lupatelli. Her
certificate is issued by the *Esempio UNTRUSTED Test CA*, which is not in the trust list (only the
synthetic Aetherneum TEST root is).

**Pass criterion.** `signature_integrity: "ok"` and `signer_chain_verified: false`
(`chain_status: "untrusted_issuer"`), shown as `NO` in the index column *Signer chain verified*, as
`ok / false / untrusted_issuer` in the *Signatures* sheet, and counted in the report. The PDF is still
extracted and classified: the signature stage labels it "extracted from .p7m", never "verified".
Where OpenSSL is available it agrees: `cms -verify -noverify` succeeds, `cms -verify -CAfile` fails.

```
python scenarios/S09/make_input.py
python scenarios/S09/check.py
```
