from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_validate_review_bundle as fixture_module


STAGE_P_VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validate_stage_p_output.py"
)
STAGE_P_FILES = {
    "00-process-parameters.json",
    "00-manifest.md",
    "01-policy-basis.md",
    "00-page-inventory.csv",
    "00-bibliography-inventory.csv",
    "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv",
    "00-citation-inventory.csv",
    "frozen-thesis.pdf",
}
PEER_AND_DOWNSTREAM_FILES = {
    *(f"R{index}-comprehensive-review.md" for index in range(1, 6)),
    "02-page-layout-ledger.md",
    "02-page-layout-ledger.csv",
    "03-bibliography-audit-ledger.md",
    "03-bibliography-audit-ledger.csv",
    "04-citation-claim-audit-ledger.md",
    "04-citation-claim-audit-ledger.csv",
    "05-ai-style-assessment.md",
    "90-chair-synthesis.md",
    "91-revision-ledger.md",
    "91-revision-ledger.csv",
    "91-ai-actionable-ledger.csv",
    "92-new-evidence-or-experiments.md",
    "92-new-evidence-or-experiments.csv",
    "93-user-facing-summary.md",
    "93-current-actionable-items.csv",
    "93-current-ai-actionable-items.csv",
    "94-post-freeze-prior-issue-closure.md",
    "95-bundle-validation.md",
}


