---
name: idea2paper
description: End-to-end orchestration from a rough AI/ML/CV/NLP/robotics research idea to a complete experiment-ready LaTeX paper sketch. Use when Codex must refine an idea, select the nearest suitable top conference whose abstract deadline is still open, obtain the official or fallback template, run a source-audited literature survey, conduct a novelty/feasibility agent meeting, design the method and experiments, generate and freeze a defensible paper title, generate every paper figure with imagegen, write all paper sections, and leave only explicitly marked experimental or implementation TODOs. Triggers include idea2paper, idea to paper, paper sketch, research proposal to paper, turn this idea into a paper, 一键写论文, 从 idea 到 paper, 打磨 idea, and 完整论文草稿.
---

# Idea to Paper

Build a traceable paper project whose prose, method, experiment design, tables, figures, citations, and LaTeX layout are complete except for explicitly marked real-world results or unsettled implementation choices. Run as an orchestrator: dispatch specialized skills, persist stage artifacts, invalidate stale outputs, and resume from the last valid stage.

## Non-negotiable rules

1. Use `ai-literature-survey` for every broad, targeted, or delta literature search. Do not replace it with an ad hoc search workflow.
2. Use `imagegen` for every figure asset, including method overviews, module figures, teasers, charts, qualitative layouts, and placeholders. Do not call another drawing skill or create figures with SVG, TikZ, draw.io, plotting libraries, HTML, or canvas. LaTeX tables and equations are not figures.
3. Permit predicted results and result-dependent claims in the sketch only through the red draft macros in `assets/idea2paper-draft.sty`. Put a matching `% TODO(<ID>): ...` comment within three source lines of every macro occurrence.
4. Keep plans, agent dialogue, risk registers, rejected ideas, and operational TODO lists outside the rendered paper. Only academically relevant limitations belong in the paper.
5. Select venues by topic fit and the nearest still-open abstract deadline. Do not consider whether the author can finish experiments before the deadline.
6. Verify current deadlines, templates, page limits, anonymity rules, and policies from official venue sources at execution time.
7. Never silently continue with stale artifacts. Mark downstream stages `stale`, rerun the affected stage, and record the new input version.
8. Treat the project name and initial idea summary only as working labels. Generate, review, and freeze the paper title from the final positioning, claim graph, Method, and venue before drafting the manuscript.
9. Invoke `paperjury:paperjury` for isolated adversarial manuscript review. Run at least two isolated rounds with at least three reviewer lenses, require the final round to be clean, adjudicate every major issue, and bind the passing report to the final manuscript hash.

## Start or resume a project

Read [project-contract.md](references/project-contract.md) before creating or resuming any project.

Before running helper scripts, verify that `python --version` resolves to Python 3.10 or newer and install `requirements.txt` into that runtime; `pdfplumber` is mandatory for the rendered layout gate. On Windows, do not use a Microsoft Store alias that exits without a runtime; select an installed or Codex-bundled Python executable and use that same executable for every command.

For a new project, run:

```bash
python scripts/init_project.py --idea "<user idea>" --out-dir <parent-directory> \
  [--venue "<venue>"] [--language en] [--resources-file <resources.json>] \
  [--data-source user]
```

The script creates the canonical directory layout, state file, current-machine resource snapshot, LaTeX section scaffold, draft macros, claim/experiment tables, figure manifest, and TODO registry. Never overwrite an existing project; resume it instead.

For an existing project:

1. Read `project.json` and `state.json`.
2. Run `python scripts/state_manager.py show <project-root>`.
3. Confirm that files declared complete still exist and that their upstream versions match.
4. Resume the earliest `pending` or `stale` stage.

## Reference routing

Load only the references required for the current stage:

| Stage or decision | Required reference |
|---|---|
| Intake, project layout, state, resume, artifact ownership | [project-contract.md](references/project-contract.md) |
| Venue selection, official-source checks, template and page budget | [venue-selection.md](references/venue-selection.md) and [venue-registry.json](references/venue-registry.json) |
| Initial or delta literature search, paper status and open-source enrichment | [literature-integration.md](references/literature-integration.md) |
| Student A, Student B, Professor rounds and convergence | [idea-council.md](references/idea-council.md) |
| Claim graph, Method, baselines, experiments, ablations, result TODOs | [claim-method-experiment.md](references/claim-method-experiment.md) |
| Paper-title candidates, adversarial review, collision check, and freeze | [title-selection.md](references/title-selection.md) |
| Any figure request or figure revision | [figure-protocol.md](references/figure-protocol.md); for teasers/overviews/pipelines also [figure-composition.md](references/figure-composition.md); then the installed `imagegen` skill |
| Related Work, Introduction, Abstract, Conclusion, Teaser placement, appendix, page budget | [manuscript-writing.md](references/manuscript-writing.md) |
| Adversarial manuscript iteration | [quality-gates.md](references/quality-gates.md), then the installed `paperjury:paperjury` skill |
| Stage gates, compilation, sketch and submission readiness | [quality-gates.md](references/quality-gates.md) |

