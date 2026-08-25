# Module, Strategy, Hyperparameter, and Statistical Studies

Use this reference to turn a method description into fair interventions rather than a collection of convenient runs.

## Bind every component to a mechanism

For each core module or strategy record:

- problem/failure it targets;
- intervention and expected mechanism;
- intermediate quantity that should change first;
- final metric and protected secondary metrics;
- removal condition;
- standard previous-work replacement;
- parameter- and compute-matched controls;
- likely interaction with other modules, scale, or data;
- anti-claim or alternative explanation.

If a module has no observable mechanism and no distinct intervention, merge it with its parent component or treat it as implementation detail rather than a contribution.

## Factorial policy

For binary core modules:

- up to 3 factors: use a full `2^k` factorial by default;
- 4 factors: use full factorial when affordable; otherwise use a documented high-resolution fractional design plus targeted interactions;
- more factors: use a screening design or staged probing, then confirm the core main effects and plausible two-factor interactions.

At minimum for two modules A and B, run `Base`, `A`, `B`, and `A+B`. `Full-A` and `Full-B` alone cannot identify whether either module works alone or interacts with the other.

If a reduced design aliases effects, record the confounding structure and do not claim an isolated effect until a targeted follow-up resolves it.

## Fair controls

Depending on the method, include:

- removal/no-op;
- simple or previous-work alternative;
- equal added parameters without the proposed mechanism;
- equal training FLOPs or wall-clock;
- equal inference compute or sampling budget;
- equal data exposure;
- placebo/randomized intervention;
- oracle upper bound only when clearly labeled and unavailable to the trained method.

All arms share splits, evaluator, preprocessing, aggregation, and selection policy.

## Scientific versus nuisance parameters

Scientific factors answer the paper question: module presence, architecture family, objective, data strategy, or a key method parameter. Nuisance parameters help each arm train fairly: learning rate, optimizer details, warmup, regularization, schedule, and often batch-related choices.

Give each scientific arm a comparable nuisance-tuning budget. A shared hyperparameter setting is fair only when transfer is validated or the setting is itself the controlled condition.

Record:

- search space and transforms;
- number of attempted and failed trials;
- sampler and pruning rule;
- validation selection metric;
- seed and data-subset policy;
- selected configuration and selection uncertainty;
- whether the winner lies near a search boundary.

## HPO workflow

Use HPO to optimize nuisance parameters, not to manufacture a scientific conclusion.

1. establish broad literature/baseline-informed ranges;
2. use random or low-discrepancy sampling for broad exploration;
3. use multi-fidelity pruning only when short-run ranking correlates sufficiently with full runs;
4. refine promising regions with TPE/Bayesian or another justified optimizer;
5. expand ranges when winners cluster at a boundary;
6. confirm top configurations with independent seeds and full fidelity;
7. keep all attempted trials and account for adaptive selection.

Never tune against the final test. Use a protected confirmation split or nested validation when repeated adaptation could overfit the validation set.

## Paper sensitivity studies

Sensitivity is distinct from HPO. After a usable region is found:

- select interpretable values spanning below, around, and above the chosen value;
- use log spacing for positive scale parameters when appropriate;
- run one-dimensional response curves for key parameters;
- run two-dimensional studies only for important interactions;
- use repeated seeds or report uncertainty rather than plotting a selected lucky trial;
- expand the range when the optimum is at the boundary;
- state whether the method has a robust plateau, narrow optimum, monotonic trend, or instability region.

Do not present the same adaptively selected HPO trials as an unbiased sensitivity experiment without disclosure.

## Cross-scale confirmation

Verify core modules and method-specific parameters at a pilot scale and target scale. A gain that disappears may indicate nuisance-transfer failure, under-training, capacity redundancy, or a genuinely scale-limited contribution. Diagnose these alternatives before generalizing.

## Statistical contract

Before confirmatory runs define:

- primary metric and direction;
- unit of analysis: examples, groups, sequences, users, tasks, or seeds;
- paired/unpaired design and pairing key;
- aggregation and weighting;
- effect size and practically meaningful threshold;
- uncertainty interval or statistical test;
- multiple-comparison family when relevant;
- seed/repeat rule;
- stopping and rerun rules;
- exclusion criteria set before observing final results.

Do not hard-code three seeds as universal evidence. Use pilot variance and the actual independent unit. Preserve every failed run and explain exclusions.

## Component disposition

Classify components with evidence, not universal percentage thresholds:

- `essential`: required for a declared claim with stable mechanism and outcome evidence;
- `contributing`: improves a required outcome at acceptable cost;
- `conditional`: useful only for stated scale/data/domain regimes;
- `redundant`: no meaningful incremental value after fair controls;
- `harmful`: reliably worsens protected outcomes or cost without compensating claim value;
- `inconclusive`: evidence cannot separate the effect from variance or confounding.

Simplify redundant/harmful modules unless another verified contribution requires them. Create a new method version when the finalized method changes.
