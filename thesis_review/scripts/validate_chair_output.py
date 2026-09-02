#!/usr/bin/env python3
"""Read-only, closed-view mechanical gate for the Stage-C output set.

The command accepts *only* a private Chair view. Its file universe is the
ordered result of ``canonical_stage_opened_inputs(..., "C", root)`` plus the
six Chair-owned outputs. The boundary is enumerated and rejected by pathname
and metadata before any substantive bytes other than the process envelope are
opened. Page renders, private SA reports, Stage-S/Stage-V artifacts, and the
final validation report are forbidden.

The semantic-acceptance gate contains hashes for R5 page-render artifacts.
Those images are intentionally not disclosed to the Chair view. This scoped
gate validates their exact expected names and 64-hex transport commitments,
but does not claim to have recomputed them. The final full-bundle gate remains
responsible for that byte-for-byte check.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
SEMANTIC_VALIDATOR = Path(__file__).with_name(
    "validate_semantic_acceptance_output.py"
)
CHAIR_OUTPUTS = (
    "90-chair-synthesis.md",
    "91-revision-ledger.md",
    "91-revision-ledger.csv",
    "91-ai-actionable-ledger.csv",
    "92-new-evidence-or-experiments.md",
    "92-new-evidence-or-experiments.csv",
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
        "The exact private Stage-C view, process/PDF identity, current panel "
        "and AI projections, visible 02/03/04 artifacts, hash-only semantic-"
        "acceptance gate, and all six Chair-owned outputs passed the scoped "
        "read-only gate. R5 page-render hashes were checked only as exact-name "
        "64-hex Stage-O transport commitments because page-renders are forbidden "
        "from the Chair view; they were not recomputed or semantically validated "
        "by this command."
    )
    return 0


def _directory_snapshot(
    module: Any, path: Path, label: str, errors: list[str]
) -> tuple[int, int, int, int, int] | None:
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
        attributes,
    )


def _entry_kind(module: Any, path: Path, relative: str, errors: list[str]) -> str:
    try:
        metadata = path.lstat()
    except OSError as exc:
        errors.append(f"cannot inspect Stage-C entry {relative}: {exc}")
        return "unsafe"
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    streams, stream_error = module._ntfs_named_streams(path)
    if stream_error is not None:
        errors.append(f"cannot inspect named streams on {relative!r}: {stream_error}")
        return "unsafe"
    if streams:
        errors.append(f"Stage-C entry {relative!r} carries named streams: {streams}")
        return "unsafe"
    if (
        stat.S_ISLNK(metadata.st_mode)
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        or module.is_link_or_reparse(path)
    ):
        return "unsafe"
    if stat.S_ISREG(metadata.st_mode) and int(metadata.st_nlink) == 1:
        return "file"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    return "unsafe"


def _scan_one_directory(
    module: Any, root: Path, relative_directory: str,
    expected_tree: dict[str, str], errors: list[str], observed: dict[str, str],
) -> None:
    """Scan one allowlisted directory; never descend through an extra child."""

    directory = root if relative_directory == "." else root / relative_directory
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        errors.append(f"cannot enumerate Stage-C directory {relative_directory!r}: {exc}")
        return
    prefix = "" if relative_directory == "." else f"{relative_directory}/"
    expected_children = {
        relative[len(prefix):].split("/", 1)[0]
        for relative in expected_tree
        if relative.startswith(prefix) and relative != relative_directory
    }
    observed_children = {entry.name for entry in entries}
    missing = sorted(expected_children - observed_children)
    extras = sorted(observed_children - expected_children)
    if missing:
        errors.append(
            f"closed Stage-C directory {relative_directory!r} is missing "
            f"canonical child path(s): {missing}"
        )
    if extras:
        errors.append(
            f"closed Stage-C directory {relative_directory!r} contains "
            f"unallowlisted path(s) among its direct children: {extras}"
        )
    for entry in entries:
        relative = f"{prefix}{entry.name}"
        if entry.name not in expected_children:
            # The extra name is recorded above and is never opened or traversed.
            continue
        if not module.is_neutral_portable_basename(entry.name):
            errors.append(f"closed Stage-C view has unsafe basename: {relative!r}")
            observed[relative] = "unsafe"
            continue
        kind = _entry_kind(module, entry, relative, errors)
        observed[relative] = kind
        expected_kind = expected_tree.get(relative)
        if expected_kind is not None and kind != expected_kind:
            errors.append(
                f"closed Stage-C path {relative!r} must be {expected_kind}, got {kind}"
            )
        if kind == "directory" and expected_kind == "directory":
            _scan_one_directory(
                module, root, relative, expected_tree, errors, observed
            )


def _scan_exact_tree(
    module: Any, root: Path, expected_tree: dict[str, str], errors: list[str]
) -> dict[str, str]:
    """Scan only exact allowlisted branches, stopping before every extra dir."""

    observed: dict[str, str] = {}
    _scan_one_directory(module, root, ".", expected_tree, errors, observed)
    return observed


def _preflight_root_directories(
    module: Any, root: Path, helper_inputs: list[str], errors: list[str]
) -> bool:
    """Reject unknown root directories without traversing into any of them."""

    try:
        entries = list(root.iterdir())
    except OSError as exc:
        errors.append(f"cannot enumerate Stage-C view root: {exc}")
        return False
    allowed_directories = {"rules"}
    if helper_inputs:
        allowed_directories.add("helpers")
    for path in entries:
        try:
            metadata = path.lstat()
        except OSError as exc:
            errors.append(f"cannot inspect root entry {path.name!r}: {exc}")
            continue
        if not module.is_neutral_portable_basename(path.name):
            errors.append(f"closed Stage-C root has unsafe basename: {path.name!r}")
            continue
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        if (
            stat.S_ISLNK(metadata.st_mode)
            or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            or module.is_link_or_reparse(path)
        ):
            errors.append(f"closed Stage-C root has unsafe entry: {path.name!r}")
        elif stat.S_ISDIR(metadata.st_mode) and path.name not in allowed_directories:
            errors.append(
                "closed Stage-C root contains unallowlisted directory without "
                f"traversing it: {path.name!r}"
            )
        elif not stat.S_ISDIR(metadata.st_mode) and not stat.S_ISREG(metadata.st_mode):
            errors.append(f"closed Stage-C root has special entry: {path.name!r}")
    observed_dirs = {
        entry.name for entry in entries
        if not module.is_link_or_reparse(entry) and entry.is_dir()
    }
    missing_dirs = sorted(allowed_directories - observed_dirs)
    unexpected_dirs = sorted(observed_dirs - allowed_directories)
    if missing_dirs:
        errors.append(f"closed Stage-C root is missing directory(s): {missing_dirs}")
    if unexpected_dirs:
        # Preserve the generic diagnostic consumed by orchestration tests.
        errors.append(f"closed Stage-C view contains unallowlisted path(s): {unexpected_dirs}")
    return not errors


def _expected_tree(expected_files: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for relative in expected_files:
        path = Path(relative)
        for index in range(1, len(path.parts)):
            expected[Path(*path.parts[:index]).as_posix()] = "directory"
        expected[path.as_posix()] = "file"
    return expected


def _capture_files(
    module: Any, root: Path, relatives: list[str], errors: list[str]
) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for relative in dict.fromkeys(relatives):
        snapshot = module.capture_helper_input_snapshot(
            root / Path(relative), relative, errors
        )
        if snapshot is not None:
            snapshots[relative] = snapshot
    return snapshots


def preflight_chair_boundary(
    module: Any, root: Path, helper_inputs: list[str], errors: list[str]
) -> tuple[dict[str, Any] | None, int, list[str], dict[str, Any], Any]:
    """Commit the exact C view before opening its substantive artifacts."""

    root_snapshot = _directory_snapshot(module, root, "Stage-C view root", errors)
    if root_snapshot is None:
        return None, 0, [], {}, None
    normalized_helpers: list[str] = []
    for value in helper_inputs:
        path = Path(value)
        if (
            path.as_posix() != value.replace("\\", "/")
            or len(path.parts) != 2
            or path.parts[0] != "helpers"
            or not module.is_neutral_portable_basename(path.parts[1])
        ):
            errors.append(
                f"--helper-input must be helpers/<neutral-basename>, got {value!r}"
            )
            continue
        normalized_helpers.append(path.as_posix())
    if len(normalized_helpers) != len(set(normalized_helpers)):
        errors.append("duplicate --helper-input values are forbidden")
    if not _preflight_root_directories(module, root, normalized_helpers, errors):
        return None, 0, [], {}, root_snapshot

    process_only = _capture_files(
        module, root, ["00-process-parameters.json"], errors
    )
    process_snapshot = process_only.get("00-process-parameters.json")
    if process_snapshot is None:
        errors.append("missing or unsafe Stage-C process envelope")
        return None, 0, [], process_only, root_snapshot
    try:
        process = module.parse_strict_json_object(
            process_snapshot.content.decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"cannot safely parse 00-process-parameters.json: {exc}")
        return None, 0, [], process_only, root_snapshot
    degree = process.get("degree_level") if isinstance(process, dict) else None
    reviewer_count = 5 if degree == "doctorate" else 3 if degree == "masters" else 0
    if reviewer_count == 0:
        errors.append("Stage-C process degree_level must be doctorate or masters")
        return None, 0, [], process_only, root_snapshot

    opened = [
        *module.canonical_stage_opened_inputs(process, reviewer_count, "C", None),
        *normalized_helpers,
    ]
    expected_files = [*opened, *CHAIR_OUTPUTS]
    unsafe_expected = []
    portable_expected: dict[tuple[str, ...], str] = {}
    collisions: list[tuple[str, str]] = []
    for relative in expected_files:
        path = Path(relative)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {".", ".."} for part in path.parts)
            or any(not module.is_neutral_portable_basename(part) for part in path.parts)
        ):
            unsafe_expected.append(relative)
            continue
        key = tuple(module.portable_basename_key(part) for part in path.parts)
        prior = portable_expected.setdefault(key, path.as_posix())
        if prior != path.as_posix():
            collisions.append((prior, path.as_posix()))
    if unsafe_expected:
        errors.append(
            f"canonical Stage-C file universe contains unsafe path(s): {unsafe_expected}"
        )
    if collisions:
        errors.append(
            f"canonical Stage-C file universe contains portable collisions: {collisions}"
        )
    duplicates = sorted(
        value for value, count in Counter(expected_files).items() if count != 1
    )
    if duplicates:
        errors.append(f"canonical Stage-C file universe contains duplicates: {duplicates}")
    if errors:
        return None, reviewer_count, expected_files, process_only, root_snapshot
    expected_tree = _expected_tree(expected_files)
    observed_tree = _scan_exact_tree(module, root, expected_tree, errors)
    missing = sorted(set(expected_tree) - set(observed_tree))
    extras = sorted(set(observed_tree) - set(expected_tree))
    wrong_kind = sorted(
        relative
        for relative in set(expected_tree) & set(observed_tree)
        if expected_tree[relative] != observed_tree[relative]
    )
    unsafe = sorted(
        relative for relative, kind in observed_tree.items() if kind == "unsafe"
    )
    if missing:
        errors.append(f"closed Stage-C view is missing canonical path(s): {missing}")
    if extras:
        errors.append(f"closed Stage-C view contains unallowlisted path(s): {extras}")
    if wrong_kind:
        errors.append(f"closed Stage-C view has wrong file/directory kind: {wrong_kind}")
    if unsafe:
        errors.append(f"closed Stage-C view contains unsafe path(s): {unsafe}")
    if errors:
        return None, reviewer_count, expected_files, process_only, root_snapshot

    # At this point every path below rules/helpers is known and exact. Only now
    # may the generic recursive safety scan and helper-provenance projection run.
    if not module.preflight_reparse_boundary(root, errors):
        return None, reviewer_count, expected_files, process_only, root_snapshot

    snapshots = _capture_files(module, root, expected_files, errors)
    if snapshots.get("00-process-parameters.json") != process_snapshot:
        errors.append(
            "Stage-C process identity/bytes changed between parsing and complete snapshot"
        )
    missing_snapshots = sorted(set(expected_files) - set(snapshots))
    if missing_snapshots:
        errors.append(f"missing or unsafe Stage-C snapshot(s): {missing_snapshots}")
    if not errors:
        with frozen_path_reads(root, snapshots):
            canonical = module.canonical_stage_opened_inputs(
                process, reviewer_count, "C", root
            )
        if canonical != opened:
            errors.append(
                "--helper-input sequence must exactly equal the canonical "
                "C-recipient helper provenance/output projection"
            )
    return (
        process if not errors else None,
        reviewer_count,
        expected_files,
        snapshots,
        root_snapshot,
    )


@contextmanager
def frozen_path_reads(root: Path, snapshots: dict[str, Any]) -> Iterator[None]:
    """Serve every semantic Path read from the committed in-memory bytes."""

    path_type = type(root)
    original_open = path_type.open
    had_local_open = "open" in path_type.__dict__
    prior_local_open = path_type.__dict__.get("open")
    frozen = {
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
            raise OSError("Stage-C scoped validator is read-only")
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        content = frozen.get(key)
        if content is None:
            raise OSError(
                f"Stage-C semantic validation attempted an uncommitted path: {path}"
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
        yield
    finally:
        if had_local_open:
            path_type.open = prior_local_open
        else:
            delattr(path_type, "open")


def validate_process_and_pdf(
    module: Any,
    root: Path,
    process: dict[str, Any],
    reviewer_count: int,
    snapshots: dict[str, Any],
    errors: list[str],
) -> tuple[str, int]:
    prompt_map = process.get("actor_prompt_sha256")
    validated, _, expected_hash, page_count, validated_count, _ = (
        module.validate_process(
            root,
            errors,
            enforce_single_reviewer_pdf=False,
            validate_governing_file_bytes=False,
            validate_frozen_pdf_bytes=False,
            process_override=process,
            stage_v_present_override=(
                isinstance(prompt_map, dict) and "V" in prompt_map
            ),
        )
    )
    if not validated or validated_count != reviewer_count:
        errors.append("Stage-C reviewer count does not match validated process")
        return expected_hash, page_count
    frozen_name = str(process.get("frozen_pdf_file", ""))
    frozen_snapshot = snapshots.get(frozen_name)
    if frozen_snapshot is None:
        errors.append("process-selected frozen PDF lacks a committed Stage-C snapshot")
    else:
        actual_hash = hashlib.sha256(frozen_snapshot.content).hexdigest().upper()
        if actual_hash != expected_hash:
            errors.append(
                f"frozen PDF hash mismatch: expected {expected_hash}, got {actual_hash}"
            )
        if not frozen_snapshot.content.startswith(b"%PDF-"):
            errors.append(f"{frozen_name}: invalid PDF header")
        else:
            try:
                from pypdf import PdfReader

                actual_pages = len(
                    PdfReader(io.BytesIO(frozen_snapshot.content), strict=False).pages
                )
                if actual_pages != page_count:
                    errors.append(
                        f"{frozen_name}: parsed page count {actual_pages} != "
                        f"physical_page_count {page_count}"
                    )
            except Exception as exc:
                errors.append(f"{frozen_name}: cannot parse frozen PDF snapshot: {exc}")
    for item in process.get("governing_local_files", []):
        if not isinstance(item, dict):
            continue
        filename = str(item.get("neutral_file", ""))
        snapshot = snapshots.get(filename)
        declared = str(item.get("sha256", "")).upper()
        if snapshot is None:
            errors.append(f"missing committed governing file snapshot: {filename}")
        elif hashlib.sha256(snapshot.content).hexdigest().upper() != declared:
            errors.append(f"neutral governing file hash mismatch: {filename}")
    return expected_hash, page_count


def read_upstream_ledgers(
    module: Any, root: Path, expected_hash: str, page_count: int,
    errors: list[str],
) -> dict[str, Any]:
    specifications = {
        "page_inventory": (
            "00-page-inventory.csv", module.PAGE_INVENTORY_COLUMNS, {"PrintedPage"},
        ),
        "page_ledger": (
            "02-page-layout-ledger.csv", module.PAGE_LEDGER_COLUMNS, {"PrintedPage"},
        ),
        "bib_inventory": (
            "00-bibliography-inventory.csv", module.BIB_INVENTORY_COLUMNS, set(),
        ),
        "bib_ledger": (
            "03-bibliography-audit-ledger.csv", module.BIB_LEDGER_COLUMNS, set(),
        ),
        "citation_inventory": (
            "00-citation-inventory.csv", module.CITATION_INVENTORY_COLUMNS, set(),
        ),
        "citation_ledger": (
            "04-citation-claim-audit-ledger.csv", module.CITATION_LEDGER_COLUMNS,
            {"ContentSourceOpened", "ExactSourceLocator"},
        ),
    }
    result: dict[str, Any] = {}
    for key, (filename, columns, blank_allowed) in specifications.items():
        rows = module.read_csv(root / filename, columns, errors, require_rows=True)
        module.validate_rows_mandatory(
            rows, filename, columns, errors, blank_allowed=blank_allowed
        )
        module.validate_pdf_hash(rows, filename, expected_hash, errors)
        result[key] = rows

    page_inventory = result["page_inventory"]
    page_ledger = result["page_ledger"]
    page_inv_by_id = module.index_unique(
        page_inventory, "PageID", "00-page-inventory.csv", errors
    )
    page_led_by_id = module.index_unique(
        page_ledger, "PageID", "02-page-layout-ledger.csv", errors
    )
    module.compare_sets("page ledger", set(page_inv_by_id), set(page_led_by_id), errors)
    if len(page_inventory) != page_count:
        errors.append(
            f"00-page-inventory.csv: row count {len(page_inventory)} != "
            f"physical_page_count {page_count}"
        )
    if len(page_ledger) != page_count:
        errors.append(
            f"02-page-layout-ledger.csv: row count {len(page_ledger)} != "
            f"physical_page_count {page_count}"
        )
    module.validate_markdown_csv_projection(
        root / "02-page-layout-ledger.md",
        module.PAGE_MARKDOWN_HEADERS,
        module.page_markdown_projection_rows(page_ledger),
        "page-ledger",
        errors,
    )

    bib_inventory = result["bib_inventory"]
    bib_ledger = result["bib_ledger"]
    bib_by_id = module.index_unique(
        bib_inventory, "ReferenceID", "00-bibliography-inventory.csv", errors
    )
    bib_keys = Counter(
        (row.get("ReferenceID", ""), row.get("Field", "")) for row in bib_ledger
    )
    expected_bib_keys = {
        (reference_id, field)
        for reference_id in bib_by_id
        for field in module.BIB_FIELDS
    }
    module.compare_sets(
        "bibliography field ledger", expected_bib_keys, set(bib_keys), errors
    )
    duplicates = sorted(key for key, count in bib_keys.items() if count != 1)
    if duplicates:
        errors.append(f"03-bibliography-audit-ledger.csv: duplicate field keys {duplicates}")
    module.validate_markdown_csv_projection(
        root / "03-bibliography-audit-ledger.md",
        module.BIB_MARKDOWN_HEADERS,
        module.bibliography_markdown_projection_rows(bib_inventory, bib_ledger),
        "bibliography-ledger",
        errors,
    )

    citation_inventory = result["citation_inventory"]
    citation_ledger = result["citation_ledger"]
    citation_by_pair = module.index_unique(
        citation_inventory, "PairID", "00-citation-inventory.csv", errors
    )
    citation_ledger_by_pair = module.index_unique(
        citation_ledger, "PairID", "04-citation-claim-audit-ledger.csv", errors
    )
    module.compare_sets(
        "citation-claim ledger", set(citation_by_pair), set(citation_ledger_by_pair), errors
    )
    module.validate_citation_pair_row_order(citation_inventory, citation_ledger, errors)
    module.validate_markdown_csv_projection(
        root / "04-citation-claim-audit-ledger.md",
        module.CITATION_MARKDOWN_HEADERS,
        module.citation_markdown_projection_rows(citation_ledger, bib_by_id),
        "citation-claim-ledger",
        errors,
    )
    result.update(page_inv_by_id=page_inv_by_id, bib_by_id=bib_by_id)
    return result


def validate_scoped_semantic_gate(
    module: Any,
    semantic_module: Any,
    root: Path,
    process: dict[str, Any],
    reviewer_count: int,
    snapshots: dict[str, Any],
    page_ids: list[str],
    errors: list[str],
) -> None:
    gate_path = root / module.SEMANTIC_ACCEPTANCE_GATE_FILE
    gate = module.read_closed_semantic_gate(gate_path, errors)
    if gate is None:
        return
    expected_top = {
        "schema", "round_id", "retry_id", "pdf_sha256", "process_sha256",
        "sa_actor_prompt_sha256", "targets", "status",
    }
    if set(gate) != expected_top:
        errors.append(
            f"{gate_path.name}: top-level key set mismatch; "
            f"missing={sorted(expected_top-set(gate))}, "
            f"extra={sorted(set(gate)-expected_top)}"
        )
    process_hash = hashlib.sha256(
        snapshots["00-process-parameters.json"].content
    ).hexdigest().upper()
    expected_scalars = {
        "schema": "thesis-review-semantic-acceptance-gate-v2",
        "round_id": str(process.get("round_id", "")),
        "retry_id": str(process.get("retry_id", "")),
        "pdf_sha256": str(process.get("selected_pdf_sha256", "")).upper(),
        "process_sha256": process_hash,
        "status": "PASS",
    }
    for key, expected in expected_scalars.items():
        if gate.get(key) != expected:
            errors.append(f"{gate_path.name}: {key} must equal {expected!r}")
    targets = gate.get("targets")
    if not isinstance(targets, dict):
        errors.append(f"{gate_path.name}: targets must be one object")
        return
    expected_targets = [
        *(f"R{index}" for index in range(1, reviewer_count + 1)), "AI"
    ]
    if set(targets) != set(expected_targets):
        errors.append(
            f"{gate_path.name}: target actor set mismatch; "
            f"missing={sorted(set(expected_targets)-set(targets))}, "
            f"extra={sorted(set(targets)-set(expected_targets))}"
        )
    prompt_map = process.get("actor_prompt_sha256", {})
    expected_prompt_projection = {
        f"SA-{target}": str(prompt_map.get(f"SA-{target}", "")).upper()
        for target in expected_targets
    } if isinstance(prompt_map, dict) else {}
    if gate.get("sa_actor_prompt_sha256") != expected_prompt_projection:
        errors.append(
            f"{gate_path.name}: sa_actor_prompt_sha256 must exactly project "
            "the current process actor_prompt_sha256 values"
        )

    expected_target_keys = {
        "target_artifacts", "acceptance_md_sha256",
        "acceptance_csv_sha256", "coverage_rows", "status",
    }
    shared = semantic_module.load_shared_validator()
    derived_cache: dict[str, Any] = {}
    page_owner = "R5" if process.get("degree_level") == "doctorate" else "R3"
    citation_owner = "R4" if process.get("degree_level") == "doctorate" else "R3"
    for target in expected_targets:
        projection = targets.get(target)
        if not isinstance(projection, dict):
            errors.append(f"{gate_path.name}: target {target} must be one object")
            continue
        if set(projection) != expected_target_keys:
            errors.append(
                f"{gate_path.name}: {target} key set mismatch; "
                f"missing={sorted(expected_target_keys-set(projection))}, "
                f"extra={sorted(set(projection)-expected_target_keys)}"
            )
        if projection.get("status") != "PASS":
            errors.append(f"{gate_path.name}: {target} status must be PASS")
        for key in ("acceptance_md_sha256", "acceptance_csv_sha256"):
            value = projection.get(key)
            if not isinstance(value, str) or module.HEX64_RE.fullmatch(value) is None:
                errors.append(
                    f"{gate_path.name}: {target}.{key} must be one 64-hex "
                    "Stage-O transport commitment"
                )

        expected_artifact_names = [f"{target}-comprehensive-review.md"]
        if target == "AI":
            expected_artifact_names = ["05-ai-style-assessment.md"]
        if target == page_owner:
            expected_artifact_names.extend((
                "02-page-layout-ledger.md", "02-page-layout-ledger.csv",
                "03-bibliography-audit-ledger.md", "03-bibliography-audit-ledger.csv",
            ))
            expected_artifact_names.extend(
                f"page-renders/{page_id}.png" for page_id in page_ids
            )
        if target == citation_owner:
            expected_artifact_names.extend((
                "04-citation-claim-audit-ledger.md",
                "04-citation-claim-audit-ledger.csv",
            ))
        declared = projection.get("target_artifacts")
        if not isinstance(declared, dict):
            errors.append(f"{gate_path.name}: {target}.target_artifacts must be an object")
            declared = {}
        if set(declared) != set(expected_artifact_names):
            errors.append(
                f"{gate_path.name}: {target} target artifact names must "
                "equal the exact current target universe"
            )
        for relative in expected_artifact_names:
            declared_hash = declared.get(relative)
            if not isinstance(declared_hash, str) or module.HEX64_RE.fullmatch(
                declared_hash
            ) is None:
                errors.append(
                    f"{gate_path.name}: {target} artifact {relative} lacks a "
                    "64-hex hash commitment"
                )
                continue
            if relative.startswith("page-renders/"):
                continue
            snapshot = snapshots.get(relative)
            if snapshot is None:
                errors.append(
                    f"{gate_path.name}: visible target artifact missing from "
                    f"Stage-C snapshot: {relative}"
                )
                continue
            actual = hashlib.sha256(snapshot.content).hexdigest().upper()
            if declared_hash.upper() != actual:
                errors.append(
                    f"{gate_path.name}: {target} target artifact hash mismatch "
                    f"for {relative}"
                )
        unit_errors: list[str] = []
        units = semantic_module.expected_units(
            root, process, target, unit_errors,
            shared=shared, derived_cache=derived_cache,
        )
        errors.extend(
            f"{gate_path.name}: {target} coverage derivation: {item}"
            for item in unit_errors
        )
        coverage = projection.get("coverage_rows")
        if (
            not isinstance(coverage, int)
            or isinstance(coverage, bool)
            or coverage != len(units)
        ):
            errors.append(
                f"{gate_path.name}: {target}.coverage_rows must equal "
                f"the current expected unit count {len(units)}"
            )


def validate_chair_ledgers(
    module: Any, root: Path, page_count: int, errors: list[str],
) -> tuple[
    list[dict[str, str]], dict[str, dict[str, str]],
    list[dict[str, str]], dict[str, dict[str, str]], list[dict[str, str]],
]:
    academic = module.read_csv(
        root / "91-revision-ledger.csv", module.ACADEMIC_LEDGER_COLUMNS,
        errors, require_rows=False,
    )
    ai = module.read_csv(
        root / "91-ai-actionable-ledger.csv", module.AI_LEDGER_COLUMNS,
        errors, require_rows=False,
    )
    for rows, filename, columns in (
        (academic, "91-revision-ledger.csv", module.ACADEMIC_LEDGER_COLUMNS),
        (ai, "91-ai-actionable-ledger.csv", module.AI_LEDGER_COLUMNS),
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
    ledger_numbers: list[int] = []
    finding_numbers: list[int] = []
    finding_counts: Counter[str] = Counter()
    for line, row in enumerate(academic, start=2):
        ledger_match = re.fullmatch(r"L(\d{2,4})", row.get("LedgerID", ""))
        finding_match = re.fullmatch(r"C-F(\d{2,4})", row.get("ChairFindingID", ""))
        if ledger_match is None:
            errors.append(f"91-revision-ledger.csv:{line}: invalid LedgerID")
        else:
            ledger_numbers.append(int(ledger_match.group(1)))
        if finding_match is None:
            errors.append(f"91-revision-ledger.csv:{line}: invalid ChairFindingID")
        else:
            finding_numbers.append(int(finding_match.group(1)))
        finding_counts[row.get("ChairFindingID", "")] += 1
        severity = row.get("Severity", "").casefold()
        if severity not in module.ACADEMIC_SEVERITIES:
            errors.append(f"91-revision-ledger.csv:{line}: invalid Severity")
        subtype = row.get("S0Subtype", "").casefold()
        if severity == "s0" and subtype not in {"procedural", "integrity/foundational"}:
            errors.append(f"91-revision-ledger.csv:{line}: invalid S0Subtype for S0")
        if severity != "s0" and subtype not in {"n/a", "na", "not applicable"}:
            errors.append(f"91-revision-ledger.csv:{line}: non-S0 row requires S0Subtype N/A")
        if row.get("Remedy", "").casefold() not in module.ACADEMIC_REMEDIES:
            errors.append(f"91-revision-ledger.csv:{line}: invalid Remedy")
        if row.get("Priority", "").casefold() not in module.ACADEMIC_PRIORITIES:
            errors.append(f"91-revision-ledger.csv:{line}: invalid Priority")
        if row.get("EvidenceStatus", "").casefold() not in {
            "verified", "partially verified", "not verifiable from submitted pdf",
            "deduplicated", "disputed",
        }:
            errors.append(f"91-revision-ledger.csv:{line}: invalid EvidenceStatus")
        if row.get("Status", "").casefold() not in module.STATUS_VALUES:
            errors.append(f"91-revision-ledger.csv:{line}: invalid Status")
        page = module.parse_physical_page_locator(row.get("ExactPDFAnchor", ""))
        if page is None or page < 1 or page > page_count:
            errors.append(
                f"91-revision-ledger.csv:{line}: ExactPDFAnchor must identify "
                "a page inside the frozen PDF"
            )
    duplicate_findings = sorted(
        value for value, count in finding_counts.items() if count != 1
    )
    if duplicate_findings:
        errors.append(
            "91-revision-ledger.csv: ChairFindingID values must be unique; "
            f"duplicates={duplicate_findings}"
        )
    if ledger_numbers != list(range(1, len(ledger_numbers) + 1)):
        errors.append("91-revision-ledger.csv: LedgerID values must be continuous from L01")
    if finding_numbers != list(range(1, len(finding_numbers) + 1)):
        errors.append("91-revision-ledger.csv: ChairFindingID values must be continuous from C-F01")
    for line, row in enumerate(ai, start=2):
        if re.fullmatch(r"AI-F\d{2,4}", row.get("AIFindingID", "")) is None:
            errors.append(f"91-ai-actionable-ledger.csv:{line}: invalid AIFindingID")
        if row.get("Impact", "").casefold() not in module.AI_ACTION_IMPACTS:
            errors.append(f"91-ai-actionable-ledger.csv:{line}: invalid Impact")
        if row.get("Status", "").casefold() not in module.STATUS_VALUES:
            errors.append(f"91-ai-actionable-ledger.csv:{line}: invalid Status")
        page = module.parse_physical_page_locator(row.get("ExactPDFAnchor", ""))
        if page is None or page < 1 or page > page_count:
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: ExactPDFAnchor must identify "
                "a page inside the frozen PDF"
            )

    module.validate_markdown_id_projection(
        root / "91-revision-ledger.md", set(academic_by_id),
        re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
        {"Ledger ID", "LedgerID"}, "chair academic revision ledger", errors,
        required_headers={
            "Ledger ID", "Priority", "Chair finding ID",
            "Source reviewer finding IDs", "Severity", "S0 subtype", "Remedy",
            "Exact PDF anchor", "Direct observation", "Evidence status",
            "Minimum edit/evidence", "Dependency", "Owner", "Status", "Verification",
        }, reference_id_headers={"Dependency"},
    )
    module.validate_markdown_id_projection(
        root / "91-revision-ledger.md", set(ai_by_id),
        re.compile(r"(?<![A-Za-z0-9])AI-F\d{2,4}(?![A-Za-z0-9])"),
        {"AI finding ID", "AIFindingID"}, "chair AI-actionable ledger", errors,
        required_headers={
            "AI finding ID", "Impact (`material` / `local`)",
            "Exact PDF anchor", "Direct style observation",
            "Minimum editing action", "Status", "Verification",
        },
    )
    module.validate_chair_ledger_markdown_values(
        root / "91-revision-ledger.md", academic_by_id, ai_by_id, errors
    )
    module.validate_chair_finding_tables(
        root / "90-chair-synthesis.md", academic_by_id, ai_by_id, errors
    )

    open_academic = {
        key: row for key, row in academic_by_id.items()
        if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
    }
    evidence = module.read_csv(
        root / "92-new-evidence-or-experiments.csv",
        module.EVIDENCE_ITEM_COLUMNS, errors,
        require_rows=any(
            row.get("Remedy", "").casefold() == "n"
            for row in open_academic.values()
        ),
    )
    module.validate_rows_mandatory(
        evidence, "92-new-evidence-or-experiments.csv",
        module.EVIDENCE_ITEM_COLUMNS, errors,
    )
    numbers: list[int] = []
    evidence_by_ledger: dict[str, dict[str, str]] = {}
    for line, row in enumerate(evidence, start=2):
        match = module.EVIDENCE_ITEM_ID_RE.fullmatch(row.get("EvidenceItemID", ""))
        if match is None:
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: invalid EvidenceItemID"
            )
        else:
            numbers.append(int(match.group(1)))
        ledger_id = row.get("LedgerID", "")
        if ledger_id in evidence_by_ledger:
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: duplicate LedgerID {ledger_id}"
            )
        evidence_by_ledger[ledger_id] = row
        source = open_academic.get(ledger_id)
        if source is None or source.get("Remedy", "").casefold() != "n":
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: LedgerID must refer "
                "to one open Remedy=N row"
            )
        elif (
            row.get("ChairFindingID") != source.get("ChairFindingID")
            or row.get("Remedy", "").casefold() != "n"
        ):
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: 91 projection mismatch"
            )
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append(
            "92-new-evidence-or-experiments.csv: EvidenceItemID values must be "
            "continuous from N01"
        )
    open_n = {
        key: row for key, row in open_academic.items()
        if row.get("Remedy", "").casefold() == "n"
    }
    module.compare_sets(
        "92 evidence coverage of open Remedy=N rows",
        set(open_n), set(evidence_by_ledger), errors,
    )
    if list(evidence_by_ledger) != list(open_n):
        errors.append(
            "92-new-evidence-or-experiments.csv: row order must follow open "
            "Remedy=N rows in 91"
        )

    evidence_text = (root / "92-new-evidence-or-experiments.md").read_text(
        encoding="utf-8", errors="replace"
    )
    for heading in (
        "No-new-experiment remedies (W/E/P)",
        "Genuine new experiments or unavailable evidence (N)",
    ):
        if module.markdown_section_body_raw(evidence_text, heading) is None:
            errors.append(
                f"92-new-evidence-or-experiments.md: missing required section {heading!r}"
            )
    no_new_rows = module.parse_markdown_table_by_exact_headers(
        module.markdown_section_body_raw(
            evidence_text, "No-new-experiment remedies (W/E/P)"
        ) or "",
        ["Ledger ID", "Remedy", "Exact PDF anchor", "Minimum edit/evidence", "Verification"],
        "92-new-evidence-or-experiments.md", errors,
    )
    expected_no_new = [
        module.markdown_projection_row(
            row,
            ("LedgerID", "Remedy", "ExactPDFAnchor", "MinimumEditEvidence", "Verification"),
        )
        for row in open_academic.values()
        if row.get("Remedy", "").casefold() in {"w", "e", "p"}
    ]
    if no_new_rows is not None and no_new_rows != expected_no_new:
        errors.append(
            "92-new-evidence-or-experiments.md: W/E/P table must exactly "
            "project open non-N 91 rows"
        )
    experiment_rows = module.parse_markdown_table_by_exact_headers(
        module.markdown_section_body_raw(
            evidence_text, "Genuine new experiments or unavailable evidence (N)"
        ) or "",
        [
            "Evidence item ID", "Ledger ID", "Chair finding ID", "Remedy", "Item",
            "Claim that depends on it", "Why writing is insufficient",
            "Minimum viable evidence", "Consequence if unavailable",
        ],
        "92-new-evidence-or-experiments.md", errors,
    )
    expected_experiments = module.markdown_projection_rows(
        evidence, module.EVIDENCE_ITEM_COLUMNS
    )
    if experiment_rows is not None and experiment_rows != expected_experiments:
        errors.append(
            "92-new-evidence-or-experiments.md: N table must exactly project CSV"
        )
    return academic, academic_by_id, ai, ai_by_id, evidence


def validate_panel_and_chair(
    module: Any,
    root: Path,
    process: dict[str, Any],
    reviewer_count: int,
    expected_hash: str,
    page_count: int,
    ledgers: dict[str, Any],
    academic: list[dict[str, str]],
    academic_by_id: dict[str, dict[str, str]],
    ai_by_id: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    rule_endpoints = set(module.governing_rule_public_endpoint_sequence(process))
    bib_endpoints = module.bibliography_ledger_public_endpoints(ledgers["bib_ledger"])
    citation_endpoints = module.citation_ledger_public_endpoints(
        ledgers["citation_ledger"]
    )
    page_owner = "R5" if reviewer_count == 5 else "R3"
    citation_owner = "R4" if reviewer_count == 5 else "R3"
    owner_vectors = module.build_owner_expected_vectors(
        ledgers["page_inventory"], ledgers["page_ledger"],
        ledgers["bib_inventory"], ledgers["bib_ledger"],
        ledgers["citation_inventory"], ledgers["citation_ledger"],
    )
    current_findings: dict[str, dict[str, str]] = {}
    current_questions: dict[str, list[str]] = {}
    persona_emphases: list[str] = []
    for index in range(1, reviewer_count + 1):
        actor = f"R{index}"
        allowed = set(rule_endpoints)
        if actor == page_owner:
            allowed |= bib_endpoints
        if actor == citation_owner:
            allowed |= citation_endpoints
        path = root / f"{actor}-comprehensive-review.md"
        module.validate_reviewer_report(
            path, expected_hash, index, process, reviewer_count,
            allowed, allowed, str(process.get("degree_level", "")),
            process.get("decision_regime_status"),
            module.process_governing_sources(process), owner_vectors,
            page_count, errors,
        )
        visible = module.markdown_visible_text(
            path.read_text(encoding="utf-8", errors="replace")
        )
        current_findings.update(
            module.parse_reviewer_findings(visible, index, path.name, page_count, [])
        )
        current_questions.update(
            module.parse_reviewer_questions(visible, index, path.name, page_count, [])
        )
        persona_emphases.append(
            module.reviewer_verdict_projection(visible).get("persona_emphasis", "").casefold()
        )
    if any(not value for value in persona_emphases) or len(persona_emphases) != len(
        set(persona_emphases)
    ):
        errors.append("reviewer persona emphases must be nonblank and distinct")

    required_findings = {
        key for key, row in current_findings.items()
        if row.get("Severity", "").casefold() in {"s0", "s1", "s2", "s3"}
    }
    direct_rejected = module.validate_chair_report(
        root / "90-chair-synthesis.md", expected_hash, process,
        ledgers["bib_inventory"], ledgers["bib_ledger"],
        ledgers["citation_inventory"], ledgers["citation_ledger"], academic,
        required_findings, set(current_questions), reviewer_count,
        process.get("decision_regime_status"),
        module.process_governing_sources(process), errors,
    )

    source_counts: Counter[str] = Counter()
    for ledger_id, row in academic_by_id.items():
        value = row.get("SourceReviewerFindingIDs", "")
        identifiers = re.findall(r"R\d+-F\d{2,4}", value)
        canonical = ", ".join(
            sorted(
                set(identifiers),
                key=lambda item: tuple(map(int, re.findall(r"\d+", item))),
            )
        )
        residue = re.sub(r"R\d+-F\d{2,4}", "", value)
        residue = re.sub(r"[\s,，;/|]+", "", residue)
        if not identifiers or residue or value != canonical:
            errors.append(
                f"91-revision-ledger.csv:{ledger_id}: SourceReviewerFindingIDs "
                "must be a canonical duplicate-free current finding list"
            )
        source_counts.update(identifiers)
        unknown = sorted(set(identifiers) - set(current_findings))
        if unknown:
            errors.append(
                f"91-revision-ledger.csv:{ledger_id}: unknown reviewer finding IDs {unknown}"
            )
    missing = sorted(required_findings - set(source_counts) - direct_rejected)
    repeated = sorted(key for key, count in source_counts.items() if count != 1)
    duplicate_paths = sorted(set(source_counts) & direct_rejected)
    if missing:
        errors.append(f"current reviewer findings omitted from Chair adjudication: {missing}")
    if repeated:
        errors.append(f"reviewer findings must be adjudicated exactly once: {repeated}")
    if duplicate_paths:
        errors.append(f"reviewer findings enter both 91 and direct rejection: {duplicate_paths}")

    module.validate_ai_report(
        root / "05-ai-style-assessment.md", expected_hash, page_count,
        process, reviewer_count, errors,
    )
    ai_text = module.markdown_visible_text(
        (root / "05-ai-style-assessment.md").read_text(
            encoding="utf-8", errors="replace"
        )
    )
    actionable_ai = {
        key: row
        for key, row in module.parse_ai_findings(
            ai_text, "05-ai-style-assessment.md", page_count, []
        ).items()
        if row.get("Impact", "").casefold() in {"material", "local"}
    }
    module.compare_sets(
        "chair AI-actionable source findings", set(actionable_ai), set(ai_by_id), errors
    )
    for key in sorted(set(actionable_ai) & set(ai_by_id)):
        source = actionable_ai[key]
        ledger = ai_by_id[key]
        expected_mapping = {
            "Impact": source["Impact"],
            "ExactPDFAnchor": source["Location"],
            "DirectStyleObservation": source["Recurrent evidence"],
            "MinimumEditingAction": source["Minimum safe editing strategy"],
            "Verification": source["Closure test"],
        }
        for field, expected in expected_mapping.items():
            if ledger.get(field) != expected:
                errors.append(
                    f"91-ai-actionable-ledger.csv:{key}: {field} does not "
                    "exactly project the AI report"
                )
        if ledger.get("Status", "").casefold() != "open":
            errors.append(f"91-ai-actionable-ledger.csv:{key}: status must be open")

    allowed_chair_endpoints = rule_endpoints | bib_endpoints | citation_endpoints
    for filename in ("91-revision-ledger.md", "92-new-evidence-or-experiments.md"):
        module.validate_declarations(
            root / filename, expected_hash, errors,
            process=process, actor_id="C", reviewer_count=reviewer_count,
            allowed_public_endpoints=allowed_chair_endpoints,
            required_public_endpoints=set(),
        )
    module.validate_identical_actor_access_receipts(
        (
            root / "90-chair-synthesis.md", root / "91-revision-ledger.md",
            root / "92-new-evidence-or-experiments.md",
        ),
        module.canonical_stage_opened_inputs(process, reviewer_count, "C", root),
        (
            *module.governing_rule_public_endpoint_sequence(process),
            *module.bibliography_ledger_public_endpoint_sequence(ledgers["bib_ledger"]),
            *module.citation_ledger_public_endpoint_sequence(ledgers["citation_ledger"]),
        ),
        "C", errors,
    )

    chair_text = module.markdown_visible_text(
        (root / "90-chair-synthesis.md").read_text(
            encoding="utf-8", errors="replace"
        )
    )
    projection = module.chair_verdict_projection(chair_text)
    if projection.get("regime") == "skill-default":
        unresolved = [
            row for row in academic_by_id.values()
            if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
        ]
        required_grade = "A"
        if any(
            row.get("Severity", "").casefold() == "s0"
            and row.get("S0Subtype", "").casefold() == "integrity/foundational"
            for row in unresolved
        ):
            required_grade = "D"
        elif any(
            (
                row.get("Severity", "").casefold() == "s0"
                and row.get("S0Subtype", "").casefold() == "procedural"
            )
            or row.get("Severity", "").casefold() == "s1"
            or row.get("Remedy", "").casefold() == "n"
            for row in unresolved
        ):
            required_grade = "C"
        elif any(row.get("Severity", "").casefold() == "s2" for row in unresolved):
            required_grade = "B"
        if projection.get("academic_grade", "").upper() != required_grade:
            errors.append(
                "90-chair-synthesis.md: skill-default grade conflicts with "
                f"the open ledger profile; expected {required_grade}"
            )


def validate_chair(
    root: Path, module: Any, semantic_module: Any,
    helper_inputs: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    process, reviewer_count, expected_files, snapshots, root_snapshot = (
        preflight_chair_boundary(module, root, helper_inputs or [], errors)
    )
    if process is None:
        return errors
    with frozen_path_reads(root, snapshots):
        expected_hash, page_count = validate_process_and_pdf(
            module, root, process, reviewer_count, snapshots, errors
        )
        if expected_hash and page_count:
            ledgers = read_upstream_ledgers(
                module, root, expected_hash, page_count, errors
            )
            validate_scoped_semantic_gate(
                module, semantic_module, root, process, reviewer_count, snapshots,
                list(ledgers["page_inv_by_id"]), errors,
            )
            academic, academic_by_id, _ai, ai_by_id, _evidence = (
                validate_chair_ledgers(module, root, page_count, errors)
            )
            validate_panel_and_chair(
                module, root, process, reviewer_count, expected_hash, page_count,
                ledgers, academic, academic_by_id, ai_by_id, errors,
            )

    if _directory_snapshot(module, root, "Stage-C view root", errors) != root_snapshot:
        errors.append("Stage-C root directory identity changed during validation")
    if _scan_exact_tree(
        module, root, _expected_tree(expected_files), errors
    ) != _expected_tree(expected_files):
        errors.append("closed Stage-C file universe changed during validation")
    final_snapshots = _capture_files(module, root, expected_files, errors)
    if final_snapshots != snapshots:
        errors.append("Stage-C file identity or bytes changed during validation")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only scoped validator for one exact private Stage-C view"
    )
    parser.add_argument("chair_view_directory", type=Path)
    parser.add_argument(
        "--helper-input",
        action="append",
        default=[],
        help=(
            "exact C-recipient helper path relative to the private view; repeat "
            "in canonical provenance/output order"
        ),
    )
    args = parser.parse_args(argv)
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_module(VALIDATOR, "thesis_review_bundle_validator_for_chair")
        semantic_module = load_module(
            SEMANTIC_VALIDATOR, "thesis_review_semantic_validator_for_chair"
        )
        return print_result(
            validate_chair(
                args.chair_view_directory.absolute(), module, semantic_module,
                args.helper_input,
            )
        )
    except Exception as exc:
        return print_result([f"Chair validator could not complete safely: {exc}"])
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


if __name__ == "__main__":
    raise SystemExit(main())
