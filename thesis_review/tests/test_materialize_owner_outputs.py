from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module
from tests.test_validate_r5_output import PEER_AND_DOWNSTREAM_FILES


SKILL_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = SKILL_ROOT / "scripts" / "materialize_owner_outputs.py"
R5_VALIDATOR = SKILL_ROOT / "scripts" / "validate_r5_output.py"
R4_VALIDATOR = SKILL_ROOT / "scripts" / "validate_r4_output.py"
MASTER_R3_VALIDATOR = SKILL_ROOT / "scripts" / "validate_master_r3_output.py"
CHAIR_VALIDATOR = SKILL_ROOT / "scripts" / "validate_chair_output.py"
SUMMARY_VALIDATOR = SKILL_ROOT / "scripts" / "validate_summary_output.py"
STAGE_S_FILES = {
    "93-user-facing-summary.md",
    "93-current-actionable-items.csv",
    "93-current-ai-actionable-items.csv",
}
CHAIR_MATERIALIZED_FILES = (
    "90-chair-synthesis.md",
    "91-revision-ledger.md",
    "92-new-evidence-or-experiments.md",
)
CHAIR_GATE_FILES = (
    *CHAIR_MATERIALIZED_FILES,
    "91-revision-ledger.csv",
    "91-ai-actionable-ledger.csv",
    "92-new-evidence-or-experiments.csv",
)


