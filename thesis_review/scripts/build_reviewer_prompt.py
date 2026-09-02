#!/usr/bin/env python3
"""Plan and verify canonical Stage-R reviewer operational prompts.

``plan`` is deliberately usable before the final process envelope exists.  It
depends only on stable administrative fields, the eventual absolute round-root
path, and (optionally) already planned helper basenames.  ``verify`` runs after
Stage P and any Stage-H helpers have been frozen.  It reconstructs the prompt
from the final process and the validator-derived Stage-R allowlist, proves the
prompt's exact bytes and SHA-256 commitment, and authenticates every staged
validator named by that prompt.

This helper does not read the thesis, reviewer output, or any review finding.
It is Stage-O process control only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from actor_prompt_contract import render_bound_actor_contract  # noqa: E402


PROMPT_SCHEMA = "thesis-review-stage-r-operational-prompt-v3"
VERIFICATION_SCHEMA = "thesis-review-stage-r-prompt-verification-v2"
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
ACTOR_RE = re.compile(r"R([1-5])\Z")
PROCESS_COMMITMENT_RE = re.compile(
    r"(?m)^- Process-parameter file and SHA-256: "
    r"00-process-parameters\.json / ([0-9A-F]{64})$"
)
VALIDATOR_COMMITMENT_RE = re.compile(
    r"(?m)^- (rules/scripts/[A-Za-z0-9_-]+\.py) SHA-256: "
    r"([0-9A-F]{64})$"
)
STABLE_PROCESS_FIELDS = (
    "round_id",
    "retry_id",
    "frozen_pdf_file",
    "selected_pdf_sha256",
    "physical_page_count",
    "degree_level",
    "governing_local_files",
    "output_language",
)
FULL_VALIDATOR_RELATIVE = Path("rules/scripts/validate_review_bundle.py")
SCRATCH_SCHEMA = "thesis-review-stage-r-actor-scratch-v1"


class ContractError(RuntimeError):
    """Fail-closed error for reviewer-prompt planning or verification."""


def uses_windows_unc_or_device_namespace(path: Path) -> bool:
    """Return whether ``path`` uses a Windows UNC/device namespace.

    A UNC share may be rooted at an arbitrary descendant of the run directory.
    Its lexical ancestor chain therefore cannot prove that the target is
    outside the run.  Keep this test independent of filesystem reachability so
    an unavailable or attacker-controlled share is rejected before any probe.
    ``WindowsPath`` normalizes forward-slash UNC spellings, but normalizing here
    as well makes the boundary explicit and robust for path-like callers.
    """

    spelling = os.fspath(path).replace("/", "\\")
    return spelling.startswith("\\\\")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def require_no_windows_named_streams(path: Path, label: str) -> None:
    """Reject NTFS named streams hidden from ordinary directory traversal."""

    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class Win32FindStreamData(ctypes.Structure):
        _fields_ = [
            ("stream_size", ctypes.c_longlong),
            ("stream_name", ctypes.c_wchar * 296),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        ctypes.POINTER(Win32FindStreamData),
        wintypes.DWORD,
    ]
    find_first.restype = wintypes.HANDLE
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Win32FindStreamData),
    ]
    find_next.restype = wintypes.BOOL
    find_close = kernel32.FindClose
    find_close.argtypes = [wintypes.HANDLE]
    find_close.restype = wintypes.BOOL

    data = Win32FindStreamData()
    handle = find_first(os.fspath(path), 0, ctypes.byref(data), 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        if error == 38:  # ERROR_HANDLE_EOF
            return
        raise ContractError(
            f"cannot enumerate Windows streams for {label} {path}: error {error}"
        )
    streams: list[str] = []
    try:
        while True:
            streams.append(str(data.stream_name))
            if find_next(handle, ctypes.byref(data)):
                continue
            error = ctypes.get_last_error()
            if error != 38:  # ERROR_HANDLE_EOF
                raise ContractError(
                    f"cannot complete Windows stream enumeration for {label} "
                    f"{path}: error {error}"
                )
            break
    finally:
        if not find_close(handle):
            error = ctypes.get_last_error()
            raise ContractError(
                f"cannot close Windows stream enumeration for {label} "
                f"{path}: error {error}"
            )
    named = [name for name in streams if name != "::$DATA"]
    if named:
        raise ContractError(
            f"{label} must not carry NTFS named streams: {path}: {named}"
        )


def absolute_no_alias(
    value: Path,
    label: str,
    *,
    must_exist: bool,
) -> Path:
    """Return one absolute lexical path without erasing alias evidence.

    ``Path.resolve`` is intentionally unsuitable for process-control inputs: it
    follows a symlink/reparse component and therefore discards the evidence we
    need to reject.  Inspect every existing component before accepting the
    normalized absolute spelling.
    """

    path = Path(value)
    if not path.is_absolute():
        raise ContractError(f"{label} must be absolute")
    if os.name == "nt" and uses_windows_unc_or_device_namespace(path):
        # Windows permits the same local object to be exposed through an
        # arbitrary nested SMB share.  A share root can itself map below the
        # run root, so no lexical ancestor of ``\\host\share\child`` need have
        # the identity of ``C:\run``.  Rejecting every UNC/device namespace at
        # the Stage-R control boundary is the only fail-closed rule that does
        # not require enumerating host share mappings.  Drive-letter paths
        # remain fully checked for reparse and 8.3 aliases below.
        raise ContractError(
            f"{label} must not use a UNC/device namespace path"
        )
    if os.name == "nt" and any(":" in part for part in path.parts[1:]):
        raise ContractError(
            f"{label} must not use an NTFS alternate data stream path"
        )
    if any(part == ".." for part in path.parts):
        raise ContractError(f"{label} must not contain lexical parent traversal")
    if any(character in os.fspath(path) for character in ('"', "\r", "\n")):
        raise ContractError(f"{label} contains a command-unsafe character")
    normalized = Path(os.path.abspath(os.fspath(path)))
    current = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise ContractError(f"cannot inspect {label} component {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise ContractError(
                f"{label} traverses a symlink/reparse component: {current}"
            )
        require_no_windows_named_streams(current, f"{label} path component")
    if must_exist and not os.path.lexists(normalized):
        raise ContractError(f"{label} is missing: {normalized}")
    # ``abspath`` preserves NTFS 8.3 short-name spellings.  Lexical containment
    # checks on that spelling can otherwise describe an in-run path as external
    # even though both names resolve to the same file or directory.  We already
    # rejected every reparse component above, so resolving the existing target
    # (or the existing parent of a not-yet-created output) is safe and lets us
    # reject all alternate filesystem spellings before they enter prompt bytes.
    canonical_probe = normalized if os.path.lexists(normalized) else normalized.parent
    if not os.path.lexists(canonical_probe):
        raise ContractError(f"{label} parent must already exist: {normalized.parent}")
    try:
        canonical_probe_resolved = canonical_probe.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"cannot canonicalize {label}: {exc}") from exc
    if os.path.normcase(os.fspath(canonical_probe)) != os.path.normcase(
        os.fspath(canonical_probe_resolved)
    ):
        raise ContractError(
            f"{label} must use its canonical filesystem spelling; aliases such "
            "as NTFS 8.3 short names are forbidden"
        )
    return normalized


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def deepest_existing_ancestor(path: Path, label: str) -> Path:
    """Return the closest existing path at or above ``path``.

    Prompt outputs do not exist at planning time, so a physical-boundary check
    must begin at their existing parent.  Walking one component at a time also
    avoids resolving away the alternate namespace whose identity we need to
    compare (for example ``C:\\...`` versus ``\\\\localhost\\C$\\...``).
    """

    current = path
    while not os.path.lexists(current):
        parent = current.parent
        if parent == current:
            raise ContractError(
                f"cannot find an existing ancestor for {label}: {path}"
            )
        current = parent
    return current


def is_physically_within(path: Path, parent: Path) -> bool:
    """Compare containment by filesystem identity, including path aliases.

    Lexical containment is insufficient on Windows: an NTFS object reachable
    below ``C:\\run`` can also be named through the administrative-share UNC
    namespace ``\\\\localhost\\C$\\run``.  ``Path.resolve`` preserves those two
    namespaces, while ``os.path.samefile`` correctly identifies the object.
    """

    if os.name == "nt" and (
        uses_windows_unc_or_device_namespace(path)
        or uses_windows_unc_or_device_namespace(parent)
    ):
        # Do not let a direct caller bypass ``absolute_no_alias`` and interpret
        # exhaustion at an SMB share root as proof that the candidate is
        # external.  A nested share root can itself identify a descendant of
        # ``parent`` even though no visible UNC ancestor is samefile(parent).
        raise ContractError(
            "cannot prove physical containment across a UNC/device namespace "
            "boundary"
        )

    parent_probe = deepest_existing_ancestor(parent, "containment parent")
    if parent_probe != parent:
        raise ContractError(
            f"containment parent must already exist: {parent}"
        )
    current = deepest_existing_ancestor(path, "containment candidate")
    while True:
        try:
            if os.path.samefile(current, parent_probe):
                return True
        except OSError as exc:
            raise ContractError(
                "cannot compare filesystem identity for containment boundary "
                f"{current} against {parent_probe}: {exc}"
            ) from exc
        next_parent = current.parent
        if next_parent == current:
            return False
        current = next_parent


def is_within_boundary(path: Path, parent: Path) -> bool:
    """Return true for either lexical or physical-identity containment."""

    return is_within(path, parent) or is_physically_within(path, parent)


def boundaries_overlap(left: Path, right: Path) -> bool:
    """Return true when either boundary contains the other by any namespace."""

    return is_within_boundary(left, right) or is_within_boundary(right, left)


def require_safe_directory(path: Path, label: str) -> None:
    if is_link_or_reparse(path) or not path.is_dir():
        raise ContractError(
            f"{label} is missing, not a directory, or link/reparse-backed: {path}"
        )
    require_no_windows_named_streams(path, label)


def require_safe_regular(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ContractError(f"cannot inspect {label}: {path}: {exc}") from exc
    if (
        is_link_or_reparse(path)
        or not stat.S_ISREG(metadata.st_mode)
        or int(metadata.st_nlink) != 1
    ):
        raise ContractError(
            f"{label} must be a non-aliased single-link regular file: {path}"
        )
    require_no_windows_named_streams(path, label)


def regular_file_snapshot(path: Path, label: str) -> tuple[str, dict[str, int]]:
    """Hash one unlinked regular file while checking path/open stability."""

    require_safe_regular(path, label)
    try:
        lexical_before = os.lstat(path)
    except OSError as exc:
        raise ContractError(f"cannot inspect {label}: {exc}") from exc
    if (
        not stat.S_ISREG(lexical_before.st_mode)
        or lexical_before.st_nlink != 1
        or bool(getattr(lexical_before, "st_file_attributes", 0) & 0x400)
    ):
        raise ContractError(f"{label} must be one unlinked regular file: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            opened_before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened_before.st_mode)
                or opened_before.st_nlink != 1
                or opened_before.st_dev != lexical_before.st_dev
                or opened_before.st_ino != lexical_before.st_ino
            ):
                raise ContractError(f"{label} pathname/open identity mismatch")
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            opened_after = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened_after.st_mode)
                or int(opened_after.st_nlink) != 1
            ):
                raise ContractError(
                    f"{label} must remain a single-link regular file while opened"
                )
        lexical_after = os.lstat(path)
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError(f"cannot snapshot {label}: {exc}") from exc
    stable_fields = ("st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns")
    if (
        any(
            getattr(opened_before, field) != getattr(opened_after, field)
            for field in (*stable_fields, "st_mode")
        )
        or any(
            getattr(lexical_before, field) != getattr(lexical_after, field)
            for field in (*stable_fields, "st_mode")
        )
        or any(
            getattr(opened_after, field) != getattr(lexical_after, field)
            for field in stable_fields
        )
        or not stat.S_ISREG(opened_after.st_mode)
        or not stat.S_ISREG(lexical_after.st_mode)
        or bool(getattr(lexical_after, "st_file_attributes", 0) & 0x400)
    ):
        raise ContractError(f"{label} changed during snapshot")
    require_no_windows_named_streams(path, label)
    try:
        lexical_terminal = os.lstat(path)
    except OSError as exc:
        raise ContractError(f"cannot recheck {label}: {exc}") from exc
    if (
        any(
            getattr(lexical_after, field) != getattr(lexical_terminal, field)
            for field in (*stable_fields, "st_mode")
        )
        or not stat.S_ISREG(lexical_terminal.st_mode)
        or int(lexical_terminal.st_nlink) != 1
        or bool(getattr(lexical_terminal, "st_file_attributes", 0) & 0x400)
    ):
        raise ContractError(f"{label} changed during terminal snapshot check")
    return digest.hexdigest().upper(), {
        field: int(getattr(lexical_terminal, field))
        for field in (*stable_fields, "st_mode")
    }


def strict_json_bytes(value: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = item
        return result

    try:
        parsed = json.loads(
            value.decode("utf-8-sig"), object_pairs_hook=reject_duplicates
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractError(f"cannot parse {label}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ContractError(f"{label} must contain one JSON object")
    return parsed


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    require_safe_regular(path, label)
    try:
        return strict_json_bytes(path.read_bytes(), label)
    except OSError as exc:
        raise ContractError(f"cannot read {label}: {exc}") from exc


def safe_basename(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"stable process field {label} must be a nonempty trimmed string")
    if (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
    ):
        raise ContractError(f"stable process field {label} must be a basename")
    return value


def stable_process_projection(process: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in STABLE_PROCESS_FIELDS if field not in process]
    if missing:
        raise ContractError(f"preplan process is missing stable field(s): {missing}")
    for field in ("round_id", "retry_id", "output_language"):
        value = process.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ContractError(
                f"stable process field {field} must be a nonempty trimmed string"
            )
    degree = process.get("degree_level")
    if degree not in {"masters", "doctorate"}:
        raise ContractError("stable process field degree_level must be masters or doctorate")
    pdf_name = safe_basename(process.get("frozen_pdf_file"), "frozen_pdf_file")
    pdf_hash = process.get("selected_pdf_sha256")
    if not isinstance(pdf_hash, str) or HEX64_RE.fullmatch(pdf_hash) is None:
        raise ContractError(
            "stable process field selected_pdf_sha256 must be 64 hexadecimal characters"
        )
    page_count = process.get("physical_page_count")
    if (
        not isinstance(page_count, int)
        or isinstance(page_count, bool)
        or page_count < 1
    ):
        raise ContractError(
            "stable process field physical_page_count must be a positive integer"
        )
    governing = process.get("governing_local_files")
    if not isinstance(governing, list):
        raise ContractError("stable process field governing_local_files must be a list")
    governing_projection: list[dict[str, str]] = []
    for index, item in enumerate(governing):
        if not isinstance(item, dict):
            raise ContractError(
                f"governing_local_files[{index}] must be an object with neutral_file"
            )
        governing_projection.append(
            {
                "neutral_file": safe_basename(
                    item.get("neutral_file"),
                    f"governing_local_files[{index}].neutral_file",
                )
            }
        )
    governing_names = [item["neutral_file"] for item in governing_projection]
    if len(governing_names) != len(set(governing_names)):
        raise ContractError("stable governing neutral_file names must be duplicate-free")
    return {
        "round_id": process["round_id"],
        "retry_id": process["retry_id"],
        "frozen_pdf_file": pdf_name,
        "selected_pdf_sha256": pdf_hash.upper(),
        "physical_page_count": page_count,
        "degree_level": degree,
        "governing_local_files": governing_projection,
        "output_language": process["output_language"],
    }


def reviewer_count(process: dict[str, Any]) -> int:
    return 5 if process["degree_level"] == "doctorate" else 3


def require_reviewer_actor(process: dict[str, Any], actor: str) -> str:
    normalized = actor.upper()
    match = ACTOR_RE.fullmatch(normalized)
    if match is None:
        raise ContractError(f"invalid Stage-R actor {actor!r}")
    index = int(match.group(1))
    if index > reviewer_count(process):
        raise ContractError(
            f"{normalized} is not required for degree_level={process['degree_level']!r}"
        )
    return normalized


def load_validator_from_source(path: Path, module_name: str) -> Any:
    require_safe_regular(path, "canonical review-bundle validator")
    try:
        source = path.read_bytes()
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = ""
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
        return module
    except Exception as exc:
        raise ContractError(f"cannot source-load {path.name}: {exc}") from exc


def canonical_validator() -> Any:
    return load_validator_from_source(
        Path(__file__).with_name("validate_review_bundle.py"),
        "thesis_review_bundle_validator_for_stage_r_prompt",
    )


def canonical_retry_manager() -> Any:
    return load_validator_from_source(
        Path(__file__).with_name("manage_review_retry.py"),
        "thesis_review_retry_manager_for_stage_r_prompt",
    )


def validate_python_executable(value: Path) -> tuple[Path, str]:
    executable = absolute_no_alias(
        value, "bundled/workspace Python executable", must_exist=True
    )
    running_executable = absolute_no_alias(
        Path(sys.executable), "currently executing Python interpreter", must_exist=True
    )
    if os.path.normcase(os.fspath(executable)) != os.path.normcase(
        os.fspath(running_executable)
    ):
        raise ContractError(
            "--python-executable must be the exact Python interpreter executing "
            f"this helper: expected {running_executable}, got {executable}"
        )
    digest, identity = regular_file_snapshot(
        executable, "bundled/workspace Python executable"
    )
    running_digest, running_identity = regular_file_snapshot(
        running_executable, "currently executing Python interpreter"
    )
    for field in ("st_dev", "st_ino"):
        if identity[field] != running_identity[field]:
            raise ContractError(
                "--python-executable does not identify the interpreter executing "
                "this helper"
            )
    if digest != running_digest:
        raise ContractError(
            "--python-executable bytes differ from the interpreter executing this helper"
        )
    return executable, digest


def scratch_identity_token(
    round_root: Path,
    process: dict[str, Any],
    actor: str,
) -> str:
    payload = {
        "schema": SCRATCH_SCHEMA,
        "round_root": str(round_root),
        "round_id": process["round_id"],
        "retry_id": process["retry_id"],
        "actor": actor,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)[:24].lower()


def expected_scratch_basename(
    round_root: Path,
    process: dict[str, Any],
    actor: str,
) -> str:
    return f"stage-r-{actor.casefold()}-{scratch_identity_token(round_root, process, actor)}"


def validate_actor_scratch(
    value: Path,
    round_root: Path,
    process: dict[str, Any],
    actor: str,
    *,
    run_root: Path | None = None,
) -> Path:
    scratch = absolute_no_alias(value, "actor-private scratch directory", must_exist=True)
    require_safe_directory(scratch, "actor-private scratch directory")
    expected_name = expected_scratch_basename(round_root, process, actor)
    if scratch.name != expected_name:
        raise ContractError(
            "actor-private scratch directory must use the unique Stage-R basename "
            f"{expected_name!r}"
        )
    if boundaries_overlap(scratch, round_root):
        raise ContractError(
            "actor-private scratch directory and round root must not overlap"
        )
    if run_root is not None and boundaries_overlap(scratch, run_root):
        raise ContractError(
            "actor-private scratch directory and run root must not overlap"
        )
    try:
        first_entry = next(scratch.iterdir(), None)
    except OSError as exc:
        raise ContractError(f"cannot inspect actor-private scratch directory: {exc}") from exc
    if first_entry is not None:
        raise ContractError(
            "actor-private scratch directory must be empty at plan/verify dispatch boundary"
        )
    return scratch


def validate_helper_inputs(values: Iterable[str], validator: Any) -> list[str]:
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ContractError(f"helper input {index} must be a nonempty trimmed path")
        normalized = value.replace("\\", "/")
        path = Path(normalized)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or len(path.parts) != 2
            or path.parts[0] != "helpers"
            or not path.parts[1]
            or not validator.is_neutral_portable_basename(path.parts[1])
        ):
            raise ContractError(
                f"helper input {value!r} must be exactly helpers/<portable-basename>"
            )
        result.append(normalized)
    if len(result) != len(set(result)):
        raise ContractError("helper inputs must be duplicate-free")
    return result


def algorithmic_opened_inputs(
    process: dict[str, Any],
    actor: str,
    validator: Any,
    helper_inputs: Iterable[str] = (),
    *,
    round_root: Path | None = None,
) -> list[str]:
    actor = require_reviewer_actor(process, actor)
    opened = validator.canonical_stage_opened_inputs(
        process, reviewer_count(process), actor, round_root
    )
    helpers = validate_helper_inputs(helper_inputs, validator)
    discovered_helpers = [item for item in opened if item.startswith("helpers/")]
    if round_root is None:
        if discovered_helpers:
            raise ContractError(
                "preplan Stage-R allowlist unexpectedly contains discovered helpers"
            )
        combined = [*opened, *helpers]
    else:
        if discovered_helpers != helpers:
            raise ContractError(
                "frozen Stage-H helper allowlist differs from the explicitly planned "
                f"helper inputs: planned={helpers}, frozen={discovered_helpers}"
            )
        combined = opened
    if len(combined) != len(set(combined)):
        raise ContractError("canonical Stage-R opened allowlist contains duplicates")
    return combined


def reviewer_owned_outputs(process: dict[str, Any], actor: str) -> list[str]:
    actor = require_reviewer_actor(process, actor)
    degree = process["degree_level"]
    outputs = [f"{actor}-comprehensive-review.md"]
    page_bib_owner = (degree == "doctorate" and actor == "R5") or (
        degree == "masters" and actor == "R3"
    )
    citation_owner = (degree == "doctorate" and actor == "R4") or (
        degree == "masters" and actor == "R3"
    )
    if page_bib_owner:
        outputs.extend(
            [
                "02-page-layout-ledger.md",
                "02-page-layout-ledger.csv",
                "03-bibliography-audit-ledger.md",
                "03-bibliography-audit-ledger.csv",
            ]
        )
        outputs.extend(
            f"page-renders/P{page:04d}.png"
            for page in range(1, int(process["physical_page_count"]) + 1)
        )
    if citation_owner:
        outputs.extend(
            [
                "04-citation-claim-audit-ledger.md",
                "04-citation-claim-audit-ledger.csv",
            ]
        )
    return outputs


def canonical_validator_commitments(
    opened: Iterable[str], validator: Any
) -> dict[str, str]:
    commitments: dict[str, str] = {}
    script_root = Path(__file__).parent
    for relative in opened:
        if not relative.startswith("rules/scripts/"):
            continue
        basename = Path(relative).name
        source = script_root / basename
        commitments[relative], _identity = regular_file_snapshot(
            source, f"canonical Stage-R validator {basename}"
        )
    if FULL_VALIDATOR_RELATIVE.as_posix() not in commitments:
        raise ContractError("Stage-R allowlist omits validate_review_bundle.py")
    expected_rules = [
        item
        for item in validator.canonical_stage_opened_inputs(
            {
                "degree_level": "doctorate",
                "governing_local_files": [],
                "frozen_pdf_file": "frozen-thesis.pdf",
            },
            5,
            "R1",
            None,
        )
        if item.startswith("rules/scripts/")
    ]
    if not expected_rules:
        raise ContractError("canonical validator exposes no ordinary Stage-R gate")
    return commitments


def reviewer_gate_commands(
    python_executable: Path,
    round_root: Path,
    process: dict[str, Any],
    actor: str,
) -> list[list[str]]:
    actor = require_reviewer_actor(process, actor)
    python = str(python_executable)
    degree = process["degree_level"]
    materializer = str(round_root / "rules/scripts/materialize_owner_outputs.py")
    if degree == "doctorate" and actor == "R4":
        return [
            [python, "-B", materializer, str(round_root), "R4"],
            [
                python,
                "-B",
                str(round_root / "rules/scripts/validate_r4_output.py"),
                str(round_root),
            ],
        ]
    if degree == "doctorate" and actor == "R5":
        return [
            [python, "-B", materializer, str(round_root), "R5"],
            [
                python,
                "-B",
                str(round_root / "rules/scripts/validate_r5_output.py"),
                str(round_root),
            ],
        ]
    if degree == "masters" and actor == "R3":
        return [
            [python, "-B", materializer, str(round_root), "R3"],
            [
                python,
                "-B",
                str(round_root / "rules/scripts/validate_master_r3_output.py"),
                str(round_root),
            ],
        ]
    return [
        [
            python,
            "-B",
            str(round_root / "rules/scripts/validate_reviewer_output.py"),
            str(round_root),
            actor,
        ]
    ]


def render_prompt(
    round_root: Path,
    actor: str,
    process: dict[str, Any],
    opened: list[str],
    validator_commitments: dict[str, str],
    validator: Any,
    python_executable: Path,
    python_sha256: str,
    scratch_dir: Path,
) -> bytes:
    actor = require_reviewer_actor(process, actor)
    index = int(actor[1:])
    persona = validator.PERSONA_ASSIGNMENTS[process["degree_level"]][index]
    outputs = reviewer_owned_outputs(process, actor)
    opened_lines = "\n".join(
        f"{number}. {round_root / Path(relative)}"
        for number, relative in enumerate(opened, start=1)
    )
    output_lines = "\n".join(
        f"- {round_root / Path(relative)}" for relative in outputs
    )
    commitment_lines = "\n".join(
        f"- {relative} SHA-256: {digest}"
        for relative, digest in validator_commitments.items()
    )
    gate_commands = reviewer_gate_commands(
        python_executable, round_root, process, actor
    )
    command_lines = "\n".join(
        f"{number}. {json.dumps(command, ensure_ascii=False, separators=(',', ':'))}"
        for number, command in enumerate(
            gate_commands, start=1
        )
    )
    bound_contract = render_bound_actor_contract(actor)
    text = f"""Stage-R reviewer operational prompt

