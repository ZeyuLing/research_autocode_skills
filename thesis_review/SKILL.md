---
name: thesis-review
description: Review Chinese computer-science and AI master's or doctoral degree theses from one frozen rendered PDF through a clean-room packet builder, isolated holistic blind-review panels, explicit operational defense recommendations and skill-default A/B/C/D conclusions, institution-aware policy checks, citation verification against public authoritative sources, CS experiment and reproducibility auditing, narrative and contribution assessment, formatting QA, a separate non-attributional AI-style prose assessment, clean-room chair adjudication, traceable user-facing synthesis, revision planning, and independent re-review. Use for 学位论文盲审、博士论文外审、硕士论文预审、论文AI味判断、thesis review, dissertation review, full-thesis quality audits, blind-review risk assessment, or verification after thesis revisions. Default to five independent reviewers for doctoral theses and three for master's theses, plus one standalone AI-style assessor outside the panel.
---

# Chinese CS Thesis Review

## Purpose

Evaluate a degree thesis as a coherent long-form research contribution, not as a stack of conference-paper reviews. Use a frozen evidence packet, independent reviewer passes, a separate chair adjudication, and a separate user-facing synthesis, with Stage O starting every substantive stage in a fresh context. Keep blind-review evidence separate from conversation history, author explanations, author-side provenance, and revision evidence. Report only evidence-backed findings with exact locations and feasible remedies.

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

PDF-only also constrains what the review may demand. The default object of judgment and correction is the rendered thesis itself: its method description, experimental protocol, internal consistency, claim--evidence relation, citations, and presentation. The absence of author-side code, commits, environment locks, full command lines, checkpoint/model-file hashes, sample/member IDs or hashes, immutable manifests, controlled audit packages, internal logs, table-generation scripts, or raw confidential data is not by itself a finding, an unresolved question, a reproducibility defect, or a reason to lower the grade. Do not request such material unless a verified governing rule makes it a formal submission component, or the PDF explicitly claims an exact public artifact/replay whose identity is necessary to decide a central claim. Even then, require the least disclosure that can appear in the revised PDF or a verified formal submission attachment. Ordinary scientific concerns about private data, duplication, leakage, configuration, or result credibility must be decided from PDF-visible definitions, protocols, numbers, and contradictions; resolve them through natural clarification, claim narrowing, or genuinely needed new evidence rather than a forensic artifact package.

The packet builder, panel reviewers, AI-style assessor, independent semantic
acceptors, and chair must not receive, recall, open, or search:

- conversation or thread history beyond a minimal operational prompt, including hidden memory or compaction summaries inherited from before the clean actor launch, prior assistant reasoning, previous answers, status reports, or problem tables; system-owned tool/environment metadata and same-clean-turn compaction are governed by the narrow exceptions in `references/clean-room-orchestration.md`, never permit inherited thesis assertions or old-task content, and permit current-round thesis assertions only when the actor newly derives them from allowlisted inputs during that same clean turn;
- user explanations, corrections, rebuttals, desired interpretations, claimed implementation facts, or statements about companion materials that are not visible in the frozen PDF;
- messages or artifacts from another current or completed actor unless the current stage's input matrix explicitly permits them;
- the LaTeX/DOCX source tree, `.bib` files, build logs, auxiliary files, comments, or inactive branches;
- Git history, old commits, diffs, blame output, tags, or prior artifact versions;
- sibling paper repositories, local paper drafts, supplements not included in the submitted PDF, code, configs, checkpoints, experiment logs, TODOs, or private data records;
- prior review rounds, old reviewer reports, old chair syntheses, old issue ledgers, source/provenance audits, author responses, or another reviewer's files before the current reports are frozen.

The orchestration process may compile the author's source to produce the requested PDF before freezing the round, then perform only Stage O mechanics: copy/hash the PDF into an identity-neutral round path, create empty paths, launch clean actors, check required files mechanically, and relay the clean Stage-S summary. Substantive actors receive the neutral frozen path, not an original workspace/repository path that may disclose identity. If the orchestrator has access to conversation history or author-side knowledge, it must not author the packet, reports, chair decision, revision ledger, or user-facing issue summary. Source paths, source lines, Git facts, and author-side comparisons must not appear in an independent reviewer finding or grade. A separately requested source-sync, provenance, implementation, or revision audit is a different task outside the blind-review round and must never be presented as reviewer evidence.

Every substantive actor must include exact `Actor ID`, `Review round ID`, and `Review retry ID`; a fresh-context declaration; and one mechanically structured input-receipt/access declaration with `received=[operational prompt]`, the actor's exact canonical ordered `opened=[...]` allowlist, and a permitted `public_endpoints=[...]` list, plus the three no-unlisted/no-prohibited/no-neighbor-enumeration confirmations inside that receipt field itself. `00-process-parameters.json` binds a distinct operational-prompt SHA-256 for P, every degree-required R actor, AI, every corresponding `SA-Rn` plus `SA-AI`, C, and S; the current production runner rejects H and V. Each artifact's prompt hash must equal its actor entry. Stage O computes the hash from the exact prompt bytes before dispatch and launches those same bytes in a new ephemeral process; artifact validation alone cannot observe task transport. The launched process itself is the bound actor and must not create another actor. Every operational prompt must explicitly forbid every collaboration API and Codex task/thread API listed by the canonical contract in `scripts/actor_prompt_contract.py`; creating, forking, messaging, handing off, continuing, waiting on, inspecting, listing, opening, sharing, mutating, or activating another task/thread or actor; starting another model process through a shell; and relaying the prompt, assigned role, summaries, extracted content, or derived instructions to another actor/model/process. Any attempted re-delegation is an actor-transport failure and requires whole-retry quarantine. Apply the remaining contamination, retry, and quarantine rules in `references/clean-room-orchestration.md`. Labeling prohibited knowledge “author-side,” “already known,” or “only used in the summary” does not rescue the affected stage.

Stage O must use `scripts/build_reviewer_prompt.py` for every R actor, `scripts/build_semantic_acceptance_prompt.py` for every SA actor, and `scripts/build_canonical_actor_prompt.py` for P, AI, C, and S. The canonical builder accepts no role body or helper input: it deterministically derives the complete actor prompt from the stable process projection, the exact future private view, fixed actor outputs, fixed scoped gates, bound Python, and bound empty scratch. Stage O plans every prompt before process sealing, retains each returned prompt and receipt outside the run, then invokes the matching builder's `verify` mode against the sealed process and staged exact private view immediately before dispatch. A handwritten prompt, free-form role body, H/V actor, post-plan edit, or bypass of the applicable builder is invalid in production runner v1. `scripts/build_bound_actor_prompt.py` is retained only as a non-production compatibility helper and cannot authorize a review round.

Stage O must use the checked-in production mechanics rather than an ad-hoc shell launch. After one fresh run has been initialized, all canonical prompts have been planned, and the final process has been sealed, `scripts/stage_o_runner.py` is the only production entry point: its append-only event chain and compare-and-swap transition token enforce the fixed P -> R/AI -> SA -> C -> S lifecycle, bind every prelaunch anchor, reject an incomplete or out-of-order operation, and quarantine the complete retry after any begun operation fails. P, C, and S are singleton phases; all degree-required R actors and AI form one phase whose launches use `launch-phase` concurrently, and all target-specific SA actors form the next concurrently launched phase. Phase promotion and the SA aggregate gate remain deterministic barriers. `scripts/manage_stage_o_workspace.py`, `scripts/launch_review_actor.py`, and the prompt builders are internal primitives called under that runner; direct primitive success never authorizes delivery. The workspace manager exclusively creates scratch, stages transient rule inputs and exact actor-private views, retains each returned input commitment outside the actor view and finalized round, promotes only the closed actor-owned output set with no replacement, and recoverably retires transient round rules. The launcher preallocates its canonical UUID, supplies a private scratch `--cwd` distinct from the actor `--workspace`, and treats any nonzero launcher/transport result as a whole-retry quarantine condition. These mechanics are process controls, never thesis evidence.

For Codex CLI execution, the accepted launch argv is a closed grammar:

```text
<absolute-codex-executable> [--search] exec <closed-exec-items-in-any-order> -
```

