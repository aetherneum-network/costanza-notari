# Skills Certificate - v2 additions (Appendix A, A.4), mapped to code

> Synthetic alumna. Each line below is a claim; the right-hand columns say where the proof lives.

| # | Skill (A.4) | Implementation | Proof (tests / scenario) |
|---|---|---|---|
| 1 | Handoff receipts with anchor restatement and sentinel comparison | `pipeline/s5_classify.py` (`anchors_of`, handoff files), `pipeline/s6_consolidate.py` (receipts, `compare`, sentinel, release gate), `pipeline/run.py` (exit 2, nothing published) | `tests/test_s6_consolidate.py`, **S01** |
| 2 | Edition-bound values and superseded-value scanning of outgoing documents | `pipeline/s7_ledger.py` (`bound`, `edition_label`, `superseded_values.json`), `pipeline/s9_distribution.py` (forms incl. raw XLSX numbers, guards G1-G6, grouping by owner) | `tests/test_s7_ledger.py`, `tests/test_s9_distribution.py`, **S02** |
| 3 | Deadline-nature classification (actionable / computed / conditional / historical) | `rules/deadline_nature.json`, `pipeline/deadlines.py`, `pipeline/terms.py` + `rules/terms.json`, safety nets in `pipeline/classify.py` | `tests/test_terms.py`, `tests/test_safety_nets.py`, **S06** |
| 4 | Loud-failure publishing with optimistic concurrency and staleness banners | `pipeline/publish.py` (`publish(if_version=...)`, `_SUPERSEDED/`, `reader_view`), `pipeline/run.py` (FAILED, red banner, no "OK"), `pipeline/s8_build.py` (banner row, *Data as of*) | `tests/test_s8_build.py`, `tests/test_ops.py`, **S04** |
| 5 | Long-path-safe corpus enumeration with count reconciliation | `pipeline/s1_enumerate.py` (`\\?\` walk, manifest reconciliation, `robocopy /L` cross-count, naive count kept for comparison) | `tests/test_s1_enumerate.py`, **S08** |
| 6 | Author, transmitter and party separation in certified-mail attribution | `pipeline/attribution.py` (`transmitter_entity`, `author_entity`, `party_entity`, `contact_channel`, `assert_debtor_excluded`), `rules/sender_class.json`, `rules/attribution.json`, `pipeline/s6_consolidate.py::resolve_author` | `tests/test_s5_classify.py`, **S05** |
| 7 | Ordered, test-backed rule files for every classification decision | `rules/*.json` (every rule: `id`, `rationale`, `tests`), `pipeline/rules_engine.py` (first match wins, `run_inline_tests`, `diff_classifications`) | `tests/test_rules.py`, **S07** |

Carried over from the thesis and re-implemented here: PEC envelope parsing (`s2_envelope.py`),
CAdES `.p7m` / detached `.p7s` handling with integrity and chain as separate facts (`s3_signature.py`,
contributed by Adèle Maurique), text recovery with an OCR fallback interface (`s4_text.py`, `ocr.py` -
*OCR fallback: not available in this environment*), the canonical entity dictionary with structural debtor
exclusion (`entities.py`), the colour-coded master index and the deterministic DOCX report (`s8_build.py`,
python-docx instead of the thesis' Node `docx`), the append-only ledger by `base_id` (`s7_ledger.py`), and
heartbeats / full vs light runs / catch-up (`heartbeat.py`, **S10**).
