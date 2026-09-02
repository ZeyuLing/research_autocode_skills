# Clean-room review orchestration

Use this protocol for every initial review, fresh independent re-review, chair adjudication, and user-facing synthesis. “PDF-only” constrains both files and context: an actor can be contaminated by inherited conversation or memory even when it never opens a prohibited local file.

## 1. Core rule

The substantive review chain must be built from fresh, stage-specific contexts. The orchestration process that receives the user's request may locate and freeze the PDF, create directories, launch clean actors, verify checksums and required files mechanically, and relay the final clean summary. It must not author the reviewer-visible packet, a reviewer report, the AI-style assessment, the chair decision, or the final issue summary when it has access to prior conversation or author-side knowledge.

The operational prompt may provide only the stage role; exact allowlisted input,
actor-private scratch, and owned-output paths; the frozen PDF identity; the
neutral process-parameter record defined below; output language; exact
validator/materializer commitments and commands; and canonical generic
checklists or workflow instructions derived from this skill. “Only” therefore
permits those thesis-agnostic execution contracts, including the reviewer
six-question evidence self-check and SA acceptance standard, but never a
thesis-specific assertion supplied by Stage O. Reviewer-visible paths and
filenames must be neutral and must not disclose an author, project, laboratory,
paper title, or repository identity that is absent from the PDF; Stage O should
make a byte-identical frozen copy in a neutral round location. The prompt must
not convey substantive assertions about the thesis, remembered defects, desired
grades, author explanations, rebuttal arguments, or conclusions from another
task.

The AI-stage operational prompt must require inspection of every physical page and must name the complete authored-prose span: any rendered preface (`序言`/`前言`, `Preface`/`Foreword`), both abstracts, all authored chapter prose, substantive appendix prose, and substantive explanatory/contribution prose anywhere in front/back matter. Exclusions are span-level; metadata cannot exclude authored prose sharing its page. The prompt must not describe the corpus as beginning at the abstracts when a preface exists.

The clean-room evidence boundary is also a submission-obligation boundary. A substantive actor must not demand hidden author-side code, logs, hashes, manifests, commands, private member lists, controlled evidence packs, or exact-replay artifacts merely because those materials are unavailable in the packet. Their absence is outside the ordinary thesis review unless a verified governing rule requires them as formal submission components or the PDF explicitly claims an exact public artifact whose identity is necessary to decide a central claim.

The fresh-context boundary concerns **substantive task input**, not system-owned
execution metadata. A platform-generated capability or environment envelope that
contains only tool descriptions, operating-system/current-time metadata, permission
state, model/runtime availability, recommended-plugin metadata, non-substantive
retry/reconnect/transport/progress/capacity notices, and a neutral stage working
directory is infrastructure, not an inherited user/task turn. Current-
directory metadata qualifies only when it names the actor's neutral stage directory
inside the closed neutral round root and no path segment conveys an author, project,
laboratory, paper, repository, or thesis identity; Stage O must launch the actor from
such a directory. An identity-bearing or non-stage current directory is prohibited
context. Qualifying infrastructure is not listed in `received=[...]` or `opened=[...]`
and does not invalidate the canonical fresh-context declaration. This exception is
closed: if an envelope carries any thesis assertion, author explanation, requested
interpretation, prior finding, old-task summary, or instruction that changes the
review, it is substantive prohibited context and the actor must stop.

A tool result that the actor deliberately obtains from an exact allowlisted local
input or permitted public endpoint is evidence already authorized by the operational
prompt, not a later external message. A system-owned runtime notice is likewise not
a later substantive message when it contains no task-specific assertion. Generic
platform policy, safety, tool, transport, or runtime instructions remain permitted
system/developer instructions under the canonical fresh-context declaration even
when delivered after actor launch; delivery timing alone is not contamination. A
new user, task, or actor message that adds or changes an instruction, supplies a
thesis assertion, identifies unlisted material, or imports another context remains
a later substantive message. A later system/developer message is contaminating only
when it imports task-specific substance outside the exact operational prompt, such
as a thesis assertion, author explanation, prior finding, old-task content, or an
unlisted identity-bearing path. In either substantive case, stop and quarantine;
when the content boundary is uncertain, do not assume the exception.

Likewise, transport compaction during the actor's **same current clean turn** is
not a new input when the compacted state is derived exclusively from the exact
operational prompt, allowlisted inputs/endpoints, and that actor's own current-turn
reasoning or tool results. It is a continuation of the same clean process and must
not expand the allowlist or be reported as contamination merely because compaction
occurred. A summary inherited from before actor launch, or any compacted state that
contains another task, prior review, user explanation, unlisted artifact, or other
prohibited assertion, is contamination. When provenance is uncertain, stop and
quarantine rather than assume the exception.

Stage O may create `00-process-parameters.json` as a closed administrative envelope. It may contain only: round/retry ID; neutral frozen-PDF filename, SHA-256, mechanically measured physical-page count, and the actual ISO-8601 timestamp with timezone at which the neutral copy was frozen (`frozen_at`); degree level and academic/professional type; institution; school/department; discipline; expected submission year; artifact type (`author-copy` or `blind-copy`); requested review mode; output language; exact governing-rule URL(s); neutral copied local rule/template filename(s), official title(s), and original-byte SHA-256; decision-regime selection status; and a closed `actor_prompt_sha256` map computed from each exact operational prompt before launch. In production runner v1 the map contains exactly `P`, every degree-appropriate `R` actor, `AI`, the corresponding independent semantic-acceptance actors `SA-R1...SA-Rn` and `SA-AI`, `C`, and `S`; `H`, `V`, and every other actor are absent, and every value is a distinct 64-hex digest. Every `governing_local_files.neutral_file` basename is unique under Unicode-NFC, case-insensitive, Win32-portable comparison; trailing dots/spaces and other filesystem aliases are invalid. A governing-file basename and the frozen-PDF basename must also be mutually distinct and must not reuse any skill-reference basename, generated round-artifact basename (including `P####.png`), or closed-root directory name; otherwise basename-only input receipts are ambiguous. Stage O copies every allowlisted local rule/template into the neutral round under a neutral filename and verifies byte identity; only the orchestration log may retain the original path. These neutral process parameters may come from an explicit current operational request even when they are intentionally absent from a blind PDF. The envelope must not contain an original identity-bearing path, author name/identifier, technical assertion, implementation fact, revision explanation, old issue ID, desired conclusion, or any evaluation of the thesis. A missing field remains `unknown`; never infer it from an identity-bearing workspace path or old conversation.

After every operational prompt hash is known, Stage O exclusively writes the
final process envelope and runs the `seal-process` and `verify-process-seal`
lifecycle in Section 8 before Stage P is dispatched. The resulting
`orchestration/process-seal.json` and the external orchestration log's exact
metadata/process/seal hashes are process-control records only. They are outside
every substantive actor view and are never reviewer evidence or an `opened`
input. Any later process change invalidates the entire retry; the seal is never
deleted, overwritten, or regenerated in place.

For each substantive stage, require both:

- a **fresh-context declaration** whose own single-line value states that the actor received no inherited substantive user/thread/task turns beyond system/developer instructions and the exact operational prompt; the required canonical sentence remains unchanged and cannot be supplied elsewhere in the report as compensation. The infrastructure-metadata and same-clean-turn-compaction rules above define what is not a substantive inherited turn. Stage O launches each actor through the canonical ephemeral CLI launcher with user configuration/rules ignored and multi-agent disabled. The launched process itself is the process-bound actor and cannot create another task or model process. Its exact operational prompt carries the one contract rendered by `scripts/actor_prompt_contract.py` and must prohibit every collaboration API and Codex task/thread API named there; creating, forking, messaging, handing off, continuing, waiting on, inspecting, listing, opening, sharing, mutating, or activating another task/thread or actor; starting another model process through a shell; and relaying the prompt, assigned role, summaries, extracted content, or derived instructions to another actor/model/process. An attempted re-delegation fails actor identity and exact-prompt transport, so Stage O quarantines the complete retry;
- an **input-receipt and access declaration** whose own mechanically parsed single-line value uses this closed clause order exactly once: `received=[operational prompt]; opened=[...]; public_endpoints=[...]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated`. Duplicate keys, reordered or unknown clauses, trailing additions, and compensating prose elsewhere are invalid. It lists every local artifact opened in the actor's exact canonical order and every public endpoint accessed. Every artifact also records exact `Actor ID`, `Review round ID`, and `Review retry ID`. The operational-prompt SHA-256 is process-bound to that actor, not merely shape-checked.

