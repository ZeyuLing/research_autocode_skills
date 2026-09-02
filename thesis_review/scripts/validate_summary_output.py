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
import io
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
STAGE_S_OUTPUTS = (
    "93-user-facing-summary.md",
    "93-current-actionable-items.csv",
    "93-current-ai-actionable-items.csv",
)


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "thesis_review_bundle_validator_for_summary", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_directory_snapshot(
    module: Any, path: Path, label: str, errors: list[str]
) -> tuple[int, int, int, int, int, int, int] | None:
    """Bind one directory without enumerating any neighboring artifact."""

    try:
        metadata = path.lstat()
    except OSError as exc:
        errors.append(f"cannot inspect {label}: {exc}")
        return None
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        or module.is_link_or_reparse(path)
    ):
        errors.append(f"{label} is missing or link/reparse-backed")
        return None
    streams, stream_error = module._ntfs_named_streams(path)
    if stream_error is not None:
        errors.append(f"{label}: {stream_error}")
        return None
    if streams:
        errors.append(f"{label} must not carry NTFS named streams; observed={streams}")
        return None
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_mode),
        int(metadata.st_nlink),
        int(metadata.st_size),
        int(getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1e9))),
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0),
    )


def scan_exact_directory(
    module: Any,
    path: Path,
    label: str,
    expected_files: set[str],
    expected_directories: set[str],
    errors: list[str],
) -> tuple[
    tuple[int, int, int, int, int, int, int] | None,
    dict[str, tuple[str, int, int, int, int, int, int, int]],
]:
    """Enumerate names and metadata only; never open an entry's bytes."""

    directory_snapshot = safe_directory_snapshot(module, path, label, errors)
    if directory_snapshot is None:
        return None, {}
    observations: dict[str, tuple[str, int, int, int, int, int, int, int]] = {}
    try:
        with os.scandir(path) as entries:
            ordered_entries = sorted(entries, key=lambda entry: entry.name)
    except OSError as exc:
        errors.append(f"cannot enumerate {label}: {exc}")
        return directory_snapshot, observations

    for entry in ordered_entries:
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            errors.append(f"cannot inspect {label} entry {entry.name!r}: {exc}")
            continue
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        is_reparse = bool(
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
        if stat.S_ISREG(metadata.st_mode):
            kind = "file"
        elif stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
        else:
            kind = "other"
        observations[entry.name] = (
            kind,
            int(metadata.st_dev),
            int(metadata.st_ino),
            int(metadata.st_mode),
            int(metadata.st_nlink),
            int(metadata.st_size),
            int(getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1e9))),
            attributes,
        )
        if entry.is_symlink() or is_reparse:
            errors.append(
                f"{label} entry {entry.name!r} must not be link/reparse-backed"
            )

    expected_names = expected_files | expected_directories
    observed_names = set(observations)
    missing = sorted(expected_names - observed_names)
    extra = sorted(observed_names - expected_names)
    if missing:
        errors.append(f"{label} is missing required entries: {missing}")
    if extra:
        errors.append(f"{label} contains forbidden extra entries: {extra}")
    for name in sorted(expected_files & observed_names):
        if observations[name][0] != "file":
            errors.append(f"{label} entry {name!r} must be a regular file")
    for name in sorted(expected_directories & observed_names):
        if observations[name][0] != "directory":
            errors.append(f"{label} entry {name!r} must be a directory")
    return directory_snapshot, observations


def validate_closed_stage_s_view(
    module: Any,
    root: Path,
    opened_inputs: list[str],
    errors: list[str],
) -> dict[str, Any]:
    """Prove that Stage S sees one exact, unified, private filesystem view.

    This boundary deliberately inspects only directory-entry names and stat
    metadata. It runs after the process envelope is read but before any other
    Stage-S source bytes are opened, so a forbidden extra file can cause a
    closed failure without exposing its contents to Stage S.
    """

    required_paths = [*opened_inputs, *STAGE_S_OUTPUTS]
    if len(required_paths) != len(set(required_paths)):
        errors.append("Stage-S canonical opened-input/output paths are not unique")

    expected_root_files: set[str] = set()
    expected_rule_scripts: set[str] = set()
    for relative in required_paths:
        relative_path = Path(relative)
        parts = relative_path.parts
        if (
            relative_path.is_absolute()
            or not parts
            or "." in parts
            or ".." in parts
            or any(":" in part for part in parts)
        ):
            errors.append(f"unsafe Stage-S canonical path: {relative!r}")
        elif len(parts) == 1:
            expected_root_files.add(parts[0])
        elif len(parts) == 3 and parts[:2] == ("rules", "scripts"):
            expected_rule_scripts.add(parts[2])
        else:
            errors.append(
                "Stage-S canonical paths may only name root files or "
                f"rules/scripts files: {relative!r}"
            )

    canonical_rule_paths = set(module.SUMMARY_VALIDATOR_RULE_INPUTS)
    observed_rule_paths = {
        f"rules/scripts/{filename}" for filename in expected_rule_scripts
    }
    if observed_rule_paths != canonical_rule_paths:
        errors.append(
            "Stage-S canonical rule inputs mismatch; "
            f"missing={sorted(canonical_rule_paths-observed_rule_paths)}, "
            f"extra={sorted(observed_rule_paths-canonical_rule_paths)}"
        )

    root_directory, root_entries = scan_exact_directory(
        module,
        root,
        "Stage-S private root",
        expected_root_files,
        {"rules"},
        errors,
    )
    rules_directory, rules_entries = scan_exact_directory(
        module,
        root / "rules",
        "Stage-S rules directory",
        set(),
        {"scripts"},
        errors,
    )
    scripts_directory, scripts_entries = scan_exact_directory(
        module,
        root / "rules" / "scripts",
        "Stage-S rules/scripts directory",
        expected_rule_scripts,
        set(),
        errors,
    )
    return {
        "root_directory": root_directory,
        "root_entries": root_entries,
        "rules_directory": rules_directory,
        "rules_entries": rules_entries,
        "scripts_directory": scripts_directory,
        "scripts_entries": scripts_entries,
    }


