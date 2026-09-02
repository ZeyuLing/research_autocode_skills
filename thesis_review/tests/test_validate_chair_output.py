from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


CHAIR_VALIDATOR = (
    Path(__file__).resolve().parents[1] / "scripts" / "validate_chair_output.py"
)
SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_chair_module():
    spec = importlib.util.spec_from_file_location(
        "test_chair_scoped_validator", CHAIR_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Chair validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHAIR_MODULE = load_chair_module()


def snapshot(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative] = ("directory", "")
        else:
            result[relative] = (
                "file", hashlib.sha256(path.read_bytes()).hexdigest().upper()
            )
    return result


class ValidateChairOutputTests(unittest.TestCase):
    def build_chair_view_fixture(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)
        harness.convert_bundle_to_doctorate(root)
        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        opened = fixture_module.VALIDATOR_MODULE.canonical_stage_opened_inputs(
            process, 5, "C", None
        )
        for relative in opened:
            destination = root / relative
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative == "SKILL.md":
                source = SKILL_ROOT / "SKILL.md"
            elif relative in fixture_module.VALIDATOR_MODULE.SKILL_REFERENCE_FILES:
                source = SKILL_ROOT / "references" / relative
            elif relative.startswith("rules/scripts/"):
                source = SKILL_ROOT / "scripts" / Path(relative).name
            else:
                self.fail(f"synthetic fixture lacks canonical C input {relative}")
            shutil.copy2(source, destination)

        expected_files = set(opened) | set(CHAIR_MODULE.CHAIR_OUTPUTS)
        expected_directories = {
            Path(*Path(relative).parts[:index]).as_posix()
            for relative in expected_files
            for index in range(1, len(Path(relative).parts))
        }
        for path in sorted(
            root.rglob("*"),
            key=lambda item: len(item.relative_to(root).parts),
            reverse=True,
        ):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and relative not in expected_files:
                path.unlink()
            elif path.is_dir() and relative not in expected_directories:
                shutil.rmtree(path)

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(CHAIR_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def install_chair_helper(self, root: Path) -> list[str]:
        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        digest = str(process["selected_pdf_sha256"])
        base_opened = "; ".join(
            fixture_module.VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, 5, "C", None
            )
        )
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.install_helper_fixture(root, digest, recipients=["C"])
        full_opened_list = (
            fixture_module.VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, 5, "C", root
            )
        )
        full_opened = "; ".join(full_opened_list)
        for filename in (
            "90-chair-synthesis.md",
            "91-revision-ledger.md",
            "92-new-evidence-or-experiments.md",
        ):
            path = root / filename
            path.write_text(
                path.read_text(encoding="utf-8").replace(base_opened, full_opened),
                encoding="utf-8",
            )
        return [
            value for value in full_opened_list if value.startswith("helpers/")
        ]

    def test_valid_exact_private_chair_view_passes_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            before = snapshot(root)
            result = self.run_validator(root)
            after = snapshot(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertEqual(before, after)

            self.assertIn("not recomputed or semantically validated", result.stdout)

    def test_downstream_private_or_page_render_artifacts_are_forbidden(self) -> None:
        forbidden = (
            "93-user-facing-summary.md",
            "94-post-freeze-prior-issue-closure.md",
            "95-bundle-validation.md",
            "06-semantic-acceptance/SA-R1.md",
            "page-renders/P0001.png",
        )
        for relative in forbidden:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_chair_view_fixture(root)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("forbidden artifact\n", encoding="utf-8")
                result = self.run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
                self.assertIn("unallowlisted path", result.stdout)

    def test_upstream_or_chair_defect_is_not_waived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            chair = root / "90-chair-synthesis.md"
            chair.write_text(
                chair.read_text(encoding="utf-8").replace(
                    "## Overall risk and recommendation",
                    "## Renamed risk and recommendation",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("90-chair-synthesis.md", result.stdout)

    def test_process_json_rejects_duplicate_keys_before_substantive_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            process_path = root / "00-process-parameters.json"
            process_text = process_path.read_text(encoding="utf-8")
            process_path.write_text(
                process_text.replace(
                    '"degree_level": "doctorate",',
                    '"degree_level": "doctorate",\n  '
                    '"degree_level": "masters",',
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate JSON key 'degree_level'", result.stdout)

    def test_recomputes_process_and_sa_prompt_commitments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            process_path = root / "00-process-parameters.json"
            process_path.write_text(
                process_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "process_sha256 must equal", result.stdout
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["actor_prompt_sha256"]["SA-R1"] = "E" * 64
            process_path.write_text(
                json.dumps(process, indent=2), encoding="utf-8"
            )
            current_process_hash = hashlib.sha256(
                process_path.read_bytes()
            ).hexdigest().upper()
            gate_path = root / "06-semantic-acceptance-gate.json"
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            gate["process_sha256"] = current_process_hash
            gate_path.write_text(
                json.dumps(gate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "sa_actor_prompt_sha256 must exactly project", result.stdout
            )

    def test_private_acceptance_hash_is_only_a_transport_commitment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            gate_path = root / "06-semantic-acceptance-gate.json"
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            original = gate["targets"]["R1"]["acceptance_md_sha256"]
            replacement = "F" * 64 if original != "F" * 64 else "E" * 64
            gate["targets"]["R1"]["acceptance_md_sha256"] = replacement
            gate_path.write_text(
                json.dumps(gate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertIn("Stage-O transport commitments", result.stdout)

    def test_page_render_hash_is_not_recomputed_in_chair_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            gate_path = root / "06-semantic-acceptance-gate.json"
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            render_name = next(
                name for name in gate["targets"]["R5"]["target_artifacts"]
                if name.startswith("page-renders/")
            )
            gate["targets"]["R5"]["target_artifacts"][render_name] = "A" * 64
            gate_path.write_text(
                json.dumps(gate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("not recomputed or semantically validated", result.stdout)

    def test_visible_target_artifact_hash_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            gate_path = root / "06-semantic-acceptance-gate.json"
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            gate["targets"]["R1"]["target_artifacts"][
                "R1-comprehensive-review.md"
            ] = "A" * 64
            gate_path.write_text(
                json.dumps(gate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target artifact hash mismatch", result.stdout)

    def test_explicit_helper_sequence_is_required_and_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            helper_inputs = self.install_chair_helper(root)
            missing_args = self.run_validator(root)
            self.assertNotEqual(missing_args.returncode, 0)
            self.assertIn("unallowlisted directory", missing_args.stdout)

            command = [sys.executable, "-B", str(CHAIR_VALIDATOR), str(root)]
            for relative in helper_inputs:
                command.extend(["--helper-input", relative])
            valid = subprocess.run(
                command, text=True, capture_output=True, check=False
            )
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

            reversed_command = [
                sys.executable, "-B", str(CHAIR_VALIDATOR), str(root)
            ]
            for relative in reversed(helper_inputs):
                reversed_command.extend(["--helper-input", relative])
            invalid = subprocess.run(
                reversed_command, text=True, capture_output=True, check=False
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("canonical C-recipient helper", invalid.stdout)

    def test_chair_csv_schema_defect_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            ledger = root / "91-revision-ledger.csv"
            ledger.write_text(
                ledger.read_text(encoding="utf-8").replace(
                    "LedgerID,", "WrongLedgerID,", 1
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("schema mismatch", result.stdout)

    def test_extra_file_is_rejected_before_its_bytes_are_opened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            extra = root / "forbidden-secret.txt"
            extra.write_bytes(b"must never be opened")
            opened_paths: list[Path] = []
            original_os_open = fixture_module.VALIDATOR_MODULE.os.open

            def recording_open(path, *args, **kwargs):
                opened_paths.append(Path(path))
                return original_os_open(path, *args, **kwargs)

            semantic = CHAIR_MODULE.load_module(
                CHAIR_MODULE.SEMANTIC_VALIDATOR,
                "test_semantic_for_closed_boundary",
            )
            with mock.patch.object(
                fixture_module.VALIDATOR_MODULE.os,
                "open",
                side_effect=recording_open,
            ):
                errors = CHAIR_MODULE.validate_chair(
                    root, fixture_module.VALIDATOR_MODULE, semantic
                )
            self.assertTrue(any("unallowlisted path" in item for item in errors))
            self.assertNotIn(extra, opened_paths)

    def test_misdirected_final_round_never_descends_into_private_sa_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            private_sa = root / "06-semantic-acceptance"
            private_sa.mkdir()
            secret = private_sa / "SA-R1.md"
            secret.write_bytes(b"must not be enumerated or opened")
            visited_directories: list[Path] = []
            opened_paths: list[Path] = []
            path_type = type(root)
            original_iterdir = path_type.iterdir
            original_os_open = fixture_module.VALIDATOR_MODULE.os.open

            def guarded_iterdir(path):
                visited_directories.append(Path(path))
                if Path(path) == private_sa:
                    raise AssertionError("validator descended into private SA directory")
                return original_iterdir(path)

            def recording_open(path, *args, **kwargs):
                opened_paths.append(Path(path))
                return original_os_open(path, *args, **kwargs)

            semantic = CHAIR_MODULE.load_module(
                CHAIR_MODULE.SEMANTIC_VALIDATOR,
                "test_semantic_for_no_sa_descent",
            )
            with mock.patch.object(path_type, "iterdir", new=guarded_iterdir), mock.patch.object(
                fixture_module.VALIDATOR_MODULE.os,
                "open",
                side_effect=recording_open,
            ):
                errors = CHAIR_MODULE.validate_chair(
                    root, fixture_module.VALIDATOR_MODULE, semantic
                )
            self.assertTrue(
                any("unallowlisted directory" in item for item in errors), errors
            )
            self.assertNotIn(private_sa, visited_directories)
            self.assertNotIn(secret, opened_paths)

    def test_early_semantic_failure_still_runs_terminal_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_chair_view_fixture(root)
            semantic = CHAIR_MODULE.load_module(
                CHAIR_MODULE.SEMANTIC_VALIDATOR,
                "test_semantic_for_terminal_closure",
            )
            original_scan = CHAIR_MODULE._scan_exact_tree
            with mock.patch.object(
                CHAIR_MODULE,
                "validate_process_and_pdf",
                return_value=("", 0),
            ), mock.patch.object(
                CHAIR_MODULE,
                "_scan_exact_tree",
                wraps=original_scan,
            ) as scan:
                CHAIR_MODULE.validate_chair(
                    root, fixture_module.VALIDATOR_MODULE, semantic
                )
            self.assertGreaterEqual(
                scan.call_count,
                2,
                "preflight and terminal tree closure must both run",
            )


if __name__ == "__main__":
    unittest.main()
