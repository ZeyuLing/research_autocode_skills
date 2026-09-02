from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import os
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "launch_review_actor.py"
SPEC = importlib.util.spec_from_file_location("launch_review_actor", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PROCESS_SHA256 = "A" * 64
PROCESS_SEAL_SHA256 = "B" * 64
INPUT_COMMITMENT_SHA256 = "C" * 64
OUTPUT_COMMITMENT_SHA256 = "D" * 64


def make_actor_workspace(base: Path, actor: str = "P") -> Path:
    run = base / "run-v1"
    (run / "round").mkdir(parents=True)
    (run / "orchestration").mkdir()
    workspace = run / "views" / actor
    workspace.mkdir(parents=True)
    return workspace


def clean_events(thread_id: str) -> bytes:
    events = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "item_1", "type": "agent_message", "text": "done"},
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_output_tokens": 0,
            },
        },
    ]
    return ("\n".join(json.dumps(item) for item in events) + "\n").encode("utf-8")


class CaptureStdin:
    def __init__(self, before_first_write=None) -> None:
        self.value = bytearray()
        self.closed = False
        self.before_first_write = before_first_write

    def write(self, value: bytes) -> int:
        if not self.value and self.before_first_write is not None:
            self.before_first_write()
        self.value.extend(value)
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(
        self,
        stdout: io.BufferedIOBase,
        log: bytes,
        before_stdin=None,
        on_wait=None,
    ) -> None:
        self.pid = 4242
        self.stdin = CaptureStdin(before_stdin)
        self._returncode: int | None = None
        self._on_wait = on_wait
        stdout.write(log)
        stdout.flush()

    def wait(self) -> int:
        if self._on_wait is not None:
            self._on_wait()
        self._returncode = 0
        return 0

    def poll(self) -> int | None:
        return self._returncode

    def kill(self) -> None:
        self._returncode = -9


class LaunchReviewActorTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "deny-write lease is Windows-specific")
    def test_windows_input_lease_blocks_swap_or_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "input.pdf"
            target.write_bytes(b"frozen")
            leases = MODULE.acquire_read_leases([target])
            try:
                with self.assertRaises(OSError):
                    target.write_bytes(b"contaminated")
                with self.assertRaises(OSError):
                    target.unlink()
                self.assertEqual(b"frozen", target.read_bytes())
            finally:
                MODULE.release_read_leases(leases)
            target.write_bytes(b"released")
            self.assertEqual(b"released", target.read_bytes())

    def test_build_argv_matches_closed_transport_grammar(self) -> None:
        executable = Path("C:/tools/codex.exe")
        workspace = Path("C:/review/round")
        argv = MODULE.build_argv(
            executable, workspace, search=True
        )
        self.assertEqual(argv[0], str(executable))
        self.assertEqual(argv[1:3], ["--search", "exec"])
        self.assertEqual(argv[-1], "-")
        self.assertEqual(argv.count("--disable"), 1)
        self.assertEqual(argv.count("multi_agent"), 1)
        self.assertEqual(argv.count("--sandbox"), 1)
        self.assertIn("workspace-write", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertNotIn("--model", argv)

    def test_launch_fixes_record_before_stdin_and_passes_real_transport_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base)
            scratch = base / "actor-scratch"
            control = base / "control"
            scratch.mkdir()
            control.mkdir()
            prompt = control / "P.prompt.txt"
            prompt_bytes = b"bounded prompt bytes\n"
            prompt.write_bytes(prompt_bytes)
            executable = control / ("codex.exe" if __import__("os").name == "nt" else "codex")
            executable.write_bytes(b"not executed because Popen is mocked")
            jsonl = control / "P.jsonl"
            stderr = control / "P.stderr"
            record = control / "P.launch.json"
            thread_id = "00000000-0000-4000-8000-000000000001"
            captured: dict[str, object] = {}
            real_popen = MODULE.subprocess.Popen

            def assert_pending_record() -> None:
                self.assertTrue(record.is_file())
                pending = json.loads(record.read_text(encoding="utf-8"))
                self.assertEqual(pending["pid"], 4242)
                self.assertEqual(pending["exit_code"], MODULE.SENTINEL_EXIT)
                self.assertEqual(pending["log_bytes"], 0)
                self.assertEqual(pending["log_sha256"], MODULE.ZERO_HASH)
                self.assertEqual(pending["thread_id"], "")

            def fake_popen(argv: list[str], **kwargs: object):
                # ``subprocess.run`` used by the real transport validator also
                # calls the module-global Popen.  Delegate that second launch
                # to the genuine implementation and mock only codex itself.
                if Path(argv[0]) != executable:
                    return real_popen(argv, **kwargs)
                captured["argv"] = argv
                process = FakeProcess(
                    kwargs["stdout"], clean_events(thread_id), assert_pending_record
                )  # type: ignore[arg-type]
                captured["process"] = process
                return process

            args = __import__("argparse").Namespace(
                actor="P",
                launch_id="10000000-0000-4000-8000-000000000001",
                prompt=prompt,
                expected_prompt_sha256=hashlib.sha256(prompt_bytes).hexdigest(),
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=workspace,
                cwd=scratch,
                jsonl=jsonl,
                stderr=stderr,
                launch_record=record,
                codex_executable=executable,
                transport_validator=SKILL_ROOT / "scripts" / "validate_actor_transport.py",
                search=False,
                bypass_sandbox=False,
            )
            with mock.patch.object(
                MODULE,
                "preflight_actor_workspace_binding",
                return_value={"bound": True},
            ), mock.patch.object(
                MODULE, "postflight_actor_workspace_binding"
            ), mock.patch.object(
                MODULE, "acquire_actor_input_leases", return_value=("portable", [])
            ), mock.patch.object(
                MODULE, "verify_actor_input_leases"
            ), mock.patch.object(
                MODULE,
                "terminal_output_commitment",
                return_value=OUTPUT_COMMITMENT_SHA256,
            ), mock.patch.object(MODULE.subprocess, "Popen", side_effect=fake_popen):
                result = MODULE.launch(args)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["thread_id"], thread_id)
            process = captured["process"]
            self.assertIsInstance(process, FakeProcess)
            self.assertEqual(bytes(process.stdin.value), prompt_bytes)  # type: ignore[union-attr]
            self.assertTrue(process.stdin.closed)  # type: ignore[union-attr]

            launch_record = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(
                set(launch_record),
                {
                    "schema",
                    "actor",
                    "launch_id",
                    "prompt_path",
                    "prompt_bytes",
                    "prompt_sha256",
                    "process_sha256",
                    "process_seal_sha256",
                    "input_commitment_sha256",
                    "output_commitment_sha256",
                    "executable_path",
                    "executable_sha256",
                    "argv",
                    "argv_sha256",
                    "cwd",
                    "workspace",
                    "pid",
                    "exit_code",
                    "log_path",
                    "log_bytes",
                    "log_sha256",
                    "thread_id",
                },
            )
            self.assertEqual(launch_record["pid"], 4242)
            self.assertEqual(launch_record["exit_code"], 0)
            self.assertEqual(launch_record["thread_id"], thread_id)
            self.assertEqual(
                launch_record["output_commitment_sha256"],
                OUTPUT_COMMITMENT_SHA256,
            )
            self.assertEqual(
                result["launch_record_sha256"], MODULE.sha256_file(record)
            )

    def test_prompt_hash_mismatch_creates_no_launch_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base)
            scratch = base / "scratch"
            control = base / "control"
            scratch.mkdir()
            control.mkdir()
            prompt = control / "prompt.txt"
            prompt.write_text("x", encoding="utf-8")
            executable = control / ("codex.exe" if __import__("os").name == "nt" else "codex")
            executable.write_bytes(b"x")
            args = __import__("argparse").Namespace(
                actor="P",
                launch_id="10000000-0000-4000-8000-000000000002",
                prompt=prompt,
                expected_prompt_sha256="0" * 64,
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=workspace,
                cwd=scratch,
                jsonl=control / "log.jsonl",
                stderr=control / "stderr.log",
                launch_record=control / "record.json",
                codex_executable=executable,
                transport_validator=SKILL_ROOT / "scripts" / "validate_actor_transport.py",
                search=False,
                bypass_sandbox=False,
            )
            with self.assertRaisesRegex(MODULE.ContractError, "externally retained"):
                MODULE.launch(args)
            self.assertFalse(args.jsonl.exists())
            self.assertFalse(args.stderr.exists())
            self.assertFalse(args.launch_record.exists())

    def test_finalized_round_cannot_be_substituted_for_private_actor_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base)
            round_root = workspace.parents[1] / "round"
            scratch = base / "scratch"
            control = base / "control"
            scratch.mkdir()
            control.mkdir()
            prompt = control / "prompt.txt"
            prompt.write_text("x", encoding="utf-8")
            executable = control / (
                "codex.exe" if __import__("os").name == "nt" else "codex"
            )
            executable.write_bytes(b"x")
            args = __import__("argparse").Namespace(
                actor="P",
                launch_id="10000000-0000-4000-8000-000000000003",
                prompt=prompt,
                expected_prompt_sha256=hashlib.sha256(b"x").hexdigest(),
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=round_root,
                cwd=scratch,
                jsonl=control / "log.jsonl",
                stderr=control / "stderr.log",
                launch_record=control / "record.json",
                codex_executable=executable,
                transport_validator=SKILL_ROOT / "scripts" / "validate_actor_transport.py",
                search=False,
                bypass_sandbox=False,
            )
            with self.assertRaisesRegex(MODULE.ContractError, "basename must exactly match"):
                MODULE.launch(args)
            self.assertFalse(args.jsonl.exists())
            self.assertFalse(args.stderr.exists())
            self.assertFalse(args.launch_record.exists())

    def test_nonempty_private_scratch_is_rejected_before_launch_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base)
            scratch = base / "scratch"
            control = base / "control"
            scratch.mkdir()
            (scratch / "old-context.txt").write_text("forbidden", encoding="utf-8")
            control.mkdir()
            prompt = control / "prompt.txt"
            prompt.write_text("x", encoding="utf-8")
            executable = control / (
                "codex.exe" if __import__("os").name == "nt" else "codex"
            )
            executable.write_bytes(b"x")
            args = __import__("argparse").Namespace(
                actor="P",
                launch_id="10000000-0000-4000-8000-000000000004",
                prompt=prompt,
                expected_prompt_sha256=hashlib.sha256(b"x").hexdigest(),
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=workspace,
                cwd=scratch,
                jsonl=control / "log.jsonl",
                stderr=control / "stderr.log",
                launch_record=control / "record.json",
                codex_executable=executable,
                transport_validator=SKILL_ROOT / "scripts" / "validate_actor_transport.py",
                search=False,
                bypass_sandbox=False,
            )
            with self.assertRaisesRegex(MODULE.ContractError, "must be empty"):
                MODULE.launch(args)
            self.assertFalse(args.jsonl.exists())
            self.assertFalse(args.stderr.exists())
            self.assertFalse(args.launch_record.exists())

    def test_actor_scratch_residue_fails_terminal_launch_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base)
            scratch = base / "scratch"
            control = base / "control"
            scratch.mkdir()
            control.mkdir()
            prompt = control / "prompt.txt"
            prompt_bytes = b"bounded prompt bytes\n"
            prompt.write_bytes(prompt_bytes)
            executable = control / (
                "codex.exe" if __import__("os").name == "nt" else "codex"
            )
            executable.write_bytes(b"mock executable")
            thread_id = "00000000-0000-4000-8000-000000000007"
            real_popen = MODULE.subprocess.Popen

            def fake_popen(argv: list[str], **kwargs: object):
                if Path(argv[0]) != executable:
                    return real_popen(argv, **kwargs)
                return FakeProcess(
                    kwargs["stdout"],
                    clean_events(thread_id),
                    on_wait=lambda: (scratch / "actor-residue.txt").write_text(
                        "forbidden", encoding="utf-8"
                    ),
                )

            args = __import__("argparse").Namespace(
                actor="P",
                launch_id="10000000-0000-4000-8000-000000000007",
                prompt=prompt,
                expected_prompt_sha256=hashlib.sha256(prompt_bytes).hexdigest(),
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=workspace,
                cwd=scratch,
                jsonl=control / "P.jsonl",
                stderr=control / "P.stderr",
                launch_record=control / "P.launch.json",
                codex_executable=executable,
                transport_validator=SKILL_ROOT
                / "scripts"
                / "validate_actor_transport.py",
                search=False,
            )
            with mock.patch.object(
                MODULE,
                "preflight_actor_workspace_binding",
                return_value={"bound": True},
            ), mock.patch.object(
                MODULE, "postflight_actor_workspace_binding"
            ), mock.patch.object(
                MODULE, "acquire_actor_input_leases", return_value=("portable", [])
            ), mock.patch.object(
                MODULE, "verify_actor_input_leases"
            ), mock.patch.object(MODULE.subprocess, "Popen", side_effect=fake_popen):
                with self.assertRaisesRegex(
                    MODULE.ContractError, "not an exact closed file tree"
                ):
                    MODULE.launch(args)
            self.assertTrue((scratch / "actor-residue.txt").is_file())

    def test_transport_validator_cannot_be_overridden_by_pass_stub(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base)
            scratch = base / "scratch"
            control = base / "control"
            scratch.mkdir()
            control.mkdir()
            prompt = control / "prompt.txt"
            prompt.write_text("x", encoding="utf-8")
            executable = control / (
                "codex.exe" if __import__("os").name == "nt" else "codex"
            )
            executable.write_bytes(b"x")
            pass_stub = control / "fake-validator.py"
            pass_stub.write_text('print("PASS")\n', encoding="utf-8")
            args = __import__("argparse").Namespace(
                actor="P",
                launch_id="10000000-0000-4000-8000-000000000005",
                prompt=prompt,
                expected_prompt_sha256=hashlib.sha256(b"x").hexdigest(),
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=workspace,
                cwd=scratch,
                jsonl=control / "log.jsonl",
                stderr=control / "stderr.log",
                launch_record=control / "record.json",
                codex_executable=executable,
                transport_validator=pass_stub,
                search=False,
                bypass_sandbox=False,
            )
            with self.assertRaisesRegex(MODULE.ContractError, "fixed to the canonical"):
                MODULE.launch(args)
            self.assertFalse(args.jsonl.exists())
            self.assertFalse(args.stderr.exists())
            self.assertFalse(args.launch_record.exists())

    def test_no_endpoint_actor_cannot_enable_search(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = make_actor_workspace(base, "S")
            scratch = base / "scratch"
            control = base / "control"
            scratch.mkdir()
            control.mkdir()
            prompt = control / "prompt.txt"
            prompt.write_text("x", encoding="utf-8")
            executable = control / (
                "codex.exe" if __import__("os").name == "nt" else "codex"
            )
            executable.write_bytes(b"x")
            args = __import__("argparse").Namespace(
                actor="S",
                launch_id="10000000-0000-4000-8000-000000000006",
                prompt=prompt,
                expected_prompt_sha256=hashlib.sha256(b"x").hexdigest(),
                expected_process_sha256=PROCESS_SHA256,
                expected_process_seal_sha256=PROCESS_SEAL_SHA256,
                expected_input_commitment_sha256=INPUT_COMMITMENT_SHA256,
                workspace=workspace,
                cwd=scratch,
                jsonl=control / "log.jsonl",
                stderr=control / "stderr.log",
                launch_record=control / "record.json",
                codex_executable=executable,
                transport_validator=SKILL_ROOT / "scripts" / "validate_actor_transport.py",
                search=True,
                bypass_sandbox=False,
            )
            with self.assertRaisesRegex(MODULE.ContractError, "public_endpoints"):
                MODULE.launch(args)
            self.assertFalse(args.jsonl.exists())


if __name__ == "__main__":
    unittest.main()
