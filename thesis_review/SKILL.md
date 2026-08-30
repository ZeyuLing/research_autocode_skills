---
name: thesis-review
description: Review Chinese computer-science and AI master's or doctoral degree theses from one frozen rendered PDF through a clean-room packet builder, isolated holistic blind-review panels, explicit operational defense recommendations and skill-default A/B/C/D conclusions, institution-aware policy checks, citation verification against public authoritative sources, CS experiment and reproducibility auditing, narrative and contribution assessment, formatting QA, a separate non-attributional AI-style prose assessment, clean-room chair adjudication, traceable user-facing synthesis, revision planning, and independent re-review. Use for 学位论文盲审、博士论文外审、硕士论文预审、论文AI味判断、thesis review, dissertation review, full-thesis quality audits, blind-review risk assessment, or verification after thesis revisions. Default to five independent reviewers for doctoral theses and three for master's theses, plus one standalone AI-style assessor outside the panel.
---

# Chinese CS Thesis Review

## Purpose

Evaluate a degree thesis as a coherent long-form research contribution, not as a stack of conference-paper reviews. Use a frozen evidence packet, independent reviewer passes, a separate chair adjudication, and a separate user-facing synthesis, with every substantive stage started in a fresh context. Keep blind-review evidence separate from conversation history, author explanations, author-side provenance, and revision evidence. Report only evidence-backed findings with exact locations and feasible remedies.

This skill is read-only unless the user explicitly asks to revise the thesis. A request to review or diagnose does not authorize edits, fabricated data, new experiments, or changes to external systems.

## Required references

Read these files completely before starting a review:

- `references/clean-room-orchestration.md` for the mandatory fresh-context stage boundaries, exact input matrix, contamination recovery, clean chair, and clean user-facing summary.
- `references/china-policy.md` for the hierarchy of national law, post-award sampling, institutional rules, and current standards.
- `references/grading-and-verdicts.md` for mandatory explicit defense recommendations, the skill-default A/B/C/D grades, institutional overrides, and chair adjudication.
- `references/review-rubric.md` for the common and CS/AI checks.
- `references/reviewer-panels.md` for panel composition, isolation, and reviewer-specific mandates.
- `references/report-template.md` for report files and required fields.
- `references/ledger-validation.md` for deterministic CSV contracts, row-set reconciliation, and the mechanical bundle validator.
- `references/rendered-pagination-audit.md` for the mandatory physical-page ledger, PDF-visible pagination audit, and post-edit visual regression gate.
- `references/citation-audit.md` for the mandatory full-text citation-occurrence ledger, claim--source verification, and bibliography/status audit.
- `references/ai-style-audit.md` for the mandatory standalone AI-style prose assessment and its non-attribution boundary.

Use only the sections relevant to the degree type and thesis form. Mark inapplicable criteria as `N/A` with a reason; never turn every checklist item into a mandatory experiment.

## Non-negotiable distinctions

Keep these concepts separate in every report:

1. **Pre-defense thesis review** is governed primarily by the degree-granting institution's current rules.
2. **National post-award sampling** is a quality-monitoring process for already awarded theses; its reviewer count and fail logic are not automatically the school's pre-defense rules.
3. **Defense committee size** is not the same as the number of external or blind reviewers.
4. The default panel in this skill is an intentionally strict simulation: **five independent reviewers for a doctorate and three for a master's thesis**. Do not describe that default as a universal national statutory count.
5. Institutional templates and current school rules control local formatting. Use current national standards only as a fallback or cross-check, not to override a binding school template.
6. **Every R-numbered reviewer is a whole-thesis academic evaluator.** All reviewers assess significance, originality, technical correctness, evidence, thesis logic, integrity, writing, and rendered presentation. Personas change weighting, depth, and skepticism; they do not create exclusive scopes.
7. **Every R-numbered reviewer must issue one explicit operational defense conclusion.** Use the verified institutional category and wording when supplied; otherwise issue the A/B/C/D grade and paired Chinese recommendation in `references/grading-and-verdicts.md`. The standalone AI-style assessor is outside this grading system.

## Strict PDF-only and context-only blind-review boundary

An independent blind-review or fresh independent re-review round evaluates exactly one frozen rendered thesis PDF. The only additional inputs permitted are the closed neutral `00-process-parameters.json`; reviewer-visible manifests, inventories, and mechanical statistics derived solely from that same PDF; this skill's governing rule/template files; verified institutional rules; and public authoritative records opened only to verify citations already visible in that PDF. PDF-derived materials are navigation aids, not independent thesis evidence, and must identify the frozen PDF checksum from which they were generated. Follow the stage-by-stage allowlist in `references/clean-room-orchestration.md`; file isolation alone is insufficient when an actor inherits conversational context.

The packet builder, panel reviewers, AI-style assessor, and chair must not receive, recall, open, or search:

- conversation or thread history beyond a minimal operational prompt, including hidden memory or compaction summaries inherited from before the clean actor launch, prior assistant reasoning, previous answers, status reports, or problem tables; system-owned tool/environment metadata and same-clean-turn compaction are governed by the narrow exceptions in `references/clean-room-orchestration.md`, never permit inherited thesis assertions or old-task content, and permit current-round thesis assertions only when the actor newly derives them from allowlisted inputs during that same clean turn;
- user explanations, corrections, rebuttals, desired interpretations, claimed implementation facts, or statements about companion materials that are not visible in the frozen PDF;
- messages or artifacts from another current or completed actor unless the current stage's input matrix explicitly permits them;
- the LaTeX/DOCX source tree, `.bib` files, build logs, auxiliary files, comments, or inactive branches;
- Git history, old commits, diffs, blame output, tags, or prior artifact versions;
- sibling paper repositories, local paper drafts, supplements not included in the submitted PDF, code, configs, checkpoints, experiment logs, TODOs, or private data records;
- prior review rounds, old reviewer reports, old chair syntheses, old issue ledgers, source/provenance audits, author responses, or another reviewer's files before the current reports are frozen.

The orchestration process may compile the author's source to produce the requested PDF before freezing the round, then perform only Stage O mechanics: copy/hash the PDF into an identity-neutral round path, create empty paths, launch clean actors, check required files mechanically, and relay the clean Stage-S summary. Substantive actors receive the neutral frozen path, not an original workspace/repository path that may disclose identity. If the orchestrator has access to conversation history or author-side knowledge, it must not author the packet, reports, chair decision, revision ledger, or user-facing issue summary. Source paths, source lines, Git facts, and author-side comparisons must not appear in an independent reviewer finding or grade. A separately requested source-sync, provenance, implementation, or revision audit is a different task outside the blind-review round and must never be presented as reviewer evidence.

Every substantive actor must include exact `Actor ID`, `Review round ID`, and `Review retry ID`; a fresh-context declaration; and one mechanically structured input-receipt/access declaration with `received=[operational prompt]`, the actor's exact canonical ordered `opened=[...]` allowlist, and a permitted `public_endpoints=[...]` list, plus the three no-unlisted/no-prohibited/no-neighbor-enumeration confirmations inside that receipt field itself. `00-process-parameters.json` binds a distinct operational-prompt SHA-256 for P, every R actor, AI, C, and S, and contains V if and only if Stage V is run; each artifact's prompt hash must equal its actor entry. Stage O computes the hash from the exact prompt bytes before dispatch and launches those same bytes; artifact validation cannot independently observe task transport. Use a new empty-context process for Stage P, each helper, each reviewer, the AI assessor, the chair, the final summarizer, and optional Stage V; in Codex multi-agent execution this means `fork_turns: "none"`. Apply the contamination, retry, and quarantine rules in `references/clean-room-orchestration.md`. Labeling prohibited knowledge “author-side,” “already known,” or “only used in the summary” does not rescue the affected stage.

Absence of a training detail is not affirmative evidence of the opposite. In particular, a row reported as mean/standard-deviation does not prove that rows reported as point estimates were trained once. Unless the PDF explicitly states the repetition count for a configuration, write `the PDF does not state the repetition count for this configuration`; do not call it single-seed, single-run, or one training result, do not turn that unknown into a defect by itself, and do not use it to lower a grade.

## Workflow

### 1. Select the exact artifact and establish neutral process parameters

Identify, in this order:

- degree level: master's or doctorate;
- academic or professional degree;
- institution, school/department, discipline, and expected submission year;
- binding thesis template and review regulations, including revision dates;
- review target: the single rendered PDF explicitly selected by exact path and frozen by Stage O with SHA-256; never guess from modification time, filename, directory contents, or old conversation;
- user intent: initial review, direct revision, or re-review.

If no exact PDF has been selected or multiple candidate artifacts remain ambiguous, Stage O must obtain an explicit selection before launching Stage P. It does not pass the original identity-bearing path downstream. Record the closed neutral administrative fields in `00-process-parameters.json` exactly as defined in `references/clean-room-orchestration.md`; these fields are process parameters, not thesis evidence.

Search official sources when rules may have changed. Record the title, issuing body, revision/effective date, URL or local file, and the exact provision used. If current institutional rules cannot be verified, say so and label any older rule as historical rather than current.

### 2. Freeze one clean evidence packet

All reviewers must assess the same PDF bytes. Launch a fresh Stage-P packet builder with no inherited conversation or author-side knowledge. It creates a PDF-derived manifest containing:

- PDF path, checksum, exact `frozen_at` timestamp copied from the closed process envelope, and page count;
- chapter and section inventory;
- figure, table, equation, algorithm, appendix, and bibliography inventories;
- a checksum-bound candidate ledger for **every balanced square-bracket span containing at least one digit** found by the validator's deterministic page-by-page PDF extraction outside the independently derived rendered bibliography span, including multiline decimal intervals, vectors/arrays, indices, formulas, and genuine citations; assign continuous `BC0001...` IDs in physical-page/extraction order, preserve the validator's exact normalized extraction window, and classify every candidate from its exact PDF context as `citation` or `non-citation` before creating citation IDs;
- a checksum-bound `00-unmatched-bracket-ledger.csv` with one continuous `UBG0001...` row for every unmatched `[` or `]` glyph outside that bibliography span, including physical page, exact normalized extraction window, and a concrete visible-role disposition;
- every genuine in-text citation occurrence and displayed source in each cluster, including exact location and adjacent PDF text; only candidate-ledger rows classified as `citation` may receive continuous `C0001...` occurrence IDs, while mathematical intervals such as `t \in [0,1]` or `K \in [3,8]`, numeric vectors/arrays such as `[8,8,8,8,4]`, indices, and other non-citations remain explicitly recorded with `MappedOccurrenceID=N/A`; the citation-audit owner independently identifies the smallest attached proposition;
- an objective one-row-per-physical-page inventory and mechanical suspect-page signals; the page-audit owner independently supplies the visual disposition in `02-page-layout-ledger.md`;
- thesis-level scientific questions and claimed contributions exactly as explicitly stated in the PDF, with page anchors and without adjudication;
- the authored-prose corpus and exclusions used by the standalone AI-style assessor;
- objective chapter/section/figure/table/citation locations needed for navigation; each reviewer independently reconstructs chapter-to-question, method-to-experiment, and claim-to-evidence mappings;
- applicable institutional rules and standards;
- the permitted public citation-verification endpoints and an explicit list of all prohibited local artifact classes.

