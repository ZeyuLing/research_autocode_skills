#!/usr/bin/env python3
"""Mechanically validate one clean-room thesis-review bundle.

The validator checks bundle identity, complete CSV contracts, referential
integrity, clean-context receipts, helper provenance, and exact Stage-C to
Stage-S reconciliation. It deliberately does not replace the reviewers'
semantic judgments or certify that an observation is scientifically correct.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEX64_FIND_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])")
PUBLIC_URL_RE = re.compile(r"https?://[^\s;,]+", re.IGNORECASE)
SOURCE_LOCATOR_RE = re.compile(
    r"(?:"
    r"\b(?:p{1,2}\.?|pages?|section|sec\.?|table|figure|equation|"
    r"theorem|lemma|appendix|supplement|paragraph|heading|lines?|anchor)"
    r"\s*[#§:]?\s*[A-Za-z]?\d+(?:\.\d+)*(?:\s*[-–]\s*\d+(?:\.\d+)*)?\b"
    r"|\b(?:abstract|introduction|conclusion|methods?|results?)\b"
    r"|\b(?:metadata|publisher|proceedings|official)\s+record\s*[:#]?\s*\S+"
    r"|§\s*\d+(?:\.\d+)*"
    r"|第\s*\d+(?:\.\d+)*\s*[页节]"
    r"|[表图式]\s*\(?\s*\d+(?:\.\d+)*(?:-\d+)?\s*\)?"
    r"|附录\s*[A-Za-z0-9]+"
    r")",
    re.IGNORECASE,
)
PAGE_ID_RE = re.compile(r"^P(\d{4})$")
REFERENCE_ID_RE = re.compile(r"^REF(\d{4})$")
OCCURRENCE_ID_RE = re.compile(r"^C(\d{4})$")
PAIR_ID_RE = re.compile(r"^C(\d{4})-S(\d{2})$")
BRACKET_CANDIDATE_ID_RE = re.compile(r"^BC(\d{4})$")
NUMERIC_BRACKET_RE = re.compile(
    r"\[(?P<items>\d{1,4}(?:\s*[-–—]\s*\d{1,4})?"
    r"(?:\s*[,，]\s*\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)*)\]"
)
NUMERIC_BRACKET_SPAN_RE = re.compile(r"\[[^\[\]]+\]")

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

BIB_FIELDS = {
    "type", "title", "ordered_authors", "year", "venue",
    "publication_status", "volume", "issue", "pages_or_article_number",
    "doi", "arxiv_id", "arxiv_version", "url", "access_date",
    "isbn_or_other_persistent_id", "existence",
    "retraction_withdrawal_correction_superseding",
}
BIB_VERDICTS = {"exact", "mismatch", "legitimate n/a", "unverifiable"}
SUPPORT_VALUES = {
    "direct", "partial", "context-only", "mismatch", "unverifiable",
    "not-needed",
}
CLOSED_STATUSES = {
    "closed", "resolved", "not required", "not applicable", "n/a",
}
STATUS_VALUES = CLOSED_STATUSES | {"open"}
ACADEMIC_SEVERITIES = {"s0", "s1", "s2", "s3"}
ACADEMIC_REMEDIES = {"w", "e", "n", "p"}
ACADEMIC_PRIORITIES = {"p0", "p1", "p2", "p3"}
AI_ACTION_IMPACTS = {"material", "local"}
PLACEHOLDERS = {
    "pending", "unchecked", "...", "…", "todo", "tbd",
    "placeholder", "not checked", "not verified", "x",
}
NON_SIGNAL_VALUES = {
    "none", "clean", "no signal", "no signals", "n/a", "not applicable",
}
INSPECTION_MODE_PREFIXES = ("individual", "small-legible-group", "full-scale")

PROCESS_KEYS = {
    "round_id", "retry_id", "frozen_pdf_file", "selected_pdf_sha256",
    "physical_page_count", "frozen_at", "degree_level", "degree_type", "institution",
    "school_or_department", "discipline", "expected_submission_year",
    "artifact_type", "review_mode", "output_language",
    "governing_rule_urls", "governing_local_files",
    "decision_regime_status",
}
HELPER_PROVENANCE_KEYS = {
    "actor_id", "round_id", "retry_id", "prompt_sha256",
    "fresh_context_declaration", "input_receipt_access_declaration",
    "received_blocks", "opened_inputs", "tool", "version",
    "command_or_query", "pdf_sha256_start", "pdf_sha256_end", "outputs",
    "limitations", "recipient_stages",
}
HELPER_OUTPUT_KEYS = {"file", "sha256"}

CANDIDATE_CLASSIFICATIONS = {"citation", "non-citation"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_pdf_structure_and_pages(
    path: Path, declared_pages: int, errors: list[str]
) -> list[tuple[float, float]]:
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                errors.append(f"{path.name}: invalid PDF header")
                return []
    except OSError as exc:
        errors.append(f"{path.name}: cannot read PDF header: {exc}")
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        errors.append(
            "validator dependency missing: install pypdf or use the bundled "
            "workspace Python runtime"
        )
        return []
    try:
        reader = PdfReader(str(path), strict=False)
        actual_pages = len(reader.pages)
        page_sizes: list[tuple[float, float]] = []
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if int(page.rotation or 0) % 180:
                width, height = height, width
            page_sizes.append((width, height))
    except Exception as exc:  # pypdf exposes several parser exception types
        errors.append(f"{path.name}: cannot parse frozen PDF: {exc}")
        return []
    if actual_pages < 1:
        errors.append(f"{path.name}: parsed PDF has no pages")
    if declared_pages and actual_pages != declared_pages:
        errors.append(
            f"{path.name}: parsed page count {actual_pages} != "
            f"physical_page_count {declared_pages}"
        )
    return page_sizes


def normalize_numeric_marker(value: str) -> str:
    """Normalize only layout variants while preserving the numeric grammar."""
    return (
        re.sub(r"\s+", "", value)
        .replace("，", ",")
        .replace("–", "-")
        .replace("—", "-")
    )


def normalize_extracted_text(value: str) -> str:
    """Use one deterministic whitespace normalization for every PDF anchor."""
    return re.sub(r"\s+", " ", value).strip()


def expand_numeric_marker(value: str) -> list[int] | None:
    match = NUMERIC_BRACKET_RE.fullmatch(value.strip())
    if not match:
        return None
    expanded: list[int] = []
    for token in re.split(r"[,，]", match.group("items")):
        token = token.strip()
        range_match = re.fullmatch(r"(\d{1,4})\s*[-–—]\s*(\d{1,4})", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            step = 1 if end >= start else -1
            expanded.extend(range(start, end + step, step))
        else:
            expanded.append(int(token))
    return expanded


def extract_numeric_bracket_candidates(
    pdf_path: Path,
    reference_pages: set[int],
    errors: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Re-extract the closed Stage-P candidate universe from the frozen PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception as exc:
        errors.append(f"cannot extract citation candidates from frozen PDF: {exc}")
        return [], []
    candidates: list[dict[str, Any]] = []
    unmatched_glyphs: list[dict[str, Any]] = []
    for physical_page, page in enumerate(reader.pages, start=1):
        if physical_page in reference_pages:
            continue
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            errors.append(
                "citation-candidate extraction failed on physical page "
                f"{physical_page}: {exc}"
            )
            continue
        opening_stack: list[int] = []
        unmatched_positions: list[tuple[int, str]] = []
        for offset, character in enumerate(text):
            if character == "[":
                opening_stack.append(offset)
            elif character == "]":
                if opening_stack:
                    opening_stack.pop()
                else:
                    unmatched_positions.append((offset, character))
        unmatched_positions.extend((offset, "[") for offset in opening_stack)
        for offset, glyph in sorted(unmatched_positions):
            start = max(0, offset - 160)
            end = min(len(text), offset + 161)
            unmatched_glyphs.append({
                "PhysicalPage": physical_page,
                "Glyph": glyph,
                "Adjacent": normalize_extracted_text(text[start:end]),
            })
        for match in NUMERIC_BRACKET_SPAN_RE.finditer(text):
            if not re.search(r"\d", match.group(0)):
                continue
            start = max(0, match.start() - 160)
            end = min(len(text), match.end() + 160)
            candidates.append({
                "PhysicalPage": physical_page,
                "Marker": normalize_numeric_marker(match.group(0)),
                "Expanded": expand_numeric_marker(match.group(0)),
                "Adjacent": normalize_extracted_text(text[start:end]),
                "Prefix": text[max(0, match.start() - 100):match.start()],
            })
    return candidates, unmatched_glyphs


def obvious_non_citation_reason(candidate: dict[str, Any]) -> str | None:
    """Reject high-certainty numeric-bracket lookalikes mechanically."""
    if candidate["Expanded"] is None:
        return "numeric bracket is not a pure integer citation marker"
    numbers = list(candidate["Expanded"])
    if 0 in numbers:
        return "zero-bearing numeric interval/vector"
    if len(numbers) != len(set(numbers)):
        return "duplicate-number vector/array"
    prefix = re.sub(r"\s+", " ", str(candidate["Prefix"])).strip()
    if re.search(r"(?:∈|\\in)\s*$", prefix):
        return "mathematical set/interval membership"
    if re.search(
        r"(?:档数(?:依次)?为|量化(?:档|级别)(?:依次)?为|数组(?:为)?|"
        r"向量(?:为)?|形状(?:为)?|尺寸(?:为)?|维度(?:为)?|大小(?:为)?|"
        r"levels?\s*(?:are|=)|array\s*(?:is|=)|vector\s*(?:is|=)|"
        r"(?:tensor\s+)?shape\s*(?:is|=)|size\s*(?:is|=)|=)\s*$",
        prefix,
        flags=re.IGNORECASE,
    ):
        return "explicit numeric vector/array introduction"
    if re.search(
        r"(?:\b(?:interval|range|domain|shape|sizes?|levels?|array|vector)"
        r"(?:\s+(?:is|are|of))?|区间|范围|集合|形状|大小|尺寸|维度)\s*$",
        prefix,
        flags=re.IGNORECASE,
    ):
        return "explicit interval/vector grammatical role"
    if re.search(
        r"\b(?:tensor|array|vector|matrix)\s+[A-Za-z_]\w*\s*$",
        prefix,
        flags=re.IGNORECASE,
    ):
        return "tensor/array index notation"
    return None


def derive_and_validate_reference_pages(
    pdf_path: Path,
    declared_reference_pages: set[int],
    bibliography_rows: list[dict[str, str]],
    errors: list[str],
) -> set[int]:
    """Bind the bibliography region to the rendered [1]...[N] entry run."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception as exc:
        errors.append(f"cannot derive rendered bibliography pages: {exc}")
        return set()
    expected_labels: list[int] = []
    for line, row in enumerate(bibliography_rows, start=2):
        match = re.fullmatch(r"\[(\d{1,4})\]", row.get("DisplayedLabel", ""))
        if not match:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: invalid DisplayedLabel"
            )
            continue
        expected_labels.append(int(match.group(1)))
    expected_sequence = list(range(1, len(bibliography_rows) + 1))
    if expected_labels != expected_sequence:
        errors.append(
            "00-bibliography-inventory.csv: DisplayedLabel sequence is not [1]..[N]"
        )
    events: list[tuple[int, int]] = []
    for physical_page, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            errors.append(
                f"bibliography extraction failed on physical page {physical_page}: {exc}"
            )
            continue
        events.extend(
            (physical_page, int(value))
            for value in re.findall(r"(?m)^\s*\[(\d{1,4})\]", text)
        )
    all_runs: list[list[tuple[int, int]]] = []
    length = len(expected_sequence)
    if length:
        for start, (_page, number) in enumerate(events):
            if number != 1:
                continue
            candidate = [events[start]]
            cursor = start + 1
            expected_next = 2
            while cursor < len(events) and events[cursor][1] == expected_next:
                candidate.append(events[cursor])
                cursor += 1
                expected_next += 1
            all_runs.append(candidate)
    longest_length = max((len(run) for run in all_runs), default=0)
    runs = [run for run in all_runs if len(run) == longest_length]
    if len(runs) != 1 or longest_length != length:
        errors.append(
            "frozen PDF must contain exactly one longest rendered line-start "
            f"bibliography run and its length must equal the {length} inventory "
            f"rows; longest_length={longest_length}, tied_longest_runs={len(runs)}"
        )
        return set()
    first_page = runs[0][0][0]
    last_page = runs[0][-1][0]
    try:
        first_page_text = reader.pages[first_page - 1].extract_text() or ""
    except Exception as exc:
        errors.append(
            f"cannot verify bibliography heading on physical page {first_page}: {exc}"
        )
        return set()
    if not re.search(
        r"(?im)(?:^|\n)\s*(?:参考文献|references|bibliography)\s*(?:\n|$)",
        first_page_text,
    ):
        errors.append(
            "rendered bibliography run is not anchored by a References/参考文献 "
            f"heading on physical page {first_page}"
        )
        return set()
    derived_pages = set(range(first_page, last_page + 1))
    if declared_reference_pages != derived_pages:
        errors.append(
            "00-page-inventory.csv: reference Region pages do not equal the "
            f"rendered bibliography span; declared={sorted(declared_reference_pages)}, "
            f"derived={sorted(derived_pages)}"
        )
    return derived_pages


