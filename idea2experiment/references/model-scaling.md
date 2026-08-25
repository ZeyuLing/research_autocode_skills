# Model and Compute Scaling

Use this reference when a claim, architecture, training strategy, or deployment result may depend on model or inference scale. “Use a bigger model” is not a protocol; every scaling study states what is held fixed and what conclusion the comparison permits.

## Discover the scale axes

Inspect the repository and adapter for applicable axes:

- dense depth, width, hidden size, layers, heads, or total parameters;
- MoE total parameters, active parameters, expert count, capacity, or top-k;
- pretrained checkpoint family;
- trainable adapter parameters or rank;
- diffusion/flow backbone capacity and sampling compute;
- retrieval corpus, test-time search, reasoning steps, samples, or verifier compute;
- modality-specific encoder, fusion, and decoder scale.

Report total, trainable, and active parameters separately. Record training tokens/samples, FLOPs estimate, step time, throughput, wall-clock, peak memory, inference latency, and inference memory.

If no meaningful scale axis exists, mark model scaling `not_applicable` with a concrete architectural reason. Resource shortage is `blocked`, not `not_applicable`.

## Required protocol selection

Choose at least one protocol and prefer two when a central scaling claim is made.

### Fixed exposure

Keep data snapshot and total tokens/samples seen fixed while increasing capacity. This isolates capacity under equal exposure, but larger models may be under-trained.

### Iso-compute

Keep estimated training FLOPs or a justified wall-clock budget comparable. Adjust tokens/steps as model cost changes. This measures compute efficiency, not maximum attainable performance.

### Joint or compute-optimal scaling

Increase capacity and data/training exposure together using a pilot-fitted rule. Treat published scaling ratios as priors, not universal constants.

### Deployment-constrained scaling

Compare under fixed latency, memory, throughput, energy, or serving cost. Record the measurement environment and variance.

Do not combine points from different protocols on one fitted curve without labeling them.

## Construct a ladder

Create 4–6 geometrically spaced rungs when feasible:

```text
S0  smallest model that can pass tiny overfit
S1  low-cost pilot
S2  intermediate scale
S3  near-target scale
S4  target or maximum available scale
```

Use the same architecture family, tokenizer/representation, data/split, evaluator, and metric implementation. Change only the declared scale and protocol-dependent training exposure. When arbitrary released checkpoints are the only option, document architecture and data differences as confounders.

For MoE, compare active compute as well as total parameter count. For adapter methods, report base-model and trainable-parameter scaling separately.

## Hyperparameters across scale

Do not assume the same learning rate, warmup, regularization, batch size, initialization, clipping, or loss weights are fair at every scale.

- With a validated scale-transfer parameterization such as μP, tune on a proxy and verify transfer on the next rung before the target run.
- Otherwise allocate a comparable nuisance-tuning budget per rung or use an explicit scale rule with validation.
- If two scientific methods have different stable hyperparameter regions, retune nuisance parameters per method and scale.
- Record effective batch and scheduler units in tokens/samples, not ambiguous “epochs” alone.

## Extrapolation discipline

When fitting a scaling trend:

1. preregister the response variable and candidate functional form or selection rule;
2. fit only on smaller rungs;
3. hold out at least one larger rung;
4. predict the held-out result and uncertainty;
5. train the held-out rung and report extrapolation error;
6. reject or revise the fit if extrapolation fails.

Interpolation fit quality alone does not justify a large-scale prediction.

## Interaction studies

A core method or data claim may change with scale. Include targeted interactions:

```text
method × model scale
data mixture × model scale
training duration × model scale
inference compute × model scale
```

At minimum, verify core modules at a pilot scale and the target scale. If an improvement disappears, diagnose under-training and nuisance tuning before narrowing the claim to a low-resource regime.

## Promotion and stopping

Promote a rung only when the previous rung:

- passes sanity and artifact checks;
- has stable finite training;
- uses a valid evaluator and complete outputs;
- meets the study's pilot criterion or is needed to diagnose a non-monotonic trend.

Stop and diagnose when larger models become worse, unstable, severely under-trained, or protocol-incompatible. A non-monotonic result is evidence, not permission to discard the rung.

## Required report

Produce curves/tables for primary and diagnostic responses against:

- total/trainable/active parameters;
- training tokens/samples and unique data;
- estimated training compute;
- wall-clock and peak memory;
- inference cost;
- method effect at each scale.

State whether evidence supports monotonic improvement, saturation, threshold/phase behavior, a changed scaling slope, or no stable trend. Do not reduce the report to “larger is better.”