`<closed-exec-items-in-any-order>` contains exactly once each of `--json`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, and `--approve-for-me`; exactly one `-C <actor-workspace>` pair; exactly one of `--disable multi_agent`, `--disable=multi_agent`, or `-c features.multi_agent=false`; and, optionally, at most once `--skip-git-repo-check`. In this Codex CLI, `--approve-for-me` supplies the workspace-write sandbox itself and must not be combined with `--sandbox`, `--sandbox=...`, or `-s`; this preserves workspace-write isolation while avoiding the CLI's mutually exclusive flag error. `--dangerously-bypass-approvals-and-sandbox` and every other sandbox/approval bypass remain forbidden. If present, the sole `--search` occurs before `exec`. The sole stdin marker `-` is last. No other flag, configuration override, positional argument, subcommand, model/profile/image/add-directory option, or second `exec` is permitted.

Stage O retains the complete JSONL and one schema-`thesis-review-actor-launch-v3` launcher record outside the review bundle. Before dispatch it fixes a unique launch UUID together with the prompt, sealed-process, process-seal, exact input-commitment, executable, argv, workspace, and scratch anchors; it must never mint replacement anchors around an existing log. The completed record has the validator's closed field set and additionally binds the terminal actor-output commitment, launcher-declared PID, process exit code, log path/bytes/hash, and emitted thread ID. The runner retains both the completed launch-record SHA-256 and terminal output commitment before promotion. After exit, `scripts/validate_actor_transport.py` must return `PASS` with the exact `--log`, `--actor`, `--launch-record`, `--expected-prompt-sha256`, `--expected-launch-id`, `--expected-process-sha256`, `--expected-process-seal-sha256`, `--expected-input-commitment-sha256`, `--expected-output-commitment-sha256`, and `--expected-launch-record-sha256` arguments. It requires exit code zero, the closed current JSONL schema, coherent item lifecycles, and one successful terminal turn; only its closed, ordered WebSocket-reconnect-to-HTTPS-fallback sequence may be treated as recovered transport rather than a failure. It rejects every unknown, malformed, or truncated event; every unrecovered top-level stream/turn or error-item event; binding drift relative to the externally retained anchors; any collaboration/task/thread event; and any recognized nested model-process command even when no child output was produced. A terminal failed command or MCP item may remain in the log only when its schema and lifecycle are complete, the actor handles it locally, and the overall turn later succeeds; this never excuses a prohibited delegation or nested-model attempt. The launcher holds deny-write/delete read leases on every declared actor input on the supported Windows runner from the final prelaunch recheck through actor exit, and requires the private scratch to be exactly empty before launch, after actor exit, and after transport validation. `workspace-write` is not represented as an operating-system read-capability boundary: the no-unlisted-input rule, exact private view, canonical prompt, immutable input leases, and transport evidence form the stated non-adversarial process boundary. UUID and PID remain launcher-owned declarations, and a malicious same-user supervisor that rewrites the fixed toolchain is outside the trust model. These controls are never thesis evidence. If another launcher cannot establish an equivalent boundary, a complete independent round is unavailable on that transport and must not be claimed.

This transport validator is not an independent operating-system attestor; its
stated trust boundary and limitations are part of the review record, not thesis
evidence.

The canonical internal launcher invocation is `"<absolute-bundled-python>" -B scripts/launch_review_actor.py --actor <actor-id> --launch-id <preallocated-canonical-uuid> --prompt <absolute-external-prompt> --expected-prompt-sha256 <64-hex> --expected-process-sha256 <64-hex> --expected-process-seal-sha256 <64-hex> --expected-input-commitment-sha256 <64-hex> --workspace <absolute-private-actor-view> --cwd <absolute-private-scratch> --jsonl <absolute-external-jsonl> --stderr <absolute-external-stderr> --launch-record <absolute-external-record> --codex-executable <absolute-codex-executable> [--search]`. It always invokes Codex with exactly one `--approve-for-me`, which supplies its workspace-write sandbox, together with `--ignore-user-config`, `--ignore-rules`, ephemeral JSONL mode, and multi-agent disabled; it never also passes an explicit sandbox option and exposes no sandbox-bypass option. The launcher opens the Codex process without sending stdin, durably writes the PID-bound pending record in the same file that will hold the completed record, acquires and verifies immutable input leases, rechecks prompt/executable/input identity and bytes, then sends the exact prompt bytes. It completes that same record after exit, freezes the terminal output commitment and record hash, and runs the transport gate itself. Reconstructing a record after prompt consumption or around a pre-existing log is invalid.

After dispatch, Stage O must not send that actor a progress request, correction,
status prompt, or any other follow-up message. It may observe task state and
filesystem topology mechanically without messaging the actor. A needed
post-launch instruction proves that the frozen operational prompt was
insufficient and requires quarantine plus a complete clean retry. Every actor's
initial frozen prompt must require the bundled Python to run with bytecode
writing disabled (`-B` and/or `PYTHONDONTWRITEBYTECODE=1`); no `__pycache__` or
`.pyc` entry may remain in an isolated view at freeze.

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

All reviewers must assess the same PDF bytes. Stage O launches a fresh Stage-P packet builder with no inherited conversation or author-side knowledge. The packet builder creates a PDF-derived manifest containing:

- PDF path, checksum, exact `frozen_at` timestamp copied from the closed process envelope, and page count;
- chapter inventory and an exact PDF-derived numbered body-section map; section
  labels, order, and physical pages must match rendered chapter-region headings,
  while TOC/list entries, table or metric decimals, equations, references, and
  appendix labels remain excluded;
- figure, table, equation, algorithm, appendix, and bibliography inventories;
- a checksum-bound candidate ledger for **every balanced square-bracket span containing at least one digit** found by the validator's deterministic page-by-page PDF extraction outside the independently derived rendered bibliography span, including multiline decimal intervals, vectors/arrays, indices, formulas, and genuine citations; assign continuous `BC0001...` IDs in physical-page/extraction order, preserve the validator's exact normalized extraction window, and classify every candidate from its exact PDF context as `citation` or `non-citation` before creating citation IDs;
- a checksum-bound `00-unmatched-bracket-ledger.csv` with one continuous `UBG0001...` row for every unmatched `[` or `]` glyph outside that bibliography span, including physical page, exact normalized extraction window, and a concrete visible-role disposition. When the frozen syntax deterministically identifies the square endpoint of `[a,b)` or `(a,b]`, `Disposition` is exactly `visible-role:half-open-mathematical-interval`; a free-form alternative such as “equation delimiter” is invalid;
- every genuine in-text citation occurrence and displayed source in each cluster, including exact location and adjacent PDF text; only candidate-ledger rows classified as `citation` may receive continuous `C0001...` occurrence IDs, while mathematical intervals such as `t \in [0,1]` or `K \in [3,8]`, numeric vectors/arrays such as `[8,8,8,8,4]`, indices, and other non-citations remain explicitly recorded with `MappedOccurrenceID=N/A`; the citation-audit owner independently identifies the smallest attached proposition;
- an objective one-row-per-physical-page inventory and mechanical suspect-page signals; the page-audit owner independently supplies the visual disposition in `02-page-layout-ledger.md`;
- thesis-level scientific questions and claimed contributions exactly as explicitly stated in the PDF, with page anchors and without adjudication;
- the authored-prose corpus, beginning with any rendered preface/序言/前言 and continuing through both abstracts, chapters, substantive appendix prose, and substantive explanatory/contribution prose anywhere in front/back matter, plus span-level exclusions for the standalone AI-style assessor; CV metadata never excludes other authored prose on the same page, and every physical page remains subject to inspection;
- objective chapter/section/figure/table/citation locations needed for navigation; each reviewer independently reconstructs chapter-to-question, method-to-experiment, and claim-to-evidence mappings;
- applicable institutional rules and standards;
- the permitted public citation-verification endpoints and an explicit list of all prohibited local artifact classes.

The packet must be neutral. It must not contain remembered issues, desired conclusions, novelty judgments, weakness labels, a consensus interpretation, or any substantive statement not traceable to the frozen PDF or governing rule. `00-page-inventory.csv` Region values are mechanically bound to PDF-derived boundaries: strong independent one-line or cross-line page-top Chinese/English chapter headings, the unique rendered bibliography run, and independent appendix/back-matter headings. TOC/list entries and sentence-like prose references to another chapter do not establish a boundary. Descriptive class prefixes such as `chapter — methods` and `body — results` are permitted; `separator`/`boundary` is permitted only on a substantively empty rendered page after repeated page furniture and a standalone page number are removed; and an explicit chapter number must agree on every page with the detected rendered chapter. Bind `00-manifest.md` to the final `00-process-parameters.json` byte hash and exact deterministic envelope projections; retain exactly one reviewer-visible thesis PDF in the round root apart from explicitly hash-bound governing-rule PDFs; and use the closed manifest H1/H2/field schema in `references/report-template.md`. Record the packet builder's fresh-context and input-receipt/access declarations in `00-manifest.md` and `01-policy-basis.md`.

