# Standalone AI-style prose assessment

Use this protocol for every initial review and independent re-review of an authored thesis. The assessment is a separate style-risk judgment, not a sixth reviewer, not an authorship detector, and not evidence of academic misconduct.

## 1. Epistemic boundary

Assess only whether the submitted prose contains recurrent linguistic or structural patterns that make it read as formulaic, mechanically generated, or insufficiently authorial. Never infer who wrote the text or whether any AI system was used.

Do not:

- report an “AI probability,” detector score, or plagiarism-style percentage;
- use commercial or opaque AI detectors as evidence;
- treat one phrase, one long sentence, polished grammar, or low error rate as proof;
- convert a style signal into `S0` authorship/integrity misconduct;
- penalize required institutional boilerplate, BibTeX output, reference lists, formulae, code, table cells, or standard declarations;
- assume that common Chinese academic transitions are defective without checking recurrence, context, and reader impact.

If the assessor encounters a factual, citation, integrity, or technical problem, it must not message any reviewer or other actor before reports are frozen. Record the PDF-visible observation, if material, only in a sealed `Out-of-scope observations for chair verification` section of `05-ai-style-assessment.md`, without an AI finding ID, severity, or conclusion. The clean chair may independently verify it after all R reports are frozen. Do not disguise it as an AI-style finding.

## 2. Independence and evidence

Follow `clean-room-orchestration.md`. Launch the AI-style assessor in a fresh context with no inherited user/thread/task turns beyond system/developer instructions and the exact operational prompt. In Codex multi-agent execution, use `fork_turns: "none"`. The assessor is independent of R1--R5 and the chair. Before freezing `05-ai-style-assessment.md`, the assessor must not read, receive, or recall:

- user explanations, corrections, rebuttals, desired interpretations, or claimed facts outside the PDF;
- earlier assistant answers, issue tables, status reports, or messages from another current/completed task;
- any R1--R5 report or ledger;
- a chair synthesis, revision response, or issue list;
- old review rounds;
- private author-side papers, repositories, prompts, chat logs, or generation history.

Use only the neutral process envelope; `SKILL.md`; the clean-room, report-template, and AI-style rules; the full and AI-scoped validator scripts; the frozen thesis PDF; `00-manifest.md`; `00-page-inventory.csv`; and any registered AI-recipient helper sidecars containing mechanical statistics derived from extracted PDF text. Do not open `01-policy-basis.md`, a governing local file, another packet/ledger/report, the thesis source, `.bib`, Git history, sibling repositories, old rounds, or author-side files. Give the assessor exact paths and a private scratch/output directory; it must not enumerate the round parent or unrelated workspace. The assessor must include a fresh-context and input-receipt/access declaration covering the prompt hash, received blocks, opened artifacts, and `public_endpoints=[none]`. Any prohibited context or artifact access by the assessor invalidates the round according to `clean-room-orchestration.md`. The assessor must not modify the thesis.

## 3. Scope

Read the complete rendered thesis at a legible scale and inspect the authored prose as rendered in the PDF. Always examine:

- the preface (`序言`/`前言`, `Preface`/`Foreword`) when present;
- Chinese and English abstracts;
- the introduction, thesis questions, contributions, and roadmap;
- every chapter introduction, transition, result-analysis passage, limitation paragraph, and conclusion;
- the thesis-level synthesis and outlook;
- figure/table captions, appendix prose, and substantive explanatory or contribution prose anywhere in front/back matter, including prose that shares a page with CV metadata.

Exclude institutional declarations, template-generated front matter, table-of-contents entries, raw equations, algorithms, tables dominated by values, bibliography entries, and CV metadata spans from the style judgment. Exclusions are span-level, not page-level: a CV/back-matter label does not exclude substantive authored prose elsewhere on that page. Record these exclusions.

## 4. Signal families

Evaluate patterns in context, not by keyword counting alone.

1. **Formulaic macro-structure:** repeated chapter openings or closings with the same rhetorical slots; five mini-paper abstracts presented with only labels changed; predictable “background--challenge--method--result--significance” templates that suppress actual reasoning.
2. **Mechanical transitions and metadiscourse:** excessive “首先/其次/最后”“综上所述”“由此可见”“值得注意的是”“本文将”等 signposting; paragraphs that describe what the text will do instead of doing it.
3. **Empty abstraction or inflated evaluation:** frequent “重要意义”“深刻揭示”“充分体现”“有效解决”“提供新思路” without a concrete object, mechanism, comparison, or evidential limit.
4. **Forced symmetry and list regularity:** repeated three-part enumerations, equal-length parallel clauses, slogan-like four-character verb chains, or “不仅……更……” constructions that appear independent of the underlying argument.
5. **Uniform cadence and syntax:** long runs of sentences with near-identical length, clause order, subject pattern, or paragraph closing; mechanical synonym substitution that destabilizes technical terminology.
6. **Translationese or voice discontinuity:** unnatural Chinese collocations, English-shaped nominalization, abrupt shifts between highly polished generic prose and locally specific technical explanation, or inconsistent authorial stance.
7. **Generic result restatement:** paragraphs that mechanically repeat every table value or say only that results “证明有效,” without explaining trade-offs, exceptions, mechanisms, or claim limits.
8. **Conversational-generation residue:** assistant-like framing, offers of help, prompt residue, knowledge-cutoff disclaimers, placeholder language, or unexplained instructions to the reader.

Also record counter-evidence: precise domain reasoning, concrete causal or diagnostic interpretation, natural syntactic variation, stable terminology, locally grounded limitations, and explicit authorial judgment. Counter-evidence is necessary for calibration.

