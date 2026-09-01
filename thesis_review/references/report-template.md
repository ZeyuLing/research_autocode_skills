# Review bundle template

Store the finalized, Stage-O-promoted review round in a dedicated directory:

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
  06-semantic-acceptance/         # mandatory fresh semantic acceptors; never Chair inputs
    SA-R1.md
    SA-R1.csv
    ...
    SA-R5.md                      # doctorate only
    SA-R5.csv                     # doctorate only
    SA-AI.md
    SA-AI.csv
  06-semantic-acceptance-gate.json # deterministic hash-only PASS gate visible to Chair
  90-chair-synthesis.md
  91-revision-ledger.md
  91-revision-ledger.csv
  91-ai-actionable-ledger.csv
  92-new-evidence-or-experiments.md
  92-new-evidence-or-experiments.csv
  93-user-facing-summary.md
  93-current-actionable-items.csv
  93-current-ai-actionable-items.csv
  stage-v-inputs/                       # optional; exact copied inputs when Stage V runs
    round-previous-prior-issues.csv     # required Stage-V prior-ID master
  94-post-freeze-prior-issue-closure.md  # optional, only after a fresh re-review round is frozen
  95-bundle-validation.md               # mechanical Stage-O validation, never reviewer input
```

For a master's thesis, all three are comprehensive reviewers: R1 has a technical/experimental emphasis, R2 a contribution/thesis-logic emphasis, and R3 an evidence/standards emphasis.

Use the neutral `comprehensive-review` filenames for new rounds so the file path does not imply an exclusive scope. Put the persona emphasis inside each report. Existing frozen rounds may retain their historical filenames; do not rename or rewrite them retroactively.

Both citation ledgers are mandatory. For a doctorate, R5 owns `03-bibliography-audit-ledger.md` and R4 owns `04-citation-claim-audit-ledger.md`; for a master's thesis, R3 owns both. Follow `citation-audit.md`. The two doctoral owners freeze their ledgers independently before the chair reconciles them.

`05-ai-style-assessment.md` is mandatory for both degree levels but is not an R-numbered reviewer report. Its assessor freezes independently from the reviewer panel and follows `ai-style-audit.md`.

Every new bundle follows `clean-room-orchestration.md`. `00`--`06`, every R report, `90`--`93`, and optional `94` are stage-owned artifacts; a conversation-aware orchestrator may not draft their substantive content. CSV files are the machine-readable master row sets and Markdown files are signed human-readable summaries/views. Preserve deterministic IDs, quote multiline CSV fields, and never let a Markdown row exist without the matching CSV row. `95` records mechanical completeness only and cannot cure semantic defects.

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
  "decision_regime_status": "verified-institutional|skill-default|undetermined",
  "actor_prompt_sha256": {"P": "...", "R1": "...", "R2": "...", "R3": "...", "R4": "...", "R5": "...", "AI": "...", "SA-R1": "...", "SA-R2": "...", "SA-R3": "...", "SA-R4": "...", "SA-R5": "...", "SA-AI": "...", "C": "...", "S": "..."}
}
```

