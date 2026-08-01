#!/usr/bin/env python3
"""Add auditable publication and openness fields to survey paper records."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


EXTRA_COLUMNS = [
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
]


def normalized_title(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def identity_key(row: dict[str, str]) -> str:
    if row.get("doi"):
        return "doi:" + row["doi"].strip().lower()
    if row.get("arxiv_id"):
        return "arxiv:" + row["arxiv_id"].strip().lower()
    if row.get("openalex_id"):
        return "openalex:" + row["openalex_id"].strip().lower().replace("https://openalex.org/", "")
    return "title:" + normalized_title(row.get("title", "")) + ":" + row.get("year", "").strip()


def identity_aliases(row: dict[str, str]) -> set[str]:
    aliases: set[str] = set()
    if row.get("doi", "").strip():
        aliases.add("doi:" + row["doi"].strip().lower())
    if row.get("arxiv_id", "").strip():
        aliases.add("arxiv:" + row["arxiv_id"].strip().lower())
    if row.get("openalex_id", "").strip():
        aliases.add(
            "openalex:" + row["openalex_id"].strip().lower().replace("https://openalex.org/", "")
        )
    title = normalized_title(row.get("title", ""))
    if title:
        aliases.add("title:" + title + ":" + row.get("year", "").strip())
    return aliases


def stable_id(key: str) -> str:
    return "PW-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()


def write_if_missing(path: Path, text: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def default_if_blank(row: dict[str, str], field: str, value: str) -> None:
    if not row.get(field, "").strip():
        row[field] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="ai-literature-survey papers_merged.csv")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--records-dir", type=Path, required=True)
    parser.add_argument("--idea-version", default="idea_v0")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Missing survey record file: {args.input}")
    with args.input.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "title" not in reader.fieldnames:
            raise SystemExit("Input must contain the ai-literature-survey paper columns")
        base_columns = list(reader.fieldnames)
        rows = list(reader)

    columns = base_columns + [column for column in EXTRA_COLUMNS if column not in base_columns]
    args.records_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    existing_by_alias: dict[str, dict[str, str]] = {}
    if args.output.exists():
        with args.output.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            for existing in csv.DictReader(handle):
                for alias in identity_aliases(existing):
                    existing_by_alias[alias] = existing

    seen_stable_ids: set[str] = set()
    for row in rows:
        aliases = identity_aliases(row)
        if not aliases:
            raise SystemExit("Every survey record must have a non-empty title or persistent identifier")
        matches = {
            existing.get("stable_id", "")
            for alias in aliases
            if (existing := existing_by_alias.get(alias)) is not None and existing.get("stable_id")
        }
        if len(matches) > 1:
            raise SystemExit(f"Conflicting stable IDs for {row.get('title', '<untitled>')}: {sorted(matches)}")
        prior = next(
            (existing_by_alias[alias] for alias in aliases if alias in existing_by_alias),
            None,
        )
        if prior:
            for field in EXTRA_COLUMNS:
                current = row.get(field, "").strip()
                previous = prior.get(field, "").strip()
                if (not current or current == "unknown") and previous:
                    row[field] = previous
        sid = row.get("stable_id") or (next(iter(matches)) if matches else stable_id(identity_key(row)))
        if sid in seen_stable_ids:
            raise SystemExit(f"Duplicate stable ID after enrichment: {sid}")
        seen_stable_ids.add(sid)
        row["stable_id"] = sid
        default_if_blank(row, "bib_key", sid)
        default_if_blank(row, "publication_status", "unknown")
        default_if_blank(row, "status_venue", "")
        default_if_blank(row, "status_year", "")
        default_if_blank(row, "status_evidence_url", "")
        default_if_blank(row, "status_checked_at", "")
        default_if_blank(row, "paper_access_status", "unknown")
        default_if_blank(row, "local_pdf_path", "")
        default_if_blank(row, "official_code_status", "unknown")
        default_if_blank(row, "code_url", "")
        default_if_blank(row, "code_license", "unknown")
        default_if_blank(row, "data_status", "unknown")
        default_if_blank(row, "data_url", "")
        default_if_blank(row, "weights_status", "unknown")
        default_if_blank(row, "weights_url", "")
        default_if_blank(row, "discovery_idea_version", args.idea_version)

        tier = row.get("tier", "").strip().lower()
        if tier and tier != "exclude":
            record_dir = args.records_dir / sid
            record_dir.mkdir(parents=True, exist_ok=True)
            try:
                row["local_record_path"] = str(record_dir.resolve().relative_to(args.output.parent.resolve()))
            except ValueError:
                row["local_record_path"] = str(record_dir.resolve())
            metadata = {column: row.get(column, "") for column in columns}
            metadata["enriched_utc"] = now
            (record_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            write_if_missing(
                record_dir / "notes.md",
                f"# {row.get('title') or sid}\n\n"
                "## Evidence\n\n"
                "## Relation to the Current Idea\n\n"
                "## Limitations and Novelty Risk\n\n",
            )
        else:
            row.setdefault("local_record_path", "")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"records": len(rows), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