def load_materializer_module():
    spec = importlib.util.spec_from_file_location(
        "test_owner_materializer_module", MATERIALIZER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load owner materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER_MODULE = load_materializer_module()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def changed_files(
    before: dict[str, str], after: dict[str, str]
) -> set[str]:
    return {
        filename
        for filename in before.keys() | after.keys()
        if before.get(filename) != after.get(filename)
    }


class MaterializeOwnerOutputsTests(unittest.TestCase):
    def stage_closed_gate_view(self, source_root: Path, actor_id: str) -> Path:
        """Copy exactly one Stage-C/S actor universe into a private view."""

        module = fixture_module.VALIDATOR_MODULE
        process = module.parse_strict_json_object(
            (source_root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        reviewer_count = 5 if process["degree_level"] == "doctorate" else 3
        opened = module.canonical_stage_opened_inputs(
            process, reviewer_count, actor_id, source_root
        )
        outputs = CHAIR_GATE_FILES if actor_id == "C" else tuple(STAGE_S_FILES)
        view_root = source_root / f".stage-{actor_id.lower()}-private-view"
        self.assertFalse(os.path.lexists(view_root))
        view_root.mkdir()

        reference_names = set(module.SKILL_REFERENCE_FILES)
        for relative_name in (*opened, *outputs):
            relative = Path(relative_name)
            if relative_name == "SKILL.md":
                source = SKILL_ROOT / "SKILL.md"
            elif relative_name in reference_names:
                source = SKILL_ROOT / "references" / relative_name
            elif relative.parts[:2] == ("rules", "scripts"):
                source = SKILL_ROOT / "scripts" / relative.name
            else:
                source = source_root / relative
            self.assertTrue(source.is_file(), relative_name)
            destination = view_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        expected_files = set(opened) | set(outputs)
        self.assertEqual(expected_files, set(file_hashes(view_root)))
        return view_root

    def install_stage_s_rule_inputs(self, root: Path) -> None:
        shutil.copy2(SKILL_ROOT / "SKILL.md", root / "SKILL.md")
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

    def build_r5_fixture(self, root: Path) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)
        harness.convert_bundle_to_doctorate(root)
        for filename in PEER_AND_DOWNSTREAM_FILES:
            (root / filename).unlink(missing_ok=True)
        shutil.rmtree(
            root / fixture_module.VALIDATOR_MODULE.SEMANTIC_ACCEPTANCE_DIRECTORY
        )

    def run_materializer(
        self,
        root: Path,
        actor_id: str = "R5",
        helper_inputs: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            "-B",
            str(MATERIALIZER),
            str(root),
            actor_id,
        ]
        for helper_input in helper_inputs or []:
            command.extend(("--helper-input", helper_input))
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

    def run_r5(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(R5_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_gate(
        self, path: Path, root: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(path), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def build_adversarial_chair_fixture(
        self, root: Path
    ) -> tuple[dict[str, object], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
        """Build the complete fixture, then make C's semantic CSVs adversarial."""

        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)

        academic_path = root / "91-revision-ledger.csv"
        academic_headers, academic_rows = read_rows(academic_path)
        academic_rows[0].update({
            "SourceReviewerFindingIDs": "R1-F01, R2-F01",
            "DirectObservation": "A | B",
            "MinimumEditEvidence": r"one\|two",
            "Verification": "real line one\nreal line two",
        })
        academic_rows.append({
            **academic_rows[0],
            "LedgerID": "L02",
            "ChairFindingID": "C-F02",
            "SourceReviewerFindingIDs": "R3-F01",
            "Remedy": "N",
            "DirectObservation": r"literal \n marker",
            "MinimumEditEvidence": "collect evidence A | B",
            "Dependency": "L01",
            "Verification": r"verify one\|two",
        })
        write_rows(academic_path, academic_headers, academic_rows)

        ai_path = root / "91-ai-actionable-ledger.csv"
        ai_headers, ai_rows = read_rows(ai_path)
        ai_rows[0].update({
            "DirectStyleObservation": "AI transition A | transition B repeats visibly",
            "MinimumEditingAction": r"Replace the one\|two transition pair locally",
        })
        write_rows(ai_path, ai_headers, ai_rows)
        ai_report_path = root / "05-ai-style-assessment.md"
        ai_report_path.write_text(
            ai_report_path.read_text(encoding="utf-8").replace(
                "- Recurrent evidence: formulaic transition",
                "- Recurrent evidence: AI transition A | transition B repeats visibly",
                1,
            ).replace(
                "- Minimum safe editing strategy: replace the transition",
                r"- Minimum safe editing strategy: Replace the one\|two transition pair locally",
                1,
            ),
            encoding="utf-8",
        )

        evidence_path = root / "92-new-evidence-or-experiments.csv"
        evidence_headers, _ = read_rows(evidence_path)
        evidence_rows = [{
            "EvidenceItemID": "N01",
            "LedgerID": "L02",
            "ChairFindingID": "C-F02",
            "Remedy": "N",
            "Item": "measure A | B",
            "ClaimThatDependsOnIt": r"claim one\|two",
            "WhyWritingIsInsufficient": "real line one\nreal line two",
            "MinimumViableEvidence": r"literal \n marker",
            "ConsequenceIfUnavailable": "retain the stated limitation",
        }]
        write_rows(evidence_path, evidence_headers, evidence_rows)

        # All three C artifacts must converge on one canonical receipt.  Start
        # two of them from deliberately noncanonical duplicate `none` entries.
        for filename, duplicate_none in (
            ("91-revision-ledger.md", "none; none"),
            ("92-new-evidence-or-experiments.md", "none; none; none"),
        ):
            path = root / filename
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "public_endpoints=[none]",
                    f"public_endpoints=[{duplicate_none}]",
                    1,
                ),
                encoding="utf-8",
            )

        # The new open Remedy=N is a semantic Chair choice, so the preexisting
        # B verdict must be made substantively consistent before materialization.
        chair_path = root / "90-chair-synthesis.md"
        chair_path.write_text(
            chair_path.read_text(encoding="utf-8").replace(
                "- Overall academic grade: B",
                "- Overall academic grade: C",
                1,
            ).replace(
                "- Overall defense recommendation: 小修后可答辩",
                "- Overall defense recommendation: 大修后重新送审，复审通过后方可答辩",
                1,
            ),
            encoding="utf-8",
        )

        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        # The adversarial fixture mutates the AI target report after the base
        # bundle is built, so rebind the independent semantic-acceptance set to
        # those exact target bytes before testing downstream materialization.
        harness.write_semantic_acceptance_fixture(root, process)
        return process, academic_rows, ai_rows, evidence_rows

    def parsed_table(self, path: Path, headers: list[str]) -> list[list[str]]:
        errors: list[str] = []
        rows = fixture_module.VALIDATOR_MODULE.parse_markdown_table_by_exact_headers(
            path.read_text(encoding="utf-8"),
            headers,
            path.name,
            errors,
            case_sensitive=True,
        )
        self.assertEqual([], errors)
        self.assertIsNotNone(rows)
        return rows or []

    def parsed_receipt(self, path: Path, label: str) -> tuple[str, dict[str, list[str]]]:
        module = fixture_module.VALIDATOR_MODULE
        receipt = module.labeled_value(path.read_text(encoding="utf-8"), label)
        self.assertIsNotNone(receipt, path.name)
        errors: list[str] = []
        parsed = module.parse_closed_access_receipt(receipt or "", path.name, errors)
        self.assertEqual([], errors)
        self.assertIsNotNone(parsed)
        return receipt or "", parsed or {}

    def projected_rows(
        self, rows: list[dict[str, str]], fields: list[str]
    ) -> list[list[str]]:
        scalar = fixture_module.VALIDATOR_MODULE.markdown_projection_scalar
        return [[scalar(row.get(field, "")) for field in fields] for row in rows]

    def test_r5_materializer_escapes_pipes_derives_receipts_and_is_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_fixture(root)
            page_csv = root / "02-page-layout-ledger.csv"
            page_headers, page_rows = read_rows(page_csv)
            page_rows[0]["NeighborPagesChecked"] = "P0002"
            page_rows[0]["Evidence"] = "cross-checked against P0002"
            page_rows[1]["NeighborPagesChecked"] = "P0001"
            write_rows(page_csv, page_headers, page_rows)

            fallback = "https://example.org/official-fallback"
            bib_csv = root / "03-bibliography-audit-ledger.csv"
            bib_headers, bib_rows = read_rows(bib_csv)
            bib_rows[0]["EvidenceNote"] = (
                "field=type; official route A | route B checked; "
                f"accessed endpoint: {fallback}"
            )
            write_rows(bib_csv, bib_headers, bib_rows)

            primary = fixture_module.BIB_ENDPOINT
            for filename in (
                "02-page-layout-ledger.md",
                "03-bibliography-audit-ledger.md",
                "R5-comprehensive-review.md",
            ):
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        f"public_endpoints=[{primary}]",
                        f"public_endpoints=[{primary}; {primary}]",
                        1,
                    ),
                    encoding="utf-8",
                )

            before = file_hashes(root)
            first = self.run_materializer(root)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertTrue(first.stdout.startswith("MATERIALIZED\n"), first.stdout)
            after_first = file_hashes(root)
            allowed_changes = {
                "02-page-layout-ledger.md",
                "03-bibliography-audit-ledger.md",
                "R5-comprehensive-review.md",
            }
            self.assertEqual(
                {key: value for key, value in before.items() if key not in allowed_changes},
                {
                    key: value
                    for key, value in after_first.items()
                    if key not in allowed_changes
                },
            )
            bib_markdown = (root / "03-bibliography-audit-ledger.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(r"official route A \| route B checked", bib_markdown)
            expected_receipt = f"public_endpoints=[{primary}; {fallback}]"
            for filename in allowed_changes:
                text = (root / filename).read_text(encoding="utf-8")
                self.assertEqual(1, text.count(expected_receipt), filename)
                self.assertNotIn(f"{primary}; {primary}", text)

            scoped = self.run_r5(root)
            self.assertEqual(0, scoped.returncode, scoped.stdout + scoped.stderr)
            self.assertTrue(scoped.stdout.startswith("PASS\n"), scoped.stdout)

            second = self.run_materializer(root)
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(after_first, file_hashes(root))

    def test_r5_rejects_unknown_page_id_in_allowed_cross_reference_column(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_fixture(root)
            page_csv = root / "02-page-layout-ledger.csv"
            headers, rows = read_rows(page_csv)
            rows[0]["NeighborPagesChecked"] = "P9999"
            write_rows(page_csv, headers, rows)
            result = self.run_materializer(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            scoped = self.run_r5(root)
            self.assertNotEqual(0, scoped.returncode)
            self.assertIn("cross-reference column contains unknown IDs ['P9999']", scoped.stdout)

    def test_bibliography_access_journal_and_receipt_are_closed_both_ways(self) -> None:
        fallback = "https://example.org/official-fallback"
        with self.subTest(contract="bare URL is not an access record"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_fixture(root)
            path = root / "03-bibliography-audit-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["EvidenceNote"] = f"fallback checked at {fallback}"
            write_rows(path, headers, rows)
            materialized = self.run_materializer(root)
            self.assertEqual(0, materialized.returncode, materialized.stdout)
            scoped = self.run_r5(root)
            self.assertNotEqual(0, scoped.returncode)
            self.assertIn(
                "EvidenceNote URL(s) must use the closed "
                "'accessed endpoint: <URL>' marker",
                scoped.stdout,
            )

        with self.subTest(contract="recorded route cannot be omitted from receipt"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_fixture(root)
            path = root / "03-bibliography-audit-ledger.csv"
            headers, rows = read_rows(path)
            rows[0]["EvidenceNote"] = f"accessed endpoint: {fallback}"
            write_rows(path, headers, rows)
            materialized = self.run_materializer(root)
            self.assertEqual(0, materialized.returncode, materialized.stdout)
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    f"; {fallback}]", "]", 1
                ),
                encoding="utf-8",
            )
            scoped = self.run_r5(root)
            self.assertNotEqual(0, scoped.returncode)
            self.assertIn(
                "public_endpoints omits authoritative endpoint(s) that this "
                "R5 artifact says were opened",
                scoped.stdout,
            )

        with self.subTest(contract="materializer does not erase an unjournaled route"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_r5_fixture(root)
            report = root / "R5-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    f"public_endpoints=[{fixture_module.BIB_ENDPOINT}]",
                    "public_endpoints=["
                    f"{fixture_module.BIB_ENDPOINT}; {fallback}]",
                    1,
                ),
                encoding="utf-8",
            )
            before = file_hashes(root)
            materialized = self.run_materializer(root)
            self.assertNotEqual(0, materialized.returncode)
            self.assertIn("absent from the authoritative owned access fields", materialized.stdout)
            self.assertEqual(before, file_hashes(root))

    def test_chair_materializer_projects_adversarial_csvs_canonicalizes_receipts_is_idempotent_and_passes_scoped_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process, academic_rows, ai_rows, evidence_rows = (
                self.build_adversarial_chair_fixture(root)
            )
            for filename in STAGE_S_FILES:
                (root / filename).unlink(missing_ok=True)
            # A Chair view receives the hash-only semantic gate, never the
            # private semantic-review directory itself.
            shutil.rmtree(
                root / fixture_module.VALIDATOR_MODULE.SEMANTIC_ACCEPTANCE_DIRECTORY
            )

            before = file_hashes(root)
            first = self.run_materializer(root, "C")
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertTrue(first.stdout.startswith("MATERIALIZED\n"), first.stdout)
            after_first = file_hashes(root)
            self.assertEqual(
                {
                    "90-chair-synthesis.md",
                    "91-revision-ledger.md",
                    "92-new-evidence-or-experiments.md",
                },
                changed_files(before, after_first),
            )

            module = fixture_module.VALIDATOR_MODULE
            revision_path = root / "91-revision-ledger.md"
            chair_path = root / "90-chair-synthesis.md"
            evidence_path = root / "92-new-evidence-or-experiments.md"
            revision_academic = self.parsed_table(
                revision_path, MATERIALIZER_MODULE.ACADEMIC_MD_HEADERS
            )
            self.assertEqual(
                self.projected_rows(
                    academic_rows, MATERIALIZER_MODULE.ACADEMIC_MD_FIELDS
                ),
                revision_academic,
            )
            self.assertEqual(
                self.projected_rows(ai_rows, MATERIALIZER_MODULE.AI_MD_FIELDS),
                self.parsed_table(revision_path, MATERIALIZER_MODULE.AI_MD_HEADERS),
            )
            self.assertEqual(
                self.projected_rows(
                    academic_rows, MATERIALIZER_MODULE.CHAIR_FINDING_FIELDS
                ),
                self.parsed_table(chair_path, MATERIALIZER_MODULE.CHAIR_FINDING_HEADERS),
            )
            self.assertEqual(
                self.projected_rows(ai_rows, MATERIALIZER_MODULE.CHAIR_AI_FIELDS),
                self.parsed_table(chair_path, MATERIALIZER_MODULE.CHAIR_AI_HEADERS),
            )
            self.assertEqual(
                self.projected_rows(
                    [academic_rows[0]], MATERIALIZER_MODULE.WEP_FIELDS
                ),
                self.parsed_table(evidence_path, MATERIALIZER_MODULE.WEP_HEADERS),
            )
            self.assertEqual(
                self.projected_rows(evidence_rows, module.EVIDENCE_ITEM_COLUMNS),
                self.parsed_table(evidence_path, MATERIALIZER_MODULE.EVIDENCE_MD_HEADERS),
            )

            # These four assertions make the otherwise visually similar real-LF
            # and literal-\n cases explicit, while also exercising both pipe forms.
            self.assertEqual(
                module.markdown_projection_scalar("A | B"), revision_academic[0][8]
            )
            self.assertEqual(
                module.markdown_projection_scalar(r"one\|two"),
                revision_academic[0][10],
            )
            self.assertEqual(
                module.markdown_projection_scalar("real line one\nreal line two"),
                revision_academic[0][14],
            )
            self.assertEqual(
                module.markdown_projection_scalar(r"literal \n marker"),
                revision_academic[1][8],
            )
            self.assertEqual("L01", revision_academic[1][11])

            receipt_specs = (
                (chair_path, "Chair input-receipt/access declaration"),
                (revision_path, "Input-receipt/access declaration"),
                (evidence_path, "Input-receipt/access declaration"),
            )
            receipts: list[str] = []
            expected_receipt = {
                "received": ["operational prompt"],
                "opened": module.canonical_stage_opened_inputs(process, 3, "C"),
                "public_endpoints": ["none"],
            }
            for path, label in receipt_specs:
                receipt, parsed = self.parsed_receipt(path, label)
                receipts.append(receipt)
                self.assertEqual(expected_receipt, parsed, path.name)
            self.assertEqual(1, len(set(receipts)), receipts)

            view_root = self.stage_closed_gate_view(root, "C")
            try:
                scoped = self.run_gate(CHAIR_VALIDATOR, view_root)
                self.assertEqual(
                    0, scoped.returncode, scoped.stdout + scoped.stderr
                )
                self.assertTrue(scoped.stdout.startswith("PASS\n"), scoped.stdout)
            finally:
                shutil.rmtree(view_root)

            second = self.run_materializer(root, "C")
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(after_first, file_hashes(root))

    def test_chair_never_materializes_governing_url_metadata_as_an_endpoint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_adversarial_chair_fixture(root)
            endpoint = "https://example.edu/official-rule"
            process_path = root / "00-process-parameters.json"
            process = fixture_module.VALIDATOR_MODULE.parse_strict_json_object(
                process_path.read_text(encoding="utf-8")
            )
            process["governing_rule_urls"] = [endpoint]
            process_path.write_text(json.dumps(process), encoding="utf-8")

            result = self.run_materializer(root, "C")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for path, label in (
                (
                    root / "90-chair-synthesis.md",
                    "Chair input-receipt/access declaration",
                ),
                (
                    root / "91-revision-ledger.md",
                    "Input-receipt/access declaration",
                ),
                (
                    root / "92-new-evidence-or-experiments.md",
                    "Input-receipt/access declaration",
                ),
            ):
                _, receipt = self.parsed_receipt(path, label)
                self.assertEqual(["none"], receipt["public_endpoints"], path.name)

            chair = root / "90-chair-synthesis.md"
            chair.write_text(
                chair.read_text(encoding="utf-8").replace(
                    "public_endpoints=[none]",
                    f"public_endpoints=[{endpoint}]",
                    1,
                ),
                encoding="utf-8",
            )
            before = file_hashes(root)
            rejected = self.run_materializer(root, "C")
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("outside the current C allowlist", rejected.stdout)
            self.assertEqual(before, file_hashes(root))

    def test_stage_s_materializer_rebuilds_only_three_outputs_with_adversarial_values_canonical_receipt_is_idempotent_and_passes_scoped_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process, academic_rows, ai_rows, evidence_rows = (
                self.build_adversarial_chair_fixture(root)
            )
            self.install_stage_s_rule_inputs(root)

            # Preserve the complete fixture's intentionally stale Stage-S
            # templates, then respect the actual C-before-S stage boundary.
            stage_s_templates = {
                filename: (root / filename).read_bytes()
                for filename in STAGE_S_FILES
            }
            for filename in STAGE_S_FILES:
                (root / filename).unlink()
            chair = self.run_materializer(root, "C")
            self.assertEqual(0, chair.returncode, chair.stdout + chair.stderr)
            for filename, content in stage_s_templates.items():
                (root / filename).write_bytes(content)

            before = file_hashes(root)
            first = self.run_materializer(root, "S")
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertTrue(first.stdout.startswith("MATERIALIZED\n"), first.stdout)
            after_first = file_hashes(root)
            self.assertEqual(STAGE_S_FILES, changed_files(before, after_first))

            academic_headers, projected_academic_csv = read_rows(
                root / "93-current-actionable-items.csv"
            )
            ai_headers, projected_ai_csv = read_rows(
                root / "93-current-ai-actionable-items.csv"
            )
            self.assertEqual(
                fixture_module.VALIDATOR_MODULE.ACADEMIC_SUMMARY_COLUMNS,
                academic_headers,
            )
            self.assertEqual(
                fixture_module.VALIDATOR_MODULE.AI_SUMMARY_COLUMNS,
                ai_headers,
            )
            self.assertEqual(academic_rows, projected_academic_csv)
            self.assertEqual(ai_rows, projected_ai_csv)

            summary_path = root / "93-user-facing-summary.md"
            self.assertEqual(
                self.projected_rows(
                    academic_rows, MATERIALIZER_MODULE.ACADEMIC_MD_FIELDS
                ),
                self.parsed_table(
                    summary_path, MATERIALIZER_MODULE.SUMMARY_ACADEMIC_HEADERS
                ),
            )
            self.assertEqual(
                self.projected_rows(ai_rows, MATERIALIZER_MODULE.AI_MD_FIELDS),
                self.parsed_table(summary_path, MATERIALIZER_MODULE.SUMMARY_AI_HEADERS),
            )
            self.assertEqual(
                self.projected_rows(
                    evidence_rows,
                    fixture_module.VALIDATOR_MODULE.EVIDENCE_ITEM_COLUMNS,
                ),
                self.parsed_table(summary_path, MATERIALIZER_MODULE.EVIDENCE_MD_HEADERS),
            )

            _receipt, parsed_receipt = self.parsed_receipt(
                summary_path, "Summary input-receipt/access declaration"
            )
            self.assertEqual(
                {
                    "received": ["operational prompt"],
                    "opened": fixture_module.VALIDATOR_MODULE.canonical_stage_opened_inputs(
                        process, 3, "S"
                    ),
                    "public_endpoints": ["none"],
                },
                parsed_receipt,
            )

            view_root = self.stage_closed_gate_view(root, "S")
            try:
                scoped = self.run_gate(SUMMARY_VALIDATOR, view_root)
                self.assertEqual(
                    0, scoped.returncode, scoped.stdout + scoped.stderr
                )
                self.assertTrue(scoped.stdout.startswith("PASS\n"), scoped.stdout)
            finally:
                shutil.rmtree(view_root)

            second = self.run_materializer(root, "S")
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(after_first, file_hashes(root))

    def test_stage_s_materializer_creates_all_three_outputs_when_absent(
        self,
    ) -> None:
        for degree in ("masters", "doctorate"):
            with self.subTest(degree=degree), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                harness = fixture_module.ValidateReviewBundleTests(
                    methodName="test_complete_fixture_passes"
                )
                harness.build_bundle(root)
                if degree == "doctorate":
                    harness.convert_bundle_to_doctorate(root)
                self.install_stage_s_rule_inputs(root)

                from_template = self.run_materializer(root, "S")
                self.assertEqual(
                    0, from_template.returncode,
                    from_template.stdout + from_template.stderr,
                )
                expected = {
                    filename: (root / filename).read_bytes()
                    for filename in STAGE_S_FILES
                }
                for filename in STAGE_S_FILES:
                    (root / filename).unlink()

                before = file_hashes(root)
                first = self.run_materializer(root, "S")
                self.assertEqual(0, first.returncode, first.stdout + first.stderr)
                self.assertTrue(
                    first.stdout.startswith("MATERIALIZED\n"), first.stdout
                )
                after_first = file_hashes(root)
                self.assertEqual(STAGE_S_FILES, changed_files(before, after_first))
                for filename in STAGE_S_FILES:
                    path = root / filename
                    self.assertTrue(path.is_file(), filename)
                    self.assertEqual(1, path.stat().st_nlink, filename)
                    self.assertEqual(expected[filename], path.read_bytes(), filename)

                view_root = self.stage_closed_gate_view(root, "S")
                try:
                    scoped = self.run_gate(SUMMARY_VALIDATOR, view_root)
                    self.assertEqual(
                        0, scoped.returncode, scoped.stdout + scoped.stderr
                    )
                    self.assertTrue(
                        scoped.stdout.startswith("PASS\n"), scoped.stdout
                    )
                finally:
                    shutil.rmtree(view_root)

                second = self.run_materializer(root, "S")
                self.assertEqual(0, second.returncode, second.stdout + second.stderr)
                self.assertEqual(after_first, file_hashes(root))

    def test_stage_s_materializer_rejects_preexisting_hardlinked_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root)
            for filename in STAGE_S_FILES:
                (root / filename).unlink()
            sentinel = root / "sentinel.txt"
            sentinel.write_text("must remain unchanged\n", encoding="utf-8")
            os.link(sentinel, root / "93-user-facing-summary.md")

            before = file_hashes(root)
            result = self.run_materializer(root, "S")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("single-link regular file", result.stdout)
            self.assertEqual(before, file_hashes(root))
            self.assertEqual(
                "must remain unchanged\n", sentinel.read_text(encoding="utf-8")
            )

    def test_stage_s_materializer_rejects_duplicate_process_keys_without_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root)
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
            before = file_hashes(root)
            result = self.run_materializer(root, "S")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("duplicate JSON key 'round_id'", result.stdout)
            self.assertEqual(before, file_hashes(root))

    def test_all_materializer_roles_reject_process_schema_drift_without_mutation(
        self,
    ) -> None:
        cases = (
            ("R5", True, "unexpected", "process envelope schema mismatch"),
            ("C", False, "wrong-type", "physical_page_count must be a positive integer"),
            ("S", False, "invalid-enum", "review_mode must be one of"),
        )
        for actor_id, doctorate, mutation, expected_error in cases:
            with self.subTest(actor=actor_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                harness = fixture_module.ValidateReviewBundleTests(
                    methodName="test_complete_fixture_passes"
                )
                harness.build_bundle(root)
                if doctorate:
                    harness.convert_bundle_to_doctorate(root)
                process_path = root / "00-process-parameters.json"
                process = json.loads(process_path.read_text(encoding="utf-8"))
                if mutation == "unexpected":
                    process["unexpected_field"] = "must fail closed"
                elif mutation == "wrong-type":
                    process["physical_page_count"] = "4"
                else:
                    process["review_mode"] = "invalid-review-mode"
                process_path.write_text(
                    json.dumps(process, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                before = file_hashes(root)
                result = self.run_materializer(root, actor_id)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stdout)
                self.assertEqual(before, file_hashes(root))

    def test_chair_ignores_undeclared_nonrecipient_helper_without_opening_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(
                root, digest, recipients=["R1"]
            )
            provenance = root / "helpers/H01-provenance.json"
            original_open = Path.open

            def guarded_open(path: Path, *args, **kwargs):
                if path.absolute() == provenance.absolute():
                    raise AssertionError(
                        "Chair materializer opened an undeclared R1 helper"
                    )
                return original_open(path, *args, **kwargs)

            before = file_hashes(root)
            with mock.patch.object(Path, "open", guarded_open):
                errors = MATERIALIZER_MODULE.materialize(root, "C")
            self.assertEqual([], errors)
            after = file_hashes(root)
            self.assertTrue(
                changed_files(before, after).issubset(
                    {
                        "90-chair-synthesis.md",
                        "91-revision-ledger.md",
                        "92-new-evidence-or-experiments.md",
                    }
                ),
                changed_files(before, after),
            )
            self.assertEqual(
                before["helpers/H01-provenance.json"],
                after["helpers/H01-provenance.json"],
            )
            self.assertEqual(
                before["helpers/H01-pages.txt"],
                after["helpers/H01-pages.txt"],
            )

    def test_chair_rejects_invalid_declared_helper_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            provenance_path = root / "helpers/H01-provenance.json"
            provenance_text = provenance_path.read_text(encoding="utf-8")
            provenance_path.write_text(
                provenance_text.replace(
                    '"recipient_stages": ["C"]',
                    '"recipient_stages": ["C"], "recipient_stages": ["C"]',
                    1,
                ),
                encoding="utf-8",
            )
            before = file_hashes(root)
            result = self.run_materializer(
                root,
                "C",
                ["helpers/H01-provenance.json", "helpers/H01-pages.txt"],
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "duplicate JSON key 'recipient_stages'", result.stdout
            )
            self.assertEqual(before, file_hashes(root))

    def test_chair_never_opens_an_undeclared_provenance_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            undeclared_output = root / "helpers/H01-pages.txt"
            original_open = Path.open

            def guarded_open(path: Path, *args, **kwargs):
                if path.absolute() == undeclared_output.absolute():
                    raise AssertionError(
                        "Chair materializer opened an undeclared helper output"
                    )
                return original_open(path, *args, **kwargs)

            before = file_hashes(root)
            with mock.patch.object(Path, "open", guarded_open):
                errors = MATERIALIZER_MODULE.materialize(
                    root,
                    "C",
                    ["helpers/H01-provenance.json"],
                )
            self.assertTrue(errors)
            self.assertTrue(
                any("refusing to inspect undeclared" in error for error in errors),
                errors,
            )
            self.assertEqual(before, file_hashes(root))

    def test_chair_rejects_reordered_or_hardlinked_declared_helpers_without_mutation(
        self,
    ) -> None:
        with self.subTest(case="reordered"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            before = file_hashes(root)
            result = self.run_materializer(
                root,
                "C",
                ["helpers/H01-pages.txt", "helpers/H01-provenance.json"],
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("ascending Hxx order", result.stdout)
            self.assertEqual(before, file_hashes(root))

        with self.subTest(case="hardlinked-output"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            output = root / "helpers/H01-pages.txt"
            sentinel = root / "external-helper-source.txt"
            sentinel.write_bytes(output.read_bytes())
            output.unlink()
            os.link(sentinel, output)
            before = file_hashes(root)
            result = self.run_materializer(
                root,
                "C",
                ["helpers/H01-provenance.json", "helpers/H01-pages.txt"],
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("single-link regular files", result.stdout)
            self.assertEqual(before, file_hashes(root))

    def test_chair_rejects_hardlinked_provenance_without_writing_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            provenance = root / "helpers/H01-provenance.json"
            sentinel = root / "external-helper-provenance.json"
            sentinel.write_bytes(provenance.read_bytes())
            provenance.unlink()
            os.link(sentinel, provenance)
            chair_before = {
                filename: hashlib.sha256((root / filename).read_bytes()).hexdigest()
                for filename in CHAIR_MATERIALIZED_FILES
            }

            result = self.run_materializer(
                root,
                "C",
                ["helpers/H01-provenance.json", "helpers/H01-pages.txt"],
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("single-link regular files", result.stdout)
            self.assertEqual(
                chair_before,
                {
                    filename: hashlib.sha256(
                        (root / filename).read_bytes()
                    ).hexdigest()
                    for filename in CHAIR_MATERIALIZED_FILES
                },
            )

    @unittest.skipUnless(os.name == "nt", "NTFS ADS is Windows-specific")
    def test_chair_rejects_named_stream_on_each_declared_helper_without_writing_outputs(
        self,
    ) -> None:
        for relative in (
            "helpers/H01-provenance.json",
            "helpers/H01-pages.txt",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                harness = fixture_module.ValidateReviewBundleTests(
                    methodName="test_complete_fixture_passes"
                )
                digest = harness.build_bundle(root)
                harness.install_helper_fixture(root, digest, recipients=["C"])
                stream_path = Path(f"{root / relative}:untrusted")
                try:
                    stream_path.write_text("must not be hidden\n", encoding="utf-8")
                except OSError as exc:
                    self.skipTest(f"test volume does not support NTFS ADS: {exc}")
                chair_before = {
                    filename: hashlib.sha256(
                        (root / filename).read_bytes()
                    ).hexdigest()
                    for filename in CHAIR_MATERIALIZED_FILES
                }

                result = self.run_materializer(
                    root,
                    "C",
                    ["helpers/H01-provenance.json", "helpers/H01-pages.txt"],
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("NTFS named streams", result.stdout)
                self.assertEqual(
                    chair_before,
                    {
                        filename: hashlib.sha256(
                            (root / filename).read_bytes()
                        ).hexdigest()
                        for filename in CHAIR_MATERIALIZED_FILES
                    },
                )

    def test_chair_rechecks_helper_snapshot_before_any_output_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            chair_before = {
                filename: hashlib.sha256((root / filename).read_bytes()).hexdigest()
                for filename in CHAIR_MATERIALIZED_FILES
            }
            original_materialize_chair = MATERIALIZER_MODULE.materialize_chair

            def mutate_after_parse(*args, **kwargs):
                prepared = original_materialize_chair(*args, **kwargs)
                with (root / "helpers/H01-pages.txt").open("ab") as handle:
                    handle.write(b"\npost-validation mutation\n")
                return prepared

            with mock.patch.object(
                MATERIALIZER_MODULE,
                "materialize_chair",
                side_effect=mutate_after_parse,
            ):
                errors = MATERIALIZER_MODULE.materialize(
                    root,
                    "C",
                    ["helpers/H01-provenance.json", "helpers/H01-pages.txt"],
                )

            self.assertTrue(errors)
            self.assertTrue(
                any("identity/hash set changed" in error for error in errors),
                errors,
            )
            self.assertEqual(
                chair_before,
                {
                    filename: hashlib.sha256(
                        (root / filename).read_bytes()
                    ).hexdigest()
                    for filename in CHAIR_MATERIALIZED_FILES
                },
            )

    @unittest.skipUnless(os.name == "nt", "NTFS junction test is Windows-specific")
    def test_chair_rejects_helpers_junction_before_first_helper_leaf_open(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as external,
        ):
            root = Path(directory)
            external_root = Path(external)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            helpers = root / "helpers"
            real_helpers = external_root / "real-helpers"
            helpers.rename(real_helpers)
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(helpers), str(real_helpers)],
                capture_output=True,
                text=True,
                check=False,
            )
            if created.returncode != 0:
                real_helpers.rename(helpers)
                self.skipTest(f"could not create NTFS junction: {created.stderr}")
            chair_before = {
                filename: (root / filename).read_bytes()
                for filename in CHAIR_MATERIALIZED_FILES
            }
            original_capture = (
                MATERIALIZER_MODULE.load_validator_cached()
                .capture_declared_helper_snapshot_set
            )
            leaf_capture_called = False

            def read_then_wash_junction(*args, **kwargs):
                nonlocal leaf_capture_called
                leaf_capture_called = True
                snapshots = original_capture(*args, **kwargs)
                helpers.rmdir()
                real_helpers.rename(helpers)
                return snapshots

            try:
                with mock.patch.object(
                    MATERIALIZER_MODULE.load_validator_cached(),
                    "capture_declared_helper_snapshot_set",
                    side_effect=read_then_wash_junction,
                ):
                    errors = MATERIALIZER_MODULE.materialize(
                        root,
                        "C",
                        [
                            "helpers/H01-provenance.json",
                            "helpers/H01-pages.txt",
                        ],
                    )
                self.assertTrue(errors)
                self.assertFalse(
                    leaf_capture_called,
                    "a helper leaf was opened before the junction preflight",
                )
                self.assertTrue(
                    any("directory chain" in error for error in errors),
                    errors,
                )
                self.assertEqual(
                    chair_before,
                    {
                        filename: (root / filename).read_bytes()
                        for filename in CHAIR_MATERIALIZED_FILES
                    },
                )
            finally:
                if helpers.exists() and helpers.is_junction():
                    helpers.rmdir()
                if real_helpers.exists() and not helpers.exists():
                    real_helpers.rename(helpers)

    @unittest.skipUnless(os.name == "nt", "NTFS ADS is Windows-specific")
    def test_chair_rejects_helpers_directory_ads_before_first_leaf_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            stream = Path(f"{root / 'helpers'}:hidden-directory-stream")
            try:
                stream.write_text("hidden\n", encoding="utf-8")
            except OSError as exc:
                self.skipTest(f"test volume does not support directory ADS: {exc}")
            leaf_capture_called = False
            validator = MATERIALIZER_MODULE.load_validator_cached()
            original_capture = validator.capture_declared_helper_snapshot_set

            def record_leaf_capture(*args, **kwargs):
                nonlocal leaf_capture_called
                leaf_capture_called = True
                return original_capture(*args, **kwargs)

            try:
                with mock.patch.object(
                    validator,
                    "capture_declared_helper_snapshot_set",
                    side_effect=record_leaf_capture,
                ):
                    errors = MATERIALIZER_MODULE.materialize(
                        root,
                        "C",
                        [
                            "helpers/H01-provenance.json",
                            "helpers/H01-pages.txt",
                        ],
                    )
                self.assertTrue(errors)
                self.assertFalse(leaf_capture_called)
                self.assertTrue(
                    any("directory-chain component" in error for error in errors),
                    errors,
                )
            finally:
                try:
                    stream.unlink(missing_ok=True)
                except OSError:
                    pass

    @unittest.skipUnless(os.name == "nt", "NTFS junction test is Windows-specific")
    def test_chair_rejects_junction_in_round_root_ancestor_chain_before_leaf_open(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as actual_directory,
            tempfile.TemporaryDirectory() as alias_directory,
        ):
            actual_parent = Path(actual_directory) / "actual-parent"
            actual_root = actual_parent / "round"
            actual_root.mkdir(parents=True)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(actual_root)
            harness.install_helper_fixture(actual_root, digest, recipients=["C"])
            alias_parent = Path(alias_directory) / "alias-parent"
            created = subprocess.run(
                [
                    "cmd", "/c", "mklink", "/J",
                    str(alias_parent), str(actual_parent),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest(f"could not create NTFS junction: {created.stderr}")
            alias_root = alias_parent / "round"
            leaf_capture_called = False
            validator = MATERIALIZER_MODULE.load_validator_cached()
            original_capture = validator.capture_declared_helper_snapshot_set

            def record_leaf_capture(*args, **kwargs):
                nonlocal leaf_capture_called
                leaf_capture_called = True
                return original_capture(*args, **kwargs)

            try:
                with mock.patch.object(
                    validator,
                    "capture_declared_helper_snapshot_set",
                    side_effect=record_leaf_capture,
                ):
                    errors = MATERIALIZER_MODULE.materialize(
                        alias_root,
                        "C",
                        [
                            "helpers/H01-provenance.json",
                            "helpers/H01-pages.txt",
                        ],
                    )
                self.assertTrue(errors)
                self.assertFalse(leaf_capture_called)
                self.assertTrue(
                    any("directory chain" in error for error in errors),
                    errors,
                )
            finally:
                alias_parent.rmdir()

    def test_chair_write_interval_helper_hardlink_or_replacement_fails_and_rolls_back(
        self,
    ) -> None:
        for mutation in ("hardlink", "same-bytes-replacement"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
                tempfile.TemporaryDirectory() as external,
            ):
                root = Path(directory)
                external_root = Path(external)
                harness = fixture_module.ValidateReviewBundleTests(
                    methodName="test_complete_fixture_passes"
                )
                digest = harness.build_bundle(root)
                harness.install_helper_fixture(root, digest, recipients=["C"])
                helper = root / "helpers/H01-pages.txt"
                chair_before = {
                    filename: (root / filename).read_bytes()
                    for filename in CHAIR_MATERIALIZED_FILES
                }
                original_atomic = MATERIALIZER_MODULE.atomic_replace_text
                first_write = True

                def inject_at_first_write(*args, **kwargs):
                    nonlocal first_write
                    if first_write:
                        first_write = False
                        if mutation == "hardlink":
                            os.link(helper, external_root / "late-helper-alias.txt")
                        else:
                            replacement = external_root / "replacement.txt"
                            replacement.write_bytes(helper.read_bytes())
                            os.replace(replacement, helper)
                    return original_atomic(*args, **kwargs)

                with mock.patch.object(
                    MATERIALIZER_MODULE,
                    "atomic_replace_text",
                    side_effect=inject_at_first_write,
                ):
                    errors = MATERIALIZER_MODULE.materialize(
                        root,
                        "C",
                        [
                            "helpers/H01-provenance.json",
                            "helpers/H01-pages.txt",
                        ],
                    )

                self.assertFalse(first_write, "the exact write-interval hook was unused")
                self.assertTrue(errors)
                self.assertTrue(
                    any("rolled back" in error for error in errors),
                    errors,
                )
                self.assertEqual(
                    chair_before,
                    {
                        filename: (root / filename).read_bytes()
                        for filename in CHAIR_MATERIALIZED_FILES
                    },
                )

    def test_chair_rollback_never_overwrites_concurrent_output_replacement(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as external,
        ):
            root = Path(directory)
            external_root = Path(external)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            helper = root / "helpers/H01-pages.txt"
            helper_alias = external_root / "late-helper-alias.txt"
            chair_before = {
                filename: (root / filename).read_bytes()
                for filename in CHAIR_MATERIALIZED_FILES
            }
            protected_paths: list[Path] = []
            replacement_payload = b"concurrent external replacement\n"
            replacement = external_root / "replacement.md"
            replacement.write_bytes(replacement_payload)
            original_atomic = MATERIALIZER_MODULE.atomic_replace_text
            first_write = True

            def replace_after_first_published_snapshot(*args, **kwargs):
                nonlocal first_write
                write_error = original_atomic(*args, **kwargs)
                if first_write and write_error is None:
                    first_write = False
                    published_path = args[1]
                    protected_paths.append(published_path)
                    os.replace(replacement, published_path)
                    os.link(helper, helper_alias)
                return write_error

            with mock.patch.object(
                MATERIALIZER_MODULE,
                "atomic_replace_text",
                side_effect=replace_after_first_published_snapshot,
            ):
                errors = MATERIALIZER_MODULE.materialize(
                    root,
                    "C",
                    [
                        "helpers/H01-provenance.json",
                        "helpers/H01-pages.txt",
                    ],
                )

            self.assertFalse(first_write, "the post-publication hook was unused")
            self.assertTrue(errors)
            self.assertTrue(
                any(
                    "rollback refused" in error
                    and "no longer names" in error
                    for error in errors
                ),
                errors,
            )
            self.assertEqual(1, len(protected_paths))
            protected_path = protected_paths[0]
            self.assertEqual(replacement_payload, protected_path.read_bytes())
            for filename in CHAIR_MATERIALIZED_FILES:
                path = root / filename
                if path != protected_path:
                    self.assertEqual(chair_before[filename], path.read_bytes())

    @unittest.skipUnless(os.name == "nt", "NTFS ADS is Windows-specific")
    def test_chair_write_interval_helper_ads_fails_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            helper = root / "helpers/H01-pages.txt"
            stream = Path(f"{helper}:late-materialization")
            try:
                stream.write_text("probe\n", encoding="utf-8")
                stream.unlink()
            except OSError as exc:
                self.skipTest(f"test volume does not support NTFS ADS: {exc}")
            chair_before = {
                filename: (root / filename).read_bytes()
                for filename in CHAIR_MATERIALIZED_FILES
            }
            original_atomic = MATERIALIZER_MODULE.atomic_replace_text
            first_write = True

            def inject_at_first_write(*args, **kwargs):
                nonlocal first_write
                if first_write:
                    first_write = False
                    stream.write_text("late hidden bytes\n", encoding="utf-8")
                return original_atomic(*args, **kwargs)

            try:
                with mock.patch.object(
                    MATERIALIZER_MODULE,
                    "atomic_replace_text",
                    side_effect=inject_at_first_write,
                ):
                    errors = MATERIALIZER_MODULE.materialize(
                        root,
                        "C",
                        [
                            "helpers/H01-provenance.json",
                            "helpers/H01-pages.txt",
                        ],
                    )
                self.assertFalse(first_write, "the exact write-interval hook was unused")
                self.assertTrue(errors)
                self.assertTrue(
                    any("named streams" in error for error in errors),
                    errors,
                )
                self.assertTrue(
                    any("rolled back" in error for error in errors),
                    errors,
                )
                self.assertEqual(
                    chair_before,
                    {
                        filename: (root / filename).read_bytes()
                        for filename in CHAIR_MATERIALIZED_FILES
                    },
                )
            finally:
                try:
                    stream.unlink(missing_ok=True)
                except OSError:
                    pass

    @unittest.skipUnless(os.name == "nt", "NTFS junction test is Windows-specific")
    def test_chair_write_interval_helpers_junction_fails_and_rolls_back(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as external,
        ):
            root = Path(directory)
            external_root = Path(external)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            helpers = root / "helpers"
            real_helpers = external_root / "real-helpers"
            chair_before = {
                filename: (root / filename).read_bytes()
                for filename in CHAIR_MATERIALIZED_FILES
            }
            original_atomic = MATERIALIZER_MODULE.atomic_replace_text
            first_write = True
            junction_created = False

            def inject_at_first_write(*args, **kwargs):
                nonlocal first_write, junction_created
                if first_write:
                    first_write = False
                    helpers.rename(real_helpers)
                    created = subprocess.run(
                        [
                            "cmd", "/c", "mklink", "/J",
                            str(helpers), str(real_helpers),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if created.returncode != 0:
                        real_helpers.rename(helpers)
                        raise unittest.SkipTest(
                            f"could not create NTFS junction: {created.stderr}"
                        )
                    junction_created = True
                return original_atomic(*args, **kwargs)

            try:
                with mock.patch.object(
                    MATERIALIZER_MODULE,
                    "atomic_replace_text",
                    side_effect=inject_at_first_write,
                ):
                    errors = MATERIALIZER_MODULE.materialize(
                        root,
                        "C",
                        [
                            "helpers/H01-provenance.json",
                            "helpers/H01-pages.txt",
                        ],
                    )
                self.assertFalse(first_write, "the exact write-interval hook was unused")
                self.assertTrue(junction_created)
                self.assertTrue(errors)
                self.assertTrue(
                    any("rolled back" in error for error in errors),
                    errors,
                )
                self.assertEqual(
                    chair_before,
                    {
                        filename: (root / filename).read_bytes()
                        for filename in CHAIR_MATERIALIZED_FILES
                    },
                )
            finally:
                if helpers.exists() and helpers.is_junction():
                    helpers.rmdir()
                if real_helpers.exists() and not helpers.exists():
                    real_helpers.rename(helpers)

    def test_chair_uses_exact_explicit_valid_helper_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.build_bundle(root)
            harness.install_helper_fixture(root, digest, recipients=["C"])
            helper_inputs = [
                "helpers/H01-provenance.json",
                "helpers/H01-pages.txt",
            ]
            result = self.run_materializer(root, "C", helper_inputs)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            expected_opened = [
                *fixture_module.VALIDATOR_MODULE.canonical_stage_opened_inputs(
                    process, 3, "C"
                ),
                *helper_inputs,
            ]
            for filename, label in (
                ("90-chair-synthesis.md", "Chair input-receipt/access declaration"),
                ("91-revision-ledger.md", "Input-receipt/access declaration"),
                ("92-new-evidence-or-experiments.md", "Input-receipt/access declaration"),
            ):
                _receipt, parsed = self.parsed_receipt(root / filename, label)
                self.assertEqual(expected_opened, parsed["opened"], filename)

            before_second = file_hashes(root)
            second = self.run_materializer(root, "C", helper_inputs)
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            self.assertEqual(before_second, file_hashes(root))

    def test_chair_and_stage_s_materializers_do_not_enumerate_root_or_read_forbidden_stage_files(
        self,
    ) -> None:
        cases = {
            "C": {
                "93-user-facing-summary.md",
                "93-current-actionable-items.csv",
                "93-current-ai-actionable-items.csv",
                "95-bundle-validation.md",
            },
            "S": {
                "frozen-thesis.pdf",
                "00-page-inventory.csv",
                "00-bibliography-inventory.csv",
                "00-citation-candidate-ledger.csv",
                "00-citation-inventory.csv",
                "00-unmatched-bracket-ledger.csv",
                "02-page-layout-ledger.csv",
                "02-page-layout-ledger.md",
                "03-bibliography-audit-ledger.csv",
                "03-bibliography-audit-ledger.md",
                "04-citation-claim-audit-ledger.csv",
                "04-citation-claim-audit-ledger.md",
                "95-bundle-validation.md",
            },
        }
        for actor_id, forbidden_names in cases.items():
            with self.subTest(actor=actor_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                harness = fixture_module.ValidateReviewBundleTests(
                    methodName="test_complete_fixture_passes"
                )
                harness.build_bundle(root)
                if actor_id == "S":
                    for filename in STAGE_S_FILES:
                        (root / filename).unlink()
                (root / "95-bundle-validation.md").write_text(
                    "forbidden downstream sentinel\n", encoding="utf-8"
                )
                root_absolute = root.absolute()
                original_iterdir = Path.iterdir
                original_glob = Path.glob
                original_rglob = Path.rglob
                original_open = Path.open

                def is_round_root(path: Path) -> bool:
                    return path.absolute() == root_absolute

                def guarded_iterdir(path: Path):
                    if is_round_root(path):
                        raise AssertionError(f"{actor_id} materializer enumerated root")
                    return original_iterdir(path)

                def guarded_glob(path: Path, pattern: str, *args, **kwargs):
                    if is_round_root(path):
                        raise AssertionError(
                            f"{actor_id} materializer globbed root with {pattern!r}"
                        )
                    return original_glob(path, pattern, *args, **kwargs)

                def guarded_rglob(path: Path, pattern: str, *args, **kwargs):
                    if is_round_root(path):
                        raise AssertionError(
                            f"{actor_id} materializer recursively globbed root "
                            f"with {pattern!r}"
                        )
                    return original_rglob(path, pattern, *args, **kwargs)

                def guarded_open(path: Path, *args, **kwargs):
                    absolute = path.absolute()
                    try:
                        relative = absolute.relative_to(root_absolute)
                    except ValueError:
                        relative = None
                    if relative is not None and relative.as_posix() in forbidden_names:
                        raise AssertionError(
                            f"{actor_id} materializer opened forbidden "
                            f"round file {relative.as_posix()}"
                        )
                    return original_open(path, *args, **kwargs)

                with (
                    mock.patch.object(Path, "iterdir", guarded_iterdir),
                    mock.patch.object(Path, "glob", guarded_glob),
                    mock.patch.object(Path, "rglob", guarded_rglob),
                    mock.patch.object(Path, "open", guarded_open),
                ):
                    errors = MATERIALIZER_MODULE.materialize(root, actor_id)
                self.assertEqual([], errors)

    def test_production_renderer_round_trips_literal_pipes_and_backslashes(self) -> None:
        module = fixture_module.VALIDATOR_MODULE
        headers = ["ID", "Value", "Note"]
        rows = [["X1", "A | B", r"one\|two \\| three"]]
        table = module.render_markdown_pipe_table(headers, rows)
        errors: list[str] = []
        parsed = module.parse_markdown_table_by_exact_headers(
            table, headers, "probe.md", errors, case_sensitive=True
        )
        self.assertEqual([], errors)
        self.assertEqual(rows, parsed)
        self.assertEqual(table, module.render_markdown_pipe_table(headers, rows))

    def test_r4_and_masters_r3_materializer_paths_pass_their_scoped_gates(self) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        with self.subTest(actor="doctoral R4"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness.build_bundle(root)
            harness.convert_bundle_to_doctorate(root)
            materialized = self.run_materializer(root, "R4")
            self.assertEqual(0, materialized.returncode, materialized.stdout)
            gated = self.run_gate(R4_VALIDATOR, root)
            self.assertEqual(0, gated.returncode, gated.stdout + gated.stderr)

        with self.subTest(actor="masters R3"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness.build_bundle(root)
            materialized = self.run_materializer(root, "R3")
            self.assertEqual(0, materialized.returncode, materialized.stdout)
            gated = self.run_gate(MASTER_R3_VALIDATOR, root)
            self.assertEqual(0, gated.returncode, gated.stdout + gated.stderr)

    def test_materializer_does_not_enumerate_root_or_open_peer_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root)
            harness.convert_bundle_to_doctorate(root)
            original_iterdir = Path.iterdir
            original_open = Path.open

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("materializer enumerated the round root")
                return original_iterdir(path)

            def guarded_open(path: Path, *args, **kwargs):
                if path.name in PEER_AND_DOWNSTREAM_FILES:
                    raise AssertionError(
                        f"materializer opened peer/downstream file {path.name}"
                    )
                return original_open(path, *args, **kwargs)

            with (
                mock.patch.object(Path, "iterdir", guarded_iterdir),
                mock.patch.object(Path, "open", guarded_open),
            ):
                errors = MATERIALIZER_MODULE.materialize(root, "R5")
            self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