The candidate ledger is a completeness and disambiguation gate, not an optional scratch file. Stage P must retain all extracted candidates, preserve duplicate integers and expand one-to-four-digit pure-integer numeric ranges deterministically, use `ExpandedNumbers=N/A` for decimal/mixed/formula spans, store the canonical normalized marker, copy the deterministic normalized PDF context exactly without a second forgiving normalization, and inspect each candidate in the rendered-PDF clause or table cell. Every `non-citation` row must carry the exact validator-derived `non-citation-role:<canonical-role>` token defined in `references/ledger-validation.md`; free-form explanations, model/data keywords, an in-range number, zero, or duplicate integer cannot suppress a source marker. If a legitimate non-citation does not match the closed frozen-context grammar, Stage P stops for a clean retry after the shared predicate and regression tests are extended rather than guessing or forcing it into either class. It must also preserve every unmatched `[` or `]` glyph in the required row-level sidecar and reconcile the exact row count in `00-manifest.md`, so a line-break/extraction artifact cannot silently hide a citation marker. The bibliography span is mechanically derived from the unique longest rendered `[1]...[N]` entry run, its length must equal the inventory, and its first page must contain the rendered `References`/`参考文献` heading; each `RenderedEntry` must equal the deterministic normalized raw slice between consecutive labels (or from the final label to the last bibliography-page end). Duplicate extracted entries and displayed citation numbers missing from that run remain visible as thesis defects for reviewer audit; Stage P must not suppress them or confuse them with packet-construction failures. A free-text page-region label or isolated body `[1]` cannot hide a body page. Do not infer that a bracket is a citation merely because all numbers fall within the bibliography range.

The closed extraction convention is algorithmic rather than visual. Stage P and every later PDF-reading or PDF-derived-packet scoped/full gate in one round must run through the same bundled workspace Python; do not use an unpinned `uv --with pypdf` or an ad-hoc interpreter. Stage P writes `PDF extraction runtime: pypdf=<pypdf.__version__>` into the canonical manifest, and every such gate rejects a runtime-version mismatch; the deterministic Stage-S projection does not read the PDF or manifest and therefore does not import an extractor. A bundled-runtime upgrade requires a newly generated packet rather than revalidating old extracted rows under new semantics. Page text is exactly `PdfReader(..., strict=False).pages[i].extract_text() or ""`; matching, page-local bracket pairing, ordering, and offsets operate on that raw string, and only a sliced window is normalized with `re.sub(r"\s+", " ", value).strip()` without Unicode normalization. Before square-span matching, the extractor deterministically recognizes high-confidence `[a,b)` and `(a,b]` mixed-delimiter intervals, emits their square endpoints as visible-role glyphs, and removes those offsets from both candidate-span matching and the ordinary square-bracket stack. Candidate spans are then the nonempty nonnested `\[[^\[\]]+\]` matches containing a decimal digit whose start/end square offsets were not removed, ordered by one-based physical page and raw start offset outside the derived bibliography span. Marker normalization removes whitespace, maps `，` to `,`, and maps `–`/`—` to `-`; candidate context includes the complete span plus up to 160 raw characters on each side. Pure one-to-four-digit integer/range markers use the exact no-space ASCII-semicolon-separated inclusive expansion, preserving order, descending ranges, and duplicates while rendering each value as an ordinary integer; every other numeric span uses exactly `N/A`. After direct interval endpoints are recorded, unmatched ordinary square glyphs come from a left-to-right LIFO page-level scan of the remaining offsets; both classes are merged in page/raw-offset order and use `text[max(0, offset-160):min(len(text), offset+161)]` before the same whitespace normalization. Citation-classified candidates alone receive continuous `Cnnnn` IDs; expanded element `n` at one-based source ordinal `k` creates the canonical Pair ID `Cnnnn-S{k:02d}`—two digits through `S99`, then ordinary wider decimal rendering through `S9999`—with `DisplayedReferenceID=REF{n:04d}`, the candidate physical page, and the same normalized context.

For Stage P only, the canonical `opened=[...]` receipt inserts `rules/scripts/validate_review_bundle.py` followed immediately by `rules/scripts/validate_stage_p_output.py` after the ten skill reference files and before process-ordered governing local files and the frozen PDF. Stage P has no helper inputs and must not probe `helpers/`, peer outputs, downstream outputs, old rounds, or neighboring paths. Before final freeze and exit, P must repeatedly run `python rules/scripts/validate_stage_p_output.py <exact-stage-p-view-root>` without skipping, patching, mocking, replacing, or suppressing either validator until the process exits `0` and its first nonempty stdout line is exactly `PASS`. P may correct only its seven owned outputs and rerun the gate. If the gate identifies a process envelope, frozen PDF, governing input, or staged-rule defect, P stops and reports failure to Stage O for a clean retry. The scripts and their output are read-only mechanical rule infrastructure, never thesis/citation evidence or a source of findings; PASS does not replace packet-neutrality sign-off or the complete post-Stage-S validator. Any missing candidate or glyph, extra row, order/page/marker/context mismatch, contradictory unmatched disposition, citation/non-citation mapping mismatch, obvious mathematical false positive, invalid occurrence physical page, or disagreement between a citation candidate's expanded numbers and its citation-inventory source rows invalidates Stage P and requires a clean retry.

For LaTeX or DOCX, the orchestrator may compile or export the final artifact before the round. The blind-review packet then contains only the rendered PDF. Reviewers inspect the PDF itself for float placement, font size, overlap, blank pages, image resolution, cross-references, prose, equations, tables, bibliography, and visible experimental disclosure.

Do not silently replace the frozen thesis during the panel review. If the thesis changes, Stage O closes the round and starts a new versioned round.

#### Reviewer-visible evidence and separate non-review tasks

The reviewer-visible packet contains the neutral process envelope, frozen PDF, checksum-bound neutral inventories, governing skill/institutional rules, and public authoritative records opened only to verify citations visible in the PDF. No thesis source, uncited-literature search output, conversation material, or author-side artifact belongs to this packet.

If the user explicitly requests source synchronization, implementation verification, figure-origin comparison, or provenance tracing, Stage O finishes or suspends the blind-review round and runs that request as a separately labeled non-review task. Its output must live outside the blind-review bundle, must not be read by the reviewers or chair, and must not alter a blind-review grade. Stage O starts any later review from a newly frozen PDF.

#### Establish evidence authority before comparing artifacts

The following authority order applies only to a separately requested source audit or direct revision, never to the blind-review round. When companion materials disagree, record their role and authority before treating the disagreement as a non-review author-side issue. Unless the author identifies a different final source or a formal correction exists, use this order for reported methods and results:

1. the final published or submitted paper, its supplementary material, and the formal figure/table sources used to build that version;
2. an official erratum, author-designated revision, or released artifact explicitly tied to that paper version;
3. thesis-specific experiment records explicitly designated as final;
4. versioned code, configuration, logs, and evaluation outputs;
5. development notes, TODO lists, experiment plans, debug reports, scratch analyses, and abandoned drafts.

Items in the fifth class describe work in progress. They must not overturn a formal paper result, create a checkpoint inconsistency, or become the sole basis for an `S0`/`S1` finding unless the paper, a formal correction, or the author explicitly promotes them to the final source of truth. If lower-authority artifacts disagree with the final paper, first determine whether they are obsolete, diagnostic, or from a different protocol. Preserve unresolved cases as questions rather than alleging selection bias, leakage, or result conflict without affirmative evidence.

The user's explicit declaration of the intended source of truth controls among supplied research artifacts unless a formal correction or direct integrity evidence contradicts it. The PDF-only submission-obligation boundary above remains in force during every later review: a separately requested source audit may help the author revise the PDF, but it cannot convert raw member hashes, immutable manifests, generic near-duplicate audits, or other author-side artifacts into universal thesis evidence.

### 3. Independent reviewer panel

The panel defined in `references/reviewer-panels.md` consists of:

