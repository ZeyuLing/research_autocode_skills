# Review bundle template

Store a review round in a dedicated directory:

```text
thesis-review-round-YYYYMMDD/
  00-manifest.md
  01-policy-basis.md
  02-page-layout-ledger.md
  03-bibliography-audit-ledger.md
  04-citation-claim-audit-ledger.md
  05-ai-style-assessment.md
  R1-comprehensive-review.md
  R2-comprehensive-review.md
  R3-comprehensive-review.md
  R4-comprehensive-review.md      # doctorate only
  R5-comprehensive-review.md      # doctorate only
  90-chair-synthesis.md
  91-revision-ledger.md
  92-new-evidence-or-experiments.md
  99-rereview.md                  # re-review rounds
```

For a master's thesis, all three are comprehensive reviewers: R1 has a technical/experimental emphasis, R2 a contribution/thesis-logic emphasis, and R3 an evidence/standards emphasis.

Use the neutral `comprehensive-review` filenames for new rounds so the file path does not imply an exclusive scope. Put the persona emphasis inside each report. Existing frozen rounds may retain their historical filenames; do not rename or rewrite them retroactively.

Both citation ledgers are mandatory. For a doctorate, R5 owns `03-bibliography-audit-ledger.md` and R4 owns `04-citation-claim-audit-ledger.md`; for a master's thesis, R3 owns both. Follow `citation-audit.md`. The two doctoral owners freeze their ledgers independently before the chair reconciles them.

`05-ai-style-assessment.md` is mandatory for both degree levels but is not an R-numbered reviewer report. Its assessor freezes independently from the reviewer panel and follows `ai-style-audit.md`.

## Manifest

```markdown
# Frozen evidence manifest

- Degree/institution/discipline:
- Review round and purpose:
- Frozen PDF path, SHA-256, timestamp, and pages:
- Governing template/rules:
- Reviewer-visible artifact: exactly one frozen thesis PDF
- Permitted public citation-verification sources:
- Prohibited local artifacts: thesis source, `.bib`, build/auxiliary files, Git history, sibling repositories, local papers, code/config/logs, old rounds, and author-side records
- Items explicitly out of scope:

## Thesis structure
...

## Scientific question -> chapter -> contribution map
...

## Claim -> evidence map
...
```

## Independent reviewer report

```markdown
# Rn — Comprehensive whole-thesis review — persona emphasis

## Role, scope, and independence
- Whole-thesis mandate: Gate A--I
- Persona emphasis:
- Separate exhaustive audit duties, if any:
- Independence declaration:
- Input-access declaration: list every local artifact actually opened; confirm that no prohibited local artifact was accessed

## Verdict
- Decision regime: institutional / skill-default
- Official category, defense recommendation, and governing source: required under `institutional`; otherwise N/A
- Academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Defense recommendation: 同意答辩 / 小修后可答辩 / 大修后重新送审，复审通过后方可答辩 / 不同意答辩 — required under `skill-default`; otherwise use the official wording above
- Confidence:
- One-paragraph whole-thesis rationale:

## What I inspected
...

## Whole-thesis synthesis
- Central thesis problem and overall answer:
- Degree-level contribution judgment:
- Strongest claim--evidence chain:
- Weakest claim--evidence chain:
- Cross-chapter coherence:
- Overall integrity and submission fitness:
- Most consequential conclusion outside the persona emphasis, or evidence that no material concern was found there:

## Whole-thesis assessment

| Gate | Review depth (`baseline` / `emphasized` / `primary`) | Disposition (`adequate` / `concern` / `unverifiable` / `N/A`) | Decisive evidence and exact locations | Related finding IDs or `none` | Confidence/limitation |
|---|---|---|---|---|---|
| A — policy, identity, ethics, integrity | ... | ... | ... | ... | ... |
| B — thesis-level story | ... | ... | ... | ... | ... |
| C — topic, literature, novelty, positioning | ... | ... | ... | ... | ... |
| D — methods and scientific reasoning | ... | ... | ... | ... | ... |
| E — data and evaluation protocol | ... | ... | ... | ... | ... |
| F — experiments and results | ... | ... | ... | ... | ... |
| G — reproducibility and disclosed traceability | ... | ... | ... | ... | ... |
| H — writing and self-contained exposition | ... | ... | ... | ... | ... |
| I — figures, tables, equations, citations, references, pages | ... | ... | ... | ... | ... |

Use `N/A` only when the gate is genuinely inapplicable to the thesis, not because another reviewer owns a related ledger. A report is incomplete if any Gate A--I row is omitted, lacks an evidence anchor, or uses a depth label as a score. Do not invent a finding merely to populate a gate; an evidence-backed strength or `none` is valid.

## Persona-weighted deep review

Explain the additional scrutiny performed because of this reviewer's expertise. This section supplements the common assessment; it does not define the report's entire scope.

## Strongest contributions
1. ...

## Findings

### Rn-F01 — short title
- Primary gate: A/B/C/D/E/F/G/H/I
- Secondary gates: any affected gates or `none`
- Scope: thesis-wide / cross-chapter / chapter / local
- Severity: S0/S1/S2/S3/S4
- S0 subtype: procedural / integrity/foundational / N/A
- Remedy: W/E/N/P
- Required for the current defense conclusion: yes/no; if `yes` with remedy `N`, the skill-default grade cannot exceed C until the evidence is supplied or the dependent claim is validly narrowed
- Location: exact PDF physical/logical page and section/table/figure/equation
- Observation: directly visible fact
- Why it matters: affected rule, claim, or reader task
- Evidence: visible PDF excerpt/data or a permitted public source used to verify a citation, without excessive quotation
- Required action: minimum sufficient remedy
- Verification: how to confirm closure
- Confidence: high/medium/low

## Questions, not findings
...

## Coverage and limitations
...
```

