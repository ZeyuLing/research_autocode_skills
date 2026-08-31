from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
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
ACTOR_PROMPT_HASHES = {
    "P": "1" * 64,
    "R1": "2" * 64,
    "R2": "3" * 64,
    "R3": "4" * 64,
    "R4": "5" * 64,
    "R5": "6" * 64,
    "AI": "7" * 64,
    "C": "8" * 64,
    "S": "9" * 64,
    "V": "A" * 64,
}
PROMPT_HASH = ACTOR_PROMPT_HASHES["P"]
BIB_ENDPOINT = "https://doi.org/10.1145/3442188.3445922"
CITATION_ENDPOINT = "https://dl.acm.org/doi/pdf/10.1145/3442188.3445922"

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
    "Severity", "S0Subtype", "Remedy", "ExactPDFAnchor", "DirectObservation",
    "EvidenceStatus", "MinimumEditEvidence", "Dependency", "Owner", "Status",
    "Verification",
]
AI_LEDGER_COLUMNS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "Status", "Verification",
]
ACADEMIC_SUMMARY_COLUMNS = list(ACADEMIC_LEDGER_COLUMNS)
AI_SUMMARY_COLUMNS = list(AI_LEDGER_COLUMNS)
EVIDENCE_ITEM_COLUMNS = [
    "EvidenceItemID", "LedgerID", "ChairFindingID", "Remedy", "Item",
    "ClaimThatDependsOnIt", "WhyWritingIsInsufficient",
    "MinimumViableEvidence", "ConsequenceIfUnavailable",
]
PRIOR_ISSUES_COLUMNS = [
    "PriorFindingID", "PriorPDFSHA256", "PriorPDFAnchor", "Finding",
    "RequiredClosureEvidence",
]
BIB_FIELDS = [
    "type", "title", "ordered_authors", "year", "venue",
    "publication_status", "volume", "issue", "pages_or_article_number",
    "doi", "arxiv_id", "arxiv_version", "url", "access_date",
    "isbn_or_other_persistent_id", "existence",
    "retraction_withdrawal_correction_superseding",
]
PAGE_MARKDOWN_HEADERS = [
    "Page ID", "Physical page", "Printed page", "Region",
    "Dominant content", "Signals", "Inspection mode/scale", "Render DPI",
    "Render artifact ID/hash", "Neighbor pages checked", "Disposition",
    "Evidence",
]
PAGE_MARKDOWN_FIELDS = [
    "PageID", "PhysicalPage", "PrintedPage", "Region", "DominantContent",
    "Signals", "InspectionModeScale", "RenderDPI", "RenderArtifactIDHash",
    "NeighborPagesChecked", "Disposition", "Evidence",
]
BIB_MARKDOWN_HEADERS = [
    "Reference ID", "Displayed label", "Cited?", "Type", "Title",
    "Ordered authors", "Year", "Venue", "Publication status",
    "Volume/issue", "Pages/article no.",
    "Persistent IDs/URL/access date", "Existence",
    "Retraction/correction/superseding", "Finding/disposition",
]
BIB_MARKDOWN_FIELD_GROUPS = [
    ["type"], ["title"], ["ordered_authors"], ["year"], ["venue"],
    ["publication_status"], ["volume", "issue"],
    ["pages_or_article_number"],
    [
        "doi", "arxiv_id", "arxiv_version", "url", "access_date",
        "isbn_or_other_persistent_id",
    ],
    ["existence"], ["retraction_withdrawal_correction_superseding"],
]
CITATION_MARKDOWN_HEADERS = [
    "Pair ID", "Occurrence ID", "PDF location",
    "Exact attached proposition", "Reference ID", "Displayed label",
    "Public source/identifier", "Content source opened and exact locator",
    "Support", "Metadata/status", "Severity/finding",
    "Disposition/evidence",
]


def markdown_projection_scalar(value: str) -> str:
    return VALIDATOR_MODULE.markdown_projection_scalar(value)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    return VALIDATOR_MODULE.render_markdown_pipe_table(headers, rows)


def bibliography_markdown_rows(
    inventory: list[dict[str, str]],
    ledger: list[dict[str, str]],
) -> list[list[str]]:
    by_key = {
        (row["ReferenceID"], row["Field"]): row
        for row in ledger
    }

    def payload(reference_id: str, field: str) -> dict[str, str]:
        row = by_key[(reference_id, field)]
        return {
            "field": field,
            "rendered": row["RenderedValue"],
            "canonical": row["CanonicalValue"],
            "verdict": row["Verdict"],
            "evidence_endpoint": row["EvidenceEndpoint"],
            "endpoint_type": row["EndpointType"],
            "checked_at": row["CheckedAt"],
            "evidence_note": row["EvidenceNote"],
        }

    projected: list[list[str]] = []
    for inventory_row in sorted(inventory, key=lambda row: row["ReferenceID"]):
        reference_id = inventory_row["ReferenceID"]
        cells = [
            markdown_projection_scalar(reference_id),
            markdown_projection_scalar(inventory_row["DisplayedLabel"]),
            markdown_projection_scalar(inventory_row["Cited"]),
        ]
        for fields in BIB_MARKDOWN_FIELD_GROUPS:
            values = [payload(reference_id, field) for field in fields]
            cells.append(json.dumps(
                values[0] if len(values) == 1 else values,
                ensure_ascii=False,
                separators=(",", ":"),
            ))
        cells.append(json.dumps([
            {
                "field": field,
                "finding_disposition": by_key[
                    (reference_id, field)
                ]["FindingDisposition"],
            }
            for field in BIB_FIELDS
        ], ensure_ascii=False, separators=(",", ":")))
        projected.append(cells)
    return projected


