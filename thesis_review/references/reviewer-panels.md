# Independent reviewer panels

## Independence protocol

Follow `clean-room-orchestration.md`. Every reviewer starts in a separate fresh context with no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt. In Codex multi-agent execution, use `fork_turns: "none"`; the prompt supplies only the role, prompt/allowlist hashes, neutral process envelope, exact allowlisted paths, frozen PDF identity, and output path.

All reviewers receive the same frozen **PDF-only reviewer-visible** evidence packet and governing-rule record. The packet contains one rendered thesis PDF, neutral PDF-derived inventories, and public authoritative sources opened only to verify citations visible in that PDF. Before submitting an individual report, a reviewer must not read, receive, or recall:

- the user's explanations, corrections, rebuttals, desired interpretation, or claimed facts outside the PDF;
- conversation/thread history, memory or compaction summaries, earlier assistant answers/tables, or messages from other current/completed tasks;
- another reviewer's notes or report;
- the chair's emerging synthesis;
- the author's response to an earlier round or any prior issue ledger during the fresh independent re-review pass; these may be opened only in a separately labeled post-freeze issue-closure verification pass after every fresh report is frozen;
- issue labels designed by another reviewer.
- the thesis source tree, `.bib`, build logs, auxiliary files, Git history, old commits, diffs, blame output, prior artifact versions, or source/provenance audits;
- sibling paper repositories, unpublished drafts, internal configs/logs, TODOs, private data documentation, or author declarations.

The same PDF-only boundary limits proposed remedies. Reviewers judge experimental credibility from the thesis's visible method, protocol, numbers, internal consistency, and claim scope. They do not turn the absence of code commits, environment locks, full commands, file/checkpoint hashes, member-level hashes, immutable manifests, controlled evidence packs, internal logs, or confidential raw data into findings or questions, except when a verified governing rule makes an item a formal submission component or the PDF explicitly makes an exact public-artifact claim that is central to the conclusion.

Use separate output files and private scratch directories. If reviewers share a filesystem, give each reviewer exact input paths; it must not enumerate the parent round, neighboring rounds, repository root, or unrelated workspace paths. Every reviewer must include a fresh-context and input-receipt/access declaration covering the prompt hash, all received blocks, opened artifacts, and public endpoints. Access to any prohibited context or artifact invalidates the round and requires the recovery defined in `clean-room-orchestration.md`; relabeling it as author-side evidence does not cure the violation. Batch execution is acceptable; evidence leakage is not.

Before freezing or exiting, every reviewer runs the exact role-scoped gate in `ledger-validation.md`: ordinary reviewers use `validate_reviewer_output.py`; doctoral R4 and R5 use their ledger-aware gates; master's R3 uses the combined owner gate. The actor may correct only its own current report and assigned ledgers/renders before freeze. A failure attributable to the packet, process envelope, PDF, governing rules, staged validators, or another actor's artifact stops the actor and triggers Stage O's global retry; no reviewer may patch an upstream or peer artifact. A mechanical `PASS` is mandatory but never substitutes for the whole-thesis semantic and visual judgment.

Do not infer an unreported run count from result formatting. If one row reports `mean ± dispersion` and another reports a point estimate, state only what each row visibly reports. Unless the PDF explicitly gives the repeat count, the latter is `not stated in the PDF`, not single-run or single-seed.

Each reviewer reads the whole thesis. The persona changes priority, depth, skepticism, and professional viewpoint; it never narrows the reviewer to one topic.

The `Persona assignment` field is a closed machine-validated value, not free prose. Use the following exact value for the active degree level and reviewer index; put any richer description only in `Persona emphasis`:

- doctorate R1: `R1 technical/methods/experiments`
- doctorate R2: `R2 contribution/novelty/positioning`
- doctorate R3: `R3 thesis architecture/narrative`
- doctorate R4: `R4 evidence/reproducibility/integrity/citation`
- doctorate R5: `R5 format/bibliography/layout`
- master's R1: `R1 technical/methods/experiments`
- master's R2: `R2 contribution/positioning + thesis architecture/narrative`
- master's R3: `R3 evidence/integrity/citation + format/bibliography/layout`

