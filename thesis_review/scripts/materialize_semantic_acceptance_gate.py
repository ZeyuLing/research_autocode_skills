#!/usr/bin/env python3
"""Atomically materialize the current semantic-acceptance PASS/hash gate.

The command is Stage-O mechanics.  It reads only the current process envelope,
the frozen current actor outputs, and the closed ``06-semantic-acceptance``
set.  It refuses to create a gate unless every required semantic acceptor is a
validated PASS.  A stale gate is removed before a failed materialization can be
reported so it cannot accidentally authorize a later Chair launch.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


VALIDATOR = Path(__file__).with_name("validate_semantic_acceptance_output.py")
GATE_FILE = "06-semantic-acceptance-gate.json"


def is_local_link_or_reparse(path: Path) -> bool:
    """Detect symlinks and Windows reparse points without importing validators."""

    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return False


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "thesis_review_semantic_acceptance_for_materializer", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load semantic-acceptance validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def remove_stale_gate(path: Path) -> None:
    if path.is_symlink() or path.exists():
        path.unlink()


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_set_with_cache(
    module: Any,
    root: Path,
    shared: Any,
    *,
    require_gate: bool,
    derived_cache: dict[str, Any],
) -> tuple[list[str], dict[str, Any] | None]:
    """Use the current cache API while preserving test/dependency compatibility."""

    parameters = inspect.signature(module.validate_set).parameters
    if "derived_cache" in parameters:
        return module.validate_set(
            root,
            shared,
            require_gate=require_gate,
            derived_cache=derived_cache,
        )
    return module.validate_set(root, shared, require_gate=require_gate)


def materialize(
    root: Path, module: Any, *, stale_gate_already_removed: bool = False
) -> list[str]:
    errors: list[str] = []
    gate_path = root / GATE_FILE
    if is_local_link_or_reparse(root) or not root.is_dir():
        return ["round root is missing or unsafe"]
    # A previous PASS token must never survive a changed/failed acceptance set.
    if not stale_gate_already_removed:
        try:
            remove_stale_gate(gate_path)
        except OSError as exc:
            return [f"cannot remove stale semantic-acceptance gate safely: {exc}"]
    closure_succeeded = False
    derived_cache: dict[str, Any] = {}
    try:
        shared = module.load_shared_validator()
        set_errors, expected = validate_set_with_cache(
            module,
            root,
            shared,
            require_gate=False,
            derived_cache=derived_cache,
        )
        errors.extend(set_errors)
        if expected is None:
            errors.append(
                "semantic-acceptance set did not produce a complete gate projection"
            )
        if not errors:
            atomic_json_write(gate_path, expected)
            closure_errors, _ = validate_set_with_cache(
                module,
                root,
                shared,
                require_gate=True,
                derived_cache=derived_cache,
            )
            errors.extend(closure_errors)
            closure_succeeded = not errors
    except Exception as exc:  # fail closed while still executing cleanup below
        errors.append(f"semantic-acceptance gate materialization failed safely: {exc}")
    finally:
        if not closure_succeeded:
            try:
                remove_stale_gate(gate_path)
            except OSError as exc:
                errors.append(
                    f"cannot remove invalid materialized gate safely: {exc}"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_root", type=Path)
    args = parser.parse_args(argv)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        root = args.round_root.absolute()
        gate_path = root / GATE_FILE
        if is_local_link_or_reparse(root) or not root.is_dir():
            errors = ["round root is missing or unsafe"]
        else:
            # Remove the exact stale authorization token before importing any
            # validator dependency.  An import failure can therefore never
            # leave an old PASS gate in place.
            try:
                remove_stale_gate(gate_path)
                module = load_validator()
                errors = materialize(
                    root, module, stale_gate_already_removed=True
                )
            except Exception as exc:  # pragma: no cover - CLI fail-closed path
                errors = [
                    f"semantic-acceptance gate materializer failed safely: {exc}"
                ]
                try:
                    remove_stale_gate(gate_path)
                except OSError as cleanup_exc:
                    errors.append(
                        "cannot remove stale semantic-acceptance gate safely: "
                        f"{cleanup_exc}"
                    )
    except Exception as exc:  # pragma: no cover - fail closed at CLI boundary
        errors = [f"semantic-acceptance gate materializer failed safely: {exc}"]
    finally:
        sys.dont_write_bytecode = previous
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("MATERIALIZED")
    print(
        "Current all-PASS semantic-acceptance set was atomically bound to the "
        "process bytes, SA prompt plan, frozen target hashes, and private "
        "acceptance-file transport commitments."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
