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

## Figure gate

- Every figure was generated or edited through `imagegen`; no alternate figure backend was used.
- Prompt, inputs, output, selected version, linked claim/module/result IDs, and QA note exist.
- Terminology, arrows, values, label associations, and scientific content match the paper.
- Palette is low-saturation with readable contrast; final-size text is legible; no watermark exists.
- Real qualitative evidence was not altered by imagegen.

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
- Double-blind metadata, acknowledgments, repository links, and self-citations comply with venue policy.
- LaTeX compiles without unresolved citations or references.
- `qa/layout_report.json` records a passing build, the correct body/reference counting rule, and body pages within the permitted budget.

## Independent review

Save the independent report as qa/independent_review.md and include the exact standalone line "Review status: pass" only after all blocking findings are resolved.

Run an independent review after the first complete draft. Review novelty positioning, significance, method clarity, claim/experiment sufficiency, baseline fairness, alternative explanations, citation support, figure communication, writing flow, and venue compliance. Produce a prioritized correction list, revise, and rerun every affected gate. Do not let the drafting agent self-certify without this pass.

## SKETCH_COMPLETE

Require:

- all venue, literature, idea, design, title, figure, and manuscript gates pass;
- compiled body is within official limit plus one page;
- all unresolved items belong only to `PREDICTED_RESULT`, `QUALITATIVE_PLACEHOLDER`, `METHOD_ALTERNATIVE`, or `TEMPLATE_UPDATE`;
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
