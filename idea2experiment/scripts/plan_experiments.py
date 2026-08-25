from __future__ import annotations

import argparse
import itertools
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from _common import file_lock, load_json, resolve_study_root, safe_node_token, sha256_file, utc_now, write_json


class Planner:
    def __init__(self, study: dict[str, Any]):
        self.study = study
        self.nodes: list[dict[str, Any]] = []
        self.ids: set[str] = set()
        self.warnings: list[str] = []

    def add(
        self,
        node_id: str,
        family: str,
        hypothesis: str,
        parents: list[str],
        fidelity: str,
        config: dict[str, Any] | None = None,
        *,
        status: str = "PLANNED",
        expected_outputs: list[str] | None = None,
        promotion_gate: list[str] | None = None,
        claim_ids: list[str] | None = None,
    ) -> str:
        if node_id in self.ids:
            raise ValueError(f"Duplicate experiment ID: {node_id}")
        self.ids.add(node_id)
        node = {
            "id": node_id,
            "family": family,
            "hypothesis": hypothesis,
            "claim_ids": claim_ids or [],
            "parents": list(dict.fromkeys(parents)),
            "status": status,
            "fidelity": fidelity,
            "seed": (config or {}).get("seed"),
            "subset_seed": (config or {}).get("subset_seed"),
            "config": config or {},
            "resources": {},
            "expected_outputs": expected_outputs or ["metrics.json"],
            "promotion_gate": promotion_gate
            or ["process_exit_zero", "required_outputs_complete", "protocol_hash_matches"],
            "protocol_hash": None,
            "runs": [],
        }
        self.nodes.append(node)
        return node_id

    def build(self) -> tuple[list[dict[str, Any]], list[str]]:
        claim_ids = [claim.get("id") for claim in self.study.get("claims", []) if claim.get("id")]

        deterministic = self.add(
            "E_SANITY_DETERMINISTIC",
            "deterministic_sanity",
            "A fixed example produces a valid deterministic loss, expected gradients, parameter updates, and checkpoint round-trip.",
            [],
            "deterministic",
            {"mode": "deterministic_sanity", "command_key": "deterministic_sanity"},
            promotion_gate=[
                "finite_loss",
                "target_gradients_present",
                "target_parameters_update",
                "checkpoint_roundtrip",
            ],
        )

        tiny_parent = deterministic
        for size in (1, 8, 32):
            tiny_parent = self.add(
                f"E_TINY_OVERFIT_{size}",
                "tiny_overfit",
                f"The production learning path can intentionally memorize a fixed set of {size} example(s) under a task-aware criterion.",
                [tiny_parent],
                "tiny_overfit",
                {"mode": "tiny_overfit", "tiny_size": size, "command_key": "tiny_overfit"},
                promotion_gate=["task_aware_memorization", "finite_gradients", "checkpoint_roundtrip"],
            )

        negative = self.add(
            "E_SANITY_NEGATIVE_CONTROLS",
            "negative_control",
            "Input-independent, shuffled-target, no-update, and task-specific negative controls behave materially worse than the valid learning path.",
            [tiny_parent],
            "tiny_overfit",
            {"mode": "negative_controls", "command_key": "negative_control"},
            promotion_gate=["controls_do_not_match_valid_model", "no_unexpected_leakage"],
        )

        baseline_nodes: list[str] = []
        baselines = self.study.get("baselines", [])
        if baselines:
            for baseline in baselines:
                baseline_id = str(baseline.get("id") or "baseline")
                baseline_nodes.append(
                    self.add(
                        f"E_BASELINE_{safe_node_token(baseline_id)}",
                        "baseline_reproduction",
                        f"Baseline {baseline_id} reproduces within its declared compatible-protocol tolerance.",
                        [negative],
                        "full_single_seed",
                        {
                            "mode": "baseline_reproduction",
                            "baseline": baseline,
                            "command_key": "baseline_reproduction",
                        },
                        promotion_gate=[
                            "compatible_protocol",
                            "required_outputs_complete",
                            "within_declared_tolerance_or_qualified",
                        ],
                        claim_ids=claim_ids,
                    )
                )
        else:
            baseline_nodes.append(
                self.add(
                    "E_BASELINE_UNRESOLVED",
                    "baseline_reproduction",
                    "A primary compatible baseline must be registered and reproduced before comparative experiments.",
                    [negative],
                    "full_single_seed",
                    {"mode": "baseline_reproduction", "command_key": "baseline_reproduction"},
                    status="BLOCKED",
                    promotion_gate=["primary_baseline_registered"],
                    claim_ids=claim_ids,
                )
            )
            self.warnings.append("No baseline is registered; downstream experiments remain blocked.")

        pilot = self.add(
            "E_PILOT_SMALL",
            "pilot",
            "The smallest meaningful method and data configuration is stable enough to estimate variance, cost, and promotion settings.",
            baseline_nodes,
            "small_subset",
            {"mode": "pilot", "command_key": "pilot", "seed": 0},
            claim_ids=claim_ids,
        )

        terminal_nodes: list[str] = [pilot]
        terminal_nodes.extend(self._build_model_scaling(pilot, claim_ids))
        terminal_nodes.extend(self._build_data_scaling(pilot, claim_ids))
        terminal_nodes.extend(self._build_module_studies(pilot, claim_ids))
        terminal_nodes.extend(self._build_parameter_studies(pilot, claim_ids))
        terminal_nodes.extend(self._build_additional_families(pilot, claim_ids))
        terminal_nodes = list(dict.fromkeys(terminal_nodes))

        seed_policy = self.study.get("statistics", {}).get("seed_policy", {})
        minimum = max(1, int(seed_policy.get("confirmatory_minimum", 3)))
        explicit = seed_policy.get("confirmatory_seeds")
        seeds = [int(seed) for seed in explicit] if explicit else list(range(minimum))
        confirmatory_nodes = []
        for seed in seeds:
            confirmatory_nodes.append(
                self.add(
                    f"E_CONFIRMATORY_SEED_{seed}",
                    "confirmatory",
                    "The frozen target-scale method supports or refutes the declared claims under the preregistered confirmatory protocol.",
                    terminal_nodes,
                    "full_multi_seed",
                    {"mode": "confirmatory", "command_key": "confirmatory", "seed": seed},
                    claim_ids=claim_ids,
                    promotion_gate=[
                        "selection_frozen",
                        "final_test_not_used_for_adaptation",
                        "required_outputs_complete",
                    ],
                )
            )

        audit = self.add(
            "E_INDEPENDENT_AUDIT",
            "independent_audit",
            "An independent evaluator can recompute central metrics and verify protocol, artifact, trial, seed, and exclusion provenance.",
            confirmatory_nodes,
            "clean_reproduction",
            {"mode": "independent_audit", "command_key": "independent_audit"},
            expected_outputs=["audit.json"],
            promotion_gate=["metric_recomputed", "artifact_hashes_match", "no_integrity_blocker"],
            claim_ids=claim_ids,
        )
        self.add(
            "E_CLAIM_SYNC",
            "claim_sync",
            "Every claim is supported, qualified, rejected, or marked inconclusive using audited result provenance.",
            [audit],
            "clean_reproduction",
            {"mode": "claim_sync", "command_key": "claim_sync"},
            expected_outputs=["claim_sync.json"],
            promotion_gate=["all_claims_disposed", "no_forecast_promoted_as_measurement"],
            claim_ids=claim_ids,
        )
        return self.nodes, self.warnings

    def _family_status(self, name: str) -> tuple[str, dict[str, Any]]:
        family = self.study.get(name, {})
        return str(family.get("status", "unresolved")), family

    def _build_model_scaling(self, pilot: str, claim_ids: list[str]) -> list[str]:
        status, family = self._family_status("model_scaling")
        if status == "not_applicable":
            return []
        protocols = family.get("protocols") or []
        rungs = family.get("rungs") or []
        if status != "required" or not protocols or not rungs:
            node = self.add(
                "E_MODEL_SCALE_UNRESOLVED",
                "model_scaling",
                "Model scaling must be configured or explicitly justified as not applicable.",
                [pilot],
                "small_subset",
                {"mode": "model_scaling", "command_key": "model_scaling"},
                status="BLOCKED",
                claim_ids=claim_ids,
            )
            self.warnings.append("Model scaling is unresolved or lacks protocols/rungs.")
            return [node]

        terminals = []
        for protocol in protocols:
            parent = pilot
            for index, rung in enumerate(rungs):
                rung_name = str(rung.get("id") or rung.get("name") or f"s{index}")
                parent = self.add(
                    f"E_MODEL_{safe_node_token(protocol)}_{safe_node_token(rung_name)}",
                    "model_scaling",
                    f"The method's behavior at model rung {rung_name} is measured under the {protocol} protocol.",
                    [parent],
                    "short_schedule" if index < len(rungs) - 1 else "full_single_seed",
                    {
                        "mode": "model_scaling",
                        "command_key": "model_scaling",
                        "scale_protocol": protocol,
                        "model_rung": rung,
                        "rung_index": index,
                    },
                    claim_ids=claim_ids,
                )
            terminals.append(parent)
        return terminals

    def _build_data_scaling(self, pilot: str, claim_ids: list[str]) -> list[str]:
        status, family = self._family_status("data_scaling")
        if status == "not_applicable":
            return []
        protocols = family.get("protocols") or []
        rungs = family.get("rungs") or []
        if status != "required" or not protocols or not rungs:
            node = self.add(
                "E_DATA_SCALE_UNRESOLVED",
                "data_scaling",
                "Data scaling must be configured or explicitly justified as not applicable.",
                [pilot],
                "small_subset",
                {"mode": "data_scaling", "command_key": "data_scaling"},
                status="BLOCKED",
                claim_ids=claim_ids,
            )
            self.warnings.append("Data scaling is unresolved or lacks protocols/rungs.")
            return [node]

        terminals = []
        for protocol in protocols:
            parent = pilot
            for index, rung in enumerate(rungs):
                rung_name = str(rung.get("id") or rung.get("name") or f"d{index}")
                parent = self.add(
                    f"E_DATA_{safe_node_token(protocol)}_{safe_node_token(rung_name)}",
                    "data_scaling",
                    f"The marginal value of data rung {rung_name} is measured under the {protocol} exposure protocol.",
                    [parent],
                    "short_schedule" if index < len(rungs) - 1 else "full_single_seed",
                    {
                        "mode": "data_scaling",
                        "command_key": "data_scaling",
                        "data_protocol": protocol,
                        "data_rung": rung,
                        "rung_index": index,
                    },
                    claim_ids=claim_ids,
                )
            terminals.append(parent)

        sources = [str(item.get("id") or item.get("name")) for item in family.get("sources", []) if item.get("id") or item.get("name")]
        if len(sources) > 1:
            full = self.add(
                "E_DATA_MIXTURE_FULL",
                "data_mixture",
                "The declared full data mixture provides a compatible reference for source-contribution studies.",
                [pilot],
                "small_subset",
                {"mode": "data_mixture", "command_key": "data_mixture", "sources": sources, "design": "full"},
                claim_ids=claim_ids,
            )
            mixture_nodes = [full]
            for source in sources:
                mixture_nodes.append(
                    self.add(
                        f"E_DATA_MIXTURE_MINUS_{safe_node_token(source)}",
                        "data_mixture",
                        f"Removing source {source} estimates its marginal contribution in the full mixture.",
                        [full],
                        "small_subset",
                        {
                            "mode": "data_mixture",
                            "command_key": "data_mixture",
                            "sources": [item for item in sources if item != source],
                            "excluded_source": source,
                            "design": "leave_one_source_out",
                        },
                        claim_ids=claim_ids,
                    )
                )
            terminals.extend(mixture_nodes[1:])

        for index, mixture in enumerate(family.get("mixtures", []) or []):
            terminals.append(
                self.add(
                    f"E_DATA_MIXTURE_{index:02d}",
                    "data_mixture",
                    "A preregistered source mixture is evaluated under frozen validation and exposure policy.",
                    [pilot],
                    "small_subset",
                    {"mode": "data_mixture", "command_key": "data_mixture", "mixture": mixture},
                    claim_ids=claim_ids,
                )
            )
        return terminals

    def _build_module_studies(self, pilot: str, claim_ids: list[str]) -> list[str]:
        disposition = self.study.get("module_study", {})
        if disposition.get("status") == "not_applicable":
            return []
        modules = [item for item in self.study.get("modules", []) if item.get("core", True)]
        if not modules:
            node = self.add(
                "E_MODULE_STUDY_UNRESOLVED",
                "module_study",
                "Core modules/strategies must be declared or the study must justify why component analysis is not applicable.",
                [pilot],
                "small_subset",
                {"mode": "module_study", "command_key": "module_study"},
                status="BLOCKED",
                claim_ids=claim_ids,
            )
            self.warnings.append("No core modules are declared; module study remains blocked.")
            return [node]
        module_ids = [str(item["id"]) for item in modules]
        nodes = []
        if len(module_ids) <= 4:
            for enabled_bits in itertools.product([False, True], repeat=len(module_ids)):
                enabled = [module_id for module_id, bit in zip(module_ids, enabled_bits) if bit]
                label = "NONE" if not enabled else "__".join(safe_node_token(item) for item in enabled)
                nodes.append(
                    self.add(
                        f"E_MODULE_{label}",
                        "module_study",
                        f"The controlled module configuration {enabled or ['base']} isolates main effects and interactions under fair nuisance tuning.",
                        [pilot],
                        "small_subset",
                        {
                            "mode": "module_study",
                            "command_key": "module_study",
                            "enabled_modules": enabled,
                            "all_modules": module_ids,
                            "design": "full_factorial",
                        },
                        claim_ids=claim_ids,
                    )
                )
        else:
            nodes.append(
                self.add(
                    "E_MODULE_BASE",
                    "module_study",
                    "The base configuration anchors a budget-limited module screening design.",
                    [pilot],
                    "small_subset",
                    {"mode": "module_study", "command_key": "module_study", "enabled_modules": [], "design": "screening_base"},
                    claim_ids=claim_ids,
                )
            )
            nodes.append(
                self.add(
                    "E_MODULE_FULL",
                    "module_study",
                    "The full configuration anchors a budget-limited module screening design.",
                    [pilot],
                    "small_subset",
                    {"mode": "module_study", "command_key": "module_study", "enabled_modules": module_ids, "design": "screening_full"},
                    claim_ids=claim_ids,
                )
            )
            for module_id in module_ids:
                nodes.append(
                    self.add(
                        f"E_MODULE_MINUS_{safe_node_token(module_id)}",
                        "module_study",
                        f"Removing {module_id} screens its conditional contribution in the full configuration.",
                        [pilot],
                        "small_subset",
                        {
                            "mode": "module_study",
                            "command_key": "module_study",
                            "enabled_modules": [item for item in module_ids if item != module_id],
                            "design": "leave_one_module_out_screening",
                        },
                        claim_ids=claim_ids,
                    )
                )
            for interaction in self.study.get("module_interactions", []) or []:
                if len(interaction) != 2 or any(item not in module_ids for item in interaction):
                    self.warnings.append(f"Ignored invalid module interaction: {interaction}")
                    continue
                nodes.append(
                    self.add(
                        f"E_MODULE_PAIR_{safe_node_token(interaction[0])}__{safe_node_token(interaction[1])}",
                        "module_study",
                        f"The targeted interaction between {interaction[0]} and {interaction[1]} is measured from the base configuration.",
                        [pilot],
                        "small_subset",
                        {
                            "mode": "module_study",
                            "command_key": "module_study",
                            "enabled_modules": list(interaction),
                            "design": "targeted_pair",
                        },
                        claim_ids=claim_ids,
                    )
                )
            self.warnings.append(
                "More than four core modules: generated screening plus declared targeted interactions; do not claim untested interactions."
            )
        return nodes

    def _build_parameter_studies(self, pilot: str, claim_ids: list[str]) -> list[str]:
        disposition = self.study.get("parameter_study", {})
        if disposition.get("status") == "not_applicable":
            return []
        parameters = self.study.get("hyperparameters", {})
        nuisance = parameters.get("nuisance", []) or []
        scientific = parameters.get("scientific", []) or []
        parent = pilot
        nodes = []
        if nuisance:
            parent = self.add(
                "E_HPO_NUISANCE",
                "parameter_search",
                "Comparable nuisance-parameter search finds stable training regions without using the final test.",
                [pilot],
                "short_schedule",
                {"mode": "parameter_search", "command_key": "parameter_search", "parameters": nuisance},
                claim_ids=claim_ids,
            )
            nodes.append(parent)
        for parameter in scientific:
            name = str(parameter.get("name") or "parameter")
            values = parameter.get("values", [])
            if not values:
                self.warnings.append(f"Scientific parameter {name} has no values and was omitted.")
                continue
            for index, value in enumerate(values):
                nodes.append(
                    self.add(
                        f"E_SENSITIVITY_{safe_node_token(name)}_{index:02d}",
                        "parameter_sensitivity",
                        f"The scientific response to {name}={value!r} is measured around the selected operating region.",
                        [parent],
                        "short_schedule",
                        {
                            "mode": "parameter_sensitivity",
                            "command_key": "parameter_sensitivity",
                            "parameter": name,
                            "value": value,
                            "scale": parameter.get("scale", "categorical"),
                        },
                        claim_ids=claim_ids,
                    )
                )
        if not nuisance and not scientific:
            nodes.append(
                self.add(
                    "E_PARAMETER_STUDY_UNRESOLVED",
                    "parameter_search",
                    "Nuisance and key scientific parameters must be declared or the study must justify why parameter analysis is not applicable.",
                    [pilot],
                    "short_schedule",
                    {"mode": "parameter_search", "command_key": "parameter_search"},
                    status="BLOCKED",
                    claim_ids=claim_ids,
                )
            )
            self.warnings.append("No hyperparameters are declared; parameter study remains blocked.")
        return nodes

    def _build_additional_families(self, pilot: str, claim_ids: list[str]) -> list[str]:
        allowed = {"robustness", "efficiency", "qualitative", "human_evaluation"}
        default_fidelity = {
            "robustness": "cross_setting",
            "efficiency": "full_single_seed",
            "qualitative": "cross_setting",
            "human_evaluation": "cross_setting",
        }
        default_outputs = {
            "robustness": ["metrics.json"],
            "efficiency": ["metrics.json"],
            "qualitative": ["qualitative_index.json"],
            "human_evaluation": ["human_evaluation.json"],
        }
        nodes = []
        for index, raw in enumerate(self.study.get("additional_families", []) or []):
            if isinstance(raw, str):
                item = {"family": raw}
            elif isinstance(raw, dict):
                item = dict(raw)
            else:
                self.warnings.append(f"Ignored malformed additional experiment family: {raw!r}")
                continue
            family = str(item.get("family") or "")
            if family not in allowed:
                self.warnings.append(f"Ignored unsupported additional experiment family: {family or raw!r}")
                continue
            if item.get("status") == "not_applicable":
                continue
            suffix = safe_node_token(str(item.get("id") or f"{index:02d}"))
            status = "BLOCKED" if item.get("status") == "blocked" else "PLANNED"
            config = {"mode": family, "command_key": family, **(item.get("config") or {})}
            nodes.append(
                self.add(
                    f"E_{safe_node_token(family)}_{suffix}",
                    family,
                    str(item.get("hypothesis") or f"The declared {family} evidence addresses its linked claim under a frozen protocol."),
                    [pilot],
                    str(item.get("fidelity") or default_fidelity[family]),
                    config,
                    status=status,
                    expected_outputs=list(item.get("expected_outputs") or default_outputs[family]),
                    claim_ids=list(item.get("claim_ids") or claim_ids),
                )
            )
        return nodes


