# Review bundle template

Store a review round in a dedicated directory:

```text
thesis-review-round-YYYYMMDD/
  00-process-parameters.json
  00-manifest.md
  00-page-inventory.csv
  00-bibliography-inventory.csv
  00-citation-candidate-ledger.csv
  00-unmatched-bracket-ledger.csv
  00-citation-inventory.csv
  helpers/                         # optional; include only helpers actually consumed
    H01-provenance.json
    H01-<mechanical-sidecar>.*
  01-policy-basis.md
  02-page-layout-ledger.md
  02-page-layout-ledger.csv
  page-renders/                   # mandatory PNG, one exact hashed render per PageID
    P0001.png
    ...
  03-bibliography-audit-ledger.md
  03-bibliography-audit-ledger.csv
  04-citation-claim-audit-ledger.md
  04-citation-claim-audit-ledger.csv
  05-ai-style-assessment.md
  R1-comprehensive-review.md
  R2-comprehensive-review.md
  R3-comprehensive-review.md
  R4-comprehensive-review.md      # doctorate only
  R5-comprehensive-review.md      # doctorate only
  90-chair-synthesis.md
  91-revision-ledger.md
  91-revision-ledger.csv
  91-ai-actionable-ledger.csv
  92-new-evidence-or-experiments.md
  93-user-facing-summary.md
  93-current-actionable-items.csv
  93-current-ai-actionable-items.csv
  94-post-freeze-prior-issue-closure.md  # optional, only after a fresh re-review round is frozen
  95-bundle-validation.md               # mechanical Stage-O validation, never reviewer input
```

For a master's thesis, all three are comprehensive reviewers: R1 has a technical/experimental emphasis, R2 a contribution/thesis-logic emphasis, and R3 an evidence/standards emphasis.

Use the neutral `comprehensive-review` filenames for new rounds so the file path does not imply an exclusive scope. Put the persona emphasis inside each report. Existing frozen rounds may retain their historical filenames; do not rename or rewrite them retroactively.

Both citation ledgers are mandatory. For a doctorate, R5 owns `03-bibliography-audit-ledger.md` and R4 owns `04-citation-claim-audit-ledger.md`; for a master's thesis, R3 owns both. Follow `citation-audit.md`. The two doctoral owners freeze their ledgers independently before the chair reconciles them.

`05-ai-style-assessment.md` is mandatory for both degree levels but is not an R-numbered reviewer report. Its assessor freezes independently from the reviewer panel and follows `ai-style-audit.md`.

Every new bundle follows `clean-room-orchestration.md`. `00`--`05`, every R report, `90`--`93`, and optional `94` are stage-owned artifacts; a conversation-aware orchestrator may not draft their substantive content. CSV files are the machine-readable master row sets and Markdown files are signed human-readable summaries/views. Preserve deterministic IDs, quote multiline CSV fields, and never let a Markdown row exist without the matching CSV row. `95` records mechanical completeness only and cannot cure semantic defects.

## Neutral process parameters

Stage O writes only the closed administrative envelope below. Unknown values remain `null`; do not add free-form notes or thesis assertions.

```json
{
  "round_id": "...",
  "retry_id": "...",
  "frozen_pdf_file": "frozen-thesis.pdf",
  "selected_pdf_sha256": "...",
  "physical_page_count": 1,
  "frozen_at": "2026-08-29T12:34:56+08:00",
  "degree_level": "doctorate|masters|null",
  "degree_type": "academic|professional|null",
  "institution": null,
  "school_or_department": null,
  "discipline": null,
  "expected_submission_year": null,
  "artifact_type": "author-copy|blind-copy|unknown",
  "review_mode": "initial|fresh-rereview",
  "output_language": "zh-CN",
  "governing_rule_urls": [],
  "governing_local_files": [{"neutral_file": "rule-01.pdf", "official_title": "...", "sha256": "..."}],
  "decision_regime_status": "verified-institutional|skill-default|undetermined"
}
```

## Manifest

