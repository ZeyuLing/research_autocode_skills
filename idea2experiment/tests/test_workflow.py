from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class WorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.code_repo = self.workspace / "code"
        self.code_repo.mkdir()
        result = self.script(
            "init_study.py",
            "--idea",
            "Test whether model capacity, data composition, and two modules improve a generic task.",
            "--out-dir",
            str(self.workspace),
            "--study-name",
            "workflow-test",
            "--code-repo",
            str(self.code_repo),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.study_root = self.workspace / "workflow-test"
        self.configure_study()

    def script(self, name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *arguments],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )

    def configure_study(self) -> None:
        study_path = self.study_root / "study.json"
        study = read_json(study_path)
        study.update(
            {
                "claims": [
                    {
                        "id": "C1",
                        "text": "The method improves the primary metric and exhibits interpretable scaling behavior.",
                        "type": "performance",
                        "required_families": [
                            "model_scaling",
                            "data_scaling",
                            "module_study",
                            "parameter_sensitivity",
                        ],
                    }
                ],
                "baselines": [{"id": "base", "primary": True, "source": "local"}],
                "model_scaling": {
                    "status": "required",
                    "reason": "",
                    "axes": ["parameters"],
                    "protocols": ["fixed_tokens"],
                    "rungs": [{"id": "S0", "parameters": 1000}, {"id": "S1", "parameters": 2000}],
                },
                "data_scaling": {
                    "status": "required",
                    "reason": "",
                    "protocols": ["fixed_tokens"],
                    "rungs": [{"id": "D0", "examples": 16}, {"id": "D1", "examples": 32}],
                    "sources": [{"id": "A"}, {"id": "B"}],
                    "mixtures": [],
                },
                "modules": [
                    {"id": "A", "core": True, "mechanism": "first mechanism"},
                    {"id": "B", "core": True, "mechanism": "second mechanism"},
                ],
                "module_study": {"status": "required", "reason": ""},
                "hyperparameters": {
                    "nuisance": [{"name": "learning_rate", "values": [0.001, 0.0001], "scale": "log"}],
                    "scientific": [{"name": "alpha", "values": [0.0, 0.5, 1.0], "scale": "linear"}],
                },
                "parameter_study": {"status": "required", "reason": ""},
                "statistics": {
                    "primary_metric": "score",
                    "direction": "maximize",
                    "unit_of_analysis": "example",
                    "seed_policy": {
                        "mode": "fixed",
                        "pilot_seeds": [0, 1, 2],
                        "confirmatory_minimum": 3,
                        "confirmatory_maximum": 3,
                        "confirmatory_seeds": [11, 12, 13],
                    },
                    "final_test_policy": "frozen",
                },
                "adapter": "adapters/local.json",
                "additional_families": [
                    {
                        "family": "robustness",
                        "id": "shift",
                        "hypothesis": "The selected method remains stable under the declared distribution shift.",
                    },
                    {"family": "qualitative", "id": "cases"},
                ],
            }
        )
        write_json(study_path, study)

        digest = "sha256:" + "a" * 64
        protocol = read_json(self.study_root / "protocols" / "protocol.json")
        protocol.update(
            {
                "status": "frozen",
                "split_hash": digest,
                "preprocessing_hash": digest,
                "evaluator_hash": digest,
                "aggregation_hash": digest,
                "final_test_policy": "frozen",
            }
        )
        write_json(self.study_root / "protocols" / "protocol.json", protocol)

        command = (
            "import json,os,pathlib; "
            "p=pathlib.Path(os.environ['I2E_RUN_DIR'])/'metrics.json'; "
            "p.write_text(json.dumps({'score': 1.0}), encoding='utf-8')"
        )
        adapter = {
            "version": 1,
            "name": "test-local",
            "working_directory": str(self.code_repo),
            "commands": {"default": [sys.executable, "-c", command]},
            "required_outputs": [],
            "timeout_seconds": 30,
        }
        write_json(self.study_root / "adapters" / "local.json", adapter)

    def plan(self) -> dict:
        result = self.script("plan_experiments.py", str(self.study_root))
        self.assertEqual(result.returncode, 0, result.stderr)
        return read_json(self.study_root / "experiments" / "experiment_graph.json")

    @staticmethod
    def ancestors(graph: dict, experiment_id: str) -> set[str]:
        parents = {node["id"]: node["parents"] for node in graph["nodes"]}
        pending = list(parents[experiment_id])
        result: set[str] = set()
        while pending:
            item = pending.pop()
            if item not in result:
                result.add(item)
                pending.extend(parents[item])
        return result

    def test_planner_generates_complete_gated_dag_and_strict_validation(self) -> None:
        graph = self.plan()
        by_id = {node["id"]: node for node in graph["nodes"]}
        families = {node["family"] for node in graph["nodes"]}

        self.assertTrue(
            {
                "deterministic_sanity",
                "tiny_overfit",
                "baseline_reproduction",
                "pilot",
                "model_scaling",
                "data_scaling",
                "data_mixture",
                "module_study",
                "parameter_search",
                "parameter_sensitivity",
                "confirmatory",
                "robustness",
                "qualitative",
                "independent_audit",
                "claim_sync",
            }.issubset(families)
        )
        self.assertEqual(sum(node["family"] == "module_study" for node in graph["nodes"]), 4)
        self.assertIn("E_TINY_OVERFIT_1", self.ancestors(graph, "E_BASELINE_BASE"))
        self.assertIn("E_BASELINE_BASE", self.ancestors(graph, "E_PILOT_SMALL"))
        self.assertIn("E_PILOT_SMALL", self.ancestors(graph, "E_CONFIRMATORY_SEED_11"))
        self.assertIn("E_INDEPENDENT_AUDIT", self.ancestors(graph, "E_CLAIM_SYNC"))
        self.assertTrue(all(node["protocol_hash"] for node in graph["nodes"]))
        self.assertEqual(by_id["E_TINY_OVERFIT_8"]["parents"], ["E_TINY_OVERFIT_1"])

        validation = self.script("validate_study.py", str(self.study_root), "--strict", "--json")
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
        self.assertTrue(json.loads(validation.stdout)["valid"])

    def test_runner_records_artifacts_and_dry_run_reports_blocked_parents(self) -> None:
        self.plan()
        ready_before = self.script("next_experiments.py", str(self.study_root), "--json")
        self.assertEqual(ready_before.returncode, 0, ready_before.stdout + ready_before.stderr)
        self.assertEqual([item["id"] for item in json.loads(ready_before.stdout)["ready"]], ["E_SANITY_DETERMINISTIC"])
        run = self.script("run_experiment.py", str(self.study_root), "E_SANITY_DETERMINISTIC")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        run_dir = Path(result["run_dir"])
        self.assertEqual(result["status"], "DONE")
        self.assertTrue((run_dir / "metrics.json").is_file())
        self.assertTrue((run_dir / "artifact_hashes.json").is_file())
        self.assertEqual(read_json(run_dir / "manifest.json")["protocol_hash"], read_json(run_dir / "resolved_command.json")["protocol_hash"])

        ready_after = self.script("next_experiments.py", str(self.study_root), "--json")
        self.assertEqual(ready_after.returncode, 0, ready_after.stdout + ready_after.stderr)
        self.assertEqual([item["id"] for item in json.loads(ready_after.stdout)["ready"]], ["E_TINY_OVERFIT_1"])

        dry_run = self.script("run_experiment.py", str(self.study_root), "E_PILOT_SMALL", "--dry-run")
        self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
        preview = json.loads(dry_run.stdout)
        self.assertTrue(preview["unsatisfied_parents"])
        self.assertFalse((self.study_root / "runs" / "E_PILOT_SMALL").exists())

        validation = self.script("validate_study.py", str(self.study_root), "--strict")
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

    def test_protocol_drift_blocks_execution_without_deleting_prior_runs(self) -> None:
        self.plan()
        first = self.script("run_experiment.py", str(self.study_root), "E_SANITY_DETERMINISTIC")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        prior_run_dir = Path(json.loads(first.stdout)["run_dir"])

        protocol_path = self.study_root / "protocols" / "protocol.json"
        protocol = read_json(protocol_path)
        protocol["aggregation_hash"] = "sha256:" + "b" * 64
        write_json(protocol_path, protocol)

        blocked = self.script("run_experiment.py", str(self.study_root), "E_TINY_OVERFIT_1")
        self.assertNotEqual(blocked.returncode, 0)
        graph = read_json(self.study_root / "experiments" / "experiment_graph.json")
        node = next(item for item in graph["nodes"] if item["id"] == "E_TINY_OVERFIT_1")
        self.assertEqual(node["status"], "INVALID_PROTOCOL")
        self.assertTrue(prior_run_dir.is_dir())

        invalidate = self.script(
            "state_manager.py",
            "invalidate",
            str(self.study_root),
            "--stage",
            "PROTOCOL_FREEZE",
            "--reason",
            "protocol changed in test",
        )
        self.assertEqual(invalidate.returncode, 0, invalidate.stdout + invalidate.stderr)
        self.assertTrue(prior_run_dir.is_dir())
        state = read_json(self.study_root / "state.json")
        self.assertEqual(state["stages"]["PROTOCOL_FREEZE"]["status"], "invalidated")

    def test_failed_node_requires_an_explicit_retry_reason(self) -> None:
        self.plan()
        mark_failed = self.script(
            "state_manager.py",
            "experiment",
            str(self.study_root),
            "--id",
            "E_SANITY_DETERMINISTIC",
            "--status",
            "FAILED_ENGINEERING",
            "--reason",
            "simulated transient failure",
        )
        self.assertEqual(mark_failed.returncode, 0, mark_failed.stdout + mark_failed.stderr)
        refused = self.script("run_experiment.py", str(self.study_root), "E_SANITY_DETERMINISTIC")
        self.assertNotEqual(refused.returncode, 0)

        retried = self.script(
            "run_experiment.py",
            str(self.study_root),
            "E_SANITY_DETERMINISTIC",
            "--retry-reason",
            "verified transient worker failure",
        )
        self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
        run_dir = Path(json.loads(retried.stdout)["run_dir"])
        manifest = read_json(run_dir / "manifest.json")
        self.assertEqual(manifest["retry_of_status"], "FAILED_ENGINEERING")
        self.assertEqual(manifest["retry_reason"], "verified transient worker failure")


if __name__ == "__main__":
    unittest.main()
