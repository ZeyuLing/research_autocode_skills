#!/usr/bin/env python3
"""Build process-bound production prompts for the P, AI, C, and S actors.

Unlike :mod:`build_bound_actor_prompt`, this helper accepts no free-form role
body.  Both planning and verification render the complete prompt from the
stable process projection, the canonical review-bundle allowlist, the fixed
actor-owned output set, and the fixed scoped-gate command sequence.

Planning is deliberately possible before Stage P and before any actor view is
published.  Verification is deliberately possible only after the final
process has been sealed and the exact ``<run>/views/<actor>`` input tree has
been staged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import build_reviewer_prompt as reviewer  # noqa: E402
import manage_stage_o_workspace as stage_o  # noqa: E402
from actor_prompt_contract import (  # noqa: E402
    ActorContractError,
    render_bound_actor_contract,
)


PROMPT_SCHEMA = "thesis-review-canonical-actor-operational-prompt-v1"
VERIFICATION_SCHEMA = "thesis-review-canonical-actor-prompt-verification-v1"
SUPPORTED_ACTORS = ("P", "AI", "C", "S")
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
CONTROL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class ContractError(RuntimeError):
    """Fail-closed canonical-prompt contract error."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def require_actor(value: str) -> str:
    """Accept only the four production actors owned by this builder."""

    if value not in SUPPORTED_ACTORS:
        raise ContractError(
            "actor must be exactly one of P, AI, C, or S; H/V are not "
            "supported and R/SA actors require their dedicated builders"
        )
    return value


def require_sha256(value: str, label: str) -> str:
    digest = str(value).strip().upper()
    if HEX64_RE.fullmatch(digest) is None:
        raise ContractError(f"{label} must be one 64-hex SHA-256")
    return digest


def stable_process(value: dict[str, Any]) -> dict[str, Any]:
    """Return the path-safe stable projection used before Stage P."""

    try:
        projected = reviewer.stable_process_projection(value)
    except Exception as exc:
        raise ContractError(f"invalid stable/preplan process envelope: {exc}") from exc
    for field in ("round_id", "retry_id"):
        if CONTROL_ID_RE.fullmatch(str(projected[field])) is None:
            raise ContractError(
                f"stable process field {field} must be a path-free control ID"
            )
    if projected["output_language"] != "zh-CN":
        raise ContractError("canonical thesis-review actor output language must be zh-CN")
    return projected


def canonical_validator() -> Any:
    try:
        return reviewer.canonical_validator()
    except Exception as exc:
        raise ContractError(f"cannot load canonical review-bundle validator: {exc}") from exc


def canonical_opened_inputs(
    process: dict[str, Any], actor: str, validator: Any
) -> list[str]:
    """Derive the no-helper v1 allowlist without opening a round directory."""

    actor = require_actor(actor)
    try:
        opened = validator.canonical_stage_opened_inputs(
            process, reviewer.reviewer_count(process), actor, None
        )
    except Exception as exc:
        raise ContractError(f"cannot derive canonical {actor} allowlist: {exc}") from exc
    if not isinstance(opened, list) or not opened:
        raise ContractError(f"canonical validator returned no inputs for {actor}")
    if len(opened) != len(set(opened)):
        raise ContractError(f"canonical {actor} allowlist contains duplicates")
    normalized: list[str] = []
    for index, item in enumerate(opened):
        if not isinstance(item, str) or item != item.strip() or not item:
            raise ContractError(f"canonical {actor} allowlist item {index} is invalid")
        try:
            relative = stage_o.safe_relative(item, f"{actor} opened[{index}]")
        except Exception as exc:
            raise ContractError(f"unsafe canonical {actor} allowlist item: {exc}") from exc
        relative_text = relative.as_posix()
        if relative_text.startswith("helpers/"):
            raise ContractError(
                "production canonical P/AI/C/S prompts do not support Stage-H helpers"
            )
        normalized.append(relative_text)
    if normalized != opened:
        raise ContractError(f"canonical {actor} allowlist is not already normalized")
    return normalized


