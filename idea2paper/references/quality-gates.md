# Quality Gates

Apply each gate to the current artifact versions. A passed report becomes stale when an upstream dependency changes.

## Venue gate

- Selected venue is user-specified or a registry-backed suitable top conference.
- Abstract deadline was open at selection time; full-paper deadline is used only when no separate abstract deadline exists.
- Official URLs, timestamps, timezone, track, page rules, anonymity, supplement, and AI-disclosure policy are recorded.
- Official current template is used, or the previous official template is visibly tracked with `TEMPLATE-UPDATE`.

## Literature gate

- `ai-literature-survey` standard artifacts exist.
- Coverage audit states sources, dates, snowball passes, blind spots, and stopping decision.
- Paper acceptance/open-source fields contain evidence or explicit `unknown` values.
- Directly relevant accepted top-venue work and novelty-threatening work are in `must_cite`.
- Every factual Related Work claim traces to a verified record.
- At least 30 included records, 10 core records, five coverage families, eight recent
  records, eight accepted/published records with evidence, and three novelty-risk
  closest works are present; excluded/off-topic padding does not count.
- Every core record has a reading-matrix extraction, at least 25 audited corpus papers
  are cited in the manuscript, and at least 20 are cited in Related Work.

## Idea gate

- Student A and B reports are independent and evidence-backed.
- Professor adjudicates all critical objections.
- No critical novelty or resource-feasibility blocker remains.
- Material revisions triggered a delta survey and confirmation round.
- Canonical idea, claim boundary, and contributions are versioned and frozen.

## Design gate

- Every contribution maps to limitation, claim, method component, experiment, metric, and paper location.
- Every core experiment tests a claim.
- Method defines the problem, notation, components, motivations, objective, and training/inference behavior.
- Baseline values have protocol and source provenance.
- Main, ablation, hyperparameter, robustness, and qualitative plans are proportionate to the claims.
- Every predicted value, predicted claim, method choice, qualitative placeholder, and template fallback uses an allowed macro plus adjacent TODO.
- `qa/todo_registry.json` is snapshot-portable: its root is `.` and every occurrence
  records a paper-root-relative POSIX path plus the exact current line and message.
  Validation compares the complete regenerated registry, not only the set of IDs.

## Figure gate

- Every figure was generated or edited through `imagegen`; no alternate figure backend was used.
- Every `figure` uses one or more registered imagegen rasters as its graphical subject and conforms to the finite raster-layout grammar; no visible TeX/math body, outer scale/resize wrapper, custom macro/input, or `tabular`/`array`/`rule`/`minipage`/box composition is disguised by a token-sized registered image.
- Prompt, inputs, output, selected version, linked claim/module/result IDs, and QA note exist.
- Terminology, arrows, values, label associations, and scientific content match the paper.
- Palette is low-saturation with readable contrast; final-size text is legible; no watermark exists.
- Real qualitative evidence was not altered by imagegen.
- Every `\QualPlaceholder` occurs inside a figure that contains a registered
  `type=qualitative` ImageGen raster linked by the same result ID. A conceptual
  placeholder declares its evidence status, visibly says it must be replaced with raw
  outputs, contains no simulated measurements, and passes the qualitative QA gates.
- Every teaser/overview has a claim-first brief and reference synthesis, records
  at least six composition directions spanning at least three archetypes and
  three targeted imagegen refinements, and passes independent Faithfulness,
  Conciseness, Readability, Aesthetics, Domain-evidence, Non-generic-composition,
  Three-glance-hierarchy, Novelty-salience, rectangular-efficiency, and
  compiled-final-size checks.
- Teasers use one dominant selling-point grammar rather than compressing the
  whole pipeline; pipelines have one dominant spine, subordinate auxiliary
  paths, no ambiguous arrow crossings, and visual weight proportional to novelty.

## Title gate

- 8--12 distinct candidates cover at least three framing families and link to frozen claims.
- At least three candidates were shortlisted and reviewed independently for positioning and clarity/faithfulness.
- The audited literature corpus was checked for exact or confusingly similar titles.
- The selected title is faithful, distinctive, venue-appropriate, and does not rely on predicted results or unsupported priority claims.
- `title/decision.json` and `paper/title.tex` agree, and the active LaTeX template consumes that title.

## Manuscript gate