The validator derives the canonical local allowlists rather than trusting prose. P opens the process envelope, `SKILL.md`, the ten required reference files in their documented order, the full and P-scoped validators, process-bound governing files, and the frozen PDF; P has no helper inputs and may not probe `helpers/`. Each R actor opens the ordinary rule/PDF prefix, its role-specific scoped-validator insertion, the seven current packet/policy/inventory artifacts, and no peer output. Doctoral R4/R5 and master's R3 use ledger-aware insertions that place the staged `materialize_owner_outputs.py` immediately after the full validator and before the shared/role scoped gates; every other R actor uses the ordinary reviewer gate. AI opens only the process envelope, `SKILL.md`, clean-room/report/AI rules, the full and AI-scoped validators, frozen PDF, manifest, and page inventory. Each `SA-*` actor opens only the rule/PDF/packet subset required for its target, process-bound local governing files, the frozen target output and owned ledgers/renders if any, and its scoped SA validator; it sees no peer report or prior-round artifact and has no live search or other public-network capability. A URL visible inside a frozen target artifact is inert target text, not SA endpoint authority. C opens the complete current rule/PDF/packet prefix, `rules/scripts/validate_review_bundle.py`, `rules/scripts/materialize_owner_outputs.py`, `rules/scripts/validate_semantic_acceptance_output.py`, `rules/scripts/validate_chair_output.py`, `02`--`04`, every current R report, the current AI report, and the hash-only `06-semantic-acceptance-gate.json`; it never opens helper sidecars, individual SA reasons, or the public network. S opens only the full validator, materializer, Stage-S scoped validator, and exact current summary-source sequence; it does not open the PDF, packet, ledgers `02`--`04`, helpers, SA files/gate, or prior artifacts. The materializer always runs inside the current fresh actor, reads only that actor's closed allowlist, and writes only the actor's explicitly owned deterministic projections before freeze: reviewer-owner Markdown; Chair `90`--`92` Markdown; or the three derived `93` outputs. A missing, extra, duplicated, reordered, or substring-only basename invalidates the stage. Public endpoints are a duplicate-free subset of the R actor's current policy/citation authority; P, AI, SA, C, and S use `[none]`. A nonempty `governing_rule_urls` array is process metadata, not endpoint authorization for P, AI, SA, C, or S. Production v1 may select an institutional regime at Stage P only from an official rule/template already frozen and hash-bound in `governing_local_files`; a URL without that frozen local evidence cannot establish the institutional regime.

If a truly fresh context is unavailable, do not claim a complete independent review. A single actor may perform a clearly labeled non-independent diagnostic pass, but its output is not an operational blind-review verdict and cannot be upgraded by disclosure alone.

## 2. Global prohibited context and artifacts

No packet builder, reviewer, AI-style assessor, or chair may receive, recall, search, or open:

- the current conversation or thread history beyond the minimal operational prompt, excluding only the qualifying system-owned infrastructure envelope defined in Section 1;
- hidden or visible memory, pre-launch or other-task conversation-compaction summaries, system-generated task summaries from outside the actor's same current clean turn, or assistant reasoning inherited from before actor launch; qualifying same-current-clean-turn transport compaction defined in Section 1 is not included in this prohibition;
- previous assistant answers, status reports, problem tables, diagnoses, or claimed closure lists;
- user explanations, corrections, rebuttals, intended interpretations, claimed implementation facts, or statements about what a companion paper/repository contains unless the same fact is visible in the frozen PDF;
- prior review rounds, reviewer reports, chair syntheses, issue ledgers, source-sync reports, provenance audits, figure-origin checks, implementation audits, or author responses;
- messages or artifacts from another current or completed actor unless that stage's input matrix below explicitly permits them;
- the thesis source tree, `.bib`, build and auxiliary files, Git state/history, old PDF versions, sibling repositories or papers, local code/config/checkpoints/logs, private data records, TODOs, and author-side research records.

Public authoritative sources are permitted only for two bounded purposes: verifying current governing institutional rules, and verifying the identity/status/support of citations already visible in the frozen PDF. They must never be used to discover or compare hidden companion artifacts or to search for uncited alternatives during this blind-review round. Accordingly, field-wide literature completeness and absolute priority are not fully verifiable here; reviewers assess positioning relative to works presented or cited in the PDF and narrow unsupported absolute novelty claims. A broader literature survey is a separately labeled non-review task and cannot alter the frozen blind-review grade.

Do not enumerate the parent review directory, neighboring review rounds, repository root, or unrelated workspace paths. Every actor uses exact allowlisted paths and a private stage scratch/output directory. Files created mechanically from the frozen PDF are permitted only when their checksum provenance is recorded.

## 3. Stage input matrix

| Stage | Must start fresh? | Permitted substantive inputs | Required outputs | Forbidden even if available |
|---|---|---|---|---|
| O — mechanical orchestrator | No | Current operational request; exact user-selected PDF path; filesystem needed to copy/hash/create empty paths | Neutral frozen PDF copy/identity; final `00-process-parameters.json`; external metadata/process/seal hash anchors; `orchestration/process-seal.json`; empty actor-view paths; exact-byte task dispatch log; mechanical completeness checks | Guessing the target PDF from mtime/name/history; authoring or editing any substantive review conclusion, packet interpretation, chair decision, or summary |
| P — packet and policy builder | Yes | Exactly one neutral frozen PDF; `00-process-parameters.json`; `SKILL.md`; all ten required reference files; read-only `rules/scripts/validate_review_bundle.py` and `rules/scripts/validate_stage_p_output.py`; frozen official local rule/template files named and hash-bound in the process envelope | `00-manifest.md`, `01-policy-basis.md`, neutral PDF-derived inventories/corpora | Public-network access, conversation history, user explanations, old reviews, helpers, peer/downstream outputs, neighboring paths, author-side files, substantive interpretations imported from the orchestrator |
| H — reserved future helper stage; unsupported by runner v1 | N/A | None in a production-v1 round | None | Any helper prompt, view, sidecar, provenance file, process-map entry, or claimed helper authority |
| R1--R5 / R1--R3 | Yes, separately for each reviewer | Neutral frozen PDF; `00-process-parameters.json`; clean packet/policy; `SKILL.md`; required panel/rubric/grading/report/audit rule files; the actor's exact full/scoped validator insertion; public authoritative sources needed only for citations visible in the PDF; own scratch/output path | Own comprehensive report and assigned ledger/sidecars; scoped-validator `PASS` before freeze | Other reviewers' work, helper sidecars, AI report, chair work, old rounds, conversation, user explanations, uncited-literature search, sibling/source artifacts |
| AI — standalone style assessor | Yes | Neutral frozen PDF; `00-process-parameters.json`; `SKILL.md`; clean-room/report/AI rules; full and AI-scoped validators; manifest and page inventory; PDF-derived prose corpus/mechanical statistics; own scratch/output path | `05-ai-style-assessment.md`; AI-scoped-validator `PASS` before freeze | Any reviewer/ledger/chair output, old AI report, conversation, prompts/generation history, author-side files |
| SA-R1...SA-Rn / SA-AI — independent semantic acceptance | Yes, separately for every frozen target | Exact target-specific neutral view containing the process/rules/PDF/packet subset, process-bound local governing files, only the frozen target report and its owned ledger/renders, exact target hashes, and the SA-scoped validator; URLs recorded in target artifacts remain inert text and confer no network authority | Private-view-root `SA-<target>.md` and `.csv` with `public_endpoints=[none]`; `PASS` permits Stage-O byte-copy into round `06-semantic-acceptance/`; `VALID-FAIL` preserves a hash-verified private failure pair and quarantines the retry without promotion; after all targets pass, hash-only `06-semantic-acceptance-gate.json` | Public-network access or treating a target-recorded URL as SA endpoint authority; creating/modifying/merging/grading/adjudicating findings; requiring concurrence on severity/weight/recommendation; rewriting an honest failure to seek PASS; peer reports; Chair/S; old rounds; conversation; source/Git/sibling artifacts; copying the target actor's rationale as acceptance evidence |
| C — chair adjudication | Yes | Neutral frozen PDF; `00-process-parameters.json`; clean packet/policy; `SKILL.md`; required clean-room/panel/rubric/grading/report/citation/AI rule files; `rules/scripts/validate_review_bundle.py`, `rules/scripts/materialize_owner_outputs.py`, `rules/scripts/validate_semantic_acceptance_output.py`, and `rules/scripts/validate_chair_output.py`; all current-round frozen R reports/ledgers and current AI report; hash-only current `06-semantic-acceptance-gate.json` | `90-chair-synthesis.md`, `91-revision-ledger.md` plus machine-readable sidecars, `92-new-evidence-or-experiments.md`, and `92-new-evidence-or-experiments.csv`; pre-Stage-S validator `PASS` before freeze | Public-network access; helper sidecars; individual SA reports/CSVs or failure reasons; conversation, user explanations/rebuttals, old rounds, source/Git/sibling artifacts, any non-current report or task summary; Stage-S/Stage-V/`95` artifacts |
| S — user-facing summary | Yes | Frozen PDF identity only, never the PDF bytes; exactly `00-process-parameters.json`, `SKILL.md`, `clean-room-orchestration.md`, `report-template.md`, full and Stage-S scoped validators, every current `Rn-comprehensive-review.md`, `05-ai-style-assessment.md`, `90-chair-synthesis.md`, `91-revision-ledger.md`, `91-revision-ledger.csv`, `91-ai-actionable-ledger.csv`, `92-new-evidence-or-experiments.md`, and `92-new-evidence-or-experiments.csv` | `93-user-facing-summary.md` plus the two lossless actionable-item sidecars; Stage-S scoped-validator `PASS` before freeze | Frozen PDF bytes, packet/`02`--`04`, helpers, conversation, user explanations, earlier assistant summaries, old ledgers/reviews, source/Git/sibling artifacts, new web research, new findings or re-adjudication |
| V — reserved future longitudinal stage; unsupported by runner v1 | N/A | None in a production-v1 round | None | Prior issues, author responses, old PDFs, old reports, comparison artifacts, longitudinal claims, or a V process-map entry |

