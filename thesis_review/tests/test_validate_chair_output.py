from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


CHAIR_VALIDATOR = (
    Path(__file__).resolve().parents[1] / "scripts" / "validate_chair_output.py"
)
STAGE_S_FILES = {
    "93-user-facing-summary.md",
    "93-current-actionable-items.csv",
    "93-current-ai-actionable-items.csv",
}


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
    def build_pre_stage_s_fixture(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)
        harness.convert_bundle_to_doctorate(root)
        for filename in STAGE_S_FILES:
            (root / filename).unlink(missing_ok=True)

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(CHAIR_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_valid_pre_stage_s_bundle_passes_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_pre_stage_s_fixture(root)
            before = snapshot(root)
            result = self.run_validator(root)
            after = snapshot(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertEqual(before, after)

    def test_stage_s_or_validation_report_is_forbidden_before_stage_s(self) -> None:
        for filename in ("93-user-facing-summary.md", "95-bundle-validation.md"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_pre_stage_s_fixture(root)
                (root / filename).write_text("downstream artifact\n", encoding="utf-8")
                result = self.run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
                self.assertIn("unallowlisted file", result.stdout)

    def test_upstream_or_chair_defect_is_not_waived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_pre_stage_s_fixture(root)
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

    def test_success_exit_without_canonical_report_fails_closed(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["validator"], returncode=0, stdout="unexpected output\n"
        )
        with mock.patch.object(
            CHAIR_MODULE.subprocess, "run", return_value=completed
        ):
            self.assertEqual(1, CHAIR_MODULE.main(["unused-round"]))

    def test_subprocess_launch_exception_fails_closed(self) -> None:
        with mock.patch.object(
            CHAIR_MODULE.subprocess, "run", side_effect=OSError("launch failed")
        ):
            self.assertEqual(1, CHAIR_MODULE.main(["unused-round"]))


if __name__ == "__main__":
    unittest.main()
