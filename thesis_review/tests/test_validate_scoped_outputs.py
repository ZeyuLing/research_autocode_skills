from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


SKILL_ROOT = Path(__file__).resolve().parents[1]
REVIEWER_VALIDATOR = SKILL_ROOT / "scripts" / "validate_reviewer_output.py"
AI_VALIDATOR = SKILL_ROOT / "scripts" / "validate_ai_output.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load synthetic-test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REVIEWER_MODULE = load_module(REVIEWER_VALIDATOR, "test_scoped_reviewer_module")
AI_MODULE = load_module(AI_VALIDATOR, "test_scoped_ai_module")
FULL_MODULE = REVIEWER_MODULE.load_validator()


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


class ValidateScopedOutputsTests(unittest.TestCase):
    def build_bundle(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)

    def run_reviewer(
        self, root: Path, actor_id: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(REVIEWER_VALIDATOR), str(root), actor_id],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_ai(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(AI_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_ordinary_reviewer_passes_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            before = snapshot(root)
            result = self.run_reviewer(root, "R1")
            after = snapshot(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertEqual(before, after)

    def test_ordinary_reviewer_and_ai_do_not_enumerate_round_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            original_iterdir = Path.iterdir

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("scoped gate enumerated the bundle root")
                return original_iterdir(path)

            with mock.patch.object(Path, "iterdir", guarded_iterdir):
                reviewer_errors = REVIEWER_MODULE.validate_reviewer(
                    root, "R1", FULL_MODULE
                )
                ai_result = AI_MODULE.main([str(root)])
            self.assertEqual([], reviewer_errors)
            self.assertEqual(0, ai_result)

    def test_ordinary_reviewer_closed_schema_defect_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R2-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "## Whole-thesis synthesis",
                    "## Renamed thesis synthesis",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_reviewer(root, "R2")
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("Whole-thesis synthesis", result.stdout)

    def test_ledger_owner_cannot_use_ordinary_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            result = self.run_reviewer(root, "R3")
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("dedicated ledger-aware scoped validator", result.stdout)

    def test_ai_report_passes_read_only_and_rejects_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            before = snapshot(root)
            valid = self.run_ai(root)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            self.assertTrue(valid.stdout.startswith("PASS\n"), valid.stdout)
            self.assertEqual(before, snapshot(root))

            report = root / "05-ai-style-assessment.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- AI-style signal: moderate",
                    "- AI prose probability: 5%",
                    1,
                ),
                encoding="utf-8",
            )
            invalid = self.run_ai(root)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertTrue(invalid.stdout.startswith("FAIL\n"), invalid.stdout)

    def test_pdf_reading_scoped_gates_reject_pypdf_runtime_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            manifest = root / "00-manifest.md"
            text = re.sub(
                r"(?m)^- PDF extraction runtime: .*$",
                "- PDF extraction runtime: pypdf=0.0.0",
                manifest.read_text(encoding="utf-8"),
            )
            manifest.write_text(text, encoding="utf-8")
            for result in (self.run_reviewer(root, "R1"), self.run_ai(root)):
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
                self.assertIn(
                    "PDF extraction runtime must exactly equal current validator runtime",
                    result.stdout,
                )


if __name__ == "__main__":
    unittest.main()
