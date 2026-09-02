#!/usr/bin/env python3
"""Bind a manual Stage-O prompt body to the no-redelegation actor contract.

Stage R and Stage SA have dedicated prompt builders.  This helper covers the
remaining manually authored operational prompts (P, Hxx, AI, C, S, and V) so
they cannot silently omit or contradict the process-bound actor requirement.
It performs no thesis work and reads no round artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from actor_prompt_contract import (  # noqa: E402
    CONTRACT_BEGIN,
    CONTRACT_END,
    ActorContractError,
    find_role_body_control_language,
    render_bound_actor_contract,
)

SCHEMA = "thesis-review-bound-actor-operational-prompt-v2"
ACTOR_RE = re.compile(r"(?:P|H(?:0[1-9]|[1-9][0-9])|AI|C|S|V)\Z")
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")


class ContractError(RuntimeError):
    """Fail-closed error for general operational-prompt construction."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def absolute_no_alias(path: Path, label: str, *, must_exist: bool) -> Path:
    """Accept one absolute control path without symlink/reparse traversal."""

    candidate = Path(path)
    if not candidate.is_absolute():
        raise ContractError(f"{label} must be absolute")
    spelling = os.fspath(candidate).replace("/", "\\")
    if os.name == "nt" and spelling.startswith("\\\\"):
        raise ContractError(f"{label} must not use a UNC/device namespace")
    if os.name == "nt" and any(":" in part for part in candidate.parts[1:]):
        raise ContractError(f"{label} must not use an NTFS alternate data stream")
    if any(part == ".." for part in candidate.parts):
        raise ContractError(f"{label} must not contain lexical parent traversal")
    normalized = Path(os.path.abspath(os.fspath(candidate)))
    current = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ContractError(f"cannot inspect {label} component: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            raise ContractError(
                f"{label} traverses a symlink/reparse component: {current}"
            )
    if must_exist and not os.path.lexists(normalized):
        raise ContractError(f"{label} is missing: {normalized}")
    return normalized


def require_actor(value: str) -> str:
    actor = value.strip().upper()
    if not ACTOR_RE.fullmatch(actor):
        raise ContractError(
            "actor must be one of P, H01..H99, AI, C, S, or V; "
            "R and SA actors require their dedicated production builders"
        )
    return actor


def canonical_contract(actor: str) -> str:
    try:
        return render_bound_actor_contract(actor)
    except ActorContractError as exc:  # pragma: no cover - require_actor owns CLI UX
        raise ContractError(str(exc)) from exc


def validate_body(text: str) -> str:
    if not text or not text.strip():
        raise ContractError("prompt body must contain role-specific instructions")
    if text.startswith("\ufeff"):
        raise ContractError("prompt body must not contain a UTF-8 BOM")
    if "\r" in text:
        raise ContractError("prompt body must use LF line endings")
    if CONTRACT_BEGIN in text or CONTRACT_END in text:
        raise ContractError("prompt body must not contain bound-contract sentinels")
    conflict = find_role_body_control_language(text)
    if conflict is not None:
        category, excerpt = conflict
        raise ContractError(
            "prompt body contains actor-launch/delegation language reserved "
            f"to the canonical contract ({category}): {excerpt!r}"
        )
    return text.rstrip("\n") + "\n"


def render_prompt(actor: str, body: str) -> str:
    canonical_actor = require_actor(actor)
    canonical_body = validate_body(body)
    return canonical_contract(canonical_actor) + "\n\n" + canonical_body


