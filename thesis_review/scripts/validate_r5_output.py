#!/usr/bin/env python3
"""Read-only mechanical gate for one doctoral R5 output set.

The command accepts the exact current bundle root.  It validates only the
frozen upstream packet, R5's report and 02/03 ledgers, and page-renders.  It
does not open or require R1--R4, AI, Chair, Stage-S, or Stage-V artifacts and
never writes a validation report into the bundle.
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


ACTOR_ID = "R5"
VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
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
    "R5-comprehensive-review.md",
)


def safe_dynamic_round_basename(module: Any, value: Any) -> bool:
    """Reject a process name that aliases staged/current/downstream artifacts."""

    return (
        isinstance(value, str)
        and module.is_neutral_portable_basename(value)
        and module.portable_basename_key(value)
        not in module.RESERVED_ROUND_BASENAME_KEYS
        and module.RENDER_ARTIFACT_BASENAME_RE.fullmatch(value) is None
    )


def load_validator() -> Any:
    """Load the sibling full validator from the same rules/scripts directory."""

    spec = importlib.util.spec_from_file_location(
        "thesis_review_bundle_validator_for_r5", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {VALIDATOR}")
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
        "Current doctoral R5 report, 02/03 ledgers, page renders, receipts, "
        "and upstream packet passed the read-only mechanical gate."
    )
    return 0


def require_r5_inputs(module: Any, root: Path, errors: list[str]) -> None:
    for filename in REQUIRED_FILES:
        path = root / filename
        if module.is_link_or_reparse(path) or not path.is_file():
            errors.append(f"missing or unsafe required R5 input: {filename}")


def preflight_r5_boundary(
    module: Any, root: Path, errors: list[str]
) -> dict[str, Any] | None:
    """Reject aliases on exact R5 paths without enumerating the bundle root."""

    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append("round directory is missing or is a symlink/junction/reparse point")
        return None
    process_path = root / "00-process-parameters.json"
    if module.is_link_or_reparse(process_path) or not process_path.is_file():
        errors.append("missing or unsafe required R5 input: 00-process-parameters.json")
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
    unsafe = sorted(
        path.name for path in exact_paths if module.is_link_or_reparse(path)
    )
    if unsafe:
        errors.append(f"R5 exact-path boundary contains unsafe aliases: {unsafe}")
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
        child_aliases = sorted(
            child.name for child in children if module.is_link_or_reparse(child)
        )
        if child_aliases:
            errors.append(
                f"{directory_name} contains unsafe aliases: {child_aliases}"
            )
    return process if not errors else None


def validate_packet_inputs(
    module: Any,
    root: Path,
    process: dict[str, Any],
    frozen_path: Path,
    expected_hash: str,
    page_count: int,
    reviewer_count: int,
    page_inventory: list[dict[str, str]],
    bibliography_inventory: list[dict[str, str]],
    errors: list[str],
) -> list[dict[str, str]]:
    """Reconcile the complete Stage-P citation packet to the frozen PDF."""

    candidates = module.read_csv(
        root / "00-citation-candidate-ledger.csv",
        module.CITATION_CANDIDATE_COLUMNS,
        errors,
        require_rows=True,
    )
    module.validate_rows_mandatory(
        candidates,
        "00-citation-candidate-ledger.csv",
        module.CITATION_CANDIDATE_COLUMNS,
        errors,
    )
    module.validate_pdf_hash(
        candidates, "00-citation-candidate-ledger.csv", expected_hash, errors
    )

    declared_reference_pages: set[int] = set()
    for line, row in enumerate(page_inventory, start=2):
        region = row.get("Region", "").strip().casefold()
        if any(token in region for token in ("reference", "bibliograph", "参考文献")):
            try:
                declared_reference_pages.add(int(row.get("PhysicalPage", "")))
            except ValueError:
                errors.append(
                    f"00-page-inventory.csv:{line}: bibliography Region has an "
                    "invalid PhysicalPage"
                )
    reference_pages = module.derive_and_validate_reference_pages(
        frozen_path, declared_reference_pages, bibliography_inventory, errors
    )
    extracted_candidates, extracted_unmatched = module.extract_numeric_bracket_candidates(
        frozen_path, reference_pages, errors
    )

    unmatched = module.read_csv(
        root / "00-unmatched-bracket-ledger.csv",
        module.UNMATCHED_BRACKET_COLUMNS,
        errors,
        require_rows=bool(extracted_unmatched),
    )
    module.validate_rows_mandatory(
        unmatched,
        "00-unmatched-bracket-ledger.csv",
        module.UNMATCHED_BRACKET_COLUMNS,
        errors,
    )
    module.validate_pdf_hash(
        unmatched, "00-unmatched-bracket-ledger.csv", expected_hash, errors
    )
    if len(unmatched) != len(extracted_unmatched):
        errors.append(
            "00-unmatched-bracket-ledger.csv: row count does not equal the "
            "frozen-PDF unmatched-glyph extraction"
        )
    for index, row in enumerate(unmatched, start=1):
        line = index + 1
        if row.get("GlyphID") != f"UBG{index:04d}":
            errors.append(
                f"00-unmatched-bracket-ledger.csv:{line}: GlyphID sequence mismatch"
            )
        if index <= len(extracted_unmatched):
            extracted = extracted_unmatched[index - 1]
            try:
                physical_page = int(row.get("PhysicalPage", ""))
            except ValueError:
                physical_page = -1
            if physical_page != extracted["PhysicalPage"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: PhysicalPage does "
                    "not match the frozen-PDF extraction"
                )
            if row.get("Glyph") != extracted["Glyph"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: Glyph does not "
                    "match the frozen-PDF extraction"
                )
            if row.get("AdjacentPDFText", "") != extracted["Adjacent"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: AdjacentPDFText "
                    "does not match the frozen-PDF extraction"
                )
        disposition = row.get("Disposition", "").strip().casefold()
        if (
            len(disposition) < 12
            or module.is_placeholder(disposition)
            or re.search(r"\b(?:none|no unmatched|zero)\b", disposition)
        ):
            errors.append(
                f"00-unmatched-bracket-ledger.csv:{line}: Disposition must give "
                "a concrete non-contradictory glyph adjudication"
            )

    if len(candidates) != len(extracted_candidates):
        errors.append(
            "00-citation-candidate-ledger.csv: row count does not equal the "
            "frozen-PDF numeric-bracket extraction"
        )
    occurrence_numbers: dict[str, list[int]] = {}
    occurrence_pages: dict[str, int] = {}
    occurrence_contexts: dict[str, str] = {}
    citation_number = 0
    for index, row in enumerate(candidates, start=1):
        line = index + 1
        if row.get("CandidateID") != f"BC{index:04d}":
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: CandidateID sequence mismatch"
            )
        try:
            physical_page = int(row.get("PhysicalPage", ""))
        except ValueError:
            physical_page = -1
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid PhysicalPage"
            )
        marker = module.normalize_numeric_marker(row.get("Marker", ""))
        if row.get("Marker", "") != marker:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: Marker must equal "
                "its canonical whitespace/comma/dash normalization"
            )
        parsed_numbers = module.expand_numeric_marker(row.get("Marker", ""))
        expected_expansion = (
            "N/A" if parsed_numbers is None
            else ";".join(str(value) for value in parsed_numbers)
        )
        if row.get("ExpandedNumbers") != expected_expansion:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: ExpandedNumbers "
                "does not equal the canonical marker expansion"
            )
        if index <= len(extracted_candidates):
            extracted = extracted_candidates[index - 1]
            if physical_page != extracted["PhysicalPage"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: PhysicalPage does "
                    "not match the frozen-PDF extraction"
                )
            if (
                row.get("Marker", "") != extracted["Marker"]
                or parsed_numbers != extracted["Expanded"]
            ):
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: marker/expansion "
                    "does not match the frozen-PDF extraction"
                )
            if row.get("AdjacentPDFText", "") != extracted["Adjacent"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: AdjacentPDFText "
                    "does not match the frozen-PDF extraction"
                )
            obvious_reason = module.obvious_non_citation_reason(extracted)
        else:
            obvious_reason = None
        classification = row.get("Classification", "").strip().casefold()
        if classification not in module.CANDIDATE_CLASSIFICATIONS:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid Classification"
            )
        evidence = row.get("ClassificationEvidence", "")
        if not module.valid_candidate_classification_evidence(evidence):
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: "
                "ClassificationEvidence is not a concrete contextual reason"
            )
        if obvious_reason and classification != "non-citation":
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: obvious non-citation "
                f"classified as citation ({obvious_reason})"
            )
        mapped = row.get("MappedOccurrenceID", "").strip()
        if classification == "citation":
            citation_number += 1
            expected_occurrence = f"C{citation_number:04d}"
            if parsed_numbers is None or mapped != expected_occurrence:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: citation candidate "
                    f"must map to {expected_occurrence} with a pure integer marker"
                )
            if mapped in occurrence_numbers:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: duplicate "
                    f"MappedOccurrenceID {mapped}"
                )
            occurrence_numbers[mapped] = parsed_numbers or []
            occurrence_pages[mapped] = physical_page
            occurrence_contexts[mapped] = row.get("AdjacentPDFText", "")
        elif classification == "non-citation" and mapped != "N/A":
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: non-citation must use "
                "MappedOccurrenceID=N/A"
            )

    citation_inventory = module.read_csv(
        root / "00-citation-inventory.csv",
        module.CITATION_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    module.validate_rows_mandatory(
        citation_inventory,
        "00-citation-inventory.csv",
        module.CITATION_INVENTORY_COLUMNS,
        errors,
    )
    module.validate_pdf_hash(
        citation_inventory, "00-citation-inventory.csv", expected_hash, errors
    )
    module.index_unique(
        citation_inventory, "PairID", "00-citation-inventory.csv", errors
    )
    current_occurrence = 0
    current_source_ordinal = 0
    inventory_numbers: dict[str, list[int]] = defaultdict(list)
    for line, row in enumerate(citation_inventory, start=2):
        occurrence_match = module.OCCURRENCE_ID_RE.fullmatch(
            row.get("OccurrenceID", "")
        )
        pair_match = module.PAIR_ID_RE.fullmatch(row.get("PairID", ""))
        if occurrence_match is None or pair_match is None:
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
        expected_pair_id = (
            f"C{occurrence_number:04d}-S{current_source_ordinal:02d}"
        )
        if row.get("PairID", "") != expected_pair_id:
            errors.append(
                f"00-citation-inventory.csv:{line}: PairID must equal canonical "
                f"reading-order ID {expected_pair_id}"
            )
        reference_match = module.REFERENCE_ID_RE.fullmatch(
            row.get("DisplayedReferenceID", "")
        )
        if reference_match is None:
            errors.append(
                f"00-citation-inventory.csv:{line}: invalid DisplayedReferenceID"
            )
        else:
            inventory_numbers[row["OccurrenceID"]].append(
                int(reference_match.group(1))
            )
        located_page = module.parse_physical_page_locator(row.get("PDFLocation", ""))
        expected_page = occurrence_pages.get(row["OccurrenceID"])
        if located_page is None or located_page < 1 or located_page > page_count:
            errors.append(
                f"00-citation-inventory.csv:{line}: PDFLocation requires an "
                "in-range physical page"
            )
        elif expected_page is not None and located_page != expected_page:
            errors.append(
                f"00-citation-inventory.csv:{line}: PDFLocation page does not "
                "match the mapped candidate"
            )
        expected_context = occurrence_contexts.get(row["OccurrenceID"])
        if (
            expected_context is not None
            and row.get("AdjacentPDFText", "") != expected_context
        ):
            errors.append(
                f"00-citation-inventory.csv:{line}: AdjacentPDFText does not "
                "equal the mapped candidate context"
            )
    module.compare_sets(
        "citation candidate-to-inventory occurrence mapping",
        set(occurrence_numbers),
        set(inventory_numbers),
        errors,
    )
    for occurrence_id in set(occurrence_numbers) & set(inventory_numbers):
        if occurrence_numbers[occurrence_id] != inventory_numbers[occurrence_id]:
            errors.append(
                "citation candidate-to-inventory number mismatch for "
                f"{occurrence_id}"
            )

    cited_ids = {
        row.get("DisplayedReferenceID", "") for row in citation_inventory
        if module.REFERENCE_ID_RE.fullmatch(row.get("DisplayedReferenceID", ""))
    }
    for line, row in enumerate(bibliography_inventory, start=2):
        expected_cited = "yes" if row.get("ReferenceID") in cited_ids else "no"
        if row.get("Cited", "").strip().casefold() != expected_cited:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: Cited must be "
                f"{expected_cited!r} from the reconciled citation inventory"
            )

    module.validate_manifest(
        root / "00-manifest.md",
        expected_hash,
        # The manifest validates the current process bytes and Stage-P counts.
        process,
        candidates,
        extracted_unmatched,
        reference_pages,
        root,
        reviewer_count,
        errors,
    )
    return citation_inventory


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
    """Mirror every current full-validator contract for R5's 02 output."""

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
            path.name for path in render_directory.iterdir()
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
            errors.append(
                f"00-page-inventory.csv:{line}: invalid PhysicalPage"
            )
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
            and re.fullmatch(r"(?i)finding[ \t]+R5-F\d{2,4}", disposition)
            is None
        ):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: final Disposition must be "
                "exactly clean, intentional, or finding R5-Fxx"
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
            rf"^(?:{re.escape(row.get('PageID', ''))}[:/| -])?[0-9a-fA-F]{{64}}$"
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
            if declared is not None and module.sha256(render_path) != declared.group(1).upper():
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
            if inventory_by_id[page_id].get(field) != ledger_by_id[page_id].get(field):
                errors.append(
                    f"page mapping mismatch for {page_id}: {field}"
                )
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
    """Mirror every current full-validator contract for R5's 03 output."""

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
    module.validate_bibliography_evidence_specificity(
        bibliography_ledger,
        "03-bibliography-audit-ledger.csv",
        errors,
    )
    ledger_reference_ids = {
        row.get("ReferenceID", "") for row in bibliography_ledger
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
        row.get("DisplayedReferenceID", "") for row in citation_inventory
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
    exact_owner_link = re.compile(r"R5-(?:F|Q)\d{2,4}")
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
                ("DisplayedLabel", "DisplayedLabel"), ("Cited", "Cited")
            ):
                if row.get(ledger_field) != inventory_row.get(inventory_field):
                    errors.append(
                        f"bibliography mapping mismatch for {reference_id}/{field}: "
                        f"{ledger_field}"
                    )
        if verdict == "unverifiable" and row.get("EvidenceNote", "").casefold() in {
            "n/a", "none"
        }:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: unverifiable row "
                "lacks an attempted-route note"
            )
        if verdict == "mismatch" and exact_owner_link.fullmatch(
            row.get("FindingDisposition", "").strip()
        ) is None:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: mismatch "
                "FindingDisposition must be exactly one current R5-Fxx or "
                "R5-Qxx ID, with no none/N/A/prose/second ID"
            )
    duplicate_keys = sorted(
        key for key, count in key_counts.items() if count > 1
    )
    if duplicate_keys:
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


