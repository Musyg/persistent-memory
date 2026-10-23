"""Independent prospective API checks; Linux only, literal fake provider only.

Both qualified wheels are required. ACTION_SOURCE, ACTION_FIXTURE and
ACTION_BENCHMARK bind staged local files. No skips, network or credential reads.
Real phases and fresh Registry callbacks reuse the existing benchmark CLI.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
FENCE = chr(96) * 3


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def support_module():
    path = Path(os.environ.get("ACTION_SOURCE", str(ROOT / "SOURCE" / "action_transfer.py"))).resolve()
    if not path.is_file() or path.is_symlink():
        raise AssertionError("ACTION_SOURCE must bind a regular local source file")
    spec = importlib.util.spec_from_file_location("_independent_action_transfer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


class IndependentActionAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux":
            raise RuntimeError("Linux qualification only; no Windows execution")
        cls.action, cls.source = support_module()

    def test_single_object_presentation_is_not_a_business_gate(self):
        expected = {"schema": "artifact-actions-v1", "actions": []}
        raw = json.dumps(expected)
        cases = [(raw, "raw_json"), ("\n" + raw + "\n", "raw_json"),
                 (FENCE + "json\n" + raw + "\n" + FENCE, "json_fence"),
                 ("Prepared:\n" + FENCE + "JSON\n" + raw + "\n" + FENCE + "\nDone.", "json_fence"),
                 ("Here is the proposal:\n" + raw + "\nEnd.", "wrapped_json"),
                 ("x" * 512 + raw, "wrapped_json")]
        for text, presentation in cases:
            with self.subTest(presentation=presentation, chars=len(text)):
                value, parser = self.action.parse_proposal(text)
                self.assertEqual(value, expected)
                self.assertEqual(parser["format"], presentation)
                self.assertLessEqual(parser["wrapper_chars"], 512)

    def test_ambiguous_duplicate_nonfinite_or_incomplete_not_salvaged(self):
        raw = '{"schema":"artifact-actions-v1","actions":[]}'
        invalid = [raw + raw, "[" + raw + "]",
                   FENCE + "json\n" + raw + "\n" + FENCE + "\n" + FENCE + "json\n" + raw + "\n" + FENCE,
                   '{"schema":"artifact-actions-v1","actions":[],"actions":[]}',
                   '{"schema":"artifact-actions-v1","actions":[NaN]}',
                   raw[:-1], "x" * 513 + raw, "No object."]
        for text in invalid:
            with self.subTest(text=text[:64]):
                with self.assertRaises(ValueError):
                    self.action.parse_proposal(text)

    def test_complete_finite_shape_and_combined_byte_bounds(self):
        valid = {"op": "emit_json", "target": "config.json", "value": {"enabled": True, "hours": 31}}
        output = self.action.serialize_actions(
            {"schema": "artifact-actions-v1", "actions": [valid]}, ["config.json", "control.json"])
        self.assertEqual(output[0][1], b'{"enabled":true,"hours":31}\n')
        invalid = [
            {"schema": "artifact-actions-v1", "actions": [valid, valid]},
            {"schema": "artifact-actions-v1", "actions": [valid, {**valid, "target": "../escape.json"}]},
            {"schema": "artifact-actions-v1", "actions": [valid, {**valid, "target": "control.json", "op": "execute"}]},
            {"schema": "artifact-actions-v1", "actions": [valid, valid, valid]},
            {"schema": "artifact-actions-v1", "actions": [{**valid, "value": "not-an-object"}]},
            {"schema": "artifact-actions-v1", "actions": [{**valid, "value": {"x": "é" * 9000}}]},
        ]
        deep = {}
        for _ in range(10):
            deep = {"nested": deep}
        invalid.append({"schema": "artifact-actions-v1", "actions": [{**valid, "value": deep}]})
        for value in invalid:
            with self.subTest(value=str(value)[:100]):
                with self.assertRaises(ValueError):
                    self.action.serialize_actions(value, ["config.json", "control.json"])

    def test_csv_format_types_and_bounds(self):
        action = {"op": "emit_csv", "target": "export.csv", "columns": ["id", "label"],
                  "rows": [["é1", 'part;"quote"'], ["x2", "line\nnext"]],
                  "delimiter": ";", "encoding": "utf-8-sig"}
        payload = self.action.serialize_actions(
            {"schema": "artifact-actions-v1", "actions": [action]}, ["export.csv", "control.json"])[0][1]
        self.assertEqual(payload, b'\xef\xbb\xbfid;label\r\n\xc3\xa91;"part;""quote"""\r\nx2;"line\nnext"\r\n')
        for changes in ({"delimiter": "\n"}, {"columns": ["id", "id"]}, {"rows": [[1, "x"]]},
                        {"rows": [["x", "y"]] * 33}, {"encoding": "utf-16"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.action.serialize_actions(
                        {"schema": "artifact-actions-v1", "actions": [{**action, **changes}]},
                        ["export.csv", "control.json"])

    def test_typed_json_and_real_request_byte_cap(self):
        form = {"kind": "json", "value": {"enabled": True}}
        self.assertFalse(self.action._format_matches(b'{"enabled":1}\n', form))
        self.assertTrue(self.action._format_matches(b'{"enabled":true}\n', form))
        with self.assertRaises(ValueError):
            self.action._request_preflight("gpt-6-luna", "é" * 6000)


class IndependentProcessAndEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux":
            raise RuntimeError("Linux process qualification only; no Windows runtime and no skips")
        cls.action, cls.source = support_module()
        cls.fixture_path = Path(os.environ.get("ACTION_FIXTURE", str(ROOT / "FIXTURE.json"))).resolve()
        cls.benchmark = Path(os.environ.get("ACTION_BENCHMARK", str(ROOT / "run_benchmark.py"))).resolve()
        for path in (cls.fixture_path, cls.benchmark):
            if not path.is_file() or path.is_symlink():
                raise AssertionError("Bind regular local ACTION_FIXTURE and ACTION_BENCHMARK paths")
        cls.dataset = sha(cls.fixture_path.read_bytes())
        cls.fixture = json.loads(cls.fixture_path.read_bytes())
        cls.worlds = {world["world_id"]: world for world in cls.fixture["worlds"]}
        if sha(cls.benchmark.with_name("action_transfer.py").read_bytes()) != sha(cls.source.read_bytes()):
            raise AssertionError("CLI and direct API must bind identical support bytes")
        cls.cells = [{"cell_id": "independent-" + world["world_id"] + "-" + model + "-" + arm + "-" + str(rep),
                      "world_id": world["world_id"], "template_id": world["template_id"],
                      "model": model, "arm": arm, "repetition": rep}
                     for world in cls.fixture["worlds"] for model in cls.action.MODELS
                     for arm in cls.action.ARMS for rep in (1, 2, 3)]
        if len(cls.cells) != 576:
            raise AssertionError("Retain all original world/model/arm/repetition cells")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="independent-action-api-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.plan_path = self.directory / "PLAN.json"
        self.plan_path.write_bytes(encoded({"schema": "persistent-memory.action-transfer.plan.v1",
                                           "dataset_sha256": self.dataset, "cells": self.cells}))
        self.plan_sha = sha(self.plan_path.read_bytes())

    def _cell(self, world_id, arm="memory_on"):
        return next(cell for cell in self.cells if cell["world_id"] == world_id
                    and cell["model"] == "gpt-6-luna" and cell["arm"] == arm and cell["repetition"] == 1)

    def _proposal(self, world, cell, *, omit_control=False, wrong=False):
        # Oracle-derived literal fake answers qualify only the harness, never
        # model utility. They are authored in the trusted test parent.
        actions = []
        for target, expected in world["oracle"]["expected_files"].items():
            form = expected["format"]
            if form["kind"] == "json":
                value = {"deliberately_wrong": True} if wrong else copy.deepcopy(form["value"])
                actions.append({"op": "emit_json", "target": target, "value": value})
            else:
                actions.append({"op": "emit_csv", "target": target,
                                **{key: copy.deepcopy(form[key])
                                   for key in ("columns", "rows", "delimiter", "encoding")}})
        if not omit_control:
            actions.append({"op": "emit_json", "target": "control.json",
                            "value": {"cell_id": cell["cell_id"], "completed": True}})
        return json.dumps({"schema": "artifact-actions-v1", "actions": actions}, ensure_ascii=False)

    def _command(self, args):
        completed = subprocess.run([sys.executable, "-I", "-B", str(self.benchmark), *args],
            cwd=self.directory, env={"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr[-6000:])
        return json.loads(completed.stdout)

    def _execute(self, world_id, arm="memory_on", *, omit_control=False, wrong=False, incomplete=False):
        world, cell = self.worlds[world_id], self._cell(world_id, arm)
        folder = self.directory / cell["cell_id"]
        fake = self.directory / (cell["cell_id"] + "-FAKE.json")
        fake.write_bytes(encoded({"schema": "persistent-memory.action-transfer.fake-response.v1",
            "cell_id": cell["cell_id"], "body": self._proposal(world, cell, omit_control=omit_control, wrong=wrong),
            "finish_reason": "length" if incomplete else "stop"}))
        report = self._command(["--action-transfer", "--action-fixture", str(self.fixture_path),
            "--action-fixture-sha256", self.dataset, "--action-plan", str(self.plan_path),
            "--action-plan-sha256", self.plan_sha, "--action-cell-id", cell["cell_id"],
            "--action-output", str(folder), "--action-mode", "fake",
            "--action-fake-response", str(fake), "--action-fake-response-sha256", sha(fake.read_bytes())])
        p1, p2, p3 = [report["phases"][phase]["receipt"] for phase in ("observe", "propose", "verify")]
        self.assertEqual(len({p1["pid"], p2["pid"], p3["pid"]}), 3)
        self.assertLessEqual(report["exits"]["observe"]["exited_ns"], p2["started_ns"])
        self.assertLessEqual(report["exits"]["propose"]["exited_ns"], p3["started_ns"])
        self.assertFalse(report["provider_called"])
        self.assertTrue(report["fake_proof_only"])
        self.assertFalse(report["runtime_activated"])
        return {"world": world, "cell": cell, "folder": folder, "report": report, "p2": p2, "verification": p3}

    def _reopen(self, context):
        folder, report = context["folder"], context["report"]
        serial = len(list(folder.glob("fresh-verifier-*.json")))
        receipt = folder / ("fresh-verifier-" + str(serial) + ".json")
        return self._command(["--action-transfer", "--action-phase", "verify",
            "--action-input", str(folder / "verify" / "INPUT.json"),
            "--action-input-sha256", report["phases"]["verify"]["projection_sha256"],
            "--action-artifacts", str(folder / "artifacts"),
            "--action-prior-receipt", str(folder / "propose-receipt.json"),
            "--action-prior-receipt-sha256", report["phases"]["propose"]["receipt_sha256"],
            "--action-prior-exit", str(folder / "propose" / "EXIT.json"),
            "--action-prior-exit-sha256", sha((folder / "propose" / "EXIT.json").read_bytes()),
            "--action-output", str(receipt)])

    def test_phase_projection_has_no_oracle_or_hidden_assertion(self):
        world, cell = self.worlds["AT-C1-EN"], self._cell("AT-C1-EN")
        for phase, keys in (("observe", {"observations", "events"}), ("propose", {"task"})):
            projected = self.action.project_world(world, cell, phase,
                dataset_sha256=self.dataset, plan_sha256=self.plan_sha)
            self.assertEqual(set(projected["payload"]), keys)
            for hidden in ("oracle", "current_contract", "parameter_seed"):
                self.assertNotIn(hidden, projected)

    def test_six_selfcontained_briefs_and_positive_control_in_every_arm(self):
        worlds = [world for world in self.worlds.values() if world["family"] == "selfcontained"]
        self.assertEqual(len(worlds), 6)
        for world in worlds:
            self.assertNotIn("missing_current_contract", world["task"]["brief"])
            self.assertTrue(all(value is None for value in world["task"]["target_dependencies"].values()))
        for arm in self.action.ARMS:
            with self.subTest(arm=arm):
                verification = self._execute("AT-S2-EN", arm)["verification"]
                self.assertTrue(verification["task_success"])
                self.assertTrue(verification["checks"]["control.json"]["exact_bytes"])

    def test_revoked_hold_correct_only_with_positive_control(self):
        self.assertTrue(self._execute("AT-R1-FR", "memory_off")["verification"]["task_success"])
        missing = self._execute("AT-R1-EN", "memory_off", omit_control=True)["verification"]
        self.assertFalse(missing["task_success"])
        self.assertFalse(missing["checks"]["control.json"]["present"])
        self.assertTrue(missing["checks"]["unchanged:export.csv"]["exact_bytes"])

    def test_wrong_durable_effect_even_with_correct_control(self):
        verification = self._execute("AT-C1-EN", wrong=True)["verification"]
        self.assertTrue(verification["effect_verified"])
        self.assertFalse(verification["task_success"])
        self.assertFalse(verification["checks"]["config.json"]["typed_semantics"])
        self.assertTrue(verification["checks"]["control.json"]["exact_bytes"])

    def test_current_file_defeats_forged_old_receipt_even_at_same_byte_count(self):
        context = self._execute("AT-C1-FR")
        self.assertTrue(context["verification"]["task_success"])
        target = context["folder"] / "artifacts" / "config.json"
        original = target.read_bytes()
        value = json.loads(original)
        value["retention_hours"] += 1
        altered = encoded(value)
        self.assertEqual(len(altered), len(original))
        target.write_bytes(altered)
        actual = self._reopen(context)
        self.assertFalse(actual["effect_verified"])
        self.assertFalse(actual["task_success"])
        self.assertFalse(actual["checks"]["config.json"]["exact_bytes"])

    def test_complete_looking_length_response_is_not_salvaged(self):
        context = self._execute("AT-S2-FR", incomplete=True)
        self.assertEqual(context["p2"]["category"], "provider_incomplete")
        self.assertFalse(context["verification"]["task_success"])
        self.assertFalse((context["folder"] / "artifacts" / "control.json").exists())

    def test_actual_registry_24_worlds_fresh_callbacks_and_post_receipt_forgery(self):
        from hermes_policy_registry import Registry, PolicyError, identity, load_learning_records
        records = load_learning_records()
        contexts = {world["world_id"]: self._execute(world["world_id"]) for world in self.fixture["worlds"]}
        self.assertTrue(all(context["verification"]["task_success"] for context in contexts.values()))
        implementation = "sha256:" + sha(self.source.read_bytes())
        policy = {"id": "independent-action-fake-binding", "implementation_sha256": implementation[7:],
                  "budget": {"top_k": 5, "max_context_chars": 2000}}
        configuration = identity({"schema": "execution-policy-set-v1", "policy_refs": [identity(policy)]})
        rule = identity({"schema": "independent-action-rule-v1", "world_ids": sorted(contexts)})
        oracle = identity({"schema": "independent-action-oracle-v1",
                           "fixture_sha256": self.dataset, "verification": "fresh-existing-P3"})
        safety = identity({"authorization_changes": False, "fake_only": True})
        protocol = {"schema_version": 1, "family": "workflow", "safety_contract_ref": safety,
                    "judge": {"kind": "executable", "identifier": "native-workflow-effects-v1", "revision": "1"},
                    "rubric_refs": [oracle], "min_observed": 24,
                    "min_success_rate": 1.0, "max_unobserved": 0, "max_p95_ratio": 1000000000.0}
        registry = Registry.create(self.directory / "registry.sqlite", records, protocol)
        artifact = {"schema_version": 1, "family": "workflow", "name": "independent-action-binding",
                    "implementation_ref": implementation, "configuration_ref": configuration,
                    "safety_contract_ref": safety, "execution_policy_refs": [identity(policy)],
                    "dependencies": [rule, oracle, "sha256:" + self.dataset]}
        proposed = registry.propose(artifact)
        runs = [self.action.workflow_evidence(context["p2"], context["verification"],
                    records=records, policy=policy, implementation_ref=implementation,
                    configuration_ref=configuration, rule_ref=rule, oracle_ref=oracle,
                    created_at="2026-10-23T00:00:00Z") for context in contexts.values()]
        report_ref = registry.add_report({"schema": "native-workflow-effects-v1", "version": 1,
            "dataset_sha256": self.dataset, "rule_ref": rule, "oracle_ref": oracle, "runs": runs})
        callback_results = []

        def callback(envelope):
            began = time.monotonic_ns()
            fresh = self._reopen(contexts[envelope["run"]["task_id"]])
            self.assertGreaterEqual(fresh["started_ns"], began)
            self.assertNotEqual(fresh["pid"], os.getpid())
            checked = self.action.workflow_verifier_result(envelope, fresh, reopened_after_ns=began)
            callback_results.append(checked["status"])
            return checked

        def authority(refs):
            # Explicit synthetic callback, not production authorization.
            return {"status": "valid", "checked": list(refs)}

        event = self.action.evaluate_workflow_partition(registry, proposed["policy_ref"], report_ref,
                runs, proposed["seq"], authority, callback)
        assessment = registry.inspect(proposed["policy_ref"])["assessment"]
        self.assertEqual(callback_results, ["verified"] * 24)
        self.assertEqual(assessment["observed"], 24)
        self.assertEqual(assessment["successes"], 24)
        self.assertTrue(all(run["native_effect_verified"] for run in assessment["runs"]))
        self.assertFalse(assessment["eligible_for_admission_review"])
        self.assertIn("native_full_cost_unavailable", assessment["reasons"])
        with self.assertRaises(PolicyError):
            registry.admit(proposed["policy_ref"], event["seq"], authority)
        self.assertFalse(registry.inspect(proposed["policy_ref"])["runtime_activated"])

        # A formerly correct emitter label cannot defeat fresh actual-file checks.
        target = contexts["AT-C1-FR"]["folder"] / "artifacts" / "config.json"
        target.write_bytes(b'{"forged_after_initial_reopen":true}\n')
        callback_results.clear()
        self.action.evaluate_workflow_partition(registry, proposed["policy_ref"], report_ref,
                runs, event["seq"], authority, callback)
        rejected = registry.inspect(proposed["policy_ref"])["assessment"]
        self.assertEqual(callback_results.count("unverified"), 1)
        self.assertEqual(rejected["observed"], 23)
        self.assertIn("native_consumed_effect_or_reopen_unverified", rejected["reasons"])
        self.assertFalse(rejected["eligible_for_admission_review"])


if __name__ == "__main__":
    unittest.main()