The following Stage-V rules are design requirements for a future extension, not an enabled runner-v1 path. Such an extension could run only after a `fresh-rereview` current round had frozen all current R/AI/C/S artifacts. Stage O would copy every authorized prior input byte-for-byte into the new round's exact `stage-v-inputs/` directory without asking V to enumerate the prior round. The directory's file set would equal the report's complete prior allowlist; every entry would be a basename-bound regular file whose bytes match the declared SHA-256. Exactly one basename would end in `prior-issues.csv`; its closed CSV contract would define the complete prior-finding ID sequence, and the Stage-V closure table would have to match that sequence exactly. An author response would remain an optional locator only and could not replace or extend this ID master.

A future V actor would be process-bound as `actor_id=V`, including exact round/retry ID and its own `actor_prompt_sha256.V` value recorded before launch. Its receipt would be exactly `received=[operational prompt]`, `public_endpoints=[none]`, and this `opened=[...]` order: process envelope; `SKILL.md`; required clean-room/grading/report/AI/ledger rules; current frozen PDF; current page/bibliography/citation inventories and `02`/`03`/`04` CSV masters; all current R/AI/C/S frozen artifacts; then the hash-bound prior-issues CSV, optional additional prior artifacts, optional prior AI report, and optional seven-artifact regression baseline. No extra, missing, duplicate, substring, or reorder would be allowed. Such a Stage V would remain outside ordinary current-PDF adjudication and would require a new prompt builder, exact view, transport, validator, promotion, and runner phase before use. A global regression result would additionally require verified basename/hash identities for the prior PDF, page inventory and page ledger, bibliography inventory and ledger, and citation inventory and ledger. Without that complete baseline, every prior-row regression cell would be `not assessed` and the limitation would say `global regression not assessed`.

Stage P's manifest is a navigation packet, not a preliminary review. Its process-parameter field is bound to the final `00-process-parameters.json` byte hash; its degree/round/PDF/rule fields are deterministic envelope projections; its round root contains exactly the selected thesis PDF apart from hash-bound governing-rule PDFs; and its exact H1/H2/field sequence is closed. It records the canonical authored-prose physical-page set, including every independently rendered substantive preface page, while the page inventory still covers every physical page. It may record objective inventories and the thesis's explicitly stated questions/contributions with exact PDF anchors. It must not pre-adjudicate novelty, construct a consensus claim--evidence map, label weaknesses, or tell reviewers what to find. Before freeze or exit, P runs the scoped Stage-P validator until exit `0` and first nonempty stdout `PASS`; it corrects only its seven owned outputs, and returns any frozen-input/rule defect to Stage O for a clean retry. Each reviewer independently reconstructs the thesis argument and claim--evidence chain.

## 4. Filesystem isolation

Stage O creates a new, uniquely named and identity-neutral round directory for each frozen PDF. It copies the exact PDF bytes to an identity-neutral filename, verifies the copy's checksum, and gives substantive actors only that frozen path rather than the original workspace path. Stage O never writes a new round into an old round or copies old reports forward. The production-v1 validated round root is closed: it contains only the process envelope, frozen PDF, hash-bound governing files, documented current-round artifacts, `page-renders/`, the exact `06-semantic-acceptance/` file set plus its hash-only root gate, and the mechanical `95` report; it contains no `helpers/`, `stage-v-inputs/`, `94`, old artifact, or comparison input. Each SA runs first in a separate target-specific neutral view containing only its allowlist; after its scoped gate passes, Stage O byte-copies the frozen SA output into the closed round. An unexpected file, old report, extra directory, symlink, NTFS junction, mount/reparse point, or special entry at the root or inside an allowed subdirectory invalidates the bundle before any artifact is opened, even if no actor claims to have opened it. Stage O gives every concurrent actor exact input paths and a private scratch/output path; it never asks an actor to discover inputs by listing the round parent. A later-stage actor receives an explicit allowlist of current-round files and must not enumerate neighboring files. After all clean artifacts are frozen, Stage O may mechanically copy the complete bundle to a user-facing storage location; that destination is not reviewer evidence.

Before launch, Stage O records the frozen PDF SHA-256 and page count, sets or treats the frozen copy as immutable, and records the exact task-prompt bytes and their SHA-256, fresh-context launch mode, actor/retry ID, input allowlist, output path, and start time in an orchestration log outside the packet. The same external log stores the exact metadata SHA-256 returned by `initialize`, the precomputed final-process SHA-256 supplied to `seal-process`, the returned seal SHA-256, and the successful `verify-process-seal` result immediately preceding Stage P. Stage O launches the actor with those exact prompt bytes; recomputing a different prompt after dispatch is invalid. The bundle validator can prove that artifacts and the process envelope agree on the declared hash, but cannot observe API/task transport. The launcher-owned exact-byte record, disabled collaboration capability or equivalent no-child attestation, and, for Codex CLI, a passing complete-JSONL `validate_actor_transport.py` check therefore form the explicit process trust boundary; they are never thesis evidence. Every PDF-opening actor recomputes the PDF checksum at start and end. Stage S does not open the PDF and instead copies the frozen identity from the process/current sources into its required identity fields. PDF-derived sidecars record their own hash plus the source PDF hash. After every substantive stage, verify mechanically that:

Dispatch is the last message Stage O sends to that actor. Do not send progress
checks, reminders, corrections, cleanup instructions, or other operational
follow-ups after launch, even when they contain no thesis assertion. Stage O may
use task-status/wait mechanisms and read-only topology/hash checks that do not
inject a new actor turn. If any additional instruction is needed, interrupt and
quarantine the retry; encode the complete instruction in a newly hashed initial
prompt for a global clean retry. Every initial prompt also requires all Python
commands to disable bytecode writes with `-B` and/or
`PYTHONDONTWRITEBYTECODE=1`. An actor may remove its own current-turn cache before
freeze without prompting, but any retained `__pycache__` directory or `.pyc`
file is an unexpected isolated-view entry and invalidates the retry.

- the report names the same checksum;
- its fresh-context and input-receipt/access declarations are present and agree with the orchestration log;
- all required files exist and no `pending`/`unchecked` placeholder remains in a mandatory ledger;
- the actor did not report opening a prohibited path, context, or endpoint.

Before an actor freezes, it must also run the exact actor-scoped command in `ledger-validation.md` and obtain exit `0` with first nonempty stdout `PASS`. It may repair only its current owned outputs in that same fresh turn. A diagnostic attributable to an upstream artifact, process envelope, PDF, governing input, or staged rule stops the actor; it is never repaired by opening a peer or editing a frozen dependency. Mechanical validation cannot cure semantic incompleteness or contamination.

