from __future__ import annotations

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
R4_VALIDATOR = SKILL_ROOT / "scripts" / "validate_r4_output.py"
FULL_VALIDATOR = SKILL_ROOT / "scripts" / "validate_review_bundle.py"
EXTRA_ENDPOINT = "https://sources.example.test/attempted-redirect"


def load_full_validator():
    spec = importlib.util.spec_from_file_location(
        "test_r4_endpoint_full_validator", FULL_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load full validator for R4 endpoint tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FULL_VALIDATOR_MODULE = load_full_validator()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R4_MODULE = load_module(R4_VALIDATOR, "test_r4_scoped_module")
R5_PACKET_MODULE = load_module(
    SKILL_ROOT / "scripts" / "validate_r5_output.py",
    "test_r4_r5_packet_module",
)


class ValidateR4EndpointClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )

    def build_doctoral_bundle(self, root: Path) -> None:
        self.harness.build_bundle(root)
        self.harness.convert_bundle_to_doctorate(root)

    def rewrite_r4_access_records(
        self,
        root: Path,
        *,
        record_extra_in_04: bool,
        declare_extra_in_04: bool,
        declare_extra_in_report: bool,
        public_identifier_url: bool = False,
    ) -> None:
        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        digest = str(process["selected_pdf_sha256"])
        _, citation_rows = fixture_module.read_csv(
            root / "04-citation-claim-audit-ledger.csv"
        )
        if record_extra_in_04:
            citation_rows[0]["DispositionEvidence"] = (
                "supported; accessed endpoint: " + EXTRA_ENDPOINT
            )
        if public_identifier_url:
            citation_rows[0]["PublicIdentifier"] = EXTRA_ENDPOINT
        fixture_module.write_csv(
            root / "04-citation-claim-audit-ledger.csv",
            fixture_module.CITATION_LEDGER_COLUMNS,
            citation_rows,
        )
        _, bibliography_inventory = fixture_module.read_csv(
            root / "00-bibliography-inventory.csv"
        )
        ledger_endpoints = [fixture_module.CITATION_ENDPOINT]
        if declare_extra_in_04:
            ledger_endpoints.append(EXTRA_ENDPOINT)
        (root / "04-citation-claim-audit-ledger.md").write_text(
            "# Citation ledger\n\n"
            + self.harness.declaration(
                digest, process, "R4", ledger_endpoints
            )
            + fixture_module.markdown_table(
                fixture_module.CITATION_MARKDOWN_HEADERS,
                fixture_module.citation_markdown_rows(
                    citation_rows, bibliography_inventory
                ),
            ),
            encoding="utf-8",
        )
        if declare_extra_in_report:
            report = root / "R4-comprehensive-review.md"
            original = (
                f"public_endpoints=[{fixture_module.CITATION_ENDPOINT}]"
            )
            replacement = (
                "public_endpoints=["
                f"{fixture_module.CITATION_ENDPOINT}; {EXTRA_ENDPOINT}]"
            )
            report_text = report.read_text(encoding="utf-8")
            self.assertIn(original, report_text)
            report.write_text(
                report_text.replace(original, replacement, 1),
                encoding="utf-8",
            )

    def run_r4(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(R4_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_scope_does_not_enumerate_round_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            original_iterdir = Path.iterdir

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("R4 validator enumerated the bundle root")
                return original_iterdir(path)

            with mock.patch.object(Path, "iterdir", guarded_iterdir):
                errors = R4_MODULE.validate_r4(
                    root, FULL_VALIDATOR_MODULE, R5_PACKET_MODULE
                )
            self.assertEqual([], errors)

    def test_scoped_gate_rejects_access_attempt_as_content_locator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            _, rows = fixture_module.read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            rows[0]["Support"] = "unverifiable"
            rows[0]["MetadataStatus"] = "unverifiable"
            rows[0]["ExactSourceLocator"] = (
                "official record: source-content access attempt"
            )
            rows[0]["DispositionEvidence"] = (
                "reasoned non-finding: network error prevented source access"
            )
            fixture_module.write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                fixture_module.CITATION_LEDGER_COLUMNS,
                rows,
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn(
                "access attempt is not an exact content locator", result.stdout
            )

    def test_only_closed_access_fields_contribute_endpoints(self) -> None:
        rows = [{
            "ExactAttachedProposition": "see https://example.test/proposition",
            "PublicIdentifier": "https://example.test/identifier",
            "ContentSourceOpened": "https://example.test/content",
            "ExactSourceLocator": "fallback https://example.test/locator p.1",
            "DispositionEvidence": (
                "raw https://example.test/not-an-access-record; "
                "accessed endpoint: https://example.test/attempt"
            ),
            "PDFSHA256": "A" * 64,
        }]
        self.assertEqual(
            {
                "https://example.test/content",
                "https://example.test/attempt",
            },
            FULL_VALIDATOR_MODULE.citation_ledger_public_endpoints(rows),
        )

    def test_public_identifier_url_does_not_create_receipt_requirement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=False,
                declare_extra_in_04=False,
                declare_extra_in_report=False,
                public_identifier_url=True,
            )
            scoped = self.run_r4(root)
            self.assertEqual(0, scoped.returncode, scoped.stdout + scoped.stderr)

    def test_access_marker_requires_a_closed_end_boundary(self) -> None:
        for disposition in (
            f"accessed endpoint: {EXTRA_ENDPOINT}",
            f"note; accessed endpoint: {EXTRA_ENDPOINT}; outcome recorded",
            f"note\naccessed endpoint: {EXTRA_ENDPOINT}\noutcome recorded",
        ):
            with self.subTest(valid=disposition):
                rows = [{
                    "ContentSourceOpened": fixture_module.CITATION_ENDPOINT,
                    "DispositionEvidence": disposition,
                }]
                errors: list[str] = []
                FULL_VALIDATOR_MODULE.validate_citation_endpoint_records(
                    rows, "04-citation-claim-audit-ledger.csv", errors
                )
                self.assertEqual([], errors)
                self.assertIn(
                    EXTRA_ENDPOINT,
                    FULL_VALIDATOR_MODULE.citation_ledger_public_endpoints(rows),
                )

        rows = [{
            "ContentSourceOpened": fixture_module.CITATION_ENDPOINT,
            "DispositionEvidence": (
                f"accessed endpoint: {EXTRA_ENDPOINT} trailing prose"
            ),
        }]
        errors = []
        FULL_VALIDATOR_MODULE.validate_citation_endpoint_records(
            rows, "04-citation-claim-audit-ledger.csv", errors
        )
        self.assertTrue(
            any("every 'accessed endpoint:' marker" in error for error in errors),
            errors,
        )
        self.assertNotIn(
            EXTRA_ENDPOINT,
            FULL_VALIDATOR_MODULE.citation_ledger_public_endpoints(rows),
        )

    def test_recorded_non_content_source_endpoint_closes_in_both_gates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=True,
                declare_extra_in_04=True,
                declare_extra_in_report=True,
            )
            scoped = self.run_r4(root)
            self.assertEqual(0, scoped.returncode, scoped.stdout + scoped.stderr)
            full = self.harness.run_validator(root)
            self.assertEqual(0, full.returncode, full.stdout + full.stderr)

    def test_unrecorded_receipt_endpoint_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=False,
                declare_extra_in_04=True,
                declare_extra_in_report=True,
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("authoritative endpoint allowlist", result.stdout)

    def test_recorded_endpoint_omitted_from_receipts_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=True,
                declare_extra_in_04=False,
                declare_extra_in_report=False,
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("omits authoritative endpoint(s)", result.stdout)
            self.assertIn(EXTRA_ENDPOINT, result.stdout)


if __name__ == "__main__":
    unittest.main()