- All required sections are complete and no internal work plan appears in rendered prose.
- Every `must_cite` paper is covered appropriately.
- Terminology, notation, claims, contributions, figures, tables, captions, Abstract, and Conclusion agree.
- Appendix movements are cited from the body and comply with venue rules.
- If a teaser is present, its rendered order is Title -> Authors -> Teaser ->
  Abstract through the audited `\maketitle -> \input{sections/teaser} ->
  \begin{abstract}` source order; it is not a float, no template-internal title
  hook is active, and the official venue template asset is unmodified.
- Double-blind metadata, acknowledgments, repository links, and self-citations comply with venue policy.
- LaTeX compiles without unresolved citations or references.
- `qa/layout_report.json` records a passing build, the correct body/reference counting rule, and body pages within the permitted budget.
- Every main-paper figure/table is rendered near its discussion and no body float appears on a page after Conclusion begins.
- Every figure, table, source-anchored `\captionof` unit, and teaser is stored as
  exactly one artifact in a dedicated `paper/figures/*.tex` or
  `paper/tables/*.tex` file and is referenced exactly once by `\input`; section
  and appendix prose files contain no inline artifact units, and no dedicated file
  groups multiple artifacts.
- Every body and appendix floating or source-anchored `\captionof` artifact has a unique label and is represented in the compiled AUX/page-density audit.
- In one-column mode, no page contains more than two floats; no adjacent appendix pages each contain at least two floats; no three-page run in either region contains at least two floats per page; the last two appendix pages do not contain a four-float/75%-share dump; and the final three appendix pages contain at most 70% of appendix floats when the appendix has at least four floats over four or more pages.
- Rendered artifact pages contain no leading blank region above 22% of the usable page. Nonterminal artifact pages also contain no trailing blank region above 22%, internal blank band above 16%, whole-page content block narrower than 50% of page width, tall local artifact region narrower than 46%, or severe one-sided occupancy. The final page may end naturally, but a final page containing a floating or source-anchored artifact must occupy at least 35% of usable height and leave no more than 45% trailing blank space; a prose-only final page must occupy at least 20% and leave no more than 70% trailing blank space. These gates prevent vertically centered artifact-only tails and accidental near-empty stubs without demanding filler prose. Treat the thresholds as failure detectors, not permission to stop visually checking smaller but conspicuous gaps.
- No top artifact interrupts a sentence across pages. The rendered audit must report zero `float_interrupted_hyphen` and zero `float_interrupted_sentence` findings; contact-sheet review remains blocking for any analogous visual break.
- A fresh compiler run removes only named `main.*` outputs, forces `latexmk` to rebuild, and records a project-build-local `main.log` path and matching SHA-256. The bound log contains no horizontal or vertical overfull box above 2 pt. Smaller overfull boxes remain recorded as visual-inspection warnings; a passing geometry scan cannot override a clipped equation or table reported by TeX.
- The active author `.tex` graph and every author-controlled local style contain no `\hfuzz` or `\vfuzz`; exact source locations are recorded in the layout report so TeX warnings cannot be suppressed silently. Register use inside an exact asset from the venue-bound official template archive is not classified as an author bypass.
- Unclamped rendered word/image coordinates do not exceed the PDF media box by more than 2 pt. This fallback catches page-edge clipping, while the compiler log remains authoritative for column-width overflow that has not crossed the page boundary.
- Tables do not create sparse single-column rows/columns merely because a wide or two-column design was reused. Split, transpose, resize, or rewrite them while keeping labels and comparison semantics legible.
- The active manuscript input graph contains no `\clearpage`, `\newpage`, `\pagebreak`, `\FloatBarrier`, or exact `[H]` figure/table placement; layout is fixed at the source rather than by forced flushing or forced-here floats.
- The sole Conclusion label, body/reference boundaries, bibliography, and appendix marker follow the canonical order; `idea2paper:start-appendix` immediately follows `\appendix`; and no body float occurs after Conclusion in source or rendered order.
- Manuscript inputs and figure/bibliography resources are static and paper-local; the audited input graph contains no TeX conditionals, dynamic file readers, page-register/output manipulation, external dependencies, untrusted local styles/classes, or non-exempt content hidden after the body-page label.
- The canonical `end-exempt` label immediately follows the optional AI-use statement, and the compiled exempt region spans no more than one additional page.
- The layout report uses the current schema, has `status=pass` only with `errors=[]` and compiler return code zero, records `pdfplumber` as a required dependency, binds both `main.log` and `main.aux` by canonical build path and SHA-256, re-derives material overfull boxes from the fixed 2 pt threshold, binds fuzz-register findings to current sources, independently recomputes source column mode, all AUX float-label pages, float distribution, rendered whitespace, float reading continuity, and media-box overflow against the hashed PDF, exactly compares those results with the report, and hashes every manuscript file and embedded figure resource under `paper/`.
- The independent PDF pass checks every page for float piles, premature section endings, large avoidable gaps, clipped tables, sparse rows/columns, and references/appendix contamination. Inspect the body and appendix as sequences: a locally acceptable page can still participate in an unprofessional multi-page float dump.

