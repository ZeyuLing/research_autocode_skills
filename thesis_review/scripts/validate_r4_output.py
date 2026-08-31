#!/usr/bin/env python3
"""Read-only mechanical gate for one doctoral R4 output set.

The command validates the current Stage-P citation packet, R4's report, and
the authoritative 04 citation-claim Markdown/CSV pair.  It never opens or
requires peer reports, R5 outputs, AI, Chair, Stage-S, or prior-round files.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ACTOR_ID = "R4"
VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
R5_VALIDATOR = Path(__file__).with_name("validate_r5_output.py")
REQUIRED_FILES = (
    "00-process-parameters.json",
    "00-manifest.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
    "01-policy-basis.md",
    "04-citation-claim-audit-ledger.md",
    "04-citation-claim-audit-ledger.csv",
    "R4-comprehensive-review.md",
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
        "Current doctoral R4 report, 04 citation-claim ledger, receipts, "
        "source locators, dispositions, and upstream citation packet passed "
        "the read-only mechanical gate."
    )
    return 0


def safe_dynamic_round_basename(module: Any, value: Any) -> bool:
    return (
        isinstance(value, str)
        and module.is_neutral_portable_basename(value)
        and module.portable_basename_key(value)
        not in module.RESERVED_ROUND_BASENAME_KEYS
        and module.RENDER_ARTIFACT_BASENAME_RE.fullmatch(value) is None
    )


def preflight_exact_inputs(
    module: Any, root: Path, errors: list[str]
) -> dict[str, Any] | None:
    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append(
            "round directory is missing or is a symlink/junction/reparse point"
        )
        return None
    for filename in REQUIRED_FILES:
        path = root / filename
        if module.is_link_or_reparse(path) or not path.is_file():
            errors.append(f"missing or unsafe required R4 input: {filename}")
    if errors:
        return None
    process_path = root / "00-process-parameters.json"
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot safely preflight 00-process-parameters.json: {exc}")
        return None
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return None
    frozen_name = process.get("frozen_pdf_file")
    if safe_dynamic_round_basename(module, frozen_name):
        frozen_path = root / frozen_name
        if module.is_link_or_reparse(frozen_path) or not frozen_path.is_file():
            errors.append("process-selected frozen PDF is missing or unsafe")
    else:
        errors.append("frozen_pdf_file is unsafe or collides with a reserved basename")
    local_files = process.get("governing_local_files")
    if isinstance(local_files, list):
        for item in local_files:
            filename = item.get("neutral_file") if isinstance(item, dict) else None
            if not safe_dynamic_round_basename(module, filename):
                errors.append(
                    "governing_local_files contains an unsafe or reserved neutral_file"
                )
                continue
            path = root / filename
            if module.is_link_or_reparse(path) or not path.is_file():
                errors.append(f"missing or unsafe governing input: {filename}")
    return process if not errors else None


def validate_citation_outputs(
    module: Any,
    root: Path,
    process: dict[str, Any],
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
    module.compare_sets(
        "citation-claim ledger",
        set(inventory_by_pair),
        set(ledger_by_pair),
        errors,
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
        r"(?<![A-Za-z0-9])R4-(?:F|Q)\d{2,4}(?![A-Za-z0-9])"
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
                "link an owning-reviewer R4-Fxx or R4-Qxx disposition; a "
                "reasoned non-finding cannot waive a contradiction"
            )
        elif requires_disposition and not (
            has_owner_link or has_reasoned_nonfinding
        ):
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: non-ideal "
                "support/metadata row must link an owning-reviewer R4-Fxx or "
                "R4-Qxx disposition, or use an explicit substantive "
                "'reasoned non-finding:' explanation"
            )

    module.validate_markdown_id_projection(
        root / "04-citation-claim-audit-ledger.md",
        set(inventory_by_pair),
        module.PAIR_ID_TOKEN_RE,
        {"Pair ID", "PairID"},
        "citation-claim ledger",
        errors,
        required_headers={
            "Pair ID",
            "Occurrence ID",
            "PDF location",
            "Exact attached proposition",
            "Reference ID",
            "Displayed label",
            "Public source/identifier",
            "Content source opened and exact locator",
            "Support",
            "Metadata/status",
            "Severity/finding",
            "Disposition/evidence",
        },
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

    citation_endpoints = module.citation_ledger_public_endpoints(
        citation_ledger
    )
    rule_endpoints = {
        value
        for value in process.get("governing_rule_urls", [])
        if isinstance(value, str)
    }
    access_endpoints = rule_endpoints | citation_endpoints
    ledger_text = module.validate_declarations(
        root / "04-citation-claim-audit-ledger.md",
        expected_hash,
        errors,
        process=process,
        actor_id=ACTOR_ID,
        reviewer_count=5,
        allowed_public_endpoints=access_endpoints,
        required_public_endpoints=citation_endpoints,
    )
    if ledger_text:
        module.validate_declarations_before_main_table(
            ledger_text,
            module.CITATION_MARKDOWN_HEADERS,
            "04-citation-claim-audit-ledger.md",
            errors,
        )


def validate_r4(root: Path, module: Any, packet_module: Any) -> list[str]:
    errors: list[str] = []
    preflight_process = preflight_exact_inputs(module, root, errors)
    if preflight_process is None:
        return errors
    prompt_map = preflight_process.get("actor_prompt_sha256")
    process, frozen_path, expected_hash, page_count, reviewer_count, _ = (
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
    if not process or not frozen_path or not expected_hash:
        return errors
    if process.get("degree_level") != "doctorate" or reviewer_count != 5:
        errors.append("validate_r4_output.py requires a doctoral five-reviewer round")
        return errors

    page_inventory = module.read_csv(
        root / "00-page-inventory.csv",
        module.PAGE_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    bibliography_inventory = module.read_csv(
        root / "00-bibliography-inventory.csv",
        module.BIB_INVENTORY_COLUMNS,
        errors,
        require_rows=True,
    )
    for rows, filename, columns, blank_allowed in (
        (
            page_inventory,
            "00-page-inventory.csv",
            module.PAGE_INVENTORY_COLUMNS,
            {"PrintedPage"},
        ),
        (
            bibliography_inventory,
            "00-bibliography-inventory.csv",
            module.BIB_INVENTORY_COLUMNS,
            set(),
        ),
    ):
        module.validate_rows_mandatory(
            rows, filename, columns, errors, blank_allowed=blank_allowed
        )
        module.validate_pdf_hash(rows, filename, expected_hash, errors)
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
    validate_citation_outputs(
        module,
        root,
        process,
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
    citation_endpoints = module.citation_ledger_public_endpoints(
        citation_ledger
    )
    owner_vectors = module.build_owner_expected_vectors(
        page_inventory,
        [],
        bibliography_inventory,
        [],
        citation_inventory,
        citation_ledger,
    )
    report_path = root / "R4-comprehensive-review.md"
    module.validate_reviewer_report(
        report_path,
        expected_hash,
        4,
        process,
        reviewer_count,
        rule_endpoints | citation_endpoints,
        rule_endpoints | citation_endpoints,
        "doctorate",
        process.get("decision_regime_status"),
        module.process_governing_sources(process),
        owner_vectors,
        page_count,
        errors,
    )
    if report_path.is_file():
        visible = module.markdown_visible_text(
            report_path.read_text(encoding="utf-8", errors="replace")
        )
        findings = module.parse_reviewer_findings(
            visible, 4, report_path.name, page_count, []
        )
        questions = module.parse_reviewer_questions(
            visible, 4, report_path.name, page_count, []
        )
        known_ids = set(findings) | set(questions)
        linked_ids = {
            match
            for row in citation_ledger
            for field in ("SeverityFinding", "DispositionEvidence")
            for match in re.findall(r"R\d+-(?:F|Q)\d{2,4}", row.get(field, ""))
        }
        foreign = sorted(
            item for item in linked_ids if not item.startswith("R4-")
        )
        if foreign:
            errors.append(
                "04-citation-claim-audit-ledger.csv: links non-owning "
                f"reviewer IDs {foreign}"
            )
        unknown = sorted(linked_ids - known_ids)
        if unknown:
            errors.append(
                "04-citation-claim-audit-ledger.csv: references unknown "
                f"current R4 finding/question IDs {unknown}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_module(VALIDATOR, "thesis_review_bundle_validator_for_r4")
        packet_module = load_module(R5_VALIDATOR, "thesis_review_r5_packet_for_r4")
        errors = validate_r4(args.round_directory.absolute(), module, packet_module)
        return print_result(errors)
    except Exception as exc:
        return print_result([f"R4 validator could not complete safely: {exc}"])
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


if __name__ == "__main__":
    sys.exit(main())
