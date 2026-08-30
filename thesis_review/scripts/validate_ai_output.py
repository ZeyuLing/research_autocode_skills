#!/usr/bin/env python3
"""Read-only mechanical gate for the independent AI-style assessment."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")


def safe_dynamic_round_basename(module: Any, value: Any) -> bool:
    return (
        isinstance(value, str)
        and module.is_neutral_portable_basename(value)
        and module.portable_basename_key(value)
        not in module.RESERVED_ROUND_BASENAME_KEYS
        and module.RENDER_ARTIFACT_BASENAME_RE.fullmatch(value) is None
    )


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "thesis_review_bundle_validator_for_ai", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight_ai_boundary(
    module: Any, root: Path, errors: list[str]
) -> dict[str, Any] | None:
    """Validate only exact AI-allowlisted paths; never enumerate the round."""

    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append(
            "round directory is missing or is a symlink/junction/reparse point"
        )
        return None
    for filename in (
        "00-process-parameters.json",
        "00-manifest.md",
        "00-page-inventory.csv",
        "05-ai-style-assessment.md",
    ):
        path = root / filename
        if module.is_link_or_reparse(path) or not path.is_file():
            errors.append(f"missing or unsafe required AI input: {filename}")
    if errors:
        return None
    process_path = root / "00-process-parameters.json"
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot safely preflight 00-process-parameters.json: {exc}")
        return None
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return None
    frozen_name = process.get("frozen_pdf_file")
    if not safe_dynamic_round_basename(module, frozen_name):
        errors.append("frozen_pdf_file is unsafe or collides with a reserved basename")
        return None
    frozen_path = root / frozen_name
    if module.is_link_or_reparse(frozen_path) or not frozen_path.is_file():
        errors.append("process-selected frozen PDF is missing or unsafe")
    return process if not errors else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    root = args.round_directory.absolute()
    errors: list[str] = []
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_validator()
        preflight_process = preflight_ai_boundary(module, root, errors)
        if preflight_process is not None:
            prompt_map = preflight_process.get("actor_prompt_sha256")
            process, _, expected_hash, page_count, reviewer_count, _ = (
                module.validate_process(
                    root,
                    errors,
                    enforce_single_reviewer_pdf=False,
                    validate_governing_file_bytes=False,
                    process_override=preflight_process,
                    stage_v_present_override=(
                        isinstance(prompt_map, dict) and "V" in prompt_map
                    ),
                )
            )
            if process and expected_hash:
                module.validate_ai_report(
                    root / "05-ai-style-assessment.md",
                    expected_hash,
                    page_count,
                    process,
                    reviewer_count,
                    errors,
                )
    except Exception as exc:
        errors.append(f"AI validator could not complete safely: {exc}")
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("PASS")
    print(
        "Current standalone AI-style report, receipt, signal, evidence, "
        "actionability split, and frozen-PDF anchors passed the read-only "
        "mechanical gate."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
