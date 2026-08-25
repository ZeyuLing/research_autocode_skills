from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from _common import load_json, resolve_study_root, sha256_file, sha256_text, update_json, utc_now, write_json


PARENT_SUCCESS = {"DONE"}
RUNNABLE_STATES = {"PLANNED", "PREFLIGHT", "SMOKE"}
RETRYABLE_STATES = {"FAILED_ENGINEERING", "CANCELLED"}


def find_node(graph: dict[str, Any], experiment_id: str) -> dict[str, Any]:
    for node in graph.get("nodes", []):
        if node.get("id") == experiment_id:
            return node
    raise KeyError(f"Experiment not found: {experiment_id}")


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def resolve_run_output(run_dir: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"Expected output must be relative to the run directory: {value}")
    path = (run_dir / relative).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Expected output escapes run directory: {value}") from exc
    return path


def verify_protected(root: Path) -> list[str]:
    protected_path = root / "protocols" / "protected_hashes.json"
    if not protected_path.is_file():
        return []
    protected = load_json(protected_path)
    errors = []
    for entry in protected.get("paths", []):
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not relative or not expected:
            errors.append(f"Malformed protected-path entry: {entry}")
            continue
        actual_path = resolve_path(root, relative)
        if not actual_path.is_file():
            errors.append(f"Protected file missing: {relative}")
        elif sha256_file(actual_path) != expected:
            errors.append(f"Protected file hash changed: {relative}")
    return errors


def code_snapshot(code_repo: Path | None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"path": str(code_repo) if code_repo else None}
    if not code_repo or not (code_repo / ".git").exists():
        snapshot["git"] = None
        return snapshot
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=code_repo, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=code_repo, capture_output=True, text=True, check=True, timeout=10
        ).stdout.splitlines()
        snapshot["git"] = {"commit": commit, "dirty": bool(dirty), "changed_path_count": len(dirty)}
    except (OSError, subprocess.SubprocessError) as exc:
        snapshot["git"] = {"error": str(exc)}
    return snapshot


def resolve_command(command: list[str], mapping: dict[str, str]) -> list[str]:
    if not command or not all(isinstance(item, str) for item in command):
        raise ValueError("Adapter commands must be non-empty JSON arrays of strings")
    resolved = []
    for item in command:
        for key, value in mapping.items():
            item = item.replace("{" + key + "}", value)
        resolved.append(item)
    return resolved


def update_node(root: Path, experiment_id: str, status: str, *, run_id: str | None = None, reason: str = "") -> None:
    graph_path = root / "experiments" / "experiment_graph.json"

    def updater(graph: dict[str, Any]) -> dict[str, Any]:
        node = find_node(graph, experiment_id)
        node["status"] = status
        node["updated_at"] = utc_now()
        if reason:
            node["status_reason"] = reason
        if run_id:
            node.setdefault("runs", []).append(run_id)
        return graph

    update_json(graph_path, updater)


def run_command(command: list[str], cwd: Path, env: dict[str, str], stdout_path: Path, stderr_path: Path, timeout: int) -> int:
    with stdout_path.open("a", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
        "a", encoding="utf-8", newline="\n"
    ) as stderr:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout or None,
            check=False,
            text=True,
        )
    return int(result.returncode)