Production runner v1 does not create or consume Stage-H helpers. Any `helpers/`
path, `Hxx-provenance.json`, helper process-map entry, or `--helper-input`
argument therefore invalidates a production-v1 round. A future helper extension
would need a canonical prompt builder, exact private view, transport receipt,
provenance schema, recipient binding, validation gate, promotion operation, and
runner phase before any helper-derived sidecar could become an actor input; the
existing dormant helper-aware validator branches do not themselves authorize
that extension.

## 5. Independent semantic acceptance

After every R/AI target has passed its own scoped gate and been frozen in the
closed current round, but before the Chair is launched, Stage O starts one
different fresh `SA-<target>` actor for each target.
Stage SA is process quality control, not another reviewer: it does not create,
edit, merge, grade, reject, or adjudicate thesis findings. It asks only whether
the frozen target output is semantically supported, complete for its mandatory
scope, internally consistent, and admissible to the Chair. Mechanical target
`PASS` is input to this step, never a substitute for it.

The acceptance standard is reasonable support/admissibility, not concurrence.
“Supported and admissible” means reasonably grounded, not that the acceptor
personally concurs. A reviewer item remains admissible when concrete permitted
evidence supports it and its inference/action are proportionate, even if the
acceptor would choose a different severity, weight, emphasis, or final
recommendation. Normal scholarly disagreement about weighting does not fail a
target. Failure is reserved for a conclusion that lacks reasonable support,
exceeds the permitted evidence, omits decisive counter-evidence, is internally
inconsistent, or cannot be checked within the closed authority.

Each SA works in a target-specific neutral filesystem view and sees no peer
output. Ordinary reviewer acceptance covers all Gate A--I rows, every
finding/question/verdict, and every body chapter. `SA-R4` covers every `04`
PairID and independently checks proposition attachment, per-source support,
multi-source responsibility, source locator/content, external versus thesis-
local result boundaries, anti-template evidence, and exact report/ledger
reconciliation. `SA-R5` covers every `02` PageID and every
`03 (ReferenceID,Field)` row, visually opens every page PNG, and independently
checks the 17 bibliography fields against the rendered PDF and authoritative
records. `SA-AI` covers the complete authored-prose page/span corpus and all AI
findings without attributing authorship or AI use.

Each SA writes the closed Markdown/CSV pair at the root of its private
target-specific view, never directly into the round root, runs
`validate_semantic_acceptance_output.py` in its own fresh turn, and freezes one
of two completed outcomes. `PASS` with exit `0` permits Stage O to byte-copy the
frozen pair, without rewriting it, into the closed round's exact
`06-semantic-acceptance/` file set. `VALID-FAIL` with exit `3` freezes an honest,
mechanically valid failure pair only in the
private view. Stage O verifies and records that pair's hashes outside every
substantive allowlist, does not promote it or materialize a gate, and
quarantines the retry. The acceptor and Stage O must not overwrite or revise a
`VALID-FAIL` pair to seek PASS. `SemanticBasis` is
the acceptance actor's own concise check; it
cannot copy the target rationale or use a bulk template. Any target-level
`fail`, missing/duplicate coverage row, receipt/hash mismatch, prohibited input,
or semantically false acceptance declaration is a failed mandatory gate. The SA
must not modify the target. Because the target was already frozen, Stage O
quarantines the entire retry and performs a new global run after any reusable
rule defect is repaired.

The frozen SA operational prompt must literally name the two private-view-root
output paths and must explicitly prohibit an actor-writable
`06-semantic-acceptance/` directory. It must not present the finalized-round
promotion destinations as actor outputs. The target and any owned
ledger/render artifacts are already hash-frozen in the current round before SA
starts. After SA `PASS`, Stage O promotes only the exact SA pair; the target is
admitted to later Chair synthesis without being copied or rewritten. Any target
byte drift is a failed mandatory gate.

After every target passes, Stage O validates the complete SA set and runs
`materialize_semantic_acceptance_gate.py`. The resulting
`06-semantic-acceptance-gate.json` contains only round/retry/PDF identity, the
exact `00-process-parameters.json` byte hash, the closed current SA-actor prompt
hash map, target/output hashes, PASS values, and a global PASS—never semantic
reasons. In its private-file-free view, the Chair independently recomputes the
process hash, SA prompt-map projection, every C-visible target-artifact hash,
and coverage cardinality. Per-target acceptance Markdown/CSV hashes and R5
page-render hashes are only Stage-O transport commitments at this point: the
Chair checks their closed placement and 64-hex shape but cannot truthfully
recompute bytes it is forbidden to see.
After Stage S, the full Stage-O validator opens `06-semantic-acceptance/` and
must recompute every acceptance hash and semantic-set relation before the round
can pass. Stage S opens neither the gate nor any SA artifact, and no SA failure
reason or acceptance prose may enter a thesis finding, Chair adjudication, or
user-facing summary.

## 6. Clean chair adjudication

The chair is a new actor, not the orchestrator and not one of the reviewers. It begins only after every current-round reviewer and the AI assessor have frozen their work and the complete independent SA set plus hash gate have passed. Its `Exact current-round input allowlist` and receipt `opened=[...]` field must both equal the canonical ordered Chair basename sequence in `report-template.md`; an extra, missing, duplicated, or reordered item invalidates the Chair stage. It verifies all `S0`/`S1` findings and any grade-determining `S2` against the frozen PDF and governing evidence, reconciles the bibliography/citation ledgers, preserves minority evidence, and creates the sole adjudicated current-round revision ledger. Every current `Rn-Qxx` reviewer question is dispositioned exactly once in the Chair's stable-ID decision table; unresolved, not-verifiable, and disputed rows remain visible to Stage S. The gate lets the Chair verify current process/prompt/target/coverage consistency and carries Stage O's private-SA PASS/hash transport commitment; it does not let the Chair independently establish the private acceptance bytes or supply substantive adjudication. Final full validation must reopen and revalidate the private set.

The chair may reject unsupported reviewer findings, but it may not use a user explanation, remembered implementation fact, old review result, companion paper, or source repository to do so. It first applies the submission-obligation gate: a request for non-submitted author-side material is rejected as outside scope and does not enter an open ledger or Stage-S question table. Only when an in-scope thesis question survives that gate but the current packet cannot resolve it may the chair record `not verifiable from the submitted PDF`; it never fills the gap from conversation.

Stage O creates `<exact-stage-c-view-root>` as the direct `views/C` child and atomically copies exactly the canonical C allowlist into that one root. Skill references and `rules/scripts/*` are mounted inside the same tree; no separate rules root is permitted. The view has no page-render directory, no individual `06-semantic-acceptance/` directory, and no helper file or directory. Stage O retains the returned path/identity/metadata/byte input commitment outside the run. Before freeze and after every semantic Chair-source edit, the Chair runs `python rules/scripts/materialize_owner_outputs.py <exact-stage-c-view-root> C` to `MATERIALIZED`, inspects the rebuilt projections, and then runs `python rules/scripts/validate_chair_output.py <exact-stage-c-view-root>` to `PASS`. Production runner v1 supplies no helper arguments. The materializer preserves the Chair's semantic CSV/prose decisions while rebuilding deterministic `90`--`92` tables, allowlist, and one byte-consistent receipt across all three Markdown artifacts. The read-only gate proves the exact private-view file set and validates the six Chair outputs without reading validator-only final-round mechanics or private SA reasons. The Chair may correct only current `90`--`92` outputs in the same fresh turn and must rematerialize. After actor transport and scoped `PASS`, Stage O rechecks the original commitment and promotes exactly those six outputs to the finalized round with no replacement; any drift, extra entry, collision, or upstream failure invalidates the retry.

## 7. Clean user-facing synthesis

The final current-PDF problem summary is a formal stage of the skill, not free-form commentary by the orchestration process. Stage O runs Stage S in another fresh context after the chair freezes `90-chair-synthesis.md`, both `91` CSV masters and the `91` Markdown projection, and both `92` Markdown/CSV artifacts.

The summary must:

1. identify the frozen PDF checksum and current review round/retry IDs;
2. reproduce each independent reviewer category/recommendation and the chair's overall decision without changing them;
3. report the standalone AI-style judgment separately;
4. contain the complete fifteen-field lossless projection of every current open academic row, including priority, S0 subtype, evidence status, dependency, owner, and verification;
5. keep optional `S4` suggestions, the exact unresolved/not-verifiable/disputed Chair rows, and review limitations in separate clearly labeled sections;
6. reconcile exactly and in source order with `91-revision-ledger.csv`: every open required row appears once, no closed/old item is imported, and no field or issue is omitted, reordered, or invented;
7. reconcile the complete seven-field AI-actionable rows exactly with `91-ai-actionable-ledger.csv`, including verification, without assigning academic severity or defense consequences;
8. copy every R verdict, decision regime/source, persona emphasis, and whole-thesis rationale, the independent AI-style label/confidence/rationale, and the chair verdict/regime/source/rationale exactly into one actor table ordered `R1...Rn, AI, Chair`, with no newly written basis text; bind each value to its documented unique `##` section and require exactly one occurrence of the authoritative label within that section, so a duplicate section/label or an earlier lookalike label cannot redirect the copy; copy the chair's `Optional suggestions` and `Review limitations` sections exactly after whitespace normalization;
9. project `92-new-evidence-or-experiments.csv` completely and exactly, so every open N-remedy dependency remains visible;
10. record the exact expanded semicolon-separated current-round input basename sequence in canonical order, with no duplicate, reordering, ellipsis, or extra file, and trace every thesis statement to a current-round finding or exact PDF anchor; use only neutral compression, never a new technical inference;
11. state separate CSV and Markdown row counts for academic, AI, and N-evidence projections and use the canonical non-invention sentence as the exact value of the `Statement` reconciliation field. Before S freezes, an error confined to an S-owned deterministic projection may be rematerialized and revalidated in that same S turn. Any inconsistency in a frozen R/AI/C/`91`/`92` source, or any failure after S freezes, is a whole-retry quarantine condition followed by a new global retry; it never authorizes reopening or rerunning the frozen Chair alone.

The summary must not mention prior resolved problems, author explanations, source-sync or repository facts, implementation details invisible in the PDF, previous review labels, or an earlier assistant's view. It cannot soften, escalate, merge, or create findings on its own. Its H1 and nine H2 sections form a closed sequence; extra sections, appendices, prose outside the canonical section bodies, noncanonical identity/reconciliation fields, or hidden/raw Markdown blocks invalidate Stage S.

Stage S is not a conversation-aware formatting step. It is a clean actor inside this skill, and its frozen `93-user-facing-summary.md` is the only authoritative user-facing compression of the current round. The root/orchestrator may relay it and add artifact links, but may not reconstruct or supplement “remaining issues” from memory, previous turns, old reports, author explanations, repository facts, or another task summary.

Stage O creates `<exact-stage-s-view-root>` as the direct `views/S` child and atomically copies exactly the canonical S allowlist into that one root, including its three rule scripts under `rules/scripts/`; it retains the returned input commitment outside the run. No PDF, governing file, packet, `02`--`04`, page render, helper, SA artifact/gate, prior input, `94`, or `95` is present. Before freeze, Stage S runs `python rules/scripts/materialize_owner_outputs.py <exact-stage-s-view-root> S` to `MATERIALIZED` and then `python rules/scripts/validate_summary_output.py <exact-stage-s-view-root>` to `PASS`. The materializer constructs all three `93` outputs as current-source projections. After parsing only the process envelope, the scoped gate first enumerates entry names and metadata to require the exact unified S tree; a forbidden extra is rejected without opening its bytes. It then captures every allowed source/output by stable handle, serves all later CSV/Markdown parsing from that immutable byte set, and repeats the exact topology check at the terminal boundary. After actor transport and scoped `PASS`, Stage O rechecks the original commitment and promotes exactly the three `93` outputs with no replacement. The finalized round never contains transient skill/rule files. Stage O then runs the full validator and is the only stage permitted to write `95-bundle-validation.md`.

Distinguish later questions precisely:

- For “当前 PDF 的独立盲审还发现什么,” relay `93-user-facing-summary.md` only.
- Production runner v1 cannot answer “相对上一轮还有哪些未关闭” by creating or relaying `94`: it runs no Stage V and accepts no prior-round input. Relay only the current `93` as current-PDF evidence and state this boundary. A future separately implemented longitudinal extension may define its own isolated comparison artifact, but it is outside this runner and cannot be merged into the current blind-review result.

## 8. Contamination and recovery

Contamination or a failed mandatory gate is a process failure, not a thesis finding. `Discard` means mark invalid and quarantine from every substantive allowlist; it never means overwrite a frozen artifact or silently delete the audit trail. An actor may self-correct only before it freezes/exits, in the same clean turn, and only when the diagnostic is confined to its owned outputs. Once any affected actor has frozen/exited—or when the post-S full validator fails—the current bundle is immutable and invalid.

The current bundle contract has one global `round_id/retry_id`, not per-stage lineage. Therefore every post-freeze restart uses one new empty run root containing new `round/`, `views/`, and `orchestration/` children, together with a new round ID, retry ID, prompt set, and scratch/view set, then reruns the complete `O -> P -> R/AI -> SA -> gate -> C -> S -> full validation` chain against the same explicitly selected PDF bytes. Do not create a mixed bundle by copying apparently clean artifacts from the failed retry; even Stage-P artifacts bind the old process bytes, prompt hash, and retry identity. A failed SA is a process failure, never a thesis finding, and cannot be repaired by rerunning only its target or by passing its reason downstream. The old retry remains intact only as a quarantined audit trail.

Use `scripts/manage_review_retry.py initialize` to publish one new run container
as a single no-replace atomic rename. The run root is a direct child of the
explicit workspace and contains exactly the fixed administrative children
`round/`, `views/`, and `orchestration/` at publication; only the explicitly
named source PDF is copied into `round/`. Use the same tool's `quarantine`
operation to move that whole run root once to a new direct-child
`QUARANTINED-*` destination. Both operations require explicit absolute paths,
refuse replacement and link/reparse-backed paths, and fail closed. A hard crash
may leave a hidden staging container; `list-staging` is read-only and
`cleanup-staging` may act only when the tool can re-prove its complete closed
tree, hashes, and object identities. Despite its compatibility name,
`cleanup-staging` never physically deletes that tree: it atomically moves it to
a unique recoverable `QUARANTINED-STAGING-*` direct child. Stage O must not
replace these operations with recursive copy, partial rename, ad-hoc deletion,
or reuse of old artifacts.

After initialization, canonical prompt planning, and process sealing,
`scripts/stage_o_runner.py` is the sole production entry point for all remaining
transitions. Its append-only event chain and compare-and-swap head enforce the
fixed phase order and make every begun failure a whole-retry quarantine
condition. Production runner v1 admits exactly `P -> (all R + AI) -> (all SA) -> C -> S`;
H and V are rejected. P, C, and S are singleton phases. The R/AI phase and SA
phase must use `prepare-phase`, `launch-phase`, and `promote-phase`; the launch
operation runs the disjoint actor processes concurrently under one phase-level
BEGIN/COMMIT transaction, while promotion and the SA aggregate gate remain
deterministic barriers. It invokes `scripts/manage_stage_o_workspace.py` only as
an internal primitive: `init-r-scratch` creates an exact actor scratch;
`stage-round-inputs` installs transient rule authority; `stage-actor-view`,
`stage-sa-view`, and `stage-clean-view` publish exact closed private views;
`promote-actor-output` and `promote-clean-output` consume the original v3
launch UUID, launch-record hash, process/seal hashes, input commitment, and
terminal output commitment, rerun the actor-scoped gate, and copy only the
receipt-bound actor outputs with no replacement; `retire-round-inputs` moves
the transient authority to a recoverable external retirement directory before
the final full gate. Calling a primitive directly, supplying a post-dispatch
baseline, or observing a primitive PASS does not advance the authoritative
event chain and cannot authorize delivery. A partially created
staging/view/promotion or failed retirement is a whole-retry quarantine
condition, never permission for an in-place repair.

The initialization modes are explicit and mutually exclusive. Use
`--initial-run` only when there is no predecessor, or
`--replacement-for <old-round-id> <old-retry-id>` for a global retry. A typical
replacement invocation is:

```text
"<absolute-bundled-python>" -B scripts/manage_review_retry.py initialize --workspace <absolute-workspace> --run-root <absolute-new-run-root> --source-pdf <absolute-selected-PDF> --neutral-pdf-name thesis.pdf --expected-sha256 <64-hex> --expected-pages <positive-integer> --new-round-id <new-round-id> --new-retry-id <new-retry-id> --replacement-for <old-round-id> <old-retry-id>
```