Prompt schema: {PROMPT_SCHEMA}
Actor ID: {actor}
Persona assignment: {persona}
Review round ID: {process['round_id']}
Review retry ID: {process['retry_id']}
Frozen PDF file: {round_root / process['frozen_pdf_file']}
Frozen PDF SHA-256: {process['selected_pdf_sha256']}
Frozen physical page count: {process['physical_page_count']}
Degree level: {process['degree_level']}
Output language: {process['output_language']}
Bundled/workspace Python executable: {python_executable}
Bundled/workspace Python SHA-256: {python_sha256}
Actor-private scratch directory: {scratch_dir}
Scratch identity convention: {SCRATCH_SCHEMA} / {scratch_dir.name}

Frozen validator commitments:
{commitment_lines}

{bound_contract}

Perform one independent, holistic, PDF-only review as {actor}. Apply every Gate A--I to the entire frozen thesis before the persona-weighted deep review. Do not enumerate neighboring paths, contact another actor, or open any local file not listed below. Do not use conversation history, user explanations, prior reviews, thesis source, Git, sibling papers, code, experiment records, or any other author-side material. No follow-up message will be sent after dispatch.

Round root:
{round_root}

Private scratch boundary:
Stage O may dispatch these bytes only after `verify` has confirmed that the scratch directory above is empty, outside and non-overlapping with the complete run root, and unique to this round/retry/actor by its bound basename. It is the only place for transient files created by this actor. Do not enumerate its parent or any neighboring path, and do not treat scratch content as review evidence. Remove all transient content before freeze; final outputs belong only at the actor-owned paths below.

