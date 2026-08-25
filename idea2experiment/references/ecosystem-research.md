# Experiment-Automation Ecosystem and Design Decisions

This note records why the core is a claim-and-evidence orchestrator with adapters rather than another trainer, sweep engine, or experiment dashboard. Recheck upstream behavior before relying on a specific integration; these projects evolve independently.

## Agentic research systems

- [MLAgentBench](https://github.com/snap-stanford/MLAgentBench) gives agents a repository-like environment in which they inspect files, run repeated ML experiments, retain interaction traces, and compare against a starter baseline. It demonstrates the value of executable environments and full trajectories, while its benchmark objective does not by itself define a complete paper-level evidence program.
- [The AI Scientist](https://github.com/SakanaAI/AI-Scientist) joins idea generation, code changes, experiments, and paper writing around experiment templates. [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2) broadens this with an experiment-manager-guided search tree. These systems motivate iterative hypothesis--experiment loops, but their own safety guidance also supports sandboxed code execution and bounded authority.
- [MLE-Agent](https://github.com/MLSysOps/MLE-agent) combines baseline construction, research retrieval, coding, and debugger--coder interaction. It is useful evidence for repository adapters and explicit debugging roles rather than a reason to hard-code one domain stack.
- [AgentHPOBench](https://github.com/OpenMOSS/AgentHPOBench) evaluates sequential interventions from a validated baseline while retaining configuration, metric, log, and decision provenance. Its scope reinforces the separation between nuisance HPO and the broader scientific experiment graph.
- [MLE-bench](https://github.com/openai/mle-bench), [SUPER](https://github.com/allenai/super-benchmark), and [PaperBench](https://github.com/openai/frontier-evals/tree/main/project/paperbench) expose complementary limits: engineering a competitive model, executing tasks from real research repositories, and reproducing paper results are related but different objectives. PaperBench's separation of agent rollout, clean execution, and grading directly motivates independent reproduction and evaluation stages.

## Configuration, sweeps, scheduling, and recovery

- [Hydra multirun](https://hydra.cc/docs/tutorials/basic/running_your_app/multi-run/) composes configuration grids and delegates launching to plugins. Use it behind an adapter when a repository already uses Hydra; preserve the fully resolved configuration because Hydra notes that lazy composition can observe later code/config changes.
- [W&B Sweeps](https://docs.wandb.ai/models/sweeps) supports grid, random, Bayesian, and early-termination searches across workers. It is an optional nuisance-HPO backend, not the authority that decides scientific controls or final-test access.
- [Ray Tune](https://docs.ray.io/en/latest/tune/tutorials/overview.html) supplies resource-aware trials, schedulers, checkpointing, persistent storage, and fault tolerance. Its recovery documentation distinguishes resuming an unchanged interrupted experiment from changing a completed experiment, which matches this skill's immutable-run and explicit-retry rules.
- [Optuna](https://optuna.readthedocs.io/en/stable/) supplies samplers, pruners, storage, and distributed optimization. It may implement a declared search node, but its trials must still inherit the study's data, protocol, budget, and result-provenance contract.

## Tracking, data lineage, and reproducibility

- [MLflow Tracking](https://mlflow.org/docs/latest/tracking/) records runs, parameters, code versions, metrics, artifacts, model checkpoints, and dataset links. It is a compatible external result store; the local immutable ledger remains valid when MLflow is unavailable or unauthorized.
- [DVC experiments](https://dvc.org/doc/user-guide/experiment-management) connect pipeline/data versions with reproducible experiment changes and comparison. DVC may provide code/data lineage behind an adapter, but paper claims still need claim-specific gates and audit.

## Resulting architecture

No surveyed tool alone enforces all of the following: tiny-overfit before expensive work, compatible baseline reproduction, explicit model and data scaling, fair module controls, scientific-versus-nuisance parameter separation, failure taxonomy, frozen final-test access, and claim-level evidence disposition. Therefore:

1. the core owns claims, DAG dependencies, promotion gates, protocol hashes, failure classes, and evidence audit;
2. repository/domain adapters own trainer and evaluator entrypoints;
3. Hydra, W&B, Ray Tune, Optuna, MLflow, DVC, Slurm, Kubernetes, or private schedulers are optional backends behind adapters;
4. agentic search proposes diagnostics or new graph nodes but cannot rewrite old runs, evaluators, or final-test evidence;
5. clean reproduction and independent metric recomputation are separate from implementation/search.

This boundary keeps the workflow generic across LLMs, vision, language, multimodal learning, diffusion, reinforcement learning, robotics, motion, and future model families.
