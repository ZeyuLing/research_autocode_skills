from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from _common import NODE_STATUSES, STAGES, STAGE_STATUSES, load_json, resolve_study_root, update_json, utc_now


FAMILY_STAGE = {
    "deterministic_sanity": "DETERMINISTIC_SANITY",
    "tiny_overfit": "TINY_OVERFIT",
    "negative_control": "TINY_OVERFIT",
    "baseline_reproduction": "BASELINE_REPRODUCTION",
    "pilot": "PILOT",
    "model_scaling": "MODEL_SCALING",
    "data_scaling": "DATA_SCALING",
    "data_mixture": "DATA_SCALING",
    "module_study": "MODULE_STUDY",
    "parameter_search": "PARAMETER_STUDY",
    "parameter_sensitivity": "PARAMETER_STUDY",
    "confirmatory": "CONFIRMATORY",
    "robustness": "ROBUSTNESS",
    "efficiency": "ROBUSTNESS",
    "qualitative": "QUALITATIVE",
    "human_evaluation": "QUALITATIVE",
    "diagnostic": "PILOT",
    "independent_audit": "INDEPENDENT_AUDIT",
    "claim_sync": "CLAIM_SYNC",
}


def show(root: Path, as_json: bool) -> None:
    state = load_json(root / "state.json")
    graph = load_json(root / "experiments" / "experiment_graph.json")
    payload = {
        "study_id": state.get("study_id"),
        "stages": state.get("stages", {}),
        "graph_version": graph.get("graph_version", 0),
        "node_statuses": dict(Counter(node.get("status") for node in graph.get("nodes", []))),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"Study: {payload['study_id']}  Graph: v{payload['graph_version']}")
    for stage in STAGES:
        info = payload["stages"].get(stage, {})
        reason = f" — {info.get('reason')}" if info.get("reason") else ""
        print(f"{stage:24} {info.get('status', 'missing'):15}{reason}")
    print("Nodes:", ", ".join(f"{key}={value}" for key, value in sorted(payload["node_statuses"].items())))


def set_stage(root: Path, stage: str, status: str, reason: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"Unknown stage: {stage}")
    if status not in STAGE_STATUSES:
        raise ValueError(f"Unknown stage status: {status}")
    if status in {"blocked", "not_applicable", "stale", "invalidated"} and not reason.strip():
        raise ValueError(f"Status {status} requires --reason")

    def updater(state: dict[str, Any]) -> dict[str, Any]:
        if status == "in_progress":
            active = [
                name
                for name, info in state.get("stages", {}).items()
                if info.get("status") == "in_progress" and name != stage
            ]
            if active:
                raise ValueError(f"Another orchestration stage is already in progress: {active[0]}")
        entry = state["stages"][stage]
        entry.update(
            {
                "status": status,
                "version": int(entry.get("version", 0)) + 1,
                "reason": reason,
                "updated_at": utc_now(),
            }
        )
        state["updated_at"] = utc_now()
        return state

    update_json(root / "state.json", updater)


def set_experiment(root: Path, experiment_id: str, status: str, reason: str) -> None:
    if status not in NODE_STATUSES:
        raise ValueError(f"Unknown experiment status: {status}")

    def updater(graph: dict[str, Any]) -> dict[str, Any]:
        for node in graph.get("nodes", []):
            if node.get("id") == experiment_id:
                node["status"] = status
                node["status_reason"] = reason
                node["updated_at"] = utc_now()
                return graph
        raise KeyError(f"Experiment not found: {experiment_id}")

    update_json(root / "experiments" / "experiment_graph.json", updater)


def invalidate(root: Path, stage: str, reason: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"Unknown stage: {stage}")
    start = STAGES.index(stage)

    def state_updater(state: dict[str, Any]) -> dict[str, Any]:
        for name in STAGES[start:]:
            entry = state["stages"][name]
            previous = entry.get("status")
            entry.update(
                {
                    "status": "invalidated" if name == stage else "stale",
                    "version": int(entry.get("version", 0)) + 1,
                    "reason": f"Upstream invalidation at {stage}: {reason}",
                    "previous_status": previous,
                    "updated_at": utc_now(),
                }
            )
        state["updated_at"] = utc_now()
        return state

    update_json(root / "state.json", state_updater)

    def graph_updater(graph: dict[str, Any]) -> dict[str, Any]:
        for node in graph.get("nodes", []):
            node_stage = FAMILY_STAGE.get(node.get("family"))
            if node_stage and STAGES.index(node_stage) >= start:
                node["previous_status"] = node.get("status")
                node["status"] = "BLOCKED"
                node["stale"] = True
                node["status_reason"] = f"Upstream invalidation at {stage}: {reason}"
                node["updated_at"] = utc_now()
        return graph

    update_json(root / "experiments" / "experiment_graph.json", graph_updater)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and update idea2experiment study state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("study_root")
    show_parser.add_argument("--json", action="store_true")

    set_parser = subparsers.add_parser("set")
    set_parser.add_argument("study_root")
    set_parser.add_argument("--stage", required=True)
    set_parser.add_argument("--status", required=True)
    set_parser.add_argument("--reason", default="")

    experiment_parser = subparsers.add_parser("experiment")
    experiment_parser.add_argument("study_root")
    experiment_parser.add_argument("--id", required=True)
    experiment_parser.add_argument("--status", required=True)
    experiment_parser.add_argument("--reason", default="")

    invalidate_parser = subparsers.add_parser("invalidate")
    invalidate_parser.add_argument("study_root")
    invalidate_parser.add_argument("--stage", required=True)
    invalidate_parser.add_argument("--reason", required=True)

    args = parser.parse_args()
    root = resolve_study_root(args.study_root)
    if args.command == "show":
        show(root, args.json)
    elif args.command == "set":
        set_stage(root, args.stage, args.status, args.reason)
    elif args.command == "experiment":
        set_experiment(root, args.id, args.status, args.reason)
    else:
        invalidate(root, args.stage, args.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