The packet must be neutral. It must not contain remembered issues, desired conclusions, novelty judgments, weakness labels, a consensus interpretation, or any substantive statement not traceable to the frozen PDF or governing rule. Bind `00-manifest.md` to the final `00-process-parameters.json` byte hash and exact deterministic envelope projections; retain exactly one reviewer-visible thesis PDF in the round root apart from explicitly hash-bound governing-rule PDFs; and use the closed manifest H1/H2/field schema in `references/report-template.md`. Record the packet builder's fresh-context and input-receipt/access declarations in `00-manifest.md` and `01-policy-basis.md`.

The candidate ledger is a completeness and disambiguation gate, not an optional scratch file. Stage P must retain all extracted candidates, preserve duplicate integers and expand one-to-four-digit pure-integer numeric ranges deterministically, use `ExpandedNumbers=N/A` for decimal/mixed/formula spans, store the canonical normalized marker, copy the deterministic normalized PDF context exactly without a second forgiving normalization, inspect each candidate in the rendered-PDF clause or table cell, and give a concrete classification reason. It must also preserve every unmatched `[` or `]` glyph in the required row-level sidecar and reconcile the exact row count in `00-manifest.md`, so a line-break/extraction artifact cannot silently hide a citation marker. The bibliography span is mechanically derived from the unique longest rendered `[1]...[N]` entry run, its length must equal the inventory, and its first page must contain the rendered `References`/`参考文献` heading; each `RenderedEntry` must equal the deterministic normalized raw slice between consecutive labels (or from the final label to the last bibliography-page end). Duplicate extracted entries and displayed citation numbers missing from that run remain visible as thesis defects for reviewer audit; Stage P must not suppress them or confuse them with packet-construction failures. A free-text page-region label or isolated body `[1]` cannot hide a body page. Do not infer that a bracket is a citation merely because all numbers fall within the bibliography range.

The closed extraction convention is algorithmic rather than visual. Page text is exactly `PdfReader(..., strict=False).pages[i].extract_text() or ""`; matching, page-local bracket pairing, ordering, and offsets operate on that raw string, and only a sliced window is normalized with `re.sub(r"\s+", " ", value).strip()` without Unicode normalization. Candidate spans are the nonempty nonnested `\[[^\[\]]+\]` matches containing a decimal digit, ordered by one-based physical page and raw start offset outside the derived bibliography span. Marker normalization removes whitespace, maps `，` to `,`, and maps `–`/`—` to `-`; candidate context includes the complete span plus up to 160 raw characters on each side. Pure one-to-four-digit integer/range markers use the exact no-space ASCII-semicolon-separated inclusive expansion, preserving order, descending ranges, and duplicates while rendering each value as an ordinary integer; every other numeric span uses exactly `N/A`. Unmatched glyphs come from a left-to-right LIFO page-level bracket scan, are ordered by page and raw offset, and use `text[max(0, offset-160):min(len(text), offset+161)]` before the same whitespace normalization. Citation-classified candidates alone receive continuous `Cnnnn` IDs; expanded element `n` at one-based source ordinal `k` creates the canonical Pair ID `Cnnnn-S{k:02d}`—two digits through `S99`, then ordinary wider decimal rendering through `S9999`—with `DisplayedReferenceID=REF{n:04d}`, the candidate physical page, and the same normalized context.

For Stage P only, the canonical `opened=[...]` receipt inserts `rules/scripts/validate_review_bundle.py` followed immediately by `rules/scripts/validate_stage_p_output.py` after the ten skill reference files and before process-ordered governing local files and the frozen PDF. Stage P has no helper inputs and must not probe `helpers/`, peer outputs, downstream outputs, old rounds, or neighboring paths. Before final freeze and exit, P must repeatedly run `python rules/scripts/validate_stage_p_output.py <exact-round-root>` without skipping, patching, mocking, replacing, or suppressing either validator until the process exits `0` and its first nonempty stdout line is exactly `PASS`. P may correct only its seven owned outputs and rerun the gate. If the gate identifies a process envelope, frozen PDF, governing input, or staged-rule defect, P stops and reports failure to Stage O for a clean retry. The scripts and their output are read-only mechanical rule infrastructure, never thesis/citation evidence or a source of findings; PASS does not replace packet-neutrality sign-off or the complete post-Stage-S validator. Any missing candidate or glyph, extra row, order/page/marker/context mismatch, contradictory unmatched disposition, citation/non-citation mapping mismatch, obvious mathematical false positive, invalid occurrence physical page, or disagreement between a citation candidate's expanded numbers and its citation-inventory source rows invalidates Stage P and requires a clean retry.

