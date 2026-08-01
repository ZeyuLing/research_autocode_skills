# Paper Title Selection Protocol

Treat the project directory, user shorthand, and initial idea summary as working labels, never as the paper title. Create `title/brief.json` after the idea is frozen, then freeze the title only after the claim graph, Method, and experiment design are stable.

## Evidence packet

Generate titles from the current:

- canonical idea version and contribution list;
- closest-prior-work positioning and accepted `must_cite` corpus;
- target venue and track;
- claim--method--experiment matrix;
- Method terminology and the paper's strongest defensible capability.

Do not title the paper from the original prompt alone.

## Candidate generation

Create 8--12 materially different candidates spanning at least three framing families:

- `problem_capability`: foreground the unsolved problem and new capability;
- `method_identity`: introduce a memorable method name plus a precise descriptor;
- `insight_mechanism`: foreground the central planning insight or mechanism;
- `application_outcome`: foreground the scientifically supported use or behavior without claiming unmeasured superiority.

Each candidate records `candidate_id`, `title`, `framing_family`, linked `claim_ids`, rationale, and scores from 1--5 for faithfulness, specificity, novelty signal, clarity, memorability, search distinctiveness, and venue fit. Record `overclaim_risk` from 1--5, where lower is safer.

Reject candidates that:

- copy or closely imitate a discovered paper title;
- depend on a contribution absent from the frozen claim graph;
- claim performance, physical correctness, generality, or semantic fidelity that only predicted results could establish;
- use unsupported priority words such as *first*, *true*, *general*, or *human-level*;
- hide the actual research problem behind an unexplained acronym;
- confuse a component name, repository name, or project directory with the paper's contribution.

## Review and decision

Shortlist at least three candidates. Run two independent reviews:

1. `positioning`: check novelty signal, collision with prior titles, search distinctiveness, and venue fit.
2. `clarity_faithfulness`: check that a reader would infer the correct problem, method class, scope, and strength of evidence.

Let the Professor/orchestrator select one title after reading both reviews. Do not mechanically choose the highest arithmetic score. Prefer the shortest title that preserves the differentiating mechanism and claim boundary. A subtitle after a colon is useful only when it adds information.

## Required artifacts

Save all candidates in `title/candidates.json` with the current idea version, venue name/edition, timestamp, and scoring fields. Keep version changes in `title/history.jsonl`. Save the frozen decision in `title/decision.json` with:

- `status: frozen`, idea version, venue name/edition, and selected candidate ID/title;
- a shortlist of at least three candidate IDs and a concrete selection rationale;
- both review roles, verdicts, and notes;
- `collision_check` containing the audited corpus hash, check timestamp, exact-match result, and reviewed conflicts;
- input hashes for the literature corpus, claim matrix, terminology, Method specification, and venue decision;
- `frozen_at` timestamp.

Write the selected title into `paper/title.tex`, keep the active LaTeX template bound to that file, then complete `TITLE_FROZEN`. Treat `title/decision.json` as canonical; do not write the late title into `project.json`, because doing so would stale unrelated early-stage hashes. The selected title must match the decision and LaTeX title exactly after escaping.

## Revisit policy

After drafting the Abstract and Introduction, reconcile the title with the actual paper story before completing `MANUSCRIPT_DRAFTED`. Reopen title selection when the idea, closest prior work, claim boundary, Method identity, target venue, central supported capability, or real evidence changes. A wording-only revision creates a new title version and invalidates `TITLE_FROZEN` plus the manuscript consistency pass.