## Independent review

Save the independent report as qa/independent_review.md and include the exact standalone line "Review status: pass" only after all blocking findings are resolved.

Run an independent review after the first complete draft. Review novelty positioning, significance, method clarity, claim/experiment sufficiency, baseline fairness, alternative explanations, citation support, figure communication, writing flow, and venue compliance. Produce a prioritized correction list, revise, and rerun every affected gate. Do not let the drafting agent self-certify without this pass.

Use the installed `paperjury:paperjury` skill for this review. Run at least three isolated reviewer lenses on an immutable snapshot; reviewers must not see one another's reports or the shared ledger. New reviewer JSON uses `schema_version: 2`, and every blocking major is an object with a reviewer-scoped stable ID, a non-empty `evidence`/`evidence_anchor` containing an exact `file:line[-line]` or LaTeX label/ref that resolves inside the frozen snapshot, and a non-empty `required_fix`. Bind that exact ID to the ledger row for the same round/reviewer; never bind a new vague string by lexical similarity. Legacy compatibility is a one-time migration allowlist keyed by the exact immutable snapshot and every reviewer-file SHA-256; a directory named `round_07` receives no privilege by its number. The orchestrator semantically deduplicates findings, adjudicates them, applies only author-authorized in-scope edits, and records each blocker in the ledger with its round/reviewer/finding provenance; issues requiring real method/data work remain visible rather than being disguised as prose fixes.

Run at least two isolated rounds, with the final round clean. A later round receives a new manuscript snapshot but no earlier reports. Stop only after the clean round contains zero blocking-major and zero minor/fixable writing or claim-alignment findings, and no gate-blocking or unadjudicated major issue remains. Save at least three `qa/paperjury/round_XX/reviewer_*.json` files, the frozen snapshot, and a derived `round_report.json` with exact hashes for every round. Keep `LEDGER.json` in the official PaperJury `schema/meta/issues` format, regenerate `LEDGER.md` from it, and bind the passing `final_report.json` to both the current complete source hash and final review-visible snapshot hash. The validator recomputes reviewer verdicts, binds every historical blocker to a ledger row, and derives ledger gates; a hand-written `pass` is insufficient. Any material claim, result narrative, caption, or layout-driven prose change invalidates that pass.

The frozen snapshot must also contain a project-relative, path-resolvable copy of the
complete figure evidence chain: `figures/manifest.csv`, every referenced prompt/input/
candidate/output/QA/receipt/provenance/skill-snapshot artifact, and the exact
`paper/figures/` files consumed by LaTeX. Missing upstream evidence is a reproducibility
failure even when the selected raster exists.

## SKETCH_COMPLETE

Require:

- all venue, literature, idea, design, title, figure, and manuscript gates pass;
- compiled body is within official limit plus one page;
- all unresolved items belong only to `PREDICTED_RESULT`, `QUALITATIVE_PLACEHOLDER`, `METHOD_ALTERNATIVE`, or `TEMPLATE_UPDATE`;
- every unresolved `QUALITATIVE_PLACEHOLDER` is a rendered ImageGen asset with a
  complete evidence chain, not a promise to generate a figure later;
- `scripts/todo_lint.py --mode sketch` reports no untracked red text or TODO;
- `scripts/validate_project.py --mode sketch` passes;
- the final report enumerates every remaining item and affected claim.

The paper may contain complete predicted experimental prose and values in red. Call the state `SKETCH_COMPLETE`, not `SUBMISSION_READY`.

## SUBMISSION_READY

Require everything above plus:

- measured results and provenance are integrated;
- every predicted-result, qualitative-placeholder, method-alternative, and template-update macro/TODO is removed;
- affected imagegen charts, qualitative layouts, Abstract, Results, Conclusion, and contribution wording are regenerated or revised;
- current official template is used;
- exact official page limit is met;
- `scripts/todo_lint.py --mode submission` and `scripts/validate_project.py --mode submission` pass;
- final citation, anonymity, policy, and PDF visual checks pass.

If actual results weaken a claim, revise the claim graph and narrative. Never retain the predicted success story merely to satisfy the original sketch.
