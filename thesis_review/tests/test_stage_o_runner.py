from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "stage_o_runner.py"
SPEC = importlib.util.spec_from_file_location("stage_o_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest().upper()


def bootstrap_payload(degree: str = "doctorate") -> dict[str, object]:
    sequence = MODULE.actor_sequence(degree)
    base = Path("C:/synthetic")
    plans: dict[str, dict[str, object]] = {}
    for actor in sequence:
        plans[actor] = {
            "plan_path": str(base / "plans" / f"{actor}.json"),
            "plan_sha256": digest(f"plan:{actor}"),
            "prompt_path": str(base / "prompts" / f"{actor}.txt"),
            "prompt_sha256": digest(f"prompt:{actor}"),
            "scratch_dir": None
            if actor.startswith("SA-")
            else str(base / "scratch" / actor),
        }
    return {
        "run_root": str(base / "run"),
        "workspace": str(base),
        "round_root": str(base / "run" / "round"),
        "views_root": str(base / "run" / "views"),
        "orchestration_root": str(base / "run" / "orchestration"),
        "skill_root": str(base / "skill"),
        "control_root": str(base / "control"),
        "scratch_root": str(base / "scratch"),
        "retirement_root": str(base / "retired"),
        "python_executable": str(base / "python.exe"),
        "python_executable_sha256": digest("python"),
        "codex_executable": str(base / "codex.exe"),
        "codex_executable_sha256": digest("codex"),
        "toolchain_sha256": {
            name: digest(f"tool:{name}") for name in MODULE.PINNED_SCRIPT_NAMES
        },
        "process_sha256": digest("process"),
        "process_seal_sha256": digest("seal"),
        "degree_level": degree,
        "actor_sequence": sequence,
        "prompt_plans": plans,
    }


def apply_event(
    state: dict,
    kind: str,
    *,
    operation_id: str,
    actor: str | None,
    payload: dict,
) -> dict:
    event = {
        "schema": MODULE.EVENT_SCHEMA,
        "sequence": state["event_count"] + 1,
        "kind": kind,
        "operation_id": operation_id,
        "actor": actor,
        "expected_transition_token": state["transition_token"],
        "previous_event_sha256": state["transition_token"],
        "payload": payload,
    }
    event_hash = MODULE.sha256_bytes(MODULE.canonical_json_bytes(event))
    return MODULE.reduce_event(state, event, event_hash)


def transact(
    state: dict,
    base: str,
    *,
    actor: str | None,
    begin: dict,
    commit: dict,
) -> dict:
    operation_id = str(uuid.uuid4())
    state = apply_event(
        state,
        f"{base}_BEGIN",
        operation_id=operation_id,
        actor=actor,
        payload=begin,
    )
    return apply_event(
        state,
        f"{base}_COMMIT",
        operation_id=operation_id,
        actor=actor,
        payload=commit,
    )


def bootstrapped(degree: str = "doctorate") -> dict:
    state = MODULE.initial_state()
    return transact(
        state,
        "BOOTSTRAP",
        actor=None,
        begin=bootstrap_payload(degree),
        commit={
            "process_seal_verification": {"status": "verified"},
            "staged_rule_files": {"SKILL.md": digest("skill")},
        },
    )


def allocations(state: dict) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for actor in MODULE._current_phase_actors(state):
        launch_id = str(uuid.uuid4())
        root = Path("C:/synthetic/control") / actor / launch_id
        result[actor] = {
            "outputs_absent": True,
            "launch_id": launch_id,
            "jsonl_path": str(root / "actor.jsonl"),
            "stderr_path": str(root / "actor.stderr"),
            "launch_record_path": str(root / "launch-record.json"),
            "scratch_dir": str(Path("C:/synthetic/scratch") / f"{actor}-{launch_id}"),
        }
    return result


def prepared_payload(state: dict, allocated: dict[str, dict[str, object]]) -> dict:
    actors: dict[str, dict[str, object]] = {}
    for actor in MODULE._current_phase_actors(state):
        item = allocated[actor]
        actors[actor] = {
            "view_root": str(Path("C:/synthetic/run/views") / actor),
            "opened": ["00-process-parameters.json"],
            "outputs": [f"{actor}-output.md"],
            "input_commitment_sha256": digest(f"input:{actor}"),
            "prompt_plan_sha256": digest(f"plan:{actor}"),
            "prompt_path": str(Path("C:/synthetic/prompts") / f"{actor}.txt"),
            "prompt_sha256": digest(f"prompt:{actor}"),
            "prompt_verification_sha256": digest(f"verify:{actor}"),
            "launch_id": item["launch_id"],
            "jsonl_path": item["jsonl_path"],
            "stderr_path": item["stderr_path"],
            "launch_record_path": item["launch_record_path"],
            "scratch_dir": item["scratch_dir"],
        }
    return {"actors": actors}


def launch_payload(state: dict, *, replay: bool = False) -> dict:
    receipts: dict[str, dict[str, object]] = {}
    shared = digest("replayed-record")
    for actor in MODULE._current_phase_actors(state):
        prepared = state["actors"][actor]["prepare"]
        receipts[actor] = {
            "schema": MODULE.LAUNCH_SCHEMA,
            "launch_id": prepared["launch_id"],
            "launch_record_path": prepared["launch_record_path"],
            "launch_record_sha256": shared if replay else digest(f"record:{actor}"),
            "output_commitment_sha256": digest(f"output:{actor}"),
            "jsonl_sha256": digest(f"jsonl:{actor}"),
            "result_sha256": digest(f"result:{actor}"),
        }
    return {"receipts": receipts}


def promotion_payload(state: dict) -> dict:
    promotions: dict[str, dict[str, object]] = {}
    for actor in MODULE._current_phase_actors(state):
        launch = state["actors"][actor]["launch"]
        promotions[actor] = {
            "launch_record_sha256": launch["launch_record_sha256"],
            "output_commitment_sha256": launch["output_commitment_sha256"],
            "promoted_outputs": {
                str(Path("C:/synthetic/run/round") / f"{actor}.md"): digest(
                    f"promoted:{actor}"
                )
            },
        }
    return {"promotions": promotions}


def complete_current_phase(state: dict) -> dict:
    allocated = allocations(state)
    state = transact(
        state,
        "PREPARE_PHASE",
        actor=None,
        begin={"allocations": allocated},
        commit=prepared_payload(state, allocated),
    )
    state = transact(
        state,
        "LAUNCH_PHASE",
        actor=None,
        begin={},
        commit=launch_payload(state),
    )
    return transact(
        state,
        "PROMOTE_PHASE",
        actor=None,
        begin={},
        commit=promotion_payload(state),
    )


class StageORunnerReducerTests(unittest.TestCase):
    def test_complete_doctorate_phase_barrier_happy_path(self) -> None:
        state = bootstrapped("doctorate")
        self.assertEqual(MODULE._current_phase_actors(state), ["P"])
        state = complete_current_phase(state)
        self.assertEqual(
            MODULE._current_phase_actors(state),
            ["R1", "R2", "R3", "R4", "R5", "AI"],
        )
        state = complete_current_phase(state)
        self.assertEqual(
            MODULE._current_phase_actors(state),
            ["SA-R1", "SA-R2", "SA-R3", "SA-R4", "SA-R5", "SA-AI"],
        )
        state = complete_current_phase(state)
        # The SA barrier does not advance merely because all private pairs were
        # promoted; the aggregate gate is a separate transaction.
        self.assertTrue(MODULE._phase_all(state, "PROMOTED"))
        state = transact(
            state,
            "CLOSE_SA_SET",
            actor=None,
            begin={},
            commit={
                "gate_path": "C:/synthetic/run/round/06-semantic-acceptance-gate.json",
                "gate_sha256": digest("sa-gate"),
            },
        )
        self.assertEqual(MODULE._current_phase_actors(state), ["C"])
        state = complete_current_phase(state)
        self.assertEqual(MODULE._current_phase_actors(state), ["S"])
        state = complete_current_phase(state)
        self.assertEqual(MODULE._current_phase_actors(state), [])
        state = transact(
            state,
            "RETIRE_RULES",
            actor=None,
            begin={},
            commit={
                "destination": "C:/synthetic/retired",
                "manifest_sha256": digest("retired"),
            },
        )
        state = transact(
            state,
            "FINALIZE",
            actor=None,
            begin={},
            commit={
                "validation_report_path": "C:/synthetic/run/round/95-bundle-validation.md",
                "validation_report_sha256": digest("95"),
                "validator_stdout_sha256": digest("validator-stdout"),
                "round_tree_sha256": digest("round-tree"),
            },
        )
        state = transact(
            state,
            "AUTHORIZE_DELIVERY",
            actor=None,
            begin={},
            commit={
                "summary_path": "C:/synthetic/run/round/93-user-facing-summary.md",
                "summary_sha256": digest("93"),
                "validation_report_sha256": digest("95"),
                "frozen_pdf_sha256": digest("pdf"),
                "round_tree_sha256": digest("round-tree"),
            },
        )
        self.assertTrue(state["delivery_authorized"])
        self.assertEqual(len(state["consumed_receipts"]), 15)
        self.assertEqual(state["event_count"], 40)

    def test_masters_plan_reduces_reviewer_and_sa_sets(self) -> None:
        state = bootstrapped("masters")
        state = complete_current_phase(state)
        self.assertEqual(MODULE._current_phase_actors(state), ["R1", "R2", "R3", "AI"])
        state = complete_current_phase(state)
        self.assertEqual(
            MODULE._current_phase_actors(state),
            ["SA-R1", "SA-R2", "SA-R3", "SA-AI"],
        )
        self.assertNotIn("R4", state["actors"])
        self.assertNotIn("SA-R5", state["actors"])

    def test_out_of_order_and_multi_actor_singleton_transitions_are_rejected(self) -> None:
        state = bootstrapped()
        allocation = allocations(state)["P"]
        operation_id = str(uuid.uuid4())
        with self.assertRaisesRegex(MODULE.RunnerError, "current phase"):
            apply_event(
                state,
                "PREPARE_ACTOR_BEGIN",
                operation_id=operation_id,
                actor="R1",
                payload=allocation,
            )
        state = complete_current_phase(state)
        # R/AI actors must be prepared under one phase transaction; a caller
        # cannot serialize the nominally concurrent phase actor by actor.
        allocation = allocations(state)["R5"]
        with self.assertRaisesRegex(MODULE.RunnerError, "singleton phase"):
            apply_event(
                state,
                "PREPARE_ACTOR_BEGIN",
                operation_id=str(uuid.uuid4()),
                actor="R5",
                payload=allocation,
            )

        prepared_allocations = allocations(state)
        state = transact(
            state,
            "PREPARE_PHASE",
            actor=None,
            begin={"allocations": prepared_allocations},
            commit=prepared_payload(state, prepared_allocations),
        )
        with self.assertRaisesRegex(MODULE.RunnerError, "singleton phase"):
            apply_event(
                state,
                "LAUNCH_ACTOR_BEGIN",
                operation_id=str(uuid.uuid4()),
                actor="R1",
                payload={},
            )

        state = transact(
            state,
            "LAUNCH_PHASE",
            actor=None,
            begin={},
            commit=launch_payload(state),
        )
        with self.assertRaisesRegex(MODULE.RunnerError, "singleton phase"):
            apply_event(
                state,
                "PROMOTE_ACTOR_BEGIN",
                operation_id=str(uuid.uuid4()),
                actor="R1",
                payload={},
            )

    def test_dangling_begin_permits_only_quarantine(self) -> None:
        state = bootstrapped()
        allocation = allocations(state)
        operation_id = str(uuid.uuid4())
        state = apply_event(
            state,
            "PREPARE_PHASE_BEGIN",
            operation_id=operation_id,
            actor=None,
            payload={"allocations": allocation},
        )
        with self.assertRaisesRegex(MODULE.RunnerError, "dangling BEGIN"):
            apply_event(
                state,
                "LAUNCH_PHASE_BEGIN",
                operation_id=str(uuid.uuid4()),
                actor=None,
                payload={},
            )
        state = apply_event(
            state,
            "QUARANTINE_BEGIN",
            operation_id=str(uuid.uuid4()),
            actor=None,
            payload={
                "reason": "crash recovery",
                "destination": "C:/synthetic/QUARANTINED-run",
                "abandoned_operation_id": operation_id,
            },
        )
        self.assertEqual(state["pending"]["base"], "QUARANTINE")

    def test_receipt_replay_inside_parallel_phase_is_rejected(self) -> None:
        state = complete_current_phase(bootstrapped())
        allocated = allocations(state)
        state = transact(
            state,
            "PREPARE_PHASE",
            actor=None,
            begin={"allocations": allocated},
            commit=prepared_payload(state, allocated),
        )
        operation_id = str(uuid.uuid4())
        state = apply_event(
            state,
            "LAUNCH_PHASE_BEGIN",
            operation_id=operation_id,
            actor=None,
            payload={},
        )
        with self.assertRaisesRegex(MODULE.RunnerError, "replayed"):
            apply_event(
                state,
                "LAUNCH_PHASE_COMMIT",
                operation_id=operation_id,
                actor=None,
                payload=launch_payload(state, replay=True),
            )

    def test_early_output_observation_rejects_prepare_begin(self) -> None:
        state = bootstrapped()
        allocated = allocations(state)
        allocated["P"]["outputs_absent"] = False
        with self.assertRaisesRegex(MODULE.RunnerError, "outputs must be absent"):
            apply_event(
                state,
                "PREPARE_PHASE_BEGIN",
                operation_id=str(uuid.uuid4()),
                actor=None,
                payload={"allocations": allocated},
            )

    def test_h_and_v_are_not_in_any_production_plan(self) -> None:
        for degree in ("doctorate", "masters"):
            sequence = MODULE.actor_sequence(degree)
            self.assertNotIn("H", "".join(sequence))
            self.assertNotIn("V", sequence)
        payload = bootstrap_payload()
        payload["actor_sequence"].append("V")  # type: ignore[union-attr]
        with self.assertRaisesRegex(MODULE.RunnerError, "canonical degree sequence"):
            apply_event(
                MODULE.initial_state(),
                "BOOTSTRAP_BEGIN",
                operation_id=str(uuid.uuid4()),
                actor=None,
                payload=payload,
            )


class StageORunnerLedgerTests(unittest.TestCase):
    def test_append_is_canonical_and_cas_rejects_stale_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_root = Path(directory) / "events"
            event_root.mkdir()
            with mock.patch.object(MODULE, "_fsync_directory"):
                state, _event, _head = MODULE.append_event(
                    event_root,
                    expected_transition_token=MODULE.ZERO_HASH,
                    kind="BOOTSTRAP_BEGIN",
                    operation_id=str(uuid.uuid4()),
                    actor=None,
                    payload=bootstrap_payload(),
                )
                self.assertEqual(state["event_count"], 1)
                raw = (event_root / "E00000001.json").read_bytes()
                parsed = json.loads(raw)
                self.assertEqual(raw, MODULE.canonical_json_bytes(parsed))
                with self.assertRaisesRegex(MODULE.RunnerError, "stale"):
                    MODULE.append_event(
                        event_root,
                        expected_transition_token=MODULE.ZERO_HASH,
                        kind="QUARANTINE_BEGIN",
                        operation_id=str(uuid.uuid4()),
                        actor=None,
                        payload={
                            "reason": "stale",
                            "destination": "C:/synthetic/QUARANTINED-run",
                            "abandoned_operation_id": parsed["operation_id"],
                        },
                    )

    def test_hash_chain_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_root = Path(directory) / "events"
            event_root.mkdir()
            with mock.patch.object(MODULE, "_fsync_directory"):
                state, first, head = MODULE.append_event(
                    event_root,
                    expected_transition_token=MODULE.ZERO_HASH,
                    kind="BOOTSTRAP_BEGIN",
                    operation_id=str(uuid.uuid4()),
                    actor=None,
                    payload=bootstrap_payload(),
                )
                MODULE.append_event(
                    event_root,
                    expected_transition_token=head,
                    kind="BOOTSTRAP_COMMIT",
                    operation_id=first["operation_id"],
                    actor=None,
                    payload={
                        "process_seal_verification": {"status": "verified"},
                        "staged_rule_files": {"SKILL.md": digest("skill")},
                    },
                )
            second = event_root / "E00000002.json"
            event = json.loads(second.read_text(encoding="utf-8"))
            event["previous_event_sha256"] = digest("tampered")
            second.write_bytes(MODULE.canonical_json_bytes(event))
            with self.assertRaisesRegex(MODULE.RunnerError, "does not match the head"):
                MODULE.load_event_chain(event_root)

    def test_unknown_or_gapped_event_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_root = Path(directory) / "events"
            event_root.mkdir()
            (event_root / "notes.txt").write_text("not an event", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.RunnerError, "closed contiguous"):
                MODULE.load_event_chain(event_root)


class StageORunnerCommandTests(unittest.TestCase):
    def test_only_reviewer_actors_receive_search_capability(self) -> None:
        for actor in MODULE.actor_sequence("doctorate"):
            self.assertEqual(
                MODULE.actor_search_enabled(actor),
                actor in {"R1", "R2", "R3", "R4", "R5"},
                actor,
            )

    def test_bootstrap_binds_the_actual_runner_and_rejects_foreign_roots(self) -> None:
        self.assertEqual(
            MODULE._canonical_bound_skill_root(MODULE.SKILL_ROOT),
            MODULE.SKILL_ROOT,
        )
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory) / "foreign-skill"
            foreign.mkdir()
            with self.assertRaisesRegex(
                MODULE.RunnerError, "must be the canonical skill root"
            ):
                MODULE._canonical_bound_skill_root(foreign)

            alternate_runner = Path(directory) / "stage_o_runner.py"
            alternate_runner.write_text("# alternate runner\n", encoding="utf-8")
            with mock.patch.object(
                MODULE, "__file__", str(alternate_runner)
            ), self.assertRaisesRegex(
                MODULE.RunnerError, "not the script under the bound skill root"
            ):
                MODULE._canonical_bound_skill_root(MODULE.SKILL_ROOT)

    def test_bootstrap_configuration_failure_precedes_event_store_creation(self) -> None:
        args = argparse.Namespace()
        with mock.patch.object(
            MODULE,
            "_canonical_bootstrap_config",
            side_effect=MODULE.RunnerError("invalid bound runner"),
        ), mock.patch.object(MODULE, "_create_event_store") as create_store:
            with self.assertRaisesRegex(MODULE.RunnerError, "invalid bound runner"):
                MODULE.command_bootstrap(args)
        create_store.assert_not_called()

    def test_transitive_runtime_dependencies_are_pinned_and_verified(self) -> None:
        required = {
            "actor_prompt_contract.py",
            "validate_semantic_acceptance_output.py",
        }
        self.assertTrue(required.issubset(set(MODULE.PINNED_SCRIPT_NAMES)))
        state = bootstrapped()
        config = state["config"]

        def current_hash(path: Path) -> str:
            if path == Path(config["python_executable"]):
                return config["python_executable_sha256"]
            if path == Path(config["codex_executable"]):
                return config["codex_executable_sha256"]
            return config["toolchain_sha256"][path.name]

        with mock.patch.object(MODULE, "sha256_file", side_effect=current_hash):
            MODULE._verify_toolchain(state)

        for changed in sorted(required):
            def drifted_hash(path: Path, changed: str = changed) -> str:
                if path.name == changed:
                    return digest(f"drift:{changed}")
                return current_hash(path)

            with self.subTest(changed=changed), mock.patch.object(
                MODULE, "sha256_file", side_effect=drifted_hash
            ), self.assertRaisesRegex(MODULE.RunnerError, "toolchain changed"):
                MODULE._verify_toolchain(state)

    def test_promoted_output_anchors_check_closed_paths_safety_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            round_root = Path(directory)
            output = round_root / "P.md"
            output.write_bytes(b"frozen output")
            expected_hash = MODULE.sha256_file(output)
            state = bootstrapped()
            state["config"]["round_root"] = str(round_root)
            state["actors"]["P"]["phase"] = "PROMOTED"
            state["actors"]["P"]["promotion"] = {
                "launch_record_sha256": digest("record:P"),
                "output_commitment_sha256": digest("output:P"),
                "promoted_outputs": {str(output): expected_hash},
            }

            with mock.patch.object(
                MODULE, "_process_from_state", return_value={}
            ), mock.patch.object(
                MODULE, "_load_module", return_value=object()
            ), mock.patch.object(
                MODULE, "_round_output_paths", return_value=[output]
            ):
                verified = MODULE._verify_promoted_output_anchors(state)
                self.assertEqual(verified["P"][str(output)], expected_hash)

                stored = state["actors"]["P"]["promotion"]["promoted_outputs"]
                state["actors"]["P"]["promotion"]["promoted_outputs"] = {
                    str(round_root / "wrong.md"): expected_hash
                }
                with self.assertRaisesRegex(MODULE.RunnerError, "path set drift"):
                    MODULE._verify_promoted_output_anchors(state)
                state["actors"]["P"]["promotion"]["promoted_outputs"] = stored

                output.write_bytes(b"changed output")
                with self.assertRaisesRegex(MODULE.RunnerError, "SHA-256 drift"):
                    MODULE._verify_promoted_output_anchors(state)

                output.unlink()
                output.mkdir()
                with self.assertRaisesRegex(MODULE.RunnerError, "single-link regular"):
                    MODULE._verify_promoted_output_anchors(state)

    def test_required_transactions_recheck_anchors_after_begin(self) -> None:
        required = {
            "PREPARE_ACTOR",
            "PREPARE_PHASE",
            "CLOSE_SA_SET",
            "RETIRE_RULES",
            "FINALIZE",
        }
        self.assertTrue(required.issubset(MODULE.PROMOTED_OUTPUT_ANCHOR_BASES))
        for base in sorted(required):
            with self.subTest(base=base):
                state = bootstrapped()
                begun = dict(state)
                begun["transition_token"] = digest(f"{base}:begin")
                committed = dict(begun)
                committed["transition_token"] = digest(f"{base}:commit")
                order: list[str] = []

                def fake_append(_event_root: Path, **kwargs):
                    order.append(kwargs["kind"])
                    if kwargs["kind"].endswith("_BEGIN"):
                        return begun, {}, begun["transition_token"]
                    return committed, {}, committed["transition_token"]

                def check_anchors(_state: dict) -> dict:
                    order.append("ANCHORS")
                    return {}

                def effect() -> dict:
                    order.append("EFFECT")
                    return {}

                with mock.patch.object(
                    MODULE, "append_event", side_effect=fake_append
                ), mock.patch.object(
                    MODULE,
                    "_verify_promoted_output_anchors",
                    side_effect=check_anchors,
                ):
                    result = MODULE._transaction(
                        Path("C:/events"),
                        state,
                        base=base,
                        actor="P" if base == "PREPARE_ACTOR" else None,
                        expected_token=state["transition_token"],
                        begin_payload={},
                        effect=effect,
                    )
                self.assertIs(result, committed)
                self.assertEqual(
                    order,
                    [f"{base}_BEGIN", "ANCHORS", "EFFECT", f"{base}_COMMIT"],
                )

    def test_promoted_anchor_failure_after_begin_quarantines_without_effect(self) -> None:
        state = bootstrapped()
        begun = dict(state)
        begun["pending"] = {
            "base": "PREPARE_PHASE",
            "operation_id": str(uuid.uuid4()),
            "actor": None,
            "begin_payload": {},
        }
        begun["transition_token"] = digest("anchor-begin")
        final = dict(begun)
        final["quarantined"] = True
        final["transition_token"] = digest("anchor-quarantine")
        effect = mock.Mock(return_value={})
        with mock.patch.object(
            MODULE,
            "append_event",
            return_value=(begun, {}, begun["transition_token"]),
        ) as append, mock.patch.object(
            MODULE,
            "_verify_promoted_output_anchors",
            side_effect=MODULE.RunnerError("promoted output SHA-256 drift"),
        ) as anchors, mock.patch.object(
            MODULE, "load_event_chain", return_value=(begun, [])
        ), mock.patch.object(
            MODULE,
            "_perform_quarantine",
            return_value=(final, Path("C:/synthetic/QUARANTINED-run")),
        ) as quarantine:
            with self.assertRaisesRegex(MODULE.RunnerError, "was quarantined"):
                MODULE._transaction(
                    Path("C:/events"),
                    state,
                    base="PREPARE_PHASE",
                    actor=None,
                    expected_token=state["transition_token"],
                    begin_payload={},
                    effect=effect,
                )
        append.assert_called_once()
        anchors.assert_called_once_with(state)
        effect.assert_not_called()
        quarantine.assert_called_once()

    def test_promote_phase_cli_has_no_caller_supplied_hash_baseline(self) -> None:
        args = MODULE.parse_args(
            [
                "promote-phase",
                "--run-root",
                "C:/synthetic/run",
                "--expected-transition-token",
                digest("head"),
            ]
        )
        self.assertFalse(hasattr(args, "expected_input_commitment_sha256"))
        self.assertFalse(hasattr(args, "expected_launch_record_sha256"))
        self.assertFalse(hasattr(args, "expected_output_commitment_sha256"))

    def test_production_cli_does_not_expose_single_actor_transitions(self) -> None:
        for command in ("prepare-actor", "launch-actor", "promote-actor"):
            with self.subTest(command=command), mock.patch(
                "sys.stderr"
            ), self.assertRaises(SystemExit):
                MODULE.parse_args(
                    [
                        command,
                        "--run-root",
                        "C:/synthetic/run",
                        "--expected-transition-token",
                        digest("head"),
                        "--actor",
                        "R1",
                    ]
                )

    def test_launch_phase_runs_peer_actors_concurrently_under_one_transaction(self) -> None:
        state = complete_current_phase(bootstrapped())
        allocated = allocations(state)
        state = transact(
            state,
            "PREPARE_PHASE",
            actor=None,
            begin={"allocations": allocated},
            commit=prepared_payload(state, allocated),
        )
        actors = MODULE._current_phase_actors(state)
        barrier = threading.Barrier(len(actors))
        seen: list[str] = []
        lock = threading.Lock()

        def fake_launch(_state: dict, actor: str) -> dict:
            with lock:
                seen.append(actor)
            barrier.wait(timeout=5)
            prepared = _state["actors"][actor]["prepare"]
            return {
                "schema": MODULE.LAUNCH_SCHEMA,
                "launch_id": prepared["launch_id"],
                "launch_record_path": prepared["launch_record_path"],
                "launch_record_sha256": digest(f"record:{actor}"),
                "output_commitment_sha256": digest(f"output:{actor}"),
                "jsonl_sha256": digest(f"jsonl:{actor}"),
                "result_sha256": digest(f"result:{actor}"),
            }

        def fake_transaction(_event_root, _state, **kwargs):
            return kwargs["effect"]()

        args = argparse.Namespace(
            run_root=Path("C:/synthetic/run"),
            expected_transition_token=state["transition_token"],
        )
        with mock.patch.object(
            MODULE, "_state_for_command", return_value=(Path("C:/events"), state)
        ), mock.patch.object(MODULE, "_execute_launch_actor", side_effect=fake_launch), mock.patch.object(
            MODULE, "_transaction", side_effect=fake_transaction
        ):
            result = MODULE.command_launch_phase(args)
        self.assertEqual(set(seen), set(actors))
        self.assertEqual(set(result["receipts"]), set(actors))

    def test_single_actor_prepare_uses_the_same_preparation_implementation_as_phase(self) -> None:
        state = bootstrapped()
        allocation = allocations(state)["P"]
        prepared = prepared_payload(state, {"P": allocation})["actors"]["P"]
        args = argparse.Namespace(
            run_root=Path("C:/synthetic/run"),
            expected_transition_token=state["transition_token"],
            actor="P",
        )

        def fake_transaction(_event_root, _state, **kwargs):
            self.assertEqual(kwargs["begin_payload"], allocation)
            return kwargs["effect"]()

        with mock.patch.object(
            MODULE, "_state_for_command", return_value=(Path("C:/events"), state)
        ), mock.patch.object(
            MODULE, "_process_from_state", return_value={"round_id": "r", "retry_id": "x"}
        ), mock.patch.object(
            MODULE, "_preallocate_actor", return_value=allocation
        ), mock.patch.object(
            MODULE, "_execute_prepare_actor", return_value=prepared
        ) as execute, mock.patch.object(
            MODULE, "_transaction", side_effect=fake_transaction
        ):
            result = MODULE.command_prepare_actor(args)

        self.assertEqual(result, prepared)
        execute.assert_called_once_with(state, "P", allocation)

    def test_begun_effect_failure_invokes_quarantine(self) -> None:
        state = bootstrapped()
        begun = dict(state)
        begun["pending"] = {
            "base": "PREPARE_PHASE",
            "operation_id": str(uuid.uuid4()),
            "actor": None,
            "begin_payload": {},
        }
        begun["transition_token"] = digest("begin")
        final = dict(begun)
        final["quarantined"] = True
        final["transition_token"] = digest("quarantine")
        with mock.patch.object(
            MODULE,
            "append_event",
            return_value=(begun, {}, begun["transition_token"]),
        ), mock.patch.object(
            MODULE, "load_event_chain", return_value=(begun, [])
        ), mock.patch.object(
            MODULE,
            "_perform_quarantine",
            return_value=(final, Path("C:/synthetic/QUARANTINED-run")),
        ) as quarantine:
            with self.assertRaisesRegex(MODULE.RunnerError, "was quarantined"):
                MODULE._transaction(
                    Path("C:/events"),
                    state,
                    base="PREPARE_PHASE",
                    actor=None,
                    expected_token=state["transition_token"],
                    begin_payload={},
                    effect=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                )
        quarantine.assert_called_once()

    def test_bootstrap_preflight_receives_run_root_not_round_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary) / "run"
            round_root = run_root / "round"
            views_root = run_root / "views"
            round_root.mkdir(parents=True)
            views_root.mkdir()
            config = {
                "run_root": str(run_root),
                "round_root": str(round_root),
                "views_root": str(views_root),
                "skill_root": str(Path(temporary) / "skill"),
                "workspace": str(Path(temporary)),
                "process_sha256": digest("process"),
                "process_seal_sha256": digest("seal"),
            }
            process = {"frozen_pdf_file": "thesis.pdf"}
            begun = {"transition_token": digest("begin")}
            committed = {"transition_token": digest("commit")}
            preflight = mock.Mock()
            preflight.verify_process_seal.return_value = {"status": "verified"}
            manager = mock.Mock()
            manager.command_stage_round.return_value = {"files": {}}

            def load_module(filename: str, _module_name: str):
                return manager if filename == "manage_stage_o_workspace.py" else preflight

            with mock.patch.object(
                MODULE,
                "_canonical_bootstrap_config",
                return_value=(config, process),
            ), mock.patch.object(
                MODULE, "_create_event_store", return_value=Path(temporary) / "events"
            ), mock.patch.object(
                MODULE,
                "append_event",
                side_effect=[
                    (begun, {}, begun["transition_token"]),
                    (committed, {}, committed["transition_token"]),
                ],
            ), mock.patch.object(MODULE, "_load_module", side_effect=load_module):
                result = MODULE.command_bootstrap(argparse.Namespace())

            self.assertEqual(result, committed)
            preflight._validate_pre_stage_p_state.assert_called_once_with(
                run_root, process
            )


if __name__ == "__main__":
    unittest.main()