Capture the successful initialization result's `metadata_sha256` in the
external orchestration log. Plan every actor prompt, write the final closed
process envelope exclusively, compute its exact byte hash, and seal it while
`views/` is empty and `round/` contains exactly that process file, the frozen
PDF, and any process-declared governing local files:

```text
"<absolute-bundled-python>" -B scripts/manage_review_retry.py seal-process --workspace <absolute-workspace> --run-root <absolute-new-run-root> --expected-metadata-sha256 <initialize-metadata-sha256> --expected-process-sha256 <final-process-sha256>
```

Store the returned `seal_sha256` outside the bundle. Do not stage Stage-P rule
inputs manually. `seal-process` is exclusive and pre-Stage-P only; it rejects a
nonempty actor-view tree, any extra/missing pre-Stage-P round entry,
process/metadata mismatch, link/reparse/hardlink, or external-hash mismatch.
The standalone `verify-process-seal` command is an optional read-only diagnostic
while the round is still in its pre-bootstrap state; it neither stages rules nor
authorizes Stage P.

Bootstrap the authoritative runner exactly once immediately after sealing. The
bootstrap transaction first proves the untouched pre-Stage-P topology, stages
the exact rule inputs itself, then internally calls the canonical
`verify-process-seal` implementation against the externally anchored process and
seal hashes before committing. Any pre-existing `round/SKILL.md` or
`round/rules/` entry makes bootstrap fail closed. Stage P is forbidden until
`BOOTSTRAP_COMMIT`; no substantive actor receives `orchestration/`. Then use
the transition token returned by each successful command as the
`--expected-transition-token` of the next mutating command:

```text
"<absolute-bundled-python>" -B scripts/stage_o_runner.py bootstrap --run-root <absolute-run-root> --skill-root <absolute-skill-root> --prompt-plan-dir <absolute-external-plan-dir> --control-root <absolute-external-control-root> --scratch-root <absolute-external-scratch-root> --retirement-root <absolute-absent-retirement-root> --python-executable <absolute-bundled-python> --codex-executable <absolute-codex-executable>

# Run once for P, once for the concurrent R/AI phase, and once for the concurrent SA phase.
"<absolute-bundled-python>" -B scripts/stage_o_runner.py prepare-phase --run-root <absolute-run-root> --expected-transition-token <previous-token>
"<absolute-bundled-python>" -B scripts/stage_o_runner.py launch-phase --run-root <absolute-run-root> --expected-transition-token <previous-token>
"<absolute-bundled-python>" -B scripts/stage_o_runner.py promote-phase --run-root <absolute-run-root> --expected-transition-token <previous-token>

"<absolute-bundled-python>" -B scripts/stage_o_runner.py close-sa-set --run-root <absolute-run-root> --expected-transition-token <previous-token>

# Run the same prepare/launch/promote triple once for C and once for S.
"<absolute-bundled-python>" -B scripts/stage_o_runner.py retire-rules --run-root <absolute-run-root> --expected-transition-token <previous-token>
"<absolute-bundled-python>" -B scripts/stage_o_runner.py finalize --run-root <absolute-run-root> --expected-transition-token <previous-token>
"<absolute-bundled-python>" -B scripts/stage_o_runner.py authorize-delivery --run-root <absolute-run-root> --expected-transition-token <previous-token>
```

`status` is read-only. Production orchestration uses the phase transactions for
every phase; `launch-phase` starts the R/AI processes and then the SA processes
in parallel. Per-actor transition commands are not exposed by the production
CLI, and the reducer rejects them for every multi-actor phase. A stale token,
out-of-order action, dangling
BEGIN, or any failure after BEGIN invalidates the retry; only whole-retry
quarantine is then admissible.

Quarantine always moves the whole container:

```text
"<absolute-bundled-python>" -B scripts/manage_review_retry.py quarantine --workspace <absolute-workspace> --run-root <absolute-current-run-root> --quarantine-run-root <absolute-new-QUARANTINED-name>
```

Exit status `3` with `commit_identity_failure` or
`committed_but_durability_uncertain`, `process_seal_commit_uncertain`, or
`sealed_but_durability_uncertain` means an atomic publication or exclusive seal
may already have committed and requires Stage-O inspection and quarantine of
the named run. It must never be treated as an ordinary unexecuted failure, as
permission to delete/recreate the seal, or as permission to reuse the retry.

Prompt construction and transport are closed rather than advisory. Stage O
uses `build_reviewer_prompt.py` for every R actor,
`build_semantic_acceptance_prompt.py` for every SA actor, and
`build_canonical_actor_prompt.py` for P, AI, C, and S. The latter accepts no
free-form body and deterministically renders the complete role, exact future
private view, opened order, output set, scoped gate, Python executable, and
empty external scratch. Before the final process is sealed, plan each P/AI/C/S
prompt with:

```text
"<absolute-bundled-python>" -B scripts/build_canonical_actor_prompt.py plan --process <absolute-stable-preplan-process> --round-root <absolute-future-round-root> --view-root <absolute-future-run-root>/views/<P|AI|C|S> --actor <P|AI|C|S> --output <absolute-external-final-prompt> --python-executable <absolute-bundled-python> --scratch-dir <absolute-external-empty-actor-scratch>
```

R and SA prompt builders, and the canonical P/AI/C/S builder, import the same
process-bound no-redelegation renderer from `scripts/actor_prompt_contract.py`;
no builder carries a private copy. Store every plan receipt and prompt outside
the run, copy all returned prompt hashes into the final process envelope once,
seal that process, and stage the actor's exact private input view. Immediately
before dispatch, reconstruct and verify each P/AI/C/S prompt with:

```text
"<absolute-bundled-python>" -B scripts/build_canonical_actor_prompt.py verify --run-root <absolute-run-root> --round-root <absolute-round-root> --view-root <absolute-run-root>/views/<P|AI|C|S> --prompt <absolute-external-final-prompt> --actor <P|AI|C|S> --expected-process-sha256 <sealed-process-sha256> --expected-seal-sha256 <process-seal-sha256> --python-executable <absolute-bundled-python> --scratch-dir <absolute-external-empty-actor-scratch>
```

The first nonempty stdout line must be `VERIFIED`. Stage O retains the planned
prompt and receipt hashes in the bundle-external control record and the runner
supplies those exact anchors to verification; reconstructing a newly
coordinated prompt cannot replace them. A manually assembled prompt, free-form
body, post-plan edit, H/V actor, or prompt passed through the wrong builder is
invalid. `build_bound_actor_prompt.py` is non-production compatibility code and
cannot authorize a runner-v1 transition.

When Codex CLI is the launcher, the accepted actor argv is the following closed
grammar:

```text
<absolute-codex-executable> [--search] exec <closed-exec-items-in-any-order> -
```

`<closed-exec-items-in-any-order>` contains exactly once each of `--json`,
`--ephemeral`, `--ignore-user-config`, `--ignore-rules`, and the
policy-respecting `--approve-for-me`; exactly one
`-C <actor-workspace>` pair; exactly one of `--disable multi_agent`,
`--disable=multi_agent`, or `-c features.multi_agent=false`; and, optionally,
at most once `--skip-git-repo-check`. In this Codex CLI, `--approve-for-me`
supplies the workspace-write sandbox itself and must not be combined with
`--sandbox`, `--sandbox=...`, or `-s`; this preserves workspace-write isolation
while avoiding the CLI's mutually exclusive flag error.
`--dangerously-bypass-approvals-and-sandbox` and every other approval/sandbox
bypass remain forbidden. If present, the sole `--search`
occurs before `exec`. The sole stdin marker `-` is last. No other flag,
configuration override, positional argument, subcommand, model/profile/image/
add-directory option, or second `exec` is permitted.

Stage O creates and fixes one unique canonical UUID launch ID, the prompt hash,
and the exact command before dispatch; it must never mint replacement anchors
around an existing log. It also creates one
bundle-external launch record with schema `thesis-review-actor-launch-v3`.
Before sending prompt bytes, its stable fields bind the actor, launch ID,
prompt path/byte count/SHA-256, sealed process SHA-256, process-seal SHA-256,
prelaunch input commitment, Codex executable path/SHA-256, exact argv plus
canonical argv SHA-256, cwd, actor workspace, PID, and intended JSONL path.
After process exit, Stage O completes that same launcher-owned record with the
integer process exit code, exact JSONL byte count/SHA-256, and the one thread ID
emitted by `thread.started`, plus a commitment over the exact ordered terminal
output paths, file identities, metadata, and bytes. The runner then freezes the
completed record SHA-256; no actor writes or opens this record.