For LaTeX or DOCX, the orchestrator may compile or export the final artifact before the round. The blind-review packet then contains only the rendered PDF. Reviewers inspect the PDF itself for float placement, font size, overlap, blank pages, image resolution, cross-references, prose, equations, tables, bibliography, and visible experimental disclosure.

Do not silently replace the frozen thesis during the panel review. If the thesis changes, close the round and start a new versioned round.

#### Reviewer-visible evidence and separate non-review tasks

The reviewer-visible packet contains the neutral process envelope, frozen PDF, checksum-bound neutral inventories, governing skill/institutional rules, and public authoritative records opened only to verify citations visible in the PDF. No thesis source, uncited-literature search output, conversation material, or author-side artifact belongs to this packet.

If the user explicitly requests source synchronization, implementation verification, figure-origin comparison, or provenance tracing, finish or suspend the blind-review round and run that request as a separately labeled non-review task. Its output must live outside the blind-review bundle, must not be read by the reviewers or chair, and must not alter a blind-review grade. Start any later review from a newly frozen PDF.

#### Establish evidence authority before comparing artifacts

The following authority order applies only to a separately requested source audit or direct revision, never to the blind-review round. When companion materials disagree, record their role and authority before treating the disagreement as a non-review author-side issue. Unless the author identifies a different final source or a formal correction exists, use this order for reported methods and results:

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

In addition, run the standalone AI-style assessor defined in `references/ai-style-audit.md`. This assessor is not R6, does not participate in academic/defense grading, and must freeze `05-ai-style-assessment.md` without reading R1--R5, the chair synthesis, old rounds, or author-side material. Its task is to judge recurrent prose-style signals, not to infer AI use or authorship.

Before the AI assessor freezes or exits, it must run `python rules/scripts/validate_ai_output.py <exact-round-root>` in the same fresh turn until the command exits `0` and its first nonempty stdout line is `PASS`. It may correct only `05-ai-style-assessment.md`; an upstream identity/rule defect is returned to Stage O. The AI gate does not open reviewer, citation/bibliography/page, Chair, Stage-S, or old-round artifacts.

Every panel reviewer must apply the complete common rubric to the whole thesis before performing the persona-weighted deep dive. Every reviewer must disposition Gates A--I from `references/review-rubric.md`: policy/identity/integrity; thesis-level story; topic/literature/positioning; methods/reasoning; data/protocol; experiments/results; reproducibility/disclosed traceability; writing/self-contained exposition; and figures/tables/equations/citations/pages. A reviewer may express lower confidence outside their deepest expertise, but may not omit a gate or treat another reviewer as its sole academic owner.

Persona assignments determine where a reviewer spends additional effort and what kind of failure they are especially likely to detect. They do not allow a reviewer to grade only novelty, only experiments, only narrative, only citations, or only formatting. Exhaustive ledgers may have designated owners for workload control, but ledger ownership is separate from the obligation of every reviewer to form a comprehensive academic judgment; semantic citation support and visual page disposition remain expert judgments, not mechanical matches.

This PDF-only blind round does not search for uncited alternatives. R2 and Gate C assess novelty and literature positioning relative to the strongest works presented or cited in the frozen PDF, test whether absolute priority wording is supported by visible evidence, and disclose that exhaustive field-wide completeness is not verifiable under this boundary. A separate literature survey may be requested later, but it is not reviewer evidence and cannot rewrite the frozen grade.

Launch every reviewer in a separate fresh context with no inherited turns. They may receive only the exact Stage-R allowlist in `references/clean-room-orchestration.md` and must not enumerate neighboring rounds or read another reviewer's report before submitting their own. With limited concurrency, run reviewers in batches while preserving that isolation. Give each reviewer an exact output path and private scratch directory.

When fresh process isolation is unavailable, do not claim a complete independent blind review or issue an operational panel verdict. A clearly labeled non-independent diagnostic pass is permitted, but it cannot substitute for this skill's required panel. Never draft a consensus first and then ask reviewers to agree with it.

Each reviewer must:

- inspect the complete thesis, not only their specialty pages;
- complete all nine Gate A--I rows in the common whole-thesis assessment matrix from `references/report-template.md` before the persona-weighted deep review, with evidence anchors and no unjustified `N/A`;
- prioritize the assigned lens for extra depth without treating any other domain as outside scope;
- give every Gate A--I evidence cell, every finding `Location`, and every nonempty question `Exact PDF anchor` at least one in-range physical-page locator in the canonical form `physical p.<n>`, where `1 <= n <= physical_page_count`; logical page, section, table, figure, or equation detail may follow only as supplementary context, and a logical-only or source-line anchor never satisfies blind review;
- distinguish direct observation, inference, and unverified concern;
- test the thesis's strongest claims against its evidence;
- state what was checked and what could not be verified;
- issue an individual category, exact defense recommendation, decision regime/source, confidence, and rationale before seeing other reports; under the skill-default regime this is the required A/B/C/D pair;
- verify that the grade, recommendation, severities, and required revision path are mutually consistent before freezing the report.

