"""Versioned record contracts; validation is not provenance or learning authorization."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

VERSION = "1.1-draft"
SUPPORTED_VERSIONS = {"1.0-draft", VERSION}
V11_UNAVAILABLE_REASONS = {
    "invalid_configuration",
    "invalid_temporary_configuration",
    "temporary_expired",
    "budget_exhausted",
    "model_mismatch",
    "invalid_input",
}
FAMILIES = {"prompt", "retrieval", "routing", "workflow", "skill"}
STATUSES = {"observed", "unavailable", "not_sampled", "withdrawn"}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def is_digest(value):
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(c in "0123456789abcdef" for c in value[7:])
    )


def canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, OverflowError, UnicodeError) as exc:
        raise ContractError("non-canonical JSON") from exc


def record_id(record):
    payload = {k: v for k, v in record.items() if k != "record_id"}
    return "sha256:" + hashlib.sha256(canonical(payload)).hexdigest()


def seal(payload):
    record = dict(payload)
    record["record_id"] = record_id(record)
    validate(record)
    return record


def validate(record):
    require(type(record) is dict, "record must be an object")
    kind = record.get("kind")
    common = {"schema_version", "kind", "record_id", "created_at"}
    experience = {
        "case_id",
        "family",
        "policy_ref",
        "source_refs",
        "lineage_status",
        "outcome_ref",
    }
    evaluation = {
        "experience_ref",
        "status",
        "success",
        "score",
        "judge",
        "rubric_ref",
        "reason",
        "supersedes",
    }
    require(isinstance(kind, str) and kind in {"experience", "evaluation"}, "unknown kind")
    require(
        set(record) == common | (experience if kind == "experience" else evaluation),
        "missing or unknown fields",
    )
    require(
        isinstance(record["schema_version"], str) and record["schema_version"] in SUPPORTED_VERSIONS,
        "unsupported schema version",
    )
    require(is_digest(record["record_id"]), "invalid identity")
    require(record["record_id"] == record_id(record), "content identity mismatch")
    timestamp = record["created_at"]
    require(isinstance(timestamp, str) and timestamp.endswith("Z"), "UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("invalid timestamp") from exc
    require(parsed.tzinfo is not None, "timezone required")
    if kind == "experience":
        require(
            isinstance(record["case_id"], str) and 0 < len(record["case_id"]) <= 128,
            "case id required",
        )
        require(
            isinstance(record["family"], str) and record["family"] in FAMILIES,
            "unsupported family",
        )
        require(is_digest(record["policy_ref"]), "immutable policy reference required")
        sources = record["source_refs"]
        require(
            type(sources) is list and len(sources) <= 256 and all(is_digest(x) for x in sources),
            "invalid bounded sources",
        )
        require(len(set(sources)) == len(sources), "duplicate sources")
        require(
            isinstance(record["lineage_status"], str) and record["lineage_status"] in {"observed", "legacy_unknown"},
            "invalid lineage",
        )
        require(
            record["outcome_ref"] is None or is_digest(record["outcome_ref"]),
            "invalid outcome",
        )
    else:
        require(is_digest(record["experience_ref"]), "experience reference required")
        require(
            isinstance(record["status"], str) and record["status"] in STATUSES,
            "invalid evaluation status",
        )
        require(
            record["supersedes"] is None or is_digest(record["supersedes"]),
            "invalid predecessor",
        )
        require(record["supersedes"] != record["record_id"], "self revision")
        require(is_digest(record["rubric_ref"]), "immutable rubric required")
        judge = record["judge"]
        require(
            type(judge) is dict and set(judge) == {"kind", "identifier", "revision"},
            "judge provenance required",
        )
        require(
            isinstance(judge["kind"], str) and judge["kind"] in {"human", "executable", "model"},
            "invalid judge kind",
        )
        require(
            all(isinstance(judge[k], str) and 0 < len(judge[k]) <= 128 for k in ("identifier", "revision")),
            "judge version required",
        )
        success, score = record["success"], record["score"]
        require(success is None or type(success) is bool, "verdict must be bool or null")
        require(
            score is None or (type(score) in {int, float} and 0 <= score <= 10 and math.isfinite(score)),
            "invalid score",
        )
        reasons = {
            None,
            "insufficient_balance",
            "timeout",
            "not_configured",
            "invalid_response",
            "rate_limited",
            "authentication_failed",
            "transport_error",
            "http_error",
            "internal_error",
            "invalid_local_score",
            "not_sampled",
            "label_withdrawn",
            "source_revoked",
            "manual_review",
        }
        extra_reasons = V11_UNAVAILABLE_REASONS if record["schema_version"] == VERSION else set()
        reasons |= extra_reasons
        require(
            (record["reason"] is None or isinstance(record["reason"], str)) and record["reason"] in reasons,
            "invalid reason",
        )
        if record["status"] == "observed":
            require(success is not None or score is not None, "observed needs evidence")
            require(record["reason"] is None, "observed cannot have unavailable reason")
        else:
            require(success is None and score is None, "unobserved cannot carry a label")
            require(record["reason"] is not None, "unobserved needs reason")
            if record["status"] == "unavailable":
                require(
                    record["reason"]
                    in {
                        "insufficient_balance",
                        "timeout",
                        "not_configured",
                        "invalid_response",
                        "rate_limited",
                        "authentication_failed",
                        "transport_error",
                        "http_error",
                        "internal_error",
                        "invalid_local_score",
                    }
                    | extra_reasons,
                    "invalid unavailable reason",
                )
            if record["status"] == "withdrawn":
                require(record["supersedes"] is not None, "withdrawal needs target")
                require(
                    record["reason"] in {"label_withdrawn", "source_revoked", "manual_review"},
                    "invalid withdrawal reason",
                )
            if record["status"] == "not_sampled":
                require(record["reason"] == "not_sampled", "invalid sampling reason")
    return record


def resolve(experience, evaluations, revoked=()):
    """Resolve one rubric/judge chain; ambiguous histories fail closed.

    Returned eligibility is structural only, never permission to learn or promote.
    Repeated identical records are idempotent; competing roots/forks are rejected.
    """
    validate(experience)
    require(experience["kind"] == "experience", "experience required")
    require(
        isinstance(evaluations, (list, tuple)) and len(evaluations) <= 1024,
        "bounded evaluations required",
    )
    require(
        isinstance(revoked, (list, tuple, set, frozenset)) and all(is_digest(x) for x in revoked),
        "invalid revocation set",
    )
    nodes = {}
    for item in evaluations:
        validate(item)
        require(
            item["kind"] == "evaluation" and item["experience_ref"] == experience["record_id"],
            "evaluation target mismatch",
        )
        nodes[item["record_id"]] = item
    empty = {
        "quality_eligible": False,
        "success_eligible": False,
        "latest": None,
        "reason": "no_evaluation",
    }
    if not nodes:
        return empty
    roots = [v for v in nodes.values() if v["supersedes"] is None]
    require(len(roots) == 1, "missing or competing roots")
    children = {}
    for item in nodes.values():
        parent_id = item["supersedes"]
        if parent_id is None:
            continue
        require(parent_id in nodes, "missing predecessor")
        require(parent_id not in children, "ambiguous revision fork")
        parent = nodes[parent_id]
        require(parent["status"] != "withdrawn", "withdrawal is terminal for this chain")
        require(
            item["judge"] == parent["judge"] and item["rubric_ref"] == parent["rubric_ref"],
            "revision provenance changed",
        )
        children[parent_id] = item
    latest = roots[0]
    visited = {latest["record_id"]}
    while latest["record_id"] in children:
        latest = children[latest["record_id"]]
        require(latest["record_id"] not in visited, "revision cycle")
        visited.add(latest["record_id"])
    require(len(visited) == len(nodes), "disconnected history")
    dependencies = {
        experience["record_id"],
        experience["policy_ref"],
        experience["outcome_ref"],
    }
    dependencies.update(experience["source_refs"])
    dependencies.update(nodes)
    dependencies.update(x["rubric_ref"] for x in nodes.values())
    result = dict(empty, latest=latest["record_id"])
    if set(revoked) & dependencies:
        return dict(result, reason="revoked_dependency")
    if experience["lineage_status"] != "observed" or not experience["source_refs"] or experience["outcome_ref"] is None:
        return dict(result, reason="incomplete_lineage")
    if latest["status"] != "observed":
        return dict(result, reason=latest["status"])
    return dict(
        result,
        quality_eligible=latest["score"] is not None,
        success_eligible=latest["success"] is not None,
        reason="structurally_eligible",
    )
