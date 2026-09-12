---
name: paperjury
description: >-
  Review CS-conference papers using current venue rules, independent whole-paper
  reviewers with varied backgrounds and individual scores, and a fresh meta
  reviewer who owns the final recommendation. Also supports author-requested
  LaTeX edits and explicitly authorized review-revise workflows.
license: MIT
metadata:
  version: 0.6.0
  author: Yiran Wang
---

# PaperJury

An author-facing mock conference review, not an official review or an acceptance
prediction. Independent judgment matters more than the number of criticisms.

## Modes

- **REVIEW:** review / 审稿 / mock-review / re-review uses the protocol below.
  Review-only requests do not authorize paper edits.
- **DIRECT-EDIT:** locate the passage, use
  [writing-toolkit.md](references/writing-toolkit.md), check logic, apply only
  the requested change, and compile. A direct edit request authorizes that edit;
  ask only when a new meaning/scope decision requires author input.
- **AUTO / courtroom hardening:** explicit opt-in only. The legacy
  [v3 engine](references/review-engine-v3.md) and
  [auto policy](references/auto-mode.md) remain for issue adjudication/revision.
  They do not replace the independent conference review or its meta reviewer.

## Default conference review

Read [conference-review.md](references/conference-review.md) and
[reviewer-personas.md](references/reviewer-personas.md) completely.

1. **Live venue rules.** Resolve conference, year and track. Browse current
   official reviewer/AC guidance, actual review fields, score options and policy.
   Save sources and retrieval date. Clearly label historical/provisional fallback
   fields when the current form cannot be verified. Never silently reuse a scale.
2. **Paper-only packet.** Freeze the anonymous compiled PDF, supplied appendix,
   figures, tables and references, plus faithful text/renders and venue rules.
   Exclude source comments, code, chat, prior reviews, ledgers, private experiment
   explanations and title suggestions. Do not read old reviews before this round.
3. **Diverse holistic reviewers.** Default to three plausible backgrounds with
   different career stages and research experience. Every reviewer reads the
   whole paper and assesses every venue criterion. Expertise is a tendency, not
   a fence. Announce the panel; do not pause unless a material choice is missing.
4. **Independent full reviews and scores.** Start fresh agents with no inherited
   chat, e.g. `fork_context:false`. Give each the same packet, rules and only
   their persona. Each provides strengths, weaknesses, questions, venue-required
   dimension scores, overall recommendation and confidence. No target score,
   forced disagreement, issue quota or parent-supplied concerns.
5. **Integrity checks.** Check hashes, allowed scores, required fields, paper
   anchors and honest coverage. Return incomplete delivery to its reviewer with
   the whole paper available. Do not replace their judgment with parent analysis.
6. **Fresh meta reviewer.** A separate new agent receives the same full paper,
   rules and complete unedited reviews. No parent summary, chat, author answers,
   old scores or ledger. They alone synthesize disagreements, final verdict,
   final score and priorities; no mechanical average. If the real venue has no
   numeric meta score, label this number a simulation summary on the stated scale.
7. **Relay, do not take over.** Present individual scores and the meta review,
   attributed to its author, with full reports. The parent handles transport and
   process notes; it must not add/suppress/reverse findings using author context.
   Any subsequent author-informed editing discussion is explicitly separate.

## Tooling and boundaries

`scripts/conference_packet.py` prepares PDF-only packets, generates isolated
role prompts, and validates outputs. It does not generate reviews or start agents:
use the host's real fresh-agent mechanism. See `--help`.

Each reviewer may read only exact packet inputs and their own output directory.
The meta reviewer additionally receives the raw current-round reviews. A prompt
allowlist is not an OS sandbox; state the actual isolation used. Restart a
contaminated role cleanly rather than asking it to forget leaked context. If
independent agents are unavailable, report the limitation; do not simulate their
independence inside one conversation.

- Judge paper claims using paper evidence; missing detail is not proof of a bug.
- Paper-only reviewers do not search the web, source tree or parent directories.
  Background knowledge guides questions, not unverified paper-specific allegations.
- Never fabricate results, citations, experimental history or author rebuttals.
- Follow AI/confidentiality policy for actual official reviewing. This simulation
  must not be represented as a human-written official assessment.
- No auto edits, official review submissions or score-target rerun loops in REVIEW.
- Ledgers and house-style memory belong to author-side editing, never fresh reviews.
- Resolve paths at runtime. Do not commit private papers, review packets, chats or
  credentials into this generic skill. Publishing the skill needs user authority.
