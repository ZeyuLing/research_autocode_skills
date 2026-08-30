#!/usr/bin/env python3
"""Read-only Stage-S gate for the current clean user-facing summary.

This validator opens only the process identity, current R/AI/Chair summary
sources, Chair 91/92 ledgers, and Stage-S's three owned outputs.  It never
opens the frozen PDF, Stage-P packet, 02/03/04 ledgers, helpers, prior rounds,
or the post-S validation report.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "thesis_review_bundle_validator_for_summary", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight_summary_boundary(
    module: Any, root: Path, errors: list[str]
) -> tuple[dict[str, Any] | None, int]:
    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append(
            "round directory is missing or is a symlink/junction/reparse point"
        )
        return None, 0
    process_path = root / "00-process-parameters.json"
    if module.is_link_or_reparse(process_path) or not process_path.is_file():
        errors.append("missing or unsafe Stage-S input: 00-process-parameters.json")
        return None, 0
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot safely preflight 00-process-parameters.json: {exc}")
        return None, 0
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return None, 0
    degree = process.get("degree_level")
    reviewer_count = 5 if degree == "doctorate" else 3 if degree == "masters" else 0
    if reviewer_count == 0:
        errors.append("Stage-S process degree_level must be doctorate or masters")
        return None, 0
    expected_hash = process.get("selected_pdf_sha256")
    if not isinstance(expected_hash, str) or module.HEX64_RE.fullmatch(expected_hash) is None:
        errors.append("Stage-S process selected_pdf_sha256 must be 64 hexadecimal characters")
    frozen_name = process.get("frozen_pdf_file")
    if not isinstance(frozen_name, str) or not module.is_neutral_portable_basename(
        frozen_name
    ):
        errors.append("Stage-S process frozen_pdf_file must be one neutral basename")
    prompt_map = process.get("actor_prompt_sha256")
    if (
        not isinstance(prompt_map, dict)
        or not isinstance(prompt_map.get("S"), str)
        or module.HEX64_RE.fullmatch(str(prompt_map.get("S", ""))) is None
    ):
        errors.append("Stage-S process lacks a valid S operational-prompt hash")
    required = [
        *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
        "05-ai-style-assessment.md",
        "90-chair-synthesis.md",
        "91-revision-ledger.md",
        "91-revision-ledger.csv",
        "91-ai-actionable-ledger.csv",
        "92-new-evidence-or-experiments.md",
        "92-new-evidence-or-experiments.csv",
        "93-user-facing-summary.md",
        "93-current-actionable-items.csv",
        "93-current-ai-actionable-items.csv",
    ]
    for filename in required:
        path = root / filename
        if module.is_link_or_reparse(path) or not path.is_file():
            errors.append(f"missing or unsafe Stage-S input/output: {filename}")
    return (process if not errors else None), reviewer_count


def validate_summary(root: Path, module: Any) -> list[str]:
    errors: list[str] = []
    preflight_process, reviewer_count = preflight_summary_boundary(
        module, root, errors
    )
    if preflight_process is None:
        return errors
    prompt_map = preflight_process.get("actor_prompt_sha256")
    process, _, _, _, validated_reviewer_count, _ = module.validate_process(
        root,
        errors,
        enforce_single_reviewer_pdf=False,
        validate_governing_file_bytes=False,
        validate_frozen_pdf_bytes=False,
        process_override=preflight_process,
        stage_v_present_override=(
            isinstance(prompt_map, dict) and "V" in prompt_map
        ),
    )
    if errors:
        return errors
    if validated_reviewer_count != reviewer_count:
        errors.append(
            "Stage-S reviewer count does not match the validated process envelope"
        )
        return errors
    expected_hash = str(process["selected_pdf_sha256"]).upper()

    academic = module.read_csv(
        root / "91-revision-ledger.csv",
        module.ACADEMIC_LEDGER_COLUMNS,
        errors,
        require_rows=False,
    )
    ai = module.read_csv(
        root / "91-ai-actionable-ledger.csv",
        module.AI_LEDGER_COLUMNS,
        errors,
        require_rows=False,
    )
    evidence = module.read_csv(
        root / "92-new-evidence-or-experiments.csv",
        module.EVIDENCE_ITEM_COLUMNS,
        errors,
        require_rows=False,
    )
    for rows, filename, columns in (
        (academic, "91-revision-ledger.csv", module.ACADEMIC_LEDGER_COLUMNS),
        (ai, "91-ai-actionable-ledger.csv", module.AI_LEDGER_COLUMNS),
        (evidence, "92-new-evidence-or-experiments.csv", module.EVIDENCE_ITEM_COLUMNS),
    ):
        module.validate_rows_mandatory(rows, filename, columns, errors)

    academic_by_id = module.index_unique(
        academic, "LedgerID", "91-revision-ledger.csv", errors
    )
    ai_by_id = module.index_unique(
        ai, "AIFindingID", "91-ai-actionable-ledger.csv", errors
    )
    evidence_by_id = module.index_unique(
        evidence,
        "EvidenceItemID",
        "92-new-evidence-or-experiments.csv",
        errors,
    )
    open_academic = {
        identifier: row
        for identifier, row in academic_by_id.items()
        if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
    }
    open_ai = {
        identifier: row
        for identifier, row in ai_by_id.items()
        if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
    }

    academic_summary = module.read_csv(
        root / "93-current-actionable-items.csv",
        module.ACADEMIC_SUMMARY_COLUMNS,
        errors,
        require_rows=bool(open_academic),
    )
    ai_summary = module.read_csv(
        root / "93-current-ai-actionable-items.csv",
        module.AI_SUMMARY_COLUMNS,
        errors,
        require_rows=bool(open_ai),
    )
    module.validate_rows_mandatory(
        academic_summary,
        "93-current-actionable-items.csv",
        module.ACADEMIC_SUMMARY_COLUMNS,
        errors,
    )
    module.validate_rows_mandatory(
        ai_summary,
        "93-current-ai-actionable-items.csv",
        module.AI_SUMMARY_COLUMNS,
        errors,
    )
    academic_summary_by_id = module.index_unique(
        academic_summary,
        "LedgerID",
        "93-current-actionable-items.csv",
        errors,
    )
    ai_summary_by_id = module.index_unique(
        ai_summary,
        "AIFindingID",
        "93-current-ai-actionable-items.csv",
        errors,
    )
    if [row.get("LedgerID", "") for row in academic_summary] != list(open_academic):
        errors.append(
            "93-current-actionable-items.csv: row order must exactly follow "
            "the open 91 academic row order"
        )
    if [row.get("AIFindingID", "") for row in ai_summary] != list(open_ai):
        errors.append(
            "93-current-ai-actionable-items.csv: row order must exactly follow "
            "the open 91 AI row order"
        )
    module.compare_sets(
        "current academic summary",
        set(open_academic),
        set(academic_summary_by_id),
        errors,
    )
    module.compare_sets(
        "current AI-actionable summary",
        set(open_ai),
        set(ai_summary_by_id),
        errors,
    )
    for identifier in sorted(set(open_academic) & set(academic_summary_by_id)):
        for field in module.ACADEMIC_SUMMARY_COLUMNS:
            if academic_summary_by_id[identifier][field] != open_academic[identifier][field]:
                errors.append(
                    f"academic 91->93 mismatch for {identifier}/{field}: "
                    f"expected {open_academic[identifier][field]!r}, got "
                    f"{academic_summary_by_id[identifier][field]!r}"
                )
    for identifier in sorted(set(open_ai) & set(ai_summary_by_id)):
        for field in module.AI_SUMMARY_COLUMNS:
            if ai_summary_by_id[identifier][field] != open_ai[identifier][field]:
                errors.append(
                    f"AI 91->93 mismatch for {identifier}/{field}: "
                    f"expected {open_ai[identifier][field]!r}, got "
                    f"{ai_summary_by_id[identifier][field]!r}"
                )

    summary_path = root / "93-user-facing-summary.md"
    module.validate_markdown_id_projection(
        summary_path,
        set(open_academic),
        re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
        {"Ledger ID", "LedgerID"},
        "Stage-S current academic summary",
        errors,
        required_headers={
            "Ledger ID", "Priority", "Chair finding ID",
            "Source reviewer finding IDs", "Severity", "S0 subtype", "Remedy",
            "Exact PDF anchor", "Direct PDF-visible observation", "Evidence status",
            "Minimum required action", "Dependency", "Owner", "Chair disposition",
            "Verification",
        },
        section_heading="Current actionable items",
    )
    module.validate_markdown_id_projection(
        summary_path,
        set(open_ai),
        re.compile(r"(?<![A-Za-z0-9])AI-F\d{2,4}(?![A-Za-z0-9])"),
        {"AI finding ID", "AIFindingID"},
        "Stage-S current AI summary",
        errors,
        required_headers={
            "AI finding ID", "Impact (`material` / `local`)",
            "Exact PDF anchor", "Direct style observation",
            "Minimum editing action", "Chair status", "Verification",
        },
        section_heading=(
            "Current AI-style actionable items — separate from academic grading"
        ),
    )
    module.validate_markdown_id_projection(
        summary_path,
        set(evidence_by_id),
        re.compile(r"(?<![A-Za-z0-9])N\d{2,4}(?![A-Za-z0-9])"),
        {"Evidence item ID", "EvidenceItemID"},
        "Stage-S current N-evidence summary",
        errors,
        required_headers={
            "Evidence item ID", "Ledger ID", "Chair finding ID", "Remedy",
            "Item", "Claim that depends on it", "Why writing is insufficient",
            "Minimum viable evidence", "Consequence if unavailable",
        },
        section_heading="Current new evidence or experiments (N)",
    )
    module.validate_summary_markdown_values(
        summary_path,
        academic_summary_by_id,
        ai_summary_by_id,
        evidence_by_id,
        errors,
    )
    module.validate_summary_report(
        summary_path,
        expected_hash,
        process,
        reviewer_count,
        len(open_academic),
        len(open_ai),
        len(evidence_by_id),
        errors,
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_validator()
        errors = validate_summary(args.round_directory.absolute(), module)
    except Exception as exc:
        errors = [f"Stage-S validator could not complete safely: {exc}"]
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("PASS")
    print(
        "Current Stage-S Markdown and both lossless 93 CSV projections passed "
        "the read-only current-round reconciliation gate."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