For Codex CLI, Stage O performs that lifecycle with the production launcher:

```text
"<absolute-bundled-python>" -B scripts/launch_review_actor.py --actor <actor-id> --launch-id <preallocated-canonical-uuid> --prompt <absolute-external-prompt> --expected-prompt-sha256 <64-hex> --expected-process-sha256 <sealed-process-sha256> --expected-process-seal-sha256 <sealed-process-seal-sha256> --expected-input-commitment-sha256 <prelaunch-input-commitment-sha256> --workspace <absolute-private-actor-view> --cwd <absolute-private-scratch> --jsonl <absolute-external-jsonl> --stderr <absolute-external-stderr> --launch-record <absolute-external-record> --codex-executable <absolute-codex-executable> [--search]
```

The workspace and scratch must be distinct, non-overlapping safe local paths;
the prompt, logs, record, and executable are outside both. The launcher starts
the process with stdin blocked, writes and fsyncs the PID-bound pending record,
acquires Windows read leases that deny writes/deletes to every declared input,
rechecks the complete leased input tree plus still-open prompt/executable bytes
and path identities, and only then writes the exact prompt bytes to stdin. On
exit it requires the scratch to remain exactly empty, detects any pending-record
mutation, completes that same file, freezes terminal outputs, and invokes the
transport validator. The input leases remain held through actor exit.

The record is one JSON object with exactly these fields and no extensions:
`schema`, `actor`, `launch_id`, `prompt_path`, `prompt_bytes`,
`prompt_sha256`, `process_sha256`, `process_seal_sha256`,
`input_commitment_sha256`, `output_commitment_sha256`, `executable_path`,
`executable_sha256`, `argv`,
`argv_sha256`, `cwd`, `workspace`, `pid`, `exit_code`, `log_path`,
`log_bytes`, `log_sha256`, and `thread_id`. Paths and hashes are strings;
`argv` is the ordered string array; byte counts, PID, and exit code are JSON
integers. `argv_sha256` is SHA-256 over the UTF-8 bytes of that exact ordered
array serialized as JSON with `ensure_ascii=false`, no whitespace, and `,`/`:`
separators—for example, Python
`json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`.
This encoding is part of the schema rather than a launcher choice.

After the actor exits
and before accepting any owned output, run:

```text
"<absolute-bundled-python>" -B scripts/validate_actor_transport.py --log <absolute-external-actor-jsonl> --actor <actor-id> --launch-record <absolute-external-launch-record> --expected-prompt-sha256 <64-hex> --expected-launch-id <canonical-UUID> --expected-process-sha256 <64-hex> --expected-process-seal-sha256 <64-hex> --expected-input-commitment-sha256 <64-hex> --expected-output-commitment-sha256 <64-hex> --expected-launch-record-sha256 <64-hex>
```

The first nonempty stdout line must be `PASS`. The validator requires process
exit code zero, the closed current JSONL event schema, coherent item lifecycles,
and exactly one ordered `thread.started`, `turn.started`, and successful terminal
`turn.completed`, with `turn.completed` as the final newline-terminated JSONL
event. It treats only the closed, consecutive, monotonic WebSocket reconnect
sequence followed immediately by the one HTTPS-fallback notice and then a
nonempty completed agent message as recovered transport. Truncation; malformed
or blank events; unrecovered top-level stream/turn errors or error-item events;
launch/log/thread/prompt/process/seal/input/output/record binding drift; any collaboration or task/thread-
tool event; and any recognized shell or local-program attempt to start a nested
model client invalidate the actor and quarantine the whole retry. A terminal
failed command or MCP item is not itself a transport failure when its schema and
lifecycle are complete, the actor handles it locally, and the overall turn later
succeeds; it never excuses a prohibited delegation or nested-model attempt. An
attempted wait or message remains fatal even when no child output was produced.
The check proves consistency
against the launcher-owned record and every externally retained UUID, prompt,
process, seal, input, output, and record anchor;
it is not an independent operating-system attestation of PID or launch
freshness. A malicious launcher that forges the record, expected arguments, and
log together is outside this trust boundary. These limitations must not be
recast as thesis evidence or reviewer confidence. Another launcher must disable
collaboration/task-management tools or supply equivalent launcher-owned
no-child/no-forwarding transport evidence. Prompt/output hashes do not by
themselves prove the consumer process, and `workspace-write` is not claimed as
an operating-system read-capability boundary. On the supported Windows runner,
deny-write/delete leases close the declared-input swap window; the canonical
prompt, exact private view, no-neighbor-enumeration declaration, and transport
record form the stated non-adversarial read-scope boundary. If the runtime
exposes neither tool disablement nor equivalent transport evidence, do not
claim a complete independent round.