def load_stage_p_module():
    spec = importlib.util.spec_from_file_location(
        "test_stage_p_validator_module", STAGE_P_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Stage-P validator for synthetic tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE_P_MODULE = load_stage_p_module()
FULL_VALIDATOR_MODULE = STAGE_P_MODULE.load_validator()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(
    path: Path, headers: list[str], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def snapshot(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative] = ("directory", "")
        else:
            result[relative] = (
                "file",
                hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            )
    return result


class ValidateStagePOutputTests(unittest.TestCase):
    def build_full_fixture(self, root: Path, *, doctorate: bool = False) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        harness.build_bundle(root)
        if doctorate:
            harness.convert_bundle_to_doctorate(root)

    def build_stage_p_only_fixture(
        self, root: Path, *, doctorate: bool = False
    ) -> None:
        self.build_full_fixture(root, doctorate=doctorate)
        for path in list(root.iterdir()):
            if path.name in STAGE_P_FILES:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def run_stage_p(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(STAGE_P_VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_full_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(STAGE_P_MODULE.VALIDATOR), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def refresh_process_identity(self, root: Path) -> None:
        process_path = root / "00-process-parameters.json"
        process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
        manifest = root / "00-manifest.md"
        manifest.write_text(
            re.sub(
                r"(?m)^- Process-parameter file and SHA-256: .*$",
                "- Process-parameter file and SHA-256: "
                f"00-process-parameters.json / {process_digest}",
                manifest.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )

    def add_governing_url_metadata(self, root: Path, endpoint: str) -> None:
        process_path = root / "00-process-parameters.json"
        process = json.loads(process_path.read_text(encoding="utf-8"))
        process["governing_rule_urls"] = [endpoint]
        process_path.write_text(json.dumps(process), encoding="utf-8")
        self.refresh_process_identity(root)
        manifest = root / "00-manifest.md"
        projection = FULL_VALIDATOR_MODULE.manifest_process_projection(process)
        manifest.write_text(
            re.sub(
                r"(?m)^- Governing template/rules: .*$",
                "- Governing template/rules: "
                + projection["Governing template/rules"],
                manifest.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )

    def assert_stage_p_and_full_fail(self, root: Path, needle: str) -> None:
        stage_p = self.run_stage_p(root)
        full = self.run_full_validator(root)
        self.assertNotEqual(stage_p.returncode, 0, stage_p.stdout + stage_p.stderr)
        self.assertNotEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assertIn(needle, stage_p.stdout)
        self.assertIn(needle, full.stdout)

    def assert_stage_p_fails(self, root: Path, needle: str) -> None:
        result = self.run_stage_p(root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("FAIL\n"), result.stdout)
        self.assertIn(needle, result.stdout)

    def test_stage_p_only_fixture_passes_without_writing(self) -> None:
        for doctorate in (False, True):
            with self.subTest(doctorate=doctorate), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_stage_p_only_fixture(root, doctorate=doctorate)
                before = snapshot(root)
                result = self.run_stage_p(root)
                after = snapshot(root)
                self.assertEqual(
                    result.returncode, 0, result.stdout + result.stderr
                )
                self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)
                self.assertEqual(before, after)
                self.assertFalse((root / "95-bundle-validation.md").exists())
                self.assertFalse((root / "__pycache__").exists())

    def test_governing_url_metadata_does_not_open_a_stage_p_endpoint(self) -> None:
        endpoint = "https://example.edu/official-rule"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            self.add_governing_url_metadata(root, endpoint)
            result = self.run_stage_p(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("PASS\n"), result.stdout)

        for filename in ("00-manifest.md", "01-policy-basis.md"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_stage_p_only_fixture(root)
                self.add_governing_url_metadata(root, endpoint)
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "public_endpoints=[none]",
                        f"public_endpoints=[{endpoint}]",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_stage_p_fails(
                    root,
                    "current P authoritative endpoint allowlist",
                )

    def test_pdf_derived_numbered_chapter_boundary_rejects_p0073_style_mislabel_in_both_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root, page_count=3)
            stage_p_before = self.run_stage_p(root)
            self.assertEqual(
                stage_p_before.returncode,
                0,
                stage_p_before.stdout + stage_p_before.stderr,
            )
            for filename in (
                "00-page-inventory.csv",
                "02-page-layout-ledger.csv",
            ):
                path = root / filename
                headers, rows = read_rows(path)
                rows[1]["Region"] = "chapter 3"
                write_rows(path, headers, rows)
            self.assert_stage_p_and_full_fail(
                root,
                "PDF-derived region mismatch at physical p.2",
            )

    def test_chapter_detector_accepts_chinese_and_english_but_not_body_references(self) -> None:
        detect = FULL_VALIDATOR_MODULE.detect_rendered_chapter_start
        self.assertEqual(
            detect("博士学位论文 4 可组合运动控制\n4 可组合运动控制\n4.1 引言"),
            4,
        )
        self.assertEqual(
            detect("Chapter IV Composable Motion Control\n4.1 Introduction"),
            4,
        )
        self.assertIsNone(
            detect(
                "Discussion of prior work\n"
                "The method follows Chapter 4 and cites Section 4.1 in prose."
            )
        )
        for toc_or_prose in (
            "目录\n第4章 可组合运动控制 73",
            "目录\n第4章 可组合运动控制 73\n4.1 引言 75\n4.2 方法 77",
            "Contents\nChapter 4 Composable Motion Control 73\n4.1 Introduction 75\n4.2 Method 77",
            "Chapter 4 Composable Motion Control 73\n4.1 Introduction 75\n4.2 Method 77",
            "Chapter 4 presents the proposed method.",
            "第4章介绍了本章方法。",
            "第4章中，我们介绍本章方法\n4.1 节给出实现细节",
        ):
            with self.subTest(text=toc_or_prose):
                self.assertIsNone(detect(toc_or_prose))

    def test_section_detector_excludes_toc_and_metric_decimals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "sections.pdf"
            writer = fixture_module.PdfWriter()
            texts = (
                "Contents\n4.1 Introduction ................ 2\n"
                "4.2 Method Details ................ 2",
                "Doctoral Thesis 4 Rendered Boundary\n"
                "4 Rendered Boundary\n"
                "4.1 Introduction\n"
                "0.14 0.30 0.52\n"
                "4.2\nMethod Details\n"
                "The experiment reports 4.6 as a numeric value.",
                "References\n[1] Fixture reference.",
            )
            for value in texts:
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(writer, page, value)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            locations = FULL_VALIDATOR_MODULE.derive_rendered_section_locations(
                pdf_path, {3}, errors
            )
            self.assertEqual(errors, [])
            self.assertEqual(locations, [("4.1", 2), ("4.2", 2)])

    def test_chapter_detector_supports_cross_line_titles_and_continuous_transitions(self) -> None:
        detect = FULL_VALIDATOR_MODULE.detect_rendered_chapter_start
        rendered_pages = (
            "CHAPTER 3\nKinematic Unit Generation\n3.1 Introduction",
            "Chapter 3 Kinematic Unit Generation\n3.7 Summary",
            "CHAPTER 4\nComposable Motion Control\n4.1 Introduction",
            "Chapter 4 Composable Motion Control\n4.6 Experiments",
        )
        self.assertEqual([detect(text) for text in rendered_pages], [3, None, 4, None])
        self.assertEqual(
            detect("CHAPTER 4\nMotion with Llama 3\n4.1 Introduction"),
            4,
        )

    def test_region_semantics_accepts_descriptive_class_prefixes(self) -> None:
        semantics = FULL_VALIDATOR_MODULE._inventory_region_semantics
        self.assertEqual(semantics("chapter — methods"), ("chapter", None))
        self.assertEqual(semantics("body — results"), ("chapter", None))
        self.assertEqual(semantics("第4章 — experiments"), ("chapter", 4))

    def test_neutral_region_requires_a_substantively_empty_rendered_page(self) -> None:
        harness = fixture_module.ValidateReviewBundleTests(
            methodName="test_complete_fixture_passes"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Five pages leave physical p.4 as a genuinely blank separator while
            # retaining the bilingual abstracts, a body section, and bibliography.
            harness.build_bundle(root, page_count=5)
            path = root / "00-page-inventory.csv"
            headers, rows = read_rows(path)
            rows[3]["Region"] = "separator — blank verso"
            write_rows(path, headers, rows)
            result = self.run_stage_p(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows[1]["Region"] = "separator — hides content"
            write_rows(path, headers, rows)
            self.assert_stage_p_fails(
                root,
                "neutral Region cannot hide substantive rendered content at physical p.2",
            )

    def test_repeated_edge_prose_is_not_treated_as_page_furniture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "repeated-prose.pdf"
            writer = fixture_module.PdfWriter()
            for _index in range(2):
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(
                    writer, page, "Repeated substantive method result."
                )
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            rows = [{
                "PageID": f"P{physical_page:04d}",
                "PhysicalPage": str(physical_page),
                "PrintedPage": "",
                "Region": "separator — claimed blank",
                "MechanicalSignals": "none",
                "PDFSHA256": "A" * 64,
            } for physical_page in (1, 2)]
            errors: list[str] = []
            FULL_VALIDATOR_MODULE.validate_pdf_derived_page_regions(
                pdf_path, rows, set(), errors
            )
            self.assertEqual(
                sum("neutral Region cannot hide" in error for error in errors),
                2,
                errors,
            )

    def test_manifest_binds_exact_pypdf_runtime_for_scoped_and_full_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_full_fixture(root)
            manifest = root / "00-manifest.md"
            manifest.write_text(
                re.sub(
                    r"(?m)^- PDF extraction runtime: .*$",
                    "- PDF extraction runtime: pypdf=0.0.0",
                    manifest.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            self.assert_stage_p_and_full_fail(
                root,
                "PDF extraction runtime must exactly equal current validator runtime",
            )

    def test_preface_detector_requires_independent_substantive_heading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "prefaces.pdf"
            writer = fixture_module.PdfWriter()
            texts = (
                "Preface\nThis thesis studies motion generation in a unified setting. "
                "It explains the research motivation, the connection among chapters, "
                "and the scope of the conclusions. These paragraphs are authored prose.",
                "Contents\nPreface 9\nChapter 1 Introduction 12\n1.1 Background 13",
                "Preface",
            )
            for value in texts:
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(writer, page, value)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            self.assertEqual(
                FULL_VALIDATOR_MODULE.detect_rendered_substantive_preface_pages(
                    pdf_path
                ),
                {1},
            )

    def test_manifest_preface_page_cannot_be_omitted_from_authored_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            with mock.patch.object(
                FULL_VALIDATOR_MODULE,
                "detect_rendered_substantive_preface_pages",
                return_value={1},
            ):
                self.assertEqual(
                    STAGE_P_MODULE.validate_stage_p(root, FULL_VALIDATOR_MODULE),
                    [],
                )
                manifest = root / "00-manifest.md"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8").replace(
                        "Authored-prose navigation pages: physical p.1",
                        "Authored-prose navigation pages: physical p.2",
                    ),
                    encoding="utf-8",
                )
                errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertTrue(
                any("omit independently rendered substantive preface" in error
                    for error in errors),
                errors,
            )

    def test_manifest_sections_rejects_numeric_false_positive_in_both_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_full_fixture(root)
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "- Sections: 1.1=physical p.3",
                    "- Sections: 0.14=physical p.1",
                ),
                encoding="utf-8",
            )
            self.assert_stage_p_and_full_fail(
                root,
                "Sections must exactly equal the rendered body-section map",
            )

    def test_manifest_sections_require_complete_exact_map_in_both_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            harness.build_bundle(root, page_count=3)
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "- Sections: 4.1=physical p.2",
                    "- Sections: none detected",
                ),
                encoding="utf-8",
            )
            self.assert_stage_p_and_full_fail(
                root,
                "Sections must exactly equal the rendered body-section map",
            )

    def test_mixed_cv_page_keeps_substantive_authored_prose_in_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "back-matter.pdf"
            writer = fixture_module.PdfWriter()
            texts = (
                "Curriculum Vitae\nEducation 2021-2026 Example University\n"
                "This thesis reorganizes the related methods and experiments around "
                "one research narrative. The author conducted the experiments, wrote "
                "the manuscript, and integrated the material into this dissertation.",
                "Curriculum Vitae\nEducation 2021-2026 Example University\n"
                "Publications\n1. Example Author. Example Paper. 2025.",
            )
            for value in texts:
                page = writer.add_blank_page(width=595.28, height=841.89)
                fixture_module.add_ascii_text(writer, page, value)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            self.assertEqual(
                FULL_VALIDATOR_MODULE.detect_rendered_substantive_authored_back_pages(
                    pdf_path
                ),
                {1},
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            with mock.patch.object(
                FULL_VALIDATOR_MODULE,
                "detect_rendered_substantive_authored_back_pages",
                return_value={4},
            ):
                errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertTrue(
                any("authored contribution/explanatory prose" in error
                    for error in errors),
                errors,
            )

    def test_authored_page_set_is_canonical_and_compact(self) -> None:
        parse = FULL_VALIDATOR_MODULE.parse_canonical_physical_page_set
        self.assertEqual(parse("physical p.1-3; physical p.7", 10), {1, 2, 3, 7})
        for malformed in (
            "physical p.1; physical p.2",
            "physical p.2; physical p.1",
            "physical p.0",
            "physical p.1-11",
            "p.1",
        ):
            with self.subTest(value=malformed):
                self.assertIsNone(parse(malformed, 10))

    def test_structural_heading_detector_rejects_toc_dot_leaders(self) -> None:
        detect = FULL_VALIDATOR_MODULE._has_rendered_structural_heading
        self.assertFalse(detect("附录 ................................ 149", "appendix"))
        self.assertFalse(detect("致谢 ……………… 151", "back"))
        self.assertFalse(
            detect("Acknowledgements ........................ 151", "back")
        )
        self.assertTrue(detect("附录\nA 补充实验", "appendix"))
        self.assertTrue(detect("致谢\n感谢所有帮助。", "back"))
        self.assertTrue(detect("Curriculum Vitae\nEducation", "back"))

    def test_scope_does_not_enumerate_or_open_peer_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_full_fixture(root)
            original_iterdir = Path.iterdir
            original_open = Path.open
            original_read_text = Path.read_text
            original_read_bytes = Path.read_bytes
            original_is_file = Path.is_file

            def guard(path: Path) -> None:
                if path.name in PEER_AND_DOWNSTREAM_FILES:
                    raise AssertionError(f"Stage-P gate touched peer path {path.name}")

            def guarded_iterdir(path: Path):
                if path.absolute() == root.absolute():
                    raise AssertionError("Stage-P gate enumerated the bundle root")
                return original_iterdir(path)

            def guarded_open(path: Path, *args, **kwargs):
                guard(path)
                return original_open(path, *args, **kwargs)

            def guarded_read_text(path: Path, *args, **kwargs):
                guard(path)
                return original_read_text(path, *args, **kwargs)

            def guarded_read_bytes(path: Path, *args, **kwargs):
                guard(path)
                return original_read_bytes(path, *args, **kwargs)

            def guarded_is_file(path: Path):
                guard(path)
                return original_is_file(path)

            with (
                mock.patch.object(Path, "iterdir", guarded_iterdir),
                mock.patch.object(Path, "open", guarded_open),
                mock.patch.object(Path, "read_text", guarded_read_text),
                mock.patch.object(Path, "read_bytes", guarded_read_bytes),
                mock.patch.object(Path, "is_file", guarded_is_file),
            ):
                errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertEqual([], errors)

    def test_reserved_process_basenames_are_rejected_without_touching_them(self) -> None:
        cases = (
            (
                "frozen PDF alias",
                "94-post-freeze-prior-issue-closure.md",
                lambda process, target: process.__setitem__(
                    "frozen_pdf_file", target
                ),
            ),
            (
                "governing-file alias",
                "R1-comprehensive-review.md",
                lambda process, target: process.__setitem__(
                    "governing_local_files",
                    [{
                        "neutral_file": target,
                        "official_title": "must not be opened",
                        "sha256": "A" * 64,
                    }],
                ),
            ),
        )
        for label, target, mutate in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_full_fixture(root)
                process_path = root / "00-process-parameters.json"
                process = json.loads(process_path.read_text(encoding="utf-8"))
                mutate(process, target)
                process_path.write_text(json.dumps(process), encoding="utf-8")
                original_lstat = Path.lstat
                original_open = Path.open
                original_read_text = Path.read_text
                original_read_bytes = Path.read_bytes
                original_is_file = Path.is_file

                def guard(path: Path) -> None:
                    if path.name == target:
                        raise AssertionError(f"reserved peer path was touched: {target}")

                def guarded_lstat(path: Path, *args, **kwargs):
                    guard(path)
                    return original_lstat(path, *args, **kwargs)

                def guarded_open(path: Path, *args, **kwargs):
                    guard(path)
                    return original_open(path, *args, **kwargs)

                def guarded_read_text(path: Path, *args, **kwargs):
                    guard(path)
                    return original_read_text(path, *args, **kwargs)

                def guarded_read_bytes(path: Path, *args, **kwargs):
                    guard(path)
                    return original_read_bytes(path, *args, **kwargs)

                def guarded_is_file(path: Path):
                    guard(path)
                    return original_is_file(path)

                with (
                    mock.patch.object(Path, "lstat", guarded_lstat),
                    mock.patch.object(Path, "open", guarded_open),
                    mock.patch.object(Path, "read_text", guarded_read_text),
                    mock.patch.object(Path, "read_bytes", guarded_read_bytes),
                    mock.patch.object(Path, "is_file", guarded_is_file),
                ):
                    errors = STAGE_P_MODULE.validate_stage_p(
                        root, FULL_VALIDATOR_MODULE
                    )
                self.assertTrue(
                    any(
                        "unsafe or" in error and "reserved" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_p_receipt_has_exact_validator_insertion_and_no_helper_probe(self) -> None:
        process = {
            "degree_level": "masters",
            "governing_local_files": [],
            "frozen_pdf_file": "frozen-thesis.pdf",
        }
        expected_pair = [
            "rules/scripts/validate_review_bundle.py",
            "rules/scripts/validate_stage_p_output.py",
        ]
        with mock.patch.object(
            FULL_VALIDATOR_MODULE,
            "helper_inputs_for_recipient",
            side_effect=AssertionError("P probed helpers"),
        ):
            opened = FULL_VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, 3, "P", Path("unused")
            )
        self.assertEqual(
            opened[2 + len(FULL_VALIDATOR_MODULE.SKILL_REFERENCE_FILES):][:2],
            expected_pair,
        )
        self.assertEqual(opened.count(expected_pair[0]), 1)
        self.assertEqual(opened.count(expected_pair[1]), 1)
        for actor in ("R1", "AI", "C", "S"):
            actor_opened = FULL_VALIDATOR_MODULE.canonical_stage_opened_inputs(
                process, 3, actor
            )
            self.assertNotIn(expected_pair[1], actor_opened)
        doctoral = dict(process)
        doctoral["degree_level"] = "doctorate"
        r5_opened = FULL_VALIDATOR_MODULE.canonical_stage_opened_inputs(
            doctoral, 5, "R5"
        )
        self.assertIn("rules/scripts/validate_r5_output.py", r5_opened)
        self.assertNotIn(expected_pair[1], r5_opened)

    def test_manifest_and_policy_each_require_both_validator_rules(self) -> None:
        for filename in ("00-manifest.md", "01-policy-basis.md"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_stage_p_only_fixture(root)
                path = root / filename
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "; rules/scripts/validate_stage_p_output.py", "", 1
                    ),
                    encoding="utf-8",
                )
                self.assert_stage_p_fails(
                    root,
                    "opened receipt must exactly equal the canonical ordered P allowlist",
                )

    def test_candidate_context_expansion_and_marker_mismatches_fail(self) -> None:
        cases = (
            (
                "comma expansion",
                lambda rows: rows.__setitem__(
                    1, {**rows[1], "ExpandedNumbers": "3,8"}
                ),
                "canonical semicolon-separated marker expansion",
            ),
            (
                "context",
                lambda rows: rows.__setitem__(
                    0,
                    {
                        **rows[0],
                        "AdjacentPDFText": rows[0]["AdjacentPDFText"] + " wrong",
                    },
                ),
                "deterministic frozen-PDF extraction window",
            ),
            (
                "marker",
                lambda rows: rows.__setitem__(
                    0,
                    {**rows[0], "Marker": "[2]", "ExpandedNumbers": "2"},
                ),
                "marker/expansion does not match the frozen-PDF extraction",
            ),
        )
        for label, mutate, needle in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_stage_p_only_fixture(root)
                path = root / "00-citation-candidate-ledger.csv"
                headers, rows = read_rows(path)
                mutate(rows)
                write_rows(path, headers, rows)
                self.assert_stage_p_fails(root, needle)

    def test_scoped_and_full_gates_share_exact_candidate_contract(self) -> None:
        cases = (
            (
                "pure source marker suppressed",
                lambda rows: rows[0].update({
                    "Classification": "non-citation",
                    "ClassificationEvidence": (
                        "local prose mentions a model or numeric specification"
                    ),
                    "MappedOccurrenceID": "N/A",
                }),
                "lacks a canonical predicate or the exact derived "
                "role token",
            ),
            (
                "derived non-citation role token mismatch",
                lambda rows: rows[1].__setitem__(
                    "ClassificationEvidence", "non-citation-role:coordinate"
                ),
                "lacks a canonical predicate or the exact derived "
                "role token",
            ),
            (
                "generic evidence",
                lambda rows: rows[0].__setitem__(
                    "ClassificationEvidence", "non-citation"
                ),
                "ClassificationEvidence is not a concrete contextual reason",
            ),
            (
                "noncanonical context bytes",
                lambda rows: rows[0].__setitem__(
                    "AdjacentPDFText",
                    rows[0]["AdjacentPDFText"].replace(
                        "fixture proposition", "fixture  proposition", 1
                    ),
                ),
                "AdjacentPDFText",
            ),
            (
                "noncanonical marker bytes",
                lambda rows: rows[1].__setitem__("Marker", "[3, 8]"),
                "Marker must equal its canonical whitespace/comma/dash normalization",
            ),
        )
        for label, mutate, needle in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_full_fixture(root)
                path = root / "00-citation-candidate-ledger.csv"
                headers, rows = read_rows(path)
                mutate(rows)
                write_rows(path, headers, rows)
                self.assert_stage_p_and_full_fail(root, needle)

    def test_rendered_bibliography_entry_is_pdf_bound_in_both_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_full_fixture(root)
            path = root / "00-bibliography-inventory.csv"
            headers, rows = read_rows(path)
            rows[0]["RenderedEntry"] += " fabricated"
            write_rows(path, headers, rows)
            self.assert_stage_p_and_full_fail(
                root, "RenderedEntry does not exactly equal"
            )

    def test_duplicate_rendered_entries_remain_a_reviewable_paper_defect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.rewrite_pdf_and_rehash(
                root,
                [
                    "CHINESE ABSTRACT\n"
                    "This synthetic Chinese abstract explains the research task, "
                    "method, and principal result. It supplies sustained authored "
                    "prose for independent semantic inspection. The fixture "
                    "proposition [1]; quantization levels are [3, 8]; scale interval "
                    "[0.85, 1].",
                    "ABSTRACT\n"
                    "This synthetic English abstract explains the research task, "
                    "method, and principal result. It contains sustained explanatory "
                    "prose for an independent semantic inspection. The evidence is "
                    "deliberately long enough to constitute authored abstract text.",
                    "CHAPTER 1\nFixture Method\n1.1 Introduction\n"
                    "This rendered body chapter explains the fixture method and result.",
                    "References\n[1] Duplicate reference.\n[2] Duplicate reference.",
                ],
            )
            write_rows(
                root / "00-bibliography-inventory.csv",
                list(FULL_VALIDATOR_MODULE.BIB_INVENTORY_COLUMNS),
                [
                    {
                        "ReferenceID": "REF0001",
                        "DisplayedLabel": "[1]",
                        "RenderedEntry": "Duplicate reference.",
                        "Cited": "yes",
                        "PDFSHA256": digest,
                    },
                    {
                        "ReferenceID": "REF0002",
                        "DisplayedLabel": "[2]",
                        "RenderedEntry": "Duplicate reference.",
                        "Cited": "no",
                        "PDFSHA256": digest,
                    },
                ],
            )
            self.refresh_process_identity(root)
            result = self.run_stage_p(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dangling_displayed_reference_remains_visible_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            harness = fixture_module.ValidateReviewBundleTests(
                methodName="test_complete_fixture_passes"
            )
            digest = harness.rewrite_pdf_and_rehash(
                root,
                [
                    "CHINESE ABSTRACT\n"
                    "This synthetic Chinese abstract explains the research task, "
                    "method, and principal result. It supplies sustained authored "
                    "prose for independent semantic inspection. The fixture "
                    "proposition [2]; quantization levels are [3, 8]; scale interval "
                    "[0.85, 1].",
                    "ABSTRACT\n"
                    "This synthetic English abstract explains the research task, "
                    "method, and principal result. It contains sustained explanatory "
                    "prose for an independent semantic inspection. The evidence is "
                    "deliberately long enough to constitute authored abstract text.",
                    "CHAPTER 1\nFixture Method\n1.1 Introduction\n"
                    "This rendered body chapter explains the fixture method and result.",
                    "References\n[1] Fixture reference.",
                ],
            )
            extraction_errors: list[str] = []
            extracted, unmatched = FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates(
                root / "frozen-thesis.pdf", {4}, extraction_errors
            )
            self.assertEqual([], extraction_errors)
            self.assertEqual([], unmatched)
            candidate_path = root / "00-citation-candidate-ledger.csv"
            candidate_headers, candidate_rows = read_rows(candidate_path)
            for row, source in zip(candidate_rows, extracted, strict=True):
                row["Marker"] = source["Marker"]
                row["ExpandedNumbers"] = (
                    "N/A" if source["Expanded"] is None
                    else ";".join(str(value) for value in source["Expanded"])
                )
                row["AdjacentPDFText"] = source["Adjacent"]
                row["PDFSHA256"] = digest
            write_rows(candidate_path, candidate_headers, candidate_rows)
            citation_path = root / "00-citation-inventory.csv"
            citation_headers, citation_rows = read_rows(citation_path)
            citation_rows[0]["DisplayedReferenceID"] = "REF0002"
            citation_rows[0]["AdjacentPDFText"] = extracted[0]["Adjacent"]
            citation_rows[0]["PDFSHA256"] = digest
            write_rows(citation_path, citation_headers, citation_rows)
            bibliography_path = root / "00-bibliography-inventory.csv"
            bibliography_headers, bibliography_rows = read_rows(bibliography_path)
            bibliography_rows[0]["Cited"] = "no"
            bibliography_rows[0]["PDFSHA256"] = digest
            write_rows(bibliography_path, bibliography_headers, bibliography_rows)
            self.refresh_process_identity(root)
            result = self.run_stage_p(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pair_ids_support_one_hundred_sources_and_numeric_sorting(self) -> None:
        self.assertIsNotNone(FULL_VALIDATOR_MODULE.PAIR_ID_RE.fullmatch("C0001-S100"))
        self.assertLess(
            FULL_VALIDATOR_MODULE.pair_id_sort_key("C0001-S99"),
            FULL_VALIDATOR_MODULE.pair_id_sort_key("C0001-S100"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = "A" * 64
            numbers = list(range(1, 101))
            context = "claim supported by the complete source range [1-100]"
            write_rows(
                root / "00-citation-candidate-ledger.csv",
                list(FULL_VALIDATOR_MODULE.CITATION_CANDIDATE_COLUMNS),
                [{
                    "CandidateID": "BC0001",
                    "PhysicalPage": "1",
                    "Marker": "[1-100]",
                    "ExpandedNumbers": ";".join(str(value) for value in numbers),
                    "Classification": "citation",
                    "ClassificationEvidence": "source marker attached to the claim",
                    "MappedOccurrenceID": "C0001",
                    "AdjacentPDFText": context,
                    "PDFSHA256": digest,
                }],
            )
            write_rows(
                root / "00-unmatched-bracket-ledger.csv",
                list(FULL_VALIDATOR_MODULE.UNMATCHED_BRACKET_COLUMNS),
                [],
            )
            write_rows(
                root / "00-citation-inventory.csv",
                list(FULL_VALIDATOR_MODULE.CITATION_INVENTORY_COLUMNS),
                [{
                    "PairID": f"C0001-S{index:02d}",
                    "OccurrenceID": "C0001",
                    "PDFLocation": "physical p.1",
                    "DisplayedReferenceID": f"REF{index:04d}",
                    "AdjacentPDFText": context,
                    "PDFSHA256": digest,
                } for index in numbers],
            )
            bibliography = [{
                "ReferenceID": f"REF{index:04d}",
                "DisplayedLabel": f"[{index}]",
                "RenderedEntry": f"Reference {index}.",
                "Cited": "yes",
                "PDFSHA256": digest,
            } for index in numbers]
            errors: list[str] = []
            extracted = [{
                "PhysicalPage": 1,
                "Marker": "[1-100]",
                "Expanded": numbers,
                "Adjacent": context,
                "Prefix": "claim cites the following sources ",
            }]
            with (
                mock.patch.object(
                    FULL_VALIDATOR_MODULE,
                    "derive_and_validate_reference_pages",
                    return_value=set(),
                ),
                mock.patch.object(
                    FULL_VALIDATOR_MODULE,
                    "extract_numeric_bracket_candidates",
                    return_value=(extracted, []),
                ),
                mock.patch.object(
                    FULL_VALIDATOR_MODULE,
                    "validate_pdf_derived_page_regions",
                ),
                mock.patch.object(FULL_VALIDATOR_MODULE, "validate_manifest"),
            ):
                STAGE_P_MODULE.validate_packet_reconciliation(
                    FULL_VALIDATOR_MODULE,
                    root,
                    {"governing_rule_urls": []},
                    root / "unused.pdf",
                    digest,
                    1,
                    5,
                    [{
                        "PageID": "P0001",
                        "PhysicalPage": "1",
                        "PrintedPage": "",
                        "Region": "chapter",
                        "MechanicalSignals": "none",
                        "PDFSHA256": digest,
                    }],
                    bibliography,
                    errors,
                )
            self.assertEqual([], errors)

    def test_citation_inventory_pair_page_reference_and_context_must_match(self) -> None:
        cases = (
            (
                "reference order",
                "DisplayedReferenceID",
                "REF0002",
                "citation candidate-to-inventory number mismatch",
            ),
            (
                "physical page",
                "PDFLocation",
                "physical p.2",
                "PDFLocation page does not match the mapped candidate",
            ),
            (
                "candidate context",
                "AdjacentPDFText",
                "wrong occurrence context",
                "AdjacentPDFText does not equal the mapped candidate context",
            ),
        )
        for label, field, value, needle in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.build_stage_p_only_fixture(root)
                path = root / "00-citation-inventory.csv"
                headers, rows = read_rows(path)
                rows[0][field] = value
                write_rows(path, headers, rows)
                self.assert_stage_p_fails(root, needle)

    def test_unmatched_glyph_context_is_reconciled_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(encoding="utf-8")
            )
            digest = process["selected_pdf_sha256"]
            write_rows(
                root / "00-unmatched-bracket-ledger.csv",
                list(FULL_VALIDATOR_MODULE.UNMATCHED_BRACKET_COLUMNS),
                [{
                    "GlyphID": "UBG0001",
                    "PhysicalPage": "1",
                    "Glyph": "[",
                    "AdjacentPDFText": "wrong deterministic context",
                    "Disposition": "rendered extraction artifact adjudicated manually",
                    "PDFSHA256": digest,
                }],
            )
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace(
                    "- Unmatched square-bracket glyphs: 0",
                    "- Unmatched square-bracket glyphs: 1",
                )
                .replace(
                    "- Unmatched glyph dispositions: No unmatched glyph was found in the rendered fixture page.",
                    "- Unmatched glyph dispositions: 1 glyph is adjudicated in 00-unmatched-bracket-ledger.csv.",
                ),
                encoding="utf-8",
            )
            original_extract = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates
            )

            def injected_extract(pdf_path, reference_pages, errors):
                candidates, _unmatched = original_extract(
                    pdf_path, reference_pages, errors
                )
                return candidates, [{
                    "PhysicalPage": 1,
                    "Glyph": "[",
                    "Adjacent": "expected deterministic context",
                }]

            with mock.patch.object(
                FULL_VALIDATOR_MODULE,
                "extract_numeric_bracket_candidates",
                side_effect=injected_extract,
            ):
                errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertTrue(
                any(
                    "00-unmatched-bracket-ledger.csv:2: AdjacentPDFText"
                    in error
                    for error in errors
                ),
                errors,
            )

    def test_half_open_interval_rejects_contradictory_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            process = json.loads(
                (root / "00-process-parameters.json").read_text(
                    encoding="utf-8"
                )
            )
            digest = process["selected_pdf_sha256"]
            context = "gamma in (0, 1] is the discount factor"
            write_rows(
                root / "00-unmatched-bracket-ledger.csv",
                list(FULL_VALIDATOR_MODULE.UNMATCHED_BRACKET_COLUMNS),
                [{
                    "GlyphID": "UBG0001",
                    "PhysicalPage": "1",
                    "Glyph": "]",
                    "AdjacentPDFText": context,
                    "Disposition": (
                        "visible role: extracted display-equation delimiter"
                    ),
                    "PDFSHA256": digest,
                }],
            )
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace(
                    "- Unmatched square-bracket glyphs: 0",
                    "- Unmatched square-bracket glyphs: 1",
                )
                .replace(
                    "- Unmatched glyph dispositions: No unmatched glyph was found in the rendered fixture page.",
                    "- Unmatched glyph dispositions: 1 glyph is adjudicated in 00-unmatched-bracket-ledger.csv.",
                ),
                encoding="utf-8",
            )
            original_extract = (
                FULL_VALIDATOR_MODULE.extract_numeric_bracket_candidates
            )

            def injected_extract(pdf_path, reference_pages, errors):
                candidates, _unmatched = original_extract(
                    pdf_path, reference_pages, errors
                )
                return candidates, [{
                    "PhysicalPage": 1,
                    "Glyph": "]",
                    "Adjacent": context,
                    "CanonicalRole": "half-open-mathematical-interval",
                }]

            with mock.patch.object(
                FULL_VALIDATOR_MODULE,
                "extract_numeric_bracket_candidates",
                side_effect=injected_extract,
            ):
                errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertTrue(
                any(
                    "Disposition must equal "
                    "'visible-role:half-open-mathematical-interval'"
                    in error
                    for error in errors
                ),
                errors,
            )

            headers, rows = read_rows(
                root / "00-unmatched-bracket-ledger.csv"
            )
            rows[0]["Disposition"] = (
                FULL_VALIDATOR_MODULE.HALF_OPEN_INTERVAL_DISPOSITION
            )
            write_rows(
                root / "00-unmatched-bracket-ledger.csv", headers, rows
            )
            with mock.patch.object(
                FULL_VALIDATOR_MODULE,
                "extract_numeric_bracket_candidates",
                side_effect=injected_extract,
            ):
                corrected_errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertEqual([], corrected_errors)

    def test_planned_stage_v_does_not_probe_stage_v_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            process_path = root / "00-process-parameters.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process["actor_prompt_sha256"]["V"] = "F" * 64
            process_path.write_text(json.dumps(process), encoding="utf-8")
            process_digest = hashlib.sha256(process_path.read_bytes()).hexdigest().upper()
            manifest = root / "00-manifest.md"
            manifest.write_text(
                re.sub(
                    r"(?m)^- Process-parameter file and SHA-256: .*$",
                    "- Process-parameter file and SHA-256: "
                    f"00-process-parameters.json / {process_digest}",
                    manifest.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            original_is_file = Path.is_file

            def guarded_is_file(path: Path):
                if path.name == "94-post-freeze-prior-issue-closure.md":
                    raise AssertionError("Stage-P gate probed Stage V")
                return original_is_file(path)

            with mock.patch.object(Path, "is_file", guarded_is_file):
                errors = STAGE_P_MODULE.validate_stage_p(
                    root, FULL_VALIDATOR_MODULE
                )
            self.assertEqual([], errors)

    def test_missing_owned_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_stage_p_only_fixture(root)
            (root / "00-citation-inventory.csv").unlink()
            self.assert_stage_p_fails(
                root, "missing or unsafe exact Stage-P path: 00-citation-inventory.csv"
            )

    def test_documented_contract_exposes_exact_extraction_and_pass_gate(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        ledger_text = (
            skill_root / "references" / "ledger-validation.md"
        ).read_text(encoding="utf-8")
        template_text = (
            skill_root / "references" / "report-template.md"
        ).read_text(encoding="utf-8")
        for text in (skill_text, ledger_text, template_text):
            self.assertIn("validate_stage_p_output.py", text)
        self.assertIn("PdfReader(..., strict=False)", skill_text)
        self.assertIn("semicolon-separated", skill_text)
        self.assertIn("PDF-derived boundaries", skill_text)
        self.assertIn("explicit chapter number must match", template_text)
        self.assertIn("shared Stage-P/full validator", ledger_text)
        self.assertIn("unpinned `uv --with pypdf`", skill_text)
        self.assertIn("PDF extraction runtime", template_text)
        self.assertIn("pypdf.__version__", ledger_text)
        self.assertIn("first nonempty stdout line is exactly `PASS`", skill_text)


if __name__ == "__main__":
    unittest.main()
