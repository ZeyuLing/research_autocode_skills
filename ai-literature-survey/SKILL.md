---
name: ai-literature-survey
description: Exhaustive, source-audited literature discovery for AI, CV, NLP, ML, robotics, multimodal, and adjacent research topics. Use when the user asks to survey a rough research idea, find almost all related papers, write or repair related work, position a half-finished paper, trace prior art, build a citation graph, monitor new arXiv/OpenReview papers, or produce a coverage-audited literature review in English or Chinese. Triggers include literature review, related work, prior art search, survey, arXiv/OpenAlex/OpenReview search, paper positioning, 综述, 文献调研, 相关工作, 查全相关论文, 选题调研.
---

# AI Literature Survey

Use this skill to turn a topic, rough requirement, or draft paper into a reproducible literature corpus and a defensible synthesis. The standard is high recall: do not call the review "complete" until the source ledger and coverage audit show what was searched, what was missed, and why the stopping condition is reasonable.

## Quick Start

1. Create a survey workspace before doing substantial search:

```bash
python3 scripts/init_survey_workspace.py --topic "<topic or research question>" --out-dir literature-surveys
```

If the user gives a draft, proposal, related-work section, PDF, or LaTeX source, pass it as `--seed-file` and extract claims, keywords, baselines, datasets, and citations before designing searches.

2. Load the references only as needed:
- `references/source-map.md` for which cloned upstream repo or external source to use.
- `references/coverage-protocol.md` for the end-to-end high-recall workflow and stopping rules.
- `references/artifact-schema.md` for required files and record columns.

3. Keep every search run recoverable. Record source, query, filters, dates, command or URL, count returned, and failure notes in `source_ledger.csv` or `coverage_audit.md`.

## Workflow

### 0. Scope the Problem

Extract and write down:
- target task, method family, modality, dataset or benchmark, application domain, and claimed novelty
- positive keywords, synonyms, acronyms, translations, and spelling variants
- negative scope and near-miss topics that should be excluded
- key venues and years to cover, usually current year back to the first clear ancestor
- seed papers from the user, draft references, cited baselines, leaderboard entries, and known methods

If the scope is vague, make a reasonable first-pass query plan and state the assumptions. Ask only when the missing choice would materially change the search space.

### 1. Build the Query Plan

Create several query families instead of one large keyword bag:
- task queries: what problem is solved
- method queries: architecture, training objective, representation, algorithm, or data construction
- benchmark queries: dataset, metric, simulator, protocol, leaderboard
- application queries: domain-specific names and downstream use cases
- author or lab queries: only for known seed clusters
- venue queries: conference or workshop accepted-paper sources

Use exact phrases for narrow concepts, OR groups for synonyms, and separate broad recall queries from high-precision validation queries.

### 2. Search Multiple Source Families

Run at least these families unless explicitly out of scope:
- arXiv for preprints and latest work
- OpenAlex for cross-venue metadata, citations, DOI, venue, and open-access links
- OpenReview for ICLR, NeurIPS, ICML, EMNLP, and similar review-platform venues
- official proceedings or venue pages for CVPR, ICCV, ECCV, NeurIPS, ACL, EMNLP, NAACL, ICLR, ICML, AAAI, SIGGRAPH, and domain-specific venues
- arXiv comments based conference crawls for "accepted to CVPR/ICCV/ECCV/NeurIPS/ICML" style metadata
- daily paper or hotspot feeds for very recent work not yet indexed elsewhere
- bibliographies and forward citations from seed and anchor papers

See `references/source-map.md` for the local upstream clones and preferred fallback order.

### 3. Normalize and Deduplicate

Normalize all candidates into one table before screening. Prefer DOI, arXiv ID, OpenAlex ID, then normalized title as dedup keys. Use:

```bash
python3 scripts/merge_paper_records.py raw_source_1.json raw_source_2.csv --output papers_merged.csv
```

Keep duplicates as merged `sources` rather than deleting provenance. If a candidate appears in multiple independent sources, raise its priority for screening.

### 4. Snowball the Citation Graph

For each seed and high-relevance anchor:
- backward snowball: inspect references for older ancestors and baselines
- forward snowball: inspect citing papers for follow-ups, variants, and evaluations
- sibling search: inspect papers sharing datasets, benchmarks, codebases, or distinctive terms

Repeat at least two passes for core anchors. Stop only when new passes produce no new core papers, or only adjacent/background papers with documented reasons.

### 5. Screen with Tiers

Assign every candidate a tier:
- `core`: directly addresses the research question or method family
- `adjacent`: shares a dataset, modality, benchmark, or subproblem
- `background`: foundational or historical context
- `exclude`: outside scope, with a short reason

Do not exclude exact-scope recent papers just because citation counts are low. Use citations for prioritization, not as the only relevance gate.

### 6. Read and Extract Evidence

For core papers, extract:
- problem and claimed contribution
- method components and assumptions
- datasets, metrics, baselines, and evaluation protocol
- empirical result that matters
- limitations, failure cases, and open questions
- relation to the user's idea or draft

Never fabricate missing details. Mark fields as `unknown`, `abstract-only`, or `not-read` when full text is unavailable.

### 7. Synthesize for the User's Goal

Choose the output shape based on the request:
- topic survey: taxonomy, timeline, method families, datasets, debates, gaps
- draft-paper support: missing citations, closest prior work, novelty risk, positioning suggestions, related-work outline
- daily monitoring: watch queries, update cadence, and a delta report of new core papers
- bibliography package: ranked reading list, BibTeX or citation table, source ledger, coverage audit

Every major claim in the synthesis must be backed by paper IDs or citations from the corpus.

## Coverage Gates

Before finalizing, verify:
- source ledger includes all planned source families or explicit reasons for skipping them
- query families cover task, method, benchmark, application, and venue dimensions
- seed-paper references and citing papers were checked for core anchors
- top venues and current-year preprints were covered
- dedup statistics and screening counts are reported
- limitations are stated without overselling "all papers"

Use cautious language: "near-complete under these sources and dates" is better than an unsupported claim of total exhaustiveness.