def validate_report_links(
    module: Any,
    report_path: Path,
    page_count: int,
    page_ledger: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    errors: list[str],
) -> None:
    text = module.markdown_visible_text(
        report_path.read_text(encoding="utf-8", errors="replace")
    )
    findings = module.parse_reviewer_findings(
        text, 5, report_path.name, page_count, []
    )
    questions = module.parse_reviewer_questions(
        text, 5, report_path.name, page_count, []
    )
    page_links = module.page_layout_finding_ids(page_ledger)
    unknown_page_links = sorted(page_links - set(findings))
    if unknown_page_links:
        errors.append(
            f"{report_path.name}: page-ledger dispositions reference unknown "
            f"current R5 finding IDs {unknown_page_links}"
        )
    known_ids = set(findings) | set(questions)
    bibliography_links = {
        match for row in bibliography_ledger
        for match in re.findall(
            r"R\d+-(?:F|Q)\d{2,4}", row.get("FindingDisposition", "")
        )
    }
    foreign = sorted(
        identifier for identifier in bibliography_links
        if not identifier.startswith("R5-")
    )
    if foreign:
        errors.append(
            f"03-bibliography-audit-ledger.csv: links non-owning reviewer IDs {foreign}"
        )
    unknown = sorted(bibliography_links - known_ids)
    if unknown:
        errors.append(
            "03-bibliography-audit-ledger.csv: references unknown current R5 "
            f"finding/question IDs {unknown}"
        )
    mismatch_finding_links = {
        row.get("FindingDisposition", "").strip()
        for row in bibliography_ledger
        if row.get("Verdict", "").casefold() == "mismatch"
        and re.fullmatch(r"R5-F\d{2,4}", row.get("FindingDisposition", "").strip())
    }
    s4_links = sorted(
        identifier for identifier in mismatch_finding_links
        if identifier in findings
        and findings[identifier].get("Severity", "").casefold() == "s4"
    )
    if s4_links:
        errors.append(
            "03-bibliography-audit-ledger.csv: mismatch rows cannot be linked "
            f"only to optional S4 findings {s4_links}"
        )


