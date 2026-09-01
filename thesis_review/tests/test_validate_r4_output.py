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


def synthetic_occurrence_packet(
    page_text: str,
    citation_flags: list[bool],
    *,
    repeated_furniture: set[str] | None = None,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, str]]]:
    """Build the internal offset shape without changing the public CSV schema."""

    normalized_page, raw_starts, raw_ends = (
        FULL_VALIDATOR_MODULE.normalized_citation_projection_with_raw_map(page_text)
    )
    furniture = []
    raw_furniture = FULL_VALIDATOR_MODULE.raw_page_furniture_spans(
        page_text, repeated_furniture
    )
    for raw_start, raw_end, label in raw_furniture:
        span = FULL_VALIDATOR_MODULE.normalized_span_for_raw_span(
            raw_starts, raw_ends, raw_start, raw_end
        )
        if span is not None:
            furniture.append((*span, label))
    matches = list(FULL_VALIDATOR_MODULE.NUMERIC_BRACKET_SPAN_RE.finditer(page_text))
    if len(matches) != len(citation_flags):
        raise AssertionError((page_text, len(matches), len(citation_flags)))
    candidate_rows = []
    extracted = []
    inventory: dict[str, dict[str, str]] = {}
    citation_number = 0
    for index, (match, is_citation) in enumerate(
        zip(matches, citation_flags), start=1
    ):
        marker = FULL_VALIDATOR_MODULE.normalize_numeric_marker(match.group(0))
        target_span = FULL_VALIDATOR_MODULE.normalized_span_for_raw_span(
            raw_starts, raw_ends, match.start(), match.end()
        )
        if target_span is None:
            raise AssertionError("candidate has no normalized target span")
        if is_citation:
            citation_number += 1
            occurrence_id = f"C{citation_number:04d}"
        else:
            occurrence_id = "N/A"
        candidate_rows.append({
            "CandidateID": f"BC{index:04d}",
            "PhysicalPage": "1",
            "Marker": marker,
            "Classification": "citation" if is_citation else "non-citation",
            "MappedOccurrenceID": occurrence_id,
        })
        extracted.append({
            "PhysicalPage": 1,
            "Marker": marker,
            "Expanded": FULL_VALIDATOR_MODULE.expand_numeric_marker(marker),
            "Adjacent": FULL_VALIDATOR_MODULE.normalize_extracted_text(page_text),
            "Prefix": page_text[:match.start()],
            "Suffix": page_text[match.end():],
            "RawPageText": page_text,
            "RawStart": match.start(),
            "RawEnd": match.end(),
            "RawContextStart": 0,
            "RawContextEnd": len(page_text),
            "RawFurnitureSpans": tuple(raw_furniture),
            "NormalizedPageText": normalized_page,
            "NormalizedRawStarts": tuple(raw_starts),
            "NormalizedRawEnds": tuple(raw_ends),
            "NormalizedStart": target_span[0],
            "NormalizedEnd": target_span[1],
            "NormalizedContextStart": 0,
            "NormalizedContextEnd": len(normalized_page),
            "NormalizedFurnitureSpans": tuple(furniture),
        })
        if is_citation:
            pair_id = f"{occurrence_id}-S01"
            numbers = FULL_VALIDATOR_MODULE.expand_numeric_marker(marker) or [index]
            inventory[pair_id] = {
                "PairID": pair_id,
                "OccurrenceID": occurrence_id,
                "DisplayedReferenceID": f"REF{numbers[0]:04d}",
                "PDFLocation": "physical p.1",
                "AdjacentPDFText": FULL_VALIDATOR_MODULE.normalize_extracted_text(
                    page_text
                ),
            }
    return (
        FULL_VALIDATOR_MODULE.build_citation_occurrence_anchors(
            candidate_rows, extracted
        ),
        inventory,
    )


