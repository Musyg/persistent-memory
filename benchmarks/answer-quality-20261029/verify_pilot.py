"""Verify a published synthetic evidence bundle using Python's standard library.

Reads files only. It does not generate responses, judge answer quality, import the
memory application, contact a provider, or reconstruct private runtime traces.
Usage: python verify_pilot.py [bundle_directory]
"""

import base64
import collections
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=no_duplicate_keys)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), label + " fields")


def decode_blob(value, label):
    exact_keys(value, ("bytes", "sha256", "base64"), label)
    require(type(value["bytes"]) is int and value["bytes"] >= 0, label + " size")
    raw = base64.b64decode(value["base64"], validate=True)
    require(len(raw) == value["bytes"] and sha(raw) == value["sha256"], label + " hash")
    return raw


def verdict(value, artifact, projection):
    exact_keys(value, ("body", "body_sha256", "terms_sha256", "projection_sha256"), "reader")
    require(isinstance(value["body"], str), "reader body type")
    require(sha(value["body"].encode("utf-8")) == value["body_sha256"], "reader body hash")
    require(value["terms_sha256"] == artifact, "reader/artifact binding")
    require(value["projection_sha256"] == projection, "reader/projection binding")
    body = decode(value["body"])
    exact_keys(body, ("success", "critical_violation", "reason"), "verdict")
    for key in ("success", "critical_violation"):
        require(body[key] is None or type(body[key]) is bool, "verdict Boolean type")
    require(isinstance(body["reason"], str), "verdict reason type")
    require(not (body["success"] is True and body["critical_violation"] is True), "incompatible verdict")
    return body


def reconcile(completed, left, right):
    keys = ("success", "critical_violation")
    if not completed or left is None or right is None or any(
        left[k] is None or right[k] is None or left[k] != right[k] for k in keys
    ):
        return {"success": None, "critical_violation": None, "status": "unknown"}
    return {"success": left["success"], "critical_violation": left["critical_violation"], "status": "confirmed"}


def label(value):
    return "unknown" if value is None else "success" if value else "failure"


def pair_outcome(memory, lexical):
    if memory is None or lexical is None:
        return "unknown"
    if memory and not lexical:
        return "gain"
    if lexical and not memory:
        return "loss"
    return "tie_success" if memory else "tie_failure"


