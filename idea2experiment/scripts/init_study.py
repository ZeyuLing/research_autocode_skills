from __future__ import annotations

import argparse
from pathlib import Path

from _common import STAGES, slugify, utc_now, write_json
from scan_resources import collect_resources


def default_state(study_id: str) -> dict:
    stages = {}
    for stage in STAGES:
        status = "completed" if stage in {"INTAKE", "RESOURCE_AUDIT"} else "pending"
        stages[stage] = {"status": status, "version": 1, "reason": "", "updated_at": utc_now()}
    return {"schema_version": 1, "study_id": study_id, "updated_at": utc_now(), "stages": stages}


def default_study(study_id: str, code_repo: str | None, data_inputs: list[str]) -> dict:
    return {
        "schema_version": 1,
        "study_id": study_id,
        "created_at": utc_now(),
        "idea_version": 0,
        "code_repo": code_repo,
        "data_inputs": data_inputs,
        "claims": [],
        "baselines": [],
        "model_scaling": {
            "status": "unresolved",
            "reason": "",
            "axes": [],
            "protocols": [],
            "rungs": [],
        },
        "data_scaling": {
            "status": "unresolved",
            "reason": "",
            "protocols": [],
            "rungs": [],
            "sources": [],
            "mixtures": [],
        },
        "modules": [],
        "module_study": {"status": "unresolved", "reason": ""},
        "module_interactions": [],
        "hyperparameters": {"scientific": [], "nuisance": []},
        "parameter_study": {"status": "unresolved", "reason": ""},
        "statistics": {
            "primary_metric": None,
            "direction": "unresolved",
            "unit_of_analysis": "unresolved",
            "seed_policy": {
                "mode": "adaptive",
                "pilot_seeds": [0, 1, 2],
                "confirmatory_minimum": 3,
                "confirmatory_maximum": 10,
                "extension_rule": "set from pilot variance and the claim-specific uncertainty target",
            },
            "final_test_policy": "frozen",
        },
        "adapter": None,
        "additional_families": [],
    }


def create_study(args: argparse.Namespace) -> Path:
    name = args.study_name or slugify(args.idea[:80])
    study_id = slugify(name)
    parent = Path(args.out_dir).expanduser().resolve()
    root = parent / study_id
    if root.exists():
        raise FileExistsError(f"Refusing to overwrite existing path: {root}")

    directories = [
        "idea/versions",
        "repository",
        "data/splits",
        "baselines",
        "protocols",
        "adapters",
        "experiments/configs",
        "runs",
        "evidence",
        "reports/debug",
    ]
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=False)

    (root / "idea" / "idea_v0.md").write_text(args.idea.rstrip() + "\n", encoding="utf-8")

    code_repo = str(Path(args.code_repo).expanduser().resolve()) if args.code_repo else None
    data_inputs = list(args.data or [])
    write_json(root / "study.json", default_study(study_id, code_repo, data_inputs))
    write_json(root / "state.json", default_state(study_id))
    write_json(root / "resources.json", collect_resources(root))
    write_json(
        root / "repository" / "audit.json",
        {"schema_version": 1, "status": "pending", "code_repo": code_repo, "findings": [], "unknowns": []},
    )
    write_json(
        root / "data" / "manifest.json",
        {
            "schema_version": 1,
            "status": "pending" if data_inputs else "unresolved",
            "inputs": data_inputs,
            "sources": [],
            "splits": {},
            "preprocessing_hash": None,
        },
    )
    write_json(root / "baselines" / "registry.json", {"schema_version": 1, "baselines": []})
    write_json(
        root / "protocols" / "protocol.json",
        {
            "schema_version": 1,
            "version": 1,
            "status": "unresolved",
            "split_hash": None,
            "preprocessing_hash": None,
            "evaluator_hash": None,
            "aggregation_hash": None,
            "final_test_policy": "frozen",
        },
    )
    write_json(root / "protocols" / "protected_hashes.json", {"schema_version": 1, "paths": []})
    write_json(
        root / "experiments" / "experiment_plan.json",
        {"schema_version": 1, "graph_version": 0, "status": "unplanned", "families": {}, "warnings": []},
    )
    write_json(
        root / "experiments" / "experiment_graph.json",
        {"schema_version": 1, "graph_version": 0, "created_at": utc_now(), "nodes": []},
    )
    write_json(root / "evidence" / "claims.json", {"schema_version": 1, "claims": []})
    write_json(root / "evidence" / "result_index.json", {"schema_version": 1, "results": []})
    write_json(root / "evidence" / "exclusions.json", {"schema_version": 1, "exclusions": []})
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a durable idea2experiment study.")
    parser.add_argument("--idea", required=True, help="The user's original research idea, preserved verbatim.")
    parser.add_argument("--out-dir", required=True, help="Parent directory for the new study.")
    parser.add_argument("--study-name", help="Optional stable study slug.")
    parser.add_argument("--code-repo", help="Existing or starter code repository path.")
    parser.add_argument("--data", action="append", help="Data path or URI; repeat for multiple inputs.")
    args = parser.parse_args()

    root = create_study(args)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
