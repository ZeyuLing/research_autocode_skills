#!/usr/bin/env python3
"""Authoritative transactional Stage-O runner for one thesis-review retry.

This module is the only production entry point for Stage-O after the final
process envelope has been sealed.  Its authority is an append-only canonical
JSON event chain under ``<run>/orchestration/stage-o/events``.  Every mutating
operation uses a caller-visible compare-and-swap transition token and is
recorded as ``*_BEGIN`` followed by ``*_COMMIT``.  A begun operation that
raises is quarantined through :mod:`manage_review_retry`; a crash that leaves a
dangling BEGIN permits only explicit quarantine.

The runner deliberately has no adopt/repair operation.  H and V are disabled
in this first production schema.  Promotion never accepts hashes from the
caller: phase preparation freezes each actor's input commitment, phase launch
freezes each v3 launch-record/output commitment, and phase promotion consumes
only those recorded commitments.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable


SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

EVENT_SCHEMA = "thesis-review-stage-o-event-v1"
STATE_SCHEMA = "thesis-review-stage-o-state-v1"
LAUNCH_SCHEMA = "thesis-review-actor-launch-v3"
CANONICAL_PROMPT_SCHEMA = "thesis-review-canonical-actor-operational-prompt-v1"
REVIEWER_PROMPT_SCHEMA = "thesis-review-stage-r-operational-prompt-v4"
SEMANTIC_PROMPT_SCHEMA = "thesis-review-semantic-acceptance-prompt-v6"
ZERO_HASH = "0" * 64
HEX64_RE = re.compile(r"[0-9A-F]{64}\Z")
EVENT_NAME_RE = re.compile(r"E([0-9]{8})\.json\Z")
ACTOR_RE = re.compile(r"(?:P|R[1-5]|AI|SA-(?:R[1-5]|AI)|C|S)\Z")
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
PINNED_SCRIPT_NAMES = (
    "stage_o_runner.py",
    "actor_prompt_contract.py",
    "manage_review_retry.py",
    "manage_stage_o_workspace.py",
    "launch_review_actor.py",
    "validate_actor_transport.py",
    "build_canonical_actor_prompt.py",
    "build_reviewer_prompt.py",
    "build_semantic_acceptance_prompt.py",
    "materialize_semantic_acceptance_gate.py",
    "validate_semantic_acceptance_output.py",
    "validate_review_bundle.py",
)

# These operations consume a round that already contains one or more actor
# output sets.  Re-authenticate every prior promotion only after the operation
# BEGIN is durable so any drift takes the normal whole-retry quarantine path.
PROMOTED_OUTPUT_ANCHOR_BASES = frozenset(
    {
        "PREPARE_ACTOR",
        "PREPARE_PHASE",
        "CLOSE_SA_SET",
        "RETIRE_RULES",
        "FINALIZE",
    }
)

BEGIN_KINDS = {
    "BOOTSTRAP_BEGIN",
    "PREPARE_ACTOR_BEGIN",
    "LAUNCH_ACTOR_BEGIN",
    "PROMOTE_ACTOR_BEGIN",
    "PREPARE_PHASE_BEGIN",
    "LAUNCH_PHASE_BEGIN",
    "PROMOTE_PHASE_BEGIN",
    "CLOSE_SA_SET_BEGIN",
    "RETIRE_RULES_BEGIN",
    "FINALIZE_BEGIN",
    "AUTHORIZE_DELIVERY_BEGIN",
    "QUARANTINE_BEGIN",
}
COMMIT_KINDS = {item.replace("_BEGIN", "_COMMIT") for item in BEGIN_KINDS}
ALL_KINDS = BEGIN_KINDS | COMMIT_KINDS


class RunnerError(RuntimeError):
    """Fail-closed Stage-O orchestration error."""


class CommitUncertainError(RunnerError):
    """An event may have been created but its durable commit is uncertain."""


def _load_module(filename: str, module_name: str) -> Any:
    path = SCRIPT_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RunnerError(f"cannot load Stage-O primitive: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_bound_skill_root(value: Path) -> Path:
    """Bind ``--skill-root`` to the skill that owns this running runner.

    Without this identity check, a runner loaded from one checkout could hash
    and stage a second checkout while continuing to execute primitives beside
    its own ``__file__``.  The event ledger would then name the wrong
    toolchain.
    """

    requested = require_directory(
        absolute_path(value, "skill root", must_exist=True), "skill root"
    )
    running_root = require_directory(
        absolute_path(SKILL_ROOT, "running runner skill root", must_exist=True),
        "running runner skill root",
    )
    if os.path.normcase(os.path.normpath(str(requested))) != os.path.normcase(
        os.path.normpath(str(running_root))
    ):
        raise RunnerError(
            "--skill-root must be the canonical skill root that owns the "
            "running stage_o_runner.py"
        )

    running_script = require_regular(
        absolute_path(Path(__file__), "running stage_o_runner.py", must_exist=True),
        "running stage_o_runner.py",
    )
    bound_script = require_regular(
        requested / "scripts" / "stage_o_runner.py", "bound stage_o_runner.py"
    )
    if os.path.normcase(os.path.normpath(str(running_script))) != os.path.normcase(
        os.path.normpath(str(bound_script))
    ):
        raise RunnerError(
            "running stage_o_runner.py is not the script under the bound skill root"
        )
    return requested


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RunnerError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest().upper()


def require_hash(value: object, label: str) -> str:
    digest = str(value).strip().upper()
    if HEX64_RE.fullmatch(digest) is None:
        raise RunnerError(f"{label} must be one 64-hex SHA-256")
    return digest


def canonical_uuid(value: object, label: str) -> str:
    text = str(value).strip().lower()
    try:
        parsed = str(uuid.UUID(text))
    except (ValueError, AttributeError) as exc:
        raise RunnerError(f"{label} must be a canonical UUID") from exc
    if parsed != text or UUID_RE.fullmatch(text) is None:
        raise RunnerError(f"{label} must be a canonical UUID")
    return text


def strict_object_from_bytes(value: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise RunnerError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = item
        return result

    try:
        decoded = value.decode("utf-8", errors="strict")
        parsed = json.loads(decoded, object_pairs_hook=pairs)
    except RunnerError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RunnerError(f"{label} must be one JSON object")
    return parsed


def require_regular(path: Path, label: str) -> Path:
    try:
        lexical = os.lstat(path)
        metadata = path.stat()
    except OSError as exc:
        raise RunnerError(f"cannot inspect {label}: {exc}") from exc
    if (
        stat.S_ISLNK(lexical.st_mode)
        or bool(getattr(lexical, "st_file_attributes", 0) & 0x400)
        or not stat.S_ISREG(metadata.st_mode)
        or int(metadata.st_nlink) != 1
    ):
        raise RunnerError(f"{label} must be a single-link regular non-reparse file")
    return path


def require_directory(path: Path, label: str) -> Path:
    try:
        lexical = os.lstat(path)
        metadata = path.stat()
    except OSError as exc:
        raise RunnerError(f"cannot inspect {label}: {exc}") from exc
    if (
        stat.S_ISLNK(lexical.st_mode)
        or bool(getattr(lexical, "st_file_attributes", 0) & 0x400)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise RunnerError(f"{label} must be a non-reparse directory")
    return path


def absolute_path(path: Path, label: str, *, must_exist: bool) -> Path:
    value = Path(path)
    if not value.is_absolute() or any(part == ".." for part in value.parts):
        raise RunnerError(f"{label} must be a canonical absolute path")
    raw = os.fspath(value)
    if os.name == "nt":
        spelling = raw.replace("/", "\\")
        if spelling.startswith("\\\\") or spelling.startswith("\\?\\") or spelling.startswith("\\.\\"):
            raise RunnerError(f"{label} must not use a UNC/device namespace")
        drive, tail = os.path.splitdrive(raw)
        if not re.fullmatch(r"[A-Za-z]:", drive) or ":" in tail:
            raise RunnerError(f"{label} must use one local drive and no NTFS stream")
    normalized = Path(os.path.abspath(raw))
    if os.path.normcase(os.path.normpath(raw)) != os.path.normcase(
        os.path.normpath(str(normalized))
    ):
        raise RunnerError(f"{label} must already use canonical absolute spelling")
    current = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            raise RunnerError(f"{label} traverses a symlink/reparse component")
    if must_exist and not os.path.lexists(normalized):
        raise RunnerError(f"{label} does not exist: {normalized}")
    return normalized


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def boundaries_overlap(first: Path, second: Path) -> bool:
    return first == second or is_within(first, second) or is_within(second, first)


def read_strict_object(path: Path, label: str) -> dict[str, Any]:
    require_regular(path, label)
    before = path.stat()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RunnerError(f"cannot read {label}: {exc}") from exc
    after = path.stat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_nlink,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_nlink,
    )
    if identity_before != identity_after:
        raise RunnerError(f"{label} changed while it was read")
    return strict_object_from_bytes(payload, label)


def stable_regular_bytes(path: Path, label: str) -> bytes:
    require_regular(path, label)
    before = path.stat()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RunnerError(f"cannot read {label}: {exc}") from exc
    after = path.stat()
    projection = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_nlink,
    )
    if projection(before) != projection(after):
        raise RunnerError(f"{label} changed while it was read")
    return payload


def closed_tree_commitment(root: Path) -> str:
    """Hash the complete relative file/dir topology and all regular-file bytes."""

    require_directory(root, "committed tree root")
    records: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise RunnerError(f"cannot enumerate committed tree {current}: {exc}") from exc
        for entry in entries:
            relative = entry.relative_to(root).as_posix()
            lexical = os.lstat(entry)
            if stat.S_ISLNK(lexical.st_mode) or bool(
                getattr(lexical, "st_file_attributes", 0) & 0x400
            ):
                raise RunnerError(f"committed tree contains link/reparse entry: {relative}")
            if stat.S_ISDIR(lexical.st_mode):
                records.append({"path": relative, "type": "directory"})
                stack.append(entry)
            elif stat.S_ISREG(lexical.st_mode) and int(lexical.st_nlink) == 1:
                records.append(
                    {
                        "path": relative,
                        "type": "file",
                        "size": int(lexical.st_size),
                        "sha256": sha256_file(entry),
                    }
                )
            else:
                raise RunnerError(f"committed tree contains unsafe entry: {relative}")
    records.sort(key=lambda item: (item["path"], item["type"]))
    return sha256_bytes(
        json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def actor_sequence(degree_level: str) -> list[str]:
    return [actor for phase in actor_phases(degree_level) for actor in phase]


def actor_phases(degree_level: str) -> list[list[str]]:
    if degree_level == "doctorate":
        reviewers = [f"R{index}" for index in range(1, 6)]
    elif degree_level == "masters":
        reviewers = [f"R{index}" for index in range(1, 4)]
    else:
        raise RunnerError("degree_level must be doctorate or masters")
    return [
        ["P"],
        [*reviewers, "AI"],
        [*(f"SA-{actor}" for actor in reviewers), "SA-AI"],
        ["C"],
        ["S"],
    ]


def _exact_keys(value: dict[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    actual = set(value)
    if actual != expected_set:
        raise RunnerError(
            f"{label} keys differ: missing={sorted(expected_set-actual)}, "
            f"extra={sorted(actual-expected_set)}"
        )


def initial_state() -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "bootstrapped": False,
        "event_count": 0,
        "transition_token": ZERO_HASH,
        "pending": None,
        "config": None,
        "actor_sequence": [],
        "phase_plan": [],
        "phase_index": 0,
        "next_actor_index": 0,
        "actors": {},
        "launched_receipts": [],
        "consumed_receipts": [],
        "sa_set_closed": False,
        "rules_retired": False,
        "finalized": False,
        "delivery_authorized": False,
        "quarantined": False,
        "quarantine_destination": None,
        "semantic_gate": None,
        "retirement": None,
        "validation": None,
        "delivery": None,
    }


def _require_actor_event(state: dict[str, Any], event: dict[str, Any]) -> str:
    actor = event.get("actor")
    if not isinstance(actor, str) or ACTOR_RE.fullmatch(actor) is None:
        raise RunnerError("actor event has invalid actor ID")
    if actor not in state["actors"]:
        raise RunnerError(f"actor {actor} is not in the degree-specific actor plan")
    return actor


def _current_actor(state: dict[str, Any]) -> str | None:
    phase = _current_phase_actors(state)
    if not phase:
        return None
    pending = [actor for actor in phase if state["actors"][actor]["phase"] != "PROMOTED"]
    return pending[0] if pending else None


def _current_phase_actors(state: dict[str, Any]) -> list[str]:
    index = int(state["phase_index"])
    phases = state["phase_plan"]
    return list(phases[index]) if index < len(phases) else []


def _actor_in_current_phase(state: dict[str, Any], actor: str) -> bool:
    return actor in _current_phase_actors(state)


def _require_singleton_phase_actor(
    state: dict[str, Any], actor: str, operation: str
) -> None:
    """Reject per-actor transitions for concurrent R/AI and SA phases."""

    current = _current_phase_actors(state)
    if current != [actor]:
        raise RunnerError(
            f"{operation} is permitted only for a singleton phase; "
            f"use the phase transaction for {current}"
        )


def _phase_all(state: dict[str, Any], phase: str) -> bool:
    actors = _current_phase_actors(state)
    return bool(actors) and all(state["actors"][actor]["phase"] == phase for actor in actors)


def _advance_completed_phase(state: dict[str, Any]) -> None:
    actors = _current_phase_actors(state)
    if not actors or not all(state["actors"][actor]["phase"] == "PROMOTED" for actor in actors):
        return
    if all(actor.startswith("SA-") for actor in actors):
        # The SA phase remains current until its aggregate hash gate closes.
        return
    state["phase_index"] += 1
    state["next_actor_index"] = sum(
        1 for actor in state["actor_sequence"] if state["actors"][actor]["phase"] == "PROMOTED"
    )


def _begin_pending(
    state: dict[str, Any], event: dict[str, Any], base: str, actor: str | None
) -> None:
    state["pending"] = {
        "base": base,
        "operation_id": event["operation_id"],
        "actor": actor,
        "begin_payload": copy.deepcopy(event["payload"]),
    }


def _require_matching_commit(
    state: dict[str, Any], event: dict[str, Any], base: str
) -> dict[str, Any]:
    pending = state.get("pending")
    if not isinstance(pending, dict):
        raise RunnerError(f"{base}_COMMIT has no matching BEGIN")
    if (
        pending.get("base") != base
        or pending.get("operation_id") != event.get("operation_id")
        or pending.get("actor") != event.get("actor")
    ):
        raise RunnerError(f"{base}_COMMIT does not match the pending BEGIN")
    return pending


def _validate_bootstrap_payload(payload: dict[str, Any]) -> None:
    _exact_keys(
        payload,
        (
            "run_root",
            "workspace",
            "round_root",
            "views_root",
            "orchestration_root",
            "skill_root",
            "control_root",
            "scratch_root",
            "retirement_root",
            "python_executable",
            "python_executable_sha256",
            "codex_executable",
            "codex_executable_sha256",
            "toolchain_sha256",
            "process_sha256",
            "process_seal_sha256",
            "degree_level",
            "actor_sequence",
            "prompt_plans",
        ),
        "BOOTSTRAP_BEGIN payload",
    )
    sequence = actor_sequence(str(payload["degree_level"]))
    if payload["actor_sequence"] != sequence:
        raise RunnerError("bootstrap actor sequence is not the canonical degree sequence")
    plans = payload["prompt_plans"]
    if not isinstance(plans, dict) or set(plans) != set(sequence):
        raise RunnerError("bootstrap prompt plan must contain exactly the actor sequence")
    require_hash(payload["process_sha256"], "bootstrap process SHA-256")
    require_hash(payload["process_seal_sha256"], "bootstrap process-seal SHA-256")
    require_hash(payload["python_executable_sha256"], "bootstrap Python SHA-256")
    require_hash(payload["codex_executable_sha256"], "bootstrap Codex SHA-256")
    toolchain = payload["toolchain_sha256"]
    if not isinstance(toolchain, dict) or set(toolchain) != set(PINNED_SCRIPT_NAMES):
        raise RunnerError("bootstrap toolchain map is not the closed production set")
    for name, digest in toolchain.items():
        require_hash(digest, f"bootstrap toolchain {name}")
    for actor, plan in plans.items():
        if not isinstance(plan, dict):
            raise RunnerError(f"prompt plan for {actor} must be an object")
        _exact_keys(
            plan,
            (
                "plan_path",
                "plan_sha256",
                "prompt_path",
                "prompt_sha256",
                "scratch_dir",
            ),
            f"prompt plan {actor}",
        )
        require_hash(plan["plan_sha256"], f"{actor} prompt-plan SHA-256")
        require_hash(plan["prompt_sha256"], f"{actor} prompt SHA-256")
        if actor.startswith("SA-"):
            if plan["scratch_dir"] is not None:
                raise RunnerError("SA scratch must be allocated by the runner")
        elif not isinstance(plan["scratch_dir"], str) or not plan["scratch_dir"]:
            raise RunnerError(f"{actor} prompt plan must bind its existing empty scratch")


def reduce_event(
    state_value: dict[str, Any], event: dict[str, Any], event_sha256: str
) -> dict[str, Any]:
    """Pure, deterministic reducer for one already-authenticated event."""

    state = copy.deepcopy(state_value)
    _exact_keys(
        event,
        (
            "schema",
            "sequence",
            "kind",
            "operation_id",
            "actor",
            "expected_transition_token",
            "previous_event_sha256",
            "payload",
        ),
        "Stage-O event",
    )
    if event["schema"] != EVENT_SCHEMA:
        raise RunnerError("unsupported Stage-O event schema")
    if not isinstance(event["sequence"], int) or isinstance(event["sequence"], bool):
        raise RunnerError("event sequence must be an integer")
    if event["sequence"] != state["event_count"] + 1:
        raise RunnerError("event sequence is not contiguous")
    kind = event["kind"]
    if kind not in ALL_KINDS:
        raise RunnerError(f"unsupported Stage-O event kind: {kind!r}")
    canonical_uuid(event["operation_id"], "event operation_id")
    expected_token = require_hash(
        event["expected_transition_token"], "event expected transition token"
    )
    previous = require_hash(event["previous_event_sha256"], "event previous hash")
    if expected_token != state["transition_token"] or previous != state["transition_token"]:
        raise RunnerError("event compare-and-swap token/previous hash does not match the head")
    event_sha256 = require_hash(event_sha256, "event SHA-256")
    payload = event["payload"]
    if not isinstance(payload, dict):
        raise RunnerError("event payload must be an object")
    if state["quarantined"]:
        raise RunnerError("no event is permitted after quarantine commit")

    pending = state.get("pending")
    if pending is not None:
        matching_commit = kind == f"{pending['base']}_COMMIT"
        first_quarantine = kind == "QUARANTINE_BEGIN" and pending["base"] != "QUARANTINE"
        if not matching_commit and not first_quarantine:
            raise RunnerError(
                "dangling BEGIN permits only its exact COMMIT or one quarantine; "
                "a dangling quarantine cannot be adopted or restarted"
            )

    if kind == "BOOTSTRAP_BEGIN":
        if state["event_count"] != 0 or state["bootstrapped"] or pending is not None:
            raise RunnerError("bootstrap must be the first operation")
        if event["actor"] is not None:
            raise RunnerError("bootstrap event must not name an actor")
        _validate_bootstrap_payload(payload)
        state["config"] = copy.deepcopy(payload)
        state["actor_sequence"] = list(payload["actor_sequence"])
        state["phase_plan"] = actor_phases(str(payload["degree_level"]))
        state["actors"] = {
            actor: {"phase": "NOT_STARTED", "prepare": None, "launch": None, "promotion": None}
            for actor in state["actor_sequence"]
        }
        _begin_pending(state, event, "BOOTSTRAP", None)

    elif kind == "BOOTSTRAP_COMMIT":
        _require_matching_commit(state, event, "BOOTSTRAP")
        _exact_keys(payload, ("process_seal_verification", "staged_rule_files"), "BOOTSTRAP_COMMIT payload")
        if not isinstance(payload["process_seal_verification"], dict):
            raise RunnerError("bootstrap process-seal verification must be an object")
        if not isinstance(payload["staged_rule_files"], dict) or not payload["staged_rule_files"]:
            raise RunnerError("bootstrap must commit the staged rule-file map")
        state["bootstrapped"] = True
        state["pending"] = None

    elif kind == "PREPARE_PHASE_BEGIN":
        if not state["bootstrapped"]:
            raise RunnerError("phase preparation requires committed bootstrap")
        if event["actor"] is not None:
            raise RunnerError("phase preparation must not name one actor")
        _exact_keys(payload, ("allocations",), "PREPARE_PHASE_BEGIN payload")
        current = _current_phase_actors(state)
        allocations = payload["allocations"]
        if not current or not isinstance(allocations, dict) or set(allocations) != set(current):
            raise RunnerError("phase preparation allocations differ from the current phase")
        for actor in current:
            if state["actors"][actor]["phase"] != "NOT_STARTED":
                raise RunnerError("phase preparation requires every actor to be NOT_STARTED")
            allocation = allocations[actor]
            if not isinstance(allocation, dict):
                raise RunnerError(f"phase allocation for {actor} must be an object")
            _exact_keys(
                allocation,
                (
                    "outputs_absent",
                    "launch_id",
                    "jsonl_path",
                    "stderr_path",
                    "launch_record_path",
                    "scratch_dir",
                ),
                f"PREPARE_PHASE_BEGIN allocation {actor}",
            )
            if allocation["outputs_absent"] is not True:
                raise RunnerError(f"{actor} outputs must be absent before phase preparation")
            canonical_uuid(allocation["launch_id"], f"{actor} phase launch ID")
        _begin_pending(state, event, "PREPARE_PHASE", None)

    elif kind == "PREPARE_PHASE_COMMIT":
        _require_matching_commit(state, event, "PREPARE_PHASE")
        _exact_keys(payload, ("actors",), "PREPARE_PHASE_COMMIT payload")
        current = _current_phase_actors(state)
        committed = payload["actors"]
        allocations = state["pending"]["begin_payload"]["allocations"]
        if not isinstance(committed, dict) or set(committed) != set(current):
            raise RunnerError("prepared actor set differs from the current phase")
        for actor in current:
            prepared = committed[actor]
            if not isinstance(prepared, dict):
                raise RunnerError(f"prepared result for {actor} must be an object")
            _exact_keys(
                prepared,
                (
                    "view_root",
                    "opened",
                    "outputs",
                    "input_commitment_sha256",
                    "prompt_plan_sha256",
                    "prompt_path",
                    "prompt_sha256",
                    "prompt_verification_sha256",
                    "launch_id",
                    "jsonl_path",
                    "stderr_path",
                    "launch_record_path",
                    "scratch_dir",
                ),
                f"PREPARE_PHASE_COMMIT actor {actor}",
            )
            for key in (
                "input_commitment_sha256",
                "prompt_plan_sha256",
                "prompt_sha256",
                "prompt_verification_sha256",
            ):
                require_hash(prepared[key], f"{actor} prepared {key}")
            canonical_uuid(prepared["launch_id"], f"{actor} prepared launch ID")
            for key in (
                "launch_id",
                "jsonl_path",
                "stderr_path",
                "launch_record_path",
                "scratch_dir",
            ):
                if prepared[key] != allocations[actor][key]:
                    raise RunnerError(f"{actor} prepared {key} differs from BEGIN")
            if not isinstance(prepared["opened"], list) or not prepared["opened"]:
                raise RunnerError(f"{actor} prepared opened allowlist is empty")
            if not isinstance(prepared["outputs"], list) or not prepared["outputs"]:
                raise RunnerError(f"{actor} prepared output allowlist is empty")
            state["actors"][actor]["phase"] = "PREPARED"
            state["actors"][actor]["prepare"] = copy.deepcopy(prepared)
        state["pending"] = None

    elif kind == "LAUNCH_PHASE_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("phase launch must not name one actor")
        _exact_keys(payload, (), "LAUNCH_PHASE_BEGIN payload")
        if not _phase_all(state, "PREPARED"):
            raise RunnerError("phase launch requires every current actor to be prepared")
        _begin_pending(state, event, "LAUNCH_PHASE", None)

    elif kind == "LAUNCH_PHASE_COMMIT":
        _require_matching_commit(state, event, "LAUNCH_PHASE")
        _exact_keys(payload, ("receipts",), "LAUNCH_PHASE_COMMIT payload")
        current = _current_phase_actors(state)
        receipts = payload["receipts"]
        if not isinstance(receipts, dict) or set(receipts) != set(current):
            raise RunnerError("phase launch receipts differ from the current phase")
        new_hashes: set[str] = set()
        for actor in current:
            receipt = receipts[actor]
            if not isinstance(receipt, dict):
                raise RunnerError(f"launch receipt for {actor} must be an object")
            _exact_keys(
                receipt,
                (
                    "schema",
                    "launch_id",
                    "launch_record_path",
                    "launch_record_sha256",
                    "output_commitment_sha256",
                    "jsonl_sha256",
                    "result_sha256",
                ),
                f"LAUNCH_PHASE_COMMIT receipt {actor}",
            )
            prepared = state["actors"][actor]["prepare"]
            if receipt["schema"] != LAUNCH_SCHEMA:
                raise RunnerError(f"{actor} launch receipt is not v3")
            if receipt["launch_id"] != prepared["launch_id"] or receipt["launch_record_path"] != prepared["launch_record_path"]:
                raise RunnerError(f"{actor} launch receipt differs from its allocation")
            record_hash = require_hash(receipt["launch_record_sha256"], f"{actor} launch-record hash")
            require_hash(receipt["output_commitment_sha256"], f"{actor} output commitment")
            require_hash(receipt["jsonl_sha256"], f"{actor} JSONL hash")
            require_hash(receipt["result_sha256"], f"{actor} launcher-result hash")
            if record_hash in state["launched_receipts"] or record_hash in new_hashes:
                raise RunnerError("phase launch receipt hash is being replayed")
            new_hashes.add(record_hash)
        for actor in current:
            receipt = copy.deepcopy(receipts[actor])
            state["launched_receipts"].append(receipt["launch_record_sha256"])
            state["actors"][actor]["phase"] = "LAUNCHED"
            state["actors"][actor]["launch"] = receipt
        state["pending"] = None

    elif kind == "PROMOTE_PHASE_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("phase promotion must not name one actor")
        _exact_keys(payload, (), "PROMOTE_PHASE_BEGIN payload")
        if not _phase_all(state, "LAUNCHED"):
            raise RunnerError("phase promotion requires every current actor to be launched")
        for actor in _current_phase_actors(state):
            if state["actors"][actor]["launch"]["launch_record_sha256"] in state["consumed_receipts"]:
                raise RunnerError("phase promotion contains a consumed launch receipt")
        _begin_pending(state, event, "PROMOTE_PHASE", None)

    elif kind == "PROMOTE_PHASE_COMMIT":
        _require_matching_commit(state, event, "PROMOTE_PHASE")
        _exact_keys(payload, ("promotions",), "PROMOTE_PHASE_COMMIT payload")
        current = _current_phase_actors(state)
        promotions = payload["promotions"]
        if not isinstance(promotions, dict) or set(promotions) != set(current):
            raise RunnerError("phase promotions differ from the current phase")
        for actor in current:
            promotion = promotions[actor]
            if not isinstance(promotion, dict):
                raise RunnerError(f"promotion result for {actor} must be an object")
            _exact_keys(
                promotion,
                ("launch_record_sha256", "output_commitment_sha256", "promoted_outputs"),
                f"PROMOTE_PHASE_COMMIT actor {actor}",
            )
            launch = state["actors"][actor]["launch"]
            record_hash = require_hash(promotion["launch_record_sha256"], f"{actor} promoted record hash")
            output_hash = require_hash(promotion["output_commitment_sha256"], f"{actor} promoted output commitment")
            if record_hash != launch["launch_record_sha256"] or output_hash != launch["output_commitment_sha256"]:
                raise RunnerError(f"{actor} promotion differs from its frozen launch receipt")
            if record_hash in state["consumed_receipts"]:
                raise RunnerError("phase promotion reuses a consumed launch receipt")
            outputs = promotion["promoted_outputs"]
            if not isinstance(outputs, dict) or not outputs:
                raise RunnerError(f"{actor} promotion output map is empty")
            for path, digest in outputs.items():
                if not isinstance(path, str) or not path:
                    raise RunnerError(f"{actor} promoted output path is invalid")
                require_hash(digest, f"{actor} promoted output {path}")
        for actor in current:
            promotion = copy.deepcopy(promotions[actor])
            state["consumed_receipts"].append(promotion["launch_record_sha256"])
            state["actors"][actor]["phase"] = "PROMOTED"
            state["actors"][actor]["promotion"] = promotion
            state["next_actor_index"] += 1
        state["pending"] = None
        _advance_completed_phase(state)

    elif kind == "PREPARE_ACTOR_BEGIN":
        if not state["bootstrapped"]:
            raise RunnerError("actor preparation requires committed bootstrap")
        actor = _require_actor_event(state, event)
        _exact_keys(
            payload,
            (
                "outputs_absent",
                "launch_id",
                "jsonl_path",
                "stderr_path",
                "launch_record_path",
                "scratch_dir",
            ),
            "PREPARE_ACTOR_BEGIN payload",
        )
        if payload["outputs_absent"] is not True:
            raise RunnerError("actor outputs must be absent before preparation")
        if not _actor_in_current_phase(state, actor):
            raise RunnerError(
                f"actor preparation is outside the current phase: {_current_phase_actors(state)}"
            )
        _require_singleton_phase_actor(state, actor, "single-actor preparation")
        if state["actors"][actor]["phase"] != "NOT_STARTED":
            raise RunnerError(f"actor {actor} is not in NOT_STARTED phase")
        if actor == "C" and not state["sa_set_closed"]:
            raise RunnerError("Chair cannot prepare before the SA set is closed")
        canonical_uuid(payload["launch_id"], "preallocated launch ID")
        _begin_pending(state, event, "PREPARE_ACTOR", actor)

    elif kind == "PREPARE_ACTOR_COMMIT":
        pending = _require_matching_commit(state, event, "PREPARE_ACTOR")
        actor = str(pending["actor"])
        _exact_keys(
            payload,
            (
                "view_root",
                "opened",
                "outputs",
                "input_commitment_sha256",
                "prompt_plan_sha256",
                "prompt_path",
                "prompt_sha256",
                "prompt_verification_sha256",
                "launch_id",
                "jsonl_path",
                "stderr_path",
                "launch_record_path",
                "scratch_dir",
            ),
            "PREPARE_ACTOR_COMMIT payload",
        )
        for key in (
            "input_commitment_sha256",
            "prompt_plan_sha256",
            "prompt_sha256",
            "prompt_verification_sha256",
        ):
            require_hash(payload[key], f"prepared actor {key}")
        canonical_uuid(payload["launch_id"], "prepared launch ID")
        begin_payload = state["pending"]["begin_payload"]
        for key in (
            "launch_id",
            "jsonl_path",
            "stderr_path",
            "launch_record_path",
            "scratch_dir",
        ):
            if payload[key] != begin_payload[key]:
                raise RunnerError(
                    f"prepared actor {key} differs from its BEGIN allocation"
                )
        if not isinstance(payload["opened"], list) or not payload["opened"]:
            raise RunnerError("prepared actor opened allowlist must be nonempty")
        if not isinstance(payload["outputs"], list) or not payload["outputs"]:
            raise RunnerError("prepared actor output allowlist must be nonempty")
        state["actors"][actor]["phase"] = "PREPARED"
        state["actors"][actor]["prepare"] = copy.deepcopy(payload)
        state["pending"] = None

    elif kind == "LAUNCH_ACTOR_BEGIN":
        actor = _require_actor_event(state, event)
        _exact_keys(payload, (), "LAUNCH_ACTOR_BEGIN payload")
        if not _actor_in_current_phase(state, actor) or state["actors"][actor]["phase"] != "PREPARED":
            raise RunnerError("actor launch is out of order or not prepared")
        _require_singleton_phase_actor(state, actor, "single-actor launch")
        _begin_pending(state, event, "LAUNCH_ACTOR", actor)

    elif kind == "LAUNCH_ACTOR_COMMIT":
        pending = _require_matching_commit(state, event, "LAUNCH_ACTOR")
        actor = str(pending["actor"])
        _exact_keys(
            payload,
            (
                "schema",
                "launch_id",
                "launch_record_path",
                "launch_record_sha256",
                "output_commitment_sha256",
                "jsonl_sha256",
                "result_sha256",
            ),
            "LAUNCH_ACTOR_COMMIT payload",
        )
        if payload["schema"] != LAUNCH_SCHEMA:
            raise RunnerError("actor launch receipt is not v3")
        prepared = state["actors"][actor]["prepare"]
        if payload["launch_id"] != prepared["launch_id"]:
            raise RunnerError("launch receipt UUID differs from prepared allocation")
        if payload["launch_record_path"] != prepared["launch_record_path"]:
            raise RunnerError("launch receipt path differs from prepared allocation")
        record_hash = require_hash(payload["launch_record_sha256"], "launch-record SHA-256")
        require_hash(payload["output_commitment_sha256"], "output commitment SHA-256")
        require_hash(payload["jsonl_sha256"], "actor JSONL SHA-256")
        require_hash(payload["result_sha256"], "launcher result SHA-256")
        if record_hash in state["launched_receipts"]:
            raise RunnerError("launch receipt hash is being replayed")
        state["launched_receipts"].append(record_hash)
        state["actors"][actor]["phase"] = "LAUNCHED"
        state["actors"][actor]["launch"] = copy.deepcopy(payload)
        state["pending"] = None

    elif kind == "PROMOTE_ACTOR_BEGIN":
        actor = _require_actor_event(state, event)
        _exact_keys(payload, (), "PROMOTE_ACTOR_BEGIN payload")
        if not _actor_in_current_phase(state, actor) or state["actors"][actor]["phase"] != "LAUNCHED":
            raise RunnerError("actor promotion is out of order or lacks a launch receipt")
        _require_singleton_phase_actor(state, actor, "single-actor promotion")
        receipt = state["actors"][actor]["launch"]["launch_record_sha256"]
        if receipt in state["consumed_receipts"]:
            raise RunnerError("launch receipt has already been consumed")
        _begin_pending(state, event, "PROMOTE_ACTOR", actor)

    elif kind == "PROMOTE_ACTOR_COMMIT":
        pending = _require_matching_commit(state, event, "PROMOTE_ACTOR")
        actor = str(pending["actor"])
        _exact_keys(
            payload,
            ("launch_record_sha256", "output_commitment_sha256", "promoted_outputs"),
            "PROMOTE_ACTOR_COMMIT payload",
        )
        launch = state["actors"][actor]["launch"]
        record_hash = require_hash(payload["launch_record_sha256"], "promoted launch-record SHA-256")
        output_hash = require_hash(payload["output_commitment_sha256"], "promoted output commitment")
        if record_hash != launch["launch_record_sha256"] or output_hash != launch["output_commitment_sha256"]:
            raise RunnerError("promotion receipt differs from the frozen launch receipt")
        if record_hash in state["consumed_receipts"]:
            raise RunnerError("launch receipt has already been consumed")
        if not isinstance(payload["promoted_outputs"], dict) or not payload["promoted_outputs"]:
            raise RunnerError("promotion must commit a nonempty output hash map")
        for path, digest in payload["promoted_outputs"].items():
            if not isinstance(path, str) or not path:
                raise RunnerError("promoted output path must be nonempty")
            require_hash(digest, f"promoted output {path}")
        state["consumed_receipts"].append(record_hash)
        state["actors"][actor]["phase"] = "PROMOTED"
        state["actors"][actor]["promotion"] = copy.deepcopy(payload)
        state["next_actor_index"] += 1
        state["pending"] = None
        _advance_completed_phase(state)

    elif kind == "CLOSE_SA_SET_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("SA-set close event must not name an actor")
        _exact_keys(payload, (), "CLOSE_SA_SET_BEGIN payload")
        current_phase = _current_phase_actors(state)
        if (
            state["sa_set_closed"]
            or not current_phase
            or not all(actor.startswith("SA-") for actor in current_phase)
            or not _phase_all(state, "PROMOTED")
        ):
            raise RunnerError("SA set can close only after every SA actor is promoted")
        _begin_pending(state, event, "CLOSE_SA_SET", None)

    elif kind == "CLOSE_SA_SET_COMMIT":
        _require_matching_commit(state, event, "CLOSE_SA_SET")
        _exact_keys(payload, ("gate_path", "gate_sha256"), "CLOSE_SA_SET_COMMIT payload")
        require_hash(payload["gate_sha256"], "semantic gate SHA-256")
        state["semantic_gate"] = copy.deepcopy(payload)
        state["sa_set_closed"] = True
        state["phase_index"] += 1
        state["pending"] = None

    elif kind == "RETIRE_RULES_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("rule-retirement event must not name an actor")
        _exact_keys(payload, (), "RETIRE_RULES_BEGIN payload")
        if _current_phase_actors(state) or state["rules_retired"]:
            raise RunnerError("rules can retire only after every actor is promoted")
        _begin_pending(state, event, "RETIRE_RULES", None)

    elif kind == "RETIRE_RULES_COMMIT":
        _require_matching_commit(state, event, "RETIRE_RULES")
        _exact_keys(payload, ("destination", "manifest_sha256"), "RETIRE_RULES_COMMIT payload")
        require_hash(payload["manifest_sha256"], "retirement manifest SHA-256")
        state["retirement"] = copy.deepcopy(payload)
        state["rules_retired"] = True
        state["pending"] = None

    elif kind == "FINALIZE_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("finalization event must not name an actor")
        _exact_keys(payload, (), "FINALIZE_BEGIN payload")
        if not state["rules_retired"] or state["finalized"]:
            raise RunnerError("finalization requires completed rule retirement")
        _begin_pending(state, event, "FINALIZE", None)

    elif kind == "FINALIZE_COMMIT":
        _require_matching_commit(state, event, "FINALIZE")
        _exact_keys(
            payload,
            (
                "validation_report_path",
                "validation_report_sha256",
                "validator_stdout_sha256",
                "round_tree_sha256",
            ),
            "FINALIZE_COMMIT payload",
        )
        require_hash(payload["validation_report_sha256"], "validation report SHA-256")
        require_hash(payload["validator_stdout_sha256"], "validator stdout SHA-256")
        require_hash(payload["round_tree_sha256"], "finalized round-tree SHA-256")
        state["validation"] = copy.deepcopy(payload)
        state["finalized"] = True
        state["pending"] = None

    elif kind == "AUTHORIZE_DELIVERY_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("delivery event must not name an actor")
        _exact_keys(payload, (), "AUTHORIZE_DELIVERY_BEGIN payload")
        if not state["finalized"] or state["delivery_authorized"]:
            raise RunnerError("delivery requires one successful final validation")
        _begin_pending(state, event, "AUTHORIZE_DELIVERY", None)

    elif kind == "AUTHORIZE_DELIVERY_COMMIT":
        _require_matching_commit(state, event, "AUTHORIZE_DELIVERY")
        _exact_keys(
            payload,
            (
                "summary_path",
                "summary_sha256",
                "validation_report_sha256",
                "frozen_pdf_sha256",
                "round_tree_sha256",
            ),
            "AUTHORIZE_DELIVERY_COMMIT payload",
        )
        for key in (
            "summary_sha256",
            "validation_report_sha256",
            "frozen_pdf_sha256",
            "round_tree_sha256",
        ):
            require_hash(payload[key], f"delivery {key}")
        if payload["validation_report_sha256"] != state["validation"]["validation_report_sha256"]:
            raise RunnerError("delivery authorization does not bind the final validation")
        if payload["round_tree_sha256"] != state["validation"]["round_tree_sha256"]:
            raise RunnerError("delivery authorization does not bind the finalized round tree")
        state["delivery"] = copy.deepcopy(payload)
        state["delivery_authorized"] = True
        state["pending"] = None

    elif kind == "QUARANTINE_BEGIN":
        if event["actor"] is not None:
            raise RunnerError("quarantine event must not name an actor")
        _exact_keys(
            payload,
            ("reason", "destination", "abandoned_operation_id"),
            "QUARANTINE_BEGIN payload",
        )
        if not isinstance(payload["reason"], str) or not payload["reason"]:
            raise RunnerError("quarantine reason must be nonempty")
        abandoned = payload["abandoned_operation_id"]
        if pending is None:
            if abandoned is not None:
                raise RunnerError("quarantine names an absent abandoned operation")
        elif abandoned != pending["operation_id"]:
            raise RunnerError("quarantine does not name the dangling operation")
        _begin_pending(state, event, "QUARANTINE", None)

    elif kind == "QUARANTINE_COMMIT":
        _require_matching_commit(state, event, "QUARANTINE")
        _exact_keys(
            payload,
            ("destination", "metadata_sha256", "round_id", "retry_id"),
            "QUARANTINE_COMMIT payload",
        )
        require_hash(payload["metadata_sha256"], "quarantined metadata SHA-256")
        state["quarantined"] = True
        state["quarantine_destination"] = payload["destination"]
        state["pending"] = None

    else:  # pragma: no cover - ALL_KINDS plus branches above is closed
        raise RunnerError(f"unhandled Stage-O event kind: {kind}")

    state["event_count"] = int(event["sequence"])
    state["transition_token"] = event_sha256
    return state


def event_root_for_run(run_root: Path) -> Path:
    return run_root / "orchestration" / "stage-o" / "events"


def load_event_chain(event_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = require_directory(event_root, "Stage-O event directory")
    entries = sorted(root.iterdir(), key=lambda item: item.name)
    expected_names = [f"E{index:08d}.json" for index in range(1, len(entries) + 1)]
    actual_names = [entry.name for entry in entries]
    if actual_names != expected_names:
        raise RunnerError(
            "Stage-O event directory is not a closed contiguous sequence: "
            f"expected={expected_names}, actual={actual_names}"
        )
    state = initial_state()
    events: list[dict[str, Any]] = []
    for index, path in enumerate(entries, start=1):
        raw = stable_regular_bytes(path, f"Stage-O event {path.name}")
        event = strict_object_from_bytes(raw, f"Stage-O event {path.name}")
        if canonical_json_bytes(event) != raw:
            raise RunnerError(f"Stage-O event {path.name} is not canonical JSON")
        if EVENT_NAME_RE.fullmatch(path.name) is None or event.get("sequence") != index:
            raise RunnerError(f"Stage-O event filename/sequence mismatch: {path.name}")
        digest = sha256_bytes(raw)
        state = reduce_event(state, event, digest)
        events.append(event)
    return state, events


def _fsync_directory(path: Path) -> None:
    retry = _load_module("manage_review_retry.py", "stage_o_runner_fsync")
    try:
        retry._fsync_directory(path)
    except Exception as exc:
        raise CommitUncertainError(f"cannot durably flush event directory: {exc}") from exc


def append_event(
    event_root: Path,
    *,
    expected_transition_token: str,
    kind: str,
    operation_id: str,
    actor: str | None,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    state, _events = load_event_chain(event_root)
    expected = require_hash(expected_transition_token, "expected transition token")
    if expected != state["transition_token"]:
        raise RunnerError(
            "compare-and-swap transition token is stale: "
            f"expected head {state['transition_token']}, got {expected}"
        )
    event = {
        "schema": EVENT_SCHEMA,
        "sequence": state["event_count"] + 1,
        "kind": kind,
        "operation_id": canonical_uuid(operation_id, "event operation_id"),
        "actor": actor,
        "expected_transition_token": expected,
        "previous_event_sha256": state["transition_token"],
        "payload": payload,
    }
    raw = canonical_json_bytes(event)
    digest = sha256_bytes(raw)
    # Validate the event before publishing it.
    next_state = reduce_event(state, event, digest)
    destination = event_root / f"E{event['sequence']:08d}.json"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(event_root)
    except FileExistsError as exc:
        raise RunnerError("Stage-O CAS lost a concurrent event-append race") from exc
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        raise
    if destination.read_bytes() != raw or sha256_file(destination) != digest:
        raise CommitUncertainError("published Stage-O event bytes changed after creation")
    terminal_state, _ = load_event_chain(event_root)
    if terminal_state != next_state:
        raise CommitUncertainError("Stage-O event-chain state changed after append")
    return terminal_state, event, digest


def _create_event_store(run_root: Path) -> Path:
    orchestration = require_directory(run_root / "orchestration", "run orchestration")
    stage_o = orchestration / "stage-o"
    events = stage_o / "events"
    if os.path.lexists(stage_o):
        raise RunnerError("Stage-O ledger already exists; bootstrap cannot adopt it")
    try:
        stage_o.mkdir()
        events.mkdir()
        _fsync_directory(stage_o)
        _fsync_directory(orchestration)
    except Exception as exc:
        raise RunnerError(f"cannot create Stage-O event store: {exc}") from exc
    return events


def _plan_actor_from_receipt(actor: str, receipt: dict[str, Any]) -> str:
    if actor.startswith("SA-"):
        if receipt.get("schema") != SEMANTIC_PROMPT_SCHEMA:
            raise RunnerError(f"prompt-plan receipt for {actor} has the wrong schema")
        if receipt.get("target") != actor[3:]:
            raise RunnerError(f"prompt-plan target does not match {actor}")
        return actor
    expected_schema = (
        REVIEWER_PROMPT_SCHEMA if re.fullmatch(r"R[1-5]", actor) else CANONICAL_PROMPT_SCHEMA
    )
    if receipt.get("schema") != expected_schema:
        raise RunnerError(f"prompt-plan receipt for {actor} has the wrong schema")
    if receipt.get("actor") != actor:
        raise RunnerError(f"prompt-plan actor does not match {actor}")
    return actor


def _load_prompt_plans(
    plan_dir: Path,
    sequence: list[str],
    process: dict[str, Any],
    run_root: Path,
    scratch_root: Path,
) -> dict[str, dict[str, Any]]:
    plan_dir = require_directory(plan_dir, "prompt-plan directory")
    expected_names = [f"{actor}.json" for actor in sequence]
    actual_names = sorted(entry.name for entry in plan_dir.iterdir())
    if sorted(expected_names) != actual_names:
        raise RunnerError(
            "prompt-plan directory must contain exactly one receipt per actor: "
            f"missing={sorted(set(expected_names)-set(actual_names))}, "
            f"extra={sorted(set(actual_names)-set(expected_names))}"
        )
    prompt_map = process.get("actor_prompt_sha256")
    if not isinstance(prompt_map, dict) or set(prompt_map) != set(sequence):
        raise RunnerError(
            "process.actor_prompt_sha256 must exactly follow the fixed actor sequence; "
            "H/V and degree-inapplicable actors are forbidden in runner v1"
        )
    plans: dict[str, dict[str, Any]] = {}
    seen_prompts: set[str] = set()
    seen_scratches: set[str] = set()
    for actor in sequence:
        plan_path = plan_dir / f"{actor}.json"
        receipt = read_strict_object(plan_path, f"{actor} prompt-plan receipt")
        _plan_actor_from_receipt(actor, receipt)
        prompt_path = absolute_path(
            Path(str(receipt.get("prompt_file", ""))),
            f"{actor} planned prompt",
            must_exist=True,
        )
        require_regular(prompt_path, f"{actor} planned prompt")
        if is_within(prompt_path, run_root):
            raise RunnerError(f"{actor} planned prompt must remain outside the run")
        prompt_hash = sha256_file(prompt_path)
        receipt_hash = require_hash(receipt.get("prompt_sha256"), f"{actor} plan prompt hash")
        process_hash = require_hash(prompt_map.get(actor), f"process prompt hash for {actor}")
        if prompt_hash != receipt_hash or prompt_hash != process_hash:
            raise RunnerError(f"{actor} prompt plan/file/process hashes do not agree")
        normalized_prompt = os.path.normcase(str(prompt_path))
        if normalized_prompt in seen_prompts:
            raise RunnerError("two actors cannot share one prompt pathname")
        seen_prompts.add(normalized_prompt)
        scratch_value: str | None = None
        if not actor.startswith("SA-"):
            scratch = absolute_path(
                Path(str(receipt.get("scratch_dir", ""))),
                f"{actor} planned scratch",
                must_exist=True,
            )
            require_directory(scratch, f"{actor} planned scratch")
            if not is_within(scratch, scratch_root) or boundaries_overlap(scratch, run_root):
                raise RunnerError(f"{actor} planned scratch is outside the bound scratch root")
            if next(scratch.iterdir(), None) is not None:
                raise RunnerError(f"{actor} planned scratch must be empty")
            normalized_scratch = os.path.normcase(str(scratch))
            if normalized_scratch in seen_scratches:
                raise RunnerError("two actors cannot share one scratch directory")
            seen_scratches.add(normalized_scratch)
            scratch_value = str(scratch)
        plans[actor] = {
            "plan_path": str(plan_path),
            "plan_sha256": sha256_file(plan_path),
            "prompt_path": str(prompt_path),
            "prompt_sha256": prompt_hash,
            "scratch_dir": scratch_value,
        }
    return plans


def _canonical_bootstrap_config(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    run_root = absolute_path(args.run_root, "run root", must_exist=True)
    require_directory(run_root, "run root")
    round_root = require_directory(run_root / "round", "round root")
    views_root = require_directory(run_root / "views", "views root")
    orchestration = require_directory(run_root / "orchestration", "orchestration root")
    workspace = require_directory(run_root.parent, "review workspace")
    skill_root = _canonical_bound_skill_root(args.skill_root)
    control_root = require_directory(
        absolute_path(args.control_root, "external control root", must_exist=True),
        "external control root",
    )
    scratch_root = require_directory(
        absolute_path(args.scratch_root, "scratch root", must_exist=True), "scratch root"
    )
    prompt_plan_dir = require_directory(
        absolute_path(args.prompt_plan_dir, "prompt-plan directory", must_exist=True),
        "prompt-plan directory",
    )
    retirement_root = absolute_path(args.retirement_root, "retirement root", must_exist=False)
    python_executable = require_regular(
        absolute_path(args.python_executable, "Python executable", must_exist=True),
        "Python executable",
    )
    codex_executable = require_regular(
        absolute_path(args.codex_executable, "Codex executable", must_exist=True),
        "Codex executable",
    )
    if codex_executable.name.casefold() not in {"codex", "codex.exe"}:
        raise RunnerError("Codex executable basename must be codex or codex.exe")
    for external, label in (
        (skill_root, "skill root"),
        (control_root, "control root"),
        (scratch_root, "scratch root"),
        (retirement_root, "retirement root"),
        (python_executable, "Python executable"),
        (codex_executable, "Codex executable"),
    ):
        if boundaries_overlap(external, run_root):
            raise RunnerError(f"{label} must remain outside the complete run")
    if not is_within(prompt_plan_dir, control_root):
        raise RunnerError("prompt-plan directory must be inside the bound control root")
    if boundaries_overlap(control_root, scratch_root):
        raise RunnerError("control and scratch roots must be disjoint")
    if os.path.lexists(retirement_root):
        raise RunnerError("retirement root must be absent before bootstrap")
    require_directory(retirement_root.parent, "retirement-root parent")

    process_path = require_regular(round_root / "00-process-parameters.json", "process envelope")
    seal_path = require_regular(orchestration / "process-seal.json", "process seal")
    process = read_strict_object(process_path, "process envelope")
    degree = str(process.get("degree_level", ""))
    sequence = actor_sequence(degree)
    plans = _load_prompt_plans(prompt_plan_dir, sequence, process, run_root, scratch_root)
    config = {
        "run_root": str(run_root),
        "workspace": str(workspace),
        "round_root": str(round_root),
        "views_root": str(views_root),
        "orchestration_root": str(orchestration),
        "skill_root": str(skill_root),
        "control_root": str(control_root),
        "scratch_root": str(scratch_root),
        "retirement_root": str(retirement_root),
        "python_executable": str(python_executable),
        "python_executable_sha256": sha256_file(python_executable),
        "codex_executable": str(codex_executable),
        "codex_executable_sha256": sha256_file(codex_executable),
        "toolchain_sha256": {
            name: sha256_file(require_regular(skill_root / "scripts" / name, f"toolchain {name}"))
            for name in PINNED_SCRIPT_NAMES
        },
        "process_sha256": sha256_file(process_path),
        "process_seal_sha256": sha256_file(seal_path),
        "degree_level": degree,
        "actor_sequence": sequence,
        "prompt_plans": plans,
    }
    _validate_bootstrap_payload(config)
    return config, process


def _quarantine_destination(state: dict[str, Any]) -> Path:
    config = state.get("config")
    if not isinstance(config, dict):
        raise RunnerError("cannot derive quarantine path before bootstrap BEGIN")
    run_root = Path(config["run_root"])
    workspace = Path(config["workspace"])
    for _ in range(16):
        candidate = workspace / f"QUARANTINED-{run_root.name}-stage-o-{uuid.uuid4().hex[:12]}"
        if not os.path.lexists(candidate):
            return candidate
    raise RunnerError("cannot allocate a unique quarantine destination")


def _perform_quarantine(
    event_root: Path,
    state: dict[str, Any],
    *,
    reason: str,
    expected_token: str,
) -> tuple[dict[str, Any], Path]:
    destination = _quarantine_destination(state)
    operation_id = str(uuid.uuid4())
    abandoned = state["pending"]["operation_id"] if state.get("pending") else None
    begun, _event, begin_token = append_event(
        event_root,
        expected_transition_token=expected_token,
        kind="QUARANTINE_BEGIN",
        operation_id=operation_id,
        actor=None,
        payload={
            "reason": reason,
            "destination": str(destination),
            "abandoned_operation_id": abandoned,
        },
    )
    retry = _load_module("manage_review_retry.py", "stage_o_runner_quarantine")
    try:
        result = retry.quarantine(
            argparse.Namespace(
                workspace=begun["config"]["workspace"],
                run_root=begun["config"]["run_root"],
                quarantine_run_root=str(destination),
            )
        )
    except Exception as exc:
        raise RunnerError(
            "quarantine BEGIN was committed but manage_review_retry quarantine failed; "
            "the retry remains terminal and must not be resumed: " + str(exc)
        ) from exc
    destination_event_root = event_root_for_run(destination)
    final, _commit, _token = append_event(
        destination_event_root,
        expected_transition_token=begin_token,
        kind="QUARANTINE_COMMIT",
        operation_id=operation_id,
        actor=None,
        payload={
            "destination": str(destination),
            "metadata_sha256": require_hash(result["metadata_sha256"], "quarantine metadata hash"),
            "round_id": str(result["round_id"]),
            "retry_id": str(result["retry_id"]),
        },
    )
    return final, destination


def _transaction(
    event_root: Path,
    state: dict[str, Any],
    *,
    base: str,
    actor: str | None,
    expected_token: str,
    begin_payload: dict[str, Any],
    effect: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    operation_id = str(uuid.uuid4())
    begun, _event, begin_token = append_event(
        event_root,
        expected_transition_token=expected_token,
        kind=f"{base}_BEGIN",
        operation_id=operation_id,
        actor=actor,
        payload=begin_payload,
    )
    try:
        if base in PROMOTED_OUTPUT_ANCHOR_BASES:
            _verify_promoted_output_anchors(state)
        commit_payload = effect()
        committed, _commit, _commit_token = append_event(
            event_root,
            expected_transition_token=begin_token,
            kind=f"{base}_COMMIT",
            operation_id=operation_id,
            actor=actor,
            payload=commit_payload,
        )
        return committed
    except BaseException as exc:
        # A process kill can prevent this handler; the durable dangling BEGIN
        # then leaves quarantine as the only admissible next transition.
        try:
            current, _ = load_event_chain(event_root)
            quarantined, destination = _perform_quarantine(
                event_root,
                current,
                reason=f"{base} failed: {type(exc).__name__}: {exc}",
                expected_token=current["transition_token"],
            )
        except BaseException as quarantine_exc:
            raise RunnerError(
                f"{base} failed after BEGIN ({exc}); automatic quarantine also failed "
                f"closed ({quarantine_exc})"
            ) from exc
        raise RunnerError(
            f"{base} failed after BEGIN and the complete retry was quarantined at "
            f"{destination}; terminal token={quarantined['transition_token']}: {exc}"
        ) from exc


def _state_for_command(run_root_value: Path, expected_token: str | None = None) -> tuple[Path, dict[str, Any]]:
    run_root = absolute_path(run_root_value, "run root", must_exist=True)
    event_root = event_root_for_run(run_root)
    state, _events = load_event_chain(event_root)
    if expected_token is not None:
        supplied = require_hash(expected_token, "expected transition token")
        if supplied != state["transition_token"]:
            raise RunnerError(
                f"stale transition token: expected {state['transition_token']}, got {supplied}"
            )
        _verify_toolchain(state)
    return event_root, state


def _verify_toolchain(state: dict[str, Any]) -> None:
    config = state.get("config")
    if not isinstance(config, dict):
        raise RunnerError("Stage-O toolchain cannot be verified before bootstrap")
    if sha256_file(Path(config["python_executable"])) != config["python_executable_sha256"]:
        raise RunnerError("bound Python executable changed after bootstrap")
    if sha256_file(Path(config["codex_executable"])) != config["codex_executable_sha256"]:
        raise RunnerError("bound Codex executable changed after bootstrap")
    skill_scripts = Path(config["skill_root"]) / "scripts"
    expected = config["toolchain_sha256"]
    if not isinstance(expected, dict) or set(expected) != set(PINNED_SCRIPT_NAMES):
        raise RunnerError("stored Stage-O toolchain map is invalid")
    for name in PINNED_SCRIPT_NAMES:
        if sha256_file(skill_scripts / name) != expected[name]:
            raise RunnerError(f"production Stage-O toolchain changed after bootstrap: {name}")


def _process_from_state(state: dict[str, Any]) -> dict[str, Any]:
    config = state["config"]
    process_path = Path(config["round_root"]) / "00-process-parameters.json"
    if sha256_file(process_path) != config["process_sha256"]:
        raise RunnerError("sealed process bytes drifted from the runner bootstrap anchor")
    return read_strict_object(process_path, "sealed process envelope")


def _actor_outputs(process: dict[str, Any], actor: str, manager: Any, semantic: Any) -> list[str]:
    if actor.startswith("SA-"):
        target = actor[3:]
        return [path.relative_to(Path("X")).as_posix() for path in semantic.private_output_paths(Path("X"), target)]
    if actor in {"P", "AI"} or re.fullmatch(r"R[1-5]", actor):
        return list(manager.general_actor_outputs(process, actor))
    return list(manager.C_OUTPUTS if actor == "C" else manager.S_OUTPUTS)


def actor_search_enabled(actor: str) -> bool:
    """Only Stage-R reviewers have a public-endpoint/search capability."""

    return re.fullmatch(r"R[1-5]", actor) is not None


def _round_output_paths(round_root: Path, process: dict[str, Any], actor: str, manager: Any, semantic: Any) -> list[Path]:
    if actor.startswith("SA-"):
        return list(semantic.round_output_paths(round_root, actor[3:]))
    return [round_root / item for item in _actor_outputs(process, actor, manager, semantic)]


def _verify_promoted_output_anchors(
    state: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Re-authenticate every actor output already promoted into the round."""

    promoted_actors = [
        actor
        for actor in state.get("actor_sequence", [])
        if state.get("actors", {}).get(actor, {}).get("phase") == "PROMOTED"
    ]
    if not promoted_actors:
        return {}

    process = _process_from_state(state)
    round_root = require_directory(
        Path(state["config"]["round_root"]), "promoted-output round root"
    )
    manager = _load_module(
        "manage_stage_o_workspace.py",
        "stage_o_runner_promoted_anchor_workspace",
    )
    semantic = _load_module(
        "build_semantic_acceptance_prompt.py",
        "stage_o_runner_promoted_anchor_semantic",
    )
    verified: dict[str, dict[str, str]] = {}
    seen_paths: set[str] = set()
    for actor in promoted_actors:
        promotion = state["actors"][actor].get("promotion")
        if not isinstance(promotion, dict):
            raise RunnerError(f"promoted actor {actor} has no promotion receipt")
        stored = promotion.get("promoted_outputs")
        if not isinstance(stored, dict) or not stored:
            raise RunnerError(f"promoted actor {actor} has no output anchor map")

        canonical_paths = _round_output_paths(
            round_root, process, actor, manager, semantic
        )
        canonical = {str(path): path for path in canonical_paths}
        if len(canonical) != len(canonical_paths):
            raise RunnerError(
                f"canonical promoted output set for {actor} has duplicates"
            )
        if set(stored) != set(canonical):
            raise RunnerError(
                f"promoted output path set drift for {actor}: "
                f"missing={sorted(set(canonical) - set(stored))}, "
                f"extra={sorted(set(stored) - set(canonical))}"
            )

        actor_verified: dict[str, str] = {}
        for pathname, path in canonical.items():
            normalized = os.path.normcase(os.path.normpath(pathname))
            if normalized in seen_paths:
                raise RunnerError(
                    "promoted output path is owned by more than one actor: "
                    f"{pathname}"
                )
            seen_paths.add(normalized)
            expected = require_hash(
                stored[pathname],
                f"promoted output anchor {actor} {pathname}",
            )
            payload = stable_regular_bytes(
                path, f"promoted output {actor} {pathname}"
            )
            actual = sha256_bytes(payload)
            require_regular(path, f"promoted output {actor} {pathname}")
            if actual != expected:
                raise RunnerError(
                    f"promoted output SHA-256 drift for {actor} {pathname}: "
                    f"expected {expected}, got {actual}"
                )
            actor_verified[pathname] = actual
        verified[actor] = actor_verified
    return verified