For a doctoral thesis, citation auditing is split between two isolated owners. R5 owns the exhaustive bibliography-integrity audit and must write the Markdown summary plus long-form `03-bibliography-audit-ledger.csv`: every bibliography entry rendered in the PDF receives separate authoritative verdicts for type, title, complete ordered authorship, year, venue, publication/acceptance status, volume/issue, page/article number, DOI, arXiv ID/version, URL/access date, ISBN/other persistent ID, existence, and retraction/withdrawal/correction/superseding status. R4 owns the citation-claim audit and must write the Markdown summary plus `04-citation-claim-audit-ledger.csv`: every visible in-text citation occurrence and every displayed source in a citation cluster receives a unique Pair ID and is checked against the exact proposition it is asked to support using source content rather than metadata alone. A displayed citation with no rendered bibliography entry stays in `04` as `Support=unverifiable`, `MetadataStatus=mismatch`, `PublicIdentifier=no rendered bibliography entry`, blank source/locator, and an owning current finding/question link; it is never deleted or converted into a packet error. For a master's thesis, R3 owns both ledgers. Ownership is not optional and does not mean that other reviewers may ignore citation problems they encounter. R4 and R5 must not collaborate in a shared ledger or read each other's results before freezing their independent verdicts; the chair reconciles the two frozen ledgers afterward. A resolved citation marker, plausible title, metadata API match, keyword match, or sample of important references is not a substitute for either audit.

The R4/R5 ledger split is an exhaustive-work assignment, not a division of academic judgment. R4 must still assess contribution, methods, experiments, narrative, writing, and presentation; R5 must still assess significance, method intelligibility, evidential sufficiency, experimental interpretation, and thesis coherence. The same principle applies to every other persona. Mechanical helpers may create checksum-bound extraction/render/count sidecars under Stage H, but they never decide citation support, bibliography fields, page dispositions, findings, or grades; the owning reviewer independently signs every semantic and visual verdict.

### 4. Classify every finding

Use both severity and remedy class.

Severity:

- `S0` — a defect that invalidates the submitted artifact or creates a substantiated integrity/foundational blocker. Every `S0` must be subclassified as `procedural` (for example, a repairable blind-copy, identity-disclosure, or wrong-artifact failure without evidence of misconduct) or `integrity/foundational` (for example, fabricated evidence or citations, authorship/integrity misconduct, or foundational thesis invalidity). The subtype controls C versus D under the skill-default regime.
- `S1` — major scientific, logical, experimental, or structural defect that may lead to rejection or mandatory major revision.
- `S2` — substantive but repairable weakness that does not overturn the central contribution.
- `S3` — local writing, citation, formatting, numerical-labeling, or presentation defect.
- `S4` — optional refinement; never present it as required.

Remedy class:

- `W` — resolvable by writing, reorganization, citation repair, or formatting.
- `E` — resolvable if the author later supplies or recovers existing evidence in a separate revision task; the blind reviewers do not open local papers, repositories, logs, or data.
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
- exact internal agreement among the PDF's prose, tables, figures, captions, bibliography, and appendices; do not compare against companion papers or repositories during review;
- hyperparameters, software/hardware, preprocessing, and commands needed for reasonable reproduction;
- negative results, boundary conditions, or claim limits where omission would mislead;
- whether each chapter contributes to one thesis-level story rather than preserving the branding and framing of separate papers.

Multiple-seed coverage is not a universal acceptance requirement for deep-learning or foundation-model experiments. A targeted multi-seed diagnostic establishes robustness only for the configuration it actually repeats; it does not imply that every cell of a larger ablation matrix or every bidirectional main table must be rerun with the same number of seeds. Elevate seed coverage to a finding only when the thesis claims statistical significance or population-level stability, reports visibly unstable or contradictory runs, omits a material stochastic choice, or when plausible run-to-run variance could reverse a central comparison. Otherwise, record the diagnostic's scope as neutral context and do not penalize the thesis, lower the grade, or prescribe universal reruns.

When only one configuration visibly reports `mean ± dispersion`, the only permissible observation is that this configuration reports a multi-run or uncertainty summary if the PDF defines that notation. For every other configuration, the repeat count is `not stated in the PDF`. Point estimates do not establish single-run training, and unequal reporting formats do not establish unequal training counts.

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
- inspect visible pagination effects page by page; source-level forcing constructs and their causes are outside the blind-review packet and must be recorded as `not verifiable from the PDF` without suppressing a visible PDF finding;
- flag nearly blank pages, float-only pages, pages dominated by one figure or table, adjacent float stacks, anomalous bottom whitespace, clipped content, split captions, and a large float that prevents later prose from filling the current page;
- treat occupancy thresholds as triage signals, not automatic findings; close or retain each signal by visual evidence;
- for cropped or continued figures, verify visible seams, numbering, labels, and semantic continuity from the rendered parts; if completeness requires an unavailable original, state `not verifiable from the PDF`.

R5 owns only the doctoral exhaustive page-ledger deliverable and its 100-percent closure. Gate I remains a mandatory whole-thesis judgment domain for every reviewer, and every reviewer must report any visible page defect encountered. A statement such as “all pages viewed” is insufficient for the R5 ledger without the completed page rows and suspect-page dispositions.

Every reviewer has a mandatory read-only scoped gate before freeze and exit. Ordinary reviewers use `validate_reviewer_output.py`; doctoral R4 and R5 use their ledger-aware owner gates; master's R3 uses the combined page/bibliography/citation owner gate. The exact commands, actor-specific script insertions, and owned-output boundaries are closed in `references/ledger-validation.md` and `references/report-template.md`. A reviewer repeats its gate in the same fresh turn until exit `0` and first nonempty stdout `PASS`, correcting only its own current outputs. It must never edit the Stage-P packet, process envelope, frozen PDF, governing inputs, staged rules, or another actor's artifact. An upstream/frozen-input defect stops the actor and returns control to Stage O for a new global retry. Validator code and output are mechanical rule infrastructure, never thesis or citation evidence, and PASS never replaces semantic or visual sign-off.

