"""Optional, pluggable LLM assistance. DISABLED BY DEFAULT. Tests never call any API.

Design (Appendix A.2):

* chunk workers (~40 records): Claude Haiku 4.5 (``claude-haiku-4-5``);
* consolidation disputes (conflicting anchors, dissent): Claude Opus 5.5 (``claude-opus-5-5``).

Contract - the model is an assistant to the rule file, never its replacement:

1. Rules run first. The model sees only records with RECUPERARE fields.
2. Its output is a *proposal* (``llm_proposals``) shown next to the RECUPERARE
   cell. It never overwrites a rule output and never clears a RECUPERARE by
   itself: a human accepts it, then the fix goes into a rule or the source.
3. The debtor exclusion and the handoff sentinel apply to proposals too.
4. Structured output (JSON schema) only; a refusal or an invalid answer is a
   non-answer, logged, and the field stays RECUPERARE.

Enable with ``--llm anthropic`` (requires the ``anthropic`` package and
credentials). Measure before you split: the most capable model at low effort
often matches a cheaper one on the same chunk (A.2).
"""
from __future__ import annotations

import json

CHUNK_MODEL = "claude-haiku-4-5"
DISPUTE_MODEL = "claude-opus-5-5"

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {"type": "array", "items": {
            "type": "object",
            "properties": {"field": {"type": "string"}, "value": {"type": "string"},
                           "evidence": {"type": "string"}, "confidence": {"type": "string",
                                                                           "enum": ["low", "medium", "high"]}},
            "required": ["field", "value", "evidence", "confidence"], "additionalProperties": False}}},
    "required": ["proposals"], "additionalProperties": False,
}


class DisabledLLM:
    enabled = False

    def propose(self, record: dict) -> list:
        return []


class AnthropicLLM:  # pragma: no cover - never exercised offline
    enabled = True

    def __init__(self, chunk_model: str = CHUNK_MODEL, dispute_model: str = DISPUTE_MODEL):
        import anthropic  # lazy: the pipeline does not depend on it
        self.client = anthropic.Anthropic()
        self.chunk_model, self.dispute_model = chunk_model, dispute_model

    def propose(self, record: dict) -> list:
        fields = record.get("recuperare_fields", [])
        prompt = ("You assist a deterministic classifier of Italian certified-mail (PEC) procedural acts. "
                  "Propose values ONLY for these fields, quoting the evidence verbatim; if the evidence is "
                  f"not in the text, propose nothing. Fields: {fields}.\n\nSUBJECT: {record.get('subject')}\n")
        resp = self.client.messages.create(
            model=self.chunk_model, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA}},
        )
        if resp.stop_reason == "refusal":
            return []
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        try:
            return json.loads(text).get("proposals", [])
        except json.JSONDecodeError:
            return []

    def resolve_dispute(self, handoff: dict, receipt: dict) -> dict:
        resp = self.client.beta.messages.create(
            model=self.dispute_model, max_tokens=4096,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content":
                       "Two stages disagree on a handoff. Do not choose a value: explain which source document "
                       "each anchor comes from and what a human must check.\n"
                       f"HANDOFF: {json.dumps(handoff, ensure_ascii=False)}\n"
                       f"RECEIPT: {json.dumps(receipt, ensure_ascii=False)}"}],
        )
        if resp.stop_reason == "refusal":
            return {"explanation": None, "note": "model declined"}
        return {"explanation": next((b.text for b in resp.content if b.type == "text"), None)}


def get(name: str | None):
    if name in (None, "", "none", "disabled"):
        return DisabledLLM()
    if name == "anthropic":
        return AnthropicLLM()
    raise ValueError(f"unknown llm backend {name!r}")