Open exactly these local files, in this order:
{opened_lines}

Public-endpoint rule:
Open public authoritative endpoints only to verify governing rules or citations already visible in the frozen PDF, and record every endpoint actually opened in the canonical receipt. Do not search for uncited alternatives or hidden companion artifacts.

Finding evidence self-check (mandatory for every proposed S0--S4 finding):
Before retaining each finding, answer all six questions from the frozen PDF and permitted governing/citation sources:
1. What exactly is visible or stated?
2. Where is it?
3. Which claim, rule, or reader task does it affect?
4. What evidence supports the concern?
5. What is the least costly sufficient remedy?
6. Is that remedy part of the thesis or a verified formal submission obligation, rather than a request for hidden author-side proof?

Then search the whole frozen PDF for every definition, qualification, disclosure, cross-reference, or other thesis-visible remedy that the proposed finding says is missing. Search beyond the local section and inspect responsive passages and counter-evidence. If the required substance is already present, delete the finding. If a genuine inconsistency remains, retain only the minimum residual and make its `Location`, `Observation`, and `Required action` describe, respectively, the exact unreconciled physical-page passage, only the residual defect after responsive text is considered, and the least sufficient change not already present in the thesis.

If questions 1--5 cannot be answered with reasonable permitted-evidence support, downgrade the item to a `Question` only when a legitimate in-scope uncertainty remains and give that question an exact PDF anchor, why it is unresolved, and the thesis-visible evidence needed; otherwise delete it. If question 6 is answered no, delete the item and do not preserve the out-of-scope request as a finding, question, or `not verifiable` concern. This six-question check is an internal retention gate: do not add rebuttal-style checklist prose to the report.

