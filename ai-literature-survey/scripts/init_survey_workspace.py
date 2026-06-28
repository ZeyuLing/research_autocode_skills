#!/usr/bin/env python3
"""Create a reproducible literature survey workspace."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SOURCE_LEDGER_COLUMNS = [
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
]

PAPER_COLUMNS = [
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

SCREENING_COLUMNS = [
    "record_id",
    "title",
    "tier",
    "reason",
    "read_priority",
    "must_cite",
    "novelty_risk",
]

SNOWBALL_COLUMNS = [
    "anchor_id",
    "anchor_title",
    "direction",
    "pass",
    "new_candidates",
    "new_core",
    "source",
    "notes",
]

READING_COLUMNS = [
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
]


def slugify(text: str, max_len: int = 72) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return (text or "literature-survey")[:max_len].strip("-")


def write_csv_header(path: Path, columns: list[str]) -> None:
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)


def read_seed_preview(path: Path, limit: int = 2400) -> str:
    if not path:
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Could not read seed file: {exc}"
    return data[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="Topic, research question, or draft-paper goal")
    parser.add_argument("--out-dir", default="literature-surveys", help="Parent directory for survey workspaces")
    parser.add_argument("--slug", help="Optional workspace slug")
    parser.add_argument("--seed-file", type=Path, help="Optional draft, proposal, related-work section, or notes file")
    parser.add_argument("--upstreams-root", help="Optional path to cloned upstream literature repos")
    args = parser.parse_args()

    parent = Path(args.out_dir).expanduser().resolve()
    slug = args.slug or slugify(args.topic)
    workspace = parent / slug
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes").mkdir(exist_ok=True)
    (workspace / "exports").mkdir(exist_ok=True)
    (workspace / "raw").mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    seed_preview = read_seed_preview(args.seed_file) if args.seed_file else ""
    state = {
        "topic": args.topic,
        "slug": slug,
        "created_utc": now,
        "seed_file": str(args.seed_file.resolve()) if args.seed_file else "",
        "upstreams_root": args.upstreams_root or "",
        "status": "initialized",
    }
    (workspace / "survey_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    scope = [
        f"# Scope: {args.topic}",
        "",
        "## User Goal",
        args.topic,
        "",
        "## Seed File",
        str(args.seed_file.resolve()) if args.seed_file else "none",
        "",
        "## Extracted Seeds",
        "- task:",
        "- method family:",
        "- modality:",
        "- datasets or benchmarks:",
        "- venues and years:",
        "- known baselines:",
        "- positive keywords:",
        "- synonyms and translations:",
        "- negative scope:",
        "",
    ]
    if seed_preview:
        scope.extend(["## Seed Preview", "```text", seed_preview, "```", ""])
    (workspace / "00_scope.md").write_text("\n".join(scope), encoding="utf-8")

    query_plan = f"""# Query Plan: {args.topic}

## Query Families

| Family | Query | Source families | Filters | Status |
|---|---|---|---|---|
| task |  | arXiv, OpenAlex, OpenReview |  | pending |
| method |  | arXiv, OpenAlex |  | pending |
| benchmark |  | arXiv, OpenAlex, proceedings |  | pending |
| application |  | arXiv, OpenAlex, web |  | pending |
| venue |  | OpenReview, proceedings, conference crawler |  | pending |
| citation graph |  | OpenAlex, paper references |  | pending |

## Notes

- Keep broad recall queries separate from high-precision validation queries.
- Add exact seed titles and method names after seed extraction.
"""
    (workspace / "01_query_plan.md").write_text(query_plan, encoding="utf-8")

    coverage = f"""# Coverage Audit: {args.topic}

## Source Ledger Summary

| Source family | Runs | Raw hits | Unique hits | Core papers | Status |
|---|---:|---:|---:|---:|---|

## Snowballing

| Anchor | Backward new core | Forward new core | Passes | Notes |
|---|---:|---:|---:|---|

## Blind Spots

- 

## Stopping Decision

Not ready. Search has not started.
"""
    (workspace / "coverage_audit.md").write_text(coverage, encoding="utf-8")

    outline = f"""# Synthesis Outline: {args.topic}

## TL;DR

## Taxonomy

## Timeline

## Core Papers

## Method and Benchmark Comparison

## Debates and Gaps

## Missing Citations or Novelty Risks

## References
"""
    (workspace / "synthesis_outline.md").write_text(outline, encoding="utf-8")

    write_csv_header(workspace / "source_ledger.csv", SOURCE_LEDGER_COLUMNS)
    write_csv_header(workspace / "papers_raw.csv", PAPER_COLUMNS)
    write_csv_header(workspace / "papers_merged.csv", PAPER_COLUMNS)
    write_csv_header(workspace / "screening.csv", SCREENING_COLUMNS)
    write_csv_header(workspace / "snowball_log.csv", SNOWBALL_COLUMNS)
    write_csv_header(workspace / "reading_matrix.csv", READING_COLUMNS)

    print(json.dumps({"workspace": str(workspace), "slug": slug}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
