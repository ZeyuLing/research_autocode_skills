#!/usr/bin/env python3
"""Fail-closed audit of one process-bound Codex actor JSONL transport.

The JSONL stream cannot by itself prove how Codex was launched. Therefore this
validator also requires a launcher-owned record that binds the actor, prompt,
executable, exact argv, working directories, output log, process, and Codex
thread. The record is operational provenance only; it is not thesis evidence.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence


SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from actor_prompt_contract import FORBIDDEN_ACTOR_TOOL_NAMES  # noqa: E402


ACTOR_RE = re.compile(
    r"(?:P|H(?:0[1-9]|[1-9][0-9])|R[1-5]|AI|SA-(?:R[1-5]|AI)|C|S|V)\Z"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
LAUNCH_RECORD_SCHEMA = "thesis-review-actor-launch-v3"
LAUNCH_RECORD_FIELDS = frozenset(
    {
        "schema",
        "actor",
        "launch_id",
        "prompt_path",
        "prompt_bytes",
        "prompt_sha256",
        "process_sha256",
        "process_seal_sha256",
        "input_commitment_sha256",
        "output_commitment_sha256",
        "executable_path",
        "executable_sha256",
        "argv",
        "argv_sha256",
        "cwd",
        "workspace",
        "pid",
        "exit_code",
        "log_path",
        "log_bytes",
        "log_sha256",
        "thread_id",
    }
)
OPTIONAL_GLOBAL_FLAGS = ("--search",)
REQUIRED_EXEC_FLAGS = (
    "--json",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--approve-for-me",
)
OPTIONAL_EXEC_FLAGS = (
    "--skip-git-repo-check",
)
MULTI_AGENT_DISABLE_FORMS = (
    "--disable multi_agent",
    "--disable=multi_agent",
    "-c features.multi_agent=false",
)
NO_PUBLIC_NETWORK_ACTOR_RE = re.compile(
    r"(?:H(?:0[1-9]|[1-9][0-9])|AI|SA-AI|S|V)\Z"
)

COLLAB_EVENT_TYPES = {
    "collab_tool_call",
    "collaboration_tool_call",
    "multi_agent_tool_call",
    "agent_tool_call",
    "task_tool_call",
    "thread_tool_call",
}

TOP_LEVEL_EVENT_TYPES = (
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
    "item.updated",
    "item.completed",
    "error",
)
THREAD_ITEM_TYPES = (
    "agent_message",
    "reasoning",
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "collab_tool_call",
    "web_search",
    "todo_list",
    "error",
)

# Prompt construction and transport auditing share one production source. The
# validator tests retain a separately authored literal copy, preventing a
# production edit from weakening the set and its assertions in lockstep.
COLLAB_TOOL_NAMES = frozenset(FORBIDDEN_ACTOR_TOOL_NAMES)

MODEL_CLI_BASENAMES = {
    "aider",
    "aider.exe",
    "aider.cmd",
    "aider.ps1",
    "aider.bat",
    "claude",
    "claude.exe",
    "claude.cmd",
    "claude.ps1",
    "claude.bat",
    "codex",
    "codex.exe",
    "codex.cmd",
    "codex.ps1",
    "codex.bat",
    "cursor-agent",
    "cursor-agent.exe",
    "gemini",
    "gemini.exe",
    "gemini.cmd",
    "gemini.ps1",
    "gemini.bat",
    "llm",
    "llm.exe",
    "ollama",
    "ollama.exe",
    "openai",
    "openai.exe",
    "opencode",
    "opencode.exe",
    "opencode.cmd",
    "opencode.ps1",
    "opencode.bat",
}
SHELL_WRAPPER_BASENAMES = {
    "bash",
    "bash.exe",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "sh",
    "sh.exe",
    "zsh",
    "zsh.exe",
}
PACKAGE_RUNNER_BASENAMES = {
    f"{name}{suffix}"
    for name in (
        "npm",
        "npx",
        "pnpm",
        "pnpx",
        "yarn",
        "yarnpkg",
        "bun",
        "bunx",
        "uvx",
    )
    for suffix in ("", ".exe", ".cmd", ".ps1", ".bat")
}
ENVIRONMENT_RUNNER_BASENAMES = {
    f"{name}{suffix}"
    for name in ("pipx", "uv", "poetry")
    for suffix in ("", ".exe", ".cmd", ".ps1", ".bat")
}
NODE_BASENAMES = {"node", "node.exe"}
START_WRAPPER_BASENAMES = {"start", "start.exe"}
WSL_WRAPPER_BASENAMES = {"wsl", "wsl.exe"}
COREPACK_WRAPPER_BASENAMES = {
    f"corepack{suffix}" for suffix in ("", ".exe", ".cmd", ".ps1", ".bat")
}
ENV_COMMAND_WRAPPER_BASENAMES = {"env", "env.exe"}
TRANSPARENT_WRAPPER_BASENAMES = {"call", "command", "exec", "nohup"}
MODEL_RUNNER_TARGETS = frozenset(
    {
        "@openai/codex",
        "aider",
        "aider-chat",
        "aider_chat",
        "claude",
        "codex",
        "cursor-agent",
        "cursor_agent",
        "gemini",
        "llm",
        "ollama",
        "openai",
        "opencode",
    }
)
PYTHON_BASENAMES = {
    "py",
    "py.exe",
    "python",
    "python.exe",
    "python3",
    "python3.exe",
}
PUBLIC_NETWORK_CLIENT_BASENAMES = {
    "aria2c",
    "aria2c.exe",
    "curl",
    "curl.exe",
    "invoke-restmethod",
    "invoke-webrequest",
    "irm",
    "iwr",
    "start-bitstransfer",
    "wget",
    "wget.exe",
    "wget2",
    "wget2.exe",
}
RECONNECT_MESSAGE_RE = re.compile(
    r"Reconnecting\.\.\. ([1-9][0-9]*)/([1-9][0-9]*) "
    r"\(([^()\r\n]+)\)\Z"
)
FALLBACK_MESSAGE_RE = re.compile(
    r"Falling back from WebSockets to HTTPS transport\. [^\r\n]+\Z"
)
MAX_RECOVERABLE_RECONNECT_ATTEMPTS = 10


class TransportError(RuntimeError):
    """Fail-closed actor-transport validation error."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TransportError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class _PairsObject(dict[str, Any]):
    """JSON object retaining duplicate-key evidence for JSONL schema checks."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        super().__init__()
        self.pairs = tuple(pairs)
        duplicates: list[str] = []
        for key, value in pairs:
            if key in self:
                duplicates.append(key)
            self[key] = value
        self.duplicate_keys = tuple(duplicates)


def _preserve_duplicate_keys(pairs: list[tuple[str, Any]]) -> _PairsObject:
    return _PairsObject(pairs)


def _validate_jsonl_duplicate_keys(
    value: Any, *, path: tuple[str, ...] = (), root: dict[str, Any] | None = None
) -> None:
    """Reject duplicates except Codex's observed flattened web-search ``id``."""

    if root is None and isinstance(value, dict):
        root = value
    if isinstance(value, _PairsObject):
        if value.duplicate_keys:
            allowed_web_search_duplicate = (
                path == ("item",)
                and root is not None
                and root.get("type") in {"item.started", "item.updated", "item.completed"}
                and value.get("type") == "web_search"
                and value.duplicate_keys == ("id",)
                and sum(1 for key, _ in value.pairs if key == "id") == 2
                and all(
                    isinstance(item, str) and item
                    for key, item in value.pairs
                    if key == "id"
                )
            )
            if not allowed_web_search_duplicate:
                raise TransportError(
                    "duplicate JSON key at "
                    + (".".join(path) or "event")
                    + f": {value.duplicate_keys[0]}"
                )
        for key, nested in value.items():
            _validate_jsonl_duplicate_keys(
                nested, path=(*path, str(key)), root=root
            )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_jsonl_duplicate_keys(
                nested, path=(*path, str(index)), root=root
            )


def _load_jsonl_event(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_preserve_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise TransportError(f"{label} is not one complete JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise TransportError(f"{label} must be a JSON object")
    _validate_jsonl_duplicate_keys(value)
    return value


def _load_json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except TransportError:
        raise
    except json.JSONDecodeError as exc:
        raise TransportError(f"{label} is not one complete JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise TransportError(f"{label} must be a JSON object")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        int(getattr(metadata, "st_file_attributes", 0)) & 0x400
    )


def _stable_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_nlink),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
    )


def _require_single_link_regular_metadata(
    metadata: os.stat_result, *, label: str
) -> None:
    if not stat.S_ISREG(metadata.st_mode) or int(metadata.st_nlink) != 1:
        raise TransportError(f"{label} must be a single-link regular file")


def _read_stable_file(path: Path, *, label: str) -> bytes:
    try:
        lexical_before = path.lstat()
        _require_single_link_regular_metadata(lexical_before, label=label)
        if _is_link_or_reparse(path):
            raise TransportError(f"{label} must not be a symlink/reparse point")
        with path.open("rb") as handle:
            opened_before = os.fstat(handle.fileno())
            _require_single_link_regular_metadata(opened_before, label=label)
            if _stable_identity(opened_before) != _stable_identity(lexical_before):
                raise TransportError(f"{label} changed before it was opened")
            value = handle.read()
            opened_after = os.fstat(handle.fileno())
            _require_single_link_regular_metadata(opened_after, label=label)
            if _stable_identity(opened_after) != _stable_identity(opened_before):
                raise TransportError(f"{label} changed while it was read")
        lexical_after = path.lstat()
        _require_single_link_regular_metadata(lexical_after, label=label)
        if _is_link_or_reparse(path):
            raise TransportError(f"{label} became a symlink/reparse point")
        if _stable_identity(lexical_after) != _stable_identity(opened_after):
            raise TransportError(f"{label} changed after it was read")
    except TransportError:
        raise
    except OSError as exc:
        raise TransportError(f"cannot read stable {label}: {exc}") from exc
    return value


