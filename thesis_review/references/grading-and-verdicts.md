# Academic grade and defense recommendation

Every panel reviewer must issue one explicit operational defense conclusion based on the complete thesis rather than the reviewer's specialty alone. When no verified institutional grading regime is available, the mandatory skill-default conclusion is one A/B/C/D grade paired with the exact Chinese recommendation below. A grade is a categorical action decision, not a numerical score.

## Authority and required output

Choose exactly one decision regime before reviewers start:

1. `institutional` — use the current institution or school review form when its categories, wording, and consequences are verified. Record the exact source and reproduce the official category and recommendation faithfully. Do not force an A/B/C/D translation unless the governing form itself defines that mapping.
2. `skill-default` — when no binding category scheme is available, use the A/B/C/D scheme below.

Every R-numbered report must state, before its findings:

- `Decision regime:` `institutional` or `skill-default`
- under `institutional`: `Official category`, `Official defense recommendation`, and `Governing source`
- under `skill-default`: `Academic grade: A / B / C / D` and the paired `Defense recommendation`
- `Confidence: high / medium / low`
- a one-paragraph rationale explaining why the whole thesis meets that category

The category, recommendation, severity profile, and required remedy must agree. A report with conflicting or hybrid regimes is incomplete and must be corrected before it is frozen. If the user requests an additional normalized A/B/C/D label alongside an institutional result, mark it explicitly as a non-official skill comparison and never substitute it for the official conclusion.

For a mechanically complete report, retain all six regime-specific category/source lines. Fill the three institutional lines with `N/A` under `skill-default`; fill `Academic grade` and `Defense recommendation` with `N/A` under `institutional`. Under an institutional regime, `Governing source` must be a duplicate-free semicolon-separated exact subset of the official URLs or local-rule official titles frozen in the process envelope. The chair's `Decision regime/source` projection is exactly `skill-default` for the default regime and exactly `institutional / <Governing source>` for an institutional regime.

## Default A/B/C/D scheme

| Grade | Required Chinese recommendation | Operational meaning | Normal evidence boundary |
|---|---|---|---|
| **A** | **同意答辩** | The thesis is defensible in its current scientific form. Only non-blocking local corrections may remain; no reviewer re-review is required before the defense. | No unresolved `S0`, `S1`, or `S2`. Only local, non-blocking `S3` and optional `S4` items may remain. |
| **B** | **小修后可答辩** | The thesis may proceed to defense after specified, checkable minor revisions. The revisions do not rebuild a core contribution and do not require a new independent review round under the default regime. | No unresolved `S0` or `S1`, and at least one actionable `S2`. All required changes are bounded writing, evidence recovery, citation, numerical, or formatting work that preserves the central scientific conclusion. |
| **C** | **大修后重新送审，复审通过后方可答辩** | The current thesis should not proceed to defense. Major revision, a corrected submission artifact, or genuinely new evidence is required, followed by independent re-review; the thesis still appears capable of becoming defensible. | At least one confirmed `S1`; or at least one unresolved mandatory `N` remedy; or a procedural `S0` such as a repairable blind-copy/anonymity failure that invalidates the submitted artifact without establishing substantive integrity misconduct. No integrity/foundational `S0` is present. |
| **D** | **不同意答辩** | The current submission fails the degree-thesis threshold or contains an integrity/foundational defect that cannot be treated as an ordinary major-revision case. | At least one substantiated integrity/foundational `S0`, such as fabricated evidence or citation, authorship/integrity misconduct, or a foundational thesis-level invalidity. |

These are action categories, not quality adjectives. Do not relabel them as “excellent/good/pass/fail” unless the governing institutional form explicitly uses those meanings.

## How findings determine a grade

- Under the skill-default regime, apply this ordered decision rule:

  1. integrity/foundational `S0 -> D`;
  2. otherwise procedural `S0`, any `S1`, or any unresolved mandatory `N` remedy `-> C`;
  3. otherwise any `S2 -> B`;
  4. otherwise `A` with only local `S3`/optional `S4` or no findings.

- `S4` never lowers a grade.
- Local `S3` corrections may coexist with A only when they do not affect interpretation, traceability, compliance, or defense readiness. A defect that materially affects any of those four properties is not local `S3`; record an evidence-backed finding at least as `S2` (or higher when warranted), so that it maps unambiguously to B, C, or D.
- In this rule, traceability means PDF-visible claim, protocol, result, and citation traceability. It does not mean forensic reconstruction of hidden code, commits, hashes, logs, manifests, private member lists, or exact replay artifacts. Their absence cannot create an `S2` or lower a grade unless they are verified formal submission components or are necessary to resolve an exact public-artifact claim made by the PDF.
- Any unresolved `S2` prevents A until it is closed, but does not by itself require C.
- Any confirmed `S1` or unresolved mandatory `N` remedy prevents A and B.
- Classify every `S0` as `integrity/foundational` or `procedural`. A repairable anonymity, identity-disclosure, wrong-artifact, or submission-form failure is procedural unless evidence supports substantive misconduct; it requires C and corrected re-review under the default scheme, not an automatic D. A substantiated integrity/foundational `S0` requires D.
- An unverified concern or a question is not a basis for lowering the grade.
- Do not lower a grade merely by counting findings. If several lower-severity defects jointly create a thesis-level `S1` or `S0`, record a separate evidence-backed aggregate finding at that severity, with the interaction and affected thesis claim explicitly explained.

Do not create pseudo-precision. No percentage, weighted mean, numeric conversion, or majority-vote formula is implied by A/B/C/D.

## Holistic grading requirement

Each reviewer assigns the conclusion after completing the common whole-thesis assessment defined in `reviewer-panels.md`. A role-specific deep dive may discover the decisive issue, but the conclusion must also consider scientific significance, technical correctness, evidence, thesis logic, integrity, writing, and rendered presentation. “Outside my specialty” may be recorded as a confidence limitation; it is not permission to omit a domain or grade only one aspect.

## Chair adjudication

The chair starts in the fresh Stage-C context defined by `clean-room-orchestration.md` and reports every frozen current-round reviewer category and recommendation individually. Under the skill-default regime it must not average letters or convert them to points.

After evidence reconciliation, the chair issues a separate overall category and defense recommendation under the same decision regime. Under the skill-default regime, the chair applies the highest-adjudicated-severity mapping above rather than the arithmetic mean, median, or majority label. If it differs from the majority or from a severe minority opinion, the chair must identify the evidence and severity decision that explains the difference.

The standalone AI-style assessor never receives an academic/defense category and never changes that conclusion by itself.

## Re-review

A fresh independent re-review report must issue a category and recommendation under the new round's decision regime from the newly frozen PDF alone. Before its report and grade are frozen, the reviewer must not see the prior ledger, author response, old grade, old reports, or earlier summary. Do not mechanically carry forward the old conclusion.

Only after the fresh reviewer reports, clean chair decision, and clean current-round summary are frozen may a separately labeled post-freeze issue-closure verification compare the new PDF with a specifically identified prior ledger. That comparison classifies each prior item as `resolved`, `unresolved`, `not verifiable`, `rejected`, or `superseded by current finding`; it cannot retroactively change the fresh reports, grades, chair decision, or clean summary. When discussing longitudinal closure outside the independent round, a prior C can be considered cleared only when no decisive `S1` remains unresolved or not verifiable, and a prior D basis only after every `S0` has been explicitly re-adjudicated.
