# Clean-room review orchestration

Use this protocol for every initial review, fresh independent re-review, chair adjudication, and user-facing synthesis. “PDF-only” constrains both files and context: an actor can be contaminated by inherited conversation or memory even when it never opens a prohibited local file.

## 1. Core rule

The substantive review chain must be built from fresh, stage-specific contexts. The orchestration process that receives the user's request may locate and freeze the PDF, create directories, launch clean actors, verify checksums and required files mechanically, and relay the final clean summary. It must not author the reviewer-visible packet, a reviewer report, the AI-style assessment, the chair decision, or the final issue summary when it has access to prior conversation or author-side knowledge.

The operational prompt may provide only the stage role, exact allowlisted input and output paths, the frozen PDF identity, the neutral process-parameter record defined below, output language, and the instruction to follow this skill. Reviewer-visible paths and filenames must be neutral and must not disclose an author, project, laboratory, paper title, or repository identity that is absent from the PDF; Stage O should make a byte-identical frozen copy in a neutral round location. The prompt must not convey substantive assertions about the thesis, remembered defects, desired grades, author explanations, rebuttal arguments, or conclusions from another task.

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
a later substantive message when it contains no task instruction or assertion. A
new user, task, actor, system, or developer message that adds or changes a task
instruction, supplies a thesis assertion, identifies unlisted material, or imports
another context remains a later substantive message and requires stop and quarantine.

Likewise, transport compaction during the actor's **same current clean turn** is
not a new input when the compacted state is derived exclusively from the exact
operational prompt, allowlisted inputs/endpoints, and that actor's own current-turn
reasoning or tool results. It is a continuation of the same clean process and must
not expand the allowlist or be reported as contamination merely because compaction
occurred. A summary inherited from before actor launch, or any compacted state that
contains another task, prior review, user explanation, unlisted artifact, or other
prohibited assertion, is contamination. When provenance is uncertain, stop and
quarantine rather than assume the exception.

Stage O may create `00-process-parameters.json` as a closed administrative envelope. It may contain only: round/retry ID; neutral frozen-PDF filename, SHA-256, mechanically measured physical-page count, and the actual ISO-8601 timestamp with timezone at which the neutral copy was frozen (`frozen_at`); degree level and academic/professional type; institution; school/department; discipline; expected submission year; artifact type (`author-copy` or `blind-copy`); requested review mode; output language; exact governing-rule URL(s); neutral copied local rule/template filename(s), official title(s), and original-byte SHA-256; decision-regime selection status; and a closed `actor_prompt_sha256` map computed from each exact operational prompt before launch. The map contains `P`, every degree-appropriate `R` actor, `AI`, `C`, and `S`; it contains `V` if and only if `94-post-freeze-prior-issue-closure.md` is launched, and every value is a distinct 64-hex digest. Every `governing_local_files.neutral_file` basename is unique under Unicode-NFC, case-insensitive, Win32-portable comparison; trailing dots/spaces and other filesystem aliases are invalid. A governing-file basename and the frozen-PDF basename must also be mutually distinct and must not reuse any skill-reference basename, generated round-artifact basename (including `P####.png`), or closed-root directory name; otherwise basename-only input receipts are ambiguous. Stage O copies every allowlisted local rule/template into the neutral round under a neutral filename and verifies byte identity; only the orchestration log may retain the original path. These neutral process parameters may come from an explicit current operational request even when they are intentionally absent from a blind PDF. The envelope must not contain an original identity-bearing path, author name/identifier, technical assertion, implementation fact, revision explanation, old issue ID, desired conclusion, or any evaluation of the thesis. A missing field remains `unknown`; never infer it from an identity-bearing workspace path or old conversation.

For each substantive stage, require both:

- a **fresh-context declaration** whose own single-line value states that the actor received no inherited substantive user/thread/task turns beyond system/developer instructions and the exact operational prompt; the required canonical sentence remains unchanged and cannot be supplied elsewhere in the report as compensation. The infrastructure-metadata and same-clean-turn-compaction rules above define what is not a substantive inherited turn. In Codex multi-agent execution, use `fork_turns: "none"`, and use an equivalent empty-context process elsewhere;
- an **input-receipt and access declaration** whose own mechanically parsed single-line value uses this closed clause order exactly once: `received=[operational prompt]; opened=[...]; public_endpoints=[...]; no unlisted substantive assertion was received; no prohibited context/artifact was used; neighboring paths were not enumerated`. Duplicate keys, reordered or unknown clauses, trailing additions, and compensating prose elsewhere are invalid. It lists every local artifact opened in the actor's exact canonical order and every public endpoint accessed. Every artifact also records exact `Actor ID`, `Review round ID`, and `Review retry ID`. The operational-prompt SHA-256 is process-bound to that actor, not merely shape-checked.

The validator derives the canonical local allowlists, rather than trusting prose. P opens the process envelope, `SKILL.md`, the ten required reference files in their documented order, process-bound governing files, and the frozen PDF. Each R actor opens that same rule/PDF prefix plus the seven current packet/policy/inventory artifacts and no peer output. AI opens only the process envelope, `SKILL.md`, clean-room/report/AI rules, frozen PDF, manifest, and page inventory. C opens the complete current rule/PDF/packet prefix followed by `02`--`04`, every current R report, and the current AI report. S opens only the exact current summary-source sequence. A missing, extra, duplicated, reordered, or substring-only basename invalidates the stage. Public endpoints are a duplicate-free subset of that actor's current policy/citation authority; AI and S use `[none]`.

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
| O — mechanical orchestrator | No | Current operational request; exact user-selected PDF path; filesystem needed to copy/hash/create empty paths | Neutral frozen PDF copy/identity; `00-process-parameters.json`; empty round/retry paths; task dispatch log with prompt hashes; mechanical completeness checks | Guessing the target PDF from mtime/name/history; authoring or editing any substantive review conclusion, packet interpretation, chair decision, or summary |
| P — packet and policy builder | Yes | Exactly one neutral frozen PDF; `00-process-parameters.json`; `SKILL.md`; all `references/*.md` needed by Stage P; allowlisted official public rule sources or frozen official local rule/template files named in the process envelope | `00-manifest.md`, `01-policy-basis.md`, neutral PDF-derived inventories/corpora | Conversation history, user explanations, old reviews, author-side files, substantive interpretations imported from the orchestrator |
| H — optional mechanical helper | Yes, separately per helper | Neutral frozen PDF; `00-process-parameters.json`; clean manifest; exact mechanical instruction; relevant skill rule; own scratch/output path | PDF-derived render/text/index/count sidecars only plus `Hxx-provenance.json`, each with source/output hashes, prompt hash, receipt/access declaration, tool/version, command/query, and limitations | Semantic judgments, visual dispositions, citation support/metadata verdicts, findings, grades, other actor outputs |
| R1--R5 / R1--R3 | Yes, separately for each reviewer | Neutral frozen PDF; `00-process-parameters.json`; clean packet/policy; `SKILL.md`; required panel/rubric/grading/report/audit rule files; public authoritative sources needed only for citations visible in the PDF; own scratch/output path; allowlisted helper sidecars | Own frozen comprehensive report and assigned ledger/sidecars only | Other reviewers' work, AI report, chair work, old rounds, conversation, user explanations, uncited-literature search, sibling/source artifacts |
| AI — standalone style assessor | Yes | Neutral frozen PDF; `00-process-parameters.json`; clean packet/policy; `SKILL.md`; `ai-style-audit.md`, `report-template.md`, and `clean-room-orchestration.md`; PDF-derived prose corpus/mechanical statistics; own scratch/output path | `05-ai-style-assessment.md` | Any reviewer/ledger/chair output, old AI report, conversation, prompts/generation history, author-side files |
| C — chair adjudication | Yes | Neutral frozen PDF; `00-process-parameters.json`; clean packet/policy; `SKILL.md`; required clean-room/panel/rubric/grading/report/citation/AI rule files; all current-round frozen R reports/ledgers and current AI report; permitted public authoritative citation/policy sources | `90-chair-synthesis.md`, `91-revision-ledger.md` plus machine-readable sidecars, `92-new-evidence-or-experiments.md`, and `92-new-evidence-or-experiments.csv` | Conversation, user explanations/rebuttals, old rounds, source/Git/sibling artifacts, any non-current report or task summary |
| S — user-facing summary | Yes | Frozen PDF identity; exactly `00-process-parameters.json`, `SKILL.md`, `clean-room-orchestration.md`, `report-template.md`, every current `Rn-comprehensive-review.md`, `05-ai-style-assessment.md`, `90-chair-synthesis.md`, `91-revision-ledger.md`, `91-revision-ledger.csv`, `91-ai-actionable-ledger.csv`, `92-new-evidence-or-experiments.md`, and `92-new-evidence-or-experiments.csv` | `93-user-facing-summary.md` plus the two lossless actionable-item sidecars | Conversation, user explanations, earlier assistant summaries, old ledgers/reviews, source/Git/sibling artifacts, new web research, new findings or re-adjudication |
| V — optional post-freeze longitudinal verification | Yes and separately labeled | Neutral current frozen PDF identity; `00-process-parameters.json`; required skill/rule files; canonical hash-bound current fresh-round artifacts; exactly one copied, hash-bound `*prior-issues.csv`; optionally copied, hash-bound author response and prior AI report; and, only for a requested full regression audit, copied prior frozen PDF plus prior page/bibliography/citation inventories and ledgers | `94-post-freeze-prior-issue-closure.md` and optional process-completion record | Treating an author response alone as closure; using an absent/hash-mismatched prior artifact; omitting or inventing a prior ID; inferring global regression without a full allowlisted prior baseline; retroactively editing current independent reports, grades, chair decision, or current clean summary |

