---
name: idea2paper
description: End-to-end orchestration from a rough AI/ML/CV/NLP/robotics research idea to a complete experiment-ready LaTeX paper sketch. Use when Codex must refine an idea, select the nearest suitable top conference whose abstract deadline is still open, obtain the official or fallback template, run a source-audited literature survey, conduct a novelty/feasibility agent meeting, design the method and experiments, generate every paper figure with imagegen, write all paper sections, and leave only explicitly marked experimental or implementation TODOs. Triggers include idea2paper, idea to paper, paper sketch, research proposal to paper, turn this idea into a paper, 一键写论文, 从 idea 到 paper, 打磨 idea, and 完整论文草稿.
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

## Start or resume a project

Read [project-contract.md](references/project-contract.md) before creating or resuming any project.

Before running helper scripts, verify that `python --version` resolves to Python 3.10 or newer. On Windows, do not use a Microsoft Store alias that exits without a runtime; select an installed or Codex-bundled Python executable and use that same executable for every command.

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
| Any figure request or figure revision | [figure-protocol.md](references/figure-protocol.md), then the installed `imagegen` skill |
| Related Work, Introduction, Abstract, Conclusion, Teaser placement, appendix, page budget | [manuscript-writing.md](references/manuscript-writing.md) |
| Stage gates, compilation, review, sketch and submission readiness | [quality-gates.md](references/quality-gates.md) |

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
2. Use `venue-registry.json` as the initial top-venue candidate set; add a domain-specific top venue only with evidence.
3. Browse official CFP or submission pages and create a verified candidate JSON file.
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

### 6. Generate every figure with imagegen

Read `figure-protocol.md`, then invoke `imagegen` separately for each figure or variant. Use it for the overview, complex modules, teaser, quantitative chart images, qualitative layouts, and placeholders.

For each final asset:

1. Save the exact prompt and input-image roles under `figures/prompts/`.
2. Move the selected raster output into the project and copy the paper-consumed version into `paper/figures/`.
3. Record it in `figures/manifest.csv` with claim/module/result IDs, an `imagegen` invocation provenance JSON, and matching hashes for the generated and paper-consumed copies.
4. Inspect it for terminology, arrows, factual content, text fidelity, layout, color, column-width readability, and watermark absence.
5. Iterate through `imagegen` with one targeted change at a time; do not repair the artwork with another drawing tool.
6. For real qualitative outputs, require preservation of the input evidence. Reject any generated layout that changes the underlying observation.

### 7. Write the manuscript

Read `manuscript-writing.md`. Draft in this order after the idea and claim graph are frozen:

1. Method and Experiments
2. Related Work
3. Introduction
4. Abstract and Conclusion
5. Teaser and final page rebalance

Cover all relevant `must_cite` accepted top-venue work in Related Work. Write result-dependent Abstract and Conclusion claims under the successful-experiment assumption, using the same red result IDs and adjacent TODOs.

Place the teaser between authors and Abstract only when the official template permits it. Allow the sketch to exceed the official body limit by at most one page; move secondary material to the appendix and cite it from the main text. Keep core claims, method, and decisive evidence in the main paper.

### 8. Review, compile, and close gates

Read `quality-gates.md` and run:

```bash
python scripts/compile_paper.py <project-root>/paper --max-pages <official-limit> --allow-overrun 1 [--references-counted when venue.page_rules.references_counted=true] --report <project-root>/qa/layout_report.json
python scripts/todo_lint.py <project-root>/paper --mode sketch --registry <project-root>/qa/todo_registry.json
python scripts/validate_project.py <project-root> --mode sketch --report <project-root>/qa/sketch_validation.json
```

Perform an independent paper review for novelty positioning, method completeness, claim/experiment coverage, baseline fairness, citation support, terminology consistency, figure readability, anonymity, venue compliance, and page balance. Revise and rerun the checks.

Declare `SKETCH_COMPLETE` only when every non-experimental component is publication-quality and the only unresolved items are registered predicted results, qualitative placeholders, method alternatives, or a temporary-template update.

After real results arrive, replace every prediction, regenerate affected imagegen figures, rewrite Results/Abstract/Conclusion, run the submission-mode checks, and declare `SUBMISSION_READY` only with zero draft macros and TODOs.

## State invalidation

Use `scripts/state_manager.py invalidate <project-root> --cause <cause>` whenever inputs change:

- `idea`: invalidate literature positioning, council, claim graph, method, experiments, figures, and manuscript.
- `literature`: invalidate council decisions and all downstream claims.
- `resources`: invalidate feasibility, resource-dependent method choices, and experiments.
- `venue`: invalidate template, page budget, teaser placement, layout, and venue QA.
- `results`: invalidate result tables, quantitative/qualitative figures, Abstract, Conclusion, and final claims.

Only the orchestrator may merge canonical artifacts. Student agents write separate reports; literature shards write separate raw outputs; `imagegen` variants use versioned filenames. Never let concurrent agents edit the same canonical file.

## Final delivery

Deliver the project directory, compiled PDF when a TeX engine is available, venue decision, resource snapshot, audited literature corpus, idea-meeting reports, claim matrix, Method and experiment plan, imagegen prompts and raster assets, modular LaTeX source, TODO registry, and QA reports. Report the current state as `SKETCH_COMPLETE` or `SUBMISSION_READY` without overstating it.
