"""Deadline classifier for the records the rules leave RECUPERARE (v2.3). OFF BY DEFAULT.

Tests and CI never call any API: the classifier runs only with ``--llm anthropic`` AND a non-empty
``ANTHROPIC_API_KEY`` in the environment. ``--llm anthropic`` without a key is refused before any stage
runs: the run FAILS, it never silently goes on without the classifier it was asked for.

Model and effort (measured, eval/history.json):

* ``claude-opus-5-5`` for every call;
* effort ``medium`` by default, visible knob ``--llm-effort low|medium|high`` or the environment variable
  ``COSTANZA_LLM_EFFORT`` (the flag wins over the variable). README.md states the rule and the reason
  for the default.

Contract - the model assists the rule files, it never replaces them:

1. Rules run first. The model sees only records whose DEADLINE the rules left RECUPERARE.
2. It is sent what the D14 measure sent: the contract below, docs/TERMS.md verbatim, the term table ids,
   and the record's own text (PEC envelope, e-mail body, every document, principal first).
3. Its answer is a strict JSON object (``OUTPUT_SCHEMA``). A refusal, a truncated or invalid answer, or a
   transport error is a non-answer: the deadline stays RECUPERARE and the record says why.
4. The model never commits on its own: every answer goes through the deterministic gate
   (``pipeline/classifier_gate.py``, ``rules/classifier_gate.json``). Only an answer that passes every
   gate rule fills the cell, marked as the classifier's; a refused one abstains and the record keeps the
   id of the rule that refused it.
5. A non-transport API error (4xx: bad request, authentication, permission, unknown model) is a
   configuration fault, not an answer: the run FAILS.

Request shape (Claude Opus 5.5, Anthropic Python SDK): streaming ``messages.stream`` + ``get_final_message``;
``output_config = {"effort": ..., "format": {"type": "json_schema", ...}}``; the system prompt is marked
for prompt caching. No ``temperature``, no ``thinking`` budget, no forced ``tool_choice`` (Opus 5.5 refuses
them; thinking is adaptive and always on) and no model fallback: a refusal is an abstention, never an
answer from another model.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from .rules_engine import RULES_DIR

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5-5"
DISPUTE_MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high")
DEFAULT_EFFORT = "medium"
EFFORT_ENV = "COSTANZA_LLM_EFFORT"
MAX_TOKENS = 32000          # backstop only: a max_tokens stop is a non-answer
RECUPERARE = "RECUPERARE"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "deadline": {"type": "string"},
        "nature": {"type": "string", "enum": ["actionable", "computed", "none", "unknown"]},
        "act_type": {"type": "string"},
        "evidence": {"type": "string"},
        "computation": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["deadline", "nature", "act_type", "evidence", "computation", "confidence"],
    "additionalProperties": False,
}

# exception classes of the SDK that mean "the call did not get through": an abstention, never a FAIL
_TRANSPORT = {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError", "OverloadedError",
              "ServiceUnavailableError", "DeadlineExceededError", "RetryableError"}


class ClassifierConfigError(RuntimeError):
    """The classifier was asked for but cannot run as configured (no key, bad effort, 4xx): the run FAILS."""


class ClassifierStop(RuntimeError):
    """Raised by a caller's guard (e.g. a spending cap) around the client: stops the run, never swallowed."""


def resolve_effort(cli: str | None = None, environ=None) -> str:
    """The flag wins, then COSTANZA_LLM_EFFORT, then the default (medium). Anything else is refused."""
    env = os.environ if environ is None else environ
    for source, value in (("--llm-effort", cli), (EFFORT_ENV, env.get(EFFORT_ENV))):
        if value not in (None, ""):
            v = str(value).strip().lower()
            if v not in EFFORTS:
                raise ClassifierConfigError(f"{source}={value!r}: effort must be one of {', '.join(EFFORTS)}")
            return v
    return DEFAULT_EFFORT


