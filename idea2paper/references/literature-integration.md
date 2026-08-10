# AI Literature Survey Integration

Treat `ai-literature-survey` as a hard dependency. Invoke it for initial discovery, novelty repair, missing-citation checks, and every delta search after a material idea change.

## Invocation contract

Pass the current:

- idea text and version;
- target task, method family, modality, application, datasets, and claimed novelty;
- target venue and years of interest;
- user seed papers, draft text, baselines, and project links;
- in-domain query families and cross-domain analogical query families.

Direct the survey workspace to `<project>/related_works/`. Preserve its standard files without renaming them.

After the survey completes, record its invocation and immutable artifact hashes:

```bash
python scripts/record_survey_run.py <project>/related_works \
  --idea-version <idea_vN> --invocation-id <survey-run-id> \
  --receipt <dispatch-layer-survey-receipt.json>
```

The receipt must be captured by the orchestrator at the actual skill dispatch and contain the invoked SKILL.md path/hash, request hash, invocation ID, orchestrator run ID, and timezone-aware start/completion timestamps. Do not create this provenance record for an ad hoc search. A failed or partial
manifest blocks `LITERATURE_AUDITED`.

Require task, method, benchmark, application, venue, exact-seed, and citation-graph queries. Search both direct prior art and papers from other domains that share the core mechanism or insight.

## Coverage gate

Do not finish the literature stage until:

- arXiv/current preprints, OpenAlex, OpenReview, official proceedings, citation graph, and web/project sources were each searched or explicitly waived in the ledger with a `WAIVER:` reason;
- at least four source groups were actually searched, including current preprints and citation graphs, and at least one of OpenReview or official proceedings;
- official proceedings or OpenReview were checked for relevant top venues;
- current preprints were checked;
- core anchors completed at least two zero-new-core passes, with both backward and forward rows for every anchor in each pass;
- two consecutive passes add no new core papers;
- exclusions have reasons;
- `coverage_audit.md` records blind spots and a stopping decision.

Describe coverage as near-complete under stated sources and dates, never as literally all literature.

For a full paper sketch, source-family coverage alone is insufficient. The audited
corpus must also satisfy all of the following relevance floors:

- at least 30 screened records with tier `core`, `adjacent`, or `background`;
- at least 10 `core` papers with completed reading-matrix evidence extraction;
- at least five non-empty `coverage_family` groups, chosen from task foundations,
  closest competing mechanisms, datasets/evaluation, control/physics/safety,
  application-specific work, and genuinely analogous adjacent mechanisms;
- at least eight included papers from the current year or previous two calendar years;
- at least eight accepted/published included works with status evidence;
- at least three included records marked `novelty_risk=yes` as closest collisions;
- at least 25 distinct audited corpus citations in the complete manuscript and at
  least 20 in Related Work.

These are floors, not targets. Do not satisfy them with citation padding: an included
paper must be relevant to a claim, method choice, benchmark, evaluation protocol, or
novelty boundary. Excluded papers and BibTeX entries never cited by the manuscript do
not count. If a search initially yields fewer records, expand query families, inspect
anchor references/citations, search benchmark and venue clusters, and repair missing
coverage before drafting Related Work.

## Enriched paper record

Run `scripts/enrich_literature.py` after merge. Add these fields without guessing:

| Field | Allowed examples |
|---|---|
| stable_id, bib_key | Persistent local identity and the LaTeX citation key |
| `coverage_family` | One or more semicolon-separated audited taxonomy families. |
| `publication_status` | `accepted`, `published`, `preprint_only`, `under_review`, `withdrawn`, `retracted`, `rejected`, `unknown` |
| `status_venue`, `status_year` | Verified venue and edition or blank |
| `status_evidence_url`, `status_checked_at` | Evidence and access time |
| `paper_access_status` | `open_pdf`, `open_html`, `metadata_only`, `unknown` |
| `official_code_status` | `available`, `announced`, `none_found`, `unknown` |
| `code_url`, `code_license` | Official artifact and license |
| `data_status`, `data_url` | Dataset artifact status |
| `weights_status`, `weights_url` | Model-weight artifact status |

Do not infer formal acceptance from arXiv comments when official proceedings or OpenReview decisions are available. Do not treat any GitHub link as official open source without authorship and license evidence.

## Local storage

- Create a local record directory for every `core`, `adjacent`, and `background` paper.
- Store notes, metadata, evidence URLs, and legal open-access PDFs there.
- For closed papers, store metadata and landing links only; never bypass authentication or paywalls.
- Preserve excluded candidates in `screening.csv`, without creating full record directories.

## Must-cite policy

Set `must_cite=yes` for a paper when it is directly relevant and any of these holds:

- it is the closest prior work;
- it establishes the problem, dataset, benchmark, or protocol;
- it is a relevant accepted top-conference/top-journal work;
- it is a recent preprint that materially threatens novelty;
- it reports a limitation or negative result central to the paper's claim.

Relevance outranks venue prestige. Related Work must cover every final `must_cite=yes` record.

## Delta survey

Trigger a delta survey when the Professor changes the problem, core claim, method family, main dataset, evaluation protocol, or contribution type. Search only the changed concepts plus their intersections with the retained idea, then merge results with provenance and rerun the coverage audit for the affected scope.