The page-layout-owning reviewer (doctoral R5 or master's R3) must additionally report the following audit-duty section after completing the same whole-thesis report as every other reviewer. This section cannot substitute for the Gate A--I matrix or persona-weighted analysis:

```markdown
## Full rendered-page audit
- Physical pages / unchecked pages:
- Suspect-page signals / resolved / unresolved:
- Actionable layout findings:
- Neighbor-page verification status:
- Source-forcing cause: `not verifiable from the PDF`
```

The bibliography-owning reviewer (doctoral R5 or master's R3) must additionally report the following audit-duty section after completing the same whole-thesis report as every other reviewer. This section cannot substitute for the Gate A--I matrix or persona-weighted analysis:

```markdown
## Full bibliography-integrity audit
- Bibliography entries rendered in the frozen PDF:
- Bibliography master rows / unchecked rows:
- Title fields verified / mismatched / unverifiable:
- Ordered-author fields verified / mismatched / unverifiable:
- Year fields verified / mismatched / unverifiable:
- Venue and publication-status fields verified / mismatched / unverifiable:
- Page-range or article-number fields verified / mismatched / legitimate N/A / unverifiable:
- DOI/arXiv/URL fields verified / mismatched / legitimate N/A / unverifiable:
- Suspected fabricated/nonexistent entries and adjudication status:
- Metadata/status verified entries:
```

The citation-claim-owning reviewer (doctoral R4 or master's R3) must additionally report the following audit-duty section after completing the same whole-thesis report as every other reviewer. This section cannot substitute for the Gate A--I matrix or persona-weighted analysis:

```markdown
## Full citation-claim audit
- Active citation occurrences:
- Citation--source pairs:
- Unique cited keys:
- Semantically verified pairs:
- Partial-support pairs:
- Context-only pairs:
- Mismatch pairs:
- Inaccessible/unverifiable pairs:
- Ledger rows and unchecked rows:
```

Questions are not counted as defects until evidence supports them.

Before freezing an R-numbered report, verify that the decision regime, category, recommendation, severity profile, and required revision path are consistent with `grading-and-verdicts.md`.

## Standalone AI-style assessment

```markdown
# Standalone AI-style prose assessment

## Boundary and independence
- Frozen artifact:
- Reviewer-visible inputs:
- Excluded material:
- Independence declaration:
- Input-access declaration:
- Required disclaimer: This is a prose-style assessment, not a determination of AI use, authorship, plagiarism, or misconduct.

## Overall judgment
- AI-style signal: low / moderate / high / indeterminate
- Confidence: high / medium / low
- Rationale:

## Coverage and mechanical checks
- Physical pages inspected:
- Authored sections inspected:
- Recurrent-pattern queries/statistics:
- Corpus exclusions:

## Signal-family summary and counter-evidence
...

## Findings

### AI-F01 — short title
- Impact: material / local / optional
- Location: exact PDF page and section
- Recurrent evidence:
- Reader impact:
- Minimum safe editing strategy:
- Closure test:

## Limitations
...
```

Do not add an academic/defense category, R1--R5 severity, AI probability, or misconduct finding to this report.

## Chair synthesis

```markdown
# Chair synthesis

## Overall risk and recommendation
- Decision regime: institutional / skill-default
- Overall official category, recommendation, and governing source: required under `institutional`; otherwise N/A
- Overall academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Overall defense recommendation: exact Chinese action conclusion
- Confidence:
- Whole-thesis rationale:
- Chair input-access declaration: list every local artifact opened; confirm that only the frozen PDF packet, permitted public citation sources, and frozen reviewer reports were used

## Reviewer coverage validation
| Reviewer | Gate A | B | C | D | E | F | G | H | I | Whole-thesis rationale | Audit duty complete | Eligible for adjudication |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

Validate this table before substantive synthesis. A report with a missing gate row must be returned to the same isolated reviewer for completion before that reviewer sees any other report.

## Independent verdicts
| Reviewer | Persona | Category/grade | Defense recommendation | Decision regime/source | Confidence | Decisive reason |
|---|---|---|---|---|---|---|

State the category distribution. Under the skill-default regime, do not convert letters to numbers: the chair's overall grade is an evidence-adjudicated decision, not an average, median, or automatic majority result. Explain any departure from a severe minority opinion or from the modal category.

## Standalone AI-style judgment
- Signal: low / moderate / high / indeterminate
- Confidence:
- Material/local/optional findings:
- Separation statement: report this outside the reviewer verdict distribution and do not infer AI use, authorship, plagiarism, or misconduct.

## Contributions that survived review
...

## Adjudicated findings
| ID | Severity | Remedy | Reviewers | Evidence status | Owner | Required action | Verification |

## Disagreements and chair decisions
| Topic | Positions | Evidence checked | Decision or unresolved status |

## Thesis-level narrative and chapter logic
...

## Policy and blind-copy status
...

## Review limitations
...
```

## Revision ledger

Prioritize by risk, not by chapter order.

```markdown
| Priority | Finding | Exact edits/evidence | Dependency | Owner | Status | Verification |
|---|---|---|---|---|---|---|
| P0 | S0/S1 blocker | ... | ... | ... | open | ... |
| P1 | material S2 | ... | ... | ... | open | ... |
| P2 | S3/local | ... | ... | ... | open | ... |
```

## New evidence or experiments

Always split the list:

```markdown
## No-new-experiment remedies (W/E/P)
- Existing evidence the author may recover in a separate revision task; reviewers do not inspect it:
- Writing or claim narrowing:
- Policy confirmation:

## Genuine new experiments or unavailable evidence (N)
| Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |
```

An empty `N` table is a valid and often preferable result.

## Re-review

```markdown
## Fresh category and defense recommendation
- Decision regime: institutional / skill-default
- Official category, recommendation, and governing source: required under `institutional`; otherwise N/A
- Academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Defense recommendation: exact Chinese action conclusion
- Confidence:
- Rationale for the newly frozen artifact:

## Fresh Gate A--I whole-thesis assessment
Repeat the complete nine-row matrix from the independent-review template before consulting the prior issue ledger.

| Prior finding | Status | Evidence in revised thesis | Regression check | Reviewer |
|---|---|---|---|---|

## New findings
...

## Final recommendation
...
```

For an iterative review--revision loop, the final recommendation must also state:

- whether every physical page was re-entered in the page ledger after the last edit;
- whether every physical page and all affected neighboring pages were rechecked in the final PDF;
- whether every bibliography entry was re-entered in the bibliography ledger, all citation--source pairs were re-entered in the citation-claim ledger, and every changed or repeated source use was reverified;
- whether every reviewer returned an empty actionable `S0`--`S3` Findings section;
- whether a fresh isolated `05-ai-style-assessment.md` was run on the final frozen artifact, its signal level, and whether any material prose-polish finding remains;
- whether any `S4` suggestion or review limitation remains.
