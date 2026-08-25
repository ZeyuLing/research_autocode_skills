# Data Scaling, Quality, Mixture, and Repetition

Use this reference whenever training data can vary. More files, samples, or tokens are not automatically more useful data. Separate quantity, quality, composition, uniqueness, and exposure.

## Freeze the candidate pool

Before scaling, create `data/manifest.json` with:

- source, version, URI/path, license, and access constraints;
- file/sample/token counts and checksums;
- schema, modality, labels/annotations, and missing fields;
- entity/group/subject/domain identities needed for safe splitting;
- duplicate and near-duplicate analysis;
- source-wise quality signals and known noise;
- preprocessing and representation version;
- train/validation/test split hashes;
- possible benchmark or final-test contamination.

Keep validation and final test fixed throughout data search. Do not use final-test performance to select sources, filters, examples, synthetic generators, or mixture ratios.

## Quantity ladder

Generate nested, stratified subsets from a frozen pool:

```text
D0  tiny-overfit set
D1  cheapest meaningful pilot fraction
D2  low fraction
D3  middle fraction
D4  high fraction
D5  full eligible pool
```

Choose logarithmic or information-relevant fractions based on actual size; do not hard-code one universal percentage list. Ensure `D1 ⊂ D2 ⊂ ...` where possible so differences are paired. Use multiple subset seeds at low data scale when sample-composition variance is material. Keep model-initialization seeds separate from subset seeds.

For grouped or sequential data, sample and split by the correct independent unit rather than rows or frames.

## Exposure protocols

Every data-scale curve names its exposure policy.

### Fixed total tokens/samples/updates

Hold training exposure and approximate compute fixed while increasing unique data. This measures the value of diversity/quality under equal compute.

### Fixed epochs/passes

Train every subset for the same number of passes. Compute increases with data size, so the result combines data and compute effects.

### Joint model-data scaling

Select capacity and exposure per data scale. Use this for compute-optimal or deployment planning, not as a substitute for a controlled fixed-exposure study.

Always report unique data and total examples/tokens seen. “Dataset size” alone is ambiguous under repetition.

## Source and quality studies

When multiple sources/domains exist, choose the designs needed by the claim:

### Add-one-source

Start from a declared core and add one source at a time. This estimates marginal value in that context.

### Leave-one-source-out

Remove each source from the full mixture. This tests necessity in the full context.

### Mixture search

Search source/domain ratios with small proxy models or reduced fidelity, then verify promising mixtures at at least one larger scale. A proxy mixture is not final evidence until transfer is checked.

### Quality tiers and filtering

Compare nested quality tiers, filtering thresholds, deduplication, label-confidence bands, human/automatic curation, or real/synthetic ratios. Match unique-token, total-token, or compute budgets according to the question.

### Repetition

Compare repeated passes over fixed unique data against new unique data. Track epoch count and total exposure; detect memorization, diminishing returns, and domain forgetting.

## Harmful-data diagnosis

If more data reduces a primary or protected capability, add diagnostics before deleting the source:

1. compare fixed-exposure and fixed-epoch protocols;
2. report per-source/per-domain validation, not only the mean;
3. audit duplicates, contamination, label/annotation noise, preprocessing, and tokenization/representation;
4. run add-one and leave-one-out controls;
5. sweep mixture ratios;
6. test the mixture at two model scales when feasible;
7. check forgetting or gradient/representation conflict if the method claims a mechanism;
8. distinguish lower average quality from useful rare or worst-group coverage.

Do not remove data solely because one adaptive search run was worse. Require repeated or paired evidence under a compatible budget.

## Crossed factors

Important interactions include:

```text
data quantity × model scale
data mixture × model scale
data quality × method module
unique data × repetition
real data × synthetic ratio
source × target-domain metric
```

Avoid a full Cartesian product when unnecessary. Use low-fidelity screening, then confirm the interactions required by claims at target scale.

## Metrics and report

For each data condition report:

- primary and secondary validation metrics with uncertainty;
- source/domain/worst-group metrics;
- unique and total data exposure;
- compute and wall-clock;
- duplicates removed and examples excluded;
- marginal gain per data unit and per compute unit;
- model scale and mixture used;
- final-test access status.

Conclude whether evidence shows monotonic gain, saturation, harmful sources, mixture sensitivity, repetition limits, or a scale-dependent transition. “All available data” is not a result.