## Workflow

### 0. Normalize intake and resources

1. Preserve the user's original idea verbatim as `idea/versions/idea_v0.md`.
2. Record existing papers, code, models, data, preliminary results, preferred language, and an explicitly requested venue.
3. When compute is omitted, use the current-machine snapshot produced by `scripts/scan_resources.py`.
4. When data is omitted, treat all relevant, accessible, research-licensed open datasets discovered during the survey as the candidate pool. Do not interpret this as every dataset on the internet or download everything immediately.
5. Set `INTAKE` and `RESOURCES_READY` complete only after assumptions are recorded.

### 1. Lock the venue and template

If the user specified a venue, retain it and verify the current track, deadlines, template, page limit, reference-counting rule, anonymity, supplement, and AI-disclosure policy.

Otherwise:

1. Extract field, task, method, modality, and application tags from the idea.
2. Use `venue-registry.json` as a strict default whitelist. Automatic selection may consider only ECCV, ICCV, CVPR, NeurIPS (alias NIPS), ICML, ICLR, AAAI, IJCAI, ACM MM (alias ACMMM), ACL, and EMNLP. Never promote a pool-external venue through community-standing evidence.
3. Browse official CFP or submission pages for all plausibly fitting whitelist members and create a verified candidate JSON file. A user may explicitly request a venue outside the pool, but record it as `selection_mode=user_specified`; do not call it a default-pool top venue.
4. Run `scripts/select_venue.py` to keep candidates with `scope_fit >= 4/5`, reject meetings whose abstract deadline has passed, and select the nearest effective deadline. If no separate abstract deadline exists, use the full-paper deadline.
5. Do not use experiment duration in filtering or ranking.
6. Download the official current-cycle template from the venue. If it is not released, use the previous official template and add `\TemplateTODO{TEMPLATE-UPDATE}{...}` plus an adjacent source TODO.
7. Record the official body-page limit and allocate a section/figure/table budget immediately.

Set `VENUE_LOCKED` complete only when `venue/decision.json` contains source URLs and check timestamps.

### 2. Build and audit the literature corpus

Read `literature-integration.md`, then invoke `ai-literature-survey` with the current idea version, target venue, user seeds, task/method/benchmark/application queries, and cross-domain analogies. Direct its workspace to `related_works/`.

After the survey:

1. Preserve its source ledger, raw and merged records, query plan, screening, reading matrix, snowball log, synthesis outline, and coverage audit.
2. Run `scripts/record_survey_run.py` to verify the standard survey schemas and save the `ai-literature-survey` invocation ID, idea version, coverage decision, and artifact hashes.
3. Run `scripts/enrich_literature.py` to add acceptance, publication, paper-access, official-code, data, model-weight, license, evidence-URL, and checked-at fields without inferring unknown values.
4. Save legal open-access PDFs locally. For unavailable PDFs, keep metadata and landing links; never bypass access controls.
5. Mark directly relevant accepted top-conference and top-journal papers `must_cite=yes`.
6. Require the survey coverage gates and two citation-snowball passes over core anchors.
7. For a full paper sketch, require at least 30 screened included records, including at
   least 10 core papers, at least five mechanism/task/evaluation coverage families,
   at least eight papers from the current or previous two calendar years, at least
   eight accepted/published papers with status evidence, and at least three explicitly
   marked closest or novelty-threatening works. These are relevance floors, not a
   license to pad the bibliography: excluded or uncited off-topic records do not count.
8. Require at least 25 distinct audited corpus papers to be cited in the manuscript
   and at least 20 in Related Work. Every core paper must have a reading-matrix
   extraction, and every citation must resolve to a verified BibTeX entry.

Set `LITERATURE_AUDITED` complete only after the coverage audit states searched sources, blind spots, and its stopping decision.

### 3. Run the idea council

Read `idea-council.md`. Run Student A and Student B independently on the same immutable idea, resource, and literature snapshots. Let the Professor read both reports only after they finish.

Run at most three rounds:

1. Student A attempts to falsify novelty, identifies the closest prior work, and proposes a minimally divergent repair when needed.
2. Student B audits technical feasibility against the available compute and data, but does not judge deadline feasibility.
3. The Professor adjudicates every critical objection, chooses rather than mechanically averages candidates, updates the canonical idea, and proposes distinct evidence-backed contributions.
4. If the problem, core claim, or method family changes, rerun a delta `ai-literature-survey` before the next round.