- doctorate: R1--R5;
- master's: R1--R3.

In addition, Stage O launches the standalone AI-style assessor defined in `references/ai-style-audit.md`. This assessor is not R6, does not participate in academic/defense grading, and must freeze `05-ai-style-assessment.md` without reading R1--R5, the chair synthesis, old rounds, or author-side material. Its task is to judge recurrent prose-style signals, not to infer AI use or authorship.

Before the AI assessor freezes or exits, it must run `python rules/scripts/validate_ai_output.py <exact-stage-ai-view-root>` in the same fresh turn until the command exits `0` and its first nonempty stdout line is `PASS`. It may correct only `05-ai-style-assessment.md`; an upstream identity/rule defect is returned to Stage O. The AI gate does not open reviewer, citation/bibliography/page, Chair, Stage-S, or old-round artifacts.

Every panel reviewer must apply the complete common rubric to the whole thesis before performing the persona-weighted deep dive. Every reviewer must disposition Gates A--I from `references/review-rubric.md`: policy/identity/integrity; thesis-level story; topic/literature/positioning; methods/reasoning; data/protocol; experiments/results; reproducibility/disclosed traceability; writing/self-contained exposition; and figures/tables/equations/citations/pages. A reviewer may express lower confidence outside their deepest expertise, but may not omit a gate or treat another reviewer as its sole academic owner.

Persona assignments determine where a reviewer spends additional effort and what kind of failure they are especially likely to detect. They do not allow a reviewer to grade only novelty, only experiments, only narrative, only citations, or only formatting. Exhaustive ledgers may have designated owners for workload control, but ledger ownership is separate from the obligation of every reviewer to form a comprehensive academic judgment; semantic citation support and visual page disposition remain expert judgments, not mechanical matches.

This PDF-only blind round does not search for uncited alternatives. R2 and Gate C assess novelty and literature positioning relative to the strongest works presented or cited in the frozen PDF, test whether absolute priority wording is supported by visible evidence, and disclose that exhaustive field-wide completeness is not verifiable under this boundary. A separate literature survey may be requested later, but it is not reviewer evidence and cannot rewrite the frozen grade.

Stage O launches every reviewer in a separate fresh context with no inherited turns. Reviewers may receive only the exact Stage-R allowlist in `references/clean-room-orchestration.md` and must not enumerate neighboring rounds or read another reviewer's report before submitting their own. With limited concurrency, Stage O runs reviewers in batches while preserving that isolation and gives each reviewer an exact output path and private scratch directory.

When fresh process isolation is unavailable, do not claim a complete independent blind review or issue an operational panel verdict. A clearly labeled non-independent diagnostic pass is permitted, but it cannot substitute for this skill's required panel. Never draft a consensus first and then ask reviewers to agree with it.

Each reviewer must:

- inspect the complete thesis, not only their specialty pages;
- complete all nine Gate A--I rows in the common whole-thesis assessment matrix from `references/report-template.md` before the persona-weighted deep review, with evidence anchors and no unjustified `N/A`;
- prioritize the assigned lens for extra depth without treating any other domain as outside scope;
- give every Gate A--I evidence cell, every finding `Location`, and every nonempty question `Exact PDF anchor` at least one in-range physical-page locator in the canonical form `physical p.<n>`, where `1 <= n <= physical_page_count`; logical page, section, table, figure, or equation detail may follow only as supplementary context, and a logical-only or source-line anchor never satisfies blind review;
- distinguish direct observation, inference, and unverified concern;
- test the thesis's strongest claims against its evidence;
- before freezing any finding, search the whole frozen PDF for the allegedly missing definition, qualification, disclosure, or other thesis-visible remedy; omit a finding whose required substance is already present, and when a local inconsistency remains, anchor and remedy only that residual inconsistency;
- reconcile Gate A--I and every `S0`--`S3` finding bidirectionally: each actionable finding's Primary and Secondary gates are `concern` rows that cite it, every `concern` cites at least one actionable finding mapped back to that Gate, and every non-`concern` row (`adequate`, `unverifiable`, or `N/A`) cites no actionable `S0`--`S3` item; optional `S4` items may remain informational and do not force `concern`;
- state what was checked and what could not be verified;
- issue an individual category, exact defense recommendation, decision regime/source, confidence, and rationale before seeing other reports; under the skill-default regime this is the required A/B/C/D pair;
- verify that the grade, recommendation, severities, and required revision path are mutually consistent before freezing the report.

For a doctoral thesis, citation auditing is split between two isolated owners. R5 owns the exhaustive bibliography-integrity audit and must write the Markdown summary plus long-form `03-bibliography-audit-ledger.csv`: every bibliography entry rendered in the PDF receives separate authoritative verdicts for type, title, complete ordered authorship, year, venue, publication/acceptance status, volume/issue, page/article number, DOI, arXiv ID/version, URL/access-date applicability under the binding style, ISBN/other persistent ID, existence, and retraction/withdrawal/correction/superseding status. R4 owns the citation-claim audit and must write the Markdown summary plus `04-citation-claim-audit-ledger.csv`: every visible in-text citation occurrence and every displayed source in a citation cluster receives a unique Pair ID and is checked against the exact proposition it is asked to support using source content rather than metadata alone. A displayed citation with no rendered bibliography entry stays in `04` as `Support=unverifiable`, `MetadataStatus=mismatch`, `PublicIdentifier=no rendered bibliography entry`, blank source/locator, and an owning current finding/question link; it is never deleted or converted into a packet error. For a master's thesis, R3 owns both ledgers. Ownership is not optional and does not mean that other reviewers may ignore citation problems they encounter. R4 and R5 must not collaborate in a shared ledger or read each other's results before freezing their independent verdicts; the chair reconciles the two frozen ledgers afterward. A resolved citation marker, plausible title, metadata API match, keyword match, or sample of important references is not a substitute for either audit.

Field-level coverage is semantic, not merely row-level. R5 must decompose each
rendered entry and authoritative record into the named scalar fields; copying
the complete citation string into several field rows is an invalid audit. R4
must distinguish opened source content from an attempted endpoint and may not
turn many unrelated sources into `unverifiable` with one generic
environment-level waiver. A failed route records its concrete source-specific
failure, while an opened source records a real content locator. The scoped and
full validators reject entry-string replication, truncated or non-source-
specific content endpoints, truncated explicit DOI/arXiv identities, vague
access-attempt locators, adjacent-window proposition drift, propositions that
absorb another citation occurrence or page furniture, external `direct` support
for thesis-local results, Abstract-only proof of detailed equations/definitions,
and dominant locator/disposition templates even when only REF/Pair IDs, URLs,
DOI/arXiv identifiers, numeric coordinates, exact proposition quotations, or
quoted work titles change. Every source in a cluster is assigned only the
smallest clause for which that source is responsible; a whole multi-source
sentence is not repeated mechanically across all Pair rows. Every substantive
R4 verdict carries the closed PairID plus
normalized-proposition-digest binding defined in `references/citation-audit.md`;
a `direct`/`partial`/`context-only`/`mismatch` row then records the closed
per-source tuple `pair role`, `source-stated claim`, short exact `source anchor`,
and `support boundary` in that order. A bare `Abstract`/`Table N` locator or a
sentence varied only by title/URL/PairID/hash is not a completed source audit.
For multi-source markers, R4 assigns and verifies each source's responsibility
separately, and distinguishes externally sourced method/dataset identity from
numbers produced or re-evaluated under the thesis's own protocol.
a complete auxiliary route cannot repair an invalid primary content endpoint.
A schema-shaped ledger that triggers any of these checks is discarded and
retried in a fresh actor context.

R5 may use `legitimate N/A` only for bibliography metadata that can genuinely
be absent, never for required title, complete ordered authors, year, venue,
publication status, type, existence, or correction/retraction status. An
`exact` verdict requires field-specific rendered/canonical equivalence for
authors and venue/status as well as identifiers and numeric fields. Page-range
normalization preserves range structure, and a DOI scalar cannot be prose that
merely contains a DOI. Every bibliography row, including `unverifiable`, keeps
the complete authoritative endpoint actually attempted.

