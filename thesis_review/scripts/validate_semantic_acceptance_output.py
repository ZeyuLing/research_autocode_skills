#!/usr/bin/env python3
"""Read-only gate for fresh per-actor semantic-acceptance artifacts.

This validator deliberately does not adjudicate a thesis.  It verifies that a
fresh semantic acceptor bound its work to one frozen target actor, covered the
target's complete mechanically derivable responsibility set, recorded no
unchecked state, used only the target actor's public authority, and did not
produce a schema-shaped/template-only acceptance artifact.

Single-actor view mode::

    python validate_semantic_acceptance_output.py <view> R4

Current-round set mode::

    python validate_semantic_acceptance_output.py <round-root> --set
    python validate_semantic_acceptance_output.py <round-root> --set --require-gate

The script imports shared path, receipt, PDF-hash, and CSV helpers from the
canonical bundle validator.  It never writes an artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SHARED_VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
ACCEPTANCE_DIRECTORY = "06-semantic-acceptance"
GATE_FILE = "06-semantic-acceptance-gate.json"
ROUND_ROOT_ACTOR_OUTPUT_RE = re.compile(
    r"SA-(?:R[1-5]|AI)\.(?:md|csv)\Z", re.IGNORECASE
)
FRESH_CONTEXT_SENTENCE = (
    "no inherited user/thread/task turns beyond system/developer "
    "instructions and the exact operational prompt"
)
BOUNDARY_SENTENCE = (
    "this actor did not create, modify, merge, grade, or adjudicate thesis "
    "findings; it evaluated only whether the frozen target actor outputs were "
    "semantically supported, complete for their mandatory scope, and "
    "admissible to the Chair."
)
CSV_COLUMNS = (
    "AcceptanceRowID",
    "TargetUnitType",
    "TargetUnitID",
    "TargetArtifact",
    "TargetArtifactSHA256",
    "CheckClass",
    "AcceptanceDisposition",
    "EvidenceAnchor",
    "SemanticBasis",
)
ALLOWED_UNIT_TYPES = {
    "gate",
    "chapter",
    "finding",
    "question",
    "verdict",
    "citation-pair",
    "page",
    "bibliography-field",
    "ai-finding",
    "ai-judgment",
}
CHECK_CLASS_BY_UNIT_TYPE = {
    "gate": "semantic-coverage",
    "chapter": "whole-chapter",
    "finding": "evidence-support",
    "question": "scope-validity",
    "verdict": "grade-consistency",
    "citation-pair": "citation-claim",
    "page": "rendered-page",
    "bibliography-field": "bibliography-field",
    "ai-finding": "style-evidence",
    "ai-judgment": "non-attribution",
}
HEX64_RE = re.compile(r"[0-9A-Fa-f]{64}")
ACTOR_RE = re.compile(r"(?:R[1-5]|AI)")
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}|`\"';,]+")
PHYSICAL_PAGE_RE = re.compile(
    r"(?i)physical\s+p\.\s*(?P<start>[1-9]\d*)"
    r"(?:\s*[-\u2013\u2014]\s*(?P<end>[1-9]\d*))?"
    r"(?![A-Za-z0-9]|\.\d|\s*[-\u2013\u2014])"
)
SOURCE_LOCATOR_RE = re.compile(
    r"(?i)(?:abstract|section|sec\.?|§|page|p\.?|figure|fig\.?|table|"
    r"equation|eq\.?|appendix|chapter|supplement)\s*[A-Za-z0-9.:-]*"
)
ADJUDICATION_INSTRUCTION_RE = re.compile(
    r"(?i)(?:official\s+grade|defen[cs]e\s+(?:approved|rejected)|"
    r"defen[cs]e\s+(?:ought(?:\s+to)?|should|must|shall|needs?\s+to)\s+"
    r"(?:not\s+)?(?:be\s+)?(?:approved|rejected|proceed|pass)|"
    r"chair\s+(?:ought\s+to|should|must|shall|needs?\s+to|is\s+to)|"
    r"(?:deserves?|warrants?|merits?)\s+(?:an?\s+)?grade\s*[ABCD]\b|"
    r"(?:create|add|invent)(?:s|ed|ing)?\s+"
    r"(?:a\s+)?(?:new\s+)?(?:thesis\s+)?finding|"
    r"(?:assign|recommend)(?:s|ed|ing)?\s+(?:an?\s+)?(?:grade|defen[cs]e\s+decision)|"
    r"同意\s*答辩|不同意\s*答辩|答辩.{0,8}(?:不通过|通过)|"
    r"主席.{0,8}(?:拒绝|接受)|建议\s*[ABCD]\b)"
)
DETAILED_CITATION_RESPONSIBILITY_RE = re.compile(
    r"(?i)(?:公式|方程|等式|定义|定理|引理|算法(?:步骤)?|"
    r"指标(?:定义)?|度量(?:定义)?|表\s*\d+(?:\.\d+)*\s*(?:中|的)?\s*(?:数值|值)|"
    r"数值|参数值|超参数|"
    r"\b(?:formula|equation|definition|theorem|lemma|algorithm(?:ic)?\s+step|"
    r"metric\s+definition|table\s+\d+(?:\.\d+)*\s+value|numeric(?:al)?\s+value|"
    r"coefficient|hyperparameter)\b|[=∑Σ∈])"
)
RENDERED_CUE_RE = re.compile(r"(?i)(?:rendered|pdf[- ]visible|论文呈现|渲染(?:字段|值)?)\s*(?:field|cue|value|字段|线索|值)?\s*:")
AUTHORITY_CUE_RE = re.compile(r"(?i)(?:authority|authoritative|canonical|官方|权威)\s*(?:field|cue|value|record|字段|线索|值|记录)?\s*:")
AUDITED_VERDICT_CUE_RE = re.compile(r"(?i)(?:audited\s+verdict|审计裁决)\s*:")
AUDITED_SUPPORT_CUE_RE = re.compile(
    r"(?i)(?:audited\s+support(?:\s+(?:state|verdict))?|审计支持(?:状态|裁决)?)\s*:"
)
AUDITED_METADATA_STATUS_CUE_RE = re.compile(
    r"(?i)(?:audited\s+metadata\s+status|审计元数据状态)\s*:"
)
AUTHORITY_ACCESS_LIMITATION_CUE_RE = re.compile(
    r"(?i)(?:authority\s+access\s+limitation|权威来源访问限制)\s*:"
)
AUTHORITATIVE_DISPOSITION_CUE_RE = re.compile(
    r"(?i)(?:authoritative\s+04\s+disposition|权威\s*04\s*处置依据)\s*:"
)
PDF_VISIBLE_LOCATION_CUE_RE = re.compile(
    r"(?i)(?:pdf[- ]visible\s+location|PDF可见位置)\s*:"
)
DISPLAYED_MARKER_CUE_RE = re.compile(
    r"(?i)(?:displayed\s+marker|呈现引文标记)\s*:"
)
RENDERED_REFERENCE_GAP_CUE_RE = re.compile(
    r"(?i)(?:rendered\s+reference\s+gap|渲染参考文献缺口)\s*:"
)
FINDING_SEMANTIC_BASIS_LABELS = (
    "premise_class",
    "target_premise",
    "supporting_pdf_evidence",
    "whole_pdf_resolution",
    "residual_gap",
    "action_delta",
)
VERDICT_SEMANTIC_BASIS_LABELS = (
    "gate_disposition_profile",
    "actionable_finding_profile",
    "synthesis_cue",
    "target_verdict",
    "coherence_result",
)
ALLOWED_FINDING_PREMISE_CLASSES = {
    "explicit-positive",
    "bounded-inference",
    "absence-after-search",
}
SYNTHESIS_PROJECTION_LABELS = (
    "Central thesis problem and overall answer",
    "Degree-level contribution judgment",
    "Strongest claim--evidence chain",
    "Weakest claim--evidence chain",
    "Cross-chapter coherence",
    "Overall integrity and submission fitness",
    "Most consequential conclusion outside the persona emphasis, or evidence that no material concern was found there",
)
FORBIDDEN_INPUT_TOKEN_RE = re.compile(
    r"(?i)(?:^|[/\\])(?:\.git|src|source|latex|old|previous|prior|chat|"
    r"conversation|thread|review-v\d+)(?:[/\\]|$)|\.bib$|\.tex$"
)
LOCAL_FILE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\.\.[/\\])*(?:[A-Za-z0-9_.-]+[/\\])*"
    r"[A-Za-z0-9_.-]+\.(?:md|csv|json|pdf|tex|bib|png|toml|log|py|"
    r"ckpt|pt|pth|bin|npy|npz|docx?|xlsx?|pptx?|zip|tar|gz|txt|yaml|"
    r"yml|sh|ps1|bat|cmd|exe)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
COMMON_SA_RULE_INPUTS = [
    "00-process-parameters.json",
    "SKILL.md",
    "clean-room-orchestration.md",
    "china-policy.md",
    "grading-and-verdicts.md",
    "review-rubric.md",
    "reviewer-panels.md",
    "report-template.md",
    "ledger-validation.md",
    "rendered-pagination-audit.md",
    "citation-audit.md",
    "ai-style-audit.md",
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_semantic_acceptance_output.py",
]
AI_SA_RULE_INPUTS = [
    "00-process-parameters.json",
    "SKILL.md",
    "clean-room-orchestration.md",
    "report-template.md",
    "ledger-validation.md",
    "ai-style-audit.md",
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_semantic_acceptance_output.py",
]
COMMON_SA_PACKET_INPUTS = [
    "00-manifest.md",
    "01-policy-basis.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
]


def path_has_unsafe_component(root: Path, path: Path, shared: Any) -> bool:
    """Reject a symlink/reparse point in any root-relative path component."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    if shared.is_link_or_reparse(current):
        return True
    for part in relative.parts:
        current = current / part
        if shared.is_link_or_reparse(current):
            return True
    return False


def preflight_regular_files(
    root: Path,
    paths: Iterable[Path],
    shared: Any,
    errors: list[str],
    *,
    label: str,
) -> None:
    """No-follow preflight before any resident input is opened or hashed."""

    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = str(path)
        if path_has_unsafe_component(root, path, shared) or not path.is_file():
            errors.append(f"missing or unsafe {label}: {relative}")


def preflight_tree_no_reparse(
    root: Path, shared: Any, errors: list[str]
) -> None:
    """Metadata-only recursive topology check; never follows a reparse directory."""

    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            errors.append(f"cannot enumerate semantic-acceptance topology: {exc}")
            continue
        for entry in entries:
            if shared.is_link_or_reparse(entry):
                try:
                    relative = entry.relative_to(root).as_posix()
                except ValueError:
                    relative = str(entry)
                errors.append(
                    f"semantic-acceptance topology contains reparse/symlink entry {relative}"
                )
                continue
            if entry.is_dir():
                stack.append(entry)
            elif not entry.is_file():
                try:
                    relative = entry.relative_to(root).as_posix()
                except ValueError:
                    relative = str(entry)
                errors.append(
                    f"semantic-acceptance topology contains non-regular entry {relative}"
                )


def process_governing_files(process: dict[str, Any]) -> list[str]:
    return [
        str(item.get("neutral_file", ""))
        for item in process.get("governing_local_files", [])
        if isinstance(item, dict) and str(item.get("neutral_file", ""))
    ]


def load_shared_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "thesis_review_shared_for_semantic_acceptance", SHARED_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load shared validator: {SHARED_VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"cannot read {path.name}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path.name}: JSON root must be an object")
        return None
    return value