def _assert_outputs_absent(round_root: Path, process: dict[str, Any], actor: str, manager: Any, semantic: Any) -> None:
    early = [str(path) for path in _round_output_paths(round_root, process, actor, manager, semantic) if os.path.lexists(path)]
    if early:
        raise RunnerError(f"actor {actor} has output(s) before preparation: {early}")


def _read_plan_again(state: dict[str, Any], actor: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stored = state["config"]["prompt_plans"][actor]
    path = Path(stored["plan_path"])
    if sha256_file(path) != stored["plan_sha256"]:
        raise RunnerError(f"{actor} prompt-plan receipt changed after bootstrap")
    receipt = read_strict_object(path, f"{actor} prompt-plan receipt")
    _plan_actor_from_receipt(actor, receipt)
    prompt = Path(stored["prompt_path"])
    if sha256_file(prompt) != stored["prompt_sha256"]:
        raise RunnerError(f"{actor} prompt bytes changed after bootstrap")
    return stored, receipt


def _verify_prepared_prompt(
    state: dict[str, Any], actor: str, view_root: Path, scratch: Path, commitment: str
) -> dict[str, Any]:
    config = state["config"]
    stored, _receipt = _read_plan_again(state, actor)
    prompt = Path(stored["prompt_path"])
    python_executable = Path(config["python_executable"])
    if actor.startswith("SA-"):
        semantic = _load_module(
            "build_semantic_acceptance_prompt.py", "stage_o_runner_sa_verify"
        )
        metadata, _context = semantic.verify_prompt(
            view_root,
            prompt,
            actor[3:],
            config["process_sha256"],
            python_executable,
            require_sa_outputs=False,
            expected_input_commitment_sha256=commitment,
        )
        return metadata
    if re.fullmatch(r"R[1-5]", actor):
        reviewer = _load_module("build_reviewer_prompt.py", "stage_o_runner_r_verify")
        return reviewer.verify_prompt(
            Path(config["run_root"]),
            Path(config["round_root"]),
            view_root,
            prompt,
            actor,
            config["process_sha256"],
            config["process_seal_sha256"],
            python_executable,
            scratch,
            (),
        )
    canonical = _load_module(
        "build_canonical_actor_prompt.py", "stage_o_runner_canonical_verify"
    )
    return canonical.verify_prompt(
        Path(config["run_root"]),
        Path(config["round_root"]),
        view_root,
        prompt,
        actor,
        config["process_sha256"],
        config["process_seal_sha256"],
        python_executable,
        scratch,
    )


def _preallocate_actor(
    state: dict[str, Any], actor: str, process: dict[str, Any]
) -> dict[str, Any]:
    stored = state["config"]["prompt_plans"][actor]
    launch_id = str(uuid.uuid4())
    launch_directory = (
        Path(state["config"]["control_root"])
        / "launches"
        / f"{process['round_id']}--{process['retry_id']}"
        / actor
        / launch_id
    )
    if os.path.lexists(launch_directory):
        raise RunnerError("preallocated launch directory unexpectedly exists")
    if actor.startswith("SA-"):
        scratch = (
            Path(state["config"]["scratch_root"])
            / f"stage-o-{process['round_id']}--{process['retry_id']}"
            / f"{actor}-{launch_id}"
        )
    else:
        scratch = Path(str(stored["scratch_dir"]))
    return {
        "outputs_absent": True,
        "launch_id": launch_id,
        "jsonl_path": str(launch_directory / "actor.jsonl"),
        "stderr_path": str(launch_directory / "actor.stderr"),
        "launch_record_path": str(launch_directory / "launch-record.json"),
        "scratch_dir": str(scratch),
    }


def _execute_prepare_actor(
    state: dict[str, Any], actor: str, allocation: dict[str, Any]
) -> dict[str, Any]:
    manager = _load_module(
        "manage_stage_o_workspace.py", f"stage_o_runner_prepare_stage_{actor.replace('-', '_')}"
    )
    semantic = _load_module(
        "build_semantic_acceptance_prompt.py", f"stage_o_runner_prepare_sa_{actor.replace('-', '_')}"
    )
    process = _process_from_state(state)
    round_root = Path(state["config"]["round_root"])
    stored = state["config"]["prompt_plans"][actor]
    _assert_outputs_absent(round_root, process, actor, manager, semantic)
    stored, _receipt = _read_plan_again(state, actor)
    launch_directory = Path(allocation["jsonl_path"]).parent
    launch_directory.mkdir(parents=True)
    scratch = Path(allocation["scratch_dir"])
    if actor.startswith("SA-"):
        scratch.mkdir(parents=True)
    require_directory(scratch, f"{actor} private scratch")
    if next(scratch.iterdir(), None) is not None:
        raise RunnerError(f"{actor} private scratch is not empty")
    view_root = Path(state["config"]["views_root"]) / actor
    if actor.startswith("SA-"):
        staged = manager.command_stage_sa(
            argparse.Namespace(round_root=round_root, view_root=view_root, target=actor[3:])
        )
        opened = list(staged["opened"])
        # SA promotion and the semantic prompt verifier intentionally use a
        # stronger, SA-specific commitment envelope (schema + view root +
        # relative paths + file identities).  The general Stage-O commitment
        # serializes a different record shape, so using it here produces a
        # different digest for identical bytes and makes every real SA phase
        # fail before launch.
        commitment = semantic.capture_opened_input_commitment(view_root, opened)[
            "sha256"
        ]
        outputs = _actor_outputs(process, actor, manager, semantic)
    elif actor in {"C", "S"}:
        staged = manager.command_stage_clean(
            argparse.Namespace(
                actor=actor,
                skill_root=Path(state["config"]["skill_root"]),
                round_root=round_root,
                view_root=view_root,
            )
        )
        opened = list(staged["opened"])
        commitment = staged["input_commitment_sha256"]
        outputs = _actor_outputs(process, actor, manager, semantic)
    else:
        staged = manager.command_stage_actor(
            argparse.Namespace(
                actor=actor,
                skill_root=Path(state["config"]["skill_root"]),
                round_root=round_root,
                view_root=view_root,
            )
        )
        opened = list(staged["opened"])
        outputs = list(staged["outputs"])
        commitment = staged["input_commitment_sha256"]
    for relative in outputs:
        if os.path.lexists(view_root / relative):
            raise RunnerError(f"{actor} output appeared before launch: {relative}")
    verification = _verify_prepared_prompt(state, actor, view_root, scratch, commitment)
    if verification.get("prompt_sha256") != stored["prompt_sha256"]:
        raise RunnerError("prompt verifier returned a different prompt hash")
    return {
        "view_root": str(view_root),
        "opened": opened,
        "outputs": outputs,
        "input_commitment_sha256": require_hash(commitment, "staged input commitment"),
        "prompt_plan_sha256": stored["plan_sha256"],
        "prompt_path": stored["prompt_path"],
        "prompt_sha256": stored["prompt_sha256"],
        "prompt_verification_sha256": sha256_bytes(canonical_json_bytes(verification)),
        "launch_id": allocation["launch_id"],
        "jsonl_path": allocation["jsonl_path"],
        "stderr_path": allocation["stderr_path"],
        "launch_record_path": allocation["launch_record_path"],
        "scratch_dir": allocation["scratch_dir"],
    }


def _execute_launch_actor(state: dict[str, Any], actor: str) -> dict[str, Any]:
    prepared = state["actors"][actor]["prepare"]
    launcher = _load_module(
        "launch_review_actor.py", f"stage_o_runner_launcher_{actor.replace('-', '_')}"
    )
    result = launcher.launch(
        argparse.Namespace(
            actor=actor,
            launch_id=prepared["launch_id"],
            prompt=Path(prepared["prompt_path"]),
            expected_prompt_sha256=prepared["prompt_sha256"],
            expected_process_sha256=state["config"]["process_sha256"],
            expected_process_seal_sha256=state["config"]["process_seal_sha256"],
            expected_input_commitment_sha256=prepared["input_commitment_sha256"],
            workspace=Path(prepared["view_root"]),
            cwd=Path(prepared["scratch_dir"]),
            jsonl=Path(prepared["jsonl_path"]),
            stderr=Path(prepared["stderr_path"]),
            launch_record=Path(prepared["launch_record_path"]),
            codex_executable=Path(state["config"]["codex_executable"]),
            search=actor_search_enabled(actor),
        )
    )
    if result.get("status") != "PASS" or result.get("launch_id") != prepared["launch_id"]:
        raise RunnerError("launcher did not return the exact successful allocation")
    if result.get("launch_record") != prepared["launch_record_path"]:
        raise RunnerError("launcher returned an unexpected launch-record path")
    record_hash = require_hash(result.get("launch_record_sha256"), "launcher record hash")
    output_hash = require_hash(result.get("output_commitment_sha256"), "launcher output commitment")
    jsonl_hash = require_hash(result.get("jsonl_sha256"), "launcher JSONL hash")
    if sha256_file(Path(prepared["launch_record_path"])) != record_hash:
        raise RunnerError("completed launch-record bytes differ from launcher receipt")
    if sha256_file(Path(prepared["jsonl_path"])) != jsonl_hash:
        raise RunnerError("completed JSONL bytes differ from launcher receipt")
    return {
        "schema": LAUNCH_SCHEMA,
        "launch_id": prepared["launch_id"],
        "launch_record_path": prepared["launch_record_path"],
        "launch_record_sha256": record_hash,
        "output_commitment_sha256": output_hash,
        "jsonl_sha256": jsonl_hash,
        "result_sha256": sha256_bytes(canonical_json_bytes(result)),
    }


def _execute_promote_actor(state: dict[str, Any], actor: str) -> dict[str, Any]:
    prepared = state["actors"][actor]["prepare"]
    launch = state["actors"][actor]["launch"]
    round_root = Path(state["config"]["round_root"])
    if actor.startswith("SA-"):
        semantic = _load_module(
            "build_semantic_acceptance_prompt.py", f"stage_o_runner_sa_promote_{actor.replace('-', '_')}"
        )
        result = semantic.promote(
            Path(prepared["view_root"]),
            round_root,
            Path(prepared["prompt_path"]),
            actor[3:],
            state["config"]["process_sha256"],
            prepared["input_commitment_sha256"],
            Path(prepared["launch_record_path"]),
            prepared["launch_id"],
            state["config"]["process_seal_sha256"],
            launch["launch_record_sha256"],
            launch["output_commitment_sha256"],
            Path(state["config"]["python_executable"]),
        )
        promoted = {
            str(item["destination"]): require_hash(item["sha256"], "SA promoted output")
            for item in result["files"]
        }
    else:
        manager = _load_module(
            "manage_stage_o_workspace.py", f"stage_o_runner_general_promote_{actor.replace('-', '_')}"
        )
        namespace = argparse.Namespace(
            actor=actor,
            round_root=round_root,
            view_root=Path(prepared["view_root"]),
            expected_input_commitment_sha256=prepared["input_commitment_sha256"],
            launch_record=Path(prepared["launch_record_path"]),
            expected_launch_id=prepared["launch_id"],
            expected_process_seal_sha256=state["config"]["process_seal_sha256"],
            expected_launch_record_sha256=launch["launch_record_sha256"],
            expected_output_commitment_sha256=launch["output_commitment_sha256"],
        )
        if actor in {"C", "S"}:
            result = manager.command_promote_clean(namespace)
        else:
            result = manager.command_promote_actor(namespace)
        promoted = {
            str(round_root / relative): require_hash(digest, "promoted output hash")
            for relative, digest in result["outputs"].items()
        }
    if not promoted:
        raise RunnerError("promotion primitive returned no output hashes")
    return {
        "launch_record_sha256": launch["launch_record_sha256"],
        "output_commitment_sha256": launch["output_commitment_sha256"],
        "promoted_outputs": promoted,
    }


def command_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    config, _process = _canonical_bootstrap_config(args)
    run_root = Path(config["run_root"])
    round_root = Path(config["round_root"])
    if os.path.lexists(round_root / "SKILL.md") or os.path.lexists(round_root / "rules"):
        raise RunnerError("bootstrap refuses previously staged/adopted rule inputs")
    if any(Path(config["views_root"]).iterdir()):
        raise RunnerError("bootstrap requires an empty views directory")
    event_root = _create_event_store(run_root)
    operation_id = str(uuid.uuid4())
    begun, _event, begin_token = append_event(
        event_root,
        expected_transition_token=ZERO_HASH,
        kind="BOOTSTRAP_BEGIN",
        operation_id=operation_id,
        actor=None,
        payload=config,
    )
    try:
        manager = _load_module("manage_stage_o_workspace.py", "stage_o_runner_bootstrap_stage")
        retry_preflight = _load_module(
            "manage_review_retry.py", "stage_o_runner_bootstrap_preflight"
        )
        retry_preflight._validate_pre_stage_p_state(run_root, _process)
        staged = manager.command_stage_round(
            argparse.Namespace(skill_root=Path(config["skill_root"]), round_root=round_root)
        )
        retry = _load_module("manage_review_retry.py", "stage_o_runner_bootstrap_seal")
        seal = retry.verify_process_seal(
            argparse.Namespace(
                workspace=config["workspace"],
                run_root=config["run_root"],
                expected_process_sha256=config["process_sha256"],
                expected_seal_sha256=config["process_seal_sha256"],
            )
        )
        committed, _commit, _token = append_event(
            event_root,
            expected_transition_token=begin_token,
            kind="BOOTSTRAP_COMMIT",
            operation_id=operation_id,
            actor=None,
            payload={
                "process_seal_verification": seal,
                "staged_rule_files": staged["files"],
            },
        )
        return committed
    except BaseException as exc:
        try:
            current, _ = load_event_chain(event_root)
            quarantined, destination = _perform_quarantine(
                event_root,
                current,
                reason=f"BOOTSTRAP failed: {type(exc).__name__}: {exc}",
                expected_token=current["transition_token"],
            )
        except BaseException as quarantine_exc:
            raise RunnerError(
                f"bootstrap failed after BEGIN ({exc}); quarantine also failed closed ({quarantine_exc})"
            ) from exc
        raise RunnerError(
            f"bootstrap failed and retry was quarantined at {destination}; "
            f"terminal token={quarantined['transition_token']}: {exc}"
        ) from exc


def command_prepare_actor(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    actor = str(args.actor).upper()
    if actor not in state["actors"] or not _actor_in_current_phase(state, actor):
        raise RunnerError(
            f"prepare actor is outside the current phase {_current_phase_actors(state)}"
        )
    _require_singleton_phase_actor(state, actor, "single-actor preparation")
    process = _process_from_state(state)
    begin_payload = _preallocate_actor(state, actor, process)

    def effect() -> dict[str, Any]:
        # Keep the single-actor path byte-for-byte equivalent to the parallel
        # phase path.  One implementation owns staging, prompt revalidation,
        # helper rejection, and the prepared receipt contract.
        return _execute_prepare_actor(state, actor, begin_payload)

    return _transaction(
        event_root,
        state,
        base="PREPARE_ACTOR",
        actor=actor,
        expected_token=args.expected_transition_token,
        begin_payload=begin_payload,
        effect=effect,
    )


def command_launch_actor(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    actor = str(args.actor).upper()
    if not _actor_in_current_phase(state, actor) or state["actors"].get(actor, {}).get("phase") != "PREPARED":
        raise RunnerError("launch actor is out of order or not prepared")
    _require_singleton_phase_actor(state, actor, "single-actor launch")
    prepared = state["actors"][actor]["prepare"]

    def effect() -> dict[str, Any]:
        launcher = _load_module("launch_review_actor.py", "stage_o_runner_launcher")
        result = launcher.launch(
            argparse.Namespace(
                actor=actor,
                launch_id=prepared["launch_id"],
                prompt=Path(prepared["prompt_path"]),
                expected_prompt_sha256=prepared["prompt_sha256"],
                expected_process_sha256=state["config"]["process_sha256"],
                expected_process_seal_sha256=state["config"]["process_seal_sha256"],
                expected_input_commitment_sha256=prepared["input_commitment_sha256"],
                workspace=Path(prepared["view_root"]),
                cwd=Path(prepared["scratch_dir"]),
                jsonl=Path(prepared["jsonl_path"]),
                stderr=Path(prepared["stderr_path"]),
                launch_record=Path(prepared["launch_record_path"]),
                codex_executable=Path(state["config"]["codex_executable"]),
                search=actor_search_enabled(actor),
            )
        )
        if result.get("status") != "PASS" or result.get("launch_id") != prepared["launch_id"]:
            raise RunnerError("launcher did not return the exact successful allocation")
        if result.get("launch_record") != prepared["launch_record_path"]:
            raise RunnerError("launcher returned an unexpected launch-record path")
        record_hash = require_hash(result.get("launch_record_sha256"), "launcher record hash")
        output_hash = require_hash(result.get("output_commitment_sha256"), "launcher output commitment")
        jsonl_hash = require_hash(result.get("jsonl_sha256"), "launcher JSONL hash")
        if sha256_file(Path(prepared["launch_record_path"])) != record_hash:
            raise RunnerError("completed launch-record bytes differ from launcher receipt")
        if sha256_file(Path(prepared["jsonl_path"])) != jsonl_hash:
            raise RunnerError("completed JSONL bytes differ from launcher receipt")
        return {
            "schema": LAUNCH_SCHEMA,
            "launch_id": prepared["launch_id"],
            "launch_record_path": prepared["launch_record_path"],
            "launch_record_sha256": record_hash,
            "output_commitment_sha256": output_hash,
            "jsonl_sha256": jsonl_hash,
            "result_sha256": sha256_bytes(canonical_json_bytes(result)),
        }

    return _transaction(
        event_root,
        state,
        base="LAUNCH_ACTOR",
        actor=actor,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_promote_actor(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    actor = str(args.actor).upper()
    if not _actor_in_current_phase(state, actor) or state["actors"].get(actor, {}).get("phase") != "LAUNCHED":
        raise RunnerError("promote actor is out of order or lacks a frozen launch receipt")
    _require_singleton_phase_actor(state, actor, "single-actor promotion")
    prepared = state["actors"][actor]["prepare"]
    launch = state["actors"][actor]["launch"]

    def effect() -> dict[str, Any]:
        round_root = Path(state["config"]["round_root"])
        if actor.startswith("SA-"):
            semantic = _load_module(
                "build_semantic_acceptance_prompt.py", "stage_o_runner_sa_promote"
            )
            result = semantic.promote(
                Path(prepared["view_root"]),
                round_root,
                Path(prepared["prompt_path"]),
                actor[3:],
                state["config"]["process_sha256"],
                prepared["input_commitment_sha256"],
                Path(prepared["launch_record_path"]),
                prepared["launch_id"],
                state["config"]["process_seal_sha256"],
                launch["launch_record_sha256"],
                launch["output_commitment_sha256"],
                Path(state["config"]["python_executable"]),
            )
            promoted = {
                str(item["destination"]): require_hash(item["sha256"], "SA promoted output")
                for item in result["files"]
            }
        else:
            manager = _load_module(
                "manage_stage_o_workspace.py", "stage_o_runner_general_promote"
            )
            namespace = argparse.Namespace(
                actor=actor,
                round_root=round_root,
                view_root=Path(prepared["view_root"]),
                expected_input_commitment_sha256=prepared["input_commitment_sha256"],
                launch_record=Path(prepared["launch_record_path"]),
                expected_launch_id=prepared["launch_id"],
                expected_process_seal_sha256=state["config"]["process_seal_sha256"],
                expected_launch_record_sha256=launch["launch_record_sha256"],
                expected_output_commitment_sha256=launch["output_commitment_sha256"],
            )
            if actor in {"C", "S"}:
                result = manager.command_promote_clean(namespace)
            else:
                result = manager.command_promote_actor(namespace)
            promoted = {
                str(round_root / relative): require_hash(digest, "promoted output hash")
                for relative, digest in result["outputs"].items()
            }
        if not promoted:
            raise RunnerError("promotion primitive returned no output hashes")
        return {
            "launch_record_sha256": launch["launch_record_sha256"],
            "output_commitment_sha256": launch["output_commitment_sha256"],
            "promoted_outputs": promoted,
        }

    return _transaction(
        event_root,
        state,
        base="PROMOTE_ACTOR",
        actor=actor,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_prepare_phase(args: argparse.Namespace) -> dict[str, Any]:
    """Prepare every actor in the current phase under one CAS transaction."""

    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    actors = _current_phase_actors(state)
    if not actors or not _phase_all(state, "NOT_STARTED"):
        raise RunnerError("prepare-phase requires a wholly NOT_STARTED current phase")
    manager = _load_module("manage_stage_o_workspace.py", "stage_o_runner_phase_precheck")
    semantic = _load_module(
        "build_semantic_acceptance_prompt.py", "stage_o_runner_phase_sa_precheck"
    )
    process = _process_from_state(state)
    round_root = Path(state["config"]["round_root"])
    allocations: dict[str, dict[str, Any]] = {}
    allocated_paths: set[str] = set()
    for actor in actors:
        allocation = _preallocate_actor(state, actor, process)
        for key in ("jsonl_path", "stderr_path", "launch_record_path", "scratch_dir"):
            normalized = os.path.normcase(str(allocation[key]))
            if normalized in allocated_paths:
                raise RunnerError("phase preallocation reuses one external path")
            allocated_paths.add(normalized)
        allocations[actor] = allocation

    def effect() -> dict[str, Any]:
        # View publication and prompt verification are intentionally ordered:
        # they are local and cheap, while the expensive clean model processes
        # are launched concurrently by launch-phase.
        prepared = {
            actor: _execute_prepare_actor(state, actor, allocations[actor])
            for actor in actors
        }
        return {"actors": prepared}

    return _transaction(
        event_root,
        state,
        base="PREPARE_PHASE",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={"allocations": allocations},
        effect=effect,
    )


def command_launch_phase(args: argparse.Namespace) -> dict[str, Any]:
    """Launch all actors in the current R/AI or SA phase concurrently."""

    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    actors = _current_phase_actors(state)
    if not actors or not _phase_all(state, "PREPARED"):
        raise RunnerError("launch-phase requires a wholly PREPARED current phase")

    def effect() -> dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor

        # The event chain has one phase-level BEGIN, so concurrent workers do
        # not race for transition tokens.  Each worker has a disjoint view,
        # scratch, prompt, JSONL, stderr, and launch-record allocation.
        with ThreadPoolExecutor(max_workers=len(actors), thread_name_prefix="stage-o") as pool:
            futures = {
                actor: pool.submit(_execute_launch_actor, state, actor) for actor in actors
            }
            receipts = {actor: futures[actor].result() for actor in actors}
        return {"receipts": receipts}

    return _transaction(
        event_root,
        state,
        base="LAUNCH_PHASE",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_promote_phase(args: argparse.Namespace) -> dict[str, Any]:
    """Promote all receipt-bound outputs in the current phase."""

    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    actors = _current_phase_actors(state)
    if not actors or not _phase_all(state, "LAUNCHED"):
        raise RunnerError("promote-phase requires a wholly LAUNCHED current phase")

    def effect() -> dict[str, Any]:
        # Promotions are ordered because they mutate one finalized round.  The
        # expensive model work has already completed in parallel.
        promotions = {
            actor: _execute_promote_actor(state, actor) for actor in actors
        }
        return {"promotions": promotions}

    return _transaction(
        event_root,
        state,
        base="PROMOTE_PHASE",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def _run_python_gate(command: list[str], cwd: Path, expected_first: str) -> tuple[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    first = next((line.strip() for line in completed.stdout.splitlines() if line.strip()), "")
    if completed.returncode != 0 or first != expected_first:
        raise RunnerError(
            f"Stage-O gate failed: exit={completed.returncode}; first={first!r}; "
            f"tail={completed.stdout[-4000:]!r}"
        )
    return completed.stdout, sha256_bytes(completed.stdout.encode("utf-8"))


def command_close_sa_set(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    if (
        state["sa_set_closed"]
        or not _current_phase_actors(state)
        or not all(actor.startswith("SA-") for actor in _current_phase_actors(state))
        or not _phase_all(state, "PROMOTED")
    ):
        raise RunnerError("SA set is not ready to close")

    def effect() -> dict[str, Any]:
        round_root = Path(state["config"]["round_root"])
        script = Path(state["config"]["skill_root"]) / "scripts" / "materialize_semantic_acceptance_gate.py"
        _stdout, _stdout_hash = _run_python_gate(
            [state["config"]["python_executable"], "-B", str(script), str(round_root)],
            round_root,
            "MATERIALIZED",
        )
        materializer = _load_module(
            "materialize_semantic_acceptance_gate.py", "stage_o_runner_sa_gate_name"
        )
        gate = require_regular(round_root / materializer.GATE_FILE, "semantic-acceptance gate")
        return {"gate_path": str(gate), "gate_sha256": sha256_file(gate)}

    return _transaction(
        event_root,
        state,
        base="CLOSE_SA_SET",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_retire_rules(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    if _current_phase_actors(state) or state["rules_retired"]:
        raise RunnerError("rule retirement is not ready")

    def effect() -> dict[str, Any]:
        manager = _load_module("manage_stage_o_workspace.py", "stage_o_runner_retire")
        destination = Path(state["config"]["retirement_root"])
        result = manager.command_retire_round(
            argparse.Namespace(
                skill_root=Path(state["config"]["skill_root"]),
                round_root=Path(state["config"]["round_root"]),
                destination=destination,
            )
        )
        manifest = require_regular(destination / "retirement-manifest.json", "retirement manifest")
        return {"destination": result["destination"], "manifest_sha256": sha256_file(manifest)}

    return _transaction(
        event_root,
        state,
        base="RETIRE_RULES",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_finalize(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    if not state["rules_retired"] or state["finalized"]:
        raise RunnerError("final bundle validation is not ready")
    report = Path(state["config"]["round_root"]) / "95-bundle-validation.md"
    if os.path.lexists(report):
        raise RunnerError("final validation report exists before finalization")

    def effect() -> dict[str, Any]:
        round_root = Path(state["config"]["round_root"])
        script = Path(state["config"]["skill_root"]) / "scripts" / "validate_review_bundle.py"
        stdout, stdout_hash = _run_python_gate(
            [
                state["config"]["python_executable"],
                "-B",
                str(script),
                str(round_root),
                "--write-report",
                str(report),
            ],
            round_root,
            "# Mechanical thesis-review bundle validation",
        )
        if "- Result: **PASS**" not in stdout:
            raise RunnerError("full bundle validator did not report PASS")
        require_regular(report, "final validation report")
        return {
            "validation_report_path": str(report),
            "validation_report_sha256": sha256_file(report),
            "validator_stdout_sha256": stdout_hash,
            "round_tree_sha256": closed_tree_commitment(round_root),
        }

    return _transaction(
        event_root,
        state,
        base="FINALIZE",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_authorize_delivery(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    if not state["finalized"] or state["delivery_authorized"]:
        raise RunnerError("delivery cannot be authorized in the current state")

    def effect() -> dict[str, Any]:
        config = state["config"]
        round_root = Path(config["round_root"])
        validation_path = Path(state["validation"]["validation_report_path"])
        validation_hash = sha256_file(validation_path)
        if validation_hash != state["validation"]["validation_report_sha256"]:
            raise RunnerError("final validation report changed before delivery authorization")
        round_tree_hash = closed_tree_commitment(round_root)
        if round_tree_hash != state["validation"]["round_tree_sha256"]:
            raise RunnerError("finalized round tree changed before delivery authorization")
        summary = require_regular(round_root / "93-user-facing-summary.md", "Stage-S summary")
        process = _process_from_state(state)
        frozen = require_regular(round_root / str(process["frozen_pdf_file"]), "frozen thesis PDF")
        frozen_hash = sha256_file(frozen)
        if frozen_hash != require_hash(process["selected_pdf_sha256"], "selected PDF SHA-256"):
            raise RunnerError("frozen PDF changed before delivery authorization")
        return {
            "summary_path": str(summary),
            "summary_sha256": sha256_file(summary),
            "validation_report_sha256": validation_hash,
            "frozen_pdf_sha256": frozen_hash,
            "round_tree_sha256": round_tree_hash,
        }

    return _transaction(
        event_root,
        state,
        base="AUTHORIZE_DELIVERY",
        actor=None,
        expected_token=args.expected_transition_token,
        begin_payload={},
        effect=effect,
    )


def command_quarantine(args: argparse.Namespace) -> dict[str, Any]:
    event_root, state = _state_for_command(args.run_root, args.expected_transition_token)
    final, _destination = _perform_quarantine(
        event_root,
        state,
        reason=str(args.reason),
        expected_token=args.expected_transition_token,
    )
    return final


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    _event_root, state = _state_for_command(args.run_root)
    return state


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--run-root", type=Path, required=True)
    bootstrap.add_argument("--skill-root", type=Path, default=SKILL_ROOT)
    bootstrap.add_argument("--prompt-plan-dir", type=Path, required=True)
    bootstrap.add_argument("--control-root", type=Path, required=True)
    bootstrap.add_argument("--scratch-root", type=Path, required=True)
    bootstrap.add_argument("--retirement-root", type=Path, required=True)
    bootstrap.add_argument("--python-executable", type=Path, required=True)
    bootstrap.add_argument("--codex-executable", type=Path, required=True)
    bootstrap.set_defaults(func=command_bootstrap)

    status = subparsers.add_parser("status")
    status.add_argument("--run-root", type=Path, required=True)
    status.set_defaults(func=command_status)

    for name, function in (
        ("prepare-phase", command_prepare_phase),
        ("launch-phase", command_launch_phase),
        ("promote-phase", command_promote_phase),
    ):
        command = subparsers.add_parser(name)
        command.add_argument("--run-root", type=Path, required=True)
        command.add_argument("--expected-transition-token", required=True)
        command.set_defaults(func=function)

    for name, function in (
        ("close-sa-set", command_close_sa_set),
        ("retire-rules", command_retire_rules),
        ("finalize", command_finalize),
        ("authorize-delivery", command_authorize_delivery),
    ):
        command = subparsers.add_parser(name)
        command.add_argument("--run-root", type=Path, required=True)
        command.add_argument("--expected-transition-token", required=True)
        command.set_defaults(func=function)

    quarantine = subparsers.add_parser("quarantine")
    quarantine.add_argument("--run-root", type=Path, required=True)
    quarantine.add_argument("--expected-transition-token", required=True)
    quarantine.add_argument("--reason", required=True)
    quarantine.set_defaults(func=command_quarantine)
    return parser.parse_args(argv)


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state)
    config = result.get("config")
    if isinstance(config, dict):
        # Plan receipts remain visible for mechanical audit, but do not copy
        # prompt bytes or any substantive artifact into status output.
        result["next_actor"] = _current_actor(result)
        result["current_phase_actors"] = _current_phase_actors(result)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parse_args(sys.argv[1:] if argv is None else argv)
        state = arguments.func(arguments)
    except RunnerError as exc:
        print("ERROR")
        print(str(exc))
        return 2
    print("PASS")
    print(json.dumps(_public_state(state), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
