---
name: idea2experiment
description: Turn a rough AI/ML research idea, an existing or starter codebase, available data, and compute into a complete executable and auditable experiment program. Use when Codex must inspect a repository and datasets, reproduce baselines, prove the training path with deterministic and tiny-set overfit gates, run model- and data-scaling studies, design module/strategy and key-parameter experiments, diagnose unexpected results, re-plan the experiment DAG, and return measured evidence with exact run provenance. Triggers include idea2experiment, automate experiments, run all experiments, scale experiment, data scaling, ablation implementation, hyperparameter study, experiment debugging, 自动做实验, 自动跑完实验, 模型scale, 数据scale, 过拟合小数据, and 实验不符合预期.
---

# Idea to Experiment

Build and execute a domain-independent research experiment program. The outcome is not a desired score: it is a versioned claim-to-evidence graph in which every planned claim is supported, qualified, or rejected by reproducible runs. Treat domain logic as an adapter. Never put motion-, language-, vision-, diffusion-, robotics-, or reinforcement-learning assumptions in the core protocol.

## Non-negotiable rules

1. Preserve the user's original idea verbatim and keep every failed or superseded run. Do not rewrite history or delete evidence to make a method look successful.
2. Never treat estimated, expected, literature-reported, or paper-placeholder values as measurements. Only an `AUDITED` or `REPRODUCED` result may update a manuscript claim.
3. Freeze data splits, preprocessing, evaluator code, aggregation rules, and final-test access behind protocol hashes. An implementation/search agent may not modify protected evaluation assets.
4. Pass deterministic-path and tiny-set-overfit gates before any expensive pilot, scaling, ablation, hyperparameter, or main experiment. A smoke run that merely avoids crashing is not an overfit test.
5. Reproduce the primary baseline under a compatible local protocol before claiming improvement. Preserve literature-reported, official-checkpoint, locally evaluated, locally retrained, and protocol-adapted results as different evidence classes.
6. Make model scale and data scale first-class experiment families whenever the claim or method can depend on scale. Mark a family `not_applicable` only with a concrete reason; do not silently omit it.
7. Separate scientific factors from nuisance hyperparameters. Give competing scientific arms comparable nuisance-tuning budgets before drawing a module, strategy, optimizer, or architecture conclusion.
8. Classify unexpected outcomes as evidence-integrity, data, engineering, protocol, optimization, generalization, scale-interaction, statistical, or scientific failures before changing the method. Debug by adding diagnostic DAG nodes; never overwrite the original run.
9. Keep exploratory validation separate from confirmatory evaluation. Do not use final-test feedback to select methods, datasets, mixtures, checkpoints, examples, seeds, or hyperparameters.
10. Avoid destructive repository recovery. Use isolated worktrees, branches, or immutable run snapshots; never use `git reset --hard` in a user's working tree.
11. Respect the compute and external-system authority the user supplied. The submission deadline is not a feasibility filter, but paid resources, private data access, large external downloads, credentials, and remote job submission still require existing authorization.

## Start or resume a study

Read [project-contract.md](references/project-contract.md) before creating or resuming a study. Use Python 3.10 or newer. On Windows, reject a Microsoft Store alias that exits without a runtime and use an installed or Codex-bundled interpreter consistently.

For a new study:

```bash
python scripts/init_study.py --idea "<verbatim idea>" --out-dir <parent-directory> \
  [--study-name <slug>] [--code-repo <path>] [--data <path-or-uri>]...
```

When compute is omitted, the initializer records the current machine. When data is omitted, record data discovery as unresolved; do not interpret “open data” as permission to download every public dataset.

For an existing study:

```bash
python scripts/state_manager.py show <study-root>
python scripts/validate_study.py <study-root>
```

Resume the earliest blocked, pending, stale, or invalidated gate. Do not rerun completed work unless an upstream protocol, code, data, or dependency hash changed.

## Reference routing

Load only the references needed for the current decision:

| Task | Required reference |
|---|---|
| Study layout, state, evidence classes, completion | [project-contract.md](references/project-contract.md) |
| Repository/data inspection, deterministic tests, tiny overfit, baseline gate | [sanity-and-baselines.md](references/sanity-and-baselines.md) |
| Model-size, active-parameter, compute, and held-out extrapolation studies | [model-scaling.md](references/model-scaling.md) |
| Data quantity, quality, source mixture, repetition, and harmful-data diagnosis | [data-scaling.md](references/data-scaling.md) |
| Module factorials, matched controls, HPO, sensitivity, and statistics | [module-and-parameter-studies.md](references/module-and-parameter-studies.md) |
| Failure taxonomy, diagnostic decision tree, bounded repair, and scientific re-planning | [debugging-and-replanning.md](references/debugging-and-replanning.md) |
| Local execution, immutable run artifacts, independent evaluation, and result promotion | [execution-and-audit.md](references/execution-and-audit.md) |
| Connecting an arbitrary repository, trainer, evaluator, scheduler, or domain | [adapter-contract.md](references/adapter-contract.md) |
| Selecting or integrating an existing agent, sweep, tracker, lineage, or scheduler backend | [ecosystem-research.md](references/ecosystem-research.md) |

The JSON contracts live under `references/schemas/`. Validate the maintained invariants with `scripts/validate_study.py`; the schemas document the public contract but do not replace semantic validation.

## Canonical workflow

### 0. Normalize the research contract

1. Preserve the exact initial idea as `idea/idea_v0.md`.
2. Extract claims, anti-claims, success metrics, closest baselines, code status, data sources, target operating regime, and resource constraints.
3. Classify each claim as performance, mechanism, scaling, data, efficiency, robustness, qualitative, or negative claim.
4. Map each claim to the minimum evidence families required. “All experiments” means all evidence needed to support, qualify, or reject these declared claims, not unbounded search.
5. Record assumptions and unresolved choices in study metadata, never as measured facts.

### 1. Audit repository, data, resources, and evaluator

Inspect code entrypoints, configuration flow, dataset classes, loss construction, train/eval mode, checkpoint round-trip, metrics, distributed paths, and protected assets. Fingerprint code, environment, data manifests, splits, preprocessing, evaluator, and aggregation scripts. Create or repair the adapter contract before planning executable runs.

### 2. Pass sanity gates

Run in order:

1. deterministic single-example forward and loss checks;
2. gradient reachability and parameter-delta checks;
3. one-batch overfit through a minimal deterministic path;
4. tiny-dataset overfit through the production loader and checkpoint path;
5. task-appropriate negative controls;
6. primary baseline reproduction.

If a gate fails, stop downstream scheduling and enter the relevant diagnostic branch. Read [sanity-and-baselines.md](references/sanity-and-baselines.md).

### 3. Build the experiment graph

Populate `study.json` with scale axes, data sources, method modules, scientific factors, nuisance parameters, baselines, metrics, and adapter path, then run:

```bash
python scripts/plan_experiments.py <study-root>
python scripts/validate_study.py <study-root> --strict
```

The graph must contain, where applicable:

- small-model/small-data pilot;
- model-scale ladder with an explicit comparison protocol;
- data-quantity ladder with explicit compute exposure;
- data-quality, source-mixture, add-one, leave-one-out, or repetition studies when multiple sources exist;
- module/strategy controls and interactions;
- nuisance HPO and scientific-parameter sensitivity;
- target-scale confirmatory multi-seed runs;
- robustness, efficiency, qualitative, or human evaluation only when required by claims;
- independent evaluation, artifact audit, and result-to-claim nodes.

### 4. Execute through promotion gates

Use multi-fidelity promotion rather than launching every full run immediately:

```text
STATIC → DETERMINISTIC → TINY_OVERFIT → SMALL_SUBSET → SHORT_SCHEDULE
       → FULL_SINGLE_SEED → FULL_MULTI_SEED → CROSS_SETTING → CLEAN_REPRODUCTION
```

Run one node with:

```bash
python scripts/next_experiments.py <study-root> --json
python scripts/run_experiment.py <study-root> <experiment-id> [--dry-run]
```