Freeze the idea only when no critical novelty or feasibility blocker remains. If three rounds cannot produce a defensible idea, narrow the claim to the strongest viable version or mark the project blocked; do not invent consensus.

### 4. Freeze the claim graph

Read `claim-method-experiment.md`. Populate `experiments/claim_experiment_matrix.csv` so every paper claim maps through:

```text
prior limitation -> contribution -> method component -> hypothesis
-> experiment and metric -> figure or table -> manuscript claim
```

Give every claim, contribution, module, experiment, result slot, and figure a stable ID. Reject unsupported contributions and experiments that do not test a claim. Require at least three genuinely distinct, evidence-backed contributions; if the idea cannot support three without artificial splitting, return to the council instead of declaring the idea frozen.

### 5. Write Method and design experiments

1. Define the problem, notation, assumptions, full pipeline, objectives, training/inference behavior, and necessary algorithmic details.
2. Explain which problem each module solves and why its design is appropriate.
3. For an unsettled design, write the most likely effective choice with `\DraftChoice{<ID>}{...}` and place the alternative in an adjacent source TODO.
4. Design Experiment Setup, datasets, training data, baselines, metrics, main benchmark tables, ablations, hyperparameters, robustness tests, and qualitative comparisons.
5. Reuse a baseline paper's reported number only when dataset version, split, training data, backbone, metric, preprocessing, and evaluation protocol are compatible. Record the source table and setting.
6. Fill expected method and ablation numbers with `\PredResult{<ID>}{...}`. Mark every dependent narrative statement with `\PredClaim{<same-ID>}{...}` and an adjacent TODO.
7. Use factorial module ablations when tractable; otherwise use an explicitly ordered probing design. Put non-core comparisons in the appendix.

### 6. Generate and freeze the paper title

Read `title-selection.md` after `METHOD_EXPERIMENT_READY` is stable. Generate 8--12 candidates across at least three framing families, shortlist at least three, check them against the audited literature corpus, and run independent positioning and clarity/faithfulness reviews. Let the Professor/orchestrator choose the title from evidence rather than the project directory or original prompt.

Save `title/brief.json`, `title/candidates.json`, and `title/decision.json`; bind the selected title to the current idea version, venue, claim IDs, Method, terminology, and corpus hashes; then update `paper/title.tex`. Keep `title/decision.json` canonical instead of mutating the early-stage `project.json`. Complete `TITLE_FROZEN` only when the decision and active LaTeX title match and the selected title has low overclaim risk. Reconcile the title once more after drafting the Abstract and Introduction; version and refreeze it if the actual story differs.

### 7. Generate every figure with imagegen

Read `figure-protocol.md`, then invoke `imagegen` separately for each figure or variant. Use it for the overview, complex modules, teaser, quantitative chart images, qualitative layouts, and placeholders.

For every teaser, overview, or pipeline, read `figure-composition.md` first.
Build a top-venue reference board and a claim-first composition brief; compare at
least six directionally distinct imagegen candidates spanning at least three
composition archetypes; then apply at least three single-change imagegen refinements
to the winner. Require at least three domain-native visual primitives and keep ordinary
module boxes/cards under 35% of the canvas. Reject any candidate whose
visual hierarchy does not match the novelty, whose arrow grammar is ambiguous,
whose rectangular footprint wastes paper area, or whose composition would remain
unchanged after arbitrary relabeling.

For each final asset:

1. Save the exact prompt and input-image roles under `figures/prompts/`.
2. Move the selected raster output into the project and copy the paper-consumed version into `paper/figures/`.
3. Record it in `figures/manifest.csv` with claim/module/result IDs, an `imagegen` invocation provenance JSON, and matching hashes for the generated and paper-consumed copies.
4. Inspect it for terminology, arrows, factual content, text fidelity, layout, color, column-width readability, and watermark absence.
5. Iterate through `imagegen` with one targeted change at a time; do not repair the artwork with another drawing tool.

Prompts are immutable invocation evidence. Never backfill composition fields into
an already executed prompt. A prompt that explicitly requests exactly one
surgical change and preserves everything else may inherit the complete
composition/critic contract only from its direct input image through matching
parent prompt and output hashes; all broader edits must carry the full contract
themselves.

