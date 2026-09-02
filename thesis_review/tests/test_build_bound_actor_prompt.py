from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "build_bound_actor_prompt.py"
SPEC = importlib.util.spec_from_file_location("build_bound_actor_prompt", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# Deliberately independent of the production tuple: deleting a production
# prohibition must make this test fail instead of shrinking its expectations.
EXPECTED_FORBIDDEN_APIS = (
    "spawn_agent",
    "followup_task",
    "send_message",
    "send_input",
    "resume_agent",
    "wait_agent",
    "close_agent",
    "interrupt_agent",
    "list_agents",
    "request_user_input",
    "automation_update",
    "create_sidebar_section",
    "create_thread",
    "delete_sidebar_section",
    "fork_thread",
    "get_handoff_status",
    "handoff_thread",
    "list_archived_threads",
    "list_projects",
    "list_threads",
    "move_project_to_sidebar_section",
    "move_thread_to_sidebar_section",
    "navigate_to_codex_page",
    "open_in_codex",
    "read_thread",
    "read_thread_terminal",
    "rename_sidebar_section",
    "reorder_section",
    "reorder_sidebar_projects",
    "reorder_sidebar_sections",
    "send_message_to_thread",
    "set_thread_archived",
    "set_thread_pinned",
    "set_thread_title",
    "share_thread",
    "wait_threads",
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


class BuildBoundActorPromptTests(unittest.TestCase):
    def test_every_general_actor_receives_one_closed_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            actors = (
                "P",
                *(f"H{index:02d}" for index in range(1, 100)),
                "AI",
                "C",
                "S",
                "V",
            )
            for actor in actors:
                with self.subTest(actor=actor):
                    body = base / f"{actor}.body.txt"
                    output = base / f"{actor}.prompt.txt"
                    body.write_text(
                        f"Role-specific operational instructions for {actor}.\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    metadata = MODULE.build(actor, body, output)
                    prompt = output.read_text(encoding="utf-8")
                    self.assertEqual(1, prompt.count(MODULE.CONTRACT_BEGIN))
                    self.assertEqual(1, prompt.count(MODULE.CONTRACT_END))
                    self.assertEqual(
                        1,
                        prompt.count(
                            "Stage O has already launched this exact process as the fresh "
                            f"empty-context {actor} actor."
                        ),
                    )
                    self.assertEqual(
                        1,
                        prompt.count(
                            "This process itself is the process-bound actor."
                        ),
                    )
                    for api_name in EXPECTED_FORBIDDEN_APIS:
                        self.assertIn(api_name, prompt)
                    self.assertIn(
                        "Perform the assigned role yourself in this process", prompt
                    )
                    self.assertNotIn("fork_turns", prompt)
                    self.assertEqual(digest(output.read_bytes()), metadata["prompt_sha256"])
                    self.assertEqual(actor, metadata["actor"])

    def test_reviewer_and_semantic_acceptor_cannot_bypass_dedicated_builders(self) -> None:
        for actor in ("R1", "R5", "SA-R1", "SA-AI", "H00", "H100", "ROOT"):
            with self.subTest(actor=actor):
                with self.assertRaisesRegex(MODULE.ContractError, "dedicated"):
                    MODULE.render_prompt(actor, "Role-specific instructions.\n")

    def test_body_cannot_contain_actor_control_or_conflicting_delegation_text(self) -> None:
        forbidden = (
            "use fork_turns none",
            "invoke spawn_agent",
            "call followup_task",
            "call send_message_to_thread",
            "call create_thread",
            "call fork_thread",
            "call handoff_thread",
            "delegate this review",
            "relay the instructions",
            "create a new task for analysis",
            "message another actor with the result",
            "Launch another actor to do the analysis.",
            "Start another actor.",
            "Have a subagent complete the role.",
            "Use another model to complete the task.",
            "Call wait_agent before writing the report.",
            "Please read_thread before proceeding.",
            "请创建子代理完成任务。",
            "让另一个模型完成分析。",
            "把工作交给其他智能体。",
            "Run a fresh isolated AI-style assessment.",
            "Run Stage S in another fresh context.",
            "Run another reviewer on the packet.",
            "Run an additional reviewer on the packet.",
            "Ask a reviewer to inspect the figures.",
            "Have H01 perform the rendering.",
            "Forward this analysis to a reviewer.",
            "Send this prompt to R2.",
            "Please open a new session for the audit.",
            "请另一位审稿人完成。",
            "交给R2完成。",
            "另请一个模型处理。",
            "新开一个会话继续。",
            "另起一个进程执行。",
            "Pass this prompt to R2.",
            "Hand this over to R2.",
            "Let R2 complete the review.",
            "R2 must complete the review.",
            "Use H01 for the extraction.",
            "Have P perform the packet build.",
            "Use ChatGPT to review the PDF.",
            "Ask Claude to analyze it.",
            "Open a fresh Codex task and continue there.",
            "由R2完成审稿。",
            "转由另一审稿人完成。",
            "让ChatGPT完成分析。",
            "用Claude审查全文。",
            "在新会话中继续。",
            "另起上下文完成审稿。",
            "Get a second opinion from R2.",
            "Route this prompt to R2.",
            "Have P prepare the packet.",
            "R2 is responsible for completing the analysis.",
            "R2, complete the analysis and write the report.",
            "Spin up a reviewer to check the citations.",
            "Ask a colleague to review the thesis.",
            "Seek input from a second assessor.",
            "Pass the role to a fresh process.",
            "Start a Codex process for the review.",
            "Run codex exec with this prompt.",
            "Execute claude -p with these instructions.",
            "Call the OpenAI API for a second review.",
            "Use Qwen to check the citations.",
            "Have another LLM complete the assessment.",
            "Send this prompt to another LLM.",
            "Create a task for the second review.",
            "Open task R2 and continue there.",
            "Hand it off to Claude.",
            "R2负责完成分析并写报告。",
            "转给R2继续。",
            "发给R2复核。",
            "另启一个模型做复核。",
            "再开一个会话继续审稿。",
            "换个模型完成分析。",
            "让另一个LLM完成。",
            "用Qwen检查引用。",
            "找人再看一遍。",
            "请同事复核这份报告。",
            "找独立评审给第二意见。",
            "在另开窗口里完成。",
            "单独开进程做这项工作。",
            "派给第二个评审处理。",
            "提交给外部推理服务复核。",
            "运行 codex exec 处理这个提示词。",
            "R2 is responsible for the review.",
            "R2 is responsible for reviewing the thesis.",
            "R2 will review the thesis.",
            "Request R2 to review the PDF.",
            "Assign this review to R2.",
            "Consult another reviewer.",
            "Create a task.",
            "Open another thread.",
            "Use another model.",
            "Have another model do it.",
            "R2会完成审稿。",
            "R2应当完成审稿。",
            "请R2给意见。",
            "另开一个任务。",
            "再开一个会话。",
            "借助Qwen复核。",
            "让另一个模型来做。",
            "请另一位\n审稿人完成。",
            "另开一个\n任务继续。",
            "Ask another\nreviewer to inspect the figures.",
        )
        for body in forbidden:
            with self.subTest(body=body):
                with self.assertRaisesRegex(MODULE.ContractError, "reserved"):
                    MODULE.render_prompt("P", body + "\n")

    def test_legitimate_local_role_wording_is_not_rejected(self) -> None:
        accepted = (
            "Your task is to read the frozen PDF and write the packet.\n",
            "Read the other actor reports listed in the frozen allowlist.\n",
            "Open the process envelope and verify its declared values.\n",
            "Run the local validator in this process.\n",
            "Use a local deterministic helper process.\n",
            "Use the R1 report as a frozen input.\n",
            "The model runs in a separate process during inference.\n",
            "Compare this model with another model reported in Table 4.1.\n",
            "The new model improves FID by 3 percent.\n",
            "Use the reviewer rubric to assess every chapter.\n",
            "Ask whether the model claim is supported by the cited evidence.\n",
            "Tell the reader which model limitation matters.\n",
            "Use the model results to assess the stated conclusion.\n",
            "Use the AI-style audit rules.\n",
            "Use AI-style prose indicators to assess the thesis.\n",
            "Use the C-recipient helper file.\n",
            "读取其他审稿人的报告作为冻结输入。\n",
            "由模型生成的动作作为待评估对象。\n",
            "请检查PDF中的图表。\n",
            "查看PDF第10页。\n",
            "使用模型结果评估所述结论。\n",
            "使用另一模型作为论文中的比较基线。\n",
            "列出论文中的任务定义。\n",
            "打开PDF并逐页查看。\n",
            "使用R1报告作为冻结输入。\n",
            "Your task is to read the frozen PDF and write one report.\n",
            "Read another reviewer report before consolidating the findings.\n",
            "The thesis studies multi-agent motion generation.\n",
            "Run the validation script on your own output.\n",
            "Create a report file at the exact output path.\n",
            "Verify the task definition in Chapter 2.\n",
            "List the task categories described in the thesis.\n",
            "Open the PDF and inspect every page.\n",
            "本文研究多智能体运动生成模型。\n",
            "创建审稿报告文件并写入指定路径。\n",
            "Run the AI assessor validator before freezing the output.\n",
            "Run the AI assessor's scoped validator before freezing the output.\n",
            "Run the assessor gate command shown below.\n",
            "Create files only in the actor-private scratch directory.\n",
            "Read the report.\nUse the reviewer rubric in this process.\n",
        )
        for body in accepted:
            with self.subTest(body=body):
                rendered = MODULE.render_prompt("C", body)
                self.assertTrue(rendered.endswith(body))

    def test_cli_binds_exact_bytes_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            body = base / "body.txt"
            output = base / "prompt.txt"
            body.write_text(
                "Role-specific packet-building instructions.\n",
                encoding="utf-8",
                newline="\n",
            )
            command = [
                sys.executable,
                "-B",
                str(SCRIPT),
                "--actor",
                "P",
                "--body",
                str(body),
                "--output",
                str(output),
            ]
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            first = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertTrue(first.stdout.startswith("BOUND\n"), first.stdout)
            metadata = json.loads(first.stdout.splitlines()[1])
            self.assertEqual(digest(output.read_bytes()), metadata["prompt_sha256"])

            second = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            self.assertEqual(2, second.returncode)
            self.assertIn("refusing to overwrite", second.stderr)

            verify_command = command[:]
            verify_command[3:3] = ["--mode", "verify"]
            verify_command.extend(
                [
                    "--expected-body-sha256",
                    metadata["body_sha256"],
                    "--expected-prompt-sha256",
                    metadata["prompt_sha256"],
                ]
            )
            verified = subprocess.run(
                verify_command,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            self.assertTrue(verified.stdout.startswith("VERIFIED\n"), verified.stdout)
            verified_metadata = json.loads(verified.stdout.splitlines()[1])
            self.assertEqual("verify", verified_metadata["operation"])
            self.assertEqual(metadata["prompt_sha256"], verified_metadata["prompt_sha256"])

            output.write_text(
                output.read_text(encoding="utf-8") + "tamper\n",
                encoding="utf-8",
                newline="\n",
            )
            tampered = subprocess.run(
                verify_command,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            self.assertEqual(2, tampered.returncode)
            self.assertIn("canonical reconstruction", tampered.stderr)

    def test_verify_detects_body_change_after_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            body = base / "body.txt"
            output = base / "prompt.txt"
            body.write_text("Write the packet.\n", encoding="utf-8", newline="\n")
            metadata = MODULE.build("P", body, output)
            body.write_text("Write and validate the packet.\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(MODULE.ContractError, "build-time"):
                MODULE.verify(
                    "P",
                    body,
                    output,
                    metadata["body_sha256"],
                    metadata["prompt_sha256"],
                )

    def test_verify_rejects_coordinated_body_and_prompt_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            body = base / "body.txt"
            output = base / "prompt.txt"
            body.write_text("Write the packet.\n", encoding="utf-8", newline="\n")
            metadata = MODULE.build("P", body, output)
            body.write_text(
                "Write and validate the packet.\n", encoding="utf-8", newline="\n"
            )
            output.write_text(
                MODULE.render_prompt("P", body.read_text(encoding="utf-8")),
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(MODULE.ContractError, "build-time"):
                MODULE.verify(
                    "P",
                    body,
                    output,
                    metadata["body_sha256"],
                    metadata["prompt_sha256"],
                )

    def test_body_requires_strict_utf8_lf_and_no_contract_sentinel(self) -> None:
        for body, message in (
            ("\ufeffinstructions\n", "BOM"),
            ("instructions\r\n", "LF"),
            (MODULE.CONTRACT_BEGIN + "\n", "sentinels"),
            ("   \n", "role-specific"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(MODULE.ContractError, message):
                    MODULE.render_prompt("AI", body)

    def test_control_paths_must_be_absolute_and_single_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            body = base / "body.txt"
            body.write_text("Write the packet.\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(MODULE.ContractError, "absolute"):
                MODULE.build("P", Path("relative-body.txt"), base / "prompt.txt")
            with self.assertRaisesRegex(MODULE.ContractError, "absolute"):
                MODULE.build("P", body, Path("relative-prompt.txt"))

            linked = base / "body-hardlink.txt"
            os.link(body, linked)
            with self.assertRaisesRegex(MODULE.ContractError, "single-link"):
                MODULE.build("P", body, base / "prompt-hardlink.txt")

    def test_symlinked_parent_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            actual = base / "actual"
            actual.mkdir()
            link = base / "link"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink creation is unavailable")
            body = actual / "body.txt"
            body.write_text("Write the packet.\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(MODULE.ContractError, "symlink/reparse"):
                MODULE.build("P", link / "body.txt", base / "prompt.txt")


if __name__ == "__main__":
    unittest.main()