Exact equivalence remains citation-style aware but identity preserving: full
given names may match their initials only with the same ordered authors and
matching surnames/initials; a common venue acronym may match its token-derived
full expansion; and only status synonyms within the same publication state are
equivalent. Before accepting optional-field `legitimate N/A`, R5 verifies that
the frozen rendered entry does not visibly contain the claimed-absent field.
Surname-first and given-first author forms must be parsed without ambiguous
comma guessing; only trailing middle-name omission after a compatible first
given name is allowed. Hyphenated and multipart surnames retain their identity.
Venue normalization uses an explicit alias family and ordered tokens; it may
recognize organization-prefixed and established journal acronyms plus
conservative dotted initialisms, but never unordered token sets or fabricated
acronyms.
Withdrawn and retracted remain different statuses, `unpublished` never matches
`published`, and a versionless arXiv identity does not imply an arXiv-version
field.

The R4/R5 ledger split is an exhaustive-work assignment, not a division of academic judgment. R4 must still assess contribution, methods, experiments, narrative, writing, and presentation; R5 must still assess significance, method intelligibility, evidential sufficiency, experimental interpretation, and thesis coherence. The same principle applies to every other persona. Production runner v1 does not admit Stage-H helpers: P and the owning reviewers perform and sign the required mechanical, semantic, and visual work from their own allowlisted PDF-only views. A future helper extension would require its own complete prompt, view, transport, provenance, validation, and phase contract before any helper sidecar could be consumed.

Every ledger owner also authors the closed `Owned-ledger finding/question
reconciliation` table defined in `references/report-template.md`. Its selectors
expand to the exact `02`/`03`/`04` rows whose authoritative dispositions name
each current report item, and the join is enforced in both directions. A
holistic item outside the owned ledgers uses `none`; a citation, bibliography, or
layout item cannot be made consistent by linking only one convenient row, and a
row signed as a reasoned non-finding cannot simultaneously support a report
finding. This table is semantic reviewer work and is not generated by the
materializer.

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
- `E` — resolvable by recovering existing evidence and incorporating the necessary result into the revised PDF or a verified formal submission attachment. Private author-side proof that will remain outside the submitted thesis is not an `E` remedy and cannot keep an otherwise out-of-scope finding open.
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
- hyperparameters, software/hardware, preprocessing, and training/evaluation procedures needed to interpret and reasonably reimplement the reported method; an exact artifact replay package is not a default thesis requirement;
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

Every reviewer has a mandatory read-only scoped gate before freeze and exit. Ordinary reviewers use `validate_reviewer_output.py`; doctoral R4 and R5 use their ledger-aware owner gates; master's R3 uses the combined page/bibliography/citation owner gate. The exact commands, actor-specific script insertions, and owned-output boundaries are closed in `references/ledger-validation.md` and `references/report-template.md`. The three ledger owners write all semantic judgments to their authoritative owned CSVs first, then, in that same fresh actor turn, run `python rules/scripts/materialize_owner_outputs.py <exact-reviewer-view-root> <actor-id>` at least once after the final CSV write and again after every subsequent owned-CSV change. Its first nonempty stdout line must be `MATERIALIZED`. This deterministic pre-freeze step rebuilds only the actor-owned `02`/`03`/`04` Markdown tables and derives duplicate-free public-endpoint receipt lists; it never changes a semantic CSV value, disposition, finding, grade, packet artifact, or peer output. Do not hand-copy deterministic table rows or endpoint lists after materialization. The reviewer then repeats its read-only scoped gate in the same fresh turn until exit `0` and first nonempty stdout `PASS`, correcting only its own current outputs and rematerializing after any CSV edit. It must never edit the Stage-P packet, process envelope, frozen PDF, governing inputs, staged rules, or another actor's artifact. An upstream/frozen-input defect stops the actor and returns control to Stage O for a new global retry. Materializer and validator code/output are mechanical rule infrastructure, never thesis or citation evidence, and MATERIALIZED/PASS never replace semantic or visual sign-off.

Stage O must not hand-write or merely hash-bind an R-stage prompt. Before the
final process envelope exists, run the canonical Stage-R plan command beginning
with `"<absolute-bundled-python>" -B scripts/build_reviewer_prompt.py plan` for
every degree-appropriate reviewer with required `--process`, `--round-root`,
`--view-root <absolute-run-root>/views/<Rn>`, `--actor`, `--output`,
`--python-executable`, and `--scratch-dir` values. The view must not exist at
plan time and the prompt may bind only that exact future private-view root, not
the finalized round as a reviewer workspace. Production runner v1 supplies no
`--helper-input` arguments and rejects any
helper path in a reviewer plan. Place each returned prompt hash in
`actor_prompt_sha256`. After the final process is sealed and Stage P has frozen
the actual packet inputs, but immediately before each
reviewer dispatch, run the verify command beginning with
`"<same-absolute-bundled-python>" -B scripts/build_reviewer_prompt.py verify`
with required `--run-root`,
`--round-root`, `--view-root <same-absolute-run-root>/views/<Rn>`, `--prompt`,
`--actor`, `--expected-process-sha256`,
`--expected-seal-sha256`, `--python-executable`, and `--scratch-dir`. The builder binds the Python path/hash and an empty,
deterministically named, actor-private scratch directory; verifies the real
process seal, frozen PDF/governing bytes, closed no-helper projection, and staged
validators; reruns the byte-identical staged Stage-P validator with that Python,
`-B`, `PYTHONDONTWRITEBYTECODE=1`, and the empty actor scratch as its working
directory to require first-line `PASS`; and reconstructs exact JSON argument-
vector reviewer gate commands beginning with that Python path and `-B`.
Dispatch only the already-planned byte-identical prompt after first-line
`VERIFIED` with exit `0`. This reconstruction guarantees that every actual reviewer prompt contains the six-question evidence
self-check, whole-PDF remedy/counter-evidence search, minimum-residual finding
rule, and downgrade-to-Question-or-delete rule. A prompt that merely has a
matching hash but differs from the canonical rendering is invalid and triggers
a clean retry.

All Stage-R control paths use canonical local spellings and reject UNC/device
namespaces, reparse traversal, hardlinks, NTFS 8.3 aliases, and NTFS named or
alternate data streams. Every actual opened file and parent directory remains
single-link/named-stream-free and identity/byte stable. Verification binds the
complete metadata-only current-round topology before its first Stage-P gate and
rechecks it after the final scratch check, so a late file, directory, link,
stale review, or other added entry invalidates dispatch.

For the doctoral bibliography/layout owner specifically, R5 may correct only its current `R5-comprehensive-review.md`, `02`, `03`, authorized page renders, and declarations inside those R5-owned Markdown artifacts before freeze. `NeighborPagesChecked` and `Evidence` may use only existing current-round `Pnnnn` values as explicit page cross-references; the primary-key column remains unique, and `Pnnnn` is still forbidden in other columns and prose. R5 records every additional redirect, failed official route, or fallback actually opened in `EvidenceNote` with the closed marker `accessed endpoint: <URL>` so the materializer can derive the complete receipt without guessing. R5 must never edit the Stage-P packet, process envelope, frozen PDF, staged rules, or any other actor's output. If its gate identifies such an upstream defect, R5 must stop and report failure; Stage O treats it as a global-retry condition.

R5 page evidence is normalized before diversity checks: page IDs/numbers,
copied dominant-content titles, neighbor values, scale/DPI, hashes, and numeric
interpolation are masked. A small rotating family of otherwise generic
checklists cannot pass merely by inserting those row values. This mechanical
gate is supplemented by independent semantic spot checks of rendered pages.

R5's page ledger likewise contains page-specific inspection evidence. It
preserves the Stage-P mechanical signal for each page, names the actual
dominant content rather than repeating the chapter/region label, and varies the
visual evidence with the rendered page. An identical “no clipping or overlap”
sentence on every page is not proof of individual inspection. Intentional
blank/separator pages state why their placement is structurally expected.

Apply the full protocol in `references/citation-audit.md` as two independent gates. For a doctorate, R5 must complete the field-by-field bibliography and existence audit, while R4 must complete the occurrence-by-occurrence claim--source audit; for a master's thesis, R3 completes both. Every mismatch, inaccessible field, ambiguous source, and unsupported occurrence must be recorded explicitly. Rendered-marker closure, an aggregate metadata match, or a spot check does not pass either gate. A substantiated fabricated or nonexistent citation is an `S0` integrity blocker.

