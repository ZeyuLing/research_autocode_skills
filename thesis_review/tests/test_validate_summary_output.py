from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


SKILL_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_VALIDATOR = SKILL_ROOT / "scripts" / "validate_summary_output.py"


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
        for filename in ("SKILL.md",):
            shutil.copy2(SKILL_ROOT / filename, root / filename)
        for filename in (
            "clean-room-orchestration.md",
            "report-template.md",
        ):
            shutil.copy2(SKILL_ROOT / "references" / filename, root / filename)
        scripts = root / "rules" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        for filename in (
            "validate_review_bundle.py",
            "materialize_owner_outputs.py",
            "validate_summary_output.py",
        ):
            shutil.copy2(SKILL_ROOT / "scripts" / filename, scripts / filename)

        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        reviewer_count = 5 if process["degree_level"] == "doctorate" else 3
        expected_files = set(
            FULL_MODULE.canonical_stage_opened_inputs(
                process, reviewer_count, "S", root
            )
        ) | set(SUMMARY_MODULE.STAGE_S_OUTPUTS)
        for child in list(root.iterdir()):
            if child.name == "rules" or child.name in expected_files:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in list((root / "rules").iterdir()):
            if child.name == "scripts":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        expected_script_names = {
            Path(relative).name for relative in FULL_MODULE.SUMMARY_VALIDATOR_RULE_INPUTS
        }
        for child in list(scripts.iterdir()):
            if child.name in expected_script_names:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

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

    def test_summary_gate_rejects_extra_forbidden_file_without_opening_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            forbidden = root / "frozen-thesis.pdf"
            forbidden.write_bytes(b"must never be opened by Stage S")
            original_os_open = os.open
            opened_paths: list[Path] = []

            def guarded_os_open(path, flags, *args, **kwargs):
                opened = Path(path).absolute()
                if opened == forbidden.absolute():
                    raise AssertionError("Stage S opened forbidden extra file bytes")
                opened_paths.append(opened)
                return original_os_open(path, flags, *args, **kwargs)

            with mock.patch.object(os, "open", guarded_os_open):
                errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("forbidden extra entries" in error for error in errors), errors
            )
            self.assertEqual(
                [root / "00-process-parameters.json"], opened_paths
            )

    def test_summary_gate_rejects_missing_canonical_root_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "R1-comprehensive-review.md").unlink()
            errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("missing required entries" in error for error in errors), errors
            )

    def test_summary_gate_rejects_extra_rule_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "rules" / "scripts" / "unexpected.py").write_text(
                "raise SystemExit('must not run')\n", encoding="utf-8"
            )
            errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("forbidden extra entries" in error for error in errors), errors
            )

    def test_summary_gate_rejects_missing_rule_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "rules" / "scripts" / "materialize_owner_outputs.py").unlink()
            errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("missing required entries" in error for error in errors), errors
            )

    def test_summary_gate_rejects_extra_root_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "forbidden-directory").mkdir()
            errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("forbidden extra entries" in error for error in errors), errors
            )

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

    def test_summary_gate_rejects_duplicate_process_keys_without_opening_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process_text = process_path.read_text(encoding="utf-8")
            duplicated = process_text.replace(
                '"round_id": "fixture"',
                '"round_id": "fixture", "round_id": "fixture"',
                1,
            )
            self.assertNotEqual(process_text, duplicated)
            self.assertEqual(duplicated.count('"round_id"'), 2)
            process_path.write_text(
                duplicated,
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
            self.assertIn("duplicate JSON key 'round_id'", errors[0])

    def test_summary_gate_rejects_hardlinked_summary_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "stage-s-view"
            root.mkdir()
            self.build_bundle(root)
            summary = root / "93-user-facing-summary.md"
            os.link(summary, base / "outside-stage-s-hardlink.md")
            errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("single-link" in error for error in errors), errors
            )

    @unittest.skipUnless(os.name == "nt", "NTFS stream test is Windows-specific")
    def test_summary_gate_rejects_named_stream_on_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            target = root / "93-current-actionable-items.csv"
            stream = Path(f"{target}:stage-s-regression")
            try:
                stream.write_bytes(b"hidden Stage-S stream\n")
            except OSError as exc:
                self.skipTest(f"fixture volume cannot create NTFS streams: {exc}")
            errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any("NTFS named streams" in error for error in errors), errors
            )

    def test_summary_gate_rejects_terminal_output_identity_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            summary = root / "93-user-facing-summary.md"
            original = FULL_MODULE.validate_summary_report

            def replace_after_semantic_validation(*args, **kwargs):
                result = original(*args, **kwargs)
                payload = summary.read_bytes()
                summary.unlink()
                summary.write_bytes(payload)
                return result

            with mock.patch.object(
                FULL_MODULE,
                "validate_summary_report",
                side_effect=replace_after_semantic_validation,
            ):
                errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)
            self.assertTrue(errors)
            self.assertTrue(
                any(
                    "identity" in error or "bytes changed" in error
                    for error in errors
                ),
                errors,
            )

    def test_summary_gate_binds_first_and_complete_process_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            original_capture = SUMMARY_MODULE.capture_stage_s_files
            calls = 0

            def replace_process_after_first_capture(*args, **kwargs):
                nonlocal calls
                result = original_capture(*args, **kwargs)
                calls += 1
                if calls == 1:
                    value = process_path.read_text(encoding="utf-8")
                    changed = value.replace(
                        '"round_id": "fixture"',
                        '"round_id": "changed"',
                        1,
                    )
                    self.assertNotEqual(value, changed)
                    process_path.write_text(changed, encoding="utf-8")
                return result

            with mock.patch.object(
                SUMMARY_MODULE,
                "capture_stage_s_files",
                side_effect=replace_process_after_first_capture,
            ):
                errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)

            self.assertTrue(errors)
            self.assertTrue(
                any(
                    "process identity or bytes changed" in error
                    for error in errors
                ),
                errors,
            )

    def test_summary_semantics_consume_frozen_bytes_not_transient_aba_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            projection = root / "93-current-actionable-items.csv"
            valid_bytes = projection.read_bytes()
            invalid_bytes = valid_bytes.replace(
                b"correct the wording",
                b"invalid final value",
                1,
            )
            self.assertNotEqual(valid_bytes, invalid_bytes)
            self.assertEqual(len(valid_bytes), len(invalid_bytes))
            projection.write_bytes(invalid_bytes)
            stable_stat = projection.stat()
            original_read_csv = FULL_MODULE.read_csv
            injected = False

            def transient_valid_bytes(path: Path, *args, **kwargs):
                nonlocal injected
                if path == projection and not injected:
                    injected = True
                    path.write_bytes(valid_bytes)
                    try:
                        return original_read_csv(path, *args, **kwargs)
                    finally:
                        path.write_bytes(invalid_bytes)
                        os.utime(
                            path,
                            ns=(stable_stat.st_atime_ns, stable_stat.st_mtime_ns),
                        )
                return original_read_csv(path, *args, **kwargs)

            with mock.patch.object(
                FULL_MODULE,
                "read_csv",
                side_effect=transient_valid_bytes,
            ):
                errors = SUMMARY_MODULE.validate_summary(root, FULL_MODULE)

            self.assertTrue(injected)
            self.assertTrue(errors)
            self.assertEqual(invalid_bytes, projection.read_bytes())
            self.assertTrue(
                any("91->93 mismatch" in error for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main()
