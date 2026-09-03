#!/usr/bin/env python3
"""Plan, verify, and promote one semantic-acceptance actor lifecycle.

The semantic-acceptance lifecycle has two deliberately different namespaces:

* an SA actor writes ``SA-<target>.md`` and ``SA-<target>.csv`` at the root of
  its closed private view; and
* Stage O copies the validated bytes into the finalized round's
  ``06-semantic-acceptance`` directory.

``plan`` runs before Stage P and depends only on stable process-envelope fields;
it never opens a downstream artifact or actor view.  ``verify`` runs after the
private view is staged and treats the validator frozen inside that view as the
sole rule implementation.  ``promote`` repeats verification, requires the
staged scoped validator to PASS, and copies only the two SA-owned outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import types
from pathlib import Path
from typing import Any, Iterable, NamedTuple


SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from actor_prompt_contract import render_bound_actor_contract  # noqa: E402


ACCEPTANCE_DIRECTORY = "06-semantic-acceptance"
TARGET_RE = re.compile(r"(?:R[1-5]|AI)\Z")
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
CONTROL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PROMPT_SCHEMA = "thesis-review-semantic-acceptance-prompt-v6"
VERIFICATION_SCHEMA = "thesis-review-semantic-acceptance-verification-v3"
PROMOTION_SCHEMA = "thesis-review-semantic-acceptance-promotion-v3"
INPUT_COMMITMENT_SCHEMA = "thesis-review-semantic-acceptance-inputs-v1"
PROCESS_COMMITMENT_RE = re.compile(
    r"(?m)^- Process-parameter file and SHA-256: "
    r"00-process-parameters\.json / ([0-9A-F]{64})$"
)
STAGED_VALIDATOR_RELATIVE = Path(
    "rules/scripts/validate_semantic_acceptance_output.py"
)
STAGED_SHARED_VALIDATOR_RELATIVE = Path("rules/scripts/validate_review_bundle.py")
VALIDATOR_COMMITMENT_RELATIVES = (
    STAGED_SHARED_VALIDATOR_RELATIVE,
    STAGED_VALIDATOR_RELATIVE,
)
VALIDATOR_COMMITMENT_RE = re.compile(
    r"(?m)^- (rules/scripts/(?:validate_review_bundle|"
    r"validate_semantic_acceptance_output)\.py) SHA-256: ([0-9A-F]{64})$"
)
PLAN_COMMON_RULE_INPUTS = [
    "00-process-parameters.json",
    "SKILL.md",
    "clean-room-orchestration.md",
    "china-policy.md",
    "grading-and-verdicts.md",
    "review-rubric.md",
    "reviewer-panels.md",
    "report-template.md",
    "ledger-validation.md",
    "rendered-pagination-audit.md",
    "citation-audit.md",
    "ai-style-audit.md",
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_semantic_acceptance_output.py",
]
PLAN_AI_RULE_INPUTS = [
    "00-process-parameters.json",
    "SKILL.md",
    "clean-room-orchestration.md",
    "report-template.md",
    "ledger-validation.md",
    "ai-style-audit.md",
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_semantic_acceptance_output.py",
]
PLAN_COMMON_PACKET_INPUTS = [
    "00-manifest.md",
    "01-policy-basis.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
]
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


class ContractError(RuntimeError):
    """Fail-closed error for prompt construction or Stage-O promotion."""


class FileIdentity(NamedTuple):
    device: int
    inode: int
    size: int
    mtime_ns: int
    sha256: str


class DirectoryIdentity(NamedTuple):
    device: int
    inode: int


def load_canonical_module(path: Path, module_name: str) -> types.ModuleType:
    """Source-load one checked-in Stage-O dependency without bytecode writes."""

    require_safe_regular(path, f"canonical Stage-O module {path.name}")
    try:
        source = path.read_bytes().decode("utf-8", errors="strict")
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = ""
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    except Exception as exc:
        raise ContractError(f"cannot load canonical Stage-O module {path}: {exc}") from exc
    return module


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _mtime_ns(stat_result: os.stat_result) -> int:
    return int(
        getattr(
            stat_result,
            "st_mtime_ns",
            int(stat_result.st_mtime * 1_000_000_000),
        )
    )


def _file_stat_signature(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(stat_result.st_dev),
        int(stat_result.st_ino),
        int(stat_result.st_size),
        _mtime_ns(stat_result),
    )


def file_identity_from_open_handle(
    handle: Any, label: str, *, require_single_link: bool = True
) -> FileIdentity:
    """Hash and identify the already-open file without following its pathname."""

    try:
        handle.flush()
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or (
            require_single_link and int(before.st_nlink) != 1
        ):
            raise ContractError(
                f"{label} must remain a single-link regular file while opened"
            )
        handle.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    except (OSError, ValueError) as exc:
        raise ContractError(f"cannot identify {label}: {exc}") from exc
    if _file_stat_signature(before) != _file_stat_signature(after):
        raise ContractError(f"{label} changed while its identity was captured")
    if not stat.S_ISREG(after.st_mode) or (
        require_single_link and int(after.st_nlink) != 1
    ):
        raise ContractError(
            f"{label} must remain a single-link regular file while opened"
        )
    return FileIdentity(
        device=int(after.st_dev),
        inode=int(after.st_ino),
        size=int(after.st_size),
        mtime_ns=_mtime_ns(after),
        sha256=digest.hexdigest().upper(),
    )


def capture_file_identity(path: Path, label: str) -> FileIdentity:
    """Capture one pathname's identity and prove the handle still names that path."""

    require_safe_regular(path, label)
    try:
        with path.open("rb") as handle:
            identity = file_identity_from_open_handle(handle, label)
            path_stat = path.lstat()
    except OSError as exc:
        raise ContractError(f"cannot identify {label}: {exc}") from exc
    if stat.S_ISLNK(path_stat.st_mode) or bool(
        getattr(path_stat, "st_file_attributes", 0) & 0x400
    ):
        raise ContractError(f"{label} became link/reparse-backed while inspected: {path}")
    if not stat.S_ISREG(path_stat.st_mode) or int(path_stat.st_nlink) != 1:
        raise ContractError(
            f"{label} became non-regular or multiply linked while inspected: {path}"
        )
    require_no_windows_named_streams(path, label)
    if _file_stat_signature(path_stat) != (
        identity.device,
        identity.inode,
        identity.size,
        identity.mtime_ns,
    ):
        raise ContractError(f"{label} pathname changed while its identity was captured")
    try:
        final_path_stat = path.lstat()
    except OSError as exc:
        raise ContractError(f"cannot recheck {label}: {path}: {exc}") from exc
    if stat.S_ISLNK(final_path_stat.st_mode) or bool(
        getattr(final_path_stat, "st_file_attributes", 0) & 0x400
    ):
        raise ContractError(f"{label} became link/reparse-backed while inspected: {path}")
    if (
        not stat.S_ISREG(final_path_stat.st_mode)
        or int(final_path_stat.st_nlink) != 1
    ):
        raise ContractError(
            f"{label} became non-regular or multiply linked while inspected: {path}"
        )
    if _file_stat_signature(final_path_stat) != (
        identity.device,
        identity.inode,
        identity.size,
        identity.mtime_ns,
    ):
        raise ContractError(f"{label} pathname changed while its identity was captured")
    return identity


def require_file_identity(
    path: Path, expected: FileIdentity, label: str
) -> None:
    current = capture_file_identity(path, label)
    if current != expected:
        raise ContractError(
            f"{label} was replaced or changed; preserving the current object: {path}"
        )


