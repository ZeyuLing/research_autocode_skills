#!/usr/bin/env python3
"""Deterministically materialize current-stage projections before freeze.

This is a pre-freeze writer, not a validator and not a substantive actor. It is
run inside the same fresh owner/Chair/Stage-S turn after semantic source content
is complete and before the role's read-only scoped gate. It never enumerates the
round root, opens an input outside the actor's closed allowlist, changes a
semantic master, or supplies a verdict. Reviewer owners and Chair write only
their owned Markdown projections. Stage S additionally writes its two wholly
derived 93 CSV subsets and their owned Markdown summary; those three wholly
derived outputs may be absent on the first Stage-S invocation.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")
RECEIPT_ENDPOINT_RE = re.compile(r"public_endpoints=\[([^\]\r\n]+)\]")

ACADEMIC_MD_HEADERS = [
    "Ledger ID", "Priority", "Chair finding ID", "Source reviewer finding IDs",
    "Severity", "S0 subtype", "Remedy", "Exact PDF anchor",
    "Direct observation", "Evidence status", "Minimum edit/evidence",
    "Dependency", "Owner", "Status", "Verification",
]
ACADEMIC_MD_FIELDS = [
    "LedgerID", "Priority", "ChairFindingID", "SourceReviewerFindingIDs",
    "Severity", "S0Subtype", "Remedy", "ExactPDFAnchor", "DirectObservation",
    "EvidenceStatus", "MinimumEditEvidence", "Dependency", "Owner", "Status",
    "Verification",
]
AI_MD_HEADERS = [
    "AI finding ID", "Impact (`material` / `local`)", "Exact PDF anchor",
    "Direct style observation", "Minimum editing action", "Status", "Verification",
]
AI_MD_FIELDS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "Status", "Verification",
]
CHAIR_FINDING_HEADERS = [
    "Chair finding ID", "Source reviewer finding IDs", "Severity", "S0 subtype",
    "Remedy", "Exact PDF anchor", "Direct observation", "Evidence status",
    "Owner", "Minimum required action", "Verification",
]
CHAIR_FINDING_FIELDS = [
    "ChairFindingID", "SourceReviewerFindingIDs", "Severity", "S0Subtype",
    "Remedy", "ExactPDFAnchor", "DirectObservation", "EvidenceStatus", "Owner",
    "MinimumEditEvidence", "Verification",
]
CHAIR_AI_HEADERS = [
    "AI finding ID", "Impact (`material` / `local`)", "Exact PDF anchor",
    "Direct style observation", "Minimum editing action", "Verification", "Status",
]
CHAIR_AI_FIELDS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "Verification", "Status",
]
WEP_HEADERS = [
    "Ledger ID", "Remedy", "Exact PDF anchor", "Minimum edit/evidence",
    "Verification",
]
WEP_FIELDS = [
    "LedgerID", "Remedy", "ExactPDFAnchor", "MinimumEditEvidence", "Verification",
]
EVIDENCE_MD_HEADERS = [
    "Evidence item ID", "Ledger ID", "Chair finding ID", "Remedy", "Item",
    "Claim that depends on it", "Why writing is insufficient",
    "Minimum viable evidence", "Consequence if unavailable",
]
SUMMARY_ACADEMIC_HEADERS = [
    "Ledger ID", "Priority", "Chair finding ID", "Source reviewer finding IDs",
    "Severity", "S0 subtype", "Remedy", "Exact PDF anchor",
    "Direct PDF-visible observation", "Evidence status", "Minimum required action",
    "Dependency", "Owner", "Chair disposition", "Verification",
]
SUMMARY_AI_HEADERS = [
    "AI finding ID", "Impact (`material` / `local`)", "Exact PDF anchor",
    "Direct style observation", "Minimum editing action", "Chair status",
    "Verification",
]
CONCLUSION_HEADERS = [
    "Actor", "Persona/status", "Category or AI-style label",
    "Exact defense recommendation", "Decision regime/source", "Confidence",
    "Decisive current-round basis",
]
DISAGREEMENT_HEADERS = [
    "Decision ID", "Source item IDs", "Topic", "Positions", "Evidence checked",
    "Status", "Decision",
]


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "thesis_review_bundle_validator_for_materializer", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_regular_file(module: Any, path: Path, errors: list[str]) -> bool:
    """Require one exact, non-aliased, single-link regular file."""

    try:
        metadata = path.lstat()
    except OSError as exc:
        errors.append(f"cannot safely inspect required file {path.name}: {exc}")
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    if (
        stat.S_ISLNK(metadata.st_mode)
        or reparse
        or module.is_link_or_reparse(path)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        errors.append(
            f"required file {path.name} must be a non-aliased single-link "
            "regular file"
        )
        return False
    return True


def read_csv_exact(
    path: Path, expected_headers: list[str], errors: list[str], *,
    require_rows: bool = True,
) -> list[dict[str, str]]:
    if not safe_regular_file(load_validator_cached(), path, errors):
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            if headers != expected_headers:
                errors.append(
                    f"{path.name}: schema mismatch; expected {expected_headers}, "
                    f"got {headers}"
                )
                return []
            rows: list[dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                if None in row:
                    errors.append(
                        f"{path.name}:{line}: values exceed declared header"
                    )
                    continue
                rows.append({
                    key: (row.get(key) or "")
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                    for key in expected_headers
                })
            if require_rows and not rows:
                errors.append(f"{path.name}: empty authoritative CSV")
            return rows
    except (OSError, csv.Error) as exc:
        errors.append(f"cannot read {path.name}: {exc}")
        return []


_VALIDATOR_CACHE: Any | None = None


def load_validator_cached() -> Any:
    global _VALIDATOR_CACHE
    if _VALIDATOR_CACHE is None:
        _VALIDATOR_CACHE = load_validator()
    return _VALIDATOR_CACHE


def replace_exact_table(
    text: str, headers: list[str], canonical_table: str, filename: str,
    errors: list[str],
) -> str:
    """Replace exactly one table beginning with the canonical header row."""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    parser = load_validator_cached().parse_markdown_pipe_row
    matches = [
        index for index, line in enumerate(lines)
        if parser(line) == headers
    ]
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one canonical table header, "
            f"found {len(matches)}"
        )
        return text
    start = matches[0]
    if start + 1 >= len(lines) or parser(lines[start + 1]) is None:
        errors.append(f"{filename}: canonical table lacks a separator row")
        return text
    end = start + 2
    while end < len(lines) and parser(lines[end]) is not None:
        end += 1
    canonical_lines = canonical_table.rstrip("\n").splitlines()
    return "\n".join([*lines[:start], *canonical_lines, *lines[end:]]) + "\n"


def replace_receipt_endpoints(
    text: str, endpoints: Iterable[str], filename: str, errors: list[str]
) -> str:
    ordered = load_validator_cached().ordered_unique(endpoints)
    replacement = "public_endpoints=[" + ("; ".join(ordered) or "none") + "]"
    matches = list(RECEIPT_ENDPOINT_RE.finditer(text))
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one public_endpoints receipt field, "
            f"found {len(matches)}"
        )
        return text
    current = [
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", matches[0].group(1))
        if token.strip()
    ]
    unknown = sorted(
        value for value in set(current) - {"none"} if value not in set(ordered)
    )
    if unknown:
        errors.append(
            f"{filename}: existing receipt contains endpoint(s) absent from "
            f"the authoritative owned access fields: {unknown}; record every "
            "actually opened auxiliary route with 'accessed endpoint: <URL>' "
            "before materialization, or remove a false receipt entry"
        )
        return text
    return RECEIPT_ENDPOINT_RE.sub(lambda _match: replacement, text, count=1)


def replace_receipt_opened(
    text: str, opened: Iterable[str], filename: str, errors: list[str]
) -> str:
    ordered = list(opened)
    replacement = "opened=[" + "; ".join(ordered) + "]"
    pattern = re.compile(r"opened=\[([^\]\r\n]*)\]")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one opened receipt field, "
            f"found {len(matches)}"
        )
        return text
    return pattern.sub(lambda _match: replacement, text, count=1)


def replace_labeled_value(
    text: str, label: str, value: str, filename: str, errors: list[str]
) -> str:
    pattern = re.compile(
        rf"(?m)^([ ]{{0,3}}-[ \t]+{re.escape(label)}[ \t]*:[ \t]*)(.*?)[ \t]*$"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one {label!r} field, found {len(matches)}"
        )
        return text
    return pattern.sub(lambda match: match.group(1) + value, text, count=1)


def replace_section_body(
    text: str, heading: str, body: str, filename: str, errors: list[str]
) -> str:
    pattern = re.compile(
        rf"(?ms)^([ ]{{0,3}}##[ \t]+{re.escape(heading)}"
        rf"(?:[ \t]+#+)?[ \t]*\n)(.*?)(?=^[ ]{{0,3}}##[ \t]+|\Z)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one section {heading!r}, found {len(matches)}"
        )
        return text
    normalized = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    replacement = lambda match: match.group(1) + normalized + "\n\n"
    return pattern.sub(replacement, text, count=1)


def render_csv_text(headers: list[str], rows: Iterable[dict[str, str]]) -> str:
    import io

    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in headers})
    return handle.getvalue()


def projected_rows(
    module: Any, rows: Iterable[dict[str, str]], fields: list[str]
) -> list[list[str]]:
    return [
        [module.markdown_projection_scalar(row.get(field, "")) for field in fields]
        for row in rows
    ]


def replace_actor_receipt(
    text: str,
    opened: list[str],
    endpoints: Iterable[str],
    filename: str,
    errors: list[str],
) -> str:
    text = replace_receipt_opened(text, opened, filename, errors)
    return replace_receipt_endpoints(text, endpoints, filename, errors)


def selected_chair_endpoints(
    module: Any,
    chair_text: str,
    allowed_sequence: list[str],
    required: set[str],
    errors: list[str],
) -> list[str]:
    """Normalize the one semantic C access selection already recorded in 90."""

    matches = list(RECEIPT_ENDPOINT_RE.finditer(chair_text))
    if len(matches) != 1:
        errors.append(
            "90-chair-synthesis.md: expected exactly one public_endpoints receipt field"
        )
        return []
    declared = [
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", matches[0].group(1))
        if token.strip() and token.strip().casefold() != "none"
    ]
    allowed = set(allowed_sequence)
    unknown = sorted(set(declared) - allowed)
    missing = sorted(required - set(declared))
    if unknown:
        errors.append(
            "90-chair-synthesis.md: public_endpoints contains endpoint(s) outside "
            f"the current C allowlist: {unknown}"
        )
    if missing:
        errors.append(
            "90-chair-synthesis.md: public_endpoints omits required governing "
            f"endpoint(s): {missing}"
        )
    selected = set(declared)
    return [value for value in allowed_sequence if value in selected]


def table_rows_from_section(
    module: Any,
    text: str,
    heading: str,
    headers: list[str],
    filename: str,
    errors: list[str],
) -> list[list[str]]:
    section = module.markdown_section_body_raw(text, heading) or ""
    rows = module.parse_markdown_table_by_exact_headers(
        section, headers, filename, errors, case_sensitive=True
    )
    return rows or []


def atomic_replace_text(
    module: Any,
    path: Path,
    text: str,
    *,
    allow_create: bool = False,
) -> str | None:
    """Atomically publish one owned projection, optionally creating it once."""

    errors: list[str] = []
    missing = False
    try:
        path.lstat()
    except FileNotFoundError:
        missing = True
    except OSError as exc:
        return f"cannot safely inspect owned projection {path.name}: {exc}"
    if missing:
        if not allow_create:
            return f"required owned projection {path.name} does not exist"
    elif not safe_regular_file(module, path, errors):
        return "; ".join(errors)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.stem}-materialized-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        if missing:
            # Link publication is atomic and fails closed if another entry
            # appeared after the absence check. Removing the temporary name
            # leaves the published output as a single-link regular file.
            os.link(temporary_path, path)
            temporary_path.unlink()
        else:
            temporary_path.replace(path)
        temporary_path = None
        return None
    except OSError as exc:
        return f"could not atomically replace {path.name}: {exc}"
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def role_contract(process: dict[str, Any], actor_id: str) -> tuple[str, ...] | None:
    degree = process.get("degree_level")
    if degree == "doctorate" and actor_id == "R5":
        return ("02", "03", "report")
    if degree == "doctorate" and actor_id == "R4":
        return ("04", "report")
    if degree == "masters" and actor_id == "R3":
        return ("02", "03", "04", "report")
    if actor_id == "C" and degree in {"doctorate", "masters"}:
        return ("chair",)
    if actor_id == "S" and degree in {"doctorate", "masters"}:
        return ("summary",)
    return None


def reviewer_count_for_process(process: dict[str, Any]) -> int:
    return 5 if process.get("degree_level") == "doctorate" else 3


def salvage_cross_ledger_semantics(
    module: Any, text: str, errors: list[str]
) -> dict[str, list[str]]:
    """Read only the four semantic tail cells; deterministic join cells are ignored."""

    headers = [
        "Rendered reference ID", "Displayed label", "Affected Pair IDs",
        "Citation-ledger identity/source projection",
        "Bibliography-ledger canonical identity projection",
        "Version/record agreement (`agree` / `disagree` / `not verifiable`)",
        "Conflict class (`none` / `local` / `substantive`)",
        "Chair finding ID(s)", "Resolution (`closed` / `open`)",
    ]
    section = module.markdown_section_body_raw(
        text, "Mandatory citation cross-ledger consistency gate"
    ) or ""
    lines = section.splitlines()
    matches = [
        index for index, line in enumerate(lines)
        if module.parse_markdown_pipe_row(line) == headers
    ]
    if len(matches) != 1:
        errors.append(
            "90-chair-synthesis.md: expected exactly one citation cross-ledger table"
        )
        return {}
    start = matches[0]
    rows: dict[str, list[str]] = {}
    for line in lines[start + 2:]:
        cells = module.parse_markdown_pipe_row(line)
        if cells is None:
            break
        if len(cells) < len(headers):
            errors.append(
                "90-chair-synthesis.md: citation cross-ledger row has fewer than "
                "nine cells"
            )
            continue
        reference_id = cells[0]
        if reference_id in rows:
            errors.append(
                f"90-chair-synthesis.md: duplicate cross-ledger row {reference_id}"
            )
            continue
        rows[reference_id] = cells[-4:]
    return rows


def chair_cross_projection(
    module: Any,
    chair_text: str,
    bibliography_inventory: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    citation_inventory: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
    errors: list[str],
) -> tuple[list[str], list[list[str]], dict[str, int], str]:
    headers = [
        "Rendered reference ID", "Displayed label", "Affected Pair IDs",
        "Citation-ledger identity/source projection",
        "Bibliography-ledger canonical identity projection",
        "Version/record agreement (`agree` / `disagree` / `not verifiable`)",
        "Conflict class (`none` / `local` / `substantive`)",
        "Chair finding ID(s)", "Resolution (`closed` / `open`)",
    ]
    semantic = salvage_cross_ledger_semantics(module, chair_text, errors)
    reference_order = list(dict.fromkeys(
        row.get("DisplayedReferenceID", "") for row in citation_inventory
        if module.REFERENCE_ID_RE.fullmatch(row.get("DisplayedReferenceID", ""))
    ))
    if set(semantic) != set(reference_order):
        errors.append(
            "90-chair-synthesis.md: cross-ledger semantic row IDs must equal the "
            f"current cited-reference set; expected={reference_order}, "
            f"observed={list(semantic)}"
        )
    inventory_by_id = {
        row.get("ReferenceID", ""): row for row in bibliography_inventory
        if row.get("ReferenceID", "")
    }
    citation_by_ref: dict[str, list[dict[str, str]]] = {}
    for row in citation_ledger:
        citation_by_ref.setdefault(row.get("ReferenceID", ""), []).append(row)
    bibliography_by_key = {
        (row.get("ReferenceID", ""), row.get("Field", "")): row
        for row in bibliography_ledger
    }
    identity_fields = (
        "title", "ordered_authors", "year", "venue", "publication_status",
        "doi", "arxiv_id", "arxiv_version", "url",
        "isbn_or_other_persistent_id", "existence",
    )
    rendered: list[list[str]] = []
    counts = {
        "Unique cited rendered references joined": len(reference_order),
        "Identity-agreement count": 0,
        "Version disagreements": 0,
        "Local conflicts": 0,
        "Substantive conflicts": 0,
        "Reclassified Pair IDs": 0,
        "Unresolved conflicts": 0,
    }
    for reference_id in reference_order:
        source_rows = citation_by_ref.get(reference_id, [])
        inventory_row = inventory_by_id.get(reference_id)
        deterministic = [
            reference_id,
            module.displayed_label_for_reference_id(reference_id, inventory_by_id),
            ", ".join(row.get("PairID", "") for row in source_rows),
            " ; ".join(
                f"{row.get('PairID', '')}=>{row.get('PublicIdentifier', '')} @ "
                f"{row.get('ContentSourceOpened', '') or 'N/A'}"
                for row in source_rows
            ),
            (
                module.DANGLING_REFERENCE_SENTINEL
                if inventory_row is None else
                " ; ".join(
                    f"{field}="
                    f"{bibliography_by_key.get((reference_id, field), {}).get('CanonicalValue', '')}"
                    for field in identity_fields
                )
            ),
        ]
        tail = semantic.get(reference_id, ["", "", "", ""])
        logical = [*deterministic, *tail]
        rendered.append([
            module.markdown_projection_scalar(value) for value in logical
        ])
        agreement = tail[0].casefold()
        conflict = tail[1].casefold()
        resolution = tail[3].casefold()
        counts["Identity-agreement count"] += int(agreement == "agree")
        counts["Version disagreements"] += int(agreement == "disagree")
        counts["Local conflicts"] += int(conflict == "local")
        counts["Substantive conflicts"] += int(conflict == "substantive")
        if conflict != "none":
            counts["Reclassified Pair IDs"] += len(source_rows)
        counts["Unresolved conflicts"] += int(
            conflict != "none" and resolution == "open"
        )
    gate = "fail" if counts["Unresolved conflicts"] else "pass"
    return headers, rendered, counts, gate


def materialize_chair(
    module: Any,
    root: Path,
    process: dict[str, Any],
    errors: list[str],
) -> dict[Path, str]:
    reviewer_count = reviewer_count_for_process(process)
    needed = {
        "00-bibliography-inventory.csv", "00-citation-inventory.csv",
        "03-bibliography-audit-ledger.csv",
        "04-citation-claim-audit-ledger.csv", "05-ai-style-assessment.md",
        "90-chair-synthesis.md", "91-revision-ledger.md",
        "91-revision-ledger.csv", "91-ai-actionable-ledger.csv",
        "92-new-evidence-or-experiments.md",
        "92-new-evidence-or-experiments.csv",
        *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
    }
    for filename in sorted(needed):
        safe_regular_file(module, root / filename, errors)
    if errors:
        return {}
    bibliography_inventory = read_csv_exact(
        root / "00-bibliography-inventory.csv", module.BIB_INVENTORY_COLUMNS, errors
    )
    citation_inventory = read_csv_exact(
        root / "00-citation-inventory.csv", module.CITATION_INVENTORY_COLUMNS, errors
    )
    bibliography_ledger = read_csv_exact(
        root / "03-bibliography-audit-ledger.csv", module.BIB_LEDGER_COLUMNS, errors
    )
    citation_ledger = read_csv_exact(
        root / "04-citation-claim-audit-ledger.csv", module.CITATION_LEDGER_COLUMNS, errors
    )
    academic = read_csv_exact(
        root / "91-revision-ledger.csv", module.ACADEMIC_LEDGER_COLUMNS, errors,
        require_rows=False,
    )
    ai_rows = read_csv_exact(
        root / "91-ai-actionable-ledger.csv", module.AI_LEDGER_COLUMNS, errors,
        require_rows=False,
    )
    evidence = read_csv_exact(
        root / "92-new-evidence-or-experiments.csv", module.EVIDENCE_ITEM_COLUMNS,
        errors, require_rows=False,
    )
    if errors:
        return {}
    texts = {
        filename: (root / filename).read_text(encoding="utf-8")
        for filename in needed if filename.endswith(".md")
    }
    opened = module.canonical_stage_opened_inputs(process, reviewer_count, "C", root)
    allowed_endpoints = module.ordered_unique([
        *module.governing_rule_public_endpoint_sequence(process),
        *module.bibliography_ledger_public_endpoint_sequence(bibliography_ledger),
        *module.citation_ledger_public_endpoint_sequence(citation_ledger),
    ])
    selected_endpoints = selected_chair_endpoints(
        module,
        texts["90-chair-synthesis.md"],
        allowed_endpoints,
        set(module.governing_rule_public_endpoint_sequence(process)),
        errors,
    )
    if errors:
        return {}

    prepared: dict[Path, str] = {}
    filename = "91-revision-ledger.md"
    text = texts[filename]
    text = replace_exact_table(
        text, ACADEMIC_MD_HEADERS,
        module.render_markdown_pipe_table(
            ACADEMIC_MD_HEADERS, projected_rows(module, academic, ACADEMIC_MD_FIELDS)
        ),
        filename, errors,
    )
    text = replace_exact_table(
        text, AI_MD_HEADERS,
        module.render_markdown_pipe_table(
            AI_MD_HEADERS, projected_rows(module, ai_rows, AI_MD_FIELDS)
        ),
        filename, errors,
    )
    prepared[root / filename] = replace_actor_receipt(
        text, opened, selected_endpoints, filename, errors
    )

    filename = "92-new-evidence-or-experiments.md"
    text = texts[filename]
    open_rows = [
        row for row in academic
        if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
    ]
    wep_rows = [
        row for row in open_rows
        if row.get("Remedy", "").casefold() in {"w", "e", "p"}
    ]
    text = replace_exact_table(
        text, WEP_HEADERS,
        module.render_markdown_pipe_table(
            WEP_HEADERS, projected_rows(module, wep_rows, WEP_FIELDS)
        ),
        filename, errors,
    )
    text = replace_exact_table(
        text, EVIDENCE_MD_HEADERS,
        module.render_markdown_pipe_table(
            EVIDENCE_MD_HEADERS,
            projected_rows(module, evidence, module.EVIDENCE_ITEM_COLUMNS),
        ),
        filename, errors,
    )
    prepared[root / filename] = replace_actor_receipt(
        text, opened, selected_endpoints, filename, errors
    )

    filename = "90-chair-synthesis.md"
    text = texts[filename]
    text = replace_labeled_value(
        text, "Exact current-round input allowlist", "; ".join(opened), filename, errors
    )
    coverage_headers = [
        "Reviewer", "Gate A", "B", "C", "D", "E", "F", "G", "H", "I",
        "Whole-thesis rationale", "Audit duty complete", "Eligible for adjudication",
    ]
    coverage_rows: list[list[str]] = []
    verdict_headers = [
        "Reviewer", "Persona", "Category/grade", "Defense recommendation",
        "Decision regime/source", "Confidence", "Decisive reason",
    ]
    verdict_rows: list[list[str]] = []
    for index in range(1, reviewer_count + 1):
        actor = f"R{index}"
        report = module.markdown_visible_text(texts[f"{actor}-comprehensive-review.md"])
        assessment = module.markdown_section_body_raw(report, "Whole-thesis assessment") or ""
        gate_rows = module.parse_markdown_table_by_exact_headers(
            assessment, module.REVIEWER_ASSESSMENT_HEADERS,
            f"{actor}-comprehensive-review.md", errors, case_sensitive=True,
        ) or []
        dispositions = [row[2] for row in gate_rows if len(row) == 6]
        owns_audit = (
            reviewer_count == 5 and index in {4, 5}
        ) or (reviewer_count == 3 and index == 3)
        coverage_rows.append([
            actor, *dispositions, "complete", "yes" if owns_audit else "not assigned",
            "yes",
        ])
        projection = module.reviewer_verdict_projection(report)
        verdict_rows.append([
            actor, projection["persona"], projection["category"],
            projection["recommendation"], projection["regime_source"],
            projection["confidence"], projection["rationale"],
        ])
    text = replace_exact_table(
        text, coverage_headers,
        module.render_markdown_pipe_table(coverage_headers, coverage_rows),
        filename, errors,
    )
    text = replace_exact_table(
        text, verdict_headers,
        module.render_markdown_pipe_table(verdict_headers, verdict_rows),
        filename, errors,
    )
    categories: dict[str, int] = {}
    for row in verdict_rows:
        categories[row[2]] = categories.get(row[2], 0) + 1
    text = replace_labeled_value(
        text, "Category distribution",
        "; ".join(f"{key}={categories[key]}" for key in sorted(categories)),
        filename, errors,
    )
    text = replace_exact_table(
        text, CHAIR_FINDING_HEADERS,
        module.render_markdown_pipe_table(
            CHAIR_FINDING_HEADERS,
            projected_rows(module, academic, CHAIR_FINDING_FIELDS),
        ),
        filename, errors,
    )
    text = replace_exact_table(
        text, CHAIR_AI_HEADERS,
        module.render_markdown_pipe_table(
            CHAIR_AI_HEADERS, projected_rows(module, ai_rows, CHAIR_AI_FIELDS)
        ),
        filename, errors,
    )
    cross_headers, cross_rows, cross_counts, cross_gate = chair_cross_projection(
        module, text, bibliography_inventory, bibliography_ledger,
        citation_inventory, citation_ledger, errors,
    )
    text = replace_exact_table(
        text, cross_headers,
        module.render_markdown_pipe_table(cross_headers, cross_rows),
        filename, errors,
    )
    for label, value in cross_counts.items():
        text = replace_labeled_value(text, label, str(value), filename, errors)
    text = replace_labeled_value(
        text, "Combined citation gate", cross_gate, filename, errors
    )
    prepared[root / filename] = replace_actor_receipt(
        text, opened, selected_endpoints, filename, errors
    )
    return prepared


def build_summary_shell(
    module: Any,
    process: dict[str, Any],
    opened: list[str],
) -> str:
    """Build the complete deterministic Stage-S schema when no output exists."""

    prompt_map = process.get("actor_prompt_sha256", {})
    prompt_hash = prompt_map.get("S", "") if isinstance(prompt_map, dict) else ""
    pdf_hash = str(process.get("selected_pdf_sha256", "")).upper()
    opened_text = "; ".join(opened)
    receipt = (
        "received=[operational prompt]; "
        f"opened=[{opened_text}]; public_endpoints=[none]; "
        "no unlisted substantive assertion was received; "
        "no prohibited context/artifact was used; "
        "neighboring paths were not enumerated"
    )
    fresh = (
        "no inherited user/thread/task turns beyond system/developer "
        "instructions and the exact operational prompt"
    )
    table = module.render_markdown_pipe_table
    blocks = [
        "# Current-round user-facing review summary",
        "## Clean-room identity\n\n"
        "- Actor ID: S\n"
        f"- Review round ID: {process.get('round_id', '')}\n"
        f"- Review retry ID: {process.get('retry_id', '')}\n"
        "- Frozen PDF path and SHA-256: "
        f"file={process.get('frozen_pdf_file', '')} ; sha256={pdf_hash}\n"
        f"- Summary fresh-context declaration: {fresh}\n"
        f"- Exact current-round input allowlist: {opened_text}\n"
        f"- Operational prompt SHA-256: {prompt_hash}\n"
        f"- Summary input-receipt/access declaration: {receipt}\n"
        f"- Frozen PDF SHA-256 at start and end: {pdf_hash} / {pdf_hash}",
        "## Independent and overall conclusions\n\n"
        + table(CONCLUSION_HEADERS, []).rstrip("\n"),
        "## Current actionable items\n\n"
        + table(SUMMARY_ACADEMIC_HEADERS, []).rstrip("\n"),
        "## Current AI-style actionable items — separate from academic grading\n\n"
        + table(SUMMARY_AI_HEADERS, []).rstrip("\n"),
        "## Current new evidence or experiments (N)\n\n"
        + table(EVIDENCE_MD_HEADERS, []).rstrip("\n"),
        "## Optional suggestions\nnone",
        "## Unresolved questions\n\n"
        + table(DISAGREEMENT_HEADERS, []).rstrip("\n"),
        "## Review limitations\nnone",
        "## Reconciliation\n\n"
        "- Open required rows in 91-revision-ledger.csv: \n"
        "- Rows in 93-current-actionable-items.csv: \n"
        "- Rows in Current actionable items Markdown table: \n"
        "- Missing ledger IDs: \n"
        "- Extra summary IDs: \n"
        "- Duplicate IDs: \n"
        "- Open AI rows in 91-ai-actionable-ledger.csv: \n"
        "- Rows in 93-current-ai-actionable-items.csv: \n"
        "- Rows in Current AI-style actionable items Markdown table: \n"
        "- Missing/extra/duplicate AI finding IDs: \n"
        "- Rows in 92-new-evidence-or-experiments.csv: \n"
        "- Rows in Current new evidence or experiments Markdown table: \n"
        "- Missing/extra/duplicate evidence item IDs: \n"
        "- Statement: This summary introduces no new finding and uses no "
        "prior-round or author-side information.",
    ]
    return "\n\n".join(blocks) + "\n"


def materialize_summary(
    module: Any,
    root: Path,
    process: dict[str, Any],
    errors: list[str],
) -> dict[Path, str]:
    reviewer_count = reviewer_count_for_process(process)
    sources = {
        "05-ai-style-assessment.md", "90-chair-synthesis.md",
        "91-revision-ledger.md", "91-revision-ledger.csv",
        "91-ai-actionable-ledger.csv", "92-new-evidence-or-experiments.md",
        "92-new-evidence-or-experiments.csv",
        *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
    }
    stage_s_outputs = {
        "93-user-facing-summary.md", "93-current-actionable-items.csv",
        "93-current-ai-actionable-items.csv",
    }
    for filename in sorted(sources):
        safe_regular_file(module, root / filename, errors)
    output_exists: dict[str, bool] = {}
    for filename in sorted(stage_s_outputs):
        path = root / filename
        try:
            path.lstat()
        except FileNotFoundError:
            output_exists[filename] = False
        except OSError as exc:
            errors.append(f"cannot safely inspect owned projection {filename}: {exc}")
        else:
            output_exists[filename] = True
            safe_regular_file(module, path, errors)
    if errors:
        return {}
    academic = read_csv_exact(
        root / "91-revision-ledger.csv", module.ACADEMIC_LEDGER_COLUMNS, errors,
        require_rows=False,
    )
    ai_rows = read_csv_exact(
        root / "91-ai-actionable-ledger.csv", module.AI_LEDGER_COLUMNS, errors,
        require_rows=False,
    )
    evidence = read_csv_exact(
        root / "92-new-evidence-or-experiments.csv", module.EVIDENCE_ITEM_COLUMNS,
        errors, require_rows=False,
    )
    if errors:
        return {}
    open_academic = [
        row for row in academic
        if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
    ]
    open_ai = [
        row for row in ai_rows
        if row.get("Status", "").casefold() not in module.CLOSED_STATUSES
    ]
    texts = {
        filename: (root / filename).read_text(encoding="utf-8")
        for filename in sources if filename.endswith(".md")
    }
    opened = module.canonical_stage_opened_inputs(process, reviewer_count, "S", root)
    filename = "93-user-facing-summary.md"
    if output_exists[filename]:
        text = (root / filename).read_text(encoding="utf-8")
    else:
        text = build_summary_shell(module, process, opened)
    text = replace_labeled_value(
        text, "Exact current-round input allowlist", "; ".join(opened), filename, errors
    )
    text = replace_actor_receipt(text, opened, [], filename, errors)

    conclusion_rows: list[list[str]] = []
    for index in range(1, reviewer_count + 1):
        actor = f"R{index}"
        report = module.markdown_visible_text(texts[f"{actor}-comprehensive-review.md"])
        projection = module.reviewer_verdict_projection(report)
        conclusion_rows.append([
            actor, projection["persona"], projection["category"],
            projection["recommendation"], projection["regime_source"],
            projection["confidence"], projection["rationale"],
        ])
    ai_report = module.markdown_visible_text(texts["05-ai-style-assessment.md"])
    ai_judgment = module.markdown_section_body_raw(ai_report, "Overall judgment") or ""
    conclusion_rows.append([
        "AI", "standalone AI-style assessment",
        module.labeled_value(ai_judgment, "AI-style signal") or "", "N/A", "N/A",
        module.labeled_value(ai_judgment, "Confidence") or "",
        module.labeled_value(ai_judgment, "Rationale") or "",
    ])
    chair = module.markdown_visible_text(texts["90-chair-synthesis.md"])
    chair_projection = module.chair_verdict_projection(chair)
    conclusion_rows.append([
        "Chair", "chair adjudication", chair_projection["category"],
        chair_projection["recommendation"], chair_projection["regime_source"],
        chair_projection["confidence"], chair_projection["rationale"],
    ])
    text = replace_exact_table(
        text, CONCLUSION_HEADERS,
        module.render_markdown_pipe_table(CONCLUSION_HEADERS, conclusion_rows),
        filename, errors,
    )
    text = replace_exact_table(
        text, SUMMARY_ACADEMIC_HEADERS,
        module.render_markdown_pipe_table(
            SUMMARY_ACADEMIC_HEADERS,
            projected_rows(module, open_academic, module.ACADEMIC_SUMMARY_COLUMNS),
        ),
        filename, errors,
    )
    text = replace_exact_table(
        text, SUMMARY_AI_HEADERS,
        module.render_markdown_pipe_table(
            SUMMARY_AI_HEADERS,
            projected_rows(module, open_ai, module.AI_SUMMARY_COLUMNS),
        ),
        filename, errors,
    )
    text = replace_exact_table(
        text, EVIDENCE_MD_HEADERS,
        module.render_markdown_pipe_table(
            EVIDENCE_MD_HEADERS,
            projected_rows(module, evidence, module.EVIDENCE_ITEM_COLUMNS),
        ),
        filename, errors,
    )
    disagreement_rows = table_rows_from_section(
        module, chair, "Disagreements and chair decisions",
        DISAGREEMENT_HEADERS, "90-chair-synthesis.md", errors,
    )
    unresolved = [
        row for row in disagreement_rows
        if len(row) == len(DISAGREEMENT_HEADERS)
        and row[5].casefold() in {"unresolved", "not verifiable", "disputed"}
    ]
    text = replace_exact_table(
        text, DISAGREEMENT_HEADERS,
        module.render_markdown_pipe_table(DISAGREEMENT_HEADERS, unresolved),
        filename, errors,
    )
    for heading in ("Optional suggestions", "Review limitations"):
        body = module.markdown_section_body(chair, heading)
        if body is None:
            errors.append(f"90-chair-synthesis.md: missing section {heading!r}")
            body = ""
        text = replace_section_body(text, heading, body, filename, errors)
    counts = {
        "Open required rows in 91-revision-ledger.csv": len(open_academic),
        "Rows in 93-current-actionable-items.csv": len(open_academic),
        "Rows in Current actionable items Markdown table": len(open_academic),
        "Missing ledger IDs": "none",
        "Extra summary IDs": "none",
        "Duplicate IDs": "none",
        "Open AI rows in 91-ai-actionable-ledger.csv": len(open_ai),
        "Rows in 93-current-ai-actionable-items.csv": len(open_ai),
        "Rows in Current AI-style actionable items Markdown table": len(open_ai),
        "Missing/extra/duplicate AI finding IDs": "none",
        "Rows in 92-new-evidence-or-experiments.csv": len(evidence),
        "Rows in Current new evidence or experiments Markdown table": len(evidence),
        "Missing/extra/duplicate evidence item IDs": "none",
        "Statement": (
            "This summary introduces no new finding and uses no prior-round or "
            "author-side information."
        ),
    }
    for label, value in counts.items():
        text = replace_labeled_value(text, label, str(value), filename, errors)
    return {
        root / filename: text,
        root / "93-current-actionable-items.csv": render_csv_text(
            module.ACADEMIC_SUMMARY_COLUMNS, open_academic
        ),
        root / "93-current-ai-actionable-items.csv": render_csv_text(
            module.AI_SUMMARY_COLUMNS, open_ai
        ),
    }


def materialize(root: Path, actor_id: str) -> list[str]:
    module = load_validator_cached()
    errors: list[str] = []
    if module.is_link_or_reparse(root) or not root.is_dir():
        return ["round root must be an existing non-aliased directory"]
    process_path = root / "00-process-parameters.json"
    if not safe_regular_file(module, process_path, errors):
        return errors
    try:
        process = json.loads(process_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read 00-process-parameters.json: {exc}"]
    if not isinstance(process, dict):
        return ["00-process-parameters.json root must be an object"]
    contract = role_contract(process, actor_id)
    if contract is None:
        return [
            "materializer supports only doctoral R4/R5, master's R3, Chair C, "
            "or Stage S, "
            f"not degree={process.get('degree_level')!r} actor={actor_id!r}"
        ]

    if "chair" in contract:
        prepared = materialize_chair(module, root, process, errors)
        if errors:
            return errors
        for path, text in prepared.items():
            write_error = atomic_replace_text(module, path, text)
            if write_error:
                return [write_error]
        return []
    if "summary" in contract:
        prepared = materialize_summary(module, root, process, errors)
        if errors:
            return errors
        for path, text in prepared.items():
            write_error = atomic_replace_text(
                module, path, text, allow_create=True
            )
            if write_error:
                return [write_error]
        return []

    needed: set[str] = {f"{actor_id}-comprehensive-review.md"}
    if "02" in contract:
        needed |= {"02-page-layout-ledger.csv", "02-page-layout-ledger.md"}
    if "03" in contract:
        needed |= {
            "00-bibliography-inventory.csv",
            "03-bibliography-audit-ledger.csv",
            "03-bibliography-audit-ledger.md",
        }
    if "04" in contract:
        needed |= {
            "00-bibliography-inventory.csv",
            "04-citation-claim-audit-ledger.csv",
            "04-citation-claim-audit-ledger.md",
        }
    for filename in sorted(needed):
        safe_regular_file(module, root / filename, errors)
    if errors:
        return errors

    page_rows: list[dict[str, str]] = []
    bib_inventory: list[dict[str, str]] = []
    bib_rows: list[dict[str, str]] = []
    citation_rows: list[dict[str, str]] = []
    if "02" in contract:
        page_rows = read_csv_exact(
            root / "02-page-layout-ledger.csv", module.PAGE_LEDGER_COLUMNS, errors
        )
    if "03" in contract:
        bib_inventory = read_csv_exact(
            root / "00-bibliography-inventory.csv",
            module.BIB_INVENTORY_COLUMNS,
            errors,
        )
        bib_rows = read_csv_exact(
            root / "03-bibliography-audit-ledger.csv",
            module.BIB_LEDGER_COLUMNS,
            errors,
        )
    elif "04" in contract:
        bib_inventory = read_csv_exact(
            root / "00-bibliography-inventory.csv",
            module.BIB_INVENTORY_COLUMNS,
            errors,
        )
    if "04" in contract:
        citation_rows = read_csv_exact(
            root / "04-citation-claim-audit-ledger.csv",
            module.CITATION_LEDGER_COLUMNS,
            errors,
        )
    if errors:
        return errors

    rule_endpoints = module.governing_rule_public_endpoint_sequence(process)
    bib_endpoints = module.bibliography_ledger_public_endpoint_sequence(bib_rows)
    citation_endpoints = module.citation_ledger_public_endpoint_sequence(
        citation_rows
    )
    prepared: dict[Path, str] = {}

    def load_owned(filename: str) -> str:
        path = root / filename
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read owned Markdown {filename}: {exc}")
            return ""

    if "02" in contract:
        filename = "02-page-layout-ledger.md"
        text = load_owned(filename)
        table = module.render_markdown_pipe_table(
            module.PAGE_MARKDOWN_HEADERS,
            module.page_markdown_projection_rows(page_rows),
        )
        text = replace_exact_table(
            text, module.PAGE_MARKDOWN_HEADERS, table, filename, errors
        )
        prepared[root / filename] = replace_receipt_endpoints(
            text, [*rule_endpoints, *bib_endpoints], filename, errors
        )
    if "03" in contract:
        filename = "03-bibliography-audit-ledger.md"
        text = load_owned(filename)
        table = module.render_markdown_pipe_table(
            module.BIB_MARKDOWN_HEADERS,
            module.bibliography_markdown_projection_rows(bib_inventory, bib_rows),
        )
        text = replace_exact_table(
            text, module.BIB_MARKDOWN_HEADERS, table, filename, errors
        )
        prepared[root / filename] = replace_receipt_endpoints(
            text, [*rule_endpoints, *bib_endpoints], filename, errors
        )
    if "04" in contract:
        filename = "04-citation-claim-audit-ledger.md"
        text = load_owned(filename)
        bibliography_by_id = {
            row.get("ReferenceID", ""): row
            for row in bib_inventory
            if row.get("ReferenceID", "")
        }
        table = module.render_markdown_pipe_table(
            module.CITATION_MARKDOWN_HEADERS,
            module.citation_markdown_projection_rows(
                citation_rows, bibliography_by_id
            ),
        )
        text = replace_exact_table(
            text, module.CITATION_MARKDOWN_HEADERS, table, filename, errors
        )
        prepared[root / filename] = replace_receipt_endpoints(
            text, [*rule_endpoints, *citation_endpoints], filename, errors
        )

    report_name = f"{actor_id}-comprehensive-review.md"
    report_endpoints = [*rule_endpoints]
    if "03" in contract:
        report_endpoints.extend(bib_endpoints)
    if "04" in contract:
        report_endpoints.extend(citation_endpoints)
    prepared[root / report_name] = replace_receipt_endpoints(
        load_owned(report_name), report_endpoints, report_name, errors
    )
    if errors:
        return errors

    for path, text in prepared.items():
        write_error = atomic_replace_text(module, path, text)
        if write_error:
            errors.append(write_error)
            break
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round_root", type=Path)
    parser.add_argument("actor_id", choices=("R3", "R4", "R5", "C", "S"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = materialize(args.round_root.absolute(), args.actor_id)
    if errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("MATERIALIZED")
    print(
        "Owned deterministic projections and receipt lists were rebuilt from "
        "the current actor's closed authoritative inputs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
