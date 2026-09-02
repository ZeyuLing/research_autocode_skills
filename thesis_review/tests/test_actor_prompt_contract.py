from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = SKILL_ROOT / "scripts" / "actor_prompt_contract.py"
BUILDER_PATHS = (
    SKILL_ROOT / "scripts" / "build_reviewer_prompt.py",
    SKILL_ROOT / "scripts" / "build_semantic_acceptance_prompt.py",
    SKILL_ROOT / "scripts" / "build_bound_actor_prompt.py",
)
SPEC = importlib.util.spec_from_file_location("actor_prompt_contract", CONTRACT_PATH)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


# Independent expected capability list.  Never derive this from production.
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


class ActorPromptContractTests(unittest.TestCase):
    def test_canonical_forbidden_api_set_matches_independent_expectation(self) -> None:
        self.assertEqual(EXPECTED_FORBIDDEN_APIS, CONTRACT.FORBIDDEN_ACTOR_TOOL_NAMES)

    def test_every_role_uses_one_actor_substitution_in_same_contract(self) -> None:
        for actor in (
            "P",
            "H01",
            "H99",
            "R1",
            "R5",
            "AI",
            "SA-R1",
            "SA-R5",
            "SA-AI",
            "C",
            "S",
            "V",
        ):
            with self.subTest(actor=actor):
                rendered = CONTRACT.render_bound_actor_contract(actor)
                self.assertEqual(1, rendered.count(CONTRACT.CONTRACT_BEGIN))
                self.assertEqual(1, rendered.count(CONTRACT.CONTRACT_END))
                self.assertEqual(
                    1,
                    rendered.count(
                        "Stage O has already launched this exact process as the fresh "
                        f"empty-context {actor} actor."
                    ),
                )
                for api in EXPECTED_FORBIDDEN_APIS:
                    self.assertIn(api, rendered)
                self.assertNotIn("fork_turns", rendered)

    def test_all_three_production_builders_import_canonical_renderer(self) -> None:
        for path in BUILDER_PATHS:
            with self.subTest(builder=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("from actor_prompt_contract import", source)
                self.assertIn("render_bound_actor_contract", source)
                self.assertNotIn(
                    "Stage O has already launched this exact process as the fresh",
                    source,
                )

    def test_ambiguous_multilingual_role_control_is_rejected(self) -> None:
        rejected = (
            "Launch another actor to do the analysis.",
            "Start another actor.",
            "Have a subagent complete the role.",
            "Use another model to complete the task.",
            "Call wait_agent before writing the report.",
            "Use mcp__codex_app__read_thread for context.",
            "Delegate this review.",
            "Relay the packet.",
            "请创建子代理完成任务。",
            "让另一个模型完成分析。",
            "把工作转交给其他智能体。",
            "Run a fresh isolated AI-style assessment.",
            "Run Stage S in another fresh context.",
            "R2 is responsible for the review.",
            "Request R2 to review the PDF.",
            "Assign this review to R2.",
            "Consult another reviewer.",
            "Create a task.",
            "Open another thread.",
            "Use another model.",
            "R2会完成审稿。",
            "请R2给意见。",
            "另开一个任务。",
            "借助Qwen复核。",
            "请另一位\n审稿人完成。",
            "另开一个\n任务继续。",
        )
        for value in rejected:
            with self.subTest(value=value):
                self.assertIsNotNone(CONTRACT.find_role_body_control_language(value))


if __name__ == "__main__":
    unittest.main()
