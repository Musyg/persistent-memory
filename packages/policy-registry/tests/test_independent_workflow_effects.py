"""Independent workflow assessment controls; stdlib SQLite and immutable synthetic records.

Frozen before reading candidate implementation. This is a unittest fixture, not
a new runner or production adapter. A host callback reopens durable state.
"""
import copy
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from hermes_policy_registry import Registry, PolicyError, identity, load_learning_records


class IndependentWorkflowEffectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="independent-workflow-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "effect.sqlite"
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE effects(case_id TEXT PRIMARY KEY, retention_hours INTEGER)")
        self.records = load_learning_records()
        self.dataset = {"schema": "independent-workflow-cases-v1",
                        "cases": [{"case_id": "positive", "expected_hours": 24}]}
        self.rule = {"rule_id": "independent-retention-v1", "revision": 1,
                     "condition": "stale active work", "action": {"retention_hours": 24}}
        self.oracle = {"kind": "independent-state-reopen", "revision": "1",
                       "case_expectations": {"positive": 24}}
        self.code = identity({"independent_executor": "permitted-sqlite-update-v1"})
        self.rule_ref = identity(self.rule)
        self.oracle_ref = identity(self.oracle)
        self.dataset_ref = identity(self.dataset)
        self.safety = identity({"authorization_changes": False})
        self.policy = {"id": "independent-executor", "implementation_sha256": self.code[7:],
                       "budget": {"top_k": 1, "max_context_chars": 100}}
        self.configuration = identity({"schema": "execution-policy-set-v1",
                                       "policy_refs": [identity(self.policy)]})
        self.judge = {"kind": "executable", "identifier": "native-workflow-effects-v1", "revision": "1"}
        self.protocol = {"schema_version": 1, "family": "workflow", "safety_contract_ref": self.safety,
                         "judge": self.judge, "rubric_refs": [self.oracle_ref], "min_observed": 1,
                         "min_success_rate": 1.0, "max_unobserved": 0, "max_p95_ratio": 1000000000.0}
        self.registry = Registry.create(self.directory / "registry.sqlite", self.records, self.protocol)
        for value, reference in ((self.rule, self.rule_ref), (self.oracle, self.oracle_ref),
                                 (self.dataset, self.dataset_ref)):
            self.assertEqual(self.registry.add_report(value), reference)
        self.baseline = {"schema": "native-workflow-effects-v1-baseline", "version": 1,
                         "implementation_ref": identity({"baseline": "fixed-prior-72"}),
                         "configuration_ref": identity({"baseline_configuration": 1})}
        self.baseline_ref = self.registry.add_report(self.baseline)
        self.artifact = {"schema_version": 1, "family": "workflow", "name": "independent-workflow",
                         "implementation_ref": self.code, "configuration_ref": self.configuration,
                         "safety_contract_ref": self.safety, "execution_policy_refs": [identity(self.policy)],
                         "dependencies": [self.rule_ref, self.oracle_ref, self.dataset_ref, self.baseline_ref]}
        self.proposed = self.registry.propose(self.artifact)
        self.ref = self.proposed["policy_ref"]
        self.oracle_calls = []

    def reopen(self, case_id="positive"):
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT retention_hours FROM effects WHERE case_id=?", (case_id,)).fetchone()
        return {"retention_hours": row[0]} if row else None

    def run_record(self, *, actual_hours=24, label=True, execution_status="completed",
                   evaluation_status="observed", case_id="positive", run_id="independent-workflow-run"):
        started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT OR REPLACE INTO effects VALUES (?,?)", (case_id, actual_hours))
        durable = self.reopen(case_id)
        wall = max(1, time.perf_counter_ns() - started)
        cpu = max(0, time.process_time_ns() - cpu_started)
        effect = {"operation": "set_retention_hours", "arguments": {"hours": actual_hours},
                  "effect_state": durable}
        receipt = {**effect, "phase": "after_consumption", "status": "completed",
                   "authority_check": {"phase": "before_consumption", "status": "current"}}
        outcome = {"execution_status": execution_status, "consumer_action_observation": receipt}
        snapshot = {"id": "synthetic-rule-source", "text": self.rule["condition"],
                    "record": {"fact": self.rule["condition"], "version": 1}}
        exp = self.records.seal({"schema_version": self.records.VERSION, "kind": "experience",
                                "created_at": "2026-10-17T00:00:00Z", "case_id": case_id, "family": "workflow",
                                "policy_ref": identity(self.policy), "source_refs": [identity(snapshot)],
                                "lineage_status": "observed", "outcome_ref": identity(outcome)})
        ev = self.records.seal({"schema_version": self.records.VERSION, "kind": "evaluation",
                               "created_at": "2026-10-17T00:00:01Z", "experience_ref": exp["record_id"],
                               "status": evaluation_status, "success": label,
                               "score": (10 if label else 0) if label is not None else None,
                               "judge": self.judge, "rubric_ref": self.oracle_ref, "reason": None if label is not None else "unavailable",
                               "supersedes": None})
        run = {"run_id": run_id, "task_id": case_id, "policy": copy.deepcopy(self.policy),
               "execution": {"implementation_ref": self.code, "configuration_ref": self.configuration},
               "outcome": outcome, "source_snapshots": [snapshot], "records": {"experience": exp, "evaluation": ev},
               "rule_ref": self.rule_ref, "oracle_ref": self.oracle_ref,
               "reopened_effect": {"phase": "after_independent_reopen", "effect_ref": identity(effect)}}
        self.cost_samples = [{"role": role, "task_id": case_id, "repeat": 0, "execution_status": "completed",
                              "implementation_ref": self.baseline["implementation_ref"] if role == "baseline" else self.code,
                              "configuration_ref": self.baseline["configuration_ref"] if role == "baseline" else self.configuration,
                              "wall_ns": wall, "cpu_ns": cpu,
                              "phase_wall_ns": {"retrieval": 0, "proposal": 0, "consume": wall, "reopen": 0}}
                             for role in ("baseline", "candidate")]
        # These equal samples qualify only binding-contract checks, not latency or
        # utility claims. Actual three-arm measurements are separate native data.
        return run

    def cost_report(self):
        return {"schema": "native-workflow-effects-v1-cost", "version": 1,
                "dataset_sha256": self.dataset_ref[7:], "candidate_implementation_ref": self.code,
                "configuration_ref": self.configuration, "baseline_ref": self.baseline_ref,
                "boundary": ["retrieval", "proposal", "consume", "reopen"],
                "samples": copy.deepcopy(self.cost_samples)}

    @staticmethod
    def authority(refs):
        return {"status": "valid", "checked": list(refs)}

    def verifier(self, envelope):
        self.oracle_calls.append(copy.deepcopy(envelope))
        run = envelope["run"]
        actual = self.reopen(run["task_id"])
        expected = self.oracle["case_expectations"][run["task_id"]]
        ev = run["records"]["evaluation"]
        receipt = run["outcome"]["consumer_action_observation"]
        effect = {key: receipt[key] for key in ("operation", "arguments", "effect_state")}
        authentic = (actual == effect["effect_state"] and
                     receipt["arguments"] == {"hours": actual["retention_hours"]})
        label_correct = ev["success"] is (actual == {"retention_hours": expected})
        bound = (envelope["rule_ref"] == self.rule_ref and envelope["oracle_ref"] == self.oracle_ref
                 and envelope["dataset_ref"] == self.dataset_ref)
        if not (authentic and label_correct and bound):
            return {"status": "unverified"}
        return {"status": "verified", "effect_ref": identity(effect), "rule_ref": self.rule_ref,
                "oracle_ref": self.oracle_ref, "dataset_ref": self.dataset_ref}

    def evaluate(self, runs=None, verifier=None, cost=None, expected_seq=None):
        runs = runs if runs is not None else [self.run_record()]
        report = {"schema": "native-workflow-effects-v1", "version": 1,
                  "dataset_sha256": self.dataset_ref[7:], "rule_ref": self.rule_ref,
                  "oracle_ref": self.oracle_ref, "runs": runs}
        report_ref = self.registry.add_report(report)
        cost_ref = self.registry.add_report(cost if cost is not None else self.cost_report())
        return self.registry.evaluate_workflow_effect_reports(
            self.ref, [{"report_ref": report_ref, "run_id": run["run_id"]} for run in runs],
            cost_ref, self.proposed["seq"] if expected_seq is None else expected_seq,
            self.authority, self.verifier if verifier is None else verifier)

    def assert_ineligible(self, callback):
        try:
            event = callback()
        except PolicyError:
            return
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertFalse(assessment["eligible_for_admission_review"], assessment)
        with self.assertRaises(PolicyError):
            self.registry.admit(self.ref, event["seq"], self.authority)

    def test_workflow_real_reopen_can_be_admitted_and_rollback_restores_behavior(self):
        event = self.evaluate()
        admitted = self.registry.admit(self.ref, event["seq"], self.authority)
        self.assertEqual(admitted["state"], "admitted")
        self.assertFalse(self.registry.inspect(self.ref)["runtime_activated"])
        self.assertEqual(self.reopen(), {"retention_hours": 24})
        self.registry.rollback(self.ref, admitted["seq"], "independent rollback")
        # Registry does not deploy. Host checks state and restores actual effect.
        self.assertEqual(self.registry.inspect(self.ref)["effective_state"], "rollback")
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE effects SET retention_hours=72")
        self.assertEqual(self.reopen(), {"retention_hours": 72})

    def test_forged_claimed_effect_without_write_is_not_admissible(self):
        run = self.run_record()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE effects SET retention_hours=72")
        self.assert_ineligible(lambda: self.evaluate([run]))

    def test_wrong_actual_effect_stays_observed_failure(self):
        event = self.evaluate([self.run_record(actual_hours=72, label=False)])
        assessment = self.registry.inspect(self.ref)["assessment"]
        self.assertEqual((assessment["observed"], assessment["successes"]), (1, 0))
        self.assertEqual(assessment["success_rate"], 0)
        self.assertFalse(assessment["eligible_for_admission_review"])
        self.assertEqual(event["state"], "evaluated")

    def test_missing_host_verifier_never_trusts_emitter_reopen_marker(self):
        self.assert_ineligible(lambda: self.evaluate(verifier=lambda envelope: None))

    def test_stale_callback_binding_is_not_admissible(self):
        def wrong_binding(envelope):
            result = self.verifier(envelope)
            result["rule_ref"] = identity({"different_rule": True})
            return result
        self.assert_ineligible(lambda: self.evaluate(verifier=wrong_binding))

    def test_duplicate_case_under_distinct_run_ids_rejected(self):
        run = self.run_record()
        duplicate = copy.deepcopy(run)
        duplicate["run_id"] = "copy"
        self.assert_ineligible(lambda: self.evaluate([run, duplicate]))

    def test_unavailable_execution_is_not_observed_success(self):
        run = self.run_record(execution_status="unavailable")
        self.assert_ineligible(lambda: self.evaluate([run]))

    def test_mutation_of_detached_callback_payload_does_not_change_stored_evidence(self):
        run = self.run_record()
        original = copy.deepcopy(run)
        def mutated(envelope):
            result = self.verifier(envelope)
            envelope["run"]["outcome"]["consumer_action_observation"]["effect_state"]["retention_hours"] = 999
            return result
        self.evaluate([run], verifier=mutated)
        self.assertEqual(run, original)
        self.assertEqual(self.reopen(), {"retention_hours": 24})

    def test_revoke_source_invalidates_admission_and_blocks_host_activation(self):
        run = self.run_record()
        event = self.evaluate([run])
        self.registry.admit(self.ref, event["seq"], self.authority)
        self.registry.revoke(run["records"]["experience"]["source_refs"][0], "independent withdrawal")
        reopened = Registry(self.registry.path, self.records).inspect(self.ref)
        self.assertEqual(reopened["effective_state"], "rollback")
        self.assertTrue(reopened["dependency_revoked"])
        self.assertFalse(reopened["runtime_activated"])

    def test_changed_rule_identity_is_not_admissible(self):
        run = self.run_record()
        run["rule_ref"] = identity({"different": "rule_ref"})
        self.assert_ineligible(lambda: self.evaluate([run]))

    def test_changed_oracle_identity_is_not_admissible(self):
        run = self.run_record()
        run["oracle_ref"] = identity({"different": "oracle_ref"})
        self.assert_ineligible(lambda: self.evaluate([run]))

    def test_cost_dataset_mismatch_cannot_qualify_effect(self):
        run = self.run_record()
        cost = self.cost_report()
        cost["dataset_sha256"] = "f" * 64
        self.assert_ineligible(lambda: self.evaluate([run], cost=cost))


if __name__ == "__main__":
    unittest.main(verbosity=2)
