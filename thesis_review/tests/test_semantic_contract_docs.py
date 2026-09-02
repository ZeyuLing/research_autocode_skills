from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_semantic_acceptance_output.py"
REVIEWER_PROMPT_HELPER = SKILL_ROOT / "scripts" / "build_reviewer_prompt.py"
SA_PROMPT_HELPER = SKILL_ROOT / "scripts" / "build_semantic_acceptance_prompt.py"
CANONICAL_PROMPT_HELPER = SKILL_ROOT / "scripts" / "build_canonical_actor_prompt.py"
ACTOR_CONTRACT_HELPER = SKILL_ROOT / "scripts" / "actor_prompt_contract.py"
TRANSPORT_VALIDATOR = SKILL_ROOT / "scripts" / "validate_actor_transport.py"
SKILL_DOC = SKILL_ROOT / "SKILL.md"
REPORT_TEMPLATE = SKILL_ROOT / "references" / "report-template.md"
LEDGER_VALIDATION = SKILL_ROOT / "references" / "ledger-validation.md"
CLEAN_ROOM = SKILL_ROOT / "references" / "clean-room-orchestration.md"
REVIEWER_PANELS = SKILL_ROOT / "references" / "reviewer-panels.md"


def literal_constant(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing literal constant {name} in {path}")


def canonical_json_after(text: str, marker: str) -> tuple[str, dict[str, object]]:
    marker_offset = text.find(marker)
    if marker_offset < 0:
        raise AssertionError(f"missing canonical schema marker: {marker}")
    match = re.search(r"```json\s*\n([^\n]+)\n```", text[marker_offset:])
    if match is None:
        raise AssertionError(f"missing one-line canonical JSON after: {marker}")
    raw = match.group(1)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise AssertionError(f"canonical JSON after {marker} must be an object")
    return raw, parsed


def cli_argument_flags(source: str, parser_name: str) -> tuple[str, ...]:
    pattern = re.compile(
        rf'{re.escape(parser_name)}\.add_argument\(\s*"(--[a-z0-9-]+)"',
        flags=re.DOTALL,
    )
    return tuple(pattern.findall(source))


class SemanticContractDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.finding_keys = tuple(
            literal_constant(VALIDATOR_PATH, "FINDING_SEMANTIC_BASIS_LABELS")
        )
        cls.gate_keys = tuple(
            literal_constant(VALIDATOR_PATH, "GATE_SEMANTIC_BASIS_LABELS")
        )
        cls.question_keys = tuple(
            literal_constant(VALIDATOR_PATH, "QUESTION_SEMANTIC_BASIS_LABELS")
        )
        cls.standard = literal_constant(VALIDATOR_PATH, "REASONABLE_SUPPORT_STANDARD")
        cls.supported = literal_constant(VALIDATOR_PATH, "REASONABLY_SUPPORTED")
        cls.common_sa_inputs = tuple(
            literal_constant(VALIDATOR_PATH, "COMMON_SA_RULE_INPUTS")
        )
        cls.docs = {
            "report-template.md": REPORT_TEMPLATE.read_text(encoding="utf-8"),
            "ledger-validation.md": LEDGER_VALIDATION.read_text(encoding="utf-8"),
        }

    def schema_objects(self, text: str) -> dict[str, tuple[str, dict[str, object]]]:
        return {
            "finding": canonical_json_after(text, "For a passing `finding` row"),
            "gate": canonical_json_after(
                text, "For a passing ordinary-reviewer `gate` row"
            ),
            "question": canonical_json_after(
                text, "For a passing ordinary-reviewer `question` row"
            ),
        }

    def test_normative_sa_documents_are_in_common_allowlist(self) -> None:
        for basename in self.docs:
            self.assertIn(basename, self.common_sa_inputs)

    def test_finding_gate_and_question_contracts_match_production(self) -> None:
        markers = (
            "For a passing `finding` row",
            "For a passing ordinary-reviewer `gate` row",
            "For a passing ordinary-reviewer `question` row",
        )
        common_declarations: dict[str, str] = {}
        for basename in self.common_sa_inputs:
            if basename == "SKILL.md":
                path = SKILL_ROOT / basename
            elif basename.endswith(".md"):
                path = SKILL_ROOT / "references" / basename
            else:
                continue
            text = path.read_text(encoding="utf-8")
            present = tuple(marker in text for marker in markers)
            if any(present):
                self.assertTrue(
                    all(present),
                    f"{basename} declares only part of the three canonical SA schemas",
                )
                common_declarations[basename] = text
        self.assertEqual(set(common_declarations), set(self.docs))
        parsed_by_doc = {
            basename: self.schema_objects(text)
            for basename, text in common_declarations.items()
        }
        for basename, schemas in parsed_by_doc.items():
            with self.subTest(document=basename, unit="finding"):
                finding = schemas["finding"][1]
                self.assertEqual(tuple(finding), self.finding_keys)
                self.assertEqual(finding["assessment_standard"], self.standard)
                self.assertEqual(finding["admissibility_result"], self.supported)
                self.assertEqual(
                    tuple(finding["whole_pdf_resolution"]),
                    ("status", "pages", "search_concepts", "detail"),
                )
                self.assertEqual(
                    tuple(finding["residual_gap"]), ("status", "detail")
                )
                self.assertEqual(
                    finding["residual_gap"]["status"], self.supported
                )
                self.assertEqual(
                    tuple(finding["action_delta"]),
                    ("status", "detail", "independent_reason"),
                )
            with self.subTest(document=basename, unit="gate"):
                gate = schemas["gate"][1]
                self.assertEqual(tuple(gate), self.gate_keys)
                self.assertEqual(gate["assessment_standard"], self.standard)
                self.assertEqual(gate["admissibility_result"], self.supported)
                self.assertEqual(
                    tuple(gate["independent_pdf_assessment"]),
                    (
                        "supporting_pdf_evidence",
                        "counterevidence_reviewed",
                        "admissibility_reason",
                    ),
                )
                self.assertRegex(gate["target_disposition"], r"(?:^|\|)n/a(?:\s|>|$)")
                self.assertIn("N/A projects to n/a", gate["target_disposition"])
                self.assertIn(
                    "`n/a` with an empty related-ID array",
                    self.docs[basename],
                )
            with self.subTest(document=basename, unit="question"):
                question = schemas["question"][1]
                self.assertEqual(tuple(question), self.question_keys)
                self.assertEqual(question["assessment_standard"], self.standard)
                self.assertEqual(question["admissibility_result"], self.supported)
                self.assertEqual(
                    tuple(question["whole_pdf_resolution"]),
                    ("status", "pages", "search_concepts", "detail"),
                )

        report_schemas = parsed_by_doc["report-template.md"]
        ledger_schemas = parsed_by_doc["ledger-validation.md"]
        for unit in ("finding", "gate", "question"):
            with self.subTest(normative_parity=unit):
                self.assertEqual(report_schemas[unit][0], ledger_schemas[unit][0])

    def test_common_sa_rules_do_not_declare_legacy_finding_contract(self) -> None:
        local_rule_texts: list[tuple[str, str]] = []
        for basename in self.common_sa_inputs:
            if basename == "SKILL.md":
                path = SKILL_ROOT / basename
            elif basename.endswith(".md"):
                path = SKILL_ROOT / "references" / basename
            else:
                continue
            local_rule_texts.append((basename, path.read_text(encoding="utf-8")))

        stale_patterns = (
            r"exact ordered (?:outer )?keys `premise_class`, `target_premise`",
            r'"residual_gap":\{"status":"present"',
        )
        for basename, text in local_rule_texts:
            for pattern in stale_patterns:
                with self.subTest(document=basename, pattern=pattern):
                    self.assertIsNone(re.search(pattern, text))

    def test_operational_prompt_only_clause_allows_generic_contracts(self) -> None:
        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        panels = REVIEWER_PANELS.read_text(encoding="utf-8")
        self.assertIn("canonical generic", clean_room)
        self.assertIn("validator/materializer commitments and commands", clean_room)
        self.assertIn("actor-private scratch", clean_room)
        self.assertRegex(
            clean_room,
            r"never a\s+thesis-specific assertion supplied by Stage O",
        )
        self.assertIn("canonical thesis-agnostic review checklists", panels)
        self.assertRegex(panels, r"exact\s+pre-freeze commands")
        self.assertIn("actor-private scratch", panels)
        self.assertIn("thesis-specific assertion", panels)

    def test_bound_actor_launch_is_not_redelegated(self) -> None:
        skill = SKILL_DOC.read_text(encoding="utf-8")
        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        panels = REVIEWER_PANELS.read_text(encoding="utf-8")
        ai_style = (SKILL_ROOT / "references" / "ai-style-audit.md").read_text(
            encoding="utf-8"
        )
        reviewer_helper = REVIEWER_PROMPT_HELPER.read_text(encoding="utf-8")
        sa_helper = SA_PROMPT_HELPER.read_text(encoding="utf-8")
        general_helper = CANONICAL_PROMPT_HELPER.read_text(encoding="utf-8")
        actor_contract = ACTOR_CONTRACT_HELPER.read_text(encoding="utf-8")
        transport_validator = TRANSPORT_VALIDATOR.read_text(encoding="utf-8")
        optional_global_flags = tuple(
            literal_constant(TRANSPORT_VALIDATOR, "OPTIONAL_GLOBAL_FLAGS")
        )
        required_exec_flags = tuple(
            literal_constant(TRANSPORT_VALIDATOR, "REQUIRED_EXEC_FLAGS")
        )
        optional_exec_flags = tuple(
            literal_constant(TRANSPORT_VALIDATOR, "OPTIONAL_EXEC_FLAGS")
        )
        disable_forms = tuple(
            literal_constant(TRANSPORT_VALIDATOR, "MULTI_AGENT_DISABLE_FORMS")
        )

        for name, text in (
            ("SKILL.md", skill),
            ("clean-room-orchestration.md", clean_room),
        ):
            with self.subTest(document=name):
                self.assertIn("The launched process itself", text)
                self.assertIn("actor_prompt_contract.py", text)
                self.assertIn("derived instructions", text)
                self.assertIn("--disable multi_agent", text)
                self.assertIn("validate_actor_transport.py", text)

        self.assertNotIn('use `fork_turns: "none"`', panels)
        self.assertNotIn("Before freezing the report, launch the assessor", panels)
        self.assertIn("no reviewer or assessor may perform that launch", panels)
        self.assertNotIn('use `fork_turns: "none"`', ai_style)
        self.assertIn("Stage O has already launched", ai_style)

        self.assertIn("Stage O has already launched this exact process", actor_contract)
        self.assertIn("This process itself is the process-bound actor.", actor_contract)
        self.assertIn("Perform the assigned role yourself", actor_contract)
        for api_name in (
            "spawn_agent",
            "wait_agent",
            "list_agents",
            "create_thread",
            "read_thread",
            "list_threads",
            "send_message_to_thread",
            "share_thread",
            "wait_threads",
        ):
            self.assertIn(api_name, actor_contract)

        for name, source in (
            ("build_reviewer_prompt.py", reviewer_helper),
            ("build_semantic_acceptance_prompt.py", sa_helper),
            ("build_canonical_actor_prompt.py", general_helper),
        ):
            with self.subTest(helper=name):
                self.assertIn("from actor_prompt_contract import", source)
                self.assertIn("render_bound_actor_contract", source)
                self.assertNotIn(
                    "Stage O has already launched this exact process as the fresh",
                    source,
                )
                self.assertNotIn(
                    "Start in a fresh empty task context with fork_turns=none.",
                    source,
                )

        self.assertIn("collab_tool_call", transport_validator)
        self.assertIn("COLLAB_TOOL_NAMES", transport_validator)
        self.assertIn("exactly one thread.started", transport_validator)
        self.assertIn("exactly one turn.started", transport_validator)
        self.assertIn("exactly one successful turn.completed", transport_validator)
        self.assertIn("--launch-record", transport_validator)
        self.assertIn("--expected-prompt-sha256", transport_validator)
        self.assertIn("--expected-launch-id", transport_validator)
        self.assertIn("nested Codex/model process", transport_validator)

        for name, text in (
            ("SKILL.md", skill),
            ("clean-room-orchestration.md", clean_room),
        ):
            with self.subTest(transport_document=name):
                self.assertIn("thesis-review-actor-launch-v3", text)
                self.assertIn("--ephemeral", text)
                self.assertIn("--ignore-user-config", text)
                self.assertIn("--ignore-rules", text)
                self.assertIn("--expected-prompt-sha256", text)
                self.assertIn("--expected-launch-id", text)
                self.assertIn("exit code", text)
                self.assertRegex(text, r"closed\s+grammar")
                self.assertIn("No other flag", text)
                self.assertIn("not an independent operating-system", text)
                for token in (
                    *optional_global_flags,
                    *required_exec_flags,
                    *optional_exec_flags,
                    *disable_forms,
                ):
                    self.assertIn(token, text)

        self.assertIn("build_canonical_actor_prompt.py", skill)
        self.assertIn("build_canonical_actor_prompt.py plan", clean_room)
        self.assertIn("build_canonical_actor_prompt.py verify", clean_room)
        self.assertIn("--scratch-dir", clean_room)
        self.assertNotIn("--expected-body-sha256", skill)
        self.assertNotIn("--expected-body-sha256", clean_room)
        self.assertIn("WebSocket", skill)
        self.assertIn("WebSocket", clean_room)

    def test_actor_visible_rules_do_not_reintroduce_orchestratorless_launches(self) -> None:
        documents = [SKILL_DOC, *sorted((SKILL_ROOT / "references").glob("*.md"))]
        forbidden_fragments = (
            "Stage SA launches one independent semantic acceptor",
            "Inventory extraction may be delegated",
            "before the Chair is launched, start one different",
            "follow `clean-room-orchestration.md` and start each ledger owner",
            "Use a new empty-context process for Stage P",
            "Before freezing the report, launch the assessor",
            "the chair starts in the fresh Stage-C context",
            "Run a fresh isolated AI-style assessment",
            "Run one additional isolated prose-style assessment",
            "Run Stage S in another fresh context",
            "Run this as Stage S in a new context",
            "### 3. Run independent reviewers",
            "In addition, run the standalone AI-style assessor",
            "### 7. Run independent semantic acceptance before Chair",
            "Create a new, uniquely named and identity-neutral round directory",
            "Give every concurrent actor exact input paths",
            "After the chair freezes its outputs, run the separate clean Stage-S",
            "After prose edits, run the assessor again",
        )
        for path in documents:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                with self.subTest(document=path.name, fragment=fragment):
                    self.assertNotIn(fragment, text)

        panels = REVIEWER_PANELS.read_text(encoding="utf-8")
        citation = (SKILL_ROOT / "references" / "citation-audit.md").read_text(
            encoding="utf-8"
        )
        grading = (
            SKILL_ROOT / "references" / "grading-and-verdicts.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Stage O starts every reviewer", panels)
        self.assertIn("must not launch, message, fork, hand off, or", panels)
        self.assertIn("otherwise delegate to another actor or task", panels)
        self.assertIn("Production runner v1 rejects Stage-H actors", panels)
        self.assertIn("Stage O starts each ledger owner", citation)
        self.assertIn("Stage O starts the chair", grading)

    def test_stage_r_production_cli_is_helper_free_and_tracks_public_cli(self) -> None:
        helper_source = REVIEWER_PROMPT_HELPER.read_text(encoding="utf-8")
        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        panels = REVIEWER_PANELS.read_text(encoding="utf-8")
        skill = SKILL_DOC.read_text(encoding="utf-8")

        plan_flags = cli_argument_flags(helper_source, "plan_parser")
        verify_flags = cli_argument_flags(helper_source, "verify_parser")
        self.assertTrue(plan_flags)
        self.assertTrue(verify_flags)

        # The low-level builder retains the historical flag only as dormant
        # compatibility surface.  Runner v1 is the production authority and
        # its documented command deliberately omits that flag.
        production_plan_flags = set(plan_flags) - {"--helper-input"}
        production_verify_flags = set(verify_flags) - {"--helper-input"}

        plan_command = re.search(
            r'```text\n("<absolute-bundled-python>" -B '
            r'scripts/build_reviewer_prompt\.py plan [^\n]+)\n```',
            clean_room,
        )
        verify_command = re.search(
            r'```text\n("<absolute-bundled-python>" -B '
            r'scripts/build_reviewer_prompt\.py verify [^\n]+)\n```',
            clean_room,
        )
        self.assertIsNotNone(plan_command)
        self.assertIsNotNone(verify_command)
        for flag in production_plan_flags:
            with self.subTest(command="plan", flag=flag):
                self.assertIn(flag, plan_command.group(1))
        for flag in production_verify_flags:
            with self.subTest(command="verify", flag=flag):
                self.assertIn(flag, verify_command.group(1))
        self.assertNotIn("--helper-input", plan_command.group(1))
        self.assertNotIn("--helper-input", verify_command.group(1))

        for required in (
            "Production runner v1 requires the no-helper plan above exactly",
            "rejects every",
            "`--helper-input` argument or `helpers/` path",
            "same Python path and scratch path",
            "snapshots the canonical and",
            "staged final-round",
            "validate_stage_p_output.py",
            "still-empty actor scratch as working",
            "PYTHONDONTWRITEBYTECODE=1",
        ):
            with self.subTest(clean_room_helper_contract=required):
                self.assertIn(required, clean_room)
        for required in (
            "Production runner v1 rejects Stage-H actors",
            "helper paths, and every",
            "`--helper-input` argument",
            "Production runner v1 launches no helper",
        ):
            with self.subTest(panel_helper_contract=required):
                self.assertIn(required, panels)
        for flag in production_plan_flags | production_verify_flags:
            with self.subTest(skill_public_cli=flag):
                self.assertIn(flag, skill)
        self.assertIn("rejects any", skill)
        self.assertIn("`--helper-input` arguments", skill)

    def test_sa_runtime_binding_documentation_tracks_public_cli(self) -> None:
        helper_source = SA_PROMPT_HELPER.read_text(encoding="utf-8")
        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        report = REPORT_TEMPLATE.read_text(encoding="utf-8")
        skill = SKILL_DOC.read_text(encoding="utf-8")

        for parser_name, command in (
            ("plan_parser", "plan"),
            ("verify_parser", "verify"),
            ("promote_parser", "promote"),
        ):
            flags = cli_argument_flags(helper_source, parser_name)
            self.assertIn("--python-executable", flags)
            command_match = re.search(
                rf'^"<absolute-bundled-python>" -B '
                rf'scripts/build_semantic_acceptance_prompt\.py {command} ([^\n]+)$',
                clean_room,
                flags=re.MULTILINE,
            )
            self.assertIsNotNone(command_match)
            for flag in flags:
                with self.subTest(command=command, flag=flag):
                    self.assertIn(flag, command_match.group(1))

        combined = "\n".join((clean_room, report, skill))
        for required in (
            "exact canonical `sys.executable`",
            "WindowsApps alias",
            "runtime drift",
            "exact JSON argument vector",
            '`{"PYTHONDONTWRITEBYTECODE":"1"}`',
            "without a shell",
        ):
            with self.subTest(sa_runtime_contract=required):
                self.assertIn(required, combined)

        self.assertIn("Bound Python executable", helper_source)
        self.assertIn("Bound Python SHA-256", helper_source)
        self.assertNotIn("\npython -B ", report)

    def test_chair_materializer_is_helper_free_and_unc_policy_is_documented(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                SKILL_DOC,
                CLEAN_ROOM,
                LEDGER_VALIDATION,
                REPORT_TEMPLATE,
                REVIEWER_PANELS,
            )
        )
        # A dormant parser compatibility branch, if retained, cannot authorize
        # a production helper and is intentionally not part of this contract.
        for required in (
            "materialize_owner_outputs.py <exact-stage-c-view-root> C`",
            "Production runner v1 supplies no helper flags or helper files",
            "Production runner v1 rejects H actors",
            "`helpers/`, and `--helper-input`",
        ):
            with self.subTest(chair_helper_contract=required):
                self.assertIn(required, combined)
        self.assertNotIn(
            "materialize_owner_outputs.py <exact-stage-c-view-root> C [--helper-input",
            combined,
        )

        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        for required in (
            "canonical local drive-letter spelling",
            "administrative-share",
            "device-",
            "hardlink",
            "NTFS 8.3",
            "named-stream",
            "arbitrary nested share",
            "complete metadata-only round topology",
        ):
            with self.subTest(stage_r_unc_contract=required):
                self.assertIn(required, clean_room)

    def test_runner_owns_bootstrap_staging_phase_barriers_and_offline_p(self) -> None:
        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        for required in (
            "Do not stage Stage-P rule",
            "bootstrap transaction first proves the untouched pre-Stage-P topology",
            "stages",
            "the exact rule inputs itself",
            "Stage P is forbidden until",
            "`BOOTSTRAP_COMMIT`",
            "Per-actor transition commands are not exposed by the production",
            "CLI, and the reducer rejects them for every multi-actor phase",
            "P, AI, SA, C, and S use `[none]`",
            "A nonempty `governing_rule_urls` array is process metadata",
            "Public-network access, conversation history",
        ):
            with self.subTest(runner_contract=required):
                self.assertIn(required, clean_room)
        self.assertNotIn(
            "After staging the exact\nStage-P rule inputs",
            clean_room,
        )
        self.assertNotIn(
            "allowlisted official public rule sources or frozen official local",
            clean_room,
        )


if __name__ == "__main__":
    unittest.main()