def capture_stage_s_files(
    module: Any,
    root: Path,
    relatives: list[str],
    errors: list[str],
) -> dict[str, Any]:
    """Read exactly Stage-S's closed sources/outputs through stable handles."""

    snapshots: dict[str, Any] = {}
    for relative in dict.fromkeys(relatives):
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or "." in relative_path.parts
            or ".." in relative_path.parts
            or any(":" in part for part in relative_path.parts)
        ):
            errors.append(f"unsafe Stage-S allowlisted path: {relative!r}")
            continue
        path = root / relative_path
        snapshot = module.capture_helper_input_snapshot(
            path, f"Stage-S file {relative}", errors
        )
        if snapshot is not None:
            snapshots[relative] = snapshot
    return snapshots


def call_with_frozen_stage_s_reads(
    root: Path,
    snapshots: dict[str, Any],
    operation: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run one semantic parser using only bytes captured by the safe preflight.

    The shared validators are intentionally reused, but their ``Path.open``
    calls are served from the immutable in-memory Stage-S snapshot.  Thus an
    ABA pathname replacement during semantic parsing cannot make validation
    inspect bytes different from the bytes whose identity is committed.
    """

    path_type = type(root)
    original_open = path_type.open
    had_local_open = "open" in path_type.__dict__
    prior_local_open = path_type.__dict__.get("open")
    frozen: dict[str, bytes] = {
        os.path.normcase(os.path.abspath(os.fspath(root / Path(relative)))):
        snapshot.content
        for relative, snapshot in snapshots.items()
    }

    def frozen_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Any:
        if any(marker in mode for marker in ("w", "a", "x", "+")):
            # The trusted shared validators never write. Keep the real write
            # path available so deterministic race-injection tests (and any
            # genuinely concurrent process) can still mutate the filesystem;
            # all semantic reads below remain bound to the frozen bytes.
            return original_open(
                path,
                mode,
                buffering=buffering,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        content = frozen.get(key)
        if content is None:
            raise OSError(
                f"Stage-S semantic validation attempted an uncommitted path: {path}"
            )
        if "b" in mode:
            return io.BytesIO(content)
        return io.TextIOWrapper(
            io.BytesIO(content),
            encoding=encoding or "utf-8",
            errors=errors,
            newline=newline,
        )

    path_type.open = frozen_open
    try:
        return operation(*args, **kwargs)
    finally:
        if had_local_open:
            path_type.open = prior_local_open
        else:
            delattr(path_type, "open")


def preflight_summary_boundary(
    module: Any, root: Path, errors: list[str]
) -> tuple[
    dict[str, Any] | None,
    int,
    tuple[int, int, int, int, int, int, int] | None,
    dict[str, Any],
    list[str],
    dict[str, Any],
]:
    root_snapshot = safe_directory_snapshot(
        module, root, "Stage-S private-view directory", errors
    )
    if root_snapshot is None:
        errors.append(
            "Stage-S private-view directory is missing or is a "
            "symlink/junction/reparse point"
        )
        return None, 0, None, {}, [], {}
    process_snapshots = capture_stage_s_files(
        module, root, ["00-process-parameters.json"], errors
    )
    process_snapshot = process_snapshots.get("00-process-parameters.json")
    if process_snapshot is None:
        errors.append("missing or unsafe Stage-S input: 00-process-parameters.json")
        return None, 0, root_snapshot, process_snapshots, [], {}
    try:
        process = module.parse_strict_json_object(
            process_snapshot.content.decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"cannot safely preflight 00-process-parameters.json: {exc}")
        return None, 0, root_snapshot, process_snapshots, [], {}
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return None, 0, root_snapshot, process_snapshots, [], {}
    degree = process.get("degree_level")
    reviewer_count = 5 if degree == "doctorate" else 3 if degree == "masters" else 0
    if reviewer_count == 0:
        errors.append("Stage-S process degree_level must be doctorate or masters")
        return None, 0, root_snapshot, process_snapshots, [], {}
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
    opened = module.canonical_stage_opened_inputs(
        process, reviewer_count, "S", root
    )
    required = [*opened, *STAGE_S_OUTPUTS]
    boundary_snapshot = validate_closed_stage_s_view(
        module, root, opened, errors
    )
    if errors:
        return (
            None,
            reviewer_count,
            root_snapshot,
            process_snapshots,
            required,
            boundary_snapshot,
        )
    snapshots = capture_stage_s_files(module, root, required, errors)
    if snapshots.get("00-process-parameters.json") != process_snapshot:
        errors.append(
            "Stage-S process identity or bytes changed between process parsing "
            "and the complete source/output snapshot"
        )
    if set(snapshots) != set(dict.fromkeys(required)):
        missing = sorted(set(required) - set(snapshots))
        if missing:
            errors.append(f"missing or unsafe Stage-S input/output: {missing}")
    return (
        process if not errors else None,
        reviewer_count,
        root_snapshot,
        snapshots,
        required,
        boundary_snapshot,
    )


def terminal_summary_closure(
    module: Any,
    root: Path,
    preflight_process: dict[str, Any],
    reviewer_count: int,
    root_snapshot: tuple[int, int, int, int, int, int, int] | None,
    safety_snapshots: dict[str, Any],
    safety_paths: list[str],
    boundary_snapshot: dict[str, Any],
    errors: list[str],
) -> None:
    """Re-prove the exact Stage-S universe on every post-preflight exit."""

    terminal_root_snapshot = safe_directory_snapshot(
        module, root, "Stage-S private-view directory", errors
    )
    if terminal_root_snapshot != root_snapshot:
        errors.append(
            "Stage-S private-view directory identity changed during validation"
        )
    terminal_boundary_snapshot = validate_closed_stage_s_view(
        module,
        root,
        module.canonical_stage_opened_inputs(
            preflight_process, reviewer_count, "S", root
        ),
        errors,
    )
    if terminal_boundary_snapshot != boundary_snapshot:
        errors.append("Stage-S private view structure changed during validation")
    terminal_snapshots = capture_stage_s_files(
        module, root, safety_paths, errors
    )
    if terminal_snapshots != safety_snapshots:
        errors.append(
            "Stage-S source/output identity or bytes changed during validation"
        )


def validate_summary(root: Path, module: Any) -> list[str]:
    errors: list[str] = []
    (
        preflight_process,
        reviewer_count,
        root_snapshot,
        safety_snapshots,
        safety_paths,
        boundary_snapshot,
    ) = preflight_summary_boundary(module, root, errors)
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
        terminal_summary_closure(
            module, root, preflight_process, reviewer_count, root_snapshot,
            safety_snapshots, safety_paths, boundary_snapshot, errors,
        )
        return errors
    if validated_reviewer_count != reviewer_count:
        errors.append(
            "Stage-S reviewer count does not match the validated process envelope"
        )
        terminal_summary_closure(
            module, root, preflight_process, reviewer_count, root_snapshot,
            safety_snapshots, safety_paths, boundary_snapshot, errors,
        )
        return errors
    expected_hash = str(process["selected_pdf_sha256"]).upper()

    academic = call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.read_csv,
        root / "91-revision-ledger.csv",
        module.ACADEMIC_LEDGER_COLUMNS,
        errors,
        require_rows=False,
    )
    ai = call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.read_csv,
        root / "91-ai-actionable-ledger.csv",
        module.AI_LEDGER_COLUMNS,
        errors,
        require_rows=False,
    )
    evidence = call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.read_csv,
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
    module.validate_academic_dependency_references(
        academic, "91-revision-ledger.csv", errors
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

    academic_summary = call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.read_csv,
        root / "93-current-actionable-items.csv",
        module.ACADEMIC_SUMMARY_COLUMNS,
        errors,
        require_rows=bool(open_academic),
    )
    ai_summary = call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.read_csv,
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
    call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.validate_markdown_id_projection,
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
        reference_id_headers={"Dependency"},
        reference_id_values=set(academic_by_id),
        section_heading="Current actionable items",
    )
    call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.validate_markdown_id_projection,
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
    call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.validate_markdown_id_projection,
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
    call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.validate_summary_markdown_values,
        summary_path,
        academic_summary_by_id,
        ai_summary_by_id,
        evidence_by_id,
        errors,
    )
    call_with_frozen_stage_s_reads(
        root,
        safety_snapshots,
        module.validate_summary_report,
        summary_path,
        expected_hash,
        process,
        reviewer_count,
        len(open_academic),
        len(open_ai),
        len(evidence_by_id),
        errors,
    )
    terminal_summary_closure(
        module, root, preflight_process, reviewer_count, root_snapshot,
        safety_snapshots, safety_paths, boundary_snapshot, errors,
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage_s_view_directory", type=Path)
    args = parser.parse_args(argv)
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_validator()
        errors = validate_summary(args.stage_s_view_directory.absolute(), module)
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
