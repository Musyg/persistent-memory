"""Small shared readonly tool; configuration is never supplied by the model."""
import asyncio
import os
import threading

from .typed_client import Client
from .typed_protocol import ContractError

NAME = "memory_typed_context"
TOOL = {"type": "function", "function": {"name": NAME, "description": "Retrieve current admitted evidence from the explicitly configured typed memory cohort. Returns structured availability and provenance; no writes or automatic legacy adoption.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 4096}, "as_of": {"type": "string"}, "conditions": {"type": "object", "additionalProperties": {"type": ["string", "boolean", "integer"]}}, "evidence_kinds": {"type": "array", "items": {"enum": ["document", "observation", "hypothesis", "procedure", "task", "feedback"]}}, "top_k": {"type": "integer", "minimum": 1, "maximum": 5}, "max_context_chars": {"type": "integer", "minimum": 0, "maximum": 2000}}, "required": ["query"], "additionalProperties": False}}}
_calls = threading.BoundedSemaphore(2)


def enabled(mode="hermes"):
    return mode in {"hermes", "legion"} and os.environ.get("HERMES_TYPED_MEMORY_ENABLED", "0") == "1"


def with_tool(existing, mode="hermes"):
    return list(existing) + ([TOOL] if enabled(mode) and not any(item["function"]["name"] == NAME for item in existing) else [])


async def execute_tool(arguments, mode="hermes", client=None):
    if not enabled(mode):
        return {"success": False, "result": {"status": "refused", "reason": "feature_disabled"}, "error": "feature_disabled"}
    # Worker retains the slot until it really exits, including caller cancellation.
    if not _calls.acquire(blocking=False):
        return {"success": False, "result": {"status": "refused", "reason": "busy"}, "error": "busy"}
    def work():
        try:
            actual = client or Client(os.environ["HERMES_TYPED_MEMORY_URL"], os.environ["HERMES_TYPED_MEMORY_TOKEN_FILE"], os.environ["HERMES_TYPED_MEMORY_POLICY"], os.environ["HERMES_TYPED_MEMORY_WORKSPACE"])
            return actual.context(arguments)
        finally:
            _calls.release()
    try:
        # Shield the queued worker too: cancelling a not-yet-started executor
        # future would otherwise skip work.finally and leak its admission slot.
        result = await asyncio.shield(asyncio.to_thread(work))
        return {"success": result["status"] == "completed", "result": result, "error": None if result["status"] == "completed" else result.get("reason", result["status"])}
    except (ContractError, KeyError, OSError):
        return {"success": False, "result": {"status": "unavailable", "reason": "client_configuration_or_contract"}, "error": "client_configuration_or_contract"}
