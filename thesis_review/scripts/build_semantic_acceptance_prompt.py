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
import sys
import types
from pathlib import Path
from typing import Any, Iterable, NamedTuple


ACCEPTANCE_DIRECTORY = "06-semantic-acceptance"
TARGET_RE = re.compile(r"(?:R[1-5]|AI)\Z")
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
PROMPT_SCHEMA = "thesis-review-semantic-acceptance-prompt-v2"
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


def file_identity_from_open_handle(handle: Any, label: str) -> FileIdentity:
    """Hash and identify the already-open file without following its pathname."""

    try:
        handle.flush()
        before = os.fstat(handle.fileno())
        handle.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    except (OSError, ValueError) as exc:
        raise ContractError(f"cannot identify {label}: {exc}") from exc
    if _file_stat_signature(before) != _file_stat_signature(after):
        raise ContractError(f"{label} changed while its identity was captured")
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
            path_stat = path.stat()
    except OSError as exc:
        raise ContractError(f"cannot identify {label}: {exc}") from exc
    if is_link_or_reparse(path):
        raise ContractError(f"{label} became link/reparse-backed while inspected: {path}")
    if _file_stat_signature(path_stat) != (
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


def unlink_created_file_if_unchanged(
    path: Path, expected: FileIdentity, label: str
) -> bool:
    """Delete only the exact object created by this invocation."""

    if not os.path.lexists(path):
        return False
    require_file_identity(path, expected, label)
    try:
        path.unlink()
    except OSError as exc:
        raise ContractError(f"cannot remove unchanged {label} {path}: {exc}") from exc
    return True


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


def rmdir_created_directory_if_unchanged(
    path: Path, expected: DirectoryIdentity, label: str
) -> bool:
    if not os.path.lexists(path):
        return False
    current = capture_directory_identity(path, label)
    if current != expected:
        raise ContractError(
            f"{label} was replaced; preserving the current directory: {path}"
        )
    try:
        path.rmdir()
    except OSError as exc:
        raise ContractError(
            f"cannot remove unchanged empty {label} {path}; preserving it: {exc}"
        ) from exc
    return True


def is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return False


def resolved(path: Path, *, must_exist: bool) -> Path:
    try:
        return path.expanduser().resolve(strict=must_exist)
    except OSError as exc:
        raise ContractError(f"cannot resolve path {path}: {exc}") from exc


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def require_safe_directory(path: Path, label: str) -> None:
    if is_link_or_reparse(path) or not path.is_dir():
        raise ContractError(f"{label} is missing, not a directory, or link/reparse-backed: {path}")


def require_safe_regular(path: Path, label: str) -> None:
    if is_link_or_reparse(path) or not path.is_file():
        raise ContractError(f"{label} is missing, non-regular, or link/reparse-backed: {path}")


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


def stable_process_projection(process: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in STABLE_PROCESS_FIELDS if field not in process]
    if missing:
        raise ContractError(f"preplan process is missing stable field(s): {missing}")
    round_id = process.get("round_id")
    retry_id = process.get("retry_id")
    output_language = process.get("output_language")
    for label, value in (
        ("round_id", round_id),
        ("retry_id", retry_id),
        ("output_language", output_language),
    ):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ContractError(f"stable process field {label} must be a nonempty trimmed string")
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
                directories.add(relative)
                walk(entry)
            elif entry.is_file():
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


def render_prompt(
    view_root: Path,
    target: str,
    process: dict[str, Any],
    opened: list[str],
    validator_commitments: dict[str, str],
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

Frozen validator commitments (authenticate before importing either file):
{validator_lines}

Start in a fresh empty task context with fork_turns=none. Follow the staged thesis-review skill and its governing references. Perform only independent semantic acceptance of the frozen {target} target. Do not create, modify, merge, grade, reject, or adjudicate thesis findings. Do not enumerate neighboring paths, contact another actor, or open any local file not listed below. No follow-up message will be sent after dispatch.

Private SA view root:
{view_root}

Open exactly these local files, in this order:
{opened_lines}

Public-endpoint rule:
No dynamic public endpoint is frozen into this prompt. At actor launch, derive the permitted endpoint set only from this target's own staged ledgers by applying the frozen validator at {validator_path}; open no endpoint outside that derived target-scoped set.

Write exactly these two actor-owned outputs at the private view root:
- {private_md}
- {private_csv}

Do not create or write {view_root / ACCEPTANCE_DIRECTORY}. That directory name is reserved for Stage O in the finalized round and is not an actor output path. Do not write an SA-* file anywhere else.

Run every Python command with bytecode writing disabled: set PYTHONDONTWRITEBYTECODE=1 and invoke Python with -B. Before freezing, run exactly:
python -B "{validator_path}" "{view_root}" "{target}"

Freeze only if the command exits 0 and its first nonempty stdout line is exactly PASS. Leave no __pycache__ directory or .pyc file. If a frozen input or staged-rule defect prevents PASS, stop without modifying any target artifact.
"""
    return text.replace("\r\n", "\n").encode("utf-8")


def exclusive_write(path: Path, value: bytes) -> None:
    exclusive_create_bytes(path, value, "prompt output")


def plan_prompt(
    process_path_value: Path,
    view_root_value: Path,
    target: str,
    output_value: Path,
) -> dict[str, Any]:
    process_path = resolved(process_path_value, must_exist=True)
    view_root = resolved(view_root_value, must_exist=False)
    output = resolved(output_value, must_exist=False)
    if is_within(output, view_root):
        raise ContractError("planned prompt output must live outside the private SA view")
    process = stable_process_projection(
        read_json_object(process_path, "preplan process envelope")
    )
    opened = algorithmic_opened_inputs(process, target)
    validator_commitments = canonical_validator_commitments()
    prompt = render_prompt(
        view_root, target, process, opened, validator_commitments
    )
    digest = sha256_bytes(prompt)
    exclusive_write(output, prompt)
    return {
        "schema": PROMPT_SCHEMA,
        "target": target,
        "view_root": str(view_root),
        "prompt_file": str(output),
        "prompt_sha256": digest,
        "stable_process_fields": process,
        "private_outputs": [
            str(path) for path in private_output_paths(view_root, target)
        ],
        "opened": opened,
        "public_endpoint_policy": "derive-at-launch-from-target-owned-ledgers",
        "validator_sha256": validator_commitments,
    }


def verify_prompt(
    view_root_value: Path,
    prompt_value: Path,
    target: str,
    expected_process_sha256: str,
    *,
    require_sa_outputs: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    view_root = resolved(view_root_value, must_exist=True)
    prompt_path = resolved(prompt_value, must_exist=True)
    require_safe_directory(view_root, "private SA view")
    require_safe_regular(prompt_path, "planned SA prompt")
    if is_within(prompt_path, view_root):
        raise ContractError("planned prompt must remain outside the private SA view")
    expected_process_sha256 = expected_process_sha256.upper()
    if not HEX64_RE.fullmatch(expected_process_sha256):
        raise ContractError(
            "expected process SHA-256 must be the 64-hex Stage-O external anchor"
        )

    actual_prompt = prompt_path.read_bytes()
    prompt_digest = sha256_bytes(actual_prompt)
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
    expected_prompt = render_prompt(
        view_root,
        target,
        stable_process,
        planned_opened,
        validator_commitments,
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
    metadata = {
        "schema": "thesis-review-semantic-acceptance-verification-v1",
        "target": target,
        "status": "VERIFIED",
        "view_root": str(view_root),
        "prompt_file": str(prompt_path),
        "prompt_sha256": digest,
        "process_prompt_sha256": process_hash,
        "process_sha256": process_sha256,
        "expected_process_sha256": expected_process_sha256,
        "opened": dynamic_opened,
        "public_endpoints_derived_at_verify": dynamic_endpoints,
        "validator_sha256": validator_commitments,
        "sa_output_state": output_state,
    }
    context = {
        "validator": validator,
        "shared": shared,
        "process": process,
        "opened": dynamic_opened,
        "view_root": view_root,
        "prompt_path": prompt_path,
    }
    return metadata, context


def ensure_disjoint_roots(view_root: Path, round_root: Path) -> None:
    if view_root == round_root or is_within(view_root, round_root) or is_within(round_root, view_root):
        raise ContractError("private SA view and finalized round root must be disjoint")


def compare_view_and_round_inputs(
    view_root: Path,
    round_root: Path,
    process: dict[str, Any],
    target: str,
    validator: Any,
    shared: Any,
) -> None:
    errors: list[str] = []
    opened = validator.canonical_sa_opened_inputs(
        view_root, process, target, errors
    )
    if errors:
        raise ContractError("; ".join(errors))
    for relative in opened:
        view_path = view_root / Path(relative)
        round_path = round_root / Path(relative)
        require_safe_regular(view_path, f"private-view input {relative}")
        require_safe_regular(round_path, f"round input {relative}")
        if sha256_file(view_path) != sha256_file(round_path):
            raise ContractError(f"private-view/round input byte mismatch: {relative}")


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
        if is_link_or_reparse(entry) or not entry.is_file():
            raise ContractError(f"unsafe/non-file existing acceptance entry: {entry}")
        if entry.name not in allowed:
            raise ContractError(f"unexpected existing acceptance entry: {entry}")


def copy_pair_exclusively(
    sources: tuple[Path, Path],
    destinations: tuple[Path, Path],
    expected_sources: tuple[FileIdentity, FileIdentity] | None = None,
) -> list[dict[str, str]]:
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

    return [
        {
            "source": str(source),
            "destination": str(destination),
            "sha256": expected.sha256,
        }
        for source, destination, _value, expected in payloads
    ]


def promote(
    view_root_value: Path,
    round_root_value: Path,
    prompt_value: Path,
    target: str,
    expected_process_sha256: str,
) -> dict[str, Any]:
    verification, context = verify_prompt(
        view_root_value,
        prompt_value,
        target,
        expected_process_sha256,
        require_sa_outputs=True,
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

    compare_view_and_round_inputs(
        view_root, round_root, process, target, validator, shared
    )
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
    destinations = round_output_paths(round_root, target)
    try:
        copied = copy_pair_exclusively(
            sources,
            destinations,
            validated_source_identities,
        )
    except Exception as exc:
        if created_directory is not None:
            try:
                rmdir_created_directory_if_unchanged(
                    acceptance_dir,
                    created_directory,
                    "round semantic-acceptance directory",
                )
            except ContractError as cleanup_exc:
                raise ContractError(
                    f"promotion failed: {exc}; directory rollback failed closed: "
                    f"{cleanup_exc}"
                ) from exc
        raise
    return {
        "schema": "thesis-review-semantic-acceptance-promotion-v1",
        "target": target,
        "status": "PROMOTED",
        "verification": verification,
        "files": copied,
    }


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

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--view-root", type=Path, required=True)
    verify_parser.add_argument("--prompt", type=Path, required=True)
    verify_parser.add_argument("--target", required=True)
    verify_parser.add_argument("--expected-process-sha256", required=True)
    verify_parser.add_argument("--require-sa-outputs", action="store_true")

    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--view-root", type=Path, required=True)
    promote_parser.add_argument("--round-root", type=Path, required=True)
    promote_parser.add_argument("--prompt", type=Path, required=True)
    promote_parser.add_argument("--target", required=True)
    promote_parser.add_argument("--expected-process-sha256", required=True)

    args = parser.parse_args(argv)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if args.command == "plan":
            return print_result(
                "PLANNED",
                plan_prompt(
                    args.process, args.view_root, args.target, args.output
                ),
            )
        if args.command == "verify":
            verification, _context = verify_prompt(
                args.view_root,
                args.prompt,
                args.target,
                args.expected_process_sha256,
                require_sa_outputs=args.require_sa_outputs,
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