def staged_opened_inputs(
    view_root: Path, process: dict[str, Any], actor: str
) -> list[str]:
    """Re-derive the allowlist through the production Stage-O view algorithm."""

    try:
        if actor in {"P", "AI"}:
            opened, _instructions = stage_o.canonical_general_actor_inputs(
                view_root, process, actor
            )
        else:
            opened, _data, _instructions = stage_o.canonical_clean_actor_inputs(
                view_root, process, actor
            )
    except Exception as exc:
        raise ContractError(
            f"cannot derive staged {actor} view through Stage O: {exc}"
        ) from exc
    return [str(item) for item in opened]


def owned_outputs(process: dict[str, Any], actor: str) -> list[str]:
    actor = require_actor(actor)
    if actor == "P":
        outputs = list(stage_o.P_OUTPUTS)
    elif actor == "AI":
        outputs = list(stage_o.AI_OUTPUTS)
    elif actor == "C":
        outputs = list(stage_o.C_OUTPUTS)
    else:
        outputs = list(stage_o.S_OUTPUTS)
    if not outputs or len(outputs) != len(set(outputs)):
        raise ContractError(f"canonical {actor} output contract is invalid")
    for index, item in enumerate(outputs):
        try:
            relative = stage_o.safe_relative(item, f"{actor} output[{index}]")
        except Exception as exc:
            raise ContractError(f"unsafe canonical {actor} output: {exc}") from exc
        if relative.as_posix() != item:
            raise ContractError(f"canonical {actor} output is not normalized: {item}")
    return outputs


def instruction_commitments(opened: Iterable[str]) -> dict[str, str]:
    """Hash every canonical skill/rule input that contributes prompt authority."""

    commitments: dict[str, str] = {}
    for item in opened:
        if not (
            item == "SKILL.md"
            or item in stage_o.REFERENCE_NAMES
            or item.startswith("rules/scripts/")
        ):
            continue
        try:
            source = stage_o.instruction_source(stage_o.SKILL_ROOT, item)
            source = reviewer.absolute_no_alias(
                source, f"canonical instruction {item}", must_exist=True
            )
            reviewer.require_safe_regular(source, f"canonical instruction {item}")
            digest, _identity = reviewer.regular_file_snapshot(
                source, f"canonical instruction {item}"
            )
        except Exception as exc:
            raise ContractError(f"cannot bind canonical instruction {item}: {exc}") from exc
        commitments[item] = digest
    if "SKILL.md" not in commitments:
        raise ContractError("canonical actor allowlist omits SKILL.md")
    return commitments


def gate_commands(
    python_executable: Path, view_root: Path, actor: str
) -> list[list[str]]:
    actor = require_actor(actor)
    scripts = view_root / "rules" / "scripts"
    if actor == "P":
        return [
            [
                str(python_executable),
                "-B",
                str(scripts / "validate_stage_p_output.py"),
                str(view_root),
            ]
        ]
    if actor == "AI":
        return [
            [
                str(python_executable),
                "-B",
                str(scripts / "validate_ai_output.py"),
                str(view_root),
            ]
        ]
    materialize = [
        str(python_executable),
        "-B",
        str(scripts / "materialize_owner_outputs.py"),
        str(view_root),
        actor,
    ]
    validator_name = (
        "validate_chair_output.py" if actor == "C" else "validate_summary_output.py"
    )
    validate = [
        str(python_executable),
        "-B",
        str(scripts / validator_name),
        str(view_root),
    ]
    return [materialize, validate]


ROLE_DUTIES = {
    "P": (
        "Build only the neutral Stage-P navigation/policy/inventory packet from the "
        "frozen PDF and the listed rules. Record objective structure and inventories; "
        "do not pre-adjudicate quality, novelty, weakness, or a reviewer conclusion."
    ),
    "AI": (
        "Perform the standalone AI-style assessment over the complete authored-prose "
        "corpus defined by the packet and rules. Judge recurrent prose signals only; "
        "do not determine AI use, authorship, plagiarism, or misconduct, and do not "
        "browse or use any public endpoint."
    ),
    "C": (
        "Act as the independent holistic Chair. Recheck and reconcile the complete "
        "current accepted reviewer/AI evidence, preserve supported minority evidence, "
        "apply the degree/regime decision rules, and write only the canonical Chair "
        "synthesis and ledgers. Do not invent a finding or consult any earlier round."
    ),
    "S": (
        "Produce only the deterministic current-round user-facing compression of the "
        "frozen reviewer, AI, and Chair sources. Do not open the PDF, browse, re-review, "
        "re-adjudicate, merge, soften, escalate, omit, or invent any issue."
    ),
}


