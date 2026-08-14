# Review rubric for Chinese CS/AI degree theses

Use the rubric as a coverage map. A finding exists only when supported by the reviewed thesis or governing rule.

## Degree-level threshold

### Doctorate

Expect an original and defensible contribution to knowledge, demonstrated independent research capability, a coherent body of work, and evidence whose scope matches the thesis-level claims. Multiple published papers do not automatically form a doctoral thesis; the thesis must explain the common scientific problem, progression, synthesis, and collective contribution.

### Master's

Expect a well-defined problem, sound use or extension of disciplinary methods, sufficient research or engineering competence, credible evaluation, and clear writing. Do not demand doctoral-scale field-shaping novelty.

### Professional degree

Evaluate practical problem definition, engineering or professional value, requirements and constraints, implementation quality, validation in representative conditions, and transferable lessons. Do not substitute publication novelty for the degree's stated outcomes.

## Gate A: policy, identity, and integrity

- Correct degree type, template, title-page information, declarations, and required components.
- Blind copy satisfies the current institution's anonymization instructions.
- No fabricated, internally contradictory, or untraceable values.
- No unattributed copying, misleading reuse, duplicate publication concealment, or improper authorship claims.
- Ethical approval, consent, privacy, licenses, and safety statements are present when applicable.
- Published/submitted work and the candidate's contribution are described accurately where required.
- Retractions, corrections, dataset-license limits, or unavailable evidence that materially affect the thesis are disclosed.

## Gate B: thesis-level story

- The real-world or scientific context naturally motivates the thesis problem.
- The central problem is broad enough to matter but precise enough to evaluate.
- Each scientific question is motivated by an actual knowledge or capability gap, not reverse-engineered from a completed chapter.
- Each technical chapter answers one question and advances the shared thesis problem.
- Chapter order expresses dependency, increasing scope, or a defensible conceptual progression.
- The introduction, abstract, roadmap figure, chapter introductions, conclusions, and final synthesis use consistent question and contribution language.
- Original paper names, venue marketing, and paper-specific framing do not make the thesis read as a compilation unless the institution explicitly permits a thesis-by-publication form.
- Shared datasets, frameworks, definitions, and evaluation protocols are introduced at the level where readers first need them, without falsely promoting support infrastructure to a peer contribution.
- The conclusion synthesizes knowledge across chapters rather than repeating five mini-paper abstracts.

## Gate C: topic, literature, and positioning

- Topic has scientific, engineering, or societal value appropriate to the degree.
- Related work covers foundational, directly competing, and current work.
- Literature organization supports the thesis questions rather than mirroring paper-by-paper citation lists.
- Comparisons are accurate about objectives, representations, assumptions, supervision, data, and evaluation protocols.
- Claimed gaps are substantive; differences such as continuous versus discrete representation are not treated as self-evident necessity.
- Citations directly support the attached claim; no citation laundering or irrelevant citation clusters.
- Important negative, contradictory, or competing evidence is not omitted.

## Gate D: methods and scientific reasoning

- Terms, variables, task definitions, assumptions, and outputs are defined before use.
- The chapter introduction explains problems and module responsibilities; implementation details appear in the method sections.
- Every major module has a scientific or engineering role, not merely an architectural description.
- Mathematical definitions are dimensionally and logically consistent.
- Algorithms, objectives, inference procedures, and training procedures agree with figures and code when code is in scope.
- Complexity, convergence, identifiability, stability, or physical assumptions are analyzed when central to the claim.
- The method does not promise physical realism, universality, causality, or controllability beyond what its objective and evidence establish.
- Cross-chapter terminology and representations are explained without manufacturing a false unified representation requirement.

## Gate E: data and evaluation protocol

- Dataset origin, composition, licenses, private-data constraints, and construction contribution are described at a defensible granularity.
- Official dataset splits are stated correctly; custom splits are reproducible.
- Training data exclude protected public test partitions where claimed.
- Duplicate or near-duplicate leakage is investigated when the dataset construction or task makes it a credible risk. Do not require a generic overlap audit without a plausible pathway.
- Training, validation, checkpoint selection, and test evaluation roles are unambiguous when the wording could imply test-guided selection.
- Preprocessing, coordinate systems, skeleton mappings, frame rates, missing-data handling, and conversions are documented.
- Baselines use comparable data, representations, metrics, and evaluation implementations, or differences are disclosed.
- Retrained baselines are labeled and their configuration source is traceable.
- Hardware, software, optimizer, learning rate, batch size, steps/epochs, model size, seeds, and inference settings are available at the level needed to interpret results.
- Compute or simulation budget is reported when it controls fairness or reproducibility.

