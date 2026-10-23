"""Independent pure-analysis tests over explicitly SYNTHETIC UNIT DATA.

No rows below are model observations, provider responses, process receipts or
campaign measurements. The paid-mode flag only exercises accounting branches.
Only the immutable fixture/plan layout is reused. Runtime: Linux, no network.
ACTION_ANALYSIS/ACTION_FIXTURE/ACTION_PLAN/ACTION_VOLUME_ANALYSIS bind local files.
"""
import copy
from decimal import Decimal
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VOLUME_PIN = "edb74bc815cb35e56e68b7b78d2af9b76eb396b08a9e62d787e18df9ec87c7f6"
UNIT_ONLY = "synthetic_unit_data_not_provider_observations"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_local(path, name, expected_pin=None):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise AssertionError("Tests require explicitly bound regular local files")
    if expected_pin is not None and sha(path.read_bytes()) != expected_pin:
        raise AssertionError("The existing interval helper must match its immutable source pin")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IndependentActionAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux":
            raise RuntimeError("Linux qualification only; do not run these tests on Windows")
        analysis_path = os.environ.get("ACTION_ANALYSIS", str(ROOT / "ANALYSIS-FUNCTION.py"))
        volume_path = os.environ.get("ACTION_VOLUME_ANALYSIS")
        if volume_path is None:
            raise AssertionError("Bind ACTION_VOLUME_ANALYSIS to the frozen existing helper")
        cls.calculate = staticmethod(load_local(analysis_path, "_independent_action_analysis").calculate_action_transfer)
        helper = load_local(volume_path, "_independent_action_volume", VOLUME_PIN).primary_interval
        fixture_path = Path(os.environ.get("ACTION_FIXTURE", str(ROOT / "FIXTURE.json")))
        plan_path = Path(os.environ.get("ACTION_PLAN", str(ROOT / "PLAN.json")))
        for path in (fixture_path, plan_path):
            if not path.is_file() or path.is_symlink():
                raise AssertionError("Bind immutable fixture/plan local files")
        cls.fixture_raw, cls.plan_raw = fixture_path.read_bytes(), plan_path.read_bytes()
        cls.dataset_pin, cls.plan_pin = sha(cls.fixture_raw), sha(cls.plan_raw)
        cls.fixture, cls.plan = json.loads(cls.fixture_raw), json.loads(cls.plan_raw)
        cls.worlds = {world["world_id"]: world for world in cls.fixture["worlds"]}
        if len(cls.plan["cells"]) != 576 or cls.plan["dataset_sha256"] != cls.dataset_pin:
            raise AssertionError("The complete original prospective plan must be retained")

        @functools.lru_cache(maxsize=128)
        def existing_interval(metadata_raw, scores_raw, samples, seed):
            # Reuse only identical calls to the exact existing deterministic
            # helper. No alternative interval or bootstrap is implemented.
            return helper(json.loads(metadata_raw), json.loads(scores_raw), samples=samples, seed=seed)

        def interval(metadata, scores, *, samples, seed):
            return copy.deepcopy(existing_interval(
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                json.dumps(scores, sort_keys=True, separators=(",", ":")), samples, seed))

        cls.interval = staticmethod(interval)
        cls.synthetic = cls.make_synthetic_rows()
        cls.baseline = cls.calculate(cls.synthetic, cls.fixture_raw, cls.plan_raw, primary_interval=cls.interval)

    @classmethod
    def make_synthetic_rows(cls):
        """Fabricate all metadata in memory; never persist as campaign evidence."""
        rows = []
        for index, cell in enumerate(cls.plan["cells"]):
            start, pid = 1000 + index * 1000, 2000 + index * 3
            context = "" if cell["arm"] == "memory_off" else UNIT_ONLY
            items = [] if not context else [{"ref": {"workspace": cls.worlds[cell["world_id"]]["workspace"],
                      "artifact_id": "unit-only-source", "version_id": "00000000-0000-4000-8000-000000000001"},
                      "text": UNIT_ONLY, "metadata": {"evidence_kind": "observation"}}]
            consume = {
                "schema": "persistent-memory.action-transfer.consume-receipt.v1",
                "cell": copy.deepcopy(cell), "dataset_sha256": cls.dataset_pin, "plan_sha256": cls.plan_pin,
                "mode": "paid", "fake_proof_only": False, "provider_called": True,
                "status": "completed", "category": UNIT_ONLY,
                "started_ns": start, "ended_ns": start + 15, "pid": pid + 1,
                "p1_exit": {"pid": pid, "returncode": 0, "exited_ns": start - 10},
                "packet": {"arm": cell["arm"], "context": context, "items": items,
                           "context_chars": len(context), "context_utf8_bytes": len(context.encode("utf-8"))},
                "preflight": {"full_request_bytes": 1200, "input_token_upper_bound": 2224,
                              "request_sha256": "e" * 64},
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                          "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 0, "audio_tokens": 0},
                          "completion_tokens_details": {"reasoning_tokens": 30, "audio_tokens": 0,
                              "accepted_prediction_tokens": 0, "rejected_prediction_tokens": 0}},
            }
            verification = {
                "schema": "persistent-memory.action-transfer.verification.v1",
                "cell": copy.deepcopy(cell), "dataset_sha256": cls.dataset_pin, "plan_sha256": cls.plan_pin,
                "fake_proof_only": False, "task_success": True, "effect_verified": True,
                "category": UNIT_ONLY, "pid": pid + 2, "started_ns": start + 17, "ended_ns": start + 20,
                "p2_exit": {"pid": pid + 1, "returncode": 0, "exited_ns": start + 16},
                "checks": {"control.json": {"present": True, "exact_bytes": True}},
            }
            rows.append({"cell": copy.deepcopy(cell), "dataset_sha256": cls.dataset_pin,
                         "plan_sha256": cls.plan_pin, "consume": consume, "verification": verification,
                         "emission_status": "confirmed_emitted", "terminal_category": UNIT_ONLY})
        return {"schema": "persistent-memory.action-transfer.observations.v1",
                "dataset_sha256": cls.dataset_pin, "plan_sha256": cls.plan_pin, "mode": "paid", "rows": rows}

    def analyze(self, data, *, fixture_raw=None, plan_raw=None):
        return self.calculate(data, self.fixture_raw if fixture_raw is None else fixture_raw,
                              self.plan_raw if plan_raw is None else plan_raw, primary_interval=self.interval)

    def first_row(self, data, model="gpt-6-luna"):
        return next(row for row in data["rows"] if row["cell"]["model"] == model)

    @staticmethod
    def episode(report, cell_id):
        return next(row for row in report["episodes"] if row["cell_id"] == cell_id)

    def test_complete_denominators_lineage_and_known_accounting(self):
        result = self.baseline
        self.assertEqual((result["planned_cells"], result["worlds"], result["template_clusters"],
                          result["families"], result["repetitions"]), (576, 24, 12, 4, 3))
        self.assertEqual(len(result["episodes"]), 576)
        self.assertEqual(len(result["groups"]), 8)
        self.assertEqual(len(result["contrasts"]), 6)
        self.assertEqual(result["overall"]["success"], 576)
        self.assertEqual(result["overall"]["observed_tokens_known_subtotal"],
                         {"prompt_tokens": 57600, "completion_tokens": 28800, "total_tokens": 86400})
        self.assertEqual(Decimal(result["overall"]["known_generation_estimate_usd"]), Decimal("0.2002176"))
        self.assertEqual(result["overall"]["generation_estimate_coverage"], 576)
        self.assertIsNone(result["actual_billed_usd"])
        for group in result["groups"]:
            self.assertEqual(group["planned"], 72)
            self.assertEqual(group["template_clusters"], 12)
            self.assertEqual([family["planned"] for family in group["families"]], [18] * 4)
        for contrast in result["contrasts"]:
            self.assertEqual(contrast["statistics"]["bootstrap_samples"], 10000)
            self.assertEqual(contrast["statistics"]["bootstrap_seed"], 20261023)
            self.assertEqual(contrast["statistics"]["effect_uncertainty_interval_95"], [0.0, 0.0])
        self.assertFalse(result["limits"]["quality_noninferiority_confirmed"])
        self.assertFalse(result["limits"]["equal_spend_comparison"])
        json.dumps(result, allow_nan=False)

    def test_duplicate_missing_model_pin_and_metadata_mismatches_rejected(self):
        variants = []
        value = copy.deepcopy(self.synthetic); value["rows"][-1] = copy.deepcopy(value["rows"][0]); variants.append(value)
        value = copy.deepcopy(self.synthetic); value["rows"].pop(); variants.append(value)
        value = copy.deepcopy(self.synthetic); value["dataset_sha256"] = "0" * 64; variants.append(value)
        value = copy.deepcopy(self.synthetic); value["rows"][0]["plan_sha256"] = "0" * 64; variants.append(value)
        value = copy.deepcopy(self.synthetic); value["rows"][0]["consume"]["cell"]["model"] = "wrong-model"; variants.append(value)
        value = copy.deepcopy(self.synthetic); value["rows"][0]["verification"]["dataset_sha256"] = "0" * 64; variants.append(value)
        value = copy.deepcopy(self.synthetic); value["rows"][0]["consume"]["provider_called"] = False; variants.append(value)
        for index, value in enumerate(variants):
            with self.subTest(mutation=index):
                with self.assertRaises(ValueError):
                    self.analyze(value)
        bad_plan = copy.deepcopy(self.plan)
        bad_plan["cells"][0]["model"] = "wrong-model"
        with self.assertRaises(ValueError):
            self.analyze(self.synthetic, plan_raw=json.dumps(bad_plan).encode("utf-8"))

    def test_verified_wrong_is_false_incomplete_and_unexecuted_are_unknown(self):
        value = copy.deepcopy(self.synthetic)
        wrong, incomplete, unexecuted, control_failed = value["rows"][:4]
        wrong["verification"]["task_success"] = False
        wrong["verification"]["category"] = wrong["terminal_category"] = "synthetic_unit_wrong_proposal"
        incomplete["consume"]["status"] = "unavailable"
        incomplete["consume"]["category"] = "provider_incomplete"
        incomplete["verification"].update(task_success=False, category="provider_incomplete")
        incomplete["verification"]["checks"]["control.json"] = {"present": False, "exact_bytes": False}
        incomplete["terminal_category"] = "provider_incomplete"
        unexecuted.update(consume=None, verification=None, emission_status="not_executed",
                          terminal_category="synthetic_unit_not_executed")
        control_failed["verification"]["task_success"] = False
        control_failed["verification"]["checks"]["control.json"] = {"present": False, "exact_bytes": False}
        result = self.analyze(value)
        self.assertIs(self.episode(result, wrong["cell"]["cell_id"])["success"], False)
        self.assertIsNone(self.episode(result, incomplete["cell"]["cell_id"])["success"])
        self.assertIsNone(self.episode(result, unexecuted["cell"]["cell_id"])["success"])
        self.assertEqual({key: result["overall"][key] for key in ("success", "failure", "unknown")},
                         {"success": 572, "failure": 2, "unknown": 2})
        self.assertEqual([result["overall"][key] for key in ("control_success", "control_failure", "control_unknown")],
                         [573, 2, 1])
        self.assertEqual(result["overall"]["success_fraction_bounds"], [572 / 576, 574 / 576])

    def test_success_requires_positive_control_and_completed_verified_effect(self):
        for field in ("control", "unverified", "unavailable"):
            value = copy.deepcopy(self.synthetic)
            row = value["rows"][0]
            if field == "control":
                row["verification"]["checks"]["control.json"]["exact_bytes"] = False
            elif field == "unverified":
                row["verification"]["effect_verified"] = False
            else:
                row["consume"]["status"] = "unavailable"
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.analyze(value)

    def test_cached_input_discount_and_reasoning_not_double_charged(self):
        value = copy.deepcopy(self.synthetic)
        for model, expected in (("gpt-6-luna", "0.000035"), ("gpt-6.1-sol", "0.0007")):
            row = self.first_row(value, model)
            row["consume"]["usage"]["prompt_tokens_details"]["cached_tokens"] = 0
            row["consume"]["usage"]["completion_tokens_details"]["reasoning_tokens"] = 0
        result = self.analyze(value)
        for model, expected in (("gpt-6-luna", "0.000035"), ("gpt-6.1-sol", "0.0007")):
            cell_id = self.first_row(value, model)["cell"]["cell_id"]
            self.assertEqual(Decimal(self.episode(result, cell_id)["estimated_generation_usd"]), Decimal(expected))
        reasoning_only = copy.deepcopy(self.synthetic)
        self.first_row(reasoning_only)["consume"]["usage"]["completion_tokens_details"]["reasoning_tokens"] = 0
        self.assertEqual(self.analyze(reasoning_only)["overall"]["known_generation_estimate_usd"],
                         self.baseline["overall"]["known_generation_estimate_usd"])

    def test_cache_write_missing_usage_and_unknown_emission_not_priced_as_zero(self):
        value = copy.deepcopy(self.synthetic)
        written, missing, unknown = value["rows"][:3]
        written["consume"]["usage"]["prompt_tokens_details"]["cache_write_tokens"] = 1
        missing["consume"]["usage"] = None
        unknown.update(consume=None, verification=None, emission_status="unknown",
                       terminal_category="synthetic_unit_uncertain_emission")
        result = self.analyze(value)
        for row in (written, missing, unknown):
            self.assertIsNone(self.episode(result, row["cell"]["cell_id"])["estimated_generation_usd"])
        self.assertFalse(result["overall"]["generation_estimate_complete_for_emissions"])
        self.assertIsNone(result["overall"]["estimated_usd_per_conforming_task"])
        self.assertEqual(result["overall"]["generation_estimate_coverage"], 573)

    def test_offline_cli_reproduces_calculation_and_rejects_incompatible_modes(self):
        benchmark = Path(os.environ['ACTION_BENCHMARK']).resolve()
        with tempfile.TemporaryDirectory(prefix='synthetic-analysis-cli-only-') as folder:
            path = Path(folder) / 'SYNTHETIC-UNIT-ONLY.json'
            raw = (json.dumps(self.synthetic, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
            path.write_bytes(raw)
            command = [sys.executable, '-I', '-B', str(benchmark), '--action-report', str(path),
                       '--action-report-sha256', sha(raw)]
            result = subprocess.run(command, cwd=folder, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            report = json.loads(result.stdout)
            provenance = report.pop('provenance')
            self.assertEqual(provenance['observations_sha256'], sha(raw))
            self.assertEqual(report, self.baseline)
            explicit = ['--action-fixture', os.environ['ACTION_FIXTURE'],
                        '--action-fixture-sha256', self.dataset_pin,
                        '--action-plan', os.environ['ACTION_PLAN'],
                        '--action-plan-sha256', self.plan_pin]
            reproduced = subprocess.run(command + explicit, cwd=folder, capture_output=True, timeout=60)
            self.assertEqual(reproduced.returncode, 0, reproduced.stderr.decode())
            self.assertEqual(json.loads(reproduced.stdout), json.loads(result.stdout))
            rejected = subprocess.run(command + explicit[:2], cwd=folder, capture_output=True, timeout=15)
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse(rejected.stdout)
            for options in (['--efficiency'], ['--action-mode', 'fake']):
                rejected = subprocess.run(command + options, cwd=folder, capture_output=True, timeout=15)
                self.assertEqual(rejected.returncode, 2)
                self.assertFalse(rejected.stdout)
            wrong_pin = command[:-1] + ['0' * 64]
            rejected = subprocess.run(wrong_pin, cwd=folder, capture_output=True, timeout=15)
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse(rejected.stdout)

    def test_invalid_usage_details_never_enter_known_subtotals(self):
        invalid = [("completion_tokens_details", "reasoning_tokens", -1, "reasoning_tokens", 30),
                   ("completion_tokens_details", "reasoning_tokens", 51, "reasoning_tokens", 30),
                   ("prompt_tokens_details", "cached_tokens", -1, "cached_tokens", 20),
                   ("prompt_tokens_details", "cached_tokens", 101, "cached_tokens", 20),
                   ("prompt_tokens_details", "cache_write_tokens", -1, "cache_write_tokens", 0)]
        for section, field, bad, reported_field, normal in invalid:
            value = copy.deepcopy(self.synthetic)
            row = value["rows"][0]
            row["consume"]["usage"][section][field] = bad
            with self.subTest(field=field, invalid_value=bad):
                result = self.analyze(value)
                usage = self.episode(result, row["cell"]["cell_id"])["usage"]
                self.assertIsNone(usage[reported_field])
                self.assertEqual(result["overall"]["usage_detail_coverage"][reported_field], 575)
                self.assertEqual(result["overall"]["observed_detail_known_subtotals"][reported_field], 575 * normal)
                self.assertIsNone(self.episode(result, row["cell"]["cell_id"])["estimated_generation_usd"])
                json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