Write only these actor-owned outputs:
{output_lines}

Follow the closed report and ledger schemas. Reconcile every actionable finding bidirectionally with Gate A--I. Issue the exact process-selected decision-regime conclusion and operational defense recommendation. Never infer an unstated training repetition count from point-estimate formatting. Do not fabricate evidence or values.

Run every Python command with bytecode writing disabled: set the exact environment entry `PYTHONDONTWRITEBYTECODE=1` and invoke only the exact bound Python executable above with `-B`. The following lines are exact argv arrays, not shell snippets; preserve every array element byte-for-byte. Before freezing, run them in order and require the final scoped validator to exit 0 with first nonempty stdout exactly PASS:
{command_lines}

For a ledger owner, rerun materialization after every owned-CSV edit before rerunning the read-only scoped gate. Correct only current actor-owned outputs. An upstream/process/PDF/rule defect stops the actor and triggers a whole-retry failure; do not patch a frozen input or peer artifact. Leave no __pycache__ directory or .pyc file.
"""
    return text.replace("\r\n", "\n").encode("utf-8")


def exclusive_write(path: Path, value: bytes) -> tuple[str, dict[str, int]]:
    if os.path.lexists(path) or is_link_or_reparse(path):
        raise ContractError(f"refusing to overwrite existing prompt output: {path}")
    require_safe_directory(path.parent, "prompt output parent")
    try:
        with path.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ContractError(f"refusing to overwrite existing prompt output: {path}") from exc
    except OSError as exc:
        raise ContractError(f"cannot create prompt output {path}: {exc}") from exc
    snapshot = regular_file_snapshot(path, "created prompt output")
    if snapshot[0] != sha256_bytes(value):
        raise ContractError(f"created prompt output hash mismatch: {path}")
    return snapshot


def plan_prompt(
    process_path_value: Path,
    round_root_value: Path,
    actor_value: str,
    output_value: Path,
    python_executable_value: Path,
    scratch_dir_value: Path,
    helper_inputs: Iterable[str] = (),
) -> dict[str, Any]:
    process_path = absolute_no_alias(
        process_path_value, "preplan process envelope", must_exist=True
    )
    round_root = absolute_no_alias(round_root_value, "round root", must_exist=True)
    output = absolute_no_alias(output_value, "planned reviewer prompt", must_exist=False)
    require_safe_directory(round_root, "round root")
    if round_root.name != "round":
        raise ContractError("round root must be exactly the 'round' child of one run root")
    inferred_run_root = absolute_no_alias(
        round_root.parent, "inferred run root", must_exist=True
    )
    require_safe_directory(inferred_run_root, "inferred run root")
    require_safe_regular(process_path, "preplan process envelope")
    preplan_snapshot = regular_file_snapshot(
        process_path, "preplan process envelope"
    )
    if is_within_boundary(output, inferred_run_root):
        raise ContractError("planned reviewer prompt must live outside the run root")
    process = stable_process_projection(
        read_json_object(process_path, "preplan process envelope")
    )
    actor = require_reviewer_actor(process, actor_value)
    python_executable, python_sha256 = validate_python_executable(
        python_executable_value
    )
    python_snapshot_sha256, python_snapshot_identity = regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    )
    if python_snapshot_sha256 != python_sha256:
        raise ContractError("Python executable changed after runtime binding")
    if is_within_boundary(python_executable, inferred_run_root):
        raise ContractError(
            "bundled/workspace Python executable must remain outside the run root"
        )
    scratch_dir = validate_actor_scratch(
        scratch_dir_value,
        round_root,
        process,
        actor,
        run_root=inferred_run_root,
    )
    if is_within_boundary(output, scratch_dir):
        raise ContractError(
            "planned reviewer prompt must remain outside the actor-private scratch directory"
        )
    validator = canonical_validator()
    opened = algorithmic_opened_inputs(
        process, actor, validator, helper_inputs=helper_inputs
    )
    commitments = canonical_validator_commitments(opened, validator)
    prompt = render_prompt(
        round_root,
        actor,
        process,
        opened,
        commitments,
        validator,
        python_executable,
        python_sha256,
        scratch_dir,
    )
    digest = sha256_bytes(prompt)
    output_snapshot = exclusive_write(output, prompt)
    if regular_file_snapshot(
        process_path, "preplan process envelope"
    ) != preplan_snapshot:
        raise ContractError("preplan process envelope changed during prompt planning")
    if regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    ) != (python_snapshot_sha256, python_snapshot_identity):
        raise ContractError("Python executable changed during prompt planning")
    validate_actor_scratch(
        scratch_dir,
        round_root,
        process,
        actor,
        run_root=inferred_run_root,
    )
    if regular_file_snapshot(output, "created prompt output") != output_snapshot:
        raise ContractError("created prompt output changed during prompt planning")
    return {
        "schema": PROMPT_SCHEMA,
        "actor": actor,
        "round_root": str(round_root),
        "prompt_file": str(output),
        "prompt_sha256": digest,
        "python_executable": str(python_executable),
        "python_executable_sha256": python_sha256,
        "scratch_dir": str(scratch_dir),
        "scratch_identity_convention": SCRATCH_SCHEMA,
        "stable_process_fields": process,
        "opened": opened,
        "owned_outputs": reviewer_owned_outputs(process, actor),
        "validator_sha256": commitments,
        "gate_commands": reviewer_gate_commands(
            python_executable, round_root, process, actor
        ),
    }


def manifest_process_commitment(round_root: Path) -> str:
    manifest = round_root / "00-manifest.md"
    require_safe_regular(manifest, "Stage-P manifest")
    try:
        text = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read Stage-P manifest: {exc}") from exc
    matches = PROCESS_COMMITMENT_RE.findall(text)
    if len(matches) != 1:
        raise ContractError(
            "Stage-P manifest must contain exactly one process-parameter SHA-256 commitment"
        )
    return matches[0].upper()


def parse_prompt_validator_commitments(prompt: bytes) -> dict[str, str]:
    try:
        text = prompt.decode("utf-8")
    except UnicodeError as exc:
        raise ContractError(f"reviewer prompt is not valid UTF-8: {exc}") from exc
    matches = VALIDATOR_COMMITMENT_RE.findall(text)
    commitments: dict[str, str] = {}
    for relative, digest in matches:
        if relative in commitments:
            raise ContractError(
                f"reviewer prompt duplicates validator commitment {relative}"
            )
        commitments[relative] = digest.upper()
    return commitments


def verify_staged_validator_commitments(
    round_root: Path, expected: dict[str, str]
) -> None:
    for relative, digest in expected.items():
        path = round_root / Path(relative)
        actual, _identity = regular_file_snapshot(
            path, f"staged reviewer validator {relative}"
        )
        if actual != digest:
            raise ContractError(
                f"staged reviewer validator hash mismatch for {relative}: "
                f"expected {digest}, got {actual}"
            )


def snapshot_helper_inputs(
    round_root: Path,
    opened: Iterable[str],
) -> dict[str, tuple[str, dict[str, int]]]:
    snapshots: dict[str, tuple[str, dict[str, int]]] = {}
    for relative in opened:
        if not relative.startswith("helpers/"):
            continue
        snapshots[relative] = regular_file_snapshot(
            round_root / Path(relative), f"frozen Stage-H helper input {relative}"
        )
    return snapshots


def require_safe_round_relative_file(
    round_root: Path, relative: str, label: str
) -> Path:
    relative_path = Path(relative)
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or "." in relative_path.parts
        or not relative_path.parts
        or any(":" in part for part in relative_path.parts)
    ):
        raise ContractError(f"{label} is not a safe round-relative file: {relative}")
    current = round_root
    require_safe_directory(current, "round root")
    for part in relative_path.parts[:-1]:
        current = current / part
        require_safe_directory(current, f"{label} parent directory")
    result = round_root / relative_path
    require_safe_regular(result, label)
    return result


def snapshot_opened_inputs(
    round_root: Path,
    opened: Iterable[str],
) -> dict[str, tuple[str, dict[str, int]]]:
    snapshots: dict[str, tuple[str, dict[str, int]]] = {}
    for relative in opened:
        path = require_safe_round_relative_file(
            round_root, relative, f"staged Stage-R input {relative}"
        )
        snapshots[relative] = regular_file_snapshot(
            path, f"staged Stage-R input {relative}"
        )
    return snapshots


def require_unchanged_opened_inputs(
    round_root: Path,
    expected: dict[str, tuple[str, dict[str, int]]],
) -> None:
    for relative, (expected_hash, expected_identity) in expected.items():
        path = require_safe_round_relative_file(
            round_root, relative, f"staged Stage-R input {relative}"
        )
        actual_hash, actual_identity = regular_file_snapshot(
            path, f"staged Stage-R input {relative}"
        )
        if actual_hash != expected_hash or actual_identity != expected_identity:
            raise ContractError(
                f"staged Stage-R input changed across verification: {relative}"
            )


def round_topology_snapshot(
    round_root: Path,
) -> dict[str, tuple[int, int, int, int, int, int, int]]:
    """Bind the complete current-round pathname topology without opening bytes.

    The staged Stage-P validator intentionally opens only its exact allowlist and
    therefore cannot notice an unrelated pathname inserted beside that packet.
    Stage O may enumerate names mechanically, however, so Stage-R binds every
    directory and regular-file identity before its first scoped gate and checks
    the same closed topology again immediately before returning ``VERIFIED``.
    No file content is opened here and no substantive sibling artifact is read.
    """

    require_safe_directory(round_root, "round root")
    snapshot: dict[str, tuple[int, int, int, int, int, int, int]] = {}
    pending: list[tuple[Path, str]] = [(round_root, ".")]
    while pending:
        directory, relative_directory = pending.pop()
        require_safe_directory(
            directory,
            "round root" if relative_directory == "." else (
                f"round topology directory {relative_directory}"
            ),
        )
        try:
            directory_before = directory.lstat()
            entries = sorted(
                list(os.scandir(directory)), key=lambda item: item.name.casefold()
            )
            directory_after = directory.lstat()
        except OSError as exc:
            raise ContractError(
                f"cannot enumerate round topology at {relative_directory}: {exc}"
            ) from exc
        directory_identity = (
            int(directory_before.st_dev),
            int(directory_before.st_ino),
            int(directory_before.st_mode),
            int(directory_before.st_nlink),
            int(directory_before.st_size),
            int(getattr(directory_before, "st_mtime_ns", 0)),
            int(getattr(directory_before, "st_file_attributes", 0)) & 0x400,
        )
        directory_after_identity = (
            int(directory_after.st_dev),
            int(directory_after.st_ino),
            int(directory_after.st_mode),
            int(directory_after.st_nlink),
            int(directory_after.st_size),
            int(getattr(directory_after, "st_mtime_ns", 0)),
            int(getattr(directory_after, "st_file_attributes", 0)) & 0x400,
        )
        if directory_identity != directory_after_identity:
            raise ContractError(
                f"round topology directory changed during enumeration: "
                f"{relative_directory}"
            )
        snapshot[relative_directory] = directory_identity
        for entry in entries:
            relative = (
                entry.name
                if relative_directory == "."
                else f"{relative_directory}/{entry.name}"
            )
            path = Path(entry.path)
            try:
                # On Windows ``DirEntry.stat`` may expose zero placeholders for
                # inode/link-count fields even though ``Path.lstat`` returns the
                # real file identity.  Use the pathname syscall consistently
                # with the rest of the Stage-R contract.
                metadata = path.lstat()
            except OSError as exc:
                raise ContractError(
                    f"cannot inspect round topology entry {relative}: {exc}"
                ) from exc
            attributes = int(getattr(metadata, "st_file_attributes", 0))
            if (
                stat.S_ISLNK(metadata.st_mode)
                or bool(attributes & 0x400)
                or is_link_or_reparse(path)
            ):
                raise ContractError(
                    f"round topology must not contain link/reparse entry: {relative}"
                )
            require_no_windows_named_streams(
                path, f"round topology entry {relative}"
            )
            identity = (
                int(metadata.st_dev),
                int(metadata.st_ino),
                int(metadata.st_mode),
                int(metadata.st_nlink),
                int(metadata.st_size),
                int(getattr(metadata, "st_mtime_ns", 0)),
                attributes & 0x400,
            )
            if stat.S_ISDIR(metadata.st_mode):
                pending.append((path, relative))
            elif stat.S_ISREG(metadata.st_mode):
                if int(metadata.st_nlink) != 1:
                    raise ContractError(
                        "round topology regular files must be single-link: "
                        f"{relative}"
                    )
                snapshot[relative] = identity
            else:
                raise ContractError(
                    "round topology contains a non-regular, non-directory entry: "
                    f"{relative}"
                )
    return snapshot


def require_unchanged_round_topology(
    round_root: Path,
    expected: dict[str, tuple[int, int, int, int, int, int, int]],
) -> None:
    observed = round_topology_snapshot(round_root)
    if observed != expected:
        added = sorted(set(observed) - set(expected))
        removed = sorted(set(expected) - set(observed))
        changed = sorted(
            path
            for path in set(expected) & set(observed)
            if expected[path] != observed[path]
        )
        raise ContractError(
            "closed Stage-P round topology changed during reviewer prompt "
            f"verification; added={added}, removed={removed}, changed={changed}"
        )


def require_terminal_stage_r_closure(
    *,
    round_root: Path,
    round_topology: dict[str, tuple[int, int, int, int, int, int, int]],
    opened_snapshots: dict[str, tuple[str, dict[str, int]]],
    helper_snapshots: dict[str, tuple[str, dict[str, int]]],
    process_path: Path,
    process_snapshot: tuple[str, dict[str, int]],
    python_executable: Path,
    python_snapshot: tuple[str, dict[str, int]],
    prompt_path: Path,
    prompt_snapshot: tuple[str, dict[str, int]],
    scratch_dir: Path,
    run_root: Path,
    stable: dict[str, Any],
    actor: str,
) -> None:
    """Linearize Stage-R authorization at one final closed snapshot.

    Earlier checks diagnose drift close to its source. This composite is the
    last filesystem-observing operation before VERIFIED is returned, so no
    individual late check can leave a different boundary class unobserved.
    """

    validate_actor_scratch(
        scratch_dir,
        round_root,
        stable,
        actor,
        run_root=run_root,
    )
    require_unchanged_opened_inputs(round_root, opened_snapshots)
    require_unchanged_helper_inputs(round_root, helper_snapshots)
    for path, expected, label in (
        (process_path, process_snapshot, "final process envelope"),
        (python_executable, python_snapshot, "bundled/workspace Python executable"),
        (prompt_path, prompt_snapshot, "planned reviewer prompt"),
    ):
        if regular_file_snapshot(path, label) != expected:
            raise ContractError(f"{label} changed during final Stage-R closure")
    # The complete topology snapshot also rechecks every opened/helper file's
    # link count, all directory boundaries, and the absence of extra entries.
    # Keep it last inside the composite so late hardlinks and late files cannot
    # survive an earlier per-file check.
    require_unchanged_round_topology(round_root, round_topology)


def require_unchanged_helper_inputs(
    round_root: Path,
    expected: dict[str, tuple[str, dict[str, int]]],
) -> None:
    for relative, (expected_hash, expected_identity) in expected.items():
        actual_hash, actual_identity = regular_file_snapshot(
            round_root / Path(relative), f"frozen Stage-H helper input {relative}"
        )
        if actual_hash != expected_hash or actual_identity != expected_identity:
            raise ContractError(
                f"frozen Stage-H helper input changed across verification: {relative}"
            )


def same_canonical_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.fspath(left)) == os.path.normcase(os.fspath(right))


def verify_real_process_seal(
    run_root: Path,
    expected_process_sha256: str,
    expected_seal_sha256: str,
) -> dict[str, Any]:
    manager = canonical_retry_manager()
    try:
        result = manager.verify_process_seal(
            types.SimpleNamespace(
                workspace=str(run_root.parent),
                run_root=str(run_root),
                expected_process_sha256=expected_process_sha256,
                expected_seal_sha256=expected_seal_sha256,
            )
        )
    except Exception as exc:
        raise ContractError(f"real process-seal verification failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ContractError("real process-seal verification returned no closed result")
    expected_projection = {
        "process_sha256": expected_process_sha256,
        "seal_sha256": expected_seal_sha256,
        "seal_file": "orchestration/process-seal.json",
    }
    for key, expected in expected_projection.items():
        if str(result.get(key, "")).upper() != expected.upper():
            raise ContractError(
                f"real process-seal result has unexpected {key}: {result.get(key)!r}"
            )
    metadata_hash = str(result.get("metadata_sha256", "")).upper()
    if HEX64_RE.fullmatch(metadata_hash) is None:
        raise ContractError("real process-seal result lacks a valid metadata SHA-256")
    return {
        "metadata_sha256": metadata_hash,
        **expected_projection,
    }


def verify_stage_p_gate(
    round_root: Path,
    python_executable: Path,
    scratch_dir: Path,
) -> dict[str, Any]:
    relative = Path("rules/scripts/validate_stage_p_output.py")
    canonical_path = Path(__file__).with_name(relative.name)
    staged_path = round_root / relative
    canonical_hash, _canonical_identity = regular_file_snapshot(
        canonical_path, "canonical Stage-P scoped validator"
    )
    staged_hash, _staged_identity = regular_file_snapshot(
        staged_path, "staged Stage-P scoped validator"
    )
    if staged_hash != canonical_hash:
        raise ContractError(
            "staged Stage-P scoped validator hash mismatch: "
            f"expected {canonical_hash}, got {staged_hash}"
        )
    argv = [str(python_executable), "-B", str(staged_path), str(round_root)]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            argv,
            cwd=str(scratch_dir),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContractError(f"cannot execute Stage-P scoped gate: {exc}") from exc
    first_nonempty = next(
        (line.strip() for line in completed.stdout.splitlines() if line.strip()), ""
    )
    if completed.returncode != 0 or first_nonempty != "PASS":
        detail = " | ".join(
            value.strip()
            for value in (completed.stdout, completed.stderr)
            if value.strip()
        )
        if len(detail) > 1200:
            detail = detail[:1200] + "..."
        raise ContractError(
            "Stage-P scoped gate must exit 0 with first nonempty stdout PASS; "
            f"exit={completed.returncode}, first={first_nonempty or '<empty>'}, "
            f"detail={detail or '<none>'}"
        )
    return {
        "status": "PASS",
        "argv": argv,
        "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "validator_sha256": staged_hash,
    }


def verify_prompt(
    run_root_value: Path,
    round_root_value: Path,
    prompt_value: Path,
    actor_value: str,
    expected_process_sha256: str,
    expected_seal_sha256: str,
    python_executable_value: Path,
    scratch_dir_value: Path,
    helper_inputs: Iterable[str] = (),
) -> dict[str, Any]:
    run_root = absolute_no_alias(run_root_value, "run root", must_exist=True)
    round_root = absolute_no_alias(round_root_value, "round root", must_exist=True)
    prompt_path = absolute_no_alias(
        prompt_value, "planned reviewer prompt", must_exist=True
    )
    require_safe_directory(run_root, "run root")
    require_safe_directory(round_root, "round root")
    if round_root.name != "round":
        raise ContractError("round root must be exactly the 'round' child of one run root")
    require_safe_regular(prompt_path, "planned reviewer prompt")
    prompt_snapshot_sha256, prompt_snapshot_identity = regular_file_snapshot(
        prompt_path, "planned reviewer prompt"
    )
    expected_round_root = absolute_no_alias(
        run_root / "round", "run-root round directory", must_exist=True
    )
    if not same_canonical_path(round_root, expected_round_root):
        raise ContractError("round root must be exactly <run-root>/round")
    if is_within_boundary(prompt_path, run_root):
        raise ContractError("planned reviewer prompt must remain outside the run root")
    expected_process_sha256 = expected_process_sha256.upper()
    if HEX64_RE.fullmatch(expected_process_sha256) is None:
        raise ContractError(
            "expected process SHA-256 must be the 64-hex Stage-O external anchor"
        )
    expected_seal_sha256 = expected_seal_sha256.upper()
    if HEX64_RE.fullmatch(expected_seal_sha256) is None:
        raise ContractError(
            "expected seal SHA-256 must be the 64-hex Stage-O external anchor"
        )
    python_executable, python_sha256 = validate_python_executable(
        python_executable_value
    )
    python_snapshot_sha256, python_snapshot_identity = regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    )
    if python_snapshot_sha256 != python_sha256:
        raise ContractError("Python executable changed after runtime binding")
    if is_within_boundary(python_executable, run_root):
        raise ContractError(
            "bundled/workspace Python executable must remain outside the run root"
        )

    first_seal_result = verify_real_process_seal(
        run_root, expected_process_sha256, expected_seal_sha256
    )

    process_path = round_root / "00-process-parameters.json"
    process_snapshot_sha256, process_snapshot_identity = regular_file_snapshot(
        process_path, "final process envelope"
    )
    try:
        process_bytes = process_path.read_bytes()
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read prompt verification input: {exc}") from exc
    process_sha256 = sha256_bytes(process_bytes)
    if process_sha256 != process_snapshot_sha256:
        raise ContractError("final process envelope changed during snapshot read")
    if process_sha256 != expected_process_sha256:
        raise ContractError(
            "final process bytes differ from the external Stage-O SHA-256 anchor"
        )
    if sha256_bytes(prompt_bytes) != prompt_snapshot_sha256:
        raise ContractError("planned reviewer prompt changed during snapshot read")
    if manifest_process_commitment(round_root) != process_sha256:
        raise ContractError(
            "Stage-P manifest process commitment differs from the final process bytes"
        )
    process = strict_json_bytes(process_bytes, "final process envelope")
    stable = stable_process_projection(process)
    actor = require_reviewer_actor(stable, actor_value)
    scratch_dir = validate_actor_scratch(
        scratch_dir_value,
        round_root,
        stable,
        actor,
        run_root=run_root,
    )
    if is_within_boundary(prompt_path, scratch_dir):
        raise ContractError(
            "planned reviewer prompt must remain outside the actor-private scratch directory"
        )

    validator = canonical_validator()
    process_errors: list[str] = []
    stage_v_present = isinstance(process.get("actor_prompt_sha256"), dict) and (
        "V" in process["actor_prompt_sha256"]
    )
    validated_process, _pdf, _hash, _pages, validated_count, _sizes = (
        validator.validate_process(
            round_root,
            process_errors,
            enforce_single_reviewer_pdf=True,
            validate_governing_file_bytes=True,
            validate_frozen_pdf_bytes=True,
            stage_v_present_override=stage_v_present,
            process_override=process,
        )
    )
    if process_errors:
        raise ContractError(
            "final process envelope fails the canonical process contract: "
            + "; ".join(process_errors)
        )
    if validated_process != process or validated_count != reviewer_count(stable):
        raise ContractError("canonical process projection changed during verification")

    helper_errors: list[str] = []
    validator.validate_helper_bundle(
        round_root,
        str(process["selected_pdf_sha256"]).upper(),
        process,
        validated_count,
        helper_errors,
    )
    if helper_errors:
        raise ContractError(
            "frozen Stage-H helper bundle fails the canonical provenance contract: "
            + "; ".join(helper_errors)
        )

    actual_opened = algorithmic_opened_inputs(
        process,
        actor,
        validator,
        helper_inputs=helper_inputs,
        round_root=round_root,
    )
    if not actual_opened:
        raise ContractError(f"canonical validator returned an empty allowlist for {actor}")
    opened_snapshots = snapshot_opened_inputs(round_root, actual_opened)
    helper_snapshots = snapshot_helper_inputs(round_root, actual_opened)
    round_topology = round_topology_snapshot(round_root)

    expected_commitments = canonical_validator_commitments(actual_opened, validator)
    prompt_commitments = parse_prompt_validator_commitments(prompt_bytes)
    if prompt_commitments != expected_commitments:
        raise ContractError(
            "reviewer prompt validator commitments differ from the canonical Stage-R set"
        )
    verify_staged_validator_commitments(round_root, expected_commitments)

    expected_prompt = render_prompt(
        round_root,
        actor,
        stable,
        actual_opened,
        expected_commitments,
        validator,
        python_executable,
        python_sha256,
        scratch_dir,
    )
    if prompt_bytes != expected_prompt:
        raise ContractError(
            "existing reviewer prompt bytes differ from the canonical Stage-R rendering"
        )
    prompt_sha256 = prompt_snapshot_sha256
    prompt_map = process.get("actor_prompt_sha256")
    process_prompt_sha256 = (
        str(prompt_map.get(actor, "")).upper()
        if isinstance(prompt_map, dict)
        else ""
    )
    if prompt_sha256 != process_prompt_sha256:
        raise ContractError(
            f"existing {actor} prompt SHA-256 {prompt_sha256} does not equal "
            f"process.actor_prompt_sha256[{actor}]={process_prompt_sha256 or '<missing>'}"
        )
    stage_p_gate = verify_stage_p_gate(
        round_root, python_executable, scratch_dir
    )
    post_helper_errors: list[str] = []
    validator.validate_helper_bundle(
        round_root,
        str(process["selected_pdf_sha256"]).upper(),
        process,
        validated_count,
        post_helper_errors,
    )
    if post_helper_errors:
        raise ContractError(
            "frozen Stage-H helper bundle changed or fails after the Stage-P gate: "
            + "; ".join(post_helper_errors)
        )
    post_opened = algorithmic_opened_inputs(
        process,
        actor,
        validator,
        helper_inputs=helper_inputs,
        round_root=round_root,
    )
    if post_opened != actual_opened:
        raise ContractError("Stage-R opened allowlist changed across Stage-P verification")
    require_unchanged_helper_inputs(round_root, helper_snapshots)
    require_unchanged_opened_inputs(round_root, opened_snapshots)
    process_sha256_after, process_identity_after = regular_file_snapshot(
        process_path, "final process envelope"
    )
    if (
        process_sha256_after != process_snapshot_sha256
        or process_identity_after != process_snapshot_identity
    ):
        raise ContractError("final process envelope changed during prompt verification")
    prompt_sha256_after, prompt_identity_after = regular_file_snapshot(
        prompt_path, "planned reviewer prompt"
    )
    if (
        prompt_sha256_after != prompt_snapshot_sha256
        or prompt_identity_after != prompt_snapshot_identity
    ):
        raise ContractError("reviewer prompt changed during prompt verification")
    python_sha256_after, python_identity_after = regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    )
    if (
        python_sha256_after != python_snapshot_sha256
        or python_identity_after != python_snapshot_identity
    ):
        raise ContractError("bundled/workspace Python executable changed during verification")
    validate_actor_scratch(
        scratch_dir,
        round_root,
        stable,
        actor,
        run_root=run_root,
    )
    if manifest_process_commitment(round_root) != process_sha256:
        raise ContractError("Stage-P manifest changed during prompt verification")
    final_seal_result = verify_real_process_seal(
        run_root, expected_process_sha256, expected_seal_sha256
    )
    if final_seal_result != first_seal_result:
        raise ContractError("process-seal result changed during prompt verification")
    terminal_stage_p_gate = verify_stage_p_gate(
        round_root, python_executable, scratch_dir
    )
    if terminal_stage_p_gate != stage_p_gate:
        raise ContractError("Stage-P scoped gate result changed during verification")
    require_unchanged_opened_inputs(round_root, opened_snapshots)
    require_unchanged_helper_inputs(round_root, helper_snapshots)
    terminal_process_sha256, terminal_process_identity = regular_file_snapshot(
        process_path, "final process envelope"
    )
    if (
        terminal_process_sha256 != process_snapshot_sha256
        or terminal_process_identity != process_snapshot_identity
    ):
        raise ContractError("final process envelope changed during terminal verification")
    terminal_python_sha256, terminal_python_identity = regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    )
    if (
        terminal_python_sha256 != python_sha256_after
        or terminal_python_identity != python_identity_after
    ):
        raise ContractError("Python executable changed during terminal verification")
    terminal_prompt_sha256, terminal_prompt_identity = regular_file_snapshot(
        prompt_path, "planned reviewer prompt"
    )
    if (
        terminal_prompt_sha256 != prompt_snapshot_sha256
        or terminal_prompt_identity != prompt_snapshot_identity
    ):
        raise ContractError("reviewer prompt changed during terminal verification")
    validate_actor_scratch(
        scratch_dir,
        round_root,
        stable,
        actor,
        run_root=run_root,
    )
    require_unchanged_round_topology(round_root, round_topology)
    require_unchanged_opened_inputs(round_root, opened_snapshots)
    require_unchanged_helper_inputs(round_root, helper_snapshots)
    post_scratch_process = regular_file_snapshot(
        process_path, "final process envelope"
    )
    if post_scratch_process != (
        process_snapshot_sha256,
        process_snapshot_identity,
    ):
        raise ContractError(
            "final process envelope changed after the terminal scratch check"
        )
    post_scratch_python = regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    )
    if post_scratch_python != (
        python_snapshot_sha256,
        python_snapshot_identity,
    ):
        raise ContractError(
            "Python executable changed after the terminal scratch check"
        )
    post_scratch_prompt = regular_file_snapshot(
        prompt_path, "planned reviewer prompt"
    )
    if post_scratch_prompt != (
        prompt_snapshot_sha256,
        prompt_snapshot_identity,
    ):
        raise ContractError(
            "reviewer prompt changed after the terminal scratch check"
        )
    result = {
        "schema": VERIFICATION_SCHEMA,
        "status": "VERIFIED",
        "actor": actor,
        "run_root": str(run_root),
        "round_root": str(round_root),
        "prompt_file": str(prompt_path),
        "prompt_sha256": prompt_sha256,
        "process_prompt_sha256": process_prompt_sha256,
        "process_sha256": process_sha256,
        "expected_process_sha256": expected_process_sha256,
        "expected_seal_sha256": expected_seal_sha256,
        "process_seal": final_seal_result,
        "stage_p_gate": stage_p_gate,
        "python_executable": str(python_executable),
        "python_executable_sha256": python_sha256,
        "scratch_dir": str(scratch_dir),
        "scratch_identity_convention": SCRATCH_SCHEMA,
        "opened": actual_opened,
        "owned_outputs": reviewer_owned_outputs(stable, actor),
        "validator_sha256": expected_commitments,
        "gate_commands": reviewer_gate_commands(
            python_executable, round_root, stable, actor
        ),
    }
    require_terminal_stage_r_closure(
        round_root=round_root,
        round_topology=round_topology,
        opened_snapshots=opened_snapshots,
        helper_snapshots=helper_snapshots,
        process_path=process_path,
        process_snapshot=(process_snapshot_sha256, process_snapshot_identity),
        python_executable=python_executable,
        python_snapshot=(python_snapshot_sha256, python_snapshot_identity),
        prompt_path=prompt_path,
        prompt_snapshot=(prompt_snapshot_sha256, prompt_snapshot_identity),
        scratch_dir=scratch_dir,
        run_root=run_root,
        stable=stable,
        actor=actor,
    )
    return result


def print_result(status: str, value: dict[str, Any] | None = None, error: str = "") -> int:
    print(status)
    if value is not None:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    if error:
        print(error)
    return 0 if status in {"PLANNED", "VERIFIED"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--process", type=Path, required=True)
    plan_parser.add_argument("--round-root", type=Path, required=True)
    plan_parser.add_argument("--actor", required=True)
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument("--python-executable", type=Path, required=True)
    plan_parser.add_argument("--scratch-dir", type=Path, required=True)
    plan_parser.add_argument(
        "--helper-input", action="append", default=[], dest="helper_inputs"
    )

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--run-root", type=Path, required=True)
    verify_parser.add_argument("--round-root", type=Path, required=True)
    verify_parser.add_argument("--prompt", type=Path, required=True)
    verify_parser.add_argument("--actor", required=True)
    verify_parser.add_argument("--expected-process-sha256", required=True)
    verify_parser.add_argument("--expected-seal-sha256", required=True)
    verify_parser.add_argument("--python-executable", type=Path, required=True)
    verify_parser.add_argument("--scratch-dir", type=Path, required=True)
    verify_parser.add_argument(
        "--helper-input", action="append", default=[], dest="helper_inputs"
    )

    args = parser.parse_args(argv)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if args.command == "plan":
            return print_result(
                "PLANNED",
                plan_prompt(
                    args.process,
                    args.round_root,
                    args.actor,
                    args.output,
                    args.python_executable,
                    args.scratch_dir,
                    helper_inputs=args.helper_inputs,
                ),
            )
        return print_result(
            "VERIFIED",
            verify_prompt(
                args.run_root,
                args.round_root,
                args.prompt,
                args.actor,
                args.expected_process_sha256,
                args.expected_seal_sha256,
                args.python_executable,
                args.scratch_dir,
                helper_inputs=args.helper_inputs,
            ),
        )
    except ContractError as exc:
        return print_result("FAIL", error=str(exc))
    except Exception as exc:  # pragma: no cover - fail-closed CLI boundary
        return print_result("FAIL", error=f"reviewer-prompt helper failed safely: {exc}")
    finally:
        sys.dont_write_bytecode = previous


if __name__ == "__main__":
    raise SystemExit(main())
