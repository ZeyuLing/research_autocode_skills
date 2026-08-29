# Profile and review schema

## Profile

`profile.json` is UTF-8 JSON. Required top-level fields:

- `profile_version`: `1` or `2`; new workspaces use `2`
- `name`, `language`, `timezone`
- `lookback_days`
- `max_candidates_per_topic`, `max_review_candidates` (set the latter high enough to cover the bounded discovery pool; any explicit truncation must be disclosed)
- `max_digest_papers`, `max_per_topic`
- `relevance_threshold`, `quality_threshold`, `watch_threshold`
- `topics[]`
- `quality_policy.intrinsic_weights`
- `quality_policy.overall_weights`

Version 2 additionally requires:

- `lanes[]`: `id`, `label`, `artifact_types[]`, `min_digest_items`, `max_digest_items`, and optional `lookback_days`
- `topic_quotas`: topic IDs mapped to a positive `min_if_eligible`, with optional `artifact_types[]`, `lanes[]`, and `require_primary_topic`
- `source_config.classic_catalog`
- `source_config.hf_models`: `limit`, `lookback_days`, `include_any[]`, and verification flags

The default v2 lanes are `recent-paper`, `classic-foundation`, and `open-model`. Lane minimums must fit inside `max_digest_papers`. Minimums reserve space only among candidates that already pass relevance, intrinsic-quality, evidence, and fatal-concern gates; they never turn a rejected or watchlist item into a highlight. Maximums and `max_per_topic` are hard constraints: when a minimum conflicts with a maximum, selection reports the minimum as unmet instead of bypassing the cap. The default audiovisual quota is scoped to `artifact_types: ["paper"]`, `lanes: ["recent-paper"]`, and `require_primary_topic: true`, so an open model or a paper reviewed under another primary topic cannot satisfy it. Version 1 profiles remain accepted and use the original recent-paper selection path. The scripts do not mutate a v1 workspace profile into v2.

`language` currently accepts `zh-CN` or `en` and localizes both Markdown and HTML output. `timezone` must be an IANA name such as `Asia/Shanghai` or `America/Los_Angeles`; it controls the local calendar-day cutoff used by all sources, while persisted timestamps remain UTC for reproducibility.

`max_digest_papers`, `max_per_topic`, and every lane maximum are global across highlights plus watchlist items; highlights consume the budget first, and the watchlist can use only the remaining total, per-topic, and per-lane capacity. Lane minimums apply to eligible highlights only.

Each topic requires:

- `id`: stable lowercase identifier
- `label`: display label
- `arxiv_categories[]`: category constraints
- `query_terms[]`: phrases used for source discovery
- `include_any[]`: phrases used for local scope matching
- `include_all_groups[]` (optional): every group must contribute at least one normalized term; use this for conjunctive concepts such as audio AND video AND generation
- `exclude_any[]`: known collisions

Weights in each group must sum to 1.0. Thresholds and caps must be positive and within their documented ranges.

## Candidate records

`candidates.json` is generated, not hand-edited. Every v2 candidate has `artifact_type` and `lane`.

Recent and classic papers use:

```json
{
  "artifact_type": "paper",
  "lane": "recent-paper",
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

A classic paper uses the same paper fields with `lane: "classic-foundation"`, `sources: ["curated-classics"]`, and `classic_family`. It bypasses the recent-paper cutoff but remains subject to seen-state deduplication and full-text review.

An open-model release uses:

```json
{
  "artifact_type": "model-release",
  "lane": "open-model",
  "canonical_id": "hf-model:organization/model-name",
  "entity_id": "hf-model:organization/model-name",
  "event_id": "hf-model:organization/model-name@0123456789ab",
  "model_id": "organization/model-name",
  "organization": "organization",
  "title": "organization/model-name",
  "published": "2026-08-20T00:00:00Z",
  "released_at": "2026-08-20T00:00:00Z",
  "updated": "2026-08-24T00:00:00Z",
  "version_sha": "0123456789abcdef...",
  "model_card_url": "https://huggingface.co/organization/model-name",
  "weights_url": "https://huggingface.co/organization/model-name/tree/main",
  "weight_files": ["model.safetensors"],
  "license_id": "apache-2.0",
  "license_url": "https://huggingface.co/organization/model-name/blob/main/LICENSE",
  "openness_class": "open-source",
  "pipeline_tag": "text-generation",
  "tags": ["text-generation"],
  "topics": ["open-model-releases"],
  "sources": ["huggingface-models"],
  "external": {
    "hf_model_likes": 100,
    "hf_model_downloads": 10000,
    "hf_trending_score": 8.5
  }
}
```

`canonical_id`/`entity_id` are stable across commits; `event_id` records the discovered version. This v2 minimum closed loop consumes a model entity after successful delivery and preserves the event/version in state. Do not treat `lastModified` alone as a major new release. `open-source` is reserved for the built-in permissive-license allowlist; another explicit license with ungated downloadable weights is labeled `open-weights`. `source_config.hf_models.require_open_source_license` and `allow_restrictive_open_weights` control admission; the default admits both labels while preserving the distinction. Missing license, gating, private status, or missing verified weight files blocks source admission. A model that matches no domain topic is assigned to the dedicated configured `fallback_topic` (`open-model-releases` by default), not to a scientific foundation topic.

## Review record

`prepare_review.py` creates a skeleton. Keep `canonical_id` unchanged. Required fields for a completed review:

```json
{
  "canonical_id": "arxiv:2608.01234",
  "artifact_type": "paper",
  "lane": "recent-paper",
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

For a model-release highlight use `evidence_level: "official-artifacts"` after inspecting the official model card, weight inventory, exact license, linked code, disclosed architecture/training, benchmark provenance, and constraints. The narrative fields retain the same shape: interpret `scientific_problem` as the capability/use-case target, `previous_work_gap` as the stated baseline or deployment gap, and `modules` as disclosed architecture, training, serving, or artifact strategies. Unknown details must be called out; they must not be invented to satisfy the schema.

`project_url` and `code_url` are optional enrichments discovered during full-text review; omit them when they cannot be verified. Use JSON numbers, not strings, for scores. Use `[]` rather than `null` for list fields. When a field is unknown, leave a concise explanation in `notes`; never fabricate content merely to satisfy the schema.

## Run files

- `profile.json`: copied workspace profile
- `state.json`: seen canonical IDs and timestamps, plus artifact/lane/entity/event metadata for v2 deliveries
- `candidates.json`: normalized current candidates
- `source-log.json`: reproducibility and source failures
- `review-packets.md`: compact abstract triage material
- `reviewed.json`: agent-completed judgments
- `digest.md`, `digest.html`: rendered outputs
- `selection-report.json`: accepted, watchlisted, rejected, score breakdown, reasons, and v2 `quota_fulfillment`
- `delivery-report.json`: per-channel notification result

The source log and selection report are part of the deliverable. They prevent a polished digest from hiding retrieval failures, query-cap truncation risks, or incomplete screening.

`profile_digest` ties the profile, candidates, source log, and reviews to one configuration, while `run_id` ties them to one retrieval run. If the profile or retrieval run changes, rerun review preparation; stale reviews must not be silently restamped into a new batch.
