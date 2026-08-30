from __future__ import annotations

import csv
import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


MASTER_R3_VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validate_master_r3_output.py"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load synthetic-test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MASTER_R3_MODULE = load_module(
    MASTER_R3_VALIDATOR, "test_master_r3_validator_module"
)
FULL_VALIDATOR_MODULE = load_module(
    MASTER_R3_MODULE.VALIDATOR,
    "test_full_validator_module_for_master_r3",
)
PACKET_VALIDATOR_MODULE = load_module(
    MASTER_R3_MODULE.PACKET_VALIDATOR,
    "test_packet_validator_module_for_master_r3",
)

PEER_AND_DOWNSTREAM_FILES = {
    "R1-comprehensive-review.md",
    "R2-comprehensive-review.md",
    "05-ai-style-assessment.md",
    "90-chair-synthesis.md",
    "91-revision-ledger.md",
    "91-revision-ledger.csv",
    "91-ai-actionable-ledger.csv",
    "92-new-evidence-or-experiments.md",
    "92-new-evidence-or-experiments.csv",
    "93-user-facing-summary.md",
    "93-current-actionable-items.csv",
    "93-current-ai-actionable-items.csv",
    "94-post-freeze-prior-issue-closure.md",
    "95-bundle-validation.md",
}


def canonical_with_master_r3(module):
    """Model the one required shared integration without patching production."""

    original = module.canonical_stage_opened_inputs

    def canonical(process, reviewer_count, actor_id, root=None):
        opened = original(process, reviewer_count, actor_id, root)
        if process.get("degree_level") != "masters" or actor_id != "R3":
            return opened
        insertion = 2 + len(module.SKILL_REFERENCE_FILES)
        rules = list(MASTER_R3_MODULE.VALIDATOR_RULE_INPUTS)
        if opened[insertion:insertion + len(rules)] == rules:
            return opened
        return [*opened[:insertion], *rules, *opened[insertion:]]

    return canonical


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def snapshot(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative] = ("directory", "")
        else:
            result[relative] = (
                "file",
                hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            )
    return result