def _sha256_file(path: Path, *, label: str = "file") -> str:
    digest = hashlib.sha256()
    try:
        lexical_before = path.lstat()
        _require_single_link_regular_metadata(lexical_before, label=label)
        if _is_link_or_reparse(path):
            raise TransportError(f"{label} must not be a symlink/reparse point")
        with path.open("rb") as handle:
            opened_before = os.fstat(handle.fileno())
            _require_single_link_regular_metadata(opened_before, label=label)
            if _stable_identity(opened_before) != _stable_identity(lexical_before):
                raise TransportError(f"{label} changed before it was opened")
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            opened_after = os.fstat(handle.fileno())
            _require_single_link_regular_metadata(opened_after, label=label)
            if _stable_identity(opened_after) != _stable_identity(opened_before):
                raise TransportError(f"{label} changed while it was hashed")
        lexical_after = path.lstat()
        _require_single_link_regular_metadata(lexical_after, label=label)
        if _is_link_or_reparse(path):
            raise TransportError(f"{label} became a symlink/reparse point")
        if _stable_identity(lexical_after) != _stable_identity(opened_after):
            raise TransportError(f"{label} changed after it was hashed")
    except TransportError:
        raise
    except OSError as exc:
        raise TransportError(f"cannot hash stable {label}: {exc}") from exc
    return digest.hexdigest()


