# Manuscript Writing Protocol

Write final prose only after the venue, literature corpus, idea, contributions, claim graph, Method, experiment matrix, and paper title are stable.

## Draft order

1. Method and Experiments
2. Related Work
3. Introduction
4. Abstract
5. Conclusion
6. Teaser placement and page rebalance

Prepare literature notes earlier, but delay final Related Work prose until the method positioning is frozen.

## Related Work

Organize by research problem and method family, not by a paper-by-paper chronological list. For each cluster:

- state the shared approach;
- cite representative foundational, closest, and recent work;
- explain the relevant capability or limitation accurately;
- position the proposed work without strawman claims.

Cover every final `must_cite=yes` record, including directly relevant accepted top-conference/top-journal papers and novelty-threatening preprints. Relevance outranks prestige. Size the section from the venue page budget; do not make it a mini-survey that displaces the contribution.

Every factual claim must trace to a verified corpus record and evidence note. Do not cite a paper from title/abstract inference when the claim requires full-text evidence.

## Introduction

Use this flow:

1. establish field context and application value;
2. define the important problem;
3. synthesize how existing approaches address it;
4. identify the unresolved limitation and explain why existing mechanisms cannot solve it;
5. introduce the proposed method and map each core component to that limitation;
6. list distinct contributions that match the frozen claim graph.

Avoid promises not covered by the experiment matrix. Wrap result-dependent statements in `\PredClaim` with the linked result ID and adjacent TODO.

## Abstract

Compress the frozen Introduction and experiment story:

```text
context -> prior limitation -> why it persists -> proposed method
-> how the method resolves it -> result-dependent achievement -> significance
```

Write a complete sketch under the assumption that planned experiments succeed. Use `\PredResult` and `\PredClaim` for every predicted number or result-dependent conclusion, with adjacent TODOs. Do not introduce a claim absent from the main paper.

## Conclusion

Restate the problem, method insight, main contributions, and supported implications without repeating the Abstract verbatim. Link every result-dependent sentence to the same IDs used in tables and Abstract. Include academically relevant limitations when required; keep project plans and operational risks outside the paper.

## Teaser

Generate the teaser only with imagegen and use the frozen claim/terminology manifest. Emphasize the paper's single strongest selling point. Before real results exist, use a conceptual or clearly marked no-number placeholder teaser; keep every predicted value in an adjacent tracked LaTeX macro or table. After real results exist, regenerate any quantitative teaser through imagegen using verified values.

When the venue permits a teaser, its rendered order is strictly **Title -> Authors
-> Teaser -> Abstract**. Never place it above the title, between title and authors,
after the abstract, or as an ordinary float. Keep the official template file
byte-for-byte unchanged and do not patch template-internal `\@maketitle` tokens.
The canonical source order is exactly one `\maketitle`, immediately followed by
exactly one `\input{sections/teaser}`, followed by `\begin{abstract}`. The teaser
file contains one non-floating `IdeaTwoPaperTitleTeaser` environment. If venue
instructions forbid insertion between the author block and abstract, omit the
teaser and record that decision; do not silently move it elsewhere.

## Page budget and appendix

Allocate body pages immediately after venue lock. Reserve the overview, main benchmark tables, and core qualitative result before expanding prose.

The sketch may exceed the official body limit by at most one page. Reduce it by:

1. removing repetition;
2. tightening background and routine implementation detail;
3. combining compatible tables/figures;
4. moving non-core derivations, secondary ablations, hyperparameters, and extra cases to the appendix.

Keep material required to understand the method or validate the main claim in the body. Cite every appendix item from the body. Respect whether the venue permits an appendix or supplementary material and whether reviewers are required to read it.

Treat float order as part of the paper's argument, not as a final LaTeX cleanup. Introduce each main-paper figure or table before or near its rendered position, keep it close to that discussion, and ensure the final main-paper float renders before `Conclusion`. Do not allow a queue of method/result floats to spill into Conclusion, references, or the appendix. If the last qualitative figure tends to drift, anchor that one float locally and rebalance adjacent prose; do not globally pin every float.

Treat the appendix as a designed reading sequence too. Interleave each table/figure with the paragraph that defines its protocol and the paragraph that interprets it. In a one-column template, place no more than two floats on a page, never place two or more floats on each of two adjacent appendix pages, avoid three consecutive pages in either region with two or more floats each, reject a four-float/75%-share dump on the final two appendix pages, and keep the final three appendix pages from holding more than 70% of all appendix floats when the appendix is long enough for that test. A prose-only appendix page followed by several float-heavy pages is a failed distribution even when every float is technically inside the appendix.

Preserve sentence-level reading continuity across every page boundary. A top float may
not appear between the two halves of a hyphenated word or between a clause and its
continuation. The compiler automatically rejects both an alphabetic hyphen fragment and
an unfinished sentence when the next artifact-bearing page begins with a Table/Figure
caption. Treat any analogous interruption found in the contact sheet as equally
blocking. Repair it with source order, figure/table size, or a legal
placement set such as `[!htbp]` or a narrowly justified non-top placement for that one
float; do not flush the queue or force `[H]`.

