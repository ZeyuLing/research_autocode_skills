#!/usr/bin/env python3
"""Read-only mechanical gate for the current Stage-P packet.

The command accepts the exact current bundle root.  It opens only the process
envelope, the process-selected frozen PDF and governing files, and Stage P's
seven owned outputs.  It neither discovers nor opens reviewer, AI, Chair,
Stage-S, Stage-V, prior-round, or thesis-source artifacts and never writes a
validation report into the bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import stat
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ACTOR_ID = "P"
VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
P_OWNED_FILES = (
    "00-manifest.md",
    "01-policy-basis.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
)


def load_validator() -> Any:
    """Load the sibling full validator from the staged read-only rules mount."""

    spec = importlib.util.spec_from_file_location(
        "thesis_review_bundle_validator_for_stage_p", VALIDATOR
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
        "Current frozen PDF, process envelope, governing inputs, and seven "
        "Stage-P packet outputs passed the read-only mechanical gate."
    )
    return 0


def safe_regular_file(module: Any, path: Path) -> bool:
    """Accept one exact regular, non-reparse, single-link path."""

    try:
        metadata = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_nlink == 1
        and not module.is_link_or_reparse(path)
    )


def safe_dynamic_round_basename(module: Any, value: Any) -> bool:
    """Reject portable names that alias any staged/current/downstream artifact."""

    return (
        isinstance(value, str)
        and module.is_neutral_portable_basename(value)
        and module.portable_basename_key(value)
        not in module.RESERVED_ROUND_BASENAME_KEYS
        and module.RENDER_ARTIFACT_BASENAME_RE.fullmatch(value) is None
    )


def exact_stage_p_paths(
    module: Any,
    root: Path,
    process: dict[str, Any],
    errors: list[str],
) -> tuple[list[Path], Path]:
    paths = [root / "00-process-parameters.json"]
    paths.extend(root / filename for filename in P_OWNED_FILES)
    frozen_name = process.get("frozen_pdf_file")
    if safe_dynamic_round_basename(module, frozen_name):
        frozen_path = root / frozen_name
        paths.append(frozen_path)
    else:
        frozen_path = root / "__missing__.pdf"
        errors.append(
            "frozen_pdf_file is unsafe or collides with a reserved round "
            "basename; the path was not accessed"
        )
    local_files = process.get("governing_local_files")
    if isinstance(local_files, list):
        for item in local_files:
            filename = item.get("neutral_file") if isinstance(item, dict) else None
            if safe_dynamic_round_basename(module, filename):
                paths.append(root / filename)
            elif filename is not None:
                errors.append(
                    "governing_local_files contains an unsafe or reserved "
                    "neutral_file; the path was not accessed"
                )
    return paths, frozen_path


def preflight_stage_p_boundary(
    module: Any, root: Path, errors: list[str]
) -> tuple[dict[str, Any], list[Path]]:
    """Resolve only Stage-P's closed exact-path allowlist; never enumerate root."""

    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append(
            "round directory is missing or is a symlink/junction/reparse point"
        )
        return {}, []
    process_path = root / "00-process-parameters.json"
    if not safe_regular_file(module, process_path):
        errors.append(
            "missing or unsafe required Stage-P input: 00-process-parameters.json"
        )
        return {}, []
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot safely preflight 00-process-parameters.json: {exc}")
        return {}, []
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return {}, []
    exact_paths, _frozen_path = exact_stage_p_paths(
        module, root, process, errors
    )
    seen: set[str] = set()
    for path in exact_paths:
        key = str(path.absolute()).casefold()
        if key in seen:
            errors.append(f"duplicate exact Stage-P path: {path.name}")
            continue
        seen.add(key)
        if not safe_regular_file(module, path):
            errors.append(f"missing or unsafe exact Stage-P path: {path.name}")
    return process, exact_paths


def snapshot_exact_paths(paths: list[Path]) -> dict[str, tuple[int, str]]:
    """Hash only the already resolved Stage-P allowlist."""

    snapshot: dict[str, tuple[int, str]] = {}
    for path in paths:
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        snapshot[str(path.absolute()).casefold()] = (
            len(payload), hashlib.sha256(payload).hexdigest().upper()
        )
    return snapshot