Stage V is valid only after a `fresh-rereview` current round has frozen all current R/AI/C/S artifacts. Stage O copies every authorized prior input byte-for-byte into the new round's exact `stage-v-inputs/` directory without asking V to enumerate the prior round. The directory's file set equals the report's complete prior allowlist; every entry is a basename-bound regular file whose bytes match the declared SHA-256. Exactly one basename ends in `prior-issues.csv`; its closed CSV contract defines the complete prior-finding ID sequence, and the Stage-V closure table must match that sequence exactly. An author response is an optional locator only and cannot replace or extend this ID master.

The V actor is process-bound as `actor_id=V`, including exact round/retry ID and the optional `actor_prompt_sha256.V` value recorded before launch. Its receipt is exactly `received=[operational prompt]`, `public_endpoints=[none]`, and this `opened=[...]` order: process envelope; `SKILL.md`; required clean-room/grading/report/AI/ledger rules; current frozen PDF; current page/bibliography/citation inventories and `02`/`03`/`04` CSV masters; all current R/AI/C/S frozen artifacts; then the hash-bound prior-issues CSV, optional additional prior artifacts, optional prior AI report, and optional seven-artifact regression baseline. No extra, missing, duplicate, substring, or reorder is allowed. Stage V is optional and absent from ordinary current-PDF adjudication. If present, validate its exact five-section schema, prior artifact hashes, prior-ID row set, and current-CSV-derived completion checklist. A global regression result additionally requires verified basename/hash identities for the prior PDF, page inventory and page ledger, bibliography inventory and ledger, and citation inventory and ledger. Without that complete baseline, every prior-row regression cell is `not assessed` and the limitation says `global regression not assessed`.

Stage P's manifest is a navigation packet, not a preliminary review. Its process-parameter field is bound to the final `00-process-parameters.json` byte hash; its degree/round/PDF/rule fields are deterministic envelope projections; its round root contains exactly the selected thesis PDF apart from hash-bound governing-rule PDFs; and its exact H1/H2/field sequence is closed. It may record objective inventories and the thesis's explicitly stated questions/contributions with exact PDF anchors. It must not pre-adjudicate novelty, construct a consensus claim--evidence map, label weaknesses, or tell reviewers what to find. Each reviewer independently reconstructs the thesis argument and claim--evidence chain.