def occurrence_attachment_errors(
    page_text: str,
    citation_flags: list[bool],
    proposition: str,
    *,
    occurrence_id: str = "C0001",
    shared_chain: bool = False,
    repeated_furniture: set[str] | None = None,
) -> list[str]:
    anchors, inventory = synthetic_occurrence_packet(
        page_text, citation_flags, repeated_furniture=repeated_furniture
    )
    pair_id = f"{occurrence_id}-S01"
    row = {
        "PairID": pair_id,
        "ReferenceID": inventory[pair_id]["DisplayedReferenceID"],
        "Support": "",
        "ExactAttachedProposition": proposition,
        "ExactSourceLocator": "",
        "DispositionEvidence": "",
    }
    errors: list[str] = []
    validator = (
        FULL_VALIDATOR_MODULE.validate_citation_claim_mechanical_semantics
        if shared_chain
        else FULL_VALIDATOR_MODULE.validate_citation_claim_occurrence_attachment
    )
    validator([row], inventory, anchors, "04.csv", errors)
    return errors


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

    def test_packet_gate_requires_exact_non_citation_role_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_doctoral_bundle(root)
            path = root / "00-citation-candidate-ledger.csv"
            _, rows = fixture_module.read_csv(path)
            non_citation = next(
                row for row in rows
                if row["Classification"].strip().casefold() == "non-citation"
            )
            non_citation["ClassificationEvidence"] = (
                "visible numeric array with contextual non-source semantics"
            )
            fixture_module.write_csv(
                path, fixture_module.CITATION_CANDIDATE_COLUMNS, rows
            )
            result = self.run_r4(root)
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(
                "lacks a canonical predicate or the exact derived role token",
                result.stdout,
            )

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
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            self.harness.write_semantic_acceptance_fixture(root, process)
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
                    [], {}, [], [], [],
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

    def test_source_title_interpolation_does_not_hide_evidence_template(self) -> None:
        rows, inventory = [], {}
        for index in range(1, 13):
            pair_id = f"C{index:04d}-S01"
            proposition = f"bounded proposition {index}"
            rows.append({
                "PairID": pair_id,
                "ReferenceID": f"REF{index:04d}",
                "Support": "direct",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": f"Section {index}.2",
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                        pair_id, proposition
                    )
                    + f"; Unique Work Title {index} describes the cited method, "
                    "dataset, representation, or evaluation premise in its "
                    "Abstract and directly supports the occurrence-specific "
                    f"proposition {proposition}"
                ),
            })
            inventory[pair_id] = {"AdjacentPDFText": proposition}
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            rows, inventory, "04.csv", errors
        )
        self.assertTrue(
            any("repeated long words evidence shingle" in error for error in errors),
            errors,
        )

    def test_atomic_locator_monoculture_fails_at_thesis_scale(self) -> None:
        rows, inventory = [], {}
        words = [f"unique{index}" for index in range(1, 25)]
        for index, word in enumerate(words, start=1):
            pair_id = f"C{index:04d}-S01"
            proposition = f"claim {word}"
            rows.append({
                "PairID": pair_id,
                "ReferenceID": f"REF{index:04d}",
                "Support": "direct",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": "Abstract",
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                        pair_id, proposition
                    )
                    + f"; {word} evidence {word} identifies {word} mechanics "
                    f"under {word} assumptions and {word} scope"
                ),
            })
            inventory[pair_id] = {"AdjacentPDFText": proposition}
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
            rows, inventory, "04.csv", errors
        )
        self.assertTrue(
            any("cross-source locator monoculture" in error for error in errors),
            errors,
        )

    def test_proposition_cannot_absorb_another_occurrence_marker(self) -> None:
        proposition = (
            "Diffusion [1] improves quality; autoregression [2] improves speed."
        )
        errors = occurrence_attachment_errors(
            proposition,
            [True, True],
            proposition,
            shared_chain=True,
        )
        self.assertTrue(
            any("CIT-PROP-FOREIGN-CITATION" in error for error in errors), errors
        )

    def test_marker_only_propositions_have_no_substantive_core(self) -> None:
        for proposition in ("[1]", "([1])", "; [1]"):
            with self.subTest(proposition=proposition):
                errors = occurrence_attachment_errors(
                    f"claim before {proposition}", [True], proposition
                )
                self.assertTrue(
                    any("CIT-PROP-EMPTY-CORE" in error for error in errors),
                    errors,
                )
        for proposition in (
            "α > β",
            "метод работает",
            "モデル",
            "모델",
        ):
            with self.subTest(unicode_core=proposition):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        f"{proposition} [1]", [True], proposition
                    ),
                )

    def test_true_marker_removal_preserves_equal_numeric_data_marker(self) -> None:
        page_text = "[1] the method uses quantization level [1]."
        anchors, inventory = synthetic_occurrence_packet(
            page_text, [True, False]
        )
        proposition = "the method uses quantization level [1]"
        spans = FULL_VALIDATOR_MODULE._anchored_proposition_spans(
            proposition, anchors["C0001"]
        )
        self.assertEqual(1, len(spans))
        core = FULL_VALIDATOR_MODULE.anchored_citation_proposition_core(
            proposition, anchors["C0001"], next(iter(spans))
        )
        self.assertEqual(proposition, core)
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                page_text, [True, False], proposition, shared_chain=True
            ),
        )

    def test_marker_only_multi_digit_cocitation_run_has_empty_core(self) -> None:
        for page_text, proposition in (
            ("[10], [11].", "[10], [11]"),
            ("[100], [200].", "[100], [200]"),
            ("([100], [200]).", "([100], [200])"),
            ("[10] and [11].", "[10] and [11]"),
            ("[10] or [11].", "[10] or [11]"),
            ("see [10], [11].", "see [10], [11]"),
        ):
            with self.subTest(page_text=page_text):
                errors = occurrence_attachment_errors(
                    page_text,
                    [True, True],
                    proposition,
                    occurrence_id="C0002",
                    shared_chain=True,
                )
                self.assertTrue(
                    any("CIT-PROP-EMPTY-CORE" in error for error in errors),
                    errors,
                )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "method A and method B [10], [11].",
                [True, True],
                "method A and method B",
                occurrence_id="C0002",
                shared_chain=True,
            ),
        )

    def test_semicolon_and_blank_line_split_runs_but_single_wrap_does_not(self) -> None:
        for separator in ("; ", "\n\n"):
            page_text = f"shared claim [1]{separator}[2]."
            proposition = (
                "shared claim [1]; [2]"
                if separator.startswith(";")
                else "shared claim [1] [2]"
            )
            errors = occurrence_attachment_errors(
                page_text, [True, True], proposition,
                shared_chain=True,
            )
            self.assertTrue(
                any("CIT-PROP-FOREIGN-CITATION" in error for error in errors),
                (separator, errors),
            )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "shared claim [1]\n[2].", [True, True], "shared claim",
                occurrence_id="C0002", shared_chain=True,
            ),
        )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "shared claim [1], [2].", [True, True], "shared claim",
                occurrence_id="C0002", shared_chain=True,
            ),
        )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "shared claim [1],\n[2].", [True, True], "shared claim",
                occurrence_id="C0002", shared_chain=True,
            ),
        )

    def test_parenthesized_marker_attaches_left_but_blank_paragraph_does_not(self) -> None:
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "bounded claim ([1]).", [True], "bounded claim"
            ),
        )
        errors = occurrence_attachment_errors(
            "detached claim\n\n[1] different paragraph.",
            [True],
            "detached claim",
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in error for error in errors), errors
        )
        enclosing_errors = occurrence_attachment_errors(
            "first paragraph claim\n\n[1] second paragraph claim.",
            [True],
            "first paragraph claim [1] second paragraph claim",
        )
        self.assertTrue(
            any("CIT-PROP-PARAGRAPH-CROSSING" in error for error in enclosing_errors),
            enclosing_errors,
        )

    def test_bounded_left_citation_introducers_attach_to_the_claim(self) -> None:
        for page_text in (
            "bounded claim (see [1]).",
            "bounded claim (see also [1]).",
            "bounded claim (e.g., [1]).",
            "bounded claim (cf. [1]).",
            "bounded claim, as shown in [1].",
            "bounded claim（见[1]）。",
            "bounded claim（参见[1]）。",
            "bounded claim（如文献[1]所示）。",
            "bounded claim（文献[1]）。",
            "bounded claim（例如[1]）。",
        ):
            with self.subTest(page_text=page_text):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        page_text, [True], "bounded claim"
                    ),
                )
        errors = occurrence_attachment_errors(
            "bounded claim (see also an extended intervening explanation [1]).",
            [True],
            "bounded claim",
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in error for error in errors), errors
        )

    def test_bounded_right_citation_introducers_attach_to_the_claim(self) -> None:
        for page_text in (
            "[1] shows that bounded claim.",
            "[1] demonstrates that bounded claim.",
            "[1] reports that bounded claim.",
            "文献[1]表明，bounded claim。",
            "文献[1]指出，bounded claim。",
            "如[1]所示，bounded claim。",
        ):
            with self.subTest(page_text=page_text):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        page_text, [True], "bounded claim"
                    ),
                )
        errors = occurrence_attachment_errors(
            "[1] reports a long intervening explanation that exceeds the "
            "bounded separator budget before bounded claim.",
            [True],
            "bounded claim",
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in error for error in errors), errors
        )

    def test_single_indented_pdf_wrap_does_not_consume_attachment_budget(self) -> None:
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "shared claim [1],\n" + " " * 23 + "[2].",
                [True, True],
                "shared claim",
                occurrence_id="C0002",
            ),
        )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "left claim\n" + " " * 18 + "[1].",
                [True],
                "left claim",
            ),
        )
        wide_left = occurrence_attachment_errors(
            "left claim" + " " * 100 + "[1].", [True], "left claim"
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in e for e in wide_left), wide_left
        )
        wide_run = occurrence_attachment_errors(
            "shared claim [1]" + " " * 100 + "[2].",
            [True, True],
            "shared claim",
            occurrence_id="C0002",
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in e for e in wide_run), wide_run
        )
        wide_right = occurrence_attachment_errors(
            "[1]" + " " * 100 + "right claim.", [True], "right claim"
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in e for e in wide_right), wide_right
        )

    def test_proposition_rejects_page_furniture_and_excessive_span(self) -> None:
        cases = (
            (
                "浙江大学博士学位论文 本节所述方法提高质量",
                "running header/page-furniture prefix",
            ),
            ("长" * 301, "marker-stripped non-whitespace characters"),
        )
        for index, (proposition, expected) in enumerate(cases, start=1):
            pair_id = f"C{index:04d}-S01"
            row = {
                "PairID": pair_id,
                "ReferenceID": f"REF{index:04d}",
                "Support": "direct",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": "Section 2",
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                        pair_id, proposition
                    )
                    + "; the source-specific section states the bounded claim"
                ),
            }
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
                [row], {pair_id: {"AdjacentPDFText": proposition}}, "04.csv", errors
            )
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_direct_local_result_and_abstract_equation_are_rejected(self) -> None:
        cases = (
            (
                "本章方法在表 3.7 的 FID 评测结果达到 0.10",
                "Section 3.7",
                "thesis-local method/result/table",
            ),
            (
                "R-Precision = 1/B times the Topk indicator",
                "Abstract",
                "Abstract-only locator",
            ),
        )
        for index, (proposition, locator, expected) in enumerate(cases, start=1):
            pair_id = f"C{index:04d}-S01"
            row = {
                "PairID": pair_id,
                "ReferenceID": f"REF{index:04d}",
                "Support": "direct",
                "ExactAttachedProposition": proposition,
                "ExactSourceLocator": locator,
                "DispositionEvidence": (
                    FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                        pair_id, proposition
                    )
                    + "; the opened source states the relevant bounded content"
                ),
            }
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
                [row], {pair_id: {"AdjacentPDFText": proposition}}, "04.csv", errors
            )
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_citation_report_finding_must_link_authoritative_pair_rows(self) -> None:
        findings = {
            "R4-F01": {
                "Primary gate": "I",
                "Observation": (
                    "Five cited bibliography records lack DOI, arXiv, or URL identity."
                ),
                "Evidence": "References [10-14] are the affected rendered records.",
                "Required action": "Add a persistent identifier to each record.",
            }
        }
        ledger = [{
            "PairID": "C0001-S01",
            "SeverityFinding": "none",
            "DispositionEvidence": (
                "reasoned non-finding: the optional URL is not required by the "
                "governing citation style"
            ),
        }]
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_owner_report_ledger_consistency(
            findings, {}, ledger, 4, "R4.md", errors
        )
        self.assertTrue(
            any("is not linked from any authoritative 04 Pair row" in error for error in errors),
            errors,
        )
        ledger[0]["SeverityFinding"] = "R4-F01"
        errors = []
        FULL_VALIDATOR_MODULE.validate_citation_owner_report_ledger_consistency(
            findings, {}, ledger, 4, "R4.md", errors
        )
        self.assertTrue(
            any("simultaneously link" in error for error in errors), errors
        )

    def test_citation_finding_heading_and_plural_source_language_are_not_hidden(self) -> None:
        phrases = (
            "Multiple citations do not support the claims",
            "Sources do not support the claims",
            "References lack stable identities",
            "Sources [10-14] do not support the claims",
            "Sources [10–14] lack stable identities",
            "Prior sources [10-14] contradict the claim",
        )
        for phrase in phrases:
            findings = {
                "R4-F01": {
                    "Heading title": phrase,
                    "Observation": "The affected material requires correction.",
                }
            }
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_citation_owner_report_ledger_consistency(
                findings,
                {},
                [{
                    "PairID": "C0001-S01",
                    "SeverityFinding": "none",
                    "DispositionEvidence": (
                        "reasoned non-finding: the source-specific row is "
                        "adequately supported"
                    ),
                }],
                4,
                "R4.md",
                errors,
            )
            with self.subTest(phrase=phrase):
                self.assertTrue(
                    any("is not linked from any authoritative 04 Pair row" in e for e in errors),
                    errors,
                )
        noncitation_errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_citation_owner_report_ledger_consistency(
            {
                "R4-F01": {
                    "Heading title": "Source code and raw data are unavailable",
                    "Observation": "The reproduction description is incomplete.",
                }
            },
            {},
            [{
                "PairID": "C0001-S01",
                "SeverityFinding": "none",
                "DispositionEvidence": "source-specific citation row is supported",
            }],
            4,
            "R4.md",
            noncitation_errors,
        )
        self.assertFalse(
            any("is not linked from any authoritative 04 Pair row" in e for e in noncitation_errors),
            noncitation_errors,
        )

    def test_owned_ledger_reconciliation_is_exact_and_bidirectional(self) -> None:
        report = (
            "## Owned-ledger finding/question reconciliation\n\n"
            "| Report item ID | Owned-ledger selectors |\n"
            "|---|---|\n"
            "| R4-F01 | 04:pair=C0001-S01 |\n"
        )
        findings = {"R4-F01": {"Heading title": "unsupported citation claim"}}
        citation = [{
            "PairID": "C0001-S01",
            "ReferenceID": "REF0001",
            "SeverityFinding": "R4-F01",
            "DispositionEvidence": "source-specific contradiction",
        }]
        errors: list[str] = []
        FULL_VALIDATOR_MODULE.validate_owned_ledger_report_reconciliation(
            report, findings, {}, "R4", "doctorate", [], [], citation,
            "R4.md", errors,
        )
        self.assertEqual([], errors)

        missing = report.replace("04:pair=C0001-S01", "none")
        errors = []
        FULL_VALIDATOR_MODULE.validate_owned_ledger_report_reconciliation(
            missing, findings, {}, "R4", "doctorate", [], [], citation,
            "R4.md", errors,
        )
        self.assertTrue(
            any("does not exactly match authoritative owned rows" in e for e in errors),
            errors,
        )

        evidence_only = [dict(citation[0])]
        evidence_only[0]["SeverityFinding"] = "none"
        evidence_only[0]["DispositionEvidence"] = "decision R4-F01 in prose"
        errors = []
        FULL_VALIDATOR_MODULE.validate_owned_ledger_report_reconciliation(
            report, findings, {}, "R4", "doctorate", [], [], evidence_only,
            "R4.md", errors,
        )
        self.assertTrue(
            any("permitted only in SeverityFinding" in e for e in errors), errors
        )
        self.assertTrue(
            any("extra=[('04', 'C0001-S01')]" in e for e in errors), errors
        )

        contradictory = [dict(citation[0])]
        contradictory[0]["DispositionEvidence"] = (
            "reasoned non-finding: this row is nevertheless declared harmless"
        )
        errors = []
        FULL_VALIDATOR_MODULE.validate_owned_ledger_report_reconciliation(
            report, findings, {}, "R4", "doctorate", [], [], contradictory,
            "R4.md", errors,
        )
        self.assertTrue(
            any("simultaneously name" in e for e in errors), errors
        )

    def test_explicit_thesis_section_anchor_is_bound_to_rendered_interval(self) -> None:
        intervals = {"2.1": (3, 5), "2.1.1": (4, 4), "2.2": (6, 8)}
        for value in (
            "physical p.4, Section 2.1",
            "physical p.4, Sec. 2.1.1",
            "physical p.4, §2.1",
            "physical p.4, 第2.1节",
            "physical p.8, Table 2.1 and DOI 10.1/example",
        ):
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_pdf_section_anchor_value(
                value, intervals, "R4.md", "anchor", errors
            )
            with self.subTest(valid=value):
                self.assertEqual([], errors)

        outside: list[str] = []
        FULL_VALIDATOR_MODULE.validate_pdf_section_anchor_value(
            "physical p.6, Section 2.1",
            intervals,
            "R4.md",
            "R4-F01 Location",
            outside,
        )
        self.assertTrue(any("outside its rendered interval" in e for e in outside), outside)
        absent: list[str] = []
        FULL_VALIDATOR_MODULE.validate_pdf_section_anchor_value(
            "physical p.4, Section 2.3",
            intervals,
            "R4.md",
            "R4-F01 Location",
            absent,
        )
        self.assertTrue(any("absent from" in e for e in absent), absent)

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

    def test_true_occurrence_anchor_rejects_another_span_in_the_same_window(
        self,
    ) -> None:
        errors = occurrence_attachment_errors(
            "fixture proposition [1]; quantization levels are [3, 8]; "
            "scale interval [0.85, 1].",
            [True, False, False],
            "quantization levels are [3, 8]",
        )
        self.assertTrue(
            any("CIT-PROP-NOT-ANCHORED" in error for error in errors), errors
        )

    def test_raw_offset_projection_retains_whole_string_nfkc_identity(self) -> None:
        for page_text in ("e\u0301 [1]", "\u1100\u1161 [1]", "\ufb01 [1]", "\uff21 [\uff11]"):
            with self.subTest(page_text=page_text):
                projected, raw_starts, raw_ends = (
                    FULL_VALIDATOR_MODULE.normalized_citation_projection_with_raw_map(
                        page_text
                    )
                )
                self.assertEqual(
                    FULL_VALIDATOR_MODULE.normalized_citation_projection_text(
                        page_text
                    ),
                    projected,
                )
                raw_start = page_text.index("[")
                raw_end = page_text.index("]") + 1
                span = FULL_VALIDATOR_MODULE.normalized_span_for_raw_span(
                    raw_starts, raw_ends, raw_start, raw_end
                )
                self.assertIsNotNone(span)
                self.assertEqual("[1]", projected[slice(*(span or (0, 0)))])

    def test_true_occurrence_anchor_accepts_left_right_and_duplicate_offsets(
        self,
    ) -> None:
        cases = (
            ("the method improves quality [1].", [True], "the method improves quality", "C0001"),
            ("[1] according to the method improves quality.", [True], "the method improves quality", "C0001"),
            ("[1] \u6839\u636e\u53f3\u4fa7\u547d\u9898\u6210\u7acb\u3002", [True], "\u53f3\u4fa7\u547d\u9898\u6210\u7acb", "C0001"),
            ("repeated claim [1]. repeated claim [1].", [True, True], "repeated claim", "C0001"),
            ("repeated claim [1]. repeated claim [1].", [True, True], "repeated claim", "C0002"),
        )
        for page_text, flags, proposition, occurrence_id in cases:
            with self.subTest(page_text=page_text, occurrence_id=occurrence_id):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        page_text,
                        flags,
                        proposition,
                        occurrence_id=occurrence_id,
                    ),
                )

    def test_co_citation_run_is_closed_but_numeric_data_is_not_foreign(self) -> None:
        page_text = "shared claim [1], [2]. separate claim [3]."
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                page_text, [True, True, True], "shared claim", occurrence_id="C0002"
            ),
        )
        errors = occurrence_attachment_errors(
            page_text,
            [True, True, True],
            "shared claim [1], [2]. separate claim [3]",
        )
        self.assertTrue(
            any("CIT-PROP-FOREIGN-CITATION" in error for error in errors), errors
        )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "the vector [1,2] improves accuracy [3].",
                [False, True],
                "the vector [1,2] improves accuracy",
            ),
        )

    def test_raw_page_furniture_requires_a_boundary_line(self) -> None:
        footer_errors = occurrence_attachment_errors(
            "UNIVERSITY HEADER\nclaim [1]\n17",
            [True],
            "claim [1] 17",
        )
        self.assertTrue(
            any("CIT-PROP-PAGE-FURNITURE" in error for error in footer_errors),
            footer_errors,
        )
        header_errors = occurrence_attachment_errors(
            "UNIVERSITY HEADER\nclaim [1]\nbody",
            [True],
            "UNIVERSITY HEADER claim",
            repeated_furniture={"UNIVERSITY HEADER"},
        )
        self.assertTrue(
            any("CIT-PROP-PAGE-FURNITURE" in error for error in header_errors),
            header_errors,
        )
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                "claim reaches 17 [1]", [True], "claim reaches 17"
            ),
        )
        for footer in (
            "- 17 -", "Page 17", "p 17", "p. 17", "17 of 300", "(17)",
            "iv", "xvii", "XVII",
        ):
            with self.subTest(footer=footer):
                errors = occurrence_attachment_errors(
                    f"claim [1]\n{footer}", [True], f"claim [1] {footer}"
                )
                self.assertTrue(
                    any("CIT-PROP-PAGE-FURNITURE" in error for error in errors),
                    errors,
                )
        repeated_header = "UNIVERSITY THESIS 17"
        repeated_errors = occurrence_attachment_errors(
            f"claim [1]\n{repeated_header}",
            [True],
            f"claim [1] {repeated_header}",
            repeated_furniture={
                FULL_VALIDATOR_MODULE.canonical_boundary_furniture_signature(
                    repeated_header
                )
            },
        )
        self.assertTrue(
            any("CIT-PROP-PAGE-FURNITURE" in error for error in repeated_errors),
            repeated_errors,
        )
        for footer in (
            "Page 17 / 300",
            "Page 17 of 300",
            "- xvii -",
            "Chapter 3 — 17",
        ):
            with self.subTest(dynamic_footer=footer):
                errors = occurrence_attachment_errors(
                    f"claim [1]\n{footer}", [True], f"claim [1] {footer}"
                )
                self.assertTrue(
                    any("CIT-PROP-PAGE-FURNITURE" in error for error in errors),
                    errors,
                )
        for valid_line in (
            "University [1] enrollment reached 100",
            "Chapter 3 reports [1] Table 10",
            "Thesis cites [1] contribution 2",
            "University [1] enrollment ratio: 100",
            "Chapter 3 reports [1] accuracy: 10",
            "Thesis [1] score/100",
            "the sample [1] contains 17 of 300 accepted cases",
            "the method [1] uses p 17 as a symbolic parameter",
            "the score [1] equals (17) in this enumeration",
        ):
            with self.subTest(valid_boundary_line=valid_line):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        valid_line, [True], valid_line
                    ),
                )
        for acronym in ("CIVIL", "MIX", "LIV", "DIV"):
            with self.subTest(roman_like_acronym=acronym):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        f"{acronym}\nclaim [1]", [True], f"{acronym} claim"
                    ),
                )

    def test_pdf_extraction_carries_repeated_furniture_as_internal_offsets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "furniture.pdf"
            writer = fixture_module.PdfWriter()
            for page_number in range(1, 4):
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(
                    writer,
                    page,
                    "UNIVERSITY HEADER\n"
                    f"page claim {page_number} [{page_number}]\n"
                    f"{page_number}",
                )
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            candidates, unmatched = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates(
                    pdf_path, set(), errors
                )
            )
            self.assertEqual([], errors)
            self.assertEqual([], unmatched)
            self.assertEqual(3, len(candidates))
            for page_number, candidate in enumerate(candidates, start=1):
                labels = {
                    label
                    for _, _, label in candidate["NormalizedFurnitureSpans"]
                }
                self.assertIn("UNIVERSITY HEADER", labels)
                self.assertIn(str(page_number), labels)
                self.assertGreaterEqual(candidate["NormalizedStart"], 0)
            self.assertNotIn(
                "NormalizedStart", FULL_VALIDATOR_MODULE.CITATION_CANDIDATE_COLUMNS
            )

    def test_pdf_extraction_marks_dynamic_running_page_furniture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "dynamic-furniture.pdf"
            writer = fixture_module.PdfWriter()
            for page_number in range(1, 4):
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(
                    writer,
                    page,
                    f"Chapter 3 -- {page_number}\n"
                    f"bounded claim {page_number} [{page_number}]\n"
                    f"Page {page_number} of 3",
                )
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            candidates, unmatched = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates(
                    pdf_path, set(), errors
                )
            )
            self.assertEqual([], errors)
            self.assertEqual([], unmatched)
            self.assertEqual(3, len(candidates))
            for page_number, candidate in enumerate(candidates, start=1):
                labels = {
                    label
                    for _, _, label in candidate["NormalizedFurnitureSpans"]
                }
                self.assertIn(f"Chapter 3 -- {page_number}", labels)
                self.assertIn(f"Page {page_number} of 3", labels)

    def test_pdf_extraction_infers_only_repeated_changing_generic_headers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "generic-dynamic-furniture.pdf"
            writer = fixture_module.PdfWriter()
            for page_number in range(1, 4):
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(
                    writer,
                    page,
                    f"Motion Generation Framework -- {page_number}\n"
                    f"bounded claim {page_number} [{page_number}]",
                )
            page = writer.add_blank_page(width=595.28, height=841.89)
            fixture_module.add_ascii_text(
                writer,
                page,
                "Accuracy -- 17\none-off substantive claim [4]",
            )
            with pdf_path.open("wb") as handle:
                writer.write(handle)

            errors: list[str] = []
            candidates, unmatched = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates(
                    pdf_path, set(), errors
                )
            )
            self.assertEqual([], errors)
            self.assertEqual([], unmatched)
            self.assertEqual(4, len(candidates))
            for page_number, candidate in enumerate(candidates[:3], start=1):
                labels = {
                    label
                    for _, _, label in candidate["NormalizedFurnitureSpans"]
                }
                self.assertIn(
                    f"Motion Generation Framework -- {page_number}", labels
                )
            final_labels = {
                label
                for _, _, label in candidates[3]["NormalizedFurnitureSpans"]
            }
            self.assertNotIn("Accuracy -- 17", final_labels)

    def test_repeated_incrementing_citation_lines_are_not_page_furniture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "substantive-boundary-lines.pdf"
            writer = fixture_module.PdfWriter()
            for page_number in range(1, 4):
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(
                    writer,
                    page,
                    f"Chapter 3 cites [1] premise {page_number}\n"
                    f"substantive body {page_number}",
                )
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            candidates, unmatched = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates(
                    pdf_path, set(), errors
                )
            )
            self.assertEqual([], errors)
            self.assertEqual([], unmatched)
            self.assertEqual(3, len(candidates))
            for page_number, candidate in enumerate(candidates, start=1):
                labels = {
                    label
                    for _, _, label in candidate["NormalizedFurnitureSpans"]
                }
                self.assertNotIn(
                    f"Chapter 3 cites [1] premise {page_number}", labels
                )

    def test_chinese_dynamic_page_furniture_signatures(self) -> None:
        signatures = {
            FULL_VALIDATOR_MODULE.canonical_boundary_furniture_signature(
                f"浙江大学博士学位论文 — 第{page_number}页"
            )
            for page_number in range(1, 4)
        }
        self.assertEqual({"浙江大学博士学位论文 <page>"}, signatures)
        for page_number in range(1, 4):
            line = f"第{page_number}页 共300页"
            self.assertEqual(
                [(0, len(line), line)],
                FULL_VALIDATOR_MODULE.raw_page_furniture_spans(line),
            )

    def test_200_300_proposition_length_policy_uses_normalized_characters(
        self,
    ) -> None:
        short_with_boundary = "x" * 99 + "; " + "y" * 99
        continuous_long = "a" * 300
        split_long = "b" * 101 + "; " + "c" * 100
        too_long = "d" * 301
        self.assertEqual(200, len(short_with_boundary))
        self.assertEqual(203, len(split_long))
        for proposition in (short_with_boundary, continuous_long):
            with self.subTest(valid_length=len(proposition)):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        f"{proposition} [1]",
                        [True],
                        proposition,
                        shared_chain=True,
                    ),
                )
        soft_errors = occurrence_attachment_errors(
            f"{split_long} [1]", [True], split_long, shared_chain=True
        )
        self.assertTrue(
            any("CIT-PROP-SOFT-LIMIT" in error for error in soft_errors), soft_errors
        )
        hard_errors = occurrence_attachment_errors(
            f"{too_long} [1]", [True], too_long, shared_chain=True
        )
        self.assertTrue(
            any("CIT-PROP-TOO-LONG" in error for error in hard_errors), hard_errors
        )
        marker_boundary = "m" * 299
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                f"{marker_boundary} [1]", [True], marker_boundary,
                shared_chain=True,
            ),
        )
        whitespace_heavy = ("w " * 299).strip()
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                f"{whitespace_heavy} [1]", [True], whitespace_heavy,
                shared_chain=True,
            ),
        )
        for abbreviation in ("e.g.", "et al."):
            proposition = "a" * 105 + f" {abbreviation} " + "b" * 105
            with self.subTest(abbreviation=abbreviation):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        f"{proposition} [1]", [True], proposition,
                        shared_chain=True,
                    ),
                )
        true_boundary = "a" * 105 + ". Sentence " + "b" * 105
        boundary_errors = occurrence_attachment_errors(
            f"{true_boundary} [1]", [True], true_boundary, shared_chain=True
        )
        self.assertTrue(
            any("CIT-PROP-SOFT-LIMIT" in e for e in boundary_errors),
            boundary_errors,
        )
        no_space_boundary = "a" * 105 + ".Sentence " + "b" * 105
        no_space_errors = occurrence_attachment_errors(
            f"{no_space_boundary} [1]", [True], no_space_boundary,
            shared_chain=True,
        )
        self.assertTrue(
            any("CIT-PROP-SOFT-LIMIT" in e for e in no_space_errors),
            no_space_errors,
        )
        abbreviation_no_space = "a" * 105 + " e.g.Method " + "b" * 105
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                f"{abbreviation_no_space} [1]", [True],
                abbreviation_no_space, shared_chain=True,
            ),
        )
        decimal_no_space = "a" * 105 + " 3.14value " + "b" * 105
        self.assertEqual(
            [],
            occurrence_attachment_errors(
                f"{decimal_no_space} [1]", [True], decimal_no_space,
                shared_chain=True,
            ),
        )
        for sentence_prefix in ("this section", "the figure", "no"):
            proposition = (
                "a" * 100 + f" {sentence_prefix}. Next sentence " + "b" * 100
            )
            with self.subTest(full_word_sentence=sentence_prefix):
                errors = occurrence_attachment_errors(
                    f"{proposition} [1]", [True], proposition,
                    shared_chain=True,
                )
                self.assertTrue(
                    any("CIT-PROP-SOFT-LIMIT" in e for e in errors), errors
                )
        for abbreviation in ("Fig. 2", "Eq. 3", "Sec. 4", "No. 5"):
            proposition = "a" * 105 + f" {abbreviation} " + "b" * 105
            with self.subTest(locator_abbreviation=abbreviation):
                self.assertEqual(
                    [],
                    occurrence_attachment_errors(
                        f"{proposition} [1]", [True], proposition,
                        shared_chain=True,
                    ),
                )

    def test_atomic_locator_dominance_preserves_exact_locator_identity(self) -> None:
        def validate_locators(locators: list[str]) -> list[str]:
            rows, inventory = [], {}
            for index, locator in enumerate(locators, start=1):
                pair_id = f"C{index:04d}-S01"
                proposition = f"atomic locator proposition {index}"
                token = "unique" + chr(96 + ((index - 1) // 26) + 1) + chr(
                    97 + ((index - 1) % 26)
                )
                rows.append({
                    "PairID": pair_id,
                    "ReferenceID": f"REF{index:04d}",
                    "Support": "direct",
                    "ExactAttachedProposition": proposition,
                    "ExactSourceLocator": locator,
                    "DispositionEvidence": (
                        FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                            pair_id, proposition
                        )
                        + "; " + " ".join([token] * 12)
                    ),
                })
                inventory[pair_id] = {"AdjacentPDFText": proposition}
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
                rows, inventory, "04.csv", errors
            )
            return errors

        dominant = validate_locators(["Table 1"] * 27 + ["Table 2"] * 3)
        self.assertTrue(
            any("CIT-LOC-ATOMIC-DOMINANCE" in error for error in dominant),
            dominant,
        )
        balanced = validate_locators(["Table 1"] * 15 + ["Table 2"] * 15)
        self.assertFalse(
            any("CIT-LOC-ATOMIC-DOMINANCE" in error for error in balanced),
            balanced,
        )
        mixed = validate_locators(
            ["Table 1"] * 27
            + [
                "Section 2, heading topic"
                + chr(96 + ((index - 1) // 26) + 1)
                + chr(97 + ((index - 1) % 26))
                for index in range(1, 31)
            ]
        )
        self.assertFalse(
            any("CIT-LOC-ATOMIC-DOMINANCE" in error for error in mixed), mixed
        )
        official = validate_locators([
            f"publisher record: DOI 10.1234/example.{index}"
            for index in range(1, 31)
        ])
        self.assertFalse(
            any("CIT-LOC-ATOMIC-DOMINANCE" in error for error in official),
            official,
        )
        self.assertNotEqual(
            FULL_VALIDATOR_MODULE.canonical_atomic_locator_identity(
                "publisher record: DOI 10.01234/example"
            ),
            FULL_VALIDATOR_MODULE.canonical_atomic_locator_identity(
                "publisher record: DOI 10.1234/example"
            ),
        )
        self.assertNotEqual(
            FULL_VALIDATOR_MODULE.canonical_atomic_locator_identity(
                "publisher record: DOI 10.1234/foo"
            ),
            FULL_VALIDATOR_MODULE.canonical_atomic_locator_identity(
                "publisher record: DOI 10.1234/foo."
            ),
        )
        self.assertEqual(
            FULL_VALIDATOR_MODULE.canonical_atomic_locator_identity(
                "publisher record: DOI 10.1234/foo"
            ),
            FULL_VALIDATOR_MODULE.canonical_atomic_locator_identity(
                "PUBLISHER Record: doi 10.1234/foo"
            ),
        )
        punctuation_variants = validate_locators(
            ["Abstract"] * 10 + ["Abstract."] * 10 + ["Abstract:"] * 10
        )
        self.assertTrue(
            any(
                "CIT-LOC-ATOMIC-DOMINANCE" in error
                for error in punctuation_variants
            ),
            punctuation_variants,
        )
        coordinate_variants = validate_locators(
            ["Table 01"] * 13 + ["Table 1"] * 13 + ["Table 2"] * 4
        )
        self.assertTrue(
            any(
                "CIT-LOC-ATOMIC-DOMINANCE" in error
                for error in coordinate_variants
            ),
            coordinate_variants,
        )
        alias_variants = validate_locators(
            ["Section 01"] * 10 + ["Sec. 1"] * 10 + ["sec 1"] * 10
        )
        self.assertTrue(
            any(
                "CIT-LOC-ATOMIC-DOMINANCE" in error
                for error in alias_variants
            ),
            alias_variants,
        )
        generic_variants = validate_locators(
            ["Method"] * 15 + ["Methods"] * 12 + ["Table 2"] * 3
        )
        self.assertTrue(
            any(
                "CIT-LOC-ATOMIC-DOMINANCE" in error
                for error in generic_variants
            ),
            generic_variants,
        )

    def test_atomic_locator_dominance_uses_row_denominator_not_unique_units(self) -> None:
        def validate_specs(
            specs: list[tuple[str, int, int]]
        ) -> list[str]:
            rows: list[dict[str, str]] = []
            inventory: dict[str, dict[str, str]] = {}
            for index, (locator, reference_number, proposition_number) in enumerate(
                specs, start=1
            ):
                pair_id = f"C{index:04d}-S01"
                proposition = f"bounded proposition {proposition_number}"
                rows.append({
                    "PairID": pair_id,
                    "ReferenceID": f"REF{reference_number:04d}",
                    "Support": "direct",
                    "ExactAttachedProposition": proposition,
                    "ExactSourceLocator": locator,
                    "DispositionEvidence": (
                        FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                            pair_id, proposition
                        )
                        + f"; source row {index} states its bounded content "
                        "under the cited source scope"
                    ),
                })
                inventory[pair_id] = {"AdjacentPDFText": proposition}
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_citation_claim_semantic_specificity(
                rows, inventory, "04.csv", errors
            )
            return errors

        dominant_unique = [
            ("Abstract", (index % 12) + 1, index + 1)
            for index in range(18)
        ]
        dominant_with_duplicates = dominant_unique + dominant_unique[:9]
        true_row_dominance = validate_specs(
            dominant_with_duplicates
            + [("Table 2", 20 + index, 30 + index) for index in range(3)]
        )
        self.assertTrue(
            any("CIT-LOC-ATOMIC-DOMINANCE" in e for e in true_row_dominance),
            true_row_dominance,
        )

        abstract_rows = [
            ("Abstract", (index % 12) + 1, (index % 18) + 1)
            for index in range(21)
        ]
        table_rows = [
            ("Table 2", 30 + (index % 3), 30 + (index % 3))
            for index in range(33)
        ]
        false_unique_unit_dominance = validate_specs(abstract_rows + table_rows)
        self.assertFalse(
            any(
                "CIT-LOC-ATOMIC-DOMINANCE" in e
                for e in false_unique_unit_dominance
            ),
            false_unique_unit_dominance,
        )

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
            rows[0]["ExactAttachedProposition"] = "quantization levels are [3, 8]"
            rows[0]["DispositionEvidence"] = (
                FULL_VALIDATOR_MODULE.citation_occurrence_binding_marker(
                    rows[0]["PairID"], rows[0]["ExactAttachedProposition"]
                )
                + "; the source reports the quantization-level claim under its protocol"
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
            self.assertIn("CIT-PROP-NOT-ANCHORED", scoped.stdout)
            full = self.harness.run_validator(root)
            self.assertNotEqual(0, full.returncode, full.stdout)
            self.assertIn("CIT-PROP-NOT-ANCHORED", full.stdout)


if __name__ == "__main__":
    unittest.main()
