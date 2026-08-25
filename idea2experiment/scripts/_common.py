from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


STAGES = [
    "INTAKE",
    "RESOURCE_AUDIT",
    "REPOSITORY_AUDIT",
    "DATA_AUDIT",
    "PROTOCOL_FREEZE",
    "DETERMINISTIC_SANITY",
    "TINY_OVERFIT",
    "BASELINE_REPRODUCTION",
    "PILOT",
    "MODEL_SCALING",
    "DATA_SCALING",
    "MODULE_STUDY",
    "PARAMETER_STUDY",
    "CONFIRMATORY",
    "ROBUSTNESS",
    "QUALITATIVE",
    "INDEPENDENT_AUDIT",
    "CLAIM_SYNC",
]

STAGE_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "blocked",
    "not_applicable",
    "stale",
    "invalidated",
}

NODE_STATUSES = {
    "PLANNED",
    "PREFLIGHT",
    "SMOKE",
    "QUEUED",
    "RUNNING",
    "EVALUATING",
    "AUDITING",
    "DONE",
    "FAILED_ENGINEERING",
    "FAILED_SCIENTIFIC",
    "INVALID_PROTOCOL",
    "BLOCKED",
    "CANCELLED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, fallback: str = "study") -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:64] or fallback


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


@contextmanager
def file_lock(path: Path, timeout_seconds: float = 30.0) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()} {utc_now()}\n".encode("utf-8"))
            os.close(descriptor)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > max(300.0, timeout_seconds * 4):
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {lock_path}")
            time.sleep(0.1)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def update_json(path: Path, updater: Callable[[Any], Any]) -> Any:
    with file_lock(path):
        data = load_json(path)
        updated = updater(data)
        write_json(path, updated)
        return updated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def resolve_study_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not (root / "study.json").is_file():
        raise FileNotFoundError(f"Not an idea2experiment study: {root}")
    return root


def safe_node_token(value: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return token or "ITEM"