def read_csv_rows(path: Path, errors: list[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
                errors.append(
                    f"{path.name}: columns must exactly equal {list(CSV_COLUMNS)}"
                )
                return []
            rows: list[dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                extras = row.get(None)
                if extras is not None:
                    errors.append(
                        f"{path.name}:{line}: row contains a cell beyond the exact CSV schema"
                    )
                rows.append(
                    {key: row.get(key) or "" for key in CSV_COLUMNS}
                )
            return rows
    except OSError as exc:
        errors.append(f"cannot read {path.name}: {exc}")
        return []


def read_generic_csv(path: Path, errors: list[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            if (
                not fieldnames
                or any(not str(name or "").strip() for name in fieldnames)
                or len(fieldnames) != len(set(fieldnames))
            ):
                errors.append(
                    f"{path.as_posix()}: generic CSV headers must be nonempty and duplicate-free"
                )
            rows: list[dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                if row.get(None) is not None:
                    errors.append(
                        f"{path.as_posix()}:{line}: row contains a cell beyond its header schema"
                    )
                rows.append(
                    {
                        str(key): str(value or "")
                        for key, value in row.items()
                        if key is not None
                    }
                )
            return rows
    except OSError as exc:
        errors.append(f"cannot read {path.as_posix()}: {exc}")
        return []


def labeled_values(text: str, label: str) -> list[str]:
    pattern = re.compile(
        rf"(?im)^[ ]{{0,3}}-[ \t]+{re.escape(label)}[ \t]*:[ \t]*(.*)$"
    )
    return [match.group(1).strip() for match in pattern.finditer(text)]


def one_labeled_value(
    text: str, label: str, filename: str, errors: list[str]
) -> str:
    values = labeled_values(text, label)
    if len(values) != 1:
        errors.append(
            f"{filename}: field {label!r} must occur exactly once; got {len(values)}"
        )
        return ""
    return values[0]


def exact_h1_h2(text: str, target: str, filename: str, errors: list[str]) -> None:
    headings = [
        (len(match.group(1)), match.group(2).strip())
        for match in re.finditer(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*$", text)
    ]
    expected = [
        (1, f"Semantic acceptance — {target}"),
        (2, "Identity and access"),
        (2, "Target hash binding and coverage"),
        (2, "Acceptance result"),
    ]
    if headings != expected:
        errors.append(f"{filename}: H1/H2 sequence must exactly equal {expected}")


def exact_section_bullets(
    text: str,
    title: str,
    expected_labels: list[str],
    filename: str,
    errors: list[str],
) -> None:
    """Reject extra labels and prose in each closed semantic-acceptance section."""

    match = re.search(
        rf"(?ms)^##[ \t]+{re.escape(title)}[ \t]*\r?\n(.*?)(?=^##[ \t]+|\Z)",
        text,
    )
    if match is None:
        errors.append(f"{filename}: missing exact section {title!r}")
        return
    observed: list[str] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bullet = re.fullmatch(r"-[ \t]+([^:\r\n]+):[ \t]+(.+)", line)
        if bullet is None:
            errors.append(
                f"{filename}: section {title!r} contains stray prose/noncanonical line {line!r}"
            )
            continue
        observed.append(bullet.group(1).strip())
    if observed != expected_labels:
        errors.append(
            f"{filename}: section {title!r} field order/set must exactly equal "
            f"{expected_labels}; observed={observed}"
        )


def validate_closed_markdown_schema(
    text: str, target: str, filename: str, errors: list[str]
) -> None:
    exact_h1_h2(text, target, filename, errors)
    preamble = re.match(
        rf"\A#[ \t]+Semantic acceptance — {re.escape(target)}[ \t]*\r?\n"
        r"(?P<gap>.*?)(?=^##[ \t]+)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if preamble is None or preamble.group("gap").strip():
        errors.append(
            f"{filename}: H1-to-first-H2 gap must contain whitespace only"
        )
    exact_section_bullets(
        text,
        "Identity and access",
        [
            "Actor ID",
            "Target actor ID",
            "Review round ID",
            "Review retry ID",
            "Operational prompt SHA-256",
            "Frozen PDF SHA-256 at start and end",
            "Fresh-context declaration",
            "Input-receipt/access declaration",
            "Semantic-acceptance boundary",
        ],
        filename,
        errors,
    )
    exact_section_bullets(
        text,
        "Target hash binding and coverage",
        ["Target artifact hashes", "Coverage row count"],
        filename,
        errors,
    )
    exact_section_bullets(
        text,
        "Acceptance result",
        ["Overall semantic acceptance", "Acceptance failure count", "Limitations"],
        filename,
        errors,
    )


def validate_evidence_input_names(
    text: str,
    expected_opened: list[str],
    target: str,
    location: str,
    errors: list[str],
) -> None:
    """Evidence may name only local files that appear in the target-only receipt."""

    scrubbed = URL_RE.sub(" ", text)
    allowed = {item.replace("\\", "/") for item in expected_opened}
    allowed_basenames = {Path(item).name for item in expected_opened}
    for match in LOCAL_FILE_TOKEN_RE.finditer(scrubbed):
        raw = match.group(0)
        normalized = raw.replace("\\", "/")
        basename = Path(normalized).name
        if (
            normalized.startswith("../")
            or Path(raw).is_absolute()
            or FORBIDDEN_INPUT_TOKEN_RE.search(normalized)
        ):
            errors.append(f"{location}: prohibited evidence input/path {raw!r}")
            continue
        peer_match = re.fullmatch(
            r"(?:SA-)?(R[1-5]|AI)(?:-comprehensive-review)?\.(?:md|csv)",
            basename,
            re.IGNORECASE,
        )
        if peer_match and peer_match.group(1).upper() != target:
            errors.append(f"{location}: peer actor evidence input is prohibited: {raw}")
            continue
        has_separator = "/" in normalized
        allowed_by_receipt = (
            normalized in allowed
            if has_separator
            else basename in allowed_basenames
        )
        if not allowed_by_receipt:
            errors.append(
                f"{location}: evidence names local input absent from the canonical receipt: {raw}"
            )


def actor_report_name(target: str) -> str:
    return "05-ai-style-assessment.md" if target == "AI" else f"{target}-comprehensive-review.md"


def reviewer_count(process: dict[str, Any]) -> int:
    return 5 if process.get("degree_level") == "doctorate" else 3


def required_targets(process: dict[str, Any]) -> list[str]:
    count = reviewer_count(process)
    return [*(f"R{index}" for index in range(1, count + 1)), "AI"]


def validate_semantic_process_shape(
    process: dict[str, Any], errors: list[str]
) -> bool:
    """Validate SA-specific process fields before degree-dependent routing."""

    start = len(errors)
    degree = process.get("degree_level")
    if degree not in {"doctorate", "masters"}:
        errors.append("degree_level must be doctorate or masters for semantic acceptance")
        return False
    page_count = process.get("physical_page_count")
    if (
        not isinstance(page_count, int)
        or isinstance(page_count, bool)
        or page_count < 1
    ):
        errors.append("physical_page_count must be a positive integer for semantic acceptance")
    count = 5 if degree == "doctorate" else 3
    expected_actors = {
        "P",
        "AI",
        "SA-AI",
        "C",
        "S",
        *(f"R{index}" for index in range(1, count + 1)),
        *(f"SA-R{index}" for index in range(1, count + 1)),
    }
    prompt_map = process.get("actor_prompt_sha256")
    if not isinstance(prompt_map, dict):
        errors.append("actor_prompt_sha256 must be an object for semantic acceptance")
    else:
        observed = set(prompt_map)
        if "V" in observed:
            expected_actors.add("V")
        if observed != expected_actors:
            errors.append(
                "semantic-acceptance actor_prompt_sha256 actor set mismatch; "
                f"missing={sorted(expected_actors-observed)}, "
                f"extra={sorted(observed-expected_actors)}"
            )
        values: list[str] = []
        for actor, value in prompt_map.items():
            if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
                errors.append(
                    f"actor_prompt_sha256[{actor!r}] must be exactly 64 hexadecimal characters"
                )
            else:
                values.append(value.upper())
        if len(values) != len(set(values)):
            errors.append("actor_prompt_sha256 values must be unique across all actors")
    return len(errors) == start


def target_is_r4(process: dict[str, Any], target: str) -> bool:
    return process.get("degree_level") == "doctorate" and target == "R4"


def target_is_page_bib_owner(process: dict[str, Any], target: str) -> bool:
    return (
        process.get("degree_level") == "doctorate" and target == "R5"
    ) or (
        process.get("degree_level") == "masters" and target == "R3"
    )


def target_is_citation_owner(process: dict[str, Any], target: str) -> bool:
    return target_is_r4(process, target) or (
        process.get("degree_level") == "masters" and target == "R3"
    )


def page_ids(root: Path, errors: list[str]) -> list[str]:
    rows = read_generic_csv(root / "00-page-inventory.csv", errors)
    values = [str(row.get("PageID", "")).strip() for row in rows]
    if not values or any(not re.fullmatch(r"P\d{4,}", value) for value in values):
        errors.append("00-page-inventory.csv: invalid or empty PageID sequence")
    if len(values) != len(set(values)):
        errors.append("00-page-inventory.csv: duplicate PageID values")
    return values


def citation_pair_ids(root: Path, errors: list[str]) -> list[str]:
    rows = read_generic_csv(root / "00-citation-inventory.csv", errors)
    values = [str(row.get("PairID", "")).strip() for row in rows]
    if not values or any(
        re.fullmatch(r"C\d{4,}-S\d{2,4}", value) is None for value in values
    ):
        errors.append("00-citation-inventory.csv: invalid or empty PairID sequence")
    if len(values) != len(set(values)):
        errors.append("00-citation-inventory.csv: duplicate PairID values")
    return values


def bibliography_reference_ids(root: Path, errors: list[str]) -> list[str]:
    rows = read_generic_csv(root / "00-bibliography-inventory.csv", errors)
    values = [str(row.get("ReferenceID", "")).strip() for row in rows]
    if not values or any(re.fullmatch(r"REF\d{4,}", value) is None for value in values):
        errors.append(
            "00-bibliography-inventory.csv: invalid or empty ReferenceID sequence"
        )
    if len(values) != len(set(values)):
        errors.append("00-bibliography-inventory.csv: duplicate ReferenceID values")
    return values


def cached_pdf_page_texts(
    pdf_path: Path,
    errors: list[str],
    *,
    derived_cache: dict[str, Any] | None = None,
    purpose: str,
) -> tuple[str, ...]:
    """Extract one frozen PDF once per byte identity within a validation run."""

    try:
        pdf_digest = sha256(pdf_path)
    except OSError as exc:
        errors.append(f"cannot hash frozen PDF for {purpose}: {exc}")
        return ()
    cache_key = f"pdf-page-text:{pdf_path.absolute()}:{pdf_digest}"
    if derived_cache is not None and cache_key in derived_cache:
        return tuple(derived_cache[cache_key])
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path), strict=False)
        page_texts = tuple(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        errors.append(f"cannot extract frozen PDF text for {purpose}: {exc}")
        return ()
    if derived_cache is not None:
        derived_cache[cache_key] = page_texts
    return page_texts


def cached_shared_page_detector(
    pdf_path: Path,
    detector_name: str,
    shared: Any,
    errors: list[str],
    *,
    derived_cache: dict[str, Any] | None = None,
) -> set[int]:
    """Cache shared rendered-page detectors without weakening byte closure."""

    try:
        pdf_digest = sha256(pdf_path)
    except OSError as exc:
        errors.append(f"cannot hash frozen PDF for {detector_name}: {exc}")
        return set()
    cache_key = f"shared-page-detector:{detector_name}:{pdf_path.absolute()}:{pdf_digest}"
    if derived_cache is not None and cache_key in derived_cache:
        return set(derived_cache[cache_key])
    try:
        detected = set(getattr(shared, detector_name)(pdf_path))
    except Exception as exc:
        errors.append(f"cannot derive {detector_name} pages: {exc}")
        return set()
    if derived_cache is not None:
        derived_cache[cache_key] = frozenset(detected)
    return detected


def authored_prose_page_ids(
    root: Path,
    process: dict[str, Any],
    shared: Any,
    errors: list[str],
    *,
    derived_cache: dict[str, Any] | None = None,
) -> list[str]:
    """Project only Stage-P's canonical authored-prose navigation page set."""

    manifest_path = root / "00-manifest.md"
    try:
        manifest = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"cannot read 00-manifest.md for authored-prose pages: {exc}")
        return []
    objective = shared.markdown_section_body_raw(
        manifest, "Objective inventories and locations"
    ) or ""
    value = shared.labeled_value(objective, "Authored-prose navigation pages") or ""
    try:
        page_count = int(process.get("physical_page_count", 0) or 0)
    except (TypeError, ValueError):
        page_count = 0
    parsed = shared.parse_canonical_physical_page_set(value, page_count)
    if parsed is None:
        errors.append(
            "00-manifest.md: invalid Authored-prose navigation pages for semantic acceptance"
        )
        return []
    inventory_rows = read_generic_csv(root / "00-page-inventory.csv", errors)
    inventory_ids = [str(row.get("PageID", "")).strip() for row in inventory_rows]
    validated_inventory_ids = page_ids(root, errors)
    if inventory_ids != validated_inventory_ids:
        errors.append("00-page-inventory.csv: unstable PageID projection")
    inventory_by_number = {
        int(match.group(1)): page_id
        for page_id in inventory_ids
        if (match := re.fullmatch(r"P(\d+)", page_id)) is not None
    }
    missing = sorted(page for page in parsed if page not in inventory_by_number)
    if missing:
        errors.append(
            f"00-manifest.md: authored-prose pages absent from page inventory {missing}"
        )
    required_pages: set[int] = set()
    for row in inventory_rows:
        page_id = str(row.get("PageID", "")).strip()
        match = re.fullmatch(r"P(\d+)", page_id)
        if match is None:
            continue
        region_class, _ = shared._inventory_region_semantics(
            str(row.get("Region", ""))
        )
        if region_class == "chapter":
            required_pages.add(int(match.group(1)))
    frozen_pdf = root / str(process.get("frozen_pdf_file", ""))
    try:
        required_pages.update(
            detect_rendered_abstract_and_appendix_pages(
                frozen_pdf,
                shared,
                errors,
                derived_cache=derived_cache,
            )
        )
        required_pages.update(
            cached_shared_page_detector(
                frozen_pdf,
                "detect_rendered_substantive_preface_pages",
                shared,
                errors,
                derived_cache=derived_cache,
            )
        )
        required_pages.update(
            cached_shared_page_detector(
                frozen_pdf,
                "detect_rendered_substantive_authored_back_pages",
                shared,
                errors,
                derived_cache=derived_cache,
            )
        )
    except Exception as exc:
        errors.append(
            f"cannot derive mandatory authored-prose lower-bound pages: {exc}"
        )
    omitted_required = sorted(required_pages - parsed)
    if omitted_required:
        errors.append(
            "00-manifest.md: Authored-prose navigation pages omit mandatory "
            f"rendered body/preface/back prose page(s) {omitted_required}"
        )
    return [inventory_by_number[page] for page in sorted(parsed) if page in inventory_by_number]


def _page_looks_substantive(text: str, *, minimum: int = 80) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    punctuation = len(re.findall(r"[，。！？；：,.!?;:]", normalized))
    return len(normalized) >= minimum and punctuation >= 2


def _top_rendered_lines(text: str, limit: int = 16) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ][:limit]


def detect_rendered_abstract_and_appendix_pages(
    pdf_path: Path,
    shared: Any,
    errors: list[str],
    *,
    derived_cache: dict[str, Any] | None = None,
) -> set[int]:
    """Derive real pre-body abstract pages plus substantive appendices.

    An abstract-like word embedded in a numbered chapter is not an independent
    Chinese/English abstract.  Each language needs its own pre-body heading
    page and a sustained prose slice before the next structural boundary.
    """

    page_texts = cached_pdf_page_texts(
        pdf_path,
        errors,
        derived_cache=derived_cache,
        purpose="rendered abstract/appendix scope",
    )
    if not page_texts:
        return set()

    chinese_heading = re.compile(r"(?i)^(?:中\s*文\s*)?摘\s*要$|^chinese\s+abstract$")
    english_heading = re.compile(r"(?i)^abstract$")
    navigation_heading = re.compile(
        r"(?i)^(?:目\s*录|contents|table\s+of\s+contents|图\s*目\s*录|"
        r"表\s*目\s*录|list\s+of\s+(?:figures|tables)|参考\s*文献|"
        r"references|bibliography)$"
    )
    all_lines_by_page = {
        physical_page: _top_rendered_lines(text, limit=10000)
        for physical_page, text in enumerate(page_texts, start=1)
    }
    furniture_counts: Counter[str] = Counter()
    for lines in all_lines_by_page.values():
        for candidate in {*lines[:2], *lines[-2:]}:
            if candidate and re.fullmatch(
                r"(?:\d+|[ivxlcdm]+)", candidate, re.I
            ) is None:
                furniture_counts[
                    shared.canonical_boundary_furniture_signature(candidate)
                ] += 1
    repeated_furniture = {
        candidate
        for candidate, count in furniture_counts.items()
        if len(candidate) <= 200
        and (
            count >= 3
            or (
                count >= 2
                and re.search(
                    r"(?i)thesis|dissertation|university|chapter|学位论文|大学",
                    candidate,
                )
                is not None
            )
        )
    }
    structural_lines_by_page: dict[int, list[str]] = {}
    for physical_page, lines in all_lines_by_page.items():
        structural_lines_by_page[physical_page] = [
            line
            for line in lines
            if shared.canonical_boundary_furniture_signature(line)
            not in repeated_furniture
            and re.fullmatch(r"(?:\d+|[ivxlcdm]+)", line, re.I) is None
        ]
    chinese_candidates: list[int] = []
    english_candidates: list[int] = []
    chapter_starts: list[int] = []
    appendix_starts: list[int] = []
    terminal_starts: list[int] = []
    for physical_page, text in enumerate(page_texts, start=1):
        lines = structural_lines_by_page[physical_page]
        first_structural = lines[0] if lines else ""
        if chinese_heading.fullmatch(first_structural):
            chinese_candidates.append(physical_page)
        if english_heading.fullmatch(first_structural):
            english_candidates.append(physical_page)
        if shared.detect_rendered_chapter_start(text) is not None:
            chapter_starts.append(physical_page)
        if shared._has_rendered_structural_heading(text, "appendix"):
            appendix_starts.append(physical_page)
        if (
            shared._has_rendered_structural_heading(text, "back")
            or navigation_heading.fullmatch(first_structural)
        ):
            terminal_starts.append(physical_page)

    first_body_page = min(chapter_starts) if chapter_starts else len(page_texts) + 1
    chinese_starts = sorted(
        page
        for page in set(chinese_candidates)
        if page < first_body_page
        and shared.detect_rendered_chapter_start(page_texts[page - 1]) is None
    )
    english_starts = sorted(
        page
        for page in set(english_candidates)
        if page < first_body_page
        and shared.detect_rendered_chapter_start(page_texts[page - 1]) is None
    )
    if len(chinese_starts) != 1:
        errors.append(
            "frozen PDF must contain exactly one independently detectable "
            f"pre-body Chinese abstract heading page; observed={chinese_starts}"
        )
    if len(english_starts) != 1:
        errors.append(
            "frozen PDF must contain exactly one independently detectable "
            f"pre-body English abstract heading page; observed={english_starts}"
        )
    if (
        len(chinese_starts) == 1
        and len(english_starts) == 1
        and chinese_starts[0] == english_starts[0]
    ):
        errors.append(
            "frozen PDF Chinese and English abstracts must begin on distinct "
            "independent physical pages"
        )

    found: set[int] = set()
    abstract_starts = sorted(set(chinese_starts + english_starts))
    for index, start in enumerate(abstract_starts):
        later_boundaries = [
            value
            for value in [
                *abstract_starts[index + 1 :],
                *chapter_starts,
                *appendix_starts,
                *terminal_starts,
            ]
            if value > start
        ]
        end = min(later_boundaries) - 1 if later_boundaries else start
        prose_lines = [
            *structural_lines_by_page.get(start, [])[1:],
            *(
                line
                for physical_page in range(start + 1, end + 1)
                for line in structural_lines_by_page.get(physical_page, [])
            ),
        ]
        prose_slice = "\n".join(prose_lines)
        if not _page_looks_substantive(prose_slice):
            errors.append(
                f"frozen PDF abstract beginning at physical p.{start} lacks "
                "a sustained independent prose slice"
            )
            continue
        found.add(start)
        for physical_page in range(start + 1, end + 1):
            if _page_looks_substantive(
                "\n".join(structural_lines_by_page.get(physical_page, []))
            ):
                found.add(physical_page)

    # An appendix page is mandatory only when it contains sustained authored
    # prose.  CV/publication metadata pages remain outside this lower bound.
    for index, start in enumerate(appendix_starts):
        later_boundaries = [
            value
            for value in [*appendix_starts[index + 1 :], *terminal_starts]
            if value > start
        ]
        end = min(later_boundaries) - 1 if later_boundaries else len(page_texts)
        for physical_page in range(start, end + 1):
            if _page_looks_substantive(page_texts[physical_page - 1]):
                found.add(physical_page)
    return found


def rendered_chapter_intervals(
    root: Path,
    process: dict[str, Any],
    shared: Any,
    errors: list[str],
    *,
    derived_cache: dict[str, Any] | None = None,
) -> list[tuple[str, int, int]]:
    """Derive exact body-chapter page intervals from the frozen PDF and inventory."""

    frozen_name = str(process.get("frozen_pdf_file", ""))
    page_texts = cached_pdf_page_texts(
        root / frozen_name,
        errors,
        derived_cache=derived_cache,
        purpose="rendered chapter coverage",
    )
    if not page_texts:
        return []
    inventory_rows = read_generic_csv(root / "00-page-inventory.csv", errors)
    inventory_region_by_page: dict[int, str] = {}
    terminal_candidates: list[int] = []
    for row in inventory_rows:
        page_match = re.fullmatch(r"P(\d+)", str(row.get("PageID", "")).strip())
        if page_match is None:
            continue
        physical_page = int(page_match.group(1))
        region_class, _ = shared._inventory_region_semantics(str(row.get("Region", "")))
        inventory_region_by_page[physical_page] = region_class
        if region_class in {"appendix", "references", "back"}:
            terminal_candidates.append(physical_page)
    first_terminal = min(terminal_candidates) if terminal_candidates else None

    starts: list[tuple[str, int]] = []
    seen: set[str] = set()
    previous_number = 0
    for physical_page, text in enumerate(page_texts, start=1):
        number = shared.detect_rendered_chapter_start(text)
        if number is None:
            continue
        region_class = inventory_region_by_page.get(physical_page, "unknown")
        if region_class in {"front", "appendix", "references", "back", "neutral"}:
            continue
        if first_terminal is not None and physical_page >= first_terminal:
            continue
        chapter = str(number)
        if chapter in seen:
            errors.append(
                f"frozen PDF renders duplicate numbered chapter start {chapter} "
                f"(latest physical p.{physical_page})"
            )
            continue
        if number <= previous_number:
            errors.append(
                f"frozen PDF chapter sequence is not strictly increasing at "
                f"Chapter-{chapter}, physical p.{physical_page}"
            )
        seen.add(chapter)
        previous_number = number
        starts.append((f"Chapter-{chapter}", physical_page))
    if not starts:
        errors.append("frozen PDF contains no mechanically detectable numbered body chapter")
        return []

    page_count = len(page_texts)
    intervals: list[tuple[str, int, int]] = []
    for index, (chapter_id, start) in enumerate(starts):
        boundaries = [
            value
            for value in [
                *(item[1] for item in starts[index + 1 :]),
                *terminal_candidates,
            ]
            if value > start
        ]
        end = min(boundaries) - 1 if boundaries else page_count
        if end < start:
            errors.append(f"frozen PDF yields an empty interval for {chapter_id}")
            end = start
        intervals.append((chapter_id, start, end))
    return intervals


def rendered_chapter_units(
    root: Path, process: dict[str, Any], shared: Any, errors: list[str]
) -> list[tuple[str, str]]:
    """Compatibility projection used by tests and actor prompts."""

    return [
        (chapter_id, f"physical p.{start}-{end}" if start != end else f"physical p.{start}")
        for chapter_id, start, end in rendered_chapter_intervals(
            root, process, shared, errors
        )
    ]


def target_artifacts(
    root: Path, process: dict[str, Any], target: str, errors: list[str]
) -> list[str]:
    result = [actor_report_name(target)]
    if target_is_page_bib_owner(process, target):
        result.extend(
            [
                "02-page-layout-ledger.md",
                "02-page-layout-ledger.csv",
                "03-bibliography-audit-ledger.md",
                "03-bibliography-audit-ledger.csv",
            ]
        )
        result.extend(f"page-renders/{item}.png" for item in page_ids(root, errors))
    if target_is_citation_owner(process, target):
        result.extend(
            [
                "04-citation-claim-audit-ledger.md",
                "04-citation-claim-audit-ledger.csv",
            ]
        )
    return result


def validate_target_ledger_closure(
    root: Path,
    process: dict[str, Any],
    target: str,
    shared: Any,
    errors: list[str],
) -> None:
    """Bind owner-ledger row universes to the neutral Stage-P masters."""

    if target_is_page_bib_owner(process, target):
        expected_pages = page_ids(root, errors)
        page_rows = read_generic_csv(root / "02-page-layout-ledger.csv", errors)
        observed_pages = [str(row.get("PageID", "")).strip() for row in page_rows]
        if observed_pages != expected_pages:
            errors.append(
                "02-page-layout-ledger.csv: PageID row universe/order does not "
                "equal 00-page-inventory.csv for semantic acceptance"
            )

        expected_bibliography_keys = [
            f"{reference_id}/{field}"
            for reference_id in bibliography_reference_ids(root, errors)
            for field in shared.BIB_FIELD_ORDER
        ]
        bibliography_rows = read_generic_csv(
            root / "03-bibliography-audit-ledger.csv", errors
        )
        observed_bibliography_keys = [
            f"{str(row.get('ReferenceID', '')).strip()}/"
            f"{str(row.get('Field', '')).strip()}"
            for row in bibliography_rows
        ]
        if observed_bibliography_keys != expected_bibliography_keys:
            errors.append(
                "03-bibliography-audit-ledger.csv: (ReferenceID,Field) row "
                "universe/order does not equal the Stage-P bibliography "
                "cross-product for semantic acceptance"
            )

    if target_is_citation_owner(process, target):
        expected_pairs = citation_pair_ids(root, errors)
        citation_rows = read_generic_csv(
            root / "04-citation-claim-audit-ledger.csv", errors
        )
        observed_pairs = [str(row.get("PairID", "")).strip() for row in citation_rows]
        if observed_pairs != expected_pairs:
            errors.append(
                "04-citation-claim-audit-ledger.csv: PairID row universe/order "
                "does not equal 00-citation-inventory.csv for semantic acceptance"
            )


def canonical_sa_opened_inputs(
    root: Path, process: dict[str, Any], target: str, errors: list[str]
) -> list[str]:
    """Return the exact local files one SA actor may open, in order."""

    governing = process_governing_files(process)
    frozen = str(process.get("frozen_pdf_file", ""))
    if target == "AI":
        return [
            *AI_SA_RULE_INPUTS,
            frozen,
            "00-manifest.md",
            "00-page-inventory.csv",
            actor_report_name(target),
        ]
    # Every ordinary reviewer is holistic.  Its independent acceptor therefore
    # receives the complete common rule/policy basis and all neutral Stage-P
    # navigation inventories, not merely the target persona's owner ledger.
    # The target actor's own outputs remain the only downstream review outputs
    # exposed to that acceptor.
    return [
        *COMMON_SA_RULE_INPUTS,
        *governing,
        frozen,
        *COMMON_SA_PACKET_INPUTS,
        *target_artifacts(root, process, target, errors),
    ]


def authoritative_report_units(
    root: Path,
    process: dict[str, Any],
    target: str,
    shared: Any,
    errors: list[str],
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], int]]:
    """Parse only canonical report sections and retain each target item page."""

    report_path = root / actor_report_name(target)
    try:
        report_text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"cannot read target report {report_path.name}: {exc}")
        return [], {}
    try:
        page_count = int(process.get("physical_page_count", 0) or 0)
    except (TypeError, ValueError):
        page_count = 0
    units: list[tuple[str, str]] = []
    anchors: dict[tuple[str, str], int] = {}
    if target == "AI":
        findings = shared.parse_ai_findings(
            report_text,
            report_path.name,
            page_count,
            errors,
        )
        for finding_id, fields in findings.items():
            key = ("ai-finding", finding_id)
            units.append(key)
            page = shared.parse_physical_page_locator(
                str(fields.get("Location", ""))
            )
            if page is not None:
                anchors[key] = page
        return units, anchors

    reviewer_index = int(target[1:])
    findings = shared.parse_reviewer_findings(
        report_text,
        reviewer_index,
        report_path.name,
        page_count,
        errors,
    )
    questions = shared.parse_reviewer_questions(
        report_text,
        reviewer_index,
        report_path.name,
        page_count,
        errors,
    )
    for finding_id, fields in findings.items():
        key = ("finding", finding_id)
        units.append(key)
        page = shared.parse_canonical_physical_page_locator(
            str(fields.get("Location", ""))
        )
        if page is not None:
            anchors[key] = page
    for question_id, row in questions.items():
        key = ("question", question_id)
        units.append(key)
        page = shared.parse_canonical_physical_page_locator(
            row[1] if len(row) > 1 else ""
        )
        if page is not None:
            anchors[key] = page
    return units, anchors


def reviewer_semantic_target_profile(
    root: Path,
    process: dict[str, Any],
    target: str,
    shared: Any,
    errors: list[str],
) -> dict[str, Any]:
    """Project only mechanically parsable reviewer fields for PASS binding.

    This projection does not decide whether thesis prose is true.  It preserves
    the report's own parsed dispositions and hashes longer prose fields so the
    SA actor can prove exact binding without replaying a defense recommendation
    as if it were the acceptor's instruction.
    """

    if target == "AI":
        return {}
    report_path = root / actor_report_name(target)
    try:
        report_text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"cannot read target report {report_path.name}: {exc}")
        return {}
    try:
        physical_page_count = int(process.get("physical_page_count", 0) or 0)
    except (TypeError, ValueError):
        physical_page_count = 0
    reviewer_index = int(target[1:])
    findings = shared.parse_reviewer_findings(
        report_text,
        reviewer_index,
        report_path.name,
        physical_page_count,
        errors,
    )

    assessment = (
        shared.markdown_section_body_raw(report_text, "Whole-thesis assessment")
        or ""
    )
    parsed_gate_rows = shared.parse_markdown_table_by_exact_headers(
        assessment,
        shared.REVIEWER_ASSESSMENT_HEADERS,
        report_path.name,
        errors,
        case_sensitive=True,
    )
    gate_rows = parsed_gate_rows or []
    gate_profile: list[dict[str, Any]] = []
    gate_states: dict[str, tuple[str, set[str]]] = {}
    gate_labels: list[str] = []
    gate_profile_complete = parsed_gate_rows is not None and len(gate_rows) == 9
    for position, cells in enumerate(gate_rows):
        if len(cells) != len(shared.REVIEWER_ASSESSMENT_HEADERS):
            gate_profile_complete = False
            continue
        gate_match = re.fullmatch(
            r"([A-I])(?:\s*(?:—|–|-)\s*\S.*)?",
            cells[0],
        )
        if gate_match is None:
            gate_profile_complete = False
            gate = f"row-{position + 1}"
        else:
            gate = gate_match.group(1)
            gate_labels.append(gate)
        related_ids = shared.parse_related_finding_ids(cells[4])
        if related_ids is None:
            gate_profile_complete = False
            related_ids = ()
        disposition = cells[2].casefold()
        review_depth = cells[1].casefold()
        gate_profile.append(
            {
                "disposition": disposition,
                "gate": gate,
                "related_finding_ids": list(related_ids),
                "review_depth": review_depth,
            }
        )
        if gate in set("ABCDEFGHI"):
            gate_states[gate] = (disposition, set(related_ids))
    if gate_labels != list("ABCDEFGHI") or len(gate_states) != 9:
        gate_profile_complete = False

    actionable_ids = sorted(
        (
            finding_id
            for finding_id, fields in findings.items()
            if fields.get("Severity", "").casefold() in {"s0", "s1", "s2", "s3"}
        ),
        key=lambda value: int(re.search(r"(\d+)$", value).group(1)),
    )
    actionable_profile: list[dict[str, Any]] = []
    finding_gate_sets: dict[str, set[str]] = {}
    for finding_id in actionable_ids:
        fields = findings[finding_id]
        primary_gate = fields.get("Primary gate", "").upper()
        secondary_gates = shared.parse_secondary_gate_set(
            fields.get("Secondary gates", "")
        )
        mapped_gates = {primary_gate} if primary_gate in set("ABCDEFGHI") else set()
        if secondary_gates is not None:
            mapped_gates.update(secondary_gates)
        finding_gate_sets[finding_id] = mapped_gates
        actionable_profile.append(
            {
                "defense_requirement_sha256": parsed_text_sha256(
                    fields.get("Required for the current defense conclusion", "")
                ),
                "finding_id": finding_id,
                "observation_sha256": parsed_text_sha256(
                    fields.get("Observation", "")
                ),
                "primary_gate": primary_gate,
                "remedy": fields.get("Remedy", "").casefold(),
                "required_action_sha256": parsed_text_sha256(
                    fields.get("Required action", "")
                ),
                "secondary_gates": list(secondary_gates or ()),
                "severity": fields.get("Severity", "").casefold(),
            }
        )

    gate_actionable_linkage = gate_profile_complete
    actionable_set = set(actionable_ids)
    for finding_id, mapped_gates in finding_gate_sets.items():
        if not mapped_gates:
            gate_actionable_linkage = False
        for gate in mapped_gates:
            state = gate_states.get(gate)
            if state is None:
                gate_actionable_linkage = False
                continue
            disposition, related_ids = state
            if disposition != "concern" or finding_id not in related_ids:
                gate_actionable_linkage = False
    for gate, (disposition, related_ids) in gate_states.items():
        related_actionable = related_ids & actionable_set
        mapped_related = {
            finding_id
            for finding_id in related_actionable
            if gate in finding_gate_sets.get(finding_id, set())
        }
        if related_actionable != mapped_related:
            gate_actionable_linkage = False
        if disposition == "concern" and not mapped_related:
            gate_actionable_linkage = False
        if disposition != "concern" and mapped_related:
            gate_actionable_linkage = False

    synthesis_section = (
        shared.markdown_section_body_raw(report_text, "Whole-thesis synthesis")
        or ""
    )
    synthesis_values = {
        label: shared.labeled_value(synthesis_section, label) or ""
        for label in SYNTHESIS_PROJECTION_LABELS
    }
    synthesis_complete = all(synthesis_values.values())
    synthesis_profile = {
        label: parsed_text_sha256(value)
        for label, value in synthesis_values.items()
    }

    verdict = shared.reviewer_verdict_projection(report_text)
    target_verdict_profile = {
        "category": verdict.get("category", ""),
        "confidence": verdict.get("confidence", "").casefold(),
        "rationale_sha256": parsed_text_sha256(verdict.get("rationale", "")),
        "recommendation_sha256": parsed_text_sha256(
            verdict.get("recommendation", "")
        ),
        "regime": verdict.get("regime", ""),
        "regime_source_sha256": parsed_text_sha256(
            verdict.get("regime_source", "")
        ),
    }
    verdict_complete = all(
        verdict.get(key, "")
        for key in ("regime", "category", "recommendation", "confidence", "rationale")
    )
    if verdict.get("regime") == "skill-default":
        category = verdict.get("category", "").upper()
        verdict_coherent = (
            verdict_complete
            and category in shared.DEFAULT_RECOMMENDATIONS
            and verdict.get("recommendation", "")
            == shared.DEFAULT_RECOMMENDATIONS.get(category, "")
        )
    elif verdict.get("regime") == "institutional":
        verdict_coherent = verdict_complete and bool(verdict.get("regime_source", ""))
    else:
        verdict_coherent = False

    coherence_profile = {
        "gate_actionable_linkage": (
            "match" if gate_actionable_linkage else "mismatch"
        ),
        "synthesis_projection": "complete" if synthesis_complete else "incomplete",
        "target_verdict_projection": "coherent" if verdict_coherent else "incoherent",
    }
    return {
        "findings": findings,
        "gate_disposition_profile": canonical_profile_json(gate_profile),
        "actionable_finding_profile": canonical_profile_json(actionable_profile),
        "synthesis_cue": canonical_profile_json(synthesis_profile),
        "target_verdict": canonical_profile_json(target_verdict_profile),
        "coherence_result": canonical_profile_json(coherence_profile),
        "coherent": (
            gate_actionable_linkage and synthesis_complete and verdict_coherent
        ),
    }


def validate_passing_finding_semantic_basis(
    semantic_basis: str,
    finding_id: str,
    finding_fields: dict[str, str] | None,
    target_page: int | None,
    physical_page_count: int,
    location: str,
    errors: list[str],
) -> None:
    parsed = parse_closed_ordered_semantic_basis(
        semantic_basis,
        FINDING_SEMANTIC_BASIS_LABELS,
        location,
        errors,
    )
    if not parsed:
        return
    if finding_fields is None:
        errors.append(
            f"{location}: passing finding {finding_id} has no parsed target finding"
        )
        return
    for label in ("premise_class", "target_premise", "supporting_pdf_evidence"):
        if not isinstance(parsed[label], str):
            errors.append(f"{location}: finding {label} must be a string")
    premise_class = str(parsed["premise_class"]).casefold()
    if premise_class not in ALLOWED_FINDING_PREMISE_CLASSES:
        errors.append(
            f"{location}: finding premise class must be exactly one of "
            f"{sorted(ALLOWED_FINDING_PREMISE_CLASSES)}"
        )
    target_observation = finding_fields.get("Observation", "")
    if normalized_binding_text(str(parsed["target_premise"])) != normalized_binding_text(
        target_observation
    ):
        errors.append(
            f"{location}: finding target premise must exactly bind the parsed "
            f"Observation of {finding_id}"
        )
    supporting_pages = validate_semantic_basis_pages(
        str(parsed["supporting_pdf_evidence"]),
        physical_page_count,
        location,
        "supporting PDF evidence",
        errors,
        require_page=True,
    )
    if target_page is not None:
        has_exact_singleton = any(
            int(match.group("start")) == target_page
            and int(match.group("end") or match.group("start")) == target_page
            for match in PHYSICAL_PAGE_RE.finditer(
                str(parsed["supporting_pdf_evidence"])
            )
        )
        if not has_exact_singleton:
            errors.append(
                f"{location}: finding supporting PDF evidence must include the "
                f"target finding's exact singleton physical p.{target_page} page"
            )
    resolution = validate_closed_object(
        parsed["whole_pdf_resolution"],
        ("status", "pages", "search_concepts", "detail"),
        location,
        "whole_pdf_resolution",
        errors,
    )
    if resolution:
        status = resolution["status"]
        allowed_statuses = {
            "responsive-passages-reviewed",
            "no-responsive-passage-found",
            "not-applicable-positive-local-fact",
        }
        if status not in allowed_statuses:
            errors.append(f"{location}: whole_pdf_resolution status is invalid")
        pages = resolution["pages"]
        concepts = resolution["search_concepts"]
        if not isinstance(pages, list) or not all(isinstance(item, str) for item in pages):
            errors.append(f"{location}: whole_pdf_resolution pages must be a string array")
            pages = []
        if not isinstance(concepts, list) or not all(
            concrete_semantic_text(item) for item in concepts
        ):
            errors.append(f"{location}: whole_pdf_resolution search_concepts must contain concrete text")
            concepts = []
        responsive_pages = validate_semantic_basis_pages(
            " ".join(pages), physical_page_count, location,
            "whole_pdf_resolution pages", errors, require_page=False,
        )
        if status == "responsive-passages-reviewed" and (not responsive_pages or not concepts):
            errors.append(f"{location}: responsive-passages-reviewed requires pages and search_concepts")
        if status == "no-responsive-passage-found" and (pages or not concepts):
            errors.append(f"{location}: no-responsive-passage-found requires empty pages and search_concepts")
        if status == "not-applicable-positive-local-fact" and (
            premise_class != "explicit-positive" or pages or concepts
        ):
            errors.append(f"{location}: not-applicable-positive-local-fact requires an explicit-positive local fact and empty pages/search_concepts")
        expected_resolution_by_premise = {
            "absence-after-search": "no-responsive-passage-found",
        }
        expected_status = expected_resolution_by_premise.get(premise_class)
        if expected_status and status != expected_status:
            errors.append(
                f"{location}: premise_class {premise_class!r} requires "
                f"whole_pdf_resolution status {expected_status!r}"
            )
        if not concrete_semantic_text(resolution["detail"]):
            errors.append(f"{location}: whole_pdf_resolution detail must be concrete")
    gap = validate_closed_object(
        parsed["residual_gap"], ("status", "detail"), location,
        "residual_gap", errors,
    )
    if gap:
        if gap["status"] != "present":
            errors.append(f"{location}: residual_gap status must be 'present'")
        if not concrete_semantic_text(gap["detail"]):
            errors.append(f"{location}: residual_gap detail must be concrete")
    action = validate_closed_object(
        parsed["action_delta"], ("status", "detail", "independent_reason"),
        location, "action_delta", errors,
    )
    if action:
        if action["status"] not in {
            "same-as-target-required-action",
            "narrower-than-target-required-action",
            "different-from-target-required-action",
        }:
            errors.append(f"{location}: action_delta status is invalid")
        for key in ("detail", "independent_reason"):
            if not concrete_semantic_text(action[key]):
                errors.append(f"{location}: action_delta {key} must be concrete")
        if action["status"] == "same-as-target-required-action" and (
            normalized_binding_text(str(action["detail"]))
            != normalized_binding_text(finding_fields.get("Required action", ""))
        ):
            errors.append(
                f"{location}: same-as-target-required-action detail must exactly "
                f"bind the Required action of {finding_id}"
            )
        required_identity = normalized_word_identity(
            finding_fields.get("Required action", "")
        )
        detail_identity = normalized_word_identity(str(action["detail"]))
        reason_identity = normalized_word_identity(str(action["independent_reason"]))
        if action["status"] in {
            "narrower-than-target-required-action",
            "different-from-target-required-action",
        } and contains_complete_normalized_phrase(detail_identity, required_identity):
            errors.append(
                f"{location}: {action['status']} detail must not copy the Required "
                f"action of {finding_id}"
            )
        if (
            contains_complete_normalized_phrase(reason_identity, detail_identity)
            or contains_complete_normalized_phrase(reason_identity, required_identity)
        ):
            errors.append(
                f"{location}: action_delta independent_reason must not copy its "
                f"detail or the Required action of {finding_id}"
            )
    for label in ("target_premise", "supporting_pdf_evidence"):
        if not concrete_semantic_text(parsed[label]):
            errors.append(f"{location}: finding {label} must be concrete and cannot be N/A/empty")
    if semantic_value_is_na(parsed["premise_class"]):
        errors.append(f"{location}: finding premise_class cannot be N/A/empty")


def validate_passing_verdict_semantic_basis(
    semantic_basis: str,
    target_profile: dict[str, Any],
    location: str,
    errors: list[str],
) -> None:
    parsed = parse_closed_ordered_semantic_basis(
        semantic_basis,
        VERDICT_SEMANTIC_BASIS_LABELS,
        location,
        errors,
    )
    if not parsed:
        return
    expected_keys = {key: key for key in VERDICT_SEMANTIC_BASIS_LABELS}
    if not target_profile:
        errors.append(f"{location}: target reviewer report could not be projected")
        return
    for cue_label, profile_key in expected_keys.items():
        expected = str(target_profile.get(profile_key, ""))
        if parsed[cue_label] != expected:
            errors.append(
                f"{location}: verdict {cue_label} does not exactly project the "
                "parsed target reviewer report"
            )
    if not target_profile.get("coherent", False):
        errors.append(
            f"{location}: passing verdict cannot admit a mechanically incoherent "
            "gate/finding/synthesis/verdict projection"
        )


def expected_units(
    root: Path,
    process: dict[str, Any],
    target: str,
    errors: list[str],
    shared: Any | None = None,
    chapter_intervals: list[tuple[str, int, int]] | None = None,
    report_units: list[tuple[str, str]] | None = None,
    derived_cache: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    active_shared = shared or load_shared_validator()
    parsed_report_units = report_units
    if parsed_report_units is None:
        parsed_report_units, _ = authoritative_report_units(
            root,
            process,
            target,
            active_shared,
            errors,
        )
    units: list[tuple[str, str]] = []
    if target == "AI":
        units.extend(
            ("page", value)
            for value in authored_prose_page_ids(
                root,
                process,
                active_shared,
                errors,
                derived_cache=derived_cache,
            )
        )
        units.extend(parsed_report_units)
        units.append(("ai-judgment", "AI-JUDGMENT"))
        return units
    units.extend(("gate", f"Gate-{letter}") for letter in "ABCDEFGHI")
    intervals = chapter_intervals
    if intervals is None:
        intervals = rendered_chapter_intervals(
            root,
            process,
            active_shared,
            errors,
            derived_cache=derived_cache,
        )
    units.extend(("chapter", chapter_id) for chapter_id, _, _ in intervals)
    units.extend(parsed_report_units)
    units.append(("verdict", f"{target}-VERDICT"))
    if target_is_citation_owner(process, target):
        units.extend(
            ("citation-pair", pair_id)
            for pair_id in citation_pair_ids(root, errors)
        )
    if target_is_page_bib_owner(process, target):
        units.extend(("page", value) for value in page_ids(root, errors))
        units.extend(
            (
                "bibliography-field",
                f"{reference_id}/{field}",
            )
            for reference_id in bibliography_reference_ids(root, errors)
            for field in active_shared.BIB_FIELD_ORDER
        )
    return units


def required_artifact_for_unit(target: str, unit_type: str, unit_id: str) -> str:
    """Bind every semantic unit to the one authoritative frozen target artifact."""

    report = actor_report_name(target)
    if unit_type == "citation-pair":
        return "04-citation-claim-audit-ledger.csv"
    if unit_type == "bibliography-field":
        return "03-bibliography-audit-ledger.csv"
    if unit_type == "page" and target != "AI":
        return f"page-renders/{unit_id}.png"
    return report


def parse_target_hashes(
    value: str, filename: str, errors: list[str]
) -> dict[str, str]:
    if not value:
        return {}
    result: dict[str, str] = {}
    for raw in value.split(";"):
        token = raw.strip()
        if "@" not in token:
            errors.append(f"{filename}: malformed target hash token {token!r}")
            continue
        name, digest = token.rsplit("@", 1)
        name = name.strip()
        digest = digest.strip().upper()
        if not name or not HEX64_RE.fullmatch(digest):
            errors.append(f"{filename}: malformed target hash token {token!r}")
            continue
        if name in result:
            errors.append(f"{filename}: duplicate target artifact hash for {name}")
            continue
        result[name] = digest
    return result


def target_public_endpoints(
    root: Path, process: dict[str, Any], target: str, shared: Any, errors: list[str]
) -> set[str]:
    if target == "AI":
        return set()
    allowed = {
        value
        for value in process.get("governing_rule_urls", [])
        if isinstance(value, str)
    }
    if target_is_page_bib_owner(process, target):
        rows = read_generic_csv(
            root / "03-bibliography-audit-ledger.csv", errors
        )
        allowed.update(shared.bibliography_ledger_public_endpoint_sequence(rows))
    if target_is_citation_owner(process, target):
        rows = read_generic_csv(
            root / "04-citation-claim-audit-ledger.csv", errors
        )
        allowed.update(shared.citation_ledger_public_endpoint_sequence(rows))
    return allowed


def exact_singleton_physical_pages(value: str) -> set[int]:
    return {
        int(match.group("start"))
        for match in PHYSICAL_PAGE_RE.finditer(value)
        if int(match.group("end") or match.group("start"))
        == int(match.group("start"))
    }


def normalized_binding_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def normalized_word_identity(value: str) -> str:
    """Normalize wording while ignoring punctuation-only copy edits."""

    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[\W_]+", " ", normalized).strip()


def contains_complete_normalized_phrase(container: str, phrase: str) -> bool:
    """Return whether *phrase* occurs as whole normalized words in *container*."""

    if not phrase:
        return False
    return re.search(
        rf"(?:^| ){re.escape(phrase)}(?:$| )",
        container,
    ) is not None


def parse_closed_ordered_semantic_basis(
    value: str,
    labels: tuple[str, ...],
    location: str,
    errors: list[str],
) -> dict[str, Any]:
    """Parse the sole canonical, closed JSON spelling for a PASS record."""

    duplicate = False

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicate
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                duplicate = True
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=closed_object)
    except (json.JSONDecodeError, TypeError):
        errors.append(f"{location}: SemanticBasis must be one canonical JSON object")
        return {}
    if duplicate or not isinstance(parsed, dict) or list(parsed) != list(labels):
        errors.append(
            f"{location}: SemanticBasis must use exact closed key order {list(labels)}"
        )
        return {}
    if value != json.dumps(parsed, ensure_ascii=False, separators=(",", ":")):
        errors.append(f"{location}: SemanticBasis must use canonical JSON spelling")
        return {}
    return parsed


def canonical_profile_json(value: Any) -> str:
    """Return the sole byte-stable JSON spelling used by verdict projections."""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def parsed_text_sha256(value: str) -> str:
    """Bind a parsed report field without replaying adjudicative wording."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def semantic_value_is_na(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return bool(
        re.match(
            r"^(?:n\s*/?\s*a|none|null|not\s+applicable|unknown|tbd|todo|"
            r"无|暂无|没有|不适用|未知|待定|未提供|未说明|空)"
            r"(?:$|[\s:：,，;；.!！?？()（）\-])",
            normalized,
        )
    )


def concrete_semantic_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return len(normalized_word_identity(text)) >= 6 and not semantic_value_is_na(text)


def validate_closed_object(
    value: Any,
    keys: tuple[str, ...],
    location: str,
    label: str,
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(value, dict) or list(value) != list(keys):
        errors.append(f"{location}: {label} must be a closed object with exact keys {list(keys)}")
        return {}
    return value


def semantic_gap_is_empty(value: str) -> bool:
    return normalized_word_identity(value) in {
        "",
        "none",
        "no gap",
        "no residual gap",
        "n a",
        "na",
        "not applicable",
    }


def validate_semantic_basis_pages(
    value: str,
    physical_page_count: int,
    location: str,
    field_label: str,
    errors: list[str],
    *,
    require_page: bool,
) -> set[int]:
    """Validate explicit physical-page locators in one structured cue."""

    matches = list(PHYSICAL_PAGE_RE.finditer(value))
    if require_page and not matches:
        errors.append(
            f"{location}: finding {field_label} requires an explicit physical p.<n> locator"
        )
    pages: set[int] = set()
    for match in matches:
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        if start > end or start < 1 or end > physical_page_count:
            errors.append(
                f"{location}: finding {field_label} locator {match.group(0)!r} "
                f"is outside 1..{physical_page_count} or descending"
            )
            continue
        pages.update(range(start, end + 1))
    return pages


def substantive_value_is_bound(value: str, evidence: str) -> bool:
    normalized_value = normalized_binding_text(value)
    if normalized_value in {"", "none", "n/a", "na", "not applicable"}:
        return True
    return normalized_value in normalized_binding_text(evidence)


def exact_normalized_value_is_bound(value: str, evidence: str) -> bool:
    normalized_value = normalized_binding_text(value)
    normalized_evidence = normalized_binding_text(evidence)
    if not normalized_value:
        return False
    start = 0
    while True:
        index = normalized_evidence.find(normalized_value, start)
        if index < 0:
            return False
        before = normalized_evidence[index - 1] if index else ""
        end = index + len(normalized_value)
        after = normalized_evidence[end] if end < len(normalized_evidence) else ""
        if not (before and (before.isalnum() or before == "_")) and not (
            after and (after.isalnum() or after == "_")
        ):
            return True
        start = index + 1


def cue_binds_value(pattern: re.Pattern[str], value: str, evidence: str) -> bool:
    """Require an exact semicolon-delimited cue value, not a prefix."""

    normalized_value = normalized_binding_text(value)
    if not normalized_value:
        return False
    for match in pattern.finditer(evidence):
        tail = normalized_binding_text(evidence[match.end() :])
        if not tail.startswith(normalized_value):
            continue
        remainder = tail[len(normalized_value) :]
        if not remainder or remainder.startswith(";"):
            return True
    return False


def source_locator_identities(value: str, shared: Any) -> set[str]:
    return {
        shared.canonical_atomic_locator_identity(match.group(0))
        for match in shared.SOURCE_LOCATOR_RE.finditer(value)
        if match.group(0).strip()
    }


def is_abstract_only_source_locator(value: str, shared: Any) -> bool:
    """Treat Abstract plus page/line/paragraph coordinates as abstract-only."""

    identity = shared.canonical_atomic_locator_identity(value)
    if re.search(
        r"(?<![A-Za-z0-9])abstract(?![A-Za-z0-9])",
        identity,
        re.IGNORECASE,
    ) is None:
        return False
    non_abstract_structure = re.compile(
        r"(?i)(?:\b(?:section|sec\.?|table|figure|fig\.?|equation|eq\.?|"
        r"theorem|lemma|appendix|supplement|introduction|conclusion|methods?|"
        r"results?)\b|§\s*\d|第\s*\d+(?:\.\d+)*\s*节|"
        r"[表图式]\s*\(?\s*\d|附录\s*[A-Za-z0-9])"
    )
    return non_abstract_structure.search(identity) is None


def rendered_bibliography_entry_pages(
    root: Path,
    process: dict[str, Any],
    shared: Any,
    errors: list[str],
    *,
    derived_cache: dict[str, Any] | None = None,
) -> dict[str, set[int]]:
    """Bind bibliography units to the frozen rendered entry page topology."""

    inventory_path = root / "00-bibliography-inventory.csv"
    pdf_path = root / str(process.get("frozen_pdf_file", ""))
    try:
        cache_key = (
            f"rendered-bibliography:{pdf_path.absolute()}:{sha256(pdf_path)}:"
            f"{sha256(inventory_path)}"
        )
    except OSError as exc:
        errors.append(f"cannot hash rendered bibliography inputs: {exc}")
        return {}
    if derived_cache is not None and cache_key in derived_cache:
        return {
            reference_id: set(pages)
            for reference_id, pages in derived_cache[cache_key].items()
        }
    inventory_rows = read_generic_csv(inventory_path, errors)
    run = shared.extract_rendered_bibliography_run(
        pdf_path,
        inventory_rows,
        errors,
    )
    if run is None:
        return {}
    result: dict[str, set[int]] = {}
    for reference_id, fact in run.entry_facts.items():
        pages = {
            int(page)
            for page, segment in fact.raw_page_segments
            if normalized_binding_text(segment)
        }
        if not pages:
            pages = {int(page) for page, _segment in fact.raw_page_segments}
        result[str(reference_id)] = pages
    if derived_cache is not None:
        derived_cache[cache_key] = {
            reference_id: frozenset(pages)
            for reference_id, pages in result.items()
        }
    return result


def normalized_basis_signature(value: str) -> str:
    value = re.sub(
        r"(?:\"[^\"\r\n]{2,160}\"|'[^'\r\n]{2,160}'|“[^”\r\n]{2,160}”|‘[^’\r\n]{2,160}’)",
        " <quoted> ",
        value,
    )
    value = URL_RE.sub(" <url> ", value)
    value = re.sub(r"(?i)\b(?:SA\d+|C\d{4}-S\d+|REF\d{4}|P\d{4}|R\d+-[FQ]\d+)\b", " <id> ", value)
    value = HEX64_RE.sub(" <hash> ", value)
    value = re.sub(r"\d+(?:\.\d+)*", " <n> ", value)
    return re.sub(r"\s+", " ", value).strip().casefold()


TEMPLATE_CLUSTER_MIN_ROWS = 6
TEMPLATE_CLUSTER_MAX_ROWS = 12
TEMPLATE_CLUSTER_DOMINANCE_NUMERATOR = 4
TEMPLATE_CLUSTER_DOMINANCE_DENOMINATOR = 5


def template_cluster_threshold(row_count: int) -> int:
    """Return the adaptive row count that constitutes template monoculture.

    The original fixed twelve-row boundary left the smallest ordinary-reviewer
    universe (nine gates, one chapter, and one verdict) wholly unchecked.  For
    small artifacts, require a dense four-fifths cluster while retaining a
    six-row floor so a handful of legitimately similar checks is not treated as
    monoculture.  At fourteen or more rows, preserve the historical twelve-row
    absolute boundary.
    """

    dominant_rows = (
        TEMPLATE_CLUSTER_DOMINANCE_NUMERATOR * max(0, row_count)
        + TEMPLATE_CLUSTER_DOMINANCE_DENOMINATOR
        - 1
    ) // TEMPLATE_CLUSTER_DOMINANCE_DENOMINATOR
    return min(
        TEMPLATE_CLUSTER_MAX_ROWS,
        max(TEMPLATE_CLUSTER_MIN_ROWS, dominant_rows),
    )


def validate_template_diversity(rows: list[dict[str, str]], errors: list[str]) -> None:
    cluster_threshold = template_cluster_threshold(len(rows))
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        value = row.get("SemanticBasis", "").replace(
            row.get("TargetUnitID", ""), " <unit> "
        )
        signature = normalized_basis_signature(value)
        groups[signature].append(
            row.get("TargetUnitID", "")
        )
    for signature, identifiers in groups.items():
        if len(identifiers) >= cluster_threshold:
            errors.append(
                "semantic-acceptance CSV: repeated identity-stripped SemanticBasis "
                f"template covers {len(identifiers)} rows; sample="
                f"{identifiers[:8]}, signature={signature!r}"
            )

    # Exact signatures are insufficient when a generic template interpolates
    # a unique source title/name in every row.  Count long repeated language
    # shingles after normalizing IDs, endpoints, numbers, and quoted slots.
    latin_shingles: dict[tuple[str, ...], set[int]] = defaultdict(set)
    cjk_shingles: dict[str, set[int]] = defaultdict(set)
    for row_index, row in enumerate(rows):
        normalized = normalized_basis_signature(
            row.get("SemanticBasis", "").replace(
                row.get("TargetUnitID", ""), " <unit> "
            )
        )
        latin_tokens = re.findall(r"[a-z]{2,}|<[a-z]+>", normalized)
        for start in range(max(0, len(latin_tokens) - 9)):
            shingle = tuple(latin_tokens[start : start + 10])
            if len(shingle) == 10:
                latin_shingles[shingle].add(row_index)
        cjk = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
        for start in range(max(0, len(cjk) - 23)):
            shingle = cjk[start : start + 24]
            if len(shingle) == 24:
                cjk_shingles[shingle].add(row_index)

    repeated: list[tuple[int, str, str, list[str]]] = []
    for shingle, row_indexes in latin_shingles.items():
        if len(row_indexes) >= cluster_threshold:
            repeated.append(
                (
                    len(row_indexes),
                    "mixed/all",
                    " ".join(shingle),
                    [rows[index].get("TargetUnitID", "") for index in sorted(row_indexes)[:8]],
                )
            )
    for shingle, row_indexes in cjk_shingles.items():
        if len(row_indexes) >= cluster_threshold:
            repeated.append(
                (
                    len(row_indexes),
                    "mixed/all",
                    shingle,
                    [rows[index].get("TargetUnitID", "") for index in sorted(row_indexes)[:8]],
                )
            )
    if repeated:
        count, unit_type, shingle, sample = max(repeated, key=lambda item: item[0])
        errors.append(
            "semantic-acceptance CSV: repeated long SemanticBasis language "
            f"shingle covers {count} {unit_type!r} rows; sample={sample}, "
            f"shingle={shingle!r}"
        )

    # A template can evade fixed shingles by inserting one unique title/name
    # every few words.  Remove corpus-singleton interpolation tokens, then
    # require that no long residual language skeleton reaches the adaptive
    # dense-cluster boundary.
    token_sequences: list[tuple[str, ...]] = []
    document_frequency: Counter[str] = Counter()
    for row in rows:
        normalized = normalized_basis_signature(
            row.get("SemanticBasis", "").replace(
                row.get("TargetUnitID", ""), " <unit> "
            )
        )
        tokens = tuple(
            re.findall(r"[a-z]{2,}|<[a-z]+>|[\u3400-\u9fff]", normalized)
        )
        token_sequences.append(tokens)
        document_frequency.update(set(tokens))
    residual_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for row, tokens in zip(rows, token_sequences):
        residual = tuple(
            token
            for token in tokens
            if document_frequency[token] >= 2 and token not in {"<unit>"}
        )
        if len(residual) >= 12:
            residual_groups[residual].append(row.get("TargetUnitID", ""))
    for residual, identifiers in residual_groups.items():
        if len(identifiers) >= cluster_threshold:
            errors.append(
                "semantic-acceptance CSV: singleton-stripped generic language "
                f"skeleton covers {len(identifiers)} rows; sample={identifiers[:8]}, "
                f"skeleton={' '.join(residual[:24])!r}"
            )
            break

    # Alternating a small token bank every few words defeats both exact
    # skeletons and contiguous shingles while leaving the same generic
    # semantic template.  Detect a dense near-duplicate cluster by token-set
    # overlap; the high threshold preserves genuinely row-specific reasoning.
    fuzzy_features: list[set[str]] = []
    for row in rows:
        normalized = normalized_basis_signature(
            row.get("SemanticBasis", "").replace(
                row.get("TargetUnitID", ""), " <unit> "
            )
        )
        latin = set(re.findall(r"[a-z]{2,}|<[a-z]+>", normalized))
        cjk = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
        cjk_bigrams = {
            f"cjk:{cjk[index:index + 2]}"
            for index in range(max(0, len(cjk) - 1))
        }
        fuzzy_features.append(latin | cjk_bigrams)
    feature_frequency: Counter[str] = Counter()
    for features in fuzzy_features:
        feature_frequency.update(features)
    stable_features = [
        {
            feature
            for feature in features
            if feature_frequency[feature] >= 2 and feature != "<unit>"
        }
        for features in fuzzy_features
    ]
    stable_groups: dict[frozenset[str], list[int]] = defaultdict(list)
    for index, features in enumerate(stable_features):
        if len(features) >= 12:
            stable_groups[frozenset(features)].append(index)

    def report_fuzzy_cluster(seed: int, cluster: list[int]) -> None:
        sample = [
            rows[row_index].get("TargetUnitID", "")
            for row_index in cluster[:8]
        ]
        errors.append(
            "semantic-acceptance CSV: fuzzy near-duplicate SemanticBasis "
            f"template cluster covers {len(cluster)} rows; sample={sample}, "
            f"seed={rows[seed].get('TargetUnitID', '')!r}"
        )

    for indexes in stable_groups.values():
        if len(indexes) >= cluster_threshold:
            report_fuzzy_cluster(indexes[0], indexes)
            return

    # Four deterministic MinHash bands generate candidates in near-linear
    # time.  Exact Jaccard verification remains the decision boundary, while
    # candidate scans stop as soon as the adaptive number of near-duplicates
    # is proved.
    minhash_buckets: dict[tuple[int, bytes], list[int]] = defaultdict(list)
    minhash_values: dict[tuple[int, str], bytes] = {}
    for index, features in enumerate(stable_features):
        if len(features) < 12:
            continue
        for seed in range(4):
            values: list[bytes] = []
            for feature in features:
                feature_key = (seed, feature)
                value = minhash_values.get(feature_key)
                if value is None:
                    value = hashlib.sha256(
                        f"{seed}\0{feature}".encode("utf-8")
                    ).digest()[:8]
                    minhash_values[feature_key] = value
                values.append(value)
            minimum = min(values)
            minhash_buckets[(seed, minimum)].append(index)
    checked_buckets: set[tuple[int, ...]] = set()
    for candidate_indexes in minhash_buckets.values():
        candidates = tuple(dict.fromkeys(candidate_indexes))
        if len(candidates) < cluster_threshold or candidates in checked_buckets:
            continue
        checked_buckets.add(candidates)
        for seed_index in candidates[:128]:
            features = stable_features[seed_index]
            cluster: list[int] = []
            for candidate in candidates:
                other = stable_features[candidate]
                union = features | other
                intersection = features & other
                similarity = len(intersection) / len(union) if union else 0.0
                overlap = (
                    len(intersection) / min(len(features), len(other))
                    if features and other
                    else 0.0
                )
                if (
                    len(intersection) >= 12
                    and similarity >= 0.75
                    and overlap >= 0.85
                ):
                    cluster.append(candidate)
                    if len(cluster) >= cluster_threshold:
                        report_fuzzy_cluster(seed_index, cluster)
                        return


def actor_seed_input_paths(
    root: Path,
    process: dict[str, Any],
    target: str,
    acceptance_directory: Path,
) -> list[Path]:
    """Resident paths whose safety is knowable without opening an inventory."""

    packet_inputs = (
        ["00-manifest.md", "00-page-inventory.csv"]
        if target == "AI"
        else COMMON_SA_PACKET_INPUTS
    )
    governing_inputs = [] if target == "AI" else process_governing_files(process)
    paths = [
        root / "00-process-parameters.json",
        root / str(process.get("frozen_pdf_file", "")),
        *(root / name for name in governing_inputs),
        *(root / name for name in packet_inputs),
        root / actor_report_name(target),
        acceptance_directory / f"SA-{target}.md",
        acceptance_directory / f"SA-{target}.csv",
    ]
    if target_is_page_bib_owner(process, target):
        paths.extend(
            root / name
            for name in (
                "02-page-layout-ledger.md",
                "02-page-layout-ledger.csv",
                "03-bibliography-audit-ledger.md",
                "03-bibliography-audit-ledger.csv",
            )
        )
    if target_is_citation_owner(process, target):
        paths.extend(
            root / name
            for name in (
                "04-citation-claim-audit-ledger.md",
                "04-citation-claim-audit-ledger.csv",
            )
        )
    return paths


def validate_process_for_semantic_acceptance(
    root: Path,
    process: dict[str, Any],
    shared: Any,
    errors: list[str],
    *,
    target: str | None,
) -> None:
    """Apply the canonical production process and extraction-runtime contract."""

    shared.validate_manifest_extraction_runtime(root / "00-manifest.md", errors)
    canonical_errors: list[str] = []
    shared.validate_process(
        root,
        canonical_errors,
        enforce_single_reviewer_pdf=True,
        validate_governing_file_bytes=target != "AI",
        validate_frozen_pdf_bytes=True,
        stage_v_present_override=(
            isinstance(process.get("actor_prompt_sha256"), dict)
            and "V" in process.get("actor_prompt_sha256", {})
        ),
        process_override=process,
    )
    # Older installed copies of the shared validator knew only P/R/AI/C/S.
    # This validator independently enforces the strictly larger SA-inclusive
    # actor map above; discard only that obsolete set-mismatch diagnostic.  As
    # soon as the shared validator is upgraded, no diagnostic is produced.
    errors.extend(
        error
        for error in canonical_errors
        if not error.startswith("actor_prompt_sha256 actor set mismatch;")
    )


def preflight_actor_resident_inputs(
    root: Path,
    process: dict[str, Any],
    target: str,
    shared: Any,
    errors: list[str],
    *,
    acceptance_directory: Path,
    include_ephemeral_rules: bool,
) -> None:
    """Preflight all resident inputs, including dynamic page-render ancestors."""

    preflight_regular_files(
        root,
        actor_seed_input_paths(root, process, target, acceptance_directory),
        shared,
        errors,
        label="semantic-acceptance resident input",
    )
    if errors:
        return
    artifacts = target_artifacts(root, process, target, errors)
    dynamic_paths = [root / Path(relative) for relative in artifacts]
    if include_ephemeral_rules:
        dynamic_paths.extend(
            root / Path(relative)
            for relative in canonical_sa_opened_inputs(
                root, process, target, errors
            )
        )
    preflight_regular_files(
        root,
        dynamic_paths,
        shared,
        errors,
        label="semantic-acceptance input",
    )


def validate_actor(
    root: Path,
    target: str,
    shared: Any,
    *,
    acceptance_directory: Path | None = None,
    enforce_closed_view: bool = False,
    require_opened_files: bool = True,
    validated_process: dict[str, Any] | None = None,
    derived_cache: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    cache = derived_cache if derived_cache is not None else {}
    if not ACTOR_RE.fullmatch(target):
        return [f"invalid semantic-acceptance target {target!r}"], None
    if shared.is_link_or_reparse(root) or not root.is_dir():
        return ["acceptance input root is missing or unsafe"], None
    preflight_tree_no_reparse(root, shared, errors)
    if errors:
        return errors, None
    process_path = root / "00-process-parameters.json"
    if path_has_unsafe_component(root, process_path, shared) or not process_path.is_file():
        return ["missing or unsafe semantic-acceptance process envelope"], None
    process = read_json(root / "00-process-parameters.json", errors)
    if process is None:
        return errors, None
    if validated_process is not None and process != validated_process:
        errors.append(
            "00-process-parameters.json changed after the semantic-acceptance "
            "set process validation"
        )
        return errors, None
    if not validate_semantic_process_shape(process, errors):
        return errors, None
    if target not in required_targets(process):
        errors.append(
            f"target {target} is not required for degree_level={process.get('degree_level')!r}"
        )
    if enforce_closed_view:
        reserved_round_directory = root / ACCEPTANCE_DIRECTORY
        if reserved_round_directory.exists() or shared.is_link_or_reparse(
            reserved_round_directory
        ):
            errors.append(
                "scoped semantic-acceptance view must place "
                f"SA-{target}.md and SA-{target}.csv at the view root; "
                f"{ACCEPTANCE_DIRECTORY} is reserved for Stage-O promotion "
                "inside the finalized round"
            )
    report_dir = acceptance_directory or root
    acceptance_md = report_dir / f"SA-{target}.md"
    acceptance_csv = report_dir / f"SA-{target}.csv"
    preflight_actor_resident_inputs(
        root,
        process,
        target,
        shared,
        errors,
        acceptance_directory=report_dir,
        include_ephemeral_rules=require_opened_files,
    )
    if errors:
        return errors, None
    if validated_process is None:
        validate_process_for_semantic_acceptance(
            root, process, shared, errors, target=target
        )
    if errors:
        return errors, None
    expected_opened = canonical_sa_opened_inputs(root, process, target, errors)
    if errors:
        return errors, None
    try:
        md_text = acceptance_md.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"cannot read {acceptance_md.name}: {exc}")
        return errors, None
    validate_closed_markdown_schema(md_text, target, acceptance_md.name, errors)
    actor_id = one_labeled_value(md_text, "Actor ID", acceptance_md.name, errors)
    target_id = one_labeled_value(md_text, "Target actor ID", acceptance_md.name, errors)
    round_id = one_labeled_value(md_text, "Review round ID", acceptance_md.name, errors)
    retry_id = one_labeled_value(md_text, "Review retry ID", acceptance_md.name, errors)
    prompt_hash = one_labeled_value(md_text, "Operational prompt SHA-256", acceptance_md.name, errors).upper()
    pdf_hash_pair = one_labeled_value(md_text, "Frozen PDF SHA-256 at start and end", acceptance_md.name, errors)
    fresh = one_labeled_value(md_text, "Fresh-context declaration", acceptance_md.name, errors)
    receipt_value = one_labeled_value(md_text, "Input-receipt/access declaration", acceptance_md.name, errors)
    target_hash_value = one_labeled_value(md_text, "Target artifact hashes", acceptance_md.name, errors)
    coverage_count_value = one_labeled_value(md_text, "Coverage row count", acceptance_md.name, errors)
    overall = one_labeled_value(md_text, "Overall semantic acceptance", acceptance_md.name, errors)
    failure_count_value = one_labeled_value(md_text, "Acceptance failure count", acceptance_md.name, errors)
    boundary = one_labeled_value(md_text, "Semantic-acceptance boundary", acceptance_md.name, errors)
    limitations = one_labeled_value(md_text, "Limitations", acceptance_md.name, errors)
    if actor_id != f"SA-{target}":
        errors.append(f"{acceptance_md.name}: Actor ID must be SA-{target}")
    if target_id != target:
        errors.append(f"{acceptance_md.name}: Target actor ID must be {target}")
    if round_id != str(process.get("round_id", "")):
        errors.append(f"{acceptance_md.name}: Review round ID mismatch")
    if retry_id != str(process.get("retry_id", "")):
        errors.append(f"{acceptance_md.name}: Review retry ID mismatch")
    prompt_map = process.get("actor_prompt_sha256")
    expected_prompt = (
        str(prompt_map.get(f"SA-{target}", "")).upper()
        if isinstance(prompt_map, dict)
        else ""
    )
    if not HEX64_RE.fullmatch(prompt_hash) or prompt_hash != expected_prompt:
        errors.append(f"{acceptance_md.name}: operational prompt hash mismatch")
    expected_pdf_hash = str(process.get("selected_pdf_sha256", "")).upper()
    pdf_parts = [part.strip().upper() for part in pdf_hash_pair.split(";")]
    if pdf_parts != [expected_pdf_hash, expected_pdf_hash] or not HEX64_RE.fullmatch(expected_pdf_hash):
        errors.append(f"{acceptance_md.name}: frozen PDF start/end hash mismatch")
    frozen_name = str(process.get("frozen_pdf_file", ""))
    frozen_path = root / frozen_name
    if not frozen_path.is_file() or sha256(frozen_path) != expected_pdf_hash:
        errors.append(f"{acceptance_md.name}: frozen PDF bytes do not match process hash")
    if fresh != FRESH_CONTEXT_SENTENCE:
        errors.append(f"{acceptance_md.name}: noncanonical fresh-context declaration")
    receipt = shared.parse_closed_access_receipt(receipt_value, acceptance_md.name, errors)
    allowed_public = target_public_endpoints(root, process, target, shared, errors)
    receipt_public: list[str] = []
    if receipt:
        if receipt.get("received") != ["operational prompt"]:
            errors.append(f"{acceptance_md.name}: received must be [operational prompt]")
        if receipt.get("opened") != expected_opened:
            errors.append(
                f"{acceptance_md.name}: opened list must exactly equal the canonical SA-{target} allowlist"
            )
        receipt_public = receipt.get("public_endpoints", [])
        if receipt_public == ["none"]:
            receipt_public = []
        elif len(receipt_public) != len(set(receipt_public)):
            errors.append(
                f"{acceptance_md.name}: public_endpoints must be duplicate-free"
            )
        if target == "AI" and receipt_public:
            errors.append(
                f"{acceptance_md.name}: SA-AI public_endpoints must be [none]"
            )
        unknown_public = sorted(set(receipt_public) - allowed_public)
        if unknown_public:
            errors.append(
                f"{acceptance_md.name}: public endpoints outside target authority {unknown_public}"
            )
        for item in receipt.get("opened", []):
            if Path(item).is_absolute() or ".." in Path(item).parts or FORBIDDEN_INPUT_TOKEN_RE.search(item):
                errors.append(f"{acceptance_md.name}: prohibited opened input {item!r}")
            peer_match = re.fullmatch(r"(?:SA-)?(R[1-5]|AI)(?:-comprehensive-review)?\.(?:md|csv)", Path(item).name, re.I)
            if peer_match and peer_match.group(1).upper() != target:
                errors.append(f"{acceptance_md.name}: peer actor input is prohibited: {item}")
    if boundary != BOUNDARY_SENTENCE:
        errors.append(f"{acceptance_md.name}: semantic-acceptance boundary is not exact")
    if len(limitations) < 20:
        errors.append(f"{acceptance_md.name}: limitations field is shell-only")
    validate_evidence_input_names(
        limitations,
        expected_opened,
        target,
        f"{acceptance_md.name}:Limitations",
        errors,
    )
    if ADJUDICATION_INSTRUCTION_RE.search(limitations):
        errors.append(
            f"{acceptance_md.name}: Limitations attempts to grade/adjudicate or create findings"
        )
    expected_artifacts = target_artifacts(root, process, target, errors)
    declared_hashes = parse_target_hashes(target_hash_value, acceptance_md.name, errors)
    if list(declared_hashes) != expected_artifacts:
        errors.append(
            f"{acceptance_md.name}: target artifact hash order/set mismatch; "
            f"expected={expected_artifacts}, observed={list(declared_hashes)}"
        )
    for relative in expected_artifacts:
        path = root / Path(relative)
        if not path.is_file():
            errors.append(
                f"{acceptance_md.name}: missing declared target artifact {relative}"
            )
            continue
        actual = sha256(path)
        if declared_hashes.get(relative) != actual:
            errors.append(f"{acceptance_md.name}: target artifact hash mismatch for {relative}")
    validate_target_ledger_closure(root, process, target, shared, errors)
    rows = read_csv_rows(acceptance_csv, errors) if acceptance_csv.is_file() else []
    report_units, report_anchor_by_unit = authoritative_report_units(
        root,
        process,
        target,
        shared,
        errors,
    )
    reviewer_semantic_profile = (
        {}
        if target == "AI"
        else reviewer_semantic_target_profile(
            root,
            process,
            target,
            shared,
            errors,
        )
    )
    chapter_intervals = (
        []
        if target == "AI"
        else rendered_chapter_intervals(
            root,
            process,
            shared,
            errors,
            derived_cache=cache,
        )
    )
    expected = expected_units(
        root,
        process,
        target,
        errors,
        shared,
        chapter_intervals=chapter_intervals,
        report_units=report_units,
        derived_cache=cache,
    )
    chapter_interval_by_id = {
        chapter_id: (start, end)
        for chapter_id, start, end in chapter_intervals
    }
    citation_rows_by_pair: dict[str, dict[str, str]] = {}
    citation_inventory_by_pair: dict[str, dict[str, str]] = {}
    citation_endpoints_by_pair: dict[str, set[str]] = {}
    bibliography_endpoints_by_key: dict[str, set[str]] = {}
    bibliography_rows_by_key: dict[str, dict[str, str]] = {}
    bibliography_pages_by_reference: dict[str, set[int]] = {}
    rendered_reference_ids: set[str] = set()
    if target_is_citation_owner(process, target):
        citation_inventory_rows = read_generic_csv(
            root / "00-citation-inventory.csv", errors
        )
        citation_inventory_by_pair = {
            str(row.get("PairID", "")).strip(): row
            for row in citation_inventory_rows
        }
        citation_rows = read_generic_csv(
            root / "04-citation-claim-audit-ledger.csv", errors
        )
        citation_rows_by_pair = {
            str(row.get("PairID", "")).strip(): row for row in citation_rows
        }
        citation_endpoints_by_pair = {
            pair_id: set(shared.citation_ledger_public_endpoint_sequence([row]))
            for pair_id, row in citation_rows_by_pair.items()
        }
        rendered_reference_ids = set(bibliography_reference_ids(root, errors))
    if target_is_page_bib_owner(process, target):
        bibliography_rows = read_generic_csv(
            root / "03-bibliography-audit-ledger.csv", errors
        )
        bibliography_rows_by_key = {
            f"{str(row.get('ReferenceID', '')).strip()}/"
            f"{str(row.get('Field', '')).strip()}": row
            for row in bibliography_rows
        }
        bibliography_endpoints_by_key = {
            f"{str(row.get('ReferenceID', '')).strip()}/"
            f"{str(row.get('Field', '')).strip()}": set(
                shared.bibliography_ledger_public_endpoint_sequence([row])
            )
            for row in bibliography_rows
        }
        bibliography_pages_by_reference = rendered_bibliography_entry_pages(
            root,
            process,
            shared,
            errors,
            derived_cache=cache,
        )
    observed: list[tuple[str, str]] = []
    row_ids: list[str] = []
    artifact_hash_by_name = {
        relative: sha256(root / Path(relative))
        for relative in expected_artifacts
        if (root / Path(relative)).is_file()
    }
    used_urls: set[str] = set()
    try:
        physical_page_count = int(process.get("physical_page_count", 0) or 0)
    except (TypeError, ValueError):
        physical_page_count = 0
    for line, row in enumerate(rows, start=2):
        row_ids.append(row["AcceptanceRowID"])
        expected_id = f"SA{line - 1:06d}"
        if row["AcceptanceRowID"] != expected_id:
            errors.append(f"{acceptance_csv.name}:{line}: expected AcceptanceRowID {expected_id}")
        unit_type = row["TargetUnitType"]
        unit_id = row["TargetUnitID"]
        observed.append((unit_type, unit_id))
        if unit_type not in ALLOWED_UNIT_TYPES:
            errors.append(f"{acceptance_csv.name}:{line}: invalid TargetUnitType {unit_type!r}")
        expected_check = CHECK_CLASS_BY_UNIT_TYPE.get(unit_type)
        if row["CheckClass"] != expected_check:
            errors.append(
                f"{acceptance_csv.name}:{line}: CheckClass must be {expected_check!r}"
            )
        disposition = row["AcceptanceDisposition"]
        if disposition not in {"pass", "fail"}:
            errors.append(f"{acceptance_csv.name}:{line}: disposition must be pass or fail")
        artifact = row["TargetArtifact"]
        required_artifact = required_artifact_for_unit(target, unit_type, unit_id)
        if artifact != required_artifact:
            errors.append(
                f"{acceptance_csv.name}:{line}: {unit_type}/{unit_id} must bind "
                f"TargetArtifact={required_artifact!r}, got {artifact!r}"
            )
        if artifact not in artifact_hash_by_name:
            errors.append(f"{acceptance_csv.name}:{line}: unknown TargetArtifact {artifact!r}")
        elif row["TargetArtifactSHA256"].upper() != artifact_hash_by_name[artifact]:
            errors.append(f"{acceptance_csv.name}:{line}: target artifact hash mismatch")
        if len(row["EvidenceAnchor"].strip()) < 5:
            errors.append(f"{acceptance_csv.name}:{line}: EvidenceAnchor is shell-only")
        if len(row["SemanticBasis"].strip()) < 24:
            errors.append(f"{acceptance_csv.name}:{line}: SemanticBasis is shell-only")
        for field_name in ("EvidenceAnchor", "SemanticBasis"):
            if ADJUDICATION_INSTRUCTION_RE.search(row[field_name]):
                errors.append(
                    f"{acceptance_csv.name}:{line}: {field_name} attempts to "
                    "grade/adjudicate, direct the Chair, or create a finding"
                )
        validate_evidence_input_names(
            f"{row['EvidenceAnchor']} {row['SemanticBasis']}",
            expected_opened,
            target,
            f"{acceptance_csv.name}:{line}",
            errors,
        )
        row_urls = set(
            URL_RE.findall(f"{row['EvidenceAnchor']} {row['SemanticBasis']}")
        )
        used_urls.update(row_urls)
        page_matches: list[re.Match[str]] = []
        if unit_type in ALLOWED_UNIT_TYPES:
            page_matches = list(PHYSICAL_PAGE_RE.finditer(row["EvidenceAnchor"]))
            if not page_matches:
                errors.append(
                    f"{acceptance_csv.name}:{line}: {unit_type} row requires a physical p.<n> anchor"
                )
            for page_match in page_matches:
                start = int(page_match.group("start"))
                end = int(page_match.group("end") or start)
                if (
                    start > end
                    or start < 1
                    or end > physical_page_count
                ):
                    errors.append(
                        f"{acceptance_csv.name}:{line}: physical-page anchor "
                        f"{page_match.group(0)!r} is outside 1..{physical_page_count} "
                        "or has a descending range"
                    )
        singleton_pages = exact_singleton_physical_pages(row["EvidenceAnchor"])
        report_key = (unit_type, unit_id)
        if (
            disposition == "pass"
            and report_key in report_anchor_by_unit
            and report_anchor_by_unit[report_key] not in singleton_pages
        ):
            required_page = report_anchor_by_unit[report_key]
            errors.append(
                f"{acceptance_csv.name}:{line}: passing {unit_type} unit "
                f"{unit_id} must include its target's exact singleton "
                f"physical p.{required_page} anchor"
            )
        if disposition == "pass" and unit_type == "finding":
            validate_passing_finding_semantic_basis(
                row["SemanticBasis"],
                unit_id,
                reviewer_semantic_profile.get("findings", {}).get(unit_id),
                report_anchor_by_unit.get(report_key),
                physical_page_count,
                f"{acceptance_csv.name}:{line}",
                errors,
            )
        if disposition == "pass" and unit_type == "verdict":
            validate_passing_verdict_semantic_basis(
                row["SemanticBasis"],
                reviewer_semantic_profile,
                f"{acceptance_csv.name}:{line}",
                errors,
            )
        if unit_type == "page":
            page_match = re.fullmatch(r"P(\d+)", unit_id)
            if page_match is not None:
                required_page_number = int(page_match.group(1))
                anchor_page_matches = list(
                    PHYSICAL_PAGE_RE.finditer(row["EvidenceAnchor"])
                )
                if not any(
                    int(match.group("start")) == required_page_number
                    and int(match.group("end") or match.group("start"))
                    == required_page_number
                    for match in anchor_page_matches
                ):
                    errors.append(
                        f"{acceptance_csv.name}:{line}: page unit {unit_id} must "
                        f"include an exact singleton physical p.{required_page_number} anchor"
                    )
        if unit_type == "chapter" and unit_id in chapter_interval_by_id:
            chapter_start, chapter_end = chapter_interval_by_id[unit_id]
            anchor_page_matches = list(
                PHYSICAL_PAGE_RE.finditer(row["EvidenceAnchor"])
            )
            if not any(
                int(match.group("start")) >= chapter_start
                and int(match.group("end") or match.group("start")) <= chapter_end
                for match in anchor_page_matches
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: chapter unit {unit_id} must "
                    f"anchor within its rendered physical p.{chapter_start}-{chapter_end} interval"
                )
        if unit_type == "citation-pair":
            target_row = citation_rows_by_pair.get(unit_id, {})
            inventory_row = citation_inventory_by_pair.get(unit_id, {})
            recorded_endpoints = citation_endpoints_by_pair.get(unit_id, set())
            reference_id = str(target_row.get("ReferenceID", "")).strip()
            dangling = bool(reference_id) and reference_id not in rendered_reference_ids
            inventory_page = shared.parse_physical_page_locator(
                str(inventory_row.get("PDFLocation", ""))
            )
            target_page = shared.parse_physical_page_locator(
                str(target_row.get("PDFLocation", ""))
            )
            if inventory_page is None:
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 00 occurrence "
                    f"for {unit_id} lacks a physical PDF anchor"
                )
            elif inventory_page not in singleton_pages:
                errors.append(
                    f"{acceptance_csv.name}:{line}: citation-pair {unit_id} must "
                    f"include its exact occurrence singleton physical p.{inventory_page} anchor"
                )
            if target_page != inventory_page:
                errors.append(
                    f"{acceptance_csv.name}:{line}: 04 PDFLocation for {unit_id} "
                    "does not equal the authoritative 00 occurrence page"
                )
            if str(target_row.get("OccurrenceID", "")).strip() != str(
                inventory_row.get("OccurrenceID", "")
            ).strip():
                errors.append(
                    f"{acceptance_csv.name}:{line}: 04 OccurrenceID for {unit_id} "
                    "does not equal the authoritative 00 occurrence"
                )
            displayed_reference_id = str(
                inventory_row.get("DisplayedReferenceID", "")
            ).strip()
            if reference_id != displayed_reference_id:
                errors.append(
                    f"{acceptance_csv.name}:{line}: 04 ReferenceID for {unit_id} "
                    "does not equal authoritative 00 DisplayedReferenceID"
                )
            for source_name, source_row in (
                ("00 citation occurrence", inventory_row),
                ("04 citation row", target_row),
            ):
                row_pdf_hash = str(source_row.get("PDFSHA256", "")).strip().upper()
                if row_pdf_hash != expected_pdf_hash:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: {source_name} for {unit_id} "
                        "does not bind the frozen PDF SHA-256"
                    )
            proposition = str(
                target_row.get("ExactAttachedProposition", "")
            ).strip()
            row_evidence = f"{row['EvidenceAnchor']} {row['SemanticBasis']}"
            if not proposition:
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 04 row for "
                    f"{unit_id} lacks an exact attached proposition"
                )
            elif not exact_normalized_value_is_bound(proposition, row_evidence):
                errors.append(
                    f"{acceptance_csv.name}:{line}: citation-pair {unit_id} does "
                    "not bind the exact attached thesis proposition"
                )
            source_locator = str(
                target_row.get("ExactSourceLocator", "")
            ).strip()
            support = str(target_row.get("Support", "")).strip().casefold()
            metadata_status = str(
                target_row.get("MetadataStatus", "")
            ).strip().casefold()
            primary_endpoint = str(
                target_row.get("ContentSourceOpened", "")
            ).strip()
            primary_is_public = bool(
                getattr(shared, "PUBLIC_URL_RE", URL_RE).fullmatch(
                    primary_endpoint
                )
            )
            documented_unopened_unverifiable = (
                not dangling
                and support == "unverifiable"
                and not primary_endpoint
                and not source_locator
            )
            requires_source_evidence = (
                not dangling and not documented_unopened_unverifiable
            )
            locator_identity = shared.canonical_atomic_locator_identity(
                source_locator
            )
            expected_locator_atoms = source_locator_identities(
                source_locator,
                shared,
            )
            evidence_locator_atoms = source_locator_identities(
                row["EvidenceAnchor"],
                shared,
            )
            if requires_source_evidence and (
                not source_locator
                or shared.SOURCE_LOCATOR_RE.search(source_locator) is None
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 04 row for "
                    f"{unit_id} lacks an exact source locator"
                )
            elif (
                requires_source_evidence
                and (
                    (
                        expected_locator_atoms
                        and not expected_locator_atoms.issubset(
                            evidence_locator_atoms
                        )
                    )
                    or (
                        not expected_locator_atoms
                        and not exact_normalized_value_is_bound(
                            locator_identity,
                            row["EvidenceAnchor"],
                        )
                    )
                )
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: citation-pair {unit_id} does "
                    "not bind its authoritative 04 source locator"
                )
            valid_support = set(
                getattr(
                    shared,
                    "SUPPORT_VALUES",
                    {
                        "direct",
                        "partial",
                        "context-only",
                        "mismatch",
                        "unverifiable",
                        "not-needed",
                    },
                )
            )
            if support not in valid_support:
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 04 row for "
                    f"{unit_id} has invalid support {support!r}"
                )
            valid_metadata_status = set(
                getattr(
                    shared,
                    "METADATA_STATUS_VALUES",
                    {"verified", "mismatch", "unverifiable"},
                )
            )
            if metadata_status not in valid_metadata_status:
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 04 row for "
                    f"{unit_id} has invalid metadata status {metadata_status!r}"
                )
            substantive_support = set(
                getattr(
                    shared,
                    "SUBSTANTIVE_CITATION_SUPPORT_VALUES",
                    {"direct", "partial", "context-only", "mismatch"},
                )
            )
            if (
                disposition == "pass"
                and support in substantive_support
                and is_abstract_only_source_locator(source_locator, shared)
                and DETAILED_CITATION_RESPONSIBILITY_RE.search(proposition)
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: an Abstract-only locator "
                    "cannot accept this detailed formula/definition/algorithm/"
                    "table-value responsibility"
                )
            if requires_source_evidence and not primary_is_public:
                errors.append(
                    f"{acceptance_csv.name}:{line}: citation-pair {unit_id} lacks "
                    "one complete primary ContentSourceOpened public endpoint"
                )
            elif requires_source_evidence and primary_endpoint not in row_urls:
                errors.append(
                    f"{acceptance_csv.name}:{line}: citation-pair {unit_id} must "
                    "cite its own primary ContentSourceOpened endpoint; an "
                    "auxiliary attempted endpoint cannot replace it"
                )
            if dangling:
                if row_urls:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: dangling citation-pair "
                        "must not invent an opened source URL"
                    )
                sentinel = str(
                    getattr(
                        shared,
                        "DANGLING_REFERENCE_SENTINEL",
                        "no rendered bibliography entry",
                    )
                )
                public_identifier = str(
                    target_row.get("PublicIdentifier", "")
                ).strip()
                disposition_evidence = str(
                    target_row.get("DispositionEvidence", "")
                ).strip()
                marker_match = re.fullmatch(r"REF(\d+)", displayed_reference_id)
                expected_marker = (
                    f"[{int(marker_match.group(1))}]"
                    if marker_match is not None else ""
                )
                expected_gap = (
                    f"{displayed_reference_id} has {sentinel}"
                    if displayed_reference_id else ""
                )
                semantic_basis = row["SemanticBasis"]
                if (
                    public_identifier != sentinel
                    or support != "unverifiable"
                    or metadata_status != "mismatch"
                    or primary_endpoint
                    or source_locator
                ):
                    errors.append(
                        f"{acceptance_csv.name}:{line}: dangling citation-pair "
                        "does not preserve the authoritative 04 dangling sentinel, "
                        "blank source/locator, and mismatch/unverifiable state"
                    )
                dangling_bindings = (
                    (
                        PDF_VISIBLE_LOCATION_CUE_RE,
                        str(target_row.get("PDFLocation", "")).strip(),
                        "PDF-visible location",
                    ),
                    (
                        DISPLAYED_MARKER_CUE_RE,
                        expected_marker,
                        "displayed marker",
                    ),
                    (
                        RENDERED_REFERENCE_GAP_CUE_RE,
                        expected_gap,
                        "rendered REF gap",
                    ),
                    (
                        AUDITED_SUPPORT_CUE_RE,
                        "unverifiable",
                        "audited Support=unverifiable state",
                    ),
                    (
                        AUDITED_METADATA_STATUS_CUE_RE,
                        "mismatch",
                        "audited MetadataStatus=mismatch state",
                    ),
                    (
                        AUTHORITATIVE_DISPOSITION_CUE_RE,
                        disposition_evidence,
                        "authoritative 04 disposition",
                    ),
                )
                missing_bindings = [
                    label
                    for pattern, value, label in dangling_bindings
                    if not cue_binds_value(pattern, value, semantic_basis)
                ]
                if missing_bindings:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: dangling citation-pair "
                        "requires exact PDF-visible marker/reference-gap and "
                        "authoritative 04 state bindings in SemanticBasis; missing "
                        + ", ".join(missing_bindings)
                    )
                non_pdf_anchor = PHYSICAL_PAGE_RE.sub(" ", row["EvidenceAnchor"])
                if shared.SOURCE_LOCATOR_RE.search(non_pdf_anchor) is not None:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: dangling citation-pair "
                        "must not invent a source-content locator"
                    )
            elif documented_unopened_unverifiable:
                disposition_evidence = str(
                    target_row.get("DispositionEvidence", "")
                ).strip()
                access_failure_re = getattr(
                    shared,
                    "ACCESS_FAILURE_DETAIL_RE",
                    re.compile(
                        r"(?i)(?:http\s*[45]\d\d|timeout|access denied|"
                        r"not found|inaccessible|insufficient to verify)"
                    ),
                )
                if not disposition_evidence or access_failure_re.search(
                    disposition_evidence
                ) is None:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: documented unopened "
                        f"unverifiable citation-pair {unit_id} lacks a concrete "
                        "authoritative 04 access/content limitation"
                    )
                for pattern, value, label in (
                    (AUDITED_SUPPORT_CUE_RE, support, "audited support"),
                    (
                        AUDITED_METADATA_STATUS_CUE_RE,
                        metadata_status,
                        "audited metadata status",
                    ),
                    (
                        AUTHORITY_ACCESS_LIMITATION_CUE_RE,
                        disposition_evidence,
                        "authority access limitation",
                    ),
                ):
                    if not cue_binds_value(pattern, value, row["SemanticBasis"]):
                        errors.append(
                            f"{acceptance_csv.name}:{line}: documented unopened "
                            f"unverifiable citation-pair {unit_id} does not bind "
                            f"its exact {label} in SemanticBasis"
                        )
                if row_urls - recorded_endpoints:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: citation-pair evidence URL "
                        "is not recorded on this authoritative 04 Pair row"
                    )
                non_pdf_anchor = PHYSICAL_PAGE_RE.sub(" ", row["EvidenceAnchor"])
                if shared.SOURCE_LOCATOR_RE.search(non_pdf_anchor) is not None:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: documented unopened "
                        "unverifiable citation-pair must not invent a source locator"
                    )
            else:
                if not row_urls:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: citation-pair requires "
                        "its recorded opened source URL"
                    )
                if row_urls - recorded_endpoints:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: citation-pair evidence URL "
                        "is not recorded on this authoritative 04 Pair row"
                    )
                if not recorded_endpoints:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: authoritative 04 Pair row "
                        "has no recorded content endpoint"
                    )
                if shared.SOURCE_LOCATOR_RE.search(row["EvidenceAnchor"]) is None:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: citation-pair requires "
                        "a numbered/named exact source locator, not a bare label"
                    )
        if unit_type == "bibliography-field":
            target_row = bibliography_rows_by_key.get(unit_id, {})
            recorded_endpoints = bibliography_endpoints_by_key.get(unit_id, set())
            primary_endpoint = str(target_row.get("EvidenceEndpoint", "")).strip()
            reference_id, _, field = unit_id.partition("/")
            rendered_pages = bibliography_pages_by_reference.get(reference_id, set())
            if not rendered_pages:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "has no derived rendered-entry page"
                )
            elif not (singleton_pages & rendered_pages):
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "must include an exact singleton physical page belonging to "
                    f"its rendered entry; expected one of {sorted(rendered_pages)}"
                )
            if field == "url" and rendered_pages - singleton_pages:
                errors.append(
                    f"{acceptance_csv.name}:{line}: cross-page URL acceptance for "
                    f"{reference_id} must bind every rendered entry page "
                    f"{sorted(rendered_pages)}"
                )
            row_evidence = f"{row['EvidenceAnchor']} {row['SemanticBasis']}"
            if RENDERED_CUE_RE.search(row_evidence) is None:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "requires an explicit rendered cue:"
                )
            if AUTHORITY_CUE_RE.search(row_evidence) is None:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "requires an explicit authority/canonical cue:"
                )
            if AUDITED_VERDICT_CUE_RE.search(row_evidence) is None:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "requires an explicit audited verdict: cue"
                )
            rendered_value = str(target_row.get("RenderedValue", "")).strip()
            canonical_value = str(target_row.get("CanonicalValue", "")).strip()
            verdict = str(target_row.get("Verdict", "")).strip().casefold()
            valid_verdicts = set(
                getattr(
                    shared,
                    "BIB_VERDICTS",
                    {"exact", "mismatch", "legitimate n/a", "unverifiable"},
                )
            )
            if verdict not in valid_verdicts:
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 03 row for "
                    f"{unit_id} has invalid verdict {verdict!r}"
                )
            if not verdict or not cue_binds_value(
                AUDITED_VERDICT_CUE_RE,
                verdict,
                row_evidence,
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "does not bind the authoritative audited verdict"
                )
            if not cue_binds_value(
                RENDERED_CUE_RE,
                rendered_value,
                row_evidence,
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "does not bind its rendered field value"
                )
            if not cue_binds_value(
                AUTHORITY_CUE_RE,
                canonical_value,
                row_evidence,
            ):
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "does not bind its canonical authority value"
                )
            if verdict == "legitimate n/a":
                if re.search(
                    r"(?i)(?:absent|not\s+(?:applicable|required)|visible\s+absence|"
                    r"缺失|未呈现|不适用|无需)",
                    row_evidence,
                ) is None:
                    errors.append(
                        f"{acceptance_csv.name}:{line}: legitimate N/A for {unit_id} "
                        "must explain rendered absence and authority/style non-applicability"
                    )
            elif verdict == "unverifiable":
                note = str(target_row.get("EvidenceNote", "")).strip()
                if note and not substantive_value_is_bound(note, row_evidence):
                    errors.append(
                        f"{acceptance_csv.name}:{line}: unverifiable {unit_id} "
                        "does not bind its concrete authority-access limitation"
                    )
            if not row_urls:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field requires "
                    "its authoritative recorded endpoint"
                )
            primary_is_public = bool(
                getattr(shared, "PUBLIC_URL_RE", URL_RE).fullmatch(
                    primary_endpoint
                )
            )
            if not primary_is_public:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "lacks one complete primary EvidenceEndpoint public URL"
                )
            elif primary_endpoint not in row_urls:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field {unit_id} "
                    "must cite its own primary EvidenceEndpoint; an auxiliary "
                    "EvidenceNote endpoint cannot replace it"
                )
            if row_urls - recorded_endpoints:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field evidence URL "
                    "is not recorded on this authoritative 03 field row"
                )
            if not recorded_endpoints:
                errors.append(
                    f"{acceptance_csv.name}:{line}: authoritative 03 field row "
                    "has no recorded evidence endpoint"
                )
            if shared.SOURCE_LOCATOR_RE.search(row["EvidenceAnchor"]) is None:
                errors.append(
                    f"{acceptance_csv.name}:{line}: bibliography-field requires "
                    "a numbered/named exact authoritative field locator"
                )
    if observed != expected:
        errors.append(
            f"{acceptance_csv.name}: semantic coverage sequence mismatch; "
            f"expected {len(expected)} rows, observed {len(observed)} rows"
        )
    if len(row_ids) != len(set(row_ids)):
        errors.append(f"{acceptance_csv.name}: duplicate AcceptanceRowID values")
    if any(url not in set(receipt_public) for url in used_urls):
        errors.append(
            f"{acceptance_csv.name}: evidence cites public endpoints absent from the SA receipt"
        )
    if target == "AI" and used_urls:
        errors.append(
            f"{acceptance_csv.name}: SA-AI evidence must not cite public endpoints"
        )
    validate_template_diversity(rows, errors)
    try:
        coverage_count = int(coverage_count_value)
    except ValueError:
        coverage_count = -1
    if coverage_count != len(rows):
        errors.append(f"{acceptance_md.name}: Coverage row count does not equal CSV rows")
    fail_count = sum(
        1 for row in rows if row["AcceptanceDisposition"] == "fail"
    )
    try:
        declared_fail_count = int(failure_count_value)
    except ValueError:
        declared_fail_count = -1
    if declared_fail_count != fail_count:
        errors.append(f"{acceptance_md.name}: Acceptance failure count mismatch")
    expected_overall = "PASS" if fail_count == 0 and rows else "FAIL"
    if overall not in {"PASS", "FAIL"} or overall != expected_overall:
        errors.append(
            f"{acceptance_md.name}: Overall semantic acceptance must be {expected_overall}"
        )
    if enforce_closed_view:
        allowed_root_files = {
            *[item for item in expected_opened if "/" not in item],
            acceptance_md.name,
            acceptance_csv.name,
        }
        allowed_dirs = {
            Path(item).parts[0]
            for item in expected_opened
            if len(Path(item).parts) > 1
        }
        for entry in root.iterdir():
            if shared.is_link_or_reparse(entry):
                errors.append(f"semantic-acceptance view contains unsafe entry {entry.name}")
            elif entry.is_file() and entry.name not in allowed_root_files:
                errors.append(f"semantic-acceptance view contains extra file {entry.name}")
            elif entry.is_dir() and entry.name not in allowed_dirs:
                errors.append(f"semantic-acceptance view contains extra directory {entry.name}")
        if "page-renders" in allowed_dirs:
            expected_renders = {
                Path(item).name for item in expected_opened if item.startswith("page-renders/")
            }
            render_root = root / "page-renders"
            if render_root.is_dir():
                actual_renders = {item.name for item in render_root.iterdir() if item.is_file()}
                unsafe_render_entries = [
                    item.name
                    for item in render_root.iterdir()
                    if shared.is_link_or_reparse(item) or not item.is_file()
                ]
                if unsafe_render_entries or actual_renders != expected_renders:
                    errors.append("semantic-acceptance view page-renders file set mismatch")
        if "rules" in allowed_dirs:
            rules_root = root / "rules"
            scripts_root = rules_root / "scripts"
            if (
                shared.is_link_or_reparse(rules_root)
                or shared.is_link_or_reparse(scripts_root)
                or not scripts_root.is_dir()
            ):
                errors.append("semantic-acceptance view rules/scripts topology is unsafe")
            else:
                extra_rule_dirs = [
                    item.name
                    for item in rules_root.iterdir()
                    if item.name != "scripts" or not item.is_dir()
                ]
                expected_scripts = {
                    Path(item).name
                    for item in expected_opened
                    if item.startswith("rules/scripts/")
                }
                actual_scripts = {
                    item.name for item in scripts_root.iterdir() if item.is_file()
                }
                unsafe_scripts = [
                    item.name
                    for item in scripts_root.iterdir()
                    if shared.is_link_or_reparse(item) or not item.is_file()
                ]
                if extra_rule_dirs or unsafe_scripts or actual_scripts != expected_scripts:
                    errors.append(
                        "semantic-acceptance view rules/scripts file topology mismatch"
                    )
    result = {
        "target": target,
        "status": overall,
        "target_artifacts": declared_hashes,
        "acceptance_md": acceptance_md,
        "acceptance_csv": acceptance_csv,
        "coverage_rows": len(rows),
        "failure_count": fail_count,
    }
    return errors, result


def expected_gate(
    root: Path, process: dict[str, Any], results: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    for result in results:
        target = str(result["target"])
        targets[target] = {
            "target_artifacts": result["target_artifacts"],
            "acceptance_md_sha256": sha256(Path(result["acceptance_md"])),
            "acceptance_csv_sha256": sha256(Path(result["acceptance_csv"])),
            "coverage_rows": int(result["coverage_rows"]),
            "status": str(result["status"]),
        }
    all_pass = bool(targets) and all(
        target.get("status") == "PASS" for target in targets.values()
    )
    prompt_map = process.get("actor_prompt_sha256", {})
    sa_prompt_hashes = {
        f"SA-{target}": str(prompt_map.get(f"SA-{target}", "")).upper()
        for target in required_targets(process)
    } if isinstance(prompt_map, dict) else {}
    return {
        "schema": "thesis-review-semantic-acceptance-gate-v2",
        "round_id": str(process.get("round_id", "")),
        "retry_id": str(process.get("retry_id", "")),
        "pdf_sha256": str(process.get("selected_pdf_sha256", "")).upper(),
        "process_sha256": sha256(root / "00-process-parameters.json"),
        "sa_actor_prompt_sha256": sa_prompt_hashes,
        "targets": targets,
        "status": "PASS" if all_pass else "FAIL",
    }


def validate_set(
    root: Path,
    shared: Any,
    *,
    require_gate: bool,
    derived_cache: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    cache = derived_cache if derived_cache is not None else {}
    if shared.is_link_or_reparse(root) or not root.is_dir():
        return ["semantic-acceptance round root is missing or unsafe"], None
    preflight_tree_no_reparse(root, shared, errors)
    if errors:
        return errors, None
    process_path = root / "00-process-parameters.json"
    if path_has_unsafe_component(root, process_path, shared) or not process_path.is_file():
        return ["missing or unsafe semantic-acceptance process envelope"], None
    process = read_json(process_path, errors)
    if process is None:
        return errors, None
    if not validate_semantic_process_shape(process, errors):
        return errors, None
    acceptance_dir = root / ACCEPTANCE_DIRECTORY
    if path_has_unsafe_component(root, acceptance_dir, shared) or not acceptance_dir.is_dir():
        return [f"missing or unsafe {ACCEPTANCE_DIRECTORY} directory"], None
    leaked_actor_outputs = sorted(
        entry.name
        for entry in root.iterdir()
        if ROUND_ROOT_ACTOR_OUTPUT_RE.fullmatch(entry.name)
    )
    if leaked_actor_outputs:
        errors.append(
            "round root: SA actor outputs must exist only inside "
            f"{ACCEPTANCE_DIRECTORY}; leaked={leaked_actor_outputs}"
        )
    # Fail before opening any acceptance or target output if any required
    # round-resident input (or an ancestor such as page-renders/) is a reparse
    # point, missing, or non-regular.
    for target in required_targets(process):
        preflight_actor_resident_inputs(
            root,
            process,
            target,
            shared,
            errors,
            acceptance_directory=acceptance_dir,
            include_ephemeral_rules=False,
        )
    gate_path = root / GATE_FILE
    if gate_path.exists() and (
        path_has_unsafe_component(root, gate_path, shared) or not gate_path.is_file()
    ):
        errors.append(f"{GATE_FILE}: unsafe gate entry")
    if errors:
        return errors, None
    validate_process_for_semantic_acceptance(
        root, process, shared, errors, target=None
    )
    if errors:
        return errors, None
    expected_names = {
        f"SA-{target}.{suffix}"
        for target in required_targets(process)
        for suffix in ("md", "csv")
    }
    actual_names: set[str] = set()
    for entry in acceptance_dir.iterdir():
        if shared.is_link_or_reparse(entry) or not entry.is_file():
            errors.append(f"{ACCEPTANCE_DIRECTORY}: unsafe/non-file entry {entry.name}")
        else:
            actual_names.add(entry.name)
    if actual_names != expected_names:
        errors.append(
            f"{ACCEPTANCE_DIRECTORY}: file set mismatch; "
            f"missing={sorted(expected_names-actual_names)}, extra={sorted(actual_names-expected_names)}"
        )
    results: list[dict[str, Any]] = []
    for target in required_targets(process):
        actor_errors, result = validate_actor(
            root,
            target,
            shared,
            acceptance_directory=acceptance_dir,
            enforce_closed_view=False,
            require_opened_files=False,
            validated_process=process,
            derived_cache=cache,
        )
        errors.extend(actor_errors)
        if result is not None and not actor_errors:
            results.append(result)
            if result.get("status") != "PASS":
                errors.append(f"SA-{target}: semantic acceptance is not PASS")
    expected = (
        expected_gate(root, process, results)
        if len(results) == len(required_targets(process))
        and all(result.get("status") == "PASS" for result in results)
        else None
    )
    if gate_path.exists():
        if shared.is_link_or_reparse(gate_path) or not gate_path.is_file():
            errors.append(f"{GATE_FILE}: unsafe gate entry")
        else:
            observed = read_json(gate_path, errors)
            if expected is None:
                errors.append(
                    f"{GATE_FILE}: gate content/hash closure mismatch; gate cannot "
                    "remain when the semantic-acceptance set is incomplete or invalid"
                )
            elif observed != expected:
                errors.append(f"{GATE_FILE}: gate content/hash closure mismatch")
    elif require_gate:
        errors.append(f"missing required {GATE_FILE}")
    return errors, expected


def print_result(errors: list[str], message: str) -> int:
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("PASS")
    print(message)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("target", nargs="?")
    parser.add_argument("--set", action="store_true", dest="set_mode")
    parser.add_argument("--require-gate", action="store_true")
    args = parser.parse_args(argv)
    if args.set_mode == bool(args.target):
        parser.error("use exactly one of <target> or --set")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        shared = load_shared_validator()
        root = args.root.absolute()
        if args.set_mode:
            errors, _ = validate_set(root, shared, require_gate=args.require_gate)
            return print_result(
                errors,
                "Current semantic-acceptance actor set and optional gate hash closure passed.",
            )
        errors, result = validate_actor(
            root, str(args.target), shared, enforce_closed_view=True
        )
        if result is not None and result.get("status") != "PASS":
            errors.append(
                f"SA-{args.target}: semantic acceptance is not PASS"
            )
        return print_result(
            errors,
            f"Current SA-{args.target} view passed the read-only semantic-acceptance gate.",
        )
    except Exception as exc:  # pragma: no cover - fail closed at CLI boundary
        return print_result([f"semantic-acceptance validator failed safely: {exc}"], "")
    finally:
        sys.dont_write_bytecode = previous


if __name__ == "__main__":
    sys.exit(main())