## 5. Procedure

1. Freeze the PDF checksum, page count, and PDF-derived authored-prose corpus, beginning with any rendered preface and continuing through the abstracts, chapters, and substantive appendix prose.
2. Inspect every physical page. Do not use a contact sheet or extracted text as a substitute for reading.
3. Mechanically count recurrent transitions, sentence openings, paragraph endings, repeated n-grams, sentence-length distribution, punctuation patterns, and chapter-introduction/conclusion templates. Preserve the query or script and record corpus exclusions.
4. Read every candidate in context. A lexical hit becomes evidence only when it participates in a recurrent pattern and degrades specificity, flow, or authorial voice.
5. Compare repeated structures across chapters. Distinguish legitimate thesis-level consistency from content-independent templating.
6. Select representative evidence across the whole thesis. Do not cherry-pick a few awkward sentences or hide a widespread pattern behind one natural passage.
7. Freeze one standalone judgment before reading any other review output.

## 6. Judgment scale

Use exactly one overall label:

- `low` — authored prose is predominantly specific, varied, and context-sensitive; isolated formulaic phrases do not form a material pattern.
- `moderate` — recurrent formulaic or mechanically uniform passages are noticeable and locally weaken authorial voice or readability; targeted revision is advisable, but the thesis remains recognizably domain-grounded.
- `high` — formulaic, empty, or mechanically repeated prose is widespread across major authored sections and materially obscures reasoning or makes the thesis read as assembled/generated text; systematic prose revision is required.
- `indeterminate` — the available artifact contains too little authored prose, is unreadable, or is dominated by translation/template material, so a defensible judgment cannot be made.

Do not translate these labels into numerical probabilities. Report confidence as `high`, `medium`, or `low` and explain the main uncertainty.

## 7. Findings and remedies

Use IDs `AI-F01`, `AI-F02`, and so on. Do not use R1--R5 `S0--S4` severity labels. Classify impact as:

- `material` — widespread pattern requiring systematic revision before claiming final prose polish;
- `local` — bounded passages needing targeted revision;
- `optional` — a preference-level refinement that does not impair readability or authorial voice.

For every material or local finding, record the exact PDF page and section, the recurrent pattern, at least two representative instances when recurrence is claimed, reader impact, the smallest safe editing strategy, and a closure test. Preserve scientific meaning, data, equations, citations, terminology, and claim limits.

## 8. Required report

Write `05-ai-style-assessment.md` with:

- frozen artifact identity and reviewer-visible scope;
- fresh-context and input-receipt/access declarations;
- independence declaration and excluded material;
- overall label and confidence;
- corpus coverage and mechanical checks;
- signal-family summary with counter-evidence;
- evidence-backed findings;
- passages sampled across every authored chapter;
- limitations and the explicit statement: **This is a prose-style assessment, not a determination of AI use, authorship, plagiarism, or misconduct.**

The `Required disclaimer` field must equal that sentence exactly; placing the
sentence elsewhere cannot compensate for a changed or contradictory field.
Do not add structured fields for an AI probability, percentage, rate, ratio,
share, detector score/positive rate, academic or defense grade, reviewer
severity/remedy, authorship or AI-use verdict/conclusion/determination, or
misconduct determination. The validator rejects those fields even when the rest
of the report is complete. Equivalent label variants are also prohibited:
normalize Unicode, spacing, hyphens, and case before applying the boundary. Thus
labels such as `AI probability estimate`, `AI-generated percentage`, `AI content
ratio`, `AI 概率`, `AI生成占比`, detector-likelihood/positive-rate scores,
academic grades, defense verdicts, authorship conclusions, AI-use conclusions,
and misconduct conclusions cannot evade the separation rule through wording
variation.

The colon-labeled bullet fields in `05-ai-style-assessment.md` are a closed
schema: use only the exact field labels shown in `report-template.md`. Put
signal-family analysis, counter-evidence, limitations, and any sealed
out-of-scope observation in paragraphs, tables, or bullets without colon-style
field labels. An extra or renamed colon-labeled bullet invalidates the report;
free prose cannot compensate for or contradict the required disclaimer.

Before freezing or exiting, run `python rules/scripts/validate_ai_output.py <exact-round-root>` until it exits `0` and its first nonempty stdout line is exactly `PASS`. This read-only scoped gate uses only the canonical AI inputs and `05-ai-style-assessment.md`; it does not enumerate the round root or open reviewer/ledger, Chair, Stage-S, old-round, or governing-local-file artifacts. The assessor may correct only its current `05-ai-style-assessment.md` in the same fresh turn. Any failure attributable to the process envelope, frozen PDF, Stage-P manifest/page inventory, governing rules, or staged validators stops the assessor and triggers Stage O's clean global retry. Validator code/stdout is mechanical rule infrastructure, not thesis evidence or a source of style findings.

The chair copies every unresolved `material` or `local` style remedy into the separate AI-actionable ledger without translating it to `S0--S4` or changing the defense grade. Any such open finding blocks a claim that the thesis has completed final prose-polish review, regardless of the overall signal label. The judgment remains separate from the R1--R5 category/recommendation distribution and does not by itself change the academic, defense, or integrity conclusion.

After prose edits, run the assessor again on the newly frozen PDF without showing it the previous assessment. Compare current and prior AI reports only in a separately labeled Stage-V longitudinal style comparison after the current R reports, chair outputs, and Stage-S summary are frozen. Never expose the prior AI report to the current chair or use the comparison to alter current grades, findings, revision ledger, or clean summary.
