#!/usr/bin/env python3
"""Merge CSV, JSON, or JSONL paper records into a deduplicated CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


OUTPUT_COLUMNS = [
    "record_id",
    "title",
    "authors",
    "year",
    "venue",
    "sources",
    "url",
    "pdf_url",
    "doi",
    "arxiv_id",
    "openalex_id",
    "citation_count",
    "abstract",
    "tier",
    "screening_reason",
    "full_text_status",
    "notes_path",
]


FIELD_ALIASES = {
    "title": ["title", "paper_title", "name"],
    "authors": ["authors", "author", "author_names"],
    "year": ["year", "publication_year", "published_year"],
    "venue": ["venue", "conference", "journal", "host_venue", "primary_location"],
    "url": ["url", "link", "abs_url", "landing_url", "openalex_url"],
    "pdf_url": ["pdf_url", "pdf", "pdf_link", "open_access_pdf"],
    "doi": ["doi"],
    "arxiv_id": ["arxiv_id", "arxiv", "id"],
    "openalex_id": ["openalex_id", "paper_id", "work_id"],
    "citation_count": ["citation_count", "cited_by_count", "citations"],
    "abstract": ["abstract", "summary", "tldr"],
}


def norm_title(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_doi(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip()


def clean_arxiv(value: str) -> str:
    value = value.strip()
    patterns = [
        r"arxiv\.org/(abs|pdf|html)/([^/?#]+)",
        r"10\.48550/arxiv\.([^ ]+)",
        r"arxiv:([^ ]+)",
        r"^(\d{4}\.\d{4,5}(v\d+)?)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return match.group(2 if "arxiv.org" in pattern else 1).replace(".pdf", "")
    return value if re.match(r"^\d{4}\.\d{4,5}", value) else ""


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(stringify(v) for v in value if stringify(v))
    if isinstance(value, dict):
        if "display_name" in value:
            return stringify(value["display_name"])
        if "name" in value:
            return stringify(value["name"])
        if "url" in value:
            return stringify(value["url"])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def pick(record: dict[str, Any], field: str) -> str:
    for key in FIELD_ALIASES.get(field, [field]):
        if key in record and record[key] not in (None, "", []):
            return stringify(record[key])
    return ""


def normalize_record(record: dict[str, Any], source_name: str) -> dict[str, str]:
    out = {column: "" for column in OUTPUT_COLUMNS}
    for field in FIELD_ALIASES:
        out[field] = pick(record, field)
    out["sources"] = source_name
    out["doi"] = clean_doi(out["doi"])
    out["arxiv_id"] = clean_arxiv(out["arxiv_id"] or out["url"] or out["doi"])
    out["openalex_id"] = out["openalex_id"].replace("https://openalex.org/", "")
    if not out["year"]:
        date = stringify(record.get("published") or record.get("publication_date") or record.get("updated"))
        match = re.search(r"(19|20)\d{2}", date)
        if match:
            out["year"] = match.group(0)
    return out


def record_key(record: dict[str, str]) -> str:
    if record["doi"]:
        return "doi:" + record["doi"]
    if record["arxiv_id"]:
        return "arxiv:" + record["arxiv_id"].lower()
    if record["openalex_id"]:
        return "openalex:" + record["openalex_id"].lower()
    title = norm_title(record["title"])
    return "title:" + title if title else ""


def merge_into(base: dict[str, str], new: dict[str, str]) -> None:
    for field in OUTPUT_COLUMNS:
        if field in {"record_id", "sources"}:
            continue
        if not base.get(field) and new.get(field):
            base[field] = new[field]
    if new.get("citation_count"):
        try:
            base_count = int(float(base.get("citation_count") or 0))
            new_count = int(float(new["citation_count"]))
            base["citation_count"] = str(max(base_count, new_count))
        except ValueError:
            if not base.get("citation_count"):
                base["citation_count"] = new["citation_count"]
    sources = {s.strip() for s in base.get("sources", "").split(";") if s.strip()}
    sources.update(s.strip() for s in new.get("sources", "").split(";") if s.strip())
    base["sources"] = "; ".join(sorted(sources))


def iter_json_records(path: Path) -> Iterable[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "papers", "candidates", "items", "data", "new"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def flatten_records(items: Iterable[Any]) -> Iterable[dict[str, Any]]:
    for item in items:
        if isinstance(item, dict):
            yield item
        elif isinstance(item, list):
            yield from flatten_records(item)


def iter_csv_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def read_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".json", ".jsonl"}:
        return list(flatten_records(iter_json_records(path)))
    if suffix == ".csv":
        return list(iter_csv_records(path))
    raise ValueError(f"Unsupported file type: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="CSV, JSON, or JSONL files")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Output CSV path")
    args = parser.parse_args()

    merged: dict[str, dict[str, str]] = {}
    skipped = 0
    raw_count = 0
    for path in args.inputs:
        source_name = path.stem
        try:
            records = read_records(path)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: failed to read {path}: {exc}", file=sys.stderr)
            continue
        for raw in records:
            raw_count += 1
            if not isinstance(raw, dict):
                skipped += 1
                continue
            normalized = normalize_record(raw, source_name)
            key = record_key(normalized)
            if not key:
                skipped += 1
                continue
            if key not in merged:
                merged[key] = normalized
            else:
                merge_into(merged[key], normalized)

    rows = sorted(merged.values(), key=lambda r: (r.get("year", ""), r.get("title", "")), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["record_id"] = f"P{idx:04d}"
        if not row.get("full_text_status"):
            row["full_text_status"] = "unread"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"raw_records": raw_count, "unique_records": len(rows), "skipped": skipped}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
