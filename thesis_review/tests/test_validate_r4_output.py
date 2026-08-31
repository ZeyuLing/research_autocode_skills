from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


SKILL_ROOT = Path(__file__).resolve().parents[1]
R4_VALIDATOR = SKILL_ROOT / "scripts" / "validate_r4_output.py"
FULL_VALIDATOR = SKILL_ROOT / "scripts" / "validate_review_bundle.py"
EXTRA_ENDPOINT = "https://sources.example.test/attempted-redirect"


def load_full_validator():
    spec = importlib.util.spec_from_file_location(
        "test_r4_endpoint_full_validator", FULL_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load full validator for R4 endpoint tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FULL_VALIDATOR_MODULE = load_full_validator()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R4_MODULE = load_module(R4_VALIDATOR, "test_r4_scoped_module")
R5_PACKET_MODULE = load_module(
    SKILL_ROOT / "scripts" / "validate_r5_output.py",
    "test_r4_r5_packet_module",
)


class ValidateR4EndpointClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )

    def build_doctoral_bundle(self, root: Path) -> None:
        self.harness.build_bundle(root)
        self.harness.convert_bundle_to_doctorate(root)

    def rewrite_r4_access_records(
        self,
        root: Path,
        *,
        record_extra_in_04: bool,
        declare_extra_in_04: bool,
        declare_extra_in_report: bool,
        public_identifier_url: bool = False,
    ) -> None:
        process = json.loads(
            (root / "00-process-parameters.json").read_text(encoding="utf-8")
        )
        digest = str(process["selected_pdf_sha256"])
        _, citation_rows = fixture_module.read_csv(
            root / "04-citation-claim-audit-ledger.csv"
        )
        if record_extra_in_04:
            citation_rows[0]["DispositionEvidence"] = (
                FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                    citation_rows[0]["PairID"],
                    citation_rows[0]["ExactAttachedProposition"],
                )
                + "; source content states the fixture proposition in the "
                "cited scope; accessed endpoint: "
                + EXTRA_ENDPOINT
            )
        if public_identifier_url:
            citation_rows[0]["PublicIdentifier"] = citation_rows[0][
                "ContentSourceOpened"
            ]
        fixture_module.write_csv(
            root / "04-citation-claim-audit-ledger.csv",
            fixture_module.CITATION_LEDGER_COLUMNS,
            citation_rows,
        )
        _, bibliography_inventory = fixture_module.read_csv(
            root / "00-bibliography-inventory.csv"
        )
        ledger_endpoints = [fixture_module.CITATION_ENDPOINT]
        if declare_extra_in_04:
            ledger_endpoints.append(EXTRA_ENDPOINT)
        (root / "04-citation-claim-audit-ledger.md").write_text(
            "# Citation ledger\n\n"
            + self.harness.declaration(
                digest, process, "R4", ledger_endpoints
            )
            + fixture_module.markdown_table(
                fixture_module.CITATION_MARKDOWN_HEADERS,
                fixture_module.citation_markdown_rows(
                    citation_rows, bibliography_inventory
                ),
            ),
            encoding="utf-8",
        )
        if declare_extra_in_report:
            report = root / "R4-comprehensive-review.md"
            original = (
                f"public_endpoints=[{fixture_module.CITATION_ENDPOINT}]"
            )
            replacement = (
                "public_endpoints=["
                f"{fixture_module.CITATION_ENDPOINT}; {EXTRA_ENDPOINT}]"
            )
            report_text = report.read_text(encoding="utf-8")
            self.assertIn(original, report_text)
            report.write_text(
                report_text.replace(original, replacement, 1),
                encoding="utf-8",
            )

    def run_r4(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(R4_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_scope_does_not_enumerate_round_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            original_iterdir = Path.iterdir

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("R4 validator enumerated the bundle root")
                return original_iterdir(path)

            with mock.patch.object(Path, "iterdir", guarded_iterdir):
                errors = R4_MODULE.validate_r4(
                    root, FULL_VALIDATOR_MODULE, R5_PACKET_MODULE
                )
            self.assertEqual([], errors)

    def test_scoped_gate_rejects_access_attempt_as_content_locator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            _, rows = fixture_module.read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            rows[0]["Support"] = "unverifiable"
            rows[0]["MetadataStatus"] = "unverifiable"
            rows[0]["ExactSourceLocator"] = (
                "official record: source-content access attempt"
            )
            rows[0]["DispositionEvidence"] = (
                "reasoned non-finding: network error prevented source access"
            )
            fixture_module.write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                fixture_module.CITATION_LEDGER_COLUMNS,
                rows,
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn(
                "access attempt is not an exact content locator", result.stdout
            )

    def test_only_closed_access_fields_contribute_endpoints(self) -> None:
        rows = [{
            "ExactAttachedProposition": "see https://example.test/proposition",
            "PublicIdentifier": "https://example.test/identifier",
            "ContentSourceOpened": "https://example.test/content",
            "ExactSourceLocator": "fallback https://example.test/locator p.1",
            "DispositionEvidence": (
                "raw https://example.test/not-an-access-record; "
                "accessed endpoint: https://example.test/attempt"
            ),
            "PDFSHA256": "A" * 64,
        }]
        self.assertEqual(
            {
                "https://example.test/content",
                "https://example.test/attempt",
            },
            FULL_VALIDATOR_MODULE.citation_ledger_public_endpoints(rows),
        )

    def test_public_identifier_url_does_not_create_receipt_requirement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=False,
                declare_extra_in_04=False,
                declare_extra_in_report=False,
                public_identifier_url=True,
            )
            scoped = self.run_r4(root)
            self.assertEqual(0, scoped.returncode, scoped.stdout + scoped.stderr)

    def test_access_marker_requires_a_closed_end_boundary(self) -> None:
        for disposition in (
            f"accessed endpoint: {EXTRA_ENDPOINT}",
            f"note; accessed endpoint: {EXTRA_ENDPOINT}; outcome recorded",
            f"note\naccessed endpoint: {EXTRA_ENDPOINT}\noutcome recorded",
        ):
            with self.subTest(valid=disposition):
                rows = [{
                    "ContentSourceOpened": fixture_module.CITATION_ENDPOINT,
                    "DispositionEvidence": disposition,
                }]
                errors: list[str] = []
                FULL_VALIDATOR_MODULE.validate_citation_endpoint_records(
                    rows, "04-citation-claim-audit-ledger.csv", errors
                )
                self.assertEqual([], errors)
                self.assertIn(
                    EXTRA_ENDPOINT,
                    FULL_VALIDATOR_MODULE.citation_ledger_public_endpoints(rows),
                )

        rows = [{
            "ContentSourceOpened": fixture_module.CITATION_ENDPOINT,
            "DispositionEvidence": (
                f"accessed endpoint: {EXTRA_ENDPOINT} trailing prose"
            ),
        }]
        errors = []
        FULL_VALIDATOR_MODULE.validate_citation_endpoint_records(
            rows, "04-citation-claim-audit-ledger.csv", errors
        )
        self.assertTrue(
            any("every 'accessed endpoint:' marker" in error for error in errors),
            errors,
        )
        self.assertNotIn(
            EXTRA_ENDPOINT,
            FULL_VALIDATOR_MODULE.citation_ledger_public_endpoints(rows),
        )

    def test_recorded_non_content_source_endpoint_closes_in_both_gates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=True,
                declare_extra_in_04=True,
                declare_extra_in_report=True,
            )
            scoped = self.run_r4(root)
            self.assertEqual(0, scoped.returncode, scoped.stdout + scoped.stderr)
            full = self.harness.run_validator(root)
            self.assertEqual(0, full.returncode, full.stdout + full.stderr)

    def test_unrecorded_receipt_endpoint_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=False,
                declare_extra_in_04=True,
                declare_extra_in_report=True,
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("authoritative endpoint allowlist", result.stdout)

    def test_recorded_endpoint_omitted_from_receipts_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            self.rewrite_r4_access_records(
                root,
                record_extra_in_04=True,
                declare_extra_in_04=False,
                declare_extra_in_report=False,
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("omits authoritative endpoint(s)", result.stdout)
            self.assertIn(EXTRA_ENDPOINT, result.stdout)

    def test_content_endpoint_shapes_reject_known_truncations(self) -> None:
        invalid = {
            "https://openreview": "non-public host",
            "https://openaccess.thecvf.com/conte": "collection/truncated route",
            "https://openaccess.thecvf.com/content/CVPR2023/html/": (
                "collection/truncated route"
            ),
            "https://proceedings.iclr.cc/paper_files/paper/2026/hash/": (
                "collection/truncated route"
            ),
            "https://proceedings.iclr.cc/paper_files/": (
                "collection/truncated route"
            ),
            "https://proceedings.mlr": "known truncated source host",
            "https://openaccess.thecvf.com/content/CVPR2024/html/Jiang_": (
                "ends with '_'"
            ),
            "https://openreview.net/forum?id=": "non-empty id=",
        }
        for endpoint, expected in invalid.items():
            with self.subTest(endpoint=endpoint):
                reason = FULL_VALIDATOR_MODULE.complete_content_endpoint_error(
                    endpoint
                )
                self.assertIsNotNone(reason)
                self.assertIn(expected, str(reason))

        valid = (
            "https://doi.org/10.1145/3442188.3445922",
            "https://arxiv.org/abs/2507.07356",
            "https://openreview.net/forum?id=CompleteForumId123",
            "https://openaccess.thecvf.com/content/CVPR2024/html/"
            "Jiang_Complete_Paper_CVPR_2024_paper.html",
            "https://proceedings.mlr.press/v235/jiang24a.html",
            "https://neurips.cc/virtual/2025/poster/123456",
            "https://bookstore.ams.org/CBMS/92",
            "https://example.org/article?id=12345",
            "https://example.org/paper?id=abc",
        )
        for endpoint in valid:
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(
                    FULL_VALIDATOR_MODULE.complete_content_endpoint_error(endpoint)
                )

    def test_scoped_r4_mandatory_gate_allows_only_dangling_source_blanks(self) -> None:
        sentinel = RuntimeError("stop after mandatory gate")
        with mock.patch.object(
            FULL_VALIDATOR_MODULE,
            "validate_rows_mandatory",
            side_effect=sentinel,
        ) as mandatory:
            with self.assertRaisesRegex(RuntimeError, "stop after mandatory gate"):
                R4_MODULE.validate_citation_outputs(
                    FULL_VALIDATOR_MODULE, Path("."), {}, "A" * 64,
                    [], [], [], [],
                )
        self.assertEqual(
            {"ContentSourceOpened", "ExactSourceLocator"},
            mandatory.call_args.kwargs["blank_allowed"],
        )

    def test_auxiliary_full_url_cannot_repair_truncated_primary(self) -> None:
        complete_doi = "10.1109/CVPR52729.2023.01726"
        complete_url = f"https://doi.org/{complete_doi}"
        row = {
            "ReferenceID": "REF0001",
            "PublicIdentifier": complete_url,
            "ContentSourceOpened": "https://doi.org/10.1109/CVPR52729",
            "DispositionEvidence": f"accessed endpoint: {complete_url}",
        }
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_source_identity(
            [row],
            {"REF0001": {"RenderedEntry": f"Paper. DOI: {complete_doi}."}},
            "04.csv",
            errors,
        )
        self.assertTrue(
            any("ContentSourceOpened is not bound" in error for error in errors),
            errors,
        )

    def test_auxiliary_path_or_query_completion_exposes_truncated_primary(self) -> None:
        cases = (
            (
                "https://openreview.net/forum?id=dTp",
                "https://openreview.net/forum?id=dTpCompleteForumId123",
            ),
            (
                "https://example.org/papers/Qi_Humanoid_",
                "https://example.org/papers/Qi_Humanoid_Generation.pdf",
            ),
        )
        for primary, auxiliary in cases:
            with self.subTest(primary=primary):
                errors: list[str] = []
                FULL_VALIDATOR_MODULE.validate_citation_endpoint_records(
                    [{
                        "ContentSourceOpened": primary,
                        "DispositionEvidence": f"accessed endpoint: {auxiliary}",
                    }],
                    "04.csv",
                    errors,
                )
                self.assertTrue(
                    any("truncated primary laundered by auxiliary" in error for error in errors),
                    errors,
                )

        self.assertFalse(FULL_VALIDATOR_MODULE.endpoint_is_strict_completion(
            "https://example.org/papers/abc",
            "https://example.org/papers/abc/supplement",
        ))
        self.assertFalse(FULL_VALIDATOR_MODULE.endpoint_is_strict_completion(
            "https://example.org/papers/abc",
            "https://example.org/papers/abc-v2",
        ))
        self.assertFalse(FULL_VALIDATOR_MODULE.endpoint_is_strict_completion(
            "https://example.org/papers/Qi_Humanoid_Genera",
            "https://example.org/papers/Qi_Humanoid_Generation.pdf",
        ))
        self.assertFalse(FULL_VALIDATOR_MODULE.endpoint_is_strict_completion(
            "https://example.org/articles/foundationmodel",
            "https://example.org/articles/foundationmodels",
        ))
        self.assertTrue(FULL_VALIDATOR_MODULE.endpoint_is_strict_completion(
            "https://example.org/papers/Qi_Humanoid_",
            "https://example.org/papers/Qi_Humanoid_Generation.pdf",
        ))

    def test_auxiliary_endpoints_are_complete_and_marked_per_occurrence(self) -> None:
        incomplete = "https://openaccess.thecvf.com/conte"
        repeated = "https://example.org/papers/complete.html"
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_endpoint_records([{
            "ContentSourceOpened": repeated,
            "DispositionEvidence": (
                f"accessed endpoint: {incomplete}; accessed endpoint: {repeated}; "
                f"second bare copy {repeated}"
            ),
        }], "04.csv", errors)
        self.assertTrue(any("auxiliary accessed endpoint" in e for e in errors), errors)
        self.assertTrue(any("unmarked=" in e and repeated in e for e in errors), errors)

        errors = []
        FULL_VALIDATOR_MODULE.validate_bibliography_endpoint_records([{
            "EvidenceNote": f"accessed endpoint: {repeated}; duplicate {repeated}"
        }], "03.csv", errors)
        self.assertTrue(any("unmarked=" in e and repeated in e for e in errors), errors)
    def test_complete_official_html_can_bind_complete_doi(self) -> None:
        complete_doi = "10.1109/CVPR52729.2023.01726"
        public_identifier = f"https://doi.org/{complete_doi}"
        official_urls = (
            "https://openaccess.thecvf.com/content/CVPR2023/html/"
            "Jiang_Complete_Paper_CVPR_2023_paper.html",
            "https://proceedings.mlr.press/v202/jiang23a.html",
        )
        for official_url in official_urls:
            with self.subTest(official_url=official_url):
                errors: list[str] = []
                FULL_VALIDATOR_MODULE.validate_citation_source_identity(
                    [{
                        "ReferenceID": "REF0001",
                        "PublicIdentifier": public_identifier,
                        "ContentSourceOpened": official_url,
                    }],
                    {"REF0001": {"RenderedEntry": (
                        f"Paper. DOI: {complete_doi}. {official_url}"
                    )}},
                    "04.csv",
                    errors,
                )
                self.assertEqual([], errors)

    def test_occurrence_binding_and_same_window_projection(self) -> None:
        pair_id = "C0007-S01"
        proposition = "the proposed method reduces reconstruction error"
        row = {
            "PairID": pair_id,
            "ReferenceID": "REF0007",
            "Support": "direct",
            "ExactAttachedProposition": proposition,
            "ExactSourceLocator": "Section 4.2, Reconstruction Results",
            "DispositionEvidence": (
                FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                    pair_id, proposition
                )
                + f"; attached proposition: {proposition}; the ablation table "
                "reports the stated reconstruction comparison"
            ),
        }
        inventory = {
            pair_id: {"AdjacentPDFText": (
                "Under the same protocol, the proposed method reduces\n"
                "reconstruction error [7] across all test sequences."
            )}
        }
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            [row], inventory, "04.csv", errors
        )
        self.assertEqual([], errors)

        conflicting = dict(row)
        conflicting["DispositionEvidence"] = (
            FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                pair_id, proposition
            )
            + "; occurrence-specific subject: an adjacent table reports speed; "
            "the source contains a different result"
        )
        errors = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            [conflicting], inventory, "04.csv", errors
        )
        self.assertTrue(
            any("does not exactly match" in error for error in errors), errors
        )

        wrong_hash = dict(row)
        wrong_hash["DispositionEvidence"] = (
            "occurrence binding: C0007-S01@sha256=" + "0" * 64
            + "; the source reports the stated reconstruction comparison"
        )
        errors = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            [wrong_hash], inventory, "04.csv", errors
        )
        self.assertTrue(
            any("occurrence binding does not match" in error for error in errors),
            errors,
        )

    def test_repeated_locator_and_disposition_templates_fail_with_counts(self) -> None:
        rows = []
        inventory = {}
        for index in range(1, 13):
            pair_id = f"C{index:04d}-S01"
            proposition = f"claim alpha {index} improves reconstruction"
            rows.append({
                "PairID": pair_id,
                "ReferenceID": f"REF{index:04d}",
                "Support": "direct",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": (
                    f"Abstract; Section {index}.3; Figure {index}"
                ),
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                        pair_id, proposition
                    )
                    + f"; source evidence for {proposition} directly reports "
                    "the stated method and result"
                ),
            })
            inventory[pair_id] = {
                "AdjacentPDFText": f"The thesis states that {proposition} [{index}]."
            }
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            rows, inventory, "04.csv", errors
        )
        self.assertTrue(
            any(
                "repeated generic ExactSourceLocator" in error
                and "support classes=['direct']" in error
                and "distinct ReferenceID=12" in error
                and "threshold=12" in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any(
                "repeated generic DispositionEvidence" in error
                and "distinct ReferenceID=12" in error
                for error in errors
            ),
            errors,
        )

    def test_occurrence_specific_variation_passes_template_gate(self) -> None:
        words = (
            "albatross", "birch", "cobalt", "dahlia", "ember", "fjord",
            "garnet", "harbor", "indigo", "juniper", "kelp", "lilac",
        )
        rows = []
        inventory = {}
        for index, word in enumerate(words, start=1):
            pair_id = f"C{index:04d}-S01"
            proposition = f"claim beta {word} improves reconstruction"
            rows.append({
                "PairID": pair_id,
                "ReferenceID": f"REF{index:04d}",
                "Support": "direct",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": (
                    f"Section {index}.1, heading {word} analysis"
                ),
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                        pair_id, proposition
                    )
                    + f"; the {word} analysis reports {proposition} under its "
                    "named evaluation protocol"
                ),
            })
            inventory[pair_id] = {
                "AdjacentPDFText": f"The thesis states {proposition} [{index}]."
            }
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            rows, inventory, "04.csv", errors
        )
        self.assertEqual([], errors)

    def test_exact_marker_preserves_unrelated_numeric_vector(self) -> None:
        pair_id = "C0001-S01"
        proposition = "the vector [1,2] improves accuracy"
        row = {
            "PairID": pair_id, "ReferenceID": "REF0001", "Support": "direct",
            "ExactAttachedProposition": proposition, "ExactSourceLocator": "Abstract",
            "DispositionEvidence": (
                FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(pair_id, proposition)
                + "; the abstract reports this exact vector comparison"
            ),
        }
        inventory = {pair_id: {
            "PairID": pair_id, "OccurrenceID": "C0001",
            "DisplayedReferenceID": "REF0001",
            "AdjacentPDFText": "the vector [1,2] improves accuracy [1]",
        }}
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            [row], inventory, "04.csv", errors
        )
        self.assertEqual([], errors)
        wrong = dict(row, ExactAttachedProposition="the vector improves accuracy")
        wrong["DispositionEvidence"] = (
            FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                pair_id, wrong["ExactAttachedProposition"]
            ) + "; the abstract reports this vector comparison"
        )
        errors = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            [wrong], inventory, "04.csv", errors
        )
        self.assertTrue(any("not an exact" in e for e in errors), errors)

    def test_occurrence_marker_orders_more_than_99_sources_numerically(self) -> None:
        inventory = {}
        adjacent = "claim text [1-100]"
        for index in range(100, 0, -1):
            pair_id = f"C0001-S{index:02d}"
            inventory[pair_id] = {
                "PairID": pair_id, "OccurrenceID": "C0001",
                "DisplayedReferenceID": f"REF{index:04d}",
                "AdjacentPDFText": adjacent,
            }
        self.assertEqual(
            "[1-100]",
            FULL_VALIDATOR_MODULE.citation_marker_by_occurrence(inventory)["C0001"],
        )
        for row in inventory.values():
            row["AdjacentPDFText"] = "numeric vector [1,2]"
        self.assertNotIn(
            "C0001", FULL_VALIDATOR_MODULE.citation_marker_by_occurrence(inventory)
        )

    def test_atomic_structured_locators_are_not_generic_templates(self) -> None:
        atomic = (
            "Abstract", "Section 3", "Sec. 3", "p. 12", "pp. 12-14",
            "Page 12", "Table 2", "Figure 4", "Fig. 4", "Appendix A",
            "Equation 7", "Supplement A",
        )
        for locator in atomic:
            signature = FULL_VALIDATOR_MODULE.normalized_citation_template_signature(locator)
            with self.subTest(locator=locator, signature=signature):
                self.assertTrue(FULL_VALIDATOR_MODULE.atomic_structured_locator(signature))
        composite = FULL_VALIDATOR_MODULE.normalized_citation_template_signature(
            "Abstract; Section 3; Figure 2"
        )
        self.assertFalse(FULL_VALIDATOR_MODULE.atomic_structured_locator(composite))

    def test_exact_official_record_locators_are_atomic_across_twelve_rows(self) -> None:
        rows, inventory = [], {}
        words = ("amber", "birch", "cobalt", "dahlia", "ember", "fjord", "garnet", "harbor", "indigo", "juniper", "kelp", "lilac")
        for index, word in enumerate(words, start=1):
            pair_id = f"C{index:04d}-S01"
            proposition = f"publisher metadata proposition {index}"
            locator = (
                f"publisher record: DOI 10.1234/example.{index}"
                if index % 2 else f"official record: arXiv 2401.{index:05d}"
            )
            rows.append({
                "PairID": pair_id, "ReferenceID": f"REF{index:04d}",
                "Support": "direct", "ExactAttachedProposition": proposition,
                "ExactSourceLocator": locator,
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(pair_id, proposition)
                    + f"; the {word} official metadata record gives this exact publication fact"
                ),
            })
            inventory[pair_id] = {"AdjacentPDFText": proposition}
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            rows, inventory, "04.csv", errors
        )
        self.assertEqual([], errors)
        composite = FULL_VALIDATOR_MODULE.normalized_citation_template_signature(
            "publisher record: DOI 10.1234/abc.1; Abstract; Table 2"
        )
        self.assertFalse(FULL_VALIDATOR_MODULE.atomic_structured_locator(composite))

    def test_truncated_official_url_fails_source_identity_without_prefix_guessing(self) -> None:
        full = "https://example.org/articles/foundationmodels"
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_source_identity(
            [{
                "ReferenceID": "REF0001", "PublicIdentifier": full,
                "ContentSourceOpened": "https://example.org/articles/foundationmodel",
            }],
            {"REF0001": {"RenderedEntry": f"Paper. {full}"}},
            "04.csv", errors,
        )
        self.assertTrue(any("does not equal" in e for e in errors), errors)

    def test_qi_title_prefix_is_rejected_by_identity_not_lexical_inference(self) -> None:
        truncated = "https://example.org/papers/Qi_Humanoid_Genera"
        complete = "https://example.org/papers/Qi_Humanoid_Generation.pdf"
        self.assertFalse(
            FULL_VALIDATOR_MODULE.endpoint_is_strict_completion(truncated, complete)
        )
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_source_identity(
            [{
                "ReferenceID": "REF0001",
                "PublicIdentifier": complete,
                "ContentSourceOpened": truncated,
                "DispositionEvidence": f"accessed endpoint: {complete}",
            }],
            {"REF0001": {"RenderedEntry": f"Qi et al. Humanoid Generation. {complete}"}},
            "04.csv",
            errors,
        )
        self.assertTrue(any("does not equal" in error for error in errors), errors)

    def test_public_identifier_alone_binds_content_source(self) -> None:
        cases = (
            (
                "official-url",
                "https://example.org/papers/complete-record",
                "https://example.org/papers/complete-record#abstract",
                "https://example.org/papers/complete-recor",
            ),
            (
                "doi",
                "10.1234/example.12345",
                "https://doi.org/10.1234/example.12345",
                "https://doi.org/10.1234/example.1234",
            ),
            (
                "arxiv",
                "arXiv:2401.12345",
                "https://arxiv.org/abs/2401.12345",
                "https://arxiv.org/abs/2401.1234",
            ),
        )
        inventory = {"REF0001": {"RenderedEntry": "Record without printed persistent identity"}}
        for label, public_identifier, exact_source, wrong_source in cases:
            with self.subTest(label=label, disposition="exact"):
                errors: list[str] = []
                FULL_VALIDATOR_MODULE.validate_citation_source_identity(
                    [{
                        "ReferenceID": "REF0001",
                        "PublicIdentifier": public_identifier,
                        "ContentSourceOpened": exact_source,
                    }], inventory, "04.csv", errors,
                )
                self.assertEqual([], errors)
            with self.subTest(label=label, disposition="mismatch-with-auxiliary"):
                errors = []
                FULL_VALIDATOR_MODULE.validate_citation_source_identity(
                    [{
                        "ReferenceID": "REF0001",
                        "PublicIdentifier": public_identifier,
                        "ContentSourceOpened": wrong_source,
                        "DispositionEvidence": f"accessed endpoint: {exact_source}",
                    }], inventory, "04.csv", errors,
                )
                self.assertTrue(errors, "complete auxiliary must not bind a different primary")

    def test_public_identifier_binding_leaves_dangling_sentinel_unchanged(self) -> None:
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_source_identity(
            [{
                "ReferenceID": "REF0002",
                "PublicIdentifier": "no rendered bibliography entry",
                "ContentSourceOpened": "",
                "ExactSourceLocator": "",
            }],
            {"REF0002": {"RenderedEntry": ""}},
            "04.csv",
            errors,
        )
        self.assertEqual([], errors)

    def test_template_dominance_crosses_support_classes_but_abstract_is_concise(self) -> None:
        rows, inventory = [], {}
        for index in range(1, 13):
            pair_id = f"C{index:04d}-S01"
            proposition = f"distinct proposition {index}"
            rows.append({
                "PairID": pair_id, "ReferenceID": f"REF{index:04d}",
                "Support": "direct" if index % 2 else "partial",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": "Abstract",
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(pair_id, proposition)
                    + f"; source evidence for {proposition} directly reports the stated result"
                ),
            })
            inventory[pair_id] = {"AdjacentPDFText": proposition}
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            rows, inventory, "04.csv", errors
        )
        self.assertFalse(any("ExactSourceLocator" in e for e in errors), errors)
        self.assertTrue(any("DispositionEvidence" in e and "direct" in e and "partial" in e for e in errors), errors)

    def test_url_fragments_do_not_change_canonical_page_or_supply_identity(self) -> None:
        base = "https://example.org/papers/abc"
        self.assertEqual(
            FULL_VALIDATOR_MODULE.normalized_rendered_urls(base),
            FULL_VALIDATOR_MODULE.normalized_rendered_urls(base + "#section-2"),
        )
        self.assertEqual(set(), FULL_VALIDATOR_MODULE.normalized_arxiv_ids(
            base + "#arXiv:2501.01234"
        ))
        self.assertEqual(set(), FULL_VALIDATOR_MODULE.normalized_doi_tokens(
            base + "#10.1000/fragment-only"
        ))

    def test_scoped_and_full_gates_reject_adjacent_window_proposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            digest = str(process["selected_pdf_sha256"])
            _, rows = fixture_module.read_csv(
                root / "04-citation-claim-audit-ledger.csv"
            )
            rows[0]["ExactAttachedProposition"] = "claim copied from adjacent row"
            rows[0]["DispositionEvidence"] = (
                FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                    rows[0]["PairID"], rows[0]["ExactAttachedProposition"]
                )
                + "; the source reports the copied claim under its protocol"
            )
            fixture_module.write_csv(
                root / "04-citation-claim-audit-ledger.csv",
                fixture_module.CITATION_LEDGER_COLUMNS,
                rows,
            )
            _, bibliography = fixture_module.read_csv(
                root / "00-bibliography-inventory.csv"
            )
            (root / "04-citation-claim-audit-ledger.md").write_text(
                "# Citation ledger\n\n"
                + self.harness.declaration(
                    digest, process, "R4", [fixture_module.CITATION_ENDPOINT]
                )
                + fixture_module.markdown_table(
                    fixture_module.CITATION_MARKDOWN_HEADERS,
                    fixture_module.citation_markdown_rows(rows, bibliography),
                ),
                encoding="utf-8",
            )
            scoped = self.run_r4(root)
            self.assertNotEqual(0, scoped.returncode, scoped.stdout)
            self.assertIn("possible occurrence/window misalignment", scoped.stdout)
            full = self.harness.run_validator(root)
            self.assertNotEqual(0, full.returncode, full.stdout)
            self.assertIn("possible occurrence/window misalignment", full.stdout)


if __name__ == "__main__":
    unittest.main()