## Gate F: experiments and results

- Main experiments directly answer the chapter's scientific question.
- Metrics are defined before use and cover the thesis's claims.
- Metric directions, best/second-best formatting, units, precision, and uncertainty are correct.
- Tables and prose match exactly, including signs, decimal precision, and dataset/protocol names.
- Comparisons do not mix incompatible representations or protocols into one ranking.
- Ablations isolate claimed components or are worded as configuration evidence rather than causal proof.
- Multiple seeds, confidence intervals, or significance tests are expected only when stochastic variation matters to the claim and the field protocol supports them.
- User studies include participant count, recruitment/eligibility, comparison design, randomization, instructions, response scale, aggregation, and uncertainty when those details are available or essential.
- Qualitative figures illustrate defined phenomena and do not substitute for population-level evidence.
- Failure cases or limits are included when omission would overstate robustness; a separate severe “limitations” section is not mandatory.
- Results are interpreted, not merely restated, and alternative explanations are considered where consequential.
- No missing cell, placeholder, invented estimate, or unexplained `N/A` remains.

## Gate G: reproducibility and source alignment

- Every chapter's reported result is traceable to a source paper, experiment artifact, or documented thesis-only experiment.
- Values copied from papers are exact and retain protocol context.
- Source paper updates are propagated to thesis figures, tables, method text, and references.
- Configuration tables avoid columns dominated by `N/A`; heterogeneous modules may be described separately in prose.
- Code, commands, configs, checkpoints, logs, and dependencies are cited when available and relevant.
- Private data or enterprise constraints are described honestly without demanding disclosure that violates confidentiality.
- Missing implementation details are classified as writing/evidence retrieval before requesting a new run.

## Gate H: writing and self-contained exposition

- Abstract states problem, thesis-level approach, major contributions, and conclusion at an appropriate level; it does not become a result table or venue list.
- Sentences are formal, precise, and free of template-like or inflated AI phrasing.
- Paragraphs have a clear claim and information flow.
- Transitions follow the real research logic rather than announcing paper titles.
- Terms such as “constraint-faithful,” “unified,” “general,” “physical,” and “controllable” are operationally defined or replaced with precise language.
- The thesis explains frontier concepts sufficiently for a competent CS reviewer outside the narrow subfield.
- Chinese and English abstracts, titles, keywords, and contribution wording agree.
- No orphan acronym, undefined symbol, stale chapter reference, or copied conference-template phrase remains.

## Gate I: figures, tables, equations, citations, and pages

- Every figure/table is cited before or near first appearance and appears in a sensible order.
- Full-width artifacts use a consistent width unless their aspect ratio or content justifies otherwise.
- Small/narrow tables are not stretched to full width merely for uniformity.
- Text inside figures is legible at print scale; images are sharp and not incorrect draft alternatives.
- Captions function as concise titles. Extended interpretation belongs in body text.
- Figures and tables are not needlessly adjacent; large floats do not create avoidable float-only or nearly blank pages.
- No `[H]`, `\clearpage`, `\newpage`, or barrier is used merely to force a local visual preference without checking neighboring pages.
- Tables use appropriate font size, column widths, alignment, line breaks, notes, and multipage mechanisms.
- Equations, symbols, algorithms, and units are consistently numbered and referenced.
- Table-of-contents hierarchy is balanced across technical chapters and exposes the thesis logic.
- Reference entries are complete, deduplicated, consistently formatted, and all cited.
- The final PDF has no overlap, clipping, broken glyph, malformed arrow, missing image, unresolved reference, or unexpected blank page.

## Finding test

Before reporting an issue, answer all five:

1. What exactly is visible or stated?
2. Where is it?
3. Which claim, rule, or reader task does it affect?
4. What evidence supports the concern?
5. What is the least costly sufficient remedy?

If any answer is missing, downgrade it to a question or omit it.