Treat the ordinary author copy and the submitted blind-review copy as different artifacts. Do not report author, supervisor, institution, or student-number fields that correctly appear in an ordinary author copy as anonymity defects. When a blind-review copy is in scope, render or obtain that actual copy and scan the entire artifact--not only the cover--for identity disclosures in body text, captions, tables, acknowledgments, CV/publications, data and project descriptions, footnotes, URLs, PDF metadata, filenames, comments, and figure watermarks. Apply the institution's exact anonymization rules; in their absence, flag school, department, laboratory, company, employer, partner organization, and other wording that can directly or cumulatively identify the candidate.

The conservative format reviewer must be able to understand the thesis without relying on frontier-specific tacit knowledge. If a term or contribution is clear only to the original paper's specialist audience, treat that as a self-contained exposition problem.

### 7. Independent semantic acceptance before Chair

After every reviewer and the AI assessor has passed its own scoped gate and
frozen its outputs in the closed current round, Stage O launches a different fresh
`SA-Rn`/`SA-AI` actor for each target under the
closed protocol in `references/clean-room-orchestration.md`. The acceptor works
in a target-only neutral view, receives no peer report or old context, and writes
the target's Markdown/CSV acceptance pair. It does not become another reviewer,
does not give A/B/C/D, and cannot create, edit, merge, reject, or adjudicate any
thesis finding.

Semantic-acceptance paths are phase-specific and must never be interchanged.
Each SA actor writes exactly `SA-<target>.md` and `SA-<target>.csv` at the root
of its private target-specific view; that view must not contain a
`06-semantic-acceptance/` directory. Only after the scoped gate passes may
Stage O byte-copy the two frozen acceptance files into the finalized round's
`06-semantic-acceptance/` directory. Conversely, root-level `SA-*` files are
forbidden in the finalized round. The already-frozen target remains
byte-identical throughout semantic acceptance; SA `PASS` admits it to the later
Chair stage, while SA `FAIL` quarantines the entire round and never produces a
patch opportunity in the same retry.

Every acceptance CSV exhausts the target's mandatory semantic units. In
particular, `SA-R4` checks every citation Pair; `SA-R5` independently inspects
every retained page PNG and every bibliography field row; `SA-AI` covers every
authored-prose page/span; ordinary reviewer acceptors cover Gate A--I, all
finding/question/verdict items, and all body chapters. A target's own mechanical
`PASS`, row count, or repeated completion phrase is never acceptance evidence.
The acceptor supplies its own non-template basis and verifies target anchors,
claims, dispositions, and grade consistency directly from its permitted current
PDF/source evidence.

Semantic acceptance applies a **reasonable-support/admissibility** standard,
not a concurrence standard and not a second vote on the thesis. A reviewer item
may pass even when the acceptor would assign a different severity, evidentiary
weight, emphasis, or final recommendation, provided concrete permitted evidence
reasonably supports the observation, the inference stays within that evidence,
decisive counter-evidence was not omitted, and the requested action is
proportionate. A normal scholarly difference in weighting is not by itself a
semantic failure. The acceptor fails an item only when it lacks reasonable
support, exceeds the permitted evidence, omits decisive counter-evidence, is
internally inconsistent, or is not checkable within the closed authority. It
must never rewrite an honest judgment merely to obtain `PASS`.

A passing reviewer-finding row uses one compact canonical JSON object with the
exact ordered keys `assessment_standard`, `premise_class`, `target_premise`,
`supporting_pdf_evidence`, `whole_pdf_resolution`, `residual_gap`,
`action_delta`, and `admissibility_result`. The three structured values are
closed subobjects. Both marker fields use the exact reasonable-support values
defined in `report-template.md`; the residual status records reasonable
support for retaining the bounded concern, not the acceptor's concurrence.
This record binds
the target `Observation`, distinguishes an explicit positive defect, bounded
inference, or absence after a real whole-PDF search, records responsive text or
a concrete unsuccessful search, identifies the residual defect, and states the
minimum increment not already satisfied by the PDF. A passing reviewer-verdict
row similarly uses one compact canonical JSON object with the exact ordered
projection keys `gate_disposition_profile`, `actionable_finding_profile`,
`synthesis_cue`, `target_verdict`, and `coherence_result`. These structures make
the independent comparison auditable; they do not let a validator decide the
truth of a scholarly proposition by keyword.

Passing reviewer `gate` and `question` rows also use their exact closed
canonical JSON contracts from `report-template.md`. A Gate row binds the target
disposition, decisive evidence, and related finding IDs before recording an
independent PDF assessment. A Question row binds all four target cells and then
records the acceptor's whole-PDF unresolved check. Generic prose is not a valid
substitute for either contract.

Before freezing, each acceptor runs the prompt's exact JSON argument vector
`["<bound-python-executable>","-B","<exact-SA-view>/rules/scripts/validate_semantic_acceptance_output.py","<exact-SA-view>","<target>"]`
with the exact environment override `{"PYTHONDONTWRITEBYTECODE":"1"}` and no
shell or `PATH` lookup
to one of two closed outcomes. `PASS` with exit `0` freezes a mechanically valid,
semantically admissible private pair that Stage O may promote. `VALID-FAIL` with
exit `3` freezes a mechanically valid private pair
containing at least one honest semantic failure. Stage O records and verifies
the failed pair's hashes outside every substantive allowlist, quarantines the
entire retry, and must not promote, overwrite, or return the pair to the
acceptor for a more favorable judgment. Any other output/exit combination is a
mechanical or staged-input failure and also stops the retry. After every passing
pair has been receipt-bound and promoted, production Stage O advances only with
`"<absolute-bundled-python>" -B scripts/stage_o_runner.py close-sa-set --run-root <absolute-run-root> --expected-transition-token <previous-token>`.
The runner uses its bootstrap-bound Python and pinned materializer to validate
the complete promoted set and exclusively create the hash-only gate before the
Chair phase becomes eligible. Directly invoking a set validator or materializer
is non-production diagnosis: even a PASS/MATERIALIZED result cannot advance the
event chain or authorize Chair launch. Each actor-scoped SA command still
resolves only its own `<exact-SA-view>` root, whereas the runner-owned closure
operates only on the finalized round's `06-semantic-acceptance/` directory.

Before Stage P, Stage O must run
`scripts/build_semantic_acceptance_prompt.py plan` for every required SA target
using only the stable preplan fields, then place the returned exact prompt
hashes in the final process envelope. Stage O then exclusively binds the
initialization metadata and those final process bytes with
`scripts/manage_review_retry.py seal-process`, stores its returned seal hash in
the bundle-external orchestration log, and runs `verify-process-seal` with the
external process/seal hashes immediately before dispatching P. From Stage P
onward that envelope, seal, and every planned prompt byte are immutable; the
seal is process-control metadata outside every substantive actor view. At SA
launch, Stage O runs the same helper's `verify` operation against the closed
target view and supplies the required
`--expected-process-sha256 <sealed-final-process-sha256>` argument.
Verification loads the validator staged in that view, recomputes the
algorithmic allowlist and exact prompt bytes, and requires the final process
bytes to match both this external anchor and the separate SHA-256 commitment
frozen by Stage P in `00-manifest.md` without changing either artifact. This
prelaunch verification occurs before either SA output exists and returns an
`input_commitment.sha256` over every opened input's relative path, single-link
identity, metadata, and bytes. Stage O retains that value only in external
orchestration state. After scoped `PASS`, Stage O must use `promote` with both
the same required external process hash and
`--expected-input-commitment-sha256 <externally-retained-prelaunch-value>` for
the validated byte-identical SA pair only. It must also supply the original v3
launch record, launch UUID, process-seal hash, externally retained completed
launch-record hash, and terminal output commitment. Promotion reruns the
transport validator against those exact anchors and never recomputes a new
baseline from post-dispatch state. A prompt/process/seal/record/output-hash mismatch,
reserved-directory output, overwrite attempt, input identity/byte drift, or
scoped failure is fatal.

Stage O invokes every `plan`, `verify`, and `promote` operation as
`"<absolute-bundled-python>" -B scripts/build_semantic_acceptance_prompt.py ...
--python-executable <same-absolute-bundled-python>`. The supplied executable
must be the builder's exact canonical `sys.executable` with the same file
identity; a launcher name, `PATH` lookup, WindowsApps alias, non-Python file,
different interpreter, or runtime drift is fatal. The planned prompt records
that path and SHA-256 and renders every validator invocation as an exact JSON
argument vector beginning with that path and `-B`, plus the exact
`PYTHONDONTWRITEBYTECODE=1` environment override. Because the exact prompt hash
is committed by the final process envelope and seal, verification and promotion
close the complete SA lifecycle over the same runtime.

