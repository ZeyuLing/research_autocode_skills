from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL_ROOT / "scripts" / "validate_review_bundle.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "thesis_review_validator_under_test", VALIDATOR
)
assert VALIDATOR_SPEC and VALIDATOR_SPEC.loader
VALIDATOR_MODULE = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR_MODULE)
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
CITATION_CANDIDATE_COLUMNS = [
    "CandidateID", "PhysicalPage", "Marker", "ExpandedNumbers",
    "Classification", "ClassificationEvidence", "MappedOccurrenceID",
    "AdjacentPDFText", "PDFSHA256",
]
UNMATCHED_BRACKET_COLUMNS = [
    "GlyphID", "PhysicalPage", "Glyph", "AdjacentPDFText", "Disposition",
    "PDFSHA256",
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


def write_grayscale_png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    raw = (b"\x00" + b"\xff" * width) * height
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
        )
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def write_empty_idat_png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
        )
        + chunk(b"IDAT", b"")
        + chunk(b"IEND", b"")
    )


def add_ascii_text(
    writer: PdfWriter, page: object, text: str
) -> None:
    escaped_lines = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in text.splitlines() or [""]
    ]
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    resources = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
    })
    stream = DecodedStreamObject()
    commands = ["BT /F1 12 Tf 72 720 Td"]
    for index, escaped in enumerate(escaped_lines):
        if index:
            commands.append("0 -18 Td")
        commands.append(f"({escaped}) Tj")
    commands.append("ET")
    stream.set_data(" ".join(commands).encode("ascii"))
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)