The selected imagegen raster must remain the graphical subject of every `figure` environment. Use only the finite raster-layout grammar: placement, centering, `includegraphics`, captions, labels, tracked draft macros, spacing, and ordinary raster `subfigure` environments. TeX text/math bodies, outer scale/resize wrappers, `tabular`, `array`, `rule`, `minipage`, boxes, inputs, custom drawing macros, or any unrecognized structure are forbidden, including attempts to satisfy provenance with a token-sized registered raster.
6. For real qualitative outputs, require preservation of the input evidence. Reject any generated layout that changes the underlying observation.
7. Before real outputs exist, every planned qualitative comparison must already be a
   real ImageGen-generated raster, not a red prose sentence or an empty box. Put an
   unmistakable `CONCEPTUAL PLACEHOLDER - REPLACE WITH RAW OUTPUTS` disclosure inside
   the generated composition, declare `Evidence status: conceptual-placeholder` in
   its prompt and QA, register the relevant qualitative result/TODO ID in
   `manifest.csv`, and render the matching `\QualPlaceholder` inside the same LaTeX
   figure environment. The placeholder may visualize the intended comparison layout
   and diagnostic overlays, but it must not imitate measured model evidence.

### 8. Write the manuscript

Read `manuscript-writing.md`. Draft in this order after the idea and claim graph are frozen:

1. Method and Experiments
2. Related Work
3. Introduction
4. Abstract and Conclusion
5. Teaser and final page rebalance

Cover all relevant `must_cite` accepted top-venue work in Related Work. Write result-dependent Abstract and Conclusion claims under the successful-experiment assumption, using the same red result IDs and adjacent TODOs.

When the venue permits a teaser, render it strictly after the complete title/author
block and before the abstract: `\maketitle`, then `\input{sections/teaser}`, then
`\begin{abstract}`. Never place it above the title, between title and authors,
after the abstract, or as a float, and never patch template-internal `\@maketitle`
tokens to position it. Allow the sketch to exceed the official body limit by at
most one page; move secondary material to the appendix and cite it from the main
text. Keep core claims, method, and decisive evidence in the main paper.

Lay out every figure and table at or shortly after its first discussion and give every body or appendix floating or source-anchored `\captionof` artifact a unique label. The final body artifact must be anchored before `Conclusion`; no body figure/table may be deferred to a dump after `Conclusion`. In a single-column template, reject an artifact page with a large empty row, a tall narrow local artifact region, one-sided empty column, or avoidable trailing blank area. Across both body and appendix, allow no more than two artifacts on a single-column page, reject adjacent appendix pages that each carry at least two artifacts, reject three consecutive pages in either region that each carry at least two artifacts, reject a four-artifact dump on the final two appendix pages, and reject an appendix whose artifacts are mostly dumped onto its final three pages. Reject any artifact that interrupts sentence continuity across a page boundary; the compiled detector must report zero `float_interrupted_hyphen` and zero `float_interrupted_sentence` findings. Infer columns from active top-level commands and actually invoked local-template macros, then cross-check confident rendered gutter geometry; dormant macro definitions or unresolved conditional branches are not column evidence, and a manual `--columns` value may not relax confirmed two-column mode. Forbid every `\hfuzz` or `\vfuzz` use in the active author `.tex` input graph and in author-controlled local styles because those registers suppress TeX clipping diagnostics; do not misclassify register use inside an exact venue-bound official template asset as an author bypass. Compile from freshly removed named `main.*` artifacts, force `latexmk` to rebuild, and bind the report to the resulting `main.log` and `main.aux` paths and hashes. The project validator must independently recompute the active column mode, every artifact-label page, distribution gates, rendered whitespace, reading-continuity findings, and media-box overflow from the bound current source/AUX/PDF and exactly compare them with the report. Treat any TeX overfull box above 2 pt as a blocking clipping defect; record smaller overfull boxes as inspection warnings rather than silently discarding them. Also reject rendered text or images extending more than 2 pt beyond the PDF media box, while retaining the compiler log as the primary detector for content that overflows a column but remains inside the page. Interleave artifacts with the prose that interprets them; do not solve clustering by moving the whole queue to the appendix.

Keep the sole Conclusion label, body/exempt/reference labels, bibliography, and appendix marker in the canonical order specified by `manuscript-writing.md`; place `\label{idea2paper:start-appendix}` immediately after `\appendix`. Use only static paper-local manuscript and figure/bibliography paths; do not add untrusted local styles/classes or use TeX conditionals to alter the audited structure. Never insert `\clearpage`, `\newpage`, `\pagebreak`, `\FloatBarrier`, or exact `[H]` figure/table placement to manufacture placement. Rebalance float size, legal `[tbp]` placement specifiers, source order, prose, and appendix transfers instead, compile twice after meaningful layout changes, and visually inspect every page rather than only the last page.