def public_endpoint_rule(actor: str) -> str:
    if actor == "P":
        return (
            "Use no public endpoint; the receipt value must be "
            "public_endpoints=[none]. governing_rule_urls are sealed process metadata "
            "only; do not open them. Any institutional rule used as Stage-P "
            "evidence must already be frozen in governing_local_files."
        )
    if actor == "C":
        return (
            "Use no public endpoint; the receipt value must be "
            "public_endpoints=[none]. Do not open governing_rule_urls or any "
            "bibliography/citation endpoint; adjudicate only from the frozen local "
            "Chair allowlist."
        )
    return "Use no public endpoint; the receipt value must be public_endpoints=[none]."


def render_prompt(
    view_root: Path,
    actor: str,
    process: dict[str, Any],
    opened: list[str],
    outputs: list[str],
    commitments: dict[str, str],
    python_executable: Path,
    python_sha256: str,
    scratch_dir: Path,
) -> bytes:
    """Render the complete immutable prompt.  There is no caller-authored body."""

    actor = require_actor(actor)
    opened_absolute = "\n".join(
        f"{index}. {view_root / Path(relative)}"
        for index, relative in enumerate(opened, start=1)
    )
    opened_receipt = "; ".join(opened)
    output_absolute = "\n".join(
        f"- {view_root / Path(relative)}" for relative in outputs
    )
    commitment_text = "\n".join(
        f"- {relative} SHA-256: {digest}"
        for relative, digest in commitments.items()
    )
    commands = gate_commands(python_executable, view_root, actor)
    command_text = "\n".join(
        f"{index}. {json.dumps(command, ensure_ascii=False, separators=(',', ':'))}"
        for index, command in enumerate(commands, start=1)
    )
    try:
        contract = render_bound_actor_contract(actor)
    except ActorContractError as exc:  # pragma: no cover - require_actor owns UX
        raise ContractError(str(exc)) from exc
    text = f"""Canonical thesis-review actor operational prompt

Prompt schema: {PROMPT_SCHEMA}
Actor ID: {actor}
Review round ID: {process['round_id']}
Review retry ID: {process['retry_id']}
Degree level: {process['degree_level']}
Output language: {process['output_language']}
Frozen PDF SHA-256: {process['selected_pdf_sha256']}
Frozen physical page count: {process['physical_page_count']}
Actor private view root: {view_root}
Exact Codex workspace (`-C`) value: {view_root}
Bundled/workspace Python executable: {python_executable}
Bundled/workspace Python SHA-256: {python_sha256}
Actor-private scratch directory: {scratch_dir}

Canonical instruction commitments:
{commitment_text}

{contract}

Stage O has supplied the complete local input universe as the private view above.
The finalized round is Stage-O-only control state and is intentionally not named.
Do not enumerate or open the private view's parent, a sibling, or any unlisted local
path. Do not use inherited conversation, user explanations, prior reviews, thesis
source, Git history, a repository, sibling work, code, experiment logs, hidden
evidence, or any other author-side material. No follow-up instruction will arrive.

Role duty:
{ROLE_DUTIES[actor]}

Open exactly these local inputs, in this order, and no others:
{opened_absolute}

The exact relative opened sequence for every actor-signed receipt is:
{opened_receipt}

Public-endpoint duty:
{public_endpoint_rule(actor)}

Write only these actor-owned outputs and do not replace an existing path:
{output_absolute}

Follow every closed schema in the listed rules exactly. In every actor-signed
Markdown output, preserve the required identity block, the exact fresh-context
declaration, the process-bound operational-prompt hash, and the exact closed
input-receipt/access declaration.
Canonical fresh-context declaration value: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
Canonical input-receipt grammar: received=[operational prompt]; opened=[the exact relative sequence above]; public_endpoints=[the permitted endpoints actually opened, or none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
Do not add, reorder, duplicate, or paraphrase a receipt clause. Recompute the frozen PDF hash at start and end whenever the
actor's canonical rules permit opening the PDF; Stage S copies the frozen identity
projection and must not open or hash the PDF.

The current working directory is the empty actor-private scratch directory bound
above. Use it only for transient mechanical files, never as review evidence; do not
enumerate its parent, and leave it empty before exit. Final artifacts belong only
at the actor-owned paths in the private view.

Run commands with `PYTHONDONTWRITEBYTECODE=1`. The following are exact argv arrays,
not shell snippets. Run them yourself, in order, using the exact executable and
paths shown. Require the materializer (when present) to exit 0 with first nonempty
stdout `MATERIALIZED`, and require the terminal scoped validator to exit 0 with
first nonempty stdout `PASS`:
{command_text}

Correct only this actor's owned outputs. After any semantic-source edit, rerun the
materializer before the scoped validator. A defect in any frozen input, rule,
process field, or upstream artifact is a whole-retry failure; do not patch it.
Leave no `__pycache__` directory or `.pyc` file.
"""
    return text.replace("\r\n", "\n").encode("utf-8")


