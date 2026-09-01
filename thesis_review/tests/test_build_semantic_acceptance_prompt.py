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
                    self.assertIn(
                        f'python -B "{view.resolve() / "rules" / "scripts" / "validate_semantic_acceptance_output.py"}" '
                        f'"{view.resolve()}" "{target}"',
                        prompt,
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

            for target in fixture.targets:
                view, prompt, plan_metadata = planned[target]
                copy_private_view(fixture, target, view)
                fixture.write_acceptance(target, view)
                verify = self.run_helper(
                    "verify",
                    "--view-root",
                    str(view),
                    "--prompt",
                    str(prompt),
                    "--target",
                    target,
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
            fixture.write_acceptance("R1", view)

            original_compare = HELPER.compare_view_and_round_inputs

            def replace_after_pass(*args: object, **kwargs: object) -> None:
                original_compare(*args, **kwargs)
                source = view / "SA-R1.md"
                source.unlink()
                source.write_text("INVALID AFTER PASS", encoding="utf-8")

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
                    )

            self.assertIn("replaced or changed", str(caught.exception))
            destination = round_root / VALIDATOR.ACCEPTANCE_DIRECTORY / "SA-R1.md"
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
