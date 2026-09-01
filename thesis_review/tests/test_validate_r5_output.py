from __future__ import annotations

import csv
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


R5_VALIDATOR = (
    Path(__file__).resolve().parents[1] / "scripts" / "validate_r5_output.py"
)


def load_r5_module():
    spec = importlib.util.spec_from_file_location("test_r5_validator_module", R5_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load R5 validator for synthetic tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R5_MODULE = load_r5_module()
FULL_VALIDATOR_MODULE = R5_MODULE.load_validator()
PEER_AND_DOWNSTREAM_FILES = {
    "R1-comprehensive-review.md",
    "R2-comprehensive-review.md",
    "R3-comprehensive-review.md",
    "R4-comprehensive-review.md",
    "04-citation-claim-audit-ledger.md",
    "04-citation-claim-audit-ledger.csv",
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
                "file", hashlib.sha256(path.read_bytes()).hexdigest().upper()
            )
    return result


class ValidateR5OutputTests(unittest.TestCase):
    def build_r5_only_fixture(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)
        harness.convert_bundle_to_doctorate(root)
        for filename in PEER_AND_DOWNSTREAM_FILES:
            (root / filename).unlink(missing_ok=True)

    def run_r5(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(R5_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_r5_fails(self, root: Path, needle: str) -> None:
        result = self.run_r5(root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
        self.assertIn(needle, result.stdout)

    def test_valid_r5_only_fixture_passes_without_writing_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            before = snapshot(root)
            result = self.run_r5(root)
            after = snapshot(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
            self.assertEqual(before, after)
            for filename in PEER_AND_DOWNSTREAM_FILES:
                self.assertFalse((root / filename).exists())

    def test_r5_packet_gate_rejects_half_open_interval_role_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(
                    encoding="utf-8"
                )
            )
            digest = process["selected_pdf_sha256"]
            context = "gamma in (0, 1] is the discount factor"
            write_rows(
                root / "00-unmatched-bracket-ledger.csv",
                list(FULL_VALIDATOR_MODULE.UNMATCHED_BRACKET_COLUMNS),
                [{
                    "GlyphID": "UBG0001",
                    "PhysicalPage": "1",
                    "Glyph": "]",
                    "AdjacentPDFText": context,
                    "Disposition": (
                        "visible role: extracted display-equation delimiter"
                    ),
                    "PDFSHA256": digest,
                }],
            )
            original_extract = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates
            )

            def injected_extract(pdf_path, reference_pages, errors):
                candidates, _unmatched = original_extract(
                    pdf_path, reference_pages, errors
                )
                return candidates, [{
                    "PhysicalPage": 1,
                    "Glyph": "]",
                    "Adjacent": context,
                    "CanonicalRole": "half-open-mathematical-interval",
                }]

            with mock.patch.object(
                FULL_VALIDATOR_MODULE,
                "extract_numeric_bracket_candidates",
                side_effect=injected_extract,
            ):
                errors = R5_MODULE.validate_r5(root, FULL_VALIDATOR_MODULE)
            self.assertTrue(
                any(
                    "Disposition must equal "
                    "'visible-role:half-open-mathematical-interval'"
                    in error
                    for error in errors
                ),
                errors,
            )

    def test_unverifiable_bibliography_row_still_requires_attempted_endpoint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            headers, rows = read_rows(root / "03-bibliography-audit-ledger.csv")
            rows[0]["Verdict"] = "unverifiable"
            rows[0]["CanonicalValue"] = "not established"
            rows[0]["EvidenceEndpoint"] = ""
            rows[0]["EvidenceNote"] = "Official route was inaccessible."
            write_rows(root / "03-bibliography-audit-ledger.csv", headers, rows)
            self.assert_r5_fails(
                root,
                "including an unverifiable verdict",
            )

    def test_bibliography_endpoint_must_bind_complete_rendered_doi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            headers, inventory = read_rows(root / "00-bibliography-inventory.csv")
            inventory[0]["RenderedEntry"] = (
                "Fixture reference. DOI: 10.1109/CVPR52729.2023.01726."
            )
            write_rows(root / "00-bibliography-inventory.csv", headers, inventory)
            headers, rows = read_rows(root / "03-bibliography-audit-ledger.csv")
            for row in rows:
                row["EvidenceEndpoint"] = "https://doi.org/10.1109/CVPR52729"
            write_rows(root / "03-bibliography-audit-ledger.csv", headers, rows)
            self.assert_r5_fails(
                root,
                "EvidenceEndpoint is not bound to the complete rendered DOI",
            )

    def test_scoped_gate_rejects_entry_string_reused_as_metadata_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            _, inventory = read_rows(root / "00-bibliography-inventory.csv")
            complete_entry = (
                "DOE J, ROE J. A complete fixture citation [C]//Fixture "
                "Proceedings. 2024: 10-20. DOI: 10.1234/fixture.1."
            )
            inventory[0]["RenderedEntry"] = complete_entry
            write_rows(
                root / "00-bibliography-inventory.csv",
                fixture_module.BIB_INVENTORY_COLUMNS,
                inventory,
            )
            headers, rows = read_rows(root / "03-bibliography-audit-ledger.csv")
            for row in rows:
                if row["Field"] in {"type", "title", "ordered_authors", "venue"}:
                    row["RenderedValue"] = complete_entry
                    row["CanonicalValue"] = complete_entry
                    row["Verdict"] = "exact"
            write_rows(root / "03-bibliography-audit-ledger.csv", headers, rows)
            self.assert_r5_fails(
                root, "repeats the complete rendered bibliography entry"
            )

    def test_r5_scope_does_not_enumerate_or_open_peer_root_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root)
            harness.convert_bundle_to_doctorate(root)
            original_iterdir = Path.iterdir
            original_is_file = Path.is_file

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("R5 validator enumerated the bundle root")
                return original_iterdir(path)

            def guarded_is_file(path: Path):
                if path.name == "94-post-freeze-prior-issue-closure.md":
                    raise AssertionError("R5 validator probed Stage V")
                return original_is_file(path)

            with (
                mock.patch.object(Path, "iterdir", guarded_iterdir),
                mock.patch.object(Path, "is_file", guarded_is_file),
            ):
                errors = R5_MODULE.validate_r5(root, FULL_VALIDATOR_MODULE)
            self.assertEqual([], errors)

    def test_r5_rejects_reserved_process_alias_without_touching_peer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root)
            harness.convert_bundle_to_doctorate(root)
            target = "R1-comprehensive-review.md"
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["frozen_pdf_file"] = target
            process_path.write_text(json.dumps(process), encoding="utf-8")
            original_lstat = Path.lstat
            original_is_file = Path.is_file

            def guard(path: Path) -> None:
                if path.name == target:
                    raise AssertionError(f"R5 touched reserved peer path {target}")

            def guarded_lstat(path: Path, *args, **kwargs):
                guard(path)
                return original_lstat(path, *args, **kwargs)

            def guarded_is_file(path: Path):
                guard(path)
                return original_is_file(path)

            with (
                mock.patch.object(Path, "lstat", guarded_lstat),
                mock.patch.object(Path, "is_file", guarded_is_file),
            ):
                errors = R5_MODULE.validate_r5(root, FULL_VALIDATOR_MODULE)
            self.assertTrue(
                any("unsafe or collides" in error for error in errors), errors
            )

    def test_report_requires_canonical_in_range_anchor_and_continuous_ids(self) -> None:
        with self.subTest(contract="gate anchor"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "physical p.1, fixture section",
                    "printed p.1, fixture section",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_r5_fails(root, "canonical physical p.<n> anchor")
        with self.subTest(contract="finding continuity"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "### R5-F01", "### R5-F02", 1
                ),
                encoding="utf-8",
            )
            self.assert_r5_fails(
                root, "reviewer finding IDs must be continuous from F01"
            )

    def test_final_02_recheck_and_unknown_finding_fail(self) -> None:
        with self.subTest(contract="no recheck"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            csv_path = root / "02-page-layout-ledger.csv"
            markdown_path = root / "02-page-layout-ledger.md"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    ",clean,", ",recheck after edit,", 1
                ),
                encoding="utf-8",
            )
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(
                    "| clean |", "| recheck after edit |", 1
                ),
                encoding="utf-8",
            )
            self.assert_r5_fails(
                root,
                "final Disposition must be exactly clean, intentional, or "
                "finding R5-Fxx",
            )
        with self.subTest(contract="finding exists"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            csv_path = root / "02-page-layout-ledger.csv"
            markdown_path = root / "02-page-layout-ledger.md"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    ",clean,", ",finding R5-F99,", 1
                ),
                encoding="utf-8",
            )
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(
                    "| clean |", "| finding R5-F99 |", 1
                ),
                encoding="utf-8",
            )
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Actionable layout findings: 0",
                    "- Actionable layout findings: 1",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_r5_fails(root, "unknown current-review finding IDs")

    def test_02_counts_distinct_finding_ids_across_multiple_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            csv_path = root / "02-page-layout-ledger.csv"
            markdown_path = root / "02-page-layout-ledger.md"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    ",clean,", ",finding R5-F01,"
                ),
                encoding="utf-8",
            )
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(
                    "| clean |", "| finding R5-F01 |"
                ),
                encoding="utf-8",
            )
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Actionable layout findings: 0",
                    "- Actionable layout findings: 1",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_r5(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_03_closed_mismatch_id_ref_column_and_mandatory_cells(self) -> None:
        cases = (
            (
                "closed mismatch",
                "FindingDisposition",
                "R5-F01; none",
                "mismatch FindingDisposition must be exactly one current R5-Fxx",
                True,
            ),
            (
                "REF only in ID column",
                "EvidenceNote",
                "fixture official record checked REF0001",
                "REFnnnn tokens are allowed only in the ReferenceID column",
                False,
            ),
            (
                "mandatory cell",
                "EvidenceNote",
                "",
                "blank mandatory field EvidenceNote",
                False,
            ),
        )
        for label, field, value, needle, make_mismatch in cases:
            with self.subTest(contract=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_r5_only_fixture(root)
                path = root / "03-bibliography-audit-ledger.csv"
                headers, rows = read_rows(path)
                rows[0][field] = value
                if make_mismatch:
                    rows[0]["Verdict"] = "mismatch"
                    rows[0]["CanonicalValue"] = "corrected value"
                write_rows(path, headers, rows)
                self.assert_r5_fails(root, needle)

    def test_render_corruption_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            (root / "page-renders" / "P0001.png").unlink()
            self.assert_r5_fails(root, "page render files")

    def test_r5_receipt_must_include_both_validator_rules_at_fixed_position(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "; rules/scripts/validate_r5_output.py", "", 1
                ),
                encoding="utf-8",
            )
            self.assert_r5_fails(
                root, "opened receipt must exactly equal the canonical ordered R5 allowlist"
            )

    def test_upstream_packet_corruption_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_only_fixture(root)
            path = root / "00-citation-candidate-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["ClassificationEvidence"] = ""
            write_rows(path, headers, rows)
            self.assert_r5_fails(
                root,
                "blank mandatory field ClassificationEvidence",
            )

    def test_r5_contract_forbids_mutating_stage_p_or_other_inputs(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        ledger_text = (skill_root / "references" / "ledger-validation.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("R5 must never edit the Stage-P packet", skill_text)
        self.assertIn("R5 must not edit the Stage-P packet", ledger_text)
        self.assertIn("stop and report failure", skill_text)
        self.assertIn("stop and report failure to Stage O", ledger_text)


if __name__ == "__main__":
    unittest.main()