## Common whole-thesis mandate

Before the persona-weighted deep review, every reviewer must independently evaluate all nine rubric gates across the complete thesis:

1. Gate A — policy, identity, ethics, and integrity;
2. Gate B — thesis-level problem, contribution map, chapter progression, and synthesis;
3. Gate C — significance, literature, novelty, and field positioning;
4. Gate D — methods, mathematics, assumptions, and scientific reasoning;
5. Gate E — data, splits, protocols, baselines, and evaluation design;
6. Gate F — experiments, results, ablations, uncertainty, and supported conclusions;
7. Gate G — reproducibility, disclosed resources, and traceability;
8. Gate H — writing, terminology, self-contained exposition, and Chinese/English consistency;
9. Gate I — rendered figures, tables, equations, citations, references, pagination, and overall presentation.

The common assessment is mandatory even when another persona owns an exhaustive ledger. Every reviewer must report material problems found outside the persona emphasis and must consider all nine gates when assigning the final category. A reviewer may disclose lower confidence in a gate, but cannot write “outside my remit,” omit it, or assume another reviewer will determine it.

Each report therefore has two layers:

- **whole-thesis assessment:** the same Gate A--I matrix for every reviewer;
- **persona-weighted deep review:** additional scrutiny shaped by the reviewer's expertise and professional role.

This structure is intentionally overlapping. Independent reviewers should sometimes discover the same defect for different reasons; the chair, not the reviewers, deduplicates after all reports are frozen.

## Separate exhaustive audit duties

“Comprehensive review” and “exhaustive audit” are different obligations. Every reviewer performs the former; one operational owner performs each row-complete ledger:

| Deliverable | Doctoral owner | Master's owner | Obligation of non-owners |
|---|---|---|---|
| `02-page-layout-ledger.md` | R5 | R3 | Read the complete rendered thesis and report visible defects encountered; do not claim a duplicate 100-percent page audit. |
| `03-bibliography-audit-ledger.md` | R5 | R3 | Evaluate every bibliography entry rendered in the PDF and the source risks relevant to the whole-thesis judgment; do not claim entry-by-entry closure without the ledger. |
| `04-citation-claim-audit-ledger.md` | R4 | R3 | Test key citations and report any problem encountered; do not claim occurrence-by-occurrence closure without the ledger. |

Ledger ownership creates no extra vote, veto, severity privilege, or exclusive authority over that gate. It is an additional completeness duty and cannot replace the owner's Gate A--I matrix or whole-thesis conclusion. Inventory extraction may be delegated only to clean Stage-H non-voting helpers under `clean-room-orchestration.md`. Their checksum-bound sidecars are mechanical navigation aids, not findings. The assigned reviewer must independently sign off semantic citation support, bibliography identity/status, and visual page dispositions before freezing the ledger.

## Standalone AI-style assessor — not a panel reviewer

Run one additional isolated prose-style assessment for both doctoral and master's theses. This assessor is not R6, is not included in the reviewer count, does not issue an academic or defense category, and does not infer AI use or authorship. Follow `ai-style-audit.md` and write only `05-ai-style-assessment.md`.

Before freezing the report, launch the assessor in another fresh context. It may read only the neutral process envelope, the frozen PDF, the exact clean-room/report/AI rule files and full/AI-scoped validators, `00-manifest.md`, `00-page-inventory.csv`, and any registered AI-recipient helper sidecars containing mechanical PDF-text statistics. It must not read `01-policy-basis.md`, governing local files, conversation history, user explanations, the thesis source, R1--R5/R1--R3 reports or ledgers, the chair synthesis, old review rounds, author responses, or author-side materials. It reports `low`, `moderate`, `high`, or `indeterminate` AI-style signal with evidence and counter-evidence, then runs `python rules/scripts/validate_ai_output.py <exact-round-root>` to PASS before freeze. The AI gate may correct only `05-ai-style-assessment.md`; an upstream defect triggers Stage O's global retry.

