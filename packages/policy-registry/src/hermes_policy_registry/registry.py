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
