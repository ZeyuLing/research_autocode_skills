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
OWNER_MATERIALIZER = SKILL_ROOT / "scripts" / "materialize_owner_outputs.py"
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

    def test_stage_r_cli_and_helper_freeze_documentation_tracks_public_cli(self) -> None:
        helper_source = REVIEWER_PROMPT_HELPER.read_text(encoding="utf-8")
        clean_room = CLEAN_ROOM.read_text(encoding="utf-8")
        panels = REVIEWER_PANELS.read_text(encoding="utf-8")
        skill = SKILL_DOC.read_text(encoding="utf-8")

        plan_flags = cli_argument_flags(helper_source, "plan_parser")
        verify_flags = cli_argument_flags(helper_source, "verify_parser")
        self.assertTrue(plan_flags)
        self.assertTrue(verify_flags)
        self.assertIn("--helper-input", plan_flags)
        self.assertIn("--helper-input", verify_flags)

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
        for flag in plan_flags:
            with self.subTest(command="plan", flag=flag):
                self.assertIn(flag, plan_command.group(1))
        for flag in verify_flags:
            with self.subTest(command="verify", flag=flag):
                self.assertIn(flag, verify_command.group(1))

        for required in (
            "repeat it once for every",
            "Hxx-provenance.json",
            "followed immediately by that provenance record's output",
            "Before the process seal, freeze every",
            "same Python path, scratch path, and repeated",
            "actual frozen recipient-helper projection",
            "snapshots the canonical and staged",
            "validate_stage_p_output.py",
            "still-empty actor scratch as working",
            "PYTHONDONTWRITEBYTECODE=1",
        ):
            with self.subTest(clean_room_helper_contract=required):
                self.assertIn(required, clean_room)
        for required in (
            "every `--helper-input` is a separate",
            "The sequence is frozen",
            "followed immediately by that record's outputs",
            "Plan and verify receive the same repeated sequence",
        ):
            with self.subTest(panel_helper_contract=required):
                self.assertIn(required, panels)
        for flag in set(plan_flags) | set(verify_flags):
            with self.subTest(skill_public_cli=flag):
                self.assertIn(flag, skill)

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

    def test_chair_helper_materializer_cli_and_unc_policy_are_documented(self) -> None:
        materializer_source = OWNER_MATERIALIZER.read_text(encoding="utf-8")
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
        self.assertIn('"--helper-input"', materializer_source)
        for required in (
            "materialize_owner_outputs.py <exact-round-root> C [--helper-input",
            "exact C-recipient",
            "canonical Hxx",
            "never discovers",
            "single-link regular files",
        ):
            with self.subTest(chair_helper_contract=required):
                self.assertIn(required, combined)

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


if __name__ == "__main__":
    unittest.main()