## 4. Filesystem isolation

Create a new, uniquely named and identity-neutral round directory for each frozen PDF. Copy the exact PDF bytes to an identity-neutral filename, verify the copy's checksum, and give substantive actors only that frozen path rather than the original workspace path. Never write a new round into an old round or copy old reports forward. The validated round root is closed: it contains only the process envelope, frozen PDF, hash-bound governing files, documented current-round artifacts, `page-renders/`, optional registered `helpers/`, optional Stage-V `stage-v-inputs/` plus `94`, and the mechanical `95` report. An unexpected file, old report, extra directory, symlink, NTFS junction, mount/reparse point, or special entry at the root or inside an allowed subdirectory invalidates the bundle before any artifact is opened, even if no actor claims to have opened it. Give every concurrent actor exact input paths and a private scratch/output path; do not ask it to discover inputs by listing the round parent. A later-stage actor receives an explicit allowlist of current-round files and must not enumerate neighboring files. After all clean artifacts are frozen, Stage O may mechanically copy the complete bundle to a user-facing storage location; that destination is not reviewer evidence.

Before launch, record the frozen PDF SHA-256 and page count, set or treat the frozen copy as immutable, and record the exact task-prompt bytes and their SHA-256, fresh-context launch mode, actor/retry ID, input allowlist, output path, and start time in an orchestration log outside the packet. Launch the actor with those exact prompt bytes; recomputing a different prompt after dispatch is invalid. The bundle validator can prove that artifacts and the process envelope agree on the declared hash, but cannot observe API/task transport; the orchestrator's exact-byte launch record is therefore an explicit process trust boundary, never thesis evidence. Every actor recomputes the PDF checksum at start and end. PDF-derived sidecars record their own hash plus the source PDF hash. After every substantive stage, verify mechanically that:

- the report names the same checksum;
- its fresh-context and input-receipt/access declarations are present and agree with the orchestration log;
- all required files exist and no `pending`/`unchecked` placeholder remains in a mandatory ledger;
- the actor did not report opening a prohibited path, context, or endpoint.

Mechanical validation cannot cure semantic incompleteness or contamination.

Every Stage-H helper actually used writes one `Hxx-provenance.json` containing: actor/round/retry ID; operational-prompt SHA-256; complete received-block and opened-input lists; fresh-context/input-receipt declaration; tool/version and exact command/query; frozen-PDF SHA-256 at start and end; each output sidecar path and SHA-256; limitations; and recipient-stage allowlist. The helper's receipt string is an exact projection of its structured `received_blocks` and `opened_inputs` arrays plus the canonical clean-access declarations; contradictory or additional prose fails validation. For every named recipient, append `helpers/Hxx-provenance.json` followed by that helper's declared `helpers/<output>` paths to the recipient actor's canonical opened list in helper-ID/output order. Every Markdown artifact signed by that actor must carry the same expanded receipt; a recipient that omits the helper paths proves non-consumption and invalidates the retained helper. A helper sidecar without matching provenance is prohibited input. Helpers not consumed downstream remain outside the final bundle.

## 5. Clean chair adjudication

The chair is a new actor, not the orchestrator and not one of the reviewers. It begins only after every current-round reviewer and the AI assessor have frozen their work. Its `Exact current-round input allowlist` and receipt `opened=[...]` field must both equal the canonical ordered Chair basename sequence in `report-template.md`; an extra, missing, duplicated, or reordered item invalidates the Chair stage. It verifies all `S0`/`S1` findings and any grade-determining `S2` against the frozen PDF and governing evidence, reconciles the bibliography/citation ledgers, preserves minority evidence, and creates the sole adjudicated current-round revision ledger. Every current `Rn-Qxx` reviewer question is dispositioned exactly once in the Chair's stable-ID decision table; unresolved, not-verifiable, and disputed rows remain visible to Stage S.

The chair may reject unsupported reviewer findings, but it may not use a user explanation, remembered implementation fact, old review result, companion paper, or source repository to do so. If the current packet cannot resolve a question, record `not verifiable from the submitted PDF`; do not fill the gap from conversation.