def validate_round_and_view_paths(
    round_root_value: Path,
    view_root_value: Path,
    actor: str,
    *,
    view_must_exist: bool,
) -> tuple[Path, Path, Path]:
    try:
        round_root = reviewer.absolute_no_alias(
            round_root_value, "round root", must_exist=True
        )
        reviewer.require_safe_directory(round_root, "round root")
    except Exception as exc:
        raise ContractError(f"invalid round root: {exc}") from exc
    if round_root.name != "round":
        raise ContractError("round root must be exactly the 'round' child of one run root")
    try:
        run_root = reviewer.absolute_no_alias(
            round_root.parent, "run root", must_exist=True
        )
        reviewer.require_safe_directory(run_root, "run root")
        view_root = reviewer.validate_reviewer_view_root(
            view_root_value, run_root, actor, must_exist=view_must_exist
        )
    except Exception as exc:
        raise ContractError(f"invalid canonical actor view: {exc}") from exc
    return run_root, round_root, view_root


def validate_scratch(
    scratch_value: Path, run_root: Path, view_root: Path
) -> Path:
    try:
        scratch = reviewer.absolute_no_alias(
            scratch_value, "actor-private scratch directory", must_exist=True
        )
        reviewer.require_safe_directory(scratch, "actor-private scratch directory")
    except Exception as exc:
        raise ContractError(f"invalid actor-private scratch directory: {exc}") from exc
    try:
        # During planning the exact future view does not yet exist, so physical
        # containment cannot be queried for that boundary.  Lexical containment
        # is sufficient there because both paths have already passed canonical
        # spelling/reparse-ancestor checks.  Verification upgrades the same
        # check to the physical boundary once the view exists.
        view_overlap = (
            reviewer.boundaries_overlap(scratch, view_root)
            if os.path.lexists(view_root)
            else reviewer.is_within(scratch, view_root)
            or reviewer.is_within(view_root, scratch)
        )
        if reviewer.boundaries_overlap(scratch, run_root) or view_overlap:
            raise ContractError(
                "actor-private scratch must not overlap the run or actor view"
            )
        first = next(scratch.iterdir(), None)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"cannot validate actor-private scratch: {exc}") from exc
    if first is not None:
        raise ContractError("actor-private scratch must be empty")
    return scratch


def validate_python(value: Path, run_root: Path) -> tuple[Path, str, dict[str, int]]:
    try:
        executable, digest = reviewer.validate_python_executable(value)
        snapshot_digest, identity = reviewer.regular_file_snapshot(
            executable, "bundled/workspace Python executable"
        )
    except Exception as exc:
        raise ContractError(f"invalid bundled/workspace Python executable: {exc}") from exc
    if digest != snapshot_digest:
        raise ContractError("Python executable changed during binding")
    if reviewer.boundaries_overlap(executable, run_root):
        raise ContractError("Python executable must remain outside the complete run")
    return executable, digest, identity


