"""Import existing synthetic measurements; never executes a retrieval policy."""
import argparse
import hashlib
import json
from pathlib import Path

from .registry import Registry, PolicyError, identity, load_learning_records, require


def pilot(records_source, r3_report_path, r4_report_path, output):
    records = load_learning_records(records_source)
    records_source = Path(records.__file__)
    raw3, raw4 = Path(r3_report_path).read_bytes(), Path(r4_report_path).read_bytes()
    r3, r4 = json.loads(raw3), json.loads(raw4)
    require(r3.get("learning_records_sha256") == hashlib.sha256(Path(records_source).read_bytes()).hexdigest(), "run_contract_source_mismatch")
    require(r3["typed_sha256"] == r4["r3_sha256"] and r3["dataset_sha256"] == r4["dataset_sha256"], "reports_not_same_policy_or_dataset")
    selected = [run for run in r3["runs"] if run["policy"]["id"] == "typed_fts_budgeted"]
    require(selected and all(run["split"] == "development" for run in selected), "development_runs_required")
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    output.chmod(0o700)
    safety = identity({"current_authority_required": True, "authorization_changes": False, "runtime_activation": "external_operator_only"})
    admission_protocol = {"schema_version": 1, "family": "retrieval", "safety_contract_ref": safety, "judge": selected[0]["records"]["evaluation"]["judge"], "rubric_refs": sorted({run["records"]["evaluation"]["rubric_ref"] for run in selected}), "min_observed": len(selected), "min_success_rate": .8, "max_unobserved": 0, "max_p95_ratio": 1.2}
    registry = Registry.create(output / "registry.sqlite", records, admission_protocol)
    report3_ref, report4_ref = registry.add_report(r3), registry.add_report(r4)
    artifacts, decisions = {}, {}
    for label, code_ref, executions in (("r3", r3["typed_sha256"], sorted({run["records"]["experience"]["policy_ref"] for run in selected})), ("r4", r4["r4_sha256"], [])):
        payload = {"schema_version": 1, "family": "retrieval", "name": "typed-retrieval-" + label, "implementation_ref": "sha256:" + code_ref, "configuration_ref": identity({"schema": "execution-policy-set-v1", "policy_refs": executions}), "safety_contract_ref": safety, "execution_policy_refs": executions, "dependencies": [report4_ref]}
        proposed = registry.propose(payload)
        artifacts[label] = proposed["policy_ref"]
        links = [{"report_ref": report3_ref, "run_id": run["run_id"]} for run in selected] if label == "r3" else []
        assessed = registry.evaluate_retrieval_reports(proposed["policy_ref"], links, report4_ref, "typed_" + label, proposed["seq"])
        try:
            # None is deliberate: this offline pilot has no fresh fleet authority
            # validator. Even an otherwise eligible candidate cannot activate.
            registry.admit(proposed["policy_ref"], assessed["seq"], None)
        except PolicyError as exc:
            admission = {"admitted": False, "reason": str(exc)}
        else:
            raise PolicyError("unexpected_pilot_admission")
        decisions[label] = {"registry": registry.inspect(proposed["policy_ref"]), "admission": admission}
    result = {"schema_version": 1, "kind": "policy_registry_replay_of_measured_retrieval_evidence", "input_bytes_sha256": {"r3": hashlib.sha256(raw3).hexdigest(), "r4": hashlib.sha256(raw4).hexdigest(), "learning_records": hashlib.sha256(Path(records_source).read_bytes()).hexdigest()}, "canonical_report_refs": {"r3": report3_ref, "r4": report4_ref}, "protocol_ref": registry.protocol_ref, "artifacts": artifacts, "decisions": decisions, "new_retrieval_runs": 0, "provider_calls": 0, "production_changed": False, "runtime_activated": False, "limits": ["R4 quality records were not invented from R3 parity", "R3 labels and cost measurements remain development evidence", "Admission registry is not permission or deployment", "Source revalidation against fleet authority is not installed"]}
    result["limits"].append("min_success_rate=0.8 is a diagnostic registry parameter chosen after DEV, not a preregistered independent validation threshold")
    (output / "pilot.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning-records", help="Optional exact contract override; bundled contract is the default")
    actions = parser.add_subparsers(dest="action", required=True)
    run = actions.add_parser("pilot")
    run.add_argument("--r3-report", required=True)
    run.add_argument("--r4-report", required=True)
    run.add_argument("--output", required=True)
    inspect = actions.add_parser("inspect")
    inspect.add_argument("--registry", required=True)
    inspect.add_argument("--policy-ref", required=True)
    args = parser.parse_args(argv)
    if args.action == "pilot":
        result = pilot(args.learning_records, args.r3_report, args.r4_report, args.output)
        print(json.dumps({"artifacts": result["artifacts"], "admission": {key: value["admission"] for key, value in result["decisions"].items()}, "new_retrieval_runs": 0}))
    else:
        registry = Registry(args.registry, load_learning_records(args.learning_records))
        print(json.dumps(registry.inspect(args.policy_ref), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