## 6. Clean user-facing synthesis

The final current-PDF problem summary is a formal stage of the skill, not free-form commentary by the orchestration process. Run Stage S in another fresh context after the chair freezes `90-chair-synthesis.md`, both `91` CSV masters and the `91` Markdown projection, and both `92` Markdown/CSV artifacts.

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
11. state separate CSV and Markdown row counts for academic, AI, and N-evidence projections, use the canonical non-invention sentence as the exact value of the `Statement` reconciliation field, and list any inconsistency as a synthesis failure requiring the chair or summary stage to be rerun.

The summary must not mention prior resolved problems, author explanations, source-sync or repository facts, implementation details invisible in the PDF, previous review labels, or an earlier assistant's view. It cannot soften, escalate, merge, or create findings on its own. Its H1 and nine H2 sections form a closed sequence; extra sections, appendices, prose outside the canonical section bodies, noncanonical identity/reconciliation fields, or hidden/raw Markdown blocks invalidate Stage S.

Stage S is not a conversation-aware formatting step. It is a clean actor inside this skill, and its frozen `93-user-facing-summary.md` is the only authoritative user-facing compression of the current round. The root/orchestrator may relay it and add artifact links, but may not reconstruct or supplement “remaining issues” from memory, previous turns, old reports, author explanations, repository facts, or another task summary.

Distinguish later questions precisely:

- For “当前 PDF 的独立盲审还发现什么,” relay `93-user-facing-summary.md` only.
- For “相对上一轮还有哪些未关闭” or whether an iterative loop is complete, relay current `93` and, if Stage V was run, `94-post-freeze-prior-issue-closure.md` in two clearly separated blocks. Do not merge or re-adjudicate them; state that `94` is longitudinal process evidence, not current blind-review evidence.

## 7. Contamination and recovery

Contamination is a process failure, not a thesis finding. `Discard` means mark invalid and quarantine from every substantive allowlist; it never means overwrite a frozen artifact or silently delete the audit trail. Every restart uses a new empty `round-id/retry-id` output and scratch path. The orchestration-only quarantine log records the contaminated stage, artifact hashes, invalidation scope, and replacement retry ID; no substantive actor may read it. Apply the earliest contaminated stage when determining scope.

- If Stage P is contaminated, quarantine the packet and every downstream artifact; restart P and all downstream stages in a new retry from the frozen PDF.
- If a Stage-H helper is contaminated before any downstream actor consumes its sidecar, quarantine that helper's provenance/sidecars and rerun H in a new retry. If any R or AI actor consumed a contaminated helper sidecar, treat every recipient as contaminated; under this strict policy, quarantine/restart the full R/AI panel and all downstream C/S artifacts in a new retry.
- If any reviewer or AI assessor is contaminated, the panel is not complete. Under this strict skill, quarantine all R/AI/C/S artifacts and restart all independent R/AI actors in a new retry from the still-clean packet before new chair adjudication.
- If the chair is contaminated, quarantine the chair outputs and user summary; restart the chair and S in new retry paths from the still-clean current-round reports. Reviewer reports remain frozen and unchanged.
- If only Stage S is contaminated, quarantine only its summary artifacts and regenerate Stage S in a new retry path from the still-frozen current-round artifacts. The grades and findings do not change.
- If the primary/orchestration conversation contains old knowledge but only performs Stage O and relays the exact Stage-S artifact, that fact alone does not contaminate the clean round.

Every invalidation and restart must be recorded in an orchestration log outside the reviewer-visible packet. That log is process metadata only and is never an input to reviewers, chair, or final summary.

## 8. Completion gate

A round cannot be described as a complete independent blind review unless Stage P, every Stage-H helper whose sidecar was used, all required R stages, AI, C, and S have fresh-context declarations, exact input-receipt/access declarations, start/end PDF checksum agreement, and all required outputs. Stage V requires the same declarations when run. The final delivery should point to the frozen artifacts and relay `93-user-facing-summary.md` with only a minimal operational wrapper.
