from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


SKILL_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_VALIDATOR = SKILL_ROOT / "scripts" / "validate_summary_output.py"
FORBIDDEN_STAGE_S_LOCAL_NAMES = {
    "frozen-thesis.pdf",
    "00-manifest.md",
    "01-policy-basis.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
    "02-page-layout-ledger.md",
    "02-page-layout-ledger.csv",
    "03-bibliography-audit-ledger.md",
    "03-bibliography-audit-ledger.csv",
    "04-citation-claim-audit-ledger.md",
    "04-citation-claim-audit-ledger.csv",
    "95-bundle-validation.md",
}


def load_summary_module():
    spec = importlib.util.spec_from_file_location(
        "test_summary_scoped_validator", SUMMARY_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Stage-S validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUMMARY_MODULE = load_summary_module()
FULL_MODULE = SUMMARY_MODULE.load_validator()


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


class ValidateSummaryOutputTests(unittest.TestCase):
    def build_bundle(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SUMMARY_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_valid_summary_passes_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            before = snapshot(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertEqual(before, snapshot(root))

    def test_summary_gate_does_not_enumerate_or_open_forbidden_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            original_iterdir = Path.iterdir
            original_is_file = Path.is_file
            original_read_text = Path.read_text
            original_read_bytes = Path.read_bytes

            def guard(path: Path) -> None:
                if path.name in FORBIDDEN_STAGE_S_LOCAL_NAMES:
                    raise AssertionError(f"Stage S opened forbidden input {path.name}")

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("Stage S enumerated the bundle root")
                return original_iterdir(path)

            def guarded_is_file(path: Path):
                guard(path)
                return original_is_file(path)

            def guarded_read_text(path: Path, *args, **kwargs):
                guard(path)
                return original_read_text(path, *args, **kwargs)

            def guarded_read_bytes(path: Path, *args, **kwargs):
                guard(path)
                return original_read_bytes(path, *args, **kwargs)

            with (
                mock.patch.object(Path, "iterdir", guarded_iterdir),
                mock.patch.object(Path, "is_file", guarded_is_file),
                mock.patch.object(Path, "read_text", guarded_read_text),
                mock.patch.object(Path, "read_bytes", guarded_read_bytes),
            ):
                errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertEqual([], errors)

    def test_summary_projection_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            csv_path = root / "93-current-actionable-items.csv"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    "correct the wording",
                    "different summary-only action",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("91->93 mismatch", result.stdout)

    def test_summary_gate_rejects_process_schema_drift_without_opening_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["unexpected_field"] = "must fail closed"
            process_path.write_text(
                json.dumps(process, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            original_is_file = Path.is_file
            original_read_bytes = Path.read_bytes

            def guarded_is_file(path: Path):
                if path.name == "frozen-thesis.pdf":
                    raise AssertionError("Stage S probed frozen PDF bytes")
                return original_is_file(path)

            def guarded_read_bytes(path: Path, *args, **kwargs):
                if path.name == "frozen-thesis.pdf":
                    raise AssertionError("Stage S opened frozen PDF bytes")
                return original_read_bytes(path, *args, **kwargs)

            with (
                mock.patch.object(Path, "is_file", guarded_is_file),
                mock.patch.object(Path, "read_bytes", guarded_read_bytes),
            ):
                errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertIn("process envelope schema mismatch", errors[0])


if __name__ == "__main__":
    unittest.main()
