from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = SKILL_ROOT / "scripts" / "build_semantic_acceptance_prompt.py"
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_semantic_acceptance_output.py"
SHARED_VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_review_bundle.py"
SEMANTIC_TEST_PATH = SKILL_ROOT / "tests" / "test_validate_semantic_acceptance_output.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module(VALIDATOR_PATH, "test_sa_prompt_contract_validator")
HELPER = load_module(HELPER_PATH, "test_sa_prompt_contract_builder")
SEMANTIC_TEST = load_module(SEMANTIC_TEST_PATH, "test_sa_prompt_contract_fixture")
SHARED = VALIDATOR.load_shared_validator()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def disabled_bytecode_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def copy_private_view(fixture: object, target: str, view: Path) -> list[str]:
    manifest_path = fixture.root / "00-manifest.md"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_text = "\n".join(
        line
        for line in manifest_text.splitlines()
        if not line.startswith("- Process-parameter file and SHA-256:")
    ).rstrip()
    manifest_path.write_text(
        manifest_text
        + "\n- Process-parameter file and SHA-256: "
        + f"00-process-parameters.json / {digest(fixture.root / '00-process-parameters.json')}\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    opened = VALIDATOR.canonical_sa_opened_inputs(
        fixture.root, fixture.process, target, errors
    )
    if errors:
        raise AssertionError(errors)
    view.mkdir(parents=True)
    for relative in opened:
        source = fixture.root / Path(relative)
        destination = view / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return opened


def freeze_validator_pair(fixture: object) -> None:
    scripts = fixture.root / "rules" / "scripts"
    shutil.copy2(VALIDATOR_PATH, scripts / VALIDATOR_PATH.name)
    shutil.copy2(SHARED_VALIDATOR_PATH, scripts / SHARED_VALIDATOR_PATH.name)


def stable_preplan_process(fixture: object) -> dict[str, object]:
    return {
        field: fixture.process[field]
        for field in HELPER.STABLE_PROCESS_FIELDS
    }


def write_process(path: Path, process: dict[str, object]) -> None:
    path.write_text(json.dumps(process, indent=2), encoding="utf-8")


