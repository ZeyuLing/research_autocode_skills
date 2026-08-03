# Quality and evidence rubric

Use this rubric consistently. Scores are 0–100 integers. Write the reason before choosing the number.

## Pass 1: relevance

### Scope match

- 90–100: directly studies the named task, modality, and setting.
- 75–89: directly useful to the topic, but one dimension is adjacent.
- 60–74: method or benchmark may transfer, but the paper's main problem differs.
- below 60: keyword collision or weak adjacency; reject.

### User fit

Score against the profile and any user-supplied priorities. Do not reward a fashionable topic the user did not request.

`relevance = 0.6 * scope_match + 0.4 * user_fit`

## Pass 2: intrinsic scientific quality

### Problem importance

Ask whether the problem is scientifically or practically consequential, clearly scoped, and measured by an appropriate task. Penalize manufactured problems and unclear assumptions.

### Method novelty

Compare the actual mechanism, objective, representation, data strategy, or system capability with the closest baselines. A renamed standard block is not novelty. Incremental work can still score well if the combination is technically justified and consequential.

### Evidence strength

This has the largest weight. Check:

- comparison against strong and current baselines
- fair compute/data/model-size controls
- multiple datasets, environments, tasks, or seeds when the claim requires them
- ablations that isolate the proposed modules
- statistical uncertainty or repeated trials where variance matters
- qualitative results that complement rather than replace quantitative evidence
- evidence for robustness, generalization, or long-horizon claims
- whether conclusions overreach the tested setting

### Reproducibility

Check code/data/model availability, algorithmic detail, hyperparameters, compute disclosure, evaluation protocol, and licensing. A repository link alone is not proof that reproduction is possible.

Compute intrinsic quality using the profile's `intrinsic_weights`.

## Previous-work gap test

For every highlighted paper, separate these claims:

1. **Observed limitation:** what prior systems demonstrably cannot do, ideally supported by experiments or cited results.
2. **Proposed cause:** why they fail; mark this as the authors' hypothesis if it is not independently tested.
3. **Mechanism:** which new module or strategy directly changes that failure mode.
4. **Evidence:** which table, figure, ablation, or analysis supports the causal link.

Do not write “previous work cannot solve it” when the paper only shows a small average gain.

## Module / strategy review

For each non-trivial component record:

- `what`: input, operation, output, training/inference role
- `problem_addressed`: the exact failure mode it targets
- `why_it_works`: mechanism, not a restatement of results
- `evidence_anchors`: section/equation/figure/table anchors

If the paper is a data, benchmark, scaling, or systems contribution rather than a modular architecture, treat dataset construction, objective, curriculum, evaluation protocol, or system policy as strategies. Do not invent modules to fit the template.

## External signal

External signal is a tie-breaker capped at 10% of the overall score. Consider:

- independent daily-paper curation or multiple-source appearance
- verified code, model, data, or project artifacts
- early citations or community adoption, normalized for paper age
- accepted venue only when independently verified

Never infer quality from author fame, institution, or social-media popularity.

## Evidence levels and gates

- `full-text`: Method and Experiments inspected; concrete anchors captured. Eligible for highlights.
- `partial-text`: more than abstract read, but experiments or method remain incomplete. Watchlist only.
- `abstract`: title/abstract/metadata only. Watchlist only.

Highlight gates:

- relevance at or above the profile threshold
- intrinsic quality at or above the profile threshold
- `evidence_level == "full-text"`
- no unresolved fatal concern, retraction, metadata mismatch, or unverifiable paper identity

Watchlist gates:

- `evidence_level` is `abstract` or `partial-text`; a completed full-text review that fails the quality gate is rejected, not softened into a watch item
- relevance is at or above `watch_threshold`
- provisional intrinsic quality is no more than 10 points below `quality_threshold`
- no fatal concern

Confidence:

- `high`: claims and comparisons are supported by primary-source anchors.
- `medium`: core claim is supported but some context or appendix evidence is missing.
- `low`: metadata or abstract-level inference dominates; watchlist or reject.

## Score calibration

Avoid clustering everything around 80. Suggested anchors:

- 90+: unusually convincing evidence and a meaningful advance
- 80–89: strong work with clear value and limited material concerns
- 70–79: useful and credible but incremental, narrow, or incompletely validated
- 60–69: promising but important evidence is missing
- below 60: weak, unsupported, or mismatched

When two papers are close, prefer stronger evidence and better user fit over popularity.

## Coverage honesty

Keep retrieval coverage and screening coverage separate. A polished shortlist is not exhaustive when a source failed, a query may have hit its result cap while still inside the requested window, or any candidate has only an empty/incomplete review record. Report each condition explicitly instead of lowering the quality gate or hiding the remainder.
