# Project Contract

Use this contract for every new, resumed, or partially supplied project.

## Input contract

Record these fields in `project.json`:

| Field | Required behavior |
|---|---|
| `idea_original` | Preserve the user's wording verbatim. |
| `idea_version` | Start at `idea_v0`; increment after every Professor revision. |
| `language` | Use the user's requested paper language; default to English. |
| `target_venue` | Preserve a supplied venue; otherwise set `auto`. |
| `existing_assets` | List papers, code, data, models, and results supplied by the user. |
| `compute_source` | Use user resources or `current_machine`. |
| `data_source` | Use user resources or `relevant_open_candidates`. |
| `automation_mode` | Default to `autopilot`; only stop for a genuine blocking decision. |

Do not ask for information that can be discovered safely. Record reasonable defaults as explicit assumptions.

## Canonical layout

```text
<project>/
  project.json
  resources.json
  state.json
  venue/{candidates.json,decision.json,template/}
  related_works/{00_scope.md,01_query_plan.md,source_ledger.csv,papers_raw.csv,
                 papers_merged.csv,papers_enriched.csv,screening.csv,snowball_log.csv,survey_receipt.json,survey_skill_snapshot.md,survey_run.json,
                 reading_matrix.csv,coverage_audit.md,synthesis_outline.md,
                 papers/,notes/,raw/,exports/}
  idea/{versions/,meetings/round_01/,claims.csv,terminology.csv}
  method/{method_spec.md,decision_log.md}
  experiments/{plan.md,claim_experiment_matrix.csv,baseline_provenance.csv}
  figures/{inputs/,prompts/,generated/,qa/,manifest.csv}
  paper/{main.tex,idea2paper-draft.sty,sections/,tables/,figures/,appendix/,references.bib}
  qa/{todo_registry.json,citation_report.md,consistency_report.md,
      figure_report.md,layout_report.md,final_report.json}
  build/
```

Keep internal decision logs outside `paper/`. Copy only selected paper-consumed imagegen outputs into `paper/figures/`.

## State machine

Use these ordered stages:

```text
INTAKE -> VENUE_LOCKED -> RESOURCES_READY -> LITERATURE_AUDITED
-> IDEA_REVIEWED -> IDEA_FROZEN -> CLAIM_GRAPH_FROZEN
-> METHOD_EXPERIMENT_READY -> MANUSCRIPT_DRAFTED -> SKETCH_COMPLETE
-> RESULTS_INTEGRATED -> SUBMISSION_READY
```

Each stage record contains `status`, `updated_utc`, `input_versions`, `artifacts`, and `notes`. Allowed statuses are `pending`, `in_progress`, `complete`, `stale`, and `blocked`.

Never treat file existence alone as completion. Confirm the artifact was generated from the current idea, resource, literature, venue, and result versions.

## Ownership and concurrency

- Let the orchestrator alone update canonical `project.json`, `state.json`, the current idea, the claim graph, and the manuscript.
- Let Student A, Student B, and the Professor write different files.
- Let parallel literature searches write different raw exports; merge only after all finish.
- Let each imagegen call write a versioned output. Promote one selected version explicitly.
- Never let two agents edit the same file concurrently.

## Resume and invalidation

On resume, read `state.json`, verify declared artifacts, and begin at the earliest `pending` or `stale` stage. Preserve earlier versions for auditability.

Use `scripts/state_manager.py invalidate` for upstream changes. Do not delete stale artifacts; retain them as history and generate a new version.

## Completion labels

- `SKETCH_COMPLETE`: all paper content exists; only registered predicted results, qualitative placeholders, method alternatives, or template updates remain.
- `SUBMISSION_READY`: real results are integrated, all draft macros/TODOs are removed, the current official template is used, the paper meets the exact page limit, and all QA gates pass.

Do not call `SKETCH_COMPLETE` submission-ready.
