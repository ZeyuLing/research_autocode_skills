from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from _common import load_json, resolve_study_root


READY_STATES = {"PLANNED", "PREFLIGHT", "SMOKE"}
RETRY_STATES = {"FAILED_ENGINEERING", "CANCELLED"}
ACTIVE_STATES = {"QUEUED", "RUNNING", "EVALUATING", "AUDITING"}
ATTENTION_STATES = {"FAILED_ENGINEERING", "FAILED_SCIENTIFIC", "INVALID_PROTOCOL", "BLOCKED", "CANCELLED"}


def summarize(graph: dict[str, Any], limit: int) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    by_id = {node["id"]: node for node in nodes}
    ready = []
    waiting = []
    retryable = []
    active = []
    attention = []
    for node in nodes:
        status = node.get("status")
        unsatisfied = [parent for parent in node.get("parents", []) if by_id.get(parent, {}).get("status") != "DONE"]
        item = {
            "id": node.get("id"),
            "family": node.get("family"),
            "fidelity": node.get("fidelity"),
            "status": status,
            "unsatisfied_parents": unsatisfied,
        }
        if status in READY_STATES:
            (ready if not unsatisfied else waiting).append(item)
        if status in RETRY_STATES and not unsatisfied:
            retryable.append(item)
        if status in ACTIVE_STATES:
            active.append(item)
        if status in ATTENTION_STATES:
            attention.append(item)

    if active:
        recommendation = "monitor_active"
    elif attention:
        recommendation = "diagnose_or_resolve_attention_nodes"
    elif ready:
        recommendation = "execute_ready_nodes"
    elif nodes and all(node.get("status") == "DONE" for node in nodes):
        recommendation = "study_graph_complete"
    else:
        recommendation = "resolve_parent_or_planning_blocker"

    return {
        "schema_version": 1,
        "graph_version": graph.get("graph_version"),
        "recommendation": recommendation,
        "ready": ready[:limit] if limit else ready,
        "ready_total": len(ready),
        "waiting_total": len(waiting),
        "retryable": retryable,
        "active": active,
        "attention": attention,
        "status_counts": dict(Counter(node.get("status") for node in nodes)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List executable and attention-needed experiment nodes.")
    parser.add_argument("study_root")
    parser.add_argument("--limit", type=int, default=0, help="Limit ready nodes shown; zero means no limit.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    root = resolve_study_root(args.study_root)
    payload = summarize(load_json(root / "experiments" / "experiment_graph.json"), args.limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"recommendation={payload['recommendation']} ready={payload['ready_total']} "
            f"active={len(payload['active'])} attention={len(payload['attention'])}"
        )
        for item in payload["ready"]:
            print(f"READY {item['id']} family={item['family']} fidelity={item['fidelity']}")
        for item in payload["attention"]:
            print(f"ATTENTION {item['id']} status={item['status']} family={item['family']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
