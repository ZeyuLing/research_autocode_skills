#!/usr/bin/env python3
"""Validate and hash an ai-literature-survey run for idea2paper provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


STANDARD_ARTIFACTS = [
    "00_scope.md",
    "01_query_plan.md",
    "source_ledger.csv",
    "papers_raw.csv",
    "papers_merged.csv",
    "screening.csv",
    "snowball_log.csv",
    "reading_matrix.csv",
    "coverage_audit.md",
    "synthesis_outline.md",
]

CSV_REQUIRED = {
    "source_ledger.csv": {
        "run_id",
        "date",
        "source_family",
        "source_name",
        "query",
        "filters",
        "command_or_url",
        "raw_output",
        "raw_hits",
        "unique_hits",
        "status",
        "notes",
    },
    "papers_raw.csv": {"title"},
    "papers_merged.csv": {"record_id", "title", "year", "sources", "tier"},
    "screening.csv": {"record_id", "title", "tier", "reason", "read_priority", "must_cite", "novelty_risk"},
    "reading_matrix.csv": {
        "record_id",
        "claim",
        "method",
        "data",
        "metrics",
        "baselines",
        "result",
        "limitation",
        "relation_to_user_work",
        "quote_or_evidence",
    },
    "snowball_log.csv": {
        "anchor_id",
        "anchor_title",
        "direction",
        "pass",
        "new_candidates",
        "new_core",
        "source",
        "notes",
    },
}

REQUIRED_SOURCE_GROUPS = {
    "current_preprints": {"arxiv", "daily_feed", "current_feed"},
    "scholarly_index": {"openalex"},
    "peer_review": {"openreview"},
    "official_venues": {"proceedings"},
    "citation_graph": {"citation_graph"},
    "web_projects": {"web"},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_fields(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        return set(reader.fieldnames or []), list(reader)


def timezone_aware(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("related_works", type=Path)
    parser.add_argument("--idea-version", required=True)
    parser.add_argument("--invocation-id", required=True, help="Identifier of the completed ai-literature-survey invocation")
    parser.add_argument("--survey-mode", choices=["initial", "delta"], default="initial")
    parser.add_argument("--skill-version", default="unknown")
    parser.add_argument(
        "--receipt",
        type=Path,
        required=True,
        help="Dispatch-layer receipt captured from the ai-literature-survey invocation",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.related_works.expanduser().resolve()
    errors: list[str] = []
    receipt_source = args.receipt.expanduser().resolve()
    receipt: dict[str, object] = {}
    receipt_bytes = b""
    skill_snapshot_bytes = b""
    if not receipt_source.is_file():
        errors.append(f"missing survey invocation receipt: {receipt_source}")
    else:
        receipt_bytes = receipt_source.read_bytes()
        try:
            loaded_receipt = json.loads(receipt_bytes.decode("utf-8"))
            if isinstance(loaded_receipt, dict):
                receipt = loaded_receipt
            else:
                errors.append("survey invocation receipt must be a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid survey invocation receipt: {exc}")
    if receipt:
        if receipt.get("skill_name") != "ai-literature-survey":
            errors.append("survey receipt skill_name must be ai-literature-survey")
        if receipt.get("invocation_id") != args.invocation_id:
            errors.append("survey receipt invocation_id does not match --invocation-id")
        for field in ("orchestrator_run_id", "request_sha256", "skill_sha256"):
            value = str(receipt.get(field, ""))
            if field.endswith("sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", value):
                errors.append(f"survey receipt has invalid {field}")
            elif field == "orchestrator_run_id" and not value:
                errors.append("survey receipt is missing orchestrator_run_id")
        for field in ("started_at", "completed_at"):
            if not timezone_aware(str(receipt.get(field, ""))):
                errors.append(f"survey receipt {field} must be timezone-aware")
        skill_path = Path(str(receipt.get("skill_path", ""))).expanduser()
        if not skill_path.is_file():
            errors.append("survey receipt skill_path does not exist")
        else:
            skill_snapshot_bytes = skill_path.read_bytes()
            if hashlib.sha256(skill_snapshot_bytes).hexdigest() != str(
                receipt.get("skill_sha256", "")
            ).lower():
                errors.append("survey receipt skill hash does not match the invoked SKILL.md")
            elif not re.search(
                r"(?m)^name:\s*ai-literature-survey\s*$",
                skill_snapshot_bytes.decode("utf-8", errors="replace"),
            ):
                errors.append("survey receipt skill_path is not an ai-literature-survey SKILL.md")
    receipt_target = root / "survey_receipt.json"
    if receipt_bytes:
        receipt_target.write_bytes(receipt_bytes)
    skill_snapshot_target = root / "survey_skill_snapshot.md"
    if skill_snapshot_bytes:
        skill_snapshot_target.write_bytes(skill_snapshot_bytes)
    artifacts: dict[str, dict[str, object]] = {}
    for relative in STANDARD_ARTIFACTS:
        path = root / relative
        if not path.exists():
            errors.append(f"missing standard ai-literature-survey artifact: {relative}")
            continue
        artifacts[relative] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}

    ledger_rows: list[dict[str, str]] = []
    snowball_rows: list[dict[str, str]] = []
    for relative, required_fields in CSV_REQUIRED.items():
        path = root / relative
        if not path.exists():
            continue
        fields, rows = read_csv_fields(path)
        missing = sorted(required_fields - fields)
        if missing:
            errors.append(f"{relative}: missing columns {missing}")
        if relative == "source_ledger.csv":
            ledger_rows = rows
        elif relative == "snowball_log.csv":
            snowball_rows = rows

    coverage_path = root / "coverage_audit.md"
    coverage_text = ""
    if coverage_path.exists():
        coverage_text = coverage_path.read_text(encoding="utf-8", errors="replace")
        for heading in ("## Source Ledger Summary", "## Snowballing", "## Blind Spots", "## Stopping Decision"):
            if heading not in coverage_text:
                errors.append(f"coverage_audit.md: missing heading {heading}")
    if not ledger_rows:
        errors.append("source_ledger.csv: no recorded searches")

    family_rows: dict[str, list[dict[str, str]]] = {}
    for row in ledger_rows:
        family = row.get("source_family", "").strip()
        if family:
            family_rows.setdefault(family, []).append(row)
    source_families = sorted(family_rows)
    covered_families: list[str] = []
    waived_families: list[str] = []
    for family, rows in family_rows.items():
        statuses = {row.get("status", "").strip().lower() for row in rows}
        if statuses & {"ok", "empty"}:
            covered_families.append(family)
        elif statuses == {"skipped"} and all(
            row.get("notes", "").strip().upper().startswith("WAIVER:") for row in rows
        ):
            waived_families.append(family)
        else:
            errors.append(f"source_ledger.csv: source family {family!r} has no successful query or documented waiver")
    covered_groups: list[str] = []
    waived_groups: list[str] = []
    for group, aliases in REQUIRED_SOURCE_GROUPS.items():
        group_rows = [row for alias in aliases for row in family_rows.get(alias, [])]
        if not group_rows:
            errors.append(f"source_ledger.csv: required source group {group!r} is neither searched nor waived")
            continue
        statuses = {row.get("status", "").strip().lower() for row in group_rows}
        if statuses & {"ok", "empty"}:
            covered_groups.append(group)
        elif statuses == {"skipped"} and all(
            row.get("notes", "").strip().upper().startswith("WAIVER:") for row in group_rows
        ):
            waived_groups.append(group)
        else:
            errors.append(f"source_ledger.csv: required source group {group!r} lacks success or explicit waiver")
    if len(covered_groups) < 4:
        errors.append("source_ledger.csv: near-complete coverage requires at least four searched source groups")
    if "current_preprints" not in covered_groups or "citation_graph" not in covered_groups:
        errors.append("source_ledger.csv: current preprints and citation graph must be searched, not waived")
    if not {"peer_review", "official_venues"} & set(covered_groups):
        errors.append("source_ledger.csv: at least one official peer-review/proceedings group must be searched")

    pass_totals: dict[str, int] = {}
    pass_order: list[str] = []
    pass_rows: dict[str, list[dict[str, str]]] = {}
    for row in snowball_rows:
        pass_id = row.get("pass", "").strip()
        if pass_id and pass_id not in pass_totals:
            pass_totals[pass_id] = 0
            pass_order.append(pass_id)
            pass_rows[pass_id] = []
        if pass_id:
            pass_rows[pass_id].append(row)
        if not pass_id or not row.get("anchor_id", "").strip() or row.get("direction", "").strip().lower() not in {
            "backward",
            "forward",
        }:
            errors.append(f"snowball_log.csv: incomplete entry in pass {pass_id or '<missing>'}")
        try:
            new_core = int(row.get("new_core", ""))
        except ValueError:
            errors.append(f"snowball_log.csv: invalid new_core value {row.get('new_core')!r}")
            new_core = 0
        if new_core < 0:
            errors.append("snowball_log.csv: new_core cannot be negative")
        if pass_id:
            pass_totals[pass_id] += new_core
    consecutive_zero_new_core_passes = 0
    for pass_id in reversed(pass_order):
        directions_by_anchor: dict[str, set[str]] = {}
        for row in pass_rows[pass_id]:
            directions_by_anchor.setdefault(row.get("anchor_id", "").strip(), set()).add(
                row.get("direction", "").strip().lower()
            )
        bidirectional = bool(directions_by_anchor) and all(
            directions == {"backward", "forward"} for directions in directions_by_anchor.values()
        )
        if pass_totals[pass_id] != 0 or not bidirectional:
            break
        consecutive_zero_new_core_passes += 1
    if consecutive_zero_new_core_passes < 2:
        errors.append("snowball_log.csv: fewer than two consecutive zero-new-core passes")

    coverage_status = (
        "near_complete"
        if re.search(r"##\s*Stopping Decision[\s\S]*?Near-complete", coverage_text, re.IGNORECASE)
        else "partial"
    )
    if coverage_status != "near_complete":
        errors.append("coverage_audit.md: stopping decision is not near-complete")

    payload = {
        "schema_version": 1,
        "skill_name": receipt.get("skill_name"),
        "skill_version": args.skill_version,
        "invocation_id": args.invocation_id,
        "survey_mode": args.survey_mode,
        "idea_version": args.idea_version,
        "completed_at": receipt.get("completed_at", datetime.now(timezone.utc).isoformat()),
        "receipt_path": "survey_receipt.json",
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest() if receipt_bytes else "",
        "skill_snapshot_path": "survey_skill_snapshot.md",
        "skill_snapshot_sha256": hashlib.sha256(skill_snapshot_bytes).hexdigest()
        if skill_snapshot_bytes
        else "",
        "artifacts": artifacts,
        "coverage": {
            "status": coverage_status,
            "consecutive_zero_new_core_passes": consecutive_zero_new_core_passes,
            "source_families": source_families,
            "covered_source_families": sorted(covered_families),
            "waived_source_families": sorted(waived_families),
            "covered_source_groups": sorted(covered_groups),
            "waived_source_groups": sorted(waived_groups),
            "blind_spots_recorded": "## Blind Spots" in coverage_text,
        },
        "errors": errors,
        "status": "pass" if not errors else "fail",
    }
    output = (args.output or root / "survey_run.json").expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