def validate_r5(root: Path, module: Any) -> list[str]:
    errors: list[str] = []
    preflight_process = preflight_r5_boundary(module, root, errors)
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
    if process.get("degree_level") != "doctorate" or reviewer_count != 5:
        return [*errors, "R5 gate requires a doctoral five-reviewer process"]
    require_r5_inputs(module, root, errors)
    if errors:
        return errors

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
    citation_inventory = validate_packet_inputs(
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

    rule_endpoints = {
        value for value in process.get("governing_rule_urls", [])
        if isinstance(value, str)
    }
    bibliography_endpoints = module.bibliography_ledger_public_endpoints(
        bibliography_ledger
    )
    allowed_endpoints = rule_endpoints | bibliography_endpoints
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
    for filename, required in (
        ("02-page-layout-ledger.md", set()),
        ("03-bibliography-audit-ledger.md", bibliography_endpoints),
    ):
        owned_text = module.validate_declarations(
            root / filename,
            expected_hash,
            errors,
            process=process,
            actor_id=ACTOR_ID,
            reviewer_count=reviewer_count,
            allowed_public_endpoints=allowed_endpoints,
            required_public_endpoints=required,
        )
        if owned_text:
            expected_headers = (
                module.PAGE_MARKDOWN_HEADERS
                if filename.startswith("02-") else module.BIB_MARKDOWN_HEADERS
            )
            module.validate_declarations_before_main_table(
                owned_text, expected_headers, filename, errors
            )

    owner_vectors = module.build_owner_expected_vectors(
        page_inventory,
        page_ledger,
        bibliography_inventory,
        bibliography_ledger,
        [],
        [],
    )
    report_path = root / "R5-comprehensive-review.md"
    module.validate_reviewer_report(
        report_path,
        expected_hash,
        5,
        process,
        reviewer_count,
        allowed_endpoints,
        allowed_endpoints,
        process.get("degree_level"),
        process.get("decision_regime_status"),
        module.process_governing_sources(process),
        owner_vectors,
        page_count,
        errors,
    )
    validate_report_links(
        module, report_path, page_count, page_ledger, bibliography_ledger, errors
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only mechanical validator for one doctoral R5 output set"
    )
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    root = args.round_directory.absolute()
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_validator()
        return print_result(validate_r5(root, module))
    except Exception as exc:
        return print_result([f"R5 validator could not complete safely: {exc}"])
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


if __name__ == "__main__":
    raise SystemExit(main())