def parse_physical_page_locator(value: str) -> int | None:
    match = re.search(
        r"(?i)\bphysical\s+(?:page\s*)?p?\.?0*(\d+)\b", value
    )
    return int(match.group(1)) if match else None


def validate_iso_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_markdown_id_projection(
    path: Path,
    expected_ids: set[str],
    id_pattern: re.Pattern[str],
    id_header_aliases: set[str],
    label: str,
    errors: list[str],
    *,
    required_headers: set[str] | None = None,
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path.name}: cannot read Markdown master: {exc}")
        return
    if len(text.strip()) < 32:
        errors.append(f"{path.name}: Markdown master is empty or shell-only")

    def parse_pipe_row(line: str) -> list[str] | None:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return None
        return [
            cell.replace(r"\|", "|").strip()
            for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
        ]

    def is_separator_row(cells: list[str], width: int) -> bool:
        return (
            len(cells) == width
            and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)
        )

    lines = text.splitlines()
    target_tables: list[tuple[int, list[str], int]] = []
    folded_aliases = {alias.casefold() for alias in id_header_aliases}
    for index in range(len(lines) - 1):
        header = parse_pipe_row(lines[index])
        separator = parse_pipe_row(lines[index + 1])
        if header is None or separator is None or not is_separator_row(separator, len(header)):
            continue
        id_columns = [
            column
            for column, cell in enumerate(header)
            if cell.casefold() in folded_aliases
        ]
        if len(id_columns) == 1:
            target_tables.append((index, header, id_columns[0]))
    if len(target_tables) != 1:
        errors.append(
            f"{path.name}: expected exactly one complete Markdown table with "
            f"ID header {sorted(id_header_aliases)}, found {len(target_tables)}"
        )
        compare_sets(f"{label} Markdown projection", expected_ids, set(), errors)
        return

    header_index, header, id_column = target_tables[0]
    if required_headers is not None:
        actual_headers = {cell.casefold() for cell in header}
        missing_headers = sorted(
            value for value in required_headers
            if value.casefold() not in actual_headers
        )
        if missing_headers:
            errors.append(
                f"{path.name}: target Markdown table is missing required "
                f"headers {missing_headers}"
            )
    row_counts: Counter[str] = Counter()
    data_row_count = 0
    target_data_lines: set[int] = set()
    for line_number in range(header_index + 2, len(lines)):
        cells = parse_pipe_row(lines[line_number])
        if cells is None:
            break
        target_data_lines.add(line_number)
        data_row_count += 1
        if len(cells) != len(header):
            errors.append(
                f"{path.name}:{line_number + 1}: Markdown table row has "
                f"{len(cells)} cells; expected {len(header)}"
            )
            continue
        identifier = cells[id_column]
        if not id_pattern.fullmatch(identifier):
            errors.append(
                f"{path.name}:{line_number + 1}: ID-column value "
                f"{identifier!r} does not match the required ID format"
            )
            continue
        row_counts[identifier] += 1
        for column, cell in enumerate(cells):
            if column == id_column:
                continue
            misplaced = sorted(set(id_pattern.findall(cell)))
            if misplaced:
                errors.append(
                    f"{path.name}:{line_number + 1}: IDs must occur only in "
                    f"the designated ID column, found {misplaced}"
                )
    if data_row_count == 0 and expected_ids:
        errors.append(f"{path.name}: target Markdown table has no data rows")
    for line_number, line in enumerate(lines):
        if line_number in target_data_lines:
            continue
        outside_ids = sorted(set(id_pattern.findall(line)))
        if outside_ids:
            errors.append(
                f"{path.name}:{line_number + 1}: IDs outside the target "
                f"Markdown table are forbidden: {outside_ids}"
            )
    actual_ids = set(row_counts)
    compare_sets(f"{label} Markdown projection", expected_ids, actual_ids, errors)
    duplicates = sorted(identifier for identifier, count in row_counts.items() if count != 1)
    if duplicates:
        errors.append(
            f"{path.name}: IDs must occur in exactly one Markdown table row: {duplicates}"
        )


def parse_markdown_table_by_header(
    text: str,
    required_first_header: str,
    filename: str,
    errors: list[str],
) -> tuple[list[str], list[list[str]]] | None:
    """Return one exact pipe table selected by its first header cell."""

    def parse_row(line: str) -> list[str] | None:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return None
        return [
            cell.replace(r"\|", "|").strip()
            for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
        ]

    lines = text.splitlines()
    matches: list[tuple[list[str], list[list[str]]]] = []
    for index in range(len(lines) - 1):
        header = parse_row(lines[index])
        separator = parse_row(lines[index + 1])
        if (
            not header
            or header[0].casefold() != required_first_header.casefold()
            or separator is None
            or len(separator) != len(header)
            or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        ):
            continue
        rows: list[list[str]] = []
        for row_line in lines[index + 2:]:
            row = parse_row(row_line)
            if row is None:
                break
            rows.append(row)
        matches.append((header, rows))
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one Markdown table whose first "
            f"header is {required_first_header!r}, found {len(matches)}"
        )
        return None
    header, rows = matches[0]
    for index, row in enumerate(rows, start=1):
        if len(row) != len(header):
            errors.append(
                f"{filename}: selected table row {index} has {len(row)} "
                f"cells; expected {len(header)}"
            )
    return header, rows


def parse_markdown_table_by_exact_headers(
    text: str,
    expected_headers: list[str],
    filename: str,
    errors: list[str],
) -> list[list[str]] | None:
    """Select exactly one pipe table by its complete ordered header schema."""

    def parse_row(line: str) -> list[str] | None:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return None
        return [
            cell.replace(r"\|", "|").strip()
            for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
        ]

    expected_folded = [value.casefold() for value in expected_headers]
    lines = text.splitlines()
    matches: list[list[list[str]]] = []
    for index in range(len(lines) - 1):
        header = parse_row(lines[index])
        separator = parse_row(lines[index + 1])
        if (
            header is None
            or [value.casefold() for value in header] != expected_folded
            or separator is None
            or len(separator) != len(header)
            or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        ):
            continue
        rows: list[list[str]] = []
        for row_line in lines[index + 2:]:
            row = parse_row(row_line)
            if row is None:
                break
            rows.append(row)
        matches.append(rows)
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one Markdown table with schema "
            f"{expected_headers}, found {len(matches)}"
        )
        return None
    rows = matches[0]
    for index, row in enumerate(rows, start=1):
        if len(row) != len(expected_headers):
            errors.append(
                f"{filename}: selected table row {index} has {len(row)} "
                f"cells; expected {len(expected_headers)}"
            )
    return rows


def read_valid_png_dimensions(path: Path, errors: list[str]) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        errors.append(f"{path.name}: cannot read render PNG: {exc}")
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        errors.append(f"{path.name}: invalid PNG signature")
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_idat = False
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            errors.append(f"{path.name}: truncated PNG chunk")
            return None
        payload = data[offset + 8:offset + 8 + length]
        declared_crc = struct.unpack(">I", data[offset + 8 + length:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if declared_crc != actual_crc:
            errors.append(f"{path.name}: PNG chunk CRC mismatch")
            return None
        if chunk_type == b"IHDR":
            if length != 13 or dimensions is not None:
                errors.append(f"{path.name}: invalid PNG IHDR")
                return None
            dimensions = struct.unpack(">II", payload[:8])
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            saw_iend = True
            break
        offset = chunk_end
    if dimensions is None or not saw_idat or not saw_iend:
        errors.append(f"{path.name}: incomplete PNG render")
        return None
    try:
        from PIL import Image
    except ImportError:
        errors.append(
            "validator dependency missing: install Pillow or use the bundled "
            "workspace Python runtime"
        )
        return None
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            decoded_dimensions = image.size
    except Exception as exc:  # Pillow exposes several decoder exception types
        errors.append(f"{path.name}: PNG pixels cannot be decoded: {exc}")
        return None
    if decoded_dimensions != dimensions:
        errors.append(
            f"{path.name}: decoded PNG dimensions {decoded_dimensions} do not "
            f"match IHDR {dimensions}"
        )
        return None
    return dimensions


def is_placeholder(value: str) -> bool:
    return value.strip().casefold() in PLACEHOLDERS


def require_value(
    row: dict[str, str],
    field: str,
    location: str,
    errors: list[str],
    *,
    allow_blank: bool = False,
) -> None:
    value = row.get(field, "").strip()
    if not value and not allow_blank:
        errors.append(f"{location}: blank mandatory field {field}")
    elif (
        value
        and is_placeholder(value)
        and not (field == "PrintedPage" and value == "X")
    ):
        errors.append(f"{location}: placeholder in mandatory field {field}: {value!r}")


def read_csv(
    path: Path,
    expected_columns: list[str],
    errors: list[str],
    *,
    require_rows: bool,
) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"missing CSV: {path.name}")
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if headers != expected_columns:
                errors.append(
                    f"{path.name}: schema mismatch; expected {expected_columns}, got {headers}"
                )
            rows: list[dict[str, str]] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    errors.append(
                        f"{path.name}:{line_number}: values exceed declared header"
                    )
                normalized = {
                    key: (row.get(key) or "").strip() for key in expected_columns
                }
                rows.append(normalized)
            if require_rows and not rows:
                errors.append(f"{path.name}: header-only or empty ledger is not complete")
            return rows
    except (OSError, csv.Error) as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
        return []


def index_unique(
    rows: list[dict[str, str]],
    field: str,
    filename: str,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for line, row in enumerate(rows, start=2):
        value = row.get(field, "")
        require_value(row, field, f"{filename}:{line}", errors)
        if value:
            if value in result:
                errors.append(f"{filename}: duplicate {field} {value!r}")
            else:
                result[value] = row
    return result


def compare_sets(
    label: str, expected: set[str], actual: set[str], errors: list[str]
) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{label}: missing IDs {missing}")
    if extra:
        errors.append(f"{label}: extra IDs {extra}")


def validate_pdf_hash(
    rows: list[dict[str, str]],
    filename: str,
    expected: str,
    errors: list[str],
) -> None:
    for line, row in enumerate(rows, start=2):
        value = row.get("PDFSHA256", "").upper()
        if not HEX64_RE.fullmatch(value):
            errors.append(f"{filename}:{line}: PDFSHA256 is not 64 hexadecimal characters")
        elif value != expected:
            errors.append(
                f"{filename}:{line}: PDFSHA256 {value} does not equal frozen PDF {expected}"
            )


def extract_hashes_from_labeled_line(text: str, label_pattern: str) -> list[str]:
    for line in text.splitlines():
        if re.search(label_pattern, line, flags=re.IGNORECASE):
            return [match.upper() for match in HEX64_FIND_RE.findall(line)]
    return []


def validate_declarations(
    path: Path, expected_pdf_hash: str, errors: list[str]
) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    lower = text.casefold()
    if "fresh-context declaration" not in lower:
        errors.append(f"{path.name}: missing fresh-context declaration")
    required_fresh_boundary = (
        "no inherited user/thread/task turns beyond system/developer "
        "instructions and the exact operational prompt"
    )
    if required_fresh_boundary not in lower:
        errors.append(
            f"{path.name}: fresh-context declaration does not state the "
            "complete no-inherited-context boundary"
        )
    if "input-receipt/access declaration" not in lower:
        errors.append(f"{path.name}: missing input-receipt/access declaration")
    if "received" not in lower or "opened" not in lower:
        errors.append(f"{path.name}: input receipt does not name received/opened inputs")
    for description, alternatives in (
        ("no unlisted substantive assertion", (
            "no unlisted substantive assertion",
            "no unlisted substantive assertions",
        )),
        ("no prohibited context/artifact", (
            "no prohibited context/artifact",
            "no prohibited context or artifact",
            "no prohibited context and no prohibited artifact",
        )),
        ("no neighboring-path enumeration", (
            "neighboring paths were not enumerated",
            "neighboring paths not enumerated",
            "no neighboring-path enumeration",
            "no neighboring path enumeration",
        )),
    ):
        if not any(value in lower for value in alternatives):
            errors.append(
                f"{path.name}: input receipt does not state {description}"
            )
    prompt_hashes = extract_hashes_from_labeled_line(text, r"prompt\s+sha-?256")
    if len(prompt_hashes) != 1:
        errors.append(
            f"{path.name}: expected exactly one 64-hex operational prompt SHA-256"
        )
    pdf_hashes = extract_hashes_from_labeled_line(
        text, r"frozen\s+pdf\s+sha-?256.*start.*end"
    )
    if len(pdf_hashes) != 2:
        errors.append(
            f"{path.name}: expected two 64-hex frozen PDF hashes on the start/end declaration"
        )
    elif any(value != expected_pdf_hash for value in pdf_hashes):
        errors.append(f"{path.name}: start/end PDF hash does not match frozen PDF")
    return text


def validate_reviewer_report(
    path: Path,
    expected_pdf_hash: str,
    reviewer_index: int,
    degree_level: str | None,
    errors: list[str],
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    for heading in (
        "Role, scope, and independence",
        "Verdict",
        "What I inspected",
        "Whole-thesis synthesis",
        "Whole-thesis assessment",
        "Persona-weighted deep review",
        "Strongest contributions",
        "Findings",
        "Questions, not findings",
        "Coverage and limitations",
    ):
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text):
            errors.append(f"{path.name}: missing required section {heading!r}")
    mandate = labeled_value(text, "Whole-thesis mandate")
    if mandate is None or not re.search(r"Gate\s+A\s*(?:--|–|—|-)\s*I", mandate, re.I):
        errors.append(f"{path.name}: Whole-thesis mandate must explicitly cover Gate A--I")
    persona = labeled_value(text, "Persona emphasis")
    persona_terms = {
        1: ("technical", "method", "experiment", "技术", "方法", "实验"),
        2: ("contribution", "thesis logic", "narrative", "贡献", "主线", "逻辑"),
        3: ("evidence", "reproduc", "integrity", "证据", "复现", "完整性"),
        4: ("citation", "claim", "source", "引用", "引文", "来源"),
        5: ("format", "bibliograph", "layout", "page", "格式", "参考文献", "版面"),
    }
    expected_terms = persona_terms.get(reviewer_index, ())
    if (
        persona is None
        or len(persona) < 12
        or not any(term.casefold() in persona.casefold() for term in expected_terms)
    ):
        errors.append(
            f"{path.name}: Persona emphasis is missing or does not match the "
            f"distinct R{reviewer_index} emphasis"
        )
    for label in ("Decision regime", "Confidence"):
        value = labeled_value(text, label)
        if value is None or len(value) < 3 or is_placeholder(value):
            errors.append(f"{path.name}: missing concrete {label}")
    rationale = labeled_value(text, "One-paragraph whole-thesis rationale")
    if rationale is None or len(rationale) < 60 or is_placeholder(rationale):
        errors.append(f"{path.name}: whole-thesis rationale is absent or shell-only")
    gate_rows: dict[str, list[str]] = {}
    gate_counts: Counter[str] = Counter()
    for line in text.splitlines():
        match = re.match(r"^\|\s*([A-I])\s*(?:[—-]|\|)", line)
        if not match:
            continue
        cells = [
            cell.replace(r"\|", "|").strip()
            for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])
        ]
        gate_counts[match.group(1)] += 1
        gate_rows.setdefault(match.group(1), cells)
    for gate in "ABCDEFGHI":
        if gate_counts[gate] != 1:
            errors.append(
                f"{path.name}: Gate {gate} must appear exactly once as a matrix row"
            )
        if gate not in gate_rows:
            continue
        cells = gate_rows[gate]
        if len(cells) != 6:
            errors.append(f"{path.name}: Gate {gate} row must have exactly six cells")
            continue
        if cells[1].casefold() not in {"baseline", "emphasized", "primary"}:
            errors.append(f"{path.name}: Gate {gate} has invalid review depth")
        if cells[2].casefold() not in {"adequate", "concern", "unverifiable", "n/a"}:
            errors.append(f"{path.name}: Gate {gate} has invalid disposition")
        if len(cells[3]) < 5 or is_placeholder(cells[3]):
            errors.append(f"{path.name}: Gate {gate} lacks decisive anchored evidence")
        if not cells[4] or not cells[5] or is_placeholder(cells[5]):
            errors.append(f"{path.name}: Gate {gate} lacks finding/confidence disposition")
    if not re.search(
        r"(?im)^\s*-\s*Academic grade:\s*(?:A|B|C|D|N/?A)\b", text
    ):
        errors.append(f"{path.name}: missing explicit academic grade")
    if not re.search(r"(?im)^\s*-\s*Defense recommendation:\s*\S", text):
        errors.append(f"{path.name}: missing explicit defense recommendation")
    if degree_level == "doctorate" and reviewer_index == 4:
        for heading in ("Full citation-claim audit",):
            if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text):
                errors.append(f"{path.name}: missing doctoral audit-duty section {heading!r}")
        for label in ("Citation--source pairs", "Ledger rows and unchecked rows"):
            value = labeled_value(text, label)
            if value is None or not re.search(r"\d", value):
                errors.append(f"{path.name}: missing concrete citation-audit count {label!r}")
    if degree_level == "doctorate" and reviewer_index == 5:
        for heading in ("Full rendered-page audit", "Full bibliography-integrity audit"):
            if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text):
                errors.append(f"{path.name}: missing doctoral audit-duty section {heading!r}")
        for label in (
            "Physical pages / unchecked pages",
            "Bibliography entries rendered in the frozen PDF",
            "Bibliography master rows / unchecked rows",
        ):
            value = labeled_value(text, label)
            if value is None or not re.search(r"\d", value):
                errors.append(f"{path.name}: missing concrete owner-audit count {label!r}")
    if degree_level == "masters" and reviewer_index == 3:
        for heading in (
            "Full rendered-page audit",
            "Full bibliography-integrity audit",
            "Full citation-claim audit",
        ):
            if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text):
                errors.append(f"{path.name}: missing master's owner-audit section {heading!r}")