def family_summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        grouped[node["family"]].append(node)
    return {
        family: {
            "count": len(items),
            "blocked": sum(item["status"] == "BLOCKED" for item in items),
            "ids": [item["id"] for item in items],
        }
        for family, items in grouped.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the current executable experiment DAG.")
    parser.add_argument("study_root")
    args = parser.parse_args()
    root = resolve_study_root(args.study_root)
    study = load_json(root / "study.json")

    planner = Planner(study)
    nodes, warnings = planner.build()
    protocol_path = root / "protocols" / "protocol.json"
    protocol_hash = sha256_file(protocol_path) if protocol_path.is_file() else None
    for node in nodes:
        node["protocol_hash"] = protocol_hash
    graph_path = root / "experiments" / "experiment_graph.json"
    with file_lock(graph_path):
        old_graph = load_json(graph_path)
        old_version = int(old_graph.get("graph_version", 0))
        if old_version > 0:
            write_json(root / "experiments" / "archive" / f"experiment_graph_v{old_version}.json", old_graph)
        graph_version = old_version + 1
        config_root = root / "experiments" / "configs" / f"graph_v{graph_version}"
        for node in nodes:
            config_path = config_root / f"{node['id']}.json"
            node["config_path"] = str(config_path.relative_to(root)).replace("\\", "/")
            write_json(config_path, {"schema_version": 1, "graph_version": graph_version, **node})
        graph = {
            "schema_version": 1,
            "graph_version": graph_version,
            "created_at": utc_now(),
            "study_id": study["study_id"],
            "nodes": nodes,
        }
        write_json(graph_path, graph)

    plan = {
        "schema_version": 1,
        "graph_version": graph_version,
        "status": "blocked" if any(node["status"] == "BLOCKED" for node in nodes) else "planned",
        "created_at": utc_now(),
        "families": family_summary(nodes),
        "node_statuses": dict(Counter(node["status"] for node in nodes)),
        "warnings": warnings,
    }
    write_json(root / "experiments" / "experiment_plan.json", plan)
    print(f"graph_version={graph_version} nodes={len(nodes)} warnings={len(warnings)}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