class ValidateReviewBundleTests(unittest.TestCase):
    def rewrite_pdf_and_rehash(self, root: Path, page_texts: list[str]) -> str:
        process_path = root / "00-process-parameters.json"
        process = json.loads(process_path.read_text(encoding="utf-8"))
        old_digest = process["selected_pdf_sha256"]
        writer = PdfWriter()
        for text in page_texts:
            page = writer.add_blank_page(width=595.28, height=841.89)
            add_ascii_text(writer, page, text)
        pdf_path = root / process["frozen_pdf_file"]
        with pdf_path.open("wb") as handle:
            writer.write(handle)
        new_digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest().upper()
        for path in root.iterdir():
            if path.is_file() and path.suffix.casefold() in {".md", ".csv", ".json"}:
                content = path.read_text(encoding="utf-8")
                path.write_text(content.replace(old_digest, new_digest), encoding="utf-8")
        return new_digest

    def declaration(self, digest: str) -> str:
        return (
            "- Fresh-context declaration: no inherited user/thread/task turns "
            "beyond system/developer instructions and the exact operational prompt\n"
            "- Input-receipt/access declaration: "
            f"Prompt SHA-256: {PROMPT_HASH}; received operational prompt; "
            "opened frozen PDF and allowlisted rules only; no unlisted substantive "
            "assertion was received; no prohibited context/artifact was used; "
            "neighboring paths were not enumerated\n"
            f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n"
        )

    def reviewer_report(self, digest: str, index: int) -> str:
        personas = {
            1: "technical method and experiment reasoning across the complete thesis",
            2: "contribution, thesis logic, and cross-chapter narrative coherence",
            3: "evidence integrity, reproducibility, standards, and whole-thesis traceability",
        }
        gate_rows = "\n".join(
            f"| {gate} — gate | baseline | adequate | physical p.1, fixture section | none | high |"
            for gate in "ABCDEFGHI"
        )
        return (
            f"# R{index} — Comprehensive whole-thesis review\n\n"
            + "## Role, scope, and independence\n"
            + self.declaration(digest)
            + "- Whole-thesis mandate: Gate A--I\n"
            + f"- Persona emphasis: {personas[index]}\n\n"
            + "## Verdict\n"
            + "- Decision regime: skill-default\n"
            + "- Academic grade: B\n"
            + "- Defense recommendation: 小修后可答辩\n\n"
            + "- Confidence: high\n"
            + "- One-paragraph whole-thesis rationale: The complete fixture thesis "
            + "was assessed across policy, argument, literature, methods, data, "
            + "experiments, reproducibility, writing, and presentation; the visible "
            + "evidence supports a minor-revision recommendation without a blocker.\n\n"
            + "## What I inspected\n\nAll frozen pages and all required ledgers.\n\n"
            + "## Whole-thesis synthesis\n\nThe fixture has one coherent claim and one source.\n\n"
            + "## Whole-thesis assessment\n\n"
            + "| Gate | Depth | Disposition | Evidence | Findings | Confidence |\n"
            + "|---|---|---|---|---|---|\n"
            + gate_rows
            + "\n\n## Persona-weighted deep review\n\n"
            + "The assigned emphasis was applied after the complete Gate A--I pass.\n\n"
            + "## Strongest contributions\n\n1. A bounded fixture contribution.\n\n"
            + "## Findings\n\nNo additional findings.\n\n"
            + "## Questions, not findings\n\nnone\n\n"
            + "## Coverage and limitations\n\nThe synthetic two-page fixture limits semantic depth.\n"
            + (
                "\n## Full rendered-page audit\n"
                "- Physical pages / unchecked pages: 2 / 0\n\n"
                "## Full bibliography-integrity audit\n"
                "- Bibliography entries rendered in the frozen PDF: 1\n"
                "- Bibliography master rows / unchecked rows: 1 / 0\n\n"
                "## Full citation-claim audit\n"
                "- Citation--source pairs: 1\n"
                "- Ledger rows and unchecked rows: 1 / 0\n"
                if index == 3 else ""
            )
        )

    def chair_report(self, digest: str) -> str:
        return (
            "# Chair synthesis\n\n"
            + "## Clean-room boundary\n"
            + self.declaration(digest)
            + "\n## Overall risk and recommendation\n"
            + "- Overall academic grade: B\n"
            + "- Overall defense recommendation: 小修后可答辩\n\n"
            + "- Confidence: high\n"
            + "- Whole-thesis rationale: The current panel evidence covers all "
            + "nine gates and the assigned citation, bibliography, page, and style "
            + "duties; one bounded wording revision remains, while no foundational "
            + "or integrity blocker is visible.\n"
            + "\n## Reviewer coverage validation\n\n"
            + "| Reviewer | Gate A | B | C | D | E | F | G | H | I | Whole-thesis rationale | Audit duty complete | Eligible for adjudication |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| R1 | pass | pass | pass | pass | pass | pass | pass | pass | pass | complete | yes | yes |\n"
            + "| R2 | pass | pass | pass | pass | pass | pass | pass | pass | pass | complete | yes | yes |\n"
            + "| R3 | pass | pass | pass | pass | pass | pass | pass | pass | pass | complete | yes | yes |\n\n"
            + "## Independent verdicts\n\n"
            + "| Reviewer | Persona | Category/grade | Defense recommendation | Decision regime/source | Confidence | Decisive reason |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| R1 | technical method and experiment | B | 小修后可答辩 | skill-default | high | Complete current-round Gate A--I evidence supports minor revision. |\n"
            + "| R2 | contribution and thesis logic | B | 小修后可答辩 | skill-default | high | Complete current-round Gate A--I evidence supports minor revision. |\n"
            + "| R3 | evidence integrity and reproducibility | B | 小修后可答辩 | skill-default | high | Complete current-round Gate A--I evidence supports minor revision. |\n\n"
            + "## Standalone AI-style judgment\n\n- Signal: moderate\n- Confidence: high\n\n"
            + "## AI-style actionable findings\n\n"
            + "| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Verification | Status |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| AI-F01 | local | physical p.1 | formulaic transition | replace the transition | reread paragraph | open |\n\n"
            + "## Contributions that survived review\n\nThe bounded fixture contribution survives.\n\n"
            + "## Adjudicated findings\n\n"
            + "| Chair finding ID | Source reviewer finding IDs | Severity | Remedy | Exact PDF anchor | Direct observation | Evidence status | Owner | Minimum required action | Verification |\n"
            + "|---|---|---|---|---|---|---|---|---|---|\n"
            + "| C-F01 | R1-F01 | S2 | W | physical p.1 | visible wording defect | verified | author | correct the wording | reinspect p.1 |\n\n"
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
            + "\n## Disagreements and chair decisions\n\nnone\n\n"
            + "## Thesis-level narrative and chapter logic\n\nCoherent within the fixture.\n\n"
            + "## Policy and blind-copy status\n\nNo fixture policy blocker.\n"
            + "\n## Optional suggestions\n\nnone\n\n"
            + "## Review limitations\n\nnone\n"
        )

    def ai_report(self, digest: str) -> str:
        return (
            "# Standalone AI-style prose assessment\n\n"
            + "## Boundary and independence\n"
            + self.declaration(digest)
            + "- Required disclaimer: This is a prose-style assessment, not a "
            + "determination of AI use, authorship, plagiarism, or misconduct.\n"
            + "\n## Overall judgment\n"
            + "- AI-style signal: moderate\n"
            + "- Confidence: high\n"
            + "- Rationale: The short fixture contains one formulaic transition, "
            + "but the limited corpus prevents any stronger stylistic inference.\n\n"
            + "## Coverage and mechanical checks\n\nBoth authored fixture pages were inspected.\n\n"
            + "## Signal-family summary and counter-evidence\n\nOne local signal; limited evidence.\n\n"
            + "## Findings\n\n### AI-F01 — formulaic transition\n\nLocal only.\n\n"
            + "## Limitations\n\nSynthetic corpus.\n\n"
            + "## Out-of-scope observations for chair verification\n\nnone\n"
        )

    def summary_report(
        self, digest: str, academic_count: int = 1, ai_count: int = 1
    ) -> str:
        allowlist = "; ".join([
            "00-process-parameters.json", "SKILL.md",
            "clean-room-orchestration.md", "report-template.md",
            "R1-comprehensive-review.md", "R2-comprehensive-review.md",
            "R3-comprehensive-review.md", "05-ai-style-assessment.md",
            "90-chair-synthesis.md", "91-revision-ledger.md",
            "91-revision-ledger.csv", "91-ai-actionable-ledger.csv",
            "92-new-evidence-or-experiments.md",
        ])
        return (
            "# Current-round user-facing review summary\n\n"
            + "## Clean-room identity\n"
            + self.declaration(digest)
            + "- Review round ID: fixture\n"
            + f"- Frozen PDF path and SHA-256: frozen-thesis.pdf / {digest}\n"
            + f"- Exact current-round input allowlist: {allowlist}\n\n"
            + "## Independent and overall conclusions\n\n"
            + "| Actor | Persona/status | Category or AI-style label | Exact defense recommendation | Confidence | Decisive current-round basis |\n"
            + "|---|---|---|---|---|---|\n"
            + "| R1 | technical method and experiment reasoning across the complete thesis | B | 小修后可答辩 | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| R2 | contribution, thesis logic, and cross-chapter narrative coherence | B | 小修后可答辩 | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| R3 | evidence integrity, reproducibility, standards, and whole-thesis traceability | B | 小修后可答辩 | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| AI | standalone AI-style assessment | moderate | N/A | high | The short fixture contains one formulaic transition, but the limited corpus prevents any stronger stylistic inference. |\n"
            + "| Chair | chair adjudication | B | 小修后可答辩 | high | The current panel evidence covers all nine gates and the assigned citation, bibliography, page, and style duties; one bounded wording revision remains, while no foundational or integrity blocker is visible. |\n\n"
            + "## Current actionable items\n\n"
            + "| Ledger ID | Current finding ID(s) | Severity / remedy | Exact PDF anchor | Direct PDF-visible observation | Minimum required action | Origin reviewer(s) | Chair disposition |\n"
            + "|---|---|---|---|---|---|---|---|\n"
            + "| L01 | C-F01 | S2/W | physical p.1 | visible wording defect | correct the wording | R1-F01 | open |\n\n"
            + "## Current AI-style actionable items — separate from academic grading\n\n"
            + "| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Chair status |\n"
            + "|---|---|---|---|---|---|\n"
            + "| AI-F01 | local | physical p.1 | formulaic transition | replace the transition | open |\n\n"
            + "## Optional suggestions\n\nnone\n\n"
            + "## Unresolved questions and review limitations\n\nnone\n\n"
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

    def build_bundle(self, root: Path, page_count: int = 2) -> str:
        pdf = root / "frozen-thesis.pdf"
        writer = PdfWriter()
        for physical_page in range(1, page_count + 1):
            page = writer.add_blank_page(width=595.28, height=841.89)
            if physical_page == 1:
                add_ascii_text(
                    writer,
                    page,
                    "fixture proposition [1]; quantization levels are [3, 8]; "
                    "scale interval [0.85, 1].",
                )
            elif physical_page == page_count:
                add_ascii_text(writer, page, "References\n[1] Fixture reference.")
        with pdf.open("wb") as handle:
            writer.write(handle)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest().upper()
        render_dir = root / "page-renders"
        render_dir.mkdir()
        render_digests: dict[str, str] = {}
        for physical_page in range(1, page_count + 1):
            page_id = f"P{physical_page:04d}"
            render_path = render_dir / f"{page_id}.png"
            write_grayscale_png(render_path, 1654, 2339)
            render_digests[page_id] = hashlib.sha256(
                render_path.read_bytes()
            ).hexdigest().upper()
        process = {
            "round_id": "fixture",
            "retry_id": "r1",
            "frozen_pdf_file": pdf.name,
            "selected_pdf_sha256": digest,
            "physical_page_count": page_count,
            "frozen_at": "2026-08-29T12:34:56+08:00",
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
            "# Manifest\n\n"
            + self.declaration(digest)
            + "- Numeric-bracket candidate rows: 3\n"
            + "- Citation-classified candidate rows: 1\n"
            + "- Non-citation-classified candidate rows: 2\n"
            + "- Unmatched square-bracket glyphs: 0\n"
            + "- Unmatched glyph dispositions: No unmatched glyph was found "
            + "in the rendered fixture page.\n"
            + "- Frozen at: 2026-08-29T12:34:56+08:00\n",
            encoding="utf-8",
        )
        (root / "01-policy-basis.md").write_text(
            "# Policy\n\n" + self.declaration(digest), encoding="utf-8"
        )
        (root / "02-page-layout-ledger.md").write_text(
            "# Page ledger\n\n" + self.declaration(digest)
            + "| Page ID | Physical page | Printed page | Region | Dominant content | Signals | Inspection mode/scale | Render DPI | Render artifact ID/hash | Neighbor pages checked | Disposition | Evidence |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "".join(
                f"| P{physical_page:04d} | {physical_page} |  | "
                f"{'bibliography' if physical_page == page_count else 'chapter'} | "
                "text | none | individual 100% | 200 | retained render hash | "
                "adjacent page checked | clean | full-page render inspected |\n"
                for physical_page in range(1, page_count + 1)
            ),
            encoding="utf-8",
        )
        (root / "03-bibliography-audit-ledger.md").write_text(
            "# Bibliography ledger\n\n" + self.declaration(digest)
            + "| Reference ID | Displayed label | Cited? | Type | Title | Ordered authors | Year | Venue | Publication status | Volume/issue | Pages/article no. | Persistent IDs/URL/access date | Existence | Retraction/correction/superseding | Finding/disposition |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| REF0001 | [1] | yes | fixture | Fixture reference | Author | 2026 | fixture | published | N/A | N/A | DOI fixture | exists | none | verified |\n",
            encoding="utf-8",
        )
        (root / "04-citation-claim-audit-ledger.md").write_text(
            "# Citation ledger\n\n" + self.declaration(digest)
            + "| Pair ID | Occurrence ID | PDF location | Exact attached proposition | Reference ID | Displayed label | Public source/identifier | Content source opened and exact locator | Support | Metadata/status | Severity/finding | Disposition/evidence |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| C0001-S01 | C0001 | physical p.1 | fixture proposition | REF0001 | [1] | DOI fixture | official PDF, p.1 | direct | verified | none | supported |\n",
            encoding="utf-8",
        )
        (root / "91-revision-ledger.md").write_text(
            "# Revision ledger\n\n" + self.declaration(digest)
            + "| Ledger ID | Priority | Chair finding ID | Source reviewer finding IDs | Severity | Remedy | Exact PDF anchor | Direct observation | Minimum edit/evidence | Dependency | Owner | Status | Verification |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| L01 | P2 | C-F01 | R1-F01 | S2 | W | physical p.1 | visible wording defect | correct the wording | none | author | open | reinspect p.1 |\n\n"
            + "## AI-style actionable ledger — separate from academic grading\n\n"
            + "| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Status | Verification |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| AI-F01 | local | physical p.1 | formulaic transition | replace the transition | open | reread paragraph |\n",
            encoding="utf-8",
        )
        (root / "92-new-evidence-or-experiments.md").write_text(
            "# New evidence or experiments\n\n" + self.declaration(digest)
            + "## No-new-experiment remedies (W/E/P)\n\n"
            + "- Writing or claim narrowing: correct the wording.\n\n"
            + "## Genuine new experiments or unavailable evidence (N)\n\n"
            + "| Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |\n"
            + "|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        for index in range(1, 4):
            (root / f"R{index}-comprehensive-review.md").write_text(
                self.reviewer_report(digest, index), encoding="utf-8"
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
                "PageID": f"P{physical_page:04d}",
                "PhysicalPage": str(physical_page),
                "PrintedPage": "",
                "Region": (
                    "bibliography" if physical_page == page_count else "chapter"
                ),
                "MechanicalSignals": "none",
                "PDFSHA256": digest,
            } for physical_page in range(1, page_count + 1)],
        )
        write_csv(
            root / "02-page-layout-ledger.csv",
            PAGE_LEDGER_COLUMNS,
            [{
                "PageID": f"P{physical_page:04d}",
                "PhysicalPage": str(physical_page),
                "PrintedPage": "",
                "Region": (
                    "bibliography" if physical_page == page_count else "chapter"
                ),
                "DominantContent": "text",
                "Signals": "none",
                "InspectionModeScale": "individual 100%",
                "RenderDPI": "200",
                "RenderArtifactIDHash": (
                    f"P{physical_page:04d}:"
                    f"{render_digests[f'P{physical_page:04d}']}"
                ),
                "NeighborPagesChecked": "boundary page; none",
                "Disposition": "clean",
                "Evidence": "full-page render inspected",
                "PDFSHA256": digest,
            } for physical_page in range(1, page_count + 1)],
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
            root / "00-citation-candidate-ledger.csv",
            CITATION_CANDIDATE_COLUMNS,
            [{
                "CandidateID": "BC0001",
                "PhysicalPage": "1",
                "Marker": "[1]",
                "ExpandedNumbers": "1",
                "Classification": "citation",
                "ClassificationEvidence": (
                    "attached to the named fixture proposition"
                ),
                "MappedOccurrenceID": "C0001",
                "AdjacentPDFText": (
                    "fixture proposition [1]; quantization levels are [3, 8]; "
                    "scale interval [0.85, 1]."
                ),
                "PDFSHA256": digest,
            }, {
                "CandidateID": "BC0002",
                "PhysicalPage": "1",
                "Marker": "[3, 8]",
                "ExpandedNumbers": "3;8",
                "Classification": "non-citation",
                "ClassificationEvidence": (
                    "numeric quantization-level list introduced by levels are"
                ),
                "MappedOccurrenceID": "N/A",
                "AdjacentPDFText": (
                    "fixture proposition [1]; quantization levels are [3, 8]; "
                    "scale interval [0.85, 1]."
                ),
                "PDFSHA256": digest,
            }, {
                "CandidateID": "BC0003",
                "PhysicalPage": "1",
                "Marker": "[0.85, 1]",
                "ExpandedNumbers": "N/A",
                "Classification": "non-citation",
                "ClassificationEvidence": (
                    "decimal scale interval rather than a source marker"
                ),
                "MappedOccurrenceID": "N/A",
                "AdjacentPDFText": (
                    "fixture proposition [1]; quantization levels are [3, 8]; "
                    "scale interval [0.85, 1]."
                ),
                "PDFSHA256": digest,
            }],
        )
        write_csv(
            root / "00-unmatched-bracket-ledger.csv",
            UNMATCHED_BRACKET_COLUMNS,
            [],
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
                "AdjacentPDFText": (
                    "fixture proposition [1]; quantization levels are [3, 8]; "
                    "scale interval [0.85, 1]."
                ),
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
            process["physical_page_count"] = 3
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
            process["physical_page_count"] = 3
            process_path.write_text(json.dumps(process), encoding="utf-8")
            self.assert_fails(root, "parsed page count 2")

    def test_frozen_at_requires_iso_datetime_with_timezone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["frozen_at"] = "2026-08-29T12:34:56"
            process_path.write_text(
                json.dumps(process, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.assert_fails(root, "frozen_at must include an explicit timezone")

    def test_printed_roman_page_x_is_not_a_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, inventory = read_csv(root / "00-page-inventory.csv")
            _, ledger = read_csv(root / "02-page-layout-ledger.csv")
            inventory[0]["PrintedPage"] = "X"
            ledger[0]["PrintedPage"] = "X"
            write_csv(
                root / "00-page-inventory.csv",
                PAGE_INVENTORY_COLUMNS,
                inventory,
            )
            write_csv(
                root / "02-page-layout-ledger.csv",
                PAGE_LEDGER_COLUMNS,
                ledger,
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_prose_only_markdown_id_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "02-page-layout-ledger.md").write_text(
                "This is prose, not a table. Claimed row P0001 was checked. "
                "The remaining text merely pads the file.\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "page ledger Markdown projection")

    def test_standalone_pipe_row_is_not_a_markdown_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "02-page-layout-ledger.md").write_text(
                "# Not a table\n\n"
                "| P0001 | a standalone pipe row without a header or separator |\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "expected exactly one complete Markdown table")

    def test_markdown_id_cannot_repeat_outside_target_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            page_markdown = root / "02-page-layout-ledger.md"
            page_markdown.write_text(
                page_markdown.read_text(encoding="utf-8")
                + "\nA prose appendix repeats P0001 outside the master table.\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "IDs outside the target Markdown table")

    def test_missing_or_hash_mismatched_render_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            render_path = root / "page-renders" / "P0001.png"
            render_path.unlink()
            self.assert_fails(root, "page render files")

    def test_existing_render_with_wrong_declared_hash_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, page_rows = read_csv(root / "02-page-layout-ledger.csv")
            page_rows[0]["RenderArtifactIDHash"] = f"P0001:{'A' * 64}"
            write_csv(
                root / "02-page-layout-ledger.csv",
                PAGE_LEDGER_COLUMNS,
                page_rows,
            )
            self.assert_fails(root, "render-file hash mismatch")

    def test_render_dimensions_must_match_pdf_page_and_dpi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            render_path = root / "page-renders" / "P0001.png"
            write_grayscale_png(render_path, 100, 200)
            render_digest = hashlib.sha256(render_path.read_bytes()).hexdigest().upper()
            _, page_rows = read_csv(root / "02-page-layout-ledger.csv")
            page_rows[0]["RenderArtifactIDHash"] = f"P0001:{render_digest}"
            write_csv(
                root / "02-page-layout-ledger.csv",
                PAGE_LEDGER_COLUMNS,
                page_rows,
            )
            self.assert_fails(root, "pixel dimensions")

    def test_page_render_directory_rejects_extra_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "page-renders" / "notes.txt").write_text(
                "not a render", encoding="utf-8"
            )
            self.assert_fails(root, "page-renders: unexpected entries")

    def test_page_id_must_equal_physical_page_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root, page_count=2)
            for filename, columns in (
                ("00-page-inventory.csv", PAGE_INVENTORY_COLUMNS),
                ("02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS),
            ):
                _, rows = read_csv(root / filename)
                rows[0]["PhysicalPage"], rows[1]["PhysicalPage"] = (
                    rows[1]["PhysicalPage"], rows[0]["PhysicalPage"]
                )
                write_csv(root / filename, columns, rows)
            self.assert_fails(root, "P0001 must map to PhysicalPage 1")

    def test_structural_png_with_undecodable_pixels_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            render_path = root / "page-renders" / "P0001.png"
            write_empty_idat_png(render_path, 1654, 2339)
            render_digest = hashlib.sha256(render_path.read_bytes()).hexdigest().upper()
            _, page_rows = read_csv(root / "02-page-layout-ledger.csv")
            page_rows[0]["RenderArtifactIDHash"] = f"P0001:{render_digest}"
            write_csv(
                root / "02-page-layout-ledger.csv",
                PAGE_LEDGER_COLUMNS,
                page_rows,
            )
            self.assert_fails(root, "PNG pixels cannot be decoded")

    def test_locator_keyword_without_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, citation_rows = read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            citation_rows[0]["ExactSourceLocator"] = "section"
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                citation_rows,
            )
            self.assert_fails(root, "ExactSourceLocator lacks a page/section")

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

    def test_citation_candidate_ledger_must_cover_pdf_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "00-citation-candidate-ledger.csv")
            write_csv(
                root / "00-citation-candidate-ledger.csv",
                CITATION_CANDIDATE_COLUMNS,
                rows[:1],
            )
            self.assert_fails(root, "row count does not equal")

    def test_citation_candidate_order_page_and_marker_are_pdf_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "00-citation-candidate-ledger.csv")
            rows[0]["CandidateID"] = "BC0002"
            rows[0]["PhysicalPage"] = "2"
            rows[0]["Marker"] = "[2]"
            rows[0]["ExpandedNumbers"] = "2"
            write_csv(
                root / "00-citation-candidate-ledger.csv",
                CITATION_CANDIDATE_COLUMNS,
                rows,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CandidateID sequence mismatch", result.stdout)
            self.assertIn("PhysicalPage", result.stdout)
            self.assertIn("!= extracted", result.stdout)

    def test_obvious_numeric_array_cannot_be_classified_as_citation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "00-citation-candidate-ledger.csv")
            rows[1]["Classification"] = "citation"
            rows[1]["MappedOccurrenceID"] = "C0002"
            write_csv(
                root / "00-citation-candidate-ledger.csv",
                CITATION_CANDIDATE_COLUMNS,
                rows,
            )
            self.assert_fails(root, "obvious non-citation classified as citation")

    def test_candidate_numbers_must_equal_citation_inventory_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "00-citation-candidate-ledger.csv")
            rows[0]["Marker"] = "[2]"
            rows[0]["ExpandedNumbers"] = "2"
            write_csv(
                root / "00-citation-candidate-ledger.csv",
                CITATION_CANDIDATE_COLUMNS,
                rows,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("!= extracted", result.stdout)
            self.assertIn("candidate-to-inventory number mismatch", result.stdout)

    def test_body_page_cannot_disappear_by_claiming_bibliography_region(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, inventory = read_csv(root / "00-page-inventory.csv")
            _, ledger = read_csv(root / "02-page-layout-ledger.csv")
            inventory[0]["Region"] = "bibliography"
            ledger[0]["Region"] = "bibliography"
            write_csv(root / "00-page-inventory.csv", PAGE_INVENTORY_COLUMNS, inventory)
            write_csv(root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, ledger)
            self.assert_fails(root, "reference Region pages do not equal")

    def test_line_start_numeric_run_without_references_heading_is_not_bibliography(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "fake-boundary.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=595.28, height=841.89)
            add_ascii_text(
                writer, page,
                "Chapter body with hidden candidate [999].\n[1] not a bibliography entry.",
            )
            with pdf.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            derived = VALIDATOR_MODULE.derive_and_validate_reference_pages(
                pdf,
                {1},
                [{"DisplayedLabel": "[1]"}],
                errors,
            )
            self.assertEqual(derived, set())
            self.assertTrue(any("not anchored" in error for error in errors), errors)

    def test_candidate_and_occurrence_context_are_pdf_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, candidates = read_csv(root / "00-citation-candidate-ledger.csv")
            candidates[0]["AdjacentPDFText"] = "fabricated neighboring words [1]"
            write_csv(
                root / "00-citation-candidate-ledger.csv",
                CITATION_CANDIDATE_COLUMNS,
                candidates,
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("deterministic frozen-PDF window", result.stdout)

    def test_occurrence_physical_page_must_equal_candidate_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, inventory = read_csv(root / "00-citation-inventory.csv")
            _, ledger = read_csv(root / "04-citation-claim-audit-ledger.csv")
            inventory[0]["PDFLocation"] = "physical p.999"
            ledger[0]["PDFLocation"] = "physical p.999"
            write_csv(
                root / "00-citation-inventory.csv",
                CITATION_INVENTORY_COLUMNS,
                inventory,
            )
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                ledger,
            )
            self.assert_fails(root, "outside 1..2")

    def test_positive_unmatched_count_cannot_claim_none_found(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            body = (
                "fixture proposition [1]; quantization levels are [3, 8]; "
                "scale interval [0.85, 1]. unmatched ["
            )
            digest = self.rewrite_pdf_and_rehash(
                root, [body, "References\n[1] Fixture reference."]
            )
            _, candidates = read_csv(root / "00-citation-candidate-ledger.csv")
            for row in candidates:
                row["AdjacentPDFText"] = body
                row["PDFSHA256"] = digest
            write_csv(
                root / "00-citation-candidate-ledger.csv",
                CITATION_CANDIDATE_COLUMNS,
                candidates,
            )
            _, occurrences = read_csv(root / "00-citation-inventory.csv")
            occurrences[0]["AdjacentPDFText"] = body
            occurrences[0]["PDFSHA256"] = digest
            write_csv(
                root / "00-citation-inventory.csv",
                CITATION_INVENTORY_COLUMNS,
                occurrences,
            )
            write_csv(
                root / "00-unmatched-bracket-ledger.csv",
                UNMATCHED_BRACKET_COLUMNS,
                [{
                    "GlyphID": "UBG0001",
                    "PhysicalPage": "1",
                    "Glyph": "[",
                    "AdjacentPDFText": body,
                    "Disposition": "visible unmatched extraction artifact",
                    "PDFSHA256": digest,
                }],
            )
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "- Unmatched square-bracket glyphs: 0",
                    "- Unmatched square-bracket glyphs: 1",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "positive unmatched-glyph count requires")

    def test_four_digit_marker_and_overlong_span_are_not_silently_lost(self) -> None:
        self.assertEqual(VALIDATOR_MODULE.expand_numeric_marker("[1000]"), [1000])
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "long.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=595.28, height=841.89)
            marker = "[1" + ("a" * 600) + "]"
            add_ascii_text(writer, page, marker)
            with pdf.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            candidates, unmatched = VALIDATOR_MODULE.extract_numeric_bracket_candidates(
                pdf, set(), errors
            )
            self.assertEqual(errors, [])
            self.assertEqual(len(candidates), 1)
            self.assertEqual(unmatched, [])

    def test_duplicate_number_vector_has_deterministic_non_citation_reason(self) -> None:
        reason = VALIDATOR_MODULE.obvious_non_citation_reason({
            "Expanded": [1, 1],
            "Prefix": "tensor shape is ",
        })
        self.assertEqual(reason, "duplicate-number vector/array")

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

    def test_chair_markdown_ledger_rows_must_equal_91_csv_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "91-revision-ledger.md"
            text = path.read_text(encoding="utf-8").replace(
                "| L01 | P2 | C-F01 | R1-F01 | S2 | W |",
                "| L01 | P2 | C-F01 | R1-F01 | S3 | W |",
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "Markdown/CSV value mismatch for L01/Severity")

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

    def test_declaration_must_state_complete_clean_room_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R1-comprehensive-review.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "no prohibited context/artifact was used; ", ""
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "no prohibited context/artifact")

    def test_manifest_frozen_at_must_equal_process_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "00-manifest.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "2026-08-29T12:34:56+08:00",
                    "2026-08-29T12:35:56+08:00",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "Frozen at must exactly equal")

    def test_reviewer_persona_cannot_be_copied_from_another_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R2-comprehensive-review.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "contribution, thesis logic, and cross-chapter narrative coherence",
                "technical method and experiment reasoning across the complete thesis",
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "distinct R2 emphasis")

    def test_summary_input_allowlist_must_be_exact_and_current_round_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "92-new-evidence-or-experiments.md",
                "92-new-evidence-or-experiments.md; old-review-summary.md",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "Exact current-round input allowlist mismatch")

    def test_summary_must_include_every_independent_actor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"(?m)^\| R2 \|.*\n", "", text)
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "independent-conclusion actors: missing IDs ['R2']")

    def test_summary_actor_basis_cannot_introduce_prior_or_author_side_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "The complete fixture thesis was assessed across policy, argument, "
                "literature, methods, data, experiments, reproducibility, writing, "
                "and presentation; the visible evidence supports a minor-revision "
                "recommendation without a blocker.",
                "A prior-round issue was resolved after the author explained "
                "repository implementation details that are not in the current PDF.",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "R1 conclusion does not exactly copy its independent current-round verdict",
            )

    def test_summary_cannot_invent_optional_or_limitation_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            text = path.read_text(encoding="utf-8").replace(
                "## Optional suggestions\n\nnone",
                "## Optional suggestions\n\ninvented prior-context suggestion",
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "exact current-round projection of chair section")

    def test_summary_markdown_rows_must_equal_summary_csv_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            text = path.read_text(encoding="utf-8").replace(
                "| L01 | C-F01 | S2/W | physical p.1 | visible wording defect |",
                "| L01 | C-F01 | S2/W | physical p.1 | invented different defect |",
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "Markdown/CSV value mismatch for L01/DirectPDFObservation")

    def test_markdown_master_requires_complete_documented_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "03-bibliography-audit-ledger.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(" | Publication status", " | Status", 1)
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "missing required headers")

    def test_missing_gate_and_grade_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R2-comprehensive-review.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "| I — gate | baseline | adequate | physical p.1, fixture section | none | high |\n",
                "",
            )
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