def plan_prompt(
    process_path_value: Path,
    round_root_value: Path,
    view_root_value: Path,
    actor_value: str,
    output_value: Path,
    python_executable_value: Path,
    scratch_value: Path,
) -> dict[str, Any]:
    actor = require_actor(actor_value)
    run_root, round_root, view_root = validate_round_and_view_paths(
        round_root_value, view_root_value, actor, view_must_exist=False
    )
    try:
        process_path = reviewer.absolute_no_alias(
            process_path_value, "stable/preplan process envelope", must_exist=True
        )
        reviewer.require_safe_regular(process_path, "stable/preplan process envelope")
        process_snapshot = reviewer.regular_file_snapshot(
            process_path, "stable/preplan process envelope"
        )
        process = stable_process(
            reviewer.read_json_object(process_path, "stable/preplan process envelope")
        )
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"cannot read stable/preplan process: {exc}") from exc
    python_executable, python_sha256, python_identity = validate_python(
        python_executable_value, run_root
    )
    scratch = validate_scratch(scratch_value, run_root, view_root)
    try:
        output = reviewer.absolute_no_alias(
            output_value, "canonical actor prompt output", must_exist=False
        )
        reviewer.require_safe_directory(output.parent, "prompt output parent")
    except Exception as exc:
        raise ContractError(f"invalid prompt output: {exc}") from exc
    if reviewer.is_within_boundary(output, run_root):
        raise ContractError("planned prompt must remain outside the complete run root")
    if reviewer.is_within_boundary(output, scratch):
        raise ContractError("planned prompt must remain outside actor scratch")
    if output == process_path or output == python_executable:
        raise ContractError("prompt output must be distinct from every bound input")

    validator = canonical_validator()
    opened = canonical_opened_inputs(process, actor, validator)
    outputs = owned_outputs(process, actor)
    commitments = instruction_commitments(opened)
    prompt = render_prompt(
        view_root,
        actor,
        process,
        opened,
        outputs,
        commitments,
        python_executable,
        python_sha256,
        scratch,
    )
    try:
        prompt_snapshot = reviewer.exclusive_write(output, prompt)
    except Exception as exc:
        raise ContractError(f"cannot publish canonical actor prompt: {exc}") from exc

    try:
        if reviewer.regular_file_snapshot(
            process_path, "stable/preplan process envelope"
        ) != process_snapshot:
            raise ContractError("stable/preplan process changed during planning")
        if reviewer.regular_file_snapshot(
            python_executable, "bundled/workspace Python executable"
        ) != (python_sha256, python_identity):
            raise ContractError("Python executable changed during planning")
        validate_scratch(scratch, run_root, view_root)
        validate_round_and_view_paths(
            round_root, view_root, actor, view_must_exist=False
        )
        if reviewer.regular_file_snapshot(output, "created prompt") != prompt_snapshot:
            raise ContractError("created prompt changed during planning")
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"terminal planning closure failed: {exc}") from exc
    return {
        "schema": PROMPT_SCHEMA,
        "operation": "plan",
        "actor": actor,
        "run_root": str(run_root),
        "round_root": str(round_root),
        "view_root": str(view_root),
        "codex_workspace": str(view_root),
        "prompt_file": str(output),
        "prompt_sha256": sha256_bytes(prompt),
        "python_executable": str(python_executable),
        "python_executable_sha256": python_sha256,
        "scratch_dir": str(scratch),
        "stable_process_fields": process,
        "opened": opened,
        "owned_outputs": outputs,
        "instruction_sha256": commitments,
        "gate_commands": gate_commands(python_executable, view_root, actor),
    }


def snapshot_paths(root: Path, relative_paths: Iterable[str]) -> dict[str, tuple[int, int, int, int, str]]:
    snapshots: dict[str, tuple[int, int, int, int, str]] = {}
    for item in relative_paths:
        try:
            snapshots[item] = stage_o.file_identity(root / Path(item))
        except Exception as exc:
            raise ContractError(f"cannot snapshot {root / Path(item)}: {exc}") from exc
    return snapshots