def argv_sha256(argv: Sequence[str]) -> str:
    """Return the canonical hash used by a launch record for an argv array."""

    encoded = json.dumps(
        list(argv), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _canonical_existing_path(value: object, *, label: str, kind: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TransportError(f"launch record {label} must be a non-empty string")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise TransportError(f"launch record {label} must be an absolute path")
    for component in (candidate, *candidate.parents):
        if component.exists() and _is_link_or_reparse(component):
            raise TransportError(
                f"launch record {label} traverses a symlink/reparse component"
            )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise TransportError(f"launch record {label} does not resolve: {exc}") from exc
    if kind == "file":
        try:
            metadata = resolved.lstat()
        except OSError as exc:
            raise TransportError(f"cannot inspect launch record {label}: {exc}") from exc
        _require_single_link_regular_metadata(metadata, label=f"launch record {label}")
    if kind == "directory" and not resolved.is_dir():
        raise TransportError(f"launch record {label} must resolve to a directory")
    return resolved


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(right.resolve(strict=False))
    )


def _required_sha256(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value.lower()):
        raise TransportError(f"launch record {key} must be a 64-digit SHA-256")
    return value.lower()


def _required_positive_int(record: dict[str, Any], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TransportError(f"launch record {key} must be a positive integer")
    return value


def canonical_tool_name(value: object) -> str:
    """Normalize namespaces including MCP's double-underscore qualification."""

    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _forbidden_tool(value: object) -> str | None:
    tool = canonical_tool_name(value)
    if not tool:
        return None
    for forbidden in sorted(COLLAB_TOOL_NAMES, key=len, reverse=True):
        if tool == forbidden or tool.endswith("_" + forbidden):
            return forbidden
    # Fail closed for previously unseen agent/task/thread management APIs. The
    # item ``agent_message`` is never inspected as a tool name (see below).
    if re.search(
        r"(?:^|_)(?:agent|agents|subagent|subagents|task|tasks|thread|threads)(?:_|$)",
        tool,
    ):
        return tool
    if tool.startswith(("collab_", "collaboration_", "multi_agent_")):
        return tool
    return None


def delegation_evidence(event: dict[str, Any]) -> list[str]:
    """Inspect only actual Codex control-plane fields, never returned content."""

    evidence: list[str] = []
    event_type = canonical_tool_name(event.get("type"))
    if event_type in COLLAB_EVENT_TYPES or event_type.startswith(
        ("multi_agent_", "collab_", "collaboration_")
    ):
        evidence.append(f"event-type={event_type}")
    item = event.get("item")
    if not isinstance(item, dict):
        return sorted(set(evidence))
    item_type = canonical_tool_name(item.get("type"))
    if item_type == "collab_tool_call" or item_type in COLLAB_EVENT_TYPES:
        evidence.append(f"item-type={item_type}")
        return sorted(set(evidence))
    if item_type != "mcp_tool_call":
        return sorted(set(evidence))
    forbidden = _forbidden_tool(item.get("tool"))
    if forbidden:
        evidence.append(f"tool={forbidden}")
    server = canonical_tool_name(item.get("server"))
    if server.startswith(("collab", "multi_agent")):
        evidence.append(f"server={server}")
    return sorted(set(evidence))


def failure_evidence(event: dict[str, Any]) -> list[str]:
    """Return stream/turn errors, not handled local-tool result failures."""

    evidence: list[str] = []
    event_type = canonical_tool_name(event.get("type"))
    if event_type in {"error", "turn_failed"}:
        evidence.append(f"type={event_type}")
    item = event.get("item")
    if not isinstance(item, dict):
        return sorted(set(evidence))
    item_type = canonical_tool_name(item.get("type"))
    if item_type == "error":
        evidence.append("item-type=error")
    return sorted(set(evidence))


def _require_closed_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    label: str,
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required - optional)
    if missing:
        raise TransportError(f"{label} is missing required field(s): {missing}")
    if extra:
        raise TransportError(f"{label} contains unknown field(s): {extra}")


def _require_string(value: object, *, label: str, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        qualifier = "non-empty " if nonempty else ""
        raise TransportError(f"{label} must be a {qualifier}string")
    return value


def _require_nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransportError(f"{label} must be a non-negative integer")
    return value


def _validate_usage(value: object) -> None:
    if not isinstance(value, dict):
        raise TransportError("turn.completed usage must be an object")
    required = {
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    }
    _require_closed_keys(value, required=required, label="turn.completed usage")
    for key in sorted(required):
        _require_nonnegative_int(value[key], label=f"turn.completed usage.{key}")


def _validate_web_search_action(value: object) -> None:
    if not isinstance(value, dict):
        raise TransportError("web_search action must be an object")
    action_type = value.get("type")
    if action_type == "other":
        _require_closed_keys(value, required={"type"}, label="web_search action")
        return
    if action_type == "search":
        _require_closed_keys(
            value,
            required={"type"},
            optional={"query", "queries"},
            label="web_search search action",
        )
        query = value.get("query")
        queries = value.get("queries")
        if query is not None and not isinstance(query, str):
            raise TransportError("web_search action.query must be a string or null")
        if queries is not None and (
            not isinstance(queries, list)
            or any(not isinstance(item, str) for item in queries)
        ):
            raise TransportError(
                "web_search action.queries must be a string array or null"
            )
        return
    if action_type == "open_page":
        _require_closed_keys(
            value,
            required={"type"},
            optional={"url"},
            label="web_search open_page action",
        )
        if value.get("url") is not None and not isinstance(value.get("url"), str):
            raise TransportError("web_search action.url must be a string or null")
        return
    if action_type == "find_in_page":
        _require_closed_keys(
            value,
            required={"type"},
            optional={"url", "pattern"},
            label="web_search find_in_page action",
        )
        for key in ("url", "pattern"):
            if value.get(key) is not None and not isinstance(value.get(key), str):
                raise TransportError(
                    f"web_search action.{key} must be a string or null"
                )
        return
    raise TransportError(f"unknown web_search action type: {action_type!r}")


def _validate_thread_item(item: object, *, event_type: str) -> None:
    if not isinstance(item, dict):
        raise TransportError(f"{event_type} item must be an object")
    item_type = item.get("type")
    if not isinstance(item_type, str) or item_type not in THREAD_ITEM_TYPES:
        raise TransportError(f"{event_type} has unknown item type: {item_type!r}")
    _require_string(item.get("id"), label=f"{event_type} item.id")

    if item_type in {"agent_message", "reasoning"}:
        _require_closed_keys(
            item,
            required={"id", "type", "text"},
            label=f"{event_type} {item_type} item",
        )
        _require_string(
            item.get("text"), label=f"{event_type} {item_type}.text", nonempty=False
        )
        return
    if item_type == "command_execution":
        _require_closed_keys(
            item,
            required={
                "id",
                "type",
                "command",
                "aggregated_output",
                "exit_code",
                "status",
            },
            label=f"{event_type} command_execution item",
        )
        _require_string(
            item.get("command"), label=f"{event_type} command_execution.command"
        )
        _require_string(
            item.get("aggregated_output"),
            label=f"{event_type} command_execution.aggregated_output",
            nonempty=False,
        )
        exit_code = item.get("exit_code")
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            raise TransportError(
                f"{event_type} command_execution.exit_code must be integer or null"
            )
        status = item.get("status")
        if status not in {
            "in_progress",
            "completed",
            "failed",
            "declined",
        }:
            raise TransportError(
                f"{event_type} command_execution carries an unknown status"
            )
        if status == "in_progress" and exit_code is not None:
            raise TransportError(
                f"{event_type} in-progress command_execution must have exit_code=null"
            )
        if status == "completed" and exit_code != 0:
            raise TransportError(
                f"{event_type} completed command_execution must have exit_code=0"
            )
        if status == "failed" and (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or exit_code == 0
        ):
            raise TransportError(
                f"{event_type} failed command_execution must have a nonzero integer exit_code"
            )
        if status == "declined" and exit_code is not None:
            raise TransportError(
                f"{event_type} declined command_execution must have exit_code=null"
            )
        return
    if item_type == "file_change":
        _require_closed_keys(
            item,
            required={"id", "type", "changes", "status"},
            label=f"{event_type} file_change item",
        )
        changes = item.get("changes")
        if not isinstance(changes, list):
            raise TransportError(f"{event_type} file_change.changes must be an array")
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                raise TransportError(
                    f"{event_type} file_change.changes[{index}] must be an object"
                )
            _require_closed_keys(
                change,
                required={"path", "kind"},
                label=f"{event_type} file_change.changes[{index}]",
            )
            _require_string(
                change.get("path"),
                label=f"{event_type} file_change.changes[{index}].path",
            )
            if change.get("kind") not in {"add", "delete", "update"}:
                raise TransportError(
                    f"{event_type} file_change.changes[{index}] has unknown kind"
                )
        if item.get("status") not in {"in_progress", "completed", "failed"}:
            raise TransportError(f"{event_type} file_change has unknown status")
        return
    if item_type == "mcp_tool_call":
        _require_closed_keys(
            item,
            required={
                "id",
                "type",
                "server",
                "tool",
                "arguments",
                "result",
                "error",
                "status",
            },
            label=f"{event_type} mcp_tool_call item",
        )
        _require_string(item.get("server"), label=f"{event_type} mcp_tool_call.server")
        _require_string(item.get("tool"), label=f"{event_type} mcp_tool_call.tool")
        if not isinstance(item.get("arguments"), dict):
            raise TransportError(
                f"{event_type} mcp_tool_call.arguments must be an object"
            )
        status = item.get("status")
        if status not in {"in_progress", "completed", "failed"}:
            raise TransportError(f"{event_type} mcp_tool_call has unknown status")
        result = item.get("result")
        if result is not None:
            if not isinstance(result, dict):
                raise TransportError(
                    f"{event_type} mcp_tool_call.result must be object or null"
                )
            _require_closed_keys(
                result,
                required={"content", "structured_content"},
                optional={"_meta"},
                label=f"{event_type} mcp_tool_call.result",
            )
            if not isinstance(result.get("content"), list):
                raise TransportError(
                    f"{event_type} mcp_tool_call.result.content must be an array"
                )
        error = item.get("error")
        if error is not None:
            if not isinstance(error, dict):
                raise TransportError(
                    f"{event_type} mcp_tool_call.error must be object or null"
                )
            _require_closed_keys(
                error,
                required={"message"},
                label=f"{event_type} mcp_tool_call.error",
            )
            _require_string(
                error.get("message"), label=f"{event_type} mcp_tool_call.error.message"
            )
        if status == "in_progress" and (result is not None or error is not None):
            raise TransportError(
                f"{event_type} in-progress mcp_tool_call must have null result and error"
            )
        if status == "completed" and (result is None or error is not None):
            raise TransportError(
                f"{event_type} completed mcp_tool_call must have a result and null error"
            )
        if status == "failed" and (result is not None or error is None):
            raise TransportError(
                f"{event_type} failed mcp_tool_call must have null result and an error"
            )
        return
    if item_type == "collab_tool_call":
        # This is a known Codex schema member but is prohibited unconditionally.
        # Delegation detection reports the violation after structural parsing.
        return
    if item_type == "web_search":
        _require_closed_keys(
            item,
            required={"id", "type", "query", "action"},
            label=f"{event_type} web_search item",
        )
        _require_string(
            item.get("query"), label=f"{event_type} web_search.query", nonempty=False
        )
        _validate_web_search_action(item.get("action"))
        return
    if item_type == "todo_list":
        _require_closed_keys(
            item,
            required={"id", "type", "items"},
            label=f"{event_type} todo_list item",
        )
        todo_items = item.get("items")
        if not isinstance(todo_items, list):
            raise TransportError(f"{event_type} todo_list.items must be an array")
        for index, todo in enumerate(todo_items):
            if not isinstance(todo, dict):
                raise TransportError(
                    f"{event_type} todo_list.items[{index}] must be an object"
                )
            _require_closed_keys(
                todo,
                required={"text", "completed"},
                label=f"{event_type} todo_list.items[{index}]",
            )
            _require_string(
                todo.get("text"), label=f"{event_type} todo_list.items[{index}].text"
            )
            if not isinstance(todo.get("completed"), bool):
                raise TransportError(
                    f"{event_type} todo_list.items[{index}].completed must be boolean"
                )
        return
    if item_type == "error":
        _require_closed_keys(
            item,
            required={"id", "type", "message"},
            label=f"{event_type} error item",
        )
        _require_string(item.get("message"), label=f"{event_type} error.message")
        return
    raise TransportError(f"unhandled thread item type: {item_type!r}")


def validate_event_schema(event: dict[str, Any]) -> None:
    """Validate the current closed Codex exec JSONL event vocabulary."""

    event_type = event.get("type")
    if not isinstance(event_type, str) or event_type not in TOP_LEVEL_EVENT_TYPES:
        raise TransportError(f"unknown or missing top-level event type: {event_type!r}")
    if event_type == "thread.started":
        _require_closed_keys(
            event,
            required={"type", "thread_id"},
            label="thread.started event",
        )
        _require_string(event.get("thread_id"), label="thread.started thread_id")
        return
    if event_type == "turn.started":
        _require_closed_keys(event, required={"type"}, label="turn.started event")
        return
    if event_type == "turn.completed":
        _require_closed_keys(
            event, required={"type", "usage"}, label="turn.completed event"
        )
        _validate_usage(event.get("usage"))
        return
    if event_type == "turn.failed":
        _require_closed_keys(
            event, required={"type", "error"}, label="turn.failed event"
        )
        error = event.get("error")
        if not isinstance(error, dict):
            raise TransportError("turn.failed error must be an object")
        _require_closed_keys(error, required={"message"}, label="turn.failed error")
        _require_string(error.get("message"), label="turn.failed error.message")
        return
    if event_type == "error":
        _require_closed_keys(
            event, required={"type", "message"}, label="error event"
        )
        _require_string(event.get("message"), label="error event.message")
        return
    _require_closed_keys(
        event, required={"type", "item"}, label=f"{event_type} event"
    )
    _validate_thread_item(event.get("item"), event_type=event_type)


def validate_item_lifecycle(
    events: Sequence[dict[str, Any]], turn_started_index: int, turn_completed_index: int
) -> None:
    """Require each emitted item ID to have one coherent terminal lifecycle."""

    states: dict[str, tuple[str, str]] = {}
    status_item_types = {"command_execution", "file_change", "mcp_tool_call"}
    for index in range(turn_started_index + 1, turn_completed_index):
        event = events[index]
        event_type = event.get("type")
        if event_type not in {"item.started", "item.updated", "item.completed"}:
            continue
        item = event.get("item")
        if not isinstance(item, dict):  # already owned by the closed schema gate
            continue
        item_id = str(item.get("id", ""))
        item_type = str(item.get("type", ""))
        previous = states.get(item_id)

        if event_type == "item.started":
            if previous is not None:
                raise TransportError(
                    f"item {item_id!r} has duplicate/reused item.started lifecycle"
                )
            if item_type in status_item_types and item.get("status") != "in_progress":
                raise TransportError(
                    f"item.started {item_id!r} must have status=in_progress"
                )
            if item_type == "command_execution" and item.get("exit_code") is not None:
                raise TransportError(
                    f"item.started command {item_id!r} must have exit_code=null"
                )
            states[item_id] = (item_type, "active")
            continue

        if event_type == "item.updated":
            if previous is None or previous[1] != "active":
                raise TransportError(
                    f"item.updated {item_id!r} has no active item.started"
                )
            if previous[0] != item_type:
                raise TransportError(
                    f"item.updated {item_id!r} changes item type"
                )
            if item_type in status_item_types and item.get("status") != "in_progress":
                raise TransportError(
                    f"item.updated {item_id!r} must remain in_progress"
                )
            continue

        if previous is not None:
            if previous[1] != "active":
                raise TransportError(f"item {item_id!r} has duplicate item.completed")
            if previous[0] != item_type:
                raise TransportError(f"item.completed {item_id!r} changes item type")
        if item_type in status_item_types and item.get("status") == "in_progress":
            raise TransportError(
                f"item.completed {item_id!r} cannot remain in_progress"
            )
        if (
            item_type == "command_execution"
            and item.get("status") == "completed"
            and (
                isinstance(item.get("exit_code"), bool)
                or not isinstance(item.get("exit_code"), int)
            )
        ):
            raise TransportError(
                f"completed command {item_id!r} must carry an integer exit_code"
            )
        states[item_id] = (item_type, "completed")

    active = sorted(item_id for item_id, (_, state) in states.items() if state == "active")
    if active:
        raise TransportError(f"turn.completed leaves unterminated item IDs: {active}")


def _recoverable_reconnect(event: dict[str, Any]) -> tuple[int, int] | None:
    if set(event) != {"type", "message"} or event.get("type") != "error":
        return None
    message = event.get("message")
    if not isinstance(message, str):
        return None
    match = RECONNECT_MESSAGE_RE.fullmatch(message)
    if match is None:
        return None
    attempt = int(match.group(1))
    total = int(match.group(2))
    if attempt > total or total > MAX_RECOVERABLE_RECONNECT_ATTEMPTS:
        return None
    return attempt, total


def _recoverable_fallback(event: dict[str, Any]) -> bool:
    if set(event) != {"type", "item"} or event.get("type") != "item.completed":
        return False
    item = event.get("item")
    if not isinstance(item, dict):
        return False
    if not {"type", "message"}.issubset(item) or not set(item).issubset(
        {"id", "type", "message"}
    ):
        return False
    if item.get("type") != "error":
        return False
    if "id" in item and (not isinstance(item["id"], str) or not item["id"]):
        return False
    message = item.get("message")
    return isinstance(message, str) and FALLBACK_MESSAGE_RE.fullmatch(message) is not None


def recoverable_transport_error_indices(
    events: Sequence[dict[str, Any]], turn_started_index: int, turn_completed_index: int
) -> frozenset[int]:
    """Recognize only the observed WebSocket-retry-to-HTTPS recovery sequence."""

    cursor = turn_started_index + 1
    reconnect_indices: list[int] = []
    attempts: list[int] = []
    total_attempts: int | None = None
    while cursor < turn_completed_index:
        reconnect = _recoverable_reconnect(events[cursor])
        if reconnect is None:
            break
        attempt, total = reconnect
        if total_attempts is None:
            total_attempts = total
        if total != total_attempts:
            return frozenset()
        reconnect_indices.append(cursor)
        attempts.append(attempt)
        cursor += 1

    if not reconnect_indices or total_attempts is None:
        return frozenset()
    if attempts != list(range(attempts[0], attempts[0] + len(attempts))):
        return frozenset()
    if attempts[-1] != total_attempts:
        return frozenset()
    if cursor >= turn_completed_index or not _recoverable_fallback(events[cursor]):
        return frozenset()
    fallback_index = cursor

    post_fallback_agent_message = False
    for event in events[fallback_index + 1 : turn_completed_index]:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip() and not failure_evidence(event):
            post_fallback_agent_message = True
            break
    if not post_fallback_agent_message:
        return frozenset()
    return frozenset([*reconnect_indices, fallback_index])


def _first_executable(segment: str, *, dialect: str) -> tuple[str, str]:
    remaining = segment.strip().lstrip("(").strip()
    remaining = re.sub(r"^&\s*", "", remaining)
    match = re.match(r'''(?:["']([^"']+)["']|([^\s]+))(.*)\Z''', remaining, re.S)
    if not match:
        return "", ""
    token = (match.group(1) or match.group(2)).strip().rstrip("),")
    # Remove only the first-token escape character used by this shell. Quoted
    # arguments later in the command remain data.
    escape_character = "^" if dialect == "cmd" else "\\" if dialect == "posix" else "`"
    token = token.replace(escape_character, "")
    basename = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return basename, match.group(3) or ""


def _shell_payload(executable: str, remainder: str) -> str | None:
    """Return the actual command string passed to a recognized shell wrapper."""

    raw = remainder.strip()
    if executable in {"cmd", "cmd.exe"}:
        while raw:
            popped = _pop_command_token(raw)
            if popped is None:
                return None
            token, suffix = popped
            lowered = token.lower()
            if lowered not in {"/d", "/q", "/a", "/u", "/s", "/i", "/x"} and not re.fullmatch(
                r"/[vef]:(?:on|off)", lowered
            ):
                break
            raw = suffix.strip()
        match = re.match(r"(?is)^/[ck](?:\s+)?(.+)\Z", raw)
    elif executable in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        match = re.search(r"(?is)(?:^|\s)-(?:command|c)(?:\s+|:)(.+)\Z", raw)
    else:
        match = re.search(r"(?is)(?:^|\s)-[a-z]*c[a-z]*\s+(.+)\Z", raw)
    if match is None:
        return None
    payload = match.group(1).strip()
    if len(payload) >= 2 and payload[0] == payload[-1] and payload[0] in {'"', "'"}:
        payload = payload[1:-1].strip()
    return payload or None


def _split_shell_segments(command: str, *, dialect: str) -> list[str]:
    """Split common shell command separators while preserving quoted data."""

    segments: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    quote_characters = {'"'} if dialect == "cmd" else {'"', "'"}
    escape_character = "^" if dialect == "cmd" else "\\" if dialect == "posix" else "`"
    separators = {"&", "|", "\r", "\n"}
    if dialect != "cmd":
        separators.add(";")
    for index, character in enumerate(command):
        if escaped:
            escaped = False
            continue
        if quote is not None:
            quote_allows_escape = (
                dialect == "cmd"
                or (dialect in {"posix", "powershell"} and quote == '"')
            )
            if quote_allows_escape and character == escape_character:
                escaped = True
                continue
            if character == quote:
                quote = None
            continue
        if character == escape_character:
            escaped = True
            continue
        if character in quote_characters:
            quote = character
            continue
        if character in separators:
            segment = command[start:index].strip()
            if segment:
                segments.append(segment)
            start = index + 1
    tail = command[start:].strip()
    if tail:
        segments.append(tail)
    return segments


def _pop_command_token(value: str) -> tuple[str, str] | None:
    """Return one shell-like token and the unconsumed suffix."""

    raw = value.lstrip()
    if not raw:
        return None
    if raw[0] in {'"', "'"}:
        quote = raw[0]
        cursor = 1
        while cursor < len(raw):
            if raw[cursor] == quote and raw[cursor - 1] not in {"^", "`"}:
                return raw[1:cursor], raw[cursor + 1 :]
            cursor += 1
        return raw[1:], ""
    match = re.match(r"([^\s]+)(.*)\Z", raw, re.S)
    if match is None:  # pragma: no cover - nonempty input always matches
        return None
    return match.group(1), match.group(2)


def _start_payload(remainder: str, *, dialect: str) -> str | None:
    """Extract the program portion of a Windows ``start`` invocation."""

    raw = remainder.strip()
    while raw:
        popped = _pop_command_token(raw)
        if popped is None:
            return None
        token, suffix = popped
        canonical = token.lower()
        if canonical.startswith("/"):
            raw = suffix.strip()
            if canonical == "/d" and raw:
                next_token = _pop_command_token(raw)
                if next_token is None:
                    return None
                _, raw = next_token
                raw = raw.strip()
            continue
        break
    if not raw:
        return None
    # cmd.exe's start builtin treats its first double-quoted token as the title.
    # PowerShell's ``start`` alias instead treats a quoted token as FilePath.
    if dialect == "cmd" and raw[0] == '"':
        popped = _pop_command_token(raw)
        if popped is None:
            return None
        _, raw = popped
        raw = raw.strip()
    return raw or None


def _wsl_payload(remainder: str) -> str | None:
    """Extract the Linux command portion of a WSL launcher invocation."""

    raw = remainder.strip()
    value_options = {
        "-d",
        "--distribution",
        "-u",
        "--user",
        "--cd",
        "--shell-type",
    }
    flag_options = {
        "--system",
        "--login",
        "--no-launch",
        "--debug-shell",
    }
    while raw:
        before = raw
        popped = _pop_command_token(raw)
        if popped is None:
            return None
        token, suffix = popped
        canonical = token.lower()
        if canonical == "--":
            return suffix.strip() or None
        if canonical in {"-e", "--exec"}:
            return suffix.strip() or None
        if canonical in value_options:
            next_token = _pop_command_token(suffix)
            if next_token is None:
                return None
            _, raw = next_token
            raw = raw.strip()
            continue
        if any(canonical.startswith(option + "=") for option in value_options):
            raw = suffix.strip()
            continue
        if canonical in flag_options:
            raw = suffix.strip()
            continue
        if canonical.startswith("-"):
            # Unknown WSL switches cannot safely be interpreted as a command.
            return None
        return before.strip()
    return None


def _canonical_runner_name(executable: str) -> str:
    for suffix in (".exe", ".cmd", ".ps1", ".bat"):
        if executable.endswith(suffix):
            return executable[: -len(suffix)]
    return executable


def _is_model_runner_target(value: str) -> bool:
    token = value.strip().strip('"\'').replace("\\", "/").lower()
    if token.startswith("@openai/codex@"):
        return True
    return token in MODEL_RUNNER_TARGETS


def _command_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    raw = value
    while raw.strip():
        popped = _pop_command_token(raw)
        if popped is None:
            break
        token, raw = popped
        tokens.append(token)
    return tokens


def _package_runner_target(executable: str, remainder: str) -> str | None:
    """Return the actual package/command target, never a later file argument."""

    runner = _canonical_runner_name(executable)
    tokens = _command_tokens(remainder)
    if not tokens:
        return None
    global_options_with_values = {
        "--cache",
        "--config",
        "--cwd",
        "--dir",
        "--filter",
        "--global-dir",
        "--prefix",
        "--registry",
        "--store-dir",
        "--userconfig",
        "--workspace",
        "-C",
        "-F",
        "-w",
    }
    cursor = 0
    while cursor < len(tokens) and tokens[cursor].startswith("-"):
        option = tokens[cursor]
        cursor += 1
        if "=" not in option and option in global_options_with_values:
            cursor += 1
    tokens = tokens[cursor:]
    if not tokens:
        return None
    if runner in {"npm"}:
        if tokens[0].lower() not in {"exec", "x"}:
            return None
        tokens = tokens[1:]
    elif runner in {"pnpm", "yarn", "yarnpkg"}:
        if tokens[0].lower() not in {"dlx", "exec"}:
            return None
        tokens = tokens[1:]
    elif runner == "bun":
        if tokens[0].lower() not in {"x", "exec", "dlx"}:
            return None
        tokens = tokens[1:]
    elif runner not in {"npx", "pnpx", "bunx", "uvx"}:
        return None
    target_options_with_values = {
        "--cache",
        "--package",
        "--prefix",
        "--registry",
        "--script-shell",
        "--shell",
        "--userconfig",
        "--workspace",
        "-c",
        "-p",
        "-w",
    }
    cursor = 0
    while cursor < len(tokens):
        token = tokens[cursor]
        lowered = token.lower()
        if lowered == "--":
            cursor += 1
            continue
        if lowered.startswith("--package="):
            candidate = token.split("=", 1)[1]
            if _is_model_runner_target(candidate):
                return candidate
            cursor += 1
            continue
        if token.startswith("-"):
            cursor += 1
            if (
                "=" not in token
                and token in target_options_with_values
                and cursor < len(tokens)
            ):
                candidate = tokens[cursor]
                if token in {"--package", "-p"} and _is_model_runner_target(candidate):
                    return candidate
                cursor += 1
            continue
        return token if _is_model_runner_target(token) else None
    return None


def _environment_runner_target(executable: str, remainder: str) -> str | None:
    runner = _canonical_runner_name(executable)
    tokens = _command_tokens(remainder)
    global_options_with_values = {
        "--config",
        "--directory",
        "--index-url",
        "--python",
        "--python-preference",
        "--project",
        "--repository",
        "--spec",
        "-C",
        "-p",
    }
    cursor = 0
    while cursor < len(tokens) and tokens[cursor].startswith("-"):
        option = tokens[cursor]
        cursor += 1
        if "=" not in option and option in global_options_with_values:
            cursor += 1
    tokens = tokens[cursor:]
    lowered_tokens = [token.lower() for token in tokens]
    if runner == "uv" and len(tokens) >= 2 and lowered_tokens[:2] == ["tool", "run"]:
        tokens = tokens[2:]
    elif runner in {"uv", "pipx", "poetry"} and lowered_tokens[:1] == ["run"]:
        tokens = tokens[1:]
    else:
        return None
    for token in tokens:
        if token == "--":
            continue
        if token.startswith("-"):
            continue
        return token if _is_model_runner_target(token) else None
    return None


def _environment_command_payload(remainder: str) -> str | None:
    """Extract the command after POSIX ``env`` options and assignments."""

    raw = remainder.strip()
    while raw:
        before = raw
        popped = _pop_command_token(raw)
        if popped is None:
            return None
        token, suffix = popped
        if token == "--":
            return suffix.strip() or None
        if token in {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}:
            next_token = _pop_command_token(suffix)
            if next_token is None:
                return None
            _, raw = next_token
            raw = raw.strip()
            continue
        if token.startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            raw = suffix.strip()
            continue
        return before.strip()
    return None


def _transparent_wrapper_payload(executable: str, remainder: str) -> str | None:
    raw = remainder.strip()
    if executable == "command":
        popped = _pop_command_token(raw)
        if popped is None:
            return None
        token, suffix = popped
        if token in {"-v", "-V"}:
            return None
        if token in {"-p", "--"}:
            return suffix.strip() or None
    if raw.startswith("--"):
        raw = raw[2:].lstrip()
    return raw or None


def _start_process_payload(remainder: str) -> str | None:
    raw = remainder.strip()
    while raw:
        before = raw
        popped = _pop_command_token(raw)
        if popped is None:
            return None
        token, suffix = popped
        lowered = token.lower()
        if lowered == "-filepath":
            return suffix.strip() or None
        if lowered.startswith("-"):
            raw = suffix.strip()
            continue
        return before.strip()
    return None


def _python_invocation_payload(remainder: str) -> tuple[str, str] | None:
    """Extract the executable payload from one Python command line.

    Only literal command-line syntax is interpreted.  In particular, this does
    not scan command output or agent prose for model/client names.
    """

    tokens = _command_tokens(remainder)
    cursor = 0
    options_with_values = {
        "--check-hash-based-pycs",
        "-W",
        "-X",
    }
    while cursor < len(tokens):
        token = tokens[cursor]
        lowered = token.lower()
        if lowered in {"-c", "-m"}:
            if cursor + 1 >= len(tokens):
                return None
            return ("code" if lowered == "-c" else "module", tokens[cursor + 1])
        if lowered.startswith("-c") and len(token) > 2:
            return "code", token[2:]
        if lowered.startswith("-m") and len(token) > 2:
            return "module", token[2:]
        if lowered == "--":
            return ("script", tokens[cursor + 1]) if cursor + 1 < len(tokens) else None
        if lowered in options_with_values:
            cursor += 2
            continue
        if lowered.startswith("-"):
            cursor += 1
            continue
        return "script", token
    return None


def _ast_dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _ast_dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _literal_command_from_ast(node: ast.AST) -> str | None:
    """Render only a literal subprocess command, never arbitrary Python data."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(
                element.value, str
            ):
                return None
            values.append(element.value)
        if values:
            return " ".join(json.dumps(value) for value in values)
    return None


def _python_call_aliases(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """Return subprocess-module, os-module, and imported process-call aliases."""

    subprocess_modules = {"subprocess"}
    os_modules = {"os"}
    direct_calls: set[str] = set()
    subprocess_calls = {"run", "Popen", "call", "check_call", "check_output"}
    os_calls = {"system", "popen", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_modules.add(alias.asname or alias.name)
                elif alias.name == "os":
                    os_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                for alias in node.names:
                    if alias.name in subprocess_calls:
                        direct_calls.add(alias.asname or alias.name)
            elif node.module == "os":
                for alias in node.names:
                    if alias.name in os_calls:
                        direct_calls.add(alias.asname or alias.name)
    return subprocess_modules, os_modules, direct_calls


def _python_process_call_commands(code: str) -> list[str]:
    """Return literal commands passed to Python process-launch APIs."""

    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError):
        return []
    subprocess_modules, os_modules, direct_calls = _python_call_aliases(tree)
    subprocess_calls = {"run", "Popen", "call", "check_call", "check_output"}
    os_calls = {"system", "popen", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe"}
    commands: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _ast_dotted_name(node.func)
        if "." in dotted:
            module, method = dotted.split(".", 1)
            recognized = (
                module in subprocess_modules and method in subprocess_calls
            ) or (module in os_modules and method in os_calls)
        else:
            recognized = dotted in direct_calls
        if not recognized:
            continue
        candidates: list[ast.AST] = []
        if node.args:
            candidates.append(node.args[0])
        candidates.extend(
            keyword.value
            for keyword in node.keywords
            if keyword.arg in {"args", "executable"}
        )
        for candidate in candidates:
            rendered = _literal_command_from_ast(candidate)
            if rendered:
                commands.append(rendered)
    return commands


def _python_code_launches_model(code: str, *, depth: int) -> str | None:
    for command in _python_process_call_commands(code):
        nested = _command_launches_model(
            command, _depth=depth + 1, _dialect="posix"
        )
        if nested:
            return f"Python process API -> {nested}"
    return None


def _python_script_is_model_runner(value: str) -> bool:
    token = value.strip().strip('"\'').replace("\\", "/")
    basename = token.rsplit("/", 1)[-1].lower()
    stem, suffix = os.path.splitext(basename)
    if suffix not in {".py", ".pyw"}:
        return False
    return _is_model_runner_target(stem) or _is_model_runner_target(
        stem.replace("_", "-")
    )


def _command_launches_model(
    command: str, *, _depth: int = 0, _dialect: str = "powershell"
) -> str | None:
    if _depth > 8:
        return "nested shell depth"
    for segment in _split_shell_segments(command, dialect=_dialect):
        executable, remainder = _first_executable(segment, dialect=_dialect)
        if not executable:
            continue
        if executable in MODEL_CLI_BASENAMES:
            return executable
        if executable in SHELL_WRAPPER_BASENAMES:
            payload = _shell_payload(executable, remainder)
            if payload is None:
                continue
            nested_dialect = (
                "cmd"
                if executable in {"cmd", "cmd.exe"}
                else "powershell"
                if executable in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
                else "posix"
            )
            nested = _command_launches_model(
                payload, _depth=_depth + 1, _dialect=nested_dialect
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in START_WRAPPER_BASENAMES:
            payload = _start_payload(remainder, dialect=_dialect)
            if payload is None:
                continue
            nested = _command_launches_model(
                payload, _depth=_depth + 1, _dialect=_dialect
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in WSL_WRAPPER_BASENAMES:
            payload = _wsl_payload(remainder)
            if payload is None:
                continue
            nested = _command_launches_model(
                payload, _depth=_depth + 1, _dialect="posix"
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in COREPACK_WRAPPER_BASENAMES:
            nested = _command_launches_model(
                remainder, _depth=_depth + 1, _dialect=_dialect
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in ENV_COMMAND_WRAPPER_BASENAMES:
            payload = _environment_command_payload(remainder)
            if payload is None:
                continue
            nested = _command_launches_model(
                payload, _depth=_depth + 1, _dialect=_dialect
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in TRANSPARENT_WRAPPER_BASENAMES:
            payload = _transparent_wrapper_payload(executable, remainder)
            if payload is None:
                continue
            nested = _command_launches_model(
                payload, _depth=_depth + 1, _dialect=_dialect
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable == "start-process":
            payload = _start_process_payload(remainder)
            if payload is None:
                continue
            nested = _command_launches_model(
                payload, _depth=_depth + 1, _dialect="powershell"
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in PACKAGE_RUNNER_BASENAMES:
            target = _package_runner_target(executable, remainder)
            if target:
                return f"{executable} model package {target}"
        if executable in ENVIRONMENT_RUNNER_BASENAMES:
            target = _environment_runner_target(executable, remainder)
            if target:
                return f"{executable} environment model runner {target}"
        if executable in NODE_BASENAMES and re.search(
            r"(?i)(?:@openai[/\\]codex|node_modules[/\\]+@openai[/\\]+codex)"
            r"[^\r\n]*[/\\]codex\.js(?:[\"']|\s|\Z)",
            remainder,
        ):
            return f"{executable} Codex JavaScript entrypoint"
        if executable in PYTHON_BASENAMES:
            invocation = _python_invocation_payload(remainder)
            if invocation is None:
                continue
            kind, payload = invocation
            if kind == "module" and _is_model_runner_target(payload):
                return f"{executable} -m model client {payload}"
            if kind == "code":
                nested = _python_code_launches_model(payload, depth=_depth)
                if nested:
                    return f"{executable} -c -> {nested}"
            if kind == "script" and _python_script_is_model_runner(payload):
                return f"{executable} model-client script {payload}"
    return None


def _python_code_accesses_public_network(code: str, *, depth: int) -> str | None:
    for command in _python_process_call_commands(code):
        nested = _command_accesses_public_network(
            command, _depth=depth + 1, _dialect="posix"
        )
        if nested:
            return f"Python process API -> {nested}"

    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError):
        return None
    network_call_patterns = (
        re.compile(r"(?:^|\.)(?:requests|httpx)\.(?:request|get|post|put|patch|delete|head|options)\Z", re.I),
        re.compile(r"(?:^|\.)urllib\.request\.(?:urlopen|urlretrieve)\Z", re.I),
        re.compile(r"(?:^|\.)socket\.create_connection\Z", re.I),
        re.compile(r"(?:^|\.)webbrowser\.open(?:_new|_new_tab)?\Z", re.I),
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _ast_dotted_name(node.func)
        if any(pattern.search(dotted) for pattern in network_call_patterns):
            return f"Python network API {dotted}"
    return None


def _command_accesses_public_network(
    command: str, *, _depth: int = 0, _dialect: str = "powershell"
) -> str | None:
    """Recognize an executed public-network client in an actual command field."""

    if _depth > 8:
        return "nested shell depth"
    for segment in _split_shell_segments(command, dialect=_dialect):
        executable, remainder = _first_executable(segment, dialect=_dialect)
        if not executable:
            continue
        if executable in PUBLIC_NETWORK_CLIENT_BASENAMES:
            return executable
        if executable in SHELL_WRAPPER_BASENAMES:
            payload = _shell_payload(executable, remainder)
            if payload is None:
                continue
            nested_dialect = (
                "cmd"
                if executable in {"cmd", "cmd.exe"}
                else "powershell"
                if executable in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
                else "posix"
            )
            nested = _command_accesses_public_network(
                payload, _depth=_depth + 1, _dialect=nested_dialect
            )
            if nested:
                return f"{executable} wrapper -> {nested}"
            continue
        if executable in START_WRAPPER_BASENAMES:
            payload = _start_payload(remainder, dialect=_dialect)
            if payload is not None:
                nested = _command_accesses_public_network(
                    payload, _depth=_depth + 1, _dialect=_dialect
                )
                if nested:
                    return f"{executable} wrapper -> {nested}"
            continue
        if executable in WSL_WRAPPER_BASENAMES:
            payload = _wsl_payload(remainder)
            if payload is not None:
                nested = _command_accesses_public_network(
                    payload, _depth=_depth + 1, _dialect="posix"
                )
                if nested:
                    return f"{executable} wrapper -> {nested}"
            continue
        if executable in ENV_COMMAND_WRAPPER_BASENAMES:
            payload = _environment_command_payload(remainder)
            if payload is not None:
                nested = _command_accesses_public_network(
                    payload, _depth=_depth + 1, _dialect=_dialect
                )
                if nested:
                    return f"{executable} wrapper -> {nested}"
            continue
        if executable in TRANSPARENT_WRAPPER_BASENAMES:
            payload = _transparent_wrapper_payload(executable, remainder)
            if payload is not None:
                nested = _command_accesses_public_network(
                    payload, _depth=_depth + 1, _dialect=_dialect
                )
                if nested:
                    return f"{executable} wrapper -> {nested}"
            continue
        if executable == "start-process":
            payload = _start_process_payload(remainder)
            if payload is not None:
                nested = _command_accesses_public_network(
                    payload, _depth=_depth + 1, _dialect="powershell"
                )
                if nested:
                    return f"{executable} wrapper -> {nested}"
            continue
        if executable in PYTHON_BASENAMES:
            invocation = _python_invocation_payload(remainder)
            if invocation is None:
                continue
            kind, payload = invocation
            if kind == "code":
                nested = _python_code_accesses_public_network(payload, depth=_depth)
                if nested:
                    return f"{executable} -c -> {nested}"
    return None


def nested_model_process_evidence(event: dict[str, Any]) -> list[str]:
    """Inspect only actual command fields, never MCP result payloads."""

    evidence: list[str] = []
    item = event.get("item")
    if not isinstance(item, dict):
        return evidence
    item_type = canonical_tool_name(item.get("type"))
    command_source: dict[str, Any] | None = None
    command_dialect = "powershell"
    if item_type == "command_execution":
        command_source = {"command": item.get("command")}
    elif item_type == "mcp_tool_call":
        tool = canonical_tool_name(item.get("tool"))
        if tool.endswith(
            (
                "exec_command",
                "command_execution",
                "command_call",
                "shell_command",
                "shell_execution",
            )
        ):
            arguments = item.get("arguments")
            if isinstance(arguments, dict):
                command_source = arguments
                shell_value = arguments.get("shell", arguments.get("shell_executable"))
                if isinstance(shell_value, str):
                    shell_basename = shell_value.replace("\\", "/").rsplit("/", 1)[-1].lower()
                    if shell_basename in {"cmd", "cmd.exe"}:
                        command_dialect = "cmd"
                    elif shell_basename in {"bash", "bash.exe", "sh", "sh.exe", "zsh", "zsh.exe"}:
                        command_dialect = "posix"
    if command_source is None:
        return evidence
    for field in ("command", "cmd", "command_line"):
        value = command_source.get(field)
        if isinstance(value, str):
            match = _command_launches_model(value, _dialect=command_dialect)
            if match:
                evidence.append(f"{field}={match}")
    argv = command_source.get("argv")
    if isinstance(argv, list) and all(isinstance(value, str) for value in argv):
        match = _command_launches_model(
            " ".join(json.dumps(value) for value in argv),
            _dialect=command_dialect,
        )
        if match:
            evidence.append(f"argv={match}")
    return sorted(set(evidence))


def public_network_command_evidence(event: dict[str, Any]) -> list[str]:
    """Inspect actual command fields for a public-network client invocation."""

    evidence: list[str] = []
    item = event.get("item")
    if not isinstance(item, dict):
        return evidence
    item_type = canonical_tool_name(item.get("type"))
    command_source: dict[str, Any] | None = None
    command_dialect = "powershell"
    if item_type == "command_execution":
        command_source = {"command": item.get("command")}
    elif item_type == "mcp_tool_call":
        tool = canonical_tool_name(item.get("tool"))
        if tool.endswith(
            (
                "exec_command",
                "command_execution",
                "command_call",
                "shell_command",
                "shell_execution",
            )
        ):
            arguments = item.get("arguments")
            if isinstance(arguments, dict):
                command_source = arguments
                shell_value = arguments.get(
                    "shell", arguments.get("shell_executable")
                )
                if isinstance(shell_value, str):
                    shell_basename = (
                        shell_value.replace("\\", "/").rsplit("/", 1)[-1].lower()
                    )
                    if shell_basename in {"cmd", "cmd.exe"}:
                        command_dialect = "cmd"
                    elif shell_basename in {
                        "bash",
                        "bash.exe",
                        "sh",
                        "sh.exe",
                        "zsh",
                        "zsh.exe",
                    }:
                        command_dialect = "posix"
    if command_source is None:
        return evidence
    for field in ("command", "cmd", "command_line"):
        value = command_source.get(field)
        if isinstance(value, str):
            match = _command_accesses_public_network(
                value, _dialect=command_dialect
            )
            if match:
                evidence.append(f"{field}={match}")
    argv = command_source.get("argv")
    if isinstance(argv, list) and all(isinstance(value, str) for value in argv):
        match = _command_accesses_public_network(
            " ".join(json.dumps(value) for value in argv),
            _dialect=command_dialect,
        )
        if match:
            evidence.append(f"argv={match}")
    return sorted(set(evidence))


def _load_launch_record(path: Path) -> dict[str, Any]:
    if not path.is_absolute():
        raise TransportError("launch-record path must be absolute")
    try:
        raw = _read_stable_file(path, label="launch record").decode(
            "utf-8", errors="strict"
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise TransportError(f"cannot read strict-UTF-8 launch record: {exc}") from exc
    if not raw.strip():
        raise TransportError("launch record is empty")
    return _load_json_object(raw, label="launch record")


def _validate_argv(
    record: dict[str, Any], executable: Path, workspace: Path, actor: str
) -> list[str]:
    argv = record.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(value, str) or not value for value in argv)
    ):
        raise TransportError("launch record argv must be a non-empty string array")
    if argv_sha256(argv) != _required_sha256(record, "argv_sha256"):
        raise TransportError("launch record argv_sha256 does not match exact argv")

    argv_executable = _canonical_existing_path(argv[0], label="argv[0]", kind="file")
    if not _same_path(argv_executable, executable):
        raise TransportError("argv[0] does not match launch record executable_path")
    if argv_executable.name.lower() not in {"codex", "codex.exe"}:
        raise TransportError("argv[0] must be the Codex CLI executable")

    if argv.count("-") != 1 or argv[-1] != "-":
        raise TransportError("exact argv must end in one stdin prompt marker '-'")

    # Closed grammar: argv[0], optional global --search, exactly one exec, then
    # only the enumerated exec flags/pairs, followed by the sole stdin marker.
    cursor = 1
    if cursor < len(argv) and argv[cursor] == OPTIONAL_GLOBAL_FLAGS[0]:
        cursor += 1
    if cursor >= len(argv) or argv[cursor] != "exec":
        raise TransportError(
            "exact argv must place one Codex exec after the optional global --search"
        )
    cursor += 1

    required_flags = {flag: 0 for flag in REQUIRED_EXEC_FLAGS}
    optional_flags = {flag: 0 for flag in OPTIONAL_EXEC_FLAGS}
    workspace_values: list[str] = []
    sandbox_values: list[str] = []
    disable_modes: list[str] = []
    while cursor < len(argv) - 1:
        token = argv[cursor]
        if token in required_flags:
            required_flags[token] += 1
            cursor += 1
            continue
        if token in optional_flags:
            optional_flags[token] += 1
            cursor += 1
            continue
        if token == "-C":
            if cursor + 1 >= len(argv) - 1:
                raise TransportError("exact argv -C is missing its workspace argument")
            workspace_values.append(argv[cursor + 1])
            cursor += 2
            continue
        if token == "--sandbox":
            if cursor + 1 >= len(argv) - 1:
                raise TransportError("exact argv --sandbox is missing its value")
            sandbox_values.append(argv[cursor + 1])
            cursor += 2
            continue
        if token == "--disable":
            if cursor + 1 >= len(argv) - 1 or argv[cursor + 1] != "multi_agent":
                raise TransportError(
                    "exact argv permits --disable only for multi_agent"
                )
            disable_modes.append(MULTI_AGENT_DISABLE_FORMS[0])
            cursor += 2
            continue
        if token == "--disable=multi_agent":
            disable_modes.append(MULTI_AGENT_DISABLE_FORMS[1])
            cursor += 1
            continue
        if token == "-c":
            if (
                cursor + 1 >= len(argv) - 1
                or argv[cursor + 1] != "features.multi_agent=false"
            ):
                raise TransportError(
                    "exact argv permits -c only for features.multi_agent=false"
                )
            disable_modes.append(MULTI_AGENT_DISABLE_FORMS[2])
            cursor += 2
            continue
        raise TransportError(f"exact argv contains an unlisted token: {token!r}")

    if argv.count("exec") != 1:
        raise TransportError("exact argv must contain exactly one Codex exec")
    if argv.count(OPTIONAL_GLOBAL_FLAGS[0]) > 1:
        raise TransportError("exact argv permits --search at most once")
    if (
        NO_PUBLIC_NETWORK_ACTOR_RE.fullmatch(actor) is not None
        and argv.count(OPTIONAL_GLOBAL_FLAGS[0])
    ):
        raise TransportError(
            f"actor {actor} has public_endpoints=[none] and cannot enable --search"
        )
    for flag, count in required_flags.items():
        if count != 1:
            raise TransportError(f"exact argv must contain {flag} exactly once")
    for flag, count in optional_flags.items():
        if count > 1:
            raise TransportError(f"exact argv permits {flag} at most once")
    if len(disable_modes) != 1:
        raise TransportError(
            "exact argv must use exactly one permitted multi_agent disable form"
        )
    if len(workspace_values) != 1:
        raise TransportError("exact argv must contain one '-C <workspace>' pair")
    if sandbox_values != ["workspace-write"]:
        raise TransportError(
            "exact argv must contain one '--sandbox workspace-write' pair"
        )
    argv_workspace = _canonical_existing_path(
        workspace_values[0], label="argv -C workspace", kind="directory"
    )
    if not _same_path(argv_workspace, workspace):
        raise TransportError("argv -C workspace does not match launch record workspace")
    return list(argv)


def _validate_launch_record(
    record: dict[str, Any],
    *,
    record_path: Path,
    log_path: Path,
    raw_log_bytes: bytes,
    actor: str,
    expected_prompt_sha256: str,
    expected_launch_id: str,
    expected_process_sha256: str | None,
    expected_process_seal_sha256: str | None,
    expected_input_commitment_sha256: str | None,
    expected_output_commitment_sha256: str | None,
) -> dict[str, Any]:
    _require_closed_keys(
        record,
        required=set(LAUNCH_RECORD_FIELDS),
        label="launch record",
    )
    if record.get("schema") != LAUNCH_RECORD_SCHEMA:
        raise TransportError(f"launch record schema must be {LAUNCH_RECORD_SCHEMA}")
    record_actor = str(record.get("actor", "")).strip().upper()
    if record_actor != actor:
        raise TransportError(
            f"launch record actor {record_actor or '<missing>'} does not match {actor}"
        )

    launch_id = str(record.get("launch_id", "")).strip().lower()
    try:
        parsed_launch_id = str(uuid.UUID(launch_id))
    except (ValueError, AttributeError) as exc:
        raise TransportError("launch record launch_id must be a canonical UUID") from exc
    if launch_id != parsed_launch_id or launch_id != expected_launch_id:
        raise TransportError("launch record launch_id does not match expected launch ID")

    prompt_sha256 = _required_sha256(record, "prompt_sha256")
    if prompt_sha256 != expected_prompt_sha256:
        raise TransportError("launch record prompt_sha256 does not match expected prompt")
    prompt_path = _canonical_existing_path(
        record.get("prompt_path"), label="prompt_path", kind="file"
    )
    prompt_bytes = _required_positive_int(record, "prompt_bytes")
    if prompt_path.stat().st_size != prompt_bytes:
        raise TransportError("launch record prompt_bytes does not match prompt file")
    if _sha256_file(prompt_path, label="prompt file") != prompt_sha256:
        raise TransportError("launch record prompt_sha256 does not match prompt file")

    process_sha256 = _required_sha256(record, "process_sha256")
    process_seal_sha256 = _required_sha256(record, "process_seal_sha256")
    input_commitment_sha256 = _required_sha256(
        record, "input_commitment_sha256"
    )
    output_commitment_sha256 = _required_sha256(
        record, "output_commitment_sha256"
    )
    for observed, expected, label in (
        (process_sha256, expected_process_sha256, "process_sha256"),
        (
            process_seal_sha256,
            expected_process_seal_sha256,
            "process_seal_sha256",
        ),
        (
            input_commitment_sha256,
            expected_input_commitment_sha256,
            "input_commitment_sha256",
        ),
        (
            output_commitment_sha256,
            expected_output_commitment_sha256,
            "output_commitment_sha256",
        ),
    ):
        if expected is not None and observed != expected:
            raise TransportError(
                f"launch record {label} does not match the external anchor"
            )

    canonical_log = log_path
    recorded_log = _canonical_existing_path(
        record.get("log_path"), label="log_path", kind="file"
    )
    if not _same_path(canonical_log, recorded_log):
        raise TransportError("launch record log_path does not match audited log")
    log_bytes = _required_positive_int(record, "log_bytes")
    if len(raw_log_bytes) != log_bytes:
        raise TransportError("launch record log_bytes does not match audited log")
    log_sha256 = _required_sha256(record, "log_sha256")
    if _sha256_bytes(raw_log_bytes) != log_sha256:
        raise TransportError("launch record log_sha256 does not match audited log")

    executable = _canonical_existing_path(
        record.get("executable_path"), label="executable_path", kind="file"
    )
    executable_sha256 = _required_sha256(record, "executable_sha256")
    if _sha256_file(executable, label="Codex executable") != executable_sha256:
        raise TransportError(
            "launch record executable_sha256 does not match executable file"
        )
    cwd = _canonical_existing_path(record.get("cwd"), label="cwd", kind="directory")
    workspace = _canonical_existing_path(
        record.get("workspace"), label="workspace", kind="directory"
    )
    argv = _validate_argv(record, executable, workspace, actor)
    pid = _required_positive_int(record, "pid")
    exit_code = record.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
        raise TransportError("launch record exit_code must be integer 0")

    if any(
        _same_path(left, right)
        for left, right in (
            (record_path, log_path),
            (record_path, prompt_path),
            (log_path, prompt_path),
        )
    ):
        raise TransportError("launch record, prompt, and JSONL log must be distinct files")

    thread_id = record.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise TransportError("launch record thread_id must be a non-empty string")
    return {
        "actor": actor,
        "argv": argv,
        "cwd": str(cwd),
        "executable_sha256": executable_sha256,
        "exit_code": exit_code,
        "launch_id": launch_id,
        "log_sha256": log_sha256,
        "pid": pid,
        "prompt_sha256": prompt_sha256,
        "process_sha256": process_sha256,
        "process_seal_sha256": process_seal_sha256,
        "input_commitment_sha256": input_commitment_sha256,
        "output_commitment_sha256": output_commitment_sha256,
        "thread_id": thread_id.strip(),
        "workspace": str(workspace),
    }


def validate_log(
    path: Path,
    actor: str,
    launch_record_path: Path,
    expected_prompt_sha256: str,
    expected_launch_id: str,
    expected_process_sha256: str | None = None,
    expected_process_seal_sha256: str | None = None,
    expected_input_commitment_sha256: str | None = None,
    expected_output_commitment_sha256: str | None = None,
    expected_launch_record_sha256: str | None = None,
) -> dict[str, object]:
    canonical_actor = actor.strip().upper()
    if not ACTOR_RE.fullmatch(canonical_actor):
        raise TransportError("invalid actor ID")
    expected_prompt_sha256 = expected_prompt_sha256.strip().lower()
    if not SHA256_RE.fullmatch(expected_prompt_sha256):
        raise TransportError("expected prompt SHA-256 must have 64 hex digits")
    expected_launch_id = expected_launch_id.strip().lower()
    try:
        if str(uuid.UUID(expected_launch_id)) != expected_launch_id:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise TransportError("expected launch ID must be a canonical UUID") from exc
    normalized_external_hashes: list[str | None] = []
    for value, label in (
        (expected_process_sha256, "expected process SHA-256"),
        (expected_process_seal_sha256, "expected process-seal SHA-256"),
        (expected_input_commitment_sha256, "expected input-commitment SHA-256"),
        (expected_output_commitment_sha256, "expected output-commitment SHA-256"),
        (expected_launch_record_sha256, "expected launch-record SHA-256"),
    ):
        if value is None:
            normalized_external_hashes.append(None)
            continue
        normalized = value.strip().lower()
        if not SHA256_RE.fullmatch(normalized):
            raise TransportError(f"{label} must have 64 hex digits")
        normalized_external_hashes.append(normalized)
    (
        expected_process_sha256,
        expected_process_seal_sha256,
        expected_input_commitment_sha256,
        expected_output_commitment_sha256,
        expected_launch_record_sha256,
    ) = normalized_external_hashes
    if not path.is_absolute():
        raise TransportError("JSONL log path must be absolute")
    if not launch_record_path.is_absolute():
        raise TransportError("launch-record path must be absolute")

    canonical_log_path = _canonical_existing_path(
        str(path), label="audited JSONL log", kind="file"
    )
    canonical_record_path = _canonical_existing_path(
        str(launch_record_path), label="launch-record path", kind="file"
    )
    try:
        raw_bytes = _read_stable_file(canonical_log_path, label="JSONL transport log")
        raw = raw_bytes.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise TransportError(f"cannot read strict-UTF-8 JSONL log: {exc}") from exc

    try:
        record_bytes = _read_stable_file(
            canonical_record_path, label="launch record"
        )
        if (
            expected_launch_record_sha256 is not None
            and _sha256_bytes(record_bytes) != expected_launch_record_sha256
        ):
            raise TransportError(
                "launch record bytes do not match the external hash anchor"
            )
        record_text = record_bytes.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise TransportError(f"cannot read strict-UTF-8 launch record: {exc}") from exc
    if not record_text.strip():
        raise TransportError("launch record is empty")
    record = _load_json_object(record_text, label="launch record")
    binding = _validate_launch_record(
        record,
        record_path=canonical_record_path,
        log_path=canonical_log_path,
        raw_log_bytes=raw_bytes,
        actor=canonical_actor,
        expected_prompt_sha256=expected_prompt_sha256,
        expected_launch_id=expected_launch_id,
        expected_process_sha256=expected_process_sha256,
        expected_process_seal_sha256=expected_process_seal_sha256,
        expected_input_commitment_sha256=expected_input_commitment_sha256,
        expected_output_commitment_sha256=expected_output_commitment_sha256,
    )

    if not raw.strip():
        raise TransportError("JSONL transport log is empty")
    if not raw.endswith("\n"):
        raise TransportError("JSONL transport log is truncated or lacks its final newline")

    events: list[dict[str, Any]] = []
    thread_started_indices: list[int] = []
    turn_started_indices: list[int] = []
    turn_completed_indices: list[int] = []
    collaboration_violations: list[str] = []
    model_process_violations: list[str] = []
    schema_violations: list[str] = []
    public_network_violations: list[str] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise TransportError(f"line {line_number} is unexpectedly blank")
        event = _load_jsonl_event(line, label=f"line {line_number}")
        events.append(event)
        event_type = event.get("type")
        if event_type == "thread.started":
            thread_started_indices.append(len(events) - 1)
        elif event_type == "turn.started":
            turn_started_indices.append(len(events) - 1)
        elif event_type == "turn.completed":
            turn_completed_indices.append(len(events) - 1)
        for evidence in delegation_evidence(event):
            collaboration_violations.append(f"line {line_number}: {evidence}")
        for evidence in nested_model_process_evidence(event):
            model_process_violations.append(f"line {line_number}: {evidence}")
        if NO_PUBLIC_NETWORK_ACTOR_RE.fullmatch(canonical_actor) is not None:
            for evidence in public_network_command_evidence(event):
                public_network_violations.append(
                    f"line {line_number}: {evidence}"
                )
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "web_search":
                public_network_violations.append(
                    f"line {line_number}: web_search item"
                )
            elif isinstance(item, dict) and item.get("type") == "mcp_tool_call":
                server = str(item.get("server", ""))
                tool = str(item.get("tool", ""))
                network_name = f"{server} {tool}".casefold()
                if re.search(
                    r"(?:^|[^a-z0-9])(?:web|browser|http|fetch|url|search_query)"
                    r"(?:[^a-z0-9]|$)",
                    network_name,
                ):
                    public_network_violations.append(
                        f"line {line_number}: public-network MCP {server}/{tool}"
                    )
        try:
            validate_event_schema(event)
        except TransportError as exc:
            schema_violations.append(f"line {line_number}: {exc}")

    if len(thread_started_indices) != 1:
        raise TransportError(
            "transport log must contain exactly one thread.started event; "
            f"got {len(thread_started_indices)}"
        )
    if len(turn_started_indices) != 1:
        raise TransportError(
            "transport log must contain exactly one turn.started event; "
            f"got {len(turn_started_indices)}"
        )
    if len(turn_completed_indices) != 1:
        raise TransportError(
            "transport log must contain exactly one successful turn.completed event; "
            f"got {len(turn_completed_indices)}"
        )
    thread_index = thread_started_indices[0]
    turn_index = turn_started_indices[0]
    completed_index = turn_completed_indices[0]
    if not thread_index < turn_index < completed_index:
        raise TransportError("thread/turn lifecycle events are out of order")
    if thread_index != 0 or turn_index != 1:
        raise TransportError(
            "thread.started and turn.started must be the first two JSONL events"
        )
    if completed_index != len(events) - 1:
        raise TransportError("turn.completed must be the final JSONL event")
    recoverable_error_indices = recoverable_transport_error_indices(
        events, turn_index, completed_index
    )
    failures: list[str] = []
    for index, event in enumerate(events):
        if index in recoverable_error_indices:
            continue
        for evidence in failure_evidence(event):
            failures.append(f"line {index + 1}: {evidence}")

    thread_id = events[thread_index].get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise TransportError("thread.started must contain one non-empty thread_id")
    if thread_id.strip() != binding["thread_id"]:
        raise TransportError("JSONL thread_id does not match launch record thread_id")
    if failures:
        raise TransportError(
            "transport contains failure/error evidence: " + "; ".join(failures)
        )
    if collaboration_violations:
        raise TransportError(
            "actor attempted collaboration/redelegation: "
            + "; ".join(collaboration_violations)
        )
    if model_process_violations:
        raise TransportError(
            "actor attempted a nested Codex/model process: "
            + "; ".join(model_process_violations)
        )
    if public_network_violations:
        raise TransportError(
            f"actor {canonical_actor} accessed public network despite "
            "public_endpoints=[none]: " + "; ".join(public_network_violations)
        )
    if schema_violations:
        raise TransportError(
            "transport contains unknown or malformed JSONL event schema: "
            + "; ".join(schema_violations)
        )
    validate_item_lifecycle(events, turn_index, completed_index)

    completed_agent_messages = []
    for event in events[turn_index + 1 : completed_index]:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        message = item.get("text")
        if isinstance(message, str) and message.strip():
            completed_agent_messages.append(message)
    if not completed_agent_messages:
        raise TransportError(
            "successful transport must contain a non-empty completed agent_message"
        )

    if _read_stable_file(canonical_record_path, label="launch record") != record_bytes:
        raise TransportError("launch record changed during transport validation")
    if _read_stable_file(canonical_log_path, label="JSONL transport log") != raw_bytes:
        raise TransportError("JSONL transport log changed during transport validation")
    return {
        "actor": canonical_actor,
        "events": len(events),
        "thread_started": 1,
        "turn_started": 1,
        "turn_completed": 1,
        "thread_id": thread_id.strip(),
        "launch_id": binding["launch_id"],
        "prompt_sha256": binding["prompt_sha256"],
        "process_sha256": binding["process_sha256"],
        "process_seal_sha256": binding["process_seal_sha256"],
        "input_commitment_sha256": binding["input_commitment_sha256"],
        "output_commitment_sha256": binding["output_commitment_sha256"],
        "log_sha256": binding["log_sha256"],
        "pid": binding["pid"],
        "exit_code": binding["exit_code"],
        "recoverable_transport_error_events": len(recoverable_error_indices),
        "collaboration_events": 0,
        "nested_model_processes": 0,
        "public_network_events": 0,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--launch-record", type=Path, required=True)
    parser.add_argument("--expected-prompt-sha256", required=True)
    parser.add_argument("--expected-launch-id", required=True)
    parser.add_argument("--expected-process-sha256", required=True)
    parser.add_argument("--expected-process-seal-sha256", required=True)
    parser.add_argument("--expected-input-commitment-sha256", required=True)
    parser.add_argument("--expected-output-commitment-sha256", required=True)
    parser.add_argument("--expected-launch-record-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = validate_log(
            arguments.log,
            arguments.actor,
            arguments.launch_record,
            arguments.expected_prompt_sha256,
            arguments.expected_launch_id,
            arguments.expected_process_sha256,
            arguments.expected_process_seal_sha256,
            arguments.expected_input_commitment_sha256,
            arguments.expected_output_commitment_sha256,
            arguments.expected_launch_record_sha256,
        )
    except TransportError as exc:
        print(f"FAIL: {exc}")
        return 2
    print("PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
