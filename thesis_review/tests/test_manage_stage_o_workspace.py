from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "manage_stage_o_workspace.py"
SPEC = importlib.util.spec_from_file_location("manage_stage_o_workspace", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_run(base: Path) -> tuple[Path, Path]:
    run = base / "run-v1"
    round_root = run / "round"
    round_root.mkdir(parents=True)
    (run / "views").mkdir()
    (run / "orchestration").mkdir()
    return run, round_root


def stable_process(page_count: int = 1) -> dict[str, object]:
    return {
        "round_id": "round-v1",
        "retry_id": "retry-v1",
        "frozen_pdf_file": "thesis.pdf",
        "selected_pdf_sha256": "A" * 64,
        "physical_page_count": page_count,
        "degree_level": "doctorate",
        "governing_local_files": [],
        "output_language": "zh-CN",
    }


def full_process(page_count: int = 1) -> dict[str, object]:
    value = stable_process(page_count)
    value.update(
        {
            "frozen_at": "2026-01-01T00:00:00+00:00",
            "degree_type": "academic",
            "institution": None,
            "school_or_department": None,
            "discipline": None,
            "expected_submission_year": None,
            "artifact_type": "unknown",
            "review_mode": "fresh-rereview",
            "governing_rule_urls": [],
            "decision_regime_status": "skill-default",
            "actor_prompt_sha256": {
                **{f"R{index}": f"{index}" * 64 for index in range(1, 6)},
                "P": "A" * 64,
                "AI": "B" * 64,
                **{f"SA-R{index}": f"{index + 5:X}" * 64 for index in range(1, 6)},
                "SA-AI": "C" * 64,
                "C": "D" * 64,
                "S": "E" * 64,
            },
        }
    )
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def promotion_args(
    *, actor: str, view: Path, round_root: Path, commitment: str
) -> argparse.Namespace:
    return argparse.Namespace(
        actor=actor,
        view_root=view,
        round_root=round_root,
        expected_input_commitment_sha256=commitment,
        launch_record=round_root.parent / "orchestration" / f"{actor}-launch.json",
        expected_launch_id="12345678-1234-4234-8234-123456789abc",
        expected_process_seal_sha256="F" * 64,
        expected_launch_record_sha256="E" * 64,
        expected_output_commitment_sha256="D" * 64,
    )


def accepted_launch_receipt() -> dict[str, str]:
    return {
        "launch_id": "12345678-1234-4234-8234-123456789abc",
        "launch_record": "fixture-launch-record.json",
    }


class ManageStageOWorkspaceTests(unittest.TestCase):
    def test_init_r_scratch_uses_canonical_internal_token_and_refuses_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _run, round_root = make_run(base)
            control = base / "control"
            control.mkdir()
            scratch_parent = base / "scratch"
            scratch_parent.mkdir()
            process_path = control / "preplan.json"
            write_json(process_path, stable_process())
            args = argparse.Namespace(
                process=process_path,
                round_root=round_root,
                actor="R4",
                scratch_parent=scratch_parent,
            )
            result = MODULE.command_init_scratch(args)
            scratch = Path(result["scratch_dir"])
            self.assertTrue(scratch.is_dir())
            self.assertRegex(scratch.name, r"^stage-r-r4-[0-9a-f]{24}$")
            with self.assertRaisesRegex(MODULE.ContractError, "reuse reviewer scratch"):
                MODULE.command_init_scratch(args)

    def test_stage_and_recoverably_retire_exact_round_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _run, round_root = make_run(base)
            result = MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            self.assertEqual(
                len(result["files"]),
                1 + len(MODULE.REFERENCE_NAMES) + len(MODULE.ROUND_SCRIPT_NAMES),
            )
            self.assertTrue((round_root / "SKILL.md").is_file())
            self.assertTrue(
                (round_root / "rules" / "scripts" / "validate_stage_p_output.py").is_file()
            )
            with self.assertRaisesRegex(MODULE.ContractError, "existing round rules"):
                MODULE.command_stage_round(
                    argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
                )

            retirement = base / "retired"
            retired = MODULE.command_retire_round(
                argparse.Namespace(
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    destination=retirement,
                )
            )
            self.assertEqual(retired["file_count"], len(result["files"]))
            self.assertFalse((round_root / "SKILL.md").exists())
            self.assertFalse((round_root / "rules").exists())
            self.assertTrue((retirement / "SKILL.md").is_file())
            self.assertTrue((retirement / "retirement-manifest.json").is_file())

    def test_stage_sa_view_uses_exact_target_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = stable_process()
            write_json(round_root / "00-process-parameters.json", process)
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            semantic = MODULE.load_module(
                SKILL_ROOT / "scripts" / "build_semantic_acceptance_prompt.py",
                "semantic_for_test",
            )
            opened = semantic.algorithmic_opened_inputs(
                semantic.stable_process_projection(process), "R1"
            )
            for item in opened:
                path = round_root / item
                if path.exists():
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"fixture:{item}".encode("utf-8"))
            view = run / "views" / "SA-R1"
            result = MODULE.command_stage_sa(
                argparse.Namespace(round_root=round_root, view_root=view, target="R1")
            )
            self.assertEqual(result["opened"], opened)
            actual = sorted(
                path.relative_to(view).as_posix()
                for path in view.rglob("*")
                if path.is_file()
            )
            self.assertEqual(actual, sorted(opened))
            self.assertNotIn("R2-comprehensive-review.md", actual)

    def test_process_json_duplicate_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process.json"
            path.write_text('{"degree_level":"doctorate","degree_level":"masters"}')
            with self.assertRaisesRegex(MODULE.ContractError, "duplicate JSON key"):
                MODULE.read_json_object(path, "process fixture")

    def test_stage_p_actor_view_is_exact_and_promotes_only_packet_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            (round_root / "thesis.pdf").write_bytes(b"fixture pdf bytes")
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            view = run / "views" / "P"
            staged = MODULE.command_stage_actor(
                argparse.Namespace(
                    actor="P",
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                )
            )
            actual = sorted(
                path.relative_to(view).as_posix()
                for path in view.rglob("*")
                if path.is_file()
            )
            self.assertEqual(actual, sorted(staged["opened"]))
            self.assertFalse(any(name.startswith("R1-") for name in actual))
            for name in staged["outputs"]:
                (view / name).write_bytes(f"packet:{name}".encode("utf-8"))
            args = promotion_args(
                actor="P",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(
                MODULE, "run_general_scoped_gate", return_value=["gate"]
            ), mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                promoted = MODULE.command_promote_actor(args)
            self.assertEqual(promoted["status"], "promoted")
            for name in MODULE.P_OUTPUTS:
                self.assertEqual((round_root / name).read_bytes(), (view / name).read_bytes())

    def test_r5_actor_view_promotes_exact_owner_tree_and_rejects_extra(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process(page_count=1)
            write_json(round_root / "00-process-parameters.json", process)
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            opened, _instructions = MODULE.canonical_general_actor_inputs(
                round_root, process, "R5"
            )
            for item in opened:
                path = round_root / item
                if path.exists():
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"fixture:{item}".encode("utf-8"))
            view = run / "views" / "R5"
            staged = MODULE.command_stage_actor(
                argparse.Namespace(
                    actor="R5",
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                )
            )
            self.assertIn("page-renders/P0001.png", staged["outputs"])
            for name in staged["outputs"]:
                path = view / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"output:{name}".encode("utf-8"))
            extra = view / "peer-leak.md"
            extra.write_text("forbidden", encoding="utf-8")
            args = promotion_args(
                actor="R5",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(MODULE, "run_general_scoped_gate") as gate, mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                with self.assertRaisesRegex(MODULE.ContractError, "not an exact closed"):
                    MODULE.command_promote_actor(args)
            gate.assert_not_called()
            extra.unlink()
            with mock.patch.object(
                MODULE, "run_general_scoped_gate", return_value=["gate"]
            ), mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                promoted = MODULE.command_promote_actor(args)
            self.assertEqual(promoted["status"], "promoted")
            self.assertTrue((round_root / "page-renders" / "P0001.png").is_file())

    def test_closed_snapshot_never_descends_into_unallowlisted_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "allowed.txt").write_text("allowed", encoding="utf-8")
            forbidden = root / "forbidden"
            forbidden.mkdir()
            (forbidden / "secret.txt").write_text("secret", encoding="utf-8")
            validator = MODULE.load_module(
                SKILL_ROOT / "scripts" / "validate_review_bundle.py",
                "validator_for_no_extra_descent",
            )
            path_type = type(root)
            original_iterdir = path_type.iterdir

            def guarded_iterdir(path):
                if Path(path) == forbidden:
                    raise AssertionError("unallowlisted directory was enumerated")
                return original_iterdir(path)

            with mock.patch.object(path_type, "iterdir", new=guarded_iterdir):
                with self.assertRaisesRegex(MODULE.ContractError, "extra_dirs"):
                    MODULE.closed_view_snapshot(root, ["allowed.txt"], validator)

    @unittest.skipUnless(os.name == "nt", "NTFS named streams are Windows-specific")
    def test_closed_snapshot_rejects_named_stream_on_view_root(self) -> None:
        with tempfile.TemporaryDirectory(dir="C:\\projects") as directory:
            root = Path(directory)
            (root / "allowed.txt").write_text("allowed", encoding="utf-8")
            stream = Path(str(root) + ":hidden")
            try:
                stream.write_bytes(b"forbidden")
            except OSError as exc:
                self.skipTest(f"test volume does not support directory ADS: {exc}")
            validator = MODULE.load_module(
                SKILL_ROOT / "scripts" / "validate_review_bundle.py",
                "validator_for_root_ads",
            )
            with self.assertRaisesRegex(MODULE.ContractError, "root.*named-stream"):
                MODULE.closed_view_snapshot(root, ["allowed.txt"], validator)

    def test_clean_c_and_s_views_are_unified_exact_actor_roots(self) -> None:
        for actor in ("C", "S"):
            with self.subTest(actor=actor), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                run, round_root = make_run(base)
                process = full_process()
                write_json(round_root / "00-process-parameters.json", process)
                MODULE.command_stage_round(
                    argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
                )
                opened, data_inputs, _instructions = MODULE.canonical_clean_actor_inputs(
                    round_root, process, actor
                )
                for item in data_inputs:
                    path = round_root / item
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        path.write_bytes(f"fixture:{item}".encode("utf-8"))
                view = run / "views" / actor
                result = MODULE.command_stage_clean(
                    argparse.Namespace(
                        skill_root=SKILL_ROOT,
                        round_root=round_root,
                        view_root=view,
                        actor=actor,
                    )
                )
                self.assertEqual(result["opened"], opened)
                self.assertTrue((view / "SKILL.md").is_file())
                self.assertTrue((view / "rules" / "scripts").is_dir())
                self.assertEqual(
                    result["path_mapping"]["SKILL.md"], str(view / "SKILL.md")
                )
                actual = sorted(
                    path.relative_to(view).as_posix()
                    for path in view.rglob("*")
                    if path.is_file()
                )
                self.assertEqual(actual, sorted(opened))
                self.assertEqual(result["mechanical_extra_trees"], [])
                if actor == "S":
                    self.assertFalse((view / "thesis.pdf").exists())
                else:
                    self.assertTrue((view / "thesis.pdf").is_file())
                    self.assertFalse((view / "page-renders").exists())
                    self.assertFalse((view / "06-semantic-acceptance").exists())

    def test_clean_promotion_is_no_replace_and_hash_preserving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            view = run / "views" / "C"
            _opened, data_inputs, _instructions = MODULE.canonical_clean_actor_inputs(
                round_root, process, "C"
            )
            for item in data_inputs:
                path = round_root / item
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(f"fixture:{item}".encode("utf-8"))
            staged = MODULE.command_stage_clean(
                argparse.Namespace(
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                    actor="C",
                )
            )
            for name in MODULE.C_OUTPUTS:
                (view / name).write_bytes(f"content:{name}".encode("utf-8"))
            args = promotion_args(
                actor="C",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(
                MODULE, "run_scoped_gate", return_value=["gate"]
            ), mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                result = MODULE.command_promote_clean(args)
            self.assertEqual(result["status"], "promoted")
            for name in MODULE.C_OUTPUTS:
                self.assertEqual((round_root / name).read_bytes(), (view / name).read_bytes())
            with mock.patch.object(
                MODULE, "run_scoped_gate", return_value=["gate"]
            ), mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                with self.assertRaisesRegex(MODULE.ContractError, "overwrite destination"):
                    MODULE.command_promote_clean(args)

    def test_clean_promotion_rejects_input_identity_drift_before_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            _opened, data_inputs, _instructions = MODULE.canonical_clean_actor_inputs(
                round_root, process, "S"
            )
            for item in data_inputs:
                path = round_root / item
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(f"fixture:{item}".encode("utf-8"))
            view = run / "views" / "S"
            staged = MODULE.command_stage_clean(
                argparse.Namespace(
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                    actor="S",
                )
            )
            source = view / "R1-comprehensive-review.md"
            source.write_bytes(source.read_bytes() + b"drift")
            args = promotion_args(
                actor="S",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(MODULE, "run_scoped_gate") as gate:
                with self.assertRaisesRegex(MODULE.ContractError, "commitment changed"):
                    MODULE.command_promote_clean(args)
            gate.assert_not_called()

    def test_clean_promotion_rejects_late_extra_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            _opened, data_inputs, _instructions = MODULE.canonical_clean_actor_inputs(
                round_root, process, "C"
            )
            for item in data_inputs:
                path = round_root / item
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(f"fixture:{item}".encode("utf-8"))
            view = run / "views" / "C"
            staged = MODULE.command_stage_clean(
                argparse.Namespace(
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                    actor="C",
                )
            )
            for name in MODULE.C_OUTPUTS:
                (view / name).write_bytes(f"content:{name}".encode("utf-8"))

            def gate_with_late_extra(*_args):
                (view / "LATE-EXTRA.txt").write_text("forbidden", encoding="utf-8")
                return ["gate"]

            args = promotion_args(
                actor="C",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(
                MODULE, "run_scoped_gate", side_effect=gate_with_late_extra
            ), mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                with self.assertRaisesRegex(MODULE.ContractError, "exact closed"):
                    MODULE.command_promote_clean(args)
            for name in MODULE.C_OUTPUTS:
                self.assertFalse((round_root / name).exists())

    def test_general_promotion_rejects_extra_injected_at_copy_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            (round_root / "thesis.pdf").write_bytes(b"fixture pdf bytes")
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            view = run / "views" / "P"
            staged = MODULE.command_stage_actor(
                argparse.Namespace(
                    actor="P",
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                )
            )
            for name in staged["outputs"]:
                (view / name).write_bytes(f"packet:{name}".encode("utf-8"))
            real_copy = MODULE.copy_output_set

            def inject_then_copy(*args, **kwargs):
                (view / "LATE-EXTRA.txt").write_text("forbidden", encoding="utf-8")
                return real_copy(*args, **kwargs)

            args = promotion_args(
                actor="P",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(
                MODULE, "run_general_scoped_gate", return_value=["gate"]
            ), mock.patch.object(
                MODULE, "copy_output_set", side_effect=inject_then_copy
            ), mock.patch.object(
                MODULE,
                "validate_launch_for_promotion",
                return_value=accepted_launch_receipt(),
            ):
                with self.assertRaisesRegex(MODULE.ContractError, "exact closed"):
                    MODULE.command_promote_actor(args)
            for name in MODULE.P_OUTPUTS:
                self.assertFalse((round_root / name).exists())

    def test_copy_set_rolls_back_first_output_when_second_copy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _run, round_root = make_run(base)
            view = base / "view"
            (view / "out").mkdir(parents=True)
            (view / "input.txt").write_bytes(b"input")
            (view / "out" / "a.txt").write_bytes(b"first")
            (view / "out" / "b.txt").write_bytes(b"second")
            validator = MODULE.load_module(
                SKILL_ROOT / "scripts" / "validate_review_bundle.py",
                "validator_for_copy_rollback",
            )
            opened = ["input.txt"]
            outputs = ["out/a.txt", "out/b.txt"]
            snapshot = MODULE.closed_view_snapshot(
                view, [*opened, *outputs], validator
            )
            commitment = MODULE.input_commitment(view, opened)
            real_copy = MODULE.copy_file_exclusive_with_identity
            call_count = 0

            def fail_second(source: Path, destination: Path):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise MODULE.ContractError("injected second-copy failure")
                return real_copy(source, destination)

            with mock.patch.object(
                MODULE,
                "copy_file_exclusive_with_identity",
                side_effect=fail_second,
            ):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "injected second-copy failure"
                ):
                    MODULE.copy_output_set(
                        view,
                        round_root,
                        outputs,
                        opened=opened,
                        expected_view_snapshot=snapshot,
                        expected_input_commitment=commitment,
                        validator=validator,
                    )
            self.assertFalse((round_root / "out" / "a.txt").exists())
            self.assertFalse((round_root / "out" / "b.txt").exists())
            self.assertFalse((round_root / "out").exists())

    def test_promotion_requires_real_v3_launch_record_before_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            (round_root / "thesis.pdf").write_bytes(b"fixture pdf bytes")
            MODULE.command_stage_round(
                argparse.Namespace(skill_root=SKILL_ROOT, round_root=round_root)
            )
            view = run / "views" / "P"
            staged = MODULE.command_stage_actor(
                argparse.Namespace(
                    actor="P",
                    skill_root=SKILL_ROOT,
                    round_root=round_root,
                    view_root=view,
                )
            )
            for name in staged["outputs"]:
                (view / name).write_bytes(f"packet:{name}".encode("utf-8"))
            args = promotion_args(
                actor="P",
                view=view,
                round_root=round_root,
                commitment=staged["input_commitment_sha256"],
            )
            with mock.patch.object(MODULE, "run_general_scoped_gate") as gate:
                with self.assertRaisesRegex(MODULE.ContractError, "launch record"):
                    MODULE.command_promote_actor(args)
            gate.assert_not_called()

    def test_launch_receipt_freezes_terminal_output_identity_and_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run, round_root = make_run(base)
            process = full_process()
            write_json(round_root / "00-process-parameters.json", process)
            view = run / "views" / "P"
            view.mkdir()
            write_json(view / "00-process-parameters.json", process)
            for output in MODULE.P_OUTPUTS:
                (view / output).write_bytes(f"output:{output}".encode("utf-8"))
            log_path = run / "orchestration" / "P.jsonl"
            log_path.write_text("{}\n", encoding="utf-8")
            launch_id = "12345678-1234-4234-8234-123456789abc"
            record_path = run / "orchestration" / "P-launch.json"
            write_json(
                record_path,
                {
                    "schema": MODULE.CANONICAL_LAUNCH_SCHEMA,
                    "workspace": str(view),
                    "log_path": str(log_path),
                },
            )
            record_sha256 = MODULE.sha256_file(record_path)
            output_commitment = MODULE.input_commitment(view, MODULE.P_OUTPUTS)
            real_load = MODULE.load_module

            def fake_load(path: Path, name: str):
                if path.name == "validate_actor_transport.py":
                    return types.SimpleNamespace(
                        validate_log=lambda *_args: {"status": "PASS"}
                    )
                if path.name == "manage_review_retry.py":
                    return types.SimpleNamespace(
                        verify_process_seal=lambda _args: {
                            "process_sha256": MODULE.sha256_file(
                                round_root / "00-process-parameters.json"
                            ),
                            "seal_sha256": "F" * 64,
                        }
                    )
                return real_load(path, name)

            arguments = dict(
                actor="P",
                view_root=view,
                round_root=round_root,
                process=process,
                input_commitment_sha256="C" * 64,
                launch_record_path=record_path,
                expected_launch_id=launch_id,
                expected_process_seal_sha256="F" * 64,
                expected_launch_record_sha256=record_sha256,
                expected_output_commitment_sha256=output_commitment,
            )
            with mock.patch.object(MODULE, "load_module", side_effect=fake_load):
                result = MODULE.validate_launch_for_promotion(**arguments)
            self.assertEqual(output_commitment, result["output_commitment_sha256"])

            target = view / MODULE.P_OUTPUTS[0]
            target.write_bytes(b"different but potentially valid output")
            with mock.patch.object(MODULE, "load_module", side_effect=fake_load):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "retained launch commitment"
                ):
                    MODULE.validate_launch_for_promotion(**arguments)


if __name__ == "__main__":
    unittest.main()