`actor_prompt_sha256` is a closed mechanical launch plan. It contains `P`, every degree-appropriate `R` actor (`R1`--`R5` for a doctorate or `R1`--`R3` for a master's thesis), `AI`, one matching fresh semantic acceptor for every such actor (`SA-R1`--`SA-R5` or `SA-R1`--`SA-R3`, plus `SA-AI`), `C`, and `S`, with one distinct 64-hex prompt hash per actor; `V` is present if and only if optional `94-post-freeze-prior-issue-closure.md` is actually launched. The doctorate-shaped JSON above is illustrative; omit `R4`, `R5`, `SA-R4`, and `SA-R5` for a master's thesis. The hash is computed from the exact operational-prompt bytes before the fresh actor starts, and Stage O dispatches those same bytes. It does not contain thesis assertions. Every `governing_local_files.neutral_file` basename is unique under Unicode-NFC, case-insensitive, Win32-portable comparison; trailing dots/spaces and filesystem aliases are invalid. Governing-file and frozen-PDF basenames are mutually distinct and do not reuse any skill-reference, generated-artifact (including `P####.png`), or closed-root-directory basename.

The process envelope is strict JSON: duplicate keys are forbidden at every
nesting level. Full validation and every scoped mode, including the Chair's
`--pre-stage-s` path, use the same fail-closed duplicate-key rule as Stage SA;
ordinary JSON last-key-wins behavior is never an authorization rule.

## Manifest

```markdown
# Frozen evidence manifest

- Process-parameter file and SHA-256: 00-process-parameters.json / <exact 64-hex file hash>
- Actor ID: P
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Packet-builder fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Packet-builder input-receipt/access declaration: received=[operational prompt]; opened=[the exact canonical ordered P allowlist]; public_endpoints=[a duplicate-free subset of current process-rule URLs, or none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Operational prompt SHA-256: <exactly one 64-hex hash>
- Frozen PDF SHA-256 at start and end: <start 64-hex hash> / <end 64-hex hash> (both hashes must be on this one line)
- Frozen at: <exact process-envelope frozen_at value>
- PDF extraction runtime: pypdf=<exact `pypdf.__version__` used to generate every PDF-derived Stage-P field>
- Degree/institution/discipline: degree_level=<value> ; degree_type=<value> ; institution=<value-or-null> ; school_or_department=<value-or-null> ; discipline=<value-or-null> ; expected_submission_year=<value-or-null>
- Review round and purpose: round_id=<value> ; retry_id=<value> ; review_mode=<value> ; artifact_type=<value> ; output_language=<value>
- Frozen PDF path, SHA-256, frozen_at timestamp, and pages: file=<frozen_pdf_file> ; sha256=<selected_pdf_sha256> ; frozen_at=<frozen_at> ; pages=<physical_page_count>
- Governing template/rules: template=thesis-review/SKILL.md ; decision_regime_status=<value> ; sources=<sorted official URL/title values joined by " | ", or none>
- Reviewer-visible artifact: exactly one frozen thesis PDF: <frozen_pdf_file>
- Permitted public citation-verification sources: authoritative publisher, DOI, proceedings, and official full-text `http(s)` endpoints only
- Prohibited context and artifacts: conversation/memory summaries, user explanations, earlier assistant outputs, other actors' messages, thesis source, `.bib`, build/auxiliary files, Git history, sibling repositories, local papers, code/config/logs, old rounds, source/provenance audits, and author-side records
- Items explicitly out of scope: <concrete non-shell boundary>

## Thesis structure
Record a neutral structural map with physical-page anchors. Do not evaluate it.

## Thesis-stated questions and contributions — neutral navigation only
Record only statements explicitly visible in the PDF, with exact page anchors. Do not adjudicate them or create a consensus map.

## Objective inventories and locations
Name at least `00-page-inventory.csv`, `00-bibliography-inventory.csv`, `00-citation-candidate-ledger.csv`, `00-citation-inventory.csv`, and `00-unmatched-bracket-ledger.csv`, plus the locations of chapters/sections, figures, tables, equations, algorithms, appendices, bibliography entries, citation occurrences, and any PDF-derived corpus. In `00-page-inventory.csv`, `Region` is bound to the rendered PDF rather than copied from manifest prose: one-line or cross-line page-top chapter-title boundaries, the unique bibliography run, and independent appendix/back headings control the class for every physical page. Class-prefix descriptions such as `chapter — methods` and `body — results` are permitted, while any explicit chapter number must match the rendered chapter number. `separator`/`boundary` is permitted only for a substantively empty rendered page after repeated page furniture and a standalone page number are removed. TOC/list entries and sentence-like prose cross-references never establish a boundary. The Stage-P scoped gate and full-bundle gate call the same shared Region implementation.

- Sections: <exact semicolon-separated rendered body-section map `N.N[.N...]=physical p.N` in PDF order, or `none detected`>
- Authored-prose navigation pages: physical p.<N>[-<M>]; physical p.<N>[-<M>]
- Numeric-bracket candidate rows: <integer>
- Citation-classified candidate rows: <integer>
- Non-citation-classified candidate rows: <integer>
- Unmatched square-bracket glyphs: <integer>
- Unmatched glyph dispositions: <concrete physical-page/context audit result; state none found when the validated count is zero>
```

The manifest uses exactly this H1 followed by these three H2 sections in this order. The eighteen identity bullets occur once, in the shown order, before the first H2. Its process fields are deterministic projections, not prose paraphrases. `Sections` is the validator-reconstructed exact map of numbered headings rendered in body chapter regions: the leading component must equal the active PDF-derived chapter, the remainder of the line must be a textual heading, and labels/order/physical pages must match exactly. Contents/list entries, table or metric decimals, equations, bibliography entries, and appendix labels are not body sections. `Authored-prose navigation pages` is one canonical ascending, compact, duplicate-free, semicolon-separated physical-page set. It includes every substantive rendered preface/序言/前言, both abstracts, authored chapter prose, substantive appendix prose, and substantive explanatory/contribution prose anywhere in front/back matter. Exclusions are span-level: declarations, contents/list entries, bibliography entries, and CV metadata spans may be excluded, but their presence never excludes other authored prose on the same physical page. This corpus guides the AI-style reading but never narrows the mandatory inspection of every physical page. The process-parameter hash is the hash of the final closed JSON bytes; if the JSON changes, regenerate the manifest before any actor starts. `PDF extraction runtime` is mechanically compared with the validator's current `pypdf.__version__`; changing extraction runtimes inside one round invalidates every scoped/full gate rather than silently changing text slices. Apart from specifically hash-bound governing-rule PDFs declared in the process envelope, the round root contains exactly one PDF: the process-selected frozen thesis.

When the unmatched count is positive, `00-unmatched-bracket-ledger.csv` is the row-level master with schema `GlyphID,PhysicalPage,Glyph,AdjacentPDFText,Disposition,PDFSHA256`; the manifest disposition names that file and its exact row count. For a square endpoint in a deterministically recognizable half-open interval `[a,b)` or `(a,b]`, write the exact closed disposition `visible-role:half-open-mathematical-interval`, not a free-form paraphrase. When the count is zero, retain the header-only CSV and state explicitly that none were found.

`01-policy-basis.md` begins with the packet builder's same complete declaration block before recording only the verified governing regime and sources.

For Stage P, the canonical `opened=[...]` sequence is exactly: `00-process-parameters.json`; `SKILL.md`; `clean-room-orchestration.md`; `china-policy.md`; `grading-and-verdicts.md`; `review-rubric.md`; `reviewer-panels.md`; `report-template.md`; `ledger-validation.md`; `rendered-pagination-audit.md`; `citation-audit.md`; `ai-style-audit.md`; `rules/scripts/validate_review_bundle.py`; `rules/scripts/validate_stage_p_output.py`; process-ordered governing local files; and `<frozen_pdf_file>`. Stage P has no helper inputs. This exact sequence appears byte-for-byte in both `00-manifest.md` and `01-policy-basis.md`. `rules/` is a staged read-only skill-rule mount, not a round-root artifact; the two scripts and validator output are mechanical rule inputs, never thesis/citation evidence or a source of findings.

Each owner-written Markdown ledger (`02`, `03`, and `04`) begins with the same complete declaration block: exact `Actor ID`, `Review round ID`, and `Review retry ID`; fresh-context declaration using the exact no-inherited-turn wording above; one input-receipt/access declaration with `received=[operational prompt]`, the actor's exact canonical ordered `opened=[...]` allowlist, the allowed `public_endpoints=[...]`, and the three boundary confirmations; the process-bound operational-prompt hash; and start/end frozen-PDF hashes on one line. These declarations belong to the ledger itself, not only to the owner's R report.

For every R actor, immediately after `ai-style-audit.md`, insert exactly one role-specific validator sequence before process-ordered governing local files, `<frozen_pdf_file>`, the seven Stage-P packet artifacts, and any recipient helper provenance/outputs:

- ordinary doctoral/master's reviewer: `rules/scripts/validate_review_bundle.py; rules/scripts/validate_reviewer_output.py`;
- doctoral R4: `rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_r5_output.py; rules/scripts/validate_r4_output.py`;
- doctoral R5: `rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_r5_output.py`;
- master's R3: `rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_r5_output.py; rules/scripts/validate_master_r3_output.py`;
- Chair C: `rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_semantic_acceptance_output.py; rules/scripts/validate_chair_output.py`;
- Stage S: `rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_summary_output.py`.

`materialize_owner_outputs.py` is the deterministic pre-freeze writer for the current actor's owned projections and receipt lists; it must run inside that same fresh actor turn and never after freeze. Reviewer/Chair semantic CSV values and Chair adjudication remain actor-authored; Stage S's two CSVs are wholly derived open-row subsets and therefore are materializer outputs. `validate_r5_output.py` in an R4/master's-R3 insertion supplies shared read-only Stage-P packet reconciliation; it does not grant access to an R5 report or R5-owned artifact. The same complete script sequence appears byte-for-byte in every Markdown artifact signed by that actor. `rules/` is a read-only staged skill-rule mount rather than a round-root artifact. Scripts and stdout are mechanical rule inputs, never thesis/citation evidence. Before freeze, complete the semantic sources, run the exact materializer command to `MATERIALIZED`, inspect the result, and then run the exact role gate in `ledger-validation.md` to `PASS`; rematerialize after every source edit. Do not rename any H2, label, field, or table header in a closed template, and do not hand-edit a deterministic projection or receipt after materialization.

## Independent reviewer report

Copy `Persona assignment` exactly from this closed degree-specific mapping; do not translate, paraphrase, add punctuation, or combine roles:

- doctorate R1: `R1 technical/methods/experiments`
- doctorate R2: `R2 contribution/novelty/positioning`
- doctorate R3: `R3 thesis architecture/narrative`
- doctorate R4: `R4 evidence/reproducibility/integrity/citation`
- doctorate R5: `R5 format/bibliography/layout`
- master's R1: `R1 technical/methods/experiments`
- master's R2: `R2 contribution/positioning + thesis architecture/narrative`
- master's R3: `R3 evidence/integrity/citation + format/bibliography/layout`

```markdown
# Rn — Comprehensive whole-thesis review — persona emphasis

## Role, scope, and independence
- Actor ID: Rn
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Whole-thesis mandate: Gate A--I
- Persona assignment: exact degree-specific value from `reviewer-panels.md` and the mapping immediately above
- Persona emphasis:
- Separate exhaustive audit duties, if any:
- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Independence declaration:
- Operational prompt SHA-256: <exactly one 64-hex hash>
- Input-receipt/access declaration: received=[operational prompt]; opened=[the exact canonical ordered Rn allowlist]; public_endpoints=[a duplicate-free subset of endpoints allowed for this actor, or none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: <start 64-hex hash> / <end 64-hex hash> (both hashes must be on this one line)

## Verdict
- Decision regime: institutional / skill-default
- Official category: required under `institutional`; otherwise N/A
- Official defense recommendation: required under `institutional`; otherwise N/A
- Governing source: required under `institutional`; otherwise N/A
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

Gate dispositions and actionable findings are a bidirectional contract. Every
`S0`--`S3` finding's Primary gate and every declared Secondary gate must be
`concern` and must cite that finding ID. Conversely, every `concern` row must
cite at least one current `S0`--`S3` finding that maps back to that Gate, and it
must not cite an actionable finding whose gate assignment excludes the row.
Every non-`concern` row (`adequate`, `unverifiable`, or `N/A`) cites no
actionable `S0`--`S3` finding. `S4` remains optional, may be referenced only as
informational context, and does not by itself force a Gate to `concern`.

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
- Location: `physical p.<n>` within `1..physical_page_count`, optionally followed by logical page and section/table/figure/equation detail
- Observation: directly visible fact
- Why it matters: affected rule, claim, or reader task
- Evidence: visible PDF excerpt/data or a permitted public source used to verify a citation, without excessive quotation
- Required action: minimum sufficient remedy
- Verification: how to confirm closure
- Confidence: high/medium/low

## Questions, not findings
| Question ID | Exact PDF anchor | Question | Why unresolved | Needed clarification/evidence |
|---|---|---|---|---|

## Coverage and limitations
...
```

Every Gate A--I row, every finding block, and every nonempty question row contains at least one physical-page anchor within `1..physical_page_count`; new artifacts emit that anchor as `physical p.<n>`. A logical page, section, table, figure, or equation locator may follow but never replaces the physical anchor. Finding headings use continuous `Rn-F01...` IDs in report order, with no gap or duplicate. Nonempty question rows use continuous `Rn-Q01...` IDs in report order; the header-only canonical question table is the explicit no-question result.

When an anchor additionally names an explicit thesis section using `Section
2.2.3`, `Sec. 2.2.3`, `§2.2.3`, or `第2.2.3节`, that section must exist in the
PDF-derived Stage-P section map and the physical page must fall within its
rendered interval. The interval starts at the heading page and ends immediately
before the next heading of equal or shallower depth (or at the rendered body
boundary for the final section). Bare decimals and `Table`/`Figure`/`Equation`
numbers, DOI components, metric values, and model versions are not section
anchors. A page-only anchor remains valid; this check applies only when the
report chooses to state an explicit section.

`Required action` and `Needed clarification/evidence` are constrained by the thesis submission obligation. They may request a PDF-visible edit, genuinely necessary new evidence whose result will be reported in the revised thesis, or a verified formal submission attachment. They must not request hidden code/commit identifiers, environment locks, full command files, checkpoint/model-file hashes, sample/member hashes, immutable manifests, controlled audit packages, internal logs, table scripts, or confidential raw data merely because such materials are absent. That absence is not preserved as a reviewer question. If a verified governing rule or an exact public-artifact claim creates an exception, name the rule or PDF claim and ask only for the least disclosure needed in the revised submission.

The page-layout-owning reviewer (doctoral R5 or master's R3) must additionally report the following audit-duty section after completing the same whole-thesis report as every other reviewer. This section cannot substitute for the Gate A--I matrix or persona-weighted analysis:

```markdown
## Full rendered-page audit
- Physical pages / unchecked pages:
- Suspect-page signals / resolved / unresolved:
- Actionable layout findings:
- Neighbor-page verification status:
- Machine-readable master: 02-page-layout-ledger.csv; duplicate/missing/extra page IDs:
- Source-forcing cause: not verifiable from the PDF
```

In the final `02-page-layout-ledger.csv`, every `Disposition` is exactly `clean`, `intentional`, or `finding Rn-Fxx`, where `Rn` is the assigned page owner. `recheck after edit` is an intermediate work state and is invalid in a frozen final ledger. Every referenced finding ID must exist in the current owner's report. `Actionable layout findings` is the number of distinct referenced finding IDs, not the number of page rows; one finding may anchor several pages and still counts once.

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
- Machine-readable master: 03-bibliography-audit-ledger.csv; duplicate/missing/extra reference IDs:
```

In the long-form bibliography ledger, `Field=url` and `Field=access_date` describe fields rendered by the frozen thesis and are carried by `RenderedValue`/`CanonicalValue`. `EvidenceEndpoint` and `CheckedAt` separately record the authoritative source and date used by the auditor. A metadata URL does not become an accessed `public_endpoints` receipt merely by appearing in a rendered or canonical bibliography value.

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
- Machine-readable master: 04-citation-claim-audit-ledger.csv; duplicate/missing/extra Pair IDs:
```

In `04`, copy `ExactAttachedProposition` from the same Pair ID's frozen
`AdjacentPDFText`. For every `direct`, `partial`, `context-only`, or `mismatch`
row, `DispositionEvidence` contains exactly one
`occurrence binding: <PairID>@sha256=<64-hex>` marker computed under the
`ledger-validation.md` normalization and then a substantive evidence statement.
Do not add a different free-text subject: an explicit `occurrence-specific
subject:` or `attached proposition:` must normalize exactly to the proposition
column. `ContentSourceOpened` is the complete identity-bound source-content
endpoint itself; a complete URL recorded only as an auxiliary `accessed
endpoint:` does not cure a truncated main endpoint. Locators and evidence are
occurrence-specific rather than a bulk template with only URLs, identifiers,
numbers, Pair IDs, source titles, or proposition quotations changed. The
proposition is an atomic source-responsibility span: it contains neither another
Stage-P occurrence marker nor running page furniture/detached page number, is no
longer than 300 marker-stripped normalized non-whitespace characters, and does
not attribute a
thesis-local method/result/table value directly to an external source. Split
multi-source sentences by supported clause. Above 200 characters, any genuine
internal sentence or clause boundary is fatal and the proposition must be split;
ordinary abbreviations such as `e.g.` and `et al.` do not create that boundary.
`Abstract` alone is insufficient
for a detailed equation, theorem, metric definition, algorithm step, or table
value.

The evidence text after the binding marker uses the closed four-clause sequence
from `citation-audit.md`: `pair role`, `source-stated claim`, `source anchor`,
and `support boundary`. A bare locator or title-similarity sentence cannot stand
in for these clauses. In a multi-source occurrence, inspect each Pair's assigned
and actual responsibility; for a thesis-produced baseline table, separate the
externally sourced method identity from thesis-local evaluated values.

Every numeric vector in the three owner sections is derived from the authoritative CSV, not estimated in prose. Page totals and suspect/resolved/unresolved counts reconcile to `02`, while `Actionable layout findings` equals the distinct current-owner finding IDs referenced by exact final `02` dispositions; unrelated Gate-I findings do not inflate it. Bibliography field groups reconcile verdict-by-verdict to all `03` rows (so the master-row total is `17 × rendered references`); and citation occurrence/pair/reference/support counts reconcile to `00-citation-inventory.csv` and `04`. `Semantically verified pairs` is the sum of `direct` and explicitly justified `not-needed`; every other support class is reported separately. Each machine-readable-master line ends with exact duplicate/missing/extra counts, which must all be zero in a complete bundle.

Questions are not counted as defects until evidence supports them. Every question is later dispositioned exactly once in the Chair disagreement/decision table so it cannot disappear from Stage S.

A question still has to be within the thesis-review obligation. A reviewer may not use the question table to retain an external-artifact wishlist that would be invalid as a finding.

Every ledger-owning reviewer adds the following actor-authored section after the
base `Coverage and limitations` section and before its full-audit duty sections.
It is a semantic declaration and is not generated by the materializer:

```markdown
## Owned-ledger finding/question reconciliation

| Report item ID | Owned-ledger selectors |
|---|---|
| Rn-F01 | none |
```

The table contains every current finding and question exactly once in report
order; an empty canonical table is required when the report has none. A holistic
item with no basis in an owned ledger uses exactly `none`. Otherwise use the
closed selectors `02:page=Pnnnn`, `03:field=REFnnnn/<field>`,
`04:pair=Cnnnn-Snn`, or `04:reference=REFnnnn`, separated by comma-space and
ordered by ledger then authoritative row order. Doctoral R4 may use only `04`;
doctoral R5 only `02`/`03`; master's R3 may use all three. A reference selector
expands to every current `04` Pair row for that `ReferenceID`; do not mix it with
any of its expanded Pair selectors. The expanded selector set must equal—not
merely overlap—the authoritative ledger rows that name the report item. A row
signed as `none`/`reasoned non-finding` cannot be claimed by this table.

Before freezing an R-numbered report, verify that the decision regime, category, recommendation, severity profile, and required revision path are consistent with `grading-and-verdicts.md`.

Under `institutional`, `Governing source` is a duplicate-free semicolon-separated subset copied exactly from `governing_rule_urls` or the `official_title` values of hash-bound `governing_local_files` in the process envelope. An invented description or unrelated URL is invalid. Under `skill-default`, the governing-source field is `N/A`.

## Standalone AI-style assessment

The canonical AI `opened=[...]` sequence is exactly: `00-process-parameters.json`; `SKILL.md`; `clean-room-orchestration.md`; `report-template.md`; `ai-style-audit.md`; `rules/scripts/validate_review_bundle.py`; `rules/scripts/validate_ai_output.py`; `<frozen_pdf_file>`; `00-manifest.md`; `00-page-inventory.csv`; and any AI-recipient helper provenance/outputs. It contains no R report, `02`--`04`, Chair, Stage-S, old-round, or governing-local-file input. Before freeze, run `python rules/scripts/validate_ai_output.py <exact-round-root>` to PASS.

```markdown
# Standalone AI-style prose assessment

## Boundary and independence
- Actor ID: AI
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Frozen artifact:
- Reviewer-visible inputs:
- Excluded material:
- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Independence declaration:
- Operational prompt SHA-256: <exactly one 64-hex hash>
- Input-receipt/access declaration: received=[operational prompt]; opened=[the exact canonical ordered AI allowlist]; public_endpoints=[none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: <start 64-hex hash> / <end 64-hex hash> (both hashes must be on this one line)
- Required disclaimer: This is a prose-style assessment, not a determination of AI use, authorship, plagiarism, or misconduct.

## Overall judgment
- AI-style signal: low / moderate / high / indeterminate
- Confidence: high / medium / low
- Rationale:

## Coverage and mechanical checks
- Physical pages inspected: <physical_page_count> / <physical_page_count>
- Authored sections inspected:
- Recurrent-pattern queries/statistics:
- Corpus exclusions:

## Signal-family summary and counter-evidence
...

## Findings

### AI-F01 — short title
- Impact: material / local / optional
- Location: canonical `physical p.<n>` within `1..physical_page_count`, optionally followed by section/table/figure detail
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
The colon-labeled bullet fields above form a closed schema. Use no additional or
renamed colon-labeled bullet field anywhere in this artifact; write
signal-family discussion, counter-evidence, limitations, and sealed out-of-scope
observations as paragraphs, tables, or bullets without colon-style field labels.

## Independent semantic acceptance

Stage SA starts only after every R report, its owner ledgers/renders, and the
standalone AI report are frozen in the closed current round. Launch one new,
mutually isolated acceptor for
each target actor. An acceptor is neither another reviewer nor a Chair: it may
not add, delete, rewrite, merge, grade, or adjudicate a finding. It decides only
whether the target's already-frozen semantic work is sufficiently supported,
complete for its mandatory scope, and safe to admit to Chair synthesis. It may
write only `SA-<target>.md` and matching CSV at the root of its private,
target-specific view; it never writes directly into the closed round's
`06-semantic-acceptance/` directory. After the scoped validator exits `0` with
`PASS`, Stage O byte-copies those two frozen files into
`06-semantic-acceptance/` without rewriting them. A single failed row makes
that acceptor `FAIL` and invalidates the entire retry; the target artifact is
never reopened or patched.

These namespaces are not alternatives: scoped validation accepts only the two
private-view-root files, while set validation accepts only the promoted pair in
the finalized-round subdirectory. The SA prompt names the root-level output
paths literally and prohibits creating a private-view
`06-semantic-acceptance/` directory. A passing SA admits the already-frozen,
byte-identical target to later Chair synthesis; it does not authorize a target
rewrite or a second target copy.

Each acceptor receives only its exact operational prompt, frozen PDF identity
and bytes, the governing rules needed for that target, the neutral Stage-P
navigation packet needed for that target, and that target's frozen report and
owned artifacts. It does not receive another R/AI report, another semantic
acceptance, Chair/Stage-S output, conversation history, author explanations,
old rounds, thesis source, `.bib`, Git state, sibling repositories, or private
experiment/provenance material. Public endpoints are restricted to those
already authorized for the target. Run the staged validator inside the isolated
view before freezing:

```text
python rules/scripts/validate_semantic_acceptance_output.py <exact-SA-view> <target>
```

The Markdown file has this exact closed H1/H2 sequence and fields:

```markdown
# Semantic acceptance — <target>

## Identity and access
- Actor ID: SA-<target>
- Target actor ID: <target>
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Operational prompt SHA-256: <exact process actor_prompt_sha256.SA-<target>>
- Frozen PDF SHA-256 at start and end: <selected_pdf_sha256>; <selected_pdf_sha256>
- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Input-receipt/access declaration: received=[operational prompt]; opened=[the exact canonical ordered SA-<target> allowlist]; public_endpoints=[the exact duplicate-free subset actually opened, or none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Semantic-acceptance boundary: this actor did not create, modify, merge, grade, or adjudicate thesis findings; it evaluated only whether the frozen target actor outputs were semantically supported, complete for their mandatory scope, and admissible to the Chair.

## Target hash binding and coverage
- Target artifact hashes: <relative-target-file>@<SHA-256>; ...
- Coverage row count: <exact matching CSV row count>

## Acceptance result
- Overall semantic acceptance: PASS / FAIL
- Acceptance failure count: <exact number of failed CSV rows>
- Limitations: <concrete limits of this acceptance, without creating thesis findings>
```

The matching CSV is the semantic master and has this exact schema:

```text
AcceptanceRowID,TargetUnitType,TargetUnitID,TargetArtifact,TargetArtifactSHA256,CheckClass,AcceptanceDisposition,EvidenceAnchor,SemanticBasis
```

`AcceptanceRowID` is continuous `SA000001...`; disposition is exactly `pass`
or `fail`. The row universe is closed and ordered:

- every ordinary reviewer covers Gate A--I, every rendered numbered body
  chapter, every current `Rn-Fxx`, every current `Rn-Qxx`, and its verdict;
- the citation-ledger owner additionally covers every authoritative `PairID`;
- the page/bibliography owner additionally covers every physical `PageID` and
  every authoritative `(ReferenceID,Field)` row;
- the AI acceptor covers every Stage-P-authored-prose page, every current
  `AI-Fxx`, and the overall non-attribution style judgment.

The target-artifact binding is equally closed: report units (including chapter
units) point to that target's report, citation pairs to
`04-citation-claim-audit-ledger.csv`, page
units to their exact `page-renders/Pnnnn.png`, bibliography fields to
`03-bibliography-audit-ledger.csv`, and AI units to
`05-ai-style-assessment.md`. Each row names the target artifact's current hash.
R4 pair rows require the exact proposition responsibility and exact singleton
physical occurrence page from `00-citation-inventory.csv`. Ordinary sourced
states additionally require the pair's independently opened source URL and
exact source locator; an abstract-only locator cannot accept a detailed
formula, definition, algorithm step, or table value. A documented non-dangling
`Support=unverifiable` row with blank authoritative `04` source and locator must
not fabricate either field: its `SemanticBasis` instead binds the exact audited
support, metadata status, and concrete `04` access/content limitation. A
dangling row contains no source URL/locator and binds the exact PDF-visible
location, displayed marker, missing `REF` entry, sentinel,
`Support=unverifiable`, `MetadataStatus=mismatch`, and authoritative `04`
disposition; generic dangling/unavailable prose fails. Passing
finding/question/AI-finding rows name the exact singleton physical page in the
target item's canonical location, while failed rows may cite a corrected page
to explain rejection. Verdict and AI-judgment rows still require concrete
physical-PDF anchors. R5 page rows are
based on the rendered PNG and check actual page numbering, float attachment,
clipping/overflow, blank-page behavior, and bibliography carry-in/new-label
ranges. R5 bibliography rows independently compare the rendered field with its
public authority, including cross-page URLs. Each bibliography row uses the
exact semicolon-delimited closed cues `rendered cue: <exact 03 value>;`,
`authority cue: <exact 03 value>;`, and
`audited verdict: <exact 03 verdict>;`; it binds
the exact `03` rendered/canonical values and a physical page belonging to that
reference's rendered entry (all contributing entry pages for a cross-page
URL). AI rows judge only recurring
authored-prose signals and counter-evidence, never authorship or misconduct.
Ordinary report rows independently test PDF support, whole-thesis search,
severity, and verdict proportionality. A generic template, unchecked row,
identity-only source match, or copied target rationale is a failure.
Neither `EvidenceAnchor` nor `SemanticBasis` may assign a grade, direct the
Chair or defense decision, or create/add/invent a thesis finding.

For a passing `finding` row, `SemanticBasis` is exactly one compact canonical
JSON object (UTF-8 characters retained, no insignificant whitespace) in this
closed key order:

```json
{"premise_class":"<explicit-positive|bounded-inference|absence-after-search>","target_premise":"<exact parsed target Observation>","supporting_pdf_evidence":"<independently checked PDF fact including the finding's exact physical p.N>","whole_pdf_resolution":{"status":"<responsive-passages-reviewed|no-responsive-passage-found|not-applicable-positive-local-fact>","pages":["<physical p.N, only when responsive>"],"search_concepts":["<concrete concept used in the whole-PDF search>"],"detail":"<what the responsive passages establish, or what the complete search did not find>"},"residual_gap":{"status":"present","detail":"<the defect remaining after the whole-PDF check>"},"action_delta":{"status":"<same-as-target-required-action|narrower-than-target-required-action|different-from-target-required-action>","detail":"<minimum still-unmet action>","independent_reason":"<acceptor's independent reason for that relation>"}}
```

For `no-responsive-passage-found`, `pages` is `[]` and
`search_concepts` is nonempty. `absence-after-search` requires that status;
`bounded-inference` may use it or `responsive-passages-reviewed`. The
`not-applicable-positive-local-fact` status is limited to `explicit-positive`
and uses empty `pages` and `search_concepts`. Every substantive string must be
concrete: empty, `N/A`/`none`-style, and Chinese-empty placeholders fail.
`same-as-target-required-action` binds the target action exactly;
`narrower`/`different` must not relabel an identical action, and the independent
reason must not copy either action text.

For a passing ordinary-reviewer `verdict` row, `SemanticBasis` is one compact
canonical JSON object with the exact ordered keys shown below. Each outer value
is the validator-derived canonical JSON projection string for that unit:

```json
{"gate_disposition_profile":"<canonical projection JSON string>","actionable_finding_profile":"<canonical projection JSON string>","synthesis_cue":"<canonical projection JSON string>","target_verdict":"<canonical projection JSON string>","coherence_result":"<canonical projection JSON string>"}
```

These values exactly project Gate A--I, all `S0`--`S3` findings, all seven
whole-thesis synthesis fields, and the verdict. The acceptor still performs the
semantic comparison; the projection only prevents it from silently accepting a
different or internally inconsistent report.

After all target acceptors freeze, Stage O runs:

```text
python rules/scripts/validate_semantic_acceptance_output.py <exact-round-root> --set
python rules/scripts/materialize_semantic_acceptance_gate.py <exact-round-root>
python rules/scripts/validate_semantic_acceptance_output.py <exact-round-root> --set --require-gate
```

The materializer may write only `06-semantic-acceptance-gate.json`. Its v2
schema contains round/retry/PDF identity, the exact process-file SHA-256, the
closed current `SA-*` prompt-hash map, exact hashes and row counts for every
required acceptance pair, exact hashes of every frozen target artifact,
per-target `PASS`, and overall `PASS`; it contains no finding text, rationale,
anchor, source URL, grade, or acceptance reason. The Chair opens this hash-only
gate but never the individual SA Markdown/CSV files. It recomputes the current
process hash, SA prompt projection, target hashes, and coverage. Because the
private acceptance files are intentionally absent, their two hashes per target
remain Stage-O transport commitments whose 64-hex form—but not bytes—the Chair
can check. Stage O's final full validator must later open the private set and
recompute those hashes/content before delivery. Stage S opens neither the gate
nor individual SA files.

## Chair synthesis

Before freeze, run `python rules/scripts/materialize_owner_outputs.py <exact-round-root> C` to MATERIALIZED and then `python rules/scripts/validate_chair_output.py <exact-round-root>` to PASS. Repeat both after any semantic Chair-source edit. The validator's explicit pre-Stage-S mode requires every current upstream/Chair artifact and the hash-only semantic-acceptance gate, while forbidding individual semantic-acceptance reports and `93`, `94`, and `95`; it does not waive errors by matching diagnostic wording. The Chair may correct only its current `90`--`92` outputs before freeze. A defect in any frozen R/AI report, packet/ledger, semantic-acceptance closure, process/rule input, or PDF returns control to Stage O for a global retry.

```markdown
# Chair synthesis

## Clean-room boundary
- Actor ID: C
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Chair fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Exact current-round input allowlist: 00-process-parameters.json; SKILL.md; clean-room-orchestration.md; china-policy.md; grading-and-verdicts.md; review-rubric.md; reviewer-panels.md; report-template.md; ledger-validation.md; rendered-pagination-audit.md; citation-audit.md; ai-style-audit.md; rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_semantic_acceptance_output.py; rules/scripts/validate_chair_output.py; <each governing_local_files neutral_file in process order>; <frozen_pdf_file>; 00-manifest.md; 01-policy-basis.md; 00-page-inventory.csv; 00-bibliography-inventory.csv; 00-citation-candidate-ledger.csv; 00-unmatched-bracket-ledger.csv; 00-citation-inventory.csv; 02-page-layout-ledger.md; 02-page-layout-ledger.csv; 03-bibliography-audit-ledger.md; 03-bibliography-audit-ledger.csv; 04-citation-claim-audit-ledger.md; 04-citation-claim-audit-ledger.csv; R1-comprehensive-review.md; ...; Rn-comprehensive-review.md; 05-ai-style-assessment.md; 06-semantic-acceptance-gate.json; <any C-recipient helper provenance/outputs in canonical helper order> (omit each inapplicable placeholder; expand every actual governing filename, R row, and registered helper path exactly, in order, with no ellipsis; never open `06-semantic-acceptance/`)
- Operational prompt SHA-256: <exactly one 64-hex hash>
- Chair input-receipt/access declaration: received=[operational prompt]; opened=[the exact expanded allowlist above in the same order]; public_endpoints=[a duplicate-free subset of current process-rule URLs and current 03/04 evidence/content endpoints, or none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: <start 64-hex hash> / <end 64-hex hash> (both hashes must be on this one line)

## Overall risk and recommendation
- Decision regime: institutional / skill-default
- Overall official category: required under `institutional`; otherwise N/A
- Overall official defense recommendation: required under `institutional`; otherwise N/A
- Overall governing source: required under `institutional`; otherwise N/A
- Overall academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Overall defense recommendation: exact skill-default Chinese action conclusion; `N/A` under `institutional`
- Confidence:
- Whole-thesis rationale:

## Reviewer coverage validation
| Reviewer | Gate A | B | C | D | E | F | G | H | I | Whole-thesis rationale | Audit duty complete | Eligible for adjudication |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

Validate this table before substantive synthesis. Because every reviewer report and its independent semantic acceptance are already frozen before Stage C starts, a missing gate row or failed hash closure invalidates the current retry and returns control to Stage O for a new global retry; the Chair must not reopen or patch that reviewer artifact.

Each Gate cell exactly copies that reviewer's frozen Gate disposition. `Whole-thesis rationale` is the literal status `complete`. `Audit duty complete` is `yes` only for the assigned owner (doctoral R4/R5, or master's R3) and `not assigned` for every other reviewer; it is not a generic quality score. `Eligible for adjudication` must be `yes` for every included reviewer.

## Independent verdicts
| Reviewer | Persona | Category/grade | Defense recommendation | Decision regime/source | Confidence | Decisive reason |
|---|---|---|---|---|---|---|

- Category distribution: <sorted category=count values joined by "; ">
- Modal/severe-minority departure explanation: <at least one concrete sentence; say explicitly when there is no departure>

Under the skill-default regime, do not convert letters to numbers: the chair's overall grade is an evidence-adjudicated decision, not an average, median, or automatic majority result. Explain any departure from a severe minority opinion or from the modal category.

## Standalone AI-style judgment
- Signal: low / moderate / high / indeterminate
- Confidence:
- Material/local/optional findings: material=<integer> ; local=<integer> ; optional=<integer>
- Separation statement: report this outside the reviewer verdict distribution and do not infer AI use, authorship, plagiarism, or misconduct.

## AI-style actionable findings
| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Verification | Status |
|---|---|---|---|---|---|---|

These rows populate `91-ai-actionable-ledger.csv` and never receive academic severity/remedy classes or change the defense grade.

## Contributions that survived review
...

## Adjudicated findings
| Chair finding ID | Source reviewer finding IDs | Severity | S0 subtype | Remedy | Exact PDF anchor | Direct observation | Evidence status | Owner | Minimum required action | Verification |
|---|---|---|---|---|---|---|---|---|---|---|

Before creating a `C-Fxx` row, the Chair applies the submission-obligation gate. A reviewer finding that merely asks for hidden author-side material not required in the thesis or a verified formal attachment is cited directly by its `Rn-Fxx` ID in a `rejected` decision-table row and produces no Chair finding, revision-ledger row, `92` evidence item, or Stage-S actionable/question projection. `not verifiable from submitted PDF` is reserved for a surviving in-scope thesis question, not for uncertainty about whether an out-of-scope private artifact exists.

## Mandatory citation cross-ledger consistency gate
| Rendered reference ID | Displayed label | Affected Pair IDs | Citation-ledger identity/source projection | Bibliography-ledger canonical identity projection | Version/record agreement (`agree` / `disagree` / `not verifiable`) | Conflict class (`none` / `local` / `substantive`) | Chair finding ID(s) | Resolution (`closed` / `open`) |
|---|---|---|---|---|---|---|---|---|

- Unique cited rendered references joined:
- Identity-agreement count:
- Version disagreements:
- Local conflicts:
- Substantive conflicts:
- Reclassified Pair IDs:
- Unresolved conflicts:
- Combined citation gate: pass / fail

The table has exactly one row for every cited `ReferenceID`, in first-citation order. `Displayed label` is copied from `00-bibliography-inventory.csv`; when the displayed citation is dangling, derive `[n]` from `REFnnnn`. `Affected Pair IDs` is the comma-space-joined sequence of all `04` rows for that reference in the exact `00`/`04` numeric Pair-ID order. `Citation-ledger identity/source projection` is the exact ledger-order serialization `PairID=>PublicIdentifier @ ContentSourceOpened`, joined by ` ; ` and using `N/A` only for a blank content source. `Bibliography-ledger canonical identity projection` is the exact fixed-order serialization `field=CanonicalValue`, joined by ` ; `, for `title`, `ordered_authors`, `year`, `venue`, `publication_status`, `doi`, `arxiv_id`, `arxiv_version`, `url`, `isbn_or_other_persistent_id`, and `existence`. For a dangling reference, that whole bibliography projection is exactly `no rendered bibliography entry`, agreement is `disagree`, and the row links the substantive current chair finding that adjudicates the missing entry.

The agreement value is derived from the frozen ledgers: `disagree` when any projected bibliography field or citation `MetadataStatus` is `mismatch`; otherwise `not verifiable` when any is `unverifiable`; otherwise `agree`. A disagreement cannot have conflict class `none`. A local conflict maps only to an `S3` chair finding; a substantive conflict maps to an `S0`--`S2` chair finding. Conflict rows list canonical comma-space-separated current `C-Fxx` IDs and set resolution from the linked `91` statuses; a no-conflict row uses `none` and `closed`. Counts are derived from these rows, `Reclassified Pair IDs` counts all Pair IDs in non-`none` rows, and the combined gate passes exactly when no conflict row remains open.

## Disagreements and chair decisions
| Decision ID | Source item IDs | Topic | Positions | Evidence checked | Status | Decision |
|---|---|---|---|---|---|---|

Keep this exact table even when it has no rows. Use continuous `D01...` IDs. `Source item IDs` is a canonical list containing current `Rn-Qxx`, current `C-Fxx`, and/or current `Rn-Fxx` IDs. A direct `Rn-Fxx` token is permitted only in a `Status=rejected` row, only for a finding rejected by the submission-obligation gate, and may not be mixed with question or Chair-finding IDs in that row. Every reviewer question, every `C-Fxx` whose `EvidenceStatus` is `not verifiable from submitted PDF` or `disputed`, and every directly rejected reviewer finding appears exactly once. `Status` is exactly `resolved`, `unresolved`, `not verifiable`, `rejected`, or `disputed`; the row preserves the positions, checked evidence, and chair decision. A direct `Rn-Fxx` `rejected` row is the terminal disposition for an out-of-scope external-artifact request and never enters `91`, `92`, or Stage S. Stage S projects the `unresolved`, `not verifiable`, and `disputed` rows exactly and in order.

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

`91-revision-ledger.md` begins with the chair's complete actor/round/retry identity, fresh-context, exact input-receipt/access, process-bound prompt-hash, and start/end PDF-hash declaration block before the tables.

```markdown
| Ledger ID | Priority | Chair finding ID | Source reviewer finding IDs | Severity | S0 subtype | Remedy | Exact PDF anchor | Direct observation | Evidence status | Minimum edit/evidence | Dependency | Owner | Status | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L01 | P0 | C-F01 | Rn-Fxx | S0/S1 | procedural / integrity/foundational / N/A | W/E/N/P | ... | ... | verified / partially verified / not verifiable from submitted PDF / deduplicated / disputed | ... | ... | ... | open | ... |
| L02 | P1 | C-F02 | Rn-Fxx | S2 | N/A | W/E/N/P | ... | ... | verified | ... | ... | ... | open | ... |
| L03 | P2 | C-F03 | Rn-Fxx | S3 | N/A | W/E/N/P | ... | ... | verified | ... | ... | ... | open | ... |
```

Every current reviewer `S0`--`S3` finding enters chair adjudication exactly once: either as its own row or as one member of a supported deduplicated row in `91`, or as a direct `Rn-Fxx` `Status=rejected` row in the Chair decision table when the submission-obligation gate rejects the request. These two paths are mutually exclusive. `Source reviewer finding IDs` is a duplicate-free canonical comma-space list in reviewer/finding-number order; no current actionable finding may disappear, recur in two paths, or point to another round. `Ledger ID` and `Chair finding ID` are unique continuous `L01...` and `C-F01...` sequences. Every open required `S0`--`S3` chair finding appears exactly once. Optional `S4` suggestions and non-finding questions do not enter this required ledger; put them in separately labeled sections of the chair report.

An upstream reviewer finding rejected by the submission-obligation gate is adjudicated by its original `Rn-Fxx` ID in the Chair decision table but is not an actionable Chair finding and therefore never enters `91`. This is rejection of an invalid review demand, not disappearance of a supported thesis defect.

When one action depends on another ledger row, `Dependency` names the existing
`Lnn` foreign key(s) directly. Do not use the current row's own ID, repeat an
ID, create a cycle, or invent a phantom ID. Validated dependency IDs may recur
only in this column; this is the intentional foreign-key exception to the
otherwise unique Ledger-ID Markdown projection.

In the same `91-revision-ledger.md`, add the following separate table, mirrored exactly by `91-ai-actionable-ledger.csv`:

```markdown
## AI-style actionable ledger — separate from academic grading
| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Status | Verification |
|---|---|---|---|---|---|---|
```

Every unresolved current-round `AI-Fxx` with `material` or `local` impact appears exactly once. Do not assign academic severity, remedy class, priority, or defense consequence. Optional AI findings remain outside this actionable table.

## New evidence or experiments

Always split the list:

`92-new-evidence-or-experiments.md` begins with the chair's complete actor/round/retry identity, fresh-context, exact input-receipt/access, process-bound prompt-hash, and start/end PDF-hash declaration block before these sections. `92-new-evidence-or-experiments.csv` is the authoritative N-remedy row set with schema `EvidenceItemID,LedgerID,ChairFindingID,Remedy,Item,ClaimThatDependsOnIt,WhyWritingIsInsufficient,MinimumViableEvidence,ConsequenceIfUnavailable`.

```markdown
## No-new-experiment remedies (W/E/P)
| Ledger ID | Remedy | Exact PDF anchor | Minimum edit/evidence | Verification |
|---|---|---|---|---|

## Genuine new experiments or unavailable evidence (N)
| Evidence item ID | Ledger ID | Chair finding ID | Remedy | Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |
|---|---|---|---|---|---|---|---|---|
```

The W/E/P table is the exact ledger-order projection of every open current `91-revision-ledger.csv` row whose remedy is W, E, or P. Each open current row whose remedy is N has exactly one `92` CSV row and Markdown row; no other `91` row may enter the CSV. `EvidenceItemID` is continuous `N01...`, and `LedgerID`, `ChairFindingID`, and `Remedy=N` exactly match the linked `91` row. An empty N CSV/table is valid and often preferable when no open N remedy exists.

Within the no-new-experiment table, `E` means existing evidence whose necessary content will be incorporated into the revised PDF or a verified formal submission attachment. Evidence that would remain only in an author's private repository, log, hash list, or audit package is not an `E` thesis remedy. Use `W` for a sufficient clarification or claim narrowing; omit an out-of-scope request entirely.

## Clean user-facing summary

Run this as Stage S in a new context after `90`--`92` are frozen. The summarizer does not browse the web, consult conversation history, open the frozen PDF, or re-adjudicate evidence. Its PDF fields are identity projections copied from the process envelope and current frozen source artifacts, not checksums recomputed by Stage S.

Before freeze, run `python rules/scripts/materialize_owner_outputs.py <exact-round-root> S` to MATERIALIZED and then `python rules/scripts/validate_summary_output.py <exact-round-root>` to PASS. These scoped commands open only the process/summary rules, full/materializer/Stage-S validator scripts, current R/AI/Chair reports, `91`/`92` sources, and S's three outputs. They never open the PDF, Stage-P packet, `02`--`04`, individual semantic-acceptance files, `06-semantic-acceptance-gate.json`, helpers, prior artifacts, or `95`; Stage O alone runs the full post-S validator and writes `95-bundle-validation.md`.

The validated Markdown dialect permits ATX headings with zero to three leading spaces and optional closing hashes. It forbids Setext headings, raw HTML blocks, HTML comments, fenced code, and indented code in review artifacts because non-rendered content cannot carry evidence or contract fields.

```markdown
# Current-round user-facing review summary

## Clean-room identity
- Actor ID: S
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Frozen PDF path and SHA-256: file=<frozen_pdf_file> ; sha256=<selected_pdf_sha256>
- Summary fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Exact current-round input allowlist: 00-process-parameters.json; SKILL.md; clean-room-orchestration.md; report-template.md; rules/scripts/validate_review_bundle.py; rules/scripts/materialize_owner_outputs.py; rules/scripts/validate_summary_output.py; R1-comprehensive-review.md; ...; Rn-comprehensive-review.md; 05-ai-style-assessment.md; 90-chair-synthesis.md; 91-revision-ledger.md; 91-revision-ledger.csv; 91-ai-actionable-ledger.csv; 92-new-evidence-or-experiments.md; 92-new-evidence-or-experiments.csv (write the expanded exact semicolon-separated basename set, with no ellipsis or extra file)
- Operational prompt SHA-256: <exactly one 64-hex hash>
- Summary input-receipt/access declaration: received=[operational prompt]; opened=[the exact expanded current-round input allowlist above in the same order]; public_endpoints=[none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: <copy selected_pdf_sha256> / <copy selected_pdf_sha256> (Stage S does not open or hash the PDF; both identity projections remain on this one line)

## Independent and overall conclusions
| Actor | Persona/status | Category or AI-style label | Exact defense recommendation | Decision regime/source | Confidence | Decisive current-round basis |
|---|---|---|---|---|---|---|

## Current actionable items
| Ledger ID | Priority | Chair finding ID | Source reviewer finding IDs | Severity | S0 subtype | Remedy | Exact PDF anchor | Direct PDF-visible observation | Evidence status | Minimum required action | Dependency | Owner | Chair disposition | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Current AI-style actionable items — separate from academic grading
| AI finding ID | Impact (`material` / `local`) | Exact PDF anchor | Direct style observation | Minimum editing action | Chair status | Verification |
|---|---|---|---|---|---|---|

## Current new evidence or experiments (N)
| Evidence item ID | Ledger ID | Chair finding ID | Remedy | Item | Claim that depends on it | Why writing is insufficient | Minimum viable evidence | Consequence if unavailable |
|---|---|---|---|---|---|---|---|---|

## Optional suggestions
none

## Unresolved questions
| Decision ID | Source item IDs | Topic | Positions | Evidence checked | Status | Decision |
|---|---|---|---|---|---|---|

## Review limitations
none

## Reconciliation
- Open required rows in 91-revision-ledger.csv:
- Rows in 93-current-actionable-items.csv:
- Rows in Current actionable items Markdown table:
- Missing ledger IDs: none / list and mark summary invalid
- Extra summary IDs: none / list and mark summary invalid
- Duplicate IDs: none / list and mark summary invalid
- Open AI rows in 91-ai-actionable-ledger.csv:
- Rows in 93-current-ai-actionable-items.csv:
- Rows in Current AI-style actionable items Markdown table:
- Missing/extra/duplicate AI finding IDs: none / list and mark summary invalid
- Rows in 92-new-evidence-or-experiments.csv:
- Rows in Current new evidence or experiments Markdown table:
- Missing/extra/duplicate evidence item IDs: none / list and mark summary invalid
- Statement: This summary introduces no new finding and uses no prior-round or author-side information.
```

The H1 and nine H2 headings above are an exact closed sequence: no extra H2, preamble, appendix, or free prose outside those sections is allowed. `Clean-room identity` contains only its nine bullets in the shown order. The allowlist is the exact canonical ordered basename sequence with each name once; a set-equivalent reorder or duplicate is invalid. `Independent and overall conclusions`, the three current-item sections, and `Unresolved questions` contain only their canonical tables. `Reconciliation` contains only its fourteen shown bullets in order. Replace the illustrative `none` bodies in `Optional suggestions` and `Review limitations` with exact whitespace-normalized copies of the current Chair sections; keep `none` only when the Chair section is `none`.

Keep the AI-style actor row visibly separate from the reviewers and Chair; its defense recommendation and regime/source are `N/A`. The actor table is an exact projection, including its prose basis; Stage S writes no new rationale. Reviewer persona fields come only from the unique `Role, scope, and independence` section, reviewer verdict fields from the unique `Verdict` section, AI fields from the unique `Overall judgment` section, and Chair fields from the unique `Overall risk and recommendation` section. `Persona/status = Persona assignment + " — " + Persona emphasis` for reviewers, `standalone AI-style assessment` for AI, and `chair adjudication` for Chair. Category, recommendation, regime/source, confidence, and rationale copy their authoritative source fields byte-for-byte after trimming. The degree-specific persona-assignment values are the exact values listed earlier in this file. Any paraphrase, extra context, old-round statement, author explanation, or repository fact invalidates Stage S.

The open academic and AI row sets are lossless, order-preserving projections: `93-current-actionable-items.csv` has exactly the same fifteen columns and values, in the same order, as the open subset of `91-revision-ledger.csv`; `93-current-ai-actionable-items.csv` has exactly the same seven columns and values, in the same order, as the open subset of `91-ai-actionable-ledger.csv`. Their Stage-S Markdown tables preserve the corresponding CSV order and exact fields. The current N-evidence table is the exact ordered projection of `92-new-evidence-or-experiments.csv`. The conclusion table order is `R1...Rn, AI, Chair`. `Unresolved questions` is the exact ordered subset of the current Chair decision table whose status is `unresolved`, `not verifiable`, or `disputed`. The `Statement` reconciliation value is exactly `This summary introduces no new finding and uses no prior-round or author-side information.` Every row and statement is current-round-only. Do not mention old/resolved items, user explanations, previous assistant summaries, companion papers/repositories, source-sync facts, or implementation claims invisible in the PDF. Before S freezes, a failure confined to an S-owned projection is corrected only in the three `93` outputs and the scoped gate is rerun. An inconsistency in a frozen R/AI/Chair/`91`/`92` source, or any failure discovered after S freezes, invalidates the whole retry and returns control to Stage O for a new global retry; never reopen the Chair or improvise a mixed lineage.

## Fresh re-review and optional prior-issue closure

```markdown
## Fresh category and defense recommendation — freeze before any prior ledger is opened
- Decision regime: institutional / skill-default
- Official category: required under `institutional`; otherwise N/A
- Official defense recommendation: required under `institutional`; otherwise N/A
- Governing source: required under `institutional`; otherwise N/A
- Academic grade: A / B / C / D — required under `skill-default`; otherwise N/A
- Defense recommendation: exact skill-default Chinese action conclusion; otherwise N/A
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

## Boundary and frozen-current-round identity
- Actor ID: V
- Review round ID: <exact process round_id>
- Review retry ID: <exact process retry_id>
- Current frozen PDF and round: round_id=<round_id> ; retry_id=<retry_id> ; file=<frozen_pdf_file> ; sha256=<current PDF SHA-256>
- Current fresh reports/chair/summary already frozen: <canonical ordered basename@SHA-256 list for current 00 page/bibliography/citation inventories, 02/03/04 CSV masters, every current R report, 05, 90, 91 Markdown/CSVs, 92 Markdown/CSV, and 93 Markdown/CSVs>
- Hash-bound prior-issues CSV: <exactly one *prior-issues.csv basename@SHA-256>
- Additional allowlisted prior artifacts: none / <duplicate-free basename@SHA-256 list of copied author responses or other specifically authorized prior artifacts>
- Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested: not run / <basename@SHA-256>
- Full regression baseline: not run / run with complete prior baseline ; prior_pdf=<basename@SHA-256> ; prior_page_inventory=<basename@SHA-256> ; prior_page_ledger=<basename@SHA-256> ; prior_bibliography_inventory=<basename@SHA-256> ; prior_bibliography_ledger=<basename@SHA-256> ; prior_citation_inventory=<basename@SHA-256> ; prior_citation_ledger=<basename@SHA-256>
- Fresh-context declaration: no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt
- Operational prompt SHA-256: <exact process actor_prompt_sha256.V>
- Input-receipt/access declaration: received=[operational prompt]; opened=[00-process-parameters.json; SKILL.md; clean-room-orchestration.md; grading-and-verdicts.md; report-template.md; ai-style-audit.md; ledger-validation.md; <frozen_pdf_file>; every current identity above; then the prior-issues CSV, additional prior artifacts, prior AI report when run, and seven baseline artifacts when run, all as exact basenames in canonical order]; public_endpoints=[none]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated
- Frozen PDF SHA-256 at start and end: <current start hash> / <current end hash>

## Prior-issue closure

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

## Iterative completion checklist
- Final page-ledger re-entry: inventory_rows=<current 00 page rows> ; ledger_rows=<current 02 rows> ; expected=<process physical_page_count> ; missing_or_extra_page_ids=<current count> ; unchecked_or_unresolved=<current count>
- Final page and affected-neighbor recheck: rows_missing_neighbor_record=<current count>
- Final bibliography/citation re-entry and re-verification: bibliography_inventory_rows=<current 00 rows> ; bibliography_audit_rows=<current 03 rows> ; bibliography_missing_or_extra_ids=<current count> ; bibliography_mismatch=<current 03 count> ; bibliography_unverifiable=<current 03 count> ; citation_inventory_rows=<current 00 rows> ; citation_audit_rows=<current 04 rows> ; citation_missing_or_extra_ids=<current count> ; citation_support_mismatch=<current 04 count> ; citation_support_unverifiable=<current 04 count> ; citation_metadata_mismatch=<current 04 count> ; citation_metadata_unverifiable=<current 04 count>
- Empty S0--S3 status across all current reviewers: yes / no ; reviewer_s0_s3=<current report count> ; open_academic_rows=<current 91 CSV count>
- Fresh isolated AI assessment status/signal/material remainder: run ; signal=<exact current AI-style signal> ; open_material_or_local_rows=<current 91 AI CSV count>
- Remaining S4 suggestions or review limitations:
- Prior unresolved or not-verifiable findings: count=<current Stage-V closure count>
- Iterative-loop completion gate: pass / fail
```

Stage O copies every specifically authorized prior input byte-for-byte into the exact `stage-v-inputs/` directory before launching V; V never discovers inputs by enumerating an old round. The directory contains exactly the basenames declared in the Stage-V boundary, with no unallowlisted file or nested directory. Every declared artifact must exist there as a regular file and match its declared SHA-256. The required prior-ID master is one UTF-8 CSV whose basename ends in `prior-issues.csv` and whose exact schema is `PriorFindingID,PriorPDFSHA256,PriorPDFAnchor,Finding,RequiredClosureEvidence`. It has at least one row; every field is nonblank and non-placeholder; `PriorFindingID` is unique; every row binds to the same 64-hex prior PDF hash and a positive physical-page anchor. The `Prior-issue closure` table contains exactly that CSV's ID sequence in the same order—no missing, extra, duplicate, or invented ID. An author response may be an additional hash-bound locator but never replaces this CSV or defines the tracked ID universe.

This optional artifact is accepted only when `review_mode=fresh-rereview`. Its H1 and five H2 sections are an exact closed sequence. Its actor/round/retry fields and operational-prompt hash exactly project the process envelope. The current artifact list is recomputed from current file bytes. The receipt uses exactly `received=[operational prompt]`, `public_endpoints=[none]`, and an `opened=[...]` sequence equal to the canonical current/prior basename list with no extra, missing, duplicate, substring, or reorder. Prior-finding statuses are limited to `resolved`, `unresolved`, `not verifiable`, `rejected`, or `superseded by current finding`; every row needs a current physical-page anchor. Regression values are limited to `not assessed`, `no regression visible`, `regression visible`, or `not comparable`. Without the complete seven-artifact baseline above, every row says `not assessed`, the regression section says `Status: not run`, and its limitations contain the exact phrase `global regression not assessed`. Current-related IDs must be current `Rn-Fxx`, `C-Fxx`, or `AI-Fxx` IDs, or `none`.

Every deterministic checklist value is recomputed from the current `02`, `03`, `04`, `91`, reviewer, and AI artifacts. `Iterative-loop completion gate` is `pass` only when page coverage is complete with no unresolved page/neighbor record, bibliography/citation mismatch and unverifiable counts are zero, and current reviewer `S0`--`S3`, open academic rows, open material/local AI rows, and prior `unresolved`/`not verifiable` rows are all zero. The remaining-S4/limitations line is a disclosure and does not alter that computed result.

This optional longitudinal artifact cannot edit or reinterpret the current independent reports, grades, chair decision, revision ledger, or clean user-facing summary.

An author response is only a locator and record of the author's claim. Mark `resolved` only when the current frozen PDF visibly supplies the closure evidence; an author statement alone cannot close an item. Without the full prior baseline named above, Stage V performs prior-finding closure only and must state `global regression not assessed`; it may not infer that a current fresh finding was introduced by revision merely because an old issue ledger omitted it.

The exact checklist above records the iterative-loop facts. Never append those fields to or edit any frozen R, C, or S artifact.