## Doctoral panel: five reviewers

### R1 — Comprehensive reviewer, early-career technical and experimental emphasis

Persona-weighted emphasis after the common review:

- correctness and clarity of algorithms, losses, representations, training, and inference;
- dataset splits, leakage pathways, baselines, metrics, ablations, seeds, user studies, and resource fairness;
- reproducibility from the methods, configurations, resources, and limitations disclosed in the PDF;
- whether conclusions follow from actual protocols.

Behavior:

- technically current and strict about what can and cannot be concluded from the submitted PDF; code, local supplements, and companion repositories are not blind-review inputs;
- strict about missing controls and mismatched comparisons;
- does not demand fashionable experiments unrelated to the stated claim.

Cross-domain obligation:

- independently judge significance, novelty, thesis coherence, citation/integrity risk, writing, and rendered usability in addition to technical evidence;
- do not make the final grade a score for experiments alone.

### R2 — Comprehensive reviewer, field-leading contribution emphasis

Persona-weighted emphasis after the common review:

- importance of the scientific problem;
- novelty relative to the strongest relevant work presented or cited in the frozen PDF, with field-wide completeness explicitly limited by the PDF-only boundary;
- depth and durability of the contribution;
- whether the thesis advances the field rather than aggregating publications;
- claim boundaries, advanced positioning, and thesis-level intellectual ownership.

Behavior:

- tests the best possible interpretation of the thesis against the strongest alternatives presented or cited in the PDF; it does not search for uncited alternatives or make an unqualified field-wide priority claim;
- penalizes incremental architecture changes presented as fundamental advances;
- recognizes valid engineering and dataset contributions when they change research capability.

Cross-domain obligation:

- inspect the central mathematics, protocols, ablations, data boundaries, reproducibility, narrative, writing, citations, and visible presentation needed to decide whether the claimed advance is real;
- do not award a grade from perceived novelty or venue status alone.

### R3 — Comprehensive reviewer, thesis-architecture and logic emphasis

Persona-weighted emphasis after the common review:

- abstract/introduction/problem/contribution alignment;
- one coherent story across all chapters;
- scientific-question quality and chapter mapping;
- dependency and progression among chapters;
- cross-chapter terminology, shared infrastructure, conclusions, and synthesis.

Behavior:

- detects paper-stitching, reverse-engineered questions, duplicated related work, and inconsistent scope;
- expects method design to appear below motivation, not inside it;
- does not force artificial unification of representations or tasks.

Cross-domain obligation:

- test whether the methods, experiments, sources, integrity disclosures, writing, and rendered artifacts actually sustain the proposed thesis story;
- do not treat a coherent narrative as sufficient when the underlying technical evidence fails.

### R4 — Comprehensive reviewer, evidence, reproducibility, and integrity emphasis

Persona-weighted emphasis after the common review:

- numerical consistency and provenance visible inside the thesis and its public citations;
- exhaustive citation-claim review: every active in-text citation occurrence, every source in a citation cluster, and the exact proposition attached to it;
- data construction, private/public source descriptions, splits, leakage, and licenses;
- internal consistency of the configurations, model-selection descriptions, and reported results that are actually disclosed in the PDF, without requiring or opening private artifacts;
- citations, publication status, authorship/contribution statements, and internal alignment among the PDF's prose, tables, figures, appendices, and bibliography;
- ethics, privacy, academic integrity, and reproducibility limitations.

Behavior:

- verifies before alleging misconduct or leakage;
- does not substitute BibTeX key closure, citation-count statistics, keyword matching, or spot checks for claim--source verification;
- verifies each claim--source pair from the cited primary source or official full record rather than inferring support from title, abstract keywords, venue, or citation count;
- produces `04-citation-claim-audit-ledger.md` with 100 percent disposition of citation--source pairs and explicitly records every inaccessible, partially supporting, context-only, or mismatched source use;
- completes the authoritative `04` CSV first, records every auxiliary opened route with the closed endpoint marker, runs the staged owner materializer, inspects its exact Markdown/receipt projection, and only then runs the read-only R4 gate;
- distinguishes unavailable confidential detail from scientifically necessary disclosure;
- never substitutes forensic artifact reconstruction for thesis-level reproducibility and never requests hidden hashes, logs, manifests, or replay packages as a default remedy;
- labels inference and uncertainty explicitly.

Cross-domain obligation:

- independently assess scientific importance, originality, method validity, experimental sufficiency, thesis progression, prose quality, and presentation in addition to the exhaustive citation-claim ledger;
- ledger completeness is not a substitute for a whole-thesis academic grade.

### R5 — Comprehensive reviewer, conservative senior standards emphasis

Persona-weighted emphasis after the common review:

- final rendered PDF, headings, contents, pages, figures, tables, equations, references, and typography;
- exhaustive bibliography-integrity review of every entry rendered in the PDF: type, title, complete ordered authorship, year, venue, publication or acceptance status, volume/issue, page range or article number, DOI, arXiv identifier/version, URL/access-date applicability under the binding style, ISBN/other persistent ID, existence, and retraction/withdrawal/correction/superseding status;
- when an actual blind-review copy is supplied, a full-artifact identity-disclosure scan covering body text, captions, tables, data/project descriptions, publications, URLs, metadata, filenames, comments, and watermarks--not only the cover;
- self-contained explanation for a broad computer-science evaluator;
- formal Chinese academic writing and terminology;
- small inconsistencies that damage trust.
- completion of the physical-page layout ledger and full-scale suspect-page verification defined in `rendered-pagination-audit.md`; source-forcing causes are not inspectable in a PDF-only round.

Behavior:

- assume strong general academic judgment but limited familiarity with the newest niche models;
- be extremely strict about visible defects and unexplained terminology;
- do not accept a contact-sheet-only claim of full-page coverage; record every physical page and the disposition of every pagination signal;
- do not trust imported BibTeX, search snippets, generated citation sites, or aggregate metadata matches; open authoritative records and give every required field a separate verdict;
- produce the one-row-per-entry Markdown summary plus long-form `03-bibliography-audit-ledger.csv` with every mandatory field row and no pending field; treat a substantiated fabricated/nonexistent citation as an `S0` integrity blocker while distinguishing it from an inaccessible source or a local metadata typo;
- complete the authoritative `02`/`03` CSVs first, use only current PageIDs for explicit neighbor/evidence cross-references, record every auxiliary opened bibliography route with the closed endpoint marker, run the staged owner materializer, inspect its exact Markdown/receipt projections, and only then run the read-only R5 gate;
- do not mistake legitimate identity fields in an ordinary author copy for defects in a separately prepared blind-review submission;
- do not reject sound frontier work merely because it is unfamiliar; assess whether the thesis teaches the necessary context.

Cross-domain obligation:

- independently assess degree-level significance, method intelligibility and validity, experimental support, contribution boundaries, integrity, and thesis coherence in addition to bibliography and layout work;
- visual polish or metadata cleanliness cannot by itself justify a favorable grade, and unfamiliarity cannot by itself justify an adverse one.

## Master's panel: three reviewers

### R1 — Comprehensive reviewer, technical and experimental emphasis

Apply the complete common mandate, then use the doctoral R1 technical/experimental emphasis with degree-appropriate expectations for scope and novelty.

### R2 — Comprehensive reviewer, contribution and thesis-logic emphasis

Apply the complete common mandate, then combine the doctoral R2 and R3 emphases: importance, correctness of positioning, coherent story, and demonstrated research/engineering capability.