For every required SA target, run
`scripts/build_semantic_acceptance_prompt.py plan` before Stage P against a
stable preplan process object containing only the fields required by that
command. Insert all returned prompt hashes into the final process envelope once,
seal and verify that envelope as above, and then freeze the prompt bytes. After
a target-specific private view is staged, run `verify` with the required
`--expected-process-sha256 <sealed-final-process-sha256>` argument; it must
reconstruct the same prompt bytes and hash from the immutable stable projection
while loading its semantic validator from that view, and it must match both the
external Stage-O process anchor and Stage P's exact `Process-parameter file and
SHA-256` commitment in `00-manifest.md`. This prelaunch `verify` must run while
the SA output pair is absent. Stage O retains the returned exact
`input_commitment.sha256` in its bundle-external orchestration state; it must
not write that anchor into the private view or finalized round. Dispatch exactly
the already-planned prompt bytes through the v3 launcher. After transport and
scoped `PASS`, run `promote` with the same required process hash, the retained
prelaunch input commitment, and the original launch UUID, process-seal hash,
completed launch-record hash, and terminal output commitment. Promotion first
reruns the canonical transport gate against that same record and log; an SA
pair without this receipt cannot be copied into the finalized round. Promotion
rechecks every opened input's pathname, single-link file identity, metadata, and
bytes against the prelaunch commitment before and after its exclusive copy; it
never derives a replacement anchor from post-dispatch state. Its final joint
closure covers the complete private view, both copied destinations, the round
inputs, acceptance directory, prompt, and bound interpreter. On Windows, failed
copy rollback deletes only the authenticated object through its opened handle,
so a later object installed at the same pathname is preserved. After scoped `VALID-FAIL`,
hash-verify and preserve the private pair in the external orchestration record,
do not invoke `promote`, and quarantine the entire retry. Any attempt to replace
that pair with a later PASS is invalid. The seal and external log never enter
the SA view.

Use the same exact absolute bundled/workspace interpreter for the builder and
its required `--python-executable` argument throughout this lifecycle:

```text
"<absolute-bundled-python>" -B scripts/build_semantic_acceptance_prompt.py plan --process <stable-preplan.json> --view-root <absolute-pre-stage-P-SA-view> --target <R1|...|AI> --output <absolute-external-prompt-path> --python-executable <same-absolute-bundled-python>
"<absolute-bundled-python>" -B scripts/build_semantic_acceptance_prompt.py verify --view-root <absolute-closed-SA-view> --prompt <absolute-external-prompt-path> --target <R1|...|AI> --expected-process-sha256 <sealed-final-process-sha256> [--expected-input-commitment-sha256 <externally-retained-prelaunch-input-sha256>] --python-executable <same-absolute-bundled-python> [--require-sa-outputs]
"<absolute-bundled-python>" -B scripts/build_semantic_acceptance_prompt.py promote --view-root <absolute-closed-SA-view> --round-root <absolute-run-root>/round --prompt <absolute-external-prompt-path> --target <R1|...|AI> --expected-process-sha256 <sealed-final-process-sha256> --expected-input-commitment-sha256 <externally-retained-prelaunch-input-sha256> --launch-record <absolute-external-launch-record> --expected-launch-id <original-canonical-UUID> --expected-process-seal-sha256 <sealed-process-seal-sha256> --expected-launch-record-sha256 <externally-retained-record-sha256> --expected-output-commitment-sha256 <externally-retained-terminal-output-sha256> --python-executable <same-absolute-bundled-python>
```

The first, prelaunch `verify` invocation omits the optional input-commitment
argument and emits the only admissible anchor. Any later verification supplies
that exact value. On Windows, every SA control path uses its canonical local
drive-letter spelling; UNC (including administrative or arbitrary nested
shares), device-namespace, symlink/reparse, hardlink, NTFS 8.3, and NTFS named-
stream/alternate-data-stream aliases are forbidden. Every object in the closed
private view is also enumerated and rejected if it carries a named stream hidden
from ordinary directory traversal. The private view and prompt, and the private view and finalized round,
must use the same drive-letter namespace so an alternate mapped or substituted
drive cannot disguise overlap.

The executable must be the builder process's exact canonical `sys.executable`
with unchanged file identity. A bare `python`/`py`, shell or `PATH` lookup,
WindowsApps alias, non-Python file, different interpreter, or runtime drift is
fatal. `plan` binds the executable's canonical path and SHA-256 into the exact
prompt; that prompt hash is then bound into the final process envelope and its
seal. `verify` reconstructs the same bytes and both `verify` and `promote`
recheck that same runtime identity. Every validator command embedded in the
prompt is an exact JSON argument vector beginning with the bound executable and
`-B`, run with the exact environment override
`{"PYTHONDONTWRITEBYTECODE":"1"}` and without a shell.

For every degree-appropriate R actor, Stage O likewise uses the public
`build_reviewer_prompt.py` lifecycle. Before finalizing or sealing the process
envelope, reserve the still-absent exact reviewer-view path
`<absolute-run-root>/views/<Rn>` and create that actor's existing empty scratch
directory outside and non-overlapping with the complete run root. The view must
be the actor-ID direct child of the already existing `views/` directory; it is
published only after Stage P has frozen the canonical packet. Production v1 has
no recipient-helper input. The scratch basename is exactly
`stage-r-<lowercase-actor>-<24-hex-token>` under the
`thesis-review-stage-r-actor-scratch-v1` convention; the token binds the exact
absolute round root, round ID, retry ID, and actor. Use one exact absolute
bundled/workspace Python executable outside the run root. Then run:

On Windows, every Stage-R control path supplied to `plan` or `verify` must use
one canonical local drive-letter spelling. UNC, administrative-share, device-
namespace, symlink/reparse, hardlink, NTFS 8.3, and NTFS named-stream/alternate-
data-stream spellings are forbidden even when they identify the same object.
An arbitrary nested share can map directly below the run root without exposing
that relation in its lexical ancestors, so accepting UNC control paths cannot
satisfy the non-overlap proof. Every final-round source file and private-view
copy that the reviewer may open, together with their parent directories,
remains single-link/named-stream-free and identity/byte stable. The verifier
binds the private view's exact metadata-only topology before its first Stage-P
gate: it contains exactly the canonical opened-input files and only their
necessary parent directories, with every actor output still absent. Its last
filesystem-observing operation jointly closes the scratch, every final-round
source input, every private-view copy, process, prompt, interpreter, and the
complete private-view topology. A late file, directory, link, output, or peer
artifact in the private view therefore cannot pass. The finalized round is not
used as the reviewer workspace and is not exhaustively enumerated by this
verification; it remains the sealed Stage-O source store and may already
contain frozen peer outputs that are not copied into the current actor's view.
The complete metadata-only round topology is therefore deliberately outside
the reviewer-view closure; only the exact final-round source inputs are bound.

```text
"<absolute-bundled-python>" -B scripts/build_reviewer_prompt.py plan --process <stable-preplan.json> --round-root <absolute-run-root>/round --view-root <absolute-run-root>/views/<Rn> --actor <Rn> --output <absolute-external-prompt-path> --python-executable <absolute-bundled-python> --scratch-dir <absolute-empty-actor-scratch>
```

Production runner v1 requires the no-helper plan above exactly and rejects every
`--helper-input` argument or `helpers/` path.

Insert each returned exact R prompt hash into `actor_prompt_sha256`. Stage P may
then freeze its allowed current-round packet outputs. Stage O next
publishes the exact closed reviewer view from those final-round sources.
Immediately before R dispatch, require the same Python path and scratch path
together with the planned exact private-view path, and run:

```text
"<absolute-bundled-python>" -B scripts/build_reviewer_prompt.py verify --run-root <absolute-run-root> --round-root <absolute-run-root>/round --view-root <absolute-run-root>/views/<Rn> --prompt <absolute-external-prompt-path> --actor <Rn> --expected-process-sha256 <sealed-final-process-sha256> --expected-seal-sha256 <sealed-process-seal-sha256> --python-executable <same-absolute-bundled-python> --scratch-dir <same-absolute-empty-actor-scratch>
```

The verifier requires the finalized round to be exactly `<run-root>/round` and
the reviewer view to be exactly `<run-root>/views/<Rn>`. It invokes the
canonical real process-seal check before and after reconstruction, validates
the final-round frozen PDF bytes/page count and governing-file bytes, requires
the recipient-helper projection to be the empty sequence fixed by production
v1, and proves that every canonical opened input in the closed private view is
byte-identical to its corresponding final-round source.
It also rechecks that the same Python executable and empty, safe, actor-unique
scratch directory are bound into the canonical prompt and authenticates every
staged reviewer validator in the private view. It snapshots the canonical and
staged final-round
`rules/scripts/validate_stage_p_output.py`, requires identical hashes, and then
runs the staged gate with the exact argument vector `[<absolute-bundled-python>,
"-B", <staged-validate_stage_p_output.py>, <absolute-round-root>]`, environment
`PYTHONDONTWRITEBYTECODE=1`, and the still-empty actor scratch as working
directory; exit `0` and first nonempty stdout `PASS` are mandatory. Every
embedded reviewer gate command is an exact JSON argument vector whose paths and
root argument all resolve inside the exact private view, with the first two
elements equal to the bound Python path and `-B`. The prompt likewise binds its
frozen PDF, complete opened-input list, complete actor-owned output list, and
explicit Codex workspace (`-C`) value to that same private view; it contains no
final-round absolute path. Dispatch only the already-planned bytes with Codex
`-C <absolute-run-root>/views/<Rn>` after first-line `VERIFIED` with exit `0`;
a handwritten, hash-only, differently interpreted, helper-drifted, packet-unvalidated, or
seal-unverified prompt invalidates the retry. The canonical prompt carries the six-question
per-finding evidence test, whole-PDF remedy and counter-evidence search,
minimum-residual `Location`/`Observation`/`Required action`, and the rule to
downgrade a legitimately unresolved item to an exact-anchored Question or
otherwise delete it before freeze.

Stage O may read the failed validator report only to record orchestration metadata: failed validator hash/version, old round/retry IDs, old artifact hashes, mechanical error counts by owning artifact, earliest invalid stage, invalidation scope, and replacement retry ID. That quarantine log lives outside the reviewer-visible bundle and is forbidden to all new substantive actors. Old errors, snippets, IDs, reports, logs, conclusions, and findings never enter a new prompt or allowlist. General reusable corrections must first be encoded in the canonical skill/rules/validators, frozen and re-hashed, and then applied by a fully fresh retry.

If the primary/orchestration conversation contains old knowledge but performs only Stage O and relays the exact passing Stage-S artifact, that fact alone does not contaminate the clean round.

Every invalidation and restart must be recorded in an orchestration log outside the reviewer-visible packet. That log is process metadata only and is never an input to reviewers, chair, or final summary.

## 9. Completion gate

A round cannot be described as a complete independent blind review unless the final process was exclusively sealed and externally hash-anchored before P and `verify-process-seal` passed immediately before P dispatch. Stage P, all required R stages, AI, every target-specific SA actor, the hash-only SA gate, C, and S must have their required fresh-context declarations, exact input-receipt/access declarations, start/end PDF checksum agreement where the stage opens the PDF, all required outputs, and a passing mandatory scoped gate before freeze. Production runner v1 rejects H helpers and Stage V; therefore no helper, prior-round artifact, author response, comparison report, or longitudinal claim may appear in its prompt plan, actor view, final bundle, or summary. After S freezes, the runner must retire transient rules, the full validator must exit `0`, begin with a PASS result, and atomically write the current `95-bundle-validation.md`; otherwise quarantine the retry. Delivery is authorized only by the final runner transition. The final response should point to the frozen artifacts and relay `93-user-facing-summary.md` with only a minimal operational wrapper; it must not relay SA reasons or add conversation-derived findings.
