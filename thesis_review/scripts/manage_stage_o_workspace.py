#!/usr/bin/env python3
"""Fail-closed Stage-O filesystem operations for a thesis-review run.

This helper performs only mechanical workspace work.  It never reads thesis
semantics, reviewer prose, or prior-round findings.  Subcommands create the
deterministic Stage-R scratch directories, stage immutable rule inputs, build
closed SA/C/S actor views by exact allowlist, retire transient round-resident
rules, and promote only a completed C/S actor's closed output set.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable


SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
REFERENCE_NAMES = (
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
)
ROUND_SCRIPT_NAMES = (
    "validate_review_bundle.py",
    "validate_stage_p_output.py",
    "validate_reviewer_output.py",
    "materialize_owner_outputs.py",
    "validate_r5_output.py",
    "validate_r4_output.py",
    "validate_master_r3_output.py",
    "validate_ai_output.py",
    "validate_semantic_acceptance_output.py",
    "materialize_semantic_acceptance_gate.py",
    "validate_chair_output.py",
    "validate_summary_output.py",
)
C_RULE_SCRIPT_NAMES = (
    "validate_review_bundle.py",
    "materialize_owner_outputs.py",
    "validate_semantic_acceptance_output.py",
    "validate_chair_output.py",
)
S_RULE_SCRIPT_NAMES = (
    "validate_review_bundle.py",
    "materialize_owner_outputs.py",
    "validate_summary_output.py",
)
C_OUTPUTS = (
    "90-chair-synthesis.md",
    "91-revision-ledger.md",
    "91-revision-ledger.csv",
    "91-ai-actionable-ledger.csv",
    "92-new-evidence-or-experiments.md",
    "92-new-evidence-or-experiments.csv",
)
S_OUTPUTS = (
    "93-user-facing-summary.md",
    "93-current-actionable-items.csv",
    "93-current-ai-actionable-items.csv",
)
P_OUTPUTS = (
    "00-manifest.md",
    "01-policy-basis.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
)
AI_OUTPUTS = ("05-ai-style-assessment.md",)
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
CANONICAL_LAUNCH_SCHEMA = "thesis-review-actor-launch-v3"
R_ACTOR_RE = re.compile(r"R[1-5]\Z")
SA_TARGET_RE = re.compile(r"(?:R[1-5]|AI)\Z")
GENERAL_ACTOR_RE = re.compile(r"(?:P|R[1-5]|AI)\Z")


class ContractError(RuntimeError):
    """Fail-closed Stage-O workspace error."""


def load_module(path: Path, name: str) -> Any:
    require_regular(path, f"module {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ContractError(f"cannot load module specification: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def uses_windows_forbidden_namespace(value: str) -> bool:
    spelling = value.replace("/", "\\")
    return spelling.startswith("\\\\") or spelling.startswith("\\?\\") or spelling.startswith("\\.\\")


def absolute_local_path(value: Path, label: str, *, must_exist: bool) -> Path:
    raw = os.fspath(value)
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ContractError(f"{label} must be absolute")
    if os.name == "nt":
        if uses_windows_forbidden_namespace(raw):
            raise ContractError(f"{label} must not use a UNC/device namespace")
        drive, tail = os.path.splitdrive(raw)
        if not re.fullmatch(r"[A-Za-z]:", drive) or ":" in tail:
            raise ContractError(f"{label} must use one local drive and no NTFS stream")
    if any(part == ".." for part in candidate.parts):
        raise ContractError(f"{label} must not contain parent traversal")
    normalized = Path(os.path.abspath(raw))
    if os.path.normcase(os.path.normpath(raw)) != os.path.normcase(os.path.normpath(str(normalized))):
        raise ContractError(f"{label} must already use canonical absolute spelling")
    if must_exist and not os.path.lexists(normalized):
        raise ContractError(f"{label} does not exist: {normalized}")
    reject_reparse_traversal(normalized, label)
    reject_windows_short_alias(normalized, label)
    return normalized


def reject_windows_short_alias(path: Path, label: str) -> None:
    """Reject 8.3 aliases for the deepest existing ancestor on Windows."""

    if os.name != "nt":
        return
    probe = path
    while not os.path.lexists(probe):
        parent = probe.parent
        if parent == probe:
            return
        probe = parent
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_long = kernel32.GetLongPathNameW
    get_long.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    get_long.restype = ctypes.c_uint
    needed = get_long(str(probe), None, 0)
    if needed == 0:
        raise ContractError(
            f"cannot canonicalize {label} for 8.3-alias rejection: "
            f"WinError {ctypes.get_last_error()}"
        )
    buffer = ctypes.create_unicode_buffer(needed + 1)
    written = get_long(str(probe), buffer, len(buffer))
    if written == 0 or written >= len(buffer):
        raise ContractError(f"cannot canonicalize {label} for 8.3-alias rejection")
    if os.path.normcase(os.path.normpath(str(probe))) != os.path.normcase(
        os.path.normpath(buffer.value)
    ):
        raise ContractError(f"{label} must not use an NTFS 8.3 alias: {probe}")


def reject_reparse_traversal(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ContractError(f"cannot inspect {label} component {current}: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ContractError(f"{label} traverses a link/reparse point: {current}")


def require_directory(path: Path, label: str) -> Path:
    canonical = absolute_local_path(path, label, must_exist=True)
    try:
        metadata = os.stat(canonical, follow_symlinks=False)
    except OSError as exc:
        raise ContractError(f"cannot inspect {label}: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise ContractError(f"{label} must be a directory")
    return canonical


def require_round_root(path: Path) -> Path:
    round_root = require_directory(path, "round root")
    if round_root.name != "round":
        raise ContractError("round root must be the exact 'round' child of one run root")
    run_root = require_directory(round_root.parent, "run root")
    require_directory(run_root / "views", "run views directory")
    require_directory(run_root / "orchestration", "run orchestration directory")
    return round_root


def require_regular(path: Path, label: str) -> Path:
    canonical = absolute_local_path(path, label, must_exist=True)
    try:
        metadata = os.stat(canonical, follow_symlinks=False)
    except OSError as exc:
        raise ContractError(f"cannot inspect {label}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode) or int(metadata.st_nlink) != 1:
        raise ContractError(f"{label} must be a single-link regular file")
    return canonical


def directory_empty(path: Path, label: str) -> None:
    try:
        first = next(path.iterdir(), None)
    except OSError as exc:
        raise ContractError(f"cannot enumerate {label}: {exc}") from exc
    if first is not None:
        raise ContractError(f"{label} must be empty")


def physically_within(child: Path, parent: Path) -> bool:
    child_abs = os.path.normcase(os.path.abspath(str(child)))
    parent_abs = os.path.normcase(os.path.abspath(str(parent)))
    try:
        return os.path.commonpath([child_abs, parent_abs]) == parent_abs
    except ValueError:
        return False


def boundaries_overlap(left: Path, right: Path) -> bool:
    return physically_within(left, right) or physically_within(right, left)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def file_identity(path: Path) -> tuple[int, int, int, int, str]:
    source = require_regular(path, str(path))
    metadata = source.stat()
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
        sha256_file(source),
    )


def rollback_contract() -> Any:
    """Load the shared by-handle rollback implementation.

    Stage-O creates files in finalized namespaces. A pathname-only
    ``identity check; unlink`` sequence can erase an unrelated replacement,
    so rollback must authenticate the object held open for deletion.
    """

    return load_module(
        SCRIPT_ROOT / "build_semantic_acceptance_prompt.py",
        "thesis_review_stage_o_authenticated_rollback",
    )


def copy_file_exclusive_with_identity(
    source: Path, destination: Path
) -> tuple[str, tuple[int, int, int, int, str]]:
    source = require_regular(source, f"copy source {source}")
    require_directory(destination.parent, f"copy destination parent {destination.parent}")
    if os.path.lexists(destination):
        raise ContractError(f"refusing to overwrite destination: {destination}")
    before = file_identity(source)
    digest = hashlib.sha256()
    destination_identity: tuple[int, int, int, int, str] | None = None
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        after = file_identity(source)
        destination_identity = file_identity(destination)
        produced = digest.hexdigest().upper()
        if before != after or destination_identity[4] != produced or produced != before[4]:
            raise ContractError(f"copy identity/hash drift for {source} -> {destination}")
        return produced, destination_identity
    except Exception as exc:
        if destination_identity is None and os.path.lexists(destination):
            try:
                destination_identity = file_identity(destination)
            except Exception as identity_exc:
                raise ContractError(
                    f"cannot publish {destination}: {exc}; partial destination could "
                    "not be authenticated for rollback and was preserved: "
                    f"{identity_exc}"
                ) from exc
        if destination_identity is not None:
            cleanup = rollback_contract()
            try:
                cleanup.unlink_created_file_if_unchanged(
                    destination,
                    cleanup.FileIdentity(*destination_identity),
                    "Stage-O copied output",
                )
            except Exception as cleanup_exc:
                raise ContractError(
                    f"cannot publish {destination}: {exc}; rollback failed closed and "
                    f"preserved the current object: {cleanup_exc}"
                ) from exc
        if isinstance(exc, ContractError):
            raise
        raise ContractError(f"cannot publish {destination}: {exc}") from exc


def copy_file_exclusive(source: Path, destination: Path) -> str:
    digest, _identity = copy_file_exclusive_with_identity(source, destination)
    return digest


def safe_relative(value: str, label: str) -> Path:
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or any(not part for part in path.parts)
    ):
        raise ContractError(f"{label} must be a safe relative path")
    return path


def make_parents(root: Path, relative: Path) -> None:
    current = root
    for part in relative.parent.parts:
        current = current / part
        if os.path.lexists(current):
            require_directory(current, f"staging directory {current}")
        else:
            try:
                current.mkdir()
            except OSError as exc:
                raise ContractError(f"cannot create staging directory {current}: {exc}") from exc


def publish_view(
    source_root: Path,
    view_root: Path,
    relatives: Iterable[str],
    *,
    extra_trees: Iterable[str] = (),
) -> dict[str, str]:
    source_root = require_directory(source_root, "source root")
    if os.path.lexists(view_root):
        raise ContractError(f"refusing to replace existing actor view: {view_root}")
    parent = require_directory(view_root.parent, "actor-view parent")
    if boundaries_overlap(source_root, view_root):
        raise ContractError("source root and actor view must not overlap")
    staging = parent / f".{view_root.name}.staging-{uuid.uuid4().hex}"
    if os.path.lexists(staging):
        raise ContractError(f"unexpected staging collision: {staging}")
    staging.mkdir()
    hashes: dict[str, str] = {}
    try:
        ordered = list(relatives)
        if len(ordered) != len(set(ordered)):
            raise ContractError("actor-view allowlist contains duplicate paths")
        for index, item in enumerate(ordered):
            relative = safe_relative(item, f"allowlist[{index}]")
            source = source_root / relative
            destination = staging / relative
            make_parents(staging, relative)
            hashes[relative.as_posix()] = copy_file_exclusive(source, destination)
        for index, tree_name in enumerate(extra_trees):
            relative = safe_relative(tree_name, f"extra_trees[{index}]")
            if len(relative.parts) != 1:
                raise ContractError("extra tree must be one top-level directory name")
            source_tree = require_directory(source_root / relative, f"extra tree {relative}")
            destination_tree = staging / relative
            destination_tree.mkdir()
            for source in sorted(source_tree.rglob("*"), key=lambda item: item.as_posix()):
                rel_child = source.relative_to(source_root)
                if source.is_dir():
                    make_parents(staging, rel_child / "placeholder")
                    (staging / rel_child).mkdir(exist_ok=True)
                else:
                    make_parents(staging, rel_child)
                    hashes[rel_child.as_posix()] = copy_file_exclusive(
                        source, staging / rel_child
                    )
        os.rename(staging, view_root)
    except Exception:
        # A partially created staging tree is deliberately preserved.  The
        # current retry is no longer admissible and Stage O must quarantine it.
        raise
    return hashes


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    source = require_regular(path, label)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    before = file_identity(source)
    try:
        payload = source.read_bytes()
        value = json.loads(
            payload.decode("utf-8-sig"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractError(f"cannot parse {label}: {exc}") from exc
    if file_identity(source) != before:
        raise ContractError(f"{label} changed while it was being read")
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be one JSON object")
    return value


def reviewer_count(process: dict[str, Any]) -> int:
    degree = process.get("degree_level")
    if degree == "doctorate":
        return 5
    if degree == "masters":
        return 3
    raise ContractError("process degree_level must be doctorate or masters")


def expected_round_instruction_paths(skill_root: Path) -> list[tuple[Path, Path]]:
    result = [(skill_root / "SKILL.md", Path("SKILL.md"))]
    result.extend(
        (skill_root / "references" / name, Path(name)) for name in REFERENCE_NAMES
    )
    result.extend(
        (skill_root / "scripts" / name, Path("rules") / "scripts" / name)
        for name in ROUND_SCRIPT_NAMES
    )
    return result


def command_init_scratch(args: argparse.Namespace) -> dict[str, Any]:
    process_path = require_regular(args.process, "stable preplan process")
    round_root = require_round_root(args.round_root)
    scratch_parent = require_directory(args.scratch_parent, "scratch parent")
    if boundaries_overlap(round_root.parent, scratch_parent):
        raise ContractError("scratch parent and complete run root must not overlap")
    reviewer = load_module(
        SCRIPT_ROOT / "build_reviewer_prompt.py", "thesis_review_stage_o_reviewer"
    )
    process = reviewer.stable_process_projection(
        read_json_object(process_path, "stable preplan process")
    )
    actor = reviewer.require_reviewer_actor(process, args.actor)
    basename = reviewer.expected_scratch_basename(round_root, process, actor)
    destination = scratch_parent / basename
    if os.path.lexists(destination):
        raise ContractError(f"refusing to reuse reviewer scratch: {destination}")
    destination.mkdir()
    directory_empty(destination, "new reviewer scratch")
    return {
        "operation": "init-r-scratch",
        "actor": actor,
        "scratch_dir": str(destination),
        "scratch_basename": basename,
    }


def command_stage_round(args: argparse.Namespace) -> dict[str, Any]:
    skill_root = require_directory(args.skill_root, "skill root")
    round_root = require_round_root(args.round_root)
    instructions = expected_round_instruction_paths(skill_root)
    if os.path.lexists(round_root / "rules"):
        raise ContractError("refusing to replace existing round rules directory")
    (round_root / "rules").mkdir()
    (round_root / "rules" / "scripts").mkdir()
    hashes: dict[str, str] = {}
    for source, relative in instructions:
        destination = round_root / relative
        hashes[relative.as_posix()] = copy_file_exclusive(source, destination)
    return {
        "operation": "stage-round-inputs",
        "round_root": str(round_root),
        "files": hashes,
    }


def command_retire_round(args: argparse.Namespace) -> dict[str, Any]:
    skill_root = require_directory(args.skill_root, "skill root")
    round_root = require_round_root(args.round_root)
    destination = absolute_local_path(args.destination, "retirement destination", must_exist=False)
    if os.path.lexists(destination):
        raise ContractError(f"refusing to replace retirement destination: {destination}")
    require_directory(destination.parent, "retirement parent")
    if boundaries_overlap(round_root, destination):
        raise ContractError("retirement destination must remain outside the round root")
    expected = expected_round_instruction_paths(skill_root)
    expected_files = {
        relative.as_posix(): sha256_file(require_regular(source, f"canonical {relative}"))
        for source, relative in expected
    }
    for relative, digest in expected_files.items():
        staged = require_regular(round_root / safe_relative(relative, relative), f"staged {relative}")
        if sha256_file(staged) != digest:
            raise ContractError(f"staged rule hash drift before retirement: {relative}")
    destination.mkdir()
    moved: list[str] = []
    try:
        for name in ("SKILL.md", *REFERENCE_NAMES):
            os.rename(round_root / name, destination / name)
            moved.append(name)
        os.rename(round_root / "rules", destination / "rules")
        moved.append("rules")
        manifest = {
            "schema": "thesis-review-retired-round-inputs-v1",
            "round_root": str(round_root),
            "files": expected_files,
        }
        manifest_path = destination / "retirement-manifest.json"
        with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        # Preserve the partial retirement as evidence; do not guess a rollback.
        raise
    return {
        "operation": "retire-round-inputs",
        "round_root": str(round_root),
        "destination": str(destination),
        "moved": moved,
        "file_count": len(expected_files),
    }


def command_stage_sa(args: argparse.Namespace) -> dict[str, Any]:
    round_root = require_round_root(args.round_root)
    view_root = absolute_local_path(args.view_root, "SA view root", must_exist=False)
    run_root = require_directory(round_root.parent, "run root")
    views_root = require_directory(run_root / "views", "views root")
    if view_root.parent != views_root:
        raise ContractError("SA view must be a direct child of the run's views directory")
    target = args.target.upper()
    if SA_TARGET_RE.fullmatch(target) is None or view_root.name != f"SA-{target}":
        raise ContractError("SA target and private-view basename do not agree")
    semantic = load_module(
        SCRIPT_ROOT / "build_semantic_acceptance_prompt.py",
        "thesis_review_stage_o_semantic",
    )
    process = semantic.stable_process_projection(
        read_json_object(round_root / "00-process-parameters.json", "process envelope")
    )
    opened = semantic.algorithmic_opened_inputs(process, target)
    hashes = publish_view(round_root, view_root, opened)
    return {
        "operation": "stage-sa-view",
        "target": target,
        "view_root": str(view_root),
        "opened": opened,
        "hashes": hashes,
    }


def canonical_clean_actor_inputs(
    round_root: Path, process: dict[str, Any], actor: str
) -> tuple[list[str], list[str], list[str]]:
    validator = load_module(
        SCRIPT_ROOT / "validate_review_bundle.py", "thesis_review_stage_o_validator"
    )
    opened = validator.canonical_stage_opened_inputs(
        process, reviewer_count(process), actor, round_root
    )
    rule_like = {
        "SKILL.md",
        *REFERENCE_NAMES,
    }
    data = [
        item
        for item in opened
        if item not in rule_like and not item.startswith("rules/scripts/")
    ]
    instructions = [item for item in opened if item not in data]
    return opened, data, instructions


def instruction_source(skill_root: Path, relative_name: str) -> Path:
    """Resolve one canonical actor-rule input without consulting the round."""

    relative = safe_relative(relative_name, "actor instruction")
    if relative_name == "SKILL.md":
        return skill_root / "SKILL.md"
    if relative_name.startswith("rules/scripts/"):
        return skill_root / "scripts" / relative.name
    if len(relative.parts) == 1 and relative.name in REFERENCE_NAMES:
        return skill_root / "references" / relative.name
    raise ContractError(f"unrecognized actor instruction path: {relative_name}")


def publish_clean_actor_view(
    round_root: Path,
    skill_root: Path,
    view_root: Path,
    actor: str,
    opened: list[str],
    instruction_names: list[str],
) -> dict[str, str]:
    """Atomically publish one unified, exact C/S private view.

    Rule inputs and substantive inputs deliberately share the same private root:
    the scoped validators resolve their sibling rule modules from that root and
    can therefore prove one closed actor-visible filesystem rather than two
    separately trusted trees.
    """

    if os.path.lexists(view_root):
        raise ContractError(f"refusing to replace existing actor view: {view_root}")
    parent = require_directory(view_root.parent, "actor-view parent")
    if boundaries_overlap(round_root, view_root) or boundaries_overlap(skill_root, view_root):
        raise ContractError("actor view must not overlap the round or canonical skill root")
    instruction_set = set(instruction_names)
    if len(opened) != len(set(opened)):
        raise ContractError(f"canonical {actor} opened-input list contains duplicates")
    staging = parent / f".{view_root.name}.staging-{uuid.uuid4().hex}"
    if os.path.lexists(staging):
        raise ContractError(f"unexpected staging collision: {staging}")
    staging.mkdir()
    hashes: dict[str, str] = {}
    try:
        for index, item in enumerate(opened):
            relative = safe_relative(item, f"{actor} opened[{index}]")
            source = round_root / relative
            if item in instruction_set:
                canonical_source = instruction_source(skill_root, item)
                if sha256_file(require_regular(source, f"staged {actor} instruction")) != sha256_file(
                    require_regular(canonical_source, f"canonical {actor} instruction")
                ):
                    raise ContractError(
                        f"staged {actor} instruction differs from the canonical skill: {item}"
                    )
            make_parents(staging, relative)
            hashes[relative.as_posix()] = copy_file_exclusive(
                source, staging / relative
            )
        os.rename(staging, view_root)
    except Exception:
        # Preserve an incomplete staging tree as quarantine evidence.  Reusing
        # this retry after a partial publication is forbidden.
        raise
    return hashes


def input_commitment(view_root: Path, opened: Iterable[str]) -> str:
    """Bind exact actor-input paths, identities, metadata, and bytes."""

    records: list[dict[str, Any]] = []
    ordered = list(opened)
    if len(ordered) != len(set(ordered)):
        raise ContractError("actor input commitment paths contain duplicates")
    for index, item in enumerate(ordered):
        relative = safe_relative(item, f"input commitment[{index}]")
        identity = file_identity(view_root / relative)
        records.append(
            {
                "path": relative.as_posix(),
                "st_dev": identity[0],
                "st_ino": identity[1],
                "st_size": identity[2],
                "st_mtime_ns": identity[3],
                "sha256": identity[4],
            }
        )
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def canonical_general_actor_inputs(
    round_root: Path, process: dict[str, Any], actor: str
) -> tuple[list[str], list[str]]:
    if GENERAL_ACTOR_RE.fullmatch(actor) is None:
        raise ContractError(f"unsupported general actor: {actor}")
    validator = load_module(
        SCRIPT_ROOT / "validate_review_bundle.py", "thesis_review_stage_o_general"
    )
    opened = validator.canonical_stage_opened_inputs(
        process, reviewer_count(process), actor, round_root
    )
    instructions = [
        item
        for item in opened
        if item == "SKILL.md"
        or item in REFERENCE_NAMES
        or item.startswith("rules/scripts/")
    ]
    return opened, instructions


def general_actor_outputs(process: dict[str, Any], actor: str) -> list[str]:
    if actor == "P":
        return list(P_OUTPUTS)
    if actor == "AI":
        return list(AI_OUTPUTS)
    if R_ACTOR_RE.fullmatch(actor):
        reviewer = load_module(
            SCRIPT_ROOT / "build_reviewer_prompt.py",
            "thesis_review_stage_o_general_reviewer",
        )
        return reviewer.reviewer_owned_outputs(process, actor)
    raise ContractError(f"unsupported general actor: {actor}")


def command_stage_actor(args: argparse.Namespace) -> dict[str, Any]:
    actor = args.actor.upper()
    if GENERAL_ACTOR_RE.fullmatch(actor) is None:
        raise ContractError("actor view is supported only for P, R1..R5, or AI")
    skill_root = require_directory(args.skill_root, "skill root")
    round_root = require_round_root(args.round_root)
    view_root = absolute_local_path(args.view_root, "actor view", must_exist=False)
    views_root = require_directory(round_root.parent / "views", "views root")
    if view_root.parent != views_root or view_root.name != actor:
        raise ContractError(
            "actor view must be the exact actor-ID direct child of run/views"
        )
    process = read_json_object(
        round_root / "00-process-parameters.json", "process envelope"
    )
    # Degree-inapplicable reviewer IDs are rejected by the canonical reviewer
    # helper before any destination is published.
    if R_ACTOR_RE.fullmatch(actor):
        reviewer = load_module(
            SCRIPT_ROOT / "build_reviewer_prompt.py",
            "thesis_review_stage_o_general_actor_check",
        )
        reviewer.require_reviewer_actor(process, actor)
    opened, instructions = canonical_general_actor_inputs(
        round_root, process, actor
    )
    hashes = publish_clean_actor_view(
        round_root, skill_root, view_root, actor, opened, instructions
    )
    outputs = general_actor_outputs(process, actor)
    for relative in outputs:
        if os.path.lexists(view_root / safe_relative(relative, "actor output")):
            raise ContractError(f"{actor} output exists before dispatch: {relative}")
    return {
        "operation": "stage-actor-view",
        "actor": actor,
        "view_root": str(view_root),
        "opened": opened,
        "outputs": outputs,
        "hashes": hashes,
        "input_commitment_sha256": input_commitment(view_root, opened),
    }


def expected_view_directories(relative_files: Iterable[str]) -> set[str]:
    directories: set[str] = set()
    for value in relative_files:
        relative = safe_relative(value, "closed-view file")
        current = Path()
        for part in relative.parent.parts:
            current = current / part
            directories.add(current.as_posix())
    return directories


def closed_view_snapshot(
    view_root: Path,
    expected_files: Iterable[str],
    validator: Any,
) -> dict[str, tuple[int, int, int, int, str]]:
    """Stage-O-only exact topology and file-identity snapshot."""

    root = require_directory(view_root, "closed actor view")
    root_before = os.lstat(root)
    root_streams, root_stream_error = validator._ntfs_named_streams(root)
    if root_stream_error is not None or root_streams:
        raise ContractError(
            "closed actor-view root has unsafe named-stream state: "
            f"{root_stream_error or root_streams}"
        )
    expected = list(expected_files)
    if len(expected) != len(set(expected)):
        raise ContractError("closed actor-view expected file set has duplicates")
    expected_file_set = {safe_relative(item, "closed-view file").as_posix() for item in expected}
    expected_dirs = expected_view_directories(expected)
    observed_files: set[str] = set()
    observed_dirs: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir(), key=lambda item: item.name):
            relative = entry.relative_to(root).as_posix()
            try:
                metadata = os.lstat(entry)
            except OSError as exc:
                raise ContractError(f"cannot inspect actor-view entry {relative}: {exc}") from exc
            attributes = int(getattr(metadata, "st_file_attributes", 0))
            if stat.S_ISLNK(metadata.st_mode) or bool(
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise ContractError(f"actor view contains link/reparse entry: {relative}")
            streams, stream_error = validator._ntfs_named_streams(entry)
            if stream_error is not None or streams:
                raise ContractError(
                    f"actor-view entry has unsafe named-stream state: {relative}: "
                    f"{stream_error or streams}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                observed_dirs.add(relative)
                # Record an unknown directory as an exact-closure defect, but
                # never enumerate its children. Only allowlisted branches are
                # eligible for descent.
                if relative in expected_dirs:
                    stack.append(entry)
            elif stat.S_ISREG(metadata.st_mode) and int(metadata.st_nlink) == 1:
                observed_files.add(relative)
            else:
                raise ContractError(
                    f"actor view contains special or hard-linked entry: {relative}"
                )
    if observed_files != expected_file_set or observed_dirs != expected_dirs:
        raise ContractError(
            "actor view is not an exact closed file tree; "
            f"missing_files={sorted(expected_file_set-observed_files)}, "
            f"extra_files={sorted(observed_files-expected_file_set)}, "
            f"missing_dirs={sorted(expected_dirs-observed_dirs)}, "
            f"extra_dirs={sorted(observed_dirs-expected_dirs)}"
        )
    identities = {
        relative: file_identity(root / Path(relative))
        for relative in sorted(observed_files)
    }
    root_after = os.lstat(root)
    if (
        int(root_before.st_dev),
        int(root_before.st_ino),
        int(root_before.st_mode),
    ) != (
        int(root_after.st_dev),
        int(root_after.st_ino),
        int(root_after.st_mode),
    ):
        raise ContractError("closed actor-view root changed during topology scan")
    root_streams, root_stream_error = validator._ntfs_named_streams(root)
    if root_stream_error is not None or root_streams:
        raise ContractError(
            "closed actor-view root gained unsafe named-stream state: "
            f"{root_stream_error or root_streams}"
        )
    require_directory(root, "closed actor view after topology scan")
    return identities


def validate_launch_for_promotion(
    *,
    actor: str,
    view_root: Path,
    round_root: Path,
    process: dict[str, Any],
    input_commitment_sha256: str,
    launch_record_path: Path,
    expected_launch_id: str,
    expected_process_seal_sha256: str,
    expected_launch_record_sha256: str,
    expected_output_commitment_sha256: str,
) -> dict[str, Any]:
    """Revalidate the canonical v3 launch receipt before any output gate/copy."""

    record_path = require_regular(launch_record_path, "actor launch record")
    if boundaries_overlap(record_path, view_root) or boundaries_overlap(
        record_path, round_root
    ):
        raise ContractError("actor launch record must remain outside view and round")
    record_identity_before = file_identity(record_path)
    record_sha256 = str(expected_launch_record_sha256).strip().upper()
    if HEX64_RE.fullmatch(record_sha256) is None:
        raise ContractError("expected launch-record SHA-256 must be 64 hexadecimal")
    if record_identity_before[4] != record_sha256:
        raise ContractError("actor launch record differs from the external hash anchor")
    output_commitment_sha256 = str(
        expected_output_commitment_sha256
    ).strip().upper()
    if HEX64_RE.fullmatch(output_commitment_sha256) is None:
        raise ContractError("expected output commitment must be 64 hexadecimal")
    record = read_json_object(record_path, "actor launch record")
    if record.get("schema") != CANONICAL_LAUNCH_SCHEMA:
        raise ContractError(
            f"actor launch record schema must be {CANONICAL_LAUNCH_SCHEMA}"
        )
    try:
        launch_id = str(uuid.UUID(str(expected_launch_id)))
    except (ValueError, AttributeError) as exc:
        raise ContractError("expected launch ID must be one canonical UUID") from exc
    if str(expected_launch_id) != launch_id:
        raise ContractError("expected launch ID must use lowercase canonical spelling")
    seal_sha256 = str(expected_process_seal_sha256).strip().upper()
    if HEX64_RE.fullmatch(seal_sha256) is None:
        raise ContractError("expected process-seal SHA-256 must be 64 hexadecimal")
    process_sha256 = sha256_file(
        require_regular(
            round_root / "00-process-parameters.json",
            "finalized process envelope",
        )
    )
    if sha256_file(
        require_regular(
            view_root / "00-process-parameters.json", "actor-view process envelope"
        )
    ) != process_sha256:
        raise ContractError("actor-view and finalized process bytes differ")
    prompt_map = process.get("actor_prompt_sha256")
    prompt_sha256 = (
        str(prompt_map.get(actor, "")).upper()
        if isinstance(prompt_map, dict)
        else ""
    )
    if HEX64_RE.fullmatch(prompt_sha256) is None:
        raise ContractError(f"sealed process lacks a valid prompt hash for {actor}")
    outputs = (
        actor_view_contract_for_promotion(view_root, process, actor)
    )
    if input_commitment(view_root, outputs) != output_commitment_sha256:
        raise ContractError("actor outputs differ from the retained launch commitment")
    record_workspace = require_directory(
        Path(str(record.get("workspace", ""))), "launch-record actor workspace"
    )
    if record_workspace != view_root:
        raise ContractError("launch record workspace does not equal actor private view")
    log_path = require_regular(
        Path(str(record.get("log_path", ""))), "actor transport JSONL"
    )
    transport = load_module(
        SCRIPT_ROOT / "validate_actor_transport.py",
        "thesis_review_stage_o_transport_gate",
    )
    try:
        transport_result = transport.validate_log(
            log_path,
            actor,
            record_path,
            prompt_sha256,
            launch_id,
            process_sha256,
            seal_sha256,
            input_commitment_sha256,
            output_commitment_sha256,
            record_sha256,
        )
    except Exception as exc:
        raise ContractError(
            f"canonical actor transport receipt failed before promotion: {exc}"
        ) from exc
    if file_identity(record_path) != record_identity_before:
        raise ContractError("actor launch record changed during promotion receipt gate")
    if input_commitment(view_root, outputs) != output_commitment_sha256:
        raise ContractError("actor outputs changed during promotion receipt gate")
    retry = load_module(
        SCRIPT_ROOT / "manage_review_retry.py",
        "thesis_review_stage_o_retry_gate",
    )
    try:
        seal_result = retry.verify_process_seal(
            argparse.Namespace(
                workspace=round_root.parent.parent,
                run_root=round_root.parent,
                expected_process_sha256=process_sha256,
                expected_seal_sha256=seal_sha256,
            )
        )
    except Exception as exc:
        raise ContractError(
            f"sealed process failed immediately before promotion: {exc}"
        ) from exc
    return {
        "launch_id": launch_id,
        "launch_record": str(record_path),
        "launch_record_sha256": record_sha256,
        "output_commitment_sha256": output_commitment_sha256,
        "transport": transport_result,
        "process_seal": seal_result,
    }


def actor_view_contract_for_promotion(
    view_root: Path, process: dict[str, Any], actor: str
) -> list[str]:
    """Return the exact actor-owned terminal output order used by the launcher."""

    if actor == "P" or actor == "AI" or GENERAL_ACTOR_RE.fullmatch(actor):
        return general_actor_outputs(process, actor)
    if actor in {"C", "S"}:
        return list(C_OUTPUTS if actor == "C" else S_OUTPUTS)
    if actor.startswith("SA-"):
        target = actor[3:]
        semantic = load_module(
            SCRIPT_ROOT / "build_semantic_acceptance_prompt.py",
            "thesis_review_stage_o_semantic_output_contract",
        )
        return [
            path.relative_to(view_root).as_posix()
            for path in semantic.private_output_paths(view_root, target)
        ]
    raise ContractError(f"unsupported actor launch receipt: {actor}")


def general_scoped_gate_command(
    actor: str, view_root: Path, process: dict[str, Any]
) -> list[str]:
    if actor == "P":
        script = "validate_stage_p_output.py"
        tail: list[str] = []
    elif actor == "AI":
        script = "validate_ai_output.py"
        tail = []
    elif process.get("degree_level") == "doctorate" and actor == "R4":
        script = "validate_r4_output.py"
        tail = []
    elif process.get("degree_level") == "doctorate" and actor == "R5":
        script = "validate_r5_output.py"
        tail = []
    elif process.get("degree_level") == "masters" and actor == "R3":
        script = "validate_master_r3_output.py"
        tail = []
    else:
        script = "validate_reviewer_output.py"
        tail = [actor]
    return [
        sys.executable,
        "-B",
        str(view_root / "rules" / "scripts" / script),
        str(view_root),
        *tail,
    ]


def run_general_scoped_gate(
    actor: str, view_root: Path, process: dict[str, Any]
) -> list[str]:
    import subprocess

    command = general_scoped_gate_command(actor, view_root, process)
    require_regular(Path(command[2]), f"{actor} scoped validator")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(view_root),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    first = next(
        (line.strip() for line in completed.stdout.splitlines() if line.strip()), ""
    )
    if completed.returncode != 0 or first != "PASS":
        raise ContractError(
            f"{actor} scoped gate failed before promotion: "
            f"exit={completed.returncode}; first={first!r}; "
            f"tail={completed.stdout[-2000:]!r}"
        )
    return command


def copy_output_set(
    view_root: Path,
    round_root: Path,
    outputs: list[str],
    *,
    opened: list[str],
    expected_view_snapshot: dict[str, tuple[int, int, int, int, str]],
    expected_input_commitment: str,
    validator: Any,
) -> dict[str, str]:
    expected_view_files = [*opened, *outputs]
    if (
        closed_view_snapshot(view_root, expected_view_files, validator)
        != expected_view_snapshot
    ):
        raise ContractError("actor view changed immediately before output promotion")
    if input_commitment(view_root, opened) != expected_input_commitment:
        raise ContractError("actor input commitment changed before output promotion")
    source_identities = {
        value: file_identity(view_root / safe_relative(value, "actor output"))
        for value in outputs
    }
    cleanup = rollback_contract()
    created_files: list[
        tuple[Path, tuple[int, int, int, int, str]]
    ] = []
    created_directories: list[tuple[Path, tuple[int, int]]] = []
    try:
        for value in outputs:
            relative = safe_relative(value, "actor output")
            destination = round_root / relative
            current = round_root
            for part in relative.parent.parts:
                current = current / part
                if os.path.lexists(current):
                    if current not in {
                        path for path, _identity in created_directories
                    }:
                        raise ContractError(
                            "refusing to reuse pre-existing actor-output directory: "
                            f"{current}"
                        )
                    require_directory(current, f"output destination directory {current}")
                else:
                    current.mkdir()
                    metadata = os.lstat(current)
                    created_directories.append(
                        (current, (int(metadata.st_dev), int(metadata.st_ino)))
                    )
            _digest, destination_identity = copy_file_exclusive_with_identity(
                view_root / relative, destination
            )
            created_files.append((destination, destination_identity))
        for value, identity in source_identities.items():
            relative = safe_relative(value, "actor output")
            if file_identity(view_root / relative) != identity:
                raise ContractError(f"actor output changed during promotion: {value}")
            if file_identity(round_root / relative)[4] != identity[4]:
                raise ContractError(f"promoted output hash mismatch: {value}")
        if input_commitment(view_root, opened) != expected_input_commitment:
            raise ContractError("actor input commitment changed during output promotion")
        if (
            closed_view_snapshot(view_root, expected_view_files, validator)
            != expected_view_snapshot
        ):
            raise ContractError("actor view changed during output promotion")

        # Any destination directory created by this promotion is actor-owned
        # and must be an exact subtree. Unknown children are rejected without
        # descending into them by ``closed_view_snapshot``.
        top_created_directories = [
            directory
            for directory, _identity in created_directories
            if directory.parent == round_root
        ]
        for directory in top_created_directories:
            relative_outputs = [
                (round_root / safe_relative(value, "actor output"))
                .relative_to(directory)
                .as_posix()
                for value in outputs
                if physically_within(
                    round_root / safe_relative(value, "actor output"), directory
                )
            ]
            closed_view_snapshot(directory, relative_outputs, validator)
        for value, identity in source_identities.items():
            relative = safe_relative(value, "actor output")
            if file_identity(round_root / relative)[4] != identity[4]:
                raise ContractError(f"promoted output changed before commit: {value}")
    except Exception as promotion_exc:
        cleanup_errors: list[str] = []
        for destination, identity in reversed(created_files):
            try:
                cleanup.unlink_created_file_if_unchanged(
                    destination,
                    cleanup.FileIdentity(*identity),
                    "Stage-O promoted output",
                )
            except Exception as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        for directory, identity in reversed(created_directories):
            try:
                cleanup.rmdir_created_directory_if_unchanged(
                    directory,
                    cleanup.DirectoryIdentity(*identity),
                    "Stage-O promoted output directory",
                )
            except Exception as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        if cleanup_errors:
            raise ContractError(
                f"actor-output promotion failed: {promotion_exc}; rollback failed "
                "closed and preserved one or more current objects: "
                + "; ".join(cleanup_errors)
            ) from promotion_exc
        raise
    return {value: identity[4] for value, identity in source_identities.items()}


def command_promote_actor(args: argparse.Namespace) -> dict[str, Any]:
    actor = args.actor.upper()
    if GENERAL_ACTOR_RE.fullmatch(actor) is None:
        raise ContractError("actor promotion supports only P, R1..R5, or AI")
    round_root = require_round_root(args.round_root)
    view_root = require_directory(args.view_root, "actor view")
    views_root = require_directory(round_root.parent / "views", "views root")
    if view_root.parent != views_root or view_root.name != actor:
        raise ContractError(
            "actor view must be the exact actor-ID direct child of run/views"
        )
    if boundaries_overlap(view_root, round_root):
        raise ContractError("actor view and finalized round must not overlap")
    expected_commitment = str(args.expected_input_commitment_sha256).strip().upper()
    if HEX64_RE.fullmatch(expected_commitment) is None:
        raise ContractError("expected input commitment must be one 64-hex SHA-256")
    process = read_json_object(
        view_root / "00-process-parameters.json", "actor process envelope"
    )
    opened, _instructions = canonical_general_actor_inputs(
        view_root, process, actor
    )
    outputs = general_actor_outputs(process, actor)
    if input_commitment(view_root, opened) != expected_commitment:
        raise ContractError(f"{actor} input commitment changed before scoped gate")
    launch_receipt = validate_launch_for_promotion(
        actor=actor,
        view_root=view_root,
        round_root=round_root,
        process=process,
        input_commitment_sha256=expected_commitment,
        launch_record_path=args.launch_record,
        expected_launch_id=args.expected_launch_id,
        expected_process_seal_sha256=args.expected_process_seal_sha256,
        expected_launch_record_sha256=args.expected_launch_record_sha256,
        expected_output_commitment_sha256=args.expected_output_commitment_sha256,
    )
    validator = load_module(
        SCRIPT_ROOT / "validate_review_bundle.py",
        "thesis_review_stage_o_general_closure",
    )
    before_tree = closed_view_snapshot(
        view_root, [*opened, *outputs], validator
    )
    gate_command = run_general_scoped_gate(actor, view_root, process)
    if input_commitment(view_root, opened) != expected_commitment:
        raise ContractError(f"{actor} input commitment changed across scoped gate")
    after_tree = closed_view_snapshot(view_root, [*opened, *outputs], validator)
    if after_tree != before_tree:
        raise ContractError(f"{actor} actor-view tree changed across scoped gate")
    output_hashes = copy_output_set(
        view_root,
        round_root,
        outputs,
        opened=opened,
        expected_view_snapshot=after_tree,
        expected_input_commitment=expected_commitment,
        validator=validator,
    )
    return {
        "operation": "promote-actor-output",
        "actor": actor,
        "round_root": str(round_root),
        "view_root": str(view_root),
        "input_commitment_sha256": expected_commitment,
        "outputs": output_hashes,
        "scoped_gate_command": gate_command,
        "launch_id": launch_receipt["launch_id"],
        "launch_record": launch_receipt["launch_record"],
        "status": "promoted",
    }


def command_stage_clean(args: argparse.Namespace) -> dict[str, Any]:
    actor = args.actor.upper()
    if actor not in {"C", "S"}:
        raise ContractError("clean actor view is supported only for C or S")
    skill_root = require_directory(args.skill_root, "skill root")
    round_root = require_round_root(args.round_root)
    view_root = absolute_local_path(args.view_root, "clean actor view", must_exist=False)
    views_root = require_directory(round_root.parent / "views", "views root")
    if view_root.parent != views_root or view_root.name != actor:
        raise ContractError(
            "clean actor view must be the exact C or S direct child of run/views"
        )
    process = read_json_object(round_root / "00-process-parameters.json", "process envelope")
    opened, data_inputs, instruction_inputs = canonical_clean_actor_inputs(
        round_root, process, actor
    )
    # data_inputs is retained as an explicit partition check.  It must account
    # for every non-instruction canonical input; no hidden page-render or helper
    # tree is appended.  C receives only helpers explicitly projected to C.
    if set(opened) != set(data_inputs) | set(instruction_inputs):
        raise ContractError(f"canonical {actor} input partition is not closed")
    hashes = publish_clean_actor_view(
        round_root, skill_root, view_root, actor, opened, instruction_inputs
    )
    commitment = input_commitment(view_root, opened)
    mapping = {
        item: str(view_root / safe_relative(item, item)) for item in opened
    }
    return {
        "operation": "stage-clean-view",
        "actor": actor,
        "view_root": str(view_root),
        "opened": opened,
        "path_mapping": mapping,
        "hashes": hashes,
        "input_commitment_sha256": commitment,
        "mechanical_extra_trees": [],
    }


def run_scoped_gate(actor: str, view_root: Path) -> list[str]:
    script = (
        view_root / "rules" / "scripts" / "validate_chair_output.py"
        if actor == "C"
        else view_root / "rules" / "scripts" / "validate_summary_output.py"
    )
    require_regular(script, f"{actor} scoped validator")
    command = [sys.executable, "-B", str(script), str(view_root)]
    if actor == "C":
        process = read_json_object(
            view_root / "00-process-parameters.json", "Chair process envelope"
        )
        opened, _data, _instructions = canonical_clean_actor_inputs(
            view_root, process, "C"
        )
        for relative in opened:
            if relative.startswith("helpers/"):
                command.extend(["--helper-input", relative])
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    import subprocess

    completed = subprocess.run(
        command,
        cwd=str(view_root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = completed.stdout.splitlines()
    first = next((line.strip() for line in lines if line.strip()), "")
    if completed.returncode != 0 or first != "PASS":
        raise ContractError(
            f"{actor} scoped gate failed before promotion: exit={completed.returncode}; "
            f"first={first!r}; tail={completed.stdout[-2000:]!r}"
        )
    return command


def command_promote_clean(args: argparse.Namespace) -> dict[str, Any]:
    actor = args.actor.upper()
    if actor not in {"C", "S"}:
        raise ContractError("clean promotion is supported only for C or S")
    view_root = require_directory(args.view_root, "clean actor view")
    round_root = require_round_root(args.round_root)
    views_root = require_directory(round_root.parent / "views", "views root")
    if view_root.parent != views_root or view_root.name != actor:
        raise ContractError(
            "clean actor view must be the exact C or S direct child of run/views"
        )
    if boundaries_overlap(view_root, round_root):
        raise ContractError("clean actor view and finalized round must not overlap")
    expected_commitment = str(args.expected_input_commitment_sha256).strip().upper()
    if HEX64_RE.fullmatch(expected_commitment) is None:
        raise ContractError("expected input commitment must be one 64-hex SHA-256")
    process = read_json_object(
        view_root / "00-process-parameters.json", "clean actor process envelope"
    )
    opened, _data_inputs, _instruction_inputs = canonical_clean_actor_inputs(
        view_root, process, actor
    )
    if input_commitment(view_root, opened) != expected_commitment:
        raise ContractError(
            f"{actor} private-view input commitment changed before scoped gate"
        )
    launch_receipt = validate_launch_for_promotion(
        actor=actor,
        view_root=view_root,
        round_root=round_root,
        process=process,
        input_commitment_sha256=expected_commitment,
        launch_record_path=args.launch_record,
        expected_launch_id=args.expected_launch_id,
        expected_process_seal_sha256=args.expected_process_seal_sha256,
        expected_launch_record_sha256=args.expected_launch_record_sha256,
        expected_output_commitment_sha256=args.expected_output_commitment_sha256,
    )
    validator = load_module(
        SCRIPT_ROOT / "validate_review_bundle.py",
        "thesis_review_stage_o_clean_closure",
    )
    outputs = list(C_OUTPUTS if actor == "C" else S_OUTPUTS)
    expected_view_files = [*opened, *outputs]
    before_tree = closed_view_snapshot(
        view_root, expected_view_files, validator
    )
    gate_command = run_scoped_gate(actor, view_root)
    if input_commitment(view_root, opened) != expected_commitment:
        raise ContractError(
            f"{actor} private-view input commitment changed across scoped gate"
        )
    after_tree = closed_view_snapshot(
        view_root, expected_view_files, validator
    )
    if after_tree != before_tree:
        raise ContractError(f"{actor} private view changed across scoped gate")
    output_hashes = copy_output_set(
        view_root,
        round_root,
        outputs,
        opened=opened,
        expected_view_snapshot=after_tree,
        expected_input_commitment=expected_commitment,
        validator=validator,
    )
    return {
        "operation": "promote-clean-output",
        "actor": actor,
        "round_root": str(round_root),
        "view_root": str(view_root),
        "outputs": output_hashes,
        "input_commitment_sha256": expected_commitment,
        "scoped_gate_command": gate_command,
        "launch_id": launch_receipt["launch_id"],
        "launch_record": launch_receipt["launch_record"],
        "status": "promoted",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scratch = subparsers.add_parser("init-r-scratch")
    scratch.add_argument("--process", type=Path, required=True)
    scratch.add_argument("--round-root", type=Path, required=True)
    scratch.add_argument("--actor", required=True)
    scratch.add_argument("--scratch-parent", type=Path, required=True)

    stage = subparsers.add_parser("stage-round-inputs")
    stage.add_argument("--skill-root", type=Path, default=SKILL_ROOT)
    stage.add_argument("--round-root", type=Path, required=True)

    retire = subparsers.add_parser("retire-round-inputs")
    retire.add_argument("--skill-root", type=Path, default=SKILL_ROOT)
    retire.add_argument("--round-root", type=Path, required=True)
    retire.add_argument("--destination", type=Path, required=True)

    stage_sa = subparsers.add_parser("stage-sa-view")
    stage_sa.add_argument("--round-root", type=Path, required=True)
    stage_sa.add_argument("--view-root", type=Path, required=True)
    stage_sa.add_argument("--target", required=True)

    stage_actor = subparsers.add_parser("stage-actor-view")
    stage_actor.add_argument("--skill-root", type=Path, default=SKILL_ROOT)
    stage_actor.add_argument("--round-root", type=Path, required=True)
    stage_actor.add_argument("--view-root", type=Path, required=True)
    stage_actor.add_argument("--actor", required=True)

    stage_clean = subparsers.add_parser("stage-clean-view")
    stage_clean.add_argument("--skill-root", type=Path, default=SKILL_ROOT)
    stage_clean.add_argument("--round-root", type=Path, required=True)
    stage_clean.add_argument("--view-root", type=Path, required=True)
    stage_clean.add_argument("--actor", choices=("C", "S"), required=True)

    promote = subparsers.add_parser("promote-clean-output")
    promote.add_argument("--round-root", type=Path, required=True)
    promote.add_argument("--view-root", type=Path, required=True)
    promote.add_argument("--expected-input-commitment-sha256", required=True)
    promote.add_argument("--launch-record", type=Path, required=True)
    promote.add_argument("--expected-launch-id", required=True)
    promote.add_argument("--expected-process-seal-sha256", required=True)
    promote.add_argument("--expected-launch-record-sha256", required=True)
    promote.add_argument("--expected-output-commitment-sha256", required=True)
    promote.add_argument("--actor", choices=("C", "S"), required=True)

    promote_actor = subparsers.add_parser("promote-actor-output")
    promote_actor.add_argument("--round-root", type=Path, required=True)
    promote_actor.add_argument("--view-root", type=Path, required=True)
    promote_actor.add_argument("--expected-input-commitment-sha256", required=True)
    promote_actor.add_argument("--launch-record", type=Path, required=True)
    promote_actor.add_argument("--expected-launch-id", required=True)
    promote_actor.add_argument("--expected-process-seal-sha256", required=True)
    promote_actor.add_argument("--expected-launch-record-sha256", required=True)
    promote_actor.add_argument("--expected-output-commitment-sha256", required=True)
    promote_actor.add_argument("--actor", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    handlers = {
        "init-r-scratch": command_init_scratch,
        "stage-round-inputs": command_stage_round,
        "retire-round-inputs": command_retire_round,
        "stage-sa-view": command_stage_sa,
        "stage-actor-view": command_stage_actor,
        "stage-clean-view": command_stage_clean,
        "promote-clean-output": command_promote_clean,
        "promote-actor-output": command_promote_actor,
    }
    try:
        result = handlers[arguments.command](arguments)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: filesystem operation failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Imported production builders use their own ContractError classes.
        # Convert every such fail-closed contract failure into the same stable
        # CLI outcome instead of leaking an uncontrolled traceback.
        print(f"ERROR: Stage-O operation failed safely: {exc}", file=sys.stderr)
        return 2
    print("OK")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
