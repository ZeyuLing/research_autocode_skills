# Claim, Method, and Experiment Contract

Freeze this contract after the idea council and before full manuscript writing.

## Claim graph

Populate `experiments/claim_experiment_matrix.csv` with:

```text
claim_id,limitation,evidence_ids,contribution_id,contribution,
method_component,hypothesis,experiment_id,datasets,baselines,metric,
figure_or_table,manuscript_locations,status
```

Use semicolon-separated `baseline_id` values from `baseline_provenance.csv` in the `baselines` column; do not put untracked display names there.

Require every contribution to identify a prior limitation, a method response, and an experiment. Require every core experiment to test a claim. Reject disconnected modules, decorative experiments, and unsupported Abstract claims.

Use stable prefixes:

- `C-*` claim
- `CONTRIB-*` contribution
- `M-*` method component
- `EXP-*` experiment
- `R-*` result slot
- `F-*` figure
- `T-*` table

## Method specification

Write:

1. formal problem definition, inputs, outputs, notation, and assumptions;
2. overview and data flow;
3. each novel module or strategy;
4. the exact limitation addressed by each component;
5. why the chosen design should address it;
6. objectives, algorithms, training, inference, and necessary complexity details;
7. interactions among modules;
8. reproducibility details known before experiments.

When a concrete implementation choice is unsettled, select the most likely effective option and use:

```latex
\DraftChoice{M-CHOICE-01}{chosen design text}
% TODO(M-CHOICE-01): Try alternative X if condition Y fails; replace with the implemented choice.
```

Keep the alternative in the source TODO or `method/decision_log.md`, not in rendered paper prose unless scientifically relevant.

## Experiment Setup

State the purpose of each experiment before mechanics. Record datasets, provenance, licenses, versions, splits, preprocessing, training data, hardware class, optimization, evaluation code, metrics, random seeds, and aggregation/statistical reporting planned.

Map primary metrics to the central claims. Add secondary metrics for efficiency, robustness, calibration, fairness, or failure modes only when relevant.

## Baseline policy

Select foundational, strong recent, closest-prior, and common-practice baselines. For every copied reported value, record source paper ID, exact table/row/column, dataset version, split, training data, backbone, preprocessing, metric definition, test-time setting, and whether it is directly comparable.

Use a prior paper's value in the main comparison only when protocols are compatible. Otherwise label it “reported” in a separate context or leave a TODO for reproduction. Never present copied values as locally reproduced.

## Predicted results

Choose targets by the evidence needed to support the claim. Place every predicted numeric value in:

```latex
\PredResult{R-MAIN-01}{82.4}
% TODO(R-MAIN-01): Replace with mean and standard deviation from EXP-MAIN-01.
```

Wrap every dependent prose statement in `\PredClaim{R-MAIN-01}{...}` and repeat an adjacent TODO. Use the same ID in Abstract, Introduction, Results, Teaser caption, and Conclusion when they depend on the same result.

Do not use untracked `\textcolor{red}{...}` for draft facts.

## Ablations and hyperparameters

- Use a full module cross when the number of core binary modules is tractable.
- Use an explicitly ordered probing design when a full cross would be unreasonable; explain that order and avoid interpreting incremental rows as independent effects.
- Compare the novel component with its absence and with the closest conventional implementation when one exists.
- Include core hyperparameter sensitivity when the method has a consequential hyperparameter.
- Put non-core component and hyperparameter studies in the appendix.
- Give every predicted ablation cell a result ID and TODO.
- Do not bake predicted numeric labels into raster figures. Keep predicted numbers in tracked LaTeX macros or tables until measured results exist.

## Qualitative results

Define what the qualitative comparison must reveal, how cases are selected, which baselines appear, and which hard/failure cases are required. Before outputs exist, generate only an unmistakable imagegen placeholder and bind it to `\QualPlaceholder{<ID>}{...}` plus a TODO. After results exist, preserve the actual evidence when imagegen arranges the layout.

## Result injection

When measured results arrive, record run/config/data/code versions, replace predictions, revise claim strength, regenerate affected imagegen figures, and rewrite every linked narrative location. Do not preserve a stronger predicted story when results support a weaker conclusion.