For the doctoral bibliography/layout owner specifically, R5 may correct only its current `R5-comprehensive-review.md`, `02`, `03`, authorized page renders, and declarations inside those R5-owned Markdown artifacts before freeze. R5 must never edit the Stage-P packet, process envelope, frozen PDF, staged rules, or any other actor's output. If its gate identifies such an upstream defect, R5 must stop and report failure; Stage O treats it as a global-retry condition.

Apply the full protocol in `references/citation-audit.md` as two independent gates. For a doctorate, R5 must complete the field-by-field bibliography and existence audit, while R4 must complete the occurrence-by-occurrence claim--source audit; for a master's thesis, R3 completes both. Every mismatch, inaccessible field, ambiguous source, and unsupported occurrence must be recorded explicitly. Rendered-marker closure, an aggregate metadata match, or a spot check does not pass either gate. A substantiated fabricated or nonexistent citation is an `S0` integrity blocker.

Treat the ordinary author copy and the submitted blind-review copy as different artifacts. Do not report author, supervisor, institution, or student-number fields that correctly appear in an ordinary author copy as anonymity defects. When a blind-review copy is in scope, render or obtain that actual copy and scan the entire artifact--not only the cover--for identity disclosures in body text, captions, tables, acknowledgments, CV/publications, data and project descriptions, footnotes, URLs, PDF metadata, filenames, comments, and figure watermarks. Apply the institution's exact anonymization rules; in their absence, flag school, department, laboratory, company, employer, partner organization, and other wording that can directly or cumulatively identify the candidate.

The conservative format reviewer must be able to understand the thesis without relying on frontier-specific tacit knowledge. If a term or contribution is clear only to the original paper's specialist audience, treat that as a self-contained exposition problem.

### 7. Adjudicate in a clean chair context only after all reports are frozen

Launch the chair as a new Stage-C actor with no inherited conversation and no role in packet building or reviewing. The chair receives only the exact current-round allowlist in `references/clean-room-orchestration.md`, reads all frozen independent reports and the reviewer-visible PDF packet, and must not enumerate the parent review directory. The chair then:

1. preserves every reviewer's frozen category, defense recommendation, decision regime, and rationale, then deduplicates findings without erasing disagreement;
2. verifies each `S0`/`S1` finding against the thesis and governing source;
3. rejects checklist-driven false positives and unsupported concerns;
4. preserves a single-reviewer severe finding when its reviewer-visible evidence is decisive;
5. records unresolved technical or policy disputes instead of averaging them away;
6. produces a separate overall category, explicit defense recommendation, combined risk decision, and revision roadmap under the same decision regime using the adjudicated evidence;
7. separates `W/E` remedies from genuinely new `N` experiments or evidence unavailable in the submitted PDF;
8. lists strengths and contributions that survived all reviewer lenses;
9. records the exact permitted inputs it opened and invalidates the round if any prohibited local artifact was accessed.

The chair must also record a fresh-context declaration. It cannot use user explanations, rebuttal arguments, remembered implementation facts, prior summaries, or old review conclusions to accept or reject a finding. When permitted evidence is insufficient, use `not verifiable from the submitted PDF`. Every current reviewer `S0`--`S3` finding must enter exactly one chair disposition through a canonical duplicate-free `SourceReviewerFindingIDs` list; it may be verified, partially verified, rejected, deduplicated, disputed, or marked not verifiable, but may not disappear or be adjudicated twice. Rejected, disputed, and not-verifiable rows must also be preserved in the chair's disagreement table.

Before the Chair freezes or exits, it must run `python rules/scripts/validate_chair_output.py <exact-round-root>` until the first nonempty stdout line is `PASS` with exit `0`. This pre-Stage-S mode validates every frozen upstream artifact and all Chair-owned `90`--`92` outputs while forbidding `93`, `94`, and `95`; the Chair may correct only its own current outputs. Any upstream failure triggers Stage O's clean global retry rather than a downstream patch.

Keep the frozen AI-style judgment separate from the reviewer verdict distribution and academic/defense categories. The chair carries every unresolved `AI-Fxx` with impact `material` or `local` into a separate AI-actionable section and sidecar of the revision ledger, without assigning `S0--S4`, `W/E/N/P`, or changing the defense grade. It must repeat that this is not an AI-use, authorship, plagiarism, or misconduct determination. Optional AI findings remain separate and optional.

Before issuing the combined decision, the chair must join the frozen bibliography and citation-claim ledgers by stable rendered reference identity/displayed label and run a cross-ledger consistency gate. A cited reference whose title, ordered authors, persistent identifier, existence, or publication identity is `mismatch` in the bibliography ledger cannot remain `direct`, `partial`, or `context-only` in the citation-claim ledger without a separately identified correct source. Likewise, a citation-claim row whose opened source metadata does not identify the cited work is invalid even if its disposition is non-empty. Record every conflict and reclassify the affected pair conservatively. A **substantive** cross-ledger contradiction is one that changes source identity, existence, publication status material to the claim, or claim support; record it as at least `S2`, require a corrected frozen-round audit, and do not issue **A — 同意答辩** until it is closed. Assign B, C, or D according to the adjudicated severity and `references/grading-and-verdicts.md`. Pure punctuation, capitalization, abbreviation, or house-style differences that do not alter source identity or support are local `S3` items and do not by themselves fail the combined gate. Row counts and `pending=0` never override a substantive contradiction.

