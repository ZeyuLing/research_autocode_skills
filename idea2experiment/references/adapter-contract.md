# Repository and Scheduler Adapter Contract

The core is domain-independent. An adapter translates experiment nodes into project commands and expected artifacts without changing research semantics.

## Adapter file

Place `adapters/adapter.json` in the study. The minimal local form is:

```json
{
  "version": 1,
  "name": "project-local",
  "working_directory": "../code",
  "environment": {},
  "commands": {
    "default": [
      "python",
      "train.py",
      "--experiment-config",
      "{config_path}",
      "--run-dir",
      "{run_dir}"
    ],
    "evaluate": [
      "python",
      "evaluate.py",
      "--run-dir",
      "{run_dir}"
    ]
  },
  "required_outputs": ["metrics.json"],
  "protected_paths": ["eval/", "splits/"],
  "timeout_seconds": 0
}
```

Commands are JSON argv arrays. The core runner does not invoke a shell. Do not embed pipes, redirects, `&&`, command substitutions, or environment expansion; use a project wrapper script when multi-step behavior is required.

Keep only non-sensitive fixed settings in `environment`. Declare credential-bearing or private runtime keys by name in `environment_from_host`; the runner requires them to exist but never writes their values. Keys in `record_environment_keys` are recorded only as presence plus a value hash. Never put secrets in command arguments because resolved argv is an auditable artifact.

Supported substitutions:

- `{study_root}` absolute study root;
- `{run_dir}` immutable run directory;
- `{config_path}` generated experiment config;
- `{experiment_id}` stable node ID;
- `{run_id}` immutable run-attempt ID;
- `{seed}` model/run seed;
- `{subset_seed}` data-subset seed;
- `{code_repo}` configured code repository.

Each substitution remains one argv element, and literal braces in code or JSON arguments are preserved. The runner also exports `I2E_STUDY_ROOT`, `I2E_RUN_DIR`, `I2E_EXPERIMENT_ID`, `I2E_RUN_ID`, `I2E_CONFIG_PATH`, `I2E_SEED`, and `I2E_SUBSET_SEED`.

## Required project capabilities

An adapter should expose or synthesize:

```text
build/inspect model from a scale spec
load a frozen data manifest/subset
run deterministic and tiny-overfit modes
train or fine-tune
save/resume checkpoints
write predictions with sample IDs
evaluate with a protected protocol
emit metrics.json and diagnostic artifacts
```

If an existing repository lacks a unified interface, add a thin project-local wrapper rather than duplicating training logic for every experiment.

## Experiment config input

The runner writes `config.json` containing:

- experiment ID, family, hypothesis, and parents;
- scientific factors;
- nuisance parameters;
- model scale and protocol;
- data scale, sources, mixture, exposure, and seeds;
- baseline/method variant;
- fidelity and resource request;
- metrics, required outputs, promotion gate, and protected protocol hash.

The project command must treat it as resolved immutable input. Additional configuration sources and overrides must be recorded in the run manifest.

## Output contract

At minimum write `metrics.json`:

```json
{
  "schema_version": 1,
  "experiment_id": "E_MAIN_S3_D5",
  "run_id": "...",
  "split": "validation",
  "metrics": {
    "primary_metric": {"value": 0.0, "direction": "maximize"}
  },
  "sample_count": 0,
  "prediction_artifact": "predictions/predictions.jsonl",
  "protocol_hash": "sha256:..."
}
```

Use task-specific fields as needed, but preserve stable sample IDs and enough raw output to recompute central metrics.

## Scheduler adapters

Local execution is the core default. Remote adapters may support SSH, Slurm/Submitit, Ray, Kubernetes, or private platforms. In the current synchronous core, the adapter wrapper must submit, poll, and collect before it exits; returning immediately after submission is an incomplete run. It must:

- submit an immutable run spec;
- record a stable external job ID in the run directory;
- expose poll, cancel, and collect operations;
- preserve stdout/stderr/checkpoints and exit reason;
- distinguish scheduler failure from scientific outcome;
- avoid hard-coded credentials, hosts, queues, or private paths;
- require authorization appropriate to external cost and data movement.

Scheduler choice must not alter experiment IDs, data/protocol hashes, or evidence requirements.

## Domain adapters

Domain adapters may add:

- task-aware overfit criteria;
- model scale-axis discovery;
- dataset/split validation;
- metrics and failure taxonomies;
- qualitative rendering and human-evaluation protocols.

They may not disable final-test isolation, baseline compatibility, provenance, immutable runs, or independent metric recomputation.

## Adapter validation

Before full experiments:

1. dry-run command resolution;
2. deterministic single-example execution;
3. tiny-overfit execution;
4. checkpoint round-trip;
5. evaluator recomputation;
6. required-output and failure-code fixtures;
7. resource/timeout behavior;
8. protected-path hash verification.

Record adapter version/hash in every run.
