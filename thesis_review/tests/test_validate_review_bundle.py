from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL_ROOT / "scripts" / "validate_review_bundle.py"
PROMPT_HASH = "A" * 64

PAGE_INVENTORY_COLUMNS = [
    "PageID", "PhysicalPage", "PrintedPage", "Region",
    "MechanicalSignals", "PDFSHA256",
]
PAGE_LEDGER_COLUMNS = [
    "PageID", "PhysicalPage", "PrintedPage", "Region", "DominantContent",
    "Signals", "InspectionModeScale", "RenderDPI", "RenderArtifactIDHash",
    "NeighborPagesChecked", "Disposition", "Evidence", "PDFSHA256",
]
BIB_INVENTORY_COLUMNS = [
    "ReferenceID", "DisplayedLabel", "RenderedEntry", "Cited", "PDFSHA256",
]
BIB_LEDGER_COLUMNS = [
    "ReferenceID", "DisplayedLabel", "Cited", "Field", "RenderedValue",
    "CanonicalValue", "Verdict", "EvidenceEndpoint", "EndpointType",
    "CheckedAt", "EvidenceNote", "FindingDisposition", "PDFSHA256",
]
CITATION_INVENTORY_COLUMNS = [
    "PairID", "OccurrenceID", "PDFLocation", "DisplayedReferenceID",
    "AdjacentPDFText", "PDFSHA256",
]
CITATION_LEDGER_COLUMNS = [
    "PairID", "OccurrenceID", "PDFLocation", "ExactAttachedProposition",
    "ReferenceID", "PublicIdentifier", "ContentSourceOpened",
    "ExactSourceLocator", "Support", "MetadataStatus", "SeverityFinding",
    "DispositionEvidence", "PDFSHA256",
]
ACADEMIC_LEDGER_COLUMNS = [
    "LedgerID", "Priority", "ChairFindingID", "SourceReviewerFindingIDs",
    "Severity", "Remedy", "ExactPDFAnchor", "DirectObservation",
    "MinimumEditEvidence", "Dependency", "Owner", "Status", "Verification",
]
AI_LEDGER_COLUMNS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "Status", "Verification",
]
ACADEMIC_SUMMARY_COLUMNS = [
    "LedgerID", "CurrentFindingIDs", "SeverityRemedy", "ExactPDFAnchor",
    "DirectPDFObservation", "MinimumRequiredAction", "OriginReviewers",
    "ChairDisposition",
]
AI_SUMMARY_COLUMNS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "ChairStatus",
]
BIB_FIELDS = [
    "type", "title", "ordered_authors", "year", "venue",
    "publication_status", "volume", "issue", "pages_or_article_number",
    "doi", "arxiv_id", "arxiv_version", "url", "access_date",
    "isbn_or_other_persistent_id", "existence",
    "retraction_withdrawal_correction_superseding",
]


