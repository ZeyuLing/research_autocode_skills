from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from pypdf import PdfWriter


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "build_canonical_actor_prompt.py"
SPEC = importlib.util.spec_from_file_location(
    "build_canonical_actor_prompt_tested", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_pdf(path: Path, pages: int = 2) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


class CanonicalActorFixture:
    """Create a real initialized/sealed run without thesis semantics."""

    def __init__(self, base: Path, actor: str) -> None:
        self.base = base.resolve()
        self.actor = actor
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.source_pdf = self.base / "source.pdf"
        write_pdf(self.source_pdf)
        self.pdf_hash = file_digest(self.source_pdf)
        self.round_id = f"round-canonical-{actor.lower()}"
        self.retry_id = f"retry-canonical-{actor.lower()}-01"
        self.run_root = self.workspace / f"run-{actor.lower()}"
        self.retry_manager = MODULE.reviewer.canonical_retry_manager()
        initialized = self.retry_manager.initialize(
            types.SimpleNamespace(
                workspace=str(self.workspace),
                run_root=str(self.run_root),
                source_pdf=str(self.source_pdf),
                neutral_pdf_name="frozen-thesis.pdf",
                expected_sha256=self.pdf_hash,
                expected_pages=2,
                new_round_id=self.round_id,
                new_retry_id=self.retry_id,
                initial_run=True,
                old_round_id=None,
                old_retry_id=None,
            )
        )
        self.metadata_hash = initialized["metadata_sha256"]
        self.frozen_at = initialized["frozen_at_utc"]
        self.round_root = self.run_root / "round"
        self.view_root = self.run_root / "views" / actor
        self.preplan_path = self.base / f"preplan-{actor}.json"
        self.prompt_path = self.base / f"prompt-{actor}.txt"
        self.python_executable = Path(sys.executable).resolve()
        self.scratch = self.base / f"scratch-{actor}"
        self.scratch.mkdir()
        self.preplan = {
            "round_id": self.round_id,
            "retry_id": self.retry_id,
            "frozen_pdf_file": "frozen-thesis.pdf",
            "selected_pdf_sha256": self.pdf_hash,
            "physical_page_count": 2,
            "degree_level": "doctorate",
            "governing_local_files": [],
            "output_language": "zh-CN",
        }
        write_json(self.preplan_path, self.preplan)
        self.planned: dict | None = None
        self.process: dict | None = None
        self.process_hash = ""
        self.seal_hash = ""

    def plan(self) -> dict:
        self.planned = MODULE.plan_prompt(
            self.preplan_path,
            self.round_root,
            self.view_root,
            self.actor,
            self.prompt_path,
            self.python_executable,
            self.scratch,
        )
        return self.planned

    def _prompt_map(self, prompt_sha256: str) -> dict[str, str]:
        actors = [
            "P",
            "R1",
            "R2",
            "R3",
            "R4",
            "R5",
            "AI",
            "SA-R1",
            "SA-R2",
            "SA-R3",
            "SA-R4",
            "SA-R5",
            "SA-AI",
            "C",
            "S",
        ]
        result = {
            item: digest(f"canonical-fixture-{item}".encode("utf-8"))
            for item in actors
        }
        result[self.actor] = prompt_sha256
        if len(set(result.values())) != len(result):
            raise AssertionError("fixture prompt hashes unexpectedly collide")
        return result

    def stage(self) -> None:
        if self.planned is None:
            self.plan()
        assert self.planned is not None
        self.process = {
            **self.preplan,
            "frozen_at": self.frozen_at,
            "degree_type": "academic",
            "institution": None,
            "school_or_department": None,
            "discipline": None,
            "expected_submission_year": 2026,
            "artifact_type": "blind-copy",
            "review_mode": "initial",
            "governing_rule_urls": [],
            "decision_regime_status": "skill-default",
            "actor_prompt_sha256": self._prompt_map(
                self.planned["prompt_sha256"]
            ),
        }
        process_path = self.round_root / "00-process-parameters.json"
        write_json(process_path, self.process)
        self.process_hash = file_digest(process_path)
        sealed = self.retry_manager.seal_process(
            types.SimpleNamespace(
                workspace=str(self.workspace),
                run_root=str(self.run_root),
                expected_metadata_sha256=self.metadata_hash,
                expected_process_sha256=self.process_hash,
            )
        )
        self.seal_hash = sealed["seal_sha256"]

        MODULE.stage_o.command_stage_round(
            argparse.Namespace(skill_root=SKILL_ROOT, round_root=self.round_root)
        )
        for relative in self.planned["opened"]:
            destination = self.round_root / Path(relative)
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.suffix == ".csv":
                destination.write_text("fixture\n", encoding="utf-8")
            elif destination.suffix == ".json":
                destination.write_text("{}\n", encoding="utf-8")
            else:
                destination.write_text("current-round fixture\n", encoding="utf-8")

        namespace = argparse.Namespace(
            skill_root=SKILL_ROOT,
            round_root=self.round_root,
            view_root=self.view_root,
            actor=self.actor,
        )
        if self.actor in {"P", "AI"}:
            MODULE.stage_o.command_stage_actor(namespace)
        else:
            MODULE.stage_o.command_stage_clean(namespace)

    def verify(self, **overrides: object) -> dict:
        values = {
            "run_root_value": self.run_root,
            "round_root_value": self.round_root,
            "view_root_value": self.view_root,
            "prompt_value": self.prompt_path,
            "actor_value": self.actor,
            "expected_process_sha256_value": self.process_hash,
            "expected_seal_sha256_value": self.seal_hash,
            "python_executable_value": self.python_executable,
            "scratch_value": self.scratch,
        }
        values.update(overrides)
        return MODULE.verify_prompt(**values)


class BuildCanonicalActorPromptTests(unittest.TestCase):
    def test_p_and_c_treat_governing_urls_as_non_openable_metadata(self) -> None:
        for actor in ("P", "C"):
            with self.subTest(actor=actor):
                rule = MODULE.public_endpoint_rule(actor)
                self.assertIn("public_endpoints=[none]", rule)
                self.assertIn("governing_rule_urls", rule)
                self.assertIn("do not open", rule.casefold())
        self.assertIn(
            "governing_local_files", MODULE.public_endpoint_rule("P")
        )

    def test_all_four_actors_have_deterministic_closed_prompts(self) -> None:
        expected_outputs = {
            "P": list(MODULE.stage_o.P_OUTPUTS),
            "AI": list(MODULE.stage_o.AI_OUTPUTS),
            "C": list(MODULE.stage_o.C_OUTPUTS),
            "S": list(MODULE.stage_o.S_OUTPUTS),
        }
        expected_gate_names = {
            "P": ["validate_stage_p_output.py"],
            "AI": ["validate_ai_output.py"],
            "C": ["materialize_owner_outputs.py", "validate_chair_output.py"],
            "S": ["materialize_owner_outputs.py", "validate_summary_output.py"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for actor in MODULE.SUPPORTED_ACTORS:
                with self.subTest(actor=actor):
                    actor_root = base / actor
                    actor_root.mkdir()
                    fixture = CanonicalActorFixture(actor_root, actor)
                    planned = fixture.plan()
                    prompt_bytes = fixture.prompt_path.read_bytes()
                    prompt = prompt_bytes.decode("utf-8")
                    rerendered = MODULE.render_prompt(
                        fixture.view_root,
                        actor,
                        planned["stable_process_fields"],
                        planned["opened"],
                        planned["owned_outputs"],
                        planned["instruction_sha256"],
                        fixture.python_executable,
                        planned["python_executable_sha256"],
                        fixture.scratch,
                    )
                    self.assertEqual(prompt_bytes, rerendered)
                    self.assertEqual(digest(prompt_bytes), planned["prompt_sha256"])
                    self.assertEqual(planned["owned_outputs"], expected_outputs[actor])
                    self.assertEqual(prompt.count("[BOUND-ACTOR-CONTRACT-BEGIN]"), 1)
                    self.assertEqual(prompt.count("[BOUND-ACTOR-CONTRACT-END]"), 1)
                    self.assertIn(f"Actor ID: {actor}", prompt)
                    self.assertIn(str(fixture.view_root), prompt)
                    self.assertNotIn(str(fixture.round_root), prompt)
                    self.assertNotIn(str(fixture.run_root / "round"), prompt)
                    self.assertIn(
                        "no inherited user/thread/task turns beyond system/developer "
                        "instructions and the exact operational prompt",
                        prompt,
                    )
                    self.assertIn("received=[operational prompt]", prompt)
                    self.assertIn("neighboring paths were not enumerated", prompt)
                    self.assertIn("Run them yourself, in order", prompt)
                    for relative in planned["opened"]:
                        self.assertIn(str(fixture.view_root / Path(relative)), prompt)
                    for relative in expected_outputs[actor]:
                        self.assertIn(str(fixture.view_root / Path(relative)), prompt)
                    rendered_gate_names = [
                        Path(command[2]).name for command in planned["gate_commands"]
                    ]
                    self.assertEqual(rendered_gate_names, expected_gate_names[actor])
                    for command in planned["gate_commands"]:
                        self.assertEqual(command[0], str(fixture.python_executable))
                        self.assertEqual(command[1], "-B")
                        self.assertTrue(command[2].startswith(str(fixture.view_root)))
                        self.assertIn(str(fixture.view_root), command)

    def test_real_sealed_lifecycle_verifies_for_p_ai_c_and_s(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for actor in MODULE.SUPPORTED_ACTORS:
                with self.subTest(actor=actor):
                    actor_root = base / actor
                    actor_root.mkdir()
                    fixture = CanonicalActorFixture(actor_root, actor)
                    planned = fixture.plan()
                    fixture.stage()
                    verified = fixture.verify()
                    self.assertEqual(verified["status"], "VERIFIED")
                    self.assertEqual(verified["actor"], actor)
                    self.assertEqual(verified["prompt_sha256"], planned["prompt_sha256"])
                    self.assertEqual(verified["opened"], planned["opened"])
                    self.assertEqual(verified["owned_outputs"], planned["owned_outputs"])
                    self.assertEqual(verified["process_sha256"], fixture.process_hash)
                    self.assertEqual(
                        verified["expected_seal_sha256"], fixture.seal_hash
                    )

    def test_only_exact_p_ai_c_s_are_supported(self) -> None:
        for actor in ("H01", "V", "R1", "SA-R1", "p", "ai", "", " C"):
            with self.subTest(actor=actor), self.assertRaisesRegex(
                MODULE.ContractError, "exactly one of P, AI, C, or S"
            ):
                MODULE.require_actor(actor)

    def test_helper_paths_are_rejected_by_the_canonical_derivation(self) -> None:
        class FakeValidator:
            @staticmethod
            def canonical_stage_opened_inputs(*_args: object) -> list[str]:
                return ["00-process-parameters.json", "helpers/H01-output.bin"]

        process = {
            "round_id": "round-helper-reject",
            "retry_id": "retry-helper-reject",
            "frozen_pdf_file": "frozen-thesis.pdf",
            "selected_pdf_sha256": "A" * 64,
            "physical_page_count": 1,
            "degree_level": "doctorate",
            "governing_local_files": [],
            "output_language": "zh-CN",
        }
        with self.assertRaisesRegex(MODULE.ContractError, "do not support Stage-H"):
            MODULE.canonical_opened_inputs(process, "AI", FakeValidator())

    def test_future_view_must_be_exact_nonexistent_run_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fixture = CanonicalActorFixture(base, "P")
            wrong = fixture.run_root / "views" / "wrong-P"
            with self.assertRaisesRegex(MODULE.ContractError, "exactly the actor-ID"):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    wrong,
                    "P",
                    fixture.prompt_path,
                    fixture.python_executable,
                    fixture.scratch,
                )
            fixture.view_root.mkdir()
            with self.assertRaisesRegex(MODULE.ContractError, "must not exist"):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    fixture.view_root,
                    "P",
                    fixture.prompt_path,
                    fixture.python_executable,
                    fixture.scratch,
                )

    def test_verify_rejects_process_view_and_prompt_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for drift in ("process", "view", "prompt"):
                with self.subTest(drift=drift):
                    case_root = base / drift
                    case_root.mkdir()
                    fixture = CanonicalActorFixture(case_root, "AI")
                    fixture.plan()
                    fixture.stage()
                    if drift == "process":
                        process_path = fixture.round_root / "00-process-parameters.json"
                        process_path.write_bytes(process_path.read_bytes() + b" ")
                        expected = "external SHA-256 anchor|changed"
                    elif drift == "view":
                        (fixture.view_root / "PROHIBITED-OLD-REVIEW.md").write_text(
                            "not current input\n", encoding="utf-8"
                        )
                        expected = "not exact and input-only|topology"
                    else:
                        fixture.prompt_path.write_bytes(
                            fixture.prompt_path.read_bytes() + b"\n"
                        )
                        expected = "canonical final reconstruction|prompt SHA-256"
                    with self.assertRaisesRegex(MODULE.ContractError, expected):
                        fixture.verify()

    def test_verify_rejects_view_input_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CanonicalActorFixture(Path(temporary), "C")
            fixture.plan()
            fixture.stage()
            target = fixture.view_root / "90-chair-synthesis.md"
            # 90 is an output and is correctly absent before C.  Mutate one
            # frozen current input instead.
            target = fixture.view_root / "R1-comprehensive-review.md"
            target.write_text("changed after staging\n", encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.ContractError, "differ from final round|canonical skill"
            ):
                fixture.verify()

    def test_cli_is_closed_and_has_no_body_or_helper_escape_hatch(self) -> None:
        valid_plan = [
            "plan",
            "--process",
            "C:/x/preplan.json",
            "--round-root",
            "C:/x/run/round",
            "--view-root",
            "C:/x/run/views/P",
            "--actor",
            "P",
            "--output",
            "C:/x/prompt.txt",
            "--python-executable",
            "C:/Python/python.exe",
            "--scratch-dir",
            "C:/x/scratch",
        ]
        parsed = MODULE.parse_args(valid_plan)
        self.assertEqual(parsed.command, "plan")
        self.assertFalse(hasattr(parsed, "body"))
        self.assertFalse(hasattr(parsed, "helper_inputs"))
        for forbidden in ("--body", "--helper-input", "--role-text"):
            with self.subTest(flag=forbidden), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    MODULE.parse_args([*valid_plan, forbidden, "injected"])
        abbreviated = list(valid_plan)
        abbreviated[abbreviated.index("--process")] = "--proces"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE.parse_args(abbreviated)

    def test_cli_success_first_line_and_exact_verify_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CanonicalActorFixture(Path(temporary), "S")
            plan_argv = [
                "plan",
                "--process",
                str(fixture.preplan_path),
                "--round-root",
                str(fixture.round_root),
                "--view-root",
                str(fixture.view_root),
                "--actor",
                fixture.actor,
                "--output",
                str(fixture.prompt_path),
                "--python-executable",
                str(fixture.python_executable),
                "--scratch-dir",
                str(fixture.scratch),
            ]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = MODULE.main(plan_argv)
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertEqual(stdout.getvalue().splitlines()[0], "PLANNED")
            fixture.planned = json.loads(stdout.getvalue().splitlines()[1])
            fixture.stage()
            verify_argv = [
                "verify",
                "--run-root",
                str(fixture.run_root),
                "--round-root",
                str(fixture.round_root),
                "--view-root",
                str(fixture.view_root),
                "--prompt",
                str(fixture.prompt_path),
                "--actor",
                fixture.actor,
                "--expected-process-sha256",
                fixture.process_hash,
                "--expected-seal-sha256",
                fixture.seal_hash,
                "--python-executable",
                str(fixture.python_executable),
                "--scratch-dir",
                str(fixture.scratch),
            ]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = MODULE.main(verify_argv)
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertEqual(stdout.getvalue().splitlines()[0], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