def collect_hashes(run_dir: Path, relative_paths: list[str]) -> dict[str, str]:
    hashes = {}
    for relative in sorted(set(relative_paths)):
        path = resolve_run_output(run_dir, relative)
        if path.is_file():
            hashes[relative.replace("\\", "/")] = sha256_file(path)
    for fixed in (
        "config.json",
        "resolved_command.json",
        "code_snapshot.json",
        "environment.json",
        "protocol_snapshot.json",
        "data_snapshot.json",
        "stdout.log",
        "stderr.log",
    ):
        path = run_dir / fixed
        if path.is_file():
            hashes[fixed] = sha256_file(path)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one experiment node through a safe argv adapter.")
    parser.add_argument("study_root")
    parser.add_argument("experiment_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-reason", default="", help="Required when rerunning a failed or cancelled node.")
    args = parser.parse_args()

    root = resolve_study_root(args.study_root)
    study = load_json(root / "study.json")
    graph = load_json(root / "experiments" / "experiment_graph.json")
    node = find_node(graph, args.experiment_id)
    node_by_id = {item["id"]: item for item in graph.get("nodes", [])}

    node_status = node.get("status")
    if node_status in RETRYABLE_STATES and not args.retry_reason.strip():
        raise RuntimeError(f"Retrying {node_status} requires --retry-reason")
    if node_status not in RUNNABLE_STATES | RETRYABLE_STATES:
        raise RuntimeError(f"Experiment state is not runnable: {node.get('status')}")
    unsatisfied = [
        parent for parent in node.get("parents", []) if node_by_id.get(parent, {}).get("status") not in PARENT_SUCCESS
    ]
    if unsatisfied and not args.dry_run:
        raise RuntimeError(f"Unsatisfied parent experiments: {', '.join(unsatisfied)}")

    protected_errors = verify_protected(root)
    protocol_path = root / "protocols" / "protocol.json"
    current_protocol_hash = sha256_file(protocol_path) if protocol_path.is_file() else None
    planned_protocol_hash = node.get("protocol_hash")
    if planned_protocol_hash and planned_protocol_hash != current_protocol_hash:
        protected_errors.append(
            f"Frozen protocol changed after graph planning: expected {planned_protocol_hash}, got {current_protocol_hash}"
        )
    if protected_errors and not args.dry_run:
        update_node(root, args.experiment_id, "INVALID_PROTOCOL", reason="; ".join(protected_errors))
        raise RuntimeError("Protected protocol check failed: " + "; ".join(protected_errors))

    adapter_value = study.get("adapter")
    if not adapter_value:
        raise RuntimeError("study.json does not configure an adapter")
    adapter_path = resolve_path(root, adapter_value)
    adapter = load_json(adapter_path)
    adapter_hash = sha256_file(adapter_path)
    host_environment_keys = [str(key) for key in adapter.get("environment_from_host", [])]
    missing_host_environment = [key for key in host_environment_keys if key not in os.environ]
    if missing_host_environment:
        raise RuntimeError("Required host environment variables are missing: " + ", ".join(missing_host_environment))
    commands = adapter.get("commands", {})
    key = node.get("config", {}).get("command_key") or node.get("family")
    command_template = commands.get(key) or commands.get(node.get("family")) or commands.get("default")
    if not command_template:
        raise RuntimeError(f"Adapter has no command for key {key!r}, family {node.get('family')!r}, or default")

    code_repo = resolve_path(root, study["code_repo"]) if study.get("code_repo") else None
    config_path = resolve_path(root, node["config_path"])
    stamp = utc_now().replace(":", "").replace("+00:00", "Z").replace("-", "")
    run_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    run_dir = root / "runs" / args.experiment_id / run_id
    mapping = {
        "study_root": str(root),
        "run_dir": str(run_dir),
        "config_path": str(config_path),
        "experiment_id": args.experiment_id,
        "run_id": run_id,
        "seed": "" if node.get("seed") is None else str(node.get("seed")),
        "subset_seed": "" if node.get("subset_seed") is None else str(node.get("subset_seed")),
        "code_repo": "" if code_repo is None else str(code_repo),
    }
    command = resolve_command(command_template, mapping)
    evaluation = resolve_command(commands["evaluate"], mapping) if commands.get("evaluate") and key != "evaluate" else None

    working_value = str(adapter.get("working_directory") or (code_repo if code_repo else root))
    working_dir = resolve_path(root, working_value)
    if not working_dir.is_dir():
        raise FileNotFoundError(f"Adapter working directory does not exist: {working_dir}")

    required_outputs = list(
        dict.fromkeys((node.get("expected_outputs") or []) + (adapter.get("required_outputs") or []))
    )
    for relative in required_outputs:
        resolve_run_output(run_dir, relative)

    preview = {
        "experiment_id": args.experiment_id,
        "run_id": run_id,
        "command_key": key,
        "command": command,
        "evaluate": evaluation,
        "working_directory": str(working_dir),
        "config_path": str(config_path),
        "required_outputs": required_outputs,
        "unsatisfied_parents": unsatisfied,
        "protected_protocol_errors": protected_errors,
        "protocol_hash": current_protocol_hash,
        "adapter_hash": adapter_hash,
        "retry_reason": args.retry_reason,
    }
    if args.dry_run:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "config.json", load_json(config_path))
    write_json(run_dir / "resolved_command.json", preview)
    write_json(run_dir / "code_snapshot.json", code_snapshot(code_repo))
    recorded_environment_keys = list(
        dict.fromkeys([str(key) for key in adapter.get("record_environment_keys", [])] + host_environment_keys)
    )
    safe_environment = {
        "captured_at": utc_now(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "python_executable": str(Path(sys.executable).resolve()),
        "recorded_adapter_keys": {
            key: {"present": True, "value_sha256": sha256_text(os.environ[key])}
            for key in recorded_environment_keys
            if key in os.environ
        },
    }
    write_json(run_dir / "environment.json", safe_environment)
    if protocol_path.is_file():
        write_json(run_dir / "protocol_snapshot.json", load_json(protocol_path))
    data_path = root / "data" / "manifest.json"
    if data_path.is_file():
        write_json(run_dir / "data_snapshot.json", load_json(data_path))

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": args.experiment_id,
        "graph_version": graph.get("graph_version"),
        "protocol_hash": current_protocol_hash,
        "adapter_hash": adapter_hash,
        "retry_of_status": node_status if node_status in RETRYABLE_STATES else None,
        "retry_reason": args.retry_reason,
        "status": "RUNNING",
        "started_at": utc_now(),
        "finished_at": None,
        "exit_code": None,
        "failure_reason": "",
    }
    write_json(run_dir / "manifest.json", manifest)
    update_node(root, args.experiment_id, "RUNNING", run_id=run_id)

    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in adapter.get("environment", {}).items()})
    env.update(
        {
            "I2E_STUDY_ROOT": str(root),
            "I2E_RUN_DIR": str(run_dir),
            "I2E_EXPERIMENT_ID": args.experiment_id,
            "I2E_RUN_ID": run_id,
            "I2E_CONFIG_PATH": str(config_path),
            "I2E_SEED": mapping["seed"],
            "I2E_SUBSET_SEED": mapping["subset_seed"],
        }
    )
    timeout = int(adapter.get("timeout_seconds", 0))
    status = "FAILED_ENGINEERING"
    reason = ""
    exit_code = -1
    try:
        exit_code = run_command(command, working_dir, env, run_dir / "stdout.log", run_dir / "stderr.log", timeout)
        if exit_code == 0 and evaluation:
            update_node(root, args.experiment_id, "EVALUATING")
            exit_code = run_command(evaluation, working_dir, env, run_dir / "stdout.log", run_dir / "stderr.log", timeout)
        required = preview["required_outputs"]
        missing = [relative for relative in required if not resolve_run_output(run_dir, relative).is_file()]
        if exit_code != 0:
            reason = f"Process exited with code {exit_code}"
        elif missing:
            reason = "Missing required outputs: " + ", ".join(missing)
        else:
            status = "DONE"
            hashes = collect_hashes(run_dir, required)
            write_json(run_dir / "artifact_hashes.json", {"schema_version": 1, "artifacts": hashes})
    except subprocess.TimeoutExpired:
        reason = f"Timed out after {timeout} seconds"
        exit_code = 124
    except Exception as exc:
        reason = f"Runner exception: {type(exc).__name__}: {exc}"

    manifest.update(
        {
            "status": status,
            "finished_at": utc_now(),
            "exit_code": exit_code,
            "failure_reason": reason,
        }
    )
    write_json(run_dir / "manifest.json", manifest)
    update_node(root, args.experiment_id, status, reason=reason)
    print(json.dumps({"run_id": run_id, "status": status, "run_dir": str(run_dir), "reason": reason}, ensure_ascii=False))
    return 0 if status == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
