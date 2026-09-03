#!/usr/bin/env python3
"""Launch one process-bound clean thesis-review actor through Codex CLI.

The launcher fixes a UUID, exact prompt bytes, executable bytes, argv, cwd,
workspace, PID, JSONL path, and a crash-evident closed launch record before it
sends stdin.  It later completes that same record and requires the canonical
transport validator to pass.  A nonzero result invalidates the complete retry;
this helper never edits a thesis artifact or retries an actor in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, BinaryIO


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from manage_stage_o_workspace import (  # noqa: E402
    C_OUTPUTS,
    ContractError,
    S_OUTPUTS,
    absolute_local_path,
    boundaries_overlap,
    canonical_clean_actor_inputs,
    canonical_general_actor_inputs,
    closed_view_snapshot,
    directory_empty,
    file_identity,
    general_actor_outputs,
    input_commitment,
    load_module,
    read_json_object,
    require_directory,
    require_regular,
    sha256_file,
)


SCHEMA = "thesis-review-actor-launch-v3"
ACTOR_RE = re.compile(
    r"(?:P|H(?:0[1-9]|[1-9][0-9])|R[1-5]|AI|SA-(?:R[1-5]|AI)|C|S|V)\Z"
)
NO_PUBLIC_NETWORK_ACTOR_RE = re.compile(r"(?:H(?:0[1-9]|[1-9][0-9])|AI|S|V)\Z")
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
ZERO_HASH = "0" * 64
SENTINEL_EXIT = -2147483648


def exact_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def stream_sha256(handle: BinaryIO) -> str:
    position = handle.tell()
    try:
        handle.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest().upper()
    finally:
        handle.seek(position)


def read_stream_bytes(handle: BinaryIO) -> bytes:
    position = handle.tell()
    try:
        handle.seek(0)
        return handle.read()
    finally:
        handle.seek(position)


def acquire_read_leases(paths: list[Path]) -> tuple[str, list[Any]]:
    """Hold read-only leases that deny concurrent writes/deletes on Windows.

    The thesis-review production runner is Windows-local.  Keeping these
    handles open across the actor process closes the preflight/postflight
    swap-and-restore window for every declared input.  Other platforms retain
    open read handles as a best-effort portability fallback; production claims
    must not treat that fallback as a mandatory OS lock.
    """

    canonical: list[Path] = []
    seen: set[str] = set()
    for index, path in enumerate(paths):
        item = require_regular(path, f"read lease[{index}]")
        key = os.path.normcase(str(item))
        if key in seen:
            continue
        seen.add(key)
        canonical.append(item)

    handles: list[Any] = []
    if os.name != "nt":  # pragma: no cover - production runner is Windows-local
        try:
            for item in canonical:
                handles.append(item.open("rb"))
        except Exception:
            release_read_leases(("portable", handles))
            raise
        return "portable", handles

    import ctypes
    from ctypes import wintypes

    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    open_reparse_point = 0x00200000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    invalid_handle = ctypes.c_void_p(-1).value
    try:
        for item in canonical:
            handle = create_file(
                str(item),
                generic_read,
                file_share_read,
                None,
                open_existing,
                open_reparse_point,
                None,
            )
            if handle in (None, invalid_handle):
                raise ContractError(
                    f"cannot acquire immutable actor-input lease for {item}: "
                    f"Windows error {ctypes.get_last_error()}"
                )
            handles.append(int(handle))
    except Exception:
        release_read_leases(("windows", handles))
        raise
    return "windows", handles


def release_read_leases(lease_set: tuple[str, list[Any]]) -> None:
    mode, handles = lease_set
    if mode == "windows":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for handle in reversed(handles):
            kernel32.CloseHandle(ctypes.c_void_p(int(handle)))
    else:
        for handle in reversed(handles):
            try:
                handle.close()
            except OSError:
                pass


def write_record(handle: BinaryIO, record: dict[str, Any]) -> None:
    payload = exact_json_bytes(record)
    handle.seek(0)
    handle.truncate(0)
    handle.write(payload)
    handle.flush()
    os.fsync(handle.fileno())


def canonical_actor(value: str) -> str:
    actor = value.strip().upper()
    if ACTOR_RE.fullmatch(actor) is None:
        raise ContractError(f"invalid process-bound actor ID: {value!r}")
    return actor


def require_private_actor_workspace(workspace: Path, actor: str) -> Path:
    """Require the exact ``<run>/views/<actor>`` launch boundary.

    This is deliberately enforced by the trusted launcher rather than left to
    prose.  In particular, a finalized ``round/`` directory can never be
    substituted for a closed actor view.
    """

    if workspace.name != actor:
        raise ContractError(
            "actor workspace basename must exactly match the process-bound actor ID"
        )
    views_root = require_directory(workspace.parent, "actor views root")
    if views_root.name != "views":
        raise ContractError(
            "actor workspace must be a direct child of the run's views directory"
        )
    run_root = require_directory(views_root.parent, "actor run root")
    require_directory(run_root / "round", "actor run round directory")
    require_directory(run_root / "orchestration", "actor run orchestration directory")
    return run_root


def verify_process_seal_binding(
    run_root: Path, expected_process_sha256: str, expected_seal_sha256: str
) -> dict[str, Any]:
    retry = load_module(
        SCRIPT_ROOT / "manage_review_retry.py",
        "thesis_review_launcher_retry_contract",
    )
    try:
        result = retry.verify_process_seal(
            argparse.Namespace(
                workspace=run_root.parent,
                run_root=run_root,
                expected_process_sha256=expected_process_sha256,
                expected_seal_sha256=expected_seal_sha256,
            )
        )
    except Exception as exc:
        raise ContractError(f"sealed process verification failed: {exc}") from exc
    if (
        str(result.get("process_sha256", "")).upper() != expected_process_sha256
        or str(result.get("seal_sha256", "")).upper() != expected_seal_sha256
    ):
        raise ContractError("sealed process verification returned mismatched anchors")
    return result


def actor_view_contract(
    workspace: Path, actor: str, process: dict[str, Any]
) -> tuple[list[str], list[str]]:
    if actor == "P" or actor == "AI" or re.fullmatch(r"R[1-5]", actor):
        opened, _instructions = canonical_general_actor_inputs(
            workspace, process, actor
        )
        return opened, general_actor_outputs(process, actor)
    if actor in {"C", "S"}:
        opened, _data, _instructions = canonical_clean_actor_inputs(
            workspace, process, actor
        )
        return opened, list(C_OUTPUTS if actor == "C" else S_OUTPUTS)
    if actor.startswith("SA-"):
        target = actor[3:]
        semantic = load_module(
            SCRIPT_ROOT / "build_semantic_acceptance_prompt.py",
            "thesis_review_launcher_semantic_contract",
        )
        projected = semantic.stable_process_projection(process)
        opened = semantic.algorithmic_opened_inputs(projected, target)
        output_paths = semantic.private_output_paths(workspace, target)
        return opened, [path.relative_to(workspace).as_posix() for path in output_paths]
    raise ContractError(
        "canonical launcher workspace binding currently supports only "
        "P, R1..R5, AI, SA-R1..SA-R5, SA-AI, C, and S"
    )


def actor_input_commitment(
    workspace: Path, actor: str, opened: list[str]
) -> str:
    """Recompute an actor input anchor with the actor's canonical schema.

    Semantic-acceptance actors bind a stronger envelope than the general
    Stage-O actors.  The runner and launcher must select the same schema at
    every preflight, lease, and postflight check; otherwise identical SA input
    bytes produce incomparable digests.
    """

    if actor.startswith("SA-"):
        semantic = load_module(
            SCRIPT_ROOT / "build_semantic_acceptance_prompt.py",
            "thesis_review_launcher_semantic_input_commitment",
        )
        result = semantic.capture_opened_input_commitment(workspace, opened)
        if not isinstance(result, dict):
            raise ContractError("SA input commitment builder returned a non-object")
        return canonical_hash(
            str(result.get("sha256", "")), "SA actor-view input commitment SHA-256"
        )
    return input_commitment(workspace, opened)


def preflight_actor_workspace_binding(
    workspace: Path,
    run_root: Path,
    actor: str,
    prompt_sha256: str,
    expected_process_sha256: str,
    expected_seal_sha256: str,
    expected_input_commitment_sha256: str,
) -> dict[str, Any]:
    process_path = require_regular(
        workspace / "00-process-parameters.json", "actor-view process envelope"
    )
    process_identity = file_identity(process_path)
    if process_identity[4] != expected_process_sha256:
        raise ContractError("actor-view process bytes differ from the external anchor")
    process = read_json_object(process_path, "actor-view process envelope")
    prompt_map = process.get("actor_prompt_sha256")
    if not isinstance(prompt_map, dict) or str(prompt_map.get(actor, "")).upper() != prompt_sha256:
        raise ContractError(
            "bound prompt SHA-256 does not match actor_prompt_sha256 in the sealed process"
        )
    verify_process_seal_binding(
        run_root, expected_process_sha256, expected_seal_sha256
    )
    opened, outputs = actor_view_contract(workspace, actor, process)
    validator = load_module(
        SCRIPT_ROOT / "validate_review_bundle.py",
        "thesis_review_launcher_view_closure",
    )
    prelaunch_tree = closed_view_snapshot(workspace, opened, validator)
    commitment = actor_input_commitment(workspace, actor, opened)
    if commitment != expected_input_commitment_sha256:
        raise ContractError(
            "actor-view input commitment differs from the external staging anchor"
        )
    return {
        "process": process,
        "actor": actor,
        "process_identity": process_identity,
        "opened": opened,
        "outputs": outputs,
        "prelaunch_tree": prelaunch_tree,
        "validator": validator,
        "input_commitment_sha256": commitment,
        "expected_process_sha256": expected_process_sha256,
        "expected_seal_sha256": expected_seal_sha256,
        "workspace": workspace,
        "run_root": run_root,
    }


def postflight_actor_workspace_binding(binding: dict[str, Any]) -> None:
    workspace = binding["workspace"]
    run_root = binding["run_root"]
    opened = binding["opened"]
    outputs = binding["outputs"]
    if file_identity(workspace / "00-process-parameters.json") != binding["process_identity"]:
        raise ContractError("actor-view process identity or bytes changed across launch")
    if (
        actor_input_commitment(workspace, binding["actor"], opened)
        != binding["input_commitment_sha256"]
    ):
        raise ContractError("actor-view input commitment changed across launch")
    closed_view_snapshot(
        workspace, [*opened, *outputs], binding["validator"]
    )
    verify_process_seal_binding(
        run_root,
        binding["expected_process_sha256"],
        binding["expected_seal_sha256"],
    )


def terminal_output_commitment(binding: dict[str, Any]) -> str:
    """Bind exact terminal output paths, identities, metadata, and bytes."""

    return input_commitment(binding["workspace"], binding["outputs"])


def acquire_actor_input_leases(
    binding: dict[str, Any], prompt: Path, executable: Path, validator: Path
) -> tuple[str, list[Any]]:
    workspace = binding["workspace"]
    paths = [
        *(workspace / Path(relative) for relative in binding["opened"]),
        prompt,
        executable,
        validator,
    ]
    return acquire_read_leases(paths)


def verify_actor_input_leases(binding: dict[str, Any]) -> None:
    """Recheck the whole input tree only after every deny-write lease is held."""

    current = closed_view_snapshot(
        binding["workspace"], binding["opened"], binding["validator"]
    )
    if current != binding["prelaunch_tree"]:
        raise ContractError("actor inputs changed while immutable leases were acquired")
    if (
        actor_input_commitment(
            binding["workspace"], binding["actor"], binding["opened"]
        )
        != binding["input_commitment_sha256"]
    ):
        raise ContractError("actor input commitment changed before process creation")


def canonical_hash(value: str, label: str) -> str:
    digest = value.strip().upper()
    if HEX64_RE.fullmatch(digest) is None:
        raise ContractError(f"{label} must be one 64-hex SHA-256")
    return digest


def actor_forbids_public_network(actor: str) -> bool:
    return NO_PUBLIC_NETWORK_ACTOR_RE.fullmatch(actor) is not None


def validate_external_control_paths(
    workspace: Path,
    cwd: Path,
    prompt: Path,
    log: Path,
    stderr: Path,
    record: Path,
    executable: Path,
    validator: Path,
) -> None:
    paths = [prompt, log, stderr, record, executable, validator]
    if os.name == "nt":
        drive_keys = {
            os.path.normcase(os.path.splitdrive(str(path))[0])
            for path in (workspace, cwd, *paths)
        }
        if len(drive_keys) != 1:
            raise ContractError(
                "workspace, scratch, prompt, logs, record, and executable must "
                "use one local drive-letter namespace"
            )
    spellings = [os.path.normcase(os.path.abspath(str(path))) for path in paths]
    if len(spellings) != len(set(spellings)):
        raise ContractError(
            "prompt, JSONL, stderr, launch record, executable, and canonical "
            "transport validator must be distinct"
        )
    if boundaries_overlap(workspace, cwd):
        raise ContractError("actor workspace and private scratch cwd must not overlap")
    for path, label in (
        (prompt, "prompt"),
        (log, "JSONL"),
        (stderr, "stderr"),
        (record, "launch record"),
    ):
        if boundaries_overlap(path, workspace):
            raise ContractError(f"{label} must remain outside the actor workspace")
        if boundaries_overlap(path, cwd):
            raise ContractError(f"{label} must remain outside the private scratch cwd")


def canonical_launch_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as exc:
        raise ContractError("launch ID must be one canonical UUID") from exc
    canonical = str(parsed)
    if value != canonical:
        raise ContractError("launch ID must use lowercase canonical UUID spelling")
    return canonical


def read_record_from_handle(handle: BinaryIO) -> dict[str, Any]:
    try:
        value = json.loads(read_stream_bytes(handle).decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("launch record changed into invalid JSON") from exc
    if not isinstance(value, dict):
        raise ContractError("launch record changed into a non-object")
    return value


def build_argv(
    executable: Path,
    workspace: Path,
    *,
    search: bool,
) -> list[str]:
    argv = [str(executable)]
    if search:
        argv.append("--search")
    argv.extend(
        [
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--approve-for-me",
            "--disable",
            "multi_agent",
            "--skip-git-repo-check",
        ]
    )
    argv.extend(["-C", str(workspace), "-"])
    return argv


def parse_thread_id(log_bytes: bytes) -> str:
    try:
        text = log_bytes.decode("utf-8", errors="strict")
    except UnicodeError:
        return ""
    first = text.splitlines()[0] if text.splitlines() else ""
    if not first:
        return ""
    try:
        event = json.loads(first)
    except json.JSONDecodeError:
        return ""
    if not isinstance(event, dict) or event.get("type") != "thread.started":
        return ""
    thread_id = event.get("thread_id")
    return thread_id if isinstance(thread_id, str) and thread_id.strip() else ""


def transport_gate(
    validator: Path,
    log: Path,
    actor: str,
    record: Path,
    prompt_sha256: str,
    launch_id: str,
    process_sha256: str,
    process_seal_sha256: str,
    input_commitment_sha256: str,
    output_commitment_sha256: str,
    launch_record_sha256: str,
) -> tuple[list[str], str]:
    command = [
        sys.executable,
        "-B",
        str(validator),
        "--log",
        str(log),
        "--actor",
        actor,
        "--launch-record",
        str(record),
        "--expected-prompt-sha256",
        prompt_sha256,
        "--expected-launch-id",
        launch_id,
        "--expected-process-sha256",
        process_sha256,
        "--expected-process-seal-sha256",
        process_seal_sha256,
        "--expected-input-commitment-sha256",
        input_commitment_sha256,
        "--expected-output-commitment-sha256",
        output_commitment_sha256,
        "--expected-launch-record-sha256",
        launch_record_sha256,
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(record.parent),
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
            "actor transport validation failed; quarantine the complete retry: "
            f"exit={completed.returncode}; first={first!r}; "
            f"tail={completed.stdout[-4000:]!r}"
        )
    return command, completed.stdout


def launch(args: argparse.Namespace) -> dict[str, Any]:
    actor = canonical_actor(args.actor)
    if bool(args.search) and actor_forbids_public_network(actor):
        raise ContractError(
            f"actor {actor} has public_endpoints=[none] and cannot enable --search"
        )
    expected_prompt_sha256 = canonical_hash(
        args.expected_prompt_sha256, "expected prompt SHA-256"
    )
    expected_process_sha256 = canonical_hash(
        args.expected_process_sha256, "expected process SHA-256"
    )
    expected_seal_sha256 = canonical_hash(
        args.expected_process_seal_sha256, "expected process-seal SHA-256"
    )
    expected_input_commitment_sha256 = canonical_hash(
        args.expected_input_commitment_sha256,
        "expected actor-view input commitment SHA-256",
    )
    executable = require_regular(args.codex_executable, "Codex executable")
    if executable.name.casefold() not in {"codex", "codex.exe"}:
        raise ContractError("Codex executable basename must be codex or codex.exe")
    prompt = require_regular(args.prompt, "bound operational prompt")
    workspace = require_directory(args.workspace, "actor workspace")
    run_root = require_private_actor_workspace(workspace, actor)
    cwd = require_directory(args.cwd, "private scratch cwd")
    if boundaries_overlap(cwd, run_root):
        raise ContractError("private scratch cwd must remain outside the complete run root")
    directory_empty(cwd, "private scratch cwd before actor launch")
    canonical_validator = require_regular(
        SCRIPT_ROOT / "validate_actor_transport.py",
        "canonical transport validator",
    )
    requested_validator = require_regular(
        getattr(args, "transport_validator", canonical_validator),
        "transport validator",
    )
    if requested_validator != canonical_validator:
        raise ContractError(
            "transport validator is fixed to the canonical checked-in script"
        )
    validator = canonical_validator
    validator_identity_before = file_identity(validator)
    closure_validator = load_module(
        SCRIPT_ROOT / "validate_review_bundle.py",
        "thesis_review_launcher_scratch_closure",
    )
    closed_view_snapshot(cwd, [], closure_validator)
    jsonl = absolute_local_path(args.jsonl, "JSONL output", must_exist=False)
    stderr = absolute_local_path(args.stderr, "stderr output", must_exist=False)
    record = absolute_local_path(args.launch_record, "launch record", must_exist=False)
    for path, label in (
        (jsonl, "JSONL parent"),
        (stderr, "stderr parent"),
        (record, "launch-record parent"),
    ):
        require_directory(path.parent, label)
        if os.path.lexists(path):
            raise ContractError(f"refusing to overwrite launch output: {path}")
    validate_external_control_paths(
        workspace, cwd, prompt, jsonl, stderr, record, executable, validator
    )

    prompt_identity_before = file_identity(prompt)
    executable_identity_before = file_identity(executable)
    with prompt.open("rb") as prompt_handle, executable.open("rb") as executable_handle:
        prompt_bytes = prompt_handle.read()
        prompt_sha256 = hashlib.sha256(prompt_bytes).hexdigest().upper()
        executable_sha256 = stream_sha256(executable_handle)
        if prompt_sha256 != expected_prompt_sha256:
            raise ContractError(
                "prompt bytes no longer match the externally retained builder hash"
            )
        if executable_sha256 != executable_identity_before[4]:
            raise ContractError("Codex executable changed while binding the launch")

        actor_binding = preflight_actor_workspace_binding(
            workspace,
            run_root,
            actor,
            prompt_sha256,
            expected_process_sha256,
            expected_seal_sha256,
            expected_input_commitment_sha256,
        )

        launch_id = canonical_launch_id(args.launch_id)
        argv = build_argv(
            executable,
            workspace,
            search=bool(args.search),
        )
        argv_sha256 = hashlib.sha256(exact_json_bytes(argv)).hexdigest().upper()
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        process: subprocess.Popen[bytes] | None = None
        with jsonl.open("xb+") as log_handle, stderr.open("xb+") as stderr_handle, record.open(
            "xb+"
        ) as record_handle:
            lease_set: tuple[str, list[Any]] | None = None
            try:
                lease_set = acquire_actor_input_leases(
                    actor_binding, prompt, executable, validator
                )
                verify_actor_input_leases(actor_binding)
                process = subprocess.Popen(
                    argv,
                    executable=str(executable),
                    cwd=str(cwd),
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=log_handle,
                    stderr=stderr_handle,
                    shell=False,
                )
                if process.stdin is None:
                    raise ContractError("Codex process has no writable stdin")
                launch_record: dict[str, Any] = {
                    "schema": SCHEMA,
                    "actor": actor,
                    "launch_id": launch_id,
                    "prompt_path": str(prompt),
                    "prompt_bytes": len(prompt_bytes),
                    "prompt_sha256": prompt_sha256,
                    "process_sha256": expected_process_sha256,
                    "process_seal_sha256": expected_seal_sha256,
                    "input_commitment_sha256": expected_input_commitment_sha256,
                    "output_commitment_sha256": ZERO_HASH,
                    "executable_path": str(executable),
                    "executable_sha256": executable_sha256,
                    "argv": argv,
                    "argv_sha256": argv_sha256,
                    "cwd": str(cwd),
                    "workspace": str(workspace),
                    "pid": int(process.pid),
                    "exit_code": SENTINEL_EXIT,
                    "log_path": str(jsonl),
                    "log_bytes": 0,
                    "log_sha256": ZERO_HASH,
                    "thread_id": "",
                }
                write_record(record_handle, launch_record)
                if read_record_from_handle(record_handle) != launch_record:
                    raise ContractError(
                        "pending launch record did not remain byte-equivalent before stdin"
                    )
                if file_identity(prompt) != prompt_identity_before:
                    raise ContractError("bound prompt changed before stdin dispatch")
                if file_identity(executable) != executable_identity_before:
                    raise ContractError("Codex executable changed before stdin dispatch")
                if stream_sha256(prompt_handle) != prompt_sha256:
                    raise ContractError("open prompt handle changed before stdin dispatch")
                if stream_sha256(executable_handle) != executable_sha256:
                    raise ContractError("open executable handle changed before stdin dispatch")
                print(
                    f"STARTED actor={actor} pid={process.pid} launch_id={launch_id}",
                    flush=True,
                )
                process.stdin.write(prompt_bytes)
                process.stdin.flush()
                process.stdin.close()
                return_code = int(process.wait())
                postflight_actor_workspace_binding(actor_binding)
                closed_view_snapshot(cwd, [], closure_validator)
                output_commitment_sha256 = terminal_output_commitment(actor_binding)
                log_handle.flush()
                stderr_handle.flush()
                os.fsync(log_handle.fileno())
                os.fsync(stderr_handle.fileno())
                log_bytes = read_stream_bytes(log_handle)
                if read_record_from_handle(record_handle) != launch_record:
                    raise ContractError(
                        "pending launch record was modified while the actor was running"
                    )
                launch_record["exit_code"] = return_code
                launch_record["log_bytes"] = len(log_bytes)
                launch_record["log_sha256"] = hashlib.sha256(log_bytes).hexdigest().upper()
                launch_record["thread_id"] = parse_thread_id(log_bytes)
                launch_record[
                    "output_commitment_sha256"
                ] = output_commitment_sha256
                write_record(record_handle, launch_record)
            except Exception:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
                raise
            finally:
                if lease_set is not None:
                    release_read_leases(lease_set)

    if file_identity(prompt) != prompt_identity_before:
        raise ContractError("bound prompt changed across actor launch")
    if file_identity(executable) != executable_identity_before:
        raise ContractError("Codex executable changed across actor launch")
    if file_identity(validator) != validator_identity_before:
        raise ContractError("canonical transport validator changed across actor launch")
    launch_record_sha256 = sha256_file(record)
    gate_command, gate_stdout = transport_gate(
        validator,
        jsonl,
        actor,
        record,
        expected_prompt_sha256,
        launch_id,
        expected_process_sha256,
        expected_seal_sha256,
        expected_input_commitment_sha256,
        output_commitment_sha256,
        launch_record_sha256,
    )
    postflight_actor_workspace_binding(actor_binding)
    closed_view_snapshot(cwd, [], closure_validator)
    if terminal_output_commitment(actor_binding) != output_commitment_sha256:
        raise ContractError("actor outputs changed across the transport gate")
    if sha256_file(record) != launch_record_sha256:
        raise ContractError("launch record changed across the transport gate")
    if file_identity(validator) != validator_identity_before:
        raise ContractError("canonical transport validator changed across its gate")
    final_record = json.loads(record.read_text(encoding="utf-8"))
    return {
        "operation": "launch-review-actor",
        "actor": actor,
        "launch_id": launch_id,
        "pid": final_record["pid"],
        "thread_id": final_record["thread_id"],
        "exit_code": final_record["exit_code"],
        "prompt_sha256": expected_prompt_sha256,
        "process_sha256": expected_process_sha256,
        "process_seal_sha256": expected_seal_sha256,
        "input_commitment_sha256": expected_input_commitment_sha256,
        "output_commitment_sha256": output_commitment_sha256,
        "launch_record_sha256": launch_record_sha256,
        "jsonl_sha256": final_record["log_sha256"],
        "launch_record": str(record),
        "transport_gate_command": gate_command,
        "transport_gate_first_line": next(
            line for line in gate_stdout.splitlines() if line.strip()
        ),
        "status": "PASS",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--expected-prompt-sha256", required=True)
    parser.add_argument("--expected-process-sha256", required=True)
    parser.add_argument("--expected-process-seal-sha256", required=True)
    parser.add_argument("--expected-input-commitment-sha256", required=True)
    parser.add_argument("--launch-id", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--launch-record", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--search", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = launch(arguments)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(
            "ERROR: actor launch failed; quarantine the complete retry: "
            f"{exc}",
            file=sys.stderr,
        )
        return 3
    print("PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