```markdown
# Frozen evidence manifest

- Process-parameter file and SHA-256:
- Packet-builder fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Packet-builder input-receipt/access declaration: prompt SHA-256; received messages/resources/preloads; exact local artifacts and public endpoints opened; confirmation that no unlisted substantive assertion was received, no prohibited context/artifact was used, and neighboring paths were not enumerated
- Operational prompt SHA-256: `<exactly one 64-hex hash>`
- Frozen PDF SHA-256 at start and end: `<start 64-hex hash> / <end 64-hex hash>` (both hashes must be on this one line)
- Frozen at: `<exact process-envelope frozen_at value>`
- Degree/institution/discipline:
- Review round and purpose:
- Frozen PDF path, SHA-256, `frozen_at` timestamp copied exactly from the process envelope, and pages:
- Governing template/rules:
- Reviewer-visible artifact: exactly one frozen thesis PDF
- Permitted public citation-verification sources:
- Prohibited context and artifacts: conversation/memory summaries, user explanations, earlier assistant outputs, other actors' messages, thesis source, `.bib`, build/auxiliary files, Git history, sibling repositories, local papers, code/config/logs, old rounds, source/provenance audits, and author-side records
- Items explicitly out of scope:

## Thesis structure
...

## Thesis-stated questions and contributions — neutral navigation only
Record only statements explicitly visible in the PDF, with exact page anchors. Do not adjudicate them or create a consensus map.

## Objective inventories and locations
Chapters/sections, figures, tables, equations, algorithms, appendices, bibliography entries, the complete numeric-bracket candidate ledger, citation occurrences, unmatched-bracket glyph count/dispositions, and PDF-derived corpus locations.

- Numeric-bracket candidate rows: `<integer>`
- Citation-classified candidate rows: `<integer>`
- Non-citation-classified candidate rows: `<integer>`
- Unmatched square-bracket glyphs: `<integer>`
- Unmatched glyph dispositions: `<concrete physical-page/context audit result; state none found when the validated count is zero>`
```

When the unmatched count is positive, `00-unmatched-bracket-ledger.csv` is the row-level master with schema `GlyphID,PhysicalPage,Glyph,AdjacentPDFText,Disposition,PDFSHA256`; the manifest disposition names that file and its exact row count. When the count is zero, retain the header-only CSV and state explicitly that none were found.

`01-policy-basis.md` begins with the packet builder's same complete declaration block before recording only the verified governing regime and sources.

Each owner-written Markdown ledger (`02`, `03`, and `04`) begins with the same complete declaration block: fresh-context declaration using the exact no-inherited-turn wording above; input-receipt/access declaration naming received and opened inputs, no unlisted substantive assertion, no prohibited context/artifact, and no neighboring-path enumeration; exact operational-prompt hash; and start/end frozen-PDF hashes on one line. These declarations belong to the ledger itself, not only to the owner's R report.

## Independent reviewer report

```markdown
# Rn — Comprehensive whole-thesis review — persona emphasis

## Role, scope, and independence
- Whole-thesis mandate: Gate A--I
- Persona emphasis:
- Separate exhaustive audit duties, if any:
- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Independence declaration:
- Operational prompt SHA-256: `<exactly one 64-hex hash>`
- Input-receipt/access declaration: received messages/resources/preloads; every local artifact and public endpoint opened; confirmation that no unlisted substantive assertion was received, no prohibited context/artifact was used, and neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: `<start 64-hex hash> / <end 64-hex hash>` (both hashes must be on this one line)

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
- Machine-readable master: `02-page-layout-ledger.csv`; duplicate/missing/extra page IDs:
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
- Venue fields verified / mismatched / unverifiable:
- Publication/acceptance-status fields verified / mismatched / unverifiable:
- Volume/issue fields verified / mismatched / legitimate N/A / unverifiable:
- Page-range or article-number fields verified / mismatched / legitimate N/A / unverifiable:
- DOI/arXiv/version/URL/access-date fields verified / mismatched / legitimate N/A / unverifiable:
- ISBN/other-persistent-ID fields verified / mismatched / legitimate N/A / unverifiable:
- Retraction/withdrawal/correction/superseding-status fields verified / mismatched / legitimate N/A / unverifiable:
- Suspected fabricated/nonexistent entries and adjudication status:
- Metadata/status verified entries:
- Machine-readable master: `03-bibliography-audit-ledger.csv`; duplicate/missing/extra reference IDs:
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
- Machine-readable master: `04-citation-claim-audit-ledger.csv`; duplicate/missing/extra Pair IDs:
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
- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Independence declaration:
- Operational prompt SHA-256: `<exactly one 64-hex hash>`
- Input-receipt/access declaration: received messages/resources/preloads; opened artifacts/endpoints; no unlisted substantive assertion received; no prohibited context/artifact used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: `<start 64-hex hash> / <end 64-hex hash>` (both hashes must be on this one line)
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

## Out-of-scope observations for chair verification
PDF-visible non-style observations only, without AI finding IDs or severity; `none` is valid. Do not message reviewers.
```