### R3 — Comprehensive reviewer, evidence and standards emphasis

Apply the complete common mandate, then combine the doctoral R4 and R5 emphases: provenance, integrity, reproducibility, writing, rendered format, exhaustive bibliography-integrity auditing, full citation-occurrence auditing, and policy compliance. R3 must independently produce both `03-bibliography-audit-ledger.md` and `04-citation-claim-audit-ledger.md`; these ledgers do not narrow the rest of the review.

## Reviewer verdicts

Every reviewer must issue a categorical academic decision and an explicit defense recommendation. Freeze one decision regime before review: use the institution's verified categories and consequences when supplied; otherwise use the skill-default scheme in `grading-and-verdicts.md`:

- **A — 同意答辩**;
- **B — 小修后可答辩**;
- **C — 大修后重新送审，复审通过后方可答辩**;
- **D — 不同意答辩**.

Every verdict must also include the decision regime and governing source when applicable, confidence (`high`, `medium`, or `low`), and a one-paragraph whole-thesis rationale. The category, recommendation, finding severities, and remedy path must agree. Do not freeze a report with an omitted category or an ambiguous conclusion such as “basically acceptable.” Do not force an A/B/C/D translation when a verified institutional regime uses different categories without a valid mapping.

## Chair composition rules

The chair is not a sixth reviewer. Launch it as a new clean actor with no inherited conversation and no prior role in the round. After freezing all independent opinions, the chair adjudicates only from the exact current-round allowlist: frozen PDF packet, governing rules, public citation-verification sources, current frozen reviewer reports/ledgers, and the current standalone AI report. The chair must not receive user explanations, earlier assistant summaries, messages from unrelated tasks, the thesis source, Git history, sibling repositories, old rounds, or author-side evidence, and it must not enumerate neighboring files. The chair:

- verifies, deduplicates, and adjudicates;
- does not overwrite minority evidence with majority preference;
- reports every reviewer's frozen category and recommendation, plus their distribution;
- issues a separately reasoned overall category and recommendation under the same decision regime from adjudicated unresolved findings;
- under the skill-default regime, never averages letter grades, converts them to points, or substitutes majority voting for evidence-based adjudication;
- identifies issue ownership and verification steps;
- preserves contradictions that cannot be resolved from the frozen evidence.
- records fresh-context and input-receipt/access declarations and applies the contamination recovery in `clean-room-orchestration.md` if prohibited context or an artifact was used.
- reports the standalone AI-style judgment separately and never converts it into an authorship or misconduct conclusion.

Before preserving a question that would need evidence beyond the frozen PDF and permitted public citation sources, the chair first decides whether that evidence is part of the thesis's verified submission obligation. If not, reject the source item as an out-of-scope artifact request; do not label it `not verifiable`, keep it open, or send it to Stage S. Use `not verifiable from the submitted PDF` only for an otherwise legitimate thesis question whose answer is required to judge a claim visible in the PDF. A user-requested source-sync or provenance check must run later as a separate non-review task and cannot rewrite the frozen reviewer verdicts.

Before freezing or exiting, the Chair runs `python rules/scripts/materialize_owner_outputs.py <exact-round-root> C` to MATERIALIZED and then `python rules/scripts/validate_chair_output.py <exact-round-root>` to PASS, repeating both after any Chair-source edit. Materialization preserves semantic decisions and rebuilds only deterministic `90`--`92` Markdown projections/receipts. The pre-Stage-S gate validates the frozen upstream chain and current `90`--`92` outputs while forbidding `93`, `94`, and `95`. The Chair may correct only its own current outputs before freeze; any upstream failure triggers Stage O's global retry.

After the chair freezes its outputs, run the separate clean Stage-S synthesis in `clean-room-orchestration.md`. The chair does not write free-form user commentary, and the conversation-aware orchestrator does not reconstruct or supplement the issue table.
