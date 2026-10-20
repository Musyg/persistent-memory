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
CORE_SHA256 = "5ad093031bb061360c616ed44ab321499f3765b7e887928d073ee20ed6a37bb0"
WORKSPACE = "portfolio-atlas"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(directory):
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
        WORKSPACE, "atlas-deadline", "Projet Atlas : livraison vendredi."
    )["ref"]
    control = memory.register_source(
        WORKSPACE, "atlas-language", "Projet Atlas : langue de communication française."
    )["ref"]
    first_reads = {"date_v1": memory.read(date_v1), "control": memory.read(control)}
    checked("initial_sources_allowed", all(item["allowed"] for item in first_reads.values()))
    record("admit", ["register_source", "read"],
           {"date_v1": date_v1, "control": control}, first_reads)

    def make_brief(date_ref, date_read, language_read, expected_version=None):
        return memory.derive(
            WORKSPACE, "atlas-brief",
            "Brief Atlas — " + date_read["content"] + " " + language_read["content"],
            "task",
            [{"ref": date_ref, "relation": "derives"},
             {"ref": control, "relation": "derives"}],
            memory.checkpoint()["epoch"],
            expected_version=expected_version,
        )["ref"]

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

    date_v2 = memory.register_source(
        WORKSPACE, "atlas-deadline", "Projet Atlas : livraison lundi.",
        expected_version=date_v1["version_id"],
    )["ref"]
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
    brief_v2 = make_brief(date_v2, corrected_reads["date_v2"],
                          corrected_reads["control"], brief_v1["version_id"])
    corrected_reads["brief_v2"] = memory.read(brief_v2)
    memory = Memory.open(root / "content.db", Authority.open(authority.path, authority.anchor_path))
    corrected_reads["reopened_brief"] = memory.read(brief_v2)
    checked("corrected_brief_allowed_after_storage_reopen",
            corrected_reads["brief_v2"]["allowed"] and corrected_reads["reopened_brief"]["allowed"])
    backup_receipt = memory.backup(root / "old-content.db")
    record("correct", ["register_source", "read", "derive", "open", "backup", "explain_artifact"],
           {"date_v1": date_v1, "date_v2": date_v2, "control": control,
            "brief_v1": brief_v1, "brief_v2": brief_v2}, corrected_reads,
           {"expected_version": date_v1["version_id"], "storage_reopened": True,
            "backup_quarantined": backup_receipt["quarantined"],
            "backup_checkpoint": backup_receipt["checkpoint"]},
           memory.explain_artifact(brief_v2))

    withdrawal = memory.revoke_source(WORKSPACE, "atlas-deadline", "atlas-withdraw-deadline")
    withdrawn_reads = {"date_v2": memory.read(date_v2),
                       "brief_v2": memory.read(brief_v2), "control": memory.read(control)}
    checked("withdrawn_date_denied", not withdrawn_reads["date_v2"]["allowed"])
    checked("dependent_brief_denied", not withdrawn_reads["brief_v2"]["allowed"])
    checked("independent_control_preserved", withdrawn_reads["control"]["allowed"])
    record("revoke", ["revoke_source", "read", "explain_artifact"],
           {"date_v2": date_v2, "control": control, "brief_v2": brief_v2},
           withdrawn_reads, {"withdrawal": withdrawal}, memory.explain_artifact(brief_v2))

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
    record("restore", ["open", "read", "restore_verify", "explain_artifact"],
           {"date_v1": date_v1, "date_v2": date_v2, "control": control, "brief_v2": brief_v2},
           restored_reads, {"retained_current_authority": True, "restoration": restoration},
           restored.explain_artifact(brief_v2))

    return {
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, help="New disposable state directory")
    parser.add_argument("--output", required=True, help="New trace JSON file; never overwritten")
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Trace output already exists.")
    if not output.parent.is_dir():
        raise FileNotFoundError("Trace output parent directory must exist.")
    trace = run(args.directory)
    encoded = (json.dumps(trace, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with output.open("xb") as target:
        target.write(encoded)
        target.flush()
        os.fsync(target.fileno())
    print(json.dumps({"schema": trace["schema"], "events": len(trace["events"]),
                      "all_assertions": all(trace["assertions"].values()),
                      "trace_sha256": sha256(encoded)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