def pointer(document, path):
    require(isinstance(path, str) and path.startswith("/histories/"), "dataset pointer")
    value = document
    for part in path.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def verify(directory):
    directory = directory.resolve()
    manifest = decode((directory / "MANIFEST.json").read_bytes())
    require(manifest["inventory_only"] is True, "manifest scope")
    required_files = {"README.fr.md", "README.md", "RESULTS.json", "EVIDENCE192.json", "verify_pilot.py"}
    require(set(manifest["files"]) == required_files, "manifest file set")
    for name, pin in manifest["files"].items():
        target = (directory / name).resolve()
        require(target.parent == directory and target.is_file(), "manifest path")
        raw = target.read_bytes()
        require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "manifest hash: " + name)

    result = decode((directory / "RESULTS.json").read_bytes())
    evidence_raw = (directory / "EVIDENCE192.json").read_bytes()
    require(sha(evidence_raw) == result["evidence_sha256"], "linked evidence hash")
    evidence = decode(evidence_raw)
    exact_keys(evidence, ("schema", "synthetic_only", "source_dataset", "source_rubric", "sources", "retrieval_followup", "cases"), "evidence")
    require(evidence["synthetic_only"] is True, "synthetic evidence scope")
    dataset = decode(decode_blob(evidence["source_dataset"], "source dataset"))
    rubric = decode(decode_blob(evidence["source_rubric"], "source rubric"))
    require(dataset["synthetic_only"] is True and dataset["development_only"] is True, "development dataset")
    histories = {x["history_id"]: x for x in dataset["histories"]}
    require(len(histories) == 8, "eight histories")
    require(collections.Counter(x["language"] for x in histories.values()) == {"FR": 4, "EN": 4}, "language counts")
    require(isinstance(rubric, dict), "rubric object")
    for source in evidence["sources"]:
        exact_keys(source, ("title", "sha256", "bytes"), "source pin")
        require(re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None, "source pin digest")
    pins = {source["title"]: source for source in evidence["sources"]}
    require(len(pins) == len(evidence["sources"]), "unique source titles")
    require(evidence["source_dataset"]["sha256"] == pins["Synthetic development histories"]["sha256"], "dataset source pin")
    require(evidence["source_rubric"]["sha256"] == pins["Closed semantic rubric"]["sha256"], "rubric source pin")

    cases = evidence["cases"]
    require(len(cases) == 192, "full denominator")
    case_keys = ("synthetic_only", "case_id", "history_id", "arm", "checkpoint", "question_id", "question_text", "query", "as_of", "conditions", "expected_status", "expected_source_facts", "retrieved_items", "retrieval_counts", "terms", "control", "functional_evidence", "functional_gate", "artifact_available", "format_failure", "readers", "projection_sha256", "primary", "secondary_posthoc", "usage", "service_tier")
    primary = {arm: collections.Counter() for arm in ("M", "L")}
    secondary = {arm: collections.Counter() for arm in ("M", "L")}
    coverage = {arm: {"questions_with_required_facts": 0, "all_required_facts_supplied": 0, "required_facts": 0, "facts_supplied": 0} for arm in ("M", "L")}
    usage = {arm: collections.Counter() for arm in ("M", "L")}
    prices = result["pricing"]["USD_per_million_tokens"]
    costs = {arm: Decimal(0) for arm in ("M", "L")}
    groups = collections.defaultdict(dict)
    artifact_count = control_failures = format_failures = verdict_count = agreements = 0
    ids = set()
    for row in cases:
        exact_keys(row, case_keys, "case")
        require(row["synthetic_only"] is True, "case synthetic scope")
        history, arm = row["history_id"], row["arm"]
        require(history in histories and arm in ("M", "L"), "case identity")
        require(row["checkpoint"] in (2, 4, 8) and row["question_id"] in ("Q1", "Q2", "Q3", "Q4"), "case grid")
        expected_id = history + ".short." + arm + ".S" + str(row["checkpoint"]) + "." + row["question_id"]
        require(row["case_id"] == expected_id and expected_id not in ids, "unique case ID")
        ids.add(expected_id)
        require(row["conditions"] == {"project": history}, "synthetic conditions")
        require(row["service_tier"] == "default", "observed service tier")
        group = (history, row["checkpoint"], row["question_id"])
        require(arm not in groups[group], "duplicate pair arm")

        for fact in row["expected_source_facts"]:
            exact_keys(fact, ("source_id", "observation_id", "dataset_json_pointer", "text", "text_sha256", "metadata"), "expected fact")
            require(fact["source_id"].startswith(history.lower() + "-"), "expected synthetic source ID")
            require(pointer(dataset, fact["dataset_json_pointer"]) == fact["text"], "source-grounded expected text")
            require(sha(fact["text"].encode("utf-8")) == fact["text_sha256"], "expected fact text hash")
        for item in row["retrieved_items"]:
            exact_keys(item, ("source_id", "version_id", "text", "metadata"), "retrieved item")
            require(item["source_id"].startswith(history.lower() + "-"), "retrieved synthetic source ID")
            require(re.fullmatch(r"[0-9a-f]{32}", item["version_id"]) is not None, "synthetic version ID")
        exact_keys(row["retrieval_counts"], ("candidate_count", "context_chars", "item_count"), "retrieval counts")
        require(all(type(n) is int and n >= 0 for n in row["retrieval_counts"].values()), "retrieval count types")
        require(row["retrieval_counts"]["item_count"] == len(row["retrieved_items"]), "retrieved item count")
        require(row["retrieval_counts"]["context_chars"] == len("\n\n".join(item["text"] for item in row["retrieved_items"])), "retrieved context length")
        facts = row["expected_source_facts"]
        if facts:
            found = 0
            for fact in facts:
                found += any(item["source_id"] == fact["source_id"] and item["text"] == fact["text"] and all(item["metadata"].get(k) == v for k, v in fact["metadata"].items()) for item in row["retrieved_items"])
            coverage[arm]["questions_with_required_facts"] += 1
            coverage[arm]["required_facts"] += len(facts)
            coverage[arm]["facts_supplied"] += found
            coverage[arm]["all_required_facts_supplied"] += found == len(facts)

        flags = row["functional_evidence"]
        flag_names = ("actual_write_readback_bound", "store_unchanged", "terms_inventory_bound", "control_present", "unrelated_inventory_exact", "created_modified_set_exact")
        exact_keys(flags, flag_names, "functional evidence")
        require(all(type(value) is bool for value in flags.values()), "functional flag types")
        exact_keys(row["control"], ("required", "actual", "identity_valid"), "control")
        required = {"cell_id": history + ".short." + arm, "completed": True}
        require(row["control"]["required"] == required, "required synthetic control")
        available = row["terms"] is not None
        require(type(row["artifact_available"]) is bool and row["artifact_available"] == available, "artifact availability")
        if available:
            artifact_count += 1
            raw = decode_blob(row["terms"], "terms")
            require(isinstance(decode(raw), dict), "terms JSON object")
            exact_keys(row["control"]["actual"], ("cell_id", "completed"), "actual control")
            require(isinstance(row["control"]["actual"]["cell_id"], str) and type(row["control"]["actual"]["completed"]) is bool, "actual control types")
            identity = row["control"]["actual"] == required
            require(row["control"]["identity_valid"] is identity, "control identity flag")
            control_failures += not identity
            require(all(flags.values()), "artifact admission evidence")
            full = all(flags.values()) and identity
            require(row["format_failure"] is None, "available artifact format")
            exact_keys(row["readers"], ("A", "B"), "reader lanes")
            require(re.fullmatch(r"[0-9a-f]{64}", row["projection_sha256"]) is not None, "projection digest")
            left = verdict(row["readers"]["A"], row["terms"]["sha256"], row["projection_sha256"])
            right = verdict(row["readers"]["B"], row["terms"]["sha256"], row["projection_sha256"])
            verdict_count += 2
            agreements += left["success"] == right["success"] and left["critical_violation"] == right["critical_violation"]
        else:
            full = False
            require(row["control"]["actual"] is None and row["control"]["identity_valid"] is None, "absent control")
            require(row["readers"] == {"A": None, "B": None} and row["projection_sha256"] is None, "unjudged missing artifact")
            exact_keys(row["format_failure"], ("kind", "description", "writes"), "format failure")
            require(row["format_failure"]["kind"] == "invalid_JSON" and row["format_failure"]["writes"] == 0, "invalid JSON disposition")
            format_failures += 1
            left = right = None
        require(type(row["functional_gate"]) is bool and row["functional_gate"] is full, "functional gate")
        got_primary = reconcile(full, left, right)
        got_secondary = reconcile(available, left, right)
        require(row["primary"] == got_primary, "per-case primary parity")
        require(row["secondary_posthoc"] == got_secondary, "per-case secondary parity")
        primary[arm][label(got_primary["success"])] += 1
        secondary[arm][label(got_secondary["success"])] += 1
        groups[group][arm] = got_primary["success"]

        counts = row["usage"]
        exact_keys(counts, ("prompt_tokens", "completion_tokens", "cached_tokens", "cache_write_tokens", "reasoning_tokens", "total_tokens"), "usage")
        require(all(type(n) is int and n >= 0 for n in counts.values()), "usage integer counts")
        require(counts["prompt_tokens"] + counts["completion_tokens"] == counts["total_tokens"], "usage total")
        ordinary = counts["prompt_tokens"] - counts["cached_tokens"] - counts["cache_write_tokens"]
        require(ordinary >= 0 and counts["reasoning_tokens"] <= counts["completion_tokens"], "usage categories")
        usage[arm].update(counts)
        costs[arm] += (Decimal(ordinary) * Decimal(prices["uncached_input"]) + Decimal(counts["cache_write_tokens"]) * Decimal(prices["cache_write_30m_input"]) + Decimal(counts["cached_tokens"]) * Decimal(prices["cached_input"]) + Decimal(counts["completion_tokens"]) * Decimal(prices["output"])) / Decimal(1000000)

    require(len(groups) == 96 and all(set(pair) == {"M", "L"} for pair in groups.values()), "96 complete pairs")
    followup = evidence["retrieval_followup"]
    exact_keys(followup, ("scope", "source_sha256", "cases"), "retrieval follow-up")
    require(followup["source_sha256"] == pins["Isolated retrieval follow-up"]["sha256"], "follow-up source pin")
    require(len(followup["cases"]) == 9, "nine follow-up cases")
    by_id = {row["case_id"]: row for row in cases}
    followed_ids = set()
    for measured in followup["cases"]:
        exact_keys(measured, ("case_id", "required_source_id", "eligible", "candidate_rank", "eligible_candidates_before", "candidate_count", "top_k", "max_context_chars", "context_chars", "selected_source_ids", "packet_items_parity", "packet_context_parity"), "follow-up case")
        case_id = measured["case_id"]
        require(case_id in by_id and case_id not in followed_ids, "unique follow-up case")
        followed_ids.add(case_id)
        source = by_id[case_id]
        require(source["arm"] == "M" and source["question_id"] == "Q2", "follow-up case scope")
        require(measured["required_source_id"] in {fact["source_id"] for fact in source["expected_source_facts"]}, "follow-up required fact")
        require(measured["eligible"] is True and measured["packet_items_parity"] is True and measured["packet_context_parity"] is True, "follow-up observed parity")
        selected = [item["source_id"] for item in source["retrieved_items"]]
        require(measured["selected_source_ids"] == selected and measured["required_source_id"] not in selected, "follow-up selected packet parity")
        require(measured["candidate_count"] == source["retrieval_counts"]["candidate_count"], "follow-up candidate count parity")
        require(measured["context_chars"] == source["retrieval_counts"]["context_chars"], "follow-up context parity")
        require(measured["top_k"] == 5 and len(selected) == 5 and measured["context_chars"] < measured["max_context_chars"] == 2000, "follow-up selection bounds")
        require(5 <= measured["eligible_candidates_before"] < measured["candidate_rank"] <= measured["candidate_count"], "follow-up rank beyond cutoff")
    pair_counts = collections.Counter(pair_outcome(pair["M"], pair["L"]) for pair in groups.values())
    zero_counts = lambda counter, keys: {key: counter.get(key, 0) for key in keys}
    summary = {
        "cases": 192,
        "paired_questions": 96,
        "primary": {arm: zero_counts(primary[arm], ("success", "failure", "unknown")) for arm in ("M", "L")},
        "secondary_posthoc": {arm: zero_counts(secondary[arm], ("success", "failure", "unknown")) for arm in ("M", "L")},
        "pairs": zero_counts(pair_counts, ("gain", "loss", "tie_success", "tie_failure", "unknown")),
        "artifacts": artifact_count,
        "control_identity_failures": control_failures,
        "invalid_JSON_without_artifact": format_failures,
        "reader_judgments": verdict_count,
        "reader_agreements": agreements,
        "required_fact_coverage": coverage,
        "usage_by_arm": {arm: dict(usage[arm]) for arm in ("M", "L")},
        "generation_estimated_USD_by_arm": {arm: format(costs[arm], ".9f") for arm in ("M", "L")},
        "generation_estimated_USD": format(sum(costs.values()), ".9f"),
        "generation_estimated_USD_per_primary_success": {arm: format(costs[arm] / primary[arm]["success"], ".9f") for arm in ("M", "L")},
        "retrieval_followup": {"cases": 9, "candidate_rank_min": min(x["candidate_rank"] for x in followup["cases"]), "candidate_rank_max": max(x["candidate_rank"] for x in followup["cases"]), "top_k": 5, "all_selected_packets_match": True},
    }
    require(summary == result["expected_recomputation"], "aggregate result parity")
    return {"passed": True, "verification": "published bytes, agreed reader decisions, functional flags, counts and tariff arithmetic", "summary": summary}


if __name__ == "__main__":
    try:
        base = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).parent
        require(len(sys.argv) <= 2, "usage: python verify_pilot.py [bundle_directory]")
        print(json.dumps(verify(base), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
