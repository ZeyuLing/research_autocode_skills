# Debugging and Scientific Re-planning

Use this reference whenever a run crashes, metrics look suspicious, a curve is non-monotonic, a module fails, or the main hypothesis is unsupported. Debugging is evidence gathering, not random modification.

## Failure taxonomy

Classify before acting:

1. `evidence_integrity`: leakage, evaluator mutation, phantom/missing artifacts, cherry-picking, wrong aggregation;
2. `data`: corruption, schema, labels, duplicates, split, sampling, mixture, preprocessing;
3. `engineering`: import, shape, device, distributed, checkpoint, resource, scheduler;
4. `protocol`: baseline incompatibility, metric definition, budget, train/eval mismatch;
5. `optimization`: flat/divergent loss, unstable gradients, under-training, bad schedule;
6. `generalization`: train success but validation/test failure, domain shift, overfitting;
7. `scale_interaction`: effect changes with model, data, train, or inference scale;
8. `statistical`: high variance, insufficient independent units, adaptive-selection bias;
9. `scientific`: valid experiment contradicts the mechanism or claim.

The category may change as diagnostics arrive. Record the prior and evidence for each update.

## Evidence-first decision tree

```text
Are artifacts complete and evaluator/split/protocol hashes valid?
├─ No  → INVALID_PROTOCOL; repair audit/evaluation and recompute from predictions
└─ Yes
   Can the deterministic and tiny-overfit gates pass?
   ├─ No  → data/engineering/optimization diagnostics; block downstream runs
   └─ Yes
      Can the primary baseline reproduce within declared tolerance?
      ├─ No  → protocol/environment/evaluator discrepancy ladder
      └─ Yes
         Does the method optimize the intended training objective?
         ├─ No  → optimization, gradient, capacity, and implementation probes
         └─ Yes
            Does it generalize on frozen validation?
            ├─ No  → overfitting, split, mixture, regularization, distribution probes
            └─ Yes
               Is the claimed effect stable across seeds/scale/data?
               ├─ No  → interaction/statistical studies; qualify the regime
               └─ Yes → confirm and audit the claim
```

## Symptom-to-diagnostic map

| Symptom | First diagnostics | Allowed plan change |
|---|---|---|
| Tiny overfit fails | labels/masks/shifts, gradient reachability, optimizer groups, loss reduction, deterministic noise, capacity | fix verified defects; do not scale |
| Loss is flat | LR range, schedule units, frozen parameters, detached graph, target entropy, input-independent baseline | correct optimization or implementation |
| NaN/explosion | input/logit/activation/gradient finiteness, fp32 pilot, initialization, AMP, masks, accumulation normalization | bounded numerical repair with new run |
| Train good, validation poor | leakage audit, learning curves, group slices, data quality, regularization, distribution shift | add data/regularization or narrow generalization claim |
| Baseline mismatch | official checkpoint/evaluator, per-example metric diff, data/preprocessing/environment/config | block main comparison until compatible or qualify protocol |
| Larger model worse | equal-exposure/iso-compute audit, under-training, scale-specific LR/warmup/init/batch, stability | retune nuisance per scale; add tokens; revise scale rule |
| More data hurts | fixed-token vs fixed-epoch, source slices, add/leave-one, duplicates/noise, mixture at two scales | reweight/remove sources only after controlled evidence |
| Module has no effect | execution trace, gradient/output perturbation, A/B/A+B, parameter/compute controls | remove, merge, strengthen probe, or narrow mechanism |
| Module removal improves | nuisance retuning per arm, optimization stability, cost controls | remove by default or state verified trade-off |
| Seeds disagree | paired seeds, more independent units, data-subset seeds, CI/effect | mark inconclusive until resolved |
| Result is implausibly good | final-test access, duplicates, ground truth in features, evaluator hash, independent recompute | invalidate immediately if integrity fails |
| Validation winner fails final test | validation adaptation, selection count, checkpoint choice, hidden slices | never tune on final; qualify or reject claim |

## Diagnostic-node contract

Every diagnostic has:

- parent failed/suspicious experiment ID;
- competing explanations it separates;
- minimal changed factor;
- expected observation under each explanation;
- protected protocol and data split;
- stop rule and follow-up mapping;
- result and confidence.

Example:

```text
E_MODEL_SCALE_S3 failed
├── D_S3_FIXED_EXPOSURE_AUDIT
├── D_S3_LR_RANGE
├── D_S3_FP32_SHORT
└── D_S3_GRADIENT_BY_LAYER
```

Never edit `E_MODEL_SCALE_S3` into a different experiment. The repaired run gets a new ID and references the diagnostics.

## Retry policy

- deterministic infrastructure glitches may retry with identical config;
- verified engineering fixes create a new code snapshot and run;
- OOM may change microbatch/accumulation only if effective batch and numerical protocol remain declared; otherwise version the protocol;
- repeated unexplained failure triggers a diagnostic or human gate, not unlimited retries;
- scientific underperformance is not retryable without a new hypothesis, configuration rationale, or evidence-supported diagnostic.

## Scientific re-planning

When valid results oppose the idea:

1. check whether the predicted mechanism changed;
2. if the mechanism changed but the outcome did not, identify the downstream bottleneck;
3. if the mechanism did not change, revise implementation or theory based on probes;
4. if the effect exists only in a scale/data/domain regime, narrow the claim to that regime;
5. if a simpler method is equivalent, prefer the simpler method and record the negative ablation insight;
6. if no supported regime remains, reject the hypothesis or create `idea_vN` with explicit ancestry.

Replanning updates the claim graph and creates new experiment nodes. It never changes old metrics, removes failed runs, or accesses the final test for guidance.

## Debug report

Write `reports/debug/<diagnostic-id>.json` with symptoms, taxonomy, evidence, candidate causes, selected diagnostic, result, fix/replan decision, affected nodes, and remaining uncertainty. A concise permanent history is more valuable than a long chat transcript.
