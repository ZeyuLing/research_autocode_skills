#!/usr/bin/env python3
"""Validate idea2paper project structure, traceability, figures, and readiness."""

from __future__ import annotations

import argparse
import binascii
import csv
import difflib
import hashlib
import json
import math
import re
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compile_paper import (
    CORE_BUILD_ARTIFACTS,
    MATERIAL_OVERFULL_PT,
    MEDIA_BOX_OVERFLOW_PT,
    aux_label_page,
    aux_label_record,
    body_float_inventory,
    body_float_tail_report,
    document_column_mode_audit,
    float_distribution_audit,
    latex_overfull_boxes,
    manual_pagination_commands,
    rendered_media_box_overflows,
    rendered_whitespace_audit,
    source_tree_sha256,
    teaser_placement_audit,
    tex_fuzz_register_uses,
)
from record_survey_run import CSV_REQUIRED as SURVEY_CSV_REQUIRED
from record_survey_run import STANDARD_ARTIFACTS as SURVEY_STANDARD_ARTIFACTS
from select_venue import SELECTION_RULE, TIER_RANK, evaluate as evaluate_venue
from select_venue import load_candidates, load_registry, parse_datetime
from state_manager import snapshot_inputs
from todo_lint import INCLUDE_RE, MACRO_RE, lint_directory, strip_tex_comments


STAGES = [
    "INTAKE",
    "VENUE_LOCKED",
    "RESOURCES_READY",
    "LITERATURE_AUDITED",
    "IDEA_REVIEWED",
    "IDEA_FROZEN",
    "CLAIM_GRAPH_FROZEN",
    "METHOD_EXPERIMENT_READY",
    "TITLE_FROZEN",
    "MANUSCRIPT_DRAFTED",
    "SKETCH_COMPLETE",
    "RESULTS_INTEGRATED",
    "SUBMISSION_READY",
]

REQUIRED_STRUCTURE = [
    "project.json",
    "resources.json",
    "state.json",
    "venue/decision.json",
    "venue/candidates.json",
    "idea/versions/idea_v0.md",
    "title/brief.json",
    "title/candidates.json",
    "title/decision.json",
    "title/history.jsonl",
    "method/method_spec.md",
    "experiments/plan.md",
    "experiments/claim_experiment_matrix.csv",
    "experiments/baseline_provenance.csv",
    "figures/manifest.csv",
    "paper/main.tex",
    "paper/title.tex",
    "paper/idea2paper-draft.sty",
    "paper/references.bib",
    "qa/todo_registry.json",
]

SURVEY_FILES = [
    "00_scope.md",
    "01_query_plan.md",
    "source_ledger.csv",
    "papers_raw.csv",
    "papers_merged.csv",
    "papers_enriched.csv",
    "screening.csv",
    "snowball_log.csv",
    "reading_matrix.csv",
    "coverage_audit.md",
    "synthesis_outline.md",
    "survey_receipt.json",
    "survey_skill_snapshot.md",
    "survey_run.json",
]

ENRICHED_REQUIRED = {
    "record_id",
    "title",
    "tier",
    "stable_id",
    "bib_key",
    "publication_status",
    "status_venue",
    "status_year",
    "status_evidence_url",
    "status_checked_at",
    "paper_access_status",
    "local_pdf_path",
    "official_code_status",
    "code_url",
    "code_license",
    "data_status",
    "data_url",
    "weights_status",
    "weights_url",
    "discovery_idea_version",
    "local_record_path",
}

PUBLICATION_STATUSES = {
    "accepted",
    "published",
    "preprint_only",
    "under_review",
    "withdrawn",
    "retracted",
    "rejected",
    "unknown",
}
PAPER_ACCESS_STATUSES = {"open_pdf", "open_html", "metadata_only", "unknown"}
ARTIFACT_STATUSES = {"available", "announced", "none_found", "unknown"}
TITLE_SCORE_FIELDS = {
    "faithfulness",
    "specificity",
    "novelty_signal",
    "clarity",
    "memorability",
    "search_distinctiveness",
    "venue_fit",
}

CLAIM_REQUIRED = [
    "claim_id",
    "limitation",
    "evidence_ids",
    "contribution_id",
    "contribution",
    "method_component",
    "hypothesis",
    "experiment_id",
    "datasets",
    "baselines",
    "metric",
    "figure_or_table",
    "manuscript_locations",
    "status",
]

BASELINE_REQUIRED = {
    "baseline_id",
    "paper_id",
    "method",
    "source_table",
    "dataset_version",
    "split",
    "training_data",
    "backbone",
    "preprocessing",
    "metric_definition",
    "test_setting",
    "reported_value",
    "directly_comparable",
    "notes",
}

FIGURE_REQUIRED = [
    "figure_id",
    "type",
    "claim_ids",
    "module_ids",
    "result_ids",
    "backend",
    "mode",
    "prompt_path",
    "input_paths",
    "generated_path",
    "paper_path",
    "version",
    "status",
    "qa_path",
    "provenance_path",
    "output_sha256",
]

CORE_COMPOSITION_FIGURE_TYPES = {"teaser", "overview", "pipeline", "method-overview"}
CORE_PROMPT_FIELDS = (
    "Figure role:",
    "10-second message:",
    "Paper claim:",
    "Final-size target:",
    "Reference synthesis:",
    "Composition grammar:",
    "Reading order:",
    "Novelty emphasis:",
    "Color semantics:",
    "Text budget:",
    "Domain visual evidence:",
    "Generic-box area budget:",
    "Three-glance hierarchy:",
    "Composition archetypes evaluated:",
    "Hard vetoes:",
)
CORE_QA_GATES = (
    "Faithfulness",
    "Conciseness",
    "Readability",
    "Aesthetics",
    "Domain evidence",
    "Non-generic composition",
    "Three-glance hierarchy",
    "Novelty salience",
    "Rectangular efficiency",
    "Final-size inspection",
)


def read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path}: expected a JSON object")
        return {}
    return data


