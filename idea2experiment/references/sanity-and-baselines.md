# Sanity, Tiny Overfit, and Baseline Reproduction

Use this protocol before any expensive experiment. Passing it gives confidence in the main learning path; it does not prove that the evaluator, distributed path, full dataset, or final test is correct.

## Repository audit

Inspect and record:

- train, inference, evaluation, export, and checkpoint entrypoints;
- configuration sources and precedence;
- model construction and trainable-parameter selection;
- dataset classes, collators, sampling, padding, masks, labels, shifts, and augmentation;
- loss terms, reductions, weights, and ignored elements;
- optimizer parameter groups, scheduler units, gradient accumulation, clipping, AMP, and distributed reduction;
- train/eval mode and stochastic layers;
- metric implementation, prediction postprocessing, aggregation, and sample weighting;
- resume semantics and checkpoint round-trip;
- protected evaluator, splits, preprocessing, and final-test paths.

Write explicit unknowns to `repository/audit.json`; do not infer correctness from familiar filenames.

## Deterministic path gate

Start with one fixed example and fixed randomness:

1. run two forwards and verify identical outputs where the objective permits;
2. verify shapes, dtypes, devices, masks, targets, ignored indices, and finite loss;
3. compare loss to a simple expected or independently computed case when feasible;
4. run backward and verify intended modules receive finite non-zero gradients;
5. confirm frozen modules do not update;
6. run one optimizer step and verify target parameters change;
7. verify `zero_grad`, accumulation, and loss normalization with one versus multiple microbatches;
8. save/load a checkpoint and reproduce inference output within declared tolerance.

For stochastic objectives, first freeze noise, masks, negative samples, environment transitions, or augmentation. Validate the production stochastic path separately after the deterministic path works.

## Tiny-set overfit ladder

Run the smallest applicable ladder:

```text
T0: one fixed example
T1: one in-memory batch, usually 2–32 examples
T2: a few batches through the production dataset/collator
T3: checkpoint restart plus production evaluator on the same tiny set
```

Initially remove avoidable regularization: data augmentation, dropout, label smoothing, mixup, stochastic depth, and weight decay. Record every change. Then restore the production path and verify the conclusion still holds or explain why stochastic regularization changes the attainable loss.

Task-aware success criteria:

- classification: near-perfect training accuracy and loss near the attainable lower bound;
- deterministic regression: error near numerical/representation tolerance;
- autoregressive generation: fixed short sequences are memorized with correct shift/padding behavior;
- masked objectives: fixed-mask overfit first, then stochastic-mask behavior;
- diffusion/flow: fixed noise/timestep deterministic fit, then a production stochastic-path check;
- contrastive learning: positive pairs separate from negatives and the fixed batch can be memorized without target leakage;
- frozen-backbone/adapter training: verify capacity with full tuning or a sufficiently expressive adapter before blaming the pipeline;
- RL: use a deterministic toy environment or fixed offline transitions; ordinary supervised loss-to-zero criteria do not transfer directly.

Failure is a hard block. Diagnose label/mask errors, detached graphs, wrong parameter groups, loss scaling, learning rate, initialization, train/eval mode, preprocessing, or insufficient capacity before proceeding.

## Negative controls

Use controls appropriate to the task:

- zero-input or input-independent baseline;
- constant-output baseline;
- shuffled-label/input-pair test;
- no-update run;
- duplicate-sample and sample-count checks;
- randomized model evaluation;
- train/eval preprocessing identity check;
- deliberately wrong split or mask fixture that the validator must reject.

Unexpectedly strong controls are evidence-integrity failures, not good results.

## Baseline registry

For each baseline record:

- paper and citation;
- official repository and commit;
- license and model/data access conditions;
- official config/checkpoint and expected result range;
- environment lock;
- data snapshot, split, preprocessing, evaluator, and aggregation;
- adaptation required by the new study;
- evidence class and reproduction status;
- all attempted runs and discrepancies.

Reproduce the closest primary baseline first. Use official checkpoints to isolate evaluator issues before expensive retraining when available.

## Discrepancy ladder

If a baseline differs from the paper:

1. verify exact metric definition, direction, units, averaging, and checkpoint selection;
2. run the official checkpoint in the official evaluator;
3. run the official checkpoint in the study evaluator and compare per-example outputs;
4. compare data manifests, preprocessing, tokenizer/representation, and splits;
5. compare environment and numerical precision;
6. compare training schedule, effective batch, optimizer, seed, and resume behavior;
7. only then inspect implementation differences.

Do not tune the new method while the primary baseline protocol is unresolved. If exact reproduction is impossible, mark the baseline and central claim accordingly rather than silently mixing protocols.

## Gate artifact

Record every check in `reports/sanity_report.json` with `pass`, `fail`, `not_applicable`, evidence paths, and residual risks. `TINY_OVERFIT` and `BASELINE_REPRODUCTION` may complete only when required checks pass or an explicit scientific/protocol disposition narrows the study.
