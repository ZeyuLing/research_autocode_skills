# Coverage Protocol

Use this protocol when the user asks for "almost all related literature" or when the output will support claims in a paper.

## Phase A: Seed Extraction

For a rough topic, create seed terms from:
- task, modality, method, dataset, benchmark, and application
- synonyms, acronyms, spelling variants, old names, and Chinese/English translations when relevant
- known baselines, closest models, authors, labs, and project names

For a draft paper, also extract:
- title, abstract, contributions, and claims
- citations already present and papers conspicuously missing
- baselines and datasets mentioned in experiments
- terminology unique to the paper
- the exact novelty sentence or implicit novelty risk

## Phase B: Query Matrix

Build a matrix with rows as concept families and columns as source families.

Rows:
- task
- method
- benchmark or dataset
- application
- related method family
- exact seed paper title or method name

Columns:
- arXiv
- OpenAlex
- OpenReview
- official proceedings
- citation graph
- web or project pages
- daily paper and monitoring feeds

Each filled cell should have at least one query or a documented reason for skipping.

## Phase C: Multi-Source Recall

Run broad search first, then high-precision validation.

Recommended breadth settings:
- arXiv: 50 to 200 results per broad query if the topic is wide
- OpenAlex: 100 to 200 results per query with year and venue filters as needed
- citation graph: up to 100 references and 100 citations per anchor before filtering
- venue pages: all accepted papers for the relevant venue/year when the venue is central

Do not rely on a single keyword. If the user says "diffusion for motion generation", also try motion synthesis, text-to-motion, human motion generation, generative motion prior, MDM, motion diffusion model, and benchmark names.

## Phase D: Dedup and Source Ledger

Merge candidates before judging coverage. Keep provenance:
- one paper can have several sources
- query failures are recorded with error messages
- empty queries are recorded when they are meaningful
- date of access is recorded for web and current-year sources

Use `scripts/merge_paper_records.py` for CSV, JSON, and JSONL exports.

## Phase E: Screening and Recall Repair

Screen quickly by title and abstract, then repair missed zones:
- If many core papers come from one source, search their shared terminology again.
- If all core papers are recent, run backwards citation search for roots.
- If all core papers are from arXiv, check proceedings and OpenReview.
- If all papers use one benchmark, search adjacent benchmark names.
- If a seed paper cites a cluster not found by keyword search, add that cluster to the query matrix.

## Phase F: Stopping Rules

A near-complete review can stop when all are true:
- every planned source family has been searched or explicitly waived
- two consecutive snowball passes over core anchors add no new core papers
- top relevant venues and years have been checked
- latest arXiv or daily-feed search has been checked for the current window
- excluded papers have reasons, not just silence
- the coverage audit states known blind spots

If these are not true, describe the result as "partial", "initial", or "high-confidence for the searched sources" rather than complete.

## Failure Modes to Avoid

- Treating arXiv as the whole literature.
- Treating citation count as relevance.
- Missing new papers because OpenAlex has not indexed them yet.
- Missing accepted papers because arXiv comments do not mention venue names.
- Reading only survey papers and inheriting their blind spots.
- Forgetting workshops, datasets, and benchmark papers that define the evaluation protocol.
- Overwriting raw exports before dedup or screening.

## Final Coverage Audit Template

```markdown
# Coverage Audit: <topic>

## Scope
- Included:
- Excluded:
- Years:
- Venues:

## Source Ledger Summary
| Source family | Runs | Raw hits | Unique hits | Core papers | Status |
|---|---:|---:|---:|---:|---|

## Query Families
| Family | Queries | Notes |
|---|---|---|

## Snowballing
| Anchor | Backward new core | Forward new core | Passes | Notes |
|---|---:|---:|---:|---|

## Blind Spots
- 

## Stopping Decision
Near-complete under the listed sources because:
1.
2.
3.
```
