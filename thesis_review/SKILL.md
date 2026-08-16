---
name: thesis-review
description: Review Chinese computer-science and AI master's or doctoral degree theses with isolated blind-review panels, evidence-anchored PDF and source inspection, institution-aware policy checks, CS experiment and reproducibility auditing, narrative and contribution assessment, formatting QA, adjudication, revision planning, and independent re-review. Use for 学位论文盲审、博士论文外审、硕士论文预审、thesis review, dissertation review, full-thesis quality audits, blind-review risk assessment, or verification after thesis revisions. Default to five independent reviewers for doctoral theses and three for master's theses.
---

# Chinese CS Thesis Review

## Purpose

Evaluate a degree thesis as a coherent long-form research contribution, not as a stack of conference-paper reviews. Use a frozen evidence packet, independent reviewer passes, and a separate chair adjudication. Keep the simulated blind-review evidence separate from author-side provenance and revision evidence. Report only evidence-backed findings with exact locations and feasible remedies.

This skill is read-only unless the user explicitly asks to revise the thesis. A request to review or diagnose does not authorize edits, fabricated data, new experiments, or changes to external systems.

## Required references

Read these files completely before starting a review:

- `references/china-policy.md` for the hierarchy of national law, post-award sampling, institutional rules, and current standards.
- `references/review-rubric.md` for the common and CS/AI checks.
- `references/reviewer-panels.md` for panel composition, isolation, and reviewer-specific mandates.
- `references/report-template.md` for report files and required fields.
- `references/rendered-pagination-audit.md` for the mandatory physical-page ledger, forced-float audit, and post-edit visual regression gate.
- `references/citation-audit.md` for the mandatory full-text citation-occurrence ledger, claim--source verification, and bibliography/status audit.

Use only the sections relevant to the degree type and thesis form. Mark inapplicable criteria as `N/A` with a reason; never turn every checklist item into a mandatory experiment.

## Non-negotiable distinctions

Keep these concepts separate in every report:

1. **Pre-defense thesis review** is governed primarily by the degree-granting institution's current rules.
2. **National post-award sampling** is a quality-monitoring process for already awarded theses; its reviewer count and fail logic are not automatically the school's pre-defense rules.
3. **Defense committee size** is not the same as the number of external or blind reviewers.
4. The default panel in this skill is an intentionally strict simulation: **five independent reviewers for a doctorate and three for a master's thesis**. Do not describe that default as a universal national statutory count.
5. Institutional templates and current school rules control local formatting. Use current national standards only as a fallback or cross-check, not to override a binding school template.

## Workflow

### 1. Establish the governing context

Identify, in this order:

- degree level: master's or doctorate;
- academic or professional degree;
- institution, school/department, discipline, and expected submission year;
- binding thesis template and review regulations, including revision dates;
- review target: source tree, compiled PDF, DOCX, or a frozen PDF only;
- user intent: initial review, direct revision, or re-review.

Search official sources when rules may have changed. Record the title, issuing body, revision/effective date, URL or local file, and the exact provision used. If current institutional rules cannot be verified, say so and label any older rule as historical rather than current.

### 2. Freeze one evidence packet

All reviewers must assess the same thesis version. Create a manifest containing:

- file path, Git commit if available, PDF checksum, compilation time, and page count;
- chapter and section inventory;
- figure, table, equation, algorithm, appendix, and bibliography inventories;
- every in-text citation occurrence and citation--source pair, including its exact location and attached claim;
- a physical-page layout ledger covering every rendered page, including suspect-page triage and reviewer disposition;
- thesis-level scientific questions and claimed contributions;
- chapter-to-question, method-to-experiment, and claim-to-evidence mappings;
- applicable institutional rules and standards;
- a reviewer-visible evidence lane and, when supplied, a separate author-side evidence lane for papers, repositories, experiment logs, or data documentation.

For LaTeX, compile the final artifact and inspect the rendered PDF. Source-only review cannot verify float placement, font size, overlap, blank pages, image resolution, or final cross-references. For DOCX or PDF, use the appropriate document/PDF inspection workflow and preserve page numbers.

Do not silently replace the frozen thesis during the panel review. If the thesis changes, close the round and start a new versioned round.

#### Separate blind-review and author-side evidence lanes

Every round must classify evidence before any reviewer starts:

1. **Reviewer-visible lane:** the submitted thesis artifact, its rendered pages, governing rules, and sources that an ordinary reviewer can obtain from the thesis or its public citations. LaTeX source may be used to locate visible defects or verify compilation, but not to import undisclosed experimental facts.
2. **Author-side lane:** sibling paper repositories, unpublished paper drafts, supplements not cited or supplied with the submission, internal code/configs/logs, TODOs, experiment records, private data documentation, and author declarations supplied for revision or provenance audit.

