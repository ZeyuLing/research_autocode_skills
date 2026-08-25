# Execution, Run Artifacts, and Independent Audit

Use this reference when launching, monitoring, evaluating, or promoting runs.

## Multi-fidelity promotion

Use the cheapest fidelity that can answer the current question:

```text
static/unit
→ deterministic single example
→ tiny overfit
→ small subset/short schedule
→ full data/short schedule
→ full single seed
→ confirmatory repeats
→ cross-setting robustness
→ clean reproduction
```

Short-run rankings are not assumed to transfer. Measure rank correlation or confirm top and representative rejected configurations at higher fidelity before using aggressive pruning.

## Execution preflight

Before launch verify:

- parent nodes and required gates are complete;
- code, adapter, environment, data, split, preprocessing, evaluator, and aggregation hashes;
- command argv and working directory;
- GPU/CPU/RAM/disk/resource request;
- output paths are unique and writable;
- expected artifacts and completion predicate;
- timeout, checkpoint, resume, retry, and failure policy;
- seed, subset seed, and final-test access;
- authorization for remote, paid, private, or external actions.

The core runner executes argv arrays without a shell. A scheduler adapter may submit work, but its wrapper must poll and collect to a terminal state before returning; it records the external job ID and preserves the same run contract.

## Immutable run layout

```text
runs/<experiment-id>/<run-id>/
├── manifest.json
├── resolved_command.json
├── config.json
├── code_snapshot.json
├── environment.json
├── data_snapshot.json
├── protocol_snapshot.json
├── stdout.log
├── stderr.log
├── checkpoints/
├── predictions/
├── metrics.json
├── curves/
├── qualitative/
├── artifact_hashes.json
└── audit.json
```

Never reuse a run directory. Resume inside the same directory only when the checkpoint and protocol contract explicitly support it; record every attempt. Scientific config changes require a new run ID.

## Monitoring

Track heartbeat, step/progress, loss, learning rate, throughput, memory, gradient/update norms when instrumented, checkpoint age, and expected completion. Detect:

- no heartbeat or stale logs;
- OOM and preemption;
- NaN/inf or exploding metrics;
- repeated data-loader errors;
- missing checkpoints or outputs;
- unexpected speed/memory regression;
- suspicious metric discontinuities.

Do not mark a process complete merely because it exited with code zero. Verify expected outputs, result counts, and parseable metrics.

## Evaluator isolation

The evaluator consumes predictions and a protected protocol. It should not import mutable training code when avoidable. Record:

- evaluator commit/hash;
- split and preprocessing hashes;
- metric implementation and version;
- sample IDs and expected count;
- per-sample or per-group outputs needed for reaggregation;
- final aggregation script/hash.

The implementation/search agent cannot modify protected assets. If it must change an evaluator bug, invalidate every dependent result and create a new protocol version.

## Audit checks

An independent evaluator/reviewer checks:

1. run exists and command/config/code/environment/data/protocol snapshots are complete;
2. required prediction and metric artifacts exist and hashes match;
3. sample count, IDs, duplicates, exclusions, weights, and missing outputs are correct;
4. metrics recompute from predictions;
5. baseline and method protocols are compatible;
6. no final-test feedback entered selection;
7. all attempted trials, seeds, failures, and exclusions are represented;
8. aggregation, uncertainty, and comparisons follow the preregistered statistical contract;
9. qualitative examples follow declared sampling/selection rules;
10. manuscript/result exports cite exact run and protocol IDs.

The same agent that implemented a metric should not be the only judge of its correctness when independent review is available.

## Evidence promotion

Promote through explicit transitions:

```text
OBSERVED     raw artifacts and metrics exist
AUDITED      independent recomputation and protocol audit pass
REPRODUCED   clean-environment or independent repeat agrees within tolerance
```

Promotion appends a record to `evidence/result_index.json`; it does not edit an old result. Failed promotion writes `audit.json` and leaves the result at its prior class.

## Result export

Export a paper-facing result only with:

- stable paper/claim key;
- value and uncertainty;
- source run IDs;
- metric extractor and aggregation hashes;
- protocol hash;
- evidence class;
- caveats or scope;
- timestamp/version.

Forecast or literature-reported values remain separate. If a writing workflow uses placeholder macros, replace them only from an audited export and preserve unresolved TODOs.

## Safety and recovery

- use isolated worktrees or explicit code snapshots rather than destructive reset;
- never print secrets into logs or manifests;
- avoid implicit network uploads by experiment trackers;
- keep local tracking as a valid default;
- require authorization before paid or private external work;
- terminate runaway processes by exact run/job ID, not broad name matching;
- preserve partial logs and checkpoints after cancellation.