def require_unchanged_paths(
    root: Path,
    snapshots: dict[str, tuple[int, int, int, int, str]],
    label: str,
) -> None:
    current = snapshot_paths(root, snapshots)
    if current != snapshots:
        raise ContractError(f"{label} changed during canonical prompt verification")


def verify_prompt(
    run_root_value: Path,
    round_root_value: Path,
    view_root_value: Path,
    prompt_value: Path,
    actor_value: str,
    expected_process_sha256_value: str,
    expected_seal_sha256_value: str,
    python_executable_value: Path,
    scratch_value: Path,
) -> dict[str, Any]:
    actor = require_actor(actor_value)
    run_root, round_root, view_root = validate_round_and_view_paths(
        round_root_value, view_root_value, actor, view_must_exist=True
    )
    try:
        supplied_run = reviewer.absolute_no_alias(
            run_root_value, "supplied run root", must_exist=True
        )
    except Exception as exc:
        raise ContractError(f"invalid supplied run root: {exc}") from exc
    if supplied_run != run_root:
        raise ContractError("--run-root must be the exact parent of --round-root")
    expected_process_sha256 = require_sha256(
        expected_process_sha256_value, "expected final process SHA-256"
    )
    expected_seal_sha256 = require_sha256(
        expected_seal_sha256_value, "expected process-seal SHA-256"
    )
    python_executable, python_sha256, python_identity = validate_python(
        python_executable_value, run_root
    )
    scratch = validate_scratch(scratch_value, run_root, view_root)
    try:
        prompt_path = reviewer.absolute_no_alias(
            prompt_value, "planned canonical actor prompt", must_exist=True
        )
        reviewer.require_safe_regular(prompt_path, "planned canonical actor prompt")
        prompt_snapshot = reviewer.regular_file_snapshot(
            prompt_path, "planned canonical actor prompt"
        )
    except Exception as exc:
        raise ContractError(f"invalid planned prompt: {exc}") from exc
    if reviewer.is_within_boundary(prompt_path, run_root) or reviewer.is_within_boundary(
        prompt_path, scratch
    ):
        raise ContractError("planned prompt must remain outside run root and scratch")

    process_path = round_root / "00-process-parameters.json"
    view_process_path = view_root / "00-process-parameters.json"
    try:
        process_snapshot = reviewer.regular_file_snapshot(
            process_path, "final process envelope"
        )
        view_process_snapshot = reviewer.regular_file_snapshot(
            view_process_path, "private-view process envelope"
        )
        process_bytes = process_path.read_bytes()
        view_process_bytes = view_process_path.read_bytes()
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read prompt verification inputs: {exc}") from exc
    if sha256_bytes(process_bytes) != process_snapshot[0]:
        raise ContractError("final process changed during its snapshot read")
    if process_snapshot[0] != expected_process_sha256:
        raise ContractError("final process differs from the external SHA-256 anchor")
    if view_process_bytes != process_bytes or view_process_snapshot[0] != expected_process_sha256:
        raise ContractError("private-view process differs from the sealed final process")
    if sha256_bytes(prompt_bytes) != prompt_snapshot[0]:
        raise ContractError("planned prompt changed during its snapshot read")
    try:
        process = reviewer.read_json_object(process_path, "final process envelope")
    except Exception as exc:
        raise ContractError(f"invalid final process envelope: {exc}") from exc
    stable = stable_process(process)

    seal_first: dict[str, Any]
    try:
        seal_first = reviewer.verify_real_process_seal(
            run_root, expected_process_sha256, expected_seal_sha256
        )
    except Exception as exc:
        raise ContractError(f"sealed process verification failed: {exc}") from exc

    validator = canonical_validator()
    process_errors: list[str] = []
    stage_v_present = isinstance(process.get("actor_prompt_sha256"), dict) and (
        "V" in process["actor_prompt_sha256"]
    )
    try:
        validated_process, _pdf, _hash, _pages, count, _sizes = validator.validate_process(
            round_root,
            process_errors,
            enforce_single_reviewer_pdf=True,
            validate_governing_file_bytes=True,
            validate_frozen_pdf_bytes=True,
            stage_v_present_override=stage_v_present,
            process_override=process,
        )
    except Exception as exc:
        raise ContractError(f"canonical final-process validation failed: {exc}") from exc
    if process_errors or validated_process != process or count != reviewer.reviewer_count(stable):
        raise ContractError(
            "final process/PDF/governing inputs fail canonical validation: "
            + "; ".join(process_errors or ["canonical process projection mismatch"])
        )
    view_errors: list[str] = []
    try:
        view_process = reviewer.read_json_object(
            view_process_path, "private-view process envelope"
        )
        # Stage S intentionally receives neither the frozen PDF nor governing
        # files, so its process projection is byte-checked above but cannot be
        # passed to the PDF-opening process validator.  P/AI/C do receive the
        # process-selected PDF and can be validated in-place.
        if actor != "S":
            view_validated, _vp, _vh, _vpages, view_count, _vsizes = validator.validate_process(
                view_root,
                view_errors,
                enforce_single_reviewer_pdf=True,
                validate_governing_file_bytes=True,
                validate_frozen_pdf_bytes=True,
                stage_v_present_override=stage_v_present,
                process_override=view_process,
            )
        else:
            view_validated = view_process
            view_count = count
    except Exception as exc:
        raise ContractError(f"canonical private-view process validation failed: {exc}") from exc
    if (
        view_errors
        or view_process != process
        or view_validated != process
        or view_count != count
    ):
        raise ContractError(
            "private-view process/PDF/governing inputs differ from final process: "
            + "; ".join(view_errors or ["process projection mismatch"])
        )

    planned_opened = canonical_opened_inputs(stable, actor, validator)
    actual_opened = staged_opened_inputs(view_root, process, actor)
    if actual_opened != planned_opened:
        raise ContractError(
            "staged actor allowlist differs from the pre-Stage-P canonical plan"
        )
    outputs = owned_outputs(stable, actor)
    try:
        view_topology = stage_o.closed_view_snapshot(view_root, actual_opened, validator)
    except Exception as exc:
        raise ContractError(f"actor private view is not exact and input-only: {exc}") from exc
    source_snapshots = snapshot_paths(round_root, actual_opened)
    view_snapshots = snapshot_paths(view_root, actual_opened)
    for relative in actual_opened:
        if (
            source_snapshots[relative][2] != view_snapshots[relative][2]
            or source_snapshots[relative][4] != view_snapshots[relative][4]
        ):
            raise ContractError(
                f"private-view input bytes/metadata differ from final round: {relative}"
            )

    commitments = instruction_commitments(actual_opened)
    for relative, digest in commitments.items():
        if source_snapshots[relative][4] != digest or view_snapshots[relative][4] != digest:
            raise ContractError(
                f"staged instruction differs from canonical skill bytes: {relative}"
            )
    expected_prompt = render_prompt(
        view_root,
        actor,
        stable,
        planned_opened,
        outputs,
        commitments,
        python_executable,
        python_sha256,
        scratch,
    )
    if prompt_bytes != expected_prompt:
        raise ContractError(
            "planned prompt bytes differ from the canonical final reconstruction"
        )
    prompt_map = process.get("actor_prompt_sha256")
    if not isinstance(prompt_map, dict) or str(prompt_map.get(actor, "")).upper() != prompt_snapshot[0]:
        raise ContractError(
            f"prompt SHA-256 does not equal process.actor_prompt_sha256[{actor}]"
        )

    # Terminal closure: recheck every exact byte/identity and the sealed process.
    require_unchanged_paths(round_root, source_snapshots, "final-round prompt inputs")
    require_unchanged_paths(view_root, view_snapshots, "private-view prompt inputs")
    try:
        if stage_o.closed_view_snapshot(view_root, actual_opened, validator) != view_topology:
            raise ContractError("actor private-view topology changed during verification")
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"terminal private-view closure failed: {exc}") from exc
    if reviewer.regular_file_snapshot(
        process_path, "final process envelope"
    ) != process_snapshot:
        raise ContractError("final process changed during verification")
    if reviewer.regular_file_snapshot(
        view_process_path, "private-view process envelope"
    ) != view_process_snapshot:
        raise ContractError("private-view process changed during verification")
    if reviewer.regular_file_snapshot(
        prompt_path, "planned canonical actor prompt"
    ) != prompt_snapshot:
        raise ContractError("planned prompt changed during verification")
    if reviewer.regular_file_snapshot(
        python_executable, "bundled/workspace Python executable"
    ) != (python_sha256, python_identity):
        raise ContractError("Python executable changed during verification")
    validate_scratch(scratch, run_root, view_root)
    try:
        seal_last = reviewer.verify_real_process_seal(
            run_root, expected_process_sha256, expected_seal_sha256
        )
    except Exception as exc:
        raise ContractError(f"terminal sealed-process verification failed: {exc}") from exc
    if seal_last != seal_first:
        raise ContractError("sealed-process result changed during verification")
    require_unchanged_paths(round_root, source_snapshots, "terminal final-round inputs")
    require_unchanged_paths(view_root, view_snapshots, "terminal private-view inputs")
    if stage_o.closed_view_snapshot(view_root, actual_opened, validator) != view_topology:
        raise ContractError("actor private-view topology changed at terminal boundary")
    return {
        "schema": VERIFICATION_SCHEMA,
        "operation": "verify",
        "status": "VERIFIED",
        "actor": actor,
        "run_root": str(run_root),
        "round_root": str(round_root),
        "view_root": str(view_root),
        "codex_workspace": str(view_root),
        "prompt_file": str(prompt_path),
        "prompt_sha256": prompt_snapshot[0],
        "process_sha256": expected_process_sha256,
        "expected_seal_sha256": expected_seal_sha256,
        "process_seal": seal_last,
        "python_executable": str(python_executable),
        "python_executable_sha256": python_sha256,
        "scratch_dir": str(scratch),
        "opened": actual_opened,
        "owned_outputs": outputs,
        "instruction_sha256": commitments,
        "gate_commands": gate_commands(python_executable, view_root, actor),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", allow_abbrev=False)
    plan.add_argument("--process", type=Path, required=True)
    plan.add_argument("--round-root", type=Path, required=True)
    plan.add_argument("--view-root", type=Path, required=True)
    plan.add_argument("--actor", required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--python-executable", type=Path, required=True)
    plan.add_argument("--scratch-dir", type=Path, required=True)

    verify = subparsers.add_parser("verify", allow_abbrev=False)
    verify.add_argument("--run-root", type=Path, required=True)
    verify.add_argument("--round-root", type=Path, required=True)
    verify.add_argument("--view-root", type=Path, required=True)
    verify.add_argument("--prompt", type=Path, required=True)
    verify.add_argument("--actor", required=True)
    verify.add_argument("--expected-process-sha256", required=True)
    verify.add_argument("--expected-seal-sha256", required=True)
    verify.add_argument("--python-executable", type=Path, required=True)
    verify.add_argument("--scratch-dir", type=Path, required=True)
    return parser.parse_args(argv)


def print_result(status: str, value: dict[str, Any] | None = None, error: str = "") -> int:
    print(status)
    if value is not None:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    if error:
        print(error)
    return 0 if status in {"PLANNED", "VERIFIED"} else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if args.command == "plan":
            result = plan_prompt(
                args.process,
                args.round_root,
                args.view_root,
                args.actor,
                args.output,
                args.python_executable,
                args.scratch_dir,
            )
            return print_result("PLANNED", result)
        result = verify_prompt(
            args.run_root,
            args.round_root,
            args.view_root,
            args.prompt,
            args.actor,
            args.expected_process_sha256,
            args.expected_seal_sha256,
            args.python_executable,
            args.scratch_dir,
        )
        return print_result("VERIFIED", result)
    except ContractError as exc:
        return print_result("FAIL", error=str(exc))
    except Exception as exc:  # pragma: no cover - fail-closed CLI boundary
        return print_result("FAIL", error=f"canonical actor prompt helper failed safely: {exc}")
    finally:
        sys.dont_write_bytecode = previous


if __name__ == "__main__":
    raise SystemExit(main())
