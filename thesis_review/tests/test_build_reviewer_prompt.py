from __future__ import annotations

import contextlib
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from pypdf import PdfWriter


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "build_reviewer_prompt.py"
SPEC = importlib.util.spec_from_file_location("build_reviewer_prompt", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BUNDLE_FIXTURE_PATH = SKILL_ROOT / "tests" / "test_validate_review_bundle.py"
BUNDLE_SPEC = importlib.util.spec_from_file_location(
    "stage_r_prompt_bundle_fixture", BUNDLE_FIXTURE_PATH
)
assert BUNDLE_SPEC is not None and BUNDLE_SPEC.loader is not None
bundle_fixture_module = importlib.util.module_from_spec(BUNDLE_SPEC)
BUNDLE_SPEC.loader.exec_module(bundle_fixture_module)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_pdf(path: Path, pages: int = 3) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


class ReviewerPromptFixture:
    """Exercise the real initialized-run/process-seal lifecycle without a thesis."""

    def __init__(
        self,
        base: Path,
        degree: str,
        actor: str,
        *,
        governing_file: bool = False,
        helper_input: bool = False,
        valid_packet: bool = False,
    ) -> None:
        self.base = base
        self.degree = degree
        self.actor = actor
        self.manager = MODULE.canonical_retry_manager()
        self.valid_packet = valid_packet
        self.seed_root: Path | None = None
        self.seed_process: dict | None = None
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        if valid_packet:
            self.seed_root = base / "stage-p-seed"
            self.seed_root.mkdir()
            harness = bundle_fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(self.seed_root, page_count=4)
            if degree == "doctorate":
                harness.convert_bundle_to_doctorate(self.seed_root)
            self.seed_process = json.loads(
                (self.seed_root / "00-process-parameters.json").read_text(
                    encoding="utf-8"
                )
            )
            self.source_pdf = self.seed_root / "frozen-thesis.pdf"
            self.page_count = 4
            self.round_id = str(self.seed_process["round_id"])
            self.retry_id = str(self.seed_process["retry_id"])
        else:
            self.source_pdf = base / "source.pdf"
            write_pdf(self.source_pdf)
            self.page_count = 3
            self.round_id = f"round-{degree}-{actor.lower()}"
            self.retry_id = f"retry-{degree}-{actor.lower()}-01"
        self.pdf_hash = file_digest(self.source_pdf)
        self.run_root = self.workspace / f"run-{degree}-{actor.lower()}"
        initialized = self.manager.initialize(
            types.SimpleNamespace(
                workspace=str(self.workspace.resolve()),
                run_root=str(self.run_root.resolve()),
                source_pdf=str(self.source_pdf.resolve()),
                neutral_pdf_name="frozen-thesis.pdf",
                expected_sha256=self.pdf_hash,
                expected_pages=self.page_count,
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
        self.prompt_path = base / f"{actor}-prompt.txt"
        self.preplan_path = base / f"{actor}-preplan.json"
        self.python_executable = Path(sys.executable).resolve()

        self.governing_local_files: list[dict[str, str]] = []
        if governing_file:
            rule_path = self.round_root / "official-rule.txt"
            rule_path.write_bytes(b"official governing fixture\n")
            self.governing_local_files.append(
                {
                    "neutral_file": rule_path.name,
                    "official_title": "Official fixture rule",
                    "sha256": file_digest(rule_path),
                }
            )

        self.preplan = {
            "round_id": self.round_id,
            "retry_id": self.retry_id,
            "frozen_pdf_file": "frozen-thesis.pdf",
            "selected_pdf_sha256": self.pdf_hash,
            "physical_page_count": self.page_count,
            "degree_level": degree,
            "governing_local_files": self.governing_local_files,
            "output_language": "zh-CN",
        }
        write_json(self.preplan_path, self.preplan)
        stable = MODULE.stable_process_projection(self.preplan)
        scratch_parent = base / "private-scratch"
        scratch_parent.mkdir()
        self.scratch_dir = scratch_parent / MODULE.expected_scratch_basename(
            self.round_root.resolve(), stable, actor
        )
        self.scratch_dir.mkdir()

        self.helper_inputs: list[str] = []
        if helper_input:
            self.helper_inputs = [
                "helpers/H01-provenance.json",
                "helpers/H01-output-a.bin",
                "helpers/H01-output-b.bin",
            ]
        self.planned: dict | None = None
        self.process_hash = ""
        self.seal_hash = ""

    def plan(self) -> dict:
        self.planned = MODULE.plan_prompt(
            self.preplan_path,
            self.round_root,
            self.actor,
            self.prompt_path,
            self.python_executable,
            self.scratch_dir,
            helper_inputs=self.helper_inputs,
        )
        return self.planned

    def stage(self, prompt_sha256: str | None = None) -> tuple[dict, str, str]:
        if self.planned is None:
            self.plan()
        assert self.planned is not None
        count = 5 if self.degree == "doctorate" else 3
        actors = [
            "P",
            *(f"R{i}" for i in range(1, count + 1)),
            "AI",
            *(f"SA-R{i}" for i in range(1, count + 1)),
            "SA-AI",
            "C",
            "S",
        ]
        prompt_map = {
            name: digest(f"fixture-prompt-{name}".encode("utf-8"))
            for name in actors
        }
        prompt_map[self.actor] = prompt_sha256 or self.planned["prompt_sha256"]
        if self.seed_process is not None:
            process = {
                **self.seed_process,
                "frozen_at": self.frozen_at,
                "actor_prompt_sha256": {
                    **self.seed_process["actor_prompt_sha256"],
                    self.actor: prompt_map[self.actor],
                },
            }
        else:
            process = {
                **self.preplan,
                "frozen_at": self.frozen_at,
                "degree_type": "academic",
                "institution": None,
                "school_or_department": None,
                "discipline": None,
                "expected_submission_year": 2026,
                "artifact_type": "blind-copy",
                "review_mode": "fresh-rereview",
                "governing_rule_urls": [],
                "decision_regime_status": "skill-default",
                "actor_prompt_sha256": prompt_map,
            }
        process_path = self.round_root / "00-process-parameters.json"
        write_json(process_path, process)
        self.process_hash = file_digest(process_path)
        seal = self.manager.seal_process(
            types.SimpleNamespace(
                workspace=str(self.workspace.resolve()),
                run_root=str(self.run_root.resolve()),
                expected_metadata_sha256=self.metadata_hash,
                expected_process_sha256=self.process_hash,
            )
        )
        self.seal_hash = seal["seal_sha256"]

        if self.seed_root is not None:
            for filename in (
                "00-manifest.md",
                "01-policy-basis.md",
                "00-page-inventory.csv",
                "00-bibliography-inventory.csv",
                "00-citation-candidate-ledger.csv",
                "00-unmatched-bracket-ledger.csv",
                "00-citation-inventory.csv",
            ):
                shutil.copy2(self.seed_root / filename, self.round_root / filename)
            manifest_path = self.round_root / "00-manifest.md"
            manifest = manifest_path.read_text(encoding="utf-8")
            manifest = re.sub(
                r"(?m)^- Process-parameter file and SHA-256: .*$",
                "- Process-parameter file and SHA-256: "
                f"00-process-parameters.json / {self.process_hash}",
                manifest,
            )
            manifest = re.sub(
                r"(?m)^- Frozen at: .*$",
                f"- Frozen at: {self.frozen_at}",
                manifest,
            )
            manifest = re.sub(
                r"frozen_at=[^ ;]+",
                f"frozen_at={self.frozen_at}",
                manifest,
            )
            manifest_path.write_text(manifest, encoding="utf-8")

        if self.helper_inputs:
            helper_root = self.round_root / "helpers"
            helper_root.mkdir()
            output_paths = [
                helper_root / "H01-output-a.bin",
                helper_root / "H01-output-b.bin",
            ]
            for index, output_path in enumerate(output_paths, start=1):
                output_path.write_bytes(
                    f"current-round helper output {index}\n".encode("utf-8")
                )
            opened_inputs = ["00-process-parameters.json"]
            write_json(
                helper_root / "H01-provenance.json",
                {
                    "actor_id": "H01",
                    "round_id": process["round_id"],
                    "retry_id": process["retry_id"],
                    "prompt_sha256": digest(b"fixture-helper-H01-prompt"),
                    "fresh_context_declaration": (
                        "no inherited user/thread/task turns beyond system/developer "
                        "instructions and the exact operational prompt"
                    ),
                    "input_receipt_access_declaration": (
                        "received=[operational prompt]; "
                        "opened=[00-process-parameters.json]; "
                        "no unlisted substantive assertion was received; "
                        "no prohibited context/artifact was used; "
                        "neighboring paths were not enumerated"
                    ),
                    "received_blocks": ["operational prompt"],
                    "opened_inputs": opened_inputs,
                    "tool": "fixture-helper",
                    "version": "1.0",
                    "command_or_query": "build current-round fixture sidecar",
                    "pdf_sha256_start": self.pdf_hash,
                    "pdf_sha256_end": self.pdf_hash,
                    "recipient_stages": [self.actor],
                    "limitations": [],
                    "outputs": [
                        {
                            "file": output_path.name,
                            "sha256": file_digest(output_path),
                        }
                        for output_path in output_paths
                    ],
                },
            )

        validator = MODULE.canonical_validator()
        for relative in self.planned["opened"]:
            destination = self.round_root / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                continue
            if relative == "SKILL.md":
                shutil.copy2(SKILL_ROOT / "SKILL.md", destination)
            elif relative in validator.SKILL_REFERENCE_FILES:
                shutil.copy2(SKILL_ROOT / "references" / relative, destination)
            elif relative.startswith("rules/scripts/"):
                shutil.copy2(SKILL_ROOT / "scripts" / Path(relative).name, destination)
            elif relative == "00-manifest.md":
                if self.seed_root is None:
                    destination.write_text(
                        "# Frozen packet manifest\n\n"
                        "- Process-parameter file and SHA-256: "
                        f"00-process-parameters.json / {self.process_hash}\n",
                        encoding="utf-8",
                    )
            elif relative.startswith("helpers/"):
                raise AssertionError(f"fixture failed to create helper {relative}")
            elif relative not in {
                "00-process-parameters.json",
                "frozen-thesis.pdf",
                *(item["neutral_file"] for item in self.governing_local_files),
            }:
                destination.write_text("current-round packet fixture\n", encoding="utf-8")
        stage_p_validator = self.round_root / "rules/scripts/validate_stage_p_output.py"
        if not stage_p_validator.exists():
            stage_p_validator.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                SKILL_ROOT / "scripts/validate_stage_p_output.py",
                stage_p_validator,
            )
        return process, self.process_hash, self.seal_hash

    def verify(self, **overrides: object) -> dict:
        values = {
            "run_root_value": self.run_root,
            "round_root_value": self.round_root,
            "prompt_value": self.prompt_path,
            "actor_value": self.actor,
            "expected_process_sha256": self.process_hash,
            "expected_seal_sha256": self.seal_hash,
            "python_executable_value": self.python_executable,
            "scratch_dir_value": self.scratch_dir,
            "helper_inputs": self.helper_inputs,
        }
        values.update(overrides)
        return MODULE.verify_prompt(**values)


class BuildReviewerPromptTests(unittest.TestCase):
    def test_all_degree_appropriate_reviewers_receive_exact_finding_guard(self) -> None:
        cases = [
            *(("doctorate", f"R{i}") for i in range(1, 6)),
            *(("masters", f"R{i}") for i in range(1, 4)),
        ]
        six_questions = (
            "1. What exactly is visible or stated?",
            "2. Where is it?",
            "3. Which claim, rule, or reader task does it affect?",
            "4. What evidence supports the concern?",
            "5. What is the least costly sufficient remedy?",
            "6. Is that remedy part of the thesis or a verified formal submission obligation, rather than a request for hidden author-side proof?",
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for degree, actor in cases:
                with self.subTest(degree=degree, actor=actor):
                    case_root = base / f"{degree}-{actor}"
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(case_root, degree, actor)
                    metadata = fixture.plan()
                    prompt = fixture.prompt_path.read_text(encoding="utf-8")
                    self.assertEqual(
                        digest(fixture.prompt_path.read_bytes()), metadata["prompt_sha256"]
                    )
                    self.assertIn(
                        "Finding evidence self-check (mandatory for every proposed S0--S4 finding)",
                        prompt,
                    )
                    for question in six_questions:
                        self.assertEqual(prompt.count(question), 1)
                    self.assertIn("search the whole frozen PDF", prompt)
                    self.assertIn("minimum residual", prompt)
                    self.assertIn("`Location`, `Observation`, and `Required action`", prompt)
                    self.assertIn("downgrade the item to a `Question`", prompt)
                    self.assertIn("otherwise delete it", prompt)
                    self.assertIn("If question 6 is answered no, delete", prompt)
                    self.assertEqual(metadata["python_executable"], str(fixture.python_executable))
                    self.assertEqual(metadata["scratch_dir"], str(fixture.scratch_dir))

    def test_real_lifecycle_verifies_pdf_process_seal_runtime_and_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary), "doctorate", "R4", valid_packet=True
            )
            planned = fixture.plan()
            _process, process_hash, seal_hash = fixture.stage()
            verified = fixture.verify()
            self.assertEqual(verified["status"], "VERIFIED")
            self.assertEqual(verified["prompt_sha256"], planned["prompt_sha256"])
            self.assertEqual(verified["process_sha256"], process_hash)
            self.assertEqual(verified["expected_seal_sha256"], seal_hash)
            self.assertEqual(verified["process_seal"]["seal_sha256"], seal_hash)
            self.assertEqual(verified["python_executable"], str(fixture.python_executable))
            self.assertEqual(verified["scratch_dir"], str(fixture.scratch_dir))
            self.assertIn("04-citation-claim-audit-ledger.csv", verified["owned_outputs"])

    def test_exact_all_role_gate_command_arrays_use_bound_python_and_b_flag(self) -> None:
        cases = [
            *(("doctorate", f"R{i}") for i in range(1, 6)),
            *(("masters", f"R{i}") for i in range(1, 4)),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for degree, actor in cases:
                with self.subTest(degree=degree, actor=actor):
                    case_root = base / f"{degree}-{actor}"
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(case_root, degree, actor)
                    metadata = fixture.plan()
                    python = str(fixture.python_executable)
                    round_root = str(fixture.round_root)
                    if (degree, actor) == ("doctorate", "R4"):
                        expected = [
                            [python, "-B", str(fixture.round_root / "rules/scripts/materialize_owner_outputs.py"), round_root, "R4"],
                            [python, "-B", str(fixture.round_root / "rules/scripts/validate_r4_output.py"), round_root],
                        ]
                    elif (degree, actor) == ("doctorate", "R5"):
                        expected = [
                            [python, "-B", str(fixture.round_root / "rules/scripts/materialize_owner_outputs.py"), round_root, "R5"],
                            [python, "-B", str(fixture.round_root / "rules/scripts/validate_r5_output.py"), round_root],
                        ]
                    elif (degree, actor) == ("masters", "R3"):
                        expected = [
                            [python, "-B", str(fixture.round_root / "rules/scripts/materialize_owner_outputs.py"), round_root, "R3"],
                            [python, "-B", str(fixture.round_root / "rules/scripts/validate_master_r3_output.py"), round_root],
                        ]
                    else:
                        expected = [
                            [python, "-B", str(fixture.round_root / "rules/scripts/validate_reviewer_output.py"), round_root, actor]
                        ]
                    self.assertEqual(metadata["gate_commands"], expected)
                    prompt = fixture.prompt_path.read_text(encoding="utf-8")
                    self.assertIn("`PYTHONDONTWRITEBYTECODE=1`", prompt)
                    for command in expected:
                        encoded = json.dumps(
                            command, ensure_ascii=False, separators=(",", ":")
                        )
                        self.assertEqual(prompt.count(encoded), 1)

    def test_prompt_or_final_actor_commitment_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            prose_case = base / "prose"
            prose_case.mkdir()
            fixture = ReviewerPromptFixture(prose_case, "doctorate", "R1")
            fixture.plan()
            fixture.stage()
            fixture.prompt_path.write_bytes(
                fixture.prompt_path.read_bytes() + b"\nArbitrary prose.\n"
            )
            with self.assertRaisesRegex(
                MODULE.ContractError,
                "bytes differ from the canonical Stage-R rendering",
            ):
                fixture.verify()

            commitment_case = base / "commitment"
            commitment_case.mkdir()
            fixture = ReviewerPromptFixture(commitment_case, "masters", "R2")
            fixture.plan()
            fixture.stage(prompt_sha256="F" * 64)
            with self.assertRaisesRegex(MODULE.ContractError, "does not equal process"):
                fixture.verify()

    def test_pdf_and_governing_byte_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for mutation in ("pdf", "governing"):
                with self.subTest(mutation=mutation):
                    case_root = base / mutation
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(
                        case_root,
                        "doctorate",
                        "R2",
                        governing_file=mutation == "governing",
                    )
                    fixture.plan()
                    fixture.stage()
                    target = fixture.round_root / (
                        "frozen-thesis.pdf" if mutation == "pdf" else "official-rule.txt"
                    )
                    target.write_bytes(target.read_bytes() + b"drift")
                    with self.assertRaisesRegex(
                        MODULE.ContractError,
                        "real process-seal verification failed|hash mismatch|identity mismatch",
                    ):
                        fixture.verify()

    def test_missing_or_wrong_process_seal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for mutation in ("missing", "wrong-anchor"):
                with self.subTest(mutation=mutation):
                    case_root = base / mutation
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(case_root, "masters", "R1")
                    fixture.plan()
                    fixture.stage()
                    if mutation == "missing":
                        (fixture.run_root / "orchestration/process-seal.json").unlink()
                        kwargs = {}
                    else:
                        kwargs = {"expected_seal_sha256": "E" * 64}
                    with self.assertRaisesRegex(
                        MODULE.ContractError, "real process-seal verification failed"
                    ):
                        fixture.verify(**kwargs)

    def test_staged_validator_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for validator_name, error in (
                ("validate_r4_output.py", "staged reviewer validator hash mismatch"),
                (
                    "validate_stage_p_output.py",
                    "staged Stage-P scoped validator hash mismatch",
                ),
            ):
                with self.subTest(validator=validator_name):
                    case_root = base / validator_name
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(case_root, "doctorate", "R4")
                    fixture.plan()
                    fixture.stage()
                    staged = fixture.round_root / f"rules/scripts/{validator_name}"
                    staged.write_bytes(staged.read_bytes() + b"\n# drift\n")
                    with self.assertRaisesRegex(MODULE.ContractError, error):
                        fixture.verify()

    def test_scratch_overlap_and_nonempty_boundaries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            overlap_case = base / "overlap"
            overlap_case.mkdir()
            fixture = ReviewerPromptFixture(overlap_case, "doctorate", "R3")
            stable = MODULE.stable_process_projection(fixture.preplan)
            overlap = fixture.round_root / MODULE.expected_scratch_basename(
                fixture.round_root.resolve(), stable, fixture.actor
            )
            overlap.mkdir()
            with self.assertRaisesRegex(
                MODULE.ContractError, "must not overlap"
            ):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    fixture.actor,
                    fixture.prompt_path,
                    fixture.python_executable,
                    overlap,
                )

            nonempty_case = base / "nonempty"
            nonempty_case.mkdir()
            fixture = ReviewerPromptFixture(nonempty_case, "doctorate", "R3")
            fixture.plan()
            fixture.stage()
            (fixture.scratch_dir / "unexpected.tmp").write_text(
                "not empty", encoding="utf-8"
            )
            with self.assertRaisesRegex(MODULE.ContractError, "must be empty"):
                fixture.verify()

    def test_python_executable_must_be_same_safe_bound_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fixture = ReviewerPromptFixture(base, "masters", "R2")
            for name, contents in (
                ("fake-python.cmd", b"@echo PASS\r\n"),
                ("fake-python.exe", b"not a Python interpreter"),
            ):
                with self.subTest(fake=name):
                    fake = base / name
                    fake.write_bytes(contents)
                    with self.assertRaisesRegex(
                        MODULE.ContractError, "exact Python interpreter executing"
                    ):
                        MODULE.plan_prompt(
                            fixture.preplan_path,
                            fixture.round_root,
                            fixture.actor,
                            fixture.prompt_path,
                            fake,
                            fixture.scratch_dir,
                        )
            fixture.plan()
            fixture.stage()
            drifted_runtime = base / "drifted-python.exe"
            drifted_runtime.write_bytes(b"different runtime after plan")
            with mock.patch.object(MODULE.sys, "executable", str(drifted_runtime)):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "exact Python interpreter executing"
                ):
                    fixture.verify()

    def test_plan_rejects_prompt_python_and_scratch_inside_inferred_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for placement in ("prompt", "python", "scratch"):
                with self.subTest(placement=placement):
                    case_root = base / placement
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(case_root, "doctorate", "R1")
                    prompt = fixture.prompt_path
                    python = fixture.python_executable
                    scratch = fixture.scratch_dir
                    runtime_patch = contextlib.nullcontext()
                    if placement == "prompt":
                        prompt = fixture.run_root / "orchestration/R1-prompt.txt"
                    elif placement == "python":
                        python = fixture.run_root / "private-python.exe"
                        shutil.copy2(fixture.python_executable, python)
                        runtime_patch = mock.patch.object(
                            MODULE.sys, "executable", str(python)
                        )
                    else:
                        stable = MODULE.stable_process_projection(fixture.preplan)
                        scratch = fixture.run_root / "views" / MODULE.expected_scratch_basename(
                            fixture.round_root.resolve(), stable, fixture.actor
                        )
                        scratch.mkdir()
                    with runtime_patch:
                        with self.assertRaisesRegex(
                            MODULE.ContractError, "outside the run root|must not overlap"
                        ):
                            MODULE.plan_prompt(
                                fixture.preplan_path,
                                fixture.round_root,
                                fixture.actor,
                                prompt,
                                python,
                                scratch,
                            )

            wrong_round_case = base / "wrong-round-name"
            wrong_round_case.mkdir()
            fixture = ReviewerPromptFixture(wrong_round_case, "doctorate", "R1")
            wrong_round = fixture.run_root / "review-packet"
            wrong_round.mkdir()
            stable = MODULE.stable_process_projection(fixture.preplan)
            wrong_scratch_parent = wrong_round_case / "wrong-round-scratch"
            wrong_scratch_parent.mkdir()
            wrong_scratch = wrong_scratch_parent / MODULE.expected_scratch_basename(
                wrong_round.resolve(), stable, fixture.actor
            )
            wrong_scratch.mkdir()
            with self.assertRaisesRegex(MODULE.ContractError, "exactly the 'round' child"):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    wrong_round,
                    fixture.actor,
                    fixture.prompt_path,
                    fixture.python_executable,
                    wrong_scratch,
                )

    @unittest.skipUnless(os.name == "nt", "NTFS 8.3 alias test is Windows-specific")
    def test_plan_rejects_ntfs_short_aliases_into_run_root(self) -> None:
        def short_path(path: Path) -> Path:
            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(  # type: ignore[attr-defined]
                str(path), buffer, len(buffer)
            )
            if length == 0 or length >= len(buffer):
                self.skipTest("GetShortPathNameW is unavailable for this volume")
            return Path(buffer.value)

        with tempfile.TemporaryDirectory(prefix="stage-r-short-alias-") as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary), "doctorate", "R1"
            )
            views = fixture.run_root / "views"
            views.mkdir(exist_ok=True)
            short_views = short_path(views)
            if os.path.normcase(str(short_views)) == os.path.normcase(str(views)):
                self.skipTest("8.3 short-name generation is disabled on this volume")
            self.assertTrue(os.path.samefile(short_views, views))

            stable = MODULE.stable_process_projection(fixture.preplan)
            scratch_name = MODULE.expected_scratch_basename(
                fixture.round_root.resolve(), stable, fixture.actor
            )
            actual_scratch = views / scratch_name
            actual_scratch.mkdir()
            alias_scratch = short_views / scratch_name
            with self.assertRaisesRegex(
                MODULE.ContractError, "canonical filesystem spelling"
            ):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    fixture.actor,
                    fixture.prompt_path,
                    fixture.python_executable,
                    alias_scratch,
                )

            alias_prompt = short_views / "R1-prompt.txt"
            with self.assertRaisesRegex(
                MODULE.ContractError, "canonical filesystem spelling"
            ):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    fixture.actor,
                    alias_prompt,
                    fixture.python_executable,
                    fixture.scratch_dir,
                )

    @unittest.skipUnless(os.name == "nt", "UNC alias test is Windows-specific")
    def test_plan_and_verify_reject_unc_admin_share_aliases_into_run_root(self) -> None:
        def localhost_admin_alias(path: Path) -> Path:
            resolved = path.resolve(strict=True)
            drive = resolved.drive
            if not re.fullmatch(r"[A-Za-z]:", drive):
                self.skipTest("fixture is not stored on a drive-letter volume")
            drive_root = Path(f"{drive}\\")
            relative = resolved.relative_to(drive_root)
            alias = Path(rf"\\localhost\{drive[0]}$") / relative
            if not alias.exists():
                self.skipTest("localhost administrative share is unavailable")
            try:
                equivalent = os.path.samefile(alias, resolved)
            except OSError:
                self.skipTest("localhost administrative share cannot be identity-checked")
            if not equivalent:
                self.skipTest("localhost administrative share is not an equivalent alias")
            return alias

        with tempfile.TemporaryDirectory(prefix="stage-r-unc-alias-") as temporary:
            base = Path(temporary)
            fixture = ReviewerPromptFixture(base, "doctorate", "R1")
            views = fixture.run_root / "views"
            views.mkdir(exist_ok=True)
            alias_views = localhost_admin_alias(views)

            stable = MODULE.stable_process_projection(fixture.preplan)
            scratch_name = MODULE.expected_scratch_basename(
                fixture.round_root.resolve(), stable, fixture.actor
            )
            actual_scratch = views / scratch_name
            actual_scratch.mkdir()
            alias_scratch = alias_views / scratch_name
            self.assertTrue(os.path.samefile(alias_scratch, actual_scratch))
            with self.assertRaisesRegex(
                MODULE.ContractError, "UNC/device namespace"
            ):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    fixture.actor,
                    fixture.prompt_path,
                    fixture.python_executable,
                    alias_scratch,
                )

            alias_prompt = alias_views / "R1-prompt.txt"
            with self.assertRaisesRegex(
                MODULE.ContractError, "UNC/device namespace"
            ):
                MODULE.plan_prompt(
                    fixture.preplan_path,
                    fixture.round_root,
                    fixture.actor,
                    alias_prompt,
                    fixture.python_executable,
                    fixture.scratch_dir,
                )

            actual_scratch.rmdir()
            fixture.plan()
            fixture.stage()
            actual_prompt = views / "R1-verified-prompt.txt"
            shutil.copy2(fixture.prompt_path, actual_prompt)
            alias_existing_prompt = localhost_admin_alias(actual_prompt)
            with self.assertRaisesRegex(
                MODULE.ContractError, "UNC/device namespace"
            ):
                MODULE.verify_prompt(
                    fixture.run_root,
                    fixture.round_root,
                    alias_existing_prompt,
                    fixture.actor,
                    fixture.process_hash,
                    fixture.seal_hash,
                    fixture.python_executable,
                    fixture.scratch_dir,
                )

    @unittest.skipUnless(os.name == "nt", "UNC rejection is Windows-specific")
    def test_nested_unc_share_control_path_is_rejected_without_share_discovery(self) -> None:
        nested_share_path = Path(
            r"\\localhost\NestedShareRootedBelowRun\R1-prompt.txt"
        )
        with self.assertRaisesRegex(
            MODULE.ContractError, "UNC/device namespace"
        ):
            MODULE.absolute_no_alias(
                nested_share_path,
                "planned reviewer prompt",
                must_exist=False,
            )

    def test_helper_plan_to_verify_is_exact_and_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary),
                "doctorate",
                "R1",
                helper_input=True,
                valid_packet=True,
            )
            planned = fixture.plan()
            fixture.stage()
            verified = fixture.verify()
            self.assertEqual(verified["opened"], planned["opened"])
            with self.assertRaisesRegex(MODULE.ContractError, "helper allowlist differs"):
                fixture.verify(helper_inputs=[])
            with self.assertRaisesRegex(MODULE.ContractError, "helper allowlist differs"):
                fixture.verify(helper_inputs=list(reversed(fixture.helper_inputs)))

    def test_helper_provenance_hash_schema_recipient_and_order_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for mutation in (
                "hash",
                "schema",
                "recipient",
                "stage-p-recipient",
                "order",
            ):
                with self.subTest(mutation=mutation):
                    case_root = base / mutation
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(
                        case_root, "doctorate", "R1", helper_input=True
                    )
                    fixture.plan()
                    fixture.stage()
                    provenance_path = (
                        fixture.round_root / "helpers/H01-provenance.json"
                    )
                    provenance = json.loads(
                        provenance_path.read_text(encoding="utf-8")
                    )
                    if mutation == "hash":
                        provenance["outputs"][0]["sha256"] = "0" * 64
                        expected = "canonical provenance contract"
                    elif mutation == "schema":
                        del provenance["tool"]
                        expected = "canonical provenance contract"
                    elif mutation == "recipient":
                        provenance["recipient_stages"] = ["R2"]
                        expected = "helper allowlist differs"
                    elif mutation == "stage-p-recipient":
                        provenance["recipient_stages"] = ["P"]
                        expected = "canonical provenance contract"
                    else:
                        provenance["outputs"] = list(reversed(provenance["outputs"]))
                        expected = "helper allowlist differs"
                    write_json(provenance_path, provenance)
                    with self.assertRaisesRegex(MODULE.ContractError, expected):
                        fixture.verify()

    def test_helper_file_identity_drift_during_stage_p_gate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary),
                "doctorate",
                "R1",
                helper_input=True,
                valid_packet=True,
            )
            fixture.plan()
            fixture.stage()
            output = fixture.round_root / "helpers/H01-output-a.bin"
            original_gate = MODULE.verify_stage_p_gate

            def gate_then_replace(*args: object, **kwargs: object) -> dict:
                result = original_gate(*args, **kwargs)
                value = output.read_bytes()
                output.unlink()
                output.write_bytes(value)
                return result

            with mock.patch.object(
                MODULE, "verify_stage_p_gate", side_effect=gate_then_replace
            ):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "changed across verification"
                ):
                    fixture.verify()

    def test_late_opened_packet_identity_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary), "doctorate", "R4", valid_packet=True
            )
            fixture.plan()
            fixture.stage()
            target = fixture.round_root / "00-page-inventory.csv"
            original_scratch_check = MODULE.validate_actor_scratch
            calls = 0

            def replace_after_second_scratch(*args: object, **kwargs: object) -> Path:
                nonlocal calls
                result = original_scratch_check(*args, **kwargs)
                calls += 1
                if calls == 2:
                    payload = target.read_bytes()
                    target.unlink()
                    target.write_bytes(payload)
                return result

            with mock.patch.object(
                MODULE,
                "validate_actor_scratch",
                side_effect=replace_after_second_scratch,
            ):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "changed across verification|topology changed"
                ):
                    fixture.verify()

    def test_prompt_hardlink_injected_at_terminal_scratch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fixture = ReviewerPromptFixture(
                base, "doctorate", "R4", valid_packet=True
            )
            fixture.plan()
            fixture.stage()
            alias = base / "late-prompt-hardlink.txt"
            original_scratch_check = MODULE.validate_actor_scratch
            calls = 0

            def link_after_terminal_scratch(*args: object, **kwargs: object) -> Path:
                nonlocal calls
                result = original_scratch_check(*args, **kwargs)
                calls += 1
                if calls == 3:
                    os.link(fixture.prompt_path, alias)
                return result

            with mock.patch.object(
                MODULE,
                "validate_actor_scratch",
                side_effect=link_after_terminal_scratch,
            ):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "single-link|changed after the terminal"
                ):
                    fixture.verify()

    def test_late_round_file_and_directory_are_rejected_by_terminal_topology(self) -> None:
        for entry_type in ("file", "directory"):
            with self.subTest(entry_type=entry_type), tempfile.TemporaryDirectory() as temporary:
                fixture = ReviewerPromptFixture(
                    Path(temporary), "doctorate", "R4", valid_packet=True
                )
                fixture.plan()
                fixture.stage()
                original_scratch_check = MODULE.validate_actor_scratch
                calls = 0

                def inject_after_terminal_scratch(
                    *args: object, **kwargs: object
                ) -> Path:
                    nonlocal calls
                    result = original_scratch_check(*args, **kwargs)
                    calls += 1
                    if calls == 3:
                        inserted = fixture.round_root / "PROHIBITED-OLD-REVIEW"
                        if entry_type == "file":
                            inserted.with_suffix(".md").write_text(
                                "late unrelated artifact\n", encoding="utf-8"
                            )
                        else:
                            inserted.mkdir()
                    return result

                with mock.patch.object(
                    MODULE,
                    "validate_actor_scratch",
                    side_effect=inject_after_terminal_scratch,
                ):
                    with self.assertRaisesRegex(
                        MODULE.ContractError,
                        "round topology (?:changed|directory changed)",
                    ):
                        fixture.verify()

    def test_late_round_symlink_is_rejected_by_terminal_topology(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary), "doctorate", "R4", valid_packet=True
            )
            fixture.plan()
            fixture.stage()
            original_scratch_check = MODULE.validate_actor_scratch
            calls = 0

            def inject_after_terminal_scratch(*args: object, **kwargs: object) -> Path:
                nonlocal calls
                result = original_scratch_check(*args, **kwargs)
                calls += 1
                if calls == 3:
                    try:
                        os.symlink(
                            fixture.round_root / "00-page-inventory.csv",
                            fixture.round_root / "PROHIBITED-LINK.csv",
                        )
                    except OSError as exc:
                        raise unittest.SkipTest(
                            f"cannot create a symbolic-link regression fixture: {exc}"
                        ) from exc
                return result

            with mock.patch.object(
                MODULE,
                "validate_actor_scratch",
                side_effect=inject_after_terminal_scratch,
            ):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "link/reparse|topology changed"
                ):
                    fixture.verify()

    def test_final_stage_r_closure_rejects_drift_after_third_opened_check(self) -> None:
        for drift_kind in ("extra-file", "packet-hardlink"):
            with self.subTest(drift=drift_kind), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                fixture = ReviewerPromptFixture(
                    base, "doctorate", "R4", valid_packet=True
                )
                fixture.plan()
                fixture.stage()
                original_check = MODULE.require_unchanged_opened_inputs
                calls = 0

                def inject_after_third_opened(*args: object, **kwargs: object) -> None:
                    nonlocal calls
                    original_check(*args, **kwargs)
                    calls += 1
                    if calls == 3:
                        if drift_kind == "extra-file":
                            (fixture.round_root / "PROHIBITED-LATE-TOPOLOGY.md").write_text(
                                "late unrelated artifact\n", encoding="utf-8"
                            )
                        else:
                            os.link(
                                fixture.round_root / "00-page-inventory.csv",
                                base / "late-packet-hardlink.csv",
                            )

                with mock.patch.object(
                    MODULE,
                    "require_unchanged_opened_inputs",
                    side_effect=inject_after_third_opened,
                ):
                    with self.assertRaisesRegex(
                        MODULE.ContractError,
                        "topology changed|single-link",
                    ):
                        fixture.verify()
                self.assertGreaterEqual(calls, 3)

    @unittest.skipUnless(os.name == "nt", "NTFS stream tests are Windows-specific")
    def test_verify_rejects_named_streams_on_every_stage_r_boundary_class(self) -> None:
        cases = (
            "prompt",
            "scratch",
            "packet",
            "helper-output",
            "staged-validator",
        )
        with tempfile.TemporaryDirectory(prefix="stage-r-ads-") as temporary:
            base = Path(temporary)
            for case in cases:
                with self.subTest(case=case):
                    case_root = base / case
                    case_root.mkdir()
                    fixture = ReviewerPromptFixture(
                        case_root,
                        "doctorate",
                        "R4",
                        valid_packet=True,
                        helper_input=True,
                    )
                    fixture.plan()
                    fixture.stage()
                    target = {
                        "prompt": fixture.prompt_path,
                        "scratch": fixture.scratch_dir,
                        "packet": fixture.round_root / "00-page-inventory.csv",
                        "helper-output": (
                            fixture.round_root / "helpers/H01-output-a.bin"
                        ),
                        "staged-validator": (
                            fixture.round_root
                            / "rules/scripts/validate_stage_p_output.py"
                        ),
                    }[case]
                    stream = Path(f"{target}:stage-r-regression")
                    try:
                        stream.write_bytes(b"hidden stream must fail closed\n")
                    except OSError as exc:
                        self.skipTest(
                            f"fixture volume cannot create NTFS named streams: {exc}"
                        )
                    with self.assertRaisesRegex(
                        MODULE.ContractError, "named streams|single-link"
                    ):
                        fixture.verify()

    def test_helper_duplicate_json_key_is_rejected_before_reviewer_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary),
                "doctorate",
                "R1",
                helper_input=True,
                valid_packet=True,
            )
            fixture.plan()
            fixture.stage()
            provenance_path = fixture.round_root / "helpers/H01-provenance.json"
            provenance_text = provenance_path.read_text(encoding="utf-8")
            provenance_path.write_text(
                provenance_text.replace(
                    '"tool": "fixture-helper"',
                    '"tool": "fixture-helper", "tool": "fixture-helper"',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.ContractError,
                "canonical provenance contract.*duplicate JSON key 'tool'",
            ):
                fixture.verify()

    def test_cli_first_line_and_exit_contract_for_plan_verify_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(
                Path(temporary), "doctorate", "R5", valid_packet=True
            )
            plan_argv = [
                "plan",
                "--process",
                str(fixture.preplan_path),
                "--round-root",
                str(fixture.round_root),
                "--actor",
                fixture.actor,
                "--output",
                str(fixture.prompt_path),
                "--python-executable",
                str(fixture.python_executable),
                "--scratch-dir",
                str(fixture.scratch_dir),
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
                str(fixture.scratch_dir),
            ]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = MODULE.main(verify_argv)
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertEqual(stdout.getvalue().splitlines()[0], "VERIFIED")

            wrong = list(verify_argv)
            wrong[wrong.index("--expected-seal-sha256") + 1] = "0" * 64
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = MODULE.main(wrong)
            self.assertEqual(code, 1, stdout.getvalue())
            self.assertEqual(stdout.getvalue().splitlines()[0], "FAIL")

    def test_hash_looking_but_incomplete_stage_p_packet_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(Path(temporary), "masters", "R1")
            fixture.plan()
            fixture.stage()
            manifest = fixture.round_root / "00-manifest.md"
            self.assertIn(fixture.process_hash, manifest.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(MODULE.ContractError, "Stage-P scoped gate"):
                fixture.verify()

    def test_degree_inappropriate_reviewer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReviewerPromptFixture(Path(temporary), "masters", "R4")
            with self.assertRaisesRegex(MODULE.ContractError, "not required"):
                fixture.plan()


if __name__ == "__main__":
    unittest.main()