def directory_identity_from_open_descriptor(
    descriptor: int, label: str
) -> DirectoryIdentity:
    """Identify an already-open directory handle, not its mutable pathname."""

    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise ContractError(f"cannot identify opened {label}: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise ContractError(f"opened {label} is no longer a directory")
    return DirectoryIdentity(int(metadata.st_dev), int(metadata.st_ino))


def _windows_opened_object_delete(
    path: Path,
    expected: FileIdentity | DirectoryIdentity,
    label: str,
    *,
    is_directory: bool,
) -> bool:
    """Delete the exact authenticated object, never a later path replacement.

    A pathname-based ``check; unlink`` sequence can erase an unrelated object
    installed after the check. Windows by-handle disposition instead binds the
    deletion to the object opened and authenticated here.
    """

    if os.name != "nt":  # pragma: no cover - the supported local runner is Windows
        raise ContractError(
            f"safe by-handle rollback is unavailable; preserving {label}: {path}"
        )

    import ctypes
    import msvcrt
    from ctypes import wintypes

    delete_access = 0x00010000
    generic_read = 0x80000000
    file_read_attributes = 0x00000080
    share_all = 0x00000001 | 0x00000002 | 0x00000004
    open_existing = 3
    open_reparse_point = 0x00200000
    backup_semantics = 0x02000000
    file_disposition_info = 4

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOL)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    flags = open_reparse_point | (backup_semantics if is_directory else 0)
    access = delete_access | file_read_attributes
    if not is_directory:
        access |= generic_read
    raw_handle = kernel32.CreateFileW(
        str(path), access, share_all, None, open_existing, flags, None
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if raw_handle in (None, invalid_handle):
        error = ctypes.get_last_error()
        if error in {2, 3}:  # file/path not found
            return False
        raise ContractError(
            f"cannot open exact {label} for rollback {path}: Windows error {error}"
        )

    descriptor: int | None = None
    try:
        descriptor = msvcrt.open_osfhandle(
            int(raw_handle), os.O_RDONLY | (0 if is_directory else os.O_BINARY)
        )
        raw_handle = None  # the CRT descriptor now owns the native handle
        if is_directory:
            current: FileIdentity | DirectoryIdentity = (
                directory_identity_from_open_descriptor(descriptor, label)
            )
        else:
            with os.fdopen(descriptor, "rb", closefd=False) as opened:
                current = file_identity_from_open_handle(
                    opened, label, require_single_link=False
                )
        if current != expected:
            raise ContractError(
                f"{label} was replaced or changed; preserving the current object: {path}"
            )
        disposition = FileDispositionInfo(True)
        native_handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
        if not kernel32.SetFileInformationByHandle(
            native_handle,
            file_disposition_info,
            ctypes.byref(disposition),
            ctypes.sizeof(disposition),
        ):
            error = ctypes.get_last_error()
            raise ContractError(
                f"cannot remove exact unchanged {label} {path}: Windows error {error}"
            )
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        elif raw_handle not in (None, invalid_handle):
            kernel32.CloseHandle(raw_handle)
    return True


def unlink_created_file_if_unchanged(
    path: Path, expected: FileIdentity, label: str
) -> bool:
    """Delete only the exact object created by this invocation."""

    if not os.path.lexists(path):
        return False
    return _windows_opened_object_delete(
        path, expected, label, is_directory=False
    )


def exclusive_create_bytes(path: Path, value: bytes, label: str) -> FileIdentity:
    """Create bytes exclusively and retain an identity suitable for safe rollback."""

    require_safe_directory(path.parent, f"{label} parent")
    if os.path.lexists(path) or is_link_or_reparse(path):
        raise ContractError(f"refusing to overwrite existing {label}: {path}")

    handle: Any | None = None
    identity: FileIdentity | None = None
    try:
        handle = path.open("x+b")
        written = handle.write(value)
        if written != len(value):
            raise OSError(
                f"short write: expected {len(value)} bytes, wrote {written}"
            )
        handle.flush()
        os.fsync(handle.fileno())
        identity = file_identity_from_open_handle(handle, label)
    except FileExistsError as exc:
        raise ContractError(f"refusing to overwrite existing {label}: {path}") from exc
    except Exception as exc:
        if handle is not None and identity is None:
            try:
                identity = file_identity_from_open_handle(handle, label)
            except ContractError:
                identity = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
            handle = None
        if identity is None:
            raise ContractError(
                f"failed to create {label} and could not prove ownership for cleanup; "
                f"preserving the path {path}: {exc}"
            ) from exc
        try:
            unlink_created_file_if_unchanged(path, identity, label)
        except ContractError as cleanup_exc:
            raise ContractError(
                f"failed to create {label}: {exc}; cleanup failed closed and preserved "
                f"the current object: {cleanup_exc}"
            ) from exc
        raise ContractError(f"failed to create {label}: {exc}") from exc
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    if identity is None:  # pragma: no cover - defensive type narrowing
        raise ContractError(f"failed to capture identity for created {label}: {path}")
    if identity.sha256 != sha256_bytes(value):
        try:
            unlink_created_file_if_unchanged(path, identity, label)
        except ContractError as cleanup_exc:
            raise ContractError(
                f"created {label} hash mismatch; cleanup failed closed and preserved "
                f"the current object: {cleanup_exc}"
            ) from cleanup_exc
        raise ContractError(f"created {label} hash mismatch: {path}")
    require_file_identity(path, identity, label)
    return identity


def capture_directory_identity(path: Path, label: str) -> DirectoryIdentity:
    require_safe_directory(path, label)
    try:
        stat_result = path.stat()
    except OSError as exc:
        raise ContractError(f"cannot identify {label}: {exc}") from exc
    if is_link_or_reparse(path):
        raise ContractError(f"{label} became link/reparse-backed while inspected: {path}")
    return DirectoryIdentity(int(stat_result.st_dev), int(stat_result.st_ino))


def require_directory_identity(
    path: Path, expected: DirectoryIdentity, label: str
) -> None:
    current = capture_directory_identity(path, label)
    if current != expected:
        raise ContractError(
            f"{label} was replaced; preserving the current directory: {path}"
        )


def rmdir_created_directory_if_unchanged(
    path: Path, expected: DirectoryIdentity, label: str
) -> bool:
    if not os.path.lexists(path):
        return False
    return _windows_opened_object_delete(
        path, expected, label, is_directory=True
    )


def is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return False


def require_no_windows_named_streams(path: Path, label: str) -> None:
    """Reject NTFS named streams that directory enumeration cannot disclose."""

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
        if error == 38:  # ERROR_HANDLE_EOF: no streams on this filesystem object.
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


def resolved(path: Path, *, must_exist: bool) -> Path:
    """Return one canonical absolute control path without erasing aliases."""

    value = Path(path)
    if not value.is_absolute():
        raise ContractError(f"path must be absolute: {value}")
    if os.name == "nt" and os.fspath(value).startswith("\\\\"):
        raise ContractError(
            f"SA control path must not use a UNC/device namespace: {value}"
        )
    if os.name == "nt" and any(":" in part for part in value.parts[1:]):
        raise ContractError(
            f"SA control path must not use an NTFS alternate data stream: {value}"
        )
    if any(part == ".." for part in value.parts):
        raise ContractError(f"path must not contain lexical parent traversal: {value}")
    if any(character in os.fspath(value) for character in ('"', "\r", "\n")):
        raise ContractError(f"path contains a command-unsafe character: {value}")
    normalized = Path(os.path.abspath(os.fspath(value)))
    current = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ContractError(f"cannot inspect path component {current}: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            raise ContractError(f"path traverses a symlink/reparse component: {current}")
    if must_exist and not os.path.lexists(normalized):
        raise ContractError(f"required path is missing: {normalized}")
    probe = normalized if os.path.lexists(normalized) else normalized.parent
    if not os.path.lexists(probe):
        raise ContractError(f"path parent must already exist: {normalized.parent}")
    try:
        canonical_probe = probe.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"cannot canonicalize path {probe}: {exc}") from exc
    if os.path.normcase(os.fspath(probe)) != os.path.normcase(
        os.fspath(canonical_probe)
    ):
        raise ContractError(
            "path must use its canonical filesystem spelling; aliases such as "
            f"NTFS 8.3 short names are forbidden: {value}"
        )
    return normalized


def validate_bound_python_executable(value: Path) -> tuple[Path, FileIdentity]:
    """Bind SA planning and verification to the builder's actual interpreter."""

    if not sys.executable:
        raise ContractError("the running builder has no sys.executable to bind")
    requested = resolved(value, must_exist=True)
    running = resolved(Path(sys.executable), must_exist=True)
    require_safe_regular(requested, "bound Python executable")
    require_safe_regular(running, "running Python executable")
    if os.path.normcase(str(requested)) != os.path.normcase(str(running)):
        raise ContractError(
            "--python-executable must be the exact canonical sys.executable "
            f"running this builder: expected {running}, got {requested}"
        )
    requested_identity = capture_file_identity(requested, "bound Python executable")
    running_identity = capture_file_identity(running, "running Python executable")
    if requested_identity != running_identity:
        raise ContractError(
            "--python-executable does not have the same file identity as "
            "the interpreter running this builder"
        )
    return requested, requested_identity


def file_identity_record(identity: FileIdentity) -> dict[str, int | str]:
    return {
        "device": identity.device,
        "inode": identity.inode,
        "size": identity.size,
        "mtime_ns": identity.mtime_ns,
        "sha256": identity.sha256,
    }


def capture_opened_input_commitment(
    view_root: Path, opened: Iterable[str]
) -> dict[str, Any]:
    """Bind every frozen SA input pathname, identity, and byte hash."""

    records: list[dict[str, Any]] = []
    for relative in opened:
        identity = capture_file_identity(
            view_root / Path(relative), f"private-view input {relative}"
        )
        records.append(
            {
                "relative_path": relative,
                **file_identity_record(identity),
            }
        )
    payload = {
        "schema": INPUT_COMMITMENT_SCHEMA,
        "view_root": str(view_root),
        "inputs": records,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {**payload, "sha256": sha256_bytes(encoded)}


def require_opened_input_commitment(
    view_root: Path,
    opened: Iterable[str],
    expected_sha256: str,
) -> dict[str, Any]:
    expected = expected_sha256.upper()
    if HEX64_RE.fullmatch(expected) is None:
        raise ContractError(
            "expected SA input commitment must be one 64-hex prelaunch anchor"
        )
    current = capture_opened_input_commitment(view_root, opened)
    if current["sha256"] != expected:
        raise ContractError(
            "private SA view inputs differ from the externally retained "
            f"prelaunch commitment: expected {expected}, got {current['sha256']}"
        )
    return current


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def require_same_windows_drive(first: Path, second: Path, label: str) -> None:
    """Exclude alternate drive-letter namespaces from a separation proof."""

    if os.name != "nt":
        return
    first_drive = os.path.normcase(first.drive)
    second_drive = os.path.normcase(second.drive)
    if not first_drive or not second_drive or first_drive != second_drive:
        raise ContractError(
            f"{label} must use one canonical local drive-letter namespace"
        )


def require_safe_directory(path: Path, label: str) -> None:
    if is_link_or_reparse(path) or not path.is_dir():
        raise ContractError(f"{label} is missing, not a directory, or link/reparse-backed: {path}")
    require_no_windows_named_streams(path, label)


def require_safe_regular(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ContractError(f"cannot inspect {label}: {path}: {exc}") from exc
    if (
        is_link_or_reparse(path)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise ContractError(
            f"{label} must be a non-aliased single-link regular file: {path}"
        )
    require_no_windows_named_streams(path, label)


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    require_safe_regular(path, label)

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractError(f"cannot parse {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label} must contain one JSON object")
    return value


def safe_relative_name(value: Any, label: str, *, basename_only: bool) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"stable process field {label} must be a nonempty trimmed string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ContractError(f"stable process field {label} must be a safe relative path")
    if basename_only and len(path.parts) != 1:
        raise ContractError(f"stable process field {label} must be a basename")
    return path.as_posix()


def require_control_id(value: Any, label: str) -> str:
    """Accept one closed, prompt-safe round/retry identifier."""

    if not isinstance(value, str) or CONTROL_ID_RE.fullmatch(value) is None:
        raise ContractError(
            f"stable process field {label} must match "
            "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
        )
    return value


def stable_process_projection(process: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in STABLE_PROCESS_FIELDS if field not in process]
    if missing:
        raise ContractError(f"preplan process is missing stable field(s): {missing}")
    round_id = require_control_id(process.get("round_id"), "round_id")
    retry_id = require_control_id(process.get("retry_id"), "retry_id")
    output_language = process.get("output_language")
    if output_language != "zh-CN":
        raise ContractError("stable process field output_language must be exactly zh-CN")
    pdf_name = safe_relative_name(
        process.get("frozen_pdf_file"), "frozen_pdf_file", basename_only=True
    )
    pdf_hash = process.get("selected_pdf_sha256")
    if not isinstance(pdf_hash, str) or HEX64_RE.fullmatch(pdf_hash) is None:
        raise ContractError("stable process field selected_pdf_sha256 must be 64 hexadecimal characters")
    page_count = process.get("physical_page_count")
    if (
        not isinstance(page_count, int)
        or isinstance(page_count, bool)
        or page_count < 1
    ):
        raise ContractError("stable process field physical_page_count must be a positive integer")
    degree = process.get("degree_level")
    if degree not in {"masters", "doctorate"}:
        raise ContractError("stable process field degree_level must be masters or doctorate")
    governing_value = process.get("governing_local_files")
    if not isinstance(governing_value, list):
        raise ContractError("stable process field governing_local_files must be a list")
    governing_files: list[str] = []
    for index, item in enumerate(governing_value):
        if not isinstance(item, dict):
            raise ContractError(
                f"governing_local_files[{index}] must be an object with neutral_file"
            )
        governing_files.append(
            safe_relative_name(
                item.get("neutral_file"),
                f"governing_local_files[{index}].neutral_file",
                basename_only=True,
            )
        )
    if len(governing_files) != len(set(governing_files)):
        raise ContractError("stable governing neutral_file names must be duplicate-free")
    return {
        "round_id": round_id,
        "retry_id": retry_id,
        "frozen_pdf_file": pdf_name,
        "selected_pdf_sha256": pdf_hash.upper(),
        "physical_page_count": page_count,
        "degree_level": degree,
        "governing_local_files": governing_files,
        "output_language": output_language,
    }


def algorithmic_required_targets(process: dict[str, Any]) -> list[str]:
    count = 5 if process["degree_level"] == "doctorate" else 3
    return [*(f"R{index}" for index in range(1, count + 1)), "AI"]


def require_algorithmic_target(process: dict[str, Any], target: str) -> None:
    if TARGET_RE.fullmatch(target) is None:
        raise ContractError(f"invalid semantic-acceptance target {target!r}")
    if target not in algorithmic_required_targets(process):
        raise ContractError(
            f"target {target} is not required for degree_level={process['degree_level']!r}"
        )


def algorithmic_actor_report_name(target: str) -> str:
    return "05-ai-style-assessment.md" if target == "AI" else f"{target}-comprehensive-review.md"


def algorithmic_target_artifacts(
    process: dict[str, Any], target: str
) -> list[str]:
    degree = process["degree_level"]
    page_owner = (degree == "doctorate" and target == "R5") or (
        degree == "masters" and target == "R3"
    )
    citation_owner = (degree == "doctorate" and target == "R4") or (
        degree == "masters" and target == "R3"
    )
    result = [algorithmic_actor_report_name(target)]
    if page_owner:
        result.extend(
            [
                "02-page-layout-ledger.md",
                "02-page-layout-ledger.csv",
                "03-bibliography-audit-ledger.md",
                "03-bibliography-audit-ledger.csv",
            ]
        )
        result.extend(
            f"page-renders/P{page:04d}.png"
            for page in range(1, int(process["physical_page_count"]) + 1)
        )
    if citation_owner:
        result.extend(
            [
                "04-citation-claim-audit-ledger.md",
                "04-citation-claim-audit-ledger.csv",
            ]
        )
    return result


def algorithmic_opened_inputs(
    process: dict[str, Any], target: str
) -> list[str]:
    require_algorithmic_target(process, target)
    if target == "AI":
        opened = [
            *PLAN_AI_RULE_INPUTS,
            process["frozen_pdf_file"],
            "00-manifest.md",
            "00-page-inventory.csv",
            algorithmic_actor_report_name(target),
        ]
    else:
        opened = [
            *PLAN_COMMON_RULE_INPUTS,
            *process["governing_local_files"],
            process["frozen_pdf_file"],
            *PLAN_COMMON_PACKET_INPUTS,
            *algorithmic_target_artifacts(process, target),
        ]
    if len(opened) != len(set(opened)):
        raise ContractError("algorithmic SA opened allowlist contains duplicate names")
    return opened


def require_safe_staged_path(root: Path, path: Path, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"{label} escapes the private SA view") from exc
    current = root
    if is_link_or_reparse(current):
        raise ContractError(f"private SA view is link/reparse-backed: {root}")
    for part in relative.parts:
        current = current / part
        if is_link_or_reparse(current):
            raise ContractError(f"{label} contains a link/reparse component: {current}")
    require_safe_regular(path, label)


def load_staged_validator(
    view_root: Path,
    authenticated_sources: dict[str, bytes],
) -> tuple[Any, Any]:
    """Compile only already-authenticated source bytes; never consult pyc caches."""

    validator_path = view_root / STAGED_VALIDATOR_RELATIVE
    shared_path = view_root / STAGED_SHARED_VALIDATOR_RELATIVE
    require_safe_staged_path(view_root, validator_path, "staged SA validator")
    require_safe_staged_path(view_root, shared_path, "staged shared validator")

    def source_only_module(
        path: Path, relative: Path, module_name: str
    ) -> Any:
        source = authenticated_sources.get(relative.as_posix())
        if source is None:
            raise ContractError(
                f"missing authenticated source bytes for {relative.as_posix()}"
            )
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = ""
        try:
            code = compile(source, str(path), "exec", dont_inherit=True)
            exec(code, module.__dict__)
        except Exception as exc:
            raise ContractError(
                f"cannot source-load authenticated validator {relative.as_posix()}: {exc}"
            ) from exc
        return module

    try:
        shared = source_only_module(
            shared_path,
            STAGED_SHARED_VALIDATOR_RELATIVE,
            "thesis_review_staged_shared_"
            + sha256_bytes(authenticated_sources[STAGED_SHARED_VALIDATOR_RELATIVE.as_posix()])[:16],
        )
        validator = source_only_module(
            validator_path,
            STAGED_VALIDATOR_RELATIVE,
            "thesis_review_staged_semantic_acceptance_"
            + sha256_bytes(authenticated_sources[STAGED_VALIDATOR_RELATIVE.as_posix()])[:16],
        )
        validator.load_shared_validator = lambda: shared
    except Exception as exc:
        raise ContractError(f"cannot load frozen validator pair from private view: {exc}") from exc
    return validator, shared


def canonical_validator_commitments() -> dict[str, str]:
    """Hash the canonical validator pair beside this Stage-O helper at plan time."""

    script_root = Path(__file__).resolve().parent
    result: dict[str, str] = {}
    for relative in VALIDATOR_COMMITMENT_RELATIVES:
        canonical = script_root / relative.name
        require_safe_regular(canonical, f"canonical validator {relative.as_posix()}")
        result[relative.as_posix()] = sha256_file(canonical)
    return result


def parse_prompt_validator_commitments(prompt: bytes) -> dict[str, str]:
    """Read the exact validator commitments already bound by the prompt hash."""

    try:
        text = prompt.decode("utf-8", errors="strict").replace("\r\n", "\n")
    except UnicodeError as exc:
        raise ContractError(f"planned SA prompt is not strict UTF-8: {exc}") from exc
    matches = VALIDATOR_COMMITMENT_RE.findall(text)
    expected_names = [path.as_posix() for path in VALIDATOR_COMMITMENT_RELATIVES]
    if [name for name, _digest in matches] != expected_names:
        raise ContractError(
            "planned SA prompt lacks the exact ordered canonical validator "
            "SHA-256 commitments"
        )
    return {name: digest for name, digest in matches}


def verify_staged_validator_commitments(
    view_root: Path, commitments: dict[str, str]
) -> dict[str, bytes]:
    """Authenticate staged code before importing or executing either validator."""

    authenticated: dict[str, bytes] = {}
    for relative in VALIDATOR_COMMITMENT_RELATIVES:
        name = relative.as_posix()
        staged = view_root / relative
        require_safe_staged_path(view_root, staged, f"staged validator {name}")
        try:
            source = staged.read_bytes()
        except OSError as exc:
            raise ContractError(f"cannot read staged validator {name}: {exc}") from exc
        if sha256_bytes(source) != commitments.get(name):
            raise ContractError(
                f"staged validator SHA-256 does not match the frozen prompt "
                f"commitment: {name}"
            )
        authenticated[name] = source
    return authenticated


def load_final_process(
    root: Path, validator: Any, shared: Any
) -> dict[str, Any]:
    process_path = root / "00-process-parameters.json"
    require_safe_regular(process_path, "process envelope")
    errors: list[str] = []
    process = validator.read_json(process_path, errors)
    if process is None:
        raise ContractError("; ".join(errors) or "cannot parse process envelope")
    validator.validate_semantic_process_shape(process, errors)
    if errors:
        raise ContractError("; ".join(errors))
    return process


def verify_manifest_process_commitment(view_root: Path) -> str:
    """Bind the final process bytes to Stage P's separately frozen manifest."""

    process_path = view_root / "00-process-parameters.json"
    manifest_path = view_root / "00-manifest.md"
    require_safe_regular(process_path, "process envelope")
    require_safe_regular(manifest_path, "Stage-P manifest")
    try:
        manifest_text = manifest_path.read_text(
            encoding="utf-8", errors="strict"
        ).replace("\r\n", "\n")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read Stage-P process commitment: {exc}") from exc
    commitments = PROCESS_COMMITMENT_RE.findall(manifest_text)
    actual = sha256_file(process_path)
    if commitments != [actual]:
        raise ContractError(
            "Stage-P manifest does not contain exactly one current full-process "
            "SHA-256 commitment"
        )
    return actual


def private_output_paths(view_root: Path, target: str) -> tuple[Path, Path]:
    return (
        view_root / f"SA-{target}.md",
        view_root / f"SA-{target}.csv",
    )


def round_output_paths(round_root: Path, target: str) -> tuple[Path, Path]:
    directory = round_root / ACCEPTANCE_DIRECTORY
    return (
        directory / f"SA-{target}.md",
        directory / f"SA-{target}.csv",
    )


def enumerate_regular_tree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()

    def walk(directory: Path) -> None:
        for entry in directory.iterdir():
            if is_link_or_reparse(entry):
                raise ContractError(f"private SA view contains link/reparse entry: {entry}")
            relative = entry.relative_to(root).as_posix()
            if entry.is_dir():
                require_safe_directory(entry, "private SA view directory")
                directories.add(relative)
                walk(entry)
            elif entry.is_file():
                require_safe_regular(entry, "private SA view file")
                files.add(relative)
            else:
                raise ContractError(f"private SA view contains non-regular entry: {entry}")

    walk(root)
    return files, directories


def expected_parent_directories(relative_files: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for value in relative_files:
        parent = Path(value).parent
        while parent != Path("."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def validate_closed_view(
    view_root: Path,
    target: str,
    opened: list[str],
    *,
    require_sa_outputs: bool,
) -> str:
    require_safe_directory(view_root, "private SA view")
    private_md, private_csv = private_output_paths(view_root, target)
    reserved = view_root / ACCEPTANCE_DIRECTORY
    if reserved.exists() or is_link_or_reparse(reserved):
        raise ContractError(
            f"private SA view must not contain reserved round-only directory: {reserved}"
        )
    expected_files = {Path(value).as_posix() for value in opened}
    output_presence = []
    for output in (private_md, private_csv):
        if output.exists() or is_link_or_reparse(output):
            require_safe_regular(output, "private SA actor output")
            output_presence.append(True)
            expected_files.add(output.name)
        else:
            output_presence.append(False)
    if output_presence[0] != output_presence[1]:
        raise ContractError("private SA view contains only one member of the SA output pair")
    output_state = "complete" if all(output_presence) else "absent"
    if require_sa_outputs and output_state != "complete":
        raise ContractError("private SA output pair is required before promotion")
    expected_dirs = expected_parent_directories(expected_files)
    actual_files, actual_dirs = enumerate_regular_tree(view_root)
    if actual_files != expected_files or actual_dirs != expected_dirs:
        raise ContractError(
            "private SA prelaunch view topology mismatch; "
            f"missing_files={sorted(expected_files-actual_files)}, "
            f"extra_files={sorted(actual_files-expected_files)}, "
            f"missing_dirs={sorted(expected_dirs-actual_dirs)}, "
            f"extra_dirs={sorted(actual_dirs-expected_dirs)}"
        )
    for relative in opened:
        staged = view_root / Path(relative)
        require_safe_regular(staged, f"staged SA input {relative}")
    return output_state


def require_terminal_sa_verify_closure(
    *,
    view_root: Path,
    target: str,
    opened: list[str],
    require_sa_outputs: bool,
    expected_output_state: str,
    expected_input_commitment_sha256: str,
    python_executable: Path,
    python_identity: FileIdentity,
    prompt_path: Path,
    prompt_identity: FileIdentity,
) -> dict[str, Any]:
    """Take the final joint private-view snapshot before returning VERIFIED."""

    observed_state = validate_closed_view(
        view_root,
        target,
        opened,
        require_sa_outputs=require_sa_outputs,
    )
    if observed_state != expected_output_state:
        raise ContractError(
            "private SA view output state changed during final verification closure"
        )
    observed_commitment = capture_opened_input_commitment(view_root, opened)
    if observed_commitment["sha256"] != expected_input_commitment_sha256.upper():
        raise ContractError(
            "private SA view inputs changed during final verification closure"
        )
    require_file_identity(
        python_executable, python_identity, "bound Python executable"
    )
    require_file_identity(prompt_path, prompt_identity, "planned SA prompt")
    # Re-enumerate the complete closed view after the external executable and
    # prompt checks; this catches late extra entries, links, and pair changes.
    observed_state = validate_closed_view(
        view_root,
        target,
        opened,
        require_sa_outputs=require_sa_outputs,
    )
    if observed_state != expected_output_state:
        raise ContractError(
            "private SA view output state changed during final verification closure"
        )
    observed_commitment = capture_opened_input_commitment(view_root, opened)
    if observed_commitment["sha256"] != expected_input_commitment_sha256.upper():
        raise ContractError(
            "private SA view inputs changed during final verification closure"
        )
    return observed_commitment


def render_prompt(
    view_root: Path,
    target: str,
    process: dict[str, Any],
    opened: list[str],
    validator_commitments: dict[str, str],
    python_executable: Path,
    python_identity: FileIdentity,
) -> bytes:
    private_md, private_csv = private_output_paths(view_root, target)
    validator_path = view_root / "rules" / "scripts" / "validate_semantic_acceptance_output.py"
    opened_lines = "\n".join(
        f"{index}. {view_root / Path(relative)}"
        for index, relative in enumerate(opened, start=1)
    )
    validator_lines = "\n".join(
        f"- {relative.as_posix()} SHA-256: "
        f"{validator_commitments[relative.as_posix()]}"
        for relative in VALIDATOR_COMMITMENT_RELATIVES
    )
    validator_argv = [
        str(python_executable),
        "-B",
        str(validator_path),
        str(view_root),
        target,
    ]
    validator_argv_json = json.dumps(
        validator_argv, ensure_ascii=False, separators=(",", ":")
    )
    environment_json = json.dumps(
        {"PYTHONDONTWRITEBYTECODE": "1"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    bound_contract = render_bound_actor_contract(f"SA-{target}")
    text = f"""Semantic-acceptance operational prompt

Prompt schema: {PROMPT_SCHEMA}
Actor ID: SA-{target}
Target actor ID: {target}
Review round ID: {process['round_id']}
Review retry ID: {process['retry_id']}
Frozen PDF file: {view_root / str(process['frozen_pdf_file'])}
Frozen PDF SHA-256: {str(process['selected_pdf_sha256']).upper()}
Frozen physical page count: {process['physical_page_count']}
Degree level: {process['degree_level']}
Output language: {process['output_language']}
Bound Python executable: {python_executable}
Bound Python SHA-256: {python_identity.sha256}

Frozen validator commitments (authenticate before importing either file):
{validator_lines}

{bound_contract}

Follow the staged thesis-review skill and its governing references. Perform only independent semantic acceptance of the frozen {target} target. Do not create, modify, merge, grade, reject, or adjudicate thesis findings. Do not enumerate neighboring paths, contact another actor, or open any local file not listed below. No follow-up message will be sent after dispatch.

Acceptance standard:
Judge reasonable support and admissibility, not concurrence. A target conclusion remains admissible when concrete permitted evidence supports it and its inference and requested action are proportionate, even if you would assign a different severity, weight, emphasis, or final recommendation. Such a reasonable scholarly disagreement is not by itself a failure. Fail a unit only when it lacks reasonable permitted-evidence support, exceeds that evidence, omits decisive counter-evidence, is internally inconsistent, or cannot be checked within the closed authority. Never rewrite an honest semantic judgment merely to obtain PASS.

Large-row SemanticBasis discipline:
Build the complete CSV in canonical target-unit order. You may construct it incrementally within the two authorized outputs, but a partial batch is invalid and the scoped validator is run only after every required row is present. Before drafting each row, re-check that exact target unit and its permitted evidence, then form a unit-specific fact capsule: the actual proposition or visible content, the exact page/source/record/status or concrete access limitation, relevant counter-evidence or boundary where applicable, and the independent reason for this disposition. Write the capsule only into the two authorized outputs; do not create a notes or batch file.

Required canonical JSON keys, marker values, and exact target bindings must remain exact and may repeat. Actor-authored evidence, search, comparison, and reasoning text must instead follow the facts of the individual unit. For a citation pair, state the occurrence-specific proposition in substantive prose, the source-stated claim and locator (or the exact source-specific access/content limitation), its support boundary or counter-evidence, and why that target disposition is reasonably supportable. For a page, state distinctive visible content and the actual numbering, float attachment, clipping, blank-page, or neighbor-page relationship checked. For a bibliography field, preserve the mandatory rendered/authority/verdict cues, then give the record-and-field-specific comparison and consequence; do not reuse one field-level stock sentence across references. For actor-authored report and AI units other than closed-projection verdict rows, name the concrete PDF evidence, counter-evidence, and search resolution appropriate to that unit. A verdict row uses only its required closed canonical projection and adds no narrative prose.

Never copy a narrative sentence frame and substitute only an ID, page, URL, title, quoted text, hash, number, or rotating synonym/token bank, including across batch boundaries. The validator normalizes those identity slots and examines the complete CSV: in a large file, any 12-row identity-stripped, repeated-shingle, singleton-stripped, or fuzzy near-duplicate cluster fails. This is a semantic safeguard, not a word-variation exercise. Do not pad rows with unique tokens. If the scoped validator identifies a mechanical schema or diversity error attributable to your own SA pair, re-check the named rows against their actual evidence, correct only your two outputs, preserve every honest pass/fail judgment, and rerun. If the error is attributable to a frozen input, stop without editing it.

Private SA view root:
{view_root}

Open exactly these local files, in this order:
{opened_lines}

Public-endpoint rule:
Use no public endpoint and do not browse. The receipt must be exactly public_endpoints=[none]. URLs recorded inside the frozen target artifacts are inert target text, not SA endpoint authority; do not open them or represent them as endpoints accessed by SA. The frozen validator enforcing this rule is {validator_path}.

Write exactly these two actor-owned outputs at the private view root:
- {private_md}
- {private_csv}

Do not create or write {view_root / ACCEPTANCE_DIRECTORY}. That directory name is reserved for Stage O in the finalized round and is not an actor output path. Do not write an SA-* file anywhere else.

Run the scoped validator without a shell or PATH lookup. Use exactly this JSON argument vector:
{validator_argv_json}
Use exactly this environment override:
{environment_json}
The bound executable is the same canonical file identity as the Python interpreter that planned and verified this prompt. The `-B` argument and `PYTHONDONTWRITEBYTECODE=1` override are mandatory. Before freezing, execute exactly that argument vector with that environment override; do not substitute `python`, `py`, a WindowsApps alias, another executable, or a changed runtime.

The scoped command has two admissible completed outcomes. `PASS` with exit 0 means the pair is mechanically valid and every target unit is semantically admissible; freeze the private pair for Stage-O promotion. `VALID-FAIL` with exit 3 means the pair is mechanically valid but contains at least one honest semantic failure; freeze and preserve that private pair for Stage O to hash-verify and quarantine the entire retry, and do not revise it to seek PASS. Any other output/exit combination is a mechanical or staged-input failure: repair and rerun only when the diagnostic is attributable to your own two SA outputs; otherwise stop. Never modify a frozen target artifact or other input. A `VALID-FAIL` pair must never be promoted or used to materialize the semantic-acceptance gate. Leave no __pycache__ directory or .pyc file.
"""
    return text.replace("\r\n", "\n").encode("utf-8")


def exclusive_write(path: Path, value: bytes) -> FileIdentity:
    return exclusive_create_bytes(path, value, "prompt output")


def validate_sa_view_root(
    view_root_value: Path,
    target: str,
    *,
    must_exist: bool,
) -> tuple[Path, Path]:
    """Bind an SA actor to exactly ``<run>/views/SA-<target>``.

    The ``views`` parent and inferred run already exist in both phases.  The
    actor directory itself must be wholly absent during planning and a safe
    directory during verification.  ``lexists`` deliberately catches broken
    links as well as files, directories, symlinks, and reparse points.
    """

    if TARGET_RE.fullmatch(target) is None:
        raise ContractError(f"invalid semantic-acceptance target {target!r}")
    raw = Path(view_root_value)
    if not raw.is_absolute():
        raise ContractError(f"private SA view path must be absolute: {raw}")
    if not must_exist and os.path.lexists(raw):
        raise ContractError(
            "private SA view must be completely absent during prompt planning"
        )
    view_root = resolved(raw, must_exist=must_exist)
    views_root = resolved(view_root.parent, must_exist=True)
    require_safe_directory(views_root, "SA views parent")
    if views_root.name != "views":
        raise ContractError("private SA view direct parent must be named exactly 'views'")
    run_root = resolved(views_root.parent, must_exist=True)
    require_safe_directory(run_root, "SA run root")
    expected = views_root / f"SA-{target}"
    if (
        os.path.normcase(os.path.normpath(str(view_root)))
        != os.path.normcase(os.path.normpath(str(expected)))
        or view_root.parent != views_root
        or view_root.name != f"SA-{target}"
    ):
        raise ContractError(
            "private SA view must be exactly the SA-target direct child of "
            f"<run>/views: expected {expected}"
        )
    if must_exist:
        require_safe_directory(view_root, "private SA view")
    elif os.path.lexists(view_root) or is_link_or_reparse(view_root):
        raise ContractError(
            "private SA view must be completely absent during prompt planning"
        )
    return view_root, run_root


def plan_prompt(
    process_path_value: Path,
    view_root_value: Path,
    target: str,
    output_value: Path,
    python_executable_value: Path,
) -> dict[str, Any]:
    process_path = resolved(process_path_value, must_exist=True)
    output = resolved(output_value, must_exist=False)
    process = stable_process_projection(
        read_json_object(process_path, "preplan process envelope")
    )
    require_algorithmic_target(process, target)
    view_root, run_root = validate_sa_view_root(
        view_root_value, target, must_exist=False
    )
    require_same_windows_drive(
        view_root, output, "private SA view and planned prompt output"
    )
    if is_within(output, view_root):
        raise ContractError("planned prompt output must live outside the private SA view")
    python_executable, python_identity = validate_bound_python_executable(
        python_executable_value
    )
    opened = algorithmic_opened_inputs(process, target)
    validator_commitments = canonical_validator_commitments()
    prompt = render_prompt(
        view_root,
        target,
        process,
        opened,
        validator_commitments,
        python_executable,
        python_identity,
    )
    digest = sha256_bytes(prompt)
    prompt_identity = exclusive_write(output, prompt)
    try:
        require_file_identity(
            python_executable, python_identity, "bound Python executable"
        )
        require_file_identity(output, prompt_identity, "prompt output")
    except ContractError:
        unlink_created_file_if_unchanged(output, prompt_identity, "prompt output")
        raise
    return {
        "schema": PROMPT_SCHEMA,
        "target": target,
        "run_root": str(run_root),
        "view_root": str(view_root),
        "prompt_file": str(output),
        "prompt_sha256": digest,
        "python_executable": str(python_executable),
        "python_executable_identity": file_identity_record(python_identity),
        "stable_process_fields": process,
        "private_outputs": [
            str(path) for path in private_output_paths(view_root, target)
        ],
        "opened": opened,
        "public_endpoint_policy": "none",
        "validator_sha256": validator_commitments,
    }


def verify_prompt(
    view_root_value: Path,
    prompt_value: Path,
    target: str,
    expected_process_sha256: str,
    python_executable_value: Path,
    *,
    require_sa_outputs: bool = False,
    expected_input_commitment_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    view_root, run_root = validate_sa_view_root(
        view_root_value, target, must_exist=True
    )
    prompt_path = resolved(prompt_value, must_exist=True)
    require_safe_directory(view_root, "private SA view")
    require_safe_regular(prompt_path, "planned SA prompt")
    require_same_windows_drive(
        view_root, prompt_path, "private SA view and planned prompt"
    )
    prompt_identity = capture_file_identity(prompt_path, "planned SA prompt")
    if is_within(prompt_path, view_root):
        raise ContractError("planned prompt must remain outside the private SA view")
    python_executable, python_identity = validate_bound_python_executable(
        python_executable_value
    )
    expected_process_sha256 = expected_process_sha256.upper()
    if not HEX64_RE.fullmatch(expected_process_sha256):
        raise ContractError(
            "expected process SHA-256 must be the 64-hex Stage-O external anchor"
        )

    actual_prompt = prompt_path.read_bytes()
    require_file_identity(prompt_path, prompt_identity, "planned SA prompt")
    prompt_digest = sha256_bytes(actual_prompt)
    if prompt_digest != prompt_identity.sha256:
        raise ContractError("planned SA prompt changed while its bytes were read")
    preimport_process = read_json_object(
        view_root / "00-process-parameters.json",
        "pre-import process envelope",
    )
    preimport_stable_process = stable_process_projection(preimport_process)
    require_algorithmic_target(preimport_stable_process, target)
    preimport_prompt_map = preimport_process.get("actor_prompt_sha256")
    preimport_process_hash = (
        str(preimport_prompt_map.get(f"SA-{target}", "")).upper()
        if isinstance(preimport_prompt_map, dict)
        else ""
    )
    if prompt_digest != preimport_process_hash:
        raise ContractError(
            f"existing SA-{target} prompt SHA-256 {prompt_digest} does not equal "
            "the pre-import process commitment"
        )
    preimport_process_sha256 = verify_manifest_process_commitment(view_root)
    if preimport_process_sha256 != expected_process_sha256:
        raise ContractError(
            "private-view process/manifest pair differs from the external Stage-O "
            "process SHA-256 anchor"
        )
    preimport_opened = algorithmic_opened_inputs(preimport_stable_process, target)
    output_state = validate_closed_view(
        view_root,
        target,
        preimport_opened,
        require_sa_outputs=require_sa_outputs,
    )
    if expected_input_commitment_sha256 is None and output_state != "absent":
        raise ContractError(
            "initial SA verification must run before dispatch while the actor "
            "output pair is absent; refusing a post-dispatch input baseline"
        )
    initial_input_commitment = capture_opened_input_commitment(
        view_root, preimport_opened
    )
    if expected_input_commitment_sha256 is not None:
        expected_input_commitment_sha256 = (
            expected_input_commitment_sha256.upper()
        )
        if HEX64_RE.fullmatch(expected_input_commitment_sha256) is None:
            raise ContractError(
                "expected SA input commitment must be one 64-hex prelaunch anchor"
            )
        if (
            initial_input_commitment["sha256"]
            != expected_input_commitment_sha256
        ):
            raise ContractError(
                "private SA view inputs differ from the externally retained "
                "prelaunch commitment: expected "
                f"{expected_input_commitment_sha256}, got "
                f"{initial_input_commitment['sha256']}"
            )
    validator_commitments = parse_prompt_validator_commitments(actual_prompt)
    authenticated_sources = verify_staged_validator_commitments(
        view_root, validator_commitments
    )
    validator, shared = load_staged_validator(view_root, authenticated_sources)
    process = load_final_process(view_root, validator, shared)
    if process != preimport_process:
        raise ContractError(
            "process envelope changed between pre-import authentication and "
            "staged-validator parsing"
        )
    process_sha256 = verify_manifest_process_commitment(view_root)
    if process_sha256 != preimport_process_sha256:
        raise ContractError(
            "process envelope changed while the staged validator was loaded"
        )
    if process_sha256 != expected_process_sha256:
        raise ContractError(
            "process envelope differs from the external Stage-O process SHA-256 anchor"
        )
    stable_process = stable_process_projection(process)
    algorithmic_targets = algorithmic_required_targets(stable_process)
    staged_targets = validator.required_targets(process)
    if staged_targets != algorithmic_targets:
        raise ContractError(
            "staged validator target routing differs from the stable planning algorithm"
        )
    require_algorithmic_target(stable_process, target)

    dynamic_errors: list[str] = []
    dynamic_opened = validator.canonical_sa_opened_inputs(
        view_root, process, target, dynamic_errors
    )
    if dynamic_errors:
        raise ContractError(
            "staged validator could not derive the canonical SA opened allowlist: "
            + "; ".join(dynamic_errors)
        )
    planned_opened = algorithmic_opened_inputs(stable_process, target)
    if dynamic_opened != planned_opened:
        raise ContractError(
            "preplanned and staged-validator SA opened allowlists differ; "
            f"planned={planned_opened}, staged={dynamic_opened}"
        )
    endpoint_errors: list[str] = []
    dynamic_endpoints = sorted(
        validator.target_public_endpoints(
            view_root, process, target, shared, endpoint_errors
        )
    )
    if endpoint_errors:
        raise ContractError(
            "staged validator could not derive target-scoped public endpoints: "
            + "; ".join(endpoint_errors)
        )
    if dynamic_endpoints:
        raise ContractError(
            "staged validator violates the closed SA no-network contract: "
            f"derived public endpoints {dynamic_endpoints}"
        )
    expected_prompt = render_prompt(
        view_root,
        target,
        stable_process,
        planned_opened,
        validator_commitments,
        python_executable,
        python_identity,
    )
    if actual_prompt != expected_prompt:
        raise ContractError(
            "existing SA prompt bytes differ from the stable preplan rendering"
        )
    digest = prompt_digest
    prompt_map = process.get("actor_prompt_sha256")
    process_hash = (
        str(prompt_map.get(f"SA-{target}", "")).upper()
        if isinstance(prompt_map, dict)
        else ""
    )
    if digest != process_hash:
        raise ContractError(
            f"existing SA-{target} prompt SHA-256 {digest} does not equal "
            f"process.actor_prompt_sha256[SA-{target}]={process_hash or '<missing>'}"
        )
    require_file_identity(
        python_executable, python_identity, "bound Python executable"
    )
    final_input_commitment = capture_opened_input_commitment(
        view_root, dynamic_opened
    )
    if final_input_commitment != initial_input_commitment:
        raise ContractError(
            "private SA view inputs changed during prompt verification"
        )
    terminal_output_state = validate_closed_view(
        view_root,
        target,
        dynamic_opened,
        require_sa_outputs=require_sa_outputs,
    )
    if terminal_output_state != output_state:
        raise ContractError(
            "private SA view output state changed during prompt verification"
        )
    terminal_input_commitment = capture_opened_input_commitment(
        view_root, dynamic_opened
    )
    if terminal_input_commitment != initial_input_commitment:
        raise ContractError(
            "private SA view inputs changed during terminal prompt verification"
        )
    require_file_identity(
        python_executable, python_identity, "bound Python executable"
    )
    require_file_identity(prompt_path, prompt_identity, "planned SA prompt")
    metadata = {
        "schema": VERIFICATION_SCHEMA,
        "target": target,
        "status": "VERIFIED",
        "run_root": str(run_root),
        "view_root": str(view_root),
        "prompt_file": str(prompt_path),
        "prompt_sha256": digest,
        "process_prompt_sha256": process_hash,
        "process_sha256": process_sha256,
        "expected_process_sha256": expected_process_sha256,
        "python_executable": str(python_executable),
        "python_executable_identity": file_identity_record(python_identity),
        "opened": dynamic_opened,
        "public_endpoints_derived_at_verify": dynamic_endpoints,
        "validator_sha256": validator_commitments,
        "sa_output_state": output_state,
        "input_commitment": terminal_input_commitment,
    }
    context = {
        "validator": validator,
        "shared": shared,
        "process": process,
        "opened": dynamic_opened,
        "run_root": run_root,
        "view_root": view_root,
        "prompt_path": prompt_path,
        "prompt_identity": prompt_identity,
        "python_executable": python_executable,
        "python_identity": python_identity,
        "input_commitment": terminal_input_commitment,
    }
    terminal_input_commitment = require_terminal_sa_verify_closure(
        view_root=view_root,
        target=target,
        opened=dynamic_opened,
        require_sa_outputs=require_sa_outputs,
        expected_output_state=output_state,
        expected_input_commitment_sha256=initial_input_commitment["sha256"],
        python_executable=python_executable,
        python_identity=python_identity,
        prompt_path=prompt_path,
        prompt_identity=prompt_identity,
    )
    metadata["input_commitment"] = terminal_input_commitment
    context["input_commitment"] = terminal_input_commitment
    return metadata, context


def ensure_disjoint_roots(view_root: Path, round_root: Path) -> None:
    require_same_windows_drive(
        view_root, round_root, "private SA view and finalized round root"
    )
    try:
        if os.path.samefile(view_root, round_root):
            raise ContractError(
                "private SA view and finalized round root identify the same directory"
            )
    except OSError as exc:
        raise ContractError(
            f"cannot prove private SA view/finalized round separation: {exc}"
        ) from exc
    if view_root == round_root or is_within(view_root, round_root) or is_within(round_root, view_root):
        raise ContractError("private SA view and finalized round root must be disjoint")


def compare_view_and_round_inputs(
    view_root: Path,
    round_root: Path,
    process: dict[str, Any],
    target: str,
    validator: Any,
    shared: Any,
) -> dict[str, tuple[FileIdentity, FileIdentity]]:
    errors: list[str] = []
    opened = validator.canonical_sa_opened_inputs(
        view_root, process, target, errors
    )
    if errors:
        raise ContractError("; ".join(errors))
    snapshots: dict[str, tuple[FileIdentity, FileIdentity]] = {}
    for relative in opened:
        view_path = view_root / Path(relative)
        round_path = round_root / Path(relative)
        view_identity = capture_file_identity(
            view_path, f"private-view input {relative}"
        )
        round_identity = capture_file_identity(
            round_path, f"round input {relative}"
        )
        if view_identity.sha256 != round_identity.sha256:
            raise ContractError(f"private-view/round input byte mismatch: {relative}")
        snapshots[relative] = (view_identity, round_identity)
    return snapshots


def require_unchanged_view_and_round_inputs(
    view_root: Path,
    round_root: Path,
    snapshots: dict[str, tuple[FileIdentity, FileIdentity]],
) -> None:
    for relative, (view_identity, round_identity) in snapshots.items():
        require_file_identity(
            view_root / Path(relative),
            view_identity,
            f"private-view input {relative}",
        )
        require_file_identity(
            round_root / Path(relative),
            round_identity,
            f"round input {relative}",
        )


def validate_existing_acceptance_directory(
    directory: Path,
    process: dict[str, Any],
    validator: Any,
) -> None:
    if not directory.exists():
        return
    require_safe_directory(directory, "round semantic-acceptance directory")
    allowed = {
        f"SA-{target}.{suffix}"
        for target in validator.required_targets(process)
        for suffix in ("md", "csv")
    }
    for entry in directory.iterdir():
        try:
            require_safe_regular(entry, "existing acceptance entry")
        except ContractError:
            raise ContractError(f"unsafe/non-file existing acceptance entry: {entry}")
        if entry.name not in allowed:
            raise ContractError(f"unexpected existing acceptance entry: {entry}")


def capture_acceptance_directory_entries(directory: Path) -> dict[str, FileIdentity]:
    return {
        entry.name: capture_file_identity(entry, "existing acceptance entry")
        for entry in sorted(directory.iterdir(), key=lambda path: path.name)
    }


def require_acceptance_directory_state(
    directory: Path,
    directory_identity: DirectoryIdentity,
    expected_entries: dict[str, FileIdentity],
) -> None:
    require_directory_identity(
        directory, directory_identity, "round semantic-acceptance directory"
    )
    actual_names = {entry.name for entry in directory.iterdir()}
    if actual_names != set(expected_entries):
        raise ContractError(
            "round semantic-acceptance directory changed concurrently; "
            f"missing={sorted(set(expected_entries) - actual_names)}, "
            f"extra={sorted(actual_names - set(expected_entries))}"
        )
    for name, identity in expected_entries.items():
        require_file_identity(
            directory / name, identity, "round semantic-acceptance entry"
        )
    require_directory_identity(
        directory, directory_identity, "round semantic-acceptance directory"
    )


def require_round_promotion_state(round_root: Path, validator: Any) -> None:
    require_safe_directory(round_root, "finalized round root")
    leaked = sorted(
        entry.name
        for entry in round_root.iterdir()
        if validator.ROUND_ROOT_ACTOR_OUTPUT_RE.fullmatch(entry.name)
    )
    if leaked:
        raise ContractError(f"round root contains leaked SA actor outputs: {leaked}")
    gate = round_root / validator.GATE_FILE
    if gate.exists() or is_link_or_reparse(gate):
        raise ContractError(
            f"refusing promotion while semantic-acceptance gate already exists: {gate}"
        )


def require_terminal_sa_promotion_closure(
    *,
    view_root: Path,
    round_root: Path,
    target: str,
    opened: list[str],
    expected_input_commitment_sha256: str,
    input_snapshots: dict[str, tuple[FileIdentity, FileIdentity]],
    sources: tuple[Path, Path],
    source_identities: tuple[FileIdentity, FileIdentity],
    destinations: tuple[Path, Path],
    destination_identities: tuple[FileIdentity, ...],
    acceptance_dir: Path,
    acceptance_directory_identity: DirectoryIdentity,
    acceptance_entries: dict[str, FileIdentity],
    validator: Any,
    python_executable: Path,
    python_identity: FileIdentity,
    prompt_path: Path,
    prompt_identity: FileIdentity,
) -> None:
    """Jointly close every namespace used to authorize PROMOTED."""

    if len(destination_identities) != 2:
        raise ContractError("terminal SA promotion closure lacks the output pair")
    if (
        validate_closed_view(
            view_root,
            target,
            opened,
            require_sa_outputs=True,
        )
        != "complete"
    ):
        raise ContractError("private SA output pair changed during promotion closure")
    for source, identity in zip(sources, source_identities):
        require_file_identity(source, identity, "private SA output")
    for destination, identity in zip(destinations, destination_identities):
        require_file_identity(destination, identity, "frozen SA output")
    require_acceptance_directory_state(
        acceptance_dir,
        acceptance_directory_identity,
        acceptance_entries,
    )
    require_round_promotion_state(round_root, validator)
    require_unchanged_view_and_round_inputs(
        view_root, round_root, input_snapshots
    )
    require_opened_input_commitment(
        view_root, opened, expected_input_commitment_sha256
    )
    require_file_identity(
        python_executable, python_identity, "bound Python executable"
    )
    require_file_identity(prompt_path, prompt_identity, "planned SA prompt")
    # End with both complete namespaces, not with one narrow file check.
    require_acceptance_directory_state(
        acceptance_dir,
        acceptance_directory_identity,
        acceptance_entries,
    )
    if (
        validate_closed_view(
            view_root,
            target,
            opened,
            require_sa_outputs=True,
        )
        != "complete"
    ):
        raise ContractError("private SA output pair changed during promotion closure")


def copy_pair_exclusively(
    sources: tuple[Path, Path],
    destinations: tuple[Path, Path],
    expected_sources: tuple[FileIdentity, FileIdentity] | None = None,
) -> tuple[list[dict[str, str]], tuple[FileIdentity, FileIdentity]]:
    if expected_sources is None:
        expected_sources = tuple(
            capture_file_identity(source, "private SA output") for source in sources
        )
    if len(expected_sources) != len(sources):
        raise ContractError("expected SA source identity count does not match output pair")
    payloads: list[tuple[Path, Path, bytes, FileIdentity]] = []
    for source, destination, expected in zip(sources, destinations, expected_sources):
        require_file_identity(source, expected, "private SA output")
        if destination.exists() or is_link_or_reparse(destination):
            raise ContractError(f"refusing to overwrite frozen SA output: {destination}")
        value = source.read_bytes()
        require_file_identity(source, expected, "private SA output")
        if sha256_bytes(value) != expected.sha256:
            raise ContractError(f"private SA output changed while reading: {source}")
        payloads.append((source, destination, value, expected))

    created: list[tuple[Path, FileIdentity]] = []
    try:
        for source, destination, value, expected in payloads:
            identity = exclusive_create_bytes(
                destination, value, "frozen SA output"
            )
            created.append((destination, identity))
            require_file_identity(source, expected, "private SA output")
            require_file_identity(destination, identity, "frozen SA output")
            if identity.sha256 != expected.sha256:
                raise ContractError(f"promoted SA output hash mismatch: {destination}")
        for (source, destination, _value, expected), (
            created_destination,
            created_identity,
        ) in zip(payloads, created):
            if destination != created_destination:
                raise ContractError("internal SA destination identity ordering mismatch")
            require_file_identity(source, expected, "private SA output")
            require_file_identity(
                destination, created_identity, "frozen SA output"
            )
    except Exception as exc:
        cleanup_errors: list[str] = []
        for destination, identity in reversed(created):
            try:
                unlink_created_file_if_unchanged(
                    destination, identity, "frozen SA output"
                )
            except ContractError as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        if cleanup_errors:
            raise ContractError(
                f"SA pair promotion failed: {exc}; rollback failed closed and preserved "
                "one or more current objects: " + "; ".join(cleanup_errors)
            ) from exc
        raise

    return (
        [
            {
                "source": str(source),
                "destination": str(destination),
                "sha256": expected.sha256,
            }
            for source, destination, _value, expected in payloads
        ],
        tuple(identity for _destination, identity in created),
    )


def promote(
    view_root_value: Path,
    round_root_value: Path,
    prompt_value: Path,
    target: str,
    expected_process_sha256: str,
    expected_input_commitment_sha256: str,
    launch_record_value: Path,
    expected_launch_id: str,
    expected_process_seal_sha256: str,
    expected_launch_record_sha256: str,
    expected_output_commitment_sha256: str,
    python_executable_value: Path,
) -> dict[str, Any]:
    verification, context = verify_prompt(
        view_root_value,
        prompt_value,
        target,
        expected_process_sha256,
        python_executable_value,
        require_sa_outputs=True,
        expected_input_commitment_sha256=expected_input_commitment_sha256,
    )
    view_root = context["view_root"]
    round_root = resolved(round_root_value, must_exist=True)
    require_safe_directory(view_root, "private SA view")
    require_safe_directory(round_root, "finalized round root")
    ensure_disjoint_roots(view_root, round_root)

    validator = context["validator"]
    shared = context["shared"]
    process = context["process"]
    round_process = load_final_process(round_root, validator, shared)
    if process != round_process or sha256_file(
        view_root / "00-process-parameters.json"
    ) != sha256_file(round_root / "00-process-parameters.json"):
        raise ContractError("private-view and finalized-round process envelopes differ")

    launch_receipt = validate_sa_launch_for_promotion(
        view_root=view_root,
        round_root=round_root,
        process=process,
        target=target,
        input_commitment_sha256=expected_input_commitment_sha256,
        launch_record_path=launch_record_value,
        expected_launch_id=expected_launch_id,
        expected_process_seal_sha256=expected_process_seal_sha256,
        expected_launch_record_sha256=expected_launch_record_sha256,
        expected_output_commitment_sha256=expected_output_commitment_sha256,
    )

    sources = private_output_paths(view_root, target)
    validated_source_identities = tuple(
        capture_file_identity(source, "private SA output") for source in sources
    )
    scoped_errors, scoped_result = validator.validate_actor(
        view_root,
        target,
        shared,
        enforce_closed_view=True,
    )
    if scoped_errors or scoped_result is None or scoped_result.get("status") != "PASS":
        details = "; ".join(scoped_errors) or "semantic acceptance status is not PASS"
        raise ContractError(f"scoped semantic-acceptance validation failed: {details}")

    input_snapshots = compare_view_and_round_inputs(
        view_root, round_root, process, target, validator, shared
    )
    require_opened_input_commitment(
        view_root, context["opened"], expected_input_commitment_sha256
    )
    require_file_identity(
        context["python_executable"],
        context["python_identity"],
        "bound Python executable",
    )
    require_file_identity(
        context["prompt_path"], context["prompt_identity"], "planned SA prompt"
    )
    require_round_promotion_state(round_root, validator)

    acceptance_dir = round_root / ACCEPTANCE_DIRECTORY
    validate_existing_acceptance_directory(acceptance_dir, process, validator)
    created_directory: DirectoryIdentity | None = None
    if not acceptance_dir.exists():
        try:
            acceptance_dir.mkdir()
        except FileExistsError as exc:
            raise ContractError(
                "semantic-acceptance directory appeared concurrently; refusing promotion"
            ) from exc
        created_directory = capture_directory_identity(
            acceptance_dir, "round semantic-acceptance directory"
        )
    require_safe_directory(acceptance_dir, "round semantic-acceptance directory")
    acceptance_directory_identity = capture_directory_identity(
        acceptance_dir, "round semantic-acceptance directory"
    )
    existing_entry_identities = capture_acceptance_directory_entries(
        acceptance_dir
    )
    destinations = round_output_paths(round_root, target)
    destination_identities: list[FileIdentity] = []
    try:
        if (
            validate_closed_view(
                view_root,
                target,
                context["opened"],
                require_sa_outputs=True,
            )
            != "complete"
        ):
            raise ContractError("private SA output pair is no longer complete")
        require_acceptance_directory_state(
            acceptance_dir,
            acceptance_directory_identity,
            existing_entry_identities,
        )
        require_unchanged_view_and_round_inputs(
            view_root, round_root, input_snapshots
        )
        require_opened_input_commitment(
            view_root, context["opened"], expected_input_commitment_sha256
        )
        require_file_identity(
            context["python_executable"],
            context["python_identity"],
            "bound Python executable",
        )
        require_file_identity(
            context["prompt_path"],
            context["prompt_identity"],
            "planned SA prompt",
        )
        copied, copied_identities = copy_pair_exclusively(
            sources,
            destinations,
            validated_source_identities,
        )
        destination_identities.extend(copied_identities)
        require_unchanged_view_and_round_inputs(
            view_root, round_root, input_snapshots
        )
        require_opened_input_commitment(
            view_root, context["opened"], expected_input_commitment_sha256
        )
        require_file_identity(
            context["python_executable"],
            context["python_identity"],
            "bound Python executable",
        )
        require_file_identity(
            context["prompt_path"],
            context["prompt_identity"],
            "planned SA prompt",
        )
        if (
            validate_closed_view(
                view_root,
                target,
                context["opened"],
                require_sa_outputs=True,
            )
            != "complete"
        ):
            raise ContractError("private SA output pair is no longer complete")
        for source, identity in zip(sources, validated_source_identities):
            require_file_identity(source, identity, "private SA output")
        for destination, identity in zip(destinations, destination_identities):
            require_file_identity(destination, identity, "frozen SA output")
        expected_acceptance_entries = dict(existing_entry_identities)
        expected_acceptance_entries.update(
            {
                destination.name: identity
                for destination, identity in zip(
                    destinations, destination_identities
                )
            }
        )
        require_acceptance_directory_state(
            acceptance_dir,
            acceptance_directory_identity,
            expected_acceptance_entries,
        )
        require_round_promotion_state(round_root, validator)
        require_unchanged_view_and_round_inputs(
            view_root, round_root, input_snapshots
        )
        require_opened_input_commitment(
            view_root, context["opened"], expected_input_commitment_sha256
        )
        require_file_identity(
            context["python_executable"],
            context["python_identity"],
            "bound Python executable",
        )
        require_file_identity(
            context["prompt_path"],
            context["prompt_identity"],
            "planned SA prompt",
        )
        promotion_result = {
            "schema": PROMOTION_SCHEMA,
            "target": target,
            "status": "PROMOTED",
            "verification": verification,
            "expected_input_commitment_sha256": (
                expected_input_commitment_sha256.upper()
            ),
            "launch_id": launch_receipt["launch_id"],
            "launch_record_sha256": launch_receipt[
                "launch_record_sha256"
            ],
            "output_commitment_sha256": launch_receipt[
                "output_commitment_sha256"
            ],
            "files": copied,
        }
        require_terminal_sa_promotion_closure(
            view_root=view_root,
            round_root=round_root,
            target=target,
            opened=context["opened"],
            expected_input_commitment_sha256=expected_input_commitment_sha256,
            input_snapshots=input_snapshots,
            sources=sources,
            source_identities=validated_source_identities,
            destinations=destinations,
            destination_identities=tuple(destination_identities),
            acceptance_dir=acceptance_dir,
            acceptance_directory_identity=acceptance_directory_identity,
            acceptance_entries=expected_acceptance_entries,
            validator=validator,
            python_executable=context["python_executable"],
            python_identity=context["python_identity"],
            prompt_path=context["prompt_path"],
            prompt_identity=context["prompt_identity"],
        )
    except Exception as exc:
        cleanup_errors: list[str] = []
        for destination, identity in reversed(
            list(zip(destinations, destination_identities))
        ):
            try:
                unlink_created_file_if_unchanged(
                    destination, identity, "frozen SA output"
                )
            except ContractError as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        if created_directory is not None:
            try:
                rmdir_created_directory_if_unchanged(
                    acceptance_dir,
                    created_directory,
                    "round semantic-acceptance directory",
                )
            except ContractError as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        if cleanup_errors:
            raise ContractError(
                f"promotion failed: {exc}; rollback failed closed and preserved "
                "one or more current objects: " + "; ".join(cleanup_errors)
            ) from exc
        raise
    return promotion_result


def validate_sa_launch_for_promotion(
    *,
    view_root: Path,
    round_root: Path,
    process: dict[str, Any],
    target: str,
    input_commitment_sha256: str,
    launch_record_path: Path,
    expected_launch_id: str,
    expected_process_seal_sha256: str,
    expected_launch_record_sha256: str,
    expected_output_commitment_sha256: str,
) -> dict[str, Any]:
    """Consume the same externally anchored v3 receipt as every other actor."""

    manager = load_canonical_module(
        Path(__file__).resolve().parent / "manage_stage_o_workspace.py",
        "thesis_review_sa_stage_o_receipt",
    )
    try:
        return manager.validate_launch_for_promotion(
            actor=f"SA-{target}",
            view_root=view_root,
            round_root=round_root,
            process=process,
            input_commitment_sha256=input_commitment_sha256,
            launch_record_path=launch_record_path,
            expected_launch_id=expected_launch_id,
            expected_process_seal_sha256=expected_process_seal_sha256,
            expected_launch_record_sha256=expected_launch_record_sha256,
            expected_output_commitment_sha256=expected_output_commitment_sha256,
        )
    except Exception as exc:
        raise ContractError(
            f"SA-{target} launch/transport receipt failed before promotion: {exc}"
        ) from exc


def print_result(status: str, value: dict[str, Any] | None = None, error: str = "") -> int:
    print(status)
    if value is not None:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    if error:
        print(error)
    return 0 if status in {"PLANNED", "VERIFIED", "PROMOTED"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--process", type=Path, required=True)
    plan_parser.add_argument("--view-root", type=Path, required=True)
    plan_parser.add_argument("--target", required=True)
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument("--python-executable", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--view-root", type=Path, required=True)
    verify_parser.add_argument("--prompt", type=Path, required=True)
    verify_parser.add_argument("--target", required=True)
    verify_parser.add_argument("--expected-process-sha256", required=True)
    verify_parser.add_argument("--expected-input-commitment-sha256")
    verify_parser.add_argument("--python-executable", type=Path, required=True)
    verify_parser.add_argument("--require-sa-outputs", action="store_true")

    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--view-root", type=Path, required=True)
    promote_parser.add_argument("--round-root", type=Path, required=True)
    promote_parser.add_argument("--prompt", type=Path, required=True)
    promote_parser.add_argument("--target", required=True)
    promote_parser.add_argument("--expected-process-sha256", required=True)
    promote_parser.add_argument(
        "--expected-input-commitment-sha256", required=True
    )
    promote_parser.add_argument("--launch-record", type=Path, required=True)
    promote_parser.add_argument("--expected-launch-id", required=True)
    promote_parser.add_argument(
        "--expected-process-seal-sha256", required=True
    )
    promote_parser.add_argument(
        "--expected-launch-record-sha256", required=True
    )
    promote_parser.add_argument(
        "--expected-output-commitment-sha256", required=True
    )
    promote_parser.add_argument("--python-executable", type=Path, required=True)

    args = parser.parse_args(argv)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if args.command == "plan":
            return print_result(
                "PLANNED",
                plan_prompt(
                    args.process,
                    args.view_root,
                    args.target,
                    args.output,
                    args.python_executable,
                ),
            )
        if args.command == "verify":
            verification, _context = verify_prompt(
                args.view_root,
                args.prompt,
                args.target,
                args.expected_process_sha256,
                args.python_executable,
                require_sa_outputs=args.require_sa_outputs,
                expected_input_commitment_sha256=(
                    args.expected_input_commitment_sha256
                ),
            )
            return print_result("VERIFIED", verification)
        return print_result(
            "PROMOTED",
            promote(
                args.view_root,
                args.round_root,
                args.prompt,
                args.target,
                args.expected_process_sha256,
                args.expected_input_commitment_sha256,
                args.launch_record,
                args.expected_launch_id,
                args.expected_process_seal_sha256,
                args.expected_launch_record_sha256,
                args.expected_output_commitment_sha256,
                args.python_executable,
            ),
        )
    except ContractError as exc:
        return print_result("FAIL", error=str(exc))
    except Exception as exc:  # pragma: no cover - fail closed at CLI boundary
        return print_result("FAIL", error=f"semantic-acceptance helper failed safely: {exc}")
    finally:
        sys.dont_write_bytecode = previous


if __name__ == "__main__":
    sys.exit(main())