Under the skill-default regime, do not average A/B/C/D grades, convert them to points, or let a majority mechanically erase a decisive minority finding. Under an institutional regime, follow its verified aggregation rule. If the institution supplies a mandatory numeric scoring form, preserve each score and its rule-based conclusion rather than substituting an ungrounded mean.

### 8. Produce the clean user-facing summary

After the chair freezes `90-chair-synthesis.md`, `91-revision-ledger.md`, `91-revision-ledger.csv`, `91-ai-actionable-ledger.csv`, `92-new-evidence-or-experiments.md`, and `92-new-evidence-or-experiments.csv`, launch a new Stage-S summarizer with no inherited conversation. Stage S is part of this skill, not a later conversation-side summarization step. It receives only the exact current-round basename allowlist in `references/clean-room-orchestration.md` and writes `93-user-facing-summary.md` plus both lossless machine-readable current-action projections using `references/report-template.md`.

The summary is a traceable compression, not another adjudication. It must reproduce every individual and chair conclusion exactly, including each reviewer's decision regime/source, persona emphasis and whole-thesis rationale, the AI assessor's exact rationale, and the chair's decision regime/source and exact rationale; report the AI-style judgment separately; list exactly the current open adjudicated items in `91-revision-ledger.csv`; copy the chair's optional-suggestion and limitation sections without rephrasing; project every unresolved/not-verifiable/disputed Chair decision; project every current N-remedy evidence item; and bind every row to current finding IDs and exact PDF anchors. Every projected source field must occur exactly once under its documented `##` section; a duplicate authoritative section or duplicate same-named field inside it invalidates the bundle, and a lookalike label elsewhere cannot redirect the projection. Its H1 and nine H2 sections, nine identity bullets, canonical ordered input allowlist, table-only conclusion/current-item/unresolved sections, and fourteen reconciliation bullets are closed schemas: no extra section, reorder, duplicate basename, appendix, or stray prose is allowed. The actor table order is `R1...Rn, AI, Chair`; the academic, AI, and N rows preserve their authoritative source order; and the reconciliation `Statement` has the exact canonical non-invention value. The current academic and AI action CSVs are lossless open-row projections of their `91` masters, not abbreviated summaries. It must not introduce, omit, soften, escalate, or merge findings; write a new “decisive basis”; mention old resolved issues; or use user explanations, source-sync facts, repository knowledge, previous assistant summaries, or new web research. The validator must reconcile the complete actor table field-by-field, exact round/retry/prompt/input identity, every Markdown/CSV row set, issue counts, and current PDF identity before the summary can be relayed.

Before Stage S freezes or exits, it must run `python rules/scripts/validate_summary_output.py <exact-round-root>` until exit `0` and first nonempty stdout `PASS`, correcting only its three `93` outputs. This scoped gate never opens the frozen PDF, Stage-P packet, `02`--`04`, helpers, or prior rounds. After S freezes, Stage O—not S—runs the complete bundle validator and writes `95-bundle-validation.md`; only a complete PASS authorizes delivery.

For questions about the current PDF's independent blind review, relay the frozen current-round `93-user-facing-summary.md` rather than reconstructing an answer from conversation memory. For a longitudinal question such as whether prior items remain open or whether an iterative loop is finished, present current `93` and, if run, `94-post-freeze-prior-issue-closure.md` in two separate blocks without merging or re-adjudicating them. A conversation-aware orchestrator may add only a minimal operational wrapper and artifact links.

### 9. Direct-edit mode

Only enter this mode when the user asks for modification.

- Convert adjudicated findings into a versioned revision ledger.
- Apply the smallest change that resolves the evidence-backed issue.
- Direct editing is a separate author-side task. Source files and author-designated final papers may be used here to recover existing values and align the thesis, but those materials remain outside every blind-review report.
- Preserve user data and unrelated changes.
- Recompile after LaTeX edits and inspect affected pages plus neighboring pages.
- Re-run numerical, cross-reference, citation, and float checks after each structural batch.
- After any citation, claim, related-work, bibliography, publication-status, dataset-source, or attribution edit, freeze the new PDF, regenerate the affected bibliography and citation-claim ledgers from that PDF, and recheck every changed entry or occurrence plus all repeated uses of the affected source.
- After any float, caption, heading, table, figure-size, barrier, or page-break edit, rebuild to a stable PDF, compare page count and affected label locations, inspect at least two neighboring physical pages on both sides, and rerun the whole-document page-layout ledger. A local improvement that creates a remote regression is not a fix.
- Do not use `[H]`, a barrier, a forced page break, or indiscriminate shrinking as the default pagination repair. First identify whether the failure is caused by float backlog, remaining-page height, source aspect ratio, caption length, or ordering. Preserve formal source figures and their semantic content.
- When a tall multi-panel figure must continue across pages, split only at a semantic boundary, retain one figure number with an explicit continuation, and compare both rendered parts against the original at legible scale. Never accept a split that crosses embedded text or visual content.
- Do not weaken accurate contributions merely to make the thesis sound cautious.
- Do not add fabricated experiments, data, citations, or institutional claims.

