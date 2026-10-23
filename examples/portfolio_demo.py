"""Capture a synthetic five-step demonstration using the installed public core.

This is an application example, not a second memory engine or an AI benchmark.
Run on Linux with hermes-memory-core 0.3.0a2 installed. All state is disposable.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys

import hermes_memory.core as core
from hermes_memory import Authority, Memory


BASE_COMMIT = "c2546be8abb05aadd518fb143d040cec0c4769a9"
CORE_SHA256 = "35dd711acb3dd16e97237721b7332a73b4d4822a88c227fc445722256cd5cecb"
WORKSPACE = "portfolio-atlas"
FIXTURE = {
    "date_v1": "Projet Atlas : livraison vendredi.",
    "date_v2": "Projet Atlas : livraison lundi.",
    "language": "Projet Atlas : langue de communication française.",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class SimpleCache:
    """Illustrative key-value cache; dependency inputs are logged, not tracked."""

    def __init__(self):
        self.state = {}
        self.receipts = []
        self.phase = "admit"

    def receipt(self, operation, inputs, result):
        self.receipts.append({
            "id": len(self.receipts) + 1,
            "phase": self.phase,
            "operation": operation,
            "inputs": inputs,
            "result": result,
            "state_sha256": sha256(canonical(self.state)),
        })
        return result

    def put(self, key, content, dependencies=None):
        previous = self.state.get(key)
        self.state[key] = content
        return self.receipt("put", {"key": key, "content": content,
                                   "declared_dependencies": dependencies or []},
                            {"replaced": previous is not None})

    def read(self, key):
        result = {"allowed": key in self.state,
                  "reason": "cache_hit" if key in self.state else "cache_miss"}
        if key in self.state:
            result["content"] = self.state[key]
        return self.receipt("read", {"key": key}, result)

    def reads(self):
        return {"date": self.read("atlas-deadline"),
                "brief": self.read("atlas-brief"),
                "language": self.read("atlas-language")}

    def remove(self, key):
        existed = key in self.state
        self.state.pop(key, None)
        return self.receipt("remove", {"key": key}, {"removed": existed})

    def backup(self, path):
        encoded = canonical(self.state)
        with path.open("xb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        return self.receipt("backup", {}, {"content_sha256": sha256(encoded)})

    def restore(self, path):
        encoded = path.read_bytes()
        self.state = json.loads(encoded)
        return self.receipt("restore", {}, {"content_sha256": sha256(encoded)})


def run(directory, compare=False):
    """Return actual operation receipts; never overwrite an existing state dir."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("This example is qualified for Linux only.")
    package_version = version("hermes-memory-core")
    module_digest = sha256(Path(core.__file__).read_bytes())
    if package_version != "0.3.0a2" or module_digest != CORE_SHA256:
        raise RuntimeError("Expected the pinned public hermes-memory-core 0.3.0a2.")

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    authority = Authority.create(
        root / "retained-authority" / "authority.db",
        root / "retained-witness" / "checkpoint.json",
    )
    memory = Memory.create(root / "content.db", authority)
    events = []
    assertions = {}
    reference = SimpleCache() if compare else None
    cases = []
    comparison_assertions = {}

    def compared(name, condition):
        comparison_assertions[name] = bool(condition)
        if not condition:
            raise RuntimeError("Comparison invariant failed: " + name)

    def checked(name, condition):
        assertions[name] = bool(condition)
        if not condition:
            raise RuntimeError("Demonstration invariant failed: " + name)

    def record(phase, operations, refs, reads, details=None, provenance=None):
        events.append({
            "id": len(events) + 1,
            "phase": phase,
            "operations": operations,
            "refs": refs,
            "reads": reads,
            "details": details or {},
            "provenance": provenance,
        })

    date_v1 = memory.register_source(
        WORKSPACE, "atlas-deadline", FIXTURE["date_v1"]
    )["ref"]
    control = memory.register_source(
        WORKSPACE, "atlas-language", FIXTURE["language"]
    )["ref"]
    if reference is not None:
        reference.put("atlas-deadline", FIXTURE["date_v1"])
        reference.put("atlas-language", FIXTURE["language"])
    first_reads = {"date_v1": memory.read(date_v1), "control": memory.read(control)}
    checked("initial_sources_allowed", all(item["allowed"] for item in first_reads.values()))
    record("admit", ["register_source", "read"],
           {"date_v1": date_v1, "control": control}, first_reads)

    def make_brief(date_ref, date_read, language_read, expected_version=None):
        content = "Brief Atlas — " + date_read["content"] + " " + language_read["content"]
        dependencies = [{"ref": date_ref, "relation": "derives"},
                        {"ref": control, "relation": "derives"}]
        result = memory.derive(
            WORKSPACE, "atlas-brief",
            content, "task", dependencies,
            memory.checkpoint()["epoch"],
            expected_version=expected_version,
        )["ref"]
        if reference is not None:
            inputs = reference.reads()
            compared("same_brief_inputs_" + reference.phase,
                     inputs["date"].get("content") == date_read["content"]
                     and inputs["language"].get("content") == language_read["content"])
            reference.put("atlas-brief", content, dependencies)
        return result

    if reference is not None:
        reference.phase = "derive"
    brief_v1 = make_brief(date_v1, first_reads["date_v1"], first_reads["control"])
    brief_read = memory.read(brief_v1)
    graph_v1 = memory.explain_artifact(brief_v1)
    root_node = next(node for node in graph_v1["nodes"] if node["ref"] == brief_v1)
    checked("initial_brief_allowed", brief_read["allowed"])
    checked("initial_exact_dependencies", root_node["dependencies"] == [
        {"ref": date_v1, "relation": "derives"},
        {"ref": control, "relation": "derives"},
    ])
    record("derive", ["derive", "read", "explain_artifact"],
           {"date_v1": date_v1, "control": control, "brief_v1": brief_v1},
           {"brief_v1": brief_read}, provenance=graph_v1)

    if reference is not None:
        reference.phase = "correct"
    date_v2 = memory.register_source(
        WORKSPACE, "atlas-deadline", FIXTURE["date_v2"],
        expected_version=date_v1["version_id"],
    )["ref"]
    if reference is not None:
        reference.put("atlas-deadline", FIXTURE["date_v2"])
    corrected_reads = {
        "old_date": memory.read(date_v1),
        # Observe before replacing the brief: the parent update invalidates it.
        "old_brief_before_replacement": memory.read(brief_v1),
        "date_v2": memory.read(date_v2),
        "control": memory.read(control),
    }
    checked("correction_new_version", date_v1["version_id"] != date_v2["version_id"])
    checked("old_date_denied", not corrected_reads["old_date"]["allowed"])
    checked("old_brief_denied_before_replacement",
            not corrected_reads["old_brief_before_replacement"]["allowed"])
    checked("corrected_date_and_control_allowed",
            corrected_reads["date_v2"]["allowed"] and corrected_reads["control"]["allowed"])
    if reference is not None:
        reference_before_rebuild = reference.reads()
    brief_v2 = make_brief(date_v2, corrected_reads["date_v2"],
                          corrected_reads["control"], brief_v1["version_id"])
    corrected_reads["brief_v2"] = memory.read(brief_v2)
    memory = Memory.open(root / "content.db", Authority.open(authority.path, authority.anchor_path))
    corrected_reads["reopened_brief"] = memory.read(brief_v2)
    checked("corrected_brief_allowed_after_storage_reopen",
            corrected_reads["brief_v2"]["allowed"] and corrected_reads["reopened_brief"]["allowed"])
    backup_receipt = memory.backup(root / "old-content.db")
    if reference is not None:
        reference_after_rebuild = reference.reads()
        reference.backup(root / "old-cache.json")
        compared("cache_old_brief_readable_before_rebuild",
                 reference_before_rebuild["brief"]["allowed"]
                 and reference_before_rebuild["brief"].get("content") == brief_read["content"])
        compared("core_old_brief_denied_before_rebuild",
                 not corrected_reads["old_brief_before_replacement"]["allowed"])
        compared("both_briefs_correct_after_rebuild",
                 reference_after_rebuild["brief"]["allowed"]
                 and corrected_reads["brief_v2"]["allowed"]
                 and reference_after_rebuild["brief"].get("content") == corrected_reads["brief_v2"]["content"])
        cases.append({"phase": "correct", "reference": {
            "before_rebuild": reference_before_rebuild,
            "after_rebuild": reference_after_rebuild}, "persistent_memory": {
                "event_id": 3, "before_rebuild": {
                    "date": corrected_reads["date_v2"],
                    "brief": corrected_reads["old_brief_before_replacement"],
                    "language": corrected_reads["control"]}, "after_rebuild": {
                    "date": corrected_reads["date_v2"], "brief": corrected_reads["brief_v2"],
                    "language": corrected_reads["control"]}}})
    record("correct", ["register_source", "read", "derive", "open", "backup", "explain_artifact"],
           {"date_v1": date_v1, "date_v2": date_v2, "control": control,
            "brief_v1": brief_v1, "brief_v2": brief_v2}, corrected_reads,
           {"expected_version": date_v1["version_id"], "storage_reopened": True,
            "backup_quarantined": backup_receipt["quarantined"],
            "backup_checkpoint": backup_receipt["checkpoint"]},
           memory.explain_artifact(brief_v2))

    if reference is not None:
        reference.phase = "revoke"
    withdrawal = memory.revoke_source(WORKSPACE, "atlas-deadline", "atlas-withdraw-deadline")
    if reference is not None:
        reference.remove("atlas-deadline")
    withdrawn_reads = {"date_v2": memory.read(date_v2),
                       "brief_v2": memory.read(brief_v2), "control": memory.read(control)}
    checked("withdrawn_date_denied", not withdrawn_reads["date_v2"]["allowed"])
    checked("dependent_brief_denied", not withdrawn_reads["brief_v2"]["allowed"])
    checked("independent_control_preserved", withdrawn_reads["control"]["allowed"])
    if reference is not None:
        reference_withdrawn = reference.reads()
        compared("cache_source_removed", not reference_withdrawn["date"]["allowed"])
        compared("cache_brief_retained_after_source_removal",
                 reference_withdrawn["brief"]["allowed"]
                 and reference_withdrawn["brief"].get("content") == corrected_reads["brief_v2"]["content"])
        compared("core_dependent_brief_denied_after_withdrawal", not withdrawn_reads["brief_v2"]["allowed"])
        cases.append({"phase": "revoke", "reference": {"after": reference_withdrawn},
                      "persistent_memory": {"event_id": 4, "after": {
                          "date": withdrawn_reads["date_v2"], "brief": withdrawn_reads["brief_v2"],
                          "language": withdrawn_reads["control"]}}})
    record("revoke", ["revoke_source", "read", "explain_artifact"],
           {"date_v2": date_v2, "control": control, "brief_v2": brief_v2},
           withdrawn_reads, {"withdrawal": withdrawal}, memory.explain_artifact(brief_v2))

    if reference is not None:
        reference.phase = "restore"
        reference.restore(root / "old-cache.json")
    restored = Memory.open(root / "old-content.db", memory.authority)
    quarantined = restored.read(control)
    checked("old_content_restore_denied_before_verification", not quarantined["allowed"])
    restoration = restored.restore_verify(memory.authority.checkpoint())
    restored_reads = {
        "quarantined_control": quarantined,
        "date_v1": restored.read(date_v1),
        "date_v2": restored.read(date_v2),
        "brief_v2": restored.read(brief_v2),
        "control": restored.read(control),
    }
    checked("old_and_current_withdrawn_versions_stay_denied",
            not restored_reads["date_v1"]["allowed"] and not restored_reads["date_v2"]["allowed"])
    checked("restored_dependent_brief_stays_denied", not restored_reads["brief_v2"]["allowed"])
    checked("restored_independent_control_allowed", restored_reads["control"]["allowed"])
    checked("no_missing_current_content", restoration["missing_current_content"] == [])
    if reference is not None:
        reference_restored = reference.reads()
        compared("cache_snapshot_restores_date_and_brief",
                 reference_restored["date"]["allowed"] and reference_restored["brief"]["allowed"]
                 and reference_restored["date"].get("content") == FIXTURE["date_v2"]
                 and reference_restored["brief"].get("content") == corrected_reads["brief_v2"]["content"])
        compared("core_restored_date_and_brief_denied",
                 not restored_reads["date_v2"]["allowed"] and not restored_reads["brief_v2"]["allowed"])
        compared("both_keep_independent_language",
                 all(reads["language"]["allowed"] and reads["language"].get("content") == FIXTURE["language"]
                     for reads in [reference_before_rebuild, reference_after_rebuild,
                                   reference_withdrawn, reference_restored])
                 and withdrawn_reads["control"]["allowed"] and restored_reads["control"]["allowed"])
        cases.append({"phase": "restore", "reference": {"after": reference_restored},
                      "persistent_memory": {"event_id": 5,
                          "before_verification": {"language": quarantined}, "after": {
                              "date": restored_reads["date_v2"], "brief": restored_reads["brief_v2"],
                              "language": restored_reads["control"]}}})
    record("restore", ["open", "read", "restore_verify", "explain_artifact"],
           {"date_v1": date_v1, "date_v2": date_v2, "control": control, "brief_v2": brief_v2},
           restored_reads, {"retained_current_authority": True, "restoration": restoration},
           restored.explain_artifact(brief_v2))

    trace = {
        "schema": "persistent-memory.portfolio-demo.trace.v1",
        "scenario": "project-atlas-deadline-v1",
        "synthetic": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provenance": {
            "base_commit": BASE_COMMIT,
            "package": "hermes-memory-core",
            "installed_version": package_version,
            "script_sha256": sha256(Path(__file__).read_bytes()),
            "modules": {"core.py": module_digest},
        },
        "events": events,
        "assertions": assertions,
        "boundaries": [
            "synthetic_application_example_without_model_or_network_calls",
            "storage_reopen_not_process_or_hardware_crash_simulation",
            "known_declared_dependencies_only",
            "current_authority_and_freshness_witness_retained_outside_content_backup",
            "coordinated_authority_and_witness_rollback_not_covered",
            "logical_read_revocation_not_physical_erasure_or_model_unlearning",
            "recorded_run_not_a_reliability_or_latency_benchmark",
        ],
    }
    if reference is None:
        return trace
    return {
        "schema": "persistent-memory.portfolio-demo.comparison.v1",
        "scenario": trace["scenario"], "synthetic": True,
        "generated_at_utc": trace["generated_at_utc"],
        "core_trace": trace,
        "reference": {
            "contract": {
                "name": "key-value-cache-without-dependency-tracking",
                "writes": "replace_the_addressed_key_only",
                "briefs": "application_stores_the_same_explicitly_rebuilt_text_as_the_core",
                "dependencies": "received_in_operation_receipts_but_not_stored_or_revalidated",
                "withdrawal": "remove_the_addressed_source_key_only",
                "recovery": "restore_all_cache_content_from_its_pre_withdrawal_json_snapshot",
                "storage": "in_process_dictionary_with_real_json_snapshot_and_restore",
                "authority": "no_separate_revocation_authority_or_freshness_witness",
            },
            "receipts": reference.receipts,
            "final_state_sha256": sha256(canonical(reference.state)),
        },
        "shared_inputs": FIXTURE,
        "cases": cases,
        "assertions": comparison_assertions,
        "provenance": {
            "fixture_sha256": sha256(canonical(FIXTURE)),
            "example_script_sha256": trace["provenance"]["script_sha256"],
            "reference_receipts_sha256": sha256(canonical(reference.receipts)),
        },
        "boundaries": trace["boundaries"] + [
            "illustrative_reference_contract_not_a_competitor_or_all_rag_systems",
            "both_receive_same_source_facts_explicit_brief_rebuild_withdrawal_and_content_restore",
            "core_retains_current_authority_and_witness_separately_reference_has_neither_by_contract",
            "cache_can_be_made_correct_by_explicit_rebuild_or_invalidation",
            "no_performance_durability_or_model_quality_comparison",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, help="New disposable state directory")
    parser.add_argument("--output", required=True, help="New trace JSON file; never overwritten")
    parser.add_argument("--compare", action="store_true",
                        help="Also execute the explicitly defined key-value cache reference")
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Trace output already exists.")
    if not output.parent.is_dir():
        raise FileNotFoundError("Trace output parent directory must exist.")
    trace = run(args.directory, compare=args.compare)
    encoded = (json.dumps(trace, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with output.open("xb") as target:
        target.write(encoded)
        target.flush()
        os.fsync(target.fileno())
    core_trace = trace.get("core_trace", trace)
    summary = {"schema": trace["schema"], "events": len(core_trace["events"]),
               "all_assertions": all(trace["assertions"].values())
               and all(core_trace["assertions"].values()),
               "trace_sha256": sha256(encoded)}
    if args.compare:
        summary["cases"] = len(trace["cases"])
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