def labeled_value(text: str, label: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*-\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text
    )
    return match.group(1).strip() if match else None


def validate_chair_report(
    path: Path,
    expected_pdf_hash: str,
    expected_cited_references: int,
    reviewer_count: int,
    errors: list[str],
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    for heading in (
        "Clean-room boundary",
        "Overall risk and recommendation",
        "Reviewer coverage validation",
        "Independent verdicts",
        "Standalone AI-style judgment",
        "AI-style actionable findings",
        "Contributions that survived review",
        "Adjudicated findings",
        "Mandatory citation cross-ledger consistency gate",
        "Disagreements and chair decisions",
        "Thesis-level narrative and chapter logic",
        "Policy and blind-copy status",
        "Optional suggestions",
        "Review limitations",
    ):
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text):
            errors.append(f"{path.name}: missing required chair section {heading!r}")
    coverage_headers = [
        "Reviewer", "Gate A", "B", "C", "D", "E", "F", "G", "H", "I",
        "Whole-thesis rationale", "Audit duty complete", "Eligible for adjudication",
    ]
    coverage_rows = parse_markdown_table_by_exact_headers(
        text, coverage_headers, path.name, errors
    )
    expected_reviewers = {f"R{index}" for index in range(1, reviewer_count + 1)}
    if coverage_rows is not None:
        coverage_by_actor = {
            row[0]: row for row in coverage_rows if len(row) == len(coverage_headers)
        }
        compare_sets(
            "chair reviewer-coverage actors",
            expected_reviewers,
            set(coverage_by_actor),
            errors,
        )
        for actor, row in coverage_by_actor.items():
            if any(not cell or is_placeholder(cell) for cell in row[1:]):
                errors.append(f"{path.name}: reviewer-coverage row {actor} is incomplete")
            if row[-1].casefold() not in {"yes", "eligible", "pass"}:
                errors.append(f"{path.name}: reviewer {actor} is not eligible for adjudication")
    verdict_headers = [
        "Reviewer", "Persona", "Category/grade", "Defense recommendation",
        "Decision regime/source", "Confidence", "Decisive reason",
    ]
    verdict_rows = parse_markdown_table_by_exact_headers(
        text, verdict_headers, path.name, errors
    )
    if verdict_rows is not None:
        verdict_by_actor = {
            row[0]: row for row in verdict_rows if len(row) == len(verdict_headers)
        }
        compare_sets(
            "chair independent-verdict actors",
            expected_reviewers,
            set(verdict_by_actor),
            errors,
        )
        for index in range(1, reviewer_count + 1):
            actor = f"R{index}"
            report_path = path.parent / f"{actor}-comprehensive-review.md"
            if actor not in verdict_by_actor or not report_path.is_file():
                continue
            report = report_path.read_text(encoding="utf-8", errors="replace")
            row = verdict_by_actor[actor]
            expected = (
                labeled_value(report, "Academic grade") or "",
                labeled_value(report, "Defense recommendation") or "",
                labeled_value(report, "Confidence") or "",
            )
            if (row[2], row[3], row[5]) != expected:
                errors.append(
                    f"{path.name}: chair independent-verdict row {actor} does "
                    "not exactly preserve the frozen reviewer verdict"
                )
            if len(row[1]) < 8 or len(row[6]) < 20:
                errors.append(f"{path.name}: chair verdict row {actor} is shell-only")
    ai_section_match = re.search(
        r"(?ims)^##\s+Standalone AI-style judgment\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    if ai_section_match:
        ai_section = ai_section_match.group(1)
        chair_signal = labeled_value(ai_section, "Signal")
        chair_ai_confidence = labeled_value(ai_section, "Confidence")
        ai_path = path.parent / "05-ai-style-assessment.md"
        if ai_path.is_file():
            ai_text = ai_path.read_text(encoding="utf-8", errors="replace")
            if chair_signal != (labeled_value(ai_text, "AI-style signal") or ""):
                errors.append(
                    f"{path.name}: standalone AI signal does not exactly preserve "
                    "the frozen AI assessment"
                )
            if chair_ai_confidence != (labeled_value(ai_text, "Confidence") or ""):
                errors.append(
                    f"{path.name}: standalone AI confidence does not exactly preserve "
                    "the frozen AI assessment"
                )
    counts: dict[str, int] = {}
    for label in (
        "Unique cited rendered references joined",
        "Identity-agreement count",
        "Version disagreements",
        "Local conflicts",
        "Substantive conflicts",
        "Reclassified Pair IDs",
        "Unresolved conflicts",
    ):
        value = parse_count_label(text, label, path.name, errors)
        if value is not None:
            counts[label] = value
    joined = counts.get("Unique cited rendered references joined")
    if joined is not None and joined != expected_cited_references:
        errors.append(
            f"{path.name}: joined cited-reference count {joined} != "
            f"citation inventory unique-reference count {expected_cited_references}"
        )
    agreements = counts.get("Identity-agreement count")
    if joined is not None and agreements is not None and agreements > joined:
        errors.append(f"{path.name}: identity-agreement count exceeds joined references")
    gate = labeled_value(text, "Combined citation gate")
    if gate is None or gate.casefold() not in {"pass", "fail"}:
        errors.append(f"{path.name}: Combined citation gate must be pass or fail")
    elif gate.casefold() == "pass" and (
        counts.get("Substantive conflicts", 0) > 0
        or counts.get("Unresolved conflicts", 0) > 0
    ):
        errors.append(
            f"{path.name}: Combined citation gate cannot pass with substantive "
            "or unresolved conflicts"
        )
    if not re.search(
        r"(?im)^\s*-\s*Overall academic grade:\s*(?:A|B|C|D|N/?A)\b", text
    ):
        errors.append(f"{path.name}: missing overall academic grade")
    if not re.search(
        r"(?im)^\s*-\s*Overall defense recommendation:\s*\S", text
    ):
        errors.append(f"{path.name}: missing overall defense recommendation")
    chair_rationale = labeled_value(text, "Whole-thesis rationale")
    if chair_rationale is None or len(chair_rationale) < 60:
        errors.append(f"{path.name}: chair whole-thesis rationale is absent or shell-only")
    for heading in ("Optional suggestions", "Review limitations"):
        body = markdown_section_body(text, heading)
        if body is None or not body:
            errors.append(f"{path.name}: missing or empty chair section {heading!r}")


def parse_count_label(
    text: str, label: str, filename: str, errors: list[str]
) -> int | None:
    value = labeled_value(text, label)
    if value is None or not re.fullmatch(r"\d+", value):
        errors.append(f"{filename}: reconciliation '{label}' must be a nonnegative integer")
        return None
    return int(value)


def validate_ai_report(
    path: Path, expected_pdf_hash: str, errors: list[str]
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    disclaimer = (
        "this is a prose-style assessment, not a determination of ai use, "
        "authorship, plagiarism, or misconduct."
    )
    if disclaimer not in text.casefold():
        errors.append(f"{path.name}: missing mandatory non-attribution disclaimer")
    if not re.search(
        r"(?im)^\s*-\s*AI-style signal:\s*(low|moderate|high|indeterminate)\s*$",
        text,
    ):
        errors.append(f"{path.name}: missing allowed AI-style signal")
    for heading in (
        "Boundary and independence",
        "Overall judgment",
        "Coverage and mechanical checks",
        "Signal-family summary and counter-evidence",
        "Findings",
        "Limitations",
        "Out-of-scope observations for chair verification",
    ):
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text):
            errors.append(f"{path.name}: missing required AI section {heading!r}")
    confidence = labeled_value(text, "Confidence")
    rationale = labeled_value(text, "Rationale")
    if confidence is None or confidence.casefold() not in {"high", "medium", "low"}:
        errors.append(f"{path.name}: missing allowed AI confidence")
    if rationale is None or len(rationale) < 40:
        errors.append(f"{path.name}: AI rationale is absent or shell-only")


def markdown_section_body(text: str, heading: str) -> str | None:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    return normalize_extracted_text(match.group(1)) if match else None


def validate_summary_markdown_values(
    path: Path,
    academic_rows: dict[str, dict[str, str]],
    ai_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    specifications = (
        (
            "Ledger ID",
            academic_rows,
            [
                ("Ledger ID", "LedgerID"),
                ("Current finding ID(s)", "CurrentFindingIDs"),
                ("Severity / remedy", "SeverityRemedy"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct PDF-visible observation", "DirectPDFObservation"),
                ("Minimum required action", "MinimumRequiredAction"),
                ("Origin reviewer(s)", "OriginReviewers"),
                ("Chair disposition", "ChairDisposition"),
            ],
        ),
        (
            "AI finding ID",
            ai_rows,
            [
                ("AI finding ID", "AIFindingID"),
                ("Impact (`material` / `local`)", "Impact"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct style observation", "DirectStyleObservation"),
                ("Minimum editing action", "MinimumEditingAction"),
                ("Chair status", "ChairStatus"),
            ],
        ),
    )
    for first_header, csv_rows, mapping in specifications:
        parsed = parse_markdown_table_by_header(text, first_header, path.name, errors)
        if parsed is None:
            continue
        headers, rows = parsed
        expected_headers = [header for header, _field in mapping]
        if [value.casefold() for value in headers] != [
            value.casefold() for value in expected_headers
        ]:
            continue
        id_field = mapping[0][1]
        markdown_by_id = {
            row[0]: row for row in rows if len(row) == len(mapping)
        }
        for identifier in sorted(set(csv_rows) & set(markdown_by_id)):
            markdown_row = markdown_by_id[identifier]
            csv_row = csv_rows[identifier]
            for index, (_header, field) in enumerate(mapping):
                if markdown_row[index] != csv_row[field]:
                    errors.append(
                        f"{path.name}: Markdown/CSV value mismatch for "
                        f"{identifier}/{field}: expected {csv_row[field]!r}, "
                        f"got {markdown_row[index]!r}"
                    )


def validate_chair_ledger_markdown_values(
    path: Path,
    academic_rows: dict[str, dict[str, str]],
    ai_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    specifications = (
        (
            "Ledger ID", academic_rows,
            [
                ("Ledger ID", "LedgerID"), ("Priority", "Priority"),
                ("Chair finding ID", "ChairFindingID"),
                ("Source reviewer finding IDs", "SourceReviewerFindingIDs"),
                ("Severity", "Severity"), ("Remedy", "Remedy"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct observation", "DirectObservation"),
                ("Minimum edit/evidence", "MinimumEditEvidence"),
                ("Dependency", "Dependency"), ("Owner", "Owner"),
                ("Status", "Status"), ("Verification", "Verification"),
            ],
        ),
        (
            "AI finding ID", ai_rows,
            [
                ("AI finding ID", "AIFindingID"),
                ("Impact (`material` / `local`)", "Impact"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct style observation", "DirectStyleObservation"),
                ("Minimum editing action", "MinimumEditingAction"),
                ("Status", "Status"), ("Verification", "Verification"),
            ],
        ),
    )
    for first_header, csv_rows, mapping in specifications:
        parsed = parse_markdown_table_by_header(text, first_header, path.name, errors)
        if parsed is None:
            continue
        headers, rows = parsed
        expected_headers = [header for header, _field in mapping]
        if [value.casefold() for value in headers] != [
            value.casefold() for value in expected_headers
        ]:
            continue
        markdown_by_id = {
            row[0]: row for row in rows if len(row) == len(mapping)
        }
        for identifier in sorted(set(csv_rows) & set(markdown_by_id)):
            markdown_row = markdown_by_id[identifier]
            csv_row = csv_rows[identifier]
            for index, (_header, field) in enumerate(mapping):
                if markdown_row[index] != csv_row[field]:
                    errors.append(
                        f"{path.name}: Markdown/CSV value mismatch for "
                        f"{identifier}/{field}: expected {csv_row[field]!r}, "
                        f"got {markdown_row[index]!r}"
                    )


def validate_chair_finding_tables(
    path: Path,
    academic_rows: dict[str, dict[str, str]],
    ai_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    academic_headers = [
        "Chair finding ID", "Source reviewer finding IDs", "Severity", "Remedy",
        "Exact PDF anchor", "Direct observation", "Evidence status", "Owner",
        "Minimum required action", "Verification",
    ]
    parsed_academic = parse_markdown_table_by_exact_headers(
        text, academic_headers, path.name, errors
    )
    academic_by_chair_id = {
        row["ChairFindingID"]: row for row in academic_rows.values()
    }
    if parsed_academic is not None:
        markdown_by_id = {
            row[0]: row for row in parsed_academic if len(row) == len(academic_headers)
        }
        compare_sets(
            "chair adjudicated-finding rows",
            set(academic_by_chair_id),
            set(markdown_by_id),
            errors,
        )
        mapping = [
            "ChairFindingID", "SourceReviewerFindingIDs", "Severity", "Remedy",
            "ExactPDFAnchor", "DirectObservation", None, "Owner",
            "MinimumEditEvidence", "Verification",
        ]
        for identifier in sorted(set(academic_by_chair_id) & set(markdown_by_id)):
            csv_row = academic_by_chair_id[identifier]
            markdown_row = markdown_by_id[identifier]
            for index, field in enumerate(mapping):
                if field is not None and markdown_row[index] != csv_row[field]:
                    errors.append(
                        f"{path.name}: chair/91 value mismatch for "
                        f"{identifier}/{field}"
                    )
    ai_headers = [
        "AI finding ID", "Impact (`material` / `local`)", "Exact PDF anchor",
        "Direct style observation", "Minimum editing action", "Verification", "Status",
    ]
    parsed_ai = parse_markdown_table_by_exact_headers(
        text, ai_headers, path.name, errors
    )
    if parsed_ai is not None:
        markdown_by_id = {
            row[0]: row for row in parsed_ai if len(row) == len(ai_headers)
        }
        compare_sets(
            "chair AI-actionable rows",
            set(ai_rows),
            set(markdown_by_id),
            errors,
        )
        mapping = [
            "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
            "MinimumEditingAction", "Verification", "Status",
        ]
        for identifier in sorted(set(ai_rows) & set(markdown_by_id)):
            csv_row = ai_rows[identifier]
            markdown_row = markdown_by_id[identifier]
            for index, field in enumerate(mapping):
                if markdown_row[index] != csv_row[field]:
                    errors.append(
                        f"{path.name}: chair/91 AI value mismatch for "
                        f"{identifier}/{field}"
                    )


def validate_summary_report(
    path: Path,
    expected_pdf_hash: str,
    process: dict[str, Any],
    reviewer_count: int,
    expected_academic_rows: int,
    expected_ai_rows: int,
    errors: list[str],
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    required_headings = (
        "Clean-room identity",
        "Independent and overall conclusions",
        "Current actionable items",
        "Current AI-style actionable items",
        "Optional suggestions",
        "Unresolved questions and review limitations",
        "Reconciliation",
    )
    for heading in required_headings:
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}(?:\s+.*)?$", text):
            errors.append(f"{path.name}: missing section '{heading}'")
    round_id = labeled_value(text, "Review round ID")
    if round_id != str(process.get("round_id", "")):
        errors.append(
            f"{path.name}: Review round ID does not equal the process envelope"
        )
    frozen_identity = labeled_value(text, "Frozen PDF path and SHA-256") or ""
    frozen_name = str(process.get("frozen_pdf_file", ""))
    if frozen_name not in frozen_identity or expected_pdf_hash not in frozen_identity.upper():
        errors.append(
            f"{path.name}: Frozen PDF path and SHA-256 are not bound to the "
            "current process envelope"
        )
    allowlist_value = labeled_value(text, "Exact current-round input allowlist") or ""
    expected_allowlist = {
        "00-process-parameters.json",
        "SKILL.md",
        "clean-room-orchestration.md",
        "report-template.md",
        *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
        "05-ai-style-assessment.md",
        "90-chair-synthesis.md",
        "91-revision-ledger.md",
        "91-revision-ledger.csv",
        "91-ai-actionable-ledger.csv",
        "92-new-evidence-or-experiments.md",
    }
    observed_allowlist = {
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", allowlist_value)
        if token.strip()
    }
    if observed_allowlist != expected_allowlist:
        errors.append(
            f"{path.name}: Exact current-round input allowlist mismatch; "
            f"missing={sorted(expected_allowlist-observed_allowlist)}, "
            f"extra={sorted(observed_allowlist-expected_allowlist)}"
        )
    conclusion_table = parse_markdown_table_by_header(
        text, "Actor", path.name, errors
    )
    if conclusion_table is not None:
        headers, rows = conclusion_table
        expected_headers = [
            "Actor", "Persona/status", "Category or AI-style label",
            "Exact defense recommendation", "Confidence",
            "Decisive current-round basis",
        ]
        if [value.casefold() for value in headers] != [
            value.casefold() for value in expected_headers
        ]:
            errors.append(f"{path.name}: independent-conclusion table schema mismatch")
        actor_rows: dict[str, list[str]] = {}
        for row in rows:
            if len(row) != len(headers):
                continue
            if row[0] in actor_rows:
                errors.append(f"{path.name}: duplicate conclusion actor {row[0]!r}")
            actor_rows[row[0]] = row
        expected_actors = {
            *(f"R{index}" for index in range(1, reviewer_count + 1)),
            "AI", "Chair",
        }
        compare_sets(
            "Stage-S independent-conclusion actors",
            expected_actors,
            set(actor_rows),
            errors,
        )
        for actor, row in actor_rows.items():
            if len(row) == len(headers) and (len(row[1]) < 8 or len(row[5]) < 20):
                errors.append(f"{path.name}: {actor} conclusion row is shell-only")
        for index in range(1, reviewer_count + 1):
            actor = f"R{index}"
            report_path = path.parent / f"R{index}-comprehensive-review.md"
            if not report_path.is_file():
                continue
            report = report_path.read_text(encoding="utf-8", errors="replace")
            row = actor_rows.get(actor)
            if row:
                expected_grade = labeled_value(report, "Academic grade") or ""
                expected_rec = labeled_value(report, "Defense recommendation") or ""
                expected_conf = labeled_value(report, "Confidence") or ""
                expected_persona = labeled_value(report, "Persona emphasis") or ""
                expected_basis = (
                    labeled_value(report, "One-paragraph whole-thesis rationale") or ""
                )
                if (
                    row[1] != expected_persona
                    or row[2] != expected_grade
                    or row[3] != expected_rec
                    or row[4] != expected_conf
                    or row[5] != expected_basis
                ):
                    errors.append(
                        f"{path.name}: {actor} conclusion does not exactly copy "
                        "its independent current-round verdict"
                    )
        ai_text = (path.parent / "05-ai-style-assessment.md").read_text(
            encoding="utf-8", errors="replace"
        )
        ai_row = actor_rows.get("AI")
        if ai_row:
            expected_signal = labeled_value(ai_text, "AI-style signal") or ""
            expected_conf = labeled_value(ai_text, "Confidence") or ""
            expected_basis = labeled_value(ai_text, "Rationale") or ""
            if (
                ai_row[1] != "standalone AI-style assessment"
                or ai_row[2] != expected_signal
                or ai_row[3].casefold() != "n/a"
                or ai_row[4] != expected_conf
                or ai_row[5] != expected_basis
            ):
                errors.append(
                    f"{path.name}: AI conclusion does not exactly copy the "
                    "separate current-round style judgment"
                )
        chair_path = path.parent / "90-chair-synthesis.md"
        chair_text = chair_path.read_text(encoding="utf-8", errors="replace")
        chair_row = actor_rows.get("Chair")
        if chair_row:
            expected_grade = labeled_value(chair_text, "Overall academic grade") or ""
            expected_rec = labeled_value(chair_text, "Overall defense recommendation") or ""
            expected_conf = labeled_value(chair_text, "Confidence") or ""
            expected_basis = labeled_value(chair_text, "Whole-thesis rationale") or ""
            if (
                chair_row[1] != "chair adjudication"
                or chair_row[2] != expected_grade
                or chair_row[3] != expected_rec
                or chair_row[4] != expected_conf
                or chair_row[5] != expected_basis
            ):
                errors.append(
                    f"{path.name}: Chair conclusion does not exactly copy the "
                    "current-round chair verdict"
                )
        for summary_heading, chair_heading in (
            ("Optional suggestions", "Optional suggestions"),
            (
                "Unresolved questions and review limitations",
                "Review limitations",
            ),
        ):
            summary_body = markdown_section_body(text, summary_heading)
            chair_body = markdown_section_body(chair_text, chair_heading)
            if summary_body != chair_body:
                errors.append(
                    f"{path.name}: section {summary_heading!r} must be an "
                    f"exact current-round projection of chair section {chair_heading!r}"
                )
    academic_91 = parse_count_label(
        text, "Open required rows in 91-revision-ledger.md", path.name, errors
    )
    academic_93 = parse_count_label(
        text, "Rows in Current actionable items", path.name, errors
    )
    ai_91 = parse_count_label(
        text, "Open AI rows in 91-ai-actionable-ledger.csv", path.name, errors
    )
    ai_93 = parse_count_label(
        text, "Rows in Current AI-style actionable items", path.name, errors
    )
    for observed, expected, label in (
        (academic_91, expected_academic_rows, "91 academic"),
        (academic_93, expected_academic_rows, "93 academic"),
        (ai_91, expected_ai_rows, "91 AI"),
        (ai_93, expected_ai_rows, "93 AI"),
    ):
        if observed is not None and observed != expected:
            errors.append(
                f"{path.name}: {label} reconciliation count {observed} != CSV count {expected}"
            )
    for label in (
        "Missing ledger IDs",
        "Extra summary IDs",
        "Duplicate IDs",
        "Missing/extra/duplicate AI finding IDs",
    ):
        value = labeled_value(text, label)
        if value is None or value.casefold() != "none":
            errors.append(f"{path.name}: reconciliation '{label}' must be none")
    statement = (
        "this summary introduces no new finding and uses no prior-round "
        "or author-side information."
    )
    if statement not in text.casefold():
        errors.append(f"{path.name}: missing clean Stage-S non-invention statement")


def validate_helper_bundle(
    root: Path, expected_pdf_hash: str, errors: list[str]
) -> None:
    helpers = root / "helpers"
    if not helpers.exists():
        return
    if not helpers.is_dir():
        errors.append("helpers exists but is not a directory")
        return
    entries = list(helpers.iterdir())
    if not entries:
        errors.append("helpers: empty directory must be omitted")
        return
    files = sorted(path for path in entries if path.is_file())
    directories = sorted(path.name for path in entries if path.is_dir())
    if directories:
        errors.append(f"helpers: nested directories are not allowed: {directories}")
    provenance_files = [
        path for path in files
        if re.fullmatch(r"H\d{2}-provenance\.json", path.name)
    ]
    registered: Counter[str] = Counter()
    for provenance_path in provenance_files:
        try:
            data = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{provenance_path.name}: invalid provenance JSON: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{provenance_path.name}: provenance root must be an object")
            continue
        keys = set(data)
        if keys != HELPER_PROVENANCE_KEYS:
            errors.append(
                f"{provenance_path.name}: provenance schema mismatch; "
                f"missing={sorted(HELPER_PROVENANCE_KEYS-keys)}, "
                f"extra={sorted(keys-HELPER_PROVENANCE_KEYS)}"
            )
        for field in (
            "actor_id", "round_id", "retry_id", "fresh_context_declaration",
            "input_receipt_access_declaration", "tool", "version",
            "command_or_query",
        ):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip() or is_placeholder(value):
                errors.append(f"{provenance_path.name}: invalid/blank {field}")
        for field in (
            "received_blocks", "opened_inputs", "limitations", "recipient_stages",
        ):
            value = data.get(field)
            if not isinstance(value, list):
                errors.append(f"{provenance_path.name}: {field} must be an array")
            elif field in {
                "received_blocks", "opened_inputs", "recipient_stages",
            } and not value:
                errors.append(f"{provenance_path.name}: {field} must be non-empty")
        if not HEX64_RE.fullmatch(str(data.get("prompt_sha256") or "")):
            errors.append(f"{provenance_path.name}: prompt_sha256 is not 64 hex")
        for field in ("pdf_sha256_start", "pdf_sha256_end"):
            if str(data.get(field) or "").upper() != expected_pdf_hash:
                errors.append(f"{provenance_path.name}: {field} does not match frozen PDF")
        outputs = data.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            errors.append(f"{provenance_path.name}: outputs must be a non-empty array")
            continue
        for index, output in enumerate(outputs):
            if not isinstance(output, dict) or set(output) != HELPER_OUTPUT_KEYS:
                errors.append(
                    f"{provenance_path.name}: outputs[{index}] must contain exactly file,sha256"
                )
                continue
            filename = str(output.get("file") or "")
            if (
                not filename
                or Path(filename).name != filename
                or filename.endswith("-provenance.json")
            ):
                errors.append(
                    f"{provenance_path.name}: outputs[{index}].file must be a neutral sidecar basename"
                )
                continue
            registered[filename] += 1
            output_path = helpers / filename
            declared_hash = str(output.get("sha256") or "").upper()
            if not output_path.is_file():
                errors.append(f"{provenance_path.name}: missing helper output {filename}")
            elif not HEX64_RE.fullmatch(declared_hash):
                errors.append(f"{provenance_path.name}: invalid hash for {filename}")
            elif sha256(output_path) != declared_hash:
                errors.append(f"{provenance_path.name}: hash mismatch for {filename}")
    non_provenance = {
        path.name for path in files
        if not re.fullmatch(r"H\d{2}-provenance\.json", path.name)
    }
    if non_provenance and not provenance_files:
        errors.append("helpers: sidecars exist without any Hxx-provenance.json")
    for filename in sorted(non_provenance):
        count = registered.get(filename, 0)
        if count != 1:
            errors.append(
                f"helpers: {filename} must be registered exactly once; observed {count}"
            )
    for filename, count in sorted(registered.items()):
        if filename not in non_provenance:
            errors.append(f"helpers: registered output is absent: {filename}")
        if count > 1:
            errors.append(f"helpers: {filename} is multiply registered ({count})")


def validate_process(
    root: Path, errors: list[str]
) -> tuple[dict[str, Any], Path, str, int, int, list[tuple[float, float]]]:
    process_path = root / "00-process-parameters.json"
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read 00-process-parameters.json: {exc}")
        return {}, root / "__missing__.pdf", "", 0, 0, []
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return {}, root / "__missing__.pdf", "", 0, 0, []
    keys = set(process)
    if keys != PROCESS_KEYS:
        errors.append(
            "process envelope schema mismatch; "
            f"missing={sorted(PROCESS_KEYS-keys)}, extra={sorted(keys-PROCESS_KEYS)}"
        )
    for key in ("round_id", "retry_id", "output_language"):
        value = process.get(key)
        if not isinstance(value, str) or not value.strip() or is_placeholder(value):
            errors.append(f"process envelope has invalid/blank {key}")
    frozen_at = process.get("frozen_at")
    if not isinstance(frozen_at, str) or not frozen_at.strip():
        errors.append("process envelope has invalid/blank frozen_at")
    else:
        try:
            parsed_frozen_at = datetime.fromisoformat(
                frozen_at.strip().replace("Z", "+00:00")
            )
            if parsed_frozen_at.tzinfo is None:
                errors.append("frozen_at must include an explicit timezone")
        except ValueError:
            errors.append("frozen_at must be an ISO-8601 datetime with timezone")
    local_files = process.get("governing_local_files")
    if not isinstance(local_files, list):
        errors.append("governing_local_files must be a list")
    else:
        for index, item in enumerate(local_files):
            if not isinstance(item, dict):
                errors.append(f"governing_local_files[{index}] must be an object")
                continue
            if set(item) != {"neutral_file", "official_title", "sha256"}:
                errors.append(
                    f"governing_local_files[{index}] must contain exactly "
                    "neutral_file,official_title,sha256"
                )
            filename = str(item.get("neutral_file") or "")
            if not filename or Path(filename).name != filename:
                errors.append(
                    f"governing_local_files[{index}].neutral_file must be a neutral basename"
                )
                continue
            rule_path = root / filename
            declared = str(item.get("sha256") or "").upper()
            if not rule_path.is_file():
                errors.append(f"missing neutral governing file: {filename}")
            elif not HEX64_RE.fullmatch(declared) or sha256(rule_path) != declared:
                errors.append(f"neutral governing file hash mismatch: {filename}")
            title = item.get("official_title")
            if not isinstance(title, str) or not title.strip():
                errors.append(f"governing_local_files[{index}].official_title is blank")
    if not isinstance(process.get("governing_rule_urls"), list):
        errors.append("governing_rule_urls must be a list")
    frozen_name = str(process.get("frozen_pdf_file") or "")
    if not frozen_name or Path(frozen_name).name != frozen_name:
        errors.append("frozen_pdf_file must be one neutral basename")
        frozen_path = root / "__missing__.pdf"
    else:
        frozen_path = root / frozen_name
    expected_hash = str(process.get("selected_pdf_sha256") or "").upper()
    if not HEX64_RE.fullmatch(expected_hash):
        errors.append("selected_pdf_sha256 must be 64 hexadecimal characters")
    if not frozen_path.is_file():
        errors.append(f"missing frozen PDF: {frozen_name or '<unspecified>'}")
    elif HEX64_RE.fullmatch(expected_hash):
        actual = sha256(frozen_path)
        if actual != expected_hash:
            errors.append(
                f"frozen PDF hash mismatch: expected {expected_hash}, got {actual}"
            )
    page_count_raw = process.get("physical_page_count")
    if (
        not isinstance(page_count_raw, int)
        or isinstance(page_count_raw, bool)
        or page_count_raw < 1
    ):
        errors.append("physical_page_count must be a positive integer")
        page_count = 0
    else:
        page_count = page_count_raw
    pdf_page_sizes = (
        validate_pdf_structure_and_pages(frozen_path, page_count, errors)
        if frozen_path.is_file()
        else []
    )
    degree = str(process.get("degree_level") or "").casefold()
    if degree not in {"doctorate", "masters"}:
        errors.append("degree_level must be doctorate or masters for a complete panel")
        reviewer_count = 0
    else:
        reviewer_count = 5 if degree == "doctorate" else 3
    return (
        process, frozen_path, expected_hash, page_count, reviewer_count,
        pdf_page_sizes,
    )


def validate_rows_mandatory(
    rows: list[dict[str, str]],
    filename: str,
    mandatory_fields: Iterable[str],
    errors: list[str],
    *,
    blank_allowed: set[str] | None = None,
) -> None:
    allowed = blank_allowed or set()
    for line, row in enumerate(rows, start=2):
        for field in mandatory_fields:
            require_value(
                row, field, f"{filename}:{line}", errors,
                allow_blank=field in allowed,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args(argv)
    root = args.round_directory.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    process, frozen_path, expected_hash, page_count, reviewer_count, pdf_page_sizes = (
        validate_process(root, errors)
    )
    required_files = {
        "00-manifest.md", "00-page-inventory.csv",
        "00-bibliography-inventory.csv", "00-citation-candidate-ledger.csv",
        "00-unmatched-bracket-ledger.csv", "00-citation-inventory.csv",
        "01-policy-basis.md", "02-page-layout-ledger.md",
        "02-page-layout-ledger.csv", "03-bibliography-audit-ledger.md",
        "03-bibliography-audit-ledger.csv",
        "04-citation-claim-audit-ledger.md",
        "04-citation-claim-audit-ledger.csv",
        "05-ai-style-assessment.md", "90-chair-synthesis.md",
        "91-revision-ledger.md", "91-revision-ledger.csv",
        "91-ai-actionable-ledger.csv", "92-new-evidence-or-experiments.md",
        "93-user-facing-summary.md", "93-current-actionable-items.csv",
        "93-current-ai-actionable-items.csv",
    }
    required_files.update(
        f"R{i}-comprehensive-review.md" for i in range(1, reviewer_count + 1)
    )
    for filename in sorted(required_files):
        if not (root / filename).is_file():
            errors.append(f"missing required file: {filename}")

    page_inventory = read_csv(
        root / "00-page-inventory.csv", PAGE_INVENTORY_COLUMNS, errors,
        require_rows=True,
    )
    page_ledger = read_csv(
        root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, errors,
        require_rows=True,
    )
    validate_rows_mandatory(
        page_inventory, "00-page-inventory.csv", PAGE_INVENTORY_COLUMNS,
        errors, blank_allowed={"PrintedPage"},
    )
    validate_rows_mandatory(
        page_ledger, "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS,
        errors, blank_allowed={"PrintedPage"},
    )
    validate_pdf_hash(page_inventory, "00-page-inventory.csv", expected_hash, errors)
    validate_pdf_hash(page_ledger, "02-page-layout-ledger.csv", expected_hash, errors)
    page_inv_by_id = index_unique(
        page_inventory, "PageID", "00-page-inventory.csv", errors
    )
    page_led_by_id = index_unique(
        page_ledger, "PageID", "02-page-layout-ledger.csv", errors
    )
    compare_sets("page ledger", set(page_inv_by_id), set(page_led_by_id), errors)
    for index, row in enumerate(page_inventory, start=1):
        expected_page_id = f"P{index:04d}"
        if row["PageID"] != expected_page_id:
            errors.append(
                "00-page-inventory.csv: PageID sequence mismatch at row "
                f"{index + 1}; expected {expected_page_id}, got {row['PageID']!r}"
            )
    if page_count and len(page_inventory) != page_count:
        errors.append(
            f"00-page-inventory.csv: row count {len(page_inventory)} "
            f"!= physical_page_count {page_count}"
        )
    if page_count and len(page_ledger) != page_count:
        errors.append(
            f"02-page-layout-ledger.csv: row count {len(page_ledger)} "
            f"!= physical_page_count {page_count}"
        )
    physical_inventory: list[int] = []
    physical_ledger: list[int] = []
    render_dir = root / "page-renders"
    if not render_dir.is_dir():
        errors.append("missing required page-renders directory")
        render_files: dict[str, Path] = {}
    else:
        render_files = {path.stem: path for path in render_dir.glob("*.png")}
        unexpected = sorted(
            path.name for path in render_dir.iterdir()
            if not path.is_file() or path.suffix.casefold() != ".png"
        )
        if unexpected:
            errors.append(f"page-renders: unexpected entries {unexpected}")
    compare_sets(
        "page render files", set(page_inv_by_id), set(render_files), errors
    )
    for line, row in enumerate(page_inventory, start=2):
        try:
            physical_page_number = int(row["PhysicalPage"])
            physical_inventory.append(physical_page_number)
            page_match = PAGE_ID_RE.fullmatch(row["PageID"])
            if page_match and physical_page_number != int(page_match.group(1)):
                errors.append(
                    f"00-page-inventory.csv:{line}: {row['PageID']} must map "
                    f"to PhysicalPage {int(page_match.group(1))}, got "
                    f"{physical_page_number}"
                )
        except ValueError:
            errors.append(
                f"00-page-inventory.csv:{line}: invalid PhysicalPage "
                f"{row['PhysicalPage']!r}"
            )
    for line, row in enumerate(page_ledger, start=2):
        physical_page_number: int | None = None
        try:
            physical_page_number = int(row["PhysicalPage"])
            physical_ledger.append(physical_page_number)
            page_match = PAGE_ID_RE.fullmatch(row["PageID"])
            if page_match and physical_page_number != int(page_match.group(1)):
                errors.append(
                    f"02-page-layout-ledger.csv:{line}: {row['PageID']} must map "
                    f"to PhysicalPage {int(page_match.group(1))}, got "
                    f"{physical_page_number}"
                )
        except ValueError:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid PhysicalPage "
                f"{row['PhysicalPage']!r}"
            )
        mode = row["InspectionModeScale"].casefold()
        if not mode.startswith(INSPECTION_MODE_PREFIXES):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid "
                f"InspectionModeScale {row['InspectionModeScale']!r}"
            )
        signals = row["Signals"].casefold()
        mechanical = page_inv_by_id.get(row["PageID"], {}).get(
            "MechanicalSignals", ""
        ).casefold()
        suspect = any(
            value and value not in NON_SIGNAL_VALUES
            for value in (signals, mechanical)
        )
        if suspect and not mode.startswith("full-scale"):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: suspect page "
                f"{row['PageID']} was not inspected full-scale"
            )
        disposition = row["Disposition"].casefold()
        if any(token in disposition for token in ("pending", "unchecked", "recheck")):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: unresolved disposition "
                f"{row['Disposition']!r}"
            )
        render_dpi: int | None = None
        try:
            render_dpi = int(row["RenderDPI"])
            if render_dpi < 120 or render_dpi > 600:
                raise ValueError
        except ValueError:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: RenderDPI must be "
                "an integer in the auditable range 120..600"
            )
        render_pattern = re.compile(
            rf"^(?:{re.escape(row['PageID'])}[:/| -])?[0-9a-fA-F]{{64}}$"
        )
        if not render_pattern.fullmatch(row["RenderArtifactIDHash"]):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: "
                "RenderArtifactIDHash must be a 64-hex hash, optionally "
                "prefixed by the matching PageID"
            )
        render_path = render_files.get(row["PageID"])
        if render_path is not None:
            declared_match = HEX64_FIND_RE.search(row["RenderArtifactIDHash"])
            if declared_match and sha256(render_path) != declared_match.group(1).upper():
                errors.append(
                    f"02-page-layout-ledger.csv:{line}: render-file hash mismatch "
                    f"for {row['PageID']}"
                )
            dimensions = read_valid_png_dimensions(render_path, errors)
            if (
                dimensions is not None
                and render_dpi is not None
                and physical_page_number is not None
                and 1 <= physical_page_number <= len(pdf_page_sizes)
            ):
                width_points, height_points = pdf_page_sizes[physical_page_number - 1]
                expected_width = round(width_points * render_dpi / 72.0)
                expected_height = round(height_points * render_dpi / 72.0)
                if (
                    abs(dimensions[0] - expected_width) > 2
                    or abs(dimensions[1] - expected_height) > 2
                ):
                    errors.append(
                        f"{render_path.name}: pixel dimensions {dimensions} do not "
                        f"match page {physical_page_number} at {render_dpi} dpi "
                        f"({expected_width}, {expected_height})"
                    )
    expected_pages = list(range(1, page_count + 1)) if page_count else []
    if page_count and sorted(physical_inventory) != expected_pages:
        errors.append(
            "00-page-inventory.csv: PhysicalPage values are not exactly 1..N"
        )
    if page_count and sorted(physical_ledger) != expected_pages:
        errors.append(
            "02-page-layout-ledger.csv: PhysicalPage values are not exactly 1..N"
        )
    for page_id in sorted(set(page_inv_by_id) & set(page_led_by_id)):
        inv = page_inv_by_id[page_id]
        led = page_led_by_id[page_id]
        for field in ("PhysicalPage", "PrintedPage", "Region"):
            if inv[field] != led[field]:
                errors.append(
                    f"page mapping mismatch for {page_id}: {field} "
                    f"inventory={inv[field]!r}, ledger={led[field]!r}"
                )
    validate_markdown_id_projection(
        root / "02-page-layout-ledger.md",
        set(page_inv_by_id),
        re.compile(r"(?<![A-Za-z0-9])P\d{4}(?![A-Za-z0-9])"),
        {"Page ID", "PageID"},
        "page ledger",
        errors,
        required_headers={
            "Page ID", "Physical page", "Printed page", "Region",
            "Dominant content", "Signals", "Inspection mode/scale",
            "Render DPI", "Render artifact ID/hash", "Neighbor pages checked",
            "Disposition", "Evidence",
        },
    )

    bib_inventory = read_csv(
        root / "00-bibliography-inventory.csv", BIB_INVENTORY_COLUMNS,
        errors, require_rows=True,
    )
    validate_rows_mandatory(
        bib_inventory, "00-bibliography-inventory.csv",
        BIB_INVENTORY_COLUMNS, errors,
    )
    validate_pdf_hash(
        bib_inventory, "00-bibliography-inventory.csv", expected_hash, errors
    )

    citation_candidates = read_csv(
        root / "00-citation-candidate-ledger.csv",
        CITATION_CANDIDATE_COLUMNS,
        errors,
        require_rows=True,
    )
    validate_rows_mandatory(
        citation_candidates,
        "00-citation-candidate-ledger.csv",
        CITATION_CANDIDATE_COLUMNS,
        errors,
    )
    validate_pdf_hash(
        citation_candidates,
        "00-citation-candidate-ledger.csv",
        expected_hash,
        errors,
    )
    reference_pages: set[int] = set()
    for row in page_inventory:
        region = row.get("Region", "").strip().casefold()
        if (
            "reference" in region
            or "bibliograph" in region
            or "参考文献" in region
        ):
            try:
                reference_pages.add(int(row["PhysicalPage"]))
            except (TypeError, ValueError):
                pass
    reference_pages = derive_and_validate_reference_pages(
        frozen_path,
        reference_pages,
        bib_inventory,
        errors,
    ) if frozen_path.is_file() else set()
    extracted_candidates, extracted_unmatched_glyphs = (
        extract_numeric_bracket_candidates(frozen_path, reference_pages, errors)
        if frozen_path.is_file()
        else ([], [])
    )
    unmatched_rows = read_csv(
        root / "00-unmatched-bracket-ledger.csv",
        UNMATCHED_BRACKET_COLUMNS,
        errors,
        require_rows=bool(extracted_unmatched_glyphs),
    )
    validate_rows_mandatory(
        unmatched_rows,
        "00-unmatched-bracket-ledger.csv",
        UNMATCHED_BRACKET_COLUMNS,
        errors,
    )
    validate_pdf_hash(
        unmatched_rows,
        "00-unmatched-bracket-ledger.csv",
        expected_hash,
        errors,
    )
    if len(unmatched_rows) != len(extracted_unmatched_glyphs):
        errors.append(
            "00-unmatched-bracket-ledger.csv: row count does not equal the "
            "validator's frozen-PDF unmatched-glyph extraction; "
            f"ledger={len(unmatched_rows)}, extracted={len(extracted_unmatched_glyphs)}"
        )
    for index, row in enumerate(unmatched_rows, start=1):
        line = index + 1
        expected_id = f"UBG{index:04d}"
        if row["GlyphID"] != expected_id:
            errors.append(
                f"00-unmatched-bracket-ledger.csv:{line}: GlyphID must be "
                f"{expected_id}, got {row['GlyphID']!r}"
            )
        if index <= len(extracted_unmatched_glyphs):
            extracted = extracted_unmatched_glyphs[index - 1]
            try:
                physical_page = int(row["PhysicalPage"])
            except (TypeError, ValueError):
                physical_page = -1
            if physical_page != extracted["PhysicalPage"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: PhysicalPage "
                    "does not match the frozen-PDF extraction"
                )
            if row["Glyph"] != extracted["Glyph"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: Glyph does not "
                    "match the frozen-PDF extraction"
                )
            if normalize_extracted_text(row["AdjacentPDFText"]) != extracted["Adjacent"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: AdjacentPDFText "
                    "does not exactly match the deterministic extraction window"
                )
        disposition = row["Disposition"].strip().casefold()
        if (
            len(disposition) < 12
            or is_placeholder(disposition)
            or re.search(r"\b(?:none|no unmatched|zero)\b", disposition)
        ):
            errors.append(
                f"00-unmatched-bracket-ledger.csv:{line}: Disposition must "
                "give a concrete non-contradictory glyph adjudication"
            )
    if len(citation_candidates) != len(extracted_candidates):
        errors.append(
            "00-citation-candidate-ledger.csv: row count does not equal the "
            "validator's frozen-PDF extraction; "
            f"ledger={len(citation_candidates)}, extracted={len(extracted_candidates)}"
        )
    candidate_occurrence_numbers: dict[str, list[int]] = {}
    candidate_occurrence_pages: dict[str, int] = {}
    candidate_occurrence_contexts: dict[str, str] = {}
    citation_candidate_count = 0
    for index, row in enumerate(citation_candidates, start=1):
        line = index + 1
        expected_id = f"BC{index:04d}"
        if row["CandidateID"] != expected_id:
            errors.append(
                "00-citation-candidate-ledger.csv: CandidateID sequence mismatch "
                f"at row {line}; expected {expected_id}, got {row['CandidateID']!r}"
            )
        if not BRACKET_CANDIDATE_ID_RE.fullmatch(row["CandidateID"]):
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid CandidateID"
            )
        try:
            physical_page = int(row["PhysicalPage"])
        except (TypeError, ValueError):
            physical_page = -1
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid PhysicalPage"
            )
        marker = normalize_numeric_marker(row["Marker"])
        parsed_numbers = expand_numeric_marker(row["Marker"])
        if parsed_numbers is None:
            declared_numbers: list[int] | None = None
            if row["ExpandedNumbers"] != "N/A":
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: mixed/decimal "
                    "numeric bracket must use ExpandedNumbers=N/A"
                )
        else:
            try:
                declared_numbers = [
                    int(item) for item in row["ExpandedNumbers"].split(";")
                ]
            except (TypeError, ValueError):
                declared_numbers = []
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: ExpandedNumbers "
                    "must be a semicolon-separated integer sequence"
                )
            canonical_expansion = ";".join(
                str(value) for value in parsed_numbers
            )
            if row["ExpandedNumbers"] != canonical_expansion:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: ExpandedNumbers "
                    f"must equal canonical expansion {canonical_expansion!r}"
                )
            if declared_numbers != parsed_numbers:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: numeric expansion "
                    "does not match Marker"
                )
        if index <= len(extracted_candidates):
            extracted = extracted_candidates[index - 1]
            if physical_page != extracted["PhysicalPage"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: PhysicalPage "
                    f"{physical_page} != extracted {extracted['PhysicalPage']}"
                )
            if marker != extracted["Marker"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: Marker {marker!r} "
                    f"!= extracted {extracted['Marker']!r}"
                )
            if parsed_numbers != extracted["Expanded"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: expansion does "
                    "not equal the frozen-PDF extraction"
                )
            if normalize_extracted_text(row["AdjacentPDFText"]) != extracted["Adjacent"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: AdjacentPDFText "
                    "does not exactly match the deterministic frozen-PDF window"
                )
        classification = row["Classification"].strip().casefold()
        if classification not in CANDIDATE_CLASSIFICATIONS:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid "
                f"Classification {row['Classification']!r}"
            )
        evidence = row["ClassificationEvidence"].strip()
        if len(evidence) < 12 or evidence.casefold() in {
            "citation", "non-citation", "checked", "verified"
        }:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: "
                "ClassificationEvidence is not a concrete contextual reason"
            )
        if index <= len(extracted_candidates):
            obvious_reason = obvious_non_citation_reason(
                extracted_candidates[index - 1]
            )
            if obvious_reason and classification != "non-citation":
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: obvious "
                    f"non-citation classified as citation ({obvious_reason})"
                )
        mapped = row["MappedOccurrenceID"].strip()
        if classification == "citation":
            citation_candidate_count += 1
            expected_occurrence = f"C{citation_candidate_count:04d}"
            if parsed_numbers is None:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: citation "
                    "classification requires a pure integer citation marker"
                )
            if mapped != expected_occurrence:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: citation "
                    f"candidate must map to {expected_occurrence}, got {mapped!r}"
                )
            if mapped in candidate_occurrence_numbers:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: duplicate "
                    f"MappedOccurrenceID {mapped}"
                )
            candidate_occurrence_numbers[mapped] = parsed_numbers or []
            candidate_occurrence_pages[mapped] = physical_page
            candidate_occurrence_contexts[mapped] = normalize_extracted_text(
                row["AdjacentPDFText"]
            )
        elif classification == "non-citation" and mapped != "N/A":
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: non-citation must "
                "use MappedOccurrenceID=N/A"
            )

    bib_ledger = read_csv(
        root / "03-bibliography-audit-ledger.csv", BIB_LEDGER_COLUMNS,
        errors, require_rows=True,
    )
    validate_rows_mandatory(
        bib_ledger, "03-bibliography-audit-ledger.csv",
        BIB_LEDGER_COLUMNS, errors,
        blank_allowed={"EvidenceEndpoint"},
    )
    validate_pdf_hash(
        bib_ledger, "03-bibliography-audit-ledger.csv", expected_hash, errors
    )
    bib_inv_by_id = index_unique(
        bib_inventory, "ReferenceID", "00-bibliography-inventory.csv", errors
    )
    bib_refs_in_ledger = {
        row["ReferenceID"] for row in bib_ledger if row["ReferenceID"]
    }
    compare_sets(
        "bibliography ledger", set(bib_inv_by_id), bib_refs_in_ledger, errors
    )
    for index, row in enumerate(bib_inventory, start=1):
        expected_ref_id = f"REF{index:04d}"
        if row["ReferenceID"] != expected_ref_id:
            errors.append(
                "00-bibliography-inventory.csv: ReferenceID sequence mismatch "
                f"at row {index + 1}; expected {expected_ref_id}, "
                f"got {row['ReferenceID']!r}"
            )
    fields_by_ref: dict[str, set[str]] = defaultdict(set)
    bib_keys: Counter[tuple[str, str]] = Counter()
    for line, row in enumerate(bib_ledger, start=2):
        ref = row["ReferenceID"]
        field = row["Field"]
        fields_by_ref[ref].add(field)
        bib_keys[(ref, field)] += 1
        verdict = row["Verdict"].casefold()
        if verdict not in BIB_VERDICTS:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid verdict "
                f"{row['Verdict']!r}"
            )
        if verdict != "unverifiable" and not row["EvidenceEndpoint"]:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "verified verdict lacks authoritative evidence endpoint"
            )
        if (
            verdict != "unverifiable"
            and row["EvidenceEndpoint"]
            and not PUBLIC_URL_RE.search(row["EvidenceEndpoint"])
        ):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "EvidenceEndpoint lacks an http(s) authoritative record"
            )
        if not validate_iso_date(row["CheckedAt"]):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "CheckedAt must be an ISO-8601 date or datetime"
            )
        if field not in BIB_FIELDS:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid field {field!r}"
            )
        inv = bib_inv_by_id.get(ref)
        if inv:
            for ledger_field, inventory_field in (
                ("DisplayedLabel", "DisplayedLabel"), ("Cited", "Cited"),
            ):
                if row[ledger_field] != inv[inventory_field]:
                    errors.append(
                        f"bibliography mapping mismatch for {ref}/{field}: "
                        f"{ledger_field}={row[ledger_field]!r}, "
                        f"inventory={inv[inventory_field]!r}"
                    )
        if (
            verdict == "unverifiable"
            and row["EvidenceNote"].casefold() in {"n/a", "none"}
        ):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "unverifiable row lacks attempted-route note"
            )
    duplicate_bib_keys = sorted(
        key for key, count in bib_keys.items() if count > 1
    )
    if duplicate_bib_keys:
        errors.append(
            "03-bibliography-audit-ledger.csv: duplicate "
            f"(ReferenceID,Field) keys {duplicate_bib_keys}"
        )
    for ref in sorted(bib_inv_by_id):
        actual_fields = fields_by_ref[ref]
        if actual_fields != BIB_FIELDS:
            errors.append(
                f"03-bibliography-audit-ledger.csv: {ref} field-set mismatch; "
                f"missing={sorted(BIB_FIELDS-actual_fields)}, "
                f"extra={sorted(actual_fields-BIB_FIELDS)}"
            )
    validate_markdown_id_projection(
        root / "03-bibliography-audit-ledger.md",
        set(bib_inv_by_id),
        re.compile(r"(?<![A-Za-z0-9])REF\d{4}(?![A-Za-z0-9])"),
        {"Reference ID", "ReferenceID"},
        "bibliography ledger",
        errors,
        required_headers={
            "Reference ID", "Displayed label", "Cited?", "Type", "Title",
            "Ordered authors", "Year", "Venue", "Publication status",
            "Volume/issue", "Pages/article no.",
            "Persistent IDs/URL/access date", "Existence",
            "Retraction/correction/superseding", "Finding/disposition",
        },
    )

    citation_inventory = read_csv(
        root / "00-citation-inventory.csv", CITATION_INVENTORY_COLUMNS,
        errors, require_rows=True,
    )
    citation_ledger = read_csv(
        root / "04-citation-claim-audit-ledger.csv",
        CITATION_LEDGER_COLUMNS, errors, require_rows=True,
    )
    validate_rows_mandatory(
        citation_inventory, "00-citation-inventory.csv",
        CITATION_INVENTORY_COLUMNS, errors,
    )
    validate_rows_mandatory(
        citation_ledger, "04-citation-claim-audit-ledger.csv",
        CITATION_LEDGER_COLUMNS, errors,
        blank_allowed={"ContentSourceOpened", "ExactSourceLocator"},
    )
    validate_pdf_hash(
        citation_inventory, "00-citation-inventory.csv", expected_hash, errors
    )
    validate_pdf_hash(
        citation_ledger, "04-citation-claim-audit-ledger.csv",
        expected_hash, errors,
    )
    citation_inv_by_pair = index_unique(
        citation_inventory, "PairID", "00-citation-inventory.csv", errors
    )
    citation_led_by_pair = index_unique(
        citation_ledger, "PairID",
        "04-citation-claim-audit-ledger.csv", errors,
    )
    compare_sets(
        "citation-claim ledger", set(citation_inv_by_pair),
        set(citation_led_by_pair), errors,
    )
    current_occurrence = 0
    current_source_ordinal = 0
    inventory_occurrence_numbers: dict[str, list[int]] = defaultdict(list)
    for line, row in enumerate(citation_inventory, start=2):
        occurrence_match = OCCURRENCE_ID_RE.fullmatch(row["OccurrenceID"])
        pair_match = PAIR_ID_RE.fullmatch(row["PairID"])
        if not occurrence_match or not pair_match:
            errors.append(
                f"00-citation-inventory.csv:{line}: invalid deterministic "
                "OccurrenceID/PairID format"
            )
            continue
        occurrence_number = int(occurrence_match.group(1))
        pair_occurrence = int(pair_match.group(1))
        source_ordinal = int(pair_match.group(2))
        if pair_occurrence != occurrence_number:
            errors.append(
                f"00-citation-inventory.csv:{line}: PairID occurrence does not "
                "match OccurrenceID"
            )
        if occurrence_number == current_occurrence:
            current_source_ordinal += 1
        elif occurrence_number == current_occurrence + 1:
            current_occurrence = occurrence_number
            current_source_ordinal = 1
        else:
            errors.append(
                f"00-citation-inventory.csv:{line}: occurrence IDs are not "
                "continuous in reading order"
            )
            current_occurrence = occurrence_number
            current_source_ordinal = 1
        if source_ordinal != current_source_ordinal:
            errors.append(
                f"00-citation-inventory.csv:{line}: source ordinals are not "
                "continuous within the occurrence"
            )
        reference_match = REFERENCE_ID_RE.fullmatch(
            row["DisplayedReferenceID"]
        )
        if not reference_match:
            errors.append(
                f"00-citation-inventory.csv:{line}: invalid "
                "DisplayedReferenceID"
            )
        else:
            inventory_occurrence_numbers[row["OccurrenceID"]].append(
                int(reference_match.group(1))
            )
        expected_page = candidate_occurrence_pages.get(row["OccurrenceID"])
        located_page = parse_physical_page_locator(row["PDFLocation"])
        if located_page is None:
            errors.append(
                f"00-citation-inventory.csv:{line}: PDFLocation must contain "
                "an explicit physical page"
            )
        elif located_page < 1 or (page_count and located_page > page_count):
            errors.append(
                f"00-citation-inventory.csv:{line}: physical page "
                f"{located_page} is outside 1..{page_count}"
            )
        elif expected_page is not None and located_page != expected_page:
            errors.append(
                f"00-citation-inventory.csv:{line}: PDFLocation page "
                f"{located_page} != candidate page {expected_page}"
            )
        expected_context = candidate_occurrence_contexts.get(row["OccurrenceID"])
        if (
            expected_context is not None
            and normalize_extracted_text(row["AdjacentPDFText"]) != expected_context
        ):
            errors.append(
                f"00-citation-inventory.csv:{line}: AdjacentPDFText does not "
                "exactly equal the mapped candidate's frozen-PDF context"
            )
    compare_sets(
        "citation candidate-to-inventory occurrence mapping",
        set(candidate_occurrence_numbers),
        set(inventory_occurrence_numbers),
        errors,
    )
    for occurrence_id in sorted(
        set(candidate_occurrence_numbers) & set(inventory_occurrence_numbers)
    ):
        if (
            candidate_occurrence_numbers[occurrence_id]
            != inventory_occurrence_numbers[occurrence_id]
        ):
            errors.append(
                "citation candidate-to-inventory number mismatch for "
                f"{occurrence_id}: candidate="
                f"{candidate_occurrence_numbers[occurrence_id]}, inventory="
                f"{inventory_occurrence_numbers[occurrence_id]}"
            )
    cited_reference_ids = {
        row["DisplayedReferenceID"] for row in citation_inventory
        if REFERENCE_ID_RE.fullmatch(row["DisplayedReferenceID"])
    }
    for line, row in enumerate(bib_inventory, start=2):
        expected_cited = "yes" if row["ReferenceID"] in cited_reference_ids else "no"
        if row["Cited"].strip().casefold() != expected_cited:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: Cited must be "
                f"{expected_cited!r} from the reconciled citation inventory"
            )
    for pair_id in sorted(
        set(citation_inv_by_pair) & set(citation_led_by_pair)
    ):
        inv = citation_inv_by_pair[pair_id]
        led = citation_led_by_pair[pair_id]
        for ledger_field, inventory_field in (
            ("OccurrenceID", "OccurrenceID"),
            ("ReferenceID", "DisplayedReferenceID"),
            ("PDFLocation", "PDFLocation"),
        ):
            if led[ledger_field] != inv[inventory_field]:
                errors.append(
                    f"citation mapping mismatch for {pair_id}: "
                    f"{ledger_field}={led[ledger_field]!r}, "
                    f"inventory={inv[inventory_field]!r}"
                )
    for line, row in enumerate(citation_ledger, start=2):
        support = row["Support"].casefold()
        if support not in SUPPORT_VALUES:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: invalid support "
                f"{row['Support']!r}"
            )
        if support in {"direct", "partial", "context-only", "mismatch"}:
            if (
                not row["ContentSourceOpened"]
                or row["ContentSourceOpened"].casefold() in {"n/a", "none"}
            ):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "substantive verdict lacks content source"
                )
            elif not PUBLIC_URL_RE.search(row["ContentSourceOpened"]):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "ContentSourceOpened lacks an http(s) content endpoint"
                )
            if (
                not row["ExactSourceLocator"]
                or row["ExactSourceLocator"].casefold() in {"n/a", "none"}
            ):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "substantive verdict lacks exact locator"
                )
            elif not SOURCE_LOCATOR_RE.search(row["ExactSourceLocator"]):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "ExactSourceLocator lacks a page/section/content locator"
                )
        if row["ReferenceID"] not in bib_inv_by_id:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: "
                f"unknown ReferenceID {row['ReferenceID']!r}"
            )
    validate_markdown_id_projection(
        root / "04-citation-claim-audit-ledger.md",
        set(citation_inv_by_pair),
        re.compile(r"(?<![A-Za-z0-9])C\d{4}-S\d{2}(?![A-Za-z0-9])"),
        {"Pair ID", "PairID"},
        "citation-claim ledger",
        errors,
        required_headers={
            "Pair ID", "Occurrence ID", "PDF location",
            "Exact attached proposition", "Reference ID", "Displayed label",
            "Public source/identifier",
            "Content source opened and exact locator", "Support",
            "Metadata/status", "Severity/finding", "Disposition/evidence",
        },
    )

    academic_ledger = read_csv(
        root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS,
        errors, require_rows=False,
    )
    ai_ledger = read_csv(
        root / "91-ai-actionable-ledger.csv", AI_LEDGER_COLUMNS,
        errors, require_rows=False,
    )
    validate_rows_mandatory(
        academic_ledger, "91-revision-ledger.csv",
        ACADEMIC_LEDGER_COLUMNS, errors,
    )
    validate_rows_mandatory(
        ai_ledger, "91-ai-actionable-ledger.csv",
        AI_LEDGER_COLUMNS, errors,
    )
    academic_by_id = index_unique(
        academic_ledger, "LedgerID", "91-revision-ledger.csv", errors
    )
    ai_by_id = index_unique(
        ai_ledger, "AIFindingID", "91-ai-actionable-ledger.csv", errors
    )
    for line, row in enumerate(academic_ledger, start=2):
        if not re.fullmatch(r"L\d{2,4}", row["LedgerID"]):
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid LedgerID {row['LedgerID']!r}"
            )
        if row["Severity"].casefold() not in ACADEMIC_SEVERITIES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Severity "
                f"{row['Severity']!r}"
            )
        if row["Remedy"].casefold() not in ACADEMIC_REMEDIES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Remedy "
                f"{row['Remedy']!r}"
            )
        if row["Priority"].casefold() not in ACADEMIC_PRIORITIES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Priority "
                f"{row['Priority']!r}"
            )
        if row["Status"].casefold() not in STATUS_VALUES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Status "
                f"{row['Status']!r}"
            )
    for line, row in enumerate(ai_ledger, start=2):
        if not re.fullmatch(r"AI-F\d{2,4}", row["AIFindingID"]):
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: invalid AIFindingID "
                f"{row['AIFindingID']!r}"
            )
        if row["Impact"].casefold() not in AI_ACTION_IMPACTS:
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: invalid Impact "
                f"{row['Impact']!r}"
            )
        if row["Status"].casefold() not in STATUS_VALUES:
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: invalid Status "
                f"{row['Status']!r}"
            )
    validate_markdown_id_projection(
        root / "91-revision-ledger.md",
        set(academic_by_id),
        re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
        {"Ledger ID", "LedgerID"},
        "chair academic revision ledger",
        errors,
        required_headers={
            "Ledger ID", "Priority", "Chair finding ID",
            "Source reviewer finding IDs", "Severity", "Remedy",
            "Exact PDF anchor", "Direct observation", "Minimum edit/evidence",
            "Dependency", "Owner", "Status", "Verification",
        },
    )
    validate_markdown_id_projection(
        root / "91-revision-ledger.md",
        set(ai_by_id),
        re.compile(r"(?<![A-Za-z0-9])AI-F\d{2,4}(?![A-Za-z0-9])"),
        {"AI finding ID", "AIFindingID"},
        "chair AI-actionable ledger",
        errors,
        required_headers={
            "AI finding ID", "Impact (`material` / `local`)",
            "Exact PDF anchor", "Direct style observation",
            "Minimum editing action", "Status", "Verification",
        },
    )
    validate_chair_ledger_markdown_values(
        root / "91-revision-ledger.md",
        academic_by_id,
        ai_by_id,
        errors,
    )
    validate_chair_finding_tables(
        root / "90-chair-synthesis.md",
        academic_by_id,
        ai_by_id,
        errors,
    )
    open_academic = {
        ledger_id: row for ledger_id, row in academic_by_id.items()
        if row["Status"].casefold() not in CLOSED_STATUSES
    }
    open_ai = {
        finding_id: row for finding_id, row in ai_by_id.items()
        if row["Status"].casefold() not in CLOSED_STATUSES
    }
    academic_summary = read_csv(
        root / "93-current-actionable-items.csv",
        ACADEMIC_SUMMARY_COLUMNS, errors,
        require_rows=bool(open_academic),
    )
    ai_summary = read_csv(
        root / "93-current-ai-actionable-items.csv",
        AI_SUMMARY_COLUMNS, errors, require_rows=bool(open_ai),
    )
    validate_rows_mandatory(
        academic_summary, "93-current-actionable-items.csv",
        ACADEMIC_SUMMARY_COLUMNS, errors,
    )
    validate_rows_mandatory(
        ai_summary, "93-current-ai-actionable-items.csv",
        AI_SUMMARY_COLUMNS, errors,
    )
    academic_summary_by_id = index_unique(
        academic_summary, "LedgerID",
        "93-current-actionable-items.csv", errors,
    )
    ai_summary_by_id = index_unique(
        ai_summary, "AIFindingID",
        "93-current-ai-actionable-items.csv", errors,
    )
    compare_sets(
        "current academic summary", set(open_academic),
        set(academic_summary_by_id), errors,
    )
    compare_sets(
        "current AI-actionable summary", set(open_ai),
        set(ai_summary_by_id), errors,
    )
    for ledger_id in sorted(
        set(open_academic) & set(academic_summary_by_id)
    ):
        ledger = open_academic[ledger_id]
        summary = academic_summary_by_id[ledger_id]
        expected_mapping = {
            "CurrentFindingIDs": ledger["ChairFindingID"],
            "SeverityRemedy": f"{ledger['Severity']}/{ledger['Remedy']}",
            "ExactPDFAnchor": ledger["ExactPDFAnchor"],
            "DirectPDFObservation": ledger["DirectObservation"],
            "MinimumRequiredAction": ledger["MinimumEditEvidence"],
            "OriginReviewers": ledger["SourceReviewerFindingIDs"],
            "ChairDisposition": ledger["Status"],
        }
        for field, expected_value in expected_mapping.items():
            if summary[field] != expected_value:
                errors.append(
                    f"academic 91->93 mismatch for {ledger_id}/{field}: "
                    f"expected {expected_value!r}, got {summary[field]!r}"
                )
    for finding_id in sorted(set(open_ai) & set(ai_summary_by_id)):
        ledger = open_ai[finding_id]
        summary = ai_summary_by_id[finding_id]
        expected_mapping = {
            "Impact": ledger["Impact"],
            "ExactPDFAnchor": ledger["ExactPDFAnchor"],
            "DirectStyleObservation": ledger["DirectStyleObservation"],
            "MinimumEditingAction": ledger["MinimumEditingAction"],
            "ChairStatus": ledger["Status"],
        }
        for field, expected_value in expected_mapping.items():
            if summary[field] != expected_value:
                errors.append(
                    f"AI 91->93 mismatch for {finding_id}/{field}: "
                    f"expected {expected_value!r}, got {summary[field]!r}"
                )
    validate_markdown_id_projection(
        root / "93-user-facing-summary.md",
        set(open_academic),
        re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
        {"Ledger ID", "LedgerID"},
        "Stage-S current academic summary",
        errors,
        required_headers={
            "Ledger ID", "Current finding ID(s)", "Severity / remedy",
            "Exact PDF anchor", "Direct PDF-visible observation",
            "Minimum required action", "Origin reviewer(s)",
            "Chair disposition",
        },
    )
    validate_markdown_id_projection(
        root / "93-user-facing-summary.md",
        set(open_ai),
        re.compile(r"(?<![A-Za-z0-9])AI-F\d{2,4}(?![A-Za-z0-9])"),
        {"AI finding ID", "AIFindingID"},
        "Stage-S current AI summary",
        errors,
        required_headers={
            "AI finding ID", "Impact (`material` / `local`)",
            "Exact PDF anchor", "Direct style observation",
            "Minimum editing action", "Chair status",
        },
    )
    validate_summary_markdown_values(
        root / "93-user-facing-summary.md",
        academic_summary_by_id,
        ai_summary_by_id,
        errors,
    )

    evidence_path = root / "92-new-evidence-or-experiments.md"
    if evidence_path.is_file():
        evidence_text = evidence_path.read_text(encoding="utf-8", errors="replace")
        for heading in (
            "No-new-experiment remedies (W/E/P)",
            "Genuine new experiments or unavailable evidence (N)",
        ):
            if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", evidence_text):
                errors.append(f"{evidence_path.name}: missing required section {heading!r}")
        experiment_table = parse_markdown_table_by_header(
            evidence_text, "Item", evidence_path.name, errors
        )
        if experiment_table is not None:
            headers, _rows = experiment_table
            expected_headers = [
                "Item", "Claim that depends on it", "Why writing is insufficient",
                "Minimum viable evidence", "Consequence if unavailable",
            ]
            if [value.casefold() for value in headers] != [
                value.casefold() for value in expected_headers
            ]:
                errors.append(f"{evidence_path.name}: N-evidence table schema mismatch")

    if expected_hash:
        manifest_text = validate_declarations(
            root / "00-manifest.md", expected_hash, errors
        )
        if manifest_text:
            manifest_counts = {
                "Numeric-bracket candidate rows": len(citation_candidates),
                "Citation-classified candidate rows": sum(
                    row["Classification"].strip().casefold() == "citation"
                    for row in citation_candidates
                ),
                "Non-citation-classified candidate rows": sum(
                    row["Classification"].strip().casefold() == "non-citation"
                    for row in citation_candidates
                ),
                "Unmatched square-bracket glyphs": len(extracted_unmatched_glyphs),
            }
            for label, expected_count in manifest_counts.items():
                observed = parse_count_label(
                    manifest_text, label, "00-manifest.md", errors
                )
                if observed is not None and observed != expected_count:
                    errors.append(
                        f"00-manifest.md: {label} {observed} != "
                        f"validated {expected_count}"
                    )
            unmatched_disposition = labeled_value(
                manifest_text, "Unmatched glyph dispositions"
            )
            if (
                not unmatched_disposition
                or len(unmatched_disposition) < 12
                or is_placeholder(unmatched_disposition)
            ):
                errors.append(
                    "00-manifest.md: Unmatched glyph dispositions must "
                    "record a concrete rendered-context audit result"
                )
            elif not extracted_unmatched_glyphs:
                if not re.search(
                    r"(?i)(?:\bnone\b|no unmatched|\b0\b)",
                    unmatched_disposition,
                ):
                    errors.append(
                        "00-manifest.md: zero unmatched glyphs require an "
                        "explicit none-found disposition"
                    )
            elif (
                re.search(
                    r"(?i)(?:\bnone\b|no unmatched|none found|\bzero\b)",
                    unmatched_disposition,
                )
                or "00-unmatched-bracket-ledger.csv" not in unmatched_disposition
                or not re.search(
                    rf"(?<!\d){len(extracted_unmatched_glyphs)}(?!\d)",
                    unmatched_disposition,
                )
            ):
                errors.append(
                    "00-manifest.md: positive unmatched-glyph count requires a "
                    "non-contradictory count and 00-unmatched-bracket-ledger.csv reference"
                )
            manifest_frozen_at = labeled_value(manifest_text, "Frozen at")
            if manifest_frozen_at != str(process.get("frozen_at", "")):
                errors.append(
                    "00-manifest.md: Frozen at must exactly equal process-envelope frozen_at"
                )
        validate_declarations(root / "01-policy-basis.md", expected_hash, errors)
        for owned_path in (
            "02-page-layout-ledger.md",
            "03-bibliography-audit-ledger.md",
            "04-citation-claim-audit-ledger.md",
            "91-revision-ledger.md",
            "92-new-evidence-or-experiments.md",
        ):
            validate_declarations(root / owned_path, expected_hash, errors)
        for index in range(1, reviewer_count + 1):
            validate_reviewer_report(
                root / f"R{index}-comprehensive-review.md",
                expected_hash,
                index,
                process.get("degree_level") if isinstance(process, dict) else None,
                errors,
            )
        validate_ai_report(
            root / "05-ai-style-assessment.md", expected_hash, errors
        )
        validate_chair_report(
            root / "90-chair-synthesis.md",
            expected_hash,
            len({
                row["DisplayedReferenceID"]
                for row in citation_inventory
                if row["DisplayedReferenceID"]
            }),
            reviewer_count,
            errors,
        )
        validate_summary_report(
            root / "93-user-facing-summary.md", expected_hash,
            process, reviewer_count, len(open_academic), len(open_ai), errors,
        )
        validate_helper_bundle(root, expected_hash, errors)

    status = "PASS" if not errors else "FAIL"
    lines = [
        "# Mechanical thesis-review bundle validation", "",
        f"- Result: **{status}**",
        f"- Round directory: {root}",
        f"- Frozen PDF SHA-256: {expected_hash or 'missing'}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        "- Boundary: mechanical validation only; semantic reviewer sign-off "
        "remains mandatory.",
        "", "## Errors", "",
        *(f"- {item}" for item in errors),
        *(["- none"] if not errors else []),
        "", "## Warnings", "",
        *(f"- {item}" for item in warnings),
        *(["- none"] if not warnings else []), "",
    ]
    report = "\n".join(lines)
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(report, encoding="utf-8")
    print(report)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