### 9. Review, compile, and close gates

Read `quality-gates.md` and run:

```bash
python scripts/compile_paper.py <project-root>/paper --max-pages <official-limit> --allow-overrun 1 [--references-counted when venue.page_rules.references_counted=true] --report <project-root>/qa/layout_report.json
python scripts/todo_lint.py <project-root>/paper --mode sketch --registry <project-root>/qa/todo_registry.json
python scripts/validate_project.py <project-root> --mode sketch --report <project-root>/qa/sketch_validation.json
```

The TODO registry is an immutable-snapshot artifact: it must use `.` as its root and
paper-root-relative POSIX paths for every exact occurrence line. Regenerate it after
any manuscript edit; project validation compares the entire registry, including paths,
lines, and messages, rather than accepting an ID-only match.

Invoke `paperjury:paperjury` after the first complete draft. Give each reviewer the same immutable manuscript snapshot but no other review or ledger; use at least three independent lenses covering domain novelty, method validity, and empirical/reproducibility risk. Every new reviewer JSON must use `schema_version: 2`; every blocking major must be an object with a reviewer-scoped stable `id`, a non-empty `evidence` or `evidence_anchor` containing an exact `file:line[-line]` or LaTeX label/ref that resolves inside the frozen snapshot, and a non-empty `required_fix`. String majors and semantic-similarity ledger binding are forbidden for new rounds. The orchestrator—not a reviewer—merges duplicates, adjudicates significance, applies author-authorized writing and claim-alignment edits, and queues issues that genuinely require new method or data. Use the official `schema/meta/issues` PaperJury ledger, and preserve each blocker ID with its round and reviewer provenance in the corresponding ledger row. Save each snapshot, three or more reviewer JSON files, and a derived `round_report.json` containing their hashes under `qa/paperjury/round_XX/`; include a path-resolvable copy of the complete `figures/` evidence chain and exact `paper/figures/` consumers in that snapshot, and render `LEDGER.md` from `LEDGER.json`, never by hand.

After revision, create a new immutable snapshot and run a clean PaperJury round whose reviewers cannot see prior reports or the ledger. Continue until a clean round adds no fixable writing/claim-alignment issue and no gate-blocking or unadjudicated major issue remains; require at least two rounds. Save `qa/paperjury/final_report.json` with `status=pass`, `mode=review`, `author_authorized=true`, the artifact-derived round/reviewer counts, `converged=true`, zero ledger-derived blocking/unadjudicated majors, the current complete `paper/` source hash, and the final review-visible `.tex`/`.bib` snapshot hash. Validation must derive the pass from reviewer files, round manifests, snapshots, and the official ledger rather than trusting this summary. Rerun PaperJury after any later material claim, result-narrative, or layout/caption rewrite.

Declare `SKETCH_COMPLETE` only when every non-experimental component is publication-quality and the only unresolved items are registered predicted results, qualitative placeholders, method alternatives, or a temporary-template update.
Text-only qualitative placeholders do not qualify: each one must be bound to a
paper-consumed ImageGen raster with prompt, receipt, provenance, manifest, and QA.

After real results arrive, replace every prediction, regenerate affected imagegen figures, rewrite Results/Abstract/Conclusion, run the submission-mode checks, and declare `SUBMISSION_READY` only with zero draft macros and TODOs.

## State invalidation

Use `scripts/state_manager.py invalidate <project-root> --cause <cause>` whenever inputs change:

- `idea`: invalidate literature positioning, council, claim graph, method, experiments, title, figures, and manuscript.
- `literature`: invalidate council decisions, title selection, and all downstream claims.
- `resources`: invalidate feasibility, resource-dependent method choices, experiments, and title selection.
- `venue`: invalidate template, title fit, page budget, teaser placement, layout, and venue QA.
- `method`: invalidate Method/experiment readiness, title selection, figures, and manuscript.
- `title`: invalidate the frozen title and manuscript consistency pass.
- `results`: invalidate title claims, result tables, quantitative/qualitative figures, Abstract, Conclusion, and final claims.

Only the orchestrator may merge canonical artifacts. Student agents write separate reports; literature shards write separate raw outputs; `imagegen` variants use versioned filenames. Never let concurrent agents edit the same canonical file.

## Final delivery

Deliver the project directory, compiled PDF when a TeX engine is available, venue decision, resource snapshot, audited literature corpus, idea-meeting reports, claim matrix, Method and experiment plan, imagegen prompts and raster assets, modular LaTeX source, TODO registry, and QA reports. Report the current state as `SKETCH_COMPLETE` or `SUBMISSION_READY` without overstating it.
