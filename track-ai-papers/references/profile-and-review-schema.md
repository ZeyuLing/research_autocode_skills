# Profile and review schema

## Profile

`profile.json` is UTF-8 JSON. Required top-level fields:

- `profile_version`: currently `1`
- `name`, `language`, `timezone`
- `lookback_days`
- `max_candidates_per_topic`, `max_review_candidates` (set the latter high enough to cover the bounded discovery pool; any explicit truncation must be disclosed)
- `max_digest_papers`, `max_per_topic`
- `relevance_threshold`, `quality_threshold`, `watch_threshold`
- `topics[]`
- `quality_policy.intrinsic_weights`
- `quality_policy.overall_weights`

`language` currently accepts `zh-CN` or `en` and localizes both Markdown and HTML output. `timezone` must be an IANA name such as `Asia/Shanghai` or `America/Los_Angeles`; it controls the local calendar-day cutoff used by all sources, while persisted timestamps remain UTC for reproducibility.

`max_digest_papers` and `max_per_topic` are global across highlights plus watchlist items; highlights consume the budget first, and the watchlist can use only the remaining total and per-topic capacity.

Each topic requires:

- `id`: stable lowercase identifier
- `label`: display label
- `arxiv_categories[]`: category constraints
- `query_terms[]`: phrases used for source discovery
- `include_any[]`: phrases used for local scope matching
- `exclude_any[]`: known collisions

Weights in each group must sum to 1.0. Thresholds and caps must be positive and within their documented ranges.

## Candidate record

`candidates.json` is generated, not hand-edited. Important fields:

```json
{
  "canonical_id": "arxiv:2608.01234",
  "arxiv_id": "2608.01234",
  "title": "...",
  "abstract": "...",
  "authors": ["..."],
  "published": "2026-08-02T00:00:00Z",
  "updated": "...",
  "topics": ["llm-agents"],
  "sources": ["arxiv", "huggingface"],
  "abs_url": "...",
  "pdf_url": "...",
  "project_url": null,
  "code_url": null,
  "external": {"hf_upvotes": 0, "hf_featured": false}
}
```

## Review record

`prepare_review.py` creates a skeleton. Keep `canonical_id` unchanged. Required fields for a completed review:

```json
{
  "canonical_id": "arxiv:2608.01234",
  "primary_topic": "llm-agents",
  "matched_topics": ["llm-agents"],
  "evidence_level": "full-text",
  "confidence": "high",
  "scope_match": 88,
  "user_fit": 90,
  "problem_importance": 82,
  "method_novelty": 78,
  "evidence_strength": 84,
  "reproducibility": 75,
  "external_signal": 35,
  "scientific_problem": "...",
  "previous_work_gap": ["..."],
  "modules": [
    {
      "name": "...",
      "what": "...",
      "problem_addressed": "...",
      "why_it_works": "...",
      "evidence_anchors": ["§3.2", "Table 4"]
    }
  ],
  "experimental_evidence": ["Table 2: ..."],
  "limitations": ["..."],
  "why_read": "...",
  "fatal_concerns": [],
  "project_url": "https://example.org/project",
  "code_url": "https://github.com/example/repo",
  "notes": ""
}
```

`project_url` and `code_url` are optional enrichments discovered during full-text review; omit them when they cannot be verified. Use JSON numbers, not strings, for scores. Use `[]` rather than `null` for list fields. When a field is unknown, leave a concise explanation in `notes`; never fabricate content merely to satisfy the schema.

## Run files

- `profile.json`: copied workspace profile
- `state.json`: seen canonical IDs and timestamps
- `candidates.json`: normalized current candidates
- `source-log.json`: reproducibility and source failures
- `review-packets.md`: compact abstract triage material
- `reviewed.json`: agent-completed judgments
- `digest.md`, `digest.html`: rendered outputs
- `selection-report.json`: accepted, watchlisted, rejected, score breakdown, and reasons
- `delivery-report.json`: per-channel notification result

The source log and selection report are part of the deliverable. They prevent a polished digest from hiding retrieval failures, query-cap truncation risks, or incomplete screening.

`profile_digest` ties the profile, candidates, source log, and reviews to one configuration, while `run_id` ties them to one retrieval run. If the profile or retrieval run changes, rerun review preparation; stale reviews must not be silently restamped into a new batch.