The ready-node query distinguishes executable, active, retryable, waiting, and attention-needed nodes. Re-run it after every completion or failure; do not jump past an attention node merely because unrelated downstream nodes were planned. Ready nodes may run concurrently only when resource requests, protected outputs, and adapter behavior do not conflict.

The runner uses an argv-array adapter without a shell, refuses unsatisfied parents during actual execution, creates an immutable run directory, captures stdout/stderr and resolved commands, verifies required outputs, and hashes artifacts. Retrying `FAILED_ENGINEERING` or `CANCELLED` requires `--retry-reason`. Scheduler-specific deployment belongs behind an adapter; do not hard-code `screen`, SSH, Slurm, or a private platform into the core.

### 5. Diagnose and re-plan

When a result is missing, unstable, suspicious, or contrary to the hypothesis:

1. invalidate evidence with broken evaluator, split, preprocessing, result completeness, or provenance;
2. distinguish engineering failure from a valid negative scientific result;
3. generate the smallest diagnostic experiment that separates plausible causes;
4. link diagnostics to the failed node and preserve the old protocol version;
5. repair only evidence-supported engineering defects;
6. narrow a claim, change the scale/data regime, simplify a module, or create a new hypothesis version when the scientific evidence requires it;
7. bound retries by failure class and stop optimization against the final test.

Use `scripts/state_manager.py invalidate` when an upstream artifact changes. For engineering defects, use the installed `autodebug` skill when available; it must operate inside the current experiment node and may not reinterpret a scientific failure as a bug.

### 6. Confirm, audit, and promote evidence

For confirmatory results:

- use preregistered metrics, seed policy, unit of analysis, aggregation, exclusions, and stopping rules;
- preserve all attempted configurations and failed runs;
- recompute metrics from predictions with the protected evaluator;
- verify result count, hashes, protocol compatibility, and exact run IDs;
- use an independent reviewer/evaluator context when delegation is available;
- promote results through `OBSERVED → AUDITED → REPRODUCED` rather than editing values in place.

Do not claim significance from a fixed “three seeds” rule. Choose repeats from the variance, unit of analysis, paired design, claim size, and compute budget; report uncertainty and effect size appropriate to the task.

### 7. Finish or return to research

A study is complete only when:

1. every required sanity and baseline gate passes or has an explicit blocking disposition;
2. model and data scaling are completed or justified as not applicable;
3. core modules and key parameters have fair, interpretable studies;
4. every planned claim is supported, qualified, rejected, or marked inconclusive;
5. every promoted number traces to immutable runs and a protocol hash;
6. independent audit finds no unresolved evidence-integrity issue;
7. measured evidence is exported without mixing it with forecast values.

If the hypothesis fails cleanly, completion may mean a negative result or a narrowed claim. Do not continue merely to obtain a positive number.

## Core versus adapters

The core owns experiment semantics, state, scaling protocols, scheduling dependencies, failure classification, evidence promotion, and audit. Adapters own only repository-specific operations such as:

```text
build_model(scale_spec)
load_dataset(data_manifest)
train(config, run_dir)
predict(checkpoint, split, run_dir)
evaluate(predictions, protected_protocol)
render_qualitative(artifacts)
submit_or_poll_scheduler(run_spec)
```

Provide separate adapters for LLM pretraining, LLM fine-tuning, vision, multimodal, diffusion, RL, robotics, motion, or project-local systems. A domain adapter may add task-specific gates and metrics, but it may not weaken core provenance, final-test isolation, tiny-overfit, baseline, or audit requirements.

## Scope boundaries

- This skill executes and audits experiments; use `idea2paper` for venue/template selection and manuscript drafting.
- It may consume an `idea2paper` claim/experiment matrix, but it also works directly from an idea, repository, and data.
- It does not guarantee SOTA, a positive hypothesis, exhaustive search, unrestricted external access, or a publication outcome.
- The workflow is designed to keep unsuccessful work visible, version protocol changes, and make promoted evidence traceable.