class ValidateMasterR3OutputTests(unittest.TestCase):
    def build_master_r3_only_fixture(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        fixture_canonical = canonical_with_master_r3(
            fixture_module.VALIDATOR_MODULE
        )
        with mock.patch.object(
            fixture_module.VALIDATOR_MODULE,
            "canonical_stage_opened_inputs",
            fixture_canonical,
        ):
            harness.build_bundle(root)
        for filename in PEER_AND_DOWNSTREAM_FILES:
            (root / filename).unlink(missing_ok=True)

    def validate(self, root: Path) -> list[str]:
        full_canonical = canonical_with_master_r3(FULL_VALIDATOR_MODULE)
        with mock.patch.object(
            FULL_VALIDATOR_MODULE,
            "canonical_stage_opened_inputs",
            full_canonical,
        ):
            return MASTER_R3_MODULE.validate_master_r3(
                root, FULL_VALIDATOR_MODULE, PACKET_VALIDATOR_MODULE
            )

    def run_cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(MASTER_R3_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_valid_scoped_fixture_passes_without_writing_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            before = snapshot(root)
            result = self.run_cli(root)
            after = snapshot(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertEqual(before, after)
            for filename in PEER_AND_DOWNSTREAM_FILES:
                self.assertFalse((root / filename).exists())

    def test_scope_does_not_enumerate_root_or_probe_peer_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            original_iterdir = Path.iterdir
            original_is_file = Path.is_file

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError(
                        "master R3 validator enumerated the bundle root"
                    )
                return original_iterdir(path)

            def guarded_is_file(path: Path):
                if path.name in PEER_AND_DOWNSTREAM_FILES:
                    raise AssertionError(
                        f"master R3 validator probed out-of-scope {path.name}"
                    )
                return original_is_file(path)

            with (
                mock.patch.object(Path, "iterdir", guarded_iterdir),
                mock.patch.object(Path, "is_file", guarded_is_file),
            ):
                errors = self.validate(root)
            self.assertEqual([], errors)

    def test_missing_shared_canonical_integration_fails_closed(self) -> None:
        fake_module = types.SimpleNamespace(
            SKILL_REFERENCE_FILES=["clean-room-orchestration.md"],
            canonical_stage_opened_inputs=lambda *_args, **_kwargs: [
                "00-process-parameters.json",
                "SKILL.md",
                "clean-room-orchestration.md",
                "frozen-thesis.pdf",
            ],
        )
        errors: list[str] = []
        MASTER_R3_MODULE.validate_canonical_support(
            fake_module,
            {"degree_level": "masters"},
            Path("unused"),
            errors,
        )
        self.assertEqual(1, len(errors))
        self.assertIn("lacks the required ordered validator-rule insertion", errors[0])

    def test_receipt_requires_all_validator_rules_in_fixed_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            report = root / "R3-comprehensive-review.md"
            first = MASTER_R3_MODULE.VALIDATOR_RULE_INPUTS[-2]
            second = MASTER_R3_MODULE.VALIDATOR_RULE_INPUTS[-1]
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    f"{first}; {second}", f"{second}; {first}", 1
                ),
                encoding="utf-8",
            )
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "opened receipt must exactly equal the canonical ordered "
                    "R3 allowlist"
                    in error
                    for error in errors
                ),
                errors,
            )

    def test_bibliography_receipt_cannot_claim_citation_only_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            ledger = root / "03-bibliography-audit-ledger.md"
            ledger.write_text(
                ledger.read_text(encoding="utf-8").replace(
                    f"public_endpoints=[{fixture_module.BIB_ENDPOINT}]",
                    "public_endpoints=["
                    f"{fixture_module.BIB_ENDPOINT}; "
                    f"{fixture_module.CITATION_ENDPOINT}]",
                    1,
                ),
                encoding="utf-8",
            )
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "03-bibliography-audit-ledger.md: public_endpoints must be"
                    in error
                    for error in errors
                ),
                errors,
            )

    def test_page_ledger_rejects_non_owner_finding_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            csv_path = root / "02-page-layout-ledger.csv"
            headers, rows = read_rows(csv_path)
            rows[0]["Disposition"] = "finding R2-F01"
            write_rows(csv_path, headers, rows)
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "exactly clean, intentional, or finding R3-Fxx" in error
                    for error in errors
                ),
                errors,
            )

    def test_bibliography_mismatch_requires_single_r3_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            path = root / "03-bibliography-audit-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["Verdict"] = "mismatch"
            rows[0]["CanonicalValue"] = "corrected fixture title"
            rows[0]["FindingDisposition"] = "R2-F01"
            write_rows(path, headers, rows)
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "must be exactly one current R3-Fxx or R3-Qxx ID" in error
                    for error in errors
                ),
                errors,
            )

    def test_citation_mismatch_requires_r3_owner_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            path = root / "04-citation-claim-audit-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["Support"] = "mismatch"
            rows[0]["SeverityFinding"] = "R2-F01"
            rows[0]["DispositionEvidence"] = "contradicted by source content"
            write_rows(path, headers, rows)
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "must link an owning-reviewer R3-Fxx or R3-Qxx" in error
                    for error in errors
                ),
                errors,
            )

    def test_substantive_citation_verdict_requires_exact_locator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            path = root / "04-citation-claim-audit-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["ExactSourceLocator"] = "available online"
            write_rows(path, headers, rows)
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "ExactSourceLocator lacks a page/section/content locator"
                    in error
                    for error in errors
                ),
                errors,
            )

    def test_citation_access_urls_require_closed_endpoint_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_master_r3_only_fixture(root)
            path = root / "04-citation-claim-audit-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["DispositionEvidence"] = (
                "supported; fallback https://example.org/unmarked"
            )
            write_rows(path, headers, rows)
            errors = self.validate(root)
            self.assertTrue(
                any(
                    "DispositionEvidence URL(s) must use the closed "
                    "'accessed endpoint: <URL>' marker" in error
                    for error in errors
                ),
                errors,
            )


if __name__ == "__main__":
    unittest.main()