def require_regular_single_link(path: Path, label: str) -> Path:
    canonical = absolute_no_alias(path, label, must_exist=True)
    try:
        original_metadata = canonical.lstat()
        if canonical.is_symlink() or bool(
            getattr(original_metadata, "st_file_attributes", 0) & 0x400
        ):
            raise ContractError(f"{label} must not be a symlink/reparse point")
        metadata = canonical.stat()
    except OSError as exc:
        raise ContractError(f"cannot resolve {label} {path}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ContractError(f"{label} must be a regular non-symlink file")
    if int(metadata.st_nlink) != 1:
        raise ContractError(f"{label} must be a single-link regular file")
    return canonical


def build(actor: str, body_path: Path, output_path: Path) -> dict[str, str | int]:
    canonical_actor = require_actor(actor)
    source = require_regular_single_link(body_path, "prompt body")
    try:
        body_bytes = source.read_bytes()
        body = body_bytes.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read prompt body as strict UTF-8: {exc}") from exc

    output = absolute_no_alias(output_path, "bound prompt output", must_exist=False)
    if output == source:
        raise ContractError("prompt body and output must be different files")
    if output.exists():
        raise ContractError(f"refusing to overwrite existing prompt: {output}")
    parent = absolute_no_alias(output.parent, "output parent", must_exist=True)
    raw_parent_metadata = parent.lstat() if parent.exists() else None
    if (
        raw_parent_metadata is None
        or parent.is_symlink()
        or bool(getattr(raw_parent_metadata, "st_file_attributes", 0) & 0x400)
        or not parent.exists()
        or not parent.is_dir()
    ):
        raise ContractError("output parent must be an existing non-symlink directory")

    prompt_bytes = render_prompt(canonical_actor, body).encode("utf-8")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(prompt_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ContractError(f"cannot publish bound operational prompt: {exc}") from exc

    return {
        "schema": SCHEMA,
        "actor": canonical_actor,
        "body_file": str(source),
        "body_sha256": sha256_bytes(body_bytes),
        "prompt_file": str(output),
        "prompt_sha256": sha256_bytes(prompt_bytes),
        "prompt_bytes": len(prompt_bytes),
        "operation": "build",
    }


def require_sha256(value: str, label: str) -> str:
    canonical = str(value).strip().upper()
    if HEX64_RE.fullmatch(canonical) is None:
        raise ContractError(f"{label} must be one 64-hex SHA-256")
    return canonical


def verify(
    actor: str,
    body_path: Path,
    output_path: Path,
    expected_body_sha256: str,
    expected_prompt_sha256: str,
) -> dict[str, str | int]:
    """Reconstruct and byte-verify an already published operational prompt."""

    canonical_actor = require_actor(actor)
    source = require_regular_single_link(body_path, "prompt body")
    prompt_file = require_regular_single_link(output_path, "bound prompt")
    if source == prompt_file:
        raise ContractError("prompt body and bound prompt must be different files")
    try:
        body_bytes = source.read_bytes()
        body = body_bytes.decode("utf-8", errors="strict")
        actual_prompt = prompt_file.read_bytes()
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read prompt inputs as strict UTF-8: {exc}") from exc
    actual_body_sha256 = sha256_bytes(body_bytes)
    expected_body_sha256 = require_sha256(
        expected_body_sha256, "expected build-time body SHA-256"
    )
    if actual_body_sha256 != expected_body_sha256:
        raise ContractError(
            "prompt body no longer matches the externally retained build-time "
            "SHA-256"
        )
    expected_prompt = render_prompt(canonical_actor, body).encode("utf-8")
    if actual_prompt != expected_prompt:
        raise ContractError(
            "bound prompt bytes do not equal the canonical reconstruction for "
            f"actor {canonical_actor}"
        )
    actual_prompt_sha256 = sha256_bytes(actual_prompt)
    expected_prompt_sha256 = require_sha256(
        expected_prompt_sha256, "expected build-time prompt SHA-256"
    )
    if actual_prompt_sha256 != expected_prompt_sha256:
        raise ContractError(
            "bound prompt no longer matches the externally retained build-time "
            "SHA-256"
        )
    return {
        "schema": SCHEMA,
        "actor": canonical_actor,
        "body_file": str(source),
        "body_sha256": actual_body_sha256,
        "prompt_file": str(prompt_file),
        "prompt_sha256": actual_prompt_sha256,
        "prompt_bytes": len(actual_prompt),
        "operation": "verify",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("build", "verify"), default="build")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-body-sha256")
    parser.add_argument("--expected-prompt-sha256")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if arguments.mode == "build":
            if (
                arguments.expected_body_sha256 is not None
                or arguments.expected_prompt_sha256 is not None
            ):
                raise ContractError(
                    "expected build-time hashes are valid only with --mode verify"
                )
            metadata = build(arguments.actor, arguments.body, arguments.output)
            result = "BOUND"
        else:
            if (
                arguments.expected_body_sha256 is None
                or arguments.expected_prompt_sha256 is None
            ):
                raise ContractError(
                    "--mode verify requires --expected-body-sha256 and "
                    "--expected-prompt-sha256"
                )
            metadata = verify(
                arguments.actor,
                arguments.body,
                arguments.output,
                arguments.expected_body_sha256,
                arguments.expected_prompt_sha256,
            )
            result = "VERIFIED"
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(result)
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
