# Packaging design - Claude Agent Skill + MCP server

*Design document only. Nothing here is deployed; no server ships with this repository.*

> Synthetic proof pack. The skill and the server operate on the synthetic corpus and TEST PKI of this
> repository. Pointing them at real certified mail requires, at least: a real trust list, revocation
> checking, a legal review of every `[TO CONFIRM with counsel]` item, and a data-protection assessment.

## 1. As a Claude Agent Skill

A skill is a folder with a `SKILL.md` (YAML front matter + instructions) and the scripts it may run.

```
procedural-vigilance/
  SKILL.md                 # the contract below
  pipeline/ rules/ corpus/ # this repository's code, unchanged
  scripts/run.sh           # python -m pipeline.run "$@"
```

Proposed `SKILL.md`:

```markdown
---
name: procedural-vigilance
description: Classify an Italian certified-mail (PEC) corpus into a colour-coded master index with
  procedural deadlines, using ordered rule files; never guess - unresolved fields are RECUPERARE.
---
# Procedural vigilance (Costanza Notari, synthetic)
1. Run `scripts/run.sh --input <corpus> --as-of <ISO timestamp>`; read `build/work/run_report.md` FIRST.
2. If status is BLOCKED or FAILED, report the red banner verbatim. Never say "done" or "OK".
3. Answer "what is due / pending" only from `pipeline.status.status()` re-run in the same turn, citing its as_of.
4. Never edit master_index.xlsx or report.docx: fix a rule in rules/*.json (with its test) and re-run.
5. A RECUPERARE cell is an honest null: list it with its reason; do not fill it from your own reading
   unless the user asks, and then as a proposal, never as a value.
6. The debtor is never a counterparty. signer_chain_verified=false never means "forged".
```

Why a skill fits: the logic lives in rule files and deterministic code; the model's job is to run it,
read the run report, explain RECUPERARE items and propose rule fixes - exactly the division of labour
of Appendix A (A.2).

## 2. As an MCP server (four tools)

Transport: stdio. Every tool is a thin wrapper over an existing function; every call returns JSON with
an `as_of` and never writes outside a work directory given at start-up. Read-only on evidence.

| tool | wraps | input | output |
|---|---|---|---|
| `parse_pec` | `pipeline.s2_envelope.parse_envelope` | `{"path": "<.eml>"}` | daticert fields, inner headers, attachment list with SHA-256, transport-signature byte range |
| `verify_signature` | `pipeline.s3_signature.check` | `{"path": "<.p7m or .p7s>", "data_path?": "...", "validation_time": "<ISO>"}` | `signature_integrity`, `signer_chain_verified`, `chain_status`, signer, `claimed_signing_time`, `validation_time_source`, `revocation_checked:false` |
| `classify_chunk` | `pipeline.s5_classify.worker` + handoff writer | `{"records": [<=40 record states], "chunk_id": "chunk-07"}` | classifications + one handoff per record (1-5 anchors) - the consolidator's receipts are NOT produced here |
| `build_index` | stages 6-8 via `pipeline.run` | `{"work": "...", "as_of": "<ISO>", "if_version": n}` | run status (OK / BLOCKED / FAILED), banner, SHA-256 of XLSX/DOCX, store version, reader view |

JSON schema sketch (`classify_chunk`):

```json
{"name": "classify_chunk",
 "description": "Rule-first classification of at most 40 PEC records; returns results and handoff anchors. Never fills RECUPERARE by itself.",
 "input_schema": {"type": "object", "additionalProperties": false, "required": ["chunk_id", "records"],
   "properties": {"chunk_id": {"type": "string", "pattern": "^chunk-[0-9]{2}$"},
                  "records": {"type": "array", "maxItems": 40, "items": {"type": "object"}}}}}
```

Server rules (the lessons, enforced server-side, not left to the client):

* **L1** `build_index` refuses to publish when any handoff lacks an identical receipt; it returns
  `BLOCKED` with both file names and both authors.
* **L3** there is no cached `status`; every answer re-reads the ledger and carries `as_of`.
* **L4** a rejected `if_version` is an error result (`isError: true`), never a success with a note.
* **L5** authorship in results comes from `from` / `by`, never from file names.
* **L10** no tool deletes; superseded artefacts move to `_SUPERSEDED/`.

## 3. Model assignment (A.2)

* `classify_chunk` callers (fan-out workers): the ordered rule files, no model. The rule files carry the
  logic.
* Deadline classifier (v2.3, optional, OFF by default): Claude Opus 5.5 (`claude-opus-5-5`), effort
  `medium` by default (`--llm-effort` / `COSTANZA_LLM_EFFORT`). It is called only on records whose deadline
  the rules leave RECUPERARE, and it only proposes: the deterministic gate `rules/classifier_gate.json`
  decides what is committed. Measured numbers: README, *The deadline classifier (v2.3)*.
* Consolidation disputes and the nightly report narrative: Claude Opus 5.5 (`claude-opus-5-5`), which may
  explain a sentinel mismatch but never choose the value (`pipeline/llm_classifier.py::resolve_dispute`;
  not wired into the pipeline).
* Measure before splitting: the most capable model at low effort on the same chunk often matches a
  cheaper one; judge by cost per completed task. The nightly full run is not latency-sensitive (Batch API).

The optional deadline classifier (`pipeline/llm_classifier.py`) is OFF by default: it runs only with
`--llm anthropic` and an `ANTHROPIC_API_KEY`. Tests never call the API: they use a fake client with sockets
blocked.