### 10. Independent re-review

For a revised thesis, freeze a new PDF-only packet through a fresh Stage-P builder and run a **fresh independent re-review pass**. Reviewers inspect the revised PDF in new empty contexts without reading the conversation, author response, prior issue ledger, source tree, Git diff, old reports, or earlier summaries; they complete a fresh Gate A--I matrix and whole-thesis synthesis and record defects visible in the current PDF and findings newly discovered in this round. They must not call a defect a revision regression or say it was introduced by revision because they have no comparison baseline. Only after every fresh report, the clean chair decision, and the clean current-round summary are frozen may separately labeled Stage V compare the new PDF against specifically allowlisted prior artifacts. With only a prior issue ledger/author response, Stage V performs prior-finding closure and cannot infer global regression. A full longitudinal regression audit additionally requires the prior frozen PDF and prior page/bibliography/citation inventories and ledgers with hashes; a longitudinal style comparison additionally requires the specifically identified prior AI report. Stage V is not part of the independent re-review evidence packet and cannot retroactively alter its findings, grades, chair decision, ledgers, or clean current-round summary. It classifies prior items as:

- `resolved`;
- `unresolved`;
- `not verifiable`;
- `rejected`;
- `superseded by current finding`.

The clean chair reports current-round defects and current-round newly discovered findings only. Stage V may identify a demonstrated regression only when its full allowlisted prior baseline proves the comparison; otherwise introduction by revision is `not verifiable`. A high longitudinal closure rate does not justify passing an unresolved `S0` or decisive `S1` issue.

Each reviewer and the chair must issue a fresh category and defense recommendation for the newly frozen artifact under the round's decision regime. Do not mechanically carry forward or edit the previous round's conclusion.

When the user requests an iterative review--revision loop, start a newly frozen round after every revision batch. Stop only when all required independent reviewers return no actionable `S0`--`S3` finding, the page-layout ledger has no unresolved signal, both the bibliography and citation-claim ledgers have 100 percent coverage and no unresolved actionable mismatch, no `AI-Fxx` with `material` or `local` impact remains, and the post-freeze Stage-V check leaves no tracked prior finding `unresolved` or `not verifiable`. Claim that no longitudinal regression was introduced only when Stage V ran against the complete prior baseline; otherwise state that global regression was not assessed. `S4` and AI-optional suggestions may remain explicitly optional and must not be described as defects. Never claim literal perfection; state the artifacts, checks, and limitations that bound the zero-actionable-finding result.

Run a fresh isolated AI-style assessment on every revised frozen artifact. Do not show the assessor the previous report before it freezes its new judgment. Any unresolved `AI-Fxx` with `material` or `local` impact prevents a claim that final prose-polish review is complete, regardless of the overall signal label, but does not by itself alter the academic or integrity verdict.

## Completion standard

A review is complete only when it includes:

- the frozen manifest and policy basis;
- the completed Markdown and CSV physical-page layout ledgers and suspect-page dispositions, plus exactly one retained checksum-bound PNG in `page-renders/<PageID>.png` for every physical page;
- the completed Markdown and CSV bibliography-integrity and citation-claim ledgers, with deterministic entry/Pair IDs, reconciled counts, and no silent unchecked rows;
- all independent reviewer reports required for the degree level;
- a complete Gate A--I whole-thesis matrix, whole-thesis synthesis, and persona-weighted deep review in every R-numbered report; ledger ownership cannot substitute for any of them;
- one internally consistent category, exact defense recommendation, decision regime/source, confidence, and whole-thesis rationale in every R-numbered report; use A/B/C/D under the skill-default regime;
- the standalone `05-ai-style-assessment.md`, reported separately from R1--R5 and containing the non-attribution disclaimer;
- a chair synthesis with agreements and disagreements;
- a chair table preserving every independent category/recommendation and a separately reasoned overall category/recommendation, with no ungrounded averaging;
- a precise, prioritized academic revision ledger and a separate AI-actionable ledger, each with machine-readable sidecars;
- a separate list of genuinely new experiments or evidence unavailable from the submitted PDF;
- a statement of review limitations;
- an explicit statement that the reviewer-visible local artifact was exactly one frozen PDF, plus a list of permitted public citation-verification sources;
- a clean `93-user-facing-summary.md` that exactly reconciles with the current chair ledger and adds no finding or contextual claim;
- a fresh-context and input-receipt/access declaration from the packet builder, every helper, reviewer, assessor, chair, final summarizer, and the Stage-V verifier when Stage V is run, confirming that no prohibited context or artifact was used;
- a passing `95-bundle-validation.md` generated from `scripts/validate_review_bundle.py`, while preserving manual semantic sign-off;
- for direct edits, compilation/render verification and a re-review result.

Do not claim that “all problems are solved.” The strongest permitted completion statement is “the current frozen PDF has no actionable findings under the recorded checks,” and only when: every R report has no actionable `S0--S3`; the page ledger has `unchecked=0` and no unresolved signal; both citation ledgers have 100-percent reconciled coverage and no actionable mismatch or cross-ledger conflict; there is no policy blocker; and no `AI-Fxx` with `material` or `local` impact remains open. Optional `S4`/AI-optional suggestions and review limitations must still be disclosed.
