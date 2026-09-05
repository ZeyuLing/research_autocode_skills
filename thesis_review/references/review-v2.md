# Bounded PDF-only review, protocol v2

This is the complete active execution and output contract. Legacy v1 references
are not loaded by v2 actors. No live round may change its rules or validators.

## 1. Prepare and run

Use the bundled absolute Python executable, not the WindowsApps alias. Discover
it with the workspace-dependency tool. The runtime needs pypdf and Poppler's
pdftoppm. Pass the absolute Codex and pdftoppm executables. Preflight tests
imports, CLI isolation flags and one-page rendering before any reviewer launch.
Never silently install/upgrade libraries during a frozen round.

Commands (substitute actual absolute paths):

```text
python -B review_v2.py preflight --codex CODEX --pdftoppm PDFTOPPM
python -B review_v2.py init --pdf PDF --run NEW_NEUTRAL_DIRECTORY --degree doctorate --codex CODEX --pdftoppm PDFTOPPM
python -B review_v2.py run --run DIRECTORY
python -B review_v2.py status --run DIRECTORY
python -B review_v2.py retry --run DIRECTORY --actor R4
python -B review_v2.py summarize --run DIRECTORY
```

`init` requires a new neutral directory outside the thesis source tree, old review
roots, user skills and the source skill repository. It freezes only one PDF,
this reference and its own implementation. Optional `--policy` names one UTF-8
JSON file of verified neutral administrative rules: `degree_description`,
`institutional_rules` (each title, source URL, exact relevant provision),
`anonymity_pages` (physical page integers), `anonymity_exclusions`, and optional
`grade_map` mapping official categories to exact recommendations. It is NOT a
free-form thesis-specific reviewer prompt. Do not insert suspected issues,
preferred findings, author explanations or unpublished implementation facts.
Absent rules are disclosed, not invented. No institution is silently presumed.

Numerically labeled bibliography is supported. If text extraction or bibliography
boundaries are ambiguous, stop preparation with an operational diagnostic. Do
not interpret parser limitations as thesis defects or repeatedly rewrite the
parser. Author-year-only or scanned PDFs need a separately validated extraction
adapter before a complete review. The PDF itself remains the source of truth.

## 2. Budgets and recovery

- Default parallel reviewers: 2; never exceed the configured concurrency.
- Each ordinary reviewer, AI or Chair: 30 minutes maximum; exhaustive ledger
  owners: 60 minutes. Every actor: 10 minutes without meaningful tool/output
  progress. A log heartbeat or reconnect alone is not meaningful progress.
- Whole round: 4 hours of accumulated execution time, including resumed runs.
  These are execution safety limits, not a promise that any thesis finishes in
  that time. Defaults are frozen at initialization; increase only with explicit
  user authorization in a NEW round, never by resetting the current state.
- Maximum 2 fresh attempts per actor, persisted across CLI invocations. The
  runner never automatically retries; after the first failure it reports the
  failure and permits one explicit `retry`. Each attempt starts from the same
  neutral inputs, without the failed report, validator feedback about findings,
  prior messages or peer reports. A reviewer may self-correct its own current
  JSON at most twice before its first exit, using the local `check` command.
- If the clean Chair rejects an owner's audit quality, it names `repair_actors`.
  `retry --actor R4` may then retire only that accepted R4 and its downstream
  Chair/summary, preserve all other accepted peers, and run R4 in an empty context.
  Old outputs remain outside every new allowlist; no Chair feedback or suspected
  findings enter the replacement reviewer's prompt. Both actor/Chair attempt and
  accumulated time budgets still apply. This is same-round recovery, not a new
  independent round or an author-response re-review.
- Process failure, timeout and malformed output stop only that actor. Successful
  peers remain accepted. Other running peers finish within their own deadlines;
  a failed task is reported immediately, not hidden behind ordered future waits.
- No six-model second full audit. A fresh Chair checks every proposed issue
  (especially S0/S1 and claims of missing content), report-grade consistency,
  every recorded cross-ledger conflict, and a stable sample of clear entries.
  Suspicious samples cause targeted follow-up or an incomplete quality result,
  never manufactured acceptance. Do not rerun already valid peers to repair one
  owner's ledger. No raw trial reports enter the Chair's input view.
- A process crash leaves its running attempt `interrupted` on the next run; it
  consumes an attempt and is never silently adopted. If a child is still alive,
  report it and refuse to launch overlapping work until it exits or is safely
  terminated by its original supervisor. Persistent round time is conservative.
- Changed PDF, packet, rules, executable or accepted outputs stop the round as
  `blocked_integrity`. No automatic new run, hash rebasing or overwrite.
- Review progress and coverage are local process metadata, never thesis evidence.

## 3. Isolation and task graph

Preparation and summary are deterministic; only R1..Rn, AI and C are model tasks.
No P, SA, helper, summary-model or nested reviewer actor is launched.