Do not add an academic/defense category, R1--R5 severity, AI probability, or misconduct finding to this report.

## Chair synthesis

```markdown
# Chair synthesis

## Clean-room boundary
- Chair fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Exact current-round input allowlist:
- Operational prompt SHA-256: `<exactly one 64-hex hash>`
- Chair input-receipt/access declaration: received messages/resources/preloads; opened artifacts/endpoints; confirm no unlisted substantive assertion, no prohibited context/artifact, and no neighboring-path enumeration
- Frozen PDF SHA-256 at start and end: `<start 64-hex hash> / <end 64-hex hash>` (both hashes must be on this one line)

## Overall risk and recommendation
- Decision regime: institutional / skill-default
- Overall official category, recommendation, and governing source: required under `institutional`; otherwise N/A
- Overall academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Overall defense recommendation: exact Chinese action conclusion
- Confidence:
- Whole-thesis rationale:

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

## AI-style actionable findings
| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Verification | Status |
|---|---|---|---|---|---|---|

These rows populate `91-ai-actionable-ledger.csv` and never receive academic severity/remedy classes or change the defense grade.

## Contributions that survived review
...

## Adjudicated findings
| Chair finding ID | Source reviewer finding IDs | Severity | Remedy | Exact PDF anchor | Direct observation | Evidence status | Owner | Minimum required action | Verification |
|---|---|---|---|---|---|---|---|---|---|

## Mandatory citation cross-ledger consistency gate
| Rendered reference ID | R4 identity/source | R5 canonical identity | Version/record agreement | Affected Pair IDs | Conflict class (`none` / `local` / `substantive`) | Reclassification/finding | Resolution |
|---|---|---|---|---|---|---|---|

- Unique cited rendered references joined:
- Identity-agreement count:
- Version disagreements:
- Local conflicts:
- Substantive conflicts:
- Reclassified Pair IDs:
- Unresolved conflicts:
- Combined citation gate: pass / fail

## Disagreements and chair decisions
| Topic | Positions | Evidence checked | Decision or unresolved status |
|---|---|---|---|

## Thesis-level narrative and chapter logic
...

## Policy and blind-copy status
...

## Optional suggestions
Only current-round adjudicated S4 suggestions, or `none`.

## Review limitations
...
```

## Revision ledger

Prioritize by risk, not by chapter order.

`91-revision-ledger.md` begins with the chair's complete fresh-context, input-receipt/access, prompt-hash, and start/end PDF-hash declaration block before the tables.

```markdown
| Ledger ID | Priority | Chair finding ID | Source reviewer finding IDs | Severity | Remedy | Exact PDF anchor | Direct observation | Minimum edit/evidence | Dependency | Owner | Status | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L01 | P0 | C-F01 | Rn-Fxx | S0/S1 | W/E/N/P | ... | ... | ... | ... | ... | open | ... |
| L02 | P1 | C-F02 | Rn-Fxx | S2 | W/E/N/P | ... | ... | ... | ... | ... | open | ... |
| L03 | P2 | C-F03 | Rn-Fxx | S3 | W/E/N/P | ... | ... | ... | ... | ... | open | ... |
```

Every open required `S0`--`S3` chair finding appears exactly once. Optional `S4` suggestions and non-finding questions do not enter this required ledger; put them in separately labeled sections of the chair report.

In the same `91-revision-ledger.md`, add the following separate table, mirrored exactly by `91-ai-actionable-ledger.csv`:

```markdown
## AI-style actionable ledger — separate from academic grading
| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Status | Verification |
|---|---|---|---|---|---|---|
```

Every unresolved current-round `AI-Fxx` with `material` or `local` impact appears exactly once. Do not assign academic severity, remedy class, priority, or defense consequence. Optional AI findings remain outside this actionable table.

## New evidence or experiments

Always split the list:

`92-new-evidence-or-experiments.md` begins with the chair's complete fresh-context, input-receipt/access, prompt-hash, and start/end PDF-hash declaration block before these sections.

```markdown
## No-new-experiment remedies (W/E/P)
- Existing evidence the author may recover in a separate revision task; reviewers do not inspect it:
- Writing or claim narrowing:
- Policy confirmation:

## Genuine new experiments or unavailable evidence (N)
| Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |
|---|---|---|---|---|
```

An empty `N` table is a valid and often preferable result.

## Clean user-facing summary

Run this as Stage S in a new context after `90`--`92` are frozen. The summarizer does not browse the web, consult conversation history, or re-adjudicate evidence.

```markdown
# Current-round user-facing review summary

## Clean-room identity
- Review round ID:
- Frozen PDF path and SHA-256:
- Summary fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Exact current-round input allowlist: `00-process-parameters.json; SKILL.md; clean-room-orchestration.md; report-template.md; R1-comprehensive-review.md; ...; Rn-comprehensive-review.md; 05-ai-style-assessment.md; 90-chair-synthesis.md; 91-revision-ledger.md; 91-revision-ledger.csv; 91-ai-actionable-ledger.csv; 92-new-evidence-or-experiments.md` (write the expanded exact semicolon-separated basename set, with no ellipsis or extra file)
- Operational prompt SHA-256: `<exactly one 64-hex hash>`
- Summary input-receipt/access declaration: received messages/resources/preloads; opened artifacts/endpoints; no unlisted substantive assertion received; no prohibited context/artifact used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: `<start 64-hex hash> / <end 64-hex hash>` (both hashes must be on this one line)

## Independent and overall conclusions
| Actor | Persona/status | Category or AI-style label | Exact defense recommendation | Confidence | Decisive current-round basis |
|---|---|---|---|---|---|

Keep the AI-style row visibly separate from R1--R5/R1--R3 and the chair; it has no defense category.

## Current actionable items
| Ledger ID | Current finding ID(s) | Severity / remedy | Exact PDF anchor | Direct PDF-visible observation | Minimum required action | Origin reviewer(s) | Chair disposition |
|---|---|---|---|---|---|---|---|

## Current AI-style actionable items — separate from academic grading
| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Chair status |
|---|---|---|---|---|---|

## Optional suggestions
Copy the current chair's `Optional suggestions` section exactly after whitespace normalization; do not summarize or add an item. Use `none` only when the chair section is `none`.

## Unresolved questions and review limitations
Copy the current chair's `Review limitations` section exactly after whitespace normalization; do not summarize or add an item. Use `none` only when the chair section is `none`.

## Reconciliation
- Open required rows in 91-revision-ledger.md:
- Rows in Current actionable items:
- Missing ledger IDs: none / list and mark summary invalid
- Extra summary IDs: none / list and mark summary invalid
- Duplicate IDs: none / list and mark summary invalid
- Open AI rows in 91-ai-actionable-ledger.csv:
- Rows in Current AI-style actionable items:
- Missing/extra/duplicate AI finding IDs: none / list and mark summary invalid
- Statement: This summary introduces no new finding and uses no prior-round or author-side information.
```

The academic required row sets and the AI-actionable row sets must each be identical to their respective `91` sidecars. Every academic row traces to a current-round chair finding, current reviewer finding ID(s), and exact PDF anchor; every AI row traces to a current `AI-Fxx` and exact PDF anchor. Do not mention old/resolved items, user explanations, previous assistant summaries, companion papers/repositories, source-sync facts, or implementation claims invisible in the PDF. If reconciliation fails, do not improvise; return the inconsistency to the clean chair or regenerate Stage S.

