#!/usr/bin/env python3
"""Validate idea2paper project structure, traceability, figures, and readiness."""

from __future__ import annotations

import argparse
import binascii
import csv
import hashlib
import json
import re
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compile_paper import source_tree_sha256
from record_survey_run import CSV_REQUIRED as SURVEY_CSV_REQUIRED
from record_survey_run import STANDARD_ARTIFACTS as SURVEY_STANDARD_ARTIFACTS
from select_venue import TIER_RANK, evaluate as evaluate_venue
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
    "method/method_spec.md",
    "experiments/plan.md",
    "experiments/claim_experiment_matrix.csv",
    "experiments/baseline_provenance.csv",
    "figures/manifest.csv",
    "paper/main.tex",
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


def validate_venue(
    project: Path,
    project_data: dict[str, Any],
    venue: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    selection_mode = venue.get("selection_mode")
    if selection_mode not in {"auto", "user"}:
        errors.append("venue/decision.json: selection_mode must be auto or user")
    selected = venue.get("selected")
    if not isinstance(selected, dict):
        errors.append("venue/decision.json: no selected venue")
        return

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
    if venue.get("selection_rule") != "scope_fit>=threshold, nearest open abstract/full-paper deadline, fit desc, tier desc":
        errors.append("venue/decision.json: unexpected or missing automatic selection_rule")
    try:
        as_of = parse_datetime(str(venue.get("as_of", "")))
    except ValueError as exc:
        errors.append(f"venue/decision.json: invalid as_of: {exc}")
        return

    registry = load_registry(Path(__file__).resolve().parents[1] / "references/venue-registry.json")
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
        if row.get("type", "").strip().lower() in {"overview", "module"} and not row.get(
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
        if prompt_path and prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
            if "Use case:" not in prompt or "Primary request:" not in prompt:
                errors.append(f"{path}:{index}: prompt file lacks the required imagegen prompt contract")
        qa_path = resolved.get("qa_path")
        if qa_path and qa_path.exists():
            qa_text = qa_path.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"(?im)^\s*(?:qa_status|qa status)\s*:\s*pass\s*$", qa_text):
                errors.append(f"{path}:{index}: QA note must contain 'QA status: pass'")

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
    }
    paper_root = project / "paper"
    for tex_path in paper_root.rglob("*.tex"):
        text = strip_tex_comments(tex_path.read_text(encoding="utf-8", errors="replace"))
        for label, pattern in forbidden_patterns.items():
            if pattern.search(text):
                errors.append(f"{tex_path}: forbidden non-imagegen figure backend ({label})")
        for match in re.finditer(
            r"\\begin\{figure\*?\}([\s\S]*?)\\end\{figure\*?\}",
            text,
            re.IGNORECASE,
        ):
            if not INCLUDE_RE.search(match.group(1)):
                line_number = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{tex_path}:{line_number}: figure environment has no registered raster includegraphics"
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
    actual = {
        (str(item.get("id", "")), str(item.get("type", "")), str(item.get("status", "")))
        for item in todo_report.get("items", [])
    }
    recorded = {
        (str(item.get("id", "")), str(item.get("type", "")), str(item.get("status", "")))
        for item in registry.get("items", [])
        if isinstance(item, dict)
    }
    if actual != recorded:
        errors.append(f"{registry_path}: registry does not match current LaTeX draft macros/TODOs")


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
        if report.get("status") != "pass":
            errors.append("qa/layout_report.json: LaTeX build or page check did not pass")
        if report.get("source_sha256") != source_tree_sha256(project / "paper"):
            errors.append("qa/layout_report.json: paper sources changed after compilation")
        if not timezone_aware(str(report.get("compiled_at", ""))):
            errors.append("qa/layout_report.json: compiled_at must be timezone-aware")
        build_value = Path(str(report.get("build_dir", ""))).expanduser()
        try:
            build_value.resolve().relative_to((project / "build").resolve())
        except ValueError:
            errors.append("qa/layout_report.json: build_dir must stay under the project build directory")
        pdf_value = report.get("pdf")
        pdf_path = Path(str(pdf_value)).expanduser() if pdf_value else Path("<missing>")
        if not pdf_value or not pdf_path.is_file():
            errors.append("qa/layout_report.json: compiled PDF is missing")
        else:
            try:
                pdf_path.resolve().relative_to((project / "build").resolve())
            except ValueError:
                errors.append("qa/layout_report.json: compiled PDF must stay under the project build directory")
            if sha256_file(pdf_path) != str(report.get("pdf_sha256", "")).lower():
                errors.append("qa/layout_report.json: compiled PDF hash mismatch")
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
        validate_figures(project, errors, require_overview=True)
        validate_no_alternate_figure_backends(project, errors)
        validate_sections(project, errors)
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