R1--R5 verdicts, ABCD grades, and findings in a blind-review simulation must use only the reviewer-visible lane. They must not read the author-side lane before freezing their reports. A discrepancy that exists only between the thesis and a sibling paper repository is not a blind-review finding.

After all independent reports are frozen, the chair may open the author-side lane to verify a reviewer concern, reject a false positive, recover an existing value, or plan a direct edit. Label every such result **author-side provenance audit**, not “discovered by the blind reviewer.” Author-side evidence may close or downgrade a finding but must not retroactively manufacture a harsher independent grade.

If the user explicitly requests a source-assisted integrity audit in which reviewers inspect private companion materials, run it as a separately labeled audit. Do not present its outputs or scores as simulated blind-review opinions.

#### Establish evidence authority before comparing artifacts

The following authority order applies to the author-side provenance audit and direct revision, not to what a blind reviewer is presumed to see. When companion materials disagree, record their role and authority before treating the disagreement as an author-side issue. Unless the author identifies a different final source or a formal correction exists, use this order for reported methods and results:

1. the final published or submitted paper, its supplementary material, and the formal figure/table sources used to build that version;
2. an official erratum, author-designated revision, or released artifact explicitly tied to that paper version;
3. thesis-specific experiment records explicitly designated as final;
4. versioned code, configuration, logs, and evaluation outputs;
5. development notes, TODO lists, experiment plans, debug reports, scratch analyses, and abandoned drafts.

Items in the fifth class describe work in progress. They must not overturn a formal paper result, create a checkpoint inconsistency, or become the sole basis for an `S0`/`S1` finding unless the paper, a formal correction, or the author explicitly promotes them to the final source of truth. If lower-authority artifacts disagree with the final paper, first determine whether they are obsolete, diagnostic, or from a different protocol. Preserve unresolved cases as questions rather than alleging selection bias, leakage, or result conflict without affirmative evidence.

The user's explicit declaration of the intended source of truth controls among supplied research artifacts unless a formal correction or direct integrity evidence contradicts it. Similarly, do not require raw member hashes, immutable manifests, or generic near-duplicate audits as universal thesis evidence. A final paper's data and split disclosure is sufficient for a writing review unless there is a concrete leakage pathway, an internal contradiction, or a central reproducibility claim that specifically depends on member-level identity.

### 3. Run independent reviewers

Use the panel defined in `references/reviewer-panels.md`:

- doctorate: R1--R5;
- master's: R1--R3.

When subagents are available, launch reviewers as isolated tasks. They may receive the reviewer-visible manifest, thesis, rules, and rubric, but must not receive the author-side evidence lane or read another reviewer's report before submitting their own. With limited concurrency, run reviewers in batches while preserving that isolation.

When isolated agents are unavailable, perform separate passes with separate notes and disclose that independence was simulated rather than process-isolated. Never draft a consensus first and then ask reviewers to agree with it.

Each reviewer must:

- inspect the complete thesis, not only their specialty pages;
- prioritize their assigned lens without ignoring fatal problems outside it;
- cite exact page/section/table/figure/equation or source location;
- distinguish direct observation, inference, and unverified concern;
- test the thesis's strongest claims against its evidence;
- state what was checked and what could not be verified;
- issue an individual verdict before seeing other reports.

R4 owns the complete citation audit for a doctoral thesis; R3 owns it for a master's thesis. Ownership is not optional and does not mean that other reviewers may ignore citation problems they encounter. The owning reviewer must follow `references/citation-audit.md`, write `03-citation-audit-ledger.md`, and reach 100 percent disposition of all citation--source pairs before returning a citation-complete verdict. A resolved citation key, plausible title, or sample of important references is not a substitute for verifying what each citation occurrence is being used to support.

### 4. Classify every finding

Use both severity and remedy class.

Severity:

- `S0` — integrity, authorship, anonymity, fabricated/untraceable evidence, or a thesis-level defect that can invalidate review.
- `S1` — major scientific, logical, experimental, or structural defect that may lead to rejection or mandatory major revision.
- `S2` — substantive but repairable weakness that does not overturn the central contribution.
- `S3` — local writing, citation, formatting, numerical-labeling, or presentation defect.
- `S4` — optional refinement; never present it as required.

Remedy class:

- `W` — resolvable by writing, reorganization, citation repair, or formatting.
- `E` — resolvable by reusing or verifying existing evidence in the supplied papers, repositories, logs, or data.
- `N` — genuinely requires a new experiment, annotation, user study, training run, or unavailable evidence.
- `P` — requires an institutional or administrative policy decision.

Do not demand a new experiment when wording can narrow a claim to the available evidence. Conversely, do not hide a missing experiment if the thesis's central claim logically depends on it.

### 5. Apply the CS/AI evidence rules

For every method chapter, reconstruct this chain:

`scientific question -> gap -> method principle -> module role -> protocol -> result -> supported conclusion`

Flag a break only when it is real and locatable. In particular, verify:

- dataset provenance, official or custom split rules, train/validation/test isolation, and duplicate leakage where relevant;
- checkpoint/model-selection protocol only when the thesis's wording creates a leakage or cherry-picking ambiguity;
- baseline comparability, implementation source, training budget, representation conversion, and metric protocol;
- ablations that correspond to claimed causal contributions;
- uncertainty, multiple seeds, significance, and user-study design when required by the strength of the claim, not as universal rituals;
- exact internal agreement among prose, tables, figures, captions, and appendices; compare against companion source papers only in the separately labeled author-side provenance audit;
- source authority before conflict claims: final paper and supplement take precedence over obsolete TODO, planning, debug, and scratch files unless formally superseded;
- hyperparameters, software/hardware, preprocessing, and commands needed for reasonable reproduction;
- negative results, boundary conditions, or claim limits where omission would mislead;
- whether each chapter contributes to one thesis-level story rather than preserving the branding and framing of separate papers.

Never invent a value, source, training detail, or result to fill a gap. An unverified item remains explicitly unverified.

### 6. Inspect the rendered thesis as a degree thesis

Review every rendered page at a legible scale. Check:

- cover, anonymity version, declarations, abstracts, contents, lists, chapters, references, appendices, acknowledgments, and CV/publications as applicable;
- heading hierarchy and whether the table of contents communicates the research progression;
- orphan headings, widows, blank or nearly blank pages, forced breaks, float-only pages, float backlog, and figure/table clustering;
- figure and table width, text size, resolution, captions as concise titles, body explanations, numbering, references, and source attribution;
- equations and algorithms for overflow, symbol definitions, alignment, punctuation, and cross-references;
- bibliography completeness, citation-to-entry consistency, current institutional style, and suspicious unsupported clusters;
- terminology, abbreviations, units, punctuation, Chinese/English consistency, and template compliance.

Apply the full protocol in `references/rendered-pagination-audit.md`. Its requirements are gates, not suggestions:

- render every physical page at a legible resolution and record it in `02-page-layout-ledger.md`;
- use whole-document contact sheets only for triage, never as proof that an individual page is correct;
- inspect every page individually or in a small legible group, then inspect every automatically or manually flagged page at full-page scale;
- when source is supplied, map every `[H]`, `\FloatBarrier`, `\clearpage`, `\newpage`, `\pagebreak`, and equivalent source-level forcing construct to the final PDF and inspect at least the preceding, containing, and following pages; for a PDF-only review, mark the source-forcing cause `not verifiable--source not supplied` without suppressing a visible PDF finding;
- flag nearly blank pages, float-only pages, pages dominated by one figure or table, adjacent float stacks, anomalous bottom whitespace, clipped content, split captions, and a large float that prevents later prose from filling the current page;
- treat occupancy thresholds as triage signals, not automatic findings; close or retain each signal by visual evidence;
- for cropped or continued figures, verify the seam against the uncropped source so that no text, person, plot element, or semantic unit is lost or duplicated.

R5 owns this gate, but every reviewer must report any visible page defect encountered. A statement such as “all pages viewed” is insufficient without the completed page ledger and suspect-page dispositions.

Apply the full protocol in `references/citation-audit.md` as a second independent gate. R4 for a doctorate, or R3 for a master's thesis, must inventory every active in-text citation occurrence, verify every occurrence--source pair against the cited public source when accessible, verify the metadata and publication status of every cited entry, and record every inaccessible or ambiguous source explicitly. Static BibTeX closure alone does not pass this gate.

Treat the ordinary author copy and the submitted blind-review copy as different artifacts. Do not report author, supervisor, institution, or student-number fields that correctly appear in an ordinary author copy as anonymity defects. When a blind-review copy is in scope, render or obtain that actual copy and scan the entire artifact--not only the cover--for identity disclosures in body text, captions, tables, acknowledgments, CV/publications, data and project descriptions, footnotes, URLs, PDF metadata, filenames, comments, and figure watermarks. Apply the institution's exact anonymization rules; in their absence, flag school, department, laboratory, company, employer, partner organization, and other wording that can directly or cumulatively identify the candidate.