Audit rendered geometry and the TeX compiler log, not only LaTeX source. On a single-column float page, a large empty row, a tall narrow local float block surrounded by empty columns, a strongly one-sided content region, or a large blank tail usually means the original table/figure format does not fit the template. First transpose or split a sparse table, shorten repeated headers, resize the asset to the true text width, adjust source order and legal placement specifiers, or move a tightly coupled paragraph with it. Do not fill space with irrelevant prose. The automated audit uses mandatory `pdfplumber` geometry, rejects float-page leading blank space above 22% of usable height, nonterminal trailing blank space above 22%, internal blank bands above 16%, page content narrower than 50%, tall local float regions narrower than 46%, severe side imbalance, more than two floats per one-column page, and multi-page float clusters. Before every build it removes only the named `main.*` compiler outputs, forces `latexmk` to rebuild, and binds the report to the fresh `main.log` path and SHA-256. Any `\hfuzz` or `\vfuzz` use in the active author `.tex` graph or an author-controlled local style is blocking; exact venue-bound official template assets are not treated as author bypasses. The audit parses the bound log: an overfull horizontal or vertical box above 2 pt is a blocking clipping defect, while smaller overfull boxes remain explicit visual-inspection warnings. Independently, unclamped `pdfplumber` coordinates more than 2 pt outside the media box are blocking; this is a page-edge fallback, not a substitute for TeX warnings about content that exceeds a column while remaining inside the page. The same PDF pass supplies total pages when external page counters are unavailable. A terminal float page may end naturally only when it occupies at least 35% of usable height and leaves at most 45% trailing blank space, preventing a float-only tail without incentivizing filler. A prose-only terminal page is also rejected when more than 70% is trailing blank or less than 20% of usable height is occupied; this catches accidental near-empty stubs without forcing a naturally short ending to be padded. Visual inspection remains stricter when a smaller defect is conspicuous.

Do not use `\clearpage`, `\newpage`, `\pagebreak`, `\FloatBarrier`, or exact `[H]` figure/table placement anywhere in the active manuscript input graph to force a layout. Fix the underlying float dimensions, legal `[tbp]` placement options, ordering, or section budget. Put optional Limitations before the sole Conclusion input, add `\label{idea2paper:start-conclusion}` immediately after the Conclusion heading, and place `\label{idea2paper:end-body}` immediately after that input so Conclusion remains the true final body section. Place the bibliography next, then `\label{idea2paper:end-references}`, and begin the appendix with `\appendix` immediately followed by `\label{idea2paper:start-appendix}`. The compiler binds these markers to that canonical order rather than trusting movable labels.

Give every body and appendix figure/table one unique `\label` inside its float environment or source-anchored `\captionof` block. The compile gate recursively expands both braced and unbraced `\input`/`\include` forms, rejects any source artifact after Conclusion begins, checks rendered page and same-page AUX order, counts floating and source-anchored artifacts per page, and measures rendered blank bands. It records the canonical `build/main.aux` path and hash; project validation reopens that AUX and independently reconstructs every artifact-label page, the source-derived column mode, page-density decisions, and PDF whitespace before exact comparison with the report. All manuscript inputs and figure/bibliography resources must use static, paper-root-relative paths and resolve under `paper/`; external or macro-generated file dependencies are forbidden. TeX conditionals are also forbidden in the audited manuscript input graph because they make section and artifact boundaries ambiguous. All files under `paper/` are included in the compilation freshness hash.

After any meaningful float/source-order change, compile at least twice so references and float placement stabilize. Render a contact sheet and inspect every page at readable zoom, then inspect every flagged or visually dense page individually. Read the last line of each page together with the first content line of the next page and verify that no caption or float body interrupts a sentence. Record final per-page float counts, reading-order findings, and geometry findings in `qa/layout_report.json`; a clean last page alone is not evidence that the distribution is professional.

The only content permitted after `idea2paper:end-body` and before `idea2paper:end-exempt` is one concise `sections/ai_use_statement` input when the venue exempts that disclosure from the page limit. The compiled labels must show that this exempt region spans at most one additional page. Only bibliography formatting may follow `idea2paper:end-exempt` before the bibliography; put no body prose or other input there. `main.tex` must then place `idea2paper:end-references` before exactly one `appendix/appendix` input, and `appendix/appendix.tex` must begin with a literal `\appendix`.

Do not add custom local `.sty` or `.cls` files. A paper-local LaTeX package/class is allowed only when its exact bytes occur in the recorded official author-kit archive; the bundled `idea2paper-draft.sty` is the sole internally audited exception. This prevents a package macro from redefining structural commands, hiding external resources, or expanding uncounted pages after the body boundary.

`SUBMISSION_READY` must meet the exact official limit; the one-page tolerance applies only to `SKETCH_COMPLETE`.

## Consistency pass

Before QA, check:

- identical terminology and capitalization across prose, equations, tables, captions, and imagegen figures;
- each acronym is defined once;
- every figure/table is cited before or near appearance;
- no main-paper figure/table renders on a page after Conclusion begins, and no body float is dumped near the references;
- no body or appendix page overloads floats, no appendix tail is a float dump, and no single-column float leaves a large avoidable blank row/column/tail;
- no manual page-break or float-flush command is used to force placement;
- all contribution bullets map to the claim matrix;
- Abstract and Conclusion contain no orphan claims;
- no agent dialogue, execution plan, rejected idea, or internal risk register appears in rendered text;
- double-blind metadata and artifact links comply with the target venue.
- the LaTeX title exactly matches the frozen title decision and accurately previews the problem, differentiating mechanism, and claim boundary without relying on predicted results.
