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
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEX64_FIND_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])")

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
PLACEHOLDERS = {"pending", "unchecked", "...", "…", "todo", "tbd"}
NON_SIGNAL_VALUES = {
    "none", "clean", "no signal", "no signals", "n/a", "not applicable",
}
INSPECTION_MODE_PREFIXES = ("individual", "small-legible-group", "full-scale")

PROCESS_KEYS = {
    "round_id", "retry_id", "frozen_pdf_file", "selected_pdf_sha256",
    "physical_page_count", "degree_level", "degree_type", "institution",
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


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
    elif value and is_placeholder(value):
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
    if "input-receipt/access declaration" not in lower:
        errors.append(f"{path.name}: missing input-receipt/access declaration")
    if "received" not in lower or "opened" not in lower:
        errors.append(f"{path.name}: input receipt does not name received/opened inputs")
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
    path: Path, expected_pdf_hash: str, errors: list[str]
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    for gate in "ABCDEFGHI":
        pattern = rf"(?im)^\|\s*{gate}\s*(?:[—-]|\|)"
        if len(re.findall(pattern, text)) != 1:
            errors.append(
                f"{path.name}: Gate {gate} must appear exactly once as a matrix row"
            )
    if not re.search(
        r"(?im)^\s*-\s*Academic grade:\s*(?:A|B|C|D|N/?A)\b", text
    ):
        errors.append(f"{path.name}: missing explicit academic grade")
    if not re.search(r"(?im)^\s*-\s*Defense recommendation:\s*\S", text):
        errors.append(f"{path.name}: missing explicit defense recommendation")


def labeled_value(text: str, label: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*-\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text
    )
    return match.group(1).strip() if match else None


def validate_chair_report(
    path: Path, expected_pdf_hash: str, errors: list[str]
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    if not re.search(
        r"(?im)^##\s+Mandatory citation cross-ledger consistency gate\s*$", text
    ):
        errors.append(f"{path.name}: missing mandatory citation cross-ledger section")
    for label in (
        "Unique cited rendered references joined",
        "Identity-agreement count",
        "Version disagreements",
        "Local conflicts",
        "Substantive conflicts",
        "Reclassified Pair IDs",
        "Unresolved conflicts",
    ):
        value = labeled_value(text, label)
        if value is None or not value or is_placeholder(value):
            errors.append(f"{path.name}: missing/nonfinal cross-ledger value '{label}'")
    gate = labeled_value(text, "Combined citation gate")
    if gate is None or gate.casefold() not in {"pass", "fail"}:
        errors.append(f"{path.name}: Combined citation gate must be pass or fail")
    if not re.search(
        r"(?im)^\s*-\s*Overall academic grade:\s*(?:A|B|C|D|N/?A)\b", text
    ):
        errors.append(f"{path.name}: missing overall academic grade")
    if not re.search(
        r"(?im)^\s*-\s*Overall defense recommendation:\s*\S", text
    ):
        errors.append(f"{path.name}: missing overall defense recommendation")


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


def validate_summary_report(
    path: Path,
    expected_pdf_hash: str,
    expected_academic_rows: int,
    expected_ai_rows: int,
    errors: list[str],
) -> None:
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    for heading in (
        "Current actionable items",
        "Current AI-style actionable items",
        "Reconciliation",
    ):
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}(?:\s+.*)?$", text):
            errors.append(f"{path.name}: missing section '{heading}'")
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
) -> tuple[dict[str, Any], Path, str, int, int]:
    process_path = root / "00-process-parameters.json"
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read 00-process-parameters.json: {exc}")
        return {}, root / "__missing__.pdf", "", 0, 0
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return {}, root / "__missing__.pdf", "", 0, 0
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
    degree = str(process.get("degree_level") or "").casefold()
    if degree not in {"doctorate", "masters"}:
        errors.append("degree_level must be doctorate or masters for a complete panel")
        reviewer_count = 0
    else:
        reviewer_count = 5 if degree == "doctorate" else 3
    return process, frozen_path, expected_hash, page_count, reviewer_count


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
    process, _frozen_path, expected_hash, page_count, reviewer_count = (
        validate_process(root, errors)
    )
    required_files = {
        "00-manifest.md", "00-page-inventory.csv",
        "00-bibliography-inventory.csv", "00-citation-inventory.csv",
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
    for line, row in enumerate(page_inventory, start=2):
        try:
            physical_inventory.append(int(row["PhysicalPage"]))
        except ValueError:
            errors.append(
                f"00-page-inventory.csv:{line}: invalid PhysicalPage "
                f"{row['PhysicalPage']!r}"
            )
    for line, row in enumerate(page_ledger, start=2):
        try:
            physical_ledger.append(int(row["PhysicalPage"]))
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
        try:
            if int(row["RenderDPI"]) <= 0:
                raise ValueError
        except ValueError:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: RenderDPI must be "
                "a positive integer"
            )
        if not HEX64_FIND_RE.search(row["RenderArtifactIDHash"]):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: "
                "RenderArtifactIDHash lacks a 64-hex hash"
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

    bib_inventory = read_csv(
        root / "00-bibliography-inventory.csv", BIB_INVENTORY_COLUMNS,
        errors, require_rows=True,
    )
    bib_ledger = read_csv(
        root / "03-bibliography-audit-ledger.csv", BIB_LEDGER_COLUMNS,
        errors, require_rows=True,
    )
    validate_rows_mandatory(
        bib_inventory, "00-bibliography-inventory.csv",
        BIB_INVENTORY_COLUMNS, errors,
    )
    validate_rows_mandatory(
        bib_ledger, "03-bibliography-audit-ledger.csv",
        BIB_LEDGER_COLUMNS, errors,
    )
    validate_pdf_hash(
        bib_inventory, "00-bibliography-inventory.csv", expected_hash, errors
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
            if row["ContentSourceOpened"].casefold() in {"n/a", "none"}:
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "substantive verdict lacks content source"
                )
            if row["ExactSourceLocator"].casefold() in {"n/a", "none"}:
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "substantive verdict lacks exact locator"
                )
        if row["ReferenceID"] not in bib_inv_by_id:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: "
                f"unknown ReferenceID {row['ReferenceID']!r}"
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

    if expected_hash:
        validate_declarations(root / "00-manifest.md", expected_hash, errors)
        validate_declarations(root / "01-policy-basis.md", expected_hash, errors)
        for index in range(1, reviewer_count + 1):
            validate_reviewer_report(
                root / f"R{index}-comprehensive-review.md",
                expected_hash, errors,
            )
        validate_ai_report(
            root / "05-ai-style-assessment.md", expected_hash, errors
        )
        validate_chair_report(
            root / "90-chair-synthesis.md", expected_hash, errors
        )
        validate_summary_report(
            root / "93-user-facing-summary.md", expected_hash,
            len(open_academic), len(open_ai), errors,
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
