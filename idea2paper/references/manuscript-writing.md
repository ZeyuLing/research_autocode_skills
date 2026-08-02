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

Place the teaser between authors and Abstract only when the official template and author instructions permit it. Otherwise follow the official placement rule. Never force a teaser when the venue forbids it or when it harms the page budget more than it helps.

## Page budget and appendix

Allocate body pages immediately after venue lock. Reserve the overview, main benchmark tables, and core qualitative result before expanding prose.

The sketch may exceed the official body limit by at most one page. Reduce it by:

1. removing repetition;
2. tightening background and routine implementation detail;
3. combining compatible tables/figures;
4. moving non-core derivations, secondary ablations, hyperparameters, and extra cases to the appendix.

Keep material required to understand the method or validate the main claim in the body. Cite every appendix item from the body. Respect whether the venue permits an appendix or supplementary material and whether reviewers are required to read it.

Treat float order as part of the paper's argument, not as a final LaTeX cleanup. Introduce each main-paper figure or table before or near its rendered position, keep it close to that discussion, and ensure the final main-paper float renders before `Conclusion`. Do not allow a queue of method/result floats to spill into Conclusion, references, or the appendix. If the last qualitative figure tends to drift, anchor that one float locally and rebalance adjacent prose; do not globally pin every float.

Do not use `\clearpage`, `\newpage`, `\pagebreak`, or `\FloatBarrier` anywhere in the active manuscript input graph to force a layout. Fix the underlying float dimensions, placement options, ordering, or section budget. Add `\label{idea2paper:start-conclusion}` immediately after the sole Conclusion heading, keep the Conclusion and optional Limitations inputs before `\label{idea2paper:end-body}`, place the bibliography next, then `\label{idea2paper:end-references}`, and begin the appendix with `\appendix`. The compiler binds these markers to that canonical order rather than trusting movable labels.

Give every figure and table before `\appendix` one unique `\label` inside its environment. The compile gate recursively expands both braced and unbraced `\input`/`\include` forms, rejects any source float after Conclusion begins, and also checks rendered page and same-page AUX order. All manuscript inputs and figure/bibliography resources must use static, paper-root-relative paths and resolve under `paper/`; external or macro-generated file dependencies are forbidden. TeX conditionals are also forbidden in the audited manuscript input graph because they make section and float boundaries ambiguous. All files under `paper/` are included in the compilation freshness hash.

The only content permitted after `idea2paper:end-body` and before `idea2paper:end-exempt` is one concise `sections/ai_use_statement` input when the venue exempts that disclosure from the page limit. The compiled labels must show that this exempt region spans at most one additional page. Only bibliography formatting may follow `idea2paper:end-exempt` before the bibliography; put no body prose or other input there. `main.tex` must then place `idea2paper:end-references` before exactly one `appendix/appendix` input, and `appendix/appendix.tex` must begin with a literal `\appendix`.

Do not add custom local `.sty` or `.cls` files. A paper-local LaTeX package/class is allowed only when its exact bytes occur in the recorded official author-kit archive; the bundled `idea2paper-draft.sty` is the sole internally audited exception. This prevents a package macro from redefining structural commands, hiding external resources, or expanding uncounted pages after the body boundary.

`SUBMISSION_READY` must meet the exact official limit; the one-page tolerance applies only to `SKETCH_COMPLETE`.

## Consistency pass

Before QA, check:

- identical terminology and capitalization across prose, equations, tables, captions, and imagegen figures;
- each acronym is defined once;
- every figure/table is cited before or near appearance;
- no main-paper figure/table renders on a page after Conclusion begins, and no body float is dumped near the references;
- no manual page-break or float-flush command is used to force placement;
- all contribution bullets map to the claim matrix;
- Abstract and Conclusion contain no orphan claims;
- no agent dialogue, execution plan, rejected idea, or internal risk register appears in rendered text;
- double-blind metadata and artifact links comply with the target venue.
- the LaTeX title exactly matches the frozen title decision and accurately previews the problem, differentiating mechanism, and claim boundary without relying on predicted results.