# ---------------------------------------------------------------------------------------------- prompt
def system_prompt(as_of: _dt.datetime, rules_dir=None, docs_dir=None) -> str:
    rd = Path(rules_dir or RULES_DIR)
    terms_path = Path(docs_dir or ROOT / "docs") / "TERMS.md"
    if not terms_path.exists():
        raise ClassifierConfigError(f"the classifier needs docs/TERMS.md (not found: {terms_path.name})")
    terms = json.loads((rd / "terms.json").read_text(encoding="utf-8"))
    terms_md = terms_path.read_text(encoding="utf-8")
    expects = ", ".join(terms["expects_deadline"])
    table_ids = ", ".join(f"{t['id']} = {t['doc_type']}" for t in terms["terms"])
    return f"""You assist a deterministic classifier of Italian certified-mail (PEC) procedural acts (synthetic proof pack, every entity fictitious). The rule files left the DEADLINE field of this record as RECUPERARE: the rules abstained. Your answer is a PROPOSAL: a deterministic gate checks it, and only a value that passes the gate fills the RECUPERARE cell, marked as the classifier's; it never overwrites a rule output.

Task: propose the record's DRIVING DEADLINE, or abstain.

Hard rule: a wrong date, or "NONE" where a deadline exists, is a never-event. Answering RECUPERARE is always safe. Commit a value only when the record's text and the rules below determine it with certainty. Where the rules below say a case is RECUPERARE, answer RECUPERARE even if you could guess.

Reference instant (as_of): {as_of.isoformat()} (Europe/Rome).

Definitions
- Every date written in the act has a nature:
  actionable  - a stated due date or hearing ("entro il 14/11/2026", "udienza del ...", "scadenza della prima rata: ..."); its date is taken from the text as is;
  computed    - a relative term counted from the notification ("entro dieci giorni dalla notifica"), computed with the algorithm below;
  conditional - applies only if something happens ("qualora entro il ... non ...", lapse clauses): never driving;
  historical  - past facts (date of the act, of an invoice, "notificata il", "il termine ... e' scaduto"): never driving.
- Driving deadline = among the record's actionable and computed deadlines, the earliest one on or after as_of ({as_of.date().isoformat()}); if none is on or after as_of, the latest one (expired).
- "NONE" only if the act type is known, is NOT in the following list, and the act has no actionable or computed deadline. For act types in the list, no determinable deadline means RECUPERARE.
  Act types that expect a deadline: {expects}
- Notification date unknown (computed terms are RECUPERARE): sender class TARGET (internal forward of an act received by post), or PEC transport signature not "ok" (timestamp untrusted). Actionable dates written in the act stay valid in those cases.
- If the act type cannot be determined, its term policy is unknown: computed terms are RECUPERARE.
- Term table ids: {table_ids}.

Term rule implemented by the rule files (docs/TERMS.md of the pack, verbatim):
<terms_md>
{terms_md}
</terms_md>

Answer with the JSON object only:
- deadline: "YYYY-MM-DD", "NONE" or "RECUPERARE";
- nature: nature of the driving deadline ("actionable" or "computed"); "none" with NONE; "unknown" with RECUPERARE;
- act_type: the act type you used (a doc_type id of the term table, another short id, or RECUPERARE);
- evidence: ONE contiguous passage of the record the value rests on, copied verbatim - the gate looks it up in the record's text and refuses the value if the passage is not found as written (no fragments joined by "...", no paraphrase); for an actionable deadline the passage contains the date as written, for a computed one the passage that states the term (or, if the act states none, the words that identify the act type); empty string with RECUPERARE;
- computation: one line - start day, days counted, suspension and roll-over applied; empty if nothing was computed;
- confidence: low, medium or high.
"""


def user_message(rec: dict, env: dict, txt: dict) -> str:
    dc = env.get("daticert") or {}
    inner = env.get("inner") or {}
    notif = rec.get("notification_date") or f"unknown - {rec.get('notification_note') or 'no reason given'}"
    lines = [
        f"RECORD {rec['record_id']}",
        "PEC envelope (daticert):",
        f"  timestamp: {dc.get('data')}",
        f"  sender: {dc.get('mittente')}",
        f"  subject: {dc.get('oggetto')}",
        f"PEC transport signature: {rec.get('transport_signature_integrity')}",
        f"Sender class (rules): {rec.get('sender_class')}",
        f"Act type (rules): {rec.get('doc_type')}",
        f"Notification date (rules): {notif}",
        f"Why the rules abstained on the deadline: {(rec.get('recuperare_reasons') or {}).get('deadline', '')}",
        "",
        "EMAIL BODY:",
        (inner.get("body") or "").strip() or "[empty]",
    ]
    docs = sorted(txt.get("documents", []), key=lambda d: d["name"] != txt.get("principal"))  # principal first
    for i, d in enumerate(docs, start=1):
        tag = " (principal)" if d["name"] == txt.get("principal") else ""
        body = (d.get("text") or "").strip() or "[no text layer: scanned image, no OCR available]"
        lines += ["", f"DOCUMENT {i}{tag} {d['name']}:", body]
    return "\n".join(lines)


def request_params(system: str, user: str, effort: str) -> dict:
    """Everything but max_tokens: the same dict serves messages.count_tokens and messages.stream."""
    return {
        "model": MODEL,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    }


