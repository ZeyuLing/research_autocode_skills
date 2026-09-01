from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_review_bundle.py"
SPEC = importlib.util.spec_from_file_location("thesis_review_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class SubmissionObligationPolicyTests(unittest.TestCase):
    def test_pdf_only_boundary_governs_findings_questions_and_remedies(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        rubric = (SKILL_ROOT / "references" / "review-rubric.md").read_text(
            encoding="utf-8"
        )
        panels = (SKILL_ROOT / "references" / "reviewer-panels.md").read_text(
            encoding="utf-8"
        )
        template = (SKILL_ROOT / "references" / "report-template.md").read_text(
            encoding="utf-8"
        )
        ledger = (SKILL_ROOT / "references" / "ledger-validation.md").read_text(
            encoding="utf-8"
        )

        for required in (
            "PDF-only also constrains what the review may demand",
            "immutable manifests",
            "formal submission component",
            "exact public artifact/replay",
        ):
            self.assertIn(required, skill)
        self.assertIn("rather than a request for hidden author-side proof", rubric)
        self.assertIn(
            "An epoch or checkpoint label is ordinary experimental description",
            rubric,
        )
        self.assertIn("limits proposed remedies", panels)
        self.assertIn("They must not request hidden code/commit identifiers", template)
        self.assertIn("never enters `91`", template)
        self.assertIn("direct Chair decision row with `Status=rejected`", ledger)

    def test_audit_endpoint_is_not_rendered_bibliography_url(self) -> None:
        metadata_url = "https://work.example/project"
        audit_url = "https://publisher.example/record"
        rows = [
            {
                "Field": "url",
                "RenderedValue": metadata_url,
                "CanonicalValue": metadata_url,
                "EvidenceEndpoint": audit_url,
                "EvidenceNote": "authoritative publisher record",
            }
        ]
        endpoints = VALIDATOR.bibliography_ledger_public_endpoint_sequence(rows)
        self.assertEqual(endpoints, [audit_url])
        self.assertNotIn(metadata_url, endpoints)

    def test_findings_require_whole_pdf_resolution_search(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        rubric = (SKILL_ROOT / "references" / "review-rubric.md").read_text(
            encoding="utf-8"
        )
        panels = (SKILL_ROOT / "references" / "reviewer-panels.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("search the whole frozen PDF", skill)
        self.assertIn("required substance is already present", skill)
        self.assertIn("whole-PDF resolution search", rubric)
        self.assertIn("already supplies the requested substance elsewhere", rubric)
        self.assertIn("merely restates text already present", rubric)
        self.assertIn("whole-PDF resolution search", panels)
        self.assertIn("already present in the frozen thesis", panels)

    def test_citation_rule_distinguishes_audit_and_rendered_dates(self) -> None:
        citation = (SKILL_ROOT / "references" / "citation-audit.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "`EvidenceEndpoint` and `CheckedAt` document what the auditor used",
            citation,
        )
        self.assertIn("an absent value is `legitimate N/A`", citation)
        self.assertIn("A wrong printed URL", citation)
        self.assertIn("ordinary six-question finding test", citation)


if __name__ == "__main__":
    unittest.main()