def validate_page_inventory(
    module: Any,
    root: Path,
    expected_hash: str,
    page_count: int,
    errors: list[str],
) -> list[dict[str, str]]:
    rows = module.read_csv(
        root / "00-page-inventory.csv",
        module.PAGE_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    module.validate_rows_mandatory(
        rows,
        "00-page-inventory.csv",
        module.PAGE_INVENTORY_COLUMNS,
        errors,
        blank_allowed={"PrintedPage"},
    )
    module.validate_pdf_hash(
        rows, "00-page-inventory.csv", expected_hash, errors
    )
    module.index_unique(rows, "PageID", "00-page-inventory.csv", errors)
    if len(rows) != page_count:
        errors.append(
            "00-page-inventory.csv: row count does not equal physical_page_count"
        )
    physical_pages: list[int] = []
    for index, row in enumerate(rows, start=1):
        line = index + 1
        expected_page_id = f"P{index:04d}"
        if row.get("PageID") != expected_page_id:
            errors.append(
                f"00-page-inventory.csv:{line}: PageID sequence mismatch; "
                f"expected {expected_page_id}"
            )
        try:
            physical_page = int(row.get("PhysicalPage", ""))
            physical_pages.append(physical_page)
        except ValueError:
            errors.append(
                f"00-page-inventory.csv:{line}: invalid PhysicalPage"
            )
            continue
        if physical_page != index:
            errors.append(
                f"00-page-inventory.csv:{line}: PhysicalPage must equal {index}"
            )
    if sorted(physical_pages) != list(range(1, page_count + 1)):
        errors.append(
            "00-page-inventory.csv: PhysicalPage values are not exactly 1..N"
        )
    return rows


def validate_bibliography_inventory(
    module: Any,
    root: Path,
    expected_hash: str,
    errors: list[str],
) -> list[dict[str, str]]:
    rows = module.read_csv(
        root / "00-bibliography-inventory.csv",
        module.BIB_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    module.validate_rows_mandatory(
        rows,
        "00-bibliography-inventory.csv",
        module.BIB_INVENTORY_COLUMNS,
        errors,
    )
    module.validate_pdf_hash(
        rows, "00-bibliography-inventory.csv", expected_hash, errors
    )
    module.index_unique(
        rows, "ReferenceID", "00-bibliography-inventory.csv", errors
    )
    for index, row in enumerate(rows, start=1):
        expected_reference_id = f"REF{index:04d}"
        if row.get("ReferenceID") != expected_reference_id:
            errors.append(
                "00-bibliography-inventory.csv: ReferenceID sequence mismatch "
                f"at row {index + 1}; expected {expected_reference_id}"
            )
    return rows


def validate_packet_reconciliation(
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
    """Re-extract and reconcile the complete Stage-P citation packet."""

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
        if any(
            token in region for token in ("reference", "bibliograph", "参考文献")
        ):
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
    extracted_candidates, extracted_unmatched = (
        module.extract_numeric_bracket_candidates(
            frozen_path, reference_pages, errors
        )
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
            "N/A"
            if parsed_numbers is None
            else ";".join(str(value) for value in parsed_numbers)
        )
        if row.get("ExpandedNumbers") != expected_expansion:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: ExpandedNumbers "
                "does not equal the canonical semicolon-separated marker expansion"
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
                    "does not match the deterministic frozen-PDF extraction window"
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
        located_page = module.parse_physical_page_locator(
            row.get("PDFLocation", "")
        )
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
    for occurrence_id in sorted(
        set(occurrence_numbers) & set(inventory_numbers)
    ):
        if occurrence_numbers[occurrence_id] != inventory_numbers[occurrence_id]:
            errors.append(
                "citation candidate-to-inventory number mismatch for "
                f"{occurrence_id}"
            )

    cited_ids = {
        row.get("DisplayedReferenceID", "")
        for row in citation_inventory
        if module.REFERENCE_ID_RE.fullmatch(
            row.get("DisplayedReferenceID", "")
        )
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
        process,
        candidates,
        extracted_unmatched,
        root,
        reviewer_count,
        errors,
    )
    return citation_inventory


def validate_stage_p(root: Path, module: Any) -> list[str]:
    """Validate only the frozen Stage-P input/output closure."""

    errors: list[str] = []
    preflight_process, exact_paths = preflight_stage_p_boundary(
        module, root, errors
    )
    if errors:
        return errors
    before = snapshot_exact_paths(exact_paths)
    (
        process,
        frozen_path,
        expected_hash,
        page_count,
        reviewer_count,
        _pdf_page_sizes,
    ) = module.validate_process(
        root,
        errors,
        enforce_single_reviewer_pdf=False,
        process_override=preflight_process,
        stage_v_present_override=(
            isinstance(preflight_process.get("actor_prompt_sha256"), dict)
            and "V" in preflight_process["actor_prompt_sha256"]
        ),
    )
    page_inventory = validate_page_inventory(
        module, root, expected_hash, page_count, errors
    )
    bibliography_inventory = validate_bibliography_inventory(
        module, root, expected_hash, errors
    )
    validate_packet_reconciliation(
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
    rule_public_endpoints = {
        value
        for value in process.get("governing_rule_urls", [])
        if isinstance(value, str)
    }
    module.validate_declarations(
        root / "01-policy-basis.md",
        expected_hash,
        errors,
        process=process,
        actor_id=ACTOR_ID,
        reviewer_count=reviewer_count,
        allowed_public_endpoints=rule_public_endpoints,
        required_public_endpoints=rule_public_endpoints,
    )
    after = snapshot_exact_paths(exact_paths)
    if before != after:
        errors.append(
            "Stage-P validator observed an input/output byte change while running"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only mechanical validator for one Stage-P packet"
    )
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    root = args.round_directory.absolute()
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_validator()
        return print_result(validate_stage_p(root, module))
    except Exception as exc:
        return print_result(
            [f"Stage-P validator could not complete safely: {exc}"]
        )
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


if __name__ == "__main__":
    raise SystemExit(main())