def parse_answer(msg) -> tuple[str, dict | None]:
    """(status, answer). status 'ok' = a schema-valid object; the gate judges its values."""
    if getattr(msg, "stop_reason", None) == "refusal":
        return "refusal", None
    if getattr(msg, "stop_reason", None) == "max_tokens":
        return "max_tokens", None
    text = next((b.text for b in (getattr(msg, "content", None) or []) if getattr(b, "type", None) == "text"), None)
    if text is None:
        return "no_text_block", None
    try:
        ans = json.loads(text)
    except json.JSONDecodeError:
        return "invalid_json", None
    props = OUTPUT_SCHEMA["properties"]
    if (not isinstance(ans, dict) or set(ans) != set(props) or not all(isinstance(v, str) for v in ans.values())
            or any(ans[k] not in p["enum"] for k, p in props.items() if "enum" in p)):
        return "invalid_schema", ans if isinstance(ans, dict) else None
    return "ok", ans


def _usage(msg) -> dict:
    u = getattr(msg, "usage", None)
    if u is None:
        return {}
    if hasattr(u, "model_dump"):
        return u.model_dump(mode="json", exclude_none=True)
    return dict(u)


def _is_transport(exc: BaseException) -> bool:
    return any(c.__name__ in _TRANSPORT for c in type(exc).__mro__)


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DisabledLLM:
    enabled = False


class AnthropicLLM:
    enabled = True

    def __init__(self, effort: str | None = None, client=None, api_key: str | None = None, rules_dir=None,
                 docs_dir=None):
        self.effort = resolve_effort(effort)
        self.model = MODEL
        self.rules_dir, self.docs_dir = rules_dir, docs_dir
        self._system: dict[str, str] = {}
        if client is None:
            key = (api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")).strip()
            if not key:
                raise ClassifierConfigError("--llm anthropic needs ANTHROPIC_API_KEY in the environment: refused, "
                                            "nothing was called")
            try:
                import anthropic  # lazy: the pipeline does not depend on it
            except ImportError as exc:
                raise ClassifierConfigError("--llm anthropic needs the 'anthropic' package") from exc
            client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=900.0)
        self.client = client

    def system_for(self, as_of: _dt.datetime) -> str:
        k = as_of.isoformat()
        if k not in self._system:
            self._system[k] = system_prompt(as_of, self.rules_dir, self.docs_dir)
        return self._system[k]

    def params(self, rec: dict, env: dict, txt: dict, as_of: _dt.datetime) -> dict:
        return request_params(self.system_for(as_of), user_message(rec, env, txt), self.effort)

    def propose(self, rec: dict, env: dict, txt: dict, as_of: _dt.datetime) -> dict:
        """One call. Returns the record's ``classifier`` block (answer, usage, status); the gate is applied
        by the caller (pipeline/s5_classify.py)."""
        params = self.params(rec, env, txt, as_of)
        out = {"model": self.model, "effort": self.effort, "status": None, "stop_reason": None, "request_id": None,
               "answer": None, "usage": {}, "error": None, "started_utc": _utc_now()}
        try:
            with self.client.messages.stream(max_tokens=MAX_TOKENS, **params) as stream:
                msg = stream.get_final_message()
        except ClassifierStop:
            raise
        except Exception as exc:  # noqa: BLE001 - sorted below: transport = abstain, anything else = FAIL
            if _is_transport(exc):
                out.update(status="transport_error", error=f"{type(exc).__name__}: {str(exc)[:200]}",
                           finished_utc=_utc_now())
                return out
            raise ClassifierConfigError(f"classifier call failed on {rec.get('record_id')}: "
                                        f"{type(exc).__name__} {getattr(exc, 'status_code', '')}".rstrip()) from exc
        status, ans = parse_answer(msg)
        out.update(status=status, answer=ans, stop_reason=getattr(msg, "stop_reason", None),
                   request_id=getattr(msg, "_request_id", None), usage=_usage(msg), finished_utc=_utc_now())
        return out

    def resolve_dispute(self, handoff: dict, receipt: dict) -> dict:  # pragma: no cover - not wired, kept as in v2.2
        resp = self.client.beta.messages.create(
            model=DISPUTE_MODEL, max_tokens=4096,
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


def get(name: str | None, effort: str | None = None, client=None):
    """None / "" / "none" / "disabled" -> OFF. "anthropic" -> the classifier (needs a key unless a client
    is injected). Anything else is refused."""
    if name in (None, "", "none", "disabled"):
        return DisabledLLM()
    if name == "anthropic":
        return AnthropicLLM(effort=effort, client=client)
    raise ClassifierConfigError(f"unknown llm backend {name!r}")