class BuildSemanticAcceptancePromptTests(unittest.TestCase):
    def run_helper(
        self,
        *arguments: str,
        helper_path: Path = HELPER_PATH,
    ) -> subprocess.CompletedProcess[str]:
        arguments_list = list(arguments)
        if (
            arguments_list
            and arguments_list[0] in {"plan", "verify", "promote"}
            and "--python-executable" not in arguments_list
        ):
            arguments_list.extend(["--python-executable", sys.executable])
        if (
            arguments_list
            and arguments_list[0] in {"verify", "promote"}
            and "--expected-process-sha256" not in arguments_list
        ):
            root_flag = "--round-root" if arguments_list[0] == "promote" else "--view-root"
            root = Path(arguments_list[arguments_list.index(root_flag) + 1])
            arguments_list.extend(
                [
                    "--expected-process-sha256",
                    digest(root / "00-process-parameters.json"),
                ]
            )
        return subprocess.run(
            [sys.executable, "-B", str(helper_path), *arguments_list],
            text=True,
            capture_output=True,
            check=False,
            env=disabled_bytecode_environment(),
        )

    def run_validator(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(VALIDATOR_PATH), *arguments],
            text=True,
            capture_output=True,
            check=False,
            env=disabled_bytecode_environment(),
        )

    def plan_one(
        self,
        process_path: Path,
        view: Path,
        target: str,
        prompt: Path,
        *,
        helper_path: Path = HELPER_PATH,
    ) -> dict[str, object]:
        result = self.run_helper(
            "plan",
            "--process",
            str(process_path),
            "--view-root",
            str(view),
            "--target",
            target,
            "--output",
            str(prompt),
            helper_path=helper_path,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("PLANNED\n"), result.stdout)
        return json.loads(result.stdout.splitlines()[1])

    def verify_one_prelaunch(
        self,
        view: Path,
        prompt: Path,
        target: str,
        expected_process_hash: str,
    ) -> dict[str, object]:
        result = self.run_helper(
            "verify",
            "--view-root",
            str(view),
            "--prompt",
            str(prompt),
            "--target",
            target,
            "--expected-process-sha256",
            expected_process_hash,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("VERIFIED\n"), result.stdout)
        metadata = json.loads(result.stdout.splitlines()[1])
        self.assertEqual("absent", metadata["sa_output_state"])
        self.assertRegex(metadata["input_commitment"]["sha256"], r"^[0-9A-F]{64}$")
        return metadata

    def test_plan_is_pre_stage_p_algorithmic_deterministic_and_endpoint_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(
                round_root, degree="doctorate"
            )
            preplan_path = base / "preplan-process.json"
            write_process(preplan_path, stable_preplan_process(fixture))
            prompt_root = base / "prompts"
            prompt_root.mkdir()

            for target in ("R1", "R4", "R5", "AI"):
                with self.subTest(target=target):
                    view = base / f"view-{target}"
                    first_prompt = prompt_root / f"SA-{target}.txt"
                    self.assertFalse(view.exists())
                    metadata = self.plan_one(
                        preplan_path, view, target, first_prompt
                    )
                    self.assertFalse(view.exists())
                    prompt = first_prompt.read_text(encoding="utf-8")
                    private_md = view.resolve() / f"SA-{target}.md"
                    private_csv = view.resolve() / f"SA-{target}.csv"
                    nested_md = (
                        view.resolve()
                        / VALIDATOR.ACCEPTANCE_DIRECTORY
                        / f"SA-{target}.md"
                    )
                    nested_csv = nested_md.with_suffix(".csv")
                    self.assertIn(f"- {private_md}", prompt)
                    self.assertIn(f"- {private_csv}", prompt)
                    self.assertNotIn(str(nested_md), prompt)
                    self.assertNotIn(str(nested_csv), prompt)
                    expected_argv = [
                        str(Path(sys.executable).resolve()),
                        "-B",
                        str(
                            view.resolve()
                            / "rules"
                            / "scripts"
                            / "validate_semantic_acceptance_output.py"
                        ),
                        str(view.resolve()),
                        target,
                    ]
                    self.assertIn(
                        json.dumps(
                            expected_argv,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        prompt,
                    )
                    self.assertIn(
                        '{"PYTHONDONTWRITEBYTECODE":"1"}',
                        prompt,
                    )
                    self.assertNotIn("\npython -B ", prompt)
                    self.assertIn(
                        f"Bound Python executable: {Path(sys.executable).resolve()}",
                        prompt,
                    )
                    self.assertEqual(
                        str(Path(sys.executable).resolve()),
                        metadata["python_executable"],
                    )
                    self.assertEqual(
                        digest(Path(sys.executable).resolve()),
                        metadata["python_executable_identity"]["sha256"],
                    )
                    self.assertIn(
                        f"Do not create or write {view.resolve() / VALIDATOR.ACCEPTANCE_DIRECTORY}",
                        prompt,
                    )
                    self.assertEqual(digest(first_prompt), metadata["prompt_sha256"])
                    self.assertEqual(
                        "derive-at-launch-from-target-owned-ledgers",
                        metadata["public_endpoint_policy"],
                    )
                    self.assertEqual(
                        {
                            HELPER.STAGED_SHARED_VALIDATOR_RELATIVE.as_posix(): digest(
                                SHARED_VALIDATOR_PATH
                            ),
                            HELPER.STAGED_VALIDATOR_RELATIVE.as_posix(): digest(
                                VALIDATOR_PATH
                            ),
                        },
                        metadata["validator_sha256"],
                    )
                    self.assertNotIn(fixture.endpoint, prompt)
                    self.assertNotIn("Permitted public endpoints", prompt)
                    self.assertIn(
                        "No dynamic public endpoint is frozen into this prompt",
                        prompt,
                    )
                    self.assertIn(
                        "Judge reasonable support and admissibility, not concurrence.",
                        prompt,
                    )
                    self.assertIn(
                        "different severity, weight, emphasis, or final recommendation",
                        prompt,
                    )
                    self.assertIn(
                        "Never rewrite an honest semantic judgment merely to obtain PASS.",
                        prompt,
                    )
                    self.assertIn(
                        "`VALID-FAIL` with exit 3",
                        prompt,
                    )
                    self.assertIn(
                        "must never be promoted or used to materialize",
                        prompt,
                    )
                    self.assertEqual(
                        [str(private_md), str(private_csv)], metadata["private_outputs"]
                    )
                    opened = metadata["opened"]
                    if target == "R5":
                        expected_pages = [
                            f"page-renders/P{page:04d}.png"
                            for page in range(1, fixture.process["physical_page_count"] + 1)
                        ]
                        self.assertEqual(
                            expected_pages,
                            [item for item in opened if item.startswith("page-renders/")],
                        )
                    if target == "R4":
                        self.assertIn("04-citation-claim-audit-ledger.csv", opened)
                        self.assertFalse(any(item.startswith("page-renders/") for item in opened))
                    if target == "R1":
                        self.assertNotIn("02-page-layout-ledger.csv", opened)

                    if target == "AI":
                        self.assertNotIn("01-policy-basis.md", opened)

                    second_prompt = prompt_root / f"SA-{target}-repeat.txt"
                    repeated_metadata = self.plan_one(
                        preplan_path, view, target, second_prompt
                    )
                    self.assertEqual(first_prompt.read_bytes(), second_prompt.read_bytes())
                    self.assertEqual(
                        metadata["prompt_sha256"], repeated_metadata["prompt_sha256"]
                    )

                    overwrite = self.run_helper(
                        "plan",
                        "--process",
                        str(preplan_path),
                        "--view-root",
                        str(view),
                        "--target",
                        target,
                        "--output",
                        str(first_prompt),
                    )
                    self.assertNotEqual(0, overwrite.returncode)
                    self.assertTrue(overwrite.stdout.startswith("FAIL\n"), overwrite.stdout)
                    self.assertIn("refusing to overwrite", overwrite.stdout)

    def test_python_executable_is_required_and_must_be_the_running_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            prompt_root = base / "prompts"
            prompt_root.mkdir()
            prompt = prompt_root / "SA-R1.txt"
            view = base / "view-R1"

            missing = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(HELPER_PATH),
                    "plan",
                    "--process",
                    str(preplan),
                    "--view-root",
                    str(view),
                    "--target",
                    "R1",
                    "--output",
                    str(prompt),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=disabled_bytecode_environment(),
            )
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("--python-executable", missing.stderr)
            self.assertFalse(prompt.exists())

            fake_python = base / "not-python.exe"
            fake_python.write_text("not an interpreter", encoding="utf-8")
            fake = self.run_helper(
                "plan",
                "--process",
                str(preplan),
                "--view-root",
                str(view),
                "--target",
                "R1",
                "--output",
                str(prompt),
                "--python-executable",
                str(fake_python),
            )
            self.assertNotEqual(0, fake.returncode)
            self.assertTrue(fake.stdout.startswith("FAIL\n"), fake.stdout)
            self.assertIn("exact canonical sys.executable", fake.stdout)
            self.assertFalse(prompt.exists())

    def test_runtime_file_identity_drift_is_rejected(self) -> None:
        executable = Path(sys.executable).resolve()
        identity = HELPER.capture_file_identity(executable, "test interpreter")
        drifted = HELPER.FileIdentity(
            identity.device,
            identity.inode,
            identity.size,
            identity.mtime_ns + 1,
            identity.sha256,
        )
        with mock.patch.object(
            HELPER,
            "capture_file_identity",
            side_effect=[identity, drifted],
        ):
            with self.assertRaises(HELPER.ContractError) as caught:
                HELPER.validate_bound_python_executable(executable)
        self.assertIn("same file identity", str(caught.exception))

    def test_plan_never_reports_success_after_prompt_output_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            original_check = HELPER.require_file_identity
            replaced = False

            def replace_after_python_check(
                path: Path, expected: object, label: str
            ) -> None:
                nonlocal replaced
                original_check(path, expected, label)
                if (
                    label == "bound Python executable"
                    and prompt.exists()
                    and not replaced
                ):
                    prompt.write_bytes(b"CONCURRENTLY REPLACED PLAN OUTPUT\n")
                    replaced = True

            with mock.patch.object(
                HELPER,
                "require_file_identity",
                side_effect=replace_after_python_check,
            ):
                with self.assertRaises(HELPER.ContractError):
                    HELPER.plan_prompt(
                        preplan,
                        view,
                        "R1",
                        prompt,
                        Path(sys.executable),
                    )
            self.assertTrue(replaced)

    def test_governing_docs_preserve_nonconcurrence_and_honest_fail_lifecycle(self) -> None:
        documents = {
            name: (SKILL_ROOT / name).read_text(encoding="utf-8")
            for name in (
                "SKILL.md",
                "references/clean-room-orchestration.md",
                "references/report-template.md",
            )
        }
        for name, text in documents.items():
            with self.subTest(document=name):
                self.assertRegex(
                    text,
                    r"reasonable[- ]support/admissibility|reasonable support and admissibility",
                )
                self.assertIn("VALID-FAIL", text)
                self.assertRegex(
                    text,
                    r"must not promote|never promote|must never be promoted|"
                    r"without promotion|do not invoke `promote`",
                )
                self.assertRegex(
                    text,
                    r"must not rewrite|never rewrite|not overwrite or revise|"
                    r"never promote or rewrite",
                )

    def test_verify_rejects_process_hash_drift_prompt_drift_and_reserved_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            freeze_validator_pair(fixture)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            self.plan_one(preplan, view, "R1", prompt)
            copy_private_view(fixture, "R1", view)

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("does not equal the pre-import process commitment", result.stdout)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata["prompt_sha256"]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            (view / VALIDATOR.ACCEPTANCE_DIRECTORY).mkdir()

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn(
                "reserved round-only directory",
                result.stdout,
            )

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata["prompt_sha256"]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            prompt.write_bytes(prompt.read_bytes() + b"\nDRIFT")

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("does not equal the pre-import process commitment", result.stdout)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            drifted = json.loads(
                (view / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            drifted["institution"] = "Drifted Institution After Stage P"
            write_process(view / "00-process-parameters.json", drifted)

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("full-process SHA-256 commitment", result.stdout)

    def test_verify_rejects_joint_process_and_manifest_drift_against_external_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            drifted = json.loads(
                (view / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            drifted["institution"] = "Jointly Drifted Institution"
            write_process(view / "00-process-parameters.json", drifted)
            drifted_hash = digest(view / "00-process-parameters.json")
            manifest_path = view / "00-manifest.md"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text(
                HELPER.PROCESS_COMMITMENT_RE.sub(
                    "- Process-parameter file and SHA-256: "
                    f"00-process-parameters.json / {drifted_hash}",
                    manifest_text,
                ),
                encoding="utf-8",
            )

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
                "--expected-process-sha256",
                expected_process_hash,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("external Stage-O process SHA-256 anchor", result.stdout)

    def test_public_cli_preplan_final_process_verify_promote_set_e2e(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan-process.json"
            write_process(preplan, stable_preplan_process(fixture))
            prompt_root = base / "prompts"
            prompt_root.mkdir()
            planned: dict[str, tuple[Path, Path, dict[str, object]]] = {}
            for target in fixture.targets:
                view = base / f"view-{target}"
                prompt = prompt_root / f"SA-{target}.txt"
                metadata = self.plan_one(preplan, view, target, prompt)
                planned[target] = (view, prompt, metadata)

            for target, (_view, _prompt, metadata) in planned.items():
                fixture.process["actor_prompt_sha256"][f"SA-{target}"] = metadata[
                    "prompt_sha256"
                ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            stage_p_process_bytes = (
                round_root / "00-process-parameters.json"
            ).read_bytes()
            expected_process_hash = digest(
                round_root / "00-process-parameters.json"
            )

            for target in fixture.targets:
                view, prompt, plan_metadata = planned[target]
                copy_private_view(fixture, target, view)
                prelaunch = self.verify_one_prelaunch(
                    view, prompt, target, expected_process_hash
                )
                input_commitment = prelaunch["input_commitment"]["sha256"]
                fixture.write_acceptance(target, view)
                verify = self.run_helper(
                    "verify",
                    "--view-root",
                    str(view),
                    "--prompt",
                    str(prompt),
                    "--target",
                    target,
                    "--expected-input-commitment-sha256",
                    input_commitment,
                    "--require-sa-outputs",
                )
                self.assertEqual(0, verify.returncode, verify.stdout + verify.stderr)
                self.assertTrue(verify.stdout.startswith("VERIFIED\n"), verify.stdout)
                verify_metadata = json.loads(verify.stdout.splitlines()[1])
                self.assertEqual("complete", verify_metadata["sa_output_state"])
                self.assertEqual(
                    plan_metadata["prompt_sha256"], verify_metadata["prompt_sha256"]
                )
                result = self.run_helper(
                    "promote",
                    "--view-root",
                    str(view),
                    "--round-root",
                    str(round_root),
                    "--prompt",
                    str(prompt),
                    "--target",
                    target,
                    "--expected-input-commitment-sha256",
                    input_commitment,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertTrue(result.stdout.startswith("PROMOTED\n"), result.stdout)
                metadata = json.loads(result.stdout.splitlines()[1])
                self.assertEqual("PROMOTED", metadata["status"])
                for suffix in ("md", "csv"):
                    source = view / f"SA-{target}.{suffix}"
                    destination = (
                        round_root
                        / VALIDATOR.ACCEPTANCE_DIRECTORY
                        / f"SA-{target}.{suffix}"
                    )
                    self.assertEqual(source.read_bytes(), destination.read_bytes())
                    self.assertEqual(digest(source), digest(destination))
                self.assertEqual(
                    stage_p_process_bytes,
                    (round_root / "00-process-parameters.json").read_bytes(),
                )
                self.assertEqual(
                    stage_p_process_bytes,
                    (view / "00-process-parameters.json").read_bytes(),
                )

            self.assertFalse(
                any(
                    VALIDATOR.ROUND_ROOT_ACTOR_OUTPUT_RE.fullmatch(path.name)
                    for path in round_root.iterdir()
                )
            )
            set_result = self.run_validator(str(round_root), "--set")
            self.assertEqual(
                0, set_result.returncode, set_result.stdout + set_result.stderr
            )
            self.assertTrue(set_result.stdout.startswith("PASS\n"), set_result.stdout)
            acceptance_names = {
                path.name
                for path in (round_root / VALIDATOR.ACCEPTANCE_DIRECTORY).iterdir()
            }
            self.assertEqual(
                {
                    f"SA-{target}.{suffix}"
                    for target in fixture.targets
                    for suffix in ("md", "csv")
                },
                acceptance_names,
            )

            for path in base.rglob("*"):
                self.assertNotEqual("__pycache__", path.name)
                self.assertNotEqual(".pyc", path.suffix)

    def test_staged_verify_is_independent_of_live_skill_validator_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            drift_tools = base / "live-drift-tools"
            drift_tools.mkdir()
            copied_helper = drift_tools / HELPER_PATH.name
            shutil.copy2(HELPER_PATH, copied_helper)
            (drift_tools / VALIDATOR_PATH.name).write_text(
                "raise RuntimeError('live checkout validator must not be imported')\n",
                encoding="utf-8",
            )
            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
                helper_path=copied_helper,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("VERIFIED\n"), result.stdout)
            verification = json.loads(result.stdout.splitlines()[1])
            self.assertEqual("absent", verification["sa_output_state"])

    @unittest.skipUnless(os.name == "nt", "Windows namespace contract")
    def test_sa_control_paths_reject_administrative_and_nested_unc_namespaces(self) -> None:
        for value in (
            r"\\localhost\C$\audit\round\private-view-R1",
            r"\\localhost\NestedShare\private-view-R1",
            r"\\?\C:\audit\round\private-view-R1",
        ):
            with self.subTest(path=value):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.resolved(Path(value), must_exist=False)
                self.assertIn("UNC/device namespace", str(caught.exception))

        with self.assertRaises(HELPER.ContractError) as caught:
            HELPER.resolved(Path(r"C:\audit\private-view-R1:prompt"), must_exist=False)
        self.assertIn("alternate data stream", str(caught.exception))

    def test_file_identity_rejects_hardlink_created_after_path_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "target.txt"
            alias = base / "alias.txt"
            target.write_text("frozen bytes", encoding="utf-8")
            original_open = Path.open

            def link_before_open(path: Path, *args: object, **kwargs: object):
                if path == target and not alias.exists():
                    os.link(target, alias)
                return original_open(path, *args, **kwargs)

            with mock.patch.object(Path, "open", new=link_before_open):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.capture_file_identity(target, "race target")
            self.assertIn("single-link regular file", str(caught.exception))

    def test_file_identity_rejects_hardlink_created_during_final_stream_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "target.txt"
            alias = base / "alias.txt"
            target.write_text("frozen bytes", encoding="utf-8")
            original_stream_check = HELPER.require_no_windows_named_streams
            calls = 0

            def link_during_second_check(path: Path, label: str) -> None:
                nonlocal calls
                calls += 1
                original_stream_check(path, label)
                if calls == 2:
                    os.link(target, alias)

            with mock.patch.object(
                HELPER,
                "require_no_windows_named_streams",
                side_effect=link_during_second_check,
            ):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.capture_file_identity(target, "race target")
            self.assertIn("multiply linked", str(caught.exception))

    def test_prelaunch_verify_rejects_hardlinked_view_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            relative = Path("R1-comprehensive-review.md")
            view_target = view / relative
            view_target.unlink()
            os.link(round_root / relative, view_target)

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("single-link regular file", result.stdout)

    @unittest.skipUnless(os.name == "nt", "NTFS named-stream contract")
    def test_prelaunch_verify_rejects_named_stream_on_allowlisted_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            target = view / "R1-comprehensive-review.md"
            Path(f"{target}:prior-review").write_text(
                "PROHIBITED OLD REVIEW", encoding="utf-8"
            )
            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("NTFS named streams", result.stdout)

    def test_promote_rejects_joint_view_and_round_drift_from_prelaunch_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            prelaunch = self.verify_one_prelaunch(
                view, prompt, "R1", expected_process_hash
            )
            prelaunch_anchor = prelaunch["input_commitment"]["sha256"]

            relative = Path("R1-comprehensive-review.md")
            changed = (view / relative).read_bytes() + b"\nJOINT POST-LAUNCH DRIFT\n"
            (view / relative).write_bytes(changed)
            (round_root / relative).write_bytes(changed)
            fixture.write_acceptance("R1", view)

            result = self.run_helper(
                "promote",
                "--view-root",
                str(view),
                "--round-root",
                str(round_root),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
                "--expected-process-sha256",
                expected_process_hash,
                "--expected-input-commitment-sha256",
                prelaunch_anchor,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("prelaunch commitment", result.stdout)
            self.assertFalse(
                (round_root / VALIDATOR.ACCEPTANCE_DIRECTORY).exists()
            )

    def test_first_verify_rejects_late_anchor_after_actor_outputs_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            fixture.write_acceptance("R1", view)

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
            self.assertIn("before dispatch", result.stdout)
            self.assertIn("post-dispatch input baseline", result.stdout)

    def test_prelaunch_verify_rechecks_terminal_closed_view_topology(self) -> None:
        contamination_kinds = ["file", "directory", "output-pair"]
        if os.name == "nt":
            contamination_kinds.append("named-stream")
        for contamination_kind in contamination_kinds:
            with self.subTest(contamination=contamination_kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                round_root = base / "round"
                round_root.mkdir()
                fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
                preplan = base / "preplan.json"
                write_process(preplan, stable_preplan_process(fixture))
                view = base / "view-R1"
                prompt = base / "prompts" / "SA-R1.txt"
                prompt.parent.mkdir()
                metadata = self.plan_one(preplan, view, "R1", prompt)
                fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                    "prompt_sha256"
                ]
                write_process(
                    round_root / "00-process-parameters.json", fixture.process
                )
                expected_process_hash = digest(
                    round_root / "00-process-parameters.json"
                )
                freeze_validator_pair(fixture)
                copy_private_view(fixture, "R1", view)

                original_capture = HELPER.capture_opened_input_commitment
                calls = 0

                def contaminate_before_terminal_topology(*args: object, **kwargs: object):
                    nonlocal calls
                    calls += 1
                    result = original_capture(*args, **kwargs)
                    if calls == 2:
                        if contamination_kind == "file":
                            (view / "PROHIBITED-OLD-REVIEW.md").write_text(
                                "old review", encoding="utf-8"
                            )
                        elif contamination_kind == "directory":
                            (view / "PROHIBITED-CONTEXT").mkdir()
                        elif contamination_kind == "output-pair":
                            (view / "SA-R1.md").write_text("late", encoding="utf-8")
                            (view / "SA-R1.csv").write_text("late", encoding="utf-8")
                        else:
                            target = view / "R1-comprehensive-review.md"
                            Path(f"{target}:old-review").write_text(
                                "old review", encoding="utf-8"
                            )
                    return result

                with mock.patch.object(
                    HELPER,
                    "capture_opened_input_commitment",
                    side_effect=contaminate_before_terminal_topology,
                ):
                    with self.assertRaises(HELPER.ContractError):
                        HELPER.verify_prompt(
                            view,
                            prompt,
                            "R1",
                            expected_process_hash,
                            Path(sys.executable),
                        )

    def test_verify_rejects_external_prompt_replacement_during_final_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            original_capture = HELPER.capture_opened_input_commitment
            calls = 0

            def replace_prompt_during_final_checks(*args: object, **kwargs: object):
                nonlocal calls
                calls += 1
                result = original_capture(*args, **kwargs)
                if calls == 2:
                    prompt.write_bytes(b"CONCURRENTLY REPLACED PROMPT\n")
                return result

            with mock.patch.object(
                HELPER,
                "capture_opened_input_commitment",
                side_effect=replace_prompt_during_final_checks,
            ):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.verify_prompt(
                        view,
                        prompt,
                        "R1",
                        expected_process_hash,
                        Path(sys.executable),
                    )
            self.assertIn("planned SA prompt", str(caught.exception))

    def test_verify_rechecks_inputs_after_terminal_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            original_topology = HELPER.validate_closed_view
            calls = 0

            def drift_during_terminal_topology(*args: object, **kwargs: object):
                nonlocal calls
                calls += 1
                result = original_topology(*args, **kwargs)
                if calls == 2:
                    target = view / "R1-comprehensive-review.md"
                    before = target.stat()
                    value = bytearray(target.read_bytes())
                    value[0] = (value[0] + 1) % 256
                    target.write_bytes(bytes(value))
                    os.utime(
                        target,
                        ns=(before.st_atime_ns, before.st_mtime_ns),
                    )
                return result

            with mock.patch.object(
                HELPER,
                "validate_closed_view",
                side_effect=drift_during_terminal_topology,
            ):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.verify_prompt(
                        view,
                        prompt,
                        "R1",
                        expected_process_hash,
                        Path(sys.executable),
                    )
            self.assertIn("terminal prompt verification", str(caught.exception))

    def test_verify_final_closure_rejects_drift_after_second_python_check(self) -> None:
        for drift_kind in ("extra-file", "input-hardlink"):
            with self.subTest(drift=drift_kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                round_root = base / "round"
                round_root.mkdir()
                fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
                preplan = base / "preplan.json"
                write_process(preplan, stable_preplan_process(fixture))
                view = base / "view-R1"
                prompt = base / "prompts" / "SA-R1.txt"
                prompt.parent.mkdir()
                metadata = self.plan_one(preplan, view, "R1", prompt)
                fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                    "prompt_sha256"
                ]
                write_process(round_root / "00-process-parameters.json", fixture.process)
                expected_process_hash = digest(
                    round_root / "00-process-parameters.json"
                )
                freeze_validator_pair(fixture)
                copy_private_view(fixture, "R1", view)

                original_check = HELPER.require_file_identity
                python_checks = 0

                def inject_after_second_python(
                    path: Path,
                    expected: object,
                    label: str,
                ) -> None:
                    nonlocal python_checks
                    original_check(path, expected, label)
                    if label == "bound Python executable":
                        python_checks += 1
                        if python_checks == 2:
                            if drift_kind == "extra-file":
                                (view / "PROHIBITED-LATE-TOPOLOGY.md").write_text(
                                    "late unrelated artifact\n", encoding="utf-8"
                                )
                            else:
                                os.link(
                                    view / "R1-comprehensive-review.md",
                                    base / "late-view-input-hardlink.md",
                                )

                with mock.patch.object(
                    HELPER,
                    "require_file_identity",
                    side_effect=inject_after_second_python,
                ):
                    with self.assertRaisesRegex(
                        HELPER.ContractError,
                        "topology mismatch|single-link",
                    ):
                        HELPER.verify_prompt(
                            view,
                            prompt,
                            "R1",
                            expected_process_hash,
                            Path(sys.executable),
                        )
                self.assertGreaterEqual(python_checks, 2)

    def test_promote_requires_external_prelaunch_input_commitment(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(HELPER_PATH),
                "promote",
                "--view-root",
                str(Path.cwd()),
                "--round-root",
                str(Path.cwd()),
                "--prompt",
                str(HELPER_PATH),
                "--target",
                "R1",
                "--expected-process-sha256",
                "0" * 64,
                "--python-executable",
                sys.executable,
            ],
            text=True,
            capture_output=True,
            check=False,
            env=disabled_bytecode_environment(),
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--expected-input-commitment-sha256", result.stderr)

    def test_verify_authenticates_staged_validator_pair_before_import(self) -> None:
        for replaced_name in (
            VALIDATOR_PATH.name,
            SHARED_VALIDATOR_PATH.name,
        ):
            with self.subTest(replaced_validator=replaced_name), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                round_root = base / "round"
                round_root.mkdir()
                fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
                preplan = base / "preplan.json"
                write_process(preplan, stable_preplan_process(fixture))
                view = base / "view-R1"
                prompt = base / "prompts" / "SA-R1.txt"
                prompt.parent.mkdir()
                metadata = self.plan_one(preplan, view, "R1", prompt)
                fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                    "prompt_sha256"
                ]
                write_process(
                    round_root / "00-process-parameters.json", fixture.process
                )
                freeze_validator_pair(fixture)
                copy_private_view(fixture, "R1", view)
                staged = view / "rules" / "scripts" / replaced_name
                staged.write_bytes(staged.read_bytes() + b"\n# staged drift\n")

                result = self.run_helper(
                    "verify",
                    "--view-root",
                    str(view),
                    "--prompt",
                    str(prompt),
                    "--target",
                    "R1",
                )
                self.assertNotEqual(0, result.returncode)
                self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
                self.assertIn("frozen prompt commitment", result.stdout)

    def test_prompt_hash_is_authenticated_before_staged_validator_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            marker = base / "MALICIOUS-IMPORT-MARKER"
            staged = view / "rules" / "scripts" / VALIDATOR_PATH.name
            staged.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            old_hash = metadata["validator_sha256"][
                HELPER.STAGED_VALIDATOR_RELATIVE.as_posix()
            ]
            prompt.write_text(
                prompt.read_text(encoding="utf-8").replace(
                    str(old_hash), digest(staged)
                ),
                encoding="utf-8",
            )

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("pre-import process commitment", result.stdout)
            self.assertFalse(marker.exists(), result.stdout + result.stderr)

    def test_closed_view_is_checked_before_any_pyc_can_execute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)

            marker = base / "PYC-EXECUTION-MARKER"
            staged = view / "rules" / "scripts" / VALIDATOR_PATH.name
            canonical_source = staged.read_bytes()
            staged.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            cache_path = Path(importlib.util.cache_from_source(str(staged)))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            py_compile.compile(
                str(staged),
                cfile=str(cache_path),
                doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            )
            staged.write_bytes(canonical_source)

            result = self.run_helper(
                "verify",
                "--view-root",
                str(view),
                "--prompt",
                str(prompt),
                "--target",
                "R1",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("topology mismatch", result.stdout)
            self.assertFalse(marker.exists(), result.stdout + result.stderr)

    def test_pair_rollback_preserves_destination_replaced_after_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source_root = base / "source"
            destination_root = base / "destination"
            source_root.mkdir()
            destination_root.mkdir()
            first_source = source_root / "SA-R1.md"
            second_source = source_root / "SA-R1.csv"
            first_source.write_bytes(b"actor-owned first output")
            second_source.write_bytes(b"actor-owned second output")
            first_destination = destination_root / first_source.name
            second_destination = destination_root / second_source.name
            external_replacement = b"concurrently installed external object"
            original_open = Path.open

            def replace_before_second_create(
                path: Path, *args: object, **kwargs: object
            ):
                mode = args[0] if args else kwargs.get("mode", "r")
                if path == second_destination and mode == "x+b":
                    first_destination.unlink()
                    with original_open(first_destination, "wb") as handle:
                        handle.write(external_replacement)
                    raise OSError("simulated second-file creation failure")
                return original_open(path, *args, **kwargs)

            with mock.patch.object(Path, "open", new=replace_before_second_create):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.copy_pair_exclusively(
                        (first_source, second_source),
                        (first_destination, second_destination),
                    )

            self.assertIn("rollback failed closed", str(caught.exception))
            self.assertIn("preserv", str(caught.exception))
            self.assertEqual(external_replacement, first_destination.read_bytes())
            self.assertFalse(second_destination.exists())

    @unittest.skipUnless(os.name == "nt", "by-handle rollback is Windows-specific")
    def test_file_rollback_preserves_replacement_installed_after_handle_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "owned.txt"
            target.write_bytes(b"invocation-owned bytes")
            expected = HELPER.capture_file_identity(target, "owned output")
            renamed_owned = base / "renamed-owned.txt"
            replacement = b"concurrent external replacement"
            original_identity = HELPER.file_identity_from_open_handle
            injected = False

            def replace_after_handle_identity(*args: object, **kwargs: object):
                nonlocal injected
                result = original_identity(*args, **kwargs)
                if not injected:
                    injected = True
                    target.replace(renamed_owned)
                    target.write_bytes(replacement)
                return result

            with mock.patch.object(
                HELPER,
                "file_identity_from_open_handle",
                side_effect=replace_after_handle_identity,
            ):
                removed = HELPER.unlink_created_file_if_unchanged(
                    target, expected, "owned output"
                )

            self.assertTrue(removed)
            self.assertTrue(injected)
            self.assertEqual(replacement, target.read_bytes())
            self.assertFalse(renamed_owned.exists())

    @unittest.skipUnless(os.name == "nt", "by-handle rollback is Windows-specific")
    def test_directory_rollback_preserves_replacement_after_handle_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "owned-directory"
            target.mkdir()
            expected = HELPER.capture_directory_identity(target, "owned directory")
            renamed_owned = base / "renamed-owned-directory"
            original_identity = HELPER.directory_identity_from_open_descriptor
            injected = False

            def replace_after_handle_identity(*args: object, **kwargs: object):
                nonlocal injected
                result = original_identity(*args, **kwargs)
                if not injected:
                    injected = True
                    target.replace(renamed_owned)
                    target.mkdir()
                    (target / "external-marker.txt").write_text(
                        "concurrent external directory", encoding="utf-8"
                    )
                return result

            with mock.patch.object(
                HELPER,
                "directory_identity_from_open_descriptor",
                side_effect=replace_after_handle_identity,
            ):
                removed = HELPER.rmdir_created_directory_if_unchanged(
                    target, expected, "owned directory"
                )

            self.assertTrue(removed)
            self.assertTrue(injected)
            self.assertTrue((target / "external-marker.txt").is_file())
            self.assertFalse(renamed_owned.exists())

    def test_promote_rejects_sa_output_replaced_after_scoped_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            prelaunch, _context = HELPER.verify_prompt(
                view,
                prompt,
                "R1",
                expected_process_hash,
                Path(sys.executable),
            )
            input_commitment = prelaunch["input_commitment"]["sha256"]
            fixture.write_acceptance("R1", view)

            original_compare = HELPER.compare_view_and_round_inputs

            def replace_after_pass(*args: object, **kwargs: object):
                snapshots = original_compare(*args, **kwargs)
                source = view / "SA-R1.md"
                source.unlink()
                source.write_text("INVALID AFTER PASS", encoding="utf-8")
                return snapshots

            with mock.patch.object(
                HELPER,
                "compare_view_and_round_inputs",
                side_effect=replace_after_pass,
            ):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.promote(
                        view,
                        round_root,
                        prompt,
                        "R1",
                        expected_process_hash,
                        input_commitment,
                        Path(sys.executable),
                    )

            self.assertIn("replaced or changed", str(caught.exception))
            destination = round_root / VALIDATOR.ACCEPTANCE_DIRECTORY / "SA-R1.md"
            self.assertFalse(destination.exists())

    def test_post_copy_input_drift_rolls_back_owned_outputs_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            prelaunch = self.verify_one_prelaunch(
                view, prompt, "R1", expected_process_hash
            )
            input_commitment = prelaunch["input_commitment"]["sha256"]
            fixture.write_acceptance("R1", view)

            original_check = HELPER.require_unchanged_view_and_round_inputs
            calls = 0

            def drift_after_copy(*args: object, **kwargs: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    target = view / "R1-comprehensive-review.md"
                    target.write_bytes(target.read_bytes() + b"\nPOST-COPY DRIFT\n")
                original_check(*args, **kwargs)

            with mock.patch.object(
                HELPER,
                "require_unchanged_view_and_round_inputs",
                side_effect=drift_after_copy,
            ):
                with self.assertRaises(HELPER.ContractError):
                    HELPER.promote(
                        view,
                        round_root,
                        prompt,
                        "R1",
                        expected_process_hash,
                        input_commitment,
                        Path(sys.executable),
                    )

            acceptance_dir = round_root / VALIDATOR.ACCEPTANCE_DIRECTORY
            self.assertFalse(acceptance_dir.exists())
            self.assertFalse((round_root / "SA-R1.md").exists())
            self.assertFalse((round_root / "SA-R1.csv").exists())

    def test_post_copy_destination_replacement_is_never_reported_as_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            prelaunch = self.verify_one_prelaunch(
                view, prompt, "R1", expected_process_hash
            )
            input_commitment = prelaunch["input_commitment"]["sha256"]
            fixture.write_acceptance("R1", view)

            original_commitment_check = HELPER.require_opened_input_commitment
            calls = 0
            replacement = b"CONCURRENT EXTERNAL REPLACEMENT"

            def replace_after_copy(*args: object, **kwargs: object):
                nonlocal calls
                calls += 1
                if calls == 3:
                    destination = (
                        round_root
                        / VALIDATOR.ACCEPTANCE_DIRECTORY
                        / "SA-R1.md"
                    )
                    destination.unlink()
                    destination.write_bytes(replacement)
                return original_commitment_check(*args, **kwargs)

            with mock.patch.object(
                HELPER,
                "require_opened_input_commitment",
                side_effect=replace_after_copy,
            ):
                with self.assertRaises(HELPER.ContractError) as caught:
                    HELPER.promote(
                        view,
                        round_root,
                        prompt,
                        "R1",
                        expected_process_hash,
                        input_commitment,
                        Path(sys.executable),
                    )

            self.assertIn("rollback failed closed", str(caught.exception))
            destination = (
                round_root / VALIDATOR.ACCEPTANCE_DIRECTORY / "SA-R1.md"
            )
            self.assertEqual(replacement, destination.read_bytes())

    def test_post_copy_private_view_contamination_fails_and_rolls_back(self) -> None:
        contamination_kinds = ["file", "directory"]
        if os.name == "nt":
            contamination_kinds.append("named-stream")
        for contamination_kind in contamination_kinds:
            with self.subTest(contamination=contamination_kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                round_root = base / "round"
                round_root.mkdir()
                fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
                preplan = base / "preplan.json"
                write_process(preplan, stable_preplan_process(fixture))
                view = base / "view-R1"
                prompt = base / "prompts" / "SA-R1.txt"
                prompt.parent.mkdir()
                metadata = self.plan_one(preplan, view, "R1", prompt)
                fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                    "prompt_sha256"
                ]
                write_process(
                    round_root / "00-process-parameters.json", fixture.process
                )
                expected_process_hash = digest(
                    round_root / "00-process-parameters.json"
                )
                freeze_validator_pair(fixture)
                copy_private_view(fixture, "R1", view)
                prelaunch = self.verify_one_prelaunch(
                    view, prompt, "R1", expected_process_hash
                )
                input_commitment = prelaunch["input_commitment"]["sha256"]
                fixture.write_acceptance("R1", view)

                original_commitment_check = HELPER.require_opened_input_commitment
                calls = 0

                def contaminate_after_copy(*args: object, **kwargs: object):
                    nonlocal calls
                    calls += 1
                    if calls == 3:
                        if contamination_kind == "file":
                            (view / "PROHIBITED-OLD-REVIEW.md").write_text(
                                "old review", encoding="utf-8"
                            )
                        elif contamination_kind == "directory":
                            (view / "PROHIBITED-CONTEXT").mkdir()
                        else:
                            target = view / "R1-comprehensive-review.md"
                            Path(f"{target}:old-review").write_text(
                                "old review", encoding="utf-8"
                            )
                    return original_commitment_check(*args, **kwargs)

                with mock.patch.object(
                    HELPER,
                    "require_opened_input_commitment",
                    side_effect=contaminate_after_copy,
                ):
                    with self.assertRaises(HELPER.ContractError):
                        HELPER.promote(
                            view,
                            round_root,
                            prompt,
                            "R1",
                            expected_process_hash,
                            input_commitment,
                            Path(sys.executable),
                        )

                self.assertFalse(
                    (round_root / VALIDATOR.ACCEPTANCE_DIRECTORY).exists()
                )

    def test_promote_final_closure_rejects_drift_after_fourth_input_check(self) -> None:
        for drift_kind in ("view-extra-file", "destination-hardlink"):
            with self.subTest(drift=drift_kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                round_root = base / "round"
                round_root.mkdir()
                fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
                preplan = base / "preplan.json"
                write_process(preplan, stable_preplan_process(fixture))
                view = base / "view-R1"
                prompt = base / "prompts" / "SA-R1.txt"
                prompt.parent.mkdir()
                metadata = self.plan_one(preplan, view, "R1", prompt)
                fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                    "prompt_sha256"
                ]
                write_process(round_root / "00-process-parameters.json", fixture.process)
                expected_process_hash = digest(
                    round_root / "00-process-parameters.json"
                )
                freeze_validator_pair(fixture)
                copy_private_view(fixture, "R1", view)
                prelaunch = self.verify_one_prelaunch(
                    view, prompt, "R1", expected_process_hash
                )
                input_commitment = prelaunch["input_commitment"]["sha256"]
                fixture.write_acceptance("R1", view)

                original_check = HELPER.require_opened_input_commitment
                calls = 0

                def inject_after_fourth_input(*args: object, **kwargs: object):
                    nonlocal calls
                    result = original_check(*args, **kwargs)
                    calls += 1
                    if calls == 4:
                        if drift_kind == "view-extra-file":
                            (view / "PROHIBITED-LATE-TOPOLOGY.md").write_text(
                                "late unrelated artifact\n", encoding="utf-8"
                            )
                        else:
                            destination = (
                                round_root
                                / VALIDATOR.ACCEPTANCE_DIRECTORY
                                / "SA-R1.md"
                            )
                            os.link(destination, base / "late-promoted-hardlink.md")
                    return result

                with mock.patch.object(
                    HELPER,
                    "require_opened_input_commitment",
                    side_effect=inject_after_fourth_input,
                ):
                    with self.assertRaises(HELPER.ContractError):
                        HELPER.promote(
                            view,
                            round_root,
                            prompt,
                            "R1",
                            expected_process_hash,
                            input_commitment,
                            Path(sys.executable),
                        )

                self.assertGreaterEqual(calls, 4)
                self.assertFalse(
                    (round_root / VALIDATOR.ACCEPTANCE_DIRECTORY).exists()
                )

    def test_promote_rechecks_round_input_and_prompt_after_final_round_state(self) -> None:
        for drift_kind in ("round-input", "prompt"):
            with self.subTest(drift=drift_kind), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                round_root = base / "round"
                round_root.mkdir()
                fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
                preplan = base / "preplan.json"
                write_process(preplan, stable_preplan_process(fixture))
                view = base / "view-R1"
                prompt = base / "prompts" / "SA-R1.txt"
                prompt.parent.mkdir()
                metadata = self.plan_one(preplan, view, "R1", prompt)
                fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                    "prompt_sha256"
                ]
                write_process(
                    round_root / "00-process-parameters.json", fixture.process
                )
                expected_process_hash = digest(
                    round_root / "00-process-parameters.json"
                )
                freeze_validator_pair(fixture)
                copy_private_view(fixture, "R1", view)
                prelaunch = self.verify_one_prelaunch(
                    view, prompt, "R1", expected_process_hash
                )
                input_commitment = prelaunch["input_commitment"]["sha256"]
                fixture.write_acceptance("R1", view)

                original_round_check = HELPER.require_round_promotion_state
                calls = 0

                def drift_after_final_round_check(*args: object, **kwargs: object):
                    nonlocal calls
                    calls += 1
                    result = original_round_check(*args, **kwargs)
                    if calls == 2:
                        if drift_kind == "round-input":
                            target = round_root / "R1-comprehensive-review.md"
                            target.write_bytes(target.read_bytes() + b"\nLATE DRIFT\n")
                        else:
                            prompt.write_bytes(b"LATE PROMPT DRIFT\n")
                    return result

                with mock.patch.object(
                    HELPER,
                    "require_round_promotion_state",
                    side_effect=drift_after_final_round_check,
                ):
                    with self.assertRaises(HELPER.ContractError):
                        HELPER.promote(
                            view,
                            round_root,
                            prompt,
                            "R1",
                            expected_process_hash,
                            input_commitment,
                            Path(sys.executable),
                        )

                self.assertFalse(
                    (round_root / VALIDATOR.ACCEPTANCE_DIRECTORY).exists()
                )

    def test_promote_rejects_valid_fail_pair_without_any_destination_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            round_root = base / "round"
            round_root.mkdir()
            fixture = SEMANTIC_TEST.SemanticAcceptanceFixture(round_root)
            preplan = base / "preplan.json"
            write_process(preplan, stable_preplan_process(fixture))
            view = base / "view-R1"
            prompt = base / "prompts" / "SA-R1.txt"
            prompt.parent.mkdir()
            metadata = self.plan_one(preplan, view, "R1", prompt)
            fixture.process["actor_prompt_sha256"]["SA-R1"] = metadata[
                "prompt_sha256"
            ]
            write_process(round_root / "00-process-parameters.json", fixture.process)
            expected_process_hash = digest(round_root / "00-process-parameters.json")
            freeze_validator_pair(fixture)
            copy_private_view(fixture, "R1", view)
            prelaunch, _context = HELPER.verify_prompt(
                view,
                prompt,
                "R1",
                expected_process_hash,
                Path(sys.executable),
            )
            input_commitment = prelaunch["input_commitment"]["sha256"]
            fixture.write_acceptance("R1", view)

            csv_path = view / "SA-R1.csv"
            rows = SEMANTIC_TEST.MODULE.read_csv_rows(csv_path, [])
            rows[0]["AcceptanceDisposition"] = "fail"
            SEMANTIC_TEST.write_csv(csv_path, SEMANTIC_TEST.MODULE.CSV_COLUMNS, rows)
            markdown_path = view / "SA-R1.md"
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8")
                .replace("Overall semantic acceptance: PASS", "Overall semantic acceptance: FAIL")
                .replace("Acceptance failure count: 0", "Acceptance failure count: 1"),
                encoding="utf-8",
            )

            errors, result = SEMANTIC_TEST.MODULE.validate_actor(
                view,
                "R1",
                SEMANTIC_TEST.SHARED,
                enforce_closed_view=True,
            )
            self.assertEqual([], errors)
            self.assertEqual("FAIL", result["status"])
            acceptance_dir = round_root / VALIDATOR.ACCEPTANCE_DIRECTORY
            self.assertFalse(acceptance_dir.exists())
            with self.assertRaises(HELPER.ContractError) as caught:
                HELPER.promote(
                    view,
                    round_root,
                    prompt,
                    "R1",
                    expected_process_hash,
                    input_commitment,
                    Path(sys.executable),
                )
            self.assertIn("status is not PASS", str(caught.exception))
            self.assertFalse(acceptance_dir.exists())
            self.assertFalse((round_root / "SA-R1.md").exists())
            self.assertFalse((round_root / "SA-R1.csv").exists())


if __name__ == "__main__":
    unittest.main()
