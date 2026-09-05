---
name: thesis-review
description: Independent PDF-only review of Chinese CS/AI doctoral or master's theses, with five (doctoral) or three (master's) holistic reviewers, explicit A/B/C/D defense recommendations, exhaustive bibliography and citation checks, rendered-page review, a separate AI-style assessment, and context-isolated synthesis. Use for 学位论文盲审、博士论文外审、硕士论文预审、独立重新审稿 and thesis review.
---

# Chinese CS Thesis Review

## Active protocol: bounded v2

Use `scripts/review_v2.py` for new reviews. Read
[review-v2.md](references/review-v2.md) completely before running it.
The other orchestration, ledger-schema, prompt-builder and report-template
documents/scripts are **legacy v1**, not additional v2 requirements.
Do not mix v1's 15-actor chain, semantic-acceptance sidecars, sealed retry
rules or closed prose templates into v2. They remain only for old artifacts
and regression diagnostics. In particular, never restart a whole review
because a local actor fails, nor edit this skill during a live review.

The v2 default is seven fresh model tasks for a doctorate (R1–R5, AI, Chair)
or five for a master's (R1–R3, AI, Chair). PDF extraction/rendering and final
summary projection are deterministic processes, not model tasks. Independent
acceptance is done by the clean Chair against the PDF and findings; it is not
a second exhaustive citation/page audit. Mechanical coverage is still full.

## Evidence and authority

- Review exactly the user-selected, checksum-frozen rendered PDF. If the target
  is ambiguous, obtain its exact path; do not choose by mtime.
- All reviewer and AI tasks start with empty history, private inputs and outputs,
  no old reviews, author explanations, source tree, .bib, Git, sibling papers,
  implementation, checkpoints, logs or prior summaries. The conversation-aware
  orchestrator performs mechanics only and never writes academic conclusions.
- The only substantive thesis evidence is the PDF. PDF-derived text, images and
  inventories are navigation aids. Public primary sources may be opened only to
  verify works cited in that PDF; verified institutional rules may govern review.
  Neither public search nor source repositories authorize figure-origin audits.
- Do not demand hidden code, hashes, immutable reproduction manifests, private
  data members, logs or attachments not formally submitted. Judge experimental
  credibility from PDF-visible protocols, numbers and claim scope. An ordinary
  point estimate does not establish a single seed or single training run.
- Respect the selected review scope (including anonymity page range and excluded
  CV/cover material); do not turn the absence of a generic institutional approval
  into a defect. If binding rules are unavailable, disclose that limitation.
- Never infer fabricated citations merely from network failure. Verify title,
  ordered authors, year, venue/status, pages/article number and other applicable
  identifiers against actual primary-source records. Record unavailable fields
  honestly; do not fabricate checks to reach 100% verification.

## Academic standard

Every reviewer reads the whole thesis and judges significance, contribution,
technical correctness, evidence, coherent chapter progression, integrity,
writing and rendered presentation. Personas change emphasis, not jurisdiction.
Each report includes Gates A–I, strengths, whole-thesis rationale, findings with
physical-page anchors, counter-evidence search and minimum sufficient remedies.
There is no quota of negative findings or new experiments.

Use the exact default conclusions:
A — 同意答辩; B — 小修后可答辩;
C — 大修后重新送审，复审通过后方可答辩; D — 不同意答辩.
Verified institutional categories take precedence when supplied.
AI-style assessment is separate, with no academic grade, authorship inference,
misconduct conclusion or AI-detection percentage.

R5 (master's R3) owns every-page visual inspection and every-entry/field
bibliography checking. R4 (master's R3) checks every citation candidate,
repeated occurrence and source in a cluster. Retrieve a work once per owner
and reuse its record across fields; independently assess each attached claim.
Do not replace these complete owner audits with sampling. The Chair verifies
all reported findings and cross-ledger conflicts, plus a deterministic sample
of no-finding entries for quality control; sampling concerns only acceptance.

## Execution, recovery and delivery

The v2 reference specifies enforceable deadlines, per-actor attempts, immutable
same-round checkpoints, preflight and completion gates. Never interpret repeated
user “继续” as permission to reset attempt/time budgets. Status must distinguish
running, locally failed, stopped, incomplete and complete; show actual coverage,
not merely the existence of a process or a filled template.

A new independent round never reads any previous round's output. Resuming the
same unchanged round may reuse only its checksum-verified accepted outputs;
a failed reviewer gets a fresh private attempt, no previous findings or peer
reports. Transport/infrastructure errors are not thesis defects and do not lower
grades. Input contamination invalidates that actor and its downstream consumers;
PDF/rule drift stops the round, without automatic recreation.

Deliver the five/three complete reports, separate AI report, clean Chair
adjudication, audit coverage/limitations and a single consolidated issue table.
The final summary is generated only from the accepted current-round reports and
Chair JSON by a standalone deterministic command. Relay that file; do not
reconstruct the issue list from conversation memory. Incomplete checks must be
visible, and no incomplete run may claim “审稿完成” or “无问题”.

## Modification and re-review

Review is read-only unless the user asks to edit. Source-based revision is a
separate author-side task: preserve unrelated edits, make the minimum sufficient
change, compile/render and inspect affected plus adjacent pages. After float
changes check the whole PDF for displaced whitespace/clipping. Never invent
results or replace accurate contributions with defensive rebuttal wording.
A later independent re-review starts from a newly frozen PDF without old
findings; longitudinal comparison, if requested, is a separately labeled task.