def read_csv(path: Path, errors: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except OSError as exc:
        errors.append(f"{path}: cannot read CSV: {exc}")
        return [], []


def non_comment_content(path: Path) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("%") and not re.fullmatch(r"\\section\{[^}]+\}", stripped):
            return True
    return False


def resolve_project_path(project: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else project / candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_draft_marker(source: str, macro_name: str, item_id: str) -> bool:
    """Return whether an active, possibly multiline tracked macro has the requested ID."""
    cleaned = strip_tex_comments(source)
    return any(
        match.group(1) == macro_name and match.group(2).strip() == item_id
        for match in MACRO_RE.finditer(cleaned)
    )


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def paper_title_tex(path: Path) -> str | None:
    r"""Extract the balanced body of \newcommand{\papertitle}{...}."""
    text = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
    marker = re.search(r"\\newcommand\s*\{\\papertitle\}\s*", text)
    if not marker:
        return None
    start = text.find("{", marker.end())
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character not in "{}":
            continue
        preceding = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == "\\":
            preceding += 1
            cursor -= 1
        if preceding % 2:
            continue
        depth += 1 if character == "{" else -1
        if depth == 0:
            return text[start + 1 : index].strip()
    return None


def timezone_aware(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_png(path: Path) -> tuple[int | None, int | None, str | None]:
    if path.suffix.lower() != ".png":
        return None, None, "paper figures must be PNG raster files"
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, None, "invalid PNG signature"
    offset = 8
    width: int | None = None
    height: int | None = None
    idat = bytearray()
    saw_iend = False
    try:
        while offset < len(data):
            if offset + 12 > len(data):
                return width, height, "truncated PNG chunk"
            length = struct.unpack(">I", data[offset : offset + 4])[0]
            chunk_type = data[offset + 4 : offset + 8]
            chunk_data = data[offset + 8 : offset + 8 + length]
            crc_start = offset + 8 + length
            if crc_start + 4 > len(data):
                return width, height, "truncated PNG data"
            expected_crc = struct.unpack(">I", data[crc_start : crc_start + 4])[0]
            actual_crc = binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                return width, height, f"PNG CRC mismatch in {chunk_type.decode('ascii', errors='replace')}"
            if chunk_type == b"IHDR":
                if length != 13:
                    return width, height, "invalid PNG IHDR"
                width, height = struct.unpack(">II", chunk_data[:8])
            elif chunk_type == b"IDAT":
                idat.extend(chunk_data)
            elif chunk_type == b"IEND":
                saw_iend = True
                break
            offset = crc_start + 4
    except (OSError, struct.error):
        return width, height, "malformed PNG"
    if width is None or height is None or width < 128 or height < 128:
        return width, height, "PNG dimensions must be at least 128x128"
    if not idat or not saw_iend:
        return width, height, "PNG is missing IDAT or IEND"
    try:
        zlib.decompress(bytes(idat))
    except zlib.error:
        return width, height, "PNG image data cannot be decompressed"
    return width, height, None


def validate_claims(project: Path, errors: list[str]) -> None:
    path = project / "experiments/claim_experiment_matrix.csv"
    fields, rows = read_csv(path, errors)
    missing_fields = [field for field in CLAIM_REQUIRED if field not in fields]
    if missing_fields:
        errors.append(f"{path}: missing columns {missing_fields}")
        return
    if not rows:
        errors.append(f"{path}: no claim/experiment rows")
        return
    seen_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=2):
        for field in CLAIM_REQUIRED:
            if not row.get(field, "").strip():
                errors.append(f"{path}:{index}: empty required field {field}")
        claim_id = row.get("claim_id", "").strip()
        experiment_id = row.get("experiment_id", "").strip()
        pair = (claim_id, experiment_id)
        if claim_id and experiment_id and pair in seen_pairs:
            errors.append(f"{path}:{index}: duplicate claim/experiment pair {claim_id}/{experiment_id}")
        seen_pairs.add(pair)

    decisions = sorted((project / "idea/meetings").glob("round_*/decision.json"))
    if decisions:
        final_decision = read_json(decisions[-1], errors)
        contribution_records = final_decision.get("contributions")
        if isinstance(contribution_records, list):
            matrix_contribution_ids = {row.get("contribution_id", "").strip() for row in rows}
            for contribution in contribution_records:
                if isinstance(contribution, dict) and contribution.get("contribution_id") not in matrix_contribution_ids:
                    errors.append(
                        f"{path}: Professor contribution is absent from claim matrix: "
                        f"{contribution.get('contribution_id')}"
                    )


def validate_design(project: Path, errors: list[str]) -> None:
    for relative in ("method/method_spec.md", "experiments/plan.md"):
        path = project / relative
        if not path.exists() or len(path.read_text(encoding="utf-8", errors="replace").strip()) < 200:
            errors.append(f"{path}: design artifact is not substantive")

    baseline_path = project / "experiments/baseline_provenance.csv"
    fields, rows = read_csv(baseline_path, errors)
    missing = sorted(BASELINE_REQUIRED - set(fields))
    if missing:
        errors.append(f"{baseline_path}: missing columns {missing}")
        return
    if not rows:
        errors.append(f"{baseline_path}: no baseline records")
        return
    baseline_ids: set[str] = set()
    protocol_fields = (
        "paper_id",
        "source_table",
        "dataset_version",
        "split",
        "training_data",
        "backbone",
        "preprocessing",
        "metric_definition",
        "test_setting",
    )
    for index, row in enumerate(rows, start=2):
        baseline_id = row.get("baseline_id", "").strip()
        if not baseline_id or baseline_id in baseline_ids:
            errors.append(f"{baseline_path}:{index}: baseline_id must be non-empty and unique")
        baseline_ids.add(baseline_id)
        if not row.get("method", "").strip():
            errors.append(f"{baseline_path}:{index}: empty method")
        comparable = row.get("directly_comparable", "").strip().lower()
        if comparable not in {"yes", "no"}:
            errors.append(f"{baseline_path}:{index}: directly_comparable must be yes or no")
        if row.get("reported_value", "").strip() or comparable == "yes":
            for field in protocol_fields:
                if not row.get(field, "").strip():
                    errors.append(f"{baseline_path}:{index}: copied/comparable result lacks {field}")

    claim_path = project / "experiments/claim_experiment_matrix.csv"
    _, claims = read_csv(claim_path, errors)
    for index, claim in enumerate(claims, start=2):
        for baseline_id in [
            item.strip() for item in claim.get("baselines", "").split(";") if item.strip()
        ]:
            if baseline_id not in baseline_ids:
                errors.append(f"{claim_path}:{index}: unknown baseline ID {baseline_id}")


def validate_title(
    project: Path,
    project_data: dict[str, Any],
    venue: dict[str, Any],
    errors: list[str],
) -> None:
    brief_path = project / "title/brief.json"
    candidates_path = project / "title/candidates.json"
    decision_path = project / "title/decision.json"
    title_tex_path = project / "paper/title.tex"
    brief = read_json(brief_path, errors)
    candidate_data = read_json(candidates_path, errors)
    decision = read_json(decision_path, errors)

    idea_version = project_data.get("idea_version")
    selected_venue = venue.get("selected") if isinstance(venue.get("selected"), dict) else {}
    venue_name = selected_venue.get("name")
    venue_edition = str(selected_venue.get("edition", ""))

    if brief.get("status") != "ready":
        errors.append("title/brief.json: status must be ready")
    if brief.get("idea_version") != idea_version:
        errors.append("title/brief.json: idea version is stale")
    if brief.get("project_directory_is_not_title") is not True:
        errors.append("title/brief.json: project_directory_is_not_title must be true")
    if brief.get("project_label") != project.name:
        errors.append("title/brief.json: project_label must record the directory label")
    for field in ("required_concepts", "forbidden_claims"):
        if not isinstance(brief.get(field), list):
            errors.append(f"title/brief.json: {field} must be a list")

    if candidate_data.get("status") != "reviewed":
        errors.append("title/candidates.json: status must be reviewed")
    if candidate_data.get("idea_version") != idea_version:
        errors.append("title/candidates.json: idea version is stale")
    if candidate_data.get("venue_name") != venue_name or str(candidate_data.get("venue_edition", "")) != venue_edition:
        errors.append("title/candidates.json: venue binding is stale")
    if not timezone_aware(str(candidate_data.get("generated_at", ""))):
        errors.append("title/candidates.json: generated_at must be timezone-aware")

    _, matrix_rows = read_csv(project / "experiments/claim_experiment_matrix.csv", errors)
    claim_ids = {row.get("claim_id", "").strip() for row in matrix_rows if row.get("claim_id", "").strip()}
    contribution_ids = {
        row.get("contribution_id", "").strip() for row in matrix_rows if row.get("contribution_id", "").strip()
    }
    component_ids = {
        row.get("method_component", "").strip() for row in matrix_rows if row.get("method_component", "").strip()
    }
    _, terminology_rows = read_csv(project / "idea/terminology.csv", errors)
    terms = {row.get("term", "").strip().casefold() for row in terminology_rows if row.get("term", "").strip()}

    candidates = candidate_data.get("candidates")
    if not isinstance(candidates, list) or not 8 <= len(candidates) <= 12:
        errors.append("title/candidates.json: require 8--12 title candidates")
        candidates = []
    by_id: dict[str, dict[str, Any]] = {}
    normalized_titles: set[str] = set()
    families: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            errors.append(f"title/candidates.json: candidate {index} must be an object")
            continue
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        title = str(candidate.get("title", "")).strip()
        family = str(candidate.get("framing_family", "")).strip()
        if not candidate_id or candidate_id in by_id:
            errors.append(f"title/candidates.json: candidate {index} has a missing or duplicate candidate_id")
        else:
            by_id[candidate_id] = candidate
        normalized = normalize_title(title)
        if not normalized or normalized in normalized_titles:
            errors.append(f"title/candidates.json: candidate {candidate_id or index} has an empty or duplicate title")
        normalized_titles.add(normalized)
        if family:
            families.add(family)
        if not str(candidate.get("rationale", "")).strip():
            errors.append(f"title/candidates.json: {candidate_id} lacks rationale")
        scores = candidate.get("scores")
        if not isinstance(scores, dict) or set(scores) != TITLE_SCORE_FIELDS:
            errors.append(f"title/candidates.json: {candidate_id} has incomplete score fields")
        else:
            for field, value in scores.items():
                if not isinstance(value, int) or not 1 <= value <= 5:
                    errors.append(f"title/candidates.json: {candidate_id} score {field} must be an integer from 1 to 5")
        risk = candidate.get("overclaim_risk")
        if not isinstance(risk, int) or not 1 <= risk <= 5:
            errors.append(f"title/candidates.json: {candidate_id} overclaim_risk must be an integer from 1 to 5")
        mappings = (
            ("claim_ids", claim_ids),
            ("contribution_ids", contribution_ids),
            ("method_component_ids", component_ids),
        )
        for field, known in mappings:
            values = candidate.get(field)
            if not isinstance(values, list) or not values:
                errors.append(f"title/candidates.json: {candidate_id} requires non-empty {field}")
            elif any(value not in known for value in values):
                errors.append(f"title/candidates.json: {candidate_id} contains unknown {field}")
        candidate_terms = candidate.get("terms")
        if not isinstance(candidate_terms, list) or not candidate_terms:
            errors.append(f"title/candidates.json: {candidate_id} requires terminology bindings")
        elif any(str(term).casefold() not in terms for term in candidate_terms):
            errors.append(f"title/candidates.json: {candidate_id} contains unknown terminology")
    if len(families) < 3:
        errors.append("title/candidates.json: candidates must span at least three framing families")

    if decision.get("status") != "frozen":
        errors.append("title/decision.json: status must be frozen")
    if not re.fullmatch(r"title_v[1-9][0-9]*", str(decision.get("title_version", ""))):
        errors.append("title/decision.json: title_version must look like title_v1")
    if decision.get("idea_version") != idea_version:
        errors.append("title/decision.json: idea version is stale")
    if decision.get("venue_name") != venue_name or str(decision.get("venue_edition", "")) != venue_edition:
        errors.append("title/decision.json: venue binding is stale")
    if not timezone_aware(str(decision.get("frozen_at", ""))):
        errors.append("title/decision.json: frozen_at must be timezone-aware")
    if not str(decision.get("selection_rationale", "")).strip():
        errors.append("title/decision.json: selection_rationale is required")
    if decision.get("unresolved_risks") != []:
        errors.append("title/decision.json: unresolved_risks must be an empty list")

    shortlist = decision.get("shortlist")
    if not isinstance(shortlist, list) or len(set(shortlist)) < 3:
        errors.append("title/decision.json: shortlist must contain at least three distinct candidate IDs")
        shortlist = []
    elif any(candidate_id not in by_id for candidate_id in shortlist):
        errors.append("title/decision.json: shortlist contains an unknown candidate ID")
    selected_id = str(decision.get("selected_candidate_id", ""))
    selected_candidate = by_id.get(selected_id)
    selected_title = str(decision.get("selected_title", "")).strip()
    if not selected_candidate:
        errors.append("title/decision.json: selected candidate does not exist")
    else:
        if selected_id not in shortlist:
            errors.append("title/decision.json: selected candidate is absent from shortlist")
        if selected_title != str(selected_candidate.get("title", "")).strip():
            errors.append("title/decision.json: selected title does not match its candidate")
        if selected_candidate.get("overclaim_risk", 5) > 2:
            errors.append("title/decision.json: selected title has unresolved overclaim risk")
        if selected_candidate.get("risk_flags") not in ([], None):
            errors.append("title/decision.json: selected title retains risk flags")

    reviewers = decision.get("reviews")
    review_roles = set()
    if isinstance(reviewers, list):
        for review in reviewers:
            if isinstance(review, dict) and review.get("verdict") == "pass" and str(review.get("notes", "")).strip():
                review_roles.add(review.get("role"))
    if not {"positioning", "clarity_faithfulness"}.issubset(review_roles):
        errors.append("title/decision.json: both independent title reviews must pass with notes")

    input_versions = decision.get("input_versions") if isinstance(decision.get("input_versions"), dict) else {}
    if input_versions.get("idea_version") != idea_version:
        errors.append("title/decision.json: input_versions.idea_version is stale")
    hash_inputs = {
        "literature_sha256": project / "related_works/papers_enriched.csv",
        "claim_graph_sha256": project / "experiments/claim_experiment_matrix.csv",
        "terminology_sha256": project / "idea/terminology.csv",
        "method_spec_sha256": project / "method/method_spec.md",
        "venue_decision_sha256": project / "venue/decision.json",
    }
    for field, path in hash_inputs.items():
        if not path.is_file() or input_versions.get(field) != sha256_file(path):
            errors.append(f"title/decision.json: stale or missing input hash {field}")

    collision = decision.get("collision_check") if isinstance(decision.get("collision_check"), dict) else {}
    corpus_path = project / "related_works/papers_enriched.csv"
    if not timezone_aware(str(collision.get("checked_at", ""))):
        errors.append("title/decision.json: collision_check.checked_at must be timezone-aware")
    if not corpus_path.is_file() or collision.get("corpus_sha256") != sha256_file(corpus_path):
        errors.append("title/decision.json: collision_check corpus hash is stale")
    if collision.get("exact_match") is not False or not isinstance(collision.get("reviewed_conflicts"), list):
        errors.append("title/decision.json: collision_check must record no exact match and reviewed conflicts")

    selected_normalized = normalize_title(selected_title)
    forbidden_labels = {
        normalize_title(project.name),
        normalize_title(str(project_data.get("project_id", ""))),
        normalize_title("Working Title Pending"),
        normalize_title(str(project_data.get("idea_original", ""))[:120]),
    }
    if not selected_normalized or selected_normalized in forbidden_labels:
        errors.append("title/decision.json: selected title is a project label, idea truncation, or placeholder")
    if re.search(r"\\(?:PredResult|PredClaim|DraftChoice|QualPlaceholder|TemplateTODO)\b", selected_title):
        errors.append("title/decision.json: draft macros are forbidden in the paper title")
    if re.search(r"(?:\b\d+(?:\.\d+)?%|\b\d+\.\d+\b)", selected_title):
        errors.append("title/decision.json: predicted numeric claims are forbidden in the paper title")

    if corpus_path.is_file() and selected_normalized:
        _, corpus_rows = read_csv(corpus_path, errors)
        for row in corpus_rows:
            prior_title = str(row.get("title", "")).strip()
            prior_normalized = normalize_title(prior_title)
            if not prior_normalized:
                continue
            similarity = difflib.SequenceMatcher(None, selected_normalized, prior_normalized).ratio()
            if selected_normalized == prior_normalized or similarity >= 0.94:
                errors.append(f"title/decision.json: selected title collides with prior work {prior_title!r}")
                break

    latex_title = paper_title_tex(title_tex_path)
    if latex_title is None:
        errors.append("paper/title.tex: missing balanced \\newcommand{\\papertitle}{...}")
    elif latex_title != latex_escape(selected_title):
        errors.append("paper/title.tex: title does not match the frozen title decision")
    main_source = strip_tex_comments((project / "paper/main.tex").read_text(encoding="utf-8", errors="replace"))
    if not re.search(r"\\input\s*\{title\}", main_source) or not re.search(
        r"\\title\s*\{\s*\\papertitle\s*\}", main_source
    ):
        errors.append("paper/main.tex: active template must consume paper/title.tex through \\papertitle")


def validate_selection_binding(
    project_data: dict[str, Any],
    venue: dict[str, Any],
    selected: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """Bind the decision mode and selected venue to the immutable intake choice."""

    target = str(project_data.get("target_venue", "")).strip()
    project_mode = str(project_data.get("venue_selection_mode", "")).strip()
    decision_mode = str(venue.get("selection_mode", "")).strip()
    if not target:
        errors.append("project.json: target_venue is required")
        return

    expected_mode = "auto" if target.casefold() == "auto" else "user_specified"
    if project_mode != expected_mode:
        errors.append(
            "project.json: venue_selection_mode does not match target_venue "
            f"(expected {expected_mode})"
        )
    if decision_mode != expected_mode:
        errors.append(
            "venue/decision.json: selection_mode does not match project target_venue "
            f"(expected {expected_mode})"
        )
    if expected_mode == "auto":
        return

    def canonical_name(value: str) -> str:
        key = " ".join(value.strip().casefold().split())
        registry_item = registry.get(key)
        return str(registry_item.get("name", "")).strip().casefold() if registry_item else key

    selected_name = str(selected.get("name", "")).strip()
    if not selected_name or canonical_name(target) != canonical_name(selected_name):
        errors.append("venue/decision.json: selected venue does not match project.json target_venue")


def validate_venue(
    project: Path,
    project_data: dict[str, Any],
    venue: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    selection_mode = venue.get("selection_mode")
    if selection_mode not in {"auto", "user_specified"}:
        errors.append("venue/decision.json: selection_mode must be auto or user_specified")
    selected = venue.get("selected")
    if not isinstance(selected, dict):
        errors.append("venue/decision.json: no selected venue")
        return

    registry = load_registry(Path(__file__).resolve().parents[1] / "references/venue-registry.json")
    validate_selection_binding(project_data, venue, selected, registry, errors)

    for field in (
        "name",
        "edition",
        "track",
        "official_url",
        "deadline_source_url",
        "anonymity",
        "ai_disclosure_policy",
        "template_url",
        "template_status",
        "template_checked_at",
        "template_path",
        "template_sha256",
    ):
        if not selected.get(field):
            errors.append(f"venue/decision.json: selected venue is missing {field}")
    if not timezone_aware(str(selected.get("template_checked_at", ""))):
        errors.append("venue/decision.json: template_checked_at must be timezone-aware")
    template_status = str(selected.get("template_status", "")).lower()
    if template_status not in {"current", "current_cycle", "previous_cycle"}:
        errors.append("venue/decision.json: invalid template_status")
    if template_status == "previous_cycle" and not selected.get("previous_template_edition"):
        errors.append("venue/decision.json: previous-cycle template needs previous_template_edition")
    template_path_value = str(selected.get("template_path", "")).strip()
    if template_path_value:
        template_path = resolve_project_path(project, template_path_value).resolve()
        template_root = (project / "venue/template").resolve()
        try:
            template_path.relative_to(template_root)
        except ValueError:
            errors.append("venue/decision.json: template_path must stay under venue/template")
        if not template_path.is_file():
            errors.append("venue/decision.json: downloaded template_path does not exist")
        else:
            expected_template_hash = str(selected.get("template_sha256", "")).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_template_hash):
                errors.append("venue/decision.json: template_sha256 is invalid")
            elif sha256_file(template_path) != expected_template_hash:
                errors.append("venue/decision.json: downloaded template hash does not match")
    required_tokens = selected.get("template_required_tokens")
    if not isinstance(required_tokens, list) or not required_tokens or not all(
        isinstance(token, str) and token for token in required_tokens
    ):
        errors.append("venue/decision.json: template_required_tokens must be a non-empty string list")
    else:
        main_source = (project / "paper/main.tex").read_text(encoding="utf-8", errors="replace")
        for token in required_tokens:
            if token not in main_source:
                errors.append(f"paper/main.tex: missing official template signature {token!r}")
        has_template_todo = has_draft_marker(main_source, "TemplateTODO", "TEMPLATE-UPDATE")
        if template_status == "previous_cycle" and not has_template_todo:
            errors.append("paper/main.tex: previous-cycle template requires TEMPLATE-UPDATE")
        if template_status in {"current", "current_cycle"} and has_template_todo:
            errors.append("paper/main.tex: current template must not retain TEMPLATE-UPDATE")

    page_rules = selected.get("page_rules")
    if not isinstance(page_rules, dict):
        errors.append("venue/decision.json: selected venue needs page_rules")
    else:
        try:
            main_pages = int(page_rules.get("main_text_pages", 0))
        except (TypeError, ValueError):
            main_pages = 0
        if main_pages <= 0:
            errors.append("venue/decision.json: page_rules.main_text_pages must be positive")
        if not isinstance(page_rules.get("references_counted"), bool):
            errors.append("venue/decision.json: page_rules.references_counted must be boolean")
        for field in ("appendix_policy", "supplement_policy"):
            if not page_rules.get(field):
                errors.append(f"venue/decision.json: page_rules is missing {field}")

    if selection_mode != "auto":
        return
    if venue.get("status") not in {"selected", "tentative"}:
        errors.append("venue/decision.json: automatic selection status must be selected or tentative")
    if venue.get("selection_rule") != SELECTION_RULE:
        errors.append("venue/decision.json: unexpected or missing automatic selection_rule")
    try:
        as_of = parse_datetime(str(venue.get("as_of", "")))
    except ValueError as exc:
        errors.append(f"venue/decision.json: invalid as_of: {exc}")
        return

    allow_tentative = venue.get("status") == "tentative"
    ok, reason, selected_deadline, normalized_selected = evaluate_venue(
        selected,
        registry,
        as_of,
        4.0,
        allow_tentative,
        24.0,
    )
    if not ok or selected_deadline is None:
        errors.append(f"venue/decision.json: selected venue is ineligible: {reason}")
        return
    if normalized_selected.get("idea_version") != project_data.get("idea_version"):
        errors.append("venue/decision.json: selected venue fit was scored for a stale idea version")
    if selected_deadline.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        warnings.append(
            "venue/decision.json: venue was open at selection time but its effective deadline has since passed"
        )

    candidate_path = project / "venue/candidates.json"
    try:
        candidates = load_candidates(candidate_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{candidate_path}: invalid candidate file: {exc}")
        return
    eligible: list[tuple[datetime, dict[str, Any]]] = []
    for candidate in candidates:
        candidate_ok, _, deadline, normalized = evaluate_venue(
            candidate,
            registry,
            as_of,
            4.0,
            allow_tentative,
            24.0,
        )
        if candidate_ok and deadline is not None:
            eligible.append((deadline, normalized))
    if allow_tentative and any(
        str(item.get("deadline_status", "")).lower() == "confirmed" for _, item in eligible
    ):
        eligible = [
            pair for pair in eligible if str(pair[1].get("deadline_status", "")).lower() == "confirmed"
        ]
    eligible.sort(
        key=lambda pair: (
            pair[0].astimezone(timezone.utc),
            -float(pair[1].get("scope_fit", 0)),
            TIER_RANK.get(str(pair[1].get("tier", "")).lower(), 99),
            str(pair[1].get("name", "")).lower(),
        )
    )
    if not eligible:
        errors.append("venue/candidates.json: no eligible automatic venue")
        return
    expected = eligible[0][1]
    identity_fields = ("name", "edition", "track")
    if any(str(expected.get(field, "")) != str(selected.get(field, "")) for field in identity_fields):
        errors.append("venue/decision.json: selected venue is not the nearest eligible candidate")


def validate_literature(project: Path, project_data: dict[str, Any], errors: list[str]) -> None:
    root = project / "related_works"
    for filename in SURVEY_FILES:
        if not (root / filename).exists():
            errors.append(f"related_works: missing {filename}")
    if any(not (root / filename).exists() for filename in SURVEY_FILES):
        return

    manifest = read_json(root / "survey_run.json", errors)
    if manifest.get("skill_name") != "ai-literature-survey":
        errors.append("related_works/survey_run.json: skill_name must be ai-literature-survey")
    if manifest.get("status") != "pass" or manifest.get("errors"):
        errors.append("related_works/survey_run.json: survey provenance did not pass")
    if manifest.get("idea_version") != project_data.get("idea_version"):
        errors.append("related_works/survey_run.json: idea version does not match project.json")
    if not manifest.get("invocation_id"):
        errors.append("related_works/survey_run.json: missing invocation_id")
    if not timezone_aware(str(manifest.get("completed_at", ""))):
        errors.append("related_works/survey_run.json: completed_at must be timezone-aware")
    coverage = manifest.get("coverage") if isinstance(manifest.get("coverage"), dict) else {}
    if coverage.get("status") != "near_complete":
        errors.append("related_works/survey_run.json: coverage status must be near_complete")
    try:
        zero_passes = int(coverage.get("consecutive_zero_new_core_passes", -1))
    except (TypeError, ValueError):
        zero_passes = -1
    if zero_passes < 2:
        errors.append("related_works/survey_run.json: fewer than two zero-new-core snowball passes")
    if coverage.get("blind_spots_recorded") is not True:
        errors.append("related_works/survey_run.json: blind spots were not recorded")
    covered_groups = set(coverage.get("covered_source_groups", []))
    if len(covered_groups) < 4 or not {"current_preprints", "citation_graph"} <= covered_groups:
        errors.append("related_works/survey_run.json: required source-group coverage is missing")

    receipt_value = str(manifest.get("receipt_path", "")).strip()
    receipt_path = (root / receipt_value).resolve() if receipt_value else root / "<missing>"
    try:
        receipt_path.relative_to(root.resolve())
    except ValueError:
        errors.append("related_works/survey_run.json: receipt_path escapes related_works")
    if not receipt_path.is_file():
        errors.append("related_works/survey_run.json: survey receipt is missing")
    else:
        receipt_hash = sha256_file(receipt_path)
        if receipt_hash != str(manifest.get("receipt_sha256", "")).lower():
            errors.append("related_works/survey_run.json: survey receipt hash mismatch")
        receipt = read_json(receipt_path, errors)
        if receipt.get("skill_name") != "ai-literature-survey":
            errors.append("related_works/survey_receipt.json: wrong skill_name")
        if receipt.get("invocation_id") != manifest.get("invocation_id"):
            errors.append("related_works/survey_receipt.json: invocation_id mismatch")
        skill_snapshot_value = str(manifest.get("skill_snapshot_path", "")).strip()
        skill_snapshot = (root / skill_snapshot_value).resolve() if skill_snapshot_value else root / "<missing>"
        try:
            skill_snapshot.relative_to(root.resolve())
        except ValueError:
            errors.append("related_works/survey_run.json: skill snapshot escapes related_works")
        if not skill_snapshot.is_file():
            errors.append("related_works/survey_run.json: invoked skill snapshot is missing")
        elif sha256_file(skill_snapshot) != str(manifest.get("skill_snapshot_sha256", "")).lower():
            errors.append("related_works/survey_run.json: invoked skill snapshot hash mismatch")
        elif sha256_file(skill_snapshot) != str(receipt.get("skill_sha256", "")).lower():
            errors.append("related_works/survey_receipt.json: skill snapshot differs from receipt")
        elif not re.search(
            r"(?m)^name:\s*ai-literature-survey\s*$",
            skill_snapshot.read_text(encoding="utf-8", errors="replace"),
        ):
            errors.append("related_works/survey_receipt.json: skill snapshot is not ai-literature-survey")

    artifact_records = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    for relative in SURVEY_STANDARD_ARTIFACTS:
        record = artifact_records.get(relative)
        if not isinstance(record, dict):
            errors.append(f"related_works/survey_run.json: missing artifact record {relative}")
            continue
        expected_hash = str(record.get("sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            errors.append(f"related_works/survey_run.json: invalid hash for {relative}")
        elif sha256_file(root / relative) != expected_hash:
            errors.append(f"related_works/survey_run.json: artifact changed after survey run: {relative}")

    screening_rows: list[dict[str, str]] = []
    for relative, required_fields in SURVEY_CSV_REQUIRED.items():
        fields, rows = read_csv(root / relative, errors)
        missing = sorted(required_fields - set(fields))
        if missing:
            errors.append(f"related_works/{relative}: missing columns {missing}")
        if relative == "source_ledger.csv" and not rows:
            errors.append("related_works/source_ledger.csv: no search records")
        if relative == "screening.csv":
            screening_rows = rows

    enriched_path = root / "papers_enriched.csv"
    fields, rows = read_csv(enriched_path, errors)
    missing_enriched = sorted(ENRICHED_REQUIRED - set(fields))
    if missing_enriched:
        errors.append(f"{enriched_path}: missing columns {missing_enriched}")
        return
    if not rows:
        errors.append(f"{enriched_path}: no paper records")
        return
    stable_ids: set[str] = set()
    enriched_by_record_id: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        record_id = row.get("record_id", "").strip()
        if not record_id or record_id in enriched_by_record_id:
            errors.append(f"{enriched_path}:{index}: record_id must be non-empty and unique")
        enriched_by_record_id[record_id] = row
        sid = row.get("stable_id", "").strip()
        if not sid:
            errors.append(f"{enriched_path}:{index}: empty stable_id")
        elif sid in stable_ids:
            errors.append(f"{enriched_path}:{index}: duplicate stable_id {sid}")
        stable_ids.add(sid)
        if not row.get("title", "").strip():
            errors.append(f"{enriched_path}:{index}: empty title")
        tier = row.get("tier", "").strip().lower()
        if tier not in {"core", "adjacent", "background", "exclude"}:
            errors.append(f"{enriched_path}:{index}: invalid literature tier {tier!r}")
        publication_status = row.get("publication_status", "").strip().lower()
        if publication_status not in PUBLICATION_STATUSES:
            errors.append(f"{enriched_path}:{index}: invalid publication_status {publication_status!r}")
        access_status = row.get("paper_access_status", "").strip().lower()
        if access_status not in PAPER_ACCESS_STATUSES:
            errors.append(f"{enriched_path}:{index}: invalid paper_access_status {access_status!r}")
        for field in ("official_code_status", "data_status", "weights_status"):
            value = row.get(field, "").strip().lower()
            if value not in ARTIFACT_STATUSES:
                errors.append(f"{enriched_path}:{index}: invalid {field} {value!r}")
        if publication_status in {"accepted", "published"}:
            if not row.get("status_evidence_url", "").strip() or not timezone_aware(
                row.get("status_checked_at", "")
            ):
                errors.append(
                    f"{enriched_path}:{index}: accepted/published status needs evidence URL and checked timestamp"
                )
        if row.get("official_code_status", "").strip().lower() == "available":
            if not row.get("code_url", "").strip() or not row.get("code_license", "").strip():
                errors.append(f"{enriched_path}:{index}: available official code needs URL and license status")
        if access_status == "open_pdf":
            pdf_value = row.get("local_pdf_path", "").strip()
            if not pdf_value or not (root / pdf_value).exists():
                errors.append(f"{enriched_path}:{index}: open PDF is not stored locally")
        if tier and tier != "exclude":
            record_path = row.get("local_record_path", "").strip()
            if not record_path or not (root / record_path).exists():
                errors.append(f"{enriched_path}:{index}: missing local paper record directory")

    related_text = (project / "paper/sections/related_work.tex").read_text(
        encoding="utf-8", errors="replace"
    )
    cited_keys: set[str] = set()
    for match in re.finditer(r"\\cite[a-zA-Z*]*\s*\{([^}]+)\}", related_text):
        cited_keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    bib_text = (project / "paper/references.bib").read_text(encoding="utf-8", errors="replace")
    must_cite_ids = {
        row.get("record_id", "").strip()
        for row in screening_rows
        if row.get("must_cite", "").strip().lower() == "yes"
    }
    for record_id, row in enriched_by_record_id.items():
        if row.get("tier", "").strip().lower() == "core" and row.get(
            "publication_status", ""
        ).strip().lower() in {"accepted", "published"}:
            if record_id not in must_cite_ids:
                errors.append(
                    f"related_works/screening.csv: accepted/published core paper {record_id} must be must_cite=yes"
                )
    for record_id in sorted(must_cite_ids):
        row = enriched_by_record_id.get(record_id)
        if not row:
            errors.append(f"related_works/screening.csv: must-cite record missing from enriched papers: {record_id}")
            continue
        bib_key = row.get("bib_key", "").strip()
        if not bib_key:
            errors.append(f"{enriched_path}: must-cite paper {record_id} lacks bib_key")
            continue
        if bib_key not in cited_keys:
            errors.append(f"paper/sections/related_work.tex: must-cite paper is not cited: {bib_key}")
        if not re.search(rf"@\w+\s*\{{\s*{re.escape(bib_key)}\s*,", bib_text):
            errors.append(f"paper/references.bib: missing must-cite entry {bib_key}")


def validate_council(project: Path, errors: list[str]) -> None:
    rounds = sorted(path for path in (project / "idea/meetings").glob("round_*") if path.is_dir())
    if not rounds:
        errors.append("idea/meetings: no idea-council round")
        return
    if len(rounds) > 3:
        errors.append("idea/meetings: more than three council rounds")
    decisions: list[dict[str, Any]] = []
    decision_rounds: list[Path] = []
    for round_path in rounds:
        required = [
            "snapshot.json",
            "idea.md",
            "resources.json",
            "literature_manifest.json",
            "student_a.md",
            "student_b.md",
            "professor.md",
            "decision.json",
        ]
        missing = [name for name in required if not (round_path / name).exists()]
        if missing:
            errors.append(f"{round_path}: missing council files {missing}")
            continue
        snapshot = read_json(round_path / "snapshot.json", errors)
        decision = read_json(round_path / "decision.json", errors)
        decisions.append(decision)
        decision_rounds.append(round_path)
        snapshot_id = str(snapshot.get("snapshot_id", "")).strip()
        for field in ("snapshot_id", "idea_version", "idea_sha256", "resource_sha256", "literature_sha256"):
            if not snapshot.get(field):
                errors.append(f"{round_path / 'snapshot.json'}: missing {field}")
        snapshot_files = {
            "idea_sha256": round_path / "idea.md",
            "resource_sha256": round_path / "resources.json",
            "literature_sha256": round_path / "literature_manifest.json",
        }
        for hash_field, snapshot_file in snapshot_files.items():
            expected = str(snapshot.get(hash_field, "")).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256_file(snapshot_file) != expected:
                errors.append(f"{round_path / 'snapshot.json'}: {hash_field} does not match {snapshot_file.name}")
        for report_name in ("student_a.md", "student_b.md", "professor.md"):
            report_path = round_path / report_name
            report = report_path.read_text(encoding="utf-8", errors="replace")
            if not snapshot_id or f"Snapshot ID: {snapshot_id}" not in report:
                errors.append(f"{report_path}: report does not bind to the shared immutable snapshot")
            if not re.search(r"(?im)^\s*Verdict\s*:\s*(KEEP|REVISE|BLOCK)\s*$", report):
                errors.append(f"{report_path}: missing machine-readable verdict")
            expected_hash = str(decision.get(report_name.replace(".md", "_sha256"), "")).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or sha256_file(report_path) != expected_hash:
                errors.append(f"{round_path / 'decision.json'}: invalid hash for {report_name}")
        if decision.get("snapshot_id") != snapshot_id:
            errors.append(f"{round_path / 'decision.json'}: snapshot_id mismatch")
        decision_verdict = str(decision.get("verdict", "")).upper()
        if decision_verdict not in {"KEEP", "REVISE", "BLOCK"}:
            errors.append(f"{round_path / 'decision.json'}: invalid verdict")
        professor_text = (round_path / "professor.md").read_text(encoding="utf-8", errors="replace")
        professor_verdicts = re.findall(
            r"(?im)^\s*Verdict\s*:\s*(KEEP|REVISE|BLOCK)\s*$",
            professor_text,
        )
        if not professor_verdicts or professor_verdicts[-1].upper() != decision_verdict:
            errors.append(f"{round_path / 'decision.json'}: Professor report verdict does not match decision")
        agents = decision.get("agents")
        if not isinstance(agents, dict):
            errors.append(f"{round_path / 'decision.json'}: missing agent identities")
        else:
            agent_ids = [str(agents.get(role, "")).strip() for role in ("student_a", "student_b", "professor")]
            if any(not agent_id for agent_id in agent_ids) or len(set(agent_ids)) != 3:
                errors.append(f"{round_path / 'decision.json'}: council requires three distinct agent identities")
        timestamp_fields = ("student_a_completed_at", "student_b_completed_at", "professor_started_at")
        if not all(timezone_aware(str(decision.get(field, ""))) for field in timestamp_fields):
            errors.append(f"{round_path / 'decision.json'}: council timestamps must be timezone-aware")
        else:
            parsed_times = {
                field: datetime.fromisoformat(str(decision[field]).replace("Z", "+00:00"))
                for field in timestamp_fields
            }
            if parsed_times["professor_started_at"] < max(
                parsed_times["student_a_completed_at"],
                parsed_times["student_b_completed_at"],
            ):
                errors.append(f"{round_path / 'decision.json'}: Professor started before both student reports finished")

    for index, decision in enumerate(decisions[:-1]):
        if str(decision.get("verdict", "")).upper() == "REVISE":
            current_literature = read_json(decision_rounds[index] / "snapshot.json", errors).get("literature_sha256")
            next_literature = read_json(decision_rounds[index + 1] / "snapshot.json", errors).get("literature_sha256")
            if current_literature == next_literature:
                errors.append(f"{decision_rounds[index + 1]}: REVISE must be followed by a delta literature snapshot")
    if decisions:
        final = decisions[-1]
        final_round = decision_rounds[-1]
        final_snapshot = read_json(final_round / "snapshot.json", errors)
        current_project = read_json(project / "project.json", errors)
        if final_snapshot.get("idea_version") != current_project.get("idea_version"):
            errors.append(f"{final_round}: final council idea_version is not current")
        current_idea_path = project / "idea/versions" / f"{final_snapshot.get('idea_version', '')}.md"
        current_bindings = {
            "idea_sha256": current_idea_path,
            "resource_sha256": project / "resources.json",
            "literature_sha256": project / "related_works/survey_run.json",
        }
        for hash_field, current_path in current_bindings.items():
            if not current_path.is_file() or sha256_file(current_path) != str(
                final_snapshot.get(hash_field, "")
            ).lower():
                errors.append(f"{final_round}: final council snapshot is stale for {hash_field}")
        if str(final.get("verdict", "")).upper() != "KEEP":
            errors.append("idea/meetings: final Professor decision must be KEEP for sketch validation")
        blockers = final.get("critical_blockers")
        if blockers not in ([], None):
            errors.append("idea/meetings: final decision retains critical blockers")
        contributions = final.get("contributions")
        if not isinstance(contributions, list) or len(contributions) < 3:
            errors.append("idea/meetings: final decision needs at least three defensible contributions")
        else:
            allowed_types = {"insight", "strategy_module", "dataset_protocol", "model", "experiment", "other"}
            contribution_ids: set[str] = set()
            for contribution in contributions:
                if not isinstance(contribution, dict):
                    errors.append("idea/meetings: contribution records must be JSON objects")
                    continue
                contribution_id = str(contribution.get("contribution_id", "")).strip()
                if not contribution_id or contribution_id in contribution_ids:
                    errors.append("idea/meetings: contribution IDs must be non-empty and unique")
                contribution_ids.add(contribution_id)
                if contribution.get("type") not in allowed_types:
                    errors.append(f"idea/meetings: invalid contribution type {contribution.get('type')!r}")
                for field in ("statement", "claim_id", "method_component", "experiment_id"):
                    if not contribution.get(field):
                        errors.append(f"idea/meetings: contribution {contribution_id or '<missing>'} lacks {field}")


def inherited_core_composition_evidence(
    project: Path, input_values: list[str]
) -> tuple[str, str] | None:
    """Return a direct parent's hash-bound prompt and QA for a surgical edit.

    Image-generation prompts are immutable execution receipts. A narrow edit is
    therefore allowed to inherit the complete composition contract from its
    direct input image, but only when that parent's prompt, QA, provenance, and
    output all exist and the provenance hashes bind the prompt and image.
    """

    generated_root = (project / "figures/generated").resolve()
    for input_value in input_values:
        input_path = resolve_project_path(project, input_value).resolve()
        try:
            input_path.relative_to(generated_root)
        except ValueError:
            continue
        if not input_path.is_file():
            continue
        stem = input_path.stem
        prompt_candidates = (
            project / "figures/prompts" / f"{stem}.txt",
            project / "figures/prompts" / f"{stem}.md",
        )
        provenance_candidates = (
            project / "figures/qa" / f"{stem}_provenance.json",
            project / "figures/qa" / f"{stem}-provenance.json",
        )
        qa_path = project / "figures/qa" / f"{stem}.md"
        prompt_path = next((item for item in prompt_candidates if item.is_file()), None)
        provenance_path = next(
            (item for item in provenance_candidates if item.is_file()), None
        )
        if prompt_path is None or provenance_path is None or not qa_path.is_file():
            continue
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(provenance, dict):
            continue
        prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
        if any(field not in prompt for field in CORE_PROMPT_FIELDS):
            continue
        if str(provenance.get("prompt_sha256", "")).lower() != sha256_file(prompt_path):
            continue
        if str(provenance.get("output_sha256", "")).lower() != sha256_file(input_path):
            continue
        qa_text = qa_path.read_text(encoding="utf-8", errors="replace")
        return prompt, qa_text
    return None


def validate_figures(project: Path, errors: list[str], require_overview: bool) -> None:
    path = project / "figures/manifest.csv"
    fields, rows = read_csv(path, errors)
    missing_fields = [field for field in FIGURE_REQUIRED if field not in fields]
    if missing_fields:
        errors.append(f"{path}: missing columns {missing_fields}")
        return
    if require_overview and not any(row.get("type", "").strip().lower() == "overview" for row in rows):
        errors.append(f"{path}: missing required overview figure")
    manifest_by_paper_path: dict[Path, list[int]] = {}
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        figure_id = row.get("figure_id", "").strip()
        figure_type = row.get("type", "").strip().lower()
        if not figure_id:
            errors.append(f"{path}:{index}: empty figure_id")
        elif figure_id in seen_ids:
            errors.append(f"{path}:{index}: duplicate figure_id {figure_id}")
        seen_ids.add(figure_id)
        if row.get("backend", "").strip().lower() != "imagegen":
            errors.append(f"{path}:{index}: figure backend must be imagegen")
        mode = row.get("mode", "").strip().lower()
        if mode not in {"generate", "edit"}:
            errors.append(f"{path}:{index}: mode must be generate or edit")
        if not row.get("claim_ids", "").strip():
            errors.append(f"{path}:{index}: every paper figure must link at least one claim_id")
        if figure_type in {"overview", "module", "pipeline", "method-overview"} and not row.get(
            "module_ids", ""
        ).strip():
            errors.append(f"{path}:{index}: overview/module figure must link module_ids")
        if not re.fullmatch(r"v[1-9][0-9]*", row.get("version", "").strip().lower()):
            errors.append(f"{path}:{index}: version must use vN syntax")

        resolved: dict[str, Path] = {}
        allowed_roots = {
            "prompt_path": project / "figures/prompts",
            "generated_path": project / "figures/generated",
            "paper_path": project / "paper/figures",
            "qa_path": project / "figures/qa",
            "provenance_path": project / "figures/qa",
        }
        for field in ("prompt_path", "generated_path", "paper_path", "qa_path", "provenance_path"):
            value = row.get(field, "").strip()
            if not value:
                errors.append(f"{path}:{index}: empty {field}")
                continue
            target = resolve_project_path(project, value).resolve()
            resolved[field] = target
            try:
                target.relative_to(allowed_roots[field].resolve())
            except ValueError:
                errors.append(f"{path}:{index}: {field} escapes its canonical project directory")
            if not target.is_file():
                errors.append(f"{path}:{index}: missing {field} file {value}")
        input_values = [
            value.strip() for value in row.get("input_paths", "").split(";") if value.strip()
        ]
        if mode == "edit" and not input_values:
            errors.append(f"{path}:{index}: imagegen edit mode requires input_paths")
        for input_value in input_values:
            input_path = resolve_project_path(project, input_value).resolve()
            try:
                input_path.relative_to(project.resolve())
            except ValueError:
                errors.append(f"{path}:{index}: input path escapes the project: {input_value}")
            if not input_path.is_file():
                errors.append(f"{path}:{index}: missing imagegen input {input_value}")
        if row.get("status", "").strip().lower() not in {"selected", "qa_passed", "final"}:
            errors.append(f"{path}:{index}: figure status is not selected/qa_passed/final")

        paper_path = resolved.get("paper_path")
        if paper_path:
            manifest_by_paper_path.setdefault(paper_path, []).append(index)
        prompt_path = resolved.get("prompt_path")
        inherited_composition: tuple[str, str] | None = None
        if prompt_path and prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
            surgical_edit = mode == "edit" and bool(
                re.search(
                    r"(?is)\b(?:exactly\s+one|single|surgical|one\s+narrow)\b"
                    r".{0,120}\b(?:edit|change|refinement)\b",
                    prompt,
                )
                and re.search(r"(?i)\bpreserv(?:e|ing)\b", prompt)
            )
            if figure_type in CORE_COMPOSITION_FIGURE_TYPES and surgical_edit:
                inherited_composition = inherited_core_composition_evidence(
                    project, input_values
                )
            if (
                "Use case:" not in prompt or "Primary request:" not in prompt
            ) and inherited_composition is None:
                errors.append(f"{path}:{index}: prompt file lacks the required imagegen prompt contract")
            if figure_type in CORE_COMPOSITION_FIGURE_TYPES:
                composition_prompt = (
                    inherited_composition[0] if inherited_composition is not None else prompt
                )
                missing_prompt_fields = [
                    field for field in CORE_PROMPT_FIELDS if field not in composition_prompt
                ]
                if missing_prompt_fields:
                    errors.append(
                        f"{path}:{index}: core-figure prompt lacks composition fields "
                        f"{missing_prompt_fields}"
                    )
                direction_match = re.search(
                    r"(?im)^Candidate directions evaluated:\s*(\d+)\s*$",
                    composition_prompt,
                )
                refinement_match = re.search(
                    r"(?im)^Targeted refinements completed:\s*(\d+)\s*$",
                    composition_prompt,
                )
                archetype_match = re.search(
                    r"(?im)^Composition archetypes evaluated:\s*(\d+)\s*$",
                    composition_prompt,
                )
                evidence_match = re.search(
                    r"(?im)^Domain visual evidence:\s*(.+)$", composition_prompt
                )
                box_budget_match = re.search(
                    r"(?im)^Generic-box area budget:\s*(?:<=|≤)\s*(\d+(?:\.\d+)?)%\s*$",
                    composition_prompt,
                )
                if direction_match is None or int(direction_match.group(1)) < 6:
                    errors.append(
                        f"{path}:{index}: teaser/overview requires at least six "
                        "composition directions"
                    )
                if refinement_match is None or int(refinement_match.group(1)) < 3:
                    errors.append(
                        f"{path}:{index}: teaser/overview requires at least three "
                        "targeted imagegen refinements"
                    )
                if archetype_match is None or int(archetype_match.group(1)) < 3:
                    errors.append(
                        f"{path}:{index}: teaser/overview requires at least three "
                        "composition archetypes"
                    )
                evidence_items = (
                    [item.strip() for item in evidence_match.group(1).split(";") if item.strip()]
                    if evidence_match
                    else []
                )
                if len(evidence_items) < 3:
                    errors.append(
                        f"{path}:{index}: teaser/overview requires at least three "
                        "domain visual-evidence primitives"
                    )
                if box_budget_match is None or float(box_budget_match.group(1)) > 35.0:
                    errors.append(
                        f"{path}:{index}: generic module boxes may occupy at most 35% "
                        "of a teaser/overview canvas"
                    )
        qa_path = resolved.get("qa_path")
        if qa_path and qa_path.exists():
            qa_text = qa_path.read_text(encoding="utf-8", errors="replace")
            if not re.search(
                r"(?im)^\s*(?:qa_status|qa status)\s*:\s*pass(?:ed)?\s*$",
                qa_text,
            ):
                errors.append(f"{path}:{index}: QA note must contain 'QA status: pass'")
            if figure_type in CORE_COMPOSITION_FIGURE_TYPES:
                composition_qa = qa_text
                if inherited_composition is not None:
                    composition_qa = f"{qa_text}\n{inherited_composition[1]}"
                for gate in CORE_QA_GATES:
                    if not re.search(
                        rf"(?im)^\s*{re.escape(gate)}\s*:\s*pass\b", composition_qa
                    ):
                        errors.append(
                            f"{path}:{index}: core-figure QA lacks '{gate}: pass'"
                        )

        provenance_path = resolved.get("provenance_path")
        provenance: dict[str, Any] = {}
        receipt: dict[str, Any] = {}
        if provenance_path and provenance_path.exists():
            provenance = read_json(provenance_path, errors)
            if provenance.get("skill_name") != "imagegen":
                errors.append(f"{path}:{index}: provenance skill_name must be imagegen")
            skill_snapshot_value = str(provenance.get("skill_snapshot_path", "")).strip()
            skill_snapshot_path = (
                resolve_project_path(project, skill_snapshot_value).resolve()
                if skill_snapshot_value
                else None
            )
            if skill_snapshot_path is None:
                errors.append(f"{path}:{index}: imagegen provenance is missing skill snapshot")
            else:
                try:
                    skill_snapshot_path.relative_to((project / "figures/qa").resolve())
                except ValueError:
                    errors.append(f"{path}:{index}: imagegen skill snapshot escapes figures/qa")
                if not skill_snapshot_path.is_file():
                    errors.append(f"{path}:{index}: imagegen skill snapshot is missing")
                else:
                    snapshot_hash = sha256_file(skill_snapshot_path)
                    if snapshot_hash != str(provenance.get("skill_snapshot_sha256", "")).lower():
                        errors.append(f"{path}:{index}: imagegen skill snapshot hash mismatch")
                    if not re.search(
                        r'''(?m)^name:\s*["']?imagegen["']?\s*$''',
                        skill_snapshot_path.read_text(encoding="utf-8", errors="replace"),
                    ):
                        errors.append(f"{path}:{index}: skill snapshot is not imagegen")
            tool_name = provenance.get("tool")
            if tool_name not in {"image_gen.imagegen", "imagegen.cli"}:
                errors.append(f"{path}:{index}: unsupported imagegen tool provenance")
            if provenance.get("mode") != mode:
                errors.append(f"{path}:{index}: provenance mode does not match manifest mode")
            if not timezone_aware(str(provenance.get("generated_at", ""))):
                errors.append(f"{path}:{index}: provenance generated_at must be timezone-aware")
            receipt_value = str(provenance.get("receipt_path", "")).strip()
            receipt_path = resolve_project_path(project, receipt_value).resolve() if receipt_value else None
            if receipt_path is None:
                errors.append(f"{path}:{index}: imagegen provenance is missing receipt_path")
            else:
                try:
                    receipt_path.relative_to((project / "figures/qa").resolve())
                except ValueError:
                    errors.append(f"{path}:{index}: imagegen receipt escapes figures/qa")
                if not receipt_path.is_file():
                    errors.append(f"{path}:{index}: imagegen receipt file is missing")
                else:
                    if sha256_file(receipt_path) != str(provenance.get("receipt_sha256", "")).lower():
                        errors.append(f"{path}:{index}: imagegen receipt hash mismatch")
                    receipt = read_json(receipt_path, errors)
                    if receipt.get("skill_name") != "imagegen" or receipt.get("tool") != tool_name:
                        errors.append(f"{path}:{index}: imagegen receipt tool identity mismatch")
                    if skill_snapshot_path and skill_snapshot_path.is_file() and str(
                        receipt.get("skill_sha256", "")
                    ).lower() != sha256_file(skill_snapshot_path):
                        errors.append(f"{path}:{index}: imagegen receipt skill hash mismatch")
                    if not receipt.get("call_id"):
                        errors.append(f"{path}:{index}: imagegen receipt is missing call_id")
                    for timestamp_field in ("started_at", "completed_at"):
                        if not timezone_aware(str(receipt.get(timestamp_field, ""))):
                            errors.append(
                                f"{path}:{index}: imagegen receipt {timestamp_field} must be timezone-aware"
                            )
                    if tool_name == "imagegen.cli":
                        if receipt.get("user_confirmed") is not True or not receipt.get("confirmation_id"):
                            errors.append(
                                f"{path}:{index}: imagegen CLI fallback needs recorded user confirmation"
                            )
                        if not re.fullmatch(
                            r"[0-9a-fA-F]{64}",
                            str(receipt.get("command_sha256", "")),
                        ):
                            errors.append(f"{path}:{index}: imagegen CLI receipt lacks command hash")

        output_hash = row.get("output_sha256", "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", output_hash):
            errors.append(f"{path}:{index}: output_sha256 must be a SHA-256 digest")
        generated_path = resolved.get("generated_path")
        if generated_path and generated_path.exists() and output_hash:
            if sha256_file(generated_path) != output_hash:
                errors.append(f"{path}:{index}: generated_path hash does not match output_sha256")
            _, _, png_error = validate_png(generated_path)
            if png_error:
                errors.append(f"{path}:{index}: generated_path {png_error}")
        if paper_path and paper_path.exists() and output_hash:
            if sha256_file(paper_path) != output_hash:
                errors.append(f"{path}:{index}: paper_path hash does not match output_sha256")
            _, _, png_error = validate_png(paper_path)
            if png_error:
                errors.append(f"{path}:{index}: paper_path {png_error}")
        if provenance:
            if str(provenance.get("output_sha256", "")).lower() != output_hash:
                errors.append(f"{path}:{index}: provenance output hash does not match manifest")
            if prompt_path and prompt_path.exists():
                if str(provenance.get("prompt_sha256", "")).lower() != sha256_file(prompt_path):
                    errors.append(f"{path}:{index}: provenance prompt hash does not match prompt file")
        if receipt:
            if str(receipt.get("output_sha256", "")).lower() != output_hash:
                errors.append(f"{path}:{index}: imagegen receipt output hash does not match")
            if prompt_path and prompt_path.exists() and str(
                receipt.get("prompt_sha256", "")
            ).lower() != sha256_file(prompt_path):
                errors.append(f"{path}:{index}: imagegen receipt prompt hash does not match")

    for paper_path, line_numbers in manifest_by_paper_path.items():
        if len(line_numbers) > 1:
            errors.append(f"{path}: paper asset {paper_path} is registered more than once at rows {line_numbers}")

    included_paths: set[Path] = set()
    paper_root = project / "paper"
    for tex_path in paper_root.rglob("*.tex"):
        text = strip_tex_comments(tex_path.read_text(encoding="utf-8", errors="replace"))
        for match in INCLUDE_RE.finditer(text):
            value = match.group(1).strip()
            line_number = text.count("\n", 0, match.start()) + 1
            raw_candidate = paper_root / value
            candidates = [raw_candidate] if raw_candidate.suffix else [raw_candidate.with_suffix(".png")]
            existing = [candidate.resolve() for candidate in candidates if candidate.exists()]
            if len(existing) != 1:
                errors.append(
                    f"{tex_path}:{line_number}: includegraphics target {value!r} resolves to "
                    f"{len(existing)} raster files"
                )
                continue
            included = existing[0]
            included_paths.add(included)
            if included not in manifest_by_paper_path:
                errors.append(f"{tex_path}:{line_number}: unregistered paper figure {value!r}")

    for paper_path in manifest_by_paper_path:
        if paper_path not in included_paths:
            errors.append(f"{path}: selected/final manifest asset is not included by the paper: {paper_path}")


def validate_no_alternate_figure_backends(project: Path, errors: list[str]) -> None:
    forbidden_patterns = {
        "TikZ/PGFPlots package": re.compile(
            r"\\usepackage(?:\[[^\]]*\])?\{[^}]*(?:tikz|pgfplots|pstricks|asymptote)[^}]*\}",
            re.IGNORECASE,
        ),
        "inline drawing environment": re.compile(
            r"\\begin\{(?:tikzpicture|axis|picture|pspicture|asy)\}",
            re.IGNORECASE,
        ),
        "inline drawing command": re.compile(
            r"\\(?:draw|addplot|psline|psframe|includesvg|asy)\b",
            re.IGNORECASE,
        ),
        "vector/drawing input": re.compile(
            r"\\(?:input|include)\s*\{[^}]*\.(?:tikz|pgf|svg|asy)\}",
            re.IGNORECASE,
        ),
        "protected raster command redefinition": re.compile(
            r"\\(?:def|gdef|edef|xdef)\s*\\includegraphics\b"
            r"|\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)"
            r"\*?\s*\{?\s*\\includegraphics\b"
            r"|\\let\s*\\includegraphics\b"
            r"|\\csname\s*includegraphics\s*\\endcsname",
            re.IGNORECASE,
        ),
    }
    paper_root = project / "paper"
    figure_composition = re.compile(
        r"\\begin\{(?:tabular\*?|tabularx|array|minipage|matrix|pmatrix|bmatrix|cases)\}"
        r"|\\(?:rule|put|multiput|line|vector|oval|circle|fbox|framebox|parbox|shortstack|"
        r"makebox|raisebox|colorbox|fcolorbox)\b",
        re.IGNORECASE,
    )
    figure_include_re = re.compile(
        r"\\includegraphics\*?(?:\[([^\]]*)\])?\s*\{([^}]+)\}", re.IGNORECASE
    )

    def raster_include_extent_points(options: str) -> float | None:
        """Estimate explicit raster extent; unknown/natural sizes are not guessed."""

        dimensions: list[float] = []
        for match in re.finditer(
            r"(?:width|height)\s*=\s*([0-9]*\.?[0-9]+)\s*"
            r"(\\(?:line|text|column|paper)width|pt|bp|in|cm|mm)",
            options,
            re.IGNORECASE,
        ):
            value = float(match.group(1))
            unit = match.group(2).lower()
            if unit.startswith("\\"):
                dimensions.append(value * 468.0)
            else:
                factors = {
                    "pt": 1.0,
                    "bp": 72.27 / 72.0,
                    "in": 72.27,
                    "cm": 28.4528,
                    "mm": 2.84528,
                }
                dimensions.append(value * factors[unit])
        if re.search(
            r"(?:width|height)\s*=\s*\\(?:line|text|column|paper)width",
            options,
            re.IGNORECASE,
        ):
            dimensions.append(468.0)
        if dimensions:
            return max(dimensions)
        scale = re.search(r"(?:^|,)\s*scale\s*=\s*([0-9]*\.?[0-9]+)", options)
        if scale is not None and float(scale.group(1)) < 0.20:
            return 0.0
        return None

    def balanced_end(source: str, start: int, opening: str, closing: str) -> int | None:
        if start >= len(source) or source[start] != opening:
            return None
        depth = 0
        index = start
        while index < len(source):
            character = source[index]
            if character == "\\":
                index += 2
                continue
            if character == opening:
                depth += 1
            elif character == closing:
                depth -= 1
                if depth == 0:
                    return index + 1
            index += 1
        return None

    def grouped_command_spans(
        source: str,
        command_pattern: str,
        group_count: int,
        *,
        optional_bracket: bool = False,
    ) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for command in re.finditer(command_pattern, source, re.IGNORECASE):
            cursor = command.end()
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            if optional_bracket and cursor < len(source) and source[cursor] == "[":
                bracket_end = balanced_end(source, cursor, "[", "]")
                if bracket_end is None:
                    continue
                cursor = bracket_end
                while cursor < len(source) and source[cursor].isspace():
                    cursor += 1
            valid = True
            for _ in range(group_count):
                if cursor >= len(source) or source[cursor] != "{":
                    valid = False
                    break
                group_end = balanced_end(source, cursor, "{", "}")
                if group_end is None:
                    valid = False
                    break
                cursor = group_end
                while cursor < len(source) and source[cursor].isspace():
                    cursor += 1
            if valid:
                spans.append((command.start(), cursor))
        return spans

    def unauthorized_figure_residue(figure_body: str) -> str:
        """Return source not covered by the finite raster-figure grammar."""

        spans: list[tuple[int, int]] = [
            (include.start(), include.end())
            for include in figure_include_re.finditer(figure_body)
        ]
        spans.extend(
            grouped_command_spans(
                figure_body,
                r"\\(?:caption|subcaption)\*?(?![A-Za-z@])",
                1,
                optional_bracket=True,
            )
        )
        spans.extend(
            grouped_command_spans(
                figure_body, r"\\(?:label|Description|captionsetup)\b", 1
            )
        )
        spans.extend(
            grouped_command_spans(
                figure_body,
                r"\\(?:PredResult|PredClaim|DraftChoice|QualPlaceholder|TemplateTODO)\b",
                2,
            )
        )
        spans.extend(
            grouped_command_spans(figure_body, r"\\[hv]space\*?(?![A-Za-z@])", 1)
        )
        for pattern in (
            r"\\begin\{subfigure\}(?:\[[^]]*\])?\s*\{[^}]*\}",
            r"\\end\{subfigure\}",
            r"\\(?:centering|raggedright|hfill|hfil|vfill|small|footnotesize|scriptsize|"
            r"tiny|normalsize|par|noindent|phantomsubcaption|smallskip|medskip|bigskip|"
            r"quad|qquad)\b",
            r"\\\\(?:\[[^]]*\])?",
        ):
            spans.extend((match.start(), match.end()) for match in re.finditer(pattern, figure_body))

        first = 0
        while first < len(figure_body) and figure_body[first].isspace():
            first += 1
        if first < len(figure_body) and figure_body[first] == "[":
            placement_end = balanced_end(figure_body, first, "[", "]")
            if placement_end is not None:
                spans.append((first, placement_end))

        masked = list(figure_body)
        for start, end in spans:
            for index in range(start, min(end, len(masked))):
                if masked[index] not in "\r\n":
                    masked[index] = " "
        return re.sub(r"\s+", " ", "".join(masked)).strip()

    audited_sources = sorted(
        {
            *paper_root.rglob("*.tex"),
            *paper_root.rglob("*.sty"),
            *paper_root.rglob("*.cls"),
        }
    )
    for tex_path in audited_sources:
        text = strip_tex_comments(tex_path.read_text(encoding="utf-8", errors="replace"))
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                errors.append(f"{tex_path}: forbidden non-imagegen figure backend ({label})")
        if tex_path.suffix.casefold() != ".tex":
            continue
        for match in re.finditer(
            r"\\begin\{figure\*?\}([\s\S]*?)\\end\{figure\*?\}",
            text,
            re.IGNORECASE,
        ):
            figure_body = match.group(1)
            line_number = text.count("\n", 0, match.start()) + 1
            includes = list(figure_include_re.finditer(figure_body))
            if not includes:
                errors.append(
                    f"{tex_path}:{line_number}: figure environment has no registered raster includegraphics"
                )
                continue
            if figure_composition.search(figure_body):
                errors.append(
                    f"{tex_path}:{line_number}: figure environment uses TeX composition primitives; "
                    "the graphical subject must be a registered imagegen raster"
                )
            residue = unauthorized_figure_residue(figure_body)
            if residue:
                errors.append(
                    f"{tex_path}:{line_number}: figure contains unauthorized TeX structure "
                    f"outside the raster-layout grammar ({residue[:120]!r})"
                )
            explicit_extents = [
                raster_include_extent_points(include.group(1) or "") for include in includes
            ]
            if (
                explicit_extents
                and all(extent is not None for extent in explicit_extents)
                and sum(float(extent) for extent in explicit_extents if extent is not None) < 72.0
            ):
                errors.append(
                    f"{tex_path}:{line_number}: every registered raster in the figure is explicitly "
                    "token-sized; an imagegen asset must remain the graphical subject"
                )
    for extension in ("*.svg", "*.tikz", "*.pgf", "*.asy"):
        for drawing_path in paper_root.rglob(extension):
            errors.append(f"{drawing_path}: vector/inline drawing assets are forbidden in idea2paper")


def validate_sections(project: Path, errors: list[str]) -> None:
    required = [
        "abstract.tex",
        "introduction.tex",
        "related_work.tex",
        "method.tex",
        "experiments.tex",
        "conclusion.tex",
        "limitations.tex",
    ]
    for filename in required:
        path = project / "paper/sections" / filename
        if not non_comment_content(path):
            errors.append(f"{path}: section has no substantive content")

    leakage_patterns = [
        re.compile(r"student\s+a\s+(agent|report)", re.IGNORECASE),
        re.compile(r"student\s+b\s+(agent|report)", re.IGNORECASE),
        re.compile(r"professor\s+agent", re.IGNORECASE),
        re.compile(r"idea/meetings/", re.IGNORECASE),
        re.compile(r"internal\s+work\s+plan", re.IGNORECASE),
    ]
    for path in (project / "paper").rglob("*.tex"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in leakage_patterns:
            if pattern.search(text):
                errors.append(f"{path}: possible internal workflow leakage ({pattern.pattern})")


def validate_todo_registry(
    project: Path,
    todo_report: dict[str, Any],
    errors: list[str],
) -> None:
    registry_path = project / "qa/todo_registry.json"
    registry = read_json(registry_path, errors)
    if registry.get("errors"):
        errors.append(f"{registry_path}: registry contains lint errors")
    if registry != todo_report:
        errors.append(
            f"{registry_path}: registry does not exactly match current portable "
            "LaTeX draft macro/TODO paths, lines, and messages"
        )


def validate_state_snapshots(project: Path, state: dict[str, Any], errors: list[str]) -> None:
    stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    for stage, record in stages.items():
        if not isinstance(record, dict) or record.get("status") != "complete":
            continue
        recorded = record.get("input_versions")
        if not isinstance(recorded, dict) or not recorded:
            errors.append(f"state.json: complete stage {stage} has no input hash snapshot")
            continue
        current = snapshot_inputs(project, stage)
        if current != recorded:
            changed = sorted(
                key
                for key in set(current) | set(recorded)
                if current.get(key) != recorded.get(key)
            )
            preview = ", ".join(changed[:5])
            suffix = " ..." if len(changed) > 5 else ""
            errors.append(
                f"state.json: complete stage {stage} is stale; changed inputs: {preview}{suffix}"
            )


PAPERJURY_ACTIVE = {
    "raised",
    "in-trial",
    "re-trial",
    "under-discussion",
    "maintain-pending-tiebreak",
    "agreed-to-fix",
    "agreed-to-fix-modified",
    "valid-fixable",
    "author-required",
}
PAPERJURY_GATE_BLOCKING = {"raised", "in-trial", "re-trial", "valid-fixable"}
PAPERJURY_TERMINAL = {"closed", "withdrawn", "override", "dropped", "queued"}


def paperjury_review_tree_sha256(root: Path) -> str:
    """Hash the review-visible manuscript text, excluding compiled/template assets."""

    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".tex", ".bib"}
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def paperjury_significance(row: dict[str, Any]) -> str | None:
    significance = row.get("significance")
    if significance in {"major", "minor"}:
        return str(significance)
    severity = row.get("severity")
    if severity in {"blocker", "major"}:
        return "major"
    if severity in {"minor", "nit"}:
        return "minor"
    return None


def paperjury_ledger_facts(
    ledger: dict[str, Any], path: Path, errors: list[str]
) -> dict[str, int]:
    facts = {
        "active": 0,
        "active_major": 0,
        "active_minor": 0,
        "author_required": 0,
        "gate_blocking_major": 0,
        "unadjudicated_major": 0,
    }
    if ledger.get("schema") != 1:
        errors.append(f"{path}: expected the PaperJury ledger schema field schema=1")
    meta = ledger.get("meta")
    if not isinstance(meta, dict):
        errors.append(f"{path}: missing PaperJury meta object")
    elif not isinstance(meta.get("assignment_unverified", []), list):
        errors.append(f"{path}: meta.assignment_unverified must be a list")
    issues = ledger.get("issues")
    if not isinstance(issues, list):
        errors.append(f"{path}: issues must be a list")
        return facts
    seen_ids: set[str] = set()
    valid_statuses = PAPERJURY_ACTIVE | PAPERJURY_TERMINAL
    for index, raw in enumerate(issues, start=1):
        if not isinstance(raw, dict):
            errors.append(f"{path}: issue {index} is not an object")
            continue
        issue_id = str(raw.get("id", ""))
        if not re.fullmatch(r"I-\d+", issue_id) or issue_id in seen_ids:
            errors.append(f"{path}: issue {index} has an invalid or duplicate id")
        seen_ids.add(issue_id)
        significance = paperjury_significance(raw)
        if significance not in {"major", "minor"}:
            errors.append(f"{path}: {issue_id or index} has no valid significance")
        if raw.get("kind") not in {"mechanical", "substantive"}:
            errors.append(f"{path}: {issue_id or index} has no valid kind")
        status = str(raw.get("status", ""))
        if status not in valid_statuses:
            errors.append(f"{path}: {issue_id or index} has invalid status {status!r}")
            continue
        if status == "valid-fixable" and not str(raw.get("close_criterion", "")).strip():
            errors.append(f"{path}: {issue_id or index} is valid-fixable without a close criterion")
        if status == "dropped" and not str(raw.get("notes", "")).strip():
            errors.append(f"{path}: {issue_id or index} was silently dropped")
        raised_by = raw.get("raised_by", [])
        if not isinstance(raised_by, list) or not all(
            isinstance(item, str) and item.strip() for item in raised_by
        ):
            errors.append(f"{path}: {issue_id or index} has invalid raised_by provenance")
        if status in PAPERJURY_ACTIVE:
            facts["active"] += 1
            if significance == "major":
                facts["active_major"] += 1
            elif significance == "minor":
                facts["active_minor"] += 1
        if status == "author-required":
            facts["author_required"] += 1
        if significance == "major" and status in PAPERJURY_GATE_BLOCKING:
            facts["gate_blocking_major"] += 1
        if (
            significance == "major"
            and status in {"raised", "in-trial", "re-trial"}
            and raw.get("verdict") is None
        ):
            facts["unadjudicated_major"] += 1
    return facts


def render_paperjury_ledger(ledger: dict[str, Any], facts: dict[str, int]) -> str:
    """Render the official PaperJury v3 Markdown view for integrity checking."""

    def cell(value: Any) -> str:
        return str("" if value is None else value).replace("|", r"\|").replace("\r", " ").replace("\n", " ").strip()

    def status_cell(row: dict[str, Any]) -> str:
        tag = row.get("reason_code") or row.get("verdict")
        return cell(str(row.get("status", "")) + (f" ({tag})" if tag else ""))

    meta = ledger.get("meta") if isinstance(ledger.get("meta"), dict) else {}
    issues = [item for item in ledger.get("issues", []) if isinstance(item, dict)]
    rank = {"major": 0, "minor": 1}
    issues.sort(
        key=lambda row: (
            0 if str(row.get("status", "")) in PAPERJURY_ACTIVE else 1,
            rank.get(paperjury_significance(row) or "", 9),
            str(row.get("id", "")),
        )
    )
    lines = [
        "# Ledger (rendered view -- do not edit; source of truth is the .json)",
        "",
        f"Manuscript: {meta.get('manuscript') or '(unset)'} | venue: {meta.get('venue_family') or '(unset)'}",
    ]
    assignments = meta.get("assignment_unverified", [])
    if isinstance(assignments, list) and assignments:
        lines.append("Assignment-unverified reviewers: " + ", ".join(map(str, assignments)))
    lines.extend(
        [
            "",
            f"Active: {facts['active']} (major {facts['active_major']}, minor {facts['active_minor']}; "
            f"author-required {facts['author_required']}). Completion gate (0 gate-blocking active major): "
            f"{'PASS' if facts['gate_blocking_major'] == 0 else 'FAIL'} "
            f"(gate-blocking majors: {facts['gate_blocking_major']}).",
            "",
            "| id | sig | kind | status | section | summary | close_criterion | by | rounds |",
            "|----|-----|------|--------|---------|---------|-----------------|----|--------|",
        ]
    )
    for row in issues:
        rounds = "->".join(
            str(value)
            for value in (row.get("round_raised"), row.get("round_closed"))
            if value is not None
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(row.get("id")),
                    cell(paperjury_significance(row)),
                    cell(row.get("kind")),
                    status_cell(row),
                    cell(row.get("section")),
                    cell(row.get("summary")),
                    cell(row.get("close_criterion")),
                    cell(",".join(map(str, row.get("raised_by", [])))),
                    cell(rounds),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


PAPERJURY_FINDING_ID_FIELDS = ("id", "finding_id", "issue_id")
PAPERJURY_REVIEWER_SCHEMA_VERSION = 2
PAPERJURY_LEGACY_SIMILARITY_MINIMUM = 0.105
# One-time migration allowlist for the immutable MotionPlanner R1--R7 artifacts.
# Compatibility is granted only when both the review-visible snapshot and every
# reviewer file match these digests; a newly named ``round_07`` cannot opt in.
PAPERJURY_LEGACY_MIGRATION: dict[int, dict[str, Any]] = {
    1: {
        "snapshot_sha256": "07e970bae7d9f9c1f54a56d712c59132376bf3af2bbd8c6be84b1a8db779d9b6",
        "reviewer_files": {
            "reviewer_empirical.json": "d4276deef77e2373fa948646cf03553f9f43f7f505112302fc6be468166313f9",
            "reviewer_novelty.json": "1894053fa9d6cb6be1b75b4dc0cc4385ceea989c9d18fefdba504ea0044039ec",
            "reviewer_planning.json": "834d302ff4e74808db423c44b1562ccb7550e0a36d4bb6a7f90038af240452d3",
        },
    },
    2: {
        "snapshot_sha256": "6cf5c6ddfae8bbaed50d016b9d3602bf7539b89db51b7399bc6b1c982e074229",
        "reviewer_files": {
            "reviewer_claims.json": "41d05b6d176471ad89ec67aac5162fbfff663dbb7801a74c779f4c21c0ea7d44",
            "reviewer_design.json": "9569af0b018f793d0e84b2c44f950ef1cb254e4f97ecc4de4b6faa79ee47f424",
            "reviewer_repro.json": "1f5f993e04d002b83d0a2191714385cec086c5b57c1de861528aae514b54b8a3",
        },
    },
    3: {
        "snapshot_sha256": "1c73b7b20efe481a34608ac735413865d49cbf9e124ed3115b8601a2bc2f8996",
        "reviewer_files": {
            "reviewer_claims.json": "6ef1527b9fe33bc5a06b1c49195d6b9cc26714388ce5826d1f4f8e812c0a47c2",
            "reviewer_design.json": "8eb1f630d47abe8aa59bde0026f9168068daa62953096ccae7f123b6da6f3bf7",
            "reviewer_repro.json": "cd2bb6532a4f0d156bd785ce7a2b05195e7a1369ccc958f29c4872eb59639842",
        },
    },
    4: {
        "snapshot_sha256": "03153e00f732a896cff923a0249bb772e94390715305013e898ef62d7ae28da0",
        "reviewer_files": {
            "reviewer_claims.json": "8556451d3d74f7a90cdef2c52a042104cef537f9e9bf61d516c1462d7af9a0fb",
            "reviewer_design.json": "b7c915e20f7397b615fab6114be32296a53c4a2e306c3b05efa502f410473fb9",
            "reviewer_repro.json": "b8cc2e0841181f91ab597c433342122dc49dd31121f38b8da97c25f229eaef18",
        },
    },
    5: {
        "snapshot_sha256": "9dbbb842081fab37e0906c992707589fb550023fca05f6d5ab547289e9d6127a",
        "reviewer_files": {
            "reviewer_claims.json": "bc2e402b38957ebde871608a841585cb55c5c7d521acd77699c392f00868cabd",
            "reviewer_design.json": "10c14e509255e6fceb689cbc2defae2fbb9196638b07b05069c3e04c6373e3bc",
            "reviewer_repro.json": "f508bcdb30e9f975fcabd7f81d76244c94a78a510e1859930f3abccd42b1b26d",
        },
    },
    6: {
        "snapshot_sha256": "1e9451fdffc8b4ad59bb0a8e6b6288aa7d2487d25d92edfe8e5df203cedec332",
        "reviewer_files": {
            "reviewer_claims.json": "1ac0cdc80bc02b63847695b032ec2d48e2621d2061eaaf1d6798219f2cd1f59e",
            "reviewer_design.json": "9c8a368a91adaaa5f0672668a86e4fa45908abf5d0bf1fa0a7da9b4bfd02973b",
            "reviewer_repro.json": "955dc189a98a11cce8b822a7c55b194b2b9ad9096516916dbf59a998df1d6728",
        },
    },
    7: {
        "snapshot_sha256": "0ff9a93c3b055d7cc7beb049c67b87251e6c8eff0865dc19a8dbbc4aa28dd80c",
        "reviewer_files": {
            "reviewer_claims.json": "440988590bfc0d91ffcad3d46cf17bf7414563c49813863f44ebacb88ec4e6bd",
            "reviewer_design.json": "0c54a40a0abbee6cfe34f5f1e90d6c987511121e1478b2da6aa24785f043768f",
            "reviewer_repro.json": "e6798daefd568ca03cea0b218e560657270b7c79aaa1ae3064acf3e976ff5cd8",
        },
    },
}
PAPERJURY_LEDGER_PROVENANCE_FIELDS = (
    "passage_id",
    "references",
    "notes",
)
PAPERJURY_FINDING_TEXT_FIELDS = (
    "title",
    "issue",
    "finding",
    "evidence",
    "why_blocking",
    "required_fix",
)
PAPERJURY_BINDING_STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "among",
    "and",
    "are",
    "because",
    "been",
    "before",
    "being",
    "between",
    "but",
    "cannot",
    "could",
    "does",
    "each",
    "for",
    "from",
    "have",
    "into",
    "must",
    "not",
    "only",
    "other",
    "should",
    "that",
    "the",
    "their",
    "then",
    "these",
    "this",
    "through",
    "under",
    "use",
    "when",
    "which",
    "while",
    "with",
    "without",
    "would",
}


def paperjury_finding_identity(
    round_number: int,
    reviewer_id: str,
    index: int,
    finding: Any,
) -> dict[str, Any] | None:
    """Derive a stable reviewer-scoped identity from an immutable finding."""

    external_id: str | None = None
    if isinstance(finding, str):
        text = finding.strip()
        canonical: Any = text
    elif isinstance(finding, dict):
        for field in PAPERJURY_FINDING_ID_FIELDS:
            value = str(finding.get(field, "")).strip()
            if value:
                external_id = value
                break
        text = " ".join(
            str(finding.get(field, "")).strip()
            for field in PAPERJURY_FINDING_TEXT_FIELDS
            if str(finding.get(field, "")).strip()
        )
        canonical = finding
    else:
        return None
    if not text:
        return None
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    local_identity = external_id or f"sha256:{fingerprint}"
    return {
        "identity": f"round={round_number};reviewer={reviewer_id};finding={local_identity}",
        "external_id": external_id,
        "fingerprint": fingerprint,
        "text": text,
        "index": index,
    }


def validate_paperjury_major_finding(
    finding: Any,
    reviewer_path: Path,
    index: int,
    errors: list[str],
    snapshot: Path | None = None,
) -> str | None:
    """Validate one schema-v2 major and return its explicit stable finding ID."""

    label = f"{reviewer_path}: blocking finding {index}"
    if not isinstance(finding, dict):
        errors.append(f"{label} must be an object under reviewer schema v2")
        return None
    finding_id = next(
        (
            str(finding.get(field, "")).strip()
            for field in PAPERJURY_FINDING_ID_FIELDS
            if str(finding.get(field, "")).strip()
        ),
        "",
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}", finding_id):
        errors.append(f"{label} requires an explicit stable id")
        finding_id = ""
    raw_evidence = finding.get("evidence_anchor")
    if not (
        isinstance(raw_evidence, str) and raw_evidence.strip()
    ) and not (
        isinstance(raw_evidence, list)
        and any(str(item).strip() for item in raw_evidence)
    ):
        raw_evidence = finding.get("evidence")
    if isinstance(raw_evidence, list):
        evidence = "; ".join(
            str(item).strip() for item in raw_evidence if str(item).strip()
        )
    else:
        evidence = raw_evidence.strip() if isinstance(raw_evidence, str) else ""
    file_locator = re.compile(
        r"(?<![A-Za-z0-9_./\\-])"
        r"(?P<path>[A-Za-z0-9_./\\-]+\.(?:tex|bib|md|csv|json|ya?ml))"
        r":(?P<start>\d+)(?:(?:--?|\.\.)(?P<end>\d+))?",
        re.IGNORECASE,
    )
    ref_locator = re.compile(
        r"\\(?:ref|autoref|cref|Cref)\{(?P<label>[A-Za-z0-9_.:-]+)\}",
        re.IGNORECASE,
    )
    bare_label_locator = re.compile(
        r"\b(?P<label>(?:fig|tab|sec|eq|alg|lst|app):[A-Za-z0-9_.:-]+)\b",
        re.IGNORECASE,
    )
    file_matches = list(file_locator.finditer(evidence))
    label_tokens = {
        match.group("label") for match in ref_locator.finditer(evidence)
    } | {
        match.group("label") for match in bare_label_locator.finditer(evidence)
    }
    if not evidence:
        errors.append(f"{label} requires a non-empty evidence anchor")
    elif not file_matches and not label_tokens:
        errors.append(
            f"{label} evidence must contain an exact file:line/range or LaTeX label/ref anchor"
        )
    elif snapshot is not None:
        snapshot_root = snapshot.resolve()
        valid_anchor = False
        for match in file_matches:
            relative_text = match.group("path").replace("\\", "/")
            relative = Path(relative_text)
            candidates = [snapshot_root / relative]
            if relative.parts and relative.parts[0].casefold() == "paper":
                candidates.append(snapshot_root.joinpath(*relative.parts[1:]))
            resolved_file: Path | None = None
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                    resolved.relative_to(snapshot_root)
                except (OSError, ValueError):
                    continue
                if resolved.is_file():
                    resolved_file = resolved
                    break
            if resolved_file is None:
                errors.append(
                    f"{label} evidence path does not resolve inside the frozen snapshot: "
                    f"{match.group('path')}"
                )
                continue
            try:
                start_line = int(match.group("start"))
                end_line = int(match.group("end") or match.group("start"))
            except ValueError:
                start_line = end_line = 0
            line_count = len(
                resolved_file.read_text(encoding="utf-8", errors="replace").splitlines()
            )
            if start_line < 1 or end_line < start_line or end_line > line_count:
                errors.append(
                    f"{label} evidence line range is outside the frozen snapshot file: "
                    f"{match.group(0)} (file has {line_count} lines)"
                )
                continue
            valid_anchor = True
        if label_tokens:
            tex_sources = [
                path.read_text(encoding="utf-8", errors="replace")
                for path in snapshot_root.rglob("*.tex")
                if path.is_file()
            ]
            for token in sorted(label_tokens):
                label_pattern = re.compile(rf"\\label\{{{re.escape(token)}\}}")
                if any(label_pattern.search(source) for source in tex_sources):
                    valid_anchor = True
                else:
                    errors.append(
                        f"{label} evidence label does not exist in the frozen snapshot: {token}"
                    )
        if not valid_anchor:
            errors.append(f"{label} has no resolvable exact anchor in the frozen snapshot")
    if not str(finding.get("required_fix", "")).strip():
        errors.append(f"{label} requires a non-empty required_fix")
    return finding_id or None


def _paperjury_issue_order(row: dict[str, Any]) -> tuple[int, str]:
    match = re.fullmatch(r"I-(\d+)", str(row.get("id", "")))
    return (int(match.group(1)), str(row.get("id", ""))) if match else (10**9, str(row.get("id", "")))


def _paperjury_provenance_contains(row: dict[str, Any], token: str) -> bool:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_.-]){re.escape(token)}(?![A-Za-z0-9_.-])",
        re.IGNORECASE,
    )
    return any(
        pattern.search(str(row.get(field, ""))) is not None
        for field in PAPERJURY_LEDGER_PROVENANCE_FIELDS
    )


def _paperjury_binding_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", value.casefold())
        if len(token) >= 3 and token not in PAPERJURY_BINDING_STOPWORDS
    }


def _paperjury_legacy_similarity(finding_text: str, row: dict[str, Any]) -> float:
    left = _paperjury_binding_tokens(finding_text)
    right = _paperjury_binding_tokens(
        " ".join(
            str(row.get(field, ""))
            for field in ("section", "summary", "evidence_anchor", "close_criterion", "notes")
        )
    )
    return len(left & right) / len(left | right) if left and right else 0.0


def paperjury_bind_blocking_findings(
    ledger: dict[str, Any],
    round_number: int,
    reviewer_id: str,
    findings: list[Any],
    reviewer_path: Path,
    errors: list[str],
    *,
    allow_legacy: bool = False,
) -> list[dict[str, Any]]:
    """Bind every reviewer blocker to one major ledger row from that reviewer/round."""

    identities: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    for index, finding in enumerate(findings, start=1):
        identity = paperjury_finding_identity(round_number, reviewer_id, index, finding)
        if identity is None:
            errors.append(f"{reviewer_path}: blocking finding {index} has no stable identity text")
            continue
        if identity["identity"] in seen_identities:
            errors.append(f"{reviewer_path}: duplicate blocking finding identity {identity['identity']}")
            continue
        seen_identities.add(identity["identity"])
        identities.append(identity)

    rows = []
    for raw in ledger.get("issues", []) if isinstance(ledger.get("issues"), list) else []:
        if not isinstance(raw, dict) or paperjury_significance(raw) != "major":
            continue
        try:
            raised_round = int(raw.get("round_raised", -1))
        except (TypeError, ValueError):
            continue
        raised_by = raw.get("raised_by", [])
        if (
            raised_round == round_number
            and isinstance(raised_by, list)
            and reviewer_id.casefold() in {str(value).casefold() for value in raised_by}
        ):
            rows.append(raw)
    rows.sort(key=_paperjury_issue_order)

    bindings: list[dict[str, Any]] = []
    used_rows: set[str] = set()
    legacy: list[dict[str, Any]] = []
    for identity in identities:
        token = identity["external_id"]
        if token:
            candidates = [row for row in rows if _paperjury_provenance_contains(row, token)]
            if len(candidates) > 1:
                errors.append(
                    f"{reviewer_path}: blocker {identity['identity']} must bind to exactly one "
                    f"major LEDGER.json row from round {round_number}; found {len(candidates)}"
                )
                continue
            if len(candidates) == 1:
                ledger_id = str(candidates[0].get("id", ""))
                if ledger_id in used_rows:
                    errors.append(
                        f"{reviewer_path}: blockers reuse ledger row {ledger_id}; finding identities must be one-to-one per reviewer"
                    )
                    continue
                used_rows.add(ledger_id)
                bindings.append(
                    {"finding_identity": identity["identity"], "ledger_issue_id": ledger_id, "mode": "explicit-id"}
                )
                continue
            if allow_legacy:
                # Frozen pre-v2 ledgers sometimes retained the stable ID only in
                # the reviewer artifact. The finite migration path below is never
                # available to a schema-v2/new round.
                legacy.append(identity)
            else:
                errors.append(
                    f"{reviewer_path}: blocker {identity['identity']} has no LEDGER.json row with "
                    "that exact finding id and round/reviewer provenance"
                )
            continue

        fingerprint_token = f"sha256:{identity['fingerprint']}"
        fingerprint_rows = [
            row for row in rows if _paperjury_provenance_contains(row, fingerprint_token)
        ]
        if len(fingerprint_rows) == 1:
            ledger_id = str(fingerprint_rows[0].get("id", ""))
            if ledger_id not in used_rows:
                used_rows.add(ledger_id)
                bindings.append(
                    {
                        "finding_identity": identity["identity"],
                        "ledger_issue_id": ledger_id,
                        "mode": "content-fingerprint",
                    }
                )
                continue
        elif len(fingerprint_rows) > 1:
            errors.append(
                f"{reviewer_path}: blocker {identity['identity']} has ambiguous fingerprint provenance"
            )
            continue
        if allow_legacy:
            legacy.append(identity)
        else:
            errors.append(
                f"{reviewer_path}: blocker {identity['identity']} requires an explicit stable "
                "finding id and exact LEDGER.json provenance"
            )

    # The migration-only branch is restricted by the caller to the immutable
    # pre-v2 round range. New reviewers cannot use semantic binding.
    scored_pairs: list[tuple[float, str, str, dict[str, Any], dict[str, Any]]] = []
    for identity in legacy:
        for row in rows:
            ledger_id = str(row.get("id", ""))
            if ledger_id in used_rows:
                continue
            score = _paperjury_legacy_similarity(str(identity["text"]), row)
            scored_pairs.append(
                (-score, str(identity["identity"]), ledger_id, identity, row)
            )
    scored_pairs.sort(key=lambda item: (item[0], item[1], _paperjury_issue_order(item[4])))
    assigned_legacy: set[str] = set()
    for negative_score, _, ledger_id, identity, _ in scored_pairs:
        identity_key = str(identity["identity"])
        if identity_key in assigned_legacy or ledger_id in used_rows:
            continue
        score = -negative_score
        if score < PAPERJURY_LEGACY_SIMILARITY_MINIMUM:
            continue
        assigned_legacy.add(identity_key)
        used_rows.add(ledger_id)
        bindings.append(
            {
                "finding_identity": identity_key,
                "ledger_issue_id": ledger_id,
                "mode": (
                    "legacy-semantic-external-id"
                    if identity.get("external_id")
                    else "legacy-semantic"
                ),
                "similarity": round(score, 4),
            }
        )
    for identity in legacy:
        if str(identity["identity"]) not in assigned_legacy:
            errors.append(
                f"{reviewer_path}: blocker {identity['identity']} has no matching major "
                f"LEDGER.json row with the same round/reviewer provenance"
            )
    return sorted(bindings, key=lambda item: item["finding_identity"])


def validate_paperjury_review(project: Path, errors: list[str]) -> None:
    root = project / "qa/paperjury"
    ledger_json = root / "LEDGER.json"
    ledger_markdown = root / "LEDGER.md"
    final_path = root / "final_report.json"
    ledger: dict[str, Any] = {}
    ledger_facts = {
        "gate_blocking_major": -1,
        "unadjudicated_major": -1,
    }
    if not ledger_json.exists() or not ledger_markdown.exists():
        errors.append("qa/paperjury: missing PaperJury LEDGER.json or LEDGER.md")
    else:
        ledger = read_json(ledger_json, errors)
        ledger_facts = paperjury_ledger_facts(ledger, ledger_json, errors)
        expected_markdown = render_paperjury_ledger(ledger, ledger_facts).replace("\r\n", "\n")
        actual_markdown = ledger_markdown.read_text(encoding="utf-8", errors="replace").replace(
            "\r\n", "\n"
        )
        if actual_markdown != expected_markdown:
            errors.append("qa/paperjury/LEDGER.md: rendered view is stale or was hand-edited")
    if not final_path.exists():
        errors.append("qa/paperjury/final_report.json: missing adversarial review result")
        return
    report = read_json(final_path, errors)
    if report.get("status") != "pass" or report.get("mode") != "review":
        errors.append("qa/paperjury/final_report.json: review status must be pass")
    if report.get("author_authorized") is not True:
        errors.append("qa/paperjury/final_report.json: author authorization is not recorded")
    try:
        rounds = int(report.get("rounds", 0))
        reviewer_count = int(report.get("reviewer_count", 0))
        blocking_major = int(report.get("gate_blocking_major", -1))
        unadjudicated_major = int(report.get("unadjudicated_major", -1))
    except (TypeError, ValueError):
        rounds = reviewer_count = 0
        blocking_major = unadjudicated_major = -1
    if rounds < 2:
        errors.append("qa/paperjury/final_report.json: at least two isolated review rounds are required")
    if reviewer_count < 3:
        errors.append("qa/paperjury/final_report.json: at least three reviewer lenses are required")
    if report.get("converged") is not True:
        errors.append("qa/paperjury/final_report.json: adversarial review has not converged")
    if blocking_major != 0 or unadjudicated_major != 0:
        errors.append("qa/paperjury/final_report.json: blocking or unadjudicated major issues remain")
    if blocking_major != ledger_facts.get("gate_blocking_major"):
        errors.append("qa/paperjury/final_report.json: gate count does not match LEDGER.json")
    if unadjudicated_major != ledger_facts.get("unadjudicated_major"):
        errors.append("qa/paperjury/final_report.json: unadjudicated count does not match LEDGER.json")
    if report.get("source_sha256") != source_tree_sha256(project / "paper"):
        errors.append("qa/paperjury/final_report.json: review is stale for the current manuscript")
    completed_rounds = sorted(
        path for path in root.glob("round_[0-9][0-9]") if path.is_dir()
    )
    v2_cutover_rounds: set[int] = set()
    for candidate_round in completed_rounds:
        candidate_reviewers = sorted(candidate_round.glob("reviewer_*.json"))
        if len(candidate_reviewers) < 3:
            continue
        candidate_schemas: list[Any] = []
        for candidate_reviewer in candidate_reviewers:
            try:
                candidate_payload = json.loads(
                    candidate_reviewer.read_text(encoding="utf-8", errors="replace")
                )
            except (OSError, json.JSONDecodeError):
                candidate_payload = {}
            candidate_schemas.append(
                candidate_payload.get("schema_version")
                if isinstance(candidate_payload, dict)
                else None
            )
        if all(
            isinstance(schema, int)
            and not isinstance(schema, bool)
            and schema == PAPERJURY_REVIEWER_SCHEMA_VERSION
            for schema in candidate_schemas
        ):
            v2_cutover_rounds.add(int(candidate_round.name.split("_")[-1]))
    verified_rounds: list[dict[str, Any]] = []
    for round_path in completed_rounds:
        round_number = int(round_path.name.split("_")[-1])
        snapshot = round_path / "snapshot"
        manifest_path = round_path / "round_report.json"
        if not snapshot.is_dir() or not manifest_path.is_file():
            errors.append(f"{round_path}: missing frozen snapshot or round_report.json")
            continue
        manifest = read_json(manifest_path, errors)
        reviewer_paths = sorted(round_path.glob("reviewer_*.json"))
        snapshot_hash = paperjury_review_tree_sha256(snapshot)
        raw_reviewer_hashes = {
            reviewer_path.name: sha256_file(reviewer_path)
            for reviewer_path in reviewer_paths
        }
        legacy_expected = PAPERJURY_LEGACY_MIGRATION.get(round_number)
        legacy_round_allowed = bool(
            legacy_expected
            and legacy_expected.get("snapshot_sha256") == snapshot_hash
            and legacy_expected.get("reviewer_files") == raw_reviewer_hashes
        )
        reviewers: list[dict[str, Any]] = []
        reviewer_hashes: dict[str, str] = {}
        reviewer_ids: set[str] = set()
        total_blocking = 0
        total_minor = 0
        all_pass = True
        finding_bindings: list[dict[str, Any]] = []
        for reviewer_path in reviewer_paths:
            reviewer = read_json(reviewer_path, errors)
            reviewer_id = str(reviewer.get("reviewer_id", "")).strip()
            status = reviewer.get("status")
            reviewer_schema = reviewer.get("schema_version")
            current_schema = (
                isinstance(reviewer_schema, int)
                and not isinstance(reviewer_schema, bool)
                and reviewer_schema == PAPERJURY_REVIEWER_SCHEMA_VERSION
            )
            legacy_schema = (
                legacy_round_allowed
                and (
                    reviewer_schema is None
                    or (
                        isinstance(reviewer_schema, int)
                        and not isinstance(reviewer_schema, bool)
                        and reviewer_schema == 1
                    )
                )
                and any(cutover_round > round_number for cutover_round in v2_cutover_rounds)
            )
            if not current_schema and not legacy_schema:
                errors.append(
                    f"{reviewer_path}: reviewer schema_version must be "
                    f"{PAPERJURY_REVIEWER_SCHEMA_VERSION}; legacy compatibility requires an "
                    "exact snapshot/reviewer digest in the built-in migration allowlist"
                )
            majors = reviewer.get("blocking_major_findings")
            if majors is None and legacy_schema:
                majors = reviewer.get("major_findings")
            minors = reviewer.get("minor_findings", [])
            if (
                not reviewer_id
                or reviewer_id in reviewer_ids
                or status not in {"pass", "revise"}
                or not isinstance(majors, list)
                or not isinstance(minors, list)
                or not isinstance(reviewer.get("queued_empirical", []), list)
                or not str(reviewer.get("verdict_rationale", "")).strip()
            ):
                errors.append(f"{reviewer_path}: invalid isolated reviewer report schema")
                continue
            major_ids: set[str] = set()
            if current_schema:
                for finding_index, finding in enumerate(majors, start=1):
                    finding_id = validate_paperjury_major_finding(
                        finding, reviewer_path, finding_index, errors, snapshot
                    )
                    if finding_id and finding_id in major_ids:
                        errors.append(
                            f"{reviewer_path}: duplicate blocking finding id {finding_id}"
                        )
                    if finding_id:
                        major_ids.add(finding_id)
            reviewer_ids.add(reviewer_id)
            reviewer_hashes[reviewer_path.name] = sha256_file(reviewer_path)
            total_blocking += len(majors)
            total_minor += len(minors)
            all_pass = all_pass and status == "pass" and not majors and not minors
            finding_bindings.extend(
                paperjury_bind_blocking_findings(
                    ledger,
                    round_number,
                    reviewer_id,
                    majors,
                    reviewer_path,
                    errors,
                    allow_legacy=legacy_schema,
                )
            )
            reviewers.append(reviewer)
        derived_status = "pass" if all_pass and len(reviewers) >= 3 else "revise"
        if manifest.get("schema_version") != 1 or manifest.get("round") != round_number:
            errors.append(f"{manifest_path}: invalid round manifest identity")
        if manifest.get("snapshot_sha256") != snapshot_hash:
            errors.append(f"{manifest_path}: frozen snapshot hash mismatch")
        if manifest.get("reviewer_files") != reviewer_hashes:
            errors.append(f"{manifest_path}: reviewer file hashes are stale or incomplete")
        if manifest.get("reviewer_count") != len(reviewers) or len(reviewers) < 3:
            errors.append(f"{manifest_path}: each round requires three valid isolated reviewers")
        if manifest.get("blocking_major_findings") != total_blocking:
            errors.append(f"{manifest_path}: blocking-major count does not match reviewer reports")
        if manifest.get("status") != derived_status:
            errors.append(f"{manifest_path}: status does not match reviewer reports")
        verified_rounds.append(
            {
                "round": round_number,
                "reviewer_count": len(reviewers),
                "status": derived_status,
                "snapshot_sha256": snapshot_hash,
                "minor_findings": total_minor,
                "finding_bindings": finding_bindings,
            }
        )
    if len(verified_rounds) < 2:
        errors.append("qa/paperjury: fewer than two verified isolated review rounds")
    else:
        final_round = verified_rounds[-1]
        if final_round["status"] != "pass":
            errors.append("qa/paperjury: final clean round did not pass all reviewer lenses")
        current_review_hash = paperjury_review_tree_sha256(project / "paper")
        if final_round["snapshot_sha256"] != current_review_hash:
            errors.append("qa/paperjury: final clean-round snapshot is stale")
        if report.get("review_snapshot_sha256") != current_review_hash:
            errors.append("qa/paperjury/final_report.json: review snapshot hash is stale")
        if rounds != len(verified_rounds):
            errors.append("qa/paperjury/final_report.json: round count is not derived from artifacts")
        if reviewer_count != final_round["reviewer_count"]:
            errors.append("qa/paperjury/final_report.json: reviewer count is not derived from final round")


def validate_layout_report_status(report: dict[str, Any], errors: list[str]) -> None:
    if report.get("status") != "pass":
        errors.append("qa/layout_report.json: LaTeX build or page check did not pass")
        return
    if report.get("errors") != []:
        errors.append("qa/layout_report.json: passing report must contain errors=[]")
    if report.get("returncode") != 0:
        errors.append("qa/layout_report.json: passing report must record compiler returncode=0")


def validate_compiler_log_binding(
    project: Path, report: dict[str, Any], errors: list[str]
) -> Path | None:
    build_root = (project / "build").resolve()
    build_value = Path(str(report.get("build_dir", ""))).expanduser()
    try:
        resolved_build = build_value.resolve()
        resolved_build.relative_to(build_root)
    except ValueError:
        errors.append("qa/layout_report.json: build_dir must stay under the project build directory")
        resolved_build = None
    if report.get("fresh_build") is not True:
        errors.append("qa/layout_report.json: compile was not recorded as a fresh build")
    removed = report.get("fresh_build_removed_artifacts")
    if (
        not isinstance(removed, list)
        or not all(isinstance(item, str) and item in CORE_BUILD_ARTIFACTS for item in removed)
        or len(removed) != len(set(removed))
    ):
        errors.append("qa/layout_report.json: fresh-build cleanup record is missing or invalid")

    log_value = report.get("compiler_log")
    log_path = Path(str(log_value)).expanduser() if log_value else None
    if log_path is None or not log_path.is_file():
        errors.append("qa/layout_report.json: fresh compiler main.log is missing")
        return None
    resolved_log = log_path.resolve()
    try:
        resolved_log.relative_to(build_root)
    except ValueError:
        errors.append("qa/layout_report.json: compiler log must stay under the project build directory")
        return None
    if resolved_build is None or resolved_log != (resolved_build / "main.log").resolve():
        errors.append("qa/layout_report.json: compiler log is not build_dir/main.log")
        return None
    expected_hash = str(report.get("compiler_log_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or sha256_file(log_path) != expected_hash:
        errors.append("qa/layout_report.json: compiler log hash mismatch")
        return None
    return log_path


def validate_aux_binding(
    project: Path, report: dict[str, Any], errors: list[str]
) -> Path | None:
    """Bind every page-placement claim to the current compiled ``main.aux``."""

    build_root = (project / "build").resolve()
    build_value = str(report.get("build_dir", "")).strip()
    if not build_value:
        errors.append("qa/layout_report.json: build_dir is missing for AUX binding")
        return None
    resolved_build = Path(build_value).expanduser().resolve()
    try:
        resolved_build.relative_to(build_root)
    except ValueError:
        errors.append("qa/layout_report.json: build_dir must stay under the project build directory")
        return None
    if resolved_build != build_root:
        errors.append("qa/layout_report.json: AUX binding requires the canonical project build directory")
        return None

    aux_value = str(report.get("aux", "")).strip()
    if not aux_value:
        errors.append("qa/layout_report.json: compiled AUX path is missing")
        return None
    aux_path = Path(aux_value).expanduser()
    if not aux_path.is_file():
        errors.append("qa/layout_report.json: compiled AUX file is missing")
        return None
    resolved_aux = aux_path.resolve()
    try:
        resolved_aux.relative_to(build_root)
    except ValueError:
        errors.append("qa/layout_report.json: compiled AUX must stay under the project build directory")
        return None
    if resolved_aux != (resolved_build / "main.aux").resolve():
        errors.append("qa/layout_report.json: compiled AUX is not build_dir/main.aux")
        return None
    expected_hash = str(report.get("aux_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or sha256_file(aux_path) != expected_hash:
        errors.append("qa/layout_report.json: compiled AUX hash mismatch")
        return None
    return aux_path


def _require_exact_layout_field(
    report: dict[str, Any], field: str, expected: Any, errors: list[str]
) -> None:
    if report.get(field) != expected:
        errors.append(
            f"qa/layout_report.json: {field} does not match the current source/AUX/PDF audit"
        )


def validate_recomputed_layout_audits(
    project: Path,
    report: dict[str, Any],
    float_inventory: dict[str, Any],
    aux_path: Path | None,
    pdf_path: Path | None,
    errors: list[str],
) -> None:
    """Recompute all placement/geometry gates instead of trusting report summaries."""

    column_report = report.get("column_mode_audit")
    requested = column_report.get("requested") if isinstance(column_report, dict) else None
    if requested not in {"auto", "1", "2"}:
        errors.append("qa/layout_report.json: column-mode request is missing or invalid")
        requested = "auto"
    try:
        current_column_audit = document_column_mode_audit(project / "paper", str(requested))
    except (OSError, ValueError) as exc:
        errors.append(f"qa/layout_report.json: cannot recompute document column mode: {exc}")
        return
    _require_exact_layout_field(report, "column_mode_audit", current_column_audit, errors)
    column_mode = int(current_column_audit["mode"])
    _require_exact_layout_field(report, "column_mode", column_mode, errors)

    if aux_path is None:
        return
    all_records = list(float_inventory.get("all_records", []))
    body_labels = list(float_inventory.get("labels", []))
    all_labels = list(float_inventory.get("all_labels", []))
    body_pages = {label: aux_label_page(aux_path, label) for label in body_labels}
    all_pages = {label: aux_label_page(aux_path, label) for label in all_labels}
    conclusion_page = aux_label_page(aux_path, "idea2paper:start-conclusion")
    end_body_page = aux_label_page(aux_path, "idea2paper:end-body")
    end_exempt_page = aux_label_page(aux_path, "idea2paper:end-exempt")
    end_references_page = aux_label_page(aux_path, "idea2paper:end-references")
    appendix_start_page = aux_label_page(aux_path, "idea2paper:start-appendix")
    current_body_pages = (
        end_references_page if report.get("references_counted") is True else end_body_page
    )
    conclusion_record = aux_label_record(aux_path, "idea2paper:start-conclusion")
    end_body_record = aux_label_record(aux_path, "idea2paper:end-body")
    conclusion_before_end_body = (
        conclusion_record[0] is not None
        and end_body_record[0] is not None
        and conclusion_record[0] <= end_body_record[0]
        and conclusion_record[1] is not None
        and end_body_record[1] is not None
        and conclusion_record[1] < end_body_record[1]
    )
    _, body_tail = body_float_tail_report(aux_path, body_labels, conclusion_page)

    exact_aux_fields = {
        "body_pages": current_body_pages,
        "conclusion_page": conclusion_page,
        "end_body_page": end_body_page,
        "end_exempt_page": end_exempt_page,
        "appendix_start_page": appendix_start_page,
        "conclusion_before_end_body": conclusion_before_end_body,
        "body_float_pages": body_pages,
        "all_float_pages": all_pages,
        "missing_body_float_aux_labels": sorted(
            label for label, page in body_pages.items() if page is None
        ),
        "missing_all_float_aux_labels": sorted(
            label for label, page in all_pages.items() if page is None
        ),
        "body_float_tail_violations": body_tail,
    }
    for field, expected in exact_aux_fields.items():
        _require_exact_layout_field(report, field, expected, errors)

    if pdf_path is None:
        return
    preliminary = float_distribution_audit(
        all_records, all_pages, appendix_start_page, None, column_mode
    )
    try:
        whitespace = rendered_whitespace_audit(
            pdf_path, preliminary["page_float_counts"], column_mode
        )
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append(f"qa/layout_report.json: cannot recompute rendered whitespace audit: {exc}")
        return
    total_pages = int(whitespace["page_count"])
    distribution = float_distribution_audit(
        all_records, all_pages, appendix_start_page, total_pages, column_mode
    )
    _require_exact_layout_field(report, "total_pages", total_pages, errors)
    for field, expected in distribution.items():
        _require_exact_layout_field(report, field, expected, errors)
    rendered_fields = {
        "rendered_column_inference": whitespace["rendered_column_inference"],
        "rendered_page_geometry": whitespace["pages"],
        "whitespace_thresholds": whitespace["thresholds"],
        "whitespace_violations": whitespace["whitespace_violations"],
        "float_reading_order_violations": whitespace.get("float_reading_order_violations", []),
        "media_box_overflows": whitespace["media_box_overflows"],
    }
    for field, expected in rendered_fields.items():
        _require_exact_layout_field(report, field, expected, errors)


def _normalized_overfull_box_list(
    value: Any, field: str, errors: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"qa/layout_report.json: {field} must be a list")
        return []
    normalized: list[dict[str, Any]] = []
    required = {"axis", "dimension", "excess_pt", "context", "material"}
    for index, item in enumerate(value):
        label = f"qa/layout_report.json: {field}[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"{label} has invalid fields")
            continue
        axis = item.get("axis")
        dimension = item.get("dimension")
        excess = item.get("excess_pt")
        context = item.get("context")
        material = item.get("material")
        valid = True
        if axis not in {"h", "v"}:
            errors.append(f"{label}.axis must be h or v")
            valid = False
        if dimension not in {"wide", "high"} or (
            axis in {"h", "v"} and dimension != {"h": "wide", "v": "high"}[axis]
        ):
            errors.append(f"{label}.dimension is inconsistent with axis")
            valid = False
        if (
            isinstance(excess, bool)
            or not isinstance(excess, (int, float))
            or not math.isfinite(float(excess))
            or float(excess) < 0.0
        ):
            errors.append(f"{label}.excess_pt must be a finite non-negative number")
            valid = False
        if not isinstance(context, str) or "\n" in context or "\r" in context:
            errors.append(f"{label}.context must be a single-line string")
            valid = False
        if not isinstance(material, bool):
            errors.append(f"{label}.material must be boolean")
            valid = False
        if not valid:
            continue
        expected_material = float(excess) > MATERIAL_OVERFULL_PT
        if material is not expected_material:
            errors.append(f"{label}.material does not match the fixed 2pt threshold")
        normalized.append(
            {
                "axis": axis,
                "dimension": dimension,
                "excess_pt": float(excess),
                "context": context,
                "material": expected_material,
            }
        )
    return normalized


def validate_overfull_box_report(
    report: dict[str, Any], errors: list[str], compiler_log: Path | None = None
) -> None:
    if report.get("overfull_box_threshold_pt") != MATERIAL_OVERFULL_PT:
        errors.append("qa/layout_report.json: material overfull-box threshold is missing or altered")
    all_boxes = _normalized_overfull_box_list(report.get("overfull_boxes"), "overfull_boxes", errors)
    reported_material = _normalized_overfull_box_list(
        report.get("material_overfull_boxes"), "material_overfull_boxes", errors
    )
    derived_material = [item for item in all_boxes if item["material"]]
    if reported_material != derived_material:
        errors.append(
            "qa/layout_report.json: material_overfull_boxes is not exactly derived from overfull_boxes"
        )
    if compiler_log is not None:
        actual = latex_overfull_boxes(
            compiler_log.read_text(encoding="utf-8", errors="replace")
        )
        if all_boxes != actual:
            errors.append("qa/layout_report.json: overfull-box diagnostics do not match compiler log")
    if derived_material:
        errors.append("qa/layout_report.json: manuscript contains clipped/material overfull boxes")


def validate_tex_fuzz_binding(
    paper: Path, report: dict[str, Any], errors: list[str]
) -> None:
    try:
        current = tex_fuzz_register_uses(paper)
    except (OSError, ValueError) as exc:
        errors.append(f"qa/layout_report.json: cannot audit TeX fuzz registers: {exc}")
        return
    if report.get("tex_fuzz_register_uses") != current:
        errors.append("qa/layout_report.json: TeX fuzz-register audit is stale or incomplete")
    if current:
        errors.append("qa/layout_report.json: active manuscript graph uses forbidden \\hfuzz/\\vfuzz")


def _normalized_media_box_overflow_list(
    value: Any, field: str, errors: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"qa/layout_report.json: {field} must be a list")
        return []
    required = {"page", "box_index", "kind", "edge", "excess_pt", "text"}
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        label = f"qa/layout_report.json: {field}[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"{label} has invalid fields")
            continue
        page = item.get("page")
        box_index = item.get("box_index")
        kind = item.get("kind")
        edge = item.get("edge")
        excess = item.get("excess_pt")
        text = item.get("text")
        valid = True
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            errors.append(f"{label}.page must be a positive integer")
            valid = False
        if isinstance(box_index, bool) or not isinstance(box_index, int) or box_index < 0:
            errors.append(f"{label}.box_index must be a non-negative integer")
            valid = False
        if kind not in {"text", "image", "content"}:
            errors.append(f"{label}.kind is invalid")
            valid = False
        if edge not in {"left", "right", "top", "bottom"}:
            errors.append(f"{label}.edge is invalid")
            valid = False
        if (
            isinstance(excess, bool)
            or not isinstance(excess, (int, float))
            or not math.isfinite(float(excess))
            or float(excess) <= MEDIA_BOX_OVERFLOW_PT
        ):
            errors.append(f"{label}.excess_pt must be above the fixed 2pt threshold")
            valid = False
        if not isinstance(text, str) or len(text) > 160:
            errors.append(f"{label}.text must be a string of at most 160 characters")
            valid = False
        if valid:
            normalized.append(
                {
                    "page": page,
                    "box_index": box_index,
                    "kind": kind,
                    "edge": edge,
                    "excess_pt": float(excess),
                    "text": text,
                }
            )
    return normalized


def validate_media_box_overflow_report(
    report: dict[str, Any], errors: list[str], pdf_path: Path | None = None
) -> None:
    if report.get("media_box_overflow_threshold_pt") != MEDIA_BOX_OVERFLOW_PT:
        errors.append("qa/layout_report.json: media-box overflow threshold is missing or altered")
    thresholds = report.get("whitespace_thresholds")
    if not isinstance(thresholds, dict) or thresholds.get(
        "media_box_overflow_maximum_pt"
    ) != MEDIA_BOX_OVERFLOW_PT:
        errors.append("qa/layout_report.json: rendered media-box threshold is missing or altered")
    reported = _normalized_media_box_overflow_list(
        report.get("media_box_overflows"), "media_box_overflows", errors
    )
    pages = report.get("rendered_page_geometry")
    flattened_raw: list[Any] = []
    if not isinstance(pages, list):
        errors.append("qa/layout_report.json: rendered page geometry must be a list")
    else:
        for page_index, page in enumerate(pages):
            if not isinstance(page, dict) or not isinstance(page.get("media_box_overflows"), list):
                errors.append(
                    f"qa/layout_report.json: rendered_page_geometry[{page_index}] lacks media-box audit"
                )
                continue
            flattened_raw.extend(page["media_box_overflows"])
    flattened = _normalized_media_box_overflow_list(
        flattened_raw, "rendered_page_geometry.media_box_overflows", errors
    )
    if reported != flattened:
        errors.append("qa/layout_report.json: media-box overflow summary is stale or incomplete")
    if pdf_path is not None:
        try:
            current = rendered_media_box_overflows(pdf_path)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"qa/layout_report.json: cannot recompute PDF media-box audit: {exc}")
        else:
            if reported != current:
                errors.append("qa/layout_report.json: media-box audit does not match compiled PDF")
    if reported:
        errors.append("qa/layout_report.json: rendered content exceeds the PDF media box")


def validate_layout_and_review(
    project: Path,
    venue: dict[str, Any],
    mode: str,
    errors: list[str],
) -> None:
    layout_path = project / "qa/layout_report.json"
    if not layout_path.exists():
        errors.append("qa/layout_report.json: missing compile and page-budget report")
    else:
        report = read_json(layout_path, errors)
        layout_schema = report.get("schema_version")
        if not isinstance(layout_schema, int) or isinstance(layout_schema, bool) or layout_schema != 10:
            errors.append("qa/layout_report.json: obsolete layout-audit schema")
        validate_layout_report_status(report, errors)
        compiler_log = validate_compiler_log_binding(project, report, errors)
        aux_path = validate_aux_binding(project, report, errors)
        validate_overfull_box_report(report, errors, compiler_log)
        validate_tex_fuzz_binding(project / "paper", report, errors)
        try:
            current_pagination = manual_pagination_commands(project / "paper")
            current_float_inventory = body_float_inventory(project / "paper")
        except ValueError as exc:
            errors.append(f"qa/layout_report.json: cannot audit active LaTeX inputs: {exc}")
            current_pagination = []
            current_float_inventory = {
                "active_body_files": [],
                "records": [],
                "labels": [],
                "all_records": [],
                "all_labels": [],
                "appendix_records": [],
                "active_appendix_files": [],
                "structure_errors": [],
                "after_conclusion_source": [],
            }
        if report.get("manual_pagination_commands") != current_pagination:
            errors.append("qa/layout_report.json: manual-pagination audit is stale or incomplete")
        if report.get("manual_pagination_commands") != []:
            errors.append("qa/layout_report.json: manuscript contains manual pagination commands")
        if report.get("active_body_files") != current_float_inventory["active_body_files"]:
            errors.append("qa/layout_report.json: active-body source coverage is stale or incomplete")
        if report.get("tracked_body_float_count") != len(current_float_inventory["records"]):
            errors.append("qa/layout_report.json: body-float coverage count is stale or incomplete")
        if report.get("tracked_appendix_float_count") != len(
            current_float_inventory.get("appendix_records", [])
        ):
            errors.append("qa/layout_report.json: appendix-float coverage count is stale or incomplete")
        if report.get("active_appendix_files") != current_float_inventory.get(
            "active_appendix_files", []
        ):
            errors.append("qa/layout_report.json: active-appendix source coverage is stale or incomplete")
        if report.get("manuscript_structure_errors") != current_float_inventory["structure_errors"]:
            errors.append("qa/layout_report.json: manuscript-structure audit is stale or incomplete")
        if report.get("manuscript_structure_errors") != []:
            errors.append("qa/layout_report.json: canonical manuscript boundaries are invalid")
        if (
            report.get("source_body_floats_after_conclusion")
            != current_float_inventory["after_conclusion_source"]
        ):
            errors.append("qa/layout_report.json: post-Conclusion source audit is stale or incomplete")
        if report.get("source_body_floats_after_conclusion") != []:
            errors.append("qa/layout_report.json: source contains floats after Conclusion begins")
        if report.get("unlabeled_body_floats") != current_float_inventory.get("unlabeled", []):
            errors.append("qa/layout_report.json: unlabeled body-float audit is stale or incomplete")
        if current_float_inventory.get("unlabeled", []):
            errors.append("qa/layout_report.json: active body contains unlabeled floats")
        if report.get("duplicate_body_float_labels") != current_float_inventory.get(
            "duplicate_labels", []
        ):
            errors.append("qa/layout_report.json: duplicate body-label audit is stale or incomplete")
        if current_float_inventory.get("duplicate_labels", []):
            errors.append("qa/layout_report.json: active body contains duplicate float labels")
        if report.get("unlabeled_appendix_floats") != current_float_inventory.get(
            "unlabeled_appendix_floats", []
        ):
            errors.append("qa/layout_report.json: unlabeled appendix-float audit is stale or incomplete")
        if current_float_inventory.get("unlabeled_appendix_floats", []):
            errors.append("qa/layout_report.json: active appendix contains unlabeled floats")
        if report.get("duplicate_all_float_labels") != current_float_inventory.get(
            "duplicate_all_float_labels", []
        ):
            errors.append("qa/layout_report.json: all-float duplicate-label audit is stale or incomplete")
        if current_float_inventory.get("duplicate_all_float_labels", []):
            errors.append("qa/layout_report.json: body/appendix float labels are not unique")
        if report.get("missing_body_float_aux_labels") != []:
            errors.append("qa/layout_report.json: body float labels are missing from compiled AUX")
        if report.get("missing_all_float_aux_labels") != []:
            errors.append("qa/layout_report.json: body/appendix float labels are missing from compiled AUX")
        if report.get("body_float_tail_violations") != []:
            errors.append("qa/layout_report.json: body floats appear after Conclusion begins")
        if report.get("float_distribution_violations") != []:
            errors.append("qa/layout_report.json: floats are overloaded or clustered across pages")
        if report.get("whitespace_violations") != []:
            errors.append("qa/layout_report.json: rendered pages contain avoidable large blank regions")
        if report.get("float_reading_order_violations") != []:
            errors.append("qa/layout_report.json: a float interrupts reading continuity across pages")
        if report.get("column_mode") not in {1, 2}:
            errors.append("qa/layout_report.json: missing audited one-/two-column mode")
        column_audit = report.get("column_mode_audit")
        if (
            not isinstance(column_audit, dict)
            or column_audit.get("mode") != report.get("column_mode")
            or column_audit.get("override_verified") is not True
            or column_audit.get("source") not in {
                "explicit-two-column-evidence",
                "audited-single-column-default",
            }
        ):
            errors.append("qa/layout_report.json: column-mode source audit is missing or inconsistent")
        rendered_column = report.get("rendered_column_inference")
        if not isinstance(rendered_column, dict):
            errors.append("qa/layout_report.json: rendered column-geometry audit is missing")
        else:
            try:
                rendered_confidence = float(rendered_column.get("confidence", 0.0))
            except (TypeError, ValueError):
                rendered_confidence = 0.0
            if (
                rendered_confidence >= 0.70
                and rendered_column.get("mode") in {1, 2}
                and rendered_column.get("mode") != report.get("column_mode")
            ):
                errors.append("qa/layout_report.json: source and rendered column modes disagree")
        if report.get("layout_dependencies") != {"pdfplumber": "required"}:
            errors.append("qa/layout_report.json: rendered-layout dependency audit is missing")
        try:
            conclusion_page = int(report.get("conclusion_page", 0))
        except (TypeError, ValueError):
            conclusion_page = 0
        if conclusion_page <= 0:
            errors.append("qa/layout_report.json: missing conclusion-page audit")
        try:
            end_body_page = int(report.get("end_body_page", 0))
        except (TypeError, ValueError):
            end_body_page = 0
        if end_body_page <= 0 or report.get("conclusion_before_end_body") is not True:
            errors.append("qa/layout_report.json: invalid Conclusion/end-body boundary order")
        try:
            appendix_start_page = int(report.get("appendix_start_page", 0))
        except (TypeError, ValueError):
            appendix_start_page = 0
        if appendix_start_page <= 0:
            errors.append("qa/layout_report.json: missing appendix-start page audit")
        try:
            end_exempt_page = int(report.get("end_exempt_page", 0))
            exempt_page_span = int(report.get("exempt_page_span", -1))
            max_exempt_page_span = int(report.get("max_exempt_page_span", -1))
        except (TypeError, ValueError):
            end_exempt_page = 0
            exempt_page_span = max_exempt_page_span = -1
        if (
            end_exempt_page <= 0
            or exempt_page_span < 0
            or exempt_page_span > 1
            or max_exempt_page_span != 1
            or end_exempt_page - end_body_page != exempt_page_span
        ):
            errors.append("qa/layout_report.json: invalid page-limit-exempt disclosure span")
        if report.get("source_sha256") != source_tree_sha256(project / "paper"):
            errors.append("qa/layout_report.json: paper sources changed after compilation")
        if not timezone_aware(str(report.get("compiled_at", ""))):
            errors.append("qa/layout_report.json: compiled_at must be timezone-aware")
        pdf_value = report.get("pdf")
        pdf_path = Path(str(pdf_value)).expanduser() if pdf_value else Path("<missing>")
        bound_pdf: Path | None = None
        if not pdf_value or not pdf_path.is_file():
            errors.append("qa/layout_report.json: compiled PDF is missing")
        else:
            try:
                pdf_path.resolve().relative_to((project / "build").resolve())
            except ValueError:
                errors.append("qa/layout_report.json: compiled PDF must stay under the project build directory")
            else:
                bound_pdf = pdf_path
                reported_build = Path(str(report.get("build_dir", ""))).expanduser().resolve()
                if pdf_path.resolve() != (reported_build / "main.pdf").resolve():
                    errors.append("qa/layout_report.json: compiled PDF is not build_dir/main.pdf")
                    bound_pdf = None
            if sha256_file(pdf_path) != str(report.get("pdf_sha256", "")).lower():
                errors.append("qa/layout_report.json: compiled PDF hash mismatch")
                bound_pdf = None
        validate_media_box_overflow_report(report, errors, bound_pdf)
        validate_recomputed_layout_audits(
            project,
            report,
            current_float_inventory,
            aux_path,
            bound_pdf,
            errors,
        )
        selected = venue.get("selected") if isinstance(venue.get("selected"), dict) else {}
        page_rules = selected.get("page_rules") if isinstance(selected.get("page_rules"), dict) else {}
        try:
            official_limit = int(page_rules.get("main_text_pages", 0))
            report_limit = int(report.get("max_pages", 0))
            body_pages = int(report.get("body_pages", 0))
            allow_overrun = int(report.get("allow_overrun", -1))
        except (TypeError, ValueError):
            official_limit = report_limit = body_pages = 0
            allow_overrun = -1
        expected_overrun = 1 if mode == "sketch" else 0
        if report_limit != official_limit or official_limit <= 0:
            errors.append("qa/layout_report.json: page limit does not match venue decision")
        if allow_overrun != expected_overrun:
            errors.append(f"qa/layout_report.json: {mode} mode requires allow_overrun={expected_overrun}")
        if body_pages <= 0 or body_pages > official_limit + expected_overrun:
            errors.append("qa/layout_report.json: body page count is outside the permitted budget")
        if report.get("references_counted") is not page_rules.get("references_counted"):
            errors.append("qa/layout_report.json: reference-counting rule does not match venue decision")

    review_path = project / "qa/independent_review.md"
    if not review_path.exists():
        errors.append("qa/independent_review.md: missing independent paper review")
    else:
        review = review_path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"(?im)^\s*review status\s*:\s*pass\s*$", review):
            errors.append("qa/independent_review.md: review must contain 'Review status: pass'")
    validate_paperjury_review(project, errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--mode", choices=["structure", "sketch", "submission"], default="sketch")
    parser.add_argument("--report", type=Path, help="Optional JSON report output")
    args = parser.parse_args()

    project = args.project.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_STRUCTURE:
        if not (project / relative).exists():
            errors.append(f"missing required path: {relative}")

    if errors:
        report = {"mode": args.mode, "project": str(project), "status": "fail", "errors": errors, "warnings": warnings}
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 1

    project_data = read_json(project / "project.json", errors)
    resources = read_json(project / "resources.json", errors)
    state = read_json(project / "state.json", errors)
    venue = read_json(project / "venue/decision.json", errors)
    if not project_data.get("idea_original"):
        errors.append("project.json: idea_original is empty")
    if resources.get("source") not in {"current_machine", "user"}:
        errors.append("resources.json: source must be current_machine or user")
    stages = state.get("stages", {})
    for stage in STAGES:
        if stage not in stages:
            errors.append(f"state.json: missing stage {stage}")
            continue
        status = stages[stage].get("status") if isinstance(stages[stage], dict) else None
        if status not in {"pending", "in_progress", "complete", "stale", "blocked"}:
            errors.append(f"state.json: invalid status for {stage}: {status!r}")
    validate_state_snapshots(project, state, errors)

    todo_report = lint_directory(project / "paper", "submission" if args.mode == "submission" else "sketch")
    errors.extend(f"todo_lint: {message}" for message in todo_report["errors"])
    if args.mode in {"sketch", "submission"}:
        validate_todo_registry(project, todo_report, errors)

    if args.mode in {"sketch", "submission"}:
        required_complete = [
            "INTAKE",
            "VENUE_LOCKED",
            "RESOURCES_READY",
            "LITERATURE_AUDITED",
            "IDEA_REVIEWED",
            "IDEA_FROZEN",
            "CLAIM_GRAPH_FROZEN",
            "METHOD_EXPERIMENT_READY",
            "TITLE_FROZEN",
            "MANUSCRIPT_DRAFTED",
        ]
        if args.mode == "submission":
            required_complete.extend(["SKETCH_COMPLETE", "RESULTS_INTEGRATED"])
        for stage in required_complete:
            if stages.get(stage, {}).get("status") != "complete":
                errors.append(f"state.json: {stage} must be complete for {args.mode} validation")
        validate_venue(project, project_data, venue, errors, warnings)
        validate_literature(project, project_data, errors)
        validate_council(project, errors)
        validate_claims(project, errors)
        validate_design(project, errors)
        validate_title(project, project_data, venue, errors)
        validate_figures(project, errors, require_overview=True)
        validate_no_alternate_figure_backends(project, errors)
        validate_sections(project, errors)
        errors.extend(
            f"paper teaser placement: {message}"
            for message in teaser_placement_audit(project / "paper")
        )
        validate_layout_and_review(project, venue, args.mode, errors)

    if args.mode == "submission":
        selected = venue.get("selected") or {}
        if selected.get("template_status") not in {"current_cycle", "current"}:
            errors.append("submission mode requires the current-cycle official template")
        if stages.get("SUBMISSION_READY", {}).get("status") in {"stale", "blocked"}:
            errors.append("SUBMISSION_READY is stale or blocked")

    report = {
        "schema_version": 1,
        "mode": args.mode,
        "project": str(project),
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "todo_summary": {"items": len(todo_report["items"]), "status": todo_report["status"]},
        "todo_items": [
            {"id": item.get("id"), "type": item.get("type"), "status": item.get("status")}
            for item in todo_report["items"]
        ],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
