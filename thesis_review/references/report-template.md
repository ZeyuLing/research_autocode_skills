# Review bundle template

Store a review round in a dedicated directory:

```text
thesis-review-round-YYYYMMDD/
  00-manifest.md
  01-policy-basis.md
  02-page-layout-ledger.md
  03-citation-audit-ledger.md
  R1-technical-experiments.md
  R2-field-contribution.md
  R3-thesis-logic.md
  R4-evidence-integrity.md        # doctorate only
  R5-format-standards.md          # doctorate only
  90-chair-synthesis.md
  91-revision-ledger.md
  92-new-evidence-or-experiments.md
  99-rereview.md                  # re-review rounds
```

For a master's thesis, use R1 technical/experimental, R2 contribution/logic, and R3 evidence/standards.

`03-citation-audit-ledger.md` is mandatory. It is owned by R4 for a doctorate and R3 for a master's thesis; follow `citation-audit.md`.

## Manifest

```markdown
# Frozen evidence manifest

- Degree/institution/discipline:
- Review round and purpose:
- Thesis path:
- Git commit/checksum:
- Compiled PDF path, timestamp, and pages:
- Governing template/rules:
- Reviewer-visible artifacts and public sources:
- Author-side papers/repos/logs (not visible to R1--R5 before verdict):
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
# Rn — persona

## Verdict
- Decision:
- Confidence:
- One-paragraph rationale:

## What I inspected
...

## Strongest contributions
1. ...

## Findings

### Rn-F01 — short title
- Severity: S0/S1/S2/S3/S4
- Remedy: W/E/N/P
- Location: exact PDF page and source/section/table/figure/equation
- Observation: directly visible fact
- Why it matters: affected rule, claim, or reader task
- Evidence: thesis excerpt/data/source comparison without excessive quotation
- Required action: minimum sufficient remedy
- Verification: how to confirm closure
- Confidence: high/medium/low

## Questions, not findings
...

## Coverage and limitations
...
```

The citation-owning reviewer must additionally report:

```markdown
## Full citation audit
- Active citation occurrences:
- Citation--source pairs:
- Unique cited keys:
- Bibliography entries:
- Semantically verified pairs:
- Partial-support pairs:
- Mismatch pairs:
- Inaccessible/unverifiable pairs:
- Metadata/status verified entries:
- Ledger rows and unchecked rows:
```

Questions are not counted as defects until evidence supports them.

## Chair synthesis

```markdown
# Chair synthesis

## Overall risk and recommendation
...

## Independent verdicts
| Reviewer | Persona | Verdict | Confidence | Decisive reason |

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

## Author-side provenance audit
List private paper/repository/log checks separately. Do not attribute these findings to the blind panel or use them to retroactively lower an independent grade.

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
- Existing paper/repository evidence to recover:
- Writing or claim narrowing:
- Policy confirmation:

## Genuine new experiments or unavailable evidence (N)
| Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |
```

An empty `N` table is a valid and often preferable result.

## Re-review

```markdown
| Prior finding | Status | Evidence in revised thesis | Regression check | Reviewer |
|---|---|---|---|---|

## New findings
...

## Final recommendation
...
```

For an iterative review--revision loop, the final recommendation must also state:

- whether every physical page was re-entered in the page ledger after the last edit;
- whether all forcing constructs were remapped to the final PDF and neighbor pages rechecked;
- whether all citation--source pairs were re-entered in the citation ledger and every changed or repeated source use was reverified;
- whether every reviewer returned an empty actionable `S0`--`S3` Findings section;
- whether any `S4` suggestion or review limitation remains.
