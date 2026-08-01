# Idea Council Protocol

Use exactly two student agents and one Professor agent for each round. Give all three the same immutable `idea_vN`, `resource_snapshot`, and `literature_snapshot` identifiers.

Save those identifiers and their SHA-256 digests in `snapshot.json`. Begin each report with `Snapshot ID: <ID>` and end it with a standalone `Verdict: KEEP|REVISE|BLOCK` line.

## Independence

Run Student A and Student B in parallel. Do not reveal either student's current-round answer to the other. Start the Professor only after both reports are complete. Require paper `record_id` or resource evidence for every critical assertion.

## Student A: Novelty Reviewer

Produce `student_a.md` with:

1. the strongest novelty case;
2. the closest direct and analogical prior work;
3. the exact prior limitation and evidence;
4. whether the idea truly addresses that limitation;
5. differences from the newest relevant papers;
6. critical novelty blockers and counterexamples;
7. a minimally divergent revised idea when novelty is insufficient;
8. a verdict: `KEEP`, `REVISE`, or `BLOCK`;
9. confidence and evidence gaps.

Attempt to falsify novelty instead of merely defending it. State “not found within the audited corpus” rather than “no prior work exists.”

## Student B: Feasibility Auditor

Produce `student_b.md` with:

1. why existing methods fail on the target limitation;
2. the mechanism by which the proposed method could succeed;
3. required data, compute, storage, software, and evaluation access;
4. expected technical bottlenecks and failure modes;
5. whether current resources support the core claim;
6. the strongest feasible claim boundary;
7. a restricted idea when the original scope is infeasible;
8. a verdict: `KEEP`, `REVISE`, or `BLOCK`;
9. confidence and unresolved assumptions.

Do not consider whether experiments can finish before the venue deadline. Judge scientific and resource feasibility only.

## Professor: Adjudicator

Produce `professor.md` with:

1. a decision for every critical A/B objection;
2. candidate ideas ranked by novelty, feasibility, significance, and fidelity to the user's original direction;
3. the selected canonical idea and explicit changes from `idea_vN`;
4. rejected alternatives and reasons, kept outside the paper;
5. frozen problem statement and claim boundary;
6. distinct contributions mapped to claims, method components, and experiments;
7. open risks and required delta-search queries;
8. a verdict: `KEEP`, `REVISE`, or `BLOCK`.

Choose a defensible candidate; do not mechanically average incompatible proposals. Freeze only an idea with at least three genuinely distinct, evidence-backed contributions. If three cannot be supported without artificial splitting, revise the idea or keep the project blocked.

## Rounds and stopping

Run at most three rounds.

- Stop successfully when A has no critical novelty blocker, B has no critical feasibility blocker, and the Professor returns `KEEP`.
- After any `REVISE`, create `idea_vN+1`, run the required delta survey, and perform at least one confirmation round.
- If the third round still has a critical blocker, narrow the claim to the strongest viable version. If no viable version remains, set the project stage to `blocked` and explain why.
- Never hide an unresolved blocker by calling it a limitation in the manuscript.

## Canonical outputs

Store each round separately:

```text
idea/meetings/round_01/snapshot.json
idea/meetings/round_01/idea.md
idea/meetings/round_01/resources.json
idea/meetings/round_01/literature_manifest.json
idea/meetings/round_01/student_a.md
idea/meetings/round_01/student_b.md
idea/meetings/round_01/professor.md
idea/meetings/round_01/decision.json
```

`decision.json` records `snapshot_id`, three distinct agent IDs, both student completion timestamps, the later Professor start timestamp, `verdict`, `critical_blockers`, `contributions`, and the SHA-256 digest of each report. A `REVISE` round must be followed by a new literature snapshot produced by the required delta `ai-literature-survey` run.

Only the orchestrator writes the next canonical idea version and updates `state.json`.
