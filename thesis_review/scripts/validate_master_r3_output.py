#!/usr/bin/env python3
"""Read-only mechanical gate for one master's R3 output set.

In a master's round R3 owns all three exhaustive audit deliverables: rendered
pages, bibliography integrity, and citation-claim support.  This scoped gate
therefore validates the frozen Stage-P packet, R3's comprehensive report,
02/03/04 Markdown and CSV masters, and page renders without opening or
requiring R1/R2, AI, Chair, Stage-S, Stage-V, or prior-round artifacts.

The sibling full validator remains authoritative.  This file deliberately
does not patch, replace, suppress, or rewrite it.  Full canonical-receipt
support requires ``canonical_stage_opened_inputs`` in that sibling to include
``MASTER_R3_VALIDATOR_RULE_INPUTS`` at the ordinary validator insertion point.
Until that shared integration exists, this gate fails closed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ACTOR_ID = "R3"
REVIEWER_INDEX = 3
DEGREE_LEVEL = "masters"
REVIEWER_COUNT = 3
VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
PACKET_VALIDATOR = Path(__file__).with_name("validate_r5_output.py")
VALIDATOR_RULE_INPUTS = (
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/materialize_owner_outputs.py",
    "rules/scripts/validate_r5_output.py",
    "rules/scripts/validate_master_r3_output.py",
)
REQUIRED_FILES = (
    "00-process-parameters.json",
    "00-manifest.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
    "01-policy-basis.md",
    "02-page-layout-ledger.md",
    "02-page-layout-ledger.csv",
    "03-bibliography-audit-ledger.md",
    "03-bibliography-audit-ledger.csv",
    "04-citation-claim-audit-ledger.md",
    "04-citation-claim-audit-ledger.csv",
    "R3-comprehensive-review.md",
)


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def print_result(errors: list[str]) -> int:
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("PASS")
    print(
        "Current master's R3 report, 02/03/04 ledgers, page renders, "
        "receipts, owner links, and upstream packet passed the read-only "
        "mechanical gate."
    )
    return 0


def validate_canonical_support(
    module: Any,
    process: dict[str, Any],
    root: Path,
    errors: list[str],
) -> None:
    """Fail closed until the shared canonical receipt includes this gate."""

    opened = module.canonical_stage_opened_inputs(
        process, REVIEWER_COUNT, ACTOR_ID, root
    )
    insertion = 2 + len(module.SKILL_REFERENCE_FILES)
    observed = tuple(opened[insertion:insertion + len(VALIDATOR_RULE_INPUTS)])
    if observed != VALIDATOR_RULE_INPUTS:
        errors.append(
            "shared canonical masters/R3 allowlist lacks the required ordered "
            f"validator-rule insertion {list(VALIDATOR_RULE_INPUTS)}"
        )


def safe_dynamic_round_basename(module: Any, value: Any) -> bool:
    local_reserved = {
        module.portable_basename_key(Path(token).name)
        for token in VALIDATOR_RULE_INPUTS
    }
    return (
        isinstance(value, str)
        and module.is_neutral_portable_basename(value)
        and module.portable_basename_key(value)
        not in module.RESERVED_ROUND_BASENAME_KEYS | local_reserved
        and module.RENDER_ARTIFACT_BASENAME_RE.fullmatch(value) is None
    )


def preflight_exact_inputs(
    module: Any, root: Path, errors: list[str]
) -> dict[str, Any] | None:
    """Inspect exact R3-owned paths without enumerating the bundle root."""

    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append(
            "round directory is missing or is a symlink/junction/reparse point"
        )
        return None
    process_path = root / "00-process-parameters.json"
    if module.is_link_or_reparse(process_path) or not process_path.is_file():
        errors.append(
            "missing or unsafe required master R3 input: "
            "00-process-parameters.json"
        )
        return None
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot safely preflight 00-process-parameters.json: {exc}")
        return None
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return None

    exact_paths = [root / filename for filename in REQUIRED_FILES]
    frozen_name = process.get("frozen_pdf_file")
    if safe_dynamic_round_basename(module, frozen_name):
        exact_paths.append(root / frozen_name)
    elif frozen_name is not None:
        errors.append(
            "frozen_pdf_file is unsafe or collides with a reserved round basename"
        )
    local_files = process.get("governing_local_files")
    if isinstance(local_files, list):
        for item in local_files:
            filename = item.get("neutral_file") if isinstance(item, dict) else None
            if safe_dynamic_round_basename(module, filename):
                exact_paths.append(root / filename)
            elif filename is not None:
                errors.append(
                    "governing_local_files contains an unsafe or reserved "
                    "neutral_file"
                )

    for path in exact_paths:
        if module.is_link_or_reparse(path) or not path.is_file():
            errors.append(
                f"missing or unsafe required master R3 input: {path.name}"
            )
    for directory_name in ("page-renders", "helpers"):
        directory = root / directory_name
        if module.is_link_or_reparse(directory):
            errors.append(f"{directory_name} is an unsafe alias or not a directory")
            continue
        if not directory.exists():
            continue
        if not directory.is_dir():
            errors.append(f"{directory_name} is an unsafe alias or not a directory")
            continue
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            errors.append(f"cannot enumerate authorized {directory_name}: {exc}")
            continue
        aliases = sorted(
            child.name for child in children if module.is_link_or_reparse(child)
        )
        if aliases:
            errors.append(f"{directory_name} contains unsafe aliases: {aliases}")
    return process if not errors else None


def validate_page_outputs(
    module: Any,
    root: Path,
    expected_hash: str,
    page_count: int,
    pdf_page_sizes: list[tuple[float, float]],
    page_inventory: list[dict[str, str]],
    page_ledger: list[dict[str, str]],
    errors: list[str],
) -> None:
    module.validate_rows_mandatory(
        page_inventory,
        "00-page-inventory.csv",
        module.PAGE_INVENTORY_COLUMNS,
        errors,
        blank_allowed={"PrintedPage"},
    )
    module.validate_rows_mandatory(
        page_ledger,
        "02-page-layout-ledger.csv",
        module.PAGE_LEDGER_COLUMNS,
        errors,
        blank_allowed={"PrintedPage"},
    )
    module.validate_pdf_hash(
        page_inventory, "00-page-inventory.csv", expected_hash, errors
    )
    module.validate_pdf_hash(
        page_ledger, "02-page-layout-ledger.csv", expected_hash, errors
    )
    inventory_by_id = module.index_unique(
        page_inventory, "PageID", "00-page-inventory.csv", errors
    )
    ledger_by_id = module.index_unique(
        page_ledger, "PageID", "02-page-layout-ledger.csv", errors
    )
    module.compare_sets(
        "page ledger", set(inventory_by_id), set(ledger_by_id), errors
    )
    if len(page_inventory) != page_count:
        errors.append(
            "00-page-inventory.csv: row count does not equal physical_page_count"
        )
    if len(page_ledger) != page_count:
        errors.append(
            "02-page-layout-ledger.csv: row count does not equal physical_page_count"
        )
    for index, row in enumerate(page_inventory, start=1):
        if row.get("PageID") != f"P{index:04d}":
            errors.append(
                f"00-page-inventory.csv:{index + 1}: PageID sequence mismatch"
            )

    render_directory = root / "page-renders"
    if module.is_link_or_reparse(render_directory) or not render_directory.is_dir():
        errors.append("missing required page-renders directory")
        render_files: dict[str, Path] = {}
    else:
        render_files = {
            path.stem: path
            for path in render_directory.glob("*.png")
            if path.is_file() and not module.is_link_or_reparse(path)
        }
        unexpected = sorted(
            path.name
            for path in render_directory.iterdir()
            if (
                module.is_link_or_reparse(path)
                or not path.is_file()
                or path.suffix.casefold() != ".png"
            )
        )
        if unexpected:
            errors.append(f"page-renders: unexpected entries {unexpected}")
    module.compare_sets(
        "page render files", set(inventory_by_id), set(render_files), errors
    )

    physical_inventory: list[int] = []
    physical_ledger: list[int] = []
    for line, row in enumerate(page_inventory, start=2):
        try:
            physical_page = int(row.get("PhysicalPage", ""))
            physical_inventory.append(physical_page)
        except ValueError:
            errors.append(f"00-page-inventory.csv:{line}: invalid PhysicalPage")
            continue
        page_match = module.PAGE_ID_RE.fullmatch(row.get("PageID", ""))
        if page_match and physical_page != int(page_match.group(1)):
            errors.append(
                f"00-page-inventory.csv:{line}: PageID/PhysicalPage mismatch"
            )
    for line, row in enumerate(page_ledger, start=2):
        physical_page: int | None = None
        try:
            physical_page = int(row.get("PhysicalPage", ""))
            physical_ledger.append(physical_page)
        except ValueError:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid PhysicalPage"
            )
        page_match = module.PAGE_ID_RE.fullmatch(row.get("PageID", ""))
        if (
            page_match is not None
            and physical_page is not None
            and physical_page != int(page_match.group(1))
        ):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: PageID/PhysicalPage mismatch"
            )
        mode = row.get("InspectionModeScale", "").casefold()
        if not mode.startswith(module.INSPECTION_MODE_PREFIXES):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid InspectionModeScale"
            )
        signals = row.get("Signals", "").casefold()
        mechanical = inventory_by_id.get(row.get("PageID", ""), {}).get(
            "MechanicalSignals", ""
        ).casefold()
        suspect = any(
            value and value not in module.NON_SIGNAL_VALUES
            for value in (signals, mechanical)
        )
        if suspect and not mode.startswith("full-scale"):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: suspect page was not "
                "inspected full-scale"
            )
        disposition = row.get("Disposition", "").strip()
        if (
            disposition.casefold() not in {"clean", "intentional"}
            and re.fullmatch(
                rf"(?i)finding[ \t]+{ACTOR_ID}-F\d{{2,4}}", disposition
            )
            is None
        ):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: final Disposition must be "
                f"exactly clean, intentional, or finding {ACTOR_ID}-Fxx"
            )
        try:
            render_dpi = int(row.get("RenderDPI", ""))
            if render_dpi < 120 or render_dpi > 600:
                raise ValueError
        except ValueError:
            render_dpi = None
            errors.append(
                f"02-page-layout-ledger.csv:{line}: RenderDPI must be in 120..600"
            )
        render_pattern = re.compile(
            rf"^(?:{re.escape(row.get('PageID', ''))}[:/| -])?"
            r"[0-9a-fA-F]{64}$"
        )
        if render_pattern.fullmatch(row.get("RenderArtifactIDHash", "")) is None:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid RenderArtifactIDHash"
            )
        render_path = render_files.get(row.get("PageID", ""))
        if render_path is not None:
            declared = module.HEX64_FIND_RE.search(
                row.get("RenderArtifactIDHash", "")
            )
            if (
                declared is not None
                and module.sha256(render_path) != declared.group(1).upper()
            ):
                errors.append(
                    f"02-page-layout-ledger.csv:{line}: render-file hash mismatch"
                )
            dimensions = module.read_valid_png_dimensions(render_path, errors)
            if (
                dimensions is not None
                and render_dpi is not None
                and physical_page is not None
                and 1 <= physical_page <= len(pdf_page_sizes)
            ):
                width_points, height_points = pdf_page_sizes[physical_page - 1]
                expected_dimensions = (
                    round(width_points * render_dpi / 72.0),
                    round(height_points * render_dpi / 72.0),
                )
                if any(
                    abs(observed - expected) > 2
                    for observed, expected in zip(dimensions, expected_dimensions)
                ):
                    errors.append(
                        f"{render_path.name}: pixel dimensions do not match PDF "
                        "page size and RenderDPI"
                    )
    expected_pages = list(range(1, page_count + 1))
    if sorted(physical_inventory) != expected_pages:
        errors.append(
            "00-page-inventory.csv: PhysicalPage values are not exactly 1..N"
        )
    if sorted(physical_ledger) != expected_pages:
        errors.append(
            "02-page-layout-ledger.csv: PhysicalPage values are not exactly 1..N"
        )
    for page_id in set(inventory_by_id) & set(ledger_by_id):
        for field in ("PhysicalPage", "PrintedPage", "Region"):
            if inventory_by_id[page_id].get(field) != ledger_by_id[page_id].get(
                field
            ):
                errors.append(f"page mapping mismatch for {page_id}: {field}")
    module.validate_page_audit_specificity(
        page_ledger,
        inventory_by_id,
        "02-page-layout-ledger.csv",
        errors,
    )
    module.validate_markdown_id_projection(
        root / "02-page-layout-ledger.md",
        set(inventory_by_id),
        re.compile(r"(?<![A-Za-z0-9])P\d{4}(?![A-Za-z0-9])"),
        {"Page ID", "PageID"},
        "page ledger",
        errors,
        required_headers=set(module.PAGE_MARKDOWN_HEADERS),
        same_row_id_headers={"Render artifact ID/hash"},
        reference_id_headers={"Neighbor pages checked", "Evidence"},
    )
    module.validate_markdown_csv_projection(
        root / "02-page-layout-ledger.md",
        module.PAGE_MARKDOWN_HEADERS,
        module.page_markdown_projection_rows(page_ledger),
        "page-ledger",
        errors,
    )


def validate_bibliography_outputs(
    module: Any,
    root: Path,
    expected_hash: str,
    bibliography_inventory: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    citation_inventory: list[dict[str, str]],
    errors: list[str],
) -> None:
    module.validate_rows_mandatory(
        bibliography_inventory,
        "00-bibliography-inventory.csv",
        module.BIB_INVENTORY_COLUMNS,
        errors,
    )
    module.validate_rows_mandatory(
        bibliography_ledger,
        "03-bibliography-audit-ledger.csv",
        module.BIB_LEDGER_COLUMNS,
        errors,
    )
    module.validate_bibliography_endpoint_records(
        bibliography_ledger, "03-bibliography-audit-ledger.csv", errors
    )
    module.validate_reference_ids_only_in_id_column(
        bibliography_ledger, "03-bibliography-audit-ledger.csv", errors
    )
    module.validate_pdf_hash(
        bibliography_inventory,
        "00-bibliography-inventory.csv",
        expected_hash,
        errors,
    )
    module.validate_pdf_hash(
        bibliography_ledger,
        "03-bibliography-audit-ledger.csv",
        expected_hash,
        errors,
    )
    inventory_by_reference = module.index_unique(
        bibliography_inventory,
        "ReferenceID",
        "00-bibliography-inventory.csv",
        errors,
    )
    module.validate_bibliography_source_identity(
        bibliography_ledger,
        inventory_by_reference,
        "03-bibliography-audit-ledger.csv",
        errors,
    )
    module.validate_bibliography_field_semantics(
        bibliography_ledger,
        inventory_by_reference,
        "03-bibliography-audit-ledger.csv",
        errors,
    )
    ledger_reference_ids = {
        row.get("ReferenceID", "")
        for row in bibliography_ledger
        if row.get("ReferenceID", "")
    }
    module.compare_sets(
        "bibliography ledger",
        set(inventory_by_reference),
        ledger_reference_ids,
        errors,
    )
    for index, row in enumerate(bibliography_inventory, start=1):
        if row.get("ReferenceID") != f"REF{index:04d}":
            errors.append(
                f"00-bibliography-inventory.csv:{index + 1}: "
                "ReferenceID sequence mismatch"
            )
    cited_ids = {
        row.get("DisplayedReferenceID", "")
        for row in citation_inventory
        if module.REFERENCE_ID_RE.fullmatch(row.get("DisplayedReferenceID", ""))
    }
    for line, row in enumerate(bibliography_inventory, start=2):
        expected_cited = "yes" if row.get("ReferenceID") in cited_ids else "no"
        if row.get("Cited", "").strip().casefold() != expected_cited:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: Cited must be "
                f"{expected_cited!r} from 00-citation-inventory.csv"
            )

    expected_order = [
        (f"REF{reference_number:04d}", field)
        for reference_number in range(1, len(bibliography_inventory) + 1)
        for field in module.BIB_FIELD_ORDER
    ]
    observed_order = [
        (row.get("ReferenceID", ""), row.get("Field", ""))
        for row in bibliography_ledger
    ]
    if observed_order != expected_order:
        errors.append(
            "03-bibliography-audit-ledger.csv: source row order must be "
            "REF0001..REFNNNN in canonical field order"
        )
    fields_by_reference: dict[str, set[str]] = defaultdict(set)
    key_counts: Counter[tuple[str, str]] = Counter()
    exact_owner_link = re.compile(rf"{ACTOR_ID}-(?:F|Q)\d{{2,4}}")
    for line, row in enumerate(bibliography_ledger, start=2):
        reference_id = row.get("ReferenceID", "")
        field = row.get("Field", "")
        fields_by_reference[reference_id].add(field)
        key_counts[(reference_id, field)] += 1
        verdict = row.get("Verdict", "").casefold()
        if verdict not in module.BIB_VERDICTS:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid Verdict"
            )
        endpoint = row.get("EvidenceEndpoint", "")
        if endpoint and module.PUBLIC_URL_RE.fullmatch(endpoint) is None:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: EvidenceEndpoint "
                "must be one complete http(s) URL"
            )
        if not module.validate_iso_date(row.get("CheckedAt", "")):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid CheckedAt"
            )
        if field not in module.BIB_FIELDS:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid Field"
            )
        inventory_row = inventory_by_reference.get(reference_id)
        if inventory_row is not None:
            for ledger_field, inventory_field in (
                ("DisplayedLabel", "DisplayedLabel"),
                ("Cited", "Cited"),
            ):
                if row.get(ledger_field) != inventory_row.get(inventory_field):
                    errors.append(
                        f"bibliography mapping mismatch for {reference_id}/{field}: "
                        f"{ledger_field}"
                    )
        if verdict == "unverifiable" and row.get(
            "EvidenceNote", ""
        ).casefold() in {"n/a", "none"}:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: unverifiable row "
                "lacks an attempted-route note"
            )
        if verdict == "mismatch" and exact_owner_link.fullmatch(
            row.get("FindingDisposition", "").strip()
        ) is None:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: mismatch "
                f"FindingDisposition must be exactly one current {ACTOR_ID}-Fxx "
                f"or {ACTOR_ID}-Qxx ID, with no none/N/A/prose/second ID"
            )
    if any(count > 1 for count in key_counts.values()):
        errors.append(
            "03-bibliography-audit-ledger.csv: duplicate (ReferenceID,Field) keys"
        )
    for reference_id in inventory_by_reference:
        if fields_by_reference[reference_id] != module.BIB_FIELDS:
            errors.append(
                f"03-bibliography-audit-ledger.csv: {reference_id} field-set mismatch"
            )
    module.validate_markdown_id_projection(
        root / "03-bibliography-audit-ledger.md",
        set(inventory_by_reference),
        re.compile(r"(?<![A-Za-z0-9])REF\d{4}(?![A-Za-z0-9])"),
        {"Reference ID", "ReferenceID"},
        "bibliography ledger",
        errors,
        required_headers=set(module.BIB_MARKDOWN_HEADERS),
    )
    module.validate_markdown_csv_projection(
        root / "03-bibliography-audit-ledger.md",
        module.BIB_MARKDOWN_HEADERS,
        module.bibliography_markdown_projection_rows(
            bibliography_inventory, bibliography_ledger
        ),
        "bibliography-ledger",
        errors,
    )


def validate_citation_outputs(
    module: Any,
    root: Path,
    expected_hash: str,
    citation_inventory: list[dict[str, str]],
    bibliography_inventory: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
    errors: list[str],
) -> None:
    module.validate_rows_mandatory(
        citation_ledger,
        "04-citation-claim-audit-ledger.csv",
        module.CITATION_LEDGER_COLUMNS,
        errors,
        blank_allowed={"ContentSourceOpened", "ExactSourceLocator"},
    )
    module.validate_citation_endpoint_records(
        citation_ledger, "04-citation-claim-audit-ledger.csv", errors
    )
    module.validate_pdf_hash(
        citation_ledger,
        "04-citation-claim-audit-ledger.csv",
        expected_hash,
        errors,
    )
    inventory_by_pair = module.index_unique(
        citation_inventory,
        "PairID",
        "00-citation-inventory.csv",
        errors,
    )
    ledger_by_pair = module.index_unique(
        citation_ledger,
        "PairID",
        "04-citation-claim-audit-ledger.csv",
        errors,
    )
    bibliography_by_id = module.index_unique(
        bibliography_inventory,
        "ReferenceID",
        "00-bibliography-inventory.csv",
        errors,
    )
    module.validate_citation_source_identity(
        citation_ledger,
        bibliography_by_id,
        "04-citation-claim-audit-ledger.csv",
        errors,
    )
    module.validate_citation_unverifiable_semantics(
        citation_ledger,
        "04-citation-claim-audit-ledger.csv",
        errors,
    )
    module.compare_sets(
        "citation-claim ledger", set(inventory_by_pair), set(ledger_by_pair), errors
    )
    module.validate_citation_pair_row_order(
        citation_inventory, citation_ledger, errors
    )
    for pair_id in sorted(set(inventory_by_pair) & set(ledger_by_pair)):
        inventory = inventory_by_pair[pair_id]
        ledger = ledger_by_pair[pair_id]
        for ledger_field, inventory_field in (
            ("OccurrenceID", "OccurrenceID"),
            ("ReferenceID", "DisplayedReferenceID"),
            ("PDFLocation", "PDFLocation"),
        ):
            if ledger.get(ledger_field) != inventory.get(inventory_field):
                errors.append(
                    f"citation mapping mismatch for {pair_id}: "
                    f"{ledger_field}={ledger.get(ledger_field)!r}, "
                    f"inventory={inventory.get(inventory_field)!r}"
                )

    citation_link_re = re.compile(
        rf"(?<![A-Za-z0-9]){ACTOR_ID}-(?:F|Q)\d{{2,4}}(?![A-Za-z0-9])"
    )
    reasoned_nonfinding_re = re.compile(
        r"(?is)\breasoned[ -]non-finding\s*:\s*\S.{19,}"
    )
    for line, row in enumerate(citation_ledger, start=2):
        support = row.get("Support", "").casefold()
        metadata_status = row.get("MetadataStatus", "").casefold()
        if support not in module.SUPPORT_VALUES:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: invalid support "
                f"{row.get('Support', '')!r}"
            )
        if metadata_status not in module.METADATA_STATUS_VALUES:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: invalid "
                f"MetadataStatus {row.get('MetadataStatus', '')!r}"
            )
        if support in {"direct", "partial", "context-only", "mismatch"}:
            content_source = row.get("ContentSourceOpened", "")
            locator = row.get("ExactSourceLocator", "")
            if not content_source or content_source.casefold() in {"n/a", "none"}:
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: substantive "
                    "verdict lacks content source"
                )
            elif not module.PUBLIC_URL_RE.search(content_source):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "ContentSourceOpened lacks an http(s) content endpoint"
                )
            if not locator or locator.casefold() in {"n/a", "none"}:
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: substantive "
                    "verdict lacks exact locator"
                )
            elif not module.SOURCE_LOCATOR_RE.search(locator):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "ExactSourceLocator lacks a page/section/content locator"
                )
        module.validate_dangling_citation_audit_row(
            row, bibliography_by_id, line, errors
        )
        requires_disposition = (
            support
            in {"partial", "context-only", "mismatch", "unverifiable", "not-needed"}
            or metadata_status in {"mismatch", "unverifiable"}
        )
        disposition_text = (
            f"{row.get('SeverityFinding', '')} "
            f"{row.get('DispositionEvidence', '')}"
        )
        has_owner_link = bool(citation_link_re.search(disposition_text))
        has_reasoned_nonfinding = bool(
            reasoned_nonfinding_re.search(row.get("DispositionEvidence", ""))
        )
        hard_mismatch = support == "mismatch" or metadata_status == "mismatch"
        if hard_mismatch and not has_owner_link:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: mismatch row must "
                f"link an owning-reviewer {ACTOR_ID}-Fxx or {ACTOR_ID}-Qxx "
                "disposition; a reasoned non-finding cannot waive a contradiction"
            )
        elif requires_disposition and not (
            has_owner_link or has_reasoned_nonfinding
        ):
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: non-ideal "
                "support/metadata row must link an owning-reviewer "
                f"{ACTOR_ID}-Fxx or {ACTOR_ID}-Qxx disposition, or use an "
                "explicit substantive 'reasoned non-finding:' explanation"
            )

    module.validate_markdown_id_projection(
        root / "04-citation-claim-audit-ledger.md",
        set(inventory_by_pair),
        module.PAIR_ID_TOKEN_RE,
        {"Pair ID", "PairID"},
        "citation-claim ledger",
        errors,
        required_headers=set(module.CITATION_MARKDOWN_HEADERS),
    )
    module.validate_markdown_csv_projection(
        root / "04-citation-claim-audit-ledger.md",
        module.CITATION_MARKDOWN_HEADERS,
        module.citation_markdown_projection_rows(
            citation_ledger, bibliography_by_id
        ),
        "citation-claim-ledger",
        errors,
    )


def validate_report_links(
    module: Any,
    report_path: Path,
    page_count: int,
    page_ledger: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
    errors: list[str],
) -> None:
    visible = module.markdown_visible_text(
        report_path.read_text(encoding="utf-8", errors="replace")
    )
    findings = module.parse_reviewer_findings(
        visible, REVIEWER_INDEX, report_path.name, page_count, []
    )
    questions = module.parse_reviewer_questions(
        visible, REVIEWER_INDEX, report_path.name, page_count, []
    )
    page_links = module.page_layout_finding_ids(page_ledger)
    foreign_page_links = sorted(
        identifier for identifier in page_links
        if not identifier.startswith(f"{ACTOR_ID}-")
    )
    if foreign_page_links:
        errors.append(
            f"02-page-layout-ledger.csv: links non-owning reviewer IDs "
            f"{foreign_page_links}"
        )
    unknown_page_links = sorted(page_links - set(findings))
    if unknown_page_links:
        errors.append(
            f"{report_path.name}: page-ledger dispositions reference unknown "
            f"current {ACTOR_ID} finding IDs {unknown_page_links}"
        )

    known_ids = set(findings) | set(questions)
    bibliography_links = {
        match
        for row in bibliography_ledger
        for match in re.findall(
            r"R\d+-(?:F|Q)\d{2,4}", row.get("FindingDisposition", "")
        )
    }
    citation_links = {
        match
        for row in citation_ledger
        for field in ("SeverityFinding", "DispositionEvidence")
        for match in re.findall(r"R\d+-(?:F|Q)\d{2,4}", row.get(field, ""))
    }
    audit_links = bibliography_links | citation_links
    foreign = sorted(
        identifier for identifier in audit_links
        if not identifier.startswith(f"{ACTOR_ID}-")
    )
    if foreign:
        errors.append(
            f"03/04 audit ledgers link non-owning reviewer IDs {foreign}"
        )
    unknown = sorted(audit_links - known_ids)
    if unknown:
        errors.append(
            "03/04 audit ledgers reference unknown current master R3 "
            f"finding/question IDs {unknown}"
        )
    mismatch_links = {
        match
        for row in bibliography_ledger
        if row.get("Verdict", "").casefold() == "mismatch"
        for match in re.findall(
            r"R\d+-(?:F|Q)\d{2,4}", row.get("FindingDisposition", "")
        )
    } | {
        match
        for row in citation_ledger
        if (
            row.get("Support", "").casefold() == "mismatch"
            or row.get("MetadataStatus", "").casefold() == "mismatch"
        )
        for field in ("SeverityFinding", "DispositionEvidence")
        for match in re.findall(r"R\d+-(?:F|Q)\d{2,4}", row.get(field, ""))
    }
    s4_links = sorted(
        identifier
        for identifier in mismatch_links
        if identifier in findings
        and findings[identifier].get("Severity", "").casefold() == "s4"
    )
    if s4_links:
        errors.append(
            "03/04 mismatch rows cannot be waived as optional S4 findings; "
            f"observed={s4_links}"
        )


def validate_master_r3(
    root: Path,
    module: Any,
    packet_module: Any,
) -> list[str]:
    errors: list[str] = []
    preflight_process = preflight_exact_inputs(module, root, errors)
    if preflight_process is None:
        return errors
    prompt_map = preflight_process.get("actor_prompt_sha256")
    process, frozen_path, expected_hash, page_count, reviewer_count, pdf_sizes = (
        module.validate_process(
            root,
            errors,
            enforce_single_reviewer_pdf=False,
            process_override=preflight_process,
            stage_v_present_override=(
                isinstance(prompt_map, dict) and "V" in prompt_map
            ),
        )
    )
    if errors:
        return errors
    if (
        process.get("degree_level") != DEGREE_LEVEL
        or reviewer_count != REVIEWER_COUNT
    ):
        errors.append(
            "validate_master_r3_output.py requires a master's "
            "three-reviewer round"
        )
        return errors
    validate_canonical_support(module, process, root, errors)

    page_inventory = module.read_csv(
        root / "00-page-inventory.csv",
        module.PAGE_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    page_ledger = module.read_csv(
        root / "02-page-layout-ledger.csv",
        module.PAGE_LEDGER_COLUMNS,
        errors,
        require_rows=True,
    )
    bibliography_inventory = module.read_csv(
        root / "00-bibliography-inventory.csv",
        module.BIB_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    bibliography_ledger = module.read_csv(
        root / "03-bibliography-audit-ledger.csv",
        module.BIB_LEDGER_COLUMNS,
        errors,
        require_rows=True,
    )
    citation_inventory = packet_module.validate_packet_inputs(
        module,
        root,
        process,
        frozen_path,
        expected_hash,
        page_count,
        reviewer_count,
        page_inventory,
        bibliography_inventory,
        errors,
    )
    citation_ledger = module.read_csv(
        root / "04-citation-claim-audit-ledger.csv",
        module.CITATION_LEDGER_COLUMNS,
        errors,
        require_rows=True,
    )

    validate_page_outputs(
        module,
        root,
        expected_hash,
        page_count,
        pdf_sizes,
        page_inventory,
        page_ledger,
        errors,
    )
    validate_bibliography_outputs(
        module,
        root,
        expected_hash,
        bibliography_inventory,
        bibliography_ledger,
        citation_inventory,
        errors,
    )
    validate_citation_outputs(
        module,
        root,
        expected_hash,
        citation_inventory,
        bibliography_inventory,
        citation_ledger,
        errors,
    )

    rule_endpoints = {
        value
        for value in process.get("governing_rule_urls", [])
        if isinstance(value, str)
    }
    bibliography_endpoints = module.bibliography_ledger_public_endpoints(
        bibliography_ledger
    )
    citation_endpoints = module.citation_ledger_public_endpoints(
        citation_ledger
    )
    all_endpoints = rule_endpoints | bibliography_endpoints | citation_endpoints
    module.validate_declarations(
        root / "01-policy-basis.md",
        expected_hash,
        errors,
        process=process,
        actor_id="P",
        reviewer_count=reviewer_count,
        allowed_public_endpoints=rule_endpoints,
        required_public_endpoints=rule_endpoints,
    )
    for filename, allowed_endpoints, required_endpoints, headers in (
        (
            "02-page-layout-ledger.md",
            rule_endpoints | bibliography_endpoints,
            set(),
            module.PAGE_MARKDOWN_HEADERS,
        ),
        (
            "03-bibliography-audit-ledger.md",
            rule_endpoints | bibliography_endpoints,
            bibliography_endpoints,
            module.BIB_MARKDOWN_HEADERS,
        ),
        (
            "04-citation-claim-audit-ledger.md",
            rule_endpoints | citation_endpoints,
            citation_endpoints,
            module.CITATION_MARKDOWN_HEADERS,
        ),
    ):
        owned_text = module.validate_declarations(
            root / filename,
            expected_hash,
            errors,
            process=process,
            actor_id=ACTOR_ID,
            reviewer_count=reviewer_count,
            allowed_public_endpoints=allowed_endpoints,
            required_public_endpoints=required_endpoints,
        )
        if owned_text:
            module.validate_declarations_before_main_table(
                owned_text, headers, filename, errors
            )

    owner_vectors = module.build_owner_expected_vectors(
        page_inventory,
        page_ledger,
        bibliography_inventory,
        bibliography_ledger,
        citation_inventory,
        citation_ledger,
    )
    report_path = root / "R3-comprehensive-review.md"
    module.validate_reviewer_report(
        report_path,
        expected_hash,
        REVIEWER_INDEX,
        process,
        reviewer_count,
        all_endpoints,
        all_endpoints,
        DEGREE_LEVEL,
        process.get("decision_regime_status"),
        module.process_governing_sources(process),
        owner_vectors,
        page_count,
        errors,
    )
    validate_report_links(
        module,
        report_path,
        page_count,
        page_ledger,
        bibliography_ledger,
        citation_ledger,
        errors,
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only mechanical validator for one master's R3 output set"
        )
    )
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    root = args.round_directory.absolute()
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_module(
            VALIDATOR, "thesis_review_bundle_validator_for_master_r3"
        )
        packet_module = load_module(
            PACKET_VALIDATOR, "thesis_review_packet_validator_for_master_r3"
        )
        return print_result(validate_master_r3(root, module, packet_module))
    except Exception as exc:
        return print_result(
            [f"master R3 validator could not complete safely: {exc}"]
        )
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


if __name__ == "__main__":
    sys.exit(main())
