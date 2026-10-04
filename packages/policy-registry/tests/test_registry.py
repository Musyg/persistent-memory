"""Synthetic registry transitions, exact report bindings and label corrections."""
import copy
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hermes_policy_registry import Registry, PolicyError, identity, load_learning_records


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_learning_records(os.environ.get("G4_LEARNING_RECORDS"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.code = "a" * 64
        self.dataset = "d" * 64
        self.execution_policy = {"id": "synthetic-only", "implementation_sha256": self.code, "budget": {"top_k": 1, "max_context_chars": 100}}
        self.safety, self.rubric = identity({"authorization_changes": False}), identity({"rubric": "synthetic-contract-only"})
        self.judge = {"kind": "executable", "identifier": "synthetic-test-oracle", "revision": "1"}
        self.protocol = {"schema_version": 1, "family": "retrieval", "safety_contract_ref": self.safety, "judge": self.judge, "rubric_refs": [self.rubric], "min_observed": 1, "min_success_rate": 1.0, "max_unobserved": 0, "max_p95_ratio": 1.2}
        self.registry = Registry.create(self.path / "registry.sqlite", self.records, self.protocol)
        self.exp, self.ev, self.run = self.make_run()
        self.report_ref = self.registry.add_report({"dataset_sha256": self.dataset, "runs": [self.run]})
        self.cost_ref = self.registry.add_report(self.cost_report())
        executions = [identity(self.execution_policy)]
        self.artifact = {"schema_version": 1, "family": "retrieval", "name": "synthetic-policy", "implementation_ref": "sha256:" + self.code, "configuration_ref": identity({"schema": "execution-policy-set-v1", "policy_refs": executions}), "safety_contract_ref": self.safety, "execution_policy_refs": executions, "dependencies": []}
        self.proposed = self.registry.propose(self.artifact)
        self.ref = self.proposed["policy_ref"]

    def make_run(self, success=True, score=10, status="observed", reason=None):
        refs = {"doc": {"workspace": "synthetic", "artifact_id": "a", "version_id": "v1"}}
        outcome = {"execution_status": "completed" if status == "observed" else "unavailable", "synthetic": True}
        exp = self.records.seal({"schema_version": self.records.VERSION, "kind": "experience", "created_at": "2026-10-04T00:00:00Z", "case_id": "synthetic", "family": "retrieval", "policy_ref": identity(self.execution_policy), "source_refs": [identity({"doc_id": key, "ref": value}) for key, value in sorted(refs.items())], "lineage_status": "observed", "outcome_ref": identity(outcome)})
        ev = self.records.seal({"schema_version": self.records.VERSION, "kind": "evaluation", "created_at": "2026-10-04T00:00:00Z", "experience_ref": exp["record_id"], "status": status, "success": success, "score": score, "judge": self.judge, "rubric_ref": self.rubric, "reason": reason, "supersedes": None})
        run = {"run_id": "synthetic-run-1", "task_id": "synthetic", "policy": copy.deepcopy(self.execution_policy), "refs": refs, "outcome": outcome, "records": {"experience": exp, "evaluation": ev}}
        return exp, ev, run

    def cost_report(self, ratio=1):
        candidate_ns = int(1000000 * ratio)
        return {"kind": "r4_serial_development_cost_screen_not_promotion", "dataset_sha256": self.dataset, "r3_sha256": self.code, "r4_sha256": "b" * 64, "unchanged_ratio_limit": 1.2, "summary": {"core_lexical_budgeted": {"wall": {"p95_ms": 1.0, "count": 1}}, "typed_r3": {"wall": {"p95_ms": candidate_ns / 1e6, "count": 1}}}, "samples": [{"policy": "core_lexical_budgeted", "task_id": "synthetic", "repeat": 0, "execution_status": "completed", "wall_ns": 1000000}, {"policy": "typed_r3", "task_id": "synthetic", "repeat": 0, "execution_status": "completed", "wall_ns": candidate_ns}], "functional_parity_and_no_mutation": True, "failures": []}

    def evaluate(self, expected=None, report=None, cost=None):
        if expected is None:
            expected = self.registry.inspect(self.ref)["seq"]
        return self.registry.evaluate_retrieval_reports(self.ref, [{"report_ref": report or self.report_ref, "run_id": "synthetic-run-1"}], cost or self.cost_ref, "typed_r3", expected)

    def admit(self):
        head = self.evaluate()
        return self.registry.admit(self.ref, head["seq"], lambda refs: {"status": "valid", "checked": list(refs)})

    def revision(self, status="withdrawn", success=None, score=None, reason="label_withdrawn"):
        body = {key: value for key, value in self.ev.items() if key != "record_id"}
        body.update(created_at="2026-10-04T00:01:00Z", status=status, success=success, score=score, reason=reason, supersedes=self.ev["record_id"])
        return self.records.seal(body)

    def test_five_families_are_representable_not_five_evaluators(self):
        for family in ("prompt", "retrieval", "routing", "workflow", "skill"):
            value = {**self.artifact, "family": family}
            event = self.registry.propose(value)
            self.assertEqual(event["state"], "proposed")
            if family != "retrieval":
                with self.assertRaisesRegex(PolicyError, "retrieval_report_adapter_required"):
                    self.registry.evaluate_retrieval_reports(event["policy_ref"], [], self.cost_ref, "typed_r3", event["seq"])

    def test_bundled_contract_available_without_private_path(self):
        bundled = load_learning_records()
        self.assertEqual(bundled.VERSION, self.records.VERSION)
        self.assertEqual(bundled.validate(self.exp), self.exp)

    def test_content_identity_and_exact_proposal_retry(self):
        self.assertEqual(self.ref, identity(self.artifact))
        self.assertEqual(self.registry.propose(self.artifact), self.proposed)
        changed = {**self.artifact, "name": "new-revision"}
        self.assertNotEqual(self.registry.propose(changed)["policy_ref"], self.ref)

    def test_configuration_mismatch_and_untested_variant_refused(self):
        with self.assertRaisesRegex(PolicyError, "configuration_execution_set_mismatch"):
            self.registry.propose({**self.artifact, "configuration_ref": identity({"unrelated": True})})
        refs = sorted(self.artifact["execution_policy_refs"] + [identity({"untested": True})])
        other = {**self.artifact, "execution_policy_refs": refs, "configuration_ref": identity({"schema": "execution-policy-set-v1", "policy_refs": refs})}
        head = self.registry.propose(other)
        with self.assertRaisesRegex(PolicyError, "unevaluated_declared_configuration"):
            self.registry.evaluate_retrieval_reports(head["policy_ref"], [{"report_ref": self.report_ref, "run_id": "synthetic-run-1"}], self.cost_ref, "typed_r3", head["seq"])

    def test_authorization_fields_cannot_be_learned(self):
        with self.assertRaisesRegex(PolicyError, "invalid_artifact_fields"):
            self.registry.propose({**self.artifact, "grant_permissions": ["all"]})
        altered = {**self.artifact, "safety_contract_ref": identity({"skip_authority": True})}
        proposed = self.registry.propose(altered)
        with self.assertRaisesRegex(PolicyError, "protocol_or_safety"):
            self.registry.evaluate_retrieval_reports(proposed["policy_ref"], [], self.cost_ref, "typed_r3", proposed["seq"])

    def test_actual_false_zero_count_as_observed_failure(self):
        _, _, run = self.make_run(False, 0)
        report = self.registry.add_report({"dataset_sha256": self.dataset, "runs": [run]})
        self.evaluate(report=report)
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertEqual((assessment["observed"], assessment["unobserved"], assessment["successes"]), (1, 0, 0))
        self.assertIn("quality_gate_not_met", assessment["reasons"])
        self.assertEqual(assessment["runs"][0]["score"], 0)

    def test_unavailable_is_not_false_or_zero(self):
        _, _, run = self.make_run(None, None, "unavailable", "timeout")
        report = self.registry.add_report({"dataset_sha256": self.dataset, "runs": [run]})
        self.evaluate(report=report)
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertEqual((assessment["observed"], assessment["unobserved"], assessment["success_rate"]), (0, 1, None))
        self.assertIsNone(assessment["runs"][0]["score"])

    def test_cost_gate_and_claimed_summary_mismatch(self):
        cost = self.registry.add_report(self.cost_report(1.542))
        event = self.evaluate(cost=cost)
        self.assertIn("latency_gate_not_met", self.registry.inspect(self.ref)["assessment"]["reasons"])
        with self.assertRaisesRegex(PolicyError, "evaluation_gate_refused"):
            self.registry.admit(self.ref, event["seq"], None)
        forged = self.cost_report()
        forged["summary"]["typed_r3"]["wall"]["p95_ms"] = .1
        with self.assertRaisesRegex(PolicyError, "cost_summary_binding_mismatch"):
            self.evaluate(cost=self.registry.add_report(forged))

    def test_fresh_dependency_validation_required_for_admission(self):
        event = self.evaluate()
        for validator in (None, lambda refs: {"status": "unknown", "checked": list(refs)}, lambda refs: {"status": "valid", "checked": []}):
            with self.assertRaises(PolicyError):
                self.registry.admit(self.ref, event["seq"], validator)
        admitted = self.registry.admit(self.ref, event["seq"], lambda refs: {"status": "valid", "checked": list(refs)})
        self.assertEqual(admitted["state"], "admitted")
        self.assertFalse(self.registry.inspect(self.ref)["runtime_activated"])

    def test_stale_sequence_evaluation_rolls_back(self):
        event = self.evaluate()
        with self.assertRaisesRegex(PolicyError, "stale_policy_state"):
            self.evaluate(expected=self.proposed["seq"])
        self.assertEqual(self.registry.inspect(self.ref)["seq"], event["seq"])

    def test_withdrawal_after_admission_invalidates_current_policy(self):
        self.admit()
        self.registry.add_record(self.revision())
        current = self.registry.inspect(self.ref)
        self.assertEqual(current["effective_state"], "rollback")
        self.assertFalse(current["assessment_current"])

    def test_source_revocation_after_admission_invalidates_policy(self):
        self.admit()
        self.registry.revoke(self.exp["source_refs"][0], "synthetic source revoked")
        current = self.registry.inspect(self.ref)
        self.assertTrue(current["dependency_revoked"])
        self.assertEqual(current["effective_state"], "rollback")

    def test_late_revision_requires_reevaluation_and_preserves_old_record(self):
        evaluated = self.evaluate()
        changed = self.revision("observed", False, 0, None)
        self.registry.add_record(changed)
        with self.assertRaisesRegex(PolicyError, "assessment_outdated"):
            self.registry.admit(self.ref, evaluated["seq"], lambda refs: {"status": "valid", "checked": list(refs)})
        self.evaluate()
        current = self.registry.inspect(self.ref)
        self.assertEqual(current["assessment"]["runs"][0]["evaluation_ref"], changed["record_id"])
        self.assertIn("quality_gate_not_met", current["assessment"]["reasons"])
        with self.registry.transaction() as connection:
            self.assertEqual(self.registry._load(connection, self.ev["record_id"]), self.ev)

    def test_rollback_terminal_no_reanimation(self):
        admitted = self.admit()
        rolled = self.registry.rollback(self.ref, admitted["seq"], "synthetic operator rollback")
        with self.assertRaisesRegex(PolicyError, "evaluation_transition_forbidden"):
            self.evaluate(expected=rolled["seq"])
        with self.assertRaisesRegex(PolicyError, "admission_transition_forbidden"):
            self.registry.admit(self.ref, rolled["seq"], None)

    def test_unknown_run_and_mismatched_executed_payload_refused(self):
        wrong = copy.deepcopy(self.run)
        wrong["policy"]["budget"]["top_k"] = 2
        with self.assertRaisesRegex(PolicyError, "executed_policy_binding_mismatch"):
            self.evaluate(report=self.registry.add_report({"dataset_sha256": self.dataset, "runs": [wrong]}))
        with self.assertRaisesRegex(PolicyError, "run_missing_or_ambiguous"):
            self.evaluate(report=self.registry.add_report({"dataset_sha256": self.dataset, "runs": []}))

    def test_judge_revision_is_not_silently_rebound(self):
        self.evaluate()
        revision = self.revision("observed", True, 10, None)
        revision["judge"] = {**self.judge, "revision": "other"}
        revision = self.records.seal({key: value for key, value in revision.items() if key != "record_id"})
        self.registry.add_record(revision)
        with self.assertRaisesRegex(PolicyError, "judge_or_rubric_not_admitted"):
            self.evaluate()

    def test_reopen_and_tampered_object_detection(self):
        self.evaluate()
        reopened = Registry(self.registry.path, self.records)
        self.assertEqual(reopened.inspect(self.ref), self.registry.inspect(self.ref))
        with sqlite3.connect(self.registry.path) as connection:
            connection.execute("UPDATE objects SET payload='{}' WHERE ref=?", (self.ref,))
        with self.assertRaisesRegex(PolicyError, "stored_identity_mismatch"):
            self.evaluate()

    def test_cost_samples_pair_cases_and_do_not_duplicate_measurements(self):
        mismatched = self.cost_report()
        mismatched["samples"][1]["task_id"] = "unrelated"
        with self.assertRaisesRegex(PolicyError, "cost_quality_case_mismatch"):
            self.evaluate(cost=self.registry.add_report(mismatched))
        duplicate = self.cost_report()
        duplicate["samples"].append(copy.deepcopy(duplicate["samples"][1]))
        with self.assertRaisesRegex(PolicyError, "duplicate_cost_sample"):
            self.evaluate(cost=self.registry.add_report(duplicate))

    def test_resealed_same_case_does_not_inflate_evidence(self):
        duplicate = copy.deepcopy(self.run)
        duplicate["run_id"] = "new-envelope"
        body = {key: value for key, value in self.exp.items() if key != "record_id"}
        body["created_at"] = "2026-10-04T00:01:00Z"
        duplicate["records"]["experience"] = self.records.seal(body)
        evaluation = {key: value for key, value in self.ev.items() if key != "record_id"}
        evaluation["experience_ref"] = duplicate["records"]["experience"]["record_id"]
        duplicate["records"]["evaluation"] = self.records.seal(evaluation)
        report = self.registry.add_report({"dataset_sha256": self.dataset, "runs": [self.run, duplicate]})
        with self.assertRaisesRegex(PolicyError, "duplicate_quality_case"):
            self.registry.evaluate_retrieval_reports(self.ref, [{"report_ref": report, "run_id": run["run_id"]} for run in (self.run, duplicate)], self.cost_ref, "typed_r3", self.proposed["seq"])

    def test_contract_error_is_normalized_but_programming_error_propagates(self):
        with patch.object(self.records, "resolve", side_effect=self.records.ContractError("ambiguous revision fork")):
            with self.assertRaisesRegex(PolicyError, "invalid_evaluation_chain"):
                self.evaluate()
        with patch.object(self.records, "resolve", side_effect=ValueError("injected programming defect")):
            with self.assertRaisesRegex(ValueError, "injected programming defect"):
                self.evaluate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
