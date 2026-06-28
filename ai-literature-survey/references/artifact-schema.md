# Artifact Schema

Create a workspace for each survey. The default script layout is:

```text
<survey-slug>/
  00_scope.md
  01_query_plan.md
  source_ledger.csv
  papers_raw.csv
  papers_merged.csv
  screening.csv
  snowball_log.csv
  reading_matrix.csv
  coverage_audit.md
  synthesis_outline.md
  notes/
  exports/
```

## Paper Record Columns

Use these columns across CSV exports when possible:

| Column | Meaning |
|---|---|
| `record_id` | stable local ID after merge |
| `title` | paper title |
| `authors` | semicolon-separated authors |
| `year` | publication or preprint year |
| `venue` | conference, journal, arXiv, OpenReview venue, or unknown |
| `sources` | semicolon-separated provenance sources |
| `url` | landing page or best available source URL |
| `pdf_url` | PDF URL if known |
| `doi` | DOI without URL prefix when possible |
| `arxiv_id` | arXiv ID without URL prefix |
| `openalex_id` | OpenAlex work ID or URL |
| `citation_count` | numeric count when known |
| `abstract` | abstract or short summary |
| `tier` | core, adjacent, background, exclude |
| `screening_reason` | short include or exclude reason |
| `full_text_status` | unread, metadata-only, abstract-only, full-text, not-available |
| `notes_path` | local note path if read |

## Source Ledger Columns

| Column | Meaning |
|---|---|
| `run_id` | stable run ID, such as S001 |
| `date` | date run was executed |
| `source_family` | arxiv, openalex, openreview, proceedings, citation_graph, daily_feed, web |
| `source_name` | concrete tool, repo, website, or API |
| `query` | exact query string or URL |
| `filters` | categories, years, venues, limits |
| `command_or_url` | command run or URL visited |
| `raw_output` | path to raw export, if any |
| `raw_hits` | count returned before dedup |
| `unique_hits` | count after merge, if known |
| `status` | ok, empty, failed, skipped |
| `notes` | failure reason or caveat |

## Screening Columns

| Column | Meaning |
|---|---|
| `record_id` | local ID from merged paper table |
| `title` | paper title |
| `tier` | core, adjacent, background, exclude |
| `reason` | one sentence reason |
| `read_priority` | high, medium, low |
| `must_cite` | yes, no, maybe |
| `novelty_risk` | yes, no, maybe |

## Reading Matrix Columns

| Column | Meaning |
|---|---|
| `record_id` | local ID |
| `claim` | paper's central claim |
| `method` | method summary |
| `data` | datasets or benchmarks |
| `metrics` | metrics and protocols |
| `baselines` | baselines compared |
| `result` | key quantitative or qualitative result |
| `limitation` | stated or inferred limitation |
| `relation_to_user_work` | support, contrast, prior art, risk, background |
| `quote_or_evidence` | short evidence pointer; avoid long copyrighted quotes |

## Output Packages

For a serious review, deliver:
- ranked paper list with tiers and reasons
- source ledger summary
- coverage audit
- taxonomy or timeline
- draft related-work outline or prose, if requested
- missing-citation and novelty-risk list for half-finished papers
