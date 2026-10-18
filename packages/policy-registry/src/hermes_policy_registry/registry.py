"""Stdlib immutable policy registry. Trusted local filesystem; no deployment API."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import sys

RECORDS_SHA = "3dd069650457f2ecb7ddacf13c7cba8a7b76ef459d8bb6228d699b16fa7c720e"
FAMILIES = {"prompt", "retrieval", "routing", "workflow", "skill"}


class PolicyError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PolicyError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def identity(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def raw_identity(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def is_ref(value):
    return type(value) is str and len(value) == 71 and value.startswith("sha256:") and all(c in "0123456789abcdef" for c in value[7:])


def load_learning_records(path=None):
    path = Path(path) if path is not None else Path(__file__).parent / "contracts" / "learning_records.py"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == RECORDS_SHA, "learning_contract_hash_mismatch")
    spec = importlib.util.spec_from_file_location("hermes_policy_pinned_learning_records", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def artifact(value):
    require(type(value) is dict and set(value) == {"schema_version", "family", "name", "implementation_ref", "configuration_ref", "safety_contract_ref", "execution_policy_refs", "dependencies"}, "invalid_artifact_fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "invalid_artifact_version")
    require(type(value["family"]) is str and value["family"] in FAMILIES and type(value["name"]) is str and 0 < len(value["name"]) <= 128, "invalid_artifact_identity")
    require(all(is_ref(value[key]) for key in ("implementation_ref", "configuration_ref", "safety_contract_ref")), "immutable_artifact_reference_required")
    for key in ("execution_policy_refs", "dependencies"):
        refs = value[key]
        require(type(refs) is list and len(refs) <= 256 and all(is_ref(ref) for ref in refs) and len(set(refs)) == len(refs), "invalid_artifact_dependencies")
    require(value["configuration_ref"] == identity({"schema": "execution-policy-set-v1", "policy_refs": sorted(value["execution_policy_refs"])}), "configuration_execution_set_mismatch")
    return value


def protocol(value):
    require(type(value) is dict and set(value) == {"schema_version", "family", "safety_contract_ref", "judge", "rubric_refs", "min_observed", "min_success_rate", "max_unobserved", "max_p95_ratio"}, "invalid_protocol_fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1 and type(value["family"]) is str and value["family"] in FAMILIES and is_ref(value["safety_contract_ref"]), "invalid_protocol_identity")
    require(type(value["judge"]) is dict and set(value["judge"]) == {"kind", "identifier", "revision"} and all(type(v) is str and v for v in value["judge"].values()), "invalid_protocol_judge")
    require(type(value["rubric_refs"]) is list and len(value["rubric_refs"]) <= 256 and all(is_ref(ref) for ref in value["rubric_refs"]), "invalid_protocol_rubrics")
    require(type(value["min_observed"]) is int and value["min_observed"] > 0 and type(value["max_unobserved"]) is int and value["max_unobserved"] >= 0, "invalid_protocol_count")
    require(type(value["min_success_rate"]) in {int, float} and 0 <= value["min_success_rate"] <= 1, "invalid_protocol_rate")
    require(type(value["max_p95_ratio"]) in {int, float} and math.isfinite(value["max_p95_ratio"]) and value["max_p95_ratio"] > 0, "invalid_protocol_cost")
    return value


class Registry:
    def __init__(self, path, records):
        self.path, self.records = Path(path).resolve(), records
        require(self.path.is_file(), "registry_missing")
        with self.transaction() as connection:
            stored = connection.execute("SELECT value FROM meta WHERE key='protocol'").fetchone()
            require(stored is not None, "registry_schema_missing")
            self.protocol = protocol(json.loads(stored[0]))
            self.protocol_ref = identity(self.protocol)

    @classmethod
    def create(cls, path, records, admission_protocol):
        admission_protocol = protocol(admission_protocol)
        path = Path(path).absolute()
        require(path.parent.is_dir() and not path.is_symlink(), "private_parent_required")
        require(path.parent.stat().st_mode & 0o077 == 0, "private_parent_required")
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE objects(ref TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL); CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,policy_ref TEXT NOT NULL,previous INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,event_ref TEXT NOT NULL); CREATE TABLE revoked(ref TEXT PRIMARY KEY,reason TEXT NOT NULL);")
            connection.execute("INSERT INTO meta VALUES ('protocol',?)", (canonical(admission_protocol),))
        return cls(path, records)

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _save(self, connection, kind, value, reference=None):
        payload = canonical(value)
        reference = reference or identity(value)
        old = connection.execute("SELECT kind,payload FROM objects WHERE ref=?", (reference,)).fetchone()
        require(old is None or (old["kind"], old["payload"]) == (kind, payload), "immutable_identity_conflict")
        if old is None:
            connection.execute("INSERT INTO objects VALUES (?,?,?)", (reference, kind, payload))
        return reference

    def _load(self, connection, reference, kind=None):
        row = connection.execute("SELECT kind,payload FROM objects WHERE ref=?", (reference,)).fetchone()
        require(row is not None and (kind is None or row["kind"] == kind), "object_missing_or_wrong_kind")
        value = json.loads(row["payload"])
        computed = self.records.record_id(value) if row["kind"] in {"experience", "evaluation"} else identity(value)
        require(computed == reference, "stored_identity_mismatch")
        if row["kind"] in {"experience", "evaluation"}:
            self.records.validate(value)
        return value

    def _head(self, connection, policy_ref):
        row = connection.execute("SELECT * FROM events WHERE policy_ref=? ORDER BY seq DESC LIMIT 1", (policy_ref,)).fetchone()
        require(row is not None, "policy_not_registered")
        value = json.loads(row["payload"])
        require(identity(value) == row["event_ref"] and value["policy_ref"] == policy_ref and value["state"] == row["state"] and value["previous"] == row["previous"], "event_integrity_mismatch")
        return {"seq": row["seq"], **value}

    def _event(self, connection, policy_ref, state, expected, details):
        last = connection.execute("SELECT seq FROM events WHERE policy_ref=? ORDER BY seq DESC LIMIT 1", (policy_ref,)).fetchone()
        require((last[0] if last else 0) == expected, "stale_policy_state")
        body = {"policy_ref": policy_ref, "state": state, "previous": expected, "details": details}
        cursor = connection.execute("INSERT INTO events(policy_ref,previous,state,payload,event_ref) VALUES (?,?,?,?,?)", (policy_ref, expected, state, canonical(body), identity(body)))
        return {"seq": cursor.lastrowid, **body}

    def propose(self, value):
        value = artifact(value)
        with self.transaction() as connection:
            ref = self._save(connection, "artifact", value)
            if connection.execute("SELECT 1 FROM events WHERE policy_ref=?", (ref,)).fetchone():
                return self._head(connection, ref)
            return self._event(connection, ref, "proposed", 0, {"protocol_ref": self.protocol_ref})

    def add_report(self, report):
        require(type(report) is dict and len(canonical(report).encode("utf-8")) <= 8388608, "bounded_report_required")
        with self.transaction() as connection:
            return self._save(connection, "report", report)

    def add_record(self, record):
        self.records.validate(record)
        with self.transaction() as connection:
            return self._save(connection, record["kind"], record, record["record_id"])

    def _resolve(self, experience, chain, revoked):
        require(all(record["judge"] == self.protocol["judge"] and record["rubric_ref"] in self.protocol["rubric_refs"] for record in chain), "judge_or_rubric_not_admitted")
        try:
            return self.records.resolve(experience, chain, revoked)
        except self.records.ContractError as exc:
            raise PolicyError("invalid_evaluation_chain") from exc

    def _cost(self, connection, policy, report_ref, candidate, datasets, quality_cases):
        report = self._load(connection, report_ref, "report")
        require(report.get("kind") == "r4_serial_development_cost_screen_not_promotion" and candidate in {"typed_r3", "typed_r4"}, "unsupported_cost_adapter")
        dataset = report.get("dataset_sha256")
        require(type(dataset) is str and is_ref("sha256:" + dataset), "cost_dataset_required")
        require(not datasets or datasets == {dataset}, "cost_quality_dataset_mismatch")
        field = "r3_sha256" if candidate == "typed_r3" else "r4_sha256"
        require(policy["implementation_ref"] == "sha256:" + report[field], "cost_policy_mismatch")
        require(report["unchanged_ratio_limit"] == self.protocol["max_p95_ratio"], "cost_protocol_mismatch")
        base = report["summary"]["core_lexical_budgeted"]["wall"]["p95_ms"]
        measured = report["summary"][candidate]["wall"]["p95_ms"]
        require(all(type(v) in {int, float} and math.isfinite(v) and v > 0 for v in (base, measured)), "cost_unavailable")
        paired = []
        for label, claimed in (("core_lexical_budgeted", base), (candidate, measured)):
            rows = [row for row in report["samples"] if row["policy"] == label]
            require(all(row.get("execution_status") == "completed" for row in rows), "cost_execution_unavailable")
            require(all(type(row.get("task_id")) is str and row["task_id"] and type(row.get("repeat")) is int and row["repeat"] >= 0 for row in rows), "cost_case_binding_required")
            keys = {(row["task_id"], row["repeat"]) for row in rows}
            require(len(keys) == len(rows), "duplicate_cost_sample")
            paired.append(keys)
            samples = [row["wall_ns"] for row in rows]
            require(samples and all(type(value) is int and value > 0 for value in samples), "invalid_cost_samples")
            measured_p95 = sorted(samples)[math.ceil(.95 * len(samples)) - 1] / 1e6
            require(measured_p95 == claimed and len(samples) == report["summary"][label]["wall"]["count"], "cost_summary_binding_mismatch")
        require(paired[0] == paired[1] and quality_cases <= {case for case, _ in paired[0]}, "cost_quality_case_mismatch")
        return {"report_ref": report_ref, "candidate": candidate, "baseline_p95_ms": base, "candidate_p95_ms": measured, "p95_ratio": measured / base, "functional_parity_reported": report.get("functional_parity_and_no_mutation") is True and not report.get("failures")}

    def evaluate_retrieval_reports(self, policy_ref, run_links, cost_report_ref, cost_candidate, expected_seq):
        """Explicit G3 report adapter; no generic optimizer/evaluator is claimed."""
        require(type(run_links) is list and len(run_links) <= 256, "bounded_run_links_required")
        with self.transaction() as connection:
            policy = self._load(connection, policy_ref, "artifact")
            require(policy["family"] == "retrieval", "retrieval_report_adapter_required")
            head = self._head(connection, policy_ref)
            require(head["state"] in {"proposed", "evaluated"}, "evaluation_transition_forbidden")
            require(policy["family"] == self.protocol["family"] and policy["safety_contract_ref"] == self.protocol["safety_contract_ref"], "protocol_or_safety_contract_mismatch")
            revoked = {row[0] for row in connection.execute("SELECT ref FROM revoked")}
            resolved, dependencies, seen = [], set(policy["dependencies"]) | {policy_ref, self.protocol_ref, cost_report_ref, policy["implementation_ref"], policy["configuration_ref"], policy["safety_contract_ref"]}, set()
            executed_configs = set()
            seen_experiences, seen_cases, datasets = set(), set(), set()
            for link in run_links:
                require(type(link) is dict and set(link) == {"report_ref", "run_id"} and type(link["run_id"]) is str, "invalid_run_link")
                marker = (link["report_ref"], link["run_id"])
                require(marker not in seen, "duplicate_run")
                seen.add(marker)
                report = self._load(connection, link["report_ref"], "report")
                dataset = report.get("dataset_sha256")
                require(type(dataset) is str and is_ref("sha256:" + dataset), "quality_dataset_required")
                datasets.add(dataset)
                matches = [run for run in report.get("runs", []) if run.get("run_id") == link["run_id"]]
                require(len(matches) == 1, "run_missing_or_ambiguous")
                run = matches[0]
                exp, ev = run["records"]["experience"], run["records"]["evaluation"]
                self.records.validate(exp)
                self.records.validate(ev)
                require(exp["kind"] == "experience" and ev["kind"] == "evaluation" and ev["experience_ref"] == exp["record_id"], "evaluation_experience_binding_mismatch")
                require(exp["record_id"] not in seen_experiences, "duplicate_experience")
                seen_experiences.add(exp["record_id"])
                require(run.get("task_id") == exp["case_id"], "run_case_binding_mismatch")
                case = (dataset, exp["case_id"])
                require(case not in seen_cases, "duplicate_quality_case")
                seen_cases.add(case)
                require(run["outcome"].get("execution_status") in {"completed", "unavailable", "error"}, "execution_status_required")
                require(exp["family"] == policy["family"] and exp["policy_ref"] in policy["execution_policy_refs"] and identity(run["policy"]) == exp["policy_ref"], "executed_policy_binding_mismatch")
                executed_configs.add(exp["policy_ref"])
                require("sha256:" + run["policy"]["implementation_sha256"] == policy["implementation_ref"], "executed_implementation_mismatch")
                require(identity(run["outcome"]) == exp["outcome_ref"] and [identity({"doc_id": name, "ref": reference}) for name, reference in sorted(run["refs"].items())] == exp["source_refs"], "run_lineage_binding_mismatch")
                self._save(connection, "experience", exp, exp["record_id"])
                self._save(connection, "evaluation", ev, ev["record_id"])
                chain = []
                for row in connection.execute("SELECT ref FROM objects WHERE kind='evaluation'"):
                    record = self._load(connection, row[0], "evaluation")
                    if record["experience_ref"] == exp["record_id"]:
                        chain.append(record)
                require(run["outcome"]["execution_status"] == "completed" or all(record["status"] != "observed" for record in chain), "unavailable_execution_observed")
                resolution = self._resolve(exp, chain, revoked)
                latest = next(record for record in chain if record["record_id"] == resolution["latest"])
                dependencies.update({link["report_ref"], exp["record_id"], exp["policy_ref"], exp["outcome_ref"]})
                dependencies.update(exp["source_refs"])
                dependencies.update(record["record_id"] for record in chain)
                dependencies.update(record["rubric_ref"] for record in chain)
                resolved.append({"run_id": link["run_id"], "experience_ref": exp["record_id"], "evaluation_ref": latest["record_id"], "judge": latest["judge"], "rubric_ref": latest["rubric_ref"], "status": latest["status"], "eligible": resolution["success_eligible"], "success": latest["success"], "score": latest["score"], "reason": resolution["reason"]})
            require(executed_configs == set(policy["execution_policy_refs"]), "unevaluated_declared_configuration")
            cost = self._cost(connection, policy, cost_report_ref, cost_candidate, datasets, {case for _, case in seen_cases})
            observed = [row for row in resolved if row["eligible"]]
            successes = sum(row["success"] is True for row in observed)
            unobserved = len(resolved) - len(observed)
            rate = successes / len(observed) if observed else None
            reasons = []
            if len(observed) < self.protocol["min_observed"]:
                reasons.append("insufficient_observed_evidence")
            if unobserved > self.protocol["max_unobserved"]:
                reasons.append("unavailable_or_withdrawn_evidence")
            if rate is not None and rate < self.protocol["min_success_rate"]:
                reasons.append("quality_gate_not_met")
            if cost["p95_ratio"] > self.protocol["max_p95_ratio"]:
                reasons.append("latency_gate_not_met")
            if not cost["functional_parity_reported"]:
                reasons.append("functional_parity_not_reported")
            if dependencies & revoked:
                reasons.append("revoked_dependency")
            assessment = {"policy_ref": policy_ref, "protocol_ref": self.protocol_ref, "runs": resolved, "cost": cost, "observed": len(observed), "unobserved": unobserved, "successes": successes, "success_rate": rate, "reasons": reasons, "eligible_for_admission_review": not reasons, "dependencies": sorted(dependencies), "provenance_authenticated": False, "runtime_activated": False}
            assessment_ref = self._save(connection, "assessment", assessment)
            return self._event(connection, policy_ref, "evaluated", expected_seq, {"assessment_ref": assessment_ref})

    def evaluate_native_effect_reports(self, policy_ref, run_links, cost_report_ref, expected_seq, revalidate):
        """native-effects-v1 assessment only; trusted revalidation is not runtime activation."""
        return self._evaluate_effect_reports(policy_ref, run_links, cost_report_ref, expected_seq, revalidate,
                                             family="retrieval", schema="native-effects-v1")

    def evaluate_workflow_effect_reports(self, policy_ref, run_links, cost_report_ref, expected_seq, revalidate, verify_effect):
        """Assess host-verified workflow effects; never executes or activates a policy."""
        require(callable(verify_effect), "workflow_effect_verifier_required")
        return self._evaluate_effect_reports(policy_ref, run_links, cost_report_ref, expected_seq, revalidate,
                                             family="workflow", schema="native-workflow-effects-v1",
                                             verify_effect=verify_effect)

    def _evaluate_effect_reports(self, policy_ref, run_links, cost_report_ref, expected_seq, revalidate, *, family, schema, verify_effect=None):
        """Shared immutable evidence assessment; never executes or activates a policy."""
        require(type(run_links) is list and 0 < len(run_links) <= 256, "bounded_native_run_links_required")
        require(type(expected_seq) is int and expected_seq >= 0, "native_sequence_required")
        require(self.protocol["family"] == family and self.protocol["judge"] ==
                {"kind": "executable", "identifier": schema, "revision": "1"},
                "native_effects_protocol_required")
        require(cost_report_ref is None or is_ref(cost_report_ref), "native_cost_reference_required")
        with self.transaction() as connection:
            policy = self._load(connection, policy_ref, "artifact")
            head = self._head(connection, policy_ref)
            require(head["state"] in {"proposed", "evaluated"}, "evaluation_transition_forbidden")
            require(policy["family"] == self.protocol["family"] and
                    policy["safety_contract_ref"] == self.protocol["safety_contract_ref"], "protocol_or_safety_contract_mismatch")
            revoked = {row[0] for row in connection.execute("SELECT ref FROM revoked")}
            dependencies = set(policy["dependencies"]) | {policy_ref, self.protocol_ref, policy["implementation_ref"],
                policy["configuration_ref"], policy["safety_contract_ref"]}
            seen_links, seen_experiences, seen_cases, executed, datasets = set(), set(), set(), set(), set()
            resolved, reasons = [], []
            workflow_binding = None
            for link in run_links:
                require(type(link) is dict and set(link) == {"report_ref", "run_id"} and
                        is_ref(link["report_ref"]) and type(link["run_id"]) is str, "invalid_native_run_link")
                marker = (link["report_ref"], link["run_id"])
                require(marker not in seen_links, "duplicate_run")
                seen_links.add(marker)
                report = self._load(connection, link["report_ref"], "report")
                require(report.get("schema") == schema and type(report.get("version")) is int and
                        report["version"] == 1, "native_effects_report_required")
                dataset = report.get("dataset_sha256")
                require(type(dataset) is str and is_ref("sha256:" + dataset), "quality_dataset_required")
                datasets.add(dataset)
                if family == "workflow":
                    rule_ref, oracle_ref = report.get("rule_ref"), report.get("oracle_ref")
                    dataset_ref = "sha256:" + dataset
                    require(is_ref(rule_ref) and is_ref(oracle_ref) and
                            {rule_ref, oracle_ref, dataset_ref} <= set(policy["dependencies"]),
                            "workflow_rule_oracle_dataset_dependencies_required")
                    require(oracle_ref in self.protocol["rubric_refs"], "workflow_oracle_not_admitted")
                    binding = (rule_ref, oracle_ref, dataset_ref)
                    require(workflow_binding is None or workflow_binding == binding, "workflow_report_binding_mismatch")
                    workflow_binding = binding
                    dependencies.update(binding)
                rows = report.get("runs")
                require(type(rows) is list and len(rows) <= 256 and all(type(row) is dict for row in rows),
                        "bounded_native_runs_required")
                matches = [row for row in rows if row.get("run_id") == link["run_id"]]
                require(len(matches) == 1, "run_missing_or_ambiguous")
                run = matches[0]
                require({"run_id", "task_id", "policy", "execution", "outcome", "source_snapshots", "records"} <= set(run)
                        and type(run["policy"]) is dict and type(run["execution"]) is dict and type(run["outcome"]) is dict
                        and type(run["records"]) is dict and set(run["records"]) == {"experience", "evaluation"},
                        "native_run_fields_required")
                exp, ev = run["records"]["experience"], run["records"]["evaluation"]
                self.records.validate(exp); self.records.validate(ev)
                if family == "workflow":
                    require(run.get("rule_ref") == rule_ref and run.get("oracle_ref") == oracle_ref and
                            ev.get("rubric_ref") == oracle_ref, "workflow_run_oracle_binding_mismatch")
                require(exp["kind"] == "experience" and ev["kind"] == "evaluation" and
                        ev["experience_ref"] == exp["record_id"], "evaluation_experience_binding_mismatch")
                require(exp["record_id"] not in seen_experiences, "duplicate_experience")
                seen_experiences.add(exp["record_id"])
                require(run.get("task_id") == exp["case_id"], "run_case_binding_mismatch")
                case = (dataset, exp["case_id"])
                require(case not in seen_cases, "duplicate_quality_case")
                seen_cases.add(case)
                require(exp["family"] == policy["family"] and exp["policy_ref"] in policy["execution_policy_refs"]
                        and identity(run["policy"]) == exp["policy_ref"], "executed_policy_binding_mismatch")
                require(run["execution"] == {"implementation_ref": policy["implementation_ref"],
                        "configuration_ref": policy["configuration_ref"]}, "native_execution_binding_mismatch")
                executed.add(exp["policy_ref"])
                outcome, snapshots = run["outcome"], run["source_snapshots"]
                require(identity(outcome) == exp["outcome_ref"], "native_outcome_identity_mismatch")
                self._save(connection, "report", run["policy"], exp["policy_ref"])
                self._save(connection, "report", outcome, exp["outcome_ref"])
                dependencies.update([exp["policy_ref"], exp["outcome_ref"]])
                require(type(snapshots) is list and len(snapshots) <= 15, "bounded_native_snapshots_required")
                for snapshot in snapshots:
                    require(type(snapshot) is dict and type(snapshot.get("id")) is str and
                            type(snapshot.get("text")) is str and snapshot["text"] and
                            type(snapshot.get("record")) is dict and snapshot["record"] and
                            snapshot["record"].get("fact", snapshot["record"].get("text")) == snapshot["text"],
                            "full_native_source_snapshot_required")
                refs = [identity(snapshot) for snapshot in snapshots]
                require(refs == exp["source_refs"] and len(refs) == len(set(refs)), "native_snapshot_identity_mismatch")
                for snapshot, ref in zip(snapshots, refs):
                    self._save(connection, "report", snapshot, ref)
                dependencies.update(refs)
                require(outcome.get("execution_status") in {"completed", "unavailable", "error"}, "execution_status_required")
                receipt, reopened = outcome.get("consumer_action_observation"), run.get("reopened_effect")
                verified = False
                if type(receipt) is dict:
                    effect = {key: receipt.get(key) for key in ("operation", "arguments", "effect_state")}
                    authority = receipt.get("authority_check")
                    verified = (outcome["execution_status"] == "completed" and receipt.get("phase") == "after_consumption"
                        and receipt.get("status") == "completed" and type(effect["arguments"]) is dict
                        and type(effect["effect_state"]) is dict and type(authority) is dict
                        and authority.get("phase") == "before_consumption"
                        and authority.get("status") in {"current", "withdrawn", "unsupported"}
                        and type(effect["operation"]) is str
                        and (family == "workflow" or effect["operation"] in {"create_work_order", "set_retention_hours", "hold_request", "record_clarification_request"})
                        and (family == "workflow" or authority.get("status") == "current" or effect["operation"] in {"hold_request", "record_clarification_request"})
                        and type(reopened) is dict and reopened == {"phase": "after_independent_reopen", "effect_ref": identity(effect)})
                    if family == "workflow":
                        verified = verified and 0 < len(effect["operation"]) <= 128
                        # Detached JSON prevents a verifier from mutating the imported report.
                        # The host still owns independent reopening, authority and oracle trust.
                        evidence = {"schema": schema, "rule_ref": rule_ref, "oracle_ref": oracle_ref,
                                    "dataset_ref": dataset_ref, "run": run}
                        checked = verify_effect(json.loads(canonical(evidence))) if verified else None
                        verified = (verified and type(checked) is dict and
                            checked == {"status": "verified", "effect_ref": identity(effect),
                                        "rule_ref": rule_ref, "oracle_ref": oracle_ref, "dataset_ref": dataset_ref})
                    effect_ref = self._save(connection, "report", receipt)
                    dependencies.add(effect_ref)
                    if type(reopened) is dict:
                        reopen_ref = self._save(connection, "report", reopened)
                        dependencies.add(reopen_ref)
                if not verified:
                    reasons.append("native_consumed_effect_or_reopen_unverified")
                self._save(connection, "experience", exp, exp["record_id"])
                self._save(connection, "evaluation", ev, ev["record_id"])
                chain = [self._load(connection, row[0], "evaluation") for row in
                         connection.execute("SELECT ref FROM objects WHERE kind='evaluation'")]
                chain = [record for record in chain if record["experience_ref"] == exp["record_id"]]
                require(outcome["execution_status"] == "completed" or all(record["status"] != "observed" for record in chain),
                        "unavailable_execution_observed")
                resolution = self._resolve(exp, chain, revoked)
                latest = next(record for record in chain if record["record_id"] == resolution["latest"])
                dependencies.update([link["report_ref"], exp["record_id"], latest["record_id"], latest["rubric_ref"]])
                dependencies.update(record["record_id"] for record in chain)
                dependencies.update(record["rubric_ref"] for record in chain)
                label_current = ev["record_id"] == latest["record_id"]
                if not label_current:
                    reasons.append("native_report_evaluation_superseded")
                resolved.append({"run_id": link["run_id"], "experience_ref": exp["record_id"], "evaluation_ref": latest["record_id"],
                    "judge": latest["judge"], "rubric_ref": latest["rubric_ref"], "status": latest["status"],
                    "eligible": resolution["success_eligible"], "success": latest["success"], "score": latest["score"],
                    "reason": resolution["reason"], "native_effect_verified": verified, "native_label_current": label_current})
            require(executed == set(policy["execution_policy_refs"]), "unevaluated_declared_configuration")
            cost = {"report_ref": cost_report_ref, "available": False, "p95_ratio": None,
                    "metric_scope": "paired_end_to_end_wall_cpu",
                    "metrics_unassessed": ["cpu_ratio", "provider_usage", "monetary_cost", "rss", "io", "energy"]}
            if cost_report_ref is not None:
                dependencies.add(cost_report_ref)
                report = self._load(connection, cost_report_ref, "report")
                require(report.get("schema") == schema + "-cost" and type(report.get("version")) is int and
                        report["version"] == 1 and report.get("dataset_sha256") in datasets
                        and len(datasets) == 1 and report.get("candidate_implementation_ref") == policy["implementation_ref"]
                        and report.get("configuration_ref") == policy["configuration_ref"], "native_cost_binding_mismatch")
                baseline_ref = report.get("baseline_ref")
                require(is_ref(baseline_ref) and baseline_ref in policy["dependencies"], "native_baseline_dependency_required")
                baseline = self._load(connection, baseline_ref, "report")
                require(baseline.get("schema") == schema + "-baseline" and type(baseline.get("version")) is int
                        and baseline["version"] == 1 and is_ref(baseline.get("implementation_ref"))
                        and is_ref(baseline.get("configuration_ref")), "native_baseline_binding_required")
                dependencies.update([baseline_ref, baseline["implementation_ref"], baseline["configuration_ref"]])
                samples = report.get("samples")
                complete = (report.get("boundary") == ["retrieval", "proposal", "consume", "reopen"]
                    and type(samples) is list and 0 < len(samples) <= 512)
                keys, times = {"baseline": set(), "candidate": set()}, {"baseline": [], "candidate": []}
                if type(samples) is list:
                    require(len(samples) <= 512, "bounded_native_cost_samples_required")
                    for row in samples:
                        require(type(row) is dict and type(row.get("role")) is str and row["role"] in keys and type(row.get("task_id")) is str
                                and type(row.get("repeat")) is int and row["repeat"] >= 0, "native_cost_sample_binding_required")
                        role, key = row["role"], (row["task_id"], row["repeat"])
                        expected_implementation = baseline["implementation_ref"] if role == "baseline" else policy["implementation_ref"]
                        expected_configuration = baseline["configuration_ref"] if role == "baseline" else policy["configuration_ref"]
                        require(row.get("implementation_ref") == expected_implementation and
                                row.get("configuration_ref") == expected_configuration, "native_cost_execution_mismatch")
                        require(key not in keys[role], "duplicate_cost_sample")
                        keys[role].add(key)
                        phases = row.get("phase_wall_ns")
                        measured = (row.get("execution_status") == "completed" and type(row.get("wall_ns")) is int
                            and row["wall_ns"] > 0 and type(row.get("cpu_ns")) is int and row["cpu_ns"] >= 0
                            and type(phases) is dict and set(phases) == {"retrieval", "proposal", "consume", "reopen"}
                            and all(type(value) is int and value >= 0 for value in phases.values())
                            and sum(phases.values()) <= row["wall_ns"])
                        complete = complete and measured
                        if measured:
                            times[role].append(row["wall_ns"])
                if keys["baseline"] or keys["candidate"]:
                    require(keys["baseline"] == keys["candidate"] and
                            {case for _, case in seen_cases} <= {case for case, _ in keys["candidate"]}, "cost_quality_case_mismatch")
                if complete:
                    base = sorted(times["baseline"])[math.ceil(.95 * len(times["baseline"])) - 1]
                    candidate = sorted(times["candidate"])[math.ceil(.95 * len(times["candidate"])) - 1]
                    cost.update(available=True, baseline_p95_ns=base, candidate_p95_ns=candidate, p95_ratio=candidate / base)
            if not cost["available"]:
                reasons.append("native_full_cost_unavailable")
            elif cost["p95_ratio"] > self.protocol["max_p95_ratio"]:
                reasons.append("latency_gate_not_met")
            # The trusted hook must freshly validate the complete immutable chain,
            # expected-effect judgement and end-to-end cost, not just an emitter marker.
            required = tuple(sorted(dependencies))
            validation = revalidate(required) if callable(revalidate) else None
            rights_valid = (type(validation) is dict and set(validation) == {"status", "checked"}
                and validation["status"] == "valid" and type(validation["checked"]) is list
                and all(type(ref) is str for ref in validation["checked"]) and sorted(validation["checked"]) == list(required))
            if not rights_valid:
                reasons.append("native_rights_and_currentness_unverified")
            observed = [row for row in resolved if row["eligible"] and row["native_effect_verified"] and row["native_label_current"]]
            successes = sum(row["success"] is True for row in observed)
            rate = successes / len(observed) if observed else None
            unobserved = len(resolved) - len(observed)
            if len(observed) < self.protocol["min_observed"]:
                reasons.append("insufficient_observed_evidence")
            if unobserved > self.protocol["max_unobserved"]:
                reasons.append("unavailable_or_withdrawn_evidence")
            if rate is not None and rate < self.protocol["min_success_rate"]:
                reasons.append("quality_gate_not_met")
            if dependencies & revoked:
                reasons.append("revoked_dependency")
            assessment = {"schema": schema, "policy_ref": policy_ref, "protocol_ref": self.protocol_ref,
                "runs": resolved, "cost": cost, "observed": len(observed), "unobserved": unobserved,
                "successes": successes, "success_rate": rate, "reasons": sorted(set(reasons)),
                "eligible_for_admission_review": not reasons, "dependencies": sorted(dependencies),
                "native_revalidation": {"status": "valid" if rights_valid else "unverified", "checked": list(required) if rights_valid else []},
                "provenance_authenticated": False, "authorized_for_learning": False, "runtime_activated": False}
            assessment_ref = self._save(connection, "assessment", assessment)
            return self._event(connection, policy_ref, "evaluated", expected_seq, {"assessment_ref": assessment_ref})


    def inspect(self, policy_ref):
        with self.transaction() as connection:
            head = self._head(connection, policy_ref)
            ref = head["details"].get("assessment_ref")
            assessment = self._load(connection, ref, "assessment") if ref else None
            revoked = {row[0] for row in connection.execute("SELECT ref FROM revoked")}
            invalidated = assessment is not None and bool(set(assessment["dependencies"]) & revoked)
            current = assessment is None or self._assessment_current(connection, assessment, revoked)
            return {**head, "assessment": assessment, "effective_state": "rollback" if head["state"] == "admitted" and (invalidated or not current) else head["state"], "dependency_revoked": invalidated, "assessment_current": current, "runtime_activated": False}

    def _assessment_current(self, connection, assessment, revoked):
        for run in assessment["runs"]:
            experience = self._load(connection, run["experience_ref"], "experience")
            chain = []
            for row in connection.execute("SELECT ref FROM objects WHERE kind='evaluation'"):
                record = self._load(connection, row[0], "evaluation")
                if record["experience_ref"] == experience["record_id"]:
                    chain.append(record)
            resolution = self._resolve(experience, chain, revoked)
            if resolution["latest"] != run["evaluation_ref"] or resolution["success_eligible"] != run["eligible"]:
                return False
        return True

    def admit(self, policy_ref, expected_seq, revalidate):
        with self.transaction() as connection:
            head = self._head(connection, policy_ref)
            require(head["state"] == "evaluated", "admission_transition_forbidden")
            assessment = self._load(connection, head["details"]["assessment_ref"], "assessment")
            require(assessment["eligible_for_admission_review"], "evaluation_gate_refused")
            revoked = {row[0] for row in connection.execute("SELECT ref FROM revoked")}
            require(not set(assessment["dependencies"]) & revoked, "revoked_dependency")
            require(self._assessment_current(connection, assessment, revoked), "assessment_outdated")
            require(callable(revalidate), "fresh_dependency_validation_required")
            decision = revalidate(tuple(assessment["dependencies"]))
            require(type(decision) is dict and set(decision) == {"status", "checked"} and decision["status"] == "valid" and type(decision["checked"]) is list and sorted(decision["checked"]) == assessment["dependencies"], "fresh_dependency_validation_failed")
            return self._event(connection, policy_ref, "admitted", expected_seq, {"assessment_ref": head["details"]["assessment_ref"], "runtime_activated": False})

    def rollback(self, policy_ref, expected_seq, reason):
        require(type(reason) is str and 0 < len(reason) <= 256, "rollback_reason_required")
        with self.transaction() as connection:
            head = self._head(connection, policy_ref)
            require(head["state"] in {"evaluated", "admitted"}, "rollback_transition_forbidden")
            return self._event(connection, policy_ref, "rollback", expected_seq, {**head["details"], "reason": reason})

    def revoke(self, reference, reason):
        require(is_ref(reference) and type(reason) is str and 0 < len(reason) <= 256, "invalid_revocation")
        with self.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO revoked VALUES (?,?)", (reference, reason))
        return {"ref": reference, "revoked": True}