On Windows, all SA builder control paths use canonical local drive-letter
spellings. UNC paths (including administrative and arbitrary nested shares),
device namespaces, symlink/reparse traversal, hardlinks, NTFS 8.3 aliases, and
NTFS named/alternate data streams are rejected. Every object in the closed SA
view is checked for named streams that ordinary directory enumeration cannot
show. The private view and prompt and the private view and finalized
round also use one drive-letter namespace, preventing a mapped/substituted drive
from disguising an overlap.

Any semantic `VALID-FAIL`, missing/duplicate unit, contamination, target-hash drift, or
scoped SA failure invalidates the entire retry after target freeze. The acceptor
must not patch the target and Stage O must not rerun only that reviewer. Encode
any general rule repair in the canonical skill/tests, quarantine the retry, and
rerun the complete chain in a new clean root. Only after all acceptors pass may
Stage O materialize and validate the hash-only
`06-semantic-acceptance-gate.json`. The Chair opens that gate but not the
acceptance reasons; Stage S opens neither.

### 8. Adjudicate in a clean chair context only after all reports are frozen

Stage O launches the chair as a new Stage-C actor with no inherited conversation and no role in packet building or reviewing, and only after the complete semantic-acceptance set and hash gate pass. Stage O first publishes the exact canonical C inputs into the single unified `<exact-stage-c-view-root>` and retains the returned input commitment outside the run. That view contains no individual `06-semantic-acceptance/` directory, page-render tree, helper, peer actor workspace, Stage-S/V artifact, or final validation report. The chair reads all frozen independent reports, the reviewer-visible PDF packet, and the hash-only gate from that view and must not enumerate the parent review directory or open individual acceptance reasons. The chair then:

1. preserves every reviewer's frozen category, defense recommendation, decision regime, and rationale, then deduplicates findings without erasing disagreement;
2. verifies each `S0`/`S1` finding against the thesis and governing source;
3. rejects checklist-driven false positives and unsupported concerns;
4. preserves a single-reviewer severe finding when its reviewer-visible evidence is decisive;
5. records unresolved technical or policy disputes instead of averaging them away;
6. produces a separate overall category, explicit defense recommendation, combined risk decision, and revision roadmap under the same decision regime using the adjudicated evidence;
7. separates `W/E` remedies from genuinely new `N` experiments or evidence unavailable in the submitted PDF;
8. lists strengths and contributions that survived all reviewer lenses;
9. records the exact permitted inputs it opened and invalidates the round if any prohibited local artifact was accessed.

The chair must also record a fresh-context declaration. It cannot use user explanations, rebuttal arguments, remembered implementation facts, prior summaries, or old review conclusions to accept or reject a finding. Before testing evidentiary sufficiency, the chair applies a submission-obligation gate: does the requested information have to be visible in the thesis or a verified formal submission attachment, and does its absence impair a claim that the PDF actually makes? A request for hidden code, logs, hashes, manifests, commands, private member lists, or other non-submitted author-side material that fails this gate is rejected as outside the thesis-review obligation; it is not labeled `not verifiable`, does not become an open revision row, and is not projected as an unresolved question. Use `not verifiable from the submitted PDF` only for an otherwise in-scope thesis question that the permitted evidence cannot decide. Every current reviewer `S0`--`S3` finding must enter exactly one chair disposition: supported/deduplicated findings appear through a canonical duplicate-free `91.SourceReviewerFindingIDs` list, while a submission-obligation rejection is preserved only by its original `Rn-Fxx` ID in a direct `Status=rejected` Chair decision row. The two paths are mutually exclusive, so no finding may disappear or be adjudicated twice. Rejected, disputed, and not-verifiable decisions remain in the chair's decision table, while Stage S projects only the statuses specified in `references/report-template.md`.

The Chair writes its semantic adjudication first, with `91-revision-ledger.csv`, `91-ai-actionable-ledger.csv`, `92-new-evidence-or-experiments.csv`, and the non-projection Chair prose as authoritative sources. Before freeze and after every such source edit, the same fresh Chair actor runs `python rules/scripts/materialize_owner_outputs.py <exact-stage-c-view-root> C` to `MATERIALIZED`; production runner v1 permits no helper arguments or helper files. The materializer rebuilds the deterministic `90`--`92` tables, canonical allowlist, and one identical closed Chair receipt without changing any semantic CSV or Chair decision. The Chair then runs `python rules/scripts/validate_chair_output.py <exact-stage-c-view-root>` until the first nonempty stdout line is `PASS` with exit `0`. This scoped gate first proves that the unified C view contains exactly the canonical C inputs and six outputs; it never opens page renders, individual SA files, or helpers. Private-SA and R5-render hashes carried by the hash-only gate remain explicitly Stage-O transport commitments until the final full validator recomputes them. The Chair may correct only its own current outputs and must rematerialize after a source edit. After transport and scoped PASS, Stage O rechecks the prelaunch C-input commitment and promotes only the six C outputs, without replacement. Any input drift, extra view entry, upstream failure, promotion collision, or transport failure triggers a clean global retry rather than a downstream patch.

Keep the frozen AI-style judgment separate from the reviewer verdict distribution and academic/defense categories. The chair carries every unresolved `AI-Fxx` with impact `material` or `local` into a separate AI-actionable section and sidecar of the revision ledger, without assigning `S0--S4`, `W/E/N/P`, or changing the defense grade. It must repeat that this is not an AI-use, authorship, plagiarism, or misconduct determination. Optional AI findings remain separate and optional.

Before issuing the combined decision, the chair must join the frozen bibliography and citation-claim ledgers by stable rendered reference identity/displayed label and run a cross-ledger consistency gate. A cited reference whose title, ordered authors, persistent identifier, existence, or publication identity is `mismatch` in the bibliography ledger cannot remain `direct`, `partial`, or `context-only` in the citation-claim ledger without a separately identified correct source. Likewise, a citation-claim row whose opened source metadata does not identify the cited work is invalid even if its disposition is non-empty. Record every conflict and reclassify the affected pair conservatively. A **substantive** cross-ledger contradiction is one that changes source identity, existence, publication status material to the claim, or claim support; record it as at least `S2`, require a corrected frozen-round audit, and do not issue **A — 同意答辩** until it is closed. Assign B, C, or D according to the adjudicated severity and `references/grading-and-verdicts.md`. Pure punctuation, capitalization, abbreviation, or house-style differences that do not alter source identity or support are local `S3` items and do not by themselves fail the combined gate. Row counts and `pending=0` never override a substantive contradiction.

Under the skill-default regime, do not average A/B/C/D grades, convert them to points, or let a majority mechanically erase a decisive minority finding. Under an institutional regime, follow its verified aggregation rule. If the institution supplies a mandatory numeric scoring form, preserve each score and its rule-based conclusion rather than substituting an ungrounded mean.

### 9. Produce the clean user-facing summary

After the chair's six outputs have passed their scoped gate and been promoted, Stage O publishes only the exact canonical Stage-S inputs into the single unified `<exact-stage-s-view-root>`, retains its input commitment outside the run, and launches a new Stage-S summarizer with no inherited conversation. Stage S is part of this skill, not a later conversation-side summarization step. Its private view contains no PDF, governing file, packet, `02`--`04`, helper, page render, SA artifact/gate, Stage-V input, or final validation report. It writes `93-user-facing-summary.md` plus both lossless machine-readable current-action projections using `references/report-template.md`.