def citation_markdown_rows(
    ledger: list[dict[str, str]],
    bibliography_inventory: list[dict[str, str]],
) -> list[list[str]]:
    labels = {
        row["ReferenceID"]: row["DisplayedLabel"]
        for row in bibliography_inventory
    }
    projected: list[list[str]] = []
    for row in sorted(
        ledger,
        key=lambda item: VALIDATOR_MODULE.pair_id_sort_key(item["PairID"]),
    ):
        displayed_label = labels.get(
            row["ReferenceID"],
            VALIDATOR_MODULE.displayed_label_for_reference_id(
                row["ReferenceID"], {}
            ),
        )
        projected.append([
            markdown_projection_scalar(row["PairID"]),
            markdown_projection_scalar(row["OccurrenceID"]),
            markdown_projection_scalar(row["PDFLocation"]),
            markdown_projection_scalar(row["ExactAttachedProposition"]),
            markdown_projection_scalar(row["ReferenceID"]),
            markdown_projection_scalar(displayed_label),
            markdown_projection_scalar(row["PublicIdentifier"]),
            json.dumps({
                "content_source_opened": row["ContentSourceOpened"],
                "exact_source_locator": row["ExactSourceLocator"],
            }, ensure_ascii=False, separators=(",", ":")),
            markdown_projection_scalar(row["Support"]),
            markdown_projection_scalar(row["MetadataStatus"]),
            markdown_projection_scalar(row["SeverityFinding"]),
            markdown_projection_scalar(row["DispositionEvidence"]),
        ])
    return projected


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
    def test_physical_page_locator_accepts_english_and_chinese_forms(self) -> None:
        parse = VALIDATOR_MODULE.parse_physical_page_locator
        self.assertEqual(parse("physical p.7, section"), 7)
        self.assertEqual(parse("physical page 008"), 8)
        self.assertEqual(parse("物理页 34--35"), 34)
        self.assertEqual(parse("物理页面：041"), 41)
        self.assertEqual(parse("物理第 52 页"), 52)
        self.assertIsNone(parse("printed p.7"))
        parse_canonical = VALIDATOR_MODULE.parse_canonical_physical_page_locator
        self.assertEqual(parse_canonical("physical p.7, section"), 7)
        self.assertIsNone(parse_canonical("physical page 7"))
        self.assertIsNone(parse_canonical("物理页 7"))

    def test_persona_signal_matching_rejects_accidental_latin_substrings(self) -> None:
        match = VALIDATOR_MODULE.contains_persona_signal
        for value, signal in (
            ("Algorithms and representations", "algorithms"),
            ("chapter progression and cross-chapter terminology", "cross-chapter"),
            ("参考文献、版面与格式规范", "参考文献"),
        ):
            with self.subTest(value=value, signal=signal):
                self.assertTrue(match(value, signal))
        for value, signal in (
            ("glossary review", "loss"),
            ("geometric reasoning", "metric"),
            ("composition analysis", "position"),
            ("transformation design", "format"),
            ("webpage quality", "page"),
            ("model architecture and neural design", "thesis architecture"),
        ):
            with self.subTest(value=value, signal=signal):
                self.assertFalse(match(value, signal))

    def test_receipt_delimiters_cannot_hide_inside_basenames_or_urls(self) -> None:
        for basename in (
            "official;rule.txt",
            "official[rule].txt",
            "official]rule.txt",
            "`official-rule.txt",
            "official-rule.txt`",
        ):
            with self.subTest(basename=basename):
                self.assertFalse(
                    VALIDATOR_MODULE.is_neutral_portable_basename(basename)
                )
        for endpoint in (
            "https://example.edu/rule;opened=fake",
            "https://example.edu/rule,https://evil.example",
            "https://example.edu/rule[none]",
            "https://example.edu/`rule`",
            'https://example.edu/"rule"',
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(
                    VALIDATOR_MODULE.PUBLIC_URL_RE.fullmatch(endpoint)
                )

    def test_pair_projection_and_row_order_handle_s100_numerically(self) -> None:
        base_row = {
            "OccurrenceID": "C0001",
            "PDFLocation": "physical p.1",
            "ExactAttachedProposition": "fixture proposition",
            "ReferenceID": "REF0001",
            "PublicIdentifier": "doi:fixture",
            "ContentSourceOpened": CITATION_ENDPOINT,
            "ExactSourceLocator": "p.1",
            "Support": "direct",
            "MetadataStatus": "verified",
            "SeverityFinding": "no finding",
            "DispositionEvidence": "supported by source content",
            "PDFSHA256": "A" * 64,
        }
        ledger = [
            {**base_row, "PairID": "C0001-S100"},
            {**base_row, "PairID": "C0001-S99"},
        ]
        projected = VALIDATOR_MODULE.citation_markdown_projection_rows(
            ledger,
            {"REF0001": {"DisplayedLabel": "[1]"}},
        )
        self.assertEqual(
            ["C0001-S99", "C0001-S100"],
            [row[0] for row in projected],
        )
        inventory = [
            {"PairID": "C0001-S99"},
            {"PairID": "C0001-S100"},
        ]
        errors: list[str] = []
        VALIDATOR_MODULE.validate_citation_pair_row_order(
            inventory, list(reversed(inventory)), errors
        )
        self.assertTrue(any("PairID row order" in error for error in errors), errors)

        with tempfile.TemporaryDirectory() as directory:
            markdown = Path(directory) / "04-citation-claim-audit-ledger.md"
            rows = []
            for pair_id in ("C0001-S99", "C0001-S100"):
                rows.append([
                    pair_id,
                    "C0001",
                    "physical p.1",
                    "fixture proposition",
                    "REF0001",
                    "[1]",
                    "doi:fixture",
                    '{"content_source_opened":"https://example.org/paper",'
                    '"exact_source_locator":"p.1"}',
                    "direct",
                    "verified",
                    "no finding",
                    "supported by source content",
                ])
            markdown.write_text(
                "# Citation ledger\n\n"
                + markdown_table(CITATION_MARKDOWN_HEADERS, rows),
                encoding="utf-8",
            )
            projection_errors: list[str] = []
            VALIDATOR_MODULE.validate_markdown_id_projection(
                markdown,
                {"C0001-S99", "C0001-S100"},
                VALIDATOR_MODULE.PAIR_ID_TOKEN_RE,
                {"Pair ID", "PairID"},
                "citation-claim ledger",
                projection_errors,
                required_headers=set(CITATION_MARKDOWN_HEADERS),
            )
            self.assertEqual([], projection_errors)

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

    def convert_bundle_to_dangling_reference(self, root: Path) -> None:
        """Turn the complete fixture into one valid, fully adjudicated REF gap."""

        body = (
            "fixture proposition [2]; quantization levels are [3, 8]; "
            "scale interval [0.85, 1]."
        )
        digest = self.rewrite_pdf_and_rehash(
            root, [body, "References\n[1] Fixture reference."]
        )
        process_path = root / "00-process-parameters.json"
        process = json.loads(process_path.read_text(encoding="utf-8"))
        process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
        manifest = root / "00-manifest.md"
        manifest.write_text(
            re.sub(
                r"(?m)^- Process-parameter file and SHA-256: .*$",
                "- Process-parameter file and SHA-256: "
                f"00-process-parameters.json / {process_digest}",
                manifest.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )

        extraction_errors: list[str] = []
        extracted, unmatched = VALIDATOR_MODULE.extract_numeric_bracket_candidates(
            root / "frozen-thesis.pdf", {2}, extraction_errors
        )
        self.assertEqual([], extraction_errors)
        self.assertEqual([], unmatched)
        _, candidate_rows = read_csv(root / "00-citation-candidate-ledger.csv")
        for row, source in zip(candidate_rows, extracted, strict=True):
            row["Marker"] = source["Marker"]
            row["ExpandedNumbers"] = (
                "N/A" if source["Expanded"] is None
                else ";".join(str(value) for value in source["Expanded"])
            )
            row["AdjacentPDFText"] = source["Adjacent"]
            row["PDFSHA256"] = digest
        write_csv(
            root / "00-citation-candidate-ledger.csv",
            CITATION_CANDIDATE_COLUMNS,
            candidate_rows,
        )

        _, citation_inventory = read_csv(root / "00-citation-inventory.csv")
        citation_inventory[0]["DisplayedReferenceID"] = "REF0002"
        citation_inventory[0]["AdjacentPDFText"] = extracted[0]["Adjacent"]
        citation_inventory[0]["PDFSHA256"] = digest
        write_csv(
            root / "00-citation-inventory.csv",
            CITATION_INVENTORY_COLUMNS,
            citation_inventory,
        )

        _, bibliography_inventory = read_csv(
            root / "00-bibliography-inventory.csv"
        )
        bibliography_inventory[0]["Cited"] = "no"
        bibliography_inventory[0]["PDFSHA256"] = digest
        write_csv(
            root / "00-bibliography-inventory.csv",
            BIB_INVENTORY_COLUMNS,
            bibliography_inventory,
        )
        _, bibliography_ledger = read_csv(
            root / "03-bibliography-audit-ledger.csv"
        )
        for row in bibliography_ledger:
            row["Cited"] = "no"
            row["PDFSHA256"] = digest
        write_csv(
            root / "03-bibliography-audit-ledger.csv",
            BIB_LEDGER_COLUMNS,
            bibliography_ledger,
        )
        (root / "03-bibliography-audit-ledger.md").write_text(
            "# Bibliography ledger\n\n"
            + self.declaration(digest, process, "R3", [BIB_ENDPOINT])
            + markdown_table(
                BIB_MARKDOWN_HEADERS,
                bibliography_markdown_rows(
                    bibliography_inventory, bibliography_ledger
                ),
            ),
            encoding="utf-8",
        )

        _, citation_ledger = read_csv(
            root / "04-citation-claim-audit-ledger.csv"
        )
        citation_ledger[0].update({
            "ReferenceID": "REF0002",
            "PublicIdentifier": VALIDATOR_MODULE.DANGLING_REFERENCE_SENTINEL,
            "ContentSourceOpened": "",
            "ExactSourceLocator": "",
            "Support": "unverifiable",
            "MetadataStatus": "mismatch",
            "SeverityFinding": "R3-F01",
            "DispositionEvidence": (
                "R3-F01: displayed citation has no rendered bibliography entry"
            ),
            "PDFSHA256": digest,
        })
        write_csv(
            root / "04-citation-claim-audit-ledger.csv",
            CITATION_LEDGER_COLUMNS,
            citation_ledger,
        )
        (root / "04-citation-claim-audit-ledger.md").write_text(
            "# Citation ledger\n\n"
            + self.declaration(digest, process, "R3")
            + markdown_table(
                CITATION_MARKDOWN_HEADERS,
                citation_markdown_rows(citation_ledger, bibliography_inventory),
            ),
            encoding="utf-8",
        )

        finding_replacements = {
            "bounded fixture wording issue": "dangling rendered citation",
            "- Primary gate: H": "- Primary gate: F",
            "- Observation: The fixture exposes one bounded wording defect for validation.": (
                "- Observation: The displayed citation [2] has no rendered "
                "bibliography entry."
            ),
            "- Why it matters: The wording must remain precise for a defensible local claim.": (
                "- Why it matters: The cited source cannot be identified or checked "
                "from the rendered thesis."
            ),
            "- Evidence: The visible fixture sentence contains the designated wording defect.": (
                "- Evidence: Physical p.1 displays [2], while the rendered "
                "bibliography ends at [1]."
            ),
            "- Required action: Correct only the bounded wording without changing the claim.": (
                "- Required action: Add the missing bibliography entry or correct "
                "the citation marker."
            ),
            "- Verification: Reinspect physical p.1 and confirm the corrected sentence.": (
                "- Verification: Recheck the citation and bibliography after PDF refreeze."
            ),
        }
        for reviewer_index in range(1, 4):
            report = root / f"R{reviewer_index}-comprehensive-review.md"
            text = report.read_text(encoding="utf-8")
            for old, new in finding_replacements.items():
                text = text.replace(old, new, 1)
            if reviewer_index == 3:
                text = text.replace(
                    f"public_endpoints=[{BIB_ENDPOINT}; {CITATION_ENDPOINT}]",
                    f"public_endpoints=[{BIB_ENDPOINT}]",
                    1,
                ).replace(
                    "- Semantically verified pairs: 1",
                    "- Semantically verified pairs: 0",
                    1,
                ).replace(
                    "- Inaccessible/unverifiable pairs: 0",
                    "- Inaccessible/unverifiable pairs: 1",
                    1,
                )
            report.write_text(text, encoding="utf-8")

        academic_row = {
            "LedgerID": "L01",
            "Priority": "P2",
            "ChairFindingID": "C-F01",
            "SourceReviewerFindingIDs": "R1-F01, R2-F01, R3-F01",
            "Severity": "S2",
            "S0Subtype": "N/A",
            "Remedy": "W",
            "ExactPDFAnchor": "physical p.1",
            "DirectObservation": (
                "displayed citation [2] has no rendered bibliography entry"
            ),
            "EvidenceStatus": "verified",
            "MinimumEditEvidence": (
                "add the missing bibliography entry or correct the citation marker"
            ),
            "Dependency": "none",
            "Owner": "author",
            "Status": "open",
            "Verification": (
                "recheck the citation and bibliography after PDF refreeze"
            ),
        }
        for filename in (
            "91-revision-ledger.csv", "93-current-actionable-items.csv"
        ):
            write_csv(root / filename, ACADEMIC_LEDGER_COLUMNS, [academic_row])
        academic_markdown_row = "| " + " | ".join(
            academic_row[field] for field in ACADEMIC_LEDGER_COLUMNS
        ) + " |"
        old_academic_row = (
            "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | "
            "physical p.1 | visible wording defect | verified | correct the wording | "
            "none | author | open | reinspect p.1 |"
        )
        for filename in ("91-revision-ledger.md", "93-user-facing-summary.md"):
            path = root / filename
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    old_academic_row, academic_markdown_row, 1
                ),
                encoding="utf-8",
            )
        evidence_plan = root / "92-new-evidence-or-experiments.md"
        evidence_plan.write_text(
            evidence_plan.read_text(encoding="utf-8").replace(
                "| L01 | W | physical p.1 | correct the wording | reinspect p.1 |",
                "| L01 | W | physical p.1 | add the missing bibliography entry "
                "or correct the citation marker | recheck the citation and "
                "bibliography after PDF refreeze |",
                1,
            ),
            encoding="utf-8",
        )

        chair = root / "90-chair-synthesis.md"
        chair_text = chair.read_text(encoding="utf-8").replace(
            "| C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | "
            "visible wording defect | verified | author | correct the wording | "
            "reinspect p.1 |",
            "| C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | "
            "displayed citation [2] has no rendered bibliography entry | verified | "
            "author | add the missing bibliography entry or correct the citation "
            "marker | recheck the citation and bibliography after PDF refreeze |",
            1,
        ).replace(
            "| REF0001 | [1] | C0001-S01 | C0001-S01=>doi:fixture @ "
            f"{CITATION_ENDPOINT} | title=fixture ; ordered_authors=fixture ; "
            "year=fixture ; venue=fixture ; publication_status=fixture ; doi=fixture ; "
            "arxiv_id=N/A ; arxiv_version=N/A ; url=N/A ; "
            "isbn_or_other_persistent_id=N/A ; existence=fixture | agree | none | "
            "none | closed |",
            "| REF0002 | [2] | C0001-S01 | C0001-S01=>no rendered "
            "bibliography entry @ N/A | no rendered bibliography entry | disagree | "
            "substantive | C-F01 | open |",
            1,
        )
        for old, new in (
            ("- Identity-agreement count: 1", "- Identity-agreement count: 0"),
            ("- Version disagreements: 0", "- Version disagreements: 1"),
            ("- Substantive conflicts: 0", "- Substantive conflicts: 1"),
            ("- Reclassified Pair IDs: 0", "- Reclassified Pair IDs: 1"),
            ("- Unresolved conflicts: 0", "- Unresolved conflicts: 1"),
            ("- Combined citation gate: pass", "- Combined citation gate: fail"),
        ):
            chair_text = chair_text.replace(old, new, 1)
        chair.write_text(chair_text, encoding="utf-8")

    def declaration(
        self,
        digest: str,
        process: dict[str, object],
        actor_id: str,
        public_endpoints: list[str] | None = None,
    ) -> str:
        reviewer_count = 5 if process["degree_level"] == "doctorate" else 3
        opened = "; ".join(
            VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, reviewer_count, actor_id
            )
        )
        public = "; ".join(public_endpoints or []) or "none"
        return (
            f"- Actor ID: {actor_id}\n"
            f"- Review round ID: {process['round_id']}\n"
            f"- Review retry ID: {process['retry_id']}\n"
            "- Fresh-context declaration: no inherited user/thread/task turns "
            "beyond system/developer instructions and the exact operational prompt\n"
            f"- Operational prompt SHA-256: {process['actor_prompt_sha256'][actor_id]}\n"
            "- Input-receipt/access declaration: received=[operational prompt]; "
            f"opened=[{opened}]; public_endpoints=[{public}]; "
            "no unlisted substantive "
            "assertion was received; no prohibited context/artifact was used; "
            "neighboring paths were not enumerated\n"
            f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n"
        )

    def install_helper_fixture(
        self,
        root: Path,
        digest: str,
        *,
        receipt: str | None = None,
        recipients: list[str] | None = None,
    ) -> None:
        helpers = root / "helpers"
        helpers.mkdir()
        sidecar = helpers / "H01-pages.txt"
        sidecar.write_text("mechanical output", encoding="utf-8")
        sidecar_hash = hashlib.sha256(sidecar.read_bytes()).hexdigest().upper()
        provenance = {
            "actor_id": "H01",
            "round_id": "fixture",
            "retry_id": "r1",
            "prompt_sha256": "B" * 64,
            "fresh_context_declaration": (
                "no inherited user/thread/task turns beyond system/developer "
                "instructions and the exact operational prompt"
            ),
            "input_receipt_access_declaration": receipt or (
                "received=[operational prompt]; opened=[frozen-thesis.pdf]; "
                "no unlisted substantive assertion was received; no prohibited "
                "context/artifact was used; neighboring paths were not enumerated"
            ),
            "received_blocks": ["operational prompt"],
            "opened_inputs": ["frozen-thesis.pdf"],
            "tool": "fixture",
            "version": "1",
            "command_or_query": "fixture --read-only",
            "pdf_sha256_start": digest,
            "pdf_sha256_end": digest,
            "outputs": [{"file": sidecar.name, "sha256": sidecar_hash}],
            "limitations": [],
            "recipient_stages": recipients or ["R3"],
        }
        (helpers / "H01-provenance.json").write_text(
            json.dumps(provenance), encoding="utf-8"
        )

    def reviewer_report(
        self, digest: str, index: int, process: dict[str, object]
    ) -> str:
        personas = {
            1: "technical method and experiment reasoning across the complete thesis",
            2: "contribution, thesis logic, and cross-chapter narrative coherence",
            3: "evidence integrity, reproducibility, bibliography, format, and layout standards",
        }
        assignments = {
            1: "R1 technical/methods/experiments",
            2: "R2 contribution/positioning + thesis architecture/narrative",
            3: "R3 evidence/integrity/citation + format/bibliography/layout",
        }
        gate_rows = "\n".join(
            f"| {gate} — gate | baseline | adequate | physical p.1, fixture section | none | high |"
            for gate in "ABCDEFGHI"
        )
        reviewer_public = (
            [BIB_ENDPOINT, CITATION_ENDPOINT]
            if process["degree_level"] == "masters" and index == 3
            else []
        )
        return (
            f"# R{index} — Comprehensive whole-thesis review\n\n"
            + "## Role, scope, and independence\n"
            + self.declaration(
                digest, process, f"R{index}", reviewer_public
            )
            + "- Whole-thesis mandate: Gate A--I\n"
            + f"- Persona assignment: {assignments[index]}\n"
            + f"- Persona emphasis: {personas[index]}\n\n"
            + "- Separate exhaustive audit duties, if any: assigned ledgers listed below or none\n"
            + "- Independence declaration: completed independently without another reviewer report\n\n"
            + "## Verdict\n"
            + "- Decision regime: skill-default\n"
            + "- Official category: N/A\n"
            + "- Official defense recommendation: N/A\n"
            + "- Governing source: N/A\n"
            + "- Academic grade: B\n"
            + "- Defense recommendation: 小修后可答辩\n\n"
            + "- Confidence: high\n"
            + "- One-paragraph whole-thesis rationale: The complete fixture thesis "
            + "was assessed across policy, argument, literature, methods, data, "
            + "experiments, reproducibility, writing, and presentation; the visible "
            + "evidence supports a minor-revision recommendation without a blocker.\n\n"
            + "## What I inspected\n\nAll frozen pages and all required ledgers.\n\n"
            + "## Whole-thesis synthesis\n"
            + "- Central thesis problem and overall answer: The fixture states one bounded problem and supplies one bounded answer.\n"
            + "- Degree-level contribution judgment: The bounded contribution is sufficient for this synthetic validation fixture.\n"
            + "- Strongest claim--evidence chain: The visible proposition and cited source form the strongest bounded chain.\n"
            + "- Weakest claim--evidence chain: The wording defect is the weakest local link and requires correction.\n"
            + "- Cross-chapter coherence: The two-page fixture has a consistent beginning-to-end narrative for validation.\n"
            + "- Overall integrity and submission fitness: No integrity blocker is visible; one minor revision remains.\n"
            + "- Most consequential conclusion outside the persona emphasis, or evidence that no material concern was found there: The complete Gate A--I pass found no additional material concern outside the assigned emphasis.\n\n"
            + "## Whole-thesis assessment\n\n"
            + "| Gate | Review depth (`baseline` / `emphasized` / `primary`) | Disposition (`adequate` / `concern` / `unverifiable` / `N/A`) | Decisive evidence and exact locations | Related finding IDs or `none` | Confidence/limitation |\n"
            + "|---|---|---|---|---|---|\n"
            + gate_rows
            + "\n\n## Persona-weighted deep review\n\n"
            + "The assigned emphasis was applied after the complete Gate A--I pass.\n\n"
            + "## Strongest contributions\n\n1. A bounded fixture contribution.\n\n"
            + "## Findings\n\n"
            + f"### R{index}-F01 — bounded fixture wording issue\n"
            + "- Primary gate: H\n"
            + "- Secondary gates: none\n"
            + "- Scope: local\n"
            + "- Severity: S2\n"
            + "- S0 subtype: N/A\n"
            + "- Remedy: W\n"
            + "- Required for the current defense conclusion: yes; bounded revision\n"
            + "- Location: physical p.1, fixture section\n"
            + "- Observation: The fixture exposes one bounded wording defect for validation.\n"
            + "- Why it matters: The wording must remain precise for a defensible local claim.\n"
            + "- Evidence: The visible fixture sentence contains the designated wording defect.\n"
            + "- Required action: Correct only the bounded wording without changing the claim.\n"
            + "- Verification: Reinspect physical p.1 and confirm the corrected sentence.\n"
            + "- Confidence: high\n\n"
            + "## Questions, not findings\n\n"
            + "| Question ID | Exact PDF anchor | Question | Why unresolved | Needed clarification/evidence |\n"
            + "|---|---|---|---|---|\n\n"
            + "## Coverage and limitations\n\nThe synthetic two-page fixture limits semantic depth.\n"
            + (
                "\n## Full rendered-page audit\n"
                "- Physical pages / unchecked pages: 2 / 0\n\n"
                "- Suspect-page signals / resolved / unresolved: 0 / 0 / 0\n"
                "- Actionable layout findings: 0\n"
                "- Neighbor-page verification status: all 2 pages checked\n"
                "- Machine-readable master: 02-page-layout-ledger.csv; duplicate/missing/extra page IDs: 0 / 0 / 0\n"
                "- Source-forcing cause: not verifiable from the PDF\n\n"
                "## Full bibliography-integrity audit\n"
                "- Bibliography entries rendered in the frozen PDF: 1\n"
                "- Bibliography master rows / unchecked rows: 17 / 0\n\n"
                "- Title fields verified / mismatched / unverifiable: 1 / 0 / 0\n"
                "- Ordered-author fields verified / mismatched / unverifiable: 1 / 0 / 0\n"
                "- Year fields verified / mismatched / unverifiable: 1 / 0 / 0\n"
                "- Venue fields verified / mismatched / unverifiable: 1 / 0 / 0\n"
                "- Publication/acceptance-status fields verified / mismatched / unverifiable: 1 / 0 / 0\n"
                "- Volume/issue fields verified / mismatched / legitimate N/A / unverifiable: 0 / 0 / 2 / 0\n"
                "- Page-range or article-number fields verified / mismatched / legitimate N/A / unverifiable: 0 / 0 / 1 / 0\n"
                "- DOI/arXiv/version/URL/access-date fields verified / mismatched / legitimate N/A / unverifiable: 1 / 0 / 4 / 0\n"
                "- ISBN/other-persistent-ID fields verified / mismatched / legitimate N/A / unverifiable: 0 / 0 / 1 / 0\n"
                "- Retraction/withdrawal/correction/superseding-status fields verified / mismatched / legitimate N/A / unverifiable: 1 / 0 / 0 / 0\n"
                "- Suspected fabricated/nonexistent entries and adjudication status: 0 suspected, 0 unresolved\n"
                "- Metadata/status verified entries: 1\n"
                "- Machine-readable master: 03-bibliography-audit-ledger.csv; duplicate/missing/extra reference IDs: 0 / 0 / 0\n\n"
                "## Full citation-claim audit\n"
                "- Active citation occurrences: 1\n"
                "- Citation--source pairs: 1\n"
                "- Unique cited keys: 1\n"
                "- Semantically verified pairs: 1\n"
                "- Partial-support pairs: 0\n"
                "- Context-only pairs: 0\n"
                "- Mismatch pairs: 0\n"
                "- Inaccessible/unverifiable pairs: 0\n"
                "- Ledger rows and unchecked rows: 1 / 0\n"
                "- Machine-readable master: 04-citation-claim-audit-ledger.csv; duplicate/missing/extra Pair IDs: 0 / 0 / 0\n"
                if index == 3 else ""
            )
        )

    def chair_report(
        self, digest: str, process: dict[str, object]
    ) -> str:
        reviewer_count = 5 if process["degree_level"] == "doctorate" else 3
        chair_allowlist = "; ".join(
            VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, reviewer_count, "C"
            )
        )
        return (
            "# Chair synthesis\n\n"
            + "## Clean-room boundary\n"
            + "- Actor ID: C\n"
            + f"- Review round ID: {process['round_id']}\n"
            + f"- Review retry ID: {process['retry_id']}\n"
            + "- Chair fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt\n"
            + f"- Exact current-round input allowlist: {chair_allowlist}\n"
            + f"- Operational prompt SHA-256: {process['actor_prompt_sha256']['C']}\n"
            + "- Chair input-receipt/access declaration: received=[operational prompt]; "
            + f"opened=[{chair_allowlist}]; public_endpoints=[none]; "
            + "no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated\n"
            + f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n"
            + "\n## Overall risk and recommendation\n"
            + "- Decision regime: skill-default\n"
            + "- Overall official category: N/A\n"
            + "- Overall official defense recommendation: N/A\n"
            + "- Overall governing source: N/A\n"
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
            + "| R1 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | not assigned | yes |\n"
            + "| R2 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | not assigned | yes |\n"
            + "| R3 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | yes | yes |\n\n"
            + "## Independent verdicts\n\n"
            + "| Reviewer | Persona | Category/grade | Defense recommendation | Decision regime/source | Confidence | Decisive reason |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| R1 | R1 technical/methods/experiments — technical method and experiment reasoning across the complete thesis | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| R2 | R2 contribution/positioning + thesis architecture/narrative — contribution, thesis logic, and cross-chapter narrative coherence | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| R3 | R3 evidence/integrity/citation + format/bibliography/layout — evidence integrity, reproducibility, bibliography, format, and layout standards | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n\n"
            + "- Category distribution: B=3\n"
            + "- Modal/severe-minority departure explanation: No departure exists because all three independent reviewers and the chair use category B.\n\n"
            + "## Standalone AI-style judgment\n\n- Signal: moderate\n- Confidence: high\n\n"
            + "- Material/local/optional findings: material=0 ; local=1 ; optional=0\n"
            + "- Separation statement: AI-style observations remain separate from academic grading and are projected only through their dedicated ledger.\n\n"
            + "## AI-style actionable findings\n\n"
            + "| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Verification | Status |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| AI-F01 | local | physical p.1 | formulaic transition | replace the transition | reread paragraph after the targeted revision | open |\n\n"
            + "## Contributions that survived review\n\nThe bounded fixture contribution survives the complete independent panel review and remains supported by the visible frozen-PDF evidence.\n\n"
            + "## Adjudicated findings\n\n"
            + "| Chair finding ID | Source reviewer finding IDs | Severity | S0 subtype | Remedy | Exact PDF anchor | Direct observation | Evidence status | Owner | Minimum required action | Verification |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | visible wording defect | verified | author | correct the wording | reinspect p.1 |\n\n"
            + "## Mandatory citation cross-ledger consistency gate\n\n"
            + "| Rendered reference ID | Displayed label | Affected Pair IDs | Citation-ledger identity/source projection | Bibliography-ledger canonical identity projection | "
            + "Version/record agreement (`agree` / `disagree` / `not verifiable`) | Conflict class (`none` / `local` / `substantive`) | "
            + "Chair finding ID(s) | Resolution (`closed` / `open`) |\n"
            + "|---|---|---|---|---|---|---|---|---|\n"
            + "| REF0001 | [1] | C0001-S01 | C0001-S01=>doi:fixture @ https://dl.acm.org/doi/pdf/10.1145/3442188.3445922 | "
            + "title=fixture ; ordered_authors=fixture ; year=fixture ; venue=fixture ; publication_status=fixture ; doi=fixture ; arxiv_id=N/A ; arxiv_version=N/A ; url=N/A ; isbn_or_other_persistent_id=N/A ; existence=fixture | "
            + "agree | none | none | closed |\n\n"
            + "- Unique cited rendered references joined: 1\n"
            + "- Identity-agreement count: 1\n"
            + "- Version disagreements: 0\n"
            + "- Local conflicts: 0\n"
            + "- Substantive conflicts: 0\n"
            + "- Reclassified Pair IDs: 0\n"
            + "- Unresolved conflicts: 0\n"
            + "- Combined citation gate: pass\n"
            + "\n## Disagreements and chair decisions\n\n"
            + "| Decision ID | Source item IDs | Topic | Positions | Evidence checked | Status | Decision |\n"
            + "|---|---|---|---|---|---|---|\n\n"
            + "## Thesis-level narrative and chapter logic\n\nThe fixture presents a coherent thesis-level progression, with its stated problem, bounded evidence, conclusion, and chapter logic aligned across the complete rendered artifact.\n\n"
            + "## Policy and blind-copy status\n\nThe frozen fixture raises no visible policy or blind-copy blocker within the declared skill-default decision regime and current-round evidence boundary.\n"
            + "\n## Optional suggestions\n\nnone\n\n"
            + "## Review limitations\n\nnone\n"
        )

    def ai_report(
        self, digest: str, process: dict[str, object]
    ) -> str:
        return (
            "# Standalone AI-style prose assessment\n\n"
            + "## Boundary and independence\n"
            + self.declaration(digest, process, "AI")
            + f"- Frozen artifact: frozen-thesis.pdf / {digest}\n"
            + "- Reviewer-visible inputs: frozen PDF and the exact AI-style rule packet\n"
            + "- Excluded material: reviewer reports, chair outputs, old rounds, and author-side records\n"
            + "- Independence declaration: assessed in a separate fresh context\n"
            + "- Required disclaimer: This is a prose-style assessment, not a "
            + "determination of AI use, authorship, plagiarism, or misconduct.\n"
            + "\n## Overall judgment\n"
            + "- AI-style signal: moderate\n"
            + "- Confidence: high\n"
            + "- Rationale: The short fixture contains one formulaic transition, "
            + "but the limited corpus prevents any stronger stylistic inference.\n\n"
            + "## Coverage and mechanical checks\n"
            + "- Physical pages inspected: 2 / 2\n"
            + "- Authored sections inspected: all authored fixture prose outside the bibliography\n"
            + "- Recurrent-pattern queries/statistics: transitions and repeated sentence frames were checked\n"
            + "- Corpus exclusions: bibliography strings and page furniture were excluded\n\n"
            + "## Signal-family summary and counter-evidence\n\nOne local formulaic transition is visible, while the remaining short corpus supplies counter-evidence against a thesis-wide style conclusion.\n\n"
            + "## Findings\n\n### AI-F01 — formulaic transition\n"
            + "- Impact: local\n"
            + "- Location: physical p.1\n"
            + "- Recurrent evidence: formulaic transition\n"
            + "- Reader impact: The repeated transition makes the local prose mechanical.\n"
            + "- Minimum safe editing strategy: replace the transition\n"
            + "- Closure test: reread paragraph after the targeted revision\n\n"
            + "## Limitations\n\nThe synthetic two-page corpus limits the strength and breadth of any style inference.\n\n"
            + "## Out-of-scope observations for chair verification\n\nnone\n"
        )

    def summary_report(
        self,
        digest: str,
        process: dict[str, object],
        academic_count: int = 1,
        ai_count: int = 1,
        evidence_count: int = 0,
    ) -> str:
        reviewer_count = 5 if process["degree_level"] == "doctorate" else 3
        allowlist = "; ".join(
            VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, reviewer_count, "S"
            )
        )
        return (
            "# Current-round user-facing review summary\n\n"
            + "## Clean-room identity\n\n"
            + "- Actor ID: S\n"
            + f"- Review round ID: {process['round_id']}\n"
            + f"- Review retry ID: {process['retry_id']}\n"
            + f"- Frozen PDF path and SHA-256: file={process['frozen_pdf_file']} ; sha256={digest}\n"
            + "- Summary fresh-context declaration: no inherited user/thread/task turns "
            + "beyond system/developer instructions and the exact operational prompt\n"
            + f"- Exact current-round input allowlist: {allowlist}\n"
            + f"- Operational prompt SHA-256: {process['actor_prompt_sha256']['S']}\n"
            + "- Summary input-receipt/access declaration: received=[operational prompt]; "
            + f"opened=[{allowlist}]; "
            + "public_endpoints=[none]; no unlisted substantive "
            + "assertion was received; no prohibited context/artifact was used; neighboring "
            + "paths were not enumerated\n"
            + f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n\n"
            + "## Independent and overall conclusions\n\n"
            + "| Actor | Persona/status | Category or AI-style label | Exact defense recommendation | Decision regime/source | Confidence | Decisive current-round basis |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| R1 | R1 technical/methods/experiments — technical method and experiment reasoning across the complete thesis | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| R2 | R2 contribution/positioning + thesis architecture/narrative — contribution, thesis logic, and cross-chapter narrative coherence | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| R3 | R3 evidence/integrity/citation + format/bibliography/layout — evidence integrity, reproducibility, bibliography, format, and layout standards | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |\n"
            + "| AI | standalone AI-style assessment | moderate | N/A | N/A | high | The short fixture contains one formulaic transition, but the limited corpus prevents any stronger stylistic inference. |\n"
            + "| Chair | chair adjudication | B | 小修后可答辩 | skill-default | high | The current panel evidence covers all nine gates and the assigned citation, bibliography, page, and style duties; one bounded wording revision remains, while no foundational or integrity blocker is visible. |\n\n"
            + "## Current actionable items\n\n"
            + "| Ledger ID | Priority | Chair finding ID | Source reviewer finding IDs | Severity | S0 subtype | Remedy | Exact PDF anchor | Direct PDF-visible observation | Evidence status | Minimum required action | Dependency | Owner | Chair disposition | Verification |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | visible wording defect | verified | correct the wording | none | author | open | reinspect p.1 |\n\n"
            + "## Current AI-style actionable items — separate from academic grading\n\n"
            + "| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Chair status | Verification |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| AI-F01 | local | physical p.1 | formulaic transition | replace the transition | open | reread paragraph after the targeted revision |\n\n"
            + "## Current new evidence or experiments (N)\n\n"
            + "| Evidence item ID | Ledger ID | Chair finding ID | Remedy | Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |\n"
            + "|---|---|---|---|---|---|---|---|---|\n\n"
            + "## Optional suggestions\n\nnone\n\n"
            + "## Unresolved questions\n\n"
            + "| Decision ID | Source item IDs | Topic | Positions | Evidence checked | Status | Decision |\n"
            + "|---|---|---|---|---|---|---|\n\n"
            + "## Review limitations\n\nnone\n\n"
            + "## Reconciliation\n\n"
            + f"- Open required rows in 91-revision-ledger.csv: {academic_count}\n"
            + f"- Rows in 93-current-actionable-items.csv: {academic_count}\n"
            + f"- Rows in Current actionable items Markdown table: {academic_count}\n"
            + "- Missing ledger IDs: none\n"
            + "- Extra summary IDs: none\n"
            + "- Duplicate IDs: none\n"
            + f"- Open AI rows in 91-ai-actionable-ledger.csv: {ai_count}\n"
            + f"- Rows in 93-current-ai-actionable-items.csv: {ai_count}\n"
            + f"- Rows in Current AI-style actionable items Markdown table: {ai_count}\n"
            + "- Missing/extra/duplicate AI finding IDs: none\n"
            + f"- Rows in 92-new-evidence-or-experiments.csv: {evidence_count}\n"
            + f"- Rows in Current new evidence or experiments Markdown table: {evidence_count}\n"
            + "- Missing/extra/duplicate evidence item IDs: none\n"
            + "- Statement: This summary introduces no new finding and uses no "
            + "prior-round or author-side information.\n"
        )

    def enable_fresh_rereview(self, root: Path) -> dict[str, object]:
        process_path = root / "00-process-parameters.json"
        process = json.loads(process_path.read_text(encoding="utf-8"))
        process["review_mode"] = "fresh-rereview"
        process["actor_prompt_sha256"]["V"] = ACTOR_PROMPT_HASHES["V"]
        process_path.write_text(json.dumps(process), encoding="utf-8")
        process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
        manifest = root / "00-manifest.md"
        text = manifest.read_text(encoding="utf-8")
        text = re.sub(
            r"(?m)^- Process-parameter file and SHA-256: .*$",
            "- Process-parameter file and SHA-256: "
            f"00-process-parameters.json / {process_digest}",
            text,
        ).replace("review_mode=initial", "review_mode=fresh-rereview")
        manifest.write_text(text, encoding="utf-8")
        return process

    def write_prior_issues_input(self, root: Path) -> str:
        input_dir = root / "stage-v-inputs"
        input_dir.mkdir(exist_ok=True)
        path = input_dir / "round-previous-prior-issues.csv"
        write_csv(
            path,
            PRIOR_ISSUES_COLUMNS,
            [{
                "PriorFindingID": "OLD-F01",
                "PriorPDFSHA256": "B" * 64,
                "PriorPDFAnchor": "physical p.1",
                "Finding": "the prior PDF contained the fixture wording defect",
                "RequiredClosureEvidence": (
                    "the current frozen PDF visibly contains corrected wording"
                ),
            }],
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        return f"{path.name}@{digest}"

    def stage_v_report(self, root: Path, digest: str) -> str:
        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        prior_issues_identity = self.write_prior_issues_input(root)
        prompt_map = process.get("actor_prompt_sha256", {})
        stage_v_prompt_hash = str(
            prompt_map.get("V", PROMPT_HASH)
            if isinstance(prompt_map, dict) else PROMPT_HASH
        )
        current_files = [
            "00-page-inventory.csv", "00-bibliography-inventory.csv",
            "00-citation-inventory.csv", "02-page-layout-ledger.csv",
            "03-bibliography-audit-ledger.csv",
            "04-citation-claim-audit-ledger.csv",
            "R1-comprehensive-review.md", "R2-comprehensive-review.md",
            "R3-comprehensive-review.md", "05-ai-style-assessment.md",
            "90-chair-synthesis.md", "91-revision-ledger.md",
            "91-revision-ledger.csv", "91-ai-actionable-ledger.csv",
            "92-new-evidence-or-experiments.md",
            *(
                ["92-new-evidence-or-experiments.csv"]
                if (root / "92-new-evidence-or-experiments.csv").is_file()
                else []
            ),
            "93-user-facing-summary.md",
            "93-current-actionable-items.csv",
            "93-current-ai-actionable-items.csv",
        ]
        current_identities = " ; ".join(
            f"{name}@{hashlib.sha256((root / name).read_bytes()).hexdigest().upper()}"
            for name in current_files
        )
        prior_issues_name = prior_issues_identity.split("@", 1)[0]
        opened = "; ".join([
            "00-process-parameters.json", "SKILL.md",
            "clean-room-orchestration.md", "grading-and-verdicts.md",
            "report-template.md", "ai-style-audit.md", "ledger-validation.md",
            process["frozen_pdf_file"], *current_files, prior_issues_name,
        ])
        return (
            "# Post-freeze prior-issue closure verification\n\n"
            + "## Boundary and frozen-current-round identity\n"
            + "- Actor ID: V\n"
            + f"- Review round ID: {process['round_id']}\n"
            + f"- Review retry ID: {process['retry_id']}\n"
            + f"- Current frozen PDF and round: round_id={process['round_id']} ; retry_id={process['retry_id']} ; file={process['frozen_pdf_file']} ; sha256={digest}\n"
            + f"- Current fresh reports/chair/summary already frozen: {current_identities}\n"
            + f"- Hash-bound prior-issues CSV: {prior_issues_identity}\n"
            + "- Additional allowlisted prior artifacts: none\n"
            + "- Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested: not run\n"
            + "- Full regression baseline: not run\n"
            + "- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt\n"
            + f"- Operational prompt SHA-256: {stage_v_prompt_hash}\n"
            + "- Input-receipt/access declaration: received=[operational prompt]; "
            + f"opened=[{opened}]; public_endpoints=[none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated\n"
            + f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n\n"
            + "## Prior-issue closure\n\n"
            + "| Prior finding | Status | Evidence in revised PDF | Regression check | Current-round related finding, if any |\n"
            + "|---|---|---|---|---|\n"
            + "| OLD-F01 | resolved | physical p.1 visibly contains the corrected fixture wording | not assessed | none |\n\n"
            + "## Longitudinal AI-style comparison — non-review\n"
            + "- Status: not run\n"
            + "- Prior AI report identity/hash: N/A\n"
            + "- Current AI report identity/hash: N/A\n"
            + "- Prior open material/local AI-F IDs: N/A\n"
            + "- Current corresponding evidence/status: N/A\n"
            + "- New current AI-F IDs: N/A\n"
            + "- Limitations: longitudinal comparison was not requested and no prior AI-style report was opened\n"
            + "- Separation statement: this comparison does not alter the current chair decision, grade, current AI report, 91 ledgers, or 93 summary.\n\n"
            + "## Full longitudinal regression audit — non-review\n"
            + "- Status: not run\n"
            + f"- Prior/current PDF identities and hashes: prior=N/A ; current={process['frozen_pdf_file']}@{digest}\n"
            + "- Prior/current page, bibliography, citation inventory/ledger identities and hashes: prior=N/A ; current=current-round frozen ledgers listed above\n"
            + "- Demonstrated regressions on comparable objects: none assessed\n"
            + "- Current fresh findings whose introduction time is not verifiable: all current fresh findings\n"
            + "- Limitations: global regression not assessed because the complete prior baseline was not opened\n\n"
            + "## Iterative completion checklist\n"
            + f"- Final page-ledger re-entry: inventory_rows={process['physical_page_count']} ; ledger_rows={process['physical_page_count']} ; expected={process['physical_page_count']} ; missing_or_extra_page_ids=0 ; unchecked_or_unresolved=0\n"
            + "- Final page and affected-neighbor recheck: rows_missing_neighbor_record=0\n"
            + "- Final bibliography/citation re-entry and re-verification: bibliography_inventory_rows=1 ; bibliography_audit_rows=17 ; bibliography_missing_or_extra_ids=0 ; bibliography_mismatch=0 ; bibliography_unverifiable=0 ; citation_inventory_rows=1 ; citation_audit_rows=1 ; citation_missing_or_extra_ids=0 ; citation_support_mismatch=0 ; citation_support_unverifiable=0 ; citation_metadata_mismatch=0 ; citation_metadata_unverifiable=0\n"
            + "- Empty S0--S3 status across all current reviewers: no ; reviewer_s0_s3=3 ; open_academic_rows=1\n"
            + "- Fresh isolated AI assessment status/signal/material remainder: run ; signal=moderate ; open_material_or_local_rows=1\n"
            + "- Remaining S4 suggestions or review limitations: none in this fixture\n"
            + "- Prior unresolved or not-verifiable findings: count=0\n"
            + "- Iterative-loop completion gate: fail\n"
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
        page_ledger_rows = [{
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
        } for physical_page in range(1, page_count + 1)]
        bibliography_inventory_rows = [{
            "ReferenceID": "REF0001",
            "DisplayedLabel": "[1]",
            "RenderedEntry": "Fixture reference.",
            "Cited": "yes",
            "PDFSHA256": digest,
        }]
        bibliography_ledger_rows = [{
            "ReferenceID": "REF0001",
            "DisplayedLabel": "[1]",
            "Cited": "yes",
            "Field": field,
            "RenderedValue": "fixture",
            "CanonicalValue": (
                "N/A" if field in {
                    "volume", "issue", "pages_or_article_number", "arxiv_id",
                    "arxiv_version", "url", "access_date",
                    "isbn_or_other_persistent_id",
                } else "fixture"
            ),
            "Verdict": (
                "legitimate N/A" if field in {
                    "volume", "issue", "pages_or_article_number", "arxiv_id",
                    "arxiv_version", "url", "access_date",
                    "isbn_or_other_persistent_id",
                } else "exact"
            ),
            "EvidenceEndpoint": "https://doi.org/10.1145/3442188.3445922",
            "EndpointType": "official fixture",
            "CheckedAt": "2026-08-29",
            "EvidenceNote": "fixture official record checked",
            "FindingDisposition": "no finding",
            "PDFSHA256": digest,
        } for field in BIB_FIELDS]
        citation_ledger_rows = [{
            "PairID": "C0001-S01",
            "OccurrenceID": "C0001",
            "PDFLocation": "physical p.1",
            "ExactAttachedProposition": "fixture proposition",
            "ReferenceID": "REF0001",
            "PublicIdentifier": "doi:fixture",
            "ContentSourceOpened": (
                "https://dl.acm.org/doi/pdf/10.1145/3442188.3445922"
            ),
            "ExactSourceLocator": "p.1",
            "Support": "direct",
            "MetadataStatus": "verified",
            "SeverityFinding": "none",
            "DispositionEvidence": "supported",
            "PDFSHA256": digest,
        }]
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
            "actor_prompt_sha256": {
                actor: ACTOR_PROMPT_HASHES[actor]
                for actor in ("P", "R1", "R2", "R3", "AI", "C", "S")
            },
        }
        process_path = root / "00-process-parameters.json"
        process_path.write_text(json.dumps(process), encoding="utf-8")
        process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
        packet_opened = "; ".join(
            VALIDATOR_MODULE.canonical_stage_opened_inputs(process, 3, "P")
        )
        (root / "00-manifest.md").write_text(
            "# Frozen evidence manifest\n\n"
            + f"- Process-parameter file and SHA-256: 00-process-parameters.json / {process_digest}\n"
            + "- Actor ID: P\n"
            + f"- Review round ID: {process['round_id']}\n"
            + f"- Review retry ID: {process['retry_id']}\n"
            + "- Packet-builder fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt\n"
            + f"- Packet-builder input-receipt/access declaration: received=[operational prompt]; opened=[{packet_opened}]; public_endpoints=[none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated\n"
            + f"- Operational prompt SHA-256: {process['actor_prompt_sha256']['P']}\n"
            + f"- Frozen PDF SHA-256 at start and end: {digest} / {digest}\n"
            + "- Frozen at: 2026-08-29T12:34:56+08:00\n"
            + "- Degree/institution/discipline: degree_level=masters ; degree_type=academic ; institution=null ; school_or_department=null ; discipline=computer science ; expected_submission_year=2026\n"
            + "- Review round and purpose: round_id=fixture ; retry_id=r1 ; review_mode=initial ; artifact_type=author-copy ; output_language=zh-CN\n"
            + f"- Frozen PDF path, SHA-256, frozen_at timestamp, and pages: file=frozen-thesis.pdf ; sha256={digest} ; frozen_at=2026-08-29T12:34:56+08:00 ; pages={page_count}\n"
            + "- Governing template/rules: template=thesis-review/SKILL.md ; decision_regime_status=skill-default ; sources=none\n"
            + "- Reviewer-visible artifact: exactly one frozen thesis PDF: frozen-thesis.pdf\n"
            + "- Permitted public citation-verification sources: authoritative publisher, DOI, proceedings, and official full-text http(s) endpoints only\n"
            + "- Prohibited context and artifacts: conversation/memory summaries, user explanations, earlier assistant outputs, other actors' messages, thesis source, .bib, build/auxiliary files, Git history, sibling repositories, local papers, code/config/logs, old rounds, source/provenance audits, and author-side records\n"
            + "- Items explicitly out of scope: source-side implementation assertions and any prior-round material not visible in the frozen PDF\n\n"
            + "## Thesis structure\n\nThe fixture contains authored thesis matter on physical p.1 and a rendered bibliography on physical p.2.\n\n"
            + "## Thesis-stated questions and contributions — neutral navigation only\n\nThe fixture proposition appears on physical p.1; this line records its location without evaluating the claim.\n\n"
            + "## Objective inventories and locations\n\nThe closed inventories are 00-page-inventory.csv, 00-bibliography-inventory.csv, 00-citation-candidate-ledger.csv, 00-citation-inventory.csv, and 00-unmatched-bracket-ledger.csv.\n\n"
            + "- Numeric-bracket candidate rows: 3\n"
            + "- Citation-classified candidate rows: 1\n"
            + "- Non-citation-classified candidate rows: 2\n"
            + "- Unmatched square-bracket glyphs: 0\n"
            + "- Unmatched glyph dispositions: No unmatched glyph was found "
            + "in the rendered fixture page.\n",
            encoding="utf-8",
        )
        (root / "01-policy-basis.md").write_text(
            "# Policy\n\n" + self.declaration(digest, process, "P"),
            encoding="utf-8",
        )
        (root / "02-page-layout-ledger.md").write_text(
            "# Page ledger\n\n" + self.declaration(digest, process, "R3")
            + markdown_table(
                PAGE_MARKDOWN_HEADERS,
                [[
                    markdown_projection_scalar(row[field])
                    for field in PAGE_MARKDOWN_FIELDS
                ] for row in page_ledger_rows],
            ),
            encoding="utf-8",
        )
        (root / "03-bibliography-audit-ledger.md").write_text(
            "# Bibliography ledger\n\n"
            + self.declaration(digest, process, "R3", [BIB_ENDPOINT])
            + markdown_table(
                BIB_MARKDOWN_HEADERS,
                bibliography_markdown_rows(
                    bibliography_inventory_rows, bibliography_ledger_rows
                ),
            ),
            encoding="utf-8",
        )
        (root / "04-citation-claim-audit-ledger.md").write_text(
            "# Citation ledger\n\n"
            + self.declaration(digest, process, "R3", [CITATION_ENDPOINT])
            + markdown_table(
                CITATION_MARKDOWN_HEADERS,
                citation_markdown_rows(
                    citation_ledger_rows, bibliography_inventory_rows
                ),
            ),
            encoding="utf-8",
        )
        (root / "91-revision-ledger.md").write_text(
            "# Revision ledger\n\n" + self.declaration(digest, process, "C")
            + "| Ledger ID | Priority | Chair finding ID | Source reviewer finding IDs | Severity | S0 subtype | Remedy | Exact PDF anchor | Direct observation | Evidence status | Minimum edit/evidence | Dependency | Owner | Status | Verification |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            + "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | visible wording defect | verified | correct the wording | none | author | open | reinspect p.1 |\n\n"
            + "## AI-style actionable ledger — separate from academic grading\n\n"
            + "| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Status | Verification |\n"
            + "|---|---|---|---|---|---|---|\n"
            + "| AI-F01 | local | physical p.1 | formulaic transition | replace the transition | open | reread paragraph after the targeted revision |\n",
            encoding="utf-8",
        )
        (root / "92-new-evidence-or-experiments.md").write_text(
            "# New evidence or experiments\n\n"
            + self.declaration(digest, process, "C")
            + "## No-new-experiment remedies (W/E/P)\n\n"
            + "| Ledger ID | Remedy | Exact PDF anchor | Minimum edit/evidence | Verification |\n"
            + "|---|---|---|---|---|\n"
            + "| L01 | W | physical p.1 | correct the wording | reinspect p.1 |\n\n"
            + "## Genuine new experiments or unavailable evidence (N)\n\n"
            + "| Evidence item ID | Ledger ID | Chair finding ID | Remedy | Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |\n"
            + "|---|---|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        for index in range(1, 4):
            (root / f"R{index}-comprehensive-review.md").write_text(
                self.reviewer_report(digest, index, process), encoding="utf-8"
            )
        (root / "05-ai-style-assessment.md").write_text(
            self.ai_report(digest, process), encoding="utf-8"
        )
        (root / "90-chair-synthesis.md").write_text(
            self.chair_report(digest, process), encoding="utf-8"
        )
        (root / "93-user-facing-summary.md").write_text(
            self.summary_report(digest, process), encoding="utf-8"
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
            page_ledger_rows,
        )
        write_csv(
            root / "00-bibliography-inventory.csv",
            BIB_INVENTORY_COLUMNS,
            bibliography_inventory_rows,
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
                "Marker": "[3,8]",
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
                "Marker": "[0.85,1]",
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
            bibliography_ledger_rows,
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
            citation_ledger_rows,
        )
        write_csv(
            root / "91-revision-ledger.csv",
            ACADEMIC_LEDGER_COLUMNS,
            [{
                "LedgerID": "L01",
                "Priority": "P2",
                "ChairFindingID": "C-F01",
                "SourceReviewerFindingIDs": "R1-F01, R2-F01, R3-F01",
                "Severity": "S2",
                "S0Subtype": "N/A",
                "Remedy": "W",
                "ExactPDFAnchor": "physical p.1",
                "DirectObservation": "visible wording defect",
                "EvidenceStatus": "verified",
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
                "Priority": "P2",
                "ChairFindingID": "C-F01",
                "SourceReviewerFindingIDs": "R1-F01, R2-F01, R3-F01",
                "Severity": "S2",
                "S0Subtype": "N/A",
                "Remedy": "W",
                "ExactPDFAnchor": "physical p.1",
                "DirectObservation": "visible wording defect",
                "EvidenceStatus": "verified",
                "MinimumEditEvidence": "correct the wording",
                "Dependency": "none",
                "Owner": "author",
                "Status": "open",
                "Verification": "reinspect p.1",
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
                "Verification": "reread paragraph after the targeted revision",
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
                "Status": "open",
                "Verification": "reread paragraph after the targeted revision",
            }],
        )
        write_csv(
            root / "92-new-evidence-or-experiments.csv",
            EVIDENCE_ITEM_COLUMNS,
            [],
        )
        return digest

    def convert_bundle_to_doctorate(self, root: Path) -> None:
        process_path = root / "00-process-parameters.json"
        process = json.loads(process_path.read_text(encoding="utf-8"))
        masters_r1_opened = "; ".join(
            VALIDATOR_MODULE.canonical_stage_opened_inputs(process, 3, "R1")
        )
        masters_r3_opened = "; ".join(
            VALIDATOR_MODULE.canonical_stage_opened_inputs(process, 3, "R3")
        )
        process["degree_level"] = "doctorate"
        process["actor_prompt_sha256"]["R4"] = ACTOR_PROMPT_HASHES["R4"]
        process["actor_prompt_sha256"]["R5"] = ACTOR_PROMPT_HASHES["R5"]
        process_path.write_text(json.dumps(process), encoding="utf-8")
        doctoral_opened = {
            actor_id: "; ".join(
                VALIDATOR_MODULE.canonical_stage_opened_inputs(
                    process, 5, actor_id
                )
            )
            for actor_id in ("R3", "R4", "R5")
        }
        process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
        manifest = root / "00-manifest.md"
        manifest_text = manifest.read_text(encoding="utf-8")
        manifest_text = re.sub(
            r"(?m)^- Process-parameter file and SHA-256: .*$",
            "- Process-parameter file and SHA-256: "
            f"00-process-parameters.json / {process_digest}",
            manifest_text,
        ).replace("degree_level=masters", "degree_level=doctorate")
        manifest.write_text(manifest_text, encoding="utf-8")

        r2_old_assignment = (
            "R2 contribution/positioning + thesis architecture/narrative"
        )
        r2_new_assignment = "R2 contribution/novelty/positioning"
        r2_old_emphasis = (
            "contribution, thesis logic, and cross-chapter narrative coherence"
        )
        r2_new_emphasis = (
            "contribution, novelty, and positioning across the complete thesis"
        )
        r3_old_assignment = (
            "R3 evidence/integrity/citation + format/bibliography/layout"
        )
        r3_new_assignment = "R3 thesis architecture/narrative"
        r3_old_emphasis = (
            "evidence integrity, reproducibility, bibliography, format, and layout standards"
        )
        r3_new_emphasis = (
            "Abstract, introduction, scientific-question, contribution, and roadmap "
            "alignment; coherent chapter progression; cross-chapter terminology; "
            "shared infrastructure; conclusions; and thesis synthesis, while still "
            "judging every Gate A through I."
        )
        r2 = root / "R2-comprehensive-review.md"
        r2.write_text(
            r2.read_text(encoding="utf-8")
            .replace(r2_old_assignment, r2_new_assignment)
            .replace(r2_old_emphasis, r2_new_emphasis),
            encoding="utf-8",
        )
        r3 = root / "R3-comprehensive-review.md"
        original_r3 = r3.read_text(encoding="utf-8")
        page_section = re.search(
            r"(?ms)^## Full rendered-page audit\n.*?(?=^## Full bibliography-integrity audit)",
            original_r3,
        )
        bib_section = re.search(
            r"(?ms)^## Full bibliography-integrity audit\n.*?(?=^## Full citation-claim audit)",
            original_r3,
        )
        citation_section = re.search(
            r"(?ms)^## Full citation-claim audit\n.*\Z", original_r3
        )
        self.assertIsNotNone(page_section)
        self.assertIsNotNone(bib_section)
        self.assertIsNotNone(citation_section)
        r3_text = re.sub(
            r"(?ms)\n## Full rendered-page audit\n.*\Z", "", original_r3
        ).replace(r3_old_assignment, r3_new_assignment).replace(
            r3_old_emphasis, r3_new_emphasis
        ).replace(
            f"public_endpoints=[{BIB_ENDPOINT}; {CITATION_ENDPOINT}]",
            "public_endpoints=[none]",
        ).replace(
            f"opened=[{masters_r3_opened}]",
            f"opened=[{doctoral_opened['R3']}]",
        )
        r3.write_text(r3_text, encoding="utf-8")

        clone = (root / "R1-comprehensive-review.md").read_text(encoding="utf-8")
        r4_assignment = "R4 evidence/reproducibility/integrity/citation"
        r4_emphasis = (
            "evidence integrity, reproducibility, and citation support across the complete thesis"
        )
        r5_assignment = "R5 format/bibliography/layout"
        r5_emphasis = (
            "format, bibliography, layout, page presentation, and standards across the complete thesis"
        )
        r1_assignment = "R1 technical/methods/experiments"
        r1_emphasis = (
            "technical method and experiment reasoning across the complete thesis"
        )
        r1_natural_emphasis = (
            "Algorithms, representations, losses, training and inference, data splits, "
            "baselines, metrics, ablations, uncertainty, user studies, resource fairness, "
            "and reproducibility, while still judging every Gate A through I."
        )
        (root / "R1-comprehensive-review.md").write_text(
            clone.replace(r1_emphasis, r1_natural_emphasis), encoding="utf-8"
        )
        r4_text = (
            clone.replace("# R1 —", "# R4 —", 1)
            .replace("R1-F01", "R4-F01")
            .replace("- Actor ID: R1", "- Actor ID: R4")
            .replace(ACTOR_PROMPT_HASHES["R1"], ACTOR_PROMPT_HASHES["R4"])
            .replace("public_endpoints=[none]", f"public_endpoints=[{CITATION_ENDPOINT}]")
            .replace(r1_assignment, r4_assignment)
            .replace(r1_emphasis, r4_emphasis)
            .replace(
                f"opened=[{masters_r1_opened}]",
                f"opened=[{doctoral_opened['R4']}]",
            )
            + "\n\n"
            + (citation_section.group(0).strip() if citation_section else "")
            + "\n"
        )
        r5_text = (
            clone.replace("# R1 —", "# R5 —", 1)
            .replace("R1-F01", "R5-F01")
            .replace("- Actor ID: R1", "- Actor ID: R5")
            .replace(ACTOR_PROMPT_HASHES["R1"], ACTOR_PROMPT_HASHES["R5"])
            .replace("public_endpoints=[none]", f"public_endpoints=[{BIB_ENDPOINT}]")
            .replace(r1_assignment, r5_assignment)
            .replace(r1_emphasis, r5_emphasis)
            .replace(
                f"opened=[{masters_r1_opened}]",
                f"opened=[{doctoral_opened['R5']}]",
            )
            + "\n\n"
            + (page_section.group(0).strip() if page_section else "")
            + "\n\n"
            + (bib_section.group(0).strip() if bib_section else "")
            + "\n"
        )
        (root / "R4-comprehensive-review.md").write_text(r4_text, encoding="utf-8")
        (root / "R5-comprehensive-review.md").write_text(r5_text, encoding="utf-8")

        for filename, old_actor, new_actor in (
            ("02-page-layout-ledger.md", "R3", "R5"),
            ("03-bibliography-audit-ledger.md", "R3", "R5"),
            ("04-citation-claim-audit-ledger.md", "R3", "R4"),
        ):
            path = root / filename
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                f"- Actor ID: {old_actor}", f"- Actor ID: {new_actor}", 1
            ).replace(
                ACTOR_PROMPT_HASHES[old_actor],
                ACTOR_PROMPT_HASHES[new_actor],
                1,
            ).replace(
                f"opened=[{masters_r3_opened}]",
                f"opened=[{doctoral_opened[new_actor]}]",
            )
            path.write_text(text, encoding="utf-8")

        old_sources = "R1-F01, R2-F01, R3-F01"
        new_sources = "R1-F01, R2-F01, R3-F01, R4-F01, R5-F01"
        old_report_tail = "R3-comprehensive-review.md; 05-ai-style-assessment.md"
        new_report_tail = (
            "R3-comprehensive-review.md; R4-comprehensive-review.md; "
            "R5-comprehensive-review.md; 05-ai-style-assessment.md"
        )
        for filename in (
            "91-revision-ledger.md", "92-new-evidence-or-experiments.md",
            "90-chair-synthesis.md",
            "93-user-facing-summary.md",
        ):
            path = root / filename
            text = (
                path.read_text(encoding="utf-8")
                .replace(old_sources, new_sources)
                .replace(r2_old_assignment, r2_new_assignment)
                .replace(r2_old_emphasis, r2_new_emphasis)
                .replace(r3_old_assignment, r3_new_assignment)
                .replace(r3_old_emphasis, r3_new_emphasis)
                .replace(r1_emphasis, r1_natural_emphasis)
                .replace(old_report_tail, new_report_tail)
            )
            path.write_text(text, encoding="utf-8")
        _headers, academic_rows = read_csv(root / "91-revision-ledger.csv")
        academic_rows[0]["SourceReviewerFindingIDs"] = new_sources
        write_csv(
            root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, academic_rows
        )
        _headers, summary_rows = read_csv(root / "93-current-actionable-items.csv")
        summary_rows[0]["SourceReviewerFindingIDs"] = new_sources
        write_csv(
            root / "93-current-actionable-items.csv",
            ACADEMIC_SUMMARY_COLUMNS,
            summary_rows,
        )

        rationale = (
            "The complete fixture thesis was assessed across policy, argument, "
            "literature, methods, data, experiments, reproducibility, writing, "
            "and presentation; the visible evidence supports a minor-revision "
            "recommendation without a blocker."
        )
        chair = root / "90-chair-synthesis.md"
        chair_text = chair.read_text(encoding="utf-8")
        chair_text = chair_text.replace(
            "| R3 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | yes | yes |",
            "| R3 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | not assigned | yes |\n"
            "| R4 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | yes | yes |\n"
            "| R5 | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | adequate | complete | yes | yes |",
            1,
        )
        r4_verdict = (
            f"| R4 | {r4_assignment} — {r4_emphasis} | B | 小修后可答辩 | "
            f"skill-default | high | {rationale} |"
        )
        r5_verdict = (
            f"| R5 | {r5_assignment} — {r5_emphasis} | B | 小修后可答辩 | "
            f"skill-default | high | {rationale} |"
        )
        r3_verdict_prefix = f"| R3 | {r3_new_assignment} — {r3_new_emphasis}"
        r3_line = next(
            line for line in chair_text.splitlines() if line.startswith(r3_verdict_prefix)
        )
        chair_text = chair_text.replace(
            r3_line, r3_line + "\n" + r4_verdict + "\n" + r5_verdict, 1
        ).replace("- Category distribution: B=3", "- Category distribution: B=5")
        chair.write_text(chair_text, encoding="utf-8")

        summary = root / "93-user-facing-summary.md"
        summary_text = summary.read_text(encoding="utf-8")
        summary_r3_line = next(
            line for line in summary_text.splitlines()
            if line.startswith(r3_verdict_prefix)
        )
        summary_text = summary_text.replace(
            summary_r3_line,
            summary_r3_line + "\n" + r4_verdict + "\n" + r5_verdict,
            1,
        )
        summary.write_text(summary_text, encoding="utf-8")

    def run_validator(
        self, root: Path, report: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-B", str(VALIDATOR), str(root)]
        if report:
            command.extend(["--write-report", str(report)])
        return subprocess.run(
            command, text=True, capture_output=True, check=False
        )

    def set_bibliography_mismatch(
        self, root: Path, finding_disposition: str
    ) -> None:
        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        digest = str(process["selected_pdf_sha256"])
        _, bib_rows = read_csv(root / "03-bibliography-audit-ledger.csv")
        row = next(
            item for item in bib_rows
            if item["Field"] == "retraction_withdrawal_correction_superseding"
        )
        row["Verdict"] = "mismatch"
        row["CanonicalValue"] = "corrected record exists"
        row["FindingDisposition"] = finding_disposition
        write_csv(
            root / "03-bibliography-audit-ledger.csv",
            BIB_LEDGER_COLUMNS,
            bib_rows,
        )
        _, inventory = read_csv(root / "00-bibliography-inventory.csv")
        (root / "03-bibliography-audit-ledger.md").write_text(
            "# Bibliography ledger\n\n"
            + self.declaration(digest, process, "R3", [BIB_ENDPOINT])
            + markdown_table(
                BIB_MARKDOWN_HEADERS,
                bibliography_markdown_rows(inventory, bib_rows),
            ),
            encoding="utf-8",
        )
        reviewer = root / "R3-comprehensive-review.md"
        reviewer_text = reviewer.read_text(encoding="utf-8")
        old_count = (
            "- Retraction/withdrawal/correction/superseding-status fields "
            "verified / mismatched / legitimate N/A / unverifiable: 1 / 0 / 0 / 0"
        )
        self.assertIn(old_count, reviewer_text)
        reviewer.write_text(
            reviewer_text.replace(
                old_count,
                "- Retraction/withdrawal/correction/superseding-status fields "
                "verified / mismatched / legitimate N/A / unverifiable: 0 / 1 / 0 / 0",
                1,
            ),
            encoding="utf-8",
        )

    def assert_fails(self, root: Path, needle: str) -> None:
        result = self.run_validator(root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(needle, result.stdout)

    def add_external_artifact_finding_and_chair_decision(
        self, root: Path, *, status: str = "rejected", finding_id: str = "R1-F02"
    ) -> None:
        reviewer = root / "R1-comprehensive-review.md"
        reviewer_text = reviewer.read_text(encoding="utf-8")
        finding = (
            f"### {finding_id} — external author-side artifact request\n"
            "- Primary gate: G\n"
            "- Secondary gates: E\n"
            "- Scope: local\n"
            "- Severity: S2\n"
            "- S0 subtype: N/A\n"
            "- Remedy: E\n"
            "- Required for the current defense conclusion: no; Chair scope decision required\n"
            "- Location: physical p.1, fixture section\n"
            "- Observation: The PDF does not include an author-side forensic replay package.\n"
            "- Why it matters: The reviewer incorrectly treats hidden artifacts as a thesis obligation.\n"
            "- Evidence: The frozen PDF and governing rules contain no formal attachment requirement or exact public-artifact claim.\n"
            "- Required action: Supply private source commits, environment locks, full commands, training logs, checkpoint and member hashes, an immutable manifest, a controlled replay package, and confidential raw data.\n"
            "- Verification: Inspect the requested private package outside the submitted thesis.\n"
            "- Confidence: high\n\n"
        )
        reviewer.write_text(
            reviewer_text.replace(
                "## Questions, not findings", finding + "## Questions, not findings", 1
            ),
            encoding="utf-8",
        )

        chair = root / "90-chair-synthesis.md"
        chair_text = chair.read_text(encoding="utf-8")
        decision_header = (
            "| Decision ID | Source item IDs | Topic | Positions | Evidence checked | Status | Decision |\n"
            "|---|---|---|---|---|---|---|\n"
        )
        decision_row = (
            f"| D01 | {finding_id} | external author-side artifact demand | "
            "reviewer requests hidden artifacts | frozen PDF and governing rules "
            "show no formal submission obligation or exact public-artifact claim | "
            f"{status} | outside the thesis submission obligation; no thesis action |\n"
        )
        self.assertIn(decision_header, chair_text)
        chair.write_text(
            chair_text.replace(decision_header, decision_header + decision_row, 1),
            encoding="utf-8",
        )

    def test_complete_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_complete_doctoral_five_reviewer_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.convert_bundle_to_doctorate(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_doctoral_r3_model_architecture_only_is_not_thesis_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.convert_bundle_to_doctorate(root)
            authentic = (
                "Abstract, introduction, scientific-question, contribution, and roadmap "
                "alignment; coherent chapter progression; cross-chapter terminology; "
                "shared infrastructure; conclusions; and thesis synthesis, while still "
                "judging every Gate A through I."
            )
            wrong = (
                "Model architecture and neural design details across every chapter, "
                "while still judging every Gate A through I."
            )
            for filename in (
                "R3-comprehensive-review.md",
                "90-chair-synthesis.md",
                "93-user-facing-summary.md",
            ):
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(authentic, wrong),
                    encoding="utf-8",
                )
            self.assert_fails(
                root,
                "Persona emphasis is missing or does not match the distinct R3 emphasis",
            )

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
            markdown_path = root / "02-page-layout-ledger.md"
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(
                    "| P0001 | 1 |  |", "| P0001 | 1 | X |", 1
                ),
                encoding="utf-8",
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

    def test_page_markdown_non_id_field_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "02-page-layout-ledger.md"
            text = path.read_text(encoding="utf-8").replace(
                " | clean | full-page render inspected |",
                " | finding invented | page was not inspected |",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root, "Markdown/CSV value mismatch for P0001/Disposition"
            )

    def test_page_markdown_row_order_must_be_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "02-page-layout-ledger.md"
            lines = path.read_text(encoding="utf-8").splitlines()
            first = next(i for i, line in enumerate(lines) if line.startswith("| P0001 |"))
            second = next(i for i, line in enumerate(lines) if line.startswith("| P0002 |"))
            lines[first], lines[second] = lines[second], lines[first]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assert_fails(root, "deterministic row order mismatch")

    def test_bibliography_markdown_serialized_field_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "03-bibliography-audit-ledger.md"
            text = path.read_text(encoding="utf-8").replace(
                '"canonical":"fixture"',
                '"canonical":"invented different value"',
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root, "Markdown/CSV value mismatch for REF0001/Type"
            )

    def test_citation_markdown_non_id_field_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "04-citation-claim-audit-ledger.md"
            text = path.read_text(encoding="utf-8").replace(
                " | direct | verified |",
                " | mismatch | mismatch |",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root, "Markdown/CSV value mismatch for C0001-S01/Support"
            )

    def test_citation_markdown_combined_source_serialization_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "04-citation-claim-audit-ledger.md"
            text = path.read_text(encoding="utf-8").replace(
                '"exact_source_locator":"p.1"',
                '"exact_source_locator":"p.2"',
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "Markdown/CSV value mismatch for C0001-S01/"
                "Content source opened and exact locator",
            )

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

    def test_bibliography_endpoint_must_be_one_complete_url_for_all_verdicts(
        self,
    ) -> None:
        cases = (
            ("leading text", f"checked {BIB_ENDPOINT}", "exact"),
            ("trailing text", f"{BIB_ENDPOINT} checked", "exact"),
            (
                "two URLs",
                f"{BIB_ENDPOINT} https://example.org/second",
                "exact",
            ),
            ("unverifiable row", f"attempted {BIB_ENDPOINT}", "unverifiable"),
        )
        for label, endpoint, verdict in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                digest = self.build_bundle(root)
                process = json.loads(
                    (root / "00-process-parameters.json").read_text(encoding="utf-8")
                )
                _, bib_rows = read_csv(root / "03-bibliography-audit-ledger.csv")
                row = next(item for item in bib_rows if item["Field"] == "type")
                row["EvidenceEndpoint"] = endpoint
                if verdict == "unverifiable":
                    row["Verdict"] = verdict
                    row["CanonicalValue"] = "not established"
                    row["EndpointType"] = "official route inaccessible"
                    row["EvidenceNote"] = (
                        "Attempted the official route, but no authoritative record "
                        "could be opened."
                    )
                write_csv(
                    root / "03-bibliography-audit-ledger.csv",
                    BIB_LEDGER_COLUMNS,
                    bib_rows,
                )
                _, inventory = read_csv(root / "00-bibliography-inventory.csv")
                (root / "03-bibliography-audit-ledger.md").write_text(
                    "# Bibliography ledger\n\n"
                    + self.declaration(digest, process, "R3", [BIB_ENDPOINT])
                    + markdown_table(
                        BIB_MARKDOWN_HEADERS,
                        bibliography_markdown_rows(inventory, bib_rows),
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "EvidenceEndpoint lacks an http(s) authoritative record or "
                    "contains material outside one complete URL",
                )

    def test_chair_citation_gate_cannot_pass_unresolved_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            chair_path = root / "90-chair-synthesis.md"
            chair = chair_path.read_text(encoding="utf-8")
            chair = chair.replace(
                "agree | none | none | closed |",
                "agree | substantive | C-F01 | open |",
            )
            chair = chair.replace("- Substantive conflicts: 0", "- Substantive conflicts: 1")
            chair = chair.replace("- Reclassified Pair IDs: 0", "- Reclassified Pair IDs: 1")
            chair = chair.replace("- Unresolved conflicts: 0", "- Unresolved conflicts: 1")
            chair_path.write_text(chair, encoding="utf-8")
            self.assert_fails(root, "Combined citation gate cannot pass")

    def test_chair_cross_ledger_must_join_exact_reference_and_pair_ids(self) -> None:
        mutations = (
            (
                "| REF0001 | [1] |",
                "| REF9999 | [1] |",
                "chair citation cross-ledger reference IDs",
            ),
            (
                "| REF0001 | [1] | C0001-S01 |",
                "| REF0001 | [1] | C9999-S01 |",
                "Affected Pair IDs do not exactly project",
            ),
            (
                "- Unique cited rendered references joined: 1",
                "- Unique cited rendered references joined: 999",
                "joined cited-reference count 999",
            ),
            (
                "agree | none | none | closed |",
                "agree | local | none | closed |",
                "conflict row requires a canonical",
            ),
        )
        for old, new, needle in mutations:
            with self.subTest(needle=needle), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                path = root / "90-chair-synthesis.md"
                path.write_text(
                    path.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                self.assert_fails(root, needle)

    def test_summary_extra_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            write_csv(
                root / "93-current-actionable-items.csv",
                ACADEMIC_SUMMARY_COLUMNS,
                [{
                    "LedgerID": "OLD-X",
                    "Priority": "P2",
                    "ChairFindingID": "C-F99",
                    "SourceReviewerFindingIDs": "R1-F01",
                    "Severity": "S2",
                    "S0Subtype": "N/A",
                    "Remedy": "W",
                    "ExactPDFAnchor": "p.1",
                    "DirectObservation": "old visible observation",
                    "EvidenceStatus": "verified",
                    "MinimumEditEvidence": "old minimum action",
                    "Dependency": "none",
                    "Owner": "author",
                    "Status": "open",
                    "Verification": "old verification action",
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

    def test_citation_pair_mapping_and_malformed_dangling_fail(self) -> None:
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
            self.assertIn("requires Support=unverifiable", result.stdout)

    def test_complete_dangling_citation_fixture_passes_full_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.convert_bundle_to_dangling_reference(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_malformed_dangling_citation_contract_fails_full_gate(self) -> None:
        cases = (
            (
                "sentinel",
                lambda row: row.__setitem__("PublicIdentifier", "invented identity"),
                "requires PublicIdentifier='no rendered bibliography entry'",
            ),
            (
                "metadata status",
                lambda row: row.__setitem__("MetadataStatus", "verified"),
                "requires MetadataStatus=mismatch",
            ),
            (
                "owner link",
                lambda row: row.update({
                    "SeverityFinding": "no current finding",
                    "DispositionEvidence": "unsupported dangling citation",
                }),
                "mismatch row must link an owning-reviewer",
            ),
        )
        for label, mutate, needle in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                self.convert_bundle_to_dangling_reference(root)
                _, rows = read_csv(root / "04-citation-claim-audit-ledger.csv")
                mutate(rows[0])
                write_csv(
                    root / "04-citation-claim-audit-ledger.csv",
                    CITATION_LEDGER_COLUMNS,
                    rows,
                )
                process = json.loads(
                    (root / "00-process-parameters.json").read_text(encoding="utf-8")
                )
                digest = process["selected_pdf_sha256"]
                _, bibliography = read_csv(
                    root / "00-bibliography-inventory.csv"
                )
                (root / "04-citation-claim-audit-ledger.md").write_text(
                    "# Citation ledger\n\n"
                    + self.declaration(digest, process, "R3")
                    + markdown_table(
                        CITATION_MARKDOWN_HEADERS,
                        citation_markdown_rows(rows, bibliography),
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(root, needle)

    def test_chair_cannot_downgrade_dangling_reference_to_local_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.convert_bundle_to_dangling_reference(root)
            chair = root / "90-chair-synthesis.md"
            chair.write_text(
                chair.read_text(encoding="utf-8").replace(
                    "| disagree | substantive | C-F01 | open |",
                    "| disagree | local | C-F01 | open |",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "dangling REF0002 requires a substantive cross-ledger conflict",
            )

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
            digest = self.build_bundle(root)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            _, bib_rows = read_csv(root / "03-bibliography-audit-ledger.csv")
            bib_row = next(row for row in bib_rows if row["Field"] == "type")
            bib_row["Verdict"] = "unverifiable"
            bib_row["CanonicalValue"] = "not established"
            bib_row["EvidenceEndpoint"] = ""
            bib_row["EndpointType"] = "official route inaccessible"
            bib_row["EvidenceNote"] = (
                "Attempted the official publisher route on 2026-08-29; "
                "the record was inaccessible."
            )
            write_csv(
                root / "03-bibliography-audit-ledger.csv",
                BIB_LEDGER_COLUMNS,
                bib_rows,
            )
            _, bibliography_inventory_rows = read_csv(
                root / "00-bibliography-inventory.csv"
            )
            (root / "03-bibliography-audit-ledger.md").write_text(
                "# Bibliography ledger\n\n"
                + self.declaration(digest, process, "R3", [BIB_ENDPOINT])
                + markdown_table(
                    BIB_MARKDOWN_HEADERS,
                    bibliography_markdown_rows(
                        bibliography_inventory_rows, bib_rows
                    ),
                ),
                encoding="utf-8",
            )
            _, citation_rows = read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            citation_rows[0]["ContentSourceOpened"] = ""
            citation_rows[0]["ExactSourceLocator"] = ""
            citation_rows[0]["Support"] = "unverifiable"
            citation_rows[0]["MetadataStatus"] = "unverifiable"
            citation_rows[0]["DispositionEvidence"] = (
                "reasoned non-finding: Official full-text route was attempted "
                "but remained inaccessible; the uncertainty is disclosed."
            )
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                citation_rows,
            )
            (root / "04-citation-claim-audit-ledger.md").write_text(
                "# Citation ledger\n\n"
                + self.declaration(digest, process, "R3")
                + markdown_table(
                    CITATION_MARKDOWN_HEADERS,
                    citation_markdown_rows(
                        citation_rows, bibliography_inventory_rows
                    ),
                ),
                encoding="utf-8",
            )
            reviewer = root / "R3-comprehensive-review.md"
            reviewer_text = reviewer.read_text(encoding="utf-8")
            reviewer_text = reviewer_text.replace(
                "- Semantically verified pairs: 1", "- Semantically verified pairs: 0"
            ).replace(
                "- Inaccessible/unverifiable pairs: 0",
                "- Inaccessible/unverifiable pairs: 1",
            ).replace(
                f"public_endpoints=[{BIB_ENDPOINT}; {CITATION_ENDPOINT}]",
                f"public_endpoints=[{BIB_ENDPOINT}]",
            )
            reviewer.write_text(reviewer_text, encoding="utf-8")
            chair = root / "90-chair-synthesis.md"
            chair_text = chair.read_text(encoding="utf-8").replace(
                "C0001-S01=>doi:fixture @ https://dl.acm.org/doi/pdf/10.1145/3442188.3445922",
                "C0001-S01=>doi:fixture @ N/A",
            ).replace(
                "| agree | none | none | closed |",
                "| not verifiable | none | none | closed |",
            ).replace(
                "- Identity-agreement count: 1", "- Identity-agreement count: 0"
            )
            chair.write_text(chair_text, encoding="utf-8")
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
            rows[0]["ChairFindingID"] = "C-F99"
            rows[0]["Severity"] = "S0"
            rows[0]["Remedy"] = "N"
            rows[0]["ExactPDFAnchor"] = "p.999"
            rows[0]["Status"] = "closed"
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
                "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W |",
                "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S3 | N/A | W |",
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
            rows[0]["Status"] = "closed"
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
                path.read_text(encoding="utf-8").replace(
                    ACTOR_PROMPT_HASHES["R1"], "short"
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "Operational prompt SHA-256")

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

    def test_manifest_must_bind_process_hash_and_complete_neutral_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "00-manifest.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "- Process-parameter file and SHA-256: 00-process-parameters.json / ",
                "- Process-parameter file and SHA-256: 00-process-parameters.json / "
                + "F" * 64
                + " # ",
                1,
            ).replace(
                "## Thesis structure\n\nThe fixture contains authored thesis matter on physical p.1 and a rendered bibliography on physical p.2.\n\n",
                "",
                1,
            )
            path.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Process-parameter file and SHA-256", result.stdout)
            self.assertIn("canonical manifest sequence", result.stdout)

    def test_round_rejects_a_second_reviewer_visible_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "old-submission.pdf").write_bytes(
                (root / "frozen-thesis.pdf").read_bytes()
            )
            self.assert_fails(root, "exactly the one process-selected reviewer-visible thesis PDF")

    def test_degree_level_casing_cannot_bypass_owner_routing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["degree_level"] = "Masters"
            process_path.write_text(json.dumps(process), encoding="utf-8")
            report = root / "R3-comprehensive-review.md"
            text = re.sub(
                r"(?ms)^## Full rendered-page audit\n.*\Z", "", report.read_text(encoding="utf-8")
            )
            report.write_text(text, encoding="utf-8")
            self.assert_fails(root, "degree_level must be doctorate or masters")

    def test_owner_summary_counts_must_equal_machine_readable_masters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R3-comprehensive-review.md"
            text = report.read_text(encoding="utf-8").replace(
                "- Physical pages / unchecked pages: 2 / 0",
                "- Physical pages / unchecked pages: 999 / 777",
                1,
            ).replace(
                "- Bibliography entries rendered in the frozen PDF: 1",
                "- Bibliography entries rendered in the frozen PDF: 999",
                1,
            ).replace(
                "- Active citation occurrences: 1",
                "- Active citation occurrences: 999",
                1,
            )
            report.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Physical pages / unchecked pages", result.stdout)
            self.assertIn("Bibliography entries rendered", result.stdout)
            self.assertIn("Active citation occurrences", result.stdout)

    def test_gate_i_nonlayout_finding_does_not_inflate_layout_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R3-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Primary gate: H",
                    "- Primary gate: I",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_page_layout_finding_dispositions_are_deduplicated_and_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            csv_path = root / "02-page-layout-ledger.csv"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    ",clean,", ",finding R3-F01,"
                ),
                encoding="utf-8",
            )
            markdown_path = root / "02-page-layout-ledger.md"
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(
                    "| clean |", "| finding R3-F01 |"
                ),
                encoding="utf-8",
            )
            report = root / "R3-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Actionable layout findings: 0",
                    "- Actionable layout findings: 1",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_page_layout_disposition_rejects_unknown_finding_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            csv_path = root / "02-page-layout-ledger.csv"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    ",clean,", ",finding R3-F99,", 1
                ),
                encoding="utf-8",
            )
            markdown_path = root / "02-page-layout-ledger.md"
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(
                    "| clean |", "| finding R3-F99 |", 1
                ),
                encoding="utf-8",
            )
            report = root / "R3-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Actionable layout findings: 0",
                    "- Actionable layout findings: 1",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "page-ledger layout dispositions reference unknown "
                "current-review finding IDs ['R3-F99']",
            )

    def test_page_layout_disposition_uses_closed_final_grammar(self) -> None:
        for invalid in ("no finding R3-F01", "recheck after edit"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                csv_path = root / "02-page-layout-ledger.csv"
                csv_path.write_text(
                    csv_path.read_text(encoding="utf-8").replace(
                        ",clean,", f",{invalid},", 1
                    ),
                    encoding="utf-8",
                )
                markdown_path = root / "02-page-layout-ledger.md"
                markdown_path.write_text(
                    markdown_path.read_text(encoding="utf-8").replace(
                        "| clean |", f"| {invalid} |", 1
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "Disposition must be exactly clean, intentional, or finding "
                    "R3-Fxx; recheck after edit is not a valid final disposition",
                )

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

    def test_panel_rejects_an_identical_omnibus_persona_for_two_reviewers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            omnibus = (
                "technical method experiment contribution novelty positioning "
                "thesis logic narrative architecture across the complete thesis"
            )
            for index, old in (
                (1, "technical method and experiment reasoning across the complete thesis"),
                (2, "contribution, thesis logic, and cross-chapter narrative coherence"),
            ):
                path = root / f"R{index}-comprehensive-review.md"
                path.write_text(
                    path.read_text(encoding="utf-8").replace(old, omnibus),
                    encoding="utf-8",
                )
                chair = root / "90-chair-synthesis.md"
                chair.write_text(
                    chair.read_text(encoding="utf-8").replace(old, omnibus),
                    encoding="utf-8",
                )
                summary = root / "93-user-facing-summary.md"
                summary.write_text(
                    summary.read_text(encoding="utf-8").replace(old, omnibus),
                    encoding="utf-8",
                )
            self.assert_fails(root, "role-specific and distinct across the panel")

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

    def test_summary_allowlist_rejects_duplicates_and_reordering(self) -> None:
        for mutation in ("duplicate", "reorder"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                path = root / "93-user-facing-summary.md"
                text = path.read_text(encoding="utf-8")
                if mutation == "duplicate":
                    text = text.replace(
                        "00-process-parameters.json; SKILL.md",
                        "00-process-parameters.json; 00-process-parameters.json; SKILL.md",
                        1,
                    )
                else:
                    text = text.replace(
                        "00-process-parameters.json; SKILL.md",
                        "SKILL.md; 00-process-parameters.json",
                        1,
                    )
                path.write_text(text, encoding="utf-8")
                self.assert_fails(root, "canonical order with each basename exactly once")

    def test_summary_receipt_cannot_open_an_unlisted_or_prior_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            text = path.read_text(encoding="utf-8").replace(
                "opened=[00-process-parameters.json;",
                "opened=[old-review.md; 00-process-parameters.json;",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "Summary opened receipt must exactly equal")

    def test_chair_receipt_and_allowlist_are_current_round_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "90-chair-synthesis.md"
            text = path.read_text(encoding="utf-8").replace(
                "05-ai-style-assessment.md]",
                "05-ai-style-assessment.md; old-chair-summary.md]",
                1,
            ).replace(
                "public_endpoints=[none]",
                "public_endpoints=[https://example.com/private-repository]",
                1,
            )
            path.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Chair opened receipt must exactly equal", result.stdout)
            self.assertIn("Chair public_endpoints must be", result.stdout)

    def test_summary_rejects_extra_prose_and_extra_h2_sections(self) -> None:
        for insertion in (
            "\nA private repository and prior round prove the implementation.\n",
            "\n## Prior-round repository proof\n\nA private repository proves it.\n",
        ):
            with self.subTest(insertion=insertion[:20]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                path = root / "93-user-facing-summary.md"
                path.write_text(
                    path.read_text(encoding="utf-8") + insertion,
                    encoding="utf-8",
                )
                result = self.run_validator(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    "canonical Stage-S section sequence" in result.stdout
                    or "prose outside the canonical Stage-S sections" in result.stdout
                    or "Reconciliation must contain only" in result.stdout,
                    result.stdout,
                )

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

    def test_out_of_section_duplicate_labels_cannot_redirect_actor_projection(self) -> None:
        cases = (
            (
                "R1-comprehensive-review.md",
                "# R1 — Comprehensive whole-thesis review\n\n",
                "# R1 — Comprehensive whole-thesis review\n\n"
                "- Persona emphasis: prior-round author explanation\n\n",
                "technical method and experiment reasoning across the complete thesis",
                "prior-round author explanation",
                "R1 conclusion does not exactly copy",
            ),
            (
                "R2-comprehensive-review.md",
                "# R2 — Comprehensive whole-thesis review\n\n",
                "# R2 — Comprehensive whole-thesis review\n\n"
                "- One-paragraph whole-thesis rationale: author-side repository fact\n\n",
                "| R2 | R2 contribution/positioning + thesis architecture/narrative — contribution, thesis logic, and cross-chapter narrative coherence | B | 小修后可答辩 | skill-default | high | The complete fixture thesis was assessed across policy, argument, literature, methods, data, experiments, reproducibility, writing, and presentation; the visible evidence supports a minor-revision recommendation without a blocker. |",
                "| R2 | R2 contribution/positioning + thesis architecture/narrative — contribution, thesis logic, and cross-chapter narrative coherence | B | 小修后可答辩 | skill-default | high | author-side repository fact |",
                "R2 conclusion does not exactly copy",
            ),
            (
                "05-ai-style-assessment.md",
                "# Standalone AI-style prose assessment\n\n",
                "# Standalone AI-style prose assessment\n\n"
                "- Rationale: repository and private-log facts\n\n",
                "The short fixture contains one formulaic transition, but the "
                "limited corpus prevents any stronger stylistic inference.",
                "repository and private-log facts",
                "AI conclusion does not exactly copy",
            ),
            (
                "90-chair-synthesis.md",
                "# Chair synthesis\n\n",
                "# Chair synthesis\n\n"
                "- Whole-thesis rationale: unrelated prior-round adjudication\n\n",
                "The current panel evidence covers all nine gates and the assigned "
                "citation, bibliography, page, and style duties; one bounded wording "
                "revision remains, while no foundational or integrity blocker is visible.",
                "unrelated prior-round adjudication",
                "Chair conclusion does not exactly copy",
            ),
        )
        for source_name, anchor, inserted, old_summary, fake_summary, needle in cases:
            with self.subTest(source=source_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                source = root / source_name
                source.write_text(
                    source.read_text(encoding="utf-8").replace(anchor, inserted, 1),
                    encoding="utf-8",
                )
                summary = root / "93-user-facing-summary.md"
                summary.write_text(
                    summary.read_text(encoding="utf-8").replace(
                        old_summary, fake_summary, 1
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(root, needle)

    def test_duplicate_authoritative_label_or_section_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R2-comprehensive-review.md"
            text = report.read_text(encoding="utf-8").replace(
                "- One-paragraph whole-thesis rationale: The complete fixture thesis",
                "- One-paragraph whole-thesis rationale: duplicate injected rationale\n"
                "- One-paragraph whole-thesis rationale: The complete fixture thesis",
                1,
            )
            report.write_text(text, encoding="utf-8")
            self.assert_fails(root, "whole-thesis rationale is absent or shell-only")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            ai = root / "05-ai-style-assessment.md"
            text = ai.read_text(encoding="utf-8")
            text += (
                "\n## Overall judgment\n"
                "- AI-style signal: low\n"
                "- Confidence: high\n"
                "- Rationale: duplicate authoritative section must fail validation.\n"
            )
            ai.write_text(text, encoding="utf-8")
            self.assert_fails(root, "missing allowed AI-style signal")

    def test_r4_r5_persona_projection_is_bound_to_authoritative_section(self) -> None:
        for actor, authentic in (
            ("R4", "evidence integrity, reproducibility, and citation support"),
            ("R5", "format, bibliography, layout, and page presentation"),
        ):
            with self.subTest(actor=actor):
                text = (
                    f"# {actor} — report\n\n"
                    "- Persona emphasis: prior-round repository explanation\n\n"
                    "## Role, scope, and independence\n"
                    f"- Persona emphasis: {authentic}\n\n"
                    "## Verdict\n- Academic grade: B\n"
                )
                section = VALIDATOR_MODULE.markdown_section_body_raw(
                    text, "Role, scope, and independence"
                )
                self.assertIsNotNone(section)
                self.assertEqual(
                    VALIDATOR_MODULE.labeled_value(section or "", "Persona emphasis"),
                    authentic,
                )

    def test_duplicate_verdict_values_cannot_collapse_to_blank_projection(self) -> None:
        mutations = (
            ("Academic grade", "C", "| R1 | technical method and experiment reasoning across the complete thesis | B |", "| R1 | technical method and experiment reasoning across the complete thesis |  |"),
            ("Defense recommendation", "同意答辩", "| B | 小修后可答辩 | high |", "| B |  | high |"),
        )
        for label, contradictory, chair_old, chair_new in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R1-comprehensive-review.md"
                text = report.read_text(encoding="utf-8")
                anchor = f"- {label}: "
                line = next(line for line in text.splitlines() if line.startswith(anchor))
                text = text.replace(line, line + f"\n- {label}: {contradictory}", 1)
                report.write_text(text, encoding="utf-8")
                chair = root / "90-chair-synthesis.md"
                chair.write_text(
                    chair.read_text(encoding="utf-8").replace(chair_old, chair_new, 1),
                    encoding="utf-8",
                )
                summary = root / "93-user-facing-summary.md"
                summary_text = summary.read_text(encoding="utf-8")
                if label == "Academic grade":
                    summary_text = summary_text.replace(
                        "| R1 | technical method and experiment reasoning across the complete thesis | B |",
                        "| R1 | technical method and experiment reasoning across the complete thesis |  |",
                        1,
                    )
                else:
                    summary_text = summary_text.replace(
                        "| R1 | technical method and experiment reasoning across the complete thesis | B | 小修后可答辩 |",
                        "| R1 | technical method and experiment reasoning across the complete thesis | B |  |",
                        1,
                    )
                summary.write_text(summary_text, encoding="utf-8")
                self.assert_fails(root, "ambiguous or incomplete")

    def test_duplicate_chair_overall_verdict_cannot_project_blank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            chair = root / "90-chair-synthesis.md"
            text = chair.read_text(encoding="utf-8").replace(
                "- Overall academic grade: B",
                "- Overall academic grade: B\n- Overall academic grade: C",
                1,
            )
            chair.write_text(text, encoding="utf-8")
            summary = root / "93-user-facing-summary.md"
            summary.write_text(
                summary.read_text(encoding="utf-8").replace(
                    "| Chair | chair adjudication | B |",
                    "| Chair | chair adjudication |  |",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "Chair source verdict is ambiguous or incomplete")

    def test_required_sections_are_unique_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8")
                + "\n## What I inspected\n\ncontradictory duplicate section\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "must occur exactly once")

    def test_required_report_sections_cannot_be_shells(self) -> None:
        mutations = (
            (
                "R1-comprehensive-review.md",
                "All frozen pages and all required ledgers.",
                "none",
                "section 'What I inspected' is empty or shell-only",
            ),
            (
                "R2-comprehensive-review.md",
                "- Cross-chapter coherence: The two-page fixture has a consistent beginning-to-end narrative for validation.\n",
                "",
                "Whole-thesis synthesis field 'Cross-chapter coherence'",
            ),
            (
                "05-ai-style-assessment.md",
                "- Physical pages inspected: 2 / 2\n",
                "",
                "Physical pages inspected must exactly equal",
            ),
            (
                "90-chair-synthesis.md",
                "- Category distribution: B=3\n",
                "",
                "Category distribution must equal",
            ),
        )
        for filename, old, new, needle in mutations:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                self.assert_fails(root, needle)

    def test_raw_html_blocks_are_forbidden_and_atx_closing_hashes_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8") + "\n<div>hidden injection</div>\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "raw HTML block")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "## Verdict\n", "  ## Verdict ##\n", 1
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            chair = root / "90-chair-synthesis.md"
            chair.write_text(
                chair.read_text(encoding="utf-8")
                + "\n## Standalone AI-style judgment\n- Signal: high\n- Confidence: low\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "must occur exactly once")

    def test_h1_and_nonrendered_blocks_cannot_supply_verdict_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            text = report.read_text(encoding="utf-8")
            text = text.replace("- Confidence: high\n", "", 1)
            text = text.replace(
                "## What I inspected",
                "# Unrelated top-level appendix\n- Confidence: high\n\n## What I inspected",
                1,
            )
            report.write_text(text, encoding="utf-8")
            self.assert_fails(root, "Confidence must be high, medium, or low")

        for wrapper, suffix in (("```markdown\n", "```\n"), ("<!--\n", "")):
            with self.subTest(wrapper=wrapper), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R1-comprehensive-review.md"
                text = report.read_text(encoding="utf-8")
                match = re.search(
                    r"(?ms)^## Verdict\n.*?(?=^## What I inspected)", text
                )
                self.assertIsNotNone(match)
                hidden = wrapper + (match.group(0) if match else "") + suffix
                report.write_text(
                    text[:match.start()] + hidden + text[match.end():],
                    encoding="utf-8",
                )
                self.assert_fails(root, "required section 'Verdict' must occur exactly once")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            text = report.read_text(encoding="utf-8").replace(
                "- Academic grade: B", "    - Academic grade: B", 1
            )
            report.write_text(text, encoding="utf-8")
            self.assert_fails(root, "missing explicit academic grade")

    def test_summary_actor_table_must_belong_to_conclusion_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            summary = root / "93-user-facing-summary.md"
            text = summary.read_text(encoding="utf-8")
            match = re.search(
                r"(?ms)(\| Actor \|.*?)(?=\n## Current actionable items)", text
            )
            self.assertIsNotNone(match)
            table = match.group(1) if match else ""
            text = text[:match.start()] + "No table here.\n" + text[match.end():]
            text += "\n## Appendix projection\n\n" + table + "\n"
            summary.write_text(text, encoding="utf-8")
            self.assert_fails(root, "first header is 'Actor', found 0")

    def test_chair_tables_reject_duplicate_actor_rows(self) -> None:
        for row_prefix, needle in (
            ("| R1 | adequate |", "duplicate reviewer-coverage actors"),
            (
                "| R1 | R1 technical/methods/experiments — technical method and experiment reasoning",
                "duplicate independent-verdict actors",
            ),
        ):
            with self.subTest(prefix=row_prefix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                chair = root / "90-chair-synthesis.md"
                text = chair.read_text(encoding="utf-8")
                line = next(line for line in text.splitlines() if line.startswith(row_prefix))
                text = text.replace(line, line + "\n" + line, 1)
                chair.write_text(text, encoding="utf-8")
                self.assert_fails(root, needle)

    def test_institutional_regime_projects_official_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            rule_endpoint = "https://example.edu/official-rule"
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["decision_regime_status"] = "verified-institutional"
            process["governing_rule_urls"] = [rule_endpoint]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            manifest = root / "00-manifest.md"
            manifest_text = manifest.read_text(encoding="utf-8")
            new_process_hash = hashlib.sha256(
                process_path.read_bytes()
            ).hexdigest().upper()
            manifest_text = re.sub(
                r"(?m)^- Process-parameter file and SHA-256: .*$",
                "- Process-parameter file and SHA-256: "
                f"00-process-parameters.json / {new_process_hash}",
                manifest_text,
            ).replace(
                "decision_regime_status=skill-default ; sources=none",
                "decision_regime_status=verified-institutional ; "
                "sources=https://example.edu/official-rule",
            ).replace(
                "public_endpoints=[none]",
                f"public_endpoints=[{rule_endpoint}]",
                1,
            )
            manifest.write_text(manifest_text, encoding="utf-8")
            policy = root / "01-policy-basis.md"
            policy.write_text(
                policy.read_text(encoding="utf-8").replace(
                    "public_endpoints=[none]",
                    f"public_endpoints=[{rule_endpoint}]",
                    1,
                ),
                encoding="utf-8",
            )
            for index in range(1, 4):
                path = root / f"R{index}-comprehensive-review.md"
                text = path.read_text(encoding="utf-8")
                if index == 3:
                    text = text.replace(
                        f"public_endpoints=[{BIB_ENDPOINT}; {CITATION_ENDPOINT}]",
                        f"public_endpoints=[{rule_endpoint}; {BIB_ENDPOINT}; {CITATION_ENDPOINT}]",
                        1,
                    )
                else:
                    text = text.replace(
                        "public_endpoints=[none]",
                        f"public_endpoints=[{rule_endpoint}]",
                        1,
                    )
                replacements = {
                    "- Decision regime: skill-default": "- Decision regime: institutional",
                    "- Official category: N/A": "- Official category: Institutional-B",
                    "- Official defense recommendation: N/A": "- Official defense recommendation: 允许答辩前小修",
                    "- Governing source: N/A": "- Governing source: https://example.edu/official-rule",
                    "- Academic grade: B": "- Academic grade: N/A",
                    "- Defense recommendation: 小修后可答辩": "- Defense recommendation: N/A",
                }
                for old, new in replacements.items():
                    text = text.replace(old, new, 1)
                path.write_text(text, encoding="utf-8")
            chair = root / "90-chair-synthesis.md"
            chair_text = chair.read_text(encoding="utf-8").replace(
                "public_endpoints=[none]",
                f"public_endpoints=[{rule_endpoint}]",
                1,
            )
            chair_replacements = {
                "- Decision regime: skill-default": "- Decision regime: institutional",
                "- Overall official category: N/A": "- Overall official category: Institutional-B",
                "- Overall official defense recommendation: N/A": "- Overall official defense recommendation: 允许答辩前小修",
                "- Overall governing source: N/A": "- Overall governing source: https://example.edu/official-rule",
                "- Overall academic grade: B": "- Overall academic grade: N/A",
                "- Overall defense recommendation: 小修后可答辩": "- Overall defense recommendation: N/A",
                "| B | 小修后可答辩 | skill-default |": "| Institutional-B | 允许答辩前小修 | institutional / https://example.edu/official-rule |",
                "- Category distribution: B=3": "- Category distribution: Institutional-B=3",
            }
            for old, new in chair_replacements.items():
                chair_text = chair_text.replace(old, new)
            chair.write_text(chair_text, encoding="utf-8")
            for filename in (
                "91-revision-ledger.md",
                "92-new-evidence-or-experiments.md",
            ):
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "public_endpoints=[none]",
                        f"public_endpoints=[{rule_endpoint}]",
                        1,
                    ),
                    encoding="utf-8",
                )
            summary = root / "93-user-facing-summary.md"
            summary_text = summary.read_text(encoding="utf-8").replace(
                "| B | 小修后可答辩 | skill-default | high |",
                "| Institutional-B | 允许答辩前小修 | institutional / https://example.edu/official-rule | high |",
            )
            summary.write_text(summary_text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            r1 = root / "R1-comprehensive-review.md"
            r1_text = r1.read_text(encoding="utf-8")
            r1.write_text(
                r1_text.replace(
                    "- Governing source: https://example.edu/official-rule",
                    "- Governing source: https://invented.example/not-in-envelope",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "absent from the frozen process envelope")
            r1.write_text(r1_text, encoding="utf-8")
            summary.write_text(
                summary.read_text(encoding="utf-8").replace(
                    "| R1 | R1 technical/methods/experiments — technical method and experiment reasoning across the complete thesis | Institutional-B |",
                    "| R1 | R1 technical/methods/experiments — technical method and experiment reasoning across the complete thesis | N/A |",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "R1 conclusion does not exactly copy")

    def test_finding_schema_and_source_ids_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Required action: Correct only the bounded wording without changing the claim.\n",
                    "",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "missing or duplicated field 'Required action'")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["SourceReviewerFindingIDs"] = "R1-F99"
            write_csv(root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows)
            self.assert_fails(root, "unknown current reviewer finding IDs")

    def test_every_actionable_reviewer_finding_requires_one_chair_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            text = report.read_text(encoding="utf-8")
            match = re.search(
                r"(?ms)(### R1-F01 —.*?)(?=^## Questions, not findings)", text
            )
            self.assertIsNotNone(match)
            duplicate = (match.group(1) if match else "").replace(
                "R1-F01", "R1-F02", 1
            ).replace(
                "bounded fixture wording issue", "second bounded fixture issue", 1
            )
            text = text[:match.end()] + "\n" + duplicate + text[match.end():]
            report.write_text(text, encoding="utf-8")
            self.assert_fails(
                root, "current reviewer findings omitted from Chair adjudication"
            )

    def test_chair_finding_ids_are_unique_and_evidence_status_is_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _headers, rows = read_csv(root / "91-revision-ledger.csv")
            duplicate = dict(rows[0])
            duplicate["LedgerID"] = "L02"
            duplicate["Status"] = "closed"
            rows.append(duplicate)
            write_csv(
                root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows
            )
            self.assert_fails(root, "ChairFindingID values must be unique")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _headers, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["EvidenceStatus"] = ""
            write_csv(
                root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows
            )
            self.assert_fails(root, "blank mandatory field EvidenceStatus")

    def test_disputed_findings_require_explicit_chair_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _headers, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["EvidenceStatus"] = "disputed"
            write_csv(
                root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows
            )
            for filename in ("91-revision-ledger.md", "90-chair-synthesis.md"):
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "| verified |", "| disputed |", 1
                    ),
                    encoding="utf-8",
                )
            self.assert_fails(root, "disagreements table omits chair dispositions ['C-F01']")

    def test_rejected_is_not_a_valid_revision_ledger_evidence_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _headers, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["EvidenceStatus"] = "rejected"
            write_csv(
                root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows
            )
            self.assert_fails(root, "invalid EvidenceStatus 'rejected'")

    def test_out_of_scope_reviewer_finding_is_rejected_without_action_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.add_external_artifact_finding_and_chair_decision(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "| D01 | R1-F02 | external author-side artifact demand |",
                (root / "90-chair-synthesis.md").read_text(encoding="utf-8"),
            )
            for filename in (
                "91-revision-ledger.csv",
                "91-revision-ledger.md",
                "92-new-evidence-or-experiments.csv",
                "92-new-evidence-or-experiments.md",
                "93-current-actionable-items.csv",
                "93-user-facing-summary.md",
            ):
                self.assertNotIn(
                    "R1-F02", (root / filename).read_text(encoding="utf-8"), filename
                )

    def test_direct_reviewer_finding_rejection_is_a_strict_partition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.add_external_artifact_finding_and_chair_decision(
                root, status="not verifiable"
            )
            self.assert_fails(root, "direct reviewer-finding sources require Status=rejected")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.add_external_artifact_finding_and_chair_decision(root)
            _headers, rows = read_csv(root / "91-revision-ledger.csv")
            rows[0]["SourceReviewerFindingIDs"] = (
                "R1-F01, R1-F02, R2-F01, R3-F01"
            )
            write_csv(
                root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS, rows
            )
            self.assert_fails(
                root,
                "current reviewer findings cannot enter both 91 and a direct "
                "Status=rejected decision",
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
                "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | visible wording defect |",
                "| L01 | P2 | C-F01 | R1-F01, R2-F01, R3-F01 | S2 | N/A | W | physical p.1 | invented different defect |",
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(root, "Markdown/CSV value mismatch for L01/DirectObservation")

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

    def test_reviewer_assessment_requires_exact_six_column_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R2-comprehensive-review.md"
            text = path.read_text(encoding="utf-8").replace(
                "| Gate | Review depth (`baseline` / `emphasized` / `primary`) | Disposition (`adequate` / `concern` / `unverifiable` / `N/A`) | Decisive evidence and exact locations | Related finding IDs or `none` | Confidence/limitation |",
                "| Gate | Review depth | Disposition | Evidence | Findings | Confidence |",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "expected exactly one Markdown table with schema "
                "['Gate', 'Review depth (`baseline` / `emphasized` / `primary`)', "
                "'Disposition (`adequate` / `concern` / `unverifiable` / `N/A`)', "
                "'Decisive evidence and exact locations', "
                "'Related finding IDs or `none`', 'Confidence/limitation']",
            )

    def test_reviewer_assessment_rejects_a_second_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R2-comprehensive-review.md"
            text = path.read_text(encoding="utf-8").replace(
                "\n\n## Persona-weighted deep review",
                "\n\n| Extra | Table |\n|---|---|\n| x | y |"
                "\n\n## Persona-weighted deep review",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "Whole-thesis assessment must contain exactly one complete "
                "Markdown table, found 2",
            )

    def test_reviewer_assessment_gate_rows_must_be_in_a_to_i_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "R2-comprehensive-review.md"
            lines = path.read_text(encoding="utf-8").splitlines()
            a_row = next(i for i, line in enumerate(lines) if line.startswith("| A —"))
            b_row = next(i for i, line in enumerate(lines) if line.startswith("| B —"))
            lines[a_row], lines[b_row] = lines[b_row], lines[a_row]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assert_fails(
                root,
                "Whole-thesis assessment gate order must be exactly "
                "A,B,C,D,E,F,G,H,I",
            )

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

    def test_ai_disclaimer_must_be_correct_in_its_own_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "05-ai-style-assessment.md"
            canonical = (
                "This is a prose-style assessment, not a determination of AI use, "
                "authorship, plagiarism, or misconduct."
            )
            text = path.read_text(encoding="utf-8").replace(
                f"- Required disclaimer: {canonical}",
                "- Required disclaimer: AI use and misconduct conclusively established",
                1,
            ).replace(
                "## Limitations\n",
                f"## Limitations\n\n{canonical}\n",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "Required disclaimer must exactly equal the canonical "
                "non-attribution disclaimer",
            )

    def test_ai_report_rejects_probability_or_academic_verdict_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "05-ai-style-assessment.md"
            text = path.read_text(encoding="utf-8").replace(
                "## Overall judgment\n",
                "## Overall judgment\n\n- AI probability: 99%\n"
                "- Academic grade: D\n- Misconduct determination: confirmed\n",
                1,
            )
            path.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "standalone AI-style report contains forbidden "
                "academic/detector/misconduct field 'AI probability'",
            )

    def test_ai_report_rejects_probability_label_variants(self) -> None:
        for label in ("AI probability estimate", "AI 概率"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                path = root / "05-ai-style-assessment.md"
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "## Overall judgment\n",
                        f"## Overall judgment\n\n- {label}: 97%\n",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "semantically forbidden probability/detector/academic/"
                    "misconduct label",
                )

    def test_ai_report_rejects_semantic_attribution_label_bypasses(self) -> None:
        forbidden_labels = (
            "AI-generated percentage",
            "AI generation rate",
            "AI content ratio",
            "人工智能生成百分比",
            "AI生成占比",
            "人工智能生成比例",
            "检测器阳性率",
            "Authorship verdict",
            "Authorship conclusion",
            "作者身份结论",
            "AI-use verdict",
            "AI-use conclusion",
            "AI使用结论",
        )
        for label in forbidden_labels:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                path = root / "05-ai-style-assessment.md"
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "## Overall judgment\n",
                        f"## Overall judgment\n\n- {label}: confirmed\n",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "semantically forbidden probability/detector/academic/"
                    "misconduct label",
                )

    def test_ai_required_disclaimer_remains_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_summary_reconciliation_count_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "93-user-facing-summary.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "- Rows in Current actionable items Markdown table: 1",
                    "- Rows in Current actionable items Markdown table: 99",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "93 academic Markdown reconciliation count")

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

    def test_valid_optional_stage_v_passes_after_fresh_rereview_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            (root / "94-post-freeze-prior-issue-closure.md").write_text(
                self.stage_v_report(root, digest), encoding="utf-8"
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_stage_v_is_rejected_before_a_fresh_rereview_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            (root / "94-post-freeze-prior-issue-closure.md").write_text(
                self.stage_v_report(root, digest), encoding="utf-8"
            )
            self.assert_fails(root, "review_mode=fresh-rereview")

    def test_stage_v_receipt_must_cover_every_allowlisted_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(
                self.stage_v_report(root, digest).replace(
                    "; round-previous-prior-issues.csv]; public_endpoints=",
                    "]; public_endpoints=",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "Stage-V opened receipt must exactly equal")

    def test_stage_v_rejects_missing_prior_allowlisted_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(self.stage_v_report(root, digest), encoding="utf-8")
            (root / "stage-v-inputs" / "round-previous-prior-issues.csv").unlink()
            self.assert_fails(root, "missing prior allowlisted artifact")

    def test_stage_v_rejects_prior_allowlisted_artifact_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(self.stage_v_report(root, digest), encoding="utf-8")
            prior_path = (
                root / "stage-v-inputs" / "round-previous-prior-issues.csv"
            )
            prior_path.write_text(
                prior_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "prior allowlisted artifact hash mismatch")

    def test_stage_v_rejects_phantom_prior_finding_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(
                self.stage_v_report(root, digest).replace(
                    "| OLD-F01 | resolved |",
                    "| GHOST-F99 | resolved |",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "phantom prior finding IDs")

    def test_stage_v_rejects_missing_prior_finding_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            report = self.stage_v_report(root, digest)
            prior_path = (
                root / "stage-v-inputs" / "round-previous-prior-issues.csv"
            )
            old_hash = hashlib.sha256(prior_path.read_bytes()).hexdigest().upper()
            _headers, rows = read_csv(prior_path)
            rows.append({
                "PriorFindingID": "OLD-F02",
                "PriorPDFSHA256": "B" * 64,
                "PriorPDFAnchor": "physical p.1",
                "Finding": "a second tracked prior issue",
                "RequiredClosureEvidence": "visible current-PDF closure evidence",
            })
            write_csv(prior_path, PRIOR_ISSUES_COLUMNS, rows)
            new_hash = hashlib.sha256(prior_path.read_bytes()).hexdigest().upper()
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(report.replace(old_hash, new_hash), encoding="utf-8")
            self.assert_fails(root, "missing prior finding IDs")

    def test_stage_v_rejects_false_csv_completion_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(
                self.stage_v_report(root, digest).replace(
                    "open_academic_rows=1",
                    "open_academic_rows=0",
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "contradicts current CSV/report state")

    def test_stage_v_cannot_claim_regression_without_complete_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            path.write_text(
                self.stage_v_report(root, digest).replace(
                    "| not assessed | none |", "| regression visible | none |"
                ),
                encoding="utf-8",
            )
            self.assert_fails(root, "cannot be asserted without the complete prior baseline")

    def test_stage_v_rejects_extra_sections_and_unbound_current_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.enable_fresh_rereview(root)
            path = root / "94-post-freeze-prior-issue-closure.md"
            text = self.stage_v_report(root, digest).replace(
                hashlib.sha256(
                    (root / "R1-comprehensive-review.md").read_bytes()
                ).hexdigest().upper(),
                "B" * 64,
                1,
            )
            text += "\n## Prior repository proof\n\nAn unlisted old repository proves the claim.\n"
            path.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Stage-V section sequence", result.stdout)
            self.assertIn("current frozen artifact identity list", result.stdout)

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
                "prompt_sha256": "B" * 64,
                "fresh_context_declaration": (
                    "no inherited user/thread/task turns beyond system/developer "
                    "instructions and the exact operational prompt"
                ),
                "input_receipt_access_declaration": (
                    "received=[operational prompt]; opened=[frozen-thesis.pdf]; "
                    "no unlisted substantive assertion was received; no prohibited "
                    "context/artifact was used; neighboring paths were not enumerated"
                ),
                "received_blocks": ["operational prompt"],
                "opened_inputs": ["frozen-thesis.pdf"],
                "tool": "fixture",
                "version": "1",
                "command_or_query": "fixture --read-only",
                "pdf_sha256_start": digest,
                "pdf_sha256_end": digest,
                "outputs": [{"file": sidecar.name, "sha256": sidecar_hash}],
                "limitations": [],
                "recipient_stages": ["R3"],
            }
            (helpers / "H01-provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            old_opened = "; ".join(
                VALIDATOR_MODULE.canonical_stage_opened_inputs(process, 3, "R3")
            )
            new_opened = "; ".join(
                VALIDATOR_MODULE.canonical_stage_opened_inputs(
                    process, 3, "R3", root
                )
            )
            for filename in (
                "R3-comprehensive-review.md", "02-page-layout-ledger.md",
                "03-bibliography-audit-ledger.md",
                "04-citation-claim-audit-ledger.md",
            ):
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        f"opened=[{old_opened}]", f"opened=[{new_opened}]", 1
                    ),
                    encoding="utf-8",
                )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_helper_receipt_must_exactly_project_structured_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.install_helper_fixture(
                root,
                digest,
                receipt=(
                    "received=[secret prior review]; opened=[old-review.md]; "
                    "no unlisted substantive assertion was received; no prohibited "
                    "context/artifact was used; neighboring paths were not enumerated"
                ),
            )
            self.assert_fails(
                root,
                "input_receipt_access_declaration must exactly project "
                "received_blocks/opened_inputs",
            )

    def test_helper_recipient_must_record_provenance_and_output_as_opened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            self.install_helper_fixture(root, digest)
            self.assert_fails(
                root,
                "opened receipt must exactly equal the canonical ordered R3 allowlist",
            )

    @unittest.skipUnless(os.name == "nt", "NTFS junction test is Windows-specific")
    def test_page_render_directory_junction_is_rejected_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            self.build_bundle(root)
            render_dir = root / "page-renders"
            external_dir = Path(external) / "render-source"
            external_dir.mkdir()
            for source in list(render_dir.iterdir()):
                source.rename(external_dir / source.name)
            render_dir.rmdir()
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(render_dir), str(external_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest(f"could not create NTFS junction: {created.stderr}")
            try:
                self.assert_fails(
                    root,
                    "closed current-round boundary contains "
                    "symlink/junction/reparse entries: ['page-renders']",
                )
            finally:
                render_dir.rmdir()

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

    def test_write_report_rejects_any_noncanonical_destination_without_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            rogue = root / "rogue.md"
            result = self.run_validator(root, rogue)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "--write-report must target exactly the in-root regular file",
                result.stdout,
            )
            self.assertFalse(rogue.exists())
            clean = self.run_validator(root)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_write_report_rejects_directory_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "95-bundle-validation.md"
            report.mkdir()
            sentinel = report / "sentinel.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            result = self.run_validator(root, report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "an existing destination must be a regular", result.stdout
            )
            self.assertNotIn("Traceback", result.stderr)
            self.assertTrue(report.is_dir())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")

    def test_write_report_rejects_hard_link_without_mutation(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as external,
        ):
            root = Path(directory)
            self.build_bundle(root)
            report = root / "95-bundle-validation.md"
            source = Path(external) / "external-report.md"
            sentinel = b"external sentinel must remain unchanged"
            source.write_bytes(sentinel)
            try:
                os.link(source, report)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"hard links unavailable on this filesystem: {exc}")
            if source.stat().st_nlink < 2:
                self.skipTest("filesystem did not expose a hard-link count")
            result = self.run_validator(root, report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("single-link file (st_nlink == 1)", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(source.read_bytes(), sentinel)
            self.assertEqual(report.read_bytes(), sentinel)

    def test_audit_owner_receipt_must_list_sources_claimed_opened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "03-bibliography-audit-ledger.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    f"public_endpoints=[{BIB_ENDPOINT}]",
                    "public_endpoints=[none]",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "public_endpoints omits authoritative endpoint(s) that this R3 "
                "artifact says were opened",
            )

    def test_bibliography_mismatch_cannot_have_no_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.set_bibliography_mismatch(root, "none")
            self.assert_fails(
                root,
                "mismatch row must link an owning-reviewer R3-Fxx or "
                "R3-Qxx disposition",
            )

    def test_bibliography_mismatch_accepts_real_current_owner_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            self.set_bibliography_mismatch(root, "R3-F01")
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("**PASS**", result.stdout)

    def test_bibliography_mismatch_rejects_link_mixed_with_exemption(self) -> None:
        for exemption in (
            "none", "clean", "no finding", "no-findings", "no issue",
            "no actionable finding", "no action required", "non-finding",
            "N/A", "N.A.", "NA", "not applicable", "not-required",
            "not a finding",
        ):
            with (
                self.subTest(exemption=exemption),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                self.build_bundle(root)
                self.set_bibliography_mismatch(
                    root, f"R3-F01; {exemption}"
                )
                self.assert_fails(
                    root,
                    "mismatch FindingDisposition cannot mix an owning-reviewer "
                    "link with a non-finding exemption phrase",
                )

    def test_bibliography_mismatch_link_must_resolve_to_current_owner_item(
        self,
    ) -> None:
        cases = (
            (
                "wrong current reviewer",
                "R2-F01",
                "mismatch row must link an owning-reviewer R3-Fxx or "
                "R3-Qxx disposition",
            ),
            (
                "unknown owner item",
                "R3-F99",
                "03/04 audit ledgers reference unknown current owning-reviewer "
                "finding/question IDs ['R3-F99']",
            ),
            (
                "owner item plus prose",
                "R3-F01; explanatory prose",
                "the whole cell must be exactly one current owner ID with no "
                "prose or second ID",
            ),
        )
        for label, disposition, error in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                self.set_bibliography_mismatch(root, disposition)
                self.assert_fails(root, error)

        with self.subTest(case="REF token outside ID column"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            path = root / "03-bibliography-audit-ledger.csv"
            headers, rows = read_csv(path)
            rows[0]["EvidenceNote"] += " REF0001"
            write_csv(path, headers, rows)
            self.assert_fails(
                root,
                "REFnnnn tokens are allowed only in the ReferenceID column",
            )

    def test_citation_mismatch_cannot_have_none_as_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = self.build_bundle(root)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            _, citation_rows = read_csv(root / "04-citation-claim-audit-ledger.csv")
            citation_rows[0]["Support"] = "mismatch"
            citation_rows[0]["SeverityFinding"] = "none"
            citation_rows[0]["DispositionEvidence"] = "none"
            write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                CITATION_LEDGER_COLUMNS,
                citation_rows,
            )
            _, inventory = read_csv(root / "00-bibliography-inventory.csv")
            (root / "04-citation-claim-audit-ledger.md").write_text(
                "# Citation ledger\n\n"
                + self.declaration(digest, process, "R3", [CITATION_ENDPOINT])
                + markdown_table(
                    CITATION_MARKDOWN_HEADERS,
                    citation_markdown_rows(citation_rows, inventory),
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "mismatch row must link an owning-reviewer R3-Fxx or "
                "R3-Qxx disposition",
            )

    def test_hardening_missing_92_csv_is_a_required_file_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "92-new-evidence-or-experiments.csv").unlink()
            self.assert_fails(
                root,
                "missing required file: 92-new-evidence-or-experiments.csv",
            )

    def test_hardening_stage_v_prompt_presence_is_bound_to_stage_v_artifact(
        self,
    ) -> None:
        with self.subTest(case="V prompt without 94"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["actor_prompt_sha256"]["V"] = ACTOR_PROMPT_HASHES["V"]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
            manifest = root / "00-manifest.md"
            manifest.write_text(
                re.sub(
                    r"(?m)^- Process-parameter file and SHA-256: .*$",
                    "- Process-parameter file and SHA-256: "
                    f"00-process-parameters.json / {process_digest}",
                    manifest.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("actor_prompt_sha256 actor set mismatch", result.stdout)
            self.assertIn("extra=['V']", result.stdout)

        with self.subTest(case="94 without V prompt"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "94-post-freeze-prior-issue-closure.md").write_text(
                "# Deliberately incomplete Stage V fixture\n",
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("actor_prompt_sha256 actor set mismatch", result.stdout)
            self.assertIn("missing=['V']", result.stdout)

    def test_hardening_chair_disagreement_rejects_phantom_chair_finding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            chair = root / "90-chair-synthesis.md"
            chair.write_text(
                chair.read_text(encoding="utf-8").replace(
                    "|---|---|---|---|---|---|---|\n\n"
                    "## Thesis-level narrative and chapter logic",
                    "|---|---|---|---|---|---|---|\n"
                    "| D01 | C-F99 | phantom concern | one unsupported "
                    "position | current frozen PDF | resolved | no action |\n\n"
                    "## Thesis-level narrative and chapter logic",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "disagreements table contains unknown chair findings ['C-F99']",
            )

    def test_hardening_stage_s_actor_rows_have_canonical_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            summary = root / "93-user-facing-summary.md"
            lines = summary.read_text(encoding="utf-8").splitlines()
            r1_index = next(
                index for index, line in enumerate(lines) if line.startswith("| R1 |")
            )
            r2_index = next(
                index for index, line in enumerate(lines) if line.startswith("| R2 |")
            )
            lines[r1_index], lines[r2_index] = lines[r2_index], lines[r1_index]
            summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assert_fails(
                root,
                "independent-conclusion actor order must exactly be "
                "['R1', 'R2', 'R3', 'AI', 'Chair']",
            )

    def test_hardening_reconciliation_statement_cannot_be_supplied_elsewhere(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            summary = root / "93-user-facing-summary.md"
            canonical = (
                "This summary introduces no new finding and uses no prior-round "
                "or author-side information."
            )
            text = summary.read_text(encoding="utf-8")
            text = text.replace(
                "# Current-round user-facing review summary\n\n",
                "# Current-round user-facing review summary\n\n"
                + canonical
                + "\n\n",
                1,
            ).replace(
                f"- Statement: {canonical}",
                "- Statement: This field is deliberately incorrect.",
                1,
            )
            summary.write_text(text, encoding="utf-8")
            self.assert_fails(
                root,
                "reconciliation Statement must exactly equal the canonical "
                "clean Stage-S non-invention statement",
            )

    def test_hardening_duplicate_governing_local_neutral_file_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            rule = root / "official-rule.txt"
            rule.write_text("synthetic official rule fixture", encoding="utf-8")
            rule_hash = hashlib.sha256(rule.read_bytes()).hexdigest().upper()
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            entry = {
                "neutral_file": rule.name,
                "official_title": "Synthetic official rule",
                "sha256": rule_hash,
            }
            process["governing_local_files"] = [entry, dict(entry)]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
            manifest = root / "00-manifest.md"
            manifest.write_text(
                re.sub(
                    r"(?m)^- Process-parameter file and SHA-256: .*$",
                    "- Process-parameter file and SHA-256: "
                    f"00-process-parameters.json / {process_digest}",
                    manifest.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "duplicate governing_local_files neutral_file 'official-rule.txt'",
            )

    def test_hardening_governing_file_cannot_reuse_reserved_round_basename(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            reserved = root / "R1-comprehensive-review.md"
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["governing_local_files"] = [{
                "neutral_file": reserved.name,
                "official_title": "Synthetic colliding rule",
                "sha256": hashlib.sha256(reserved.read_bytes()).hexdigest().upper(),
            }]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            self.assert_fails(
                root,
                "governing_local_files[0].neutral_file "
                "'R1-comprehensive-review.md' collides with a reserved "
                "skill/round basename",
            )

    def test_hardening_frozen_pdf_cannot_reuse_governing_file_basename(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            frozen_name = process["frozen_pdf_file"]
            frozen_hash = hashlib.sha256((root / frozen_name).read_bytes()).hexdigest().upper()
            process["governing_local_files"] = [{
                "neutral_file": frozen_name,
                "official_title": "Synthetic colliding rule",
                "sha256": frozen_hash,
            }]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            self.assert_fails(
                root,
                f"frozen_pdf_file {frozen_name!r} collides with a governing local file",
            )

    def test_hardening_reserved_names_use_portable_casefolded_comparison(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            alias = root / "r1-comprehensive-review.md"
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["governing_local_files"] = [{
                "neutral_file": alias.name,
                "official_title": "Synthetic case-alias rule",
                "sha256": hashlib.sha256(alias.read_bytes()).hexdigest().upper(),
            }]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            self.assert_fails(
                root,
                "'r1-comprehensive-review.md' collides with a reserved "
                "skill/round basename",
            )

    def test_hardening_governing_names_reject_win32_aliases_and_render_names(
        self,
    ) -> None:
        for name, expected in (
            (
                "official-rule.txt.",
                "must be a neutral portable basename without filesystem aliases",
            ),
            (
                "P0001.png",
                "'P0001.png' collides with a reserved skill/round basename",
            ),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                rule = root / name.rstrip(" .")
                if not rule.exists():
                    rule.write_text("synthetic rule", encoding="utf-8")
                process_path = root / "00-process-parameters.json"
                process = json.loads(process_path.read_text(encoding="utf-8"))
                process["governing_local_files"] = [{
                    "neutral_file": name,
                    "official_title": "Synthetic alias rule",
                    "sha256": hashlib.sha256(rule.read_bytes()).hexdigest().upper(),
                }]
                process_path.write_text(json.dumps(process), encoding="utf-8")
                self.assert_fails(root, expected)

    def test_hardening_governing_duplicate_detection_is_case_insensitive(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            rule = root / "official-rule.txt"
            rule.write_text("synthetic official rule fixture", encoding="utf-8")
            rule_hash = hashlib.sha256(rule.read_bytes()).hexdigest().upper()
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["governing_local_files"] = [
                {
                    "neutral_file": "official-rule.txt",
                    "official_title": "Synthetic official rule one",
                    "sha256": rule_hash,
                },
                {
                    "neutral_file": "OFFICIAL-RULE.TXT",
                    "official_title": "Synthetic official rule two",
                    "sha256": rule_hash,
                },
            ]
            process_path.write_text(json.dumps(process), encoding="utf-8")
            self.assert_fails(
                root,
                "duplicate governing_local_files neutral_file 'OFFICIAL-RULE.TXT'",
            )

    def test_hardening_reviewer_receipt_rejects_extra_prior_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            reviewer = root / "R1-comprehensive-review.md"
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8").replace(
                    "opened=[", "opened=[old-review.md; ", 1
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "opened receipt must exactly equal the canonical ordered R1 allowlist",
            )

    def test_hardening_receipt_rejects_duplicate_structured_keys(self) -> None:
        mutations = (
            (
                "received=[operational prompt]; opened=[",
                "received=[operational prompt]; received=[user rebuttal]; opened=[",
            ),
            (
                "]; public_endpoints=[none]; no unlisted",
                "]; opened=[prior-review.md]; public_endpoints=[none]; no unlisted",
            ),
            (
                "public_endpoints=[none]; no unlisted",
                "public_endpoints=[none]; public_endpoints=[https://invalid.example]; "
                "no unlisted",
            ),
        )
        for old, new in mutations:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                reviewer = root / "R1-comprehensive-review.md"
                reviewer.write_text(
                    reviewer.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "input receipt must use the exact closed grammar with one "
                    "received, one opened, one public_endpoints",
                )

    def test_hardening_public_endpoints_none_is_exclusive(self) -> None:
        endpoint = "https://example.test"
        cases = (
            ([], set(), set(), []),
            ([endpoint], {endpoint}, {endpoint}, []),
            (
                ["none", endpoint],
                {endpoint},
                {endpoint},
                [
                    "receipt.md: public_endpoints=[none] must not be combined "
                    "with endpoint tokens"
                ],
            ),
        )
        for endpoints, allowed, required, expected_errors in cases:
            with (
                self.subTest(endpoints=endpoints),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                digest = self.build_bundle(root)
                process = json.loads(
                    (root / "00-process-parameters.json").read_text(encoding="utf-8")
                )
                receipt_path = root / "receipt.md"
                receipt_path.write_text(
                    self.declaration(digest, process, "R1", endpoints),
                    encoding="utf-8",
                )
                errors: list[str] = []
                VALIDATOR_MODULE.validate_declarations(
                    receipt_path,
                    digest,
                    errors,
                    process=process,
                    actor_id="R1",
                    reviewer_count=3,
                    allowed_public_endpoints=allowed,
                    required_public_endpoints=required,
                )
                self.assertEqual(errors, expected_errors)

    def test_count_vector_accepts_standard_thousands_separators(self) -> None:
        parse = VALIDATOR_MODULE.parse_count_integer_vector
        self.assertEqual(parse("3,264 / 0"), (3264, 0))
        self.assertEqual(parse("90 / 0 / 74; reference [144]"), (90, 0, 74, 144))
        self.assertEqual(parse("-1 / +2"), (-1, 2))
        for malformed in ("1.0", "1.0 / 0", "1,00 / 0", "1e3 / 0"):
            with self.subTest(malformed=malformed):
                self.assertIsNone(parse(malformed))

    def test_owner_count_vectors_reject_negative_and_hidden_master_counts(self) -> None:
        mutations = (
            (
                "- Metadata/status verified entries: 1",
                "- Metadata/status verified entries: -1",
                "Metadata/status verified entries",
            ),
            (
                "duplicate/missing/extra page IDs: 0 / 0 / 0",
                "hidden 999.0; duplicate/missing/extra page IDs: 0 / 0 / 0",
                "must name 02-page-layout-ledger.csv and report "
                "duplicate/missing/extra counts",
            ),
        )
        for old, new, expected in mutations:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R3-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(old, new, 1),
                    encoding="utf-8",
                )
                self.assert_fails(root, expected)

    def test_fresh_context_declaration_requires_trimmed_exact_canonical_value(
        self,
    ) -> None:
        canonical = (
            "no inherited user/thread/task turns beyond system/developer "
            "instructions and the exact operational prompt"
        )
        with self.subTest(case="surrounding whitespace"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    f"- Fresh-context declaration: {canonical}\n",
                    f"- Fresh-context declaration:   {canonical}   \n",
                    1,
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for replacement in (
            canonical + "; no other context was used",
            canonical + ".",
            "No" + canonical[2:],
        ):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R1-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        f"- Fresh-context declaration: {canonical}",
                        f"- Fresh-context declaration: {replacement}",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "fresh-context declaration must exactly equal the canonical "
                    "no-inherited-context sentence",
                )

    def test_page_owner_source_forcing_cause_requires_exact_literal(self) -> None:
        for replacement in (
            "Not verifiable from the PDF",
            "not verifiable from the PDF; source unavailable",
            "because it is not verifiable from the PDF",
        ):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R3-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        "- Source-forcing cause: not verifiable from the PDF",
                        f"- Source-forcing cause: {replacement}",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "field 'Source-forcing cause' must exactly equal "
                    "'not verifiable from the PDF'",
                )

    def test_actual_audit_owners_cannot_disclaim_separate_duties(self) -> None:
        original = "assigned ledgers listed below or none"
        for denial in (
            "none", "N-A", "NA", "not assigned", "no duty", "no duties", "无",
        ):
            with self.subTest(degree="masters", denial=denial), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R3-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(original, denial, 1),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "assigned audit owner cannot disclaim Separate exhaustive audit duties",
                )

        for reviewer_index in (4, 5):
            with self.subTest(degree="doctorate", reviewer=reviewer_index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                self.convert_bundle_to_doctorate(root)
                report = root / f"R{reviewer_index}-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(original, "none", 1),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "assigned audit owner cannot disclaim Separate exhaustive audit duties",
                )

    def test_nonowner_may_use_exact_none_for_separate_audit_duties(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "assigned ledgers listed below or none", "none", 1
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gate_related_findings_are_closed_and_current_actor_bound(self) -> None:
        gate_a_row = (
            "| A — gate | baseline | adequate | physical p.1, fixture section | "
            "none | high |"
        )
        with self.subTest(case="actual current finding"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    gate_a_row, gate_a_row.replace("| none |", "| R1-F01 |"), 1
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        invalid_values = (
            "R2-F01",
            "R1-F99",
            "R1-Q01",
            "C-F01",
            "AI-F01",
            "R1-F01, R1-F01",
            "none / R1-F01",
            "see current finding R1-F01",
            "None",
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R1-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        gate_a_row,
                        gate_a_row.replace("| none |", f"| {invalid} |"),
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "Related finding IDs must be exact none or a non-duplicated "
                    "list of actual current R1 findings",
                )

    def test_secondary_gates_allow_flexible_sets_but_reject_open_grammar(self) -> None:
        for valid in ("B", "Gate B / I", "i and b", "Gates B，I"):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R1-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        "- Secondary gates: none",
                        f"- Secondary gates: {valid}",
                        1,
                    ),
                    encoding="utf-8",
                )
                result = self.run_validator(root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for invalid in ("J", "B / B", "none / B", "B because related", "None", "A-I"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R1-comprehensive-review.md"
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        "- Secondary gates: none",
                        f"- Secondary gates: {invalid}",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "Secondary gates must be exact none or a non-duplicated set "
                    "drawn only from Gate A--I",
                )

    def test_owned_ledger_declarations_must_precede_canonical_main_table(self) -> None:
        for filename in (
            "02-page-layout-ledger.md",
            "03-bibliography-audit-ledger.md",
            "04-citation-claim-audit-ledger.md",
        ):
            for label in (
                "Actor ID",
                "Review round ID",
                "Review retry ID",
                "Fresh-context declaration",
                "Operational prompt SHA-256",
                "Input-receipt/access declaration",
                "Frozen PDF SHA-256 at start and end",
            ):
                with self.subTest(filename=filename, label=label), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.build_bundle(root)
                    ledger = root / filename
                    text = ledger.read_text(encoding="utf-8")
                    match = re.search(
                        rf"(?m)^- {re.escape(label)}:.*\n",
                        text,
                    )
                    self.assertIsNotNone(match)
                    assert match is not None
                    moved_line = match.group(0)
                    text = text[:match.start()] + text[match.end():]
                    ledger.write_text(
                        text.rstrip() + "\n\n" + moved_line,
                        encoding="utf-8",
                    )
                    self.assert_fails(
                        root,
                        "all required declarations must precede the first canonical "
                        "main table header",
                    )

        for label, rendered_label in (
            (
                "Fresh-context declaration",
                "Reviewer Fresh-context declaration",
            ),
            (
                "Input-receipt/access declaration",
                "Reviewer Input-receipt/access declaration",
            ),
            (
                "Frozen PDF SHA-256 at start and end",
                "Frozen PDF SHA-256 at start and end",
            ),
        ):
            with self.subTest(alternate_recognized_label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                ledger = root / "02-page-layout-ledger.md"
                text = ledger.read_text(encoding="utf-8")
                match = re.search(rf"(?m)^- {re.escape(label)}:.*\n", text)
                self.assertIsNotNone(match)
                assert match is not None
                moved_line = match.group(0).replace(
                    f"- {label}:",
                    (
                        f"- {rendered_label}:"
                        if label != "Frozen PDF SHA-256 at start and end"
                        else f"{rendered_label}:"
                    ),
                    1,
                )
                text = text[:match.start()] + text[match.end():]
                ledger.write_text(
                    text.rstrip() + "\n\n" + moved_line,
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    "all required declarations must precede the first canonical "
                    "main table header",
                )

    def test_reviewer_h2_relative_order_is_enforced_without_full_serialization(
        self,
    ) -> None:
        def move_section_before(text: str, heading: str, before: str) -> str:
            section = re.search(
                rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)", text
            )
            self.assertIsNotNone(section)
            assert section is not None
            body = section.group(0)
            without = text[:section.start()] + text[section.end():]
            insertion = without.index(f"## {before}\n")
            return without[:insertion] + body + without[insertion:]

        with self.subTest(case="assessment after deep review"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R1-comprehensive-review.md"
            text = report.read_text(encoding="utf-8")
            assessment = re.search(
                r"(?ms)^## Whole-thesis assessment\n.*?(?=^## Persona-weighted deep review)",
                text,
            )
            deep_review = re.search(
                r"(?ms)^## Persona-weighted deep review\n.*?(?=^## Strongest contributions)",
                text,
            )
            self.assertIsNotNone(assessment)
            self.assertIsNotNone(deep_review)
            assert assessment is not None and deep_review is not None
            reordered = (
                text[:assessment.start()]
                + deep_review.group(0)
                + assessment.group(0)
                + text[deep_review.end():]
            )
            report.write_text(reordered, encoding="utf-8")
            self.assert_fails(
                root,
                "Whole-thesis assessment must precede Persona-weighted deep review",
            )

        for heading in (
            "Full rendered-page audit",
            "Full bibliography-integrity audit",
            "Full citation-claim audit",
        ):
            with self.subTest(case="owner before base end", heading=heading), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_bundle(root)
                report = root / "R3-comprehensive-review.md"
                report.write_text(
                    move_section_before(
                        report.read_text(encoding="utf-8"),
                        heading,
                        "Coverage and limitations",
                    ),
                    encoding="utf-8",
                )
                self.assert_fails(
                    root,
                    f"conditional owner section '{heading}' must follow the final "
                    "required base section 'Coverage and limitations'",
                )

        with self.subTest(case="extra H2 and reordered owner H2s remain allowed"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            report = root / "R3-comprehensive-review.md"
            text = report.read_text(encoding="utf-8").replace(
                "## Coverage and limitations",
                "## Supplemental reviewer note\n\nA bounded supplemental note.\n\n"
                "## Coverage and limitations",
                1,
            )
            text = move_section_before(
                text, "Full citation-claim audit", "Full rendered-page audit"
            )
            report.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_hardening_closed_round_root_rejects_old_review_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            (root / "old-review.md").write_text(
                "# Prohibited prior-round review\n",
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "closed current-round root contains unallowlisted file(s): "
                "['old-review.md']",
            )

    def test_hardening_reviewer_retry_id_is_process_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            reviewer = root / "R1-comprehensive-review.md"
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8").replace(
                    "- Review retry ID: r1",
                    "- Review retry ID: r9",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "Review retry ID does not equal the process envelope",
            )

    def test_hardening_indented_setext_heading_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            reviewer = root / "R1-comprehensive-review.md"
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8").replace(
                    "## Role, scope, and independence",
                    "  Disguised heading\n  -----------------\n\n"
                    "## Role, scope, and independence",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "Setext headings are not allowed in the validated Markdown dialect",
            )

    def test_hardening_reviewer_question_requires_chair_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            reviewer = root / "R1-comprehensive-review.md"
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8").replace(
                    "|---|---|---|---|---|\n\n"
                    "## Coverage and limitations",
                    "|---|---|---|---|---|\n"
                    "| R1-Q01 | physical p.1 | Does the rendered claim cover "
                    "all cases? | The submitted PDF does not resolve the "
                    "scope. | A precise author clarification or visible "
                    "evidence is needed. |\n\n"
                    "## Coverage and limitations",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "disagreements table omits chair dispositions ['R1-Q01']",
            )

    def test_hardening_92_csv_rejects_missing_and_phantom_n_coverage(self) -> None:
        with self.subTest(case="missing N row"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            for filename, columns in (
                ("91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS),
                ("93-current-actionable-items.csv", ACADEMIC_SUMMARY_COLUMNS),
            ):
                _headers, rows = read_csv(root / filename)
                rows[0]["Remedy"] = "N"
                write_csv(root / filename, columns, rows)
            for filename in (
                "91-revision-ledger.md",
                "90-chair-synthesis.md",
                "93-user-facing-summary.md",
            ):
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "| S2 | N/A | W | physical p.1 |",
                        "| S2 | N/A | N | physical p.1 |",
                        1,
                    ),
                    encoding="utf-8",
                )
            evidence_md = root / "92-new-evidence-or-experiments.md"
            evidence_md.write_text(
                evidence_md.read_text(encoding="utf-8").replace(
                    "| L01 | W | physical p.1 | correct the wording | reinspect p.1 |\n",
                    "",
                    1,
                ),
                encoding="utf-8",
            )
            self.assert_fails(
                root,
                "92 evidence coverage of open Remedy=N rows: missing IDs ['L01']",
            )

        with self.subTest(case="phantom N row"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            write_csv(
                root / "92-new-evidence-or-experiments.csv",
                EVIDENCE_ITEM_COLUMNS,
                [{
                    "EvidenceItemID": "N01",
                    "LedgerID": "L99",
                    "ChairFindingID": "C-F99",
                    "Remedy": "N",
                    "Item": "phantom additional experiment",
                    "ClaimThatDependsOnIt": "phantom unsupported claim",
                    "WhyWritingIsInsufficient": "new evidence would be required",
                    "MinimumViableEvidence": "one bounded experiment",
                    "ConsequenceIfUnavailable": "remove the phantom claim",
                }],
            )
            self.assert_fails(
                root,
                "LedgerID must refer to one open current 91 row with Remedy=N",
            )

    def test_hardening_stage_s_csv_row_order_tracks_authoritative_ledgers(
        self,
    ) -> None:
        with self.subTest(kind="academic"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _headers, ledger_rows = read_csv(root / "91-revision-ledger.csv")
            second = dict(ledger_rows[0])
            second["LedgerID"] = "L02"
            second["ChairFindingID"] = "C-F02"
            write_csv(
                root / "91-revision-ledger.csv",
                ACADEMIC_LEDGER_COLUMNS,
                [ledger_rows[0], second],
            )
            write_csv(
                root / "93-current-actionable-items.csv",
                ACADEMIC_SUMMARY_COLUMNS,
                [second, ledger_rows[0]],
            )
            self.assert_fails(
                root,
                "93-current-actionable-items.csv: row order must exactly follow "
                "the open 91-revision-ledger.csv row order",
            )

        with self.subTest(kind="AI"), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_bundle(root)
            _headers, ledger_rows = read_csv(root / "91-ai-actionable-ledger.csv")
            second = dict(ledger_rows[0])
            second["AIFindingID"] = "AI-F02"
            write_csv(
                root / "91-ai-actionable-ledger.csv",
                AI_LEDGER_COLUMNS,
                [ledger_rows[0], second],
            )
            write_csv(
                root / "93-current-ai-actionable-items.csv",
                AI_SUMMARY_COLUMNS,
                [second, ledger_rows[0]],
            )
            self.assert_fails(
                root,
                "93-current-ai-actionable-items.csv: row order must exactly follow "
                "the open 91-ai-actionable-ledger.csv row order",
            )

    def test_rule_text_exposes_exact_personas_and_ai_physical_locator(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        report_template = (skill_root / "references" / "report-template.md").read_text(
            encoding="utf-8"
        )
        reviewer_panels = (skill_root / "references" / "reviewer-panels.md").read_text(
            encoding="utf-8"
        )
        exact_personas = (
            "R1 technical/methods/experiments",
            "R2 contribution/novelty/positioning",
            "R3 thesis architecture/narrative",
            "R4 evidence/reproducibility/integrity/citation",
            "R5 format/bibliography/layout",
        )
        for persona in exact_personas:
            self.assertIn(persona, report_template)
            self.assertIn(persona, reviewer_panels)
        self.assertIn(
            "Location: canonical `physical p.<n>` within `1..physical_page_count`",
            report_template,
        )

    def test_dependency_ledger_ids_are_validated_as_closed_foreign_keys(self) -> None:
        rows = [
            {"LedgerID": "L01", "Dependency": "requires L02"},
            {"LedgerID": "L02", "Dependency": "none"},
        ]
        errors: list[str] = []
        VALIDATOR_MODULE.validate_academic_dependency_references(
            rows, "91-revision-ledger.csv", errors
        )
        self.assertEqual([], errors)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "91-revision-ledger.md"
            path.write_text(
                VALIDATOR_MODULE.render_markdown_pipe_table(
                    ["Ledger ID", "Dependency"],
                    [["L01", "L02"], ["L02", "none"]],
                ),
                encoding="utf-8",
            )
            projection_errors: list[str] = []
            VALIDATOR_MODULE.validate_markdown_id_projection(
                path,
                {"L01", "L02"},
                re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
                {"Ledger ID"},
                "academic dependency fixture",
                projection_errors,
                required_headers={"Ledger ID", "Dependency"},
                reference_id_headers={"Dependency"},
            )
            self.assertEqual([], projection_errors)

        cases = (
            (
                [
                    {"LedgerID": "L01", "Dependency": "L99"},
                    {"LedgerID": "L02", "Dependency": "none"},
                ],
                "unknown LedgerID references ['L99']",
            ),
            (
                [
                    {"LedgerID": "L01", "Dependency": "L01"},
                    {"LedgerID": "L02", "Dependency": "none"},
                ],
                "cannot reference its own LedgerID L01",
            ),
            (
                [
                    {"LedgerID": "L01", "Dependency": "L02"},
                    {"LedgerID": "L02", "Dependency": "L01"},
                ],
                "Dependency cycle is forbidden",
            ),
            (
                [
                    {"LedgerID": "L01", "Dependency": "L02; L02"},
                    {"LedgerID": "L02", "Dependency": "none"},
                ],
                "repeats LedgerID references ['L02']",
            ),
        )
        for candidate, needle in cases:
            with self.subTest(needle=needle):
                errors = []
                VALIDATOR_MODULE.validate_academic_dependency_references(
                    candidate, "91-revision-ledger.csv", errors
                )
                self.assertTrue(any(needle in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