def write_csv(
    path: Path, headers: list[str], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


class ValidateReviewBundleTests(unittest.TestCase):
    def declaration(self, digest: str) -> str:
        return (
            "- Fresh-context declaration: clean empty context\n"
            "- Input-receipt/access declaration: "
            f"Prompt SHA-256: {PROMPT_HASH}; received operational prompt; "
            "opened frozen PDF and allowlisted rules only\n"
            f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n"
        )

    def reviewer_report(self, digest: str) -> str:
        gate_rows = "\n".join(
            f"| {gate} — gate | baseline | adequate | p.1 | none | high |"
            for gate in "ABCDEFGHI"
        )
        return (
            "# Comprehensive review\n\n"
            + self.declaration(digest)
            + "- Academic grade: B\n"
            + "- Defense recommendation: 小修后可答辩\n\n"
            + "| Gate | Depth | Disposition | Evidence | Findings | Confidence |\n"
            + "|---|---|---|---|---|---|\n"
            + gate_rows
            + "\n"
        )

    def chair_report(self, digest: str) -> str:
        return (
            "# Chair synthesis\n\n"
            + self.declaration(digest)
            + "- Overall academic grade: B\n"
            + "- Overall defense recommendation: 小修后可答辩\n\n"
            + "## Mandatory citation cross-ledger consistency gate\n\n"
            + "| Rendered reference ID | R4 identity/source | R5 canonical identity | "
            + "Version/record agreement | Affected Pair IDs | Conflict class | "
            + "Reclassification/finding | Resolution |\n"
            + "|---|---|---|---|---|---|---|---|\n"
            + "| REF0001 | verified | verified | agree | C0001-S01 | none | none | closed |\n\n"
            + "- Unique cited rendered references joined: 1\n"
            + "- Identity-agreement count: 1\n"
            + "- Version disagreements: 0\n"
            + "- Local conflicts: 0\n"
            + "- Substantive conflicts: 0\n"
            + "- Reclassified Pair IDs: 0\n"
            + "- Unresolved conflicts: 0\n"
            + "- Combined citation gate: pass\n"
        )

    def ai_report(self, digest: str) -> str:
        return (
            "# Standalone AI-style prose assessment\n\n"
            + self.declaration(digest)
            + "- Required disclaimer: This is a prose-style assessment, not a "
            + "determination of AI use, authorship, plagiarism, or misconduct.\n"
            + "- AI-style signal: moderate\n"
        )

    def summary_report(
        self, digest: str, academic_count: int = 1, ai_count: int = 1
    ) -> str:
        return (
            "# Current-round user-facing review summary\n\n"
            + self.declaration(digest)
            + "## Current actionable items\n\n"
            + "See authoritative CSV.\n\n"
            + "## Current AI-style actionable items — separate from academic grading\n\n"
            + "See authoritative CSV.\n\n"
            + "## Reconciliation\n\n"
            + f"- Open required rows in 91-revision-ledger.md: {academic_count}\n"
            + f"- Rows in Current actionable items: {academic_count}\n"
            + "- Missing ledger IDs: none\n"
            + "- Extra summary IDs: none\n"
            + "- Duplicate IDs: none\n"
            + f"- Open AI rows in 91-ai-actionable-ledger.csv: {ai_count}\n"
            + f"- Rows in Current AI-style actionable items: {ai_count}\n"
            + "- Missing/extra/duplicate AI finding IDs: none\n"
            + "- Statement: This summary introduces no new finding and uses no "
            + "prior-round or author-side information.\n"
        )

    def build_bundle(self, root: Path) -> str:
        pdf = root / "frozen-thesis.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=595.28, height=841.89)
        with pdf.open("wb") as handle:
            writer.write(handle)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest().upper()
        process = {
            "round_id": "fixture",
            "retry_id": "r1",
            "frozen_pdf_file": pdf.name,
            "selected_pdf_sha256": digest,
            "physical_page_count": 1,
            "degree_level": "masters",
            "degree_type": "academic",
            "institution": None,
            "school_or_department": None,
            "discipline": "computer science",
            "expected_submission_year": 2026,
            "artifact_type": "author-copy",
            "review_mode": "initial",
            "output_language": "zh-CN",
            "governing_rule_urls": [],
            "governing_local_files": [],
            "decision_regime_status": "skill-default",
        }
        (root / "00-process-parameters.json").write_text(
            json.dumps(process), encoding="utf-8"
        )
        (root / "00-manifest.md").write_text(
            "# Manifest\n\n" + self.declaration(digest), encoding="utf-8"
        )
        (root / "01-policy-basis.md").write_text(
            "# Policy\n\n" + self.declaration(digest), encoding="utf-8"
        )
        (root / "02-page-layout-ledger.md").write_text(
            "# Page ledger\n\n| PageID | Disposition |\n|---|---|\n| P0001 | clean |\n",
            encoding="utf-8",
        )
        (root / "03-bibliography-audit-ledger.md").write_text(
            "# Bibliography ledger\n\n| ReferenceID | Disposition |\n|---|---|\n"
            "| REF0001 | verified |\n",
            encoding="utf-8",
        )
        (root / "04-citation-claim-audit-ledger.md").write_text(
            "# Citation ledger\n\n| PairID | Support |\n|---|---|\n"
            "| C0001-S01 | direct |\n",
            encoding="utf-8",
        )
        for filename in ("91-revision-ledger.md", "92-new-evidence-or-experiments.md"):
            (root / filename).write_text("# Complete\n", encoding="utf-8")
        for index in range(1, 4):
            (root / f"R{index}-comprehensive-review.md").write_text(
                self.reviewer_report(digest), encoding="utf-8"
            )
        (root / "05-ai-style-assessment.md").write_text(
            self.ai_report(digest), encoding="utf-8"
        )
        (root / "90-chair-synthesis.md").write_text(
            self.chair_report(digest), encoding="utf-8"
        )
        (root / "93-user-facing-summary.md").write_text(
            self.summary_report(digest), encoding="utf-8"
        )
        write_csv(
            root / "00-page-inventory.csv",
            PAGE_INVENTORY_COLUMNS,
            [{
                "PageID": "P0001",
                "PhysicalPage": "1",
                "PrintedPage": "",
                "Region": "front matter",
                "MechanicalSignals": "none",
                "PDFSHA256": digest,
            }],
        )
        write_csv(
            root / "02-page-layout-ledger.csv",
            PAGE_LEDGER_COLUMNS,
            [{
                "PageID": "P0001",
                "PhysicalPage": "1",
                "PrintedPage": "",
                "Region": "front matter",
                "DominantContent": "text",
                "Signals": "none",
                "InspectionModeScale": "individual 100%",
                "RenderDPI": "200",
                "RenderArtifactIDHash": f"P0001:{digest}",
                "NeighborPagesChecked": "boundary page; none",
                "Disposition": "clean",
                "Evidence": "full-page render inspected",
                "PDFSHA256": digest,
            }],
        )
        write_csv(
            root / "00-bibliography-inventory.csv",
            BIB_INVENTORY_COLUMNS,
            [{
                "ReferenceID": "REF0001",
                "DisplayedLabel": "[1]",
                "RenderedEntry": "Fixture reference.",
                "Cited": "yes",
                "PDFSHA256": digest,
            }],
        )
        write_csv(
            root / "03-bibliography-audit-ledger.csv",
            BIB_LEDGER_COLUMNS,
            [{
                "ReferenceID": "REF0001",
                "DisplayedLabel": "[1]",
                "Cited": "yes",
                "Field": field,
                "RenderedValue": "fixture",
                "CanonicalValue": "fixture",
                "Verdict": "exact",
                "EvidenceEndpoint": "https://doi.org/10.1145/3442188.3445922",
                "EndpointType": "official fixture",
                "CheckedAt": "2026-08-29",
                "EvidenceNote": "fixture official record checked",
                "FindingDisposition": "no finding",
                "PDFSHA256": digest,
            } for field in BIB_FIELDS],
        )
        write_csv(
            root / "00-citation-inventory.csv",
            CITATION_INVENTORY_COLUMNS,
            [{
                "PairID": "C0001-S01",
                "OccurrenceID": "C0001",
                "PDFLocation": "physical p.1",
                "DisplayedReferenceID": "REF0001",
                "AdjacentPDFText": "fixture proposition [1]",
                "PDFSHA256": digest,
            }],
        )
        write_csv(
            root / "04-citation-claim-audit-ledger.csv",
            CITATION_LEDGER_COLUMNS,
            [{
                "PairID": "C0001-S01",
                "OccurrenceID": "C0001",
                "PDFLocation": "physical p.1",
                "ExactAttachedProposition": "fixture proposition",
                "ReferenceID": "REF0001",
                "PublicIdentifier": "doi:fixture",
                "ContentSourceOpened": "https://dl.acm.org/doi/pdf/10.1145/3442188.3445922",
                "ExactSourceLocator": "p.1",
                "Support": "direct",
                "MetadataStatus": "verified",
                "SeverityFinding": "none",
                "DispositionEvidence": "supported",
                "PDFSHA256": digest,
            }],
        )
        write_csv(
            root / "91-revision-ledger.csv",
            ACADEMIC_LEDGER_COLUMNS,
            [{
                "LedgerID": "L01",
                "Priority": "P2",
                "ChairFindingID": "C-F01",
                "SourceReviewerFindingIDs": "R1-F01",
                "Severity": "S2",
                "Remedy": "W",
                "ExactPDFAnchor": "physical p.1",
                "DirectObservation": "visible wording defect",
                "MinimumEditEvidence": "correct the wording",
                "Dependency": "none",
                "Owner": "author",
                "Status": "open",
                "Verification": "reinspect p.1",
            }],
        )
        write_csv(
            root / "93-current-actionable-items.csv",
            ACADEMIC_SUMMARY_COLUMNS,
            [{
                "LedgerID": "L01",
                "CurrentFindingIDs": "C-F01",
                "SeverityRemedy": "S2/W",
                "ExactPDFAnchor": "physical p.1",
                "DirectPDFObservation": "visible wording defect",
                "MinimumRequiredAction": "correct the wording",
                "OriginReviewers": "R1-F01",
                "ChairDisposition": "open",
            }],
        )
        write_csv(
            root / "91-ai-actionable-ledger.csv",
            AI_LEDGER_COLUMNS,
            [{
                "AIFindingID": "AI-F01",
                "Impact": "local",
                "ExactPDFAnchor": "physical p.1",
                "DirectStyleObservation": "formulaic transition",
                "MinimumEditingAction": "replace the transition",
                "Status": "open",
                "Verification": "reread paragraph",
            }],
        )
        write_csv(
            root / "93-current-ai-actionable-items.csv",
            AI_SUMMARY_COLUMNS,
            [{
                "AIFindingID": "AI-F01",
                "Impact": "local",
                "ExactPDFAnchor": "physical p.1",
                "DirectStyleObservation": "formulaic transition",
                "MinimumEditingAction": "replace the transition",
                "ChairStatus": "open",
            }],
        )
        return digest

    def run_validator(
        self, root: Path, report: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-B", str(VALIDATOR), str(root)]
        if report:
            command.extend(["--write-report", str(report)])
        return subprocess.run(
            command, text=True, capture_output=True, check=False
        )

    def assert_fails(self, root: Path, needle: str) -> None:
        result = self.run_validator(root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(needle, result.stdout)

    def test_complete_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_invalid_pdf_and_declared_page_count_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            pdf = root / "frozen-thesis.pdf"
            pdf.write_bytes(b"NOT A PDF")
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["selected_pdf_sha256"] = hashlib.sha256(
                pdf.read_bytes()
            ).hexdigest().upper()
            process["physical_page_count"] = 2
            process_path.write_text(json.dumps(process), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid PDF header", result.stdout)

    def test_real_pdf_page_count_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["physical_page_count"] = 2
            process_path.write_text(json.dumps(process), encoding="utf-8")
            self.assert_fails(root, "parsed page count 1")

    def test_markdown_master_shell_and_missing_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "03-bibliography-audit-ledger.md").write_text(
                "# x\n", encoding="utf-8"
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Markdown master is empty or shell-only", result.stdout)
            self.assertIn("bibliography ledger Markdown projection", result.stdout)

    def test_fake_endpoint_date_locator_and_render_record_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, bib_rows = read_csv(root / "03-bibliography-audit-ledger.csv")
            bib_rows[0]["EvidenceEndpoint"] = "claimed endpoint"
            bib_rows[0]["CheckedAt"] = "sometime"
            write_csv(
                root / "03-bibliography-audit-ledger.csv",
                BIB_LEDGER_COLUMNS,
                bib_rows,
            )
            _, citation_rows = read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            citation_rows[0]["ContentSourceOpened"] = "claimed full text"
            citation_rows[0]["ExactSourceLocator"] = "somewhere"
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                citation_rows,
            )
            _, page_rows = read_csv(root / "02-page-layout-ledger.csv")
            page_rows[0]["RenderDPI"] = "1"
            page_rows[0]["RenderArtifactIDHash"] = "claimed hash"
            write_csv(
                root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, page_rows
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("EvidenceEndpoint lacks an http(s)", result.stdout)
            self.assertIn("CheckedAt must be an ISO-8601", result.stdout)
            self.assertIn("ContentSourceOpened lacks an http(s)", result.stdout)
            self.assertIn("ExactSourceLocator lacks a page/section", result.stdout)
            self.assertIn("RenderDPI must be an integer in", result.stdout)
            self.assertIn("RenderArtifactIDHash must be a 64-hex hash", result.stdout)

    def test_chair_citation_gate_cannot_pass_unresolved_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            chair_path = root / "90-chair-synthesis.md"
            chair = chair_path.read_text(encoding="utf-8").replace(
                "- Substantive conflicts: 0", "- Substantive conflicts: 1"
            )
            chair_path.write_text(chair, encoding="utf-8")
            self.assert_fails(root, "Combined citation gate cannot pass")

    def test_summary_extra_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            write_csv(
                root / "93-current-actionable-items.csv",
                ACADEMIC_SUMMARY_COLUMNS,
                [{
                    "LedgerID": "OLD-X",
                    "CurrentFindingIDs": "OLD",
                    "SeverityRemedy": "S2/W",
                    "ExactPDFAnchor": "p.1",
                    "DirectPDFObservation": "old",
                    "MinimumRequiredAction": "old",
                    "OriginReviewers": "old",
                    "ChairDisposition": "open",
                }],
            )
            self.assert_fails(root, "current academic summary")

    def test_empty_page_ledgers_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            write_csv(root / "00-page-inventory.csv", PAGE_INVENTORY_COLUMNS, [])
            write_csv(root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, [])
            self.assert_fails(root, "header-only or empty")

    def test_missing_full_schema_column_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            headers, rows = read_csv(root / "02-page-layout-ledger.csv")
            headers.remove("Evidence")
            for row in rows:
                row.pop("Evidence", None)
            write_csv(root / "02-page-layout-ledger.csv", headers, rows)
            self.assert_fails(root, "schema mismatch")

    def test_page_mapping_and_invalid_mode_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "02-page-layout-ledger.csv")
            rows[0]["PhysicalPage"] = "2"
            rows[0]["Signals"] = "bottom crowding"
            rows[0]["InspectionModeScale"] = "nonsense"
            write_csv(root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, rows)
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid InspectionModeScale", result.stdout)
            self.assertIn("page mapping mismatch", result.stdout)

    def test_suspect_page_requires_full_scale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "02-page-layout-ledger.csv")
            rows[0]["Signals"] = "bottom crowding"
            write_csv(root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, rows)
            self.assert_fails(root, "was not inspected full-scale")

    def test_citation_pair_mapping_and_unknown_reference_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "04-citation-claim-audit-ledger.csv")
            rows[0]["OccurrenceID"] = "WRONG"
            rows[0]["ReferenceID"] = "REF9999"
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                rows,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("citation mapping mismatch", result.stdout)
            self.assertIn("unknown ReferenceID", result.stdout)

    def test_documented_unverifiable_rows_allow_missing_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, bib_rows = read_csv(root / "03-bibliography-audit-ledger.csv")
            bib_rows[0]["Verdict"] = "unverifiable"
            bib_rows[0]["CanonicalValue"] = "not established"
            bib_rows[0]["EvidenceEndpoint"] = ""
            bib_rows[0]["EndpointType"] = "official route inaccessible"
            bib_rows[0]["EvidenceNote"] = (
                "Attempted the official publisher route on 2026-08-29; "
                "the record was inaccessible."
            )
            write_csv(
                root / "03-bibliography-audit-ledger.csv",
                BIB_LEDGER_COLUMNS,
                bib_rows,
            )
            _, citation_rows = read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            citation_rows[0]["ContentSourceOpened"] = ""
            citation_rows[0]["ExactSourceLocator"] = ""
            citation_rows[0]["Support"] = "unverifiable"
            citation_rows[0]["DispositionEvidence"] = (
                "Official full-text route attempted but inaccessible."
            )
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                citation_rows,
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verified_rows_require_endpoint_and_content_locator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, bib_rows = read_csv(root / "03-bibliography-audit-ledger.csv")
            bib_rows[0]["EvidenceEndpoint"] = ""
            write_csv(
                root / "03-bibliography-audit-ledger.csv",
                BIB_LEDGER_COLUMNS,
                bib_rows,
            )
            _, citation_rows = read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            citation_rows[0]["ContentSourceOpened"] = ""
            citation_rows[0]["ExactSourceLocator"] = ""
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                citation_rows,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verified verdict lacks authoritative evidence endpoint", result.stdout)
            self.assertIn("substantive verdict lacks content source", result.stdout)
            self.assertIn("substantive verdict lacks exact locator", result.stdout)

    def test_invalid_academic_enums_and_blank_anchor_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["Severity"] = "BANANA"
            rows[0]["Remedy"] = "BAD"
            rows[0]["ExactPDFAnchor"] = ""
            write_csv(root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows)
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid Severity", result.stdout)
            self.assertIn("invalid Remedy", result.stdout)
            self.assertIn("blank mandatory field ExactPDFAnchor", result.stdout)

    def test_invalid_ai_impact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "91-ai-actionable-ledger.csv")
            rows[0]["Impact"] = "BANANA"
            write_csv(root / "91-ai-actionable-ledger.csv", AI_LEDGER_COLUMNS, rows)
            self.assert_fails(root, "invalid Impact")

    def test_invalid_status_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["Status"] = "mystery"
            write_csv(root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows)
            self.assert_fails(root, "invalid Status")

    def test_placeholder_mandatory_field_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "00-citation-inventory.csv")
            rows[0]["AdjacentPDFText"] = "TODO"
            write_csv(
                root / "00-citation-inventory.csv",
                CITATION_INVENTORY_COLUMNS,
                rows,
            )
            self.assert_fails(root, "placeholder in mandatory field")

    def test_academic_91_93_content_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "93-current-actionable-items.csv")
            rows[0]["CurrentFindingIDs"] = "DIFFERENT"
            rows[0]["SeverityRemedy"] = "S0/N"
            rows[0]["ExactPDFAnchor"] = "p.999"
            rows[0]["ChairDisposition"] = "closed"
            write_csv(
                root / "93-current-actionable-items.csv",
                ACADEMIC_SUMMARY_COLUMNS,
                rows,
            )
            self.assert_fails(root, "academic 91->93 mismatch")

    def test_ai_91_93_content_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "93-current-ai-actionable-items.csv")
            rows[0]["Impact"] = "material"
            rows[0]["ExactPDFAnchor"] = "p.999"
            rows[0]["ChairStatus"] = "closed"
            write_csv(
                root / "93-current-ai-actionable-items.csv",
                AI_SUMMARY_COLUMNS,
                rows,
            )
            self.assert_fails(root, "AI 91->93 mismatch")

    def test_bad_prompt_hash_declaration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R1-comprehensive-review.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(PROMPT_HASH, "short"),
                encoding="utf-8",
            )
            self.assert_fails(root, "operational prompt SHA-256")

    def test_missing_gate_and_grade_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R2-comprehensive-review.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace("| I — gate | baseline | adequate | p.1 | none | high |\n", "")
            text = text.replace("- Academic grade: B\n", "")
            path.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Gate I", result.stdout)
            self.assertIn("missing explicit academic grade", result.stdout)

    def test_missing_chair_cross_ledger_result_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "90-chair-synthesis.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "- Combined citation gate: pass\n", ""
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "Combined citation gate")

    def test_missing_ai_disclaimer_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "05-ai-style-assessment.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "- Required disclaimer: This is a prose-style assessment, not a "
                "determination of AI use, authorship, plagiarism, or misconduct.\n",
                "",
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "non-attribution disclaimer")

    def test_summary_reconciliation_count_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "- Rows in Current actionable items: 1",
                    "- Rows in Current actionable items: 99",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "93 academic reconciliation count")

    def test_frozen_pdf_hash_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "frozen-thesis.pdf").write_bytes(b"changed")
            self.assert_fails(root, "frozen PDF hash mismatch")

    def test_doctorate_requires_r4_r5(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["degree_level"] = "doctorate"
            process_path.write_text(json.dumps(process), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("R4-comprehensive-review.md", result.stdout)
            self.assertIn("R5-comprehensive-review.md", result.stdout)

    def test_valid_helper_provenance_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            helpers = root / "helpers"
            helpers.mkdir()
            sidecar = helpers / "H01-pages.txt"
            sidecar.write_text("mechanical output", encoding="utf-8")
            sidecar_hash = hashlib.sha256(sidecar.read_bytes()).hexdigest().upper()
            provenance = {
                "actor_id": "H01",
                "round_id": "fixture",
                "retry_id": "r1",
                "prompt_sha256": PROMPT_HASH,
                "fresh_context_declaration": "clean empty context",
                "input_receipt_access_declaration": "received prompt; opened PDF",
                "received_blocks": ["operational prompt"],
                "opened_inputs": ["frozen-thesis.pdf"],
                "tool": "fixture",
                "version": "1",
                "command_or_query": "fixture --read-only",
                "pdf_sha256_start": digest,
                "pdf_sha256_end": digest,
                "outputs": [{"file": sidecar.name, "sha256": sidecar_hash}],
                "limitations": [],
                "recipient_stages": ["R5"],
            }
            (helpers / "H01-provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_helper_hash_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            helpers = root / "helpers"
            helpers.mkdir()
            sidecar = helpers / "H01-pages.txt"
            sidecar.write_text("mechanical output", encoding="utf-8")
            provenance = {
                "actor_id": "H01",
                "round_id": "fixture",
                "retry_id": "r1",
                "prompt_sha256": PROMPT_HASH,
                "fresh_context_declaration": "clean empty context",
                "input_receipt_access_declaration": "received prompt; opened PDF",
                "received_blocks": ["operational prompt"],
                "opened_inputs": ["frozen-thesis.pdf"],
                "tool": "fixture",
                "version": "1",
                "command_or_query": "fixture --read-only",
                "pdf_sha256_start": digest,
                "pdf_sha256_end": digest,
                "outputs": [{"file": sidecar.name, "sha256": "0" * 64}],
                "limitations": [],
                "recipient_stages": ["R5"],
            }
            (helpers / "H01-provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            self.assert_fails(root, "hash mismatch for H01-pages.txt")

    def test_empty_helper_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "helpers").mkdir()
            self.assert_fails(root, "empty directory must be omitted")

    def test_write_report_records_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "95-bundle-validation.md"
            result = self.run_validator(root, report)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(report.is_file())
            self.assertIn("**PASS**", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