The summary is a traceable compression, not another adjudication. It must reproduce every individual and chair conclusion exactly, including each reviewer's decision regime/source, persona emphasis and whole-thesis rationale, the AI assessor's exact rationale, and the chair's decision regime/source and exact rationale; report the AI-style judgment separately; list exactly the current open adjudicated items in `91-revision-ledger.csv`; copy the chair's optional-suggestion and limitation sections without rephrasing; project every unresolved/not-verifiable/disputed Chair decision; project every current N-remedy evidence item; and bind every row to current finding IDs and exact PDF anchors. Every projected source field must occur exactly once under its documented `##` section; a duplicate authoritative section or duplicate same-named field inside it invalidates the bundle, and a lookalike label elsewhere cannot redirect the projection. Its H1 and nine H2 sections, nine identity bullets, canonical ordered input allowlist, table-only conclusion/current-item/unresolved sections, and fourteen reconciliation bullets are closed schemas: no extra section, reorder, duplicate basename, appendix, or stray prose is allowed. The actor table order is `R1...Rn, AI, Chair`; the academic, AI, and N rows preserve their authoritative source order; and the reconciliation `Statement` has the exact canonical non-invention value. The current academic and AI action CSVs are lossless open-row projections of their `91` masters, not abbreviated summaries. It must not introduce, omit, soften, escalate, or merge findings; write a new “decisive basis”; mention old resolved issues; or use user explanations, source-sync facts, repository knowledge, previous assistant summaries, or new web research. The validator must reconcile the complete actor table field-by-field, exact round/retry/prompt/input identity, every Markdown/CSV row set, issue counts, and current PDF identity before the summary can be relayed.

Before Stage S freezes or exits, the same fresh summarizer runs `python rules/scripts/materialize_owner_outputs.py <exact-stage-s-view-root> S` to `MATERIALIZED`. Stage S is a deterministic projection actor: this command rebuilds both open-row `93` CSV subsets and every mechanically copied table, section, count, allowlist, and receipt in `93-user-facing-summary.md` from the closed current-round inputs; it introduces no adjudication. It then runs `python rules/scripts/validate_summary_output.py <exact-stage-s-view-root>` until exit `0` and first nonempty stdout `PASS`, correcting only its three `93` outputs and rematerializing after any change. Before opening any source other than the process envelope, the scoped gate enumerates names and metadata to prove the exact unified view closure and rejects every missing or extra entry without opening an extra file's bytes; it then binds all allowed inputs/outputs to one stable-handle snapshot and repeats the topology check at the terminal boundary. After transport and scoped PASS, Stage O rechecks the prelaunch S-input commitment and promotes only the three `93` outputs, without replacement. After S freezes, Stage O—not S—runs the complete bundle validator over the finalized round and writes `95-bundle-validation.md`; only a complete PASS authorizes delivery.

For questions about the current PDF's independent blind review, relay the frozen current-round `93-user-facing-summary.md` rather than reconstructing an answer from conversation memory. Production runner v1 neither runs Stage V nor creates or relays `94-post-freeze-prior-issue-closure.md`; for a longitudinal question, provide only the current `93` as current-PDF evidence and state that prior-item comparison is outside this runner. A future separately implemented longitudinal extension must keep any comparison artifact separate and cannot rewrite the current round. A conversation-aware orchestrator may add only a minimal operational wrapper and artifact links.

### 10. Direct-edit mode

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

### 11. Independent re-review

For a revised thesis, freeze a new PDF-only packet through a fresh Stage-P builder and run a **fresh independent re-review pass**. Reviewers inspect the revised PDF in new empty contexts without reading the conversation, author response, prior issue ledger, source tree, Git diff, old reports, or earlier summaries; they complete a fresh Gate A--I matrix and whole-thesis synthesis and record defects visible in the current PDF and findings newly discovered in this round. They must not call a defect a revision regression or say it was introduced by revision because they have no comparison baseline. Every fresh R/AI output must pass its own different semantic acceptor and the hash-only gate before the clean Chair begins. The current production runner stops at this clean current-PDF result and rejects Stage V. The following longitudinal Stage-V semantics are reserved for a separately implemented future extension and must not be claimed by runner v1. Only after every fresh report/assessment, acceptance gate, clean chair decision, and clean current-round summary are frozen could such a separately labeled Stage V compare the new PDF against specifically allowlisted prior artifacts. With only a prior issue ledger/author response, it would perform prior-finding closure and could not infer global regression. A full longitudinal regression audit would additionally require the prior frozen PDF and prior page/bibliography/citation inventories and ledgers with hashes; a longitudinal style comparison would additionally require the specifically identified prior AI report. Stage V would not be part of the independent re-review evidence packet and could not retroactively alter its findings, grades, chair decision, ledgers, or clean current-round summary. It would classify prior items as:

- `resolved`;
- `unresolved`;
- `not verifiable`;
- `rejected`;
- `superseded by current finding`.

The clean chair reports current-round defects and current-round newly discovered findings only. A future Stage-V extension could identify a demonstrated regression only when its full allowlisted prior baseline proved the comparison; otherwise introduction by revision would remain `not verifiable`. A high longitudinal closure rate would never justify passing an unresolved `S0` or decisive `S1` issue.

Each reviewer and the chair must issue a fresh category and defense recommendation for the newly frozen artifact under the round's decision regime. Do not mechanically carry forward or edit the previous round's conclusion.

When the user requests an iterative review--revision loop, Stage O starts a newly frozen PDF-only round after every revision batch and applies the same current-round completion gate without reading a prior review. Under production runner v1, do not claim prior-item closure or longitudinal regression testing: neither Stage V nor prior artifacts enter the round. The current round may be described as having no actionable findings only when all required independent reviewers return no actionable `S0`--`S3` finding, the page-layout ledger has no unresolved signal, both bibliography and citation-claim ledgers have 100 percent coverage and no unresolved actionable mismatch, no `AI-Fxx` with `material` or `local` impact remains, and every current target-specific semantic acceptance plus the aggregate hash gate passes. `S4` and AI-optional suggestions may remain explicitly optional and must not be described as defects. Never claim literal perfection; state the artifacts, checks, and limitations that bound the current-PDF result.

Stage O runs a fresh isolated AI-style assessment on every revised frozen artifact. The assessor does not receive the previous report before it freezes its new judgment. Any unresolved `AI-Fxx` with `material` or `local` impact prevents a claim that final prose-polish review is complete, regardless of the overall signal label, but does not by itself alter the academic or integrity verdict.

## Completion standard

A review is complete only when it includes:

- the frozen manifest and policy basis;
- the completed Markdown and CSV physical-page layout ledgers and suspect-page dispositions, plus exactly one retained checksum-bound PNG in `page-renders/<PageID>.png` for every physical page;
- the completed Markdown and CSV bibliography-integrity and citation-claim ledgers, with deterministic entry/Pair IDs, reconciled counts, and no silent unchecked rows;
- all independent reviewer reports required for the degree level;
- a complete Gate A--I whole-thesis matrix, whole-thesis synthesis, and persona-weighted deep review in every R-numbered report; ledger ownership cannot substitute for any of them;
- one internally consistent category, exact defense recommendation, decision regime/source, confidence, and whole-thesis rationale in every R-numbered report; use A/B/C/D under the skill-default regime;
- the standalone `05-ai-style-assessment.md`, reported separately from R1--R5 and containing the non-attribution disclaimer;
- one fresh target-specific semantic-acceptance Markdown/CSV pair for every
  reviewer and the AI assessor, with exhaustive target-unit coverage and no
  `fail`, plus the hash-only passing `06-semantic-acceptance-gate.json`;
- a chair synthesis with agreements and disagreements;
- a chair table preserving every independent category/recommendation and a separately reasoned overall category/recommendation, with no ungrounded averaging;
- a precise, prioritized academic revision ledger and a separate AI-actionable ledger, each with machine-readable sidecars;
- a separate list of genuinely new experiments or evidence unavailable from the submitted PDF;
- a statement of review limitations;
- an explicit statement that the reviewer-visible local artifact was exactly one frozen PDF, plus a list of permitted public citation-verification sources;
- a clean `93-user-facing-summary.md` that exactly reconciles with the current chair ledger and adds no finding or contextual claim;
- a fresh-context and input-receipt/access declaration from the packet builder, every reviewer, assessor, independent semantic acceptor, chair, and final summarizer, confirming that no prohibited context or artifact was used; production runner v1 admits neither H helpers nor Stage V;
- a passing `95-bundle-validation.md` generated from `scripts/validate_review_bundle.py`, while preserving manual semantic sign-off;
- for direct edits, compilation/render verification and a re-review result.

Do not claim that “all problems are solved.” The strongest permitted completion statement is “the current frozen PDF has no actionable findings under the recorded checks,” and only when: every R report has no actionable `S0--S3`; the page ledger has `unchecked=0` and no unresolved signal; both citation ledgers have 100-percent reconciled coverage and no actionable mismatch or cross-ledger conflict; there is no policy blocker; and no `AI-Fxx` with `material` or `local` impact remains open. Optional `S4`/AI-optional suggestions and review limitations must still be disclosed.
