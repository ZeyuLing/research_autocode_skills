#!/usr/bin/env python3
"""Read-only mechanical gate for one non-audit-owner reviewer report.

The command accepts the exact current bundle root and actor ID.  It opens only
the process-selected frozen inputs and that actor's own report.  It exists so
ordinary reviewers cannot finish with a semantically useful but mechanically
non-canonical report and leave the defect to the post-Chair bundle gate.

Audit owners use their dedicated scoped validators because those validators
must also reconcile the actor-owned 02/03/04 ledgers.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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
        "thesis_review_bundle_validator_for_reviewer", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def print_result(actor_id: str, errors: list[str]) -> int:
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("PASS")
    print(
        f"Current {actor_id} report, receipt, verdict, findings, questions, "
        "Gate A--I matrix, and frozen-PDF anchors passed the read-only "
        "mechanical gate."
    )
    return 0


def preflight_exact_inputs(
    module: Any, root: Path, actor_id: str, errors: list[str]
) -> dict[str, Any] | None:
    if module.is_link_or_reparse(root) or not root.is_dir():
        errors.append(
            "round directory is missing or is a symlink/junction/reparse point"
        )
        return None
    process_path = root / "00-process-parameters.json"
    report_path = root / f"{actor_id}-comprehensive-review.md"
    for path, label in (
        (process_path, "00-process-parameters.json"),
        (report_path, f"{actor_id}-comprehensive-review.md"),
    ):
        if module.is_link_or_reparse(path) or not path.is_file():
            errors.append(f"missing or unsafe required reviewer input: {label}")
    if errors:
        return None
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read 00-process-parameters.json: {exc}")
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
    local_files = process.get("governing_local_files")
    if isinstance(local_files, list):
        for item in local_files:
            filename = item.get("neutral_file") if isinstance(item, dict) else None
            if not safe_dynamic_round_basename(module, filename):
                errors.append(
                    "governing_local_files contains an unsafe or reserved neutral_file"
                )
                continue
            path = root / filename
            if module.is_link_or_reparse(path) or not path.is_file():
                errors.append(f"missing or unsafe governing input: {filename}")
    return process if not errors else None


def validate_reviewer(root: Path, actor_id: str, module: Any) -> list[str]:
    errors: list[str] = []
    process = preflight_exact_inputs(module, root, actor_id, errors)
    if process is None:
        return errors
    match = re.fullmatch(r"R([1-9]\d*)", actor_id)
    if match is None:
        return [f"invalid reviewer actor ID: {actor_id!r}"]
    reviewer_index = int(match.group(1))

    prompt_map = process.get("actor_prompt_sha256")
    validated_process, _, expected_hash, page_count, reviewer_count, _ = (
        module.validate_process(
            root,
            errors,
            enforce_single_reviewer_pdf=False,
            process_override=process,
            stage_v_present_override=(
                isinstance(prompt_map, dict) and "V" in prompt_map
            ),
        )
    )
    if not validated_process or not expected_hash:
        return errors
    if reviewer_index > reviewer_count:
        errors.append(
            f"{actor_id} is outside the process reviewer_count={reviewer_count}"
        )
        return errors
    degree_level = validated_process.get("degree_level")
    citation_owner = (
        "R4" if degree_level == "doctorate" else "R3"
    )
    page_bib_owner = (
        "R5" if degree_level == "doctorate" else "R3"
    )
    if actor_id in {citation_owner, page_bib_owner}:
        errors.append(
            f"{actor_id} is an exhaustive-audit owner and must use its "
            "dedicated ledger-aware scoped validator"
        )
        return errors

    rule_public_endpoints = {
        value
        for value in validated_process.get("governing_rule_urls", [])
        if isinstance(value, str)
    }
    module.validate_reviewer_report(
        root / f"{actor_id}-comprehensive-review.md",
        expected_hash,
        reviewer_index,
        validated_process,
        reviewer_count,
        rule_public_endpoints,
        rule_public_endpoints,
        degree_level,
        validated_process.get("decision_regime_status"),
        module.process_governing_sources(validated_process),
        {},
        page_count,
        errors,
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    parser.add_argument("actor_id")
    args = parser.parse_args(argv)
    actor_id = args.actor_id.upper()
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = load_validator()
        errors = validate_reviewer(args.round_directory.absolute(), actor_id, module)
        return print_result(actor_id, errors)
    except Exception as exc:
        return print_result(
            actor_id, [f"reviewer validator could not complete safely: {exc}"]
        )
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting


if __name__ == "__main__":
    sys.exit(main())
