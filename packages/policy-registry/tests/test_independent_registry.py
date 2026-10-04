"""Independent G4 assertions against synthetic immutable records and real SQLite."""
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hermes_policy_registry import Registry, PolicyError, identity, load_learning_records


class IndependentRegistryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.records = load_learning_records()
        self.code = "c" * 64
        self.dataset = "d" * 64
        self.execution = {"id": "review-synthetic", "implementation_sha256": self.code, "budget": {"top_k": 1, "max_context_chars": 100}}
        self.safety = identity({"authority": "unchanged"})
        self.rubric = identity({"rubric": "independent-synthetic"})
        self.judge = {"kind": "executable", "identifier": "independent-fixture", "revision": "1"}
        self.protocol = {"schema_version": 1, "family": "retrieval", "safety_contract_ref": self.safety, "judge": self.judge,
                         "rubric_refs": [self.rubric], "min_observed": 1, "min_success_rate": 1.0, "max_unobserved": 0, "max_p95_ratio": 1.2}
        self.registry = Registry.create(self.root / "registry.sqlite", self.records, self.protocol)
        execution_refs = [identity(self.execution)]
        self.artifact = {"schema_version": 1, "family": "retrieval", "name": "independent-policy", "implementation_ref": "sha256:" + self.code,
                         "configuration_ref": identity({"schema": "execution-policy-set-v1", "policy_refs": execution_refs}),
                         "safety_contract_ref": self.safety, "execution_policy_refs": execution_refs, "dependencies": []}
        self.proposed = self.registry.propose(self.artifact)
        self.ref = self.proposed["policy_ref"]

    def run_record(self, status="completed", success=True, score=10, evaluation_status="observed", reason=None, run_id="review-run"):
        refs = {"synthetic-doc": {"workspace": "review", "artifact_id": "A", "version_id": "v1"}}
        outcome = {"execution_status": status, "synthetic": True}
        exp = self.records.seal({"schema_version": self.records.VERSION, "kind": "experience", "created_at": "2026-10-04T10:00:00Z",
                                 "case_id": "review-case", "family": "retrieval", "policy_ref": identity(self.execution),
                                 "source_refs": [identity({"doc_id": key, "ref": value}) for key, value in sorted(refs.items())],
                                 "lineage_status": "observed", "outcome_ref": identity(outcome)})
        ev = self.records.seal({"schema_version": self.records.VERSION, "kind": "evaluation", "created_at": "2026-10-04T10:00:01Z",
                                "experience_ref": exp["record_id"], "status": evaluation_status, "success": success, "score": score,
                                "judge": self.judge, "rubric_ref": self.rubric, "reason": reason, "supersedes": None})
        return {"run_id": run_id, "task_id": "review-case", "policy": copy.deepcopy(self.execution), "refs": refs, "outcome": outcome,
                "records": {"experience": exp, "evaluation": ev}}

    def cost(self):
        return {"kind": "r4_serial_development_cost_screen_not_promotion", "dataset_sha256": self.dataset, "r3_sha256": self.code,
                "r4_sha256": "b" * 64, "unchanged_ratio_limit": 1.2,
                "summary": {label: {"wall": {"p95_ms": 1.0, "count": 1}} for label in ("core_lexical_budgeted", "typed_r3")},
                "samples": [{"policy": label, "task_id": "review-case", "repeat": 0, "execution_status": "completed", "wall_ns": 1000000} for label in ("core_lexical_budgeted", "typed_r3")],
                "functional_parity_and_no_mutation": True, "failures": []}

    def evaluate(self, runs=None, cost=None, dataset=None, expected=None):
        runs = runs or [self.run_record()]
        report = self.registry.add_report({"dataset_sha256": dataset or self.dataset, "runs": runs})
        cost_ref = self.registry.add_report(cost or self.cost())
        return self.registry.evaluate_retrieval_reports(self.ref, [{"report_ref": report, "run_id": run["run_id"]} for run in runs], cost_ref,
                                                        "typed_r3", self.proposed["seq"] if expected is None else expected)

    @staticmethod
    def validator(refs):
        return {"status": "valid", "checked": list(refs)}

    def assert_not_admissible(self, operation):
        try:
            event = operation()
        except PolicyError:
            return
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertFalse(assessment["eligible_for_admission_review"], assessment)
        with self.assertRaises(PolicyError):
            self.registry.admit(self.ref, event["seq"], self.validator)

    def test_exact_bindings_can_be_admitted_without_runtime_activation(self):
        event = self.evaluate()
        admitted = self.registry.admit(self.ref, event["seq"], self.validator)
        self.assertEqual(admitted["state"], "admitted")
        self.assertFalse(self.registry.inspect(self.ref)["runtime_activated"])

    def test_duplicate_experience_under_distinct_run_ids_cannot_meet_observed_minimum(self):
        strict = Registry.create(self.root / "strict.sqlite", self.records, {**self.protocol, "min_observed": 2})
        self.registry = strict
        self.proposed = strict.propose(self.artifact)
        run = self.run_record()
        duplicate = copy.deepcopy(run)
        duplicate["run_id"] = "review-copy"
        self.assert_not_admissible(lambda: self.evaluate([run, duplicate]))

    def test_duplicate_experience_in_distinct_reports_cannot_meet_observed_minimum(self):
        self.registry = Registry.create(self.root / "strict.sqlite", self.records, {**self.protocol, "min_observed": 2})
        self.proposed = self.registry.propose(self.artifact)
        run = self.run_record()
        refs = [self.registry.add_report({"dataset_sha256": self.dataset, "copy": i, "runs": [run]}) for i in range(2)]
        cost = self.registry.add_report(self.cost())
        self.assert_not_admissible(lambda: self.registry.evaluate_retrieval_reports(self.ref, [{"report_ref": ref, "run_id": run["run_id"]} for ref in refs], cost, "typed_r3", self.proposed["seq"]))

    def test_unavailable_execution_cannot_become_positive_observation(self):
        self.assert_not_admissible(lambda: self.evaluate([self.run_record(status="unavailable")]))

    def test_error_execution_cannot_become_positive_observation(self):
        self.assert_not_admissible(lambda: self.evaluate([self.run_record(status="error")]))

    def test_different_cost_dataset_cannot_qualify_quality_runs(self):
        cost = self.cost()
        cost["dataset_sha256"] = "e" * 64
        self.assert_not_admissible(lambda: self.evaluate(cost=cost))

    def test_failed_cost_samples_cannot_be_positive_parity_evidence(self):
        cost = self.cost()
        cost["samples"][1]["execution_status"] = "error"
        self.assert_not_admissible(lambda: self.evaluate(cost=cost))

    def test_false_zero_stays_observed_failure(self):
        self.evaluate([self.run_record(success=False, score=0)])
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertEqual((assessment["observed"], assessment["unobserved"], assessment["successes"]), (1, 0, 0))
        self.assertEqual(assessment["runs"][0]["score"], 0)
        self.assertFalse(assessment["eligible_for_admission_review"])

    def test_unavailable_null_stays_unobserved(self):
        self.evaluate([self.run_record(status="unavailable", success=None, score=None, evaluation_status="unavailable", reason="timeout")])
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertEqual((assessment["observed"], assessment["unobserved"]), (0, 1))
        self.assertIsNone(assessment["success_rate"])
        self.assertIsNone(assessment["runs"][0]["score"])

    def test_configuration_mutation_without_resealed_evidence_refuses(self):
        run = self.run_record()
        run["policy"]["budget"]["max_context_chars"] = 9000
        with self.assertRaisesRegex(PolicyError, "executed_policy_binding"):
            self.evaluate([run])

    def test_stale_evaluation_rolls_back_new_objects_as_well_as_event(self):
        first = self.evaluate()
        changed = self.run_record()
        changed["outcome"]["variant"] = "new-synthetic-experience"
        exp = {key: value for key, value in changed["records"]["experience"].items() if key != "record_id"}
        exp["outcome_ref"] = identity(changed["outcome"])
        changed["records"]["experience"] = self.records.seal(exp)
        ev = {key: value for key, value in changed["records"]["evaluation"].items() if key != "record_id"}
        ev["experience_ref"] = changed["records"]["experience"]["record_id"]
        changed["records"]["evaluation"] = self.records.seal(ev)
        report = self.registry.add_report({"dataset_sha256": self.dataset, "runs": [changed]})
        cost = self.registry.add_report(self.cost())
        with sqlite3.connect(self.registry.path) as connection:
            before = tuple(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in ("objects", "events"))
        reopened = Registry(self.registry.path, self.records)
        with self.assertRaisesRegex(PolicyError, "stale_policy_state"):
            reopened.evaluate_retrieval_reports(self.ref, [{"report_ref": report, "run_id": "review-run"}], cost, "typed_r3", self.proposed["seq"])
        with sqlite3.connect(self.registry.path) as connection:
            after = tuple(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in ("objects", "events"))
        self.assertEqual(before, after)
        self.assertEqual(reopened.inspect(self.ref)["seq"], first["seq"])

    def test_revoked_source_invalidates_admitted_policy_on_reopen(self):
        run = self.run_record()
        event = self.evaluate([run])
        self.registry.admit(self.ref, event["seq"], self.validator)
        self.registry.revoke(run["records"]["experience"]["source_refs"][0], "synthetic revocation")
        current = Registry(self.registry.path, self.records).inspect(self.ref)
        self.assertEqual(current["effective_state"], "rollback")
        self.assertTrue(current["dependency_revoked"])

    def test_superseded_evaluation_invalidates_admitted_policy(self):
        run = self.run_record()
        event = self.evaluate([run])
        self.registry.admit(self.ref, event["seq"], self.validator)
        original = run["records"]["evaluation"]
        revision = {key: value for key, value in original.items() if key != "record_id"}
        revision.update(created_at="2026-10-04T10:01:00Z", success=False, score=0, supersedes=original["record_id"])
        self.registry.add_record(self.records.seal(revision))
        current = self.registry.inspect(self.ref)
        self.assertEqual(current["effective_state"], "rollback")
        self.assertFalse(current["assessment_current"])

    def test_cost_summary_recomputed_and_original_ratio_kept(self):
        cost = self.cost()
        cost["samples"][1]["wall_ns"] = 1500000
        cost["summary"]["typed_r3"]["wall"]["p95_ms"] = 1.5
        self.evaluate(cost=cost)
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertEqual(assessment["cost"]["p95_ratio"], 1.5)
        self.assertIn("latency_gate_not_met", assessment["reasons"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
