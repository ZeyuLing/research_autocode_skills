# Study Contract

Read this file before creating or resuming an experiment study. The study directory is a durable research ledger, not a scratch folder. Every artifact has one owner and every downstream conclusion names its upstream versions.

## Canonical layout

```text
<study-root>/
├── study.json                         # research contract and experiment-family configuration
├── state.json                         # stage status, versions, invalidation reasons
├── resources.json                     # current/user-provided compute snapshot
├── idea/
│   ├── idea_v0.md                     # exact user input; immutable
│   └── versions/                      # later scientific revisions
├── repository/
│   └── audit.json                     # code, environment, entrypoint, protected-path audit
├── data/
│   ├── manifest.json                  # sources, versions, licenses, hashes, statistics
│   └── splits/                        # frozen split manifests; data may live elsewhere
├── baselines/
│   └── registry.json                  # reported, checkpoint, reproduced, adapted evidence
├── protocols/
│   ├── protocol.json                  # preprocessing/evaluator/aggregation/final-test policy
│   └── protected_hashes.json
├── adapters/
│   └── adapter.json                   # argv-array command contract
├── experiments/
│   ├── experiment_plan.json           # human-readable family summary
│   └── experiment_graph.json          # executable DAG
├── runs/                              # immutable run directories
├── evidence/
│   ├── claims.json                    # claim and anti-claim ledger
│   ├── result_index.json              # promoted result provenance
│   └── exclusions.json                # all excluded/invalid runs and reasons
└── reports/                           # validation, debug, audit, scaling, and export reports
```

Large datasets and checkpoints should remain in explicit external locations. The study stores manifests and hashes, not silent copies.

## Stages

Use these canonical stages:

```text
INTAKE
RESOURCE_AUDIT
REPOSITORY_AUDIT
DATA_AUDIT
PROTOCOL_FREEZE
DETERMINISTIC_SANITY
TINY_OVERFIT
BASELINE_REPRODUCTION
PILOT
MODEL_SCALING
DATA_SCALING
MODULE_STUDY
PARAMETER_STUDY
CONFIRMATORY
ROBUSTNESS
QUALITATIVE
INDEPENDENT_AUDIT
CLAIM_SYNC
```

Allowed stage statuses are `pending`, `in_progress`, `completed`, `blocked`, `not_applicable`, `stale`, and `invalidated`. At most one local orchestration stage is `in_progress`; experiment nodes may run concurrently when their parents are complete.

`not_applicable` requires a non-empty reason. `blocked` names the missing authority, resource, artifact, or scientific decision. `invalidated` means its evidence cannot be used. `stale` means upstream inputs changed and the work must be recomputed before promotion.

## Experiment-node states

```text
PLANNED → PREFLIGHT → SMOKE → QUEUED → RUNNING → EVALUATING → AUDITING → DONE
```

Terminal alternatives:

- `FAILED_ENGINEERING`: code, environment, resource, or infrastructure failure.
- `FAILED_SCIENTIFIC`: valid execution that does not support the hypothesis.
- `INVALID_PROTOCOL`: broken split, evaluator, preprocessing, aggregation, or provenance.
- `BLOCKED`: missing prerequisite or authorization.
- `CANCELLED`: explicitly stopped; preserve partial artifacts.

Do not relabel `FAILED_SCIENTIFIC` as engineering failure to justify indefinite retries.

## Evidence classes

Baseline/result provenance is one of:

- `LITERATURE_REPORTED`: copied from a cited source under its original protocol.
- `OFFICIAL_CHECKPOINT_EVALUATED`: official weights evaluated locally.
- `LOCALLY_REPRODUCED`: official code/config rerun locally under compatible protocol.
- `LOCALLY_RETRAINED`: locally implemented/retrained baseline under the study protocol.
- `PROTOCOL_ADAPTED`: baseline changed to fit a new dataset, representation, budget, or evaluator.
- `OBSERVED`: raw result exists but audit is incomplete.
- `AUDITED`: artifacts and metrics were independently recomputed and verified.
- `REPRODUCED`: audited result was recreated in a clean environment or independent run.

Never compare incompatible evidence classes as though they were the same experiment. Tables may show literature-reported context, but central improvement claims require compatible local evidence.

## Version and invalidation rules

Maintain monotonically increasing versions for:

- idea/hypothesis;
- code snapshot;
- data manifest and splits;
- preprocessing;
- evaluator and metric extractor;
- aggregation/statistical protocol;
- experiment graph;
- adapter.

If an upstream version changes, call:

```bash
python scripts/state_manager.py invalidate <study-root> --stage <STAGE> --reason "<why>"
```

The state manager invalidates downstream stages without deleting artifacts. Existing run directories remain immutable and are marked incompatible with the new protocol where appropriate.

## Claim contract

Each claim has:

- stable ID and text;
- type: performance, mechanism, scaling, data, efficiency, robustness, qualitative, or negative;
- primary and secondary metrics;
- minimum practically meaningful effect when definable;
- required experiment families;
- anti-claim or alternative explanation;
- status: proposed, exploratory, supported, qualified, rejected, or inconclusive;
- supporting result IDs and protocol hash.

A claim is never “supported” merely because one selected run improved. It becomes supported only after the required evidence set and independent audit pass.

## Completion

The study is complete when every required claim has a supported, qualified, rejected, or inconclusive disposition; required scale/data/module/parameter families are complete or justified; and every promoted numeric result resolves to run manifests, metrics, hashes, and a compatible protocol.

Completion does not require a positive paper result. A clean negative conclusion is a valid terminal state.

## Optional idea2paper bridge

When consuming an `idea2paper` project:

1. import its final idea version and claim-experiment matrix;
2. retain predicted values only as non-evidence targets;
3. assign new stable experiment IDs rather than treating LaTeX table rows as runs;
4. export only audited result records for manuscript backfill;
5. leave unresolved or failed claims visible so the writing workflow can narrow them.
