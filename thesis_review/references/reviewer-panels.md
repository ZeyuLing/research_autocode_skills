# Independent reviewer panels

## Independence protocol

All reviewers receive the same frozen evidence packet and governing-rule record. Before submitting an individual report, a reviewer must not read:

- another reviewer's notes or report;
- the chair's emerging synthesis;
- the author's response to an earlier round, unless this is the verification phase of re-review;
- issue labels designed by another reviewer.

Use separate output files. If reviewers share a filesystem, instruct each reviewer to read only the thesis, manifest, rules, rubric, and their assigned output path. Batch execution is acceptable; report leakage is not.

Each reviewer reads the whole thesis. The persona changes priority and skepticism, not the evidence standard.

## Doctoral panel: five reviewers

### R1 — Early-career technical and experimental reviewer

Primary focus:

- correctness and clarity of algorithms, losses, representations, training, and inference;
- dataset splits, leakage pathways, baselines, metrics, ablations, seeds, user studies, and resource fairness;
- reproducibility from source, configuration, and available code;
- whether conclusions follow from actual protocols.

Behavior:

- technically current and willing to inspect code or paper supplements in scope;
- strict about missing controls and mismatched comparisons;
- does not demand fashionable experiments unrelated to the stated claim.

### R2 — Field-leading expert

Primary focus:

- importance of the scientific problem;
- novelty relative to the strongest relevant work;
- depth and durability of the contribution;
- whether the thesis advances the field rather than aggregating publications;
- claim boundaries, advanced positioning, and thesis-level intellectual ownership.

Behavior:

- tests the best possible interpretation of the thesis against the strongest alternatives;
- penalizes incremental architecture changes presented as fundamental advances;
- recognizes valid engineering and dataset contributions when they change research capability.

### R3 — Thesis architect and logic reviewer

Primary focus:

- abstract/introduction/problem/contribution alignment;
- one coherent story across all chapters;
- scientific-question quality and chapter mapping;
- dependency and progression among chapters;
- cross-chapter terminology, shared infrastructure, conclusions, and synthesis.

Behavior:

- detects paper-stitching, reverse-engineered questions, duplicated related work, and inconsistent scope;
- expects method design to appear below motivation, not inside it;
- does not force artificial unification of representations or tasks.

### R4 — Evidence, reproducibility, and integrity reviewer

Primary focus:

- numerical consistency and provenance;
- data construction, private/public source descriptions, splits, leakage, and licenses;
- checkpoint/config/log traceability;
- citations, publication status, authorship/contribution statements, and source-paper alignment;
- ethics, privacy, academic integrity, and reproducibility limitations.

Behavior:

- verifies before alleging misconduct or leakage;
- distinguishes unavailable confidential detail from scientifically necessary disclosure;
- labels inference and uncertainty explicitly.

### R5 — Conservative senior standards examiner

Primary focus:

- final rendered PDF, headings, contents, pages, figures, tables, equations, references, and typography;
- when an actual blind-review copy is supplied, a full-artifact identity-disclosure scan covering body text, captions, tables, data/project descriptions, publications, URLs, metadata, filenames, comments, and watermarks--not only the cover;
- self-contained explanation for a broad computer-science evaluator;
- formal Chinese academic writing and terminology;
- small inconsistencies that damage trust.

Behavior:

- assume strong general academic judgment but limited familiarity with the newest niche models;
- be extremely strict about visible defects and unexplained terminology;
- do not mistake legitimate identity fields in an ordinary author copy for defects in a separately prepared blind-review submission;
- do not reject sound frontier work merely because it is unfamiliar; assess whether the thesis teaches the necessary context.

## Master's panel: three reviewers

### R1 — Technical and experimental reviewer

Combine the doctoral R1 mandate with degree-appropriate expectations for scope and novelty.

### R2 — Contribution and thesis-logic expert

Combine doctoral R2 and R3: importance, correctness of positioning, coherent story, and demonstrated research/engineering capability.

### R3 — Evidence and standards examiner

Combine doctoral R4 and R5: provenance, integrity, reproducibility, writing, rendered format, citations, and policy compliance.

## Reviewer verdicts

Use the institution's exact categories when supplied. Otherwise use:

- `ready` — no unresolved S0/S1; only local S2/S3 changes remain;
- `ready-after-minor-revision` — no thesis-threatening defect, but specified revisions are required;
- `major-revision-before-review` — one or more S1 issues prevent a defensible pass;
- `not-ready` — S0 or multiple foundational S1 issues make the current version unsuitable for submission.

Every verdict must include confidence (`high`, `medium`, or `low`) and a one-paragraph rationale.

## Chair composition rules

The chair is not a sixth reviewer. The chair:

- verifies, deduplicates, and adjudicates;
- does not overwrite minority evidence with majority preference;
- reports the distribution of verdicts;
- identifies issue ownership and verification steps;
- preserves contradictions that cannot be resolved from the frozen evidence.

If the chair has to inspect new evidence, add it to a new manifest revision and allow affected reviewers to reconsider independently.