Each attempt has its own workspace, neutral PDF-derived inputs, own outputs and
scratch. Prompts are generated by code from role and fixed rules, not hand-written
by the conversation-aware coordinator. Run Codex with ephemeral/no-user-config/
no-rules flags, multi-agent disabled, a private cwd and a clean CODEX_HOME with
authentication only (never copy user skills, plugins, histories or configuration).
Never log authentication contents or include that directory in an actor allowlist.
No user-model override is chosen by the runner.

Reviewers/AI receive only `inputs/thesis.pdf`, `inputs/packet.json`, per-page text
and PNGs, `inputs/policy.json`, `inputs/review-v2.md`, and the read-only local check
script. The Chair additionally receives accepted current-round reports and audit
JSONs, plus a deterministic acceptance selection. Reviewers never see those files.
No actor reads parent directories, source repositories, old attempts, conversation
history or other tasks. No delegation, subprocess model launch or task API.
The runner checks immutable input hashes before/after execution, keeps prompt and
transport records, rejects observed prohibited task/delegation tool use, and
requires an explicit access declaration. This is a non-adversarial isolation
contract, not a claim that workspace-write prevents every OS-level read. Unknown
or unsuccessful transport is not accepted. A recovered network reconnect followed
by a successful terminal turn is not by itself grounds to discard valid work.

## 4. Whole-thesis academic review

All R actors cover the entire PDF. Emphases:

- R1: methods, mathematics, experiments and scientific reasoning.
- R2: significance, contribution and literature positioning.
- R3: thesis architecture, scientific questions, chapter progression and synthesis.
- R4: evidence, disclosed reproducibility, integrity and citation attachment.
- R5: self-contained writing, format, bibliography and rendered layout.
- Master's R2 combines contribution and architecture; master's R3 combines the
  exhaustive duties and evidence/presentation emphasis.

All nine gates need concrete PDF anchors and independent judgments:
A policy/integrity; B thesis story; C positioning/literature; D methods/reasoning;
E data/protocol; F experiments/results; G PDF-visible reproducibility;
H writing/self-contained exposition; I figures/tables/equations/citations/pages.
The degree threshold is original coherent independent research for a doctorate,
sound research/engineering competence for a master's, and practical validation
plus transferable insight for a professional degree. Published papers alone do
not prove thesis coherence. Do not manufacture common representations or reusable
experiments merely to make independent chapters look unified.

Before each finding: identify what is visible, physical page, affected claim/rule,
supporting evidence, whole-PDF counter-evidence search, and the least sufficient
PDF-visible remedy. If the requested substance is elsewhere, omit the finding or
state only a real residual inconsistency. No finding quota. No hidden-evidence
wishlist, source-version comparison, missing-seed ritual or inference that an
unspecified training count equals one. Judge private-data and user-study disclosure
proportionately to the visible claims and verified submission obligations.

Severity: S0 procedural or integrity/foundational; S1 major scientific/structural;
S2 substantive bounded repair; S3 local non-blocking correction; S4 optional.
Remedy: W writing/format/citation; E incorporate necessary existing evidence into
the PDF; N genuinely necessary new experiment; P actual administrative decision.
Do not demand N where a natural bounded claim is sufficient. Do not prescribe
defensive rebuttal prose or inflate harmless omissions into scientific defects.

Default grade order: integrity/foundational S0 -> D; procedural S0, S1 or mandatory
N -> C; S2 -> B; otherwise A. Exact recommendations are those in SKILL.md. S4 does
not affect grade; unverified questions cannot lower it. Chair adjudicates, not
averages votes. An institutional grade_map overrides the default recommendation
mapping; rationale must identify the applicable verified rule.

## 5. Compact JSON outputs, not duplicated prose schemas

Write UTF-8 JSON only in `outputs/`. Markdown reports/tables are materialized by
the runner, so never manually duplicate JSON into thousands of Markdown rows.
Write checkpoints incrementally. Unknown fields may be recorded in `limitations`
but every mandatory coverage row must exist before acceptance. Never fabricate
verification to satisfy the schema. Use the local checker (maximum 3 invocations
including the first); a failure is operational, not a thesis finding.

Every actor's `report.json` has `actor`, `pdf_sha256`, `fresh_context: true`,
`inputs_used` (exact relative input file paths actually opened), `public_sources`
(actual HTTP(S) endpoints opened), `limitations` (strings), `rationale`, and
`findings`. No thesis assertions from outside the allowlist. Report prose is
Chinese unless the user explicitly selected another language before freezing.

Each R report also has `grade`, `recommendation`, `confidence` (high/medium/low),
`strengths` (strings), `gates` (exact A..I keys, each with `judgment`, `pages` and
`finding_ids`), `whole_thesis` (scientific problem, progression, contribution and
supported conclusion in coherent prose). Each finding has `id` (actor-Fnnn),
`pages` (nonempty physical page integers), `title`, `observation`, `evidence`,
`counterevidence_search`, `remedy`, `severity`, `remedy_type`, `gates` (A..I), and
`s0_type` if S0. All cited finding IDs must exist. No numerical pseudo-scores.

R5/master R3 additionally writes:

- `pages.json`: exactly one row per physical page: `page`, `status`
  (clear/issue/intentional_blank), `observation` (page-specific visible evidence),
  `finding_ids`. Every PNG must actually be viewed, not merely rendered. Inspect
  margins, clipping, whitespace, float stacks, orphan headings, captions as titles,
  arrows, small text, numbering and nearby continuity. Triage is not judgment.
- `bibliography.json`: exactly one row per `packet.bibliography` ID, `id`,
  `sources` (opened primary-source URLs), `fields` with each field named below,
  and `finding_ids`. Each field has `rendered`, `canonical`, `status`
  (verified/mismatch/unverifiable/na), `evidence` (specific record locator or
  concrete access failure). Fields: title, authors, year, venue, status, pages,
  identifiers, type, volume_issue, existence, correction_status. Authors must be complete
  and ordered; pages includes article numbers. N/A is allowed only for genuinely
  inapplicable pages/identifiers/volume_issue. Shared record retrieval is allowed;
  repeating a whole entry in every scalar is not an audit. Missing authoritative
  access means unverifiable, not fabricated/nonexistent. Published, accepted,
  preprint, withdrawn and retracted are distinct. Formatting aliases may be valid
  but cannot change work identity. Every mismatch needs a linked finding.

R4/master R3 additionally writes `citations.json`: one row for every packet
candidate ID, including numeric mathematical brackets and unpaired glyphs:
`id`, `kind` (citation/noncitation/ambiguous), `reason`, `sources` and `finding_ids`.
Mathematical intervals do not need a new parser rule: explain the visible role.
For `citation`, sources preserves every expanded number (including repetitions)
from `expected_sources`, and each item has `reference` (displayed number),
`proposition` (smallest attached PDF clause), `support`
(direct/partial/context/mismatch/unverifiable), `url`, `locator`, `evidence`
(short exact source quotation and explanation of the support boundary). Resolve
ambiguous extraction from the PDF; if it cannot be resolved, declare incomplete.
Read actual source content, not just a metadata/keyword match. R4 and R5 retrieve
independently; neither sees the other's result before freezing. Record a dangling
citation as a mismatch with a linked finding, not a packet-construction failure.

AI report has `signal` (low/moderate/high/indeterminate), `counterevidence`,
`disclaimer` explicitly stating this is not an AI-use/authorship/misconduct test,
`prose_pages` (all authored prose pages inspected, including substantive appendix
prose), and findings with id/pages/title/observation/evidence/remedy and `impact`
(material/local/optional). No academic grade. Repetition, mechanical transitions,
empty abstraction and unnatural translation require concrete recurring examples;
technical terminology or polished prose alone is not an AI-style defect.

## 6. Clean Chair and deterministic summary

C writes report.json with common fields plus `grade`, `recommendation`,
`decisions`, `acceptance`, `repair_actors` (empty unless targeted audit repair is
needed), and `quality_complete` boolean. It does not manufacture
new reviewer findings. `decisions` contains exactly one row per current R/AI
finding ID: `finding_id`, `status` (accepted/rejected/disputed), `reason`, and
`canonical_id` (same ID unless genuinely deduplicated to another accepted finding).
Every decision records PDF evidence and whether the remedy is a submission
obligation. Rejected/out-of-scope requests never appear as open problems. Keep
AI findings separate. Disagreement is not a validator failure.

`acceptance` has one row per `inputs/acceptance.json` item: `id`, `status`
(pass/fail/unverifiable), `basis` (specific PDF/source inspection). Selection
contains each actor's verdict, all report findings, all bibliography/citation mismatches, cross-owner
identity/support conflicts, and up to 12 stable clear rows in each audit. All
findings get a whole-PDF resolution check; all S0/S1 bases get direct inspection.
Do not re-open every clear bibliography field/page by default. If a sample reveals
template-filling or unsupported sign-off, set quality_complete=false and explain
the scope needing targeted review. An unverifiable source is an audit limitation,
not proof of misconduct. No pass-count substitutes for expert judgment.

The runner verifies coverage, report/grade/ID reconciliation, frozen hashes,
transport and Chair acceptance. It marks an incomplete audit as incomplete,
never as fully verified. Deterministic `summarize` reads only accepted current
reports, Chair decisions and coverage. It copies every grade/rationale and all
accepted/disputed findings into a single table with source IDs and physical
pages; AI stays separate, rejected findings and limitations remain transparent.
It cannot introduce external context or infer old-issue closure. The parent relays
this generated summary without a second conversation-aware substantive summary.

## 7. Tests, not full-thesis trial-and-error

Before activating a changed runner, run its unit/integration tests on synthetic
PDFs and fake subprocesses: hangs, idle streams, process exit, local retry,
remaining valid peers, input drift, budget persistence, contamination, incomplete
coverage, grade mismatch, acceptance and summary projection. A short real CLI
smoke may use a synthetic document; it is not an academic review-quality test.
Do not use a 172-page thesis as the first test of paths, locks or output schemas.