The conservative format reviewer must be able to understand the thesis without relying on frontier-specific tacit knowledge. If a term or contribution is clear only to the original paper's specialist audience, treat that as a self-contained exposition problem.

### 7. Adjudicate only after all reports are frozen

The chair first reads all independent reports and the reviewer-visible evidence packet. Only after preserving the independent verdicts may the chair read the author-side lane, then:

1. deduplicates findings without erasing reviewer disagreement;
2. verifies each `S0`/`S1` finding against the thesis and governing source;
3. rejects checklist-driven false positives and unsupported concerns;
4. preserves a single-reviewer severe finding when its reviewer-visible evidence is decisive;
5. records unresolved technical or policy disputes instead of averaging them away;
6. produces the combined risk decision and revision roadmap;
7. separates `W/E` remedies from the genuinely new `N` experiments or user-provided evidence;
8. lists strengths and contributions that survived all reviewer lenses;
9. records private-paper, repository, log, or author-declaration checks in a separate author-side provenance section and never attributes them to the blind panel.

Do not average reviewer scores unless the institution supplies a mandatory scoring form. If scores are required, preserve each score and the rule-based conclusion rather than substituting an ungrounded mean.

### 8. Direct-edit mode

Only enter this mode when the user asks for modification.

- Convert adjudicated findings into a versioned revision ledger.
- Apply the smallest change that resolves the evidence-backed issue.
- Use the author-side lane to recover existing values and align the thesis with the author's final papers, while keeping those repairs distinct from what the simulated blind panel independently observed.
- Preserve user data and unrelated changes.
- Recompile after LaTeX edits and inspect affected pages plus neighboring pages.
- Re-run numerical, cross-reference, citation, and float checks after each structural batch.
- After any citation, claim, related-work, bibliography, publication-status, dataset-source, or attribution edit, regenerate the full citation ledger and recheck every changed occurrence plus all repeated uses of the affected source.
- After any float, caption, heading, table, figure-size, barrier, or page-break edit, rebuild to a stable PDF, compare page count and affected label locations, inspect at least two neighboring physical pages on both sides, and rerun the whole-document page-layout ledger. A local improvement that creates a remote regression is not a fix.
- Do not use `[H]`, a barrier, a forced page break, or indiscriminate shrinking as the default pagination repair. First identify whether the failure is caused by float backlog, remaining-page height, source aspect ratio, caption length, or ordering. Preserve formal source figures and their semantic content.
- When a tall multi-panel figure must continue across pages, split only at a semantic boundary, retain one figure number with an explicit continuation, and compare both rendered parts against the original at legible scale. Never accept a split that crosses embedded text or visual content.
- Do not weaken accurate contributions merely to make the thesis sound cautious.
- Do not add fabricated experiments, data, citations, or institutional claims.

### 9. Independent re-review

For a revised thesis, freeze a new evidence packet and run a new panel round. Reviewers first inspect the revised thesis without reading the author response. They then receive the prior issue ledger and verify each item as:

- `resolved`;
- `partially resolved`;
- `unresolved`;
- `not reproducible in the new version`;
- `regressed elsewhere`.

The chair must report new defects introduced by revision. A high closure rate does not justify passing an unresolved `S0` or decisive `S1` issue.

When the user requests an iterative review--revision loop, start a newly frozen round after every revision batch. Stop only when all required independent reviewers return no actionable `S0`--`S3` finding, the page-layout ledger has no unresolved signal, the citation ledger has 100 percent coverage and no unresolved actionable mismatch, all prior findings are resolved or not reproducible, and the stable build introduces no regression. `S4` suggestions may remain explicitly optional and must not be described as defects. Never claim literal perfection; state the artifacts, checks, and limitations that bound the zero-actionable-finding result.

## Completion standard

A review is complete only when it includes:

- the frozen manifest and policy basis;
- the completed physical-page layout ledger and suspect-page dispositions;
- the completed full-text citation ledger, with occurrence/source counts and no silent unchecked rows;
- all independent reviewer reports required for the degree level;
- a chair synthesis with agreements and disagreements;
- a precise, prioritized revision ledger;
- a separate list of genuinely new experiments or missing user evidence;
- a statement of review limitations;
- an explicit statement of which artifacts were reviewer-visible and which were used only for author-side provenance or revision;
- for direct edits, compilation/render verification and a re-review result.

Do not claim that “all problems are solved” unless the re-review found no unresolved `S0`/`S1`, no material `S2` that contradicts a central claim, and no policy blocker.
