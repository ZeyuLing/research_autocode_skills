from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any

from _common import NODE_STATUSES, STAGES, STAGE_STATUSES, load_json, resolve_study_root, sha256_file, utc_now, write_json


REQUIRED_FILES = [
    "study.json",
    "state.json",
    "resources.json",
    "idea/idea_v0.md",
    "repository/audit.json",
    "data/manifest.json",
    "baselines/registry.json",
    "protocols/protocol.json",
    "protocols/protected_hashes.json",
    "experiments/experiment_plan.json",
    "experiments/experiment_graph.json",
    "evidence/claims.json",
    "evidence/result_index.json",
    "evidence/exclusions.json",
]
SENSITIVE_ENVIRONMENT_TOKENS = {"TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "PRIVATE_KEY", "CREDENTIAL"}


def add(report: dict[str, Any], level: str, code: str, message: str, path: str | None = None) -> None:
    item = {"code": code, "message": message}
    if path:
        item["path"] = path
    report[level].append(item)


def read_required_json(root: Path, relative: str, report: dict[str, Any]) -> Any | None:
    path = root / relative
    if not path.is_file():
        add(report, "errors", "missing_file", f"Required file is missing: {relative}", relative)
        return None
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        add(report, "errors", "invalid_json", f"Cannot parse {relative}: {exc}", relative)
        return None


def validate_state(state: dict[str, Any], report: dict[str, Any]) -> None:
    stages = state.get("stages")
    if not isinstance(stages, dict):
        add(report, "errors", "state_stages", "state.json must contain a stages object")
        return
    active = []
    for stage in STAGES:
        info = stages.get(stage)
        if not isinstance(info, dict):
            add(report, "errors", "missing_stage", f"Missing stage state: {stage}")
            continue
        status = info.get("status")
        if status not in STAGE_STATUSES:
            add(report, "errors", "stage_status", f"Invalid status for {stage}: {status}")
        if status == "in_progress":
            active.append(stage)
        if status in {"blocked", "not_applicable", "stale", "invalidated"} and not str(info.get("reason", "")).strip():
            add(report, "errors", "stage_reason", f"Stage {stage} with status {status} needs a reason")
    if len(active) > 1:
        add(report, "errors", "multiple_active_stages", f"Multiple orchestration stages are in progress: {active}")


def validate_family(name: str, value: Any, strict: bool, report: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        add(report, "errors", "family_shape", f"{name} must be an object")
        return
    status = value.get("status")
    allowed = {"required", "not_applicable", "blocked", "unresolved"}
    if status not in allowed:
        add(report, "errors", "family_status", f"{name}.status must be one of {sorted(allowed)}")
        return
    if status in {"not_applicable", "blocked"} and not str(value.get("reason", "")).strip():
        add(report, "errors", "family_reason", f"{name} with status {status} needs a reason")
    if strict and status == "unresolved":
        add(report, "errors", "family_unresolved", f"{name} must be resolved before strict execution")
    if name in {"model_scaling", "data_scaling"} and status == "required":
        if not value.get("protocols"):
            add(report, "errors", "missing_protocols", f"{name} is required but has no protocols")
        if not value.get("rungs"):
            add(report, "errors", "missing_rungs", f"{name} is required but has no rungs")


def valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest.lower())


def sensitive_environment_key(value: Any) -> bool:
    upper = str(value).upper()
    return any(
        upper == token or upper.startswith(token + "_") or upper.endswith("_" + token)
        for token in SENSITIVE_ENVIRONMENT_TOKENS
    )


def validate_protocol(protocol: dict[str, Any], strict: bool, report: dict[str, Any]) -> None:
    if protocol.get("final_test_policy") != "frozen":
        add(report, "errors" if strict else "warnings", "protocol_final_test", "Protocol must freeze final-test access")
    if strict and protocol.get("status") != "frozen":
        add(report, "errors", "protocol_status", "Strict execution requires protocol.status=frozen")
    for key in ("split_hash", "preprocessing_hash", "evaluator_hash", "aggregation_hash"):
        if not valid_sha256(protocol.get(key)):
            add(
                report,
                "errors" if strict else "warnings",
                "protocol_hash",
                f"Protocol {key} must be a concrete sha256 digest",
            )


def validate_study(root: Path, study: dict[str, Any], strict: bool, report: dict[str, Any]) -> None:
    required = [
        "schema_version",
        "study_id",
        "idea_version",
        "claims",
        "baselines",
        "model_scaling",
        "data_scaling",
        "modules",
        "module_study",
        "hyperparameters",
        "parameter_study",
        "statistics",
        "adapter",
    ]
    for key in required:
        if key not in study:
            add(report, "errors", "study_key", f"study.json is missing {key}")

    validate_family("model_scaling", study.get("model_scaling"), strict, report)
    validate_family("data_scaling", study.get("data_scaling"), strict, report)
    validate_family("module_study", study.get("module_study"), strict, report)
    validate_family("parameter_study", study.get("parameter_study"), strict, report)

    claims = study.get("claims", [])
    if strict and not claims:
        add(report, "errors", "no_claims", "Strict execution requires at least one declared claim")
    claim_ids = [item.get("id") for item in claims if isinstance(item, dict)]
    if len(claim_ids) != len(set(claim_ids)):
        add(report, "errors", "duplicate_claim", "Claim IDs must be unique")
    for claim in claims:
        if not isinstance(claim, dict) or not claim.get("id") or not str(claim.get("text", "")).strip():
            add(report, "errors", "claim_shape", f"Malformed claim: {claim}")
        if not claim.get("required_families"):
            add(report, "warnings", "claim_evidence", f"Claim {claim.get('id')} has no required experiment families")

    baselines = study.get("baselines", [])
    if strict and not any(item.get("primary") for item in baselines if isinstance(item, dict)):
        add(report, "errors", "primary_baseline", "Strict execution requires a primary baseline")

    code_repo = study.get("code_repo")
    if strict and not code_repo:
        add(report, "errors", "code_repo", "Strict execution requires an existing or starter code repository")
    elif code_repo:
        code_repo_path = Path(code_repo).expanduser()
        code_repo_path = code_repo_path if code_repo_path.is_absolute() else root / code_repo_path
        if not code_repo_path.is_dir():
            add(report, "errors", "code_repo_missing", f"Configured code repository does not exist: {code_repo}")

    statistics = study.get("statistics", {})
    if strict and not statistics.get("primary_metric"):
        add(report, "errors", "primary_metric", "Strict execution requires a primary metric")
    if strict and statistics.get("direction") not in {"maximize", "minimize"}:
        add(report, "errors", "metric_direction", "Strict execution requires maximize or minimize direction")
    if statistics.get("final_test_policy") != "frozen":
        level = "errors" if strict else "warnings"
        add(report, level, "final_test", "Final-test policy must be frozen before adaptive experiments")

    module_status = (study.get("module_study") or {}).get("status")
    if module_status == "required" and not study.get("modules"):
        add(report, "errors", "modules_empty", "Module study is required but no modules are declared")
    parameter_status = (study.get("parameter_study") or {}).get("status")
    parameters = study.get("hyperparameters", {})
    if parameter_status == "required" and not (parameters.get("scientific") or parameters.get("nuisance")):
        add(report, "errors", "parameters_empty", "Parameter study is required but no parameters are declared")

    adapter_value = study.get("adapter")
    if strict and not adapter_value:
        add(report, "errors", "adapter_missing", "Strict execution requires a configured adapter")
    if adapter_value:
        adapter_path = Path(adapter_value).expanduser()
        if not adapter_path.is_absolute():
            adapter_path = root / adapter_path
        if not adapter_path.is_file():
            add(report, "errors", "adapter_missing", f"Adapter file does not exist: {adapter_value}")
        else:
            try:
                adapter = load_json(adapter_path)
                commands = adapter.get("commands")
                if not isinstance(commands, dict) or not commands:
                    add(report, "errors", "adapter_commands", "Adapter must define at least one command")
                else:
                    for name, command in commands.items():
                        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                            add(report, "errors", "adapter_command", f"Adapter command {name} must be a non-empty argv array")
                for key in (adapter.get("environment") or {}):
                    if sensitive_environment_key(key):
                        add(
                            report,
                            "errors" if strict else "warnings",
                            "adapter_secret",
                            f"Adapter environment key {key} looks sensitive; load it from the authorized host environment instead of storing a literal",
                        )
            except (OSError, json.JSONDecodeError) as exc:
                add(report, "errors", "adapter_json", f"Cannot parse adapter: {exc}")


def graph_ancestors(node_id: str, parents: dict[str, list[str]]) -> set[str]:
    result: set[str] = set()
    stack = list(parents.get(node_id, []))
    while stack:
        item = stack.pop()
        if item in result:
            continue
        result.add(item)
        stack.extend(parents.get(item, []))
    return result


def validate_graph(root: Path, graph: dict[str, Any], study: dict[str, Any], strict: bool, report: dict[str, Any]) -> None:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        add(report, "errors", "graph_nodes", "experiment_graph.json must contain a nodes array")
        return
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(set(ids)):
        add(report, "errors", "duplicate_node", "Experiment node IDs must be unique")
    by_id = {node.get("id"): node for node in nodes if isinstance(node, dict) and node.get("id")}
    parents: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    indegree = {node_id: 0 for node_id in by_id}
    required_keys = {"id", "family", "hypothesis", "parents", "status", "fidelity", "config", "expected_outputs", "promotion_gate"}
    protocol_path = root / "protocols" / "protocol.json"
    current_protocol_hash = sha256_file(protocol_path) if protocol_path.is_file() else None
    for node_id, node in by_id.items():
        missing = sorted(required_keys - set(node))
        if missing:
            add(report, "errors", "node_keys", f"Node {node_id} is missing {missing}")
        if node.get("status") not in NODE_STATUSES:
            add(report, "errors", "node_status", f"Node {node_id} has invalid status {node.get('status')}")
        if not str(node.get("hypothesis", "")).strip():
            add(report, "errors", "node_hypothesis", f"Node {node_id} has no hypothesis")
        parents[node_id] = list(node.get("parents") or [])
        for parent in parents[node_id]:
            if parent not in by_id:
                add(report, "errors", "missing_parent", f"Node {node_id} references missing parent {parent}")
                continue
            children[parent].append(node_id)
            indegree[node_id] += 1
        config_path = node.get("config_path")
        if config_path and not (root / config_path).is_file():
            add(report, "errors", "config_missing", f"Node {node_id} config is missing: {config_path}")
        if strict and node.get("protocol_hash") != current_protocol_hash:
            add(report, "errors", "graph_protocol", f"Node {node_id} is not bound to the current frozen protocol")

    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(by_id):
        add(report, "errors", "graph_cycle", "Experiment graph contains a cycle")

    tiny_ids = [node_id for node_id, node in by_id.items() if node.get("family") == "tiny_overfit"]
    baseline_ids = [node_id for node_id, node in by_id.items() if node.get("family") == "baseline_reproduction"]
    pilot_ids = [node_id for node_id, node in by_id.items() if node.get("family") == "pilot"]
    confirm_ids = [node_id for node_id, node in by_id.items() if node.get("family") == "confirmatory"]
    audit_ids = [node_id for node_id, node in by_id.items() if node.get("family") == "independent_audit"]
    sync_ids = [node_id for node_id, node in by_id.items() if node.get("family") == "claim_sync"]
    if not tiny_ids:
        add(report, "errors", "tiny_gate", "Graph has no tiny-overfit gate")
    if not baseline_ids:
        add(report, "errors", "baseline_gate", "Graph has no baseline-reproduction gate")
    if not pilot_ids:
        add(report, "errors", "pilot_gate", "Graph has no pilot node")
    for baseline in baseline_ids:
        if tiny_ids and not set(tiny_ids).intersection(graph_ancestors(baseline, parents)):
            add(report, "errors", "baseline_order", f"Baseline {baseline} is not downstream of tiny overfit")
    for pilot in pilot_ids:
        if baseline_ids and not set(baseline_ids).intersection(graph_ancestors(pilot, parents)):
            add(report, "errors", "pilot_order", f"Pilot {pilot} is not downstream of baseline reproduction")
    for node_id, node in by_id.items():
        if node.get("family") in {"model_scaling", "data_scaling", "data_mixture", "module_study", "parameter_search", "parameter_sensitivity"}:
            if pilot_ids and not set(pilot_ids).intersection(graph_ancestors(node_id, parents)):
                add(report, "errors", "family_order", f"{node_id} is not downstream of the pilot")
    for confirm in confirm_ids:
        if pilot_ids and not set(pilot_ids).intersection(graph_ancestors(confirm, parents)):
            add(report, "errors", "confirm_order", f"Confirmatory node {confirm} is not downstream of the pilot")
    for audit in audit_ids:
        if confirm_ids and not set(confirm_ids).intersection(graph_ancestors(audit, parents)):
            add(report, "errors", "audit_order", f"Audit node {audit} is not downstream of confirmatory runs")
    for sync in sync_ids:
        if audit_ids and not set(audit_ids).intersection(graph_ancestors(sync, parents)):
            add(report, "errors", "sync_order", f"Claim-sync node {sync} is not downstream of audit")

    families_present = {node.get("family") for node in nodes}
    for claim in study.get("claims", []):
        for family in claim.get("required_families", []):
            if family not in families_present:
                add(report, "errors" if strict else "warnings", "claim_family", f"Claim {claim.get('id')} requires missing family {family}")


def validate_protected(root: Path, protected: dict[str, Any], report: dict[str, Any]) -> None:
    for entry in protected.get("paths", []):
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not relative or not expected:
            add(report, "errors", "protected_entry", f"Malformed protected-path entry: {entry}")
            continue
        path = Path(relative)
        path = path if path.is_absolute() else root / path
        if not path.is_file():
            add(report, "errors", "protected_missing", f"Protected file is missing: {relative}")
        elif sha256_file(path) != expected:
            add(report, "errors", "protected_hash", f"Protected file hash mismatch: {relative}")


def validate_runs(root: Path, graph: dict[str, Any], report: dict[str, Any]) -> None:
    for node in graph.get("nodes", []):
        for run_id in node.get("runs", []):
            run_dir = root / "runs" / node["id"] / run_id
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.is_file():
                add(report, "errors", "run_manifest", f"Run manifest missing: {node['id']}/{run_id}")
                continue
            manifest = load_json(manifest_path)
            if manifest.get("experiment_id") != node["id"] or manifest.get("run_id") != run_id:
                add(report, "errors", "run_identity", f"Run identity mismatch: {node['id']}/{run_id}")
            hashes_path = run_dir / "artifact_hashes.json"
            if manifest.get("status") == "DONE" and not hashes_path.is_file():
                add(report, "errors", "run_hashes", f"Completed run lacks artifact hashes: {node['id']}/{run_id}")
            if hashes_path.is_file():
                for relative, expected in load_json(hashes_path).get("artifacts", {}).items():
                    path = (run_dir / relative).resolve()
                    try:
                        path.relative_to(run_dir.resolve())
                    except ValueError:
                        add(report, "errors", "artifact_path", f"Artifact path escapes run directory: {node['id']}/{run_id}/{relative}")
                        continue
                    if not path.is_file() or sha256_file(path) != expected:
                        add(report, "errors", "artifact_hash", f"Artifact missing or changed: {node['id']}/{run_id}/{relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an idea2experiment study and experiment DAG.")
    parser.add_argument("study_root")
    parser.add_argument("--strict", action="store_true", help="Require all execution-critical choices to be resolved.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()
    root = resolve_study_root(args.study_root)
    report: dict[str, Any] = {
        "schema_version": 1,
        "study_root": str(root),
        "strict": args.strict,
        "checked_at": utc_now(),
        "errors": [],
        "warnings": [],
    }

    loaded: dict[str, Any] = {}
    for relative in REQUIRED_FILES:
        if relative.endswith(".json"):
            loaded[relative] = read_required_json(root, relative, report)
        elif not (root / relative).is_file():
            add(report, "errors", "missing_file", f"Required file is missing: {relative}", relative)

    state = loaded.get("state.json")
    study = loaded.get("study.json")
    graph = loaded.get("experiments/experiment_graph.json")
    protected = loaded.get("protocols/protected_hashes.json")
    protocol = loaded.get("protocols/protocol.json")
    if state:
        validate_state(state, report)
    if study:
        validate_study(root, study, args.strict, report)
    if protocol:
        validate_protocol(protocol, args.strict, report)
    if graph and study:
        validate_graph(root, graph, study, args.strict, report)
        validate_runs(root, graph, report)
    if protected:
        validate_protected(root, protected, report)

    report["valid"] = not report["errors"]
    report["summary"] = {"errors": len(report["errors"]), "warnings": len(report["warnings"])}
    write_json(root / "reports" / "validation.json", report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"valid={report['valid']} errors={len(report['errors'])} warnings={len(report['warnings'])}")
        for item in report["errors"]:
            print(f"ERROR [{item['code']}]: {item['message']}")
        for item in report["warnings"]:
            print(f"WARNING [{item['code']}]: {item['message']}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