For deterministic reconciliation, the CSV projections are exact field mappings, not paraphrases. For each open academic row, `93.CurrentFindingIDs = 91.ChairFindingID`, `93.SeverityRemedy = 91.Severity + "/" + 91.Remedy`, `93.ExactPDFAnchor = 91.ExactPDFAnchor`, `93.DirectPDFObservation = 91.DirectObservation`, `93.MinimumRequiredAction = 91.MinimumEditEvidence`, `93.OriginReviewers = 91.SourceReviewerFindingIDs`, and `93.ChairDisposition = 91.Status`. For each open material/local AI row, `AIFindingID`, `Impact`, `ExactPDFAnchor`, `DirectStyleObservation`, and `MinimumEditingAction` are byte-for-byte equal after CSV parsing and trimming, and `93.ChairStatus = 91.Status`.

## Fresh re-review and optional prior-issue closure

```markdown
## Fresh category and defense recommendation — freeze before any prior ledger is opened
- Decision regime: institutional / skill-default
- Official category, recommendation, and governing source: required under `institutional`; otherwise N/A
- Academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Defense recommendation: exact Chinese action conclusion
- Confidence:
- Rationale for the newly frozen artifact:

## Fresh Gate A--I whole-thesis assessment
Repeat the complete nine-row matrix from the independent-review template. This report contains no prior-finding table and is frozen before any prior ledger is opened.

## New findings
...

## Final recommendation
...
```

Only after all fresh R reports, the clean chair outputs, and `93-user-facing-summary.md` are frozen may a separate Stage-V actor write `94-post-freeze-prior-issue-closure.md`:

```markdown
# Post-freeze prior-issue closure verification
- Current frozen PDF and round:
- Current fresh reports/chair/summary already frozen:
- Specifically allowlisted prior ledger/author response:
- Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested: not run / ...
- Full regression baseline: not run / prior frozen PDF hash plus prior inventory/page/bibliography/citation ledger identities and hashes
- Fresh-context and input-receipt/access declarations:
- Frozen current PDF SHA-256 at start and end:

| Prior finding | Status | Evidence in revised PDF | Regression check | Current-round related finding, if any |
|---|---|---|---|---|

## Longitudinal AI-style comparison — non-review
- Status: not run / run
- Prior AI report identity/hash:
- Current AI report identity/hash:
- Prior open material/local AI-F IDs:
- Current corresponding evidence/status:
- New current AI-F IDs:
- Limitations:
- Separation statement: this comparison does not alter the current chair decision, grade, current AI report, 91 ledgers, or 93 summary.

## Full longitudinal regression audit — non-review
- Status: not run / run with complete prior baseline
- Prior/current PDF identities and hashes:
- Prior/current page, bibliography, citation inventory/ledger identities and hashes:
- Demonstrated regressions on comparable objects:
- Current fresh findings whose introduction time is not verifiable:
- Limitations:
```

This optional longitudinal artifact cannot edit or reinterpret the current independent reports, grades, chair decision, revision ledger, or clean user-facing summary.

An author response is only a locator and record of the author's claim. Mark `resolved` only when the current frozen PDF visibly supplies the closure evidence; an author statement alone cannot close an item. Without the full prior baseline named above, Stage V performs prior-finding closure only and must state `global regression not assessed`; it may not infer that a current fresh finding was introduced by revision merely because an old issue ledger omitted it.

When Stage V is run for an iterative review--revision loop, `94-post-freeze-prior-issue-closure.md` or a separate Stage-O process-completion record must additionally state the following. Never append these fields to or edit any frozen R, C, or S artifact:

- whether every physical page was re-entered in the page ledger after the last edit;
- whether every physical page and all affected neighboring pages were rechecked in the final PDF;
- whether every bibliography entry was re-entered in the bibliography ledger, all citation--source pairs were re-entered in the citation-claim ledger, and every changed or repeated source use was reverified;
- whether every reviewer returned an empty actionable `S0`--`S3` Findings section;
- whether a fresh isolated `05-ai-style-assessment.md` was run on the final frozen artifact, its signal level, and whether any material prose-polish finding remains;
- whether any `S4` suggestion or review limitation remains.
