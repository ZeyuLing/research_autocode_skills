from __future__ import annotations

import binascii
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compile_paper as compile_paper_module  # noqa: E402
import validate_project as validate_project_module  # noqa: E402
from validate_project import (  # noqa: E402
    has_draft_marker,
    paperjury_bind_blocking_findings,
    paperjury_ledger_facts,
    paperjury_review_tree_sha256,
    render_paperjury_ledger,
    validate_figures,
    validate_qualitative_figure_bindings,
    validate_no_alternate_figure_backends,
    validate_compiler_log_binding,
    validate_layout_report_status,
    validate_aux_binding,
    validate_media_box_overflow_report,
    validate_overfull_box_report,
    validate_paperjury_review,
    validate_paperjury_major_finding,
    validate_recomputed_layout_audits,
    validate_selection_binding,
    validate_tex_fuzz_binding,
    validate_title,
)
from compile_paper import (  # noqa: E402
    aux_label_page,
    body_float_inventory,
    body_float_labels,
    body_float_tail_report,
    clean_core_build_artifacts,
    command_for,
    document_column_mode_audit,
    float_distribution_audit,
    float_reading_order_violations_from_pages,
    infer_column_mode_from_pages,
    latex_overfull_boxes,
    manual_pagination_commands,
    manuscript_structure_audit,
    media_box_overflows_from_boxes,
    page_geometry_from_boxes,
    rendered_whitespace_audit,
    sha256_file,
    source_tree_sha256,
    teaser_placement_audit,
    tex_fuzz_register_uses,
)
from select_venue import load_registry  # noqa: E402
from todo_lint import lint_directory  # noqa: E402


def run_script(name: str, *arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *(str(argument) for argument in arguments)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def make_png(width: int = 512, height: int = 256) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    scanlines = b"".join(b"\x00" + (b"\x80\x90\xa0\xff" * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def make_minimal_pdf() -> bytes:
    """Create one parseable text PDF without a PDF-writing dependency."""

    stream = b"BT /F1 12 Tf 72 720 Td (Layout integration smoke test) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(payload)


def make_paperjury_rounds(
    project: Path,
    *,
    first_round_blocker: dict[str, str] | None = None,
    final_round_minor: dict[str, str] | None = None,
) -> None:
    paper = project / "paper"
    root = project / "qa/paperjury"
    paper.mkdir(parents=True)
    root.mkdir(parents=True)
    (paper / "main.tex").write_text("Final paper.\n", encoding="utf-8")
    ledger = {
        "schema": 1,
        "meta": {
            "manuscript": str(paper),
            "venue_family": "ml",
            "created_round": 1,
            "assignment_unverified": [],
        },
        "issues": [],
    }
    ledger_path = root / "LEDGER.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    ledger_errors: list[str] = []
    facts = paperjury_ledger_facts(ledger, ledger_path, ledger_errors)
    if ledger_errors:
        raise AssertionError(ledger_errors)
    (root / "LEDGER.md").write_text(
        render_paperjury_ledger(ledger, facts), encoding="utf-8"
    )

    for round_number in (1, 2):
        round_path = root / f"round_{round_number:02d}"
        snapshot = round_path / "snapshot"
        snapshot.mkdir(parents=True)
        (snapshot / "main.tex").write_text("Final paper.\n", encoding="utf-8")
        reviewer_hashes: dict[str, str] = {}
        total_blocking = 0
        total_minor = 0
        all_pass = True
        for lens in ("claims", "design", "repro"):
            majors = (
                [first_round_blocker]
                if round_number == 1 and lens == "claims" and first_round_blocker
                else []
            )
            minors = (
                [final_round_minor]
                if round_number == 2 and lens == "claims" and final_round_minor
                else []
            )
            status = "pass" if not majors and not minors else "revise"
            reviewer = {
                "schema_version": 2,
                "reviewer_id": f"r{round_number}_{lens}",
                "status": status,
                "blocking_major_findings": majors,
                "minor_findings": minors,
                "queued_empirical": [],
                "verdict_rationale": "Independent review complete.",
            }
            reviewer_path = round_path / f"reviewer_{lens}.json"
            reviewer_path.write_text(json.dumps(reviewer), encoding="utf-8")
            reviewer_hashes[reviewer_path.name] = sha256_file(reviewer_path)
            total_blocking += len(majors)
            total_minor += len(minors)
            all_pass = all_pass and status == "pass"
        del total_minor
        (round_path / "round_report.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "round": round_number,
                    "snapshot_sha256": paperjury_review_tree_sha256(snapshot),
                    "reviewer_count": 3,
                    "reviewer_files": reviewer_hashes,
                    "blocking_major_findings": total_blocking,
                    "status": "pass" if all_pass else "revise",
                }
            ),
            encoding="utf-8",
        )
    (root / "final_report.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "mode": "review",
                "author_authorized": True,
                "rounds": 2,
                "reviewer_count": 3,
                "converged": True,
                "gate_blocking_major": 0,
                "unadjudicated_major": 0,
                "source_sha256": source_tree_sha256(paper),
                "review_snapshot_sha256": paperjury_review_tree_sha256(paper),
            }
        ),
        encoding="utf-8",
    )


class Idea2PaperScriptTests(unittest.TestCase):
    def test_todo_registry_uses_snapshot_portable_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "portable-todos"
            paper = project / "paper"
            section = paper / "sections"
            section.mkdir(parents=True)
            (project / "qa").mkdir()
            (section / "experiments.tex").write_text(
                "\\PredResult{RESULT-01}{42}\\n"
                "% TODO(RESULT-01): Replace with the measured value.\\n",
                encoding="utf-8",
            )
            report = lint_directory(paper)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["root"], ".")
            item = report["items"][0]
            self.assertEqual(
                item["macro_occurrences"][0]["file"],
                "sections/experiments.tex",
            )
            self.assertEqual(
                item["todo_occurrences"][0]["file"],
                "sections/experiments.tex",
            )
            self.assertNotIn(str(paper), json.dumps(report))
            registry = project / "qa" / "todo_registry.json"
            registry.write_text(json.dumps(report), encoding="utf-8")
            errors: list[str] = []
            validate_project_module.validate_todo_registry(project, report, errors)
            self.assertEqual(errors, [])
            stale = json.loads(json.dumps(report))
            stale["items"][0]["todo_occurrences"][0]["line"] += 1
            registry.write_text(json.dumps(stale), encoding="utf-8")
            errors = []
            validate_project_module.validate_todo_registry(project, report, errors)
            self.assertTrue(any("does not exactly match" in error for error in errors))

    def test_compile_log_overfull_audit_blocks_material_clipping(self) -> None:
        diagnostics = latex_overfull_boxes(
            "Overfull \\hbox (233.5427pt too wide) detected at line 122\n"
            "Overfull \\hbox (1.41768pt too wide) in paragraph at lines 383--383\n"
            "Overfull \\vbox (3.25pt too high) has occurred while \\output is active\n"
            "Overfull \\hbox (2.0pt too wide) at the exact threshold\n"
        )
        self.assertEqual(len(diagnostics), 4)
        self.assertEqual(diagnostics[0]["axis"], "h")
        self.assertTrue(diagnostics[0]["material"])
        self.assertFalse(diagnostics[1]["material"])
        self.assertEqual(diagnostics[2]["dimension"], "high")
        self.assertTrue(diagnostics[2]["material"])
        self.assertFalse(diagnostics[3]["material"])

    def test_overfull_validator_derives_material_and_binds_the_log(self) -> None:
        material = latex_overfull_boxes(
            "Overfull \\hbox (233.5427pt too wide) detected at line 122\n"
        )
        report = {
            "overfull_box_threshold_pt": 2.0,
            "overfull_boxes": material,
            "material_overfull_boxes": [],
        }
        errors: list[str] = []
        validate_overfull_box_report(report, errors)
        self.assertTrue(any("not exactly derived" in error for error in errors))
        self.assertTrue(any("clipped/material" in error for error in errors))

        report["overfull_boxes"][0]["material"] = False
        errors = []
        validate_overfull_box_report(report, errors)
        self.assertTrue(any("fixed 2pt threshold" in error for error in errors))

        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "main.log"
            log.write_text(
                "Overfull \\hbox (233.5427pt too wide) detected at line 122\n",
                encoding="utf-8",
            )
            clean_report = {
                "overfull_box_threshold_pt": 2.0,
                "overfull_boxes": [],
                "material_overfull_boxes": [],
            }
            errors = []
            validate_overfull_box_report(clean_report, errors, log)
            self.assertTrue(any("do not match compiler log" in error for error in errors))

    def test_passing_layout_report_requires_empty_errors(self) -> None:
        errors: list[str] = []
        validate_layout_report_status(
            {"status": "pass", "returncode": 0, "errors": ["hidden failure"]}, errors
        )
        self.assertTrue(any("errors=[]" in error for error in errors))

    def test_tex_fuzz_registers_are_location_bound_across_active_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            sections = paper / "sections"
            sections.mkdir()
            (paper / "main.tex").write_text(
                "\\documentclass{article}\n"
                "\\usepackage{venue}\n"
                "\\begin{document}\n"
                "\\input{sections/body}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            (sections / "body.tex").write_text(
                "Safe text.\n  \\hfuzz=300pt\n% \\vfuzz=ignored\n", encoding="utf-8"
            )
            (paper / "venue.sty").write_text(
                "% template comment\n\\vfuzz=30pt\n", encoding="utf-8"
            )
            uses = tex_fuzz_register_uses(paper)
            self.assertEqual(
                uses,
                [
                    {
                        "path": "sections/body.tex",
                        "line": 2,
                        "column": 3,
                        "command": "\\hfuzz",
                    },
                    {
                        "path": "venue.sty",
                        "line": 2,
                        "column": 1,
                        "command": "\\vfuzz",
                    },
                ],
            )
            with mock.patch.object(
                compile_paper_module,
                "_official_template_asset_hashes",
                return_value={sha256_file(paper / "venue.sty")},
            ):
                bound_uses = tex_fuzz_register_uses(paper)
            self.assertEqual(bound_uses, [uses[0]])
            errors: list[str] = []
            validate_tex_fuzz_binding(paper, {"tex_fuzz_register_uses": uses}, errors)
            self.assertTrue(any("forbidden" in error for error in errors))

    def test_fresh_build_cleanup_and_log_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            build = project / "build"
            build.mkdir()
            for name in ("main.pdf", "main.log", "main.aux", "main.fdb_latexmk"):
                (build / name).write_text("stale", encoding="utf-8")
            unrelated = build / "keep.me"
            unrelated.write_text("preserve", encoding="utf-8")
            removed = clean_core_build_artifacts(build)
            self.assertEqual(
                set(removed), {"main.pdf", "main.log", "main.aux", "main.fdb_latexmk"}
            )
            self.assertTrue(unrelated.is_file())
            self.assertFalse((build / "main.log").exists())
            self.assertIn("-g", command_for("latexmk", project, build))

            log = build / "main.log"
            log.write_text("fresh compiler log\n", encoding="utf-8")
            report = {
                "build_dir": str(build),
                "fresh_build": True,
                "fresh_build_removed_artifacts": removed,
                "compiler_log": str(log),
                "compiler_log_sha256": sha256_file(log),
            }
            errors: list[str] = []
            self.assertEqual(validate_compiler_log_binding(project, report, errors), log)
            self.assertEqual(errors, [])
            report["compiler_log_sha256"] = "0" * 64
            errors = []
            self.assertIsNone(validate_compiler_log_binding(project, report, errors))
            self.assertTrue(any("hash mismatch" in error for error in errors))

    def test_layout_validator_binds_aux_and_recomputes_forged_float_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paper = project / "paper"
            build = project / "build"
            paper.mkdir()
            build.mkdir()
            (paper / "main.tex").write_text(
                "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n",
                encoding="utf-8",
            )
            aux = build / "main.aux"
            aux.write_text(
                "\\newlabel{fig:real}{{1}{2}}\n"
                "\\newlabel{idea2paper:start-conclusion}{{}{3}}\n"
                "\\newlabel{idea2paper:end-body}{{}{3}}\n"
                "\\newlabel{idea2paper:end-exempt}{{}{3}}\n"
                "\\newlabel{idea2paper:end-references}{{}{3}}\n"
                "\\newlabel{idea2paper:start-appendix}{{}{3}}\n",
                encoding="utf-8",
            )
            pdf = build / "main.pdf"
            pdf.write_bytes(make_minimal_pdf())
            column_audit = document_column_mode_audit(paper, "auto")
            inventory = {
                "records": [
                    {
                        "float_index": 1,
                        "region": "body",
                        "path": "main.tex",
                        "line": 3,
                        "labels": ["fig:real"],
                    }
                ],
                "labels": ["fig:real"],
                "all_records": [
                    {
                        "float_index": 1,
                        "region": "body",
                        "path": "main.tex",
                        "line": 3,
                        "labels": ["fig:real"],
                    }
                ],
                "all_labels": ["fig:real"],
            }
            fake_whitespace = {
                "page_count": 3,
                "rendered_column_inference": {
                    "mode": 1,
                    "confidence": 1.0,
                    "inspected_pages": 3,
                    "eligible_text_rows": 30,
                    "split_gutter_rows": 0,
                    "split_gutter_ratio": 0.0,
                },
                "thresholds": {"media_box_overflow_maximum_pt": 2.0},
                "pages": [],
                "media_box_overflows": [],
                "whitespace_violations": [],
            }
            forged_distribution = float_distribution_audit(
                inventory["all_records"], {"fig:real": 1}, 3, 3, 1
            )
            report = {
                "build_dir": str(build),
                "aux": str(aux),
                "aux_sha256": sha256_file(aux),
                "column_mode": 1,
                "column_mode_audit": column_audit,
                "references_counted": False,
                "body_pages": 3,
                "conclusion_page": 3,
                "end_body_page": 3,
                "end_exempt_page": 3,
                "appendix_start_page": 3,
                "conclusion_before_end_body": True,
                "body_float_pages": {"fig:real": 1},
                "all_float_pages": {"fig:real": 1},
                "missing_body_float_aux_labels": [],
                "missing_all_float_aux_labels": [],
                "body_float_tail_violations": [],
                "total_pages": 3,
                **forged_distribution,
                "rendered_column_inference": fake_whitespace["rendered_column_inference"],
                "rendered_page_geometry": [],
                "whitespace_thresholds": fake_whitespace["thresholds"],
                "whitespace_violations": [],
                "media_box_overflows": [],
            }
            binding_errors: list[str] = []
            self.assertEqual(validate_aux_binding(project, report, binding_errors), aux)
            self.assertEqual(binding_errors, [])
            report["aux_sha256"] = "0" * 64
            tampered_errors: list[str] = []
            self.assertIsNone(validate_aux_binding(project, report, tampered_errors))
            self.assertTrue(any("AUX hash mismatch" in error for error in tampered_errors))
            report["aux_sha256"] = sha256_file(aux)

            errors: list[str] = []
            with mock.patch.object(
                validate_project_module,
                "rendered_whitespace_audit",
                return_value=fake_whitespace,
            ):
                validate_recomputed_layout_audits(
                    project, report, inventory, aux, pdf, errors
                )
            self.assertTrue(any("body_float_pages" in error for error in errors))
            self.assertTrue(any("page_float_counts" in error for error in errors))

    def test_compile_main_fresh_log_gate_blocks_233pt_but_not_1pt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paper = project / "paper"
            sections = paper / "sections"
            appendix = paper / "appendix"
            build = project / "build"
            sections.mkdir(parents=True)
            appendix.mkdir()
            build.mkdir()
            (paper / "references.bib").write_text("", encoding="utf-8")
            (sections / "body.tex").write_text("Body.\n", encoding="utf-8")
            (sections / "conclusion.tex").write_text(
                "\\section{Conclusion}\n\\label{idea2paper:start-conclusion}\n",
                encoding="utf-8",
            )
            (sections / "ai_use_statement.tex").write_text(
                "\\subsection*{AI use statement}\nDisclosure.\n", encoding="utf-8"
            )
            (appendix / "appendix.tex").write_text(
                "\\appendix\n\\label{idea2paper:start-appendix}\n"
                "\\section{Additional Material}\n",
                encoding="utf-8",
            )
            (paper / "main.tex").write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\input{sections/body}\n"
                "\\input{sections/conclusion}\n"
                "\\label{idea2paper:end-body}\n"
                "\\input{sections/ai_use_statement}\n"
                "\\label{idea2paper:end-exempt}\n"
                "{\\small\\bibliographystyle{plain}\\bibliography{references}}\n"
                "\\label{idea2paper:end-references}\n"
                "\\input{appendix/appendix}\n\\end{document}\n",
                encoding="utf-8",
            )
            self.assertEqual(manuscript_structure_audit(paper)["errors"], [])
            aux_text = (
                "\\newlabel{idea2paper:start-conclusion}{{}{1}}\n"
                "\\newlabel{idea2paper:end-body}{{}{1}}\n"
                "\\newlabel{idea2paper:end-exempt}{{}{1}}\n"
                "\\newlabel{idea2paper:end-references}{{}{1}}\n"
                "\\newlabel{idea2paper:start-appendix}{{}{1}}\n"
            )
            log_holder = {"text": ""}
            unrelated = build / "keep.me"
            unrelated.write_text("preserve", encoding="utf-8")

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                self.assertFalse((build / "main.log").exists())
                self.assertFalse((build / "main.pdf").exists())
                self.assertFalse((build / "main.aux").exists())
                (build / "main.log").write_text(log_holder["text"], encoding="utf-8")
                (build / "main.pdf").write_bytes(make_minimal_pdf())
                (build / "main.aux").write_text(aux_text, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            whitespace = {
                "page_count": 1,
                "rendered_column_inference": {
                    "mode": 1,
                    "confidence": 1.0,
                    "inspected_pages": 1,
                    "eligible_text_rows": 1,
                    "split_gutter_rows": 0,
                    "split_gutter_ratio": 0.0,
                },
                "thresholds": {"media_box_overflow_maximum_pt": 2.0},
                "pages": [{"page": 1, "media_box_overflows": [], "violations": []}],
                "media_box_overflows": [],
                "whitespace_violations": [],
            }
            cases = [
                (
                    "Overfull \\hbox (233.5427pt too wide) detected at line 122\n"
                    "Overfull \\hbox (1.41768pt too wide) at lines 383--383\n",
                    1,
                ),
                ("Overfull \\hbox (1.41768pt too wide) at lines 383--383\n", 0),
            ]
            for log_text, expected_returncode in cases:
                with self.subTest(log_text=log_text):
                    for name in ("main.log", "main.pdf", "main.aux"):
                        (build / name).write_text("stale", encoding="utf-8")
                    log_holder["text"] = log_text
                    output = io.StringIO()
                    with (
                        mock.patch.object(
                            compile_paper_module,
                            "choose_engine",
                            return_value=str(project / "tectonic.exe"),
                        ),
                        mock.patch.object(compile_paper_module, "pdf_pages", return_value=1),
                        mock.patch.object(
                            compile_paper_module,
                            "rendered_whitespace_audit",
                            return_value=whitespace,
                        ),
                        mock.patch.object(
                            compile_paper_module.subprocess, "run", side_effect=fake_run
                        ),
                        mock.patch.object(
                            sys,
                            "argv",
                            [
                                "compile_paper.py",
                                str(paper),
                                "--engine",
                                "tectonic",
                                "--build-dir",
                                str(build),
                            ],
                        ),
                        contextlib.redirect_stdout(output),
                    ):
                        returncode = compile_paper_module.main()
                    report = json.loads(output.getvalue())
                    self.assertEqual(returncode, expected_returncode)
                    self.assertEqual(report["schema_version"], 10)
                    self.assertEqual(report["aux"], str(build / "main.aux"))
                    self.assertTrue(report["fresh_build"])
                    self.assertEqual(report["compiler_log_sha256"], sha256_file(build / "main.log"))
                    self.assertTrue(unrelated.is_file())
                    self.assertEqual(report["overfull_boxes"][0]["excess_pt"], float(log_text.split("(", 1)[1].split("pt", 1)[0]))
                    if expected_returncode == 0:
                        self.assertEqual(report["errors"], [])
                        self.assertEqual(report["material_overfull_boxes"], [])
                    else:
                        self.assertEqual(report["material_overfull_boxes"][0]["excess_pt"], 233.5427)

    def test_compile_helpers_keep_intermediates_and_read_body_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aux = root / "main.aux"
            aux.write_text(
                "\\newlabel{idea2paper:end-body}{{}{8}}\n"
                "\\newlabel{idea2paper:end-references}{{}{10}}\n",
                encoding="utf-8",
            )
            self.assertEqual(aux_label_page(aux, "idea2paper:end-body"), 8)
            self.assertEqual(aux_label_page(aux, "idea2paper:end-references"), 10)
            command = command_for("tectonic", root, root / "build")
            self.assertIn("--keep-intermediates", command)
            paper = root / "paper"
            paper.mkdir()
            source = paper / "main.tex"
            source.write_text("first", encoding="utf-8")
            first_hash = source_tree_sha256(paper)
            source.write_text("second", encoding="utf-8")
            self.assertNotEqual(first_hash, source_tree_sha256(paper))
            ltx = paper / "body.ltx"
            ltx.write_text("first", encoding="utf-8")
            ltx_hash = source_tree_sha256(paper)
            ltx.write_text("second", encoding="utf-8")
            self.assertNotEqual(ltx_hash, source_tree_sha256(paper))
            figure = paper / "figure.pdf"
            figure.write_bytes(b"first")
            figure_hash = source_tree_sha256(paper)
            figure.write_bytes(b"second")
            self.assertNotEqual(figure_hash, source_tree_sha256(paper))

    def test_layout_gate_rejects_manual_breaks_and_post_conclusion_body_floats(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary) / "paper"
            sections = paper / "sections"
            appendix = paper / "appendix"
            sections.mkdir(parents=True)
            appendix.mkdir()
            body = sections / "experiments.tex"
            body.write_text(
                "% \\clearpage is only documentation\n"
                "\\begin{IdeaTwoPaperTitleTeaser}{caption}{fig:teaser}"
                "\nx\\end{IdeaTwoPaperTitleTeaser}\n"
                "\\begin{figure}[t]\\caption{x}\\label{fig:late}\\end{figure}\n"
                "\\begin{minipage}{\\linewidth}\\captionof{table}{x}"
                "\\label{tab:anchored}\\end{minipage}\n",
                encoding="utf-8",
            )
            appended = appendix / "appendix.tex"
            appended.write_text(
                "\\appendix\n"
                "\\label{idea2paper:start-appendix}\n"
                "\\begin{figure}[t]\\label{fig:appendix-only}\\end{figure}\n",
                encoding="utf-8",
            )
            (paper / "references.bib").write_text("", encoding="utf-8")
            (sections / "conclusion.tex").write_text(
                "\\section{Conclusion}\n"
                "\\label{idea2paper:start-conclusion}\n",
                encoding="utf-8",
            )
            (paper / "unused-draft.tex").write_text("\\clearpage\n", encoding="utf-8")
            (paper / "main.tex").write_text(
                "\\input sections/experiments.tex\n"
                "\\input{sections/conclusion}\n"
                "\\label{idea2paper:end-body}\n"
                "\\label{idea2paper:end-exempt}\n"
                "\\bibliography{references}\n"
                "\\label{idea2paper:end-references}\n"
                "\\input{appendix/appendix}\n",
                encoding="utf-8",
            )
            self.assertEqual(manual_pagination_commands(paper), [])
            self.assertEqual(
                body_float_labels(paper), ["fig:late", "fig:teaser", "tab:anchored"]
            )
            inventory = body_float_inventory(paper)
            self.assertEqual(inventory["unlabeled"], [])
            self.assertEqual(
                [item["placement"] for item in inventory["records"]],
                ["source-anchored", "floating", "source-anchored"],
            )
            self.assertNotIn("appendix/appendix.tex", inventory["active_body_files"])
            self.assertEqual(inventory["appendix_labels"], ["fig:appendix-only"])
            self.assertEqual(len(inventory["appendix_records"]), 1)
            self.assertEqual(inventory["structure_errors"], [])
            self.assertEqual(inventory["after_conclusion_source"], [])

            labeled_source = body.read_text(encoding="utf-8")
            body.write_text(labeled_source.replace(r"\label{fig:late}", ""), encoding="utf-8")
            self.assertEqual(len(body_float_inventory(paper)["unlabeled"]), 1)
            body.write_text(labeled_source, encoding="utf-8")

            for command in (r"\clearpage", r"\newpage", r"\pagebreak", r"\FloatBarrier"):
                body.write_text(labeled_source + command + "\n", encoding="utf-8")
                commands = manual_pagination_commands(paper)
                self.assertEqual([item["command"] for item in commands], [command])
            body.write_text(
                labeled_source.replace(r"\begin{figure}[t]", r"\begin{figure}[H]"),
                encoding="utf-8",
            )
            commands = manual_pagination_commands(paper)
            self.assertEqual([item["command"] for item in commands], [r"\begin{figure}[H]"])
            body.write_text(labeled_source, encoding="utf-8")

            aux = Path(temporary) / "main.aux"
            aux.write_text(
                "\\newlabel{idea2paper:start-conclusion}{{}{10}}\n"
                "\\newlabel{fig:late}{{3}{11}}\n",
                encoding="utf-8",
            )
            conclusion_page = aux_label_page(aux, "idea2paper:start-conclusion")
            pages, violations = body_float_tail_report(aux, ["fig:late"], conclusion_page)
            self.assertEqual(pages, {"fig:late": 11})
            self.assertEqual(violations[0]["label"], "fig:late")

            pages, violations = body_float_tail_report(aux, ["fig:missing"], conclusion_page)
            self.assertEqual(pages, {"fig:missing": None})
            self.assertEqual(violations, [])

            aux.write_text(
                "\\newlabel{fig:late}{{3}{10}}\n"
                "\\newlabel{idea2paper:start-conclusion}{{}{10}}\n",
                encoding="utf-8",
            )
            conclusion_page = aux_label_page(aux, "idea2paper:start-conclusion")
            _, violations = body_float_tail_report(aux, ["fig:late"], conclusion_page)
            self.assertEqual(violations, [])

            aux.write_text(
                "\\newlabel{idea2paper:start-conclusion}{{}{10}}\n"
                "\\newlabel{fig:late}{{3}{10}}\n",
                encoding="utf-8",
            )
            conclusion_page = aux_label_page(aux, "idea2paper:start-conclusion")
            _, violations = body_float_tail_report(aux, ["fig:late"], conclusion_page)
            self.assertEqual(violations[0]["reason"], "same_page_after_conclusion")

            conclusion = sections / "conclusion.tex"
            conclusion.write_text(
                "\\section{Conclusion}\n"
                "\\begin{figure}[t]\\caption{x}\\label{fig:evade}\\end{figure}\n"
                "\\label{idea2paper:start-conclusion}\n",
                encoding="utf-8",
            )
            structure = manuscript_structure_audit(paper)
            self.assertTrue(any("immediately follows" in error for error in structure["errors"]))

            conclusion.write_text(
                "\\section{Conclusion}\n"
                "\\label{idea2paper:start-conclusion}\n"
                "\\begin{figure}[t]\\caption{x}\\label{fig:after}\\end{figure}\n",
                encoding="utf-8",
            )
            inventory = body_float_inventory(paper)
            self.assertEqual(
                [item["labels"] for item in inventory["after_conclusion_source"]],
                [["fig:after"]],
            )

            conclusion.write_text(
                "\\section{Conclusion}\n\\label{idea2paper:start-conclusion}\n",
                encoding="utf-8",
            )
            main = paper / "main.tex"
            valid_main = main.read_text(encoding="utf-8")
            main.write_text(
                valid_main.replace(
                    "\\input{sections/conclusion}\n\\label{idea2paper:end-body}",
                    "\\label{idea2paper:end-body}\n\\input{sections/conclusion}",
                ),
                encoding="utf-8",
            )
            structure = manuscript_structure_audit(paper)
            self.assertTrue(any("boundaries must be ordered" in error for error in structure["errors"]))

    def test_float_distribution_rejects_overload_dense_runs_and_terminal_dumping(self) -> None:
        records = []
        label_pages: dict[str, int | None] = {}
        layout = [
            ("body", 8, 2),
            ("body", 9, 2),
            ("appendix", 13, 2),
            ("appendix", 15, 3),
            ("appendix", 16, 2),
            ("appendix", 17, 2),
        ]
        index = 0
        for region, page, count in layout:
            for _ in range(count):
                index += 1
                label = f"fig:f{index}"
                records.append(
                    {
                        "float_index": index,
                        "region": region,
                        "path": "appendix/appendix.tex" if region == "appendix" else "sections/x.tex",
                        "line": index,
                        "labels": [label],
                    }
                )
                label_pages[label] = page
        report = float_distribution_audit(records, label_pages, 13, 17, 1)
        codes = [item["code"] for item in report["float_distribution_violations"]]
        self.assertIn("overloaded_float_page", codes)
        self.assertIn("consecutive_dense_float_pages", codes)
        self.assertIn("appendix_terminal_float_cluster", codes)
        self.assertEqual(report["page_float_counts"]["15"], 3)

    def test_float_distribution_accepts_balanced_appendix(self) -> None:
        records = []
        label_pages: dict[str, int | None] = {}
        index = 0
        for page, count in [(13, 1), (14, 1), (15, 2), (16, 1), (17, 1), (18, 1)]:
            for _ in range(count):
                index += 1
                label = f"tab:t{index}"
                records.append(
                    {
                        "float_index": index,
                        "region": "appendix",
                        "path": "appendix/appendix.tex",
                        "line": index,
                        "labels": [label],
                    }
                )
                label_pages[label] = page
        report = float_distribution_audit(records, label_pages, 13, 18, 1)
        self.assertEqual(report["float_distribution_violations"], [])

    def test_float_distribution_rejects_two_page_appendix_dump(self) -> None:
        records = []
        label_pages: dict[str, int | None] = {}
        for index, page in enumerate((17, 17, 18, 18), start=1):
            label = f"fig:terminal-{index}"
            records.append(
                {
                    "float_index": index,
                    "region": "appendix",
                    "path": "appendix/appendix.tex",
                    "line": index,
                    "labels": [label],
                }
            )
            label_pages[label] = page
        report = float_distribution_audit(records, label_pages, 13, 18, 1)
        codes = [item["code"] for item in report["float_distribution_violations"]]
        self.assertIn("appendix_terminal_two_page_cluster", codes)

    def test_float_distribution_rejects_adjacent_mid_appendix_two_plus_two(self) -> None:
        records = []
        label_pages: dict[str, int | None] = {}
        for index, page in enumerate((13, 13, 14, 14), start=1):
            label = f"fig:middle-{index}"
            records.append(
                {
                    "float_index": index,
                    "region": "appendix",
                    "path": "appendix/appendix.tex",
                    "line": index,
                    "labels": [label],
                }
            )
            label_pages[label] = page
        report = float_distribution_audit(records, label_pages, 10, 20, 1)
        codes = [item["code"] for item in report["float_distribution_violations"]]
        self.assertIn("adjacent_dense_appendix_float_pages", codes)
        self.assertNotIn("appendix_terminal_float_cluster", codes)

    def test_column_mode_audit_uses_only_referenced_templates_and_checks_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            (paper / "main.tex").write_text(
                "\\documentclass{article}\n\\usepackage{venue}\n", encoding="utf-8"
            )
            (paper / "venue.sty").write_text("\\twocolumn\n", encoding="utf-8")
            (paper / "unused.sty").write_text("\\onecolumn\n", encoding="utf-8")
            audit = document_column_mode_audit(paper)
            self.assertEqual(audit["mode"], 2)
            self.assertIn("venue.sty", audit["inspected_template_files"])
            self.assertNotIn("unused.sty", audit["inspected_template_files"])
            self.assertFalse(document_column_mode_audit(paper, "1")["override_verified"])

    def test_column_mode_ignores_dormant_macro_but_follows_invoked_macro(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            main = paper / "main.tex"
            main.write_text(
                "\\documentclass{article}\n\\usepackage{venue}\n"
                "\\begin{document}Single column.\\end{document}\n",
                encoding="utf-8",
            )
            (paper / "venue.sty").write_text(
                "\\newcommand{\\unusedlayout}{\\twocolumn}\n"
                "\\newcommand{\\activelayout}{\\twocolumn}\n",
                encoding="utf-8",
            )
            dormant = document_column_mode_audit(paper, "1")
            self.assertEqual(dormant["mode"], 1)
            self.assertTrue(dormant["override_verified"])

            main.write_text(
                "\\documentclass{article}\n\\usepackage{venue}\n"
                "\\begin{document}\\activelayout Active.\\end{document}\n",
                encoding="utf-8",
            )
            invoked = document_column_mode_audit(paper, "1")
            self.assertEqual(invoked["mode"], 2)
            self.assertFalse(invoked["override_verified"])
            self.assertTrue(
                any(item.get("kind") == "author-invoked-template-command" for item in invoked["evidence"])
            )

    def test_rendered_column_inference_detects_repeated_gutter(self) -> None:
        two_column_pages = []
        for _ in range(2):
            words = []
            for row in range(18):
                top = 100 + row * 12
                for column_start in (55, 330):
                    for word in range(4):
                        x0 = column_start + word * 42
                        words.append({"x0": x0, "x1": x0 + 28, "top": top})
            two_column_pages.append({"width": 612, "height": 792, "words": words})
        inferred = infer_column_mode_from_pages(two_column_pages)
        self.assertEqual(inferred["mode"], 2)
        self.assertGreaterEqual(inferred["confidence"], 0.70)

        single_words = []
        for row in range(24):
            top = 100 + row * 12
            for word in range(10):
                x0 = 70 + word * 45
                single_words.append({"x0": x0, "x1": x0 + 34, "top": top})
        single = infer_column_mode_from_pages(
            [{"width": 612, "height": 792, "words": single_words}]
        )
        self.assertEqual(single["mode"], 1)

    def test_single_column_geometry_flags_large_blank_bands_and_narrow_content(self) -> None:
        boxes = [
            {"x0": 200, "x1": 400, "top": 100, "bottom": 210, "text": "table"},
            {"x0": 200, "x1": 400, "top": 400, "bottom": 470, "text": "caption"},
        ]
        report = page_geometry_from_boxes(
            600,
            800,
            boxes,
            page_number=4,
            float_count=1,
            column_mode=1,
        )
        codes = [item["code"] for item in report["violations"]]
        self.assertIn("float_page_trailing_blank", codes)
        self.assertIn("float_page_internal_blank_band", codes)
        self.assertIn("single_column_narrow_content_block", codes)

        balanced = page_geometry_from_boxes(
            600,
            800,
            [{"x0": 95, "x1": 505, "top": 80, "bottom": 720, "text": "content"}],
            page_number=5,
            float_count=1,
            column_mode=1,
        )
        self.assertEqual(balanced["violations"], [])

        sparse_terminal = page_geometry_from_boxes(
            600,
            800,
            [{"x0": 95, "x1": 505, "top": 80, "bottom": 220, "text": "float"}],
            page_number=6,
            float_count=1,
            column_mode=1,
            is_last_page=True,
        )
        terminal_codes = [item["code"] for item in sparse_terminal["violations"]]
        self.assertIn("terminal_float_page_too_sparse", terminal_codes)

        substantive_terminal = page_geometry_from_boxes(
            600,
            800,
            [{"x0": 95, "x1": 505, "top": 80, "bottom": 520, "text": "content"}],
            page_number=7,
            float_count=1,
            column_mode=1,
            is_last_page=True,
        )
        self.assertEqual(substantive_terminal["violations"], [])

        bottom_only_terminal = page_geometry_from_boxes(
            600,
            800,
            [{"x0": 95, "x1": 505, "top": 310, "bottom": 720, "text": "bottom float"}],
            page_number=8,
            float_count=1,
            column_mode=1,
            is_last_page=True,
        )
        bottom_only_codes = [item["code"] for item in bottom_only_terminal["violations"]]
        self.assertIn("float_page_leading_blank", bottom_only_codes)

        prose_stub_terminal = page_geometry_from_boxes(
            600,
            800,
            [{"x0": 95, "x1": 505, "top": 80, "bottom": 180, "text": "prose stub"}],
            page_number=9,
            float_count=0,
            column_mode=1,
            is_last_page=True,
        )
        prose_stub_codes = [item["code"] for item in prose_stub_terminal["violations"]]
        self.assertIn("terminal_page_trailing_blank", prose_stub_codes)
        self.assertIn("terminal_page_too_sparse", prose_stub_codes)

        source_anchored_artifact = page_geometry_from_boxes(
            600,
            800,
            [
                {"x0": 95, "x1": 505, "top": 80, "bottom": 380, "text": "<image>"},
                {"x0": 95, "x1": 135, "top": 390, "bottom": 405, "text": "Figure"},
                {"x0": 140, "x1": 155, "top": 390, "bottom": 405, "text": "4:"},
            ],
            page_number=10,
            float_count=0,
            column_mode=1,
            is_last_page=True,
        )
        anchored_codes = [item["code"] for item in source_anchored_artifact["violations"]]
        self.assertTrue(source_anchored_artifact["rendered_artifact_detected"])
        self.assertIn("terminal_artifact_page_trailing_blank", anchored_codes)

        masked_by_prose = [
            {"x0": 90, "x1": 510, "top": 80, "bottom": 100, "text": "prose"}
        ]
        masked_by_prose.extend(
            {
                "x0": 220,
                "x1": 380,
                "top": 300 + row * 9,
                "bottom": 307 + row * 9,
                "text": f"row {row}",
            }
            for row in range(16)
        )
        local = page_geometry_from_boxes(
            600,
            800,
            masked_by_prose,
            page_number=8,
            float_count=1,
            column_mode=1,
        )
        local_codes = [item["code"] for item in local["violations"]]
        self.assertIn("single_column_sparse_float_region", local_codes)

    def test_media_box_overflow_uses_unclamped_coordinates_and_validator_binding(self) -> None:
        boxes = [
            {
                "x0": -1.41768,
                "x1": 300,
                "top": 100,
                "bottom": 120,
                "text": "small",
                "kind": "text",
            },
            {
                "x0": 100,
                "x1": 833.5427,
                "top": 200,
                "bottom": 220,
                "text": "clipped equation",
                "kind": "text",
            },
        ]
        overflows = media_box_overflows_from_boxes(600, 800, boxes, page_number=4)
        self.assertEqual(len(overflows), 1)
        self.assertEqual(overflows[0]["edge"], "right")
        self.assertEqual(overflows[0]["excess_pt"], 233.5427)
        geometry = page_geometry_from_boxes(
            600,
            800,
            boxes,
            page_number=4,
            float_count=0,
            column_mode=1,
        )
        self.assertEqual(geometry["media_box_overflows"], overflows)
        self.assertIn("media_box_overflow", [item["code"] for item in geometry["violations"]])

        report = {
            "media_box_overflow_threshold_pt": 2.0,
            "whitespace_thresholds": {"media_box_overflow_maximum_pt": 2.0},
            "media_box_overflows": [],
            "rendered_page_geometry": [{"media_box_overflows": overflows}],
        }
        errors: list[str] = []
        validate_media_box_overflow_report(report, errors)
        self.assertTrue(any("stale or incomplete" in error for error in errors))

    @unittest.skipUnless(importlib.util.find_spec("pdfplumber"), "pdfplumber not installed")
    def test_rendered_whitespace_audit_reads_a_real_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "layout.pdf"
            pdf.write_bytes(make_minimal_pdf())
            report = rendered_whitespace_audit(pdf, {"1": 0}, 1)
            self.assertEqual(report["page_count"], 1)
            self.assertEqual(len(report["pages"]), 1)
            layout_fields = {
                "media_box_overflow_threshold_pt": 2.0,
                "whitespace_thresholds": report["thresholds"],
                "media_box_overflows": report["media_box_overflows"],
                "rendered_page_geometry": report["pages"],
            }
            errors: list[str] = []
            validate_media_box_overflow_report(layout_fields, errors, pdf)
            self.assertEqual(errors, [])

    def test_float_reading_order_rejects_caption_between_word_halves(self) -> None:
        pages = [
            {
                "width": 600.0,
                "height": 800.0,
                "words": [
                    {"x0": 110.0, "top": 700.0, "bottom": 710.0, "text": "diagno-"}
                ],
            },
            {
                "width": 600.0,
                "height": 800.0,
                "words": [
                    {"x0": 110.0, "top": 90.0, "bottom": 100.0, "text": "Table"},
                    {"x0": 140.0, "top": 90.0, "bottom": 100.0, "text": "3:"},
                    {"x0": 110.0, "top": 500.0, "bottom": 510.0, "text": "sis"},
                ],
            },
        ]
        violations = float_reading_order_violations_from_pages(pages, {"2": 1})
        self.assertEqual(
            [item["code"] for item in violations], ["float_interrupted_hyphen"]
        )

    def test_float_reading_order_allows_immediate_word_continuation(self) -> None:
        pages = [
            {
                "width": 600.0,
                "height": 800.0,
                "words": [
                    {"x0": 110.0, "top": 700.0, "bottom": 710.0, "text": "diagno-"}
                ],
            },
            {
                "width": 600.0,
                "height": 800.0,
                "words": [
                    {"x0": 110.0, "top": 90.0, "bottom": 100.0, "text": "sis"},
                    {"x0": 110.0, "top": 650.0, "bottom": 660.0, "text": "Table"},
                ],
            },
        ]
        self.assertEqual(float_reading_order_violations_from_pages(pages, {"2": 1}), [])

    def test_float_reading_order_rejects_caption_inside_unfinished_sentence(self) -> None:
        pages = [
            {
                "width": 600.0,
                "height": 800.0,
                "words": [
                    {"x0": 110.0, "top": 700.0, "bottom": 710.0, "text": "from"},
                    {"x0": 150.0, "top": 700.0, "bottom": 710.0, "text": "complete"},
                ],
            },
            {
                "width": 600.0,
                "height": 800.0,
                "words": [
                    {"x0": 110.0, "top": 90.0, "bottom": 100.0, "text": "Figure"},
                    {"x0": 155.0, "top": 90.0, "bottom": 100.0, "text": "4:"},
                    {"x0": 110.0, "top": 500.0, "bottom": 510.0, "text": "satisfaction"},
                ],
            },
        ]
        violations = float_reading_order_violations_from_pages(pages, {"2": 1})
        self.assertEqual(
            [item["code"] for item in violations], ["float_interrupted_sentence"]
        )

    def test_paperjury_self_reported_pass_without_artifacts_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paper = project / "paper"
            root = project / "qa/paperjury"
            paper.mkdir(parents=True)
            root.mkdir(parents=True)
            (paper / "main.tex").write_text("Paper.\n", encoding="utf-8")
            ledger = {
                "schema": 1,
                "meta": {
                    "manuscript": str(paper),
                    "venue_family": "ml",
                    "created_round": 1,
                    "assignment_unverified": [],
                },
                "issues": [],
            }
            ledger_path = root / "LEDGER.json"
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            ledger_errors: list[str] = []
            facts = paperjury_ledger_facts(ledger, ledger_path, ledger_errors)
            self.assertEqual(ledger_errors, [])
            (root / "LEDGER.md").write_text(
                render_paperjury_ledger(ledger, facts), encoding="utf-8"
            )
            (root / "final_report.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "mode": "review",
                        "author_authorized": True,
                        "rounds": 2,
                        "reviewer_count": 3,
                        "converged": True,
                        "gate_blocking_major": 0,
                        "unadjudicated_major": 0,
                        "source_sha256": source_tree_sha256(paper),
                    }
                ),
                encoding="utf-8",
            )
            errors: list[str] = []
            validate_paperjury_review(project, errors)
            self.assertTrue(any("verified isolated review rounds" in error for error in errors))

    def test_paperjury_blocker_requires_exact_ledger_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            make_paperjury_rounds(
                project,
                first_round_blocker={
                    "id": "CLAIMS-B01",
                    "title": "Unregistered blocker",
                    "evidence": "The claim is unsupported.",
                    "why_blocking": "It changes the conclusion.",
                    "required_fix": "Narrow the claim.",
                },
            )
            errors: list[str] = []
            validate_paperjury_review(project, errors)
            self.assertTrue(any("CLAIMS-B01" in error and "LEDGER.json" in error for error in errors))

    def test_paperjury_final_clean_round_rejects_minor_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            make_paperjury_rounds(
                project,
                final_round_minor={"id": "FINAL-m01", "finding": "A fixable wording issue remains."},
            )
            errors: list[str] = []
            validate_paperjury_review(project, errors)
            self.assertTrue(any("final clean round" in error for error in errors))

    def test_paperjury_round_number_cannot_forge_legacy_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            make_paperjury_rounds(project)
            source_round = project / "qa/paperjury/round_01"
            forged_round = project / "qa/paperjury/round_07"
            source_round.rename(forged_round)
            manifest_path = forged_round / "round_report.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["round"] = 7
            for reviewer_path in forged_round.glob("reviewer_*.json"):
                reviewer = json.loads(reviewer_path.read_text(encoding="utf-8"))
                reviewer.pop("schema_version", None)
                reviewer_path.write_text(json.dumps(reviewer), encoding="utf-8")
            manifest["reviewer_files"] = {
                path.name: sha256_file(path)
                for path in sorted(forged_round.glob("reviewer_*.json"))
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            final_path = project / "qa/paperjury/final_report.json"
            final = json.loads(final_path.read_text(encoding="utf-8"))
            final["rounds"] = 2
            final_path.write_text(json.dumps(final), encoding="utf-8")

            errors: list[str] = []
            validate_paperjury_review(project, errors)
            self.assertTrue(any("migration allowlist" in error for error in errors))

    def test_paperjury_exact_legacy_migration_requires_later_v2_round(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            make_paperjury_rounds(project)
            legacy_round = project / "qa/paperjury/round_01"
            for reviewer_path in legacy_round.glob("reviewer_*.json"):
                reviewer = json.loads(reviewer_path.read_text(encoding="utf-8"))
                reviewer.pop("schema_version", None)
                reviewer_path.write_text(json.dumps(reviewer), encoding="utf-8")
            reviewer_hashes = {
                path.name: sha256_file(path)
                for path in sorted(legacy_round.glob("reviewer_*.json"))
            }
            manifest_path = legacy_round / "round_report.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["reviewer_files"] = reviewer_hashes
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            migration = {
                "snapshot_sha256": paperjury_review_tree_sha256(
                    legacy_round / "snapshot"
                ),
                "reviewer_files": reviewer_hashes,
            }
            errors: list[str] = []
            with mock.patch.dict(
                validate_project_module.PAPERJURY_LEGACY_MIGRATION,
                {1: migration},
                clear=True,
            ):
                validate_paperjury_review(project, errors)
            self.assertEqual(errors, [])

    def test_paperjury_binding_supports_explicit_and_legacy_motionplanner_formats(self) -> None:
        ledger = {
            "issues": [
                {
                    "id": "I-101",
                    "round_raised": 5,
                    "raised_by": ["reviewer_claims"],
                    "significance": "major",
                    "references": "reviewer_claims.json; finding=CNL-01",
                    "summary": "Reference phases and order relations are absent.",
                },
                {
                    "id": "I-102",
                    "round_raised": 5,
                    "raised_by": ["reviewer_claims"],
                    "significance": "major",
                    "summary": "The resource limits conflate equal ceilings with matched realized compute.",
                    "evidence_anchor": "matched total compute",
                    "close_criterion": "Separate equal ceilings from realized work.",
                },
            ]
        }
        errors: list[str] = []
        bindings = paperjury_bind_blocking_findings(
            ledger,
            5,
            "reviewer_claims",
            [
                {
                    "id": "CNL-01",
                    "title": "Reference phases and order relations are absent",
                    "evidence": "No sealed phase records exist.",
                },
                {
                    "issue": "Resource limits conflate equal ceilings and matched realized compute.",
                    "why_blocking": "These are different estimands.",
                    "required_fix": "Separate equal ceilings from realized work.",
                },
            ],
            Path("reviewer_claims.json"),
            errors,
            allow_legacy=True,
        )
        self.assertEqual(errors, [])
        self.assertEqual({item["ledger_issue_id"] for item in bindings}, {"I-101", "I-102"})
        self.assertEqual({item["mode"] for item in bindings}, {"explicit-id", "legacy-semantic"})

    def test_paperjury_v2_rejects_vague_string_and_semantic_ledger_binding(self) -> None:
        ledger = {
            "issues": [
                {
                    "id": "I-900",
                    "round_raised": 8,
                    "raised_by": ["r8_claims"],
                    "significance": "major",
                    "summary": "The resource limits conflate equal ceilings and realized compute.",
                }
            ]
        }
        reviewer = Path("reviewer_claims.json")
        errors: list[str] = []
        bindings = paperjury_bind_blocking_findings(
            ledger,
            8,
            "r8_claims",
            ["Resource limits conflate equal ceilings and realized compute."],
            reviewer,
            errors,
        )
        self.assertEqual(bindings, [])
        self.assertTrue(any("explicit stable finding id" in error for error in errors))

        schema_errors: list[str] = []
        self.assertIsNone(
            validate_paperjury_major_finding(
                "A vague string blocker", reviewer, 1, schema_errors
            )
        )
        self.assertTrue(any("must be an object" in error for error in schema_errors))
        vague_anchor_errors: list[str] = []
        validate_paperjury_major_finding(
            {
                "id": "R8-C-001",
                "evidence": "Method is unclear.",
                "required_fix": "Clarify it.",
            },
            reviewer,
            1,
            vague_anchor_errors,
        )
        self.assertTrue(any("exact file:line" in error for error in vague_anchor_errors))
        for vague_evidence in (
            "Introduction: novelty unsupported.",
            "paper/sections/method.tex",
        ):
            vague_anchor_errors = []
            validate_paperjury_major_finding(
                {
                    "id": "R8-C-001",
                    "evidence": vague_evidence,
                    "required_fix": "Clarify it.",
                },
                reviewer,
                1,
                vague_anchor_errors,
            )
            self.assertTrue(any("exact file:line" in error for error in vague_anchor_errors))
        valid_errors: list[str] = []
        self.assertEqual(
            validate_paperjury_major_finding(
                {
                    "id": "R8-C-002",
                    "evidence": "sections/method.tex:41-47 contradicts Table 2.",
                    "required_fix": "Align the stated operator with the registered condition.",
                },
                reviewer,
                2,
                valid_errors,
            ),
            "R8-C-002",
        )
        self.assertEqual(valid_errors, [])

        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "snapshot"
            method = snapshot / "sections/method.tex"
            method.parent.mkdir(parents=True)
            method.write_text(
                "first line\nsecond line\\label{fig:real-anchor}\nthird line\n",
                encoding="utf-8",
            )
            invalid_errors: list[str] = []
            validate_paperjury_major_finding(
                {
                    "id": "R8-C-003",
                    "evidence": "sections/method.tex:99 cites a nonexistent line.",
                    "required_fix": "Correct the cited defect.",
                },
                reviewer,
                3,
                invalid_errors,
                snapshot,
            )
            self.assertTrue(any("outside the frozen snapshot" in error for error in invalid_errors))
            resolved_errors: list[str] = []
            self.assertEqual(
                validate_paperjury_major_finding(
                    {
                        "id": "R8-C-004",
                        "evidence": "sections/method.tex:2 and \\ref{fig:real-anchor}.",
                        "required_fix": "Align the anchored statement.",
                    },
                    reviewer,
                    4,
                    resolved_errors,
                    snapshot,
                ),
                "R8-C-004",
            )
            self.assertEqual(resolved_errors, [])

    def test_layout_gate_rejects_dynamic_tex_and_boundary_budget_bypasses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paper = root / "paper"
            sections = paper / "sections"
            appendix = paper / "appendix"
            sections.mkdir(parents=True)
            appendix.mkdir()
            (paper / "references.bib").write_text("", encoding="utf-8")
            (sections / "body.tex").write_text("Body.\n", encoding="utf-8")
            (sections / "conclusion.tex").write_text(
                "\\section{Conclusion}\n\\label{idea2paper:start-conclusion}\n",
                encoding="utf-8",
            )
            (sections / "limitations.tex").write_text(
                "\\section{Limitations}\nScoped limitations.\n", encoding="utf-8"
            )
            (sections / "ai_use_statement.tex").write_text(
                "\\subsection*{AI use statement}\nA concise disclosure.\n", encoding="utf-8"
            )
            (appendix / "appendix.tex").write_text(
                "\\appendix\n\\label{idea2paper:start-appendix}\n"
                "\\section{Additional Material}\n",
                encoding="utf-8",
            )
            canonical_main = (
                "\\input{sections/body}\n"
                "\\input{sections/limitations}\n"
                "\\input{sections/conclusion}\n"
                "\\label{idea2paper:end-body}\n"
                "\\input{sections/ai_use_statement}\n"
                "\\label{idea2paper:end-exempt}\n"
                "{\\small\\bibliographystyle{plain}\\bibliography{references}}\n"
                "\\label{idea2paper:end-references}\n"
                "\\input{appendix/appendix}\n"
                "\\end{document}\n"
            )
            main = paper / "main.tex"
            main.write_text(canonical_main, encoding="utf-8")
            self.assertEqual(manuscript_structure_audit(paper)["errors"], [])

            (sections / "late.ltx").write_text(
                "\\begin{figure}\\label{fig:late}\\end{figure}\n", encoding="utf-8"
            )
            main.write_text(
                "\\def\\latefile{late.ltx}\n"
                + canonical_main.replace(
                    "\\input{sections/conclusion}",
                    "\\input{sections/conclusion}\n\\input{sections/\\latefile}",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "static literal path"):
                manuscript_structure_audit(paper)

            main.write_text(
                canonical_main.replace(
                    "\\input{sections/conclusion}",
                    "\\input{sections/conclusion}\n"
                    "\\makeatletter\\@input{sections/late.ltx}\\makeatother",
                ),
                encoding="utf-8",
            )
            dynamic_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("dynamic file-reading" in error for error in dynamic_errors))

            main.write_text(
                canonical_main.replace(
                    "\\input{sections/conclusion}",
                    "\\input{sections/conclusion}\n"
                    "\\inputfrom{sections/}{late.ltx}\\subinputfrom{sections/}{late.ltx}",
                ),
                encoding="utf-8",
            )
            dynamic_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("dynamic file-reading" in error for error in dynamic_errors))

            main.write_text(
                canonical_main.replace(
                    "\\input{sections/conclusion}",
                    "\\input{sections/conclusion}\n"
                    "\\ExplSyntaxOn\\file_input:n { sections/late.ltx }\\ExplSyntaxOff",
                ),
                encoding="utf-8",
            )
            dynamic_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("dynamic file-reading" in error for error in dynamic_errors))

            (paper / "evil.sty").write_text(
                "\\renewcommand{\\appendix}{}\n"
                "\\newcommand{\\manypages}{hidden output}\n",
                encoding="utf-8",
            )
            main.write_text("\\usepackage{evil}\n" + canonical_main, encoding="utf-8")
            package_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(
                any("not present in the recorded official template" in error for error in package_errors)
            )

            (sections / "ai_use_statement.tex").write_text(
                "\\subsection*{AI use statement}\n"
                "Disclosure text.\\makeatletter\\global\\c@page=1\\relax\\makeatother\n"
                "\\global\\count0=1\n",
                encoding="utf-8",
            )
            main.write_text(canonical_main, encoding="utf-8")
            page_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("page-counter/output manipulation" in error for error in page_errors))
            (sections / "ai_use_statement.tex").write_text(
                "\\subsection*{AI use statement}\nA concise disclosure.\n", encoding="utf-8"
            )

            main.write_text(
                "\\renewcommand{\\thepage}{1}\n" + canonical_main, encoding="utf-8"
            )
            page_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("may not be redefined" in error for error in page_errors))

            main.write_text(
                "\\newwrite\\auditout\\openout\\auditout=generated.tex"
                "\\write\\auditout{hidden}\\closeout\\auditout\n"
                + canonical_main,
                encoding="utf-8",
            )
            write_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("file-writing commands" in error for error in write_errors))

            (paper / "evil.bst").write_text("ENTRY{}{}{}\nREAD\n", encoding="utf-8")
            main.write_text(
                canonical_main.replace("\\bibliographystyle{plain}", "\\bibliographystyle{evil}"),
                encoding="utf-8",
            )
            style_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(
                any("not present in the recorded official template" in error for error in style_errors)
            )

            main.write_text(
                canonical_main.replace(
                    "\\input{sections/conclusion}",
                    "\\input{sections/conclusion}\n\\input sections/late.ltx\\relax",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "static literal path"):
                manuscript_structure_audit(paper)

            main.write_text(
                canonical_main.replace(
                    "\\input{appendix/appendix}",
                    "\\iffalse\\appendix\\fi\n"
                    "\\begin{figure}\\label{fig:hidden-tail}\\end{figure}\n"
                    "\\csname appendix\\endcsname",
                ),
                encoding="utf-8",
            )
            fake_appendix_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("conditionals are not allowed" in error for error in fake_appendix_errors))
            self.assertTrue(any("appendix/appendix exactly once" in error for error in fake_appendix_errors))

            main.write_text(
                canonical_main.replace(
                    "\\label{idea2paper:end-body}\n",
                    "\\label{idea2paper:end-body}\nHidden body prose that evades the page label.\n",
                ),
                encoding="utf-8",
            )
            boundary_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("end-exempt" in error for error in boundary_errors))

            (root / "external.bib").write_text("", encoding="utf-8")
            main.write_text(
                canonical_main.replace("\\bibliography{references}", "\\bibliography{../external}"),
                encoding="utf-8",
            )
            dependency_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("bibliography resource escapes" in error for error in dependency_errors))

            (root / "external.pdf").write_bytes(b"external")
            (sections / "body.tex").write_text(
                "\\includegraphics{../external.pdf}\n", encoding="utf-8"
            )
            main.write_text(canonical_main, encoding="utf-8")
            dependency_errors = manuscript_structure_audit(paper)["errors"]
            self.assertTrue(any("figure resource escapes" in error for error in dependency_errors))

    def test_init_resume_resources_and_structure_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            result = run_script(
                "init_project.py",
                "--idea",
                "A&B_# uncertainty model",
                "--out-dir",
                parent,
                "--slug",
                "demo",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            project = parent / "demo"
            self.assertEqual(json.loads((project / "resources.json").read_text(encoding="utf-8"))["source"], "current_machine")
            main_tex = (project / "paper/main.tex").read_text(encoding="utf-8")
            title_tex = (project / "paper/title.tex").read_text(encoding="utf-8")
            self.assertIn(r"\input{title}", main_tex)
            self.assertIn(r"\title{\papertitle}", main_tex)
            self.assertNotIn(r"\IdeaTwoPaperPatchTitleTeaser", main_tex)
            self.assertEqual(main_tex.count(r"\input{sections/teaser}"), 1)
            self.assertLess(
                main_tex.index(r"\maketitle"),
                main_tex.index(r"\input{sections/teaser}"),
            )
            self.assertLess(
                main_tex.index(r"\input{sections/teaser}"),
                main_tex.index(r"\begin{abstract}"),
            )
            self.assertIn(r"\label{idea2paper:end-exempt}", main_tex)
            self.assertIn("Working Title Pending", title_tex)
            self.assertNotIn("A&B_# uncertainty model", title_tex)
            self.assertTrue(json.loads((project / "title/brief.json").read_text(encoding="utf-8"))["project_directory_is_not_title"])

            duplicate = run_script(
                "init_project.py",
                "--idea",
                "A&B_# uncertainty model",
                "--out-dir",
                parent,
                "--slug",
                "demo",
            )
            self.assertNotEqual(duplicate.returncode, 0)
            resumed = run_script(
                "init_project.py",
                "--idea",
                "A&B_# uncertainty model",
                "--out-dir",
                parent,
                "--slug",
                "demo",
                "--resume",
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            mismatched = run_script(
                "init_project.py",
                "--idea",
                "A different idea",
                "--out-dir",
                parent,
                "--slug",
                "demo",
                "--resume",
            )
            self.assertNotEqual(mismatched.returncode, 0)
            structure = run_script("validate_project.py", project, "--mode", "structure")
            self.assertEqual(structure.returncode, 0, structure.stdout + structure.stderr)
            resources = json.loads((project / "resources.json").read_text(encoding="utf-8"))
            resources["notes"].append("changed after RESOURCES_READY")
            (project / "resources.json").write_text(json.dumps(resources), encoding="utf-8")
            stale = run_script("validate_project.py", project, "--mode", "structure")
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("RESOURCES_READY is stale", stale.stdout)

            resources_file = parent / "resources.json"
            resources_file.write_text(
                json.dumps({"compute": {"gpus": [{"name": "User GPU"}]}, "data": ["private-dataset"]}),
                encoding="utf-8",
            )
            supplied = run_script(
                "init_project.py",
                "--idea",
                "Resource-aware idea",
                "--out-dir",
                parent,
                "--slug",
                "supplied",
                "--resources-file",
                resources_file,
                "--data-source",
                "user",
            )
            self.assertEqual(supplied.returncode, 0, supplied.stderr)
            supplied_root = parent / "supplied"
            supplied_project = json.loads((supplied_root / "project.json").read_text(encoding="utf-8"))
            supplied_resources = json.loads((supplied_root / "resources.json").read_text(encoding="utf-8"))
            self.assertEqual(supplied_project["compute_source"], "user")
            self.assertEqual(supplied_project["data_source"], "user")
            self.assertEqual(supplied_resources["source"], "user")

            explicit = run_script(
                "init_project.py",
                "--idea",
                "Explicit venue idea",
                "--out-dir",
                parent,
                "--slug",
                "explicit",
                "--venue",
                "3DV",
            )
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            explicit_project = json.loads((parent / "explicit/project.json").read_text(encoding="utf-8"))
            explicit_decision = json.loads((parent / "explicit/venue/decision.json").read_text(encoding="utf-8"))
            self.assertEqual(explicit_project["venue_selection_mode"], "user_specified")
            self.assertEqual(explicit_decision["selection_mode"], "user_specified")

    def test_teaser_requires_title_author_then_teaser_then_abstract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary) / "paper"
            sections = paper / "sections"
            sections.mkdir(parents=True)
            teaser = sections / "teaser.tex"
            teaser.write_text(
                "\\begin{IdeaTwoPaperTitleTeaser}{Conceptual teaser.}{fig:teaser}\n"
                "\\includegraphics[width=0.8\\linewidth]{figures/teaser.png}\n"
                "\\end{IdeaTwoPaperTitleTeaser}\n",
                encoding="utf-8",
            )
            main = paper / "main.tex"
            main.write_text(
                "\\documentclass{article}\n"
                "\\title{A Title}\\author{Anonymous Authors}\n"
                "\\begin{document}\n"
                "\\maketitle\n"
                "\\input{sections/teaser}\n"
                "\\begin{abstract}Abstract.\\end{abstract}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            self.assertEqual(teaser_placement_audit(paper), [])

            main.write_text(
                "\\documentclass{article}\n"
                "\\title{A Title}\\author{Anonymous Authors}\n"
                "\\makeatletter\n"
                "\\IdeaTwoPaperPatchTitleTeaser{{\\LARGE \\@title \\par}}"
                "{\\input{sections/teaser}}\n"
                "\\makeatother\n"
                "\\begin{document}\n"
                "\\maketitle\n"
                "\\begin{abstract}Abstract.\\end{abstract}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            legacy_errors = teaser_placement_audit(paper)
            self.assertTrue(
                any("IdeaTwoPaperPatchTitleTeaser" in error for error in legacy_errors)
            )

            teaser.write_text(
                "\\begin{figure}[t]\\includegraphics{figures/teaser.png}"
                "\\caption{Wrong float.}\\end{figure}\n",
                encoding="utf-8",
            )
            main.write_text(
                "\\documentclass{article}\n"
                "\\title{A Title}\\author{Anonymous Authors}\n"
                "\\begin{document}\\maketitle\n"
                "\\input{sections/teaser}\n"
                "\\begin{abstract}Abstract.\\end{abstract}\\end{document}\n",
                encoding="utf-8",
            )
            float_errors = teaser_placement_audit(paper)
            self.assertTrue(any("non-floating" in error for error in float_errors))

            teaser.write_text(
                "\\begin{IdeaTwoPaperTitleTeaser}{Conceptual teaser.}{fig:teaser}\n"
                "\\includegraphics[width=0.8\\linewidth]{figures/teaser.png}\n"
                "\\end{IdeaTwoPaperTitleTeaser}\n",
                encoding="utf-8",
            )
            main.write_text(
                "\\documentclass{article}\n"
                "\\title{A Title}\\author{Anonymous Authors}\n"
                "\\begin{document}\\maketitle\n"
                "Rendered interruption.\n"
                "\\input{sections/teaser}\n"
                "\\begin{abstract}Abstract.\\end{abstract}\\end{document}\n",
                encoding="utf-8",
            )
            interrupted_errors = teaser_placement_audit(paper)
            self.assertTrue(any("immediately follow maketitle" in error for error in interrupted_errors))

    def test_auto_venue_uses_open_abstract_or_paper_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = {
                "candidates": [
                    {
                        "name": "CVPR",
                        "edition": "2027",
                        "track": "main",
                        "tier": "flagship",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["vision", "representation learning"],
                        "fit_reason": "The idea is directly in scope.",
                        "scope_evidence_url": "https://cvpr.thecvf.com/Conferences/2027/CallForPapers",
                        "has_separate_abstract_deadline": True,
                        "abstract_deadline": "2026-07-20T23:59:59-12:00",
                        "paper_deadline": "2026-08-30T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://cvpr.thecvf.com/",
                        "deadline_source_url": "https://cvpr.thecvf.com/Conferences/2027/Dates",
                        "checked_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "name": "ECCV",
                        "edition": "2026",
                        "track": "main",
                        "tier": "top",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["vision", "representation learning"],
                        "fit_reason": "The idea is directly in scope.",
                        "scope_evidence_url": "https://eccv.ecva.net/Conferences/2026/CallForPapers",
                        "has_separate_abstract_deadline": False,
                        "paper_deadline": "2026-08-10T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://eccv.ecva.net/",
                        "deadline_source_url": "https://eccv.ecva.net/Conferences/2026/Dates",
                        "checked_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "name": "ICCV",
                        "edition": "2027",
                        "track": "main",
                        "tier": "flagship",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["vision"],
                        "fit_reason": "The idea is directly in scope.",
                        "scope_evidence_url": "https://iccv.thecvf.com/Conferences/2027/CallForPapers",
                        "has_separate_abstract_deadline": False,
                        "abstract_deadline": "2026-08-04T23:59:59-12:00",
                        "paper_deadline": "2026-08-05T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://iccv.thecvf.com/",
                        "deadline_source_url": "https://iccv.thecvf.com/Conferences/2027/Dates",
                        "checked_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "name": "NeurIPS",
                        "edition": "2026",
                        "track": "main",
                        "tier": "flagship",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["machine learning"],
                        "fit_reason": "The idea is directly in scope.",
                        "scope_evidence_url": "https://neurips.cc/Conferences/2026/CallForPapers",
                        "has_separate_abstract_deadline": False,
                        "paper_deadline": "2026-08-20T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://neurips.cc/",
                        "deadline_source_url": "https://neurips.cc/Conferences/2026/Dates",
                        "checked_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "name": "3DV",
                        "edition": "2027",
                        "track": "main",
                        "tier": "top",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["3d vision", "human motion"],
                        "fit_reason": "The idea is directly in scope.",
                        "scope_evidence_url": "https://3dvconf.github.io/2027/call-for-papers/",
                        "community_top_evidence_url": "https://3dvconf.github.io/2027/",
                        "has_separate_abstract_deadline": False,
                        "paper_deadline": "2026-08-03T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://3dvconf.github.io/2027/",
                        "deadline_source_url": "https://3dvconf.github.io/2027/call-for-papers/",
                        "checked_at": "2026-08-01T00:00:00Z"
                    },
                    {
                        "name": "CVPR",
                        "edition": "2027",
                        "track": "workshop",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["vision"],
                        "fit_reason": "A workshop is near but is not the main conference.",
                        "scope_evidence_url": "https://cvpr.thecvf.com/",
                        "has_separate_abstract_deadline": False,
                        "paper_deadline": "2026-08-02T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://cvpr.thecvf.com/",
                        "deadline_source_url": "https://cvpr.thecvf.com/",
                        "checked_at": "2026-08-01T00:00:00Z"
                    },
                    {
                        "name": "ACL",
                        "edition": "2027",
                        "track": "Findings",
                        "scope_fit": 5,
                        "idea_version": "idea_v0",
                        "idea_tags": ["language"],
                        "fit_reason": "Findings is not the main conference track.",
                        "scope_evidence_url": "https://2027.aclweb.org/",
                        "has_separate_abstract_deadline": False,
                        "paper_deadline": "2026-08-02T23:59:59-12:00",
                        "deadline_status": "confirmed",
                        "official_url": "https://2027.aclweb.org/",
                        "deadline_source_url": "https://2027.aclweb.org/",
                        "checked_at": "2026-08-01T00:00:00Z"
                    },
                ]
            }
            source = root / "candidates.json"
            output = root / "decision.json"
            source.write_text(json.dumps(candidates), encoding="utf-8")
            result = run_script(
                "select_venue.py",
                source,
                "--output",
                output,
                "--as-of",
                "2026-08-01T00:00:00Z",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            decision = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(decision["selected"]["name"], "ECCV")
            self.assertEqual(decision["selected"]["effective_deadline_kind"], "paper_deadline")
            self.assertTrue(any(item["name"] == "CVPR" for item in decision["excluded"]))
            self.assertTrue(any(item["name"] == "ICCV" for item in decision["excluded"]))
            excluded_3dv = next(item for item in decision["excluded"] if item["name"] == "3DV")
            self.assertIn("strict default top-conference pool", excluded_3dv["reason"])
            excluded_non_main = [
                item for item in decision["excluded"] if item["name"] in {"CVPR", "ACL"}
                and "main track" in item["reason"]
            ]
            self.assertEqual(len(excluded_non_main), 2)

    def test_auto_venue_canonicalizes_pool_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            common = {
                "edition": "2027",
                "track": "main",
                "tier": "flagship",
                "scope_fit": 5,
                "idea_version": "idea_v0",
                "idea_tags": ["machine learning"],
                "fit_reason": "The idea is directly in scope.",
                "scope_evidence_url": "https://example.org/official-scope",
                "has_separate_abstract_deadline": False,
                "deadline_status": "confirmed",
                "official_url": "https://example.org/official",
                "deadline_source_url": "https://example.org/official-dates",
                "checked_at": "2026-08-01T00:00:00Z",
            }
            candidates = {
                "candidates": [
                    {**common, "name": "NIPS", "paper_deadline": "2026-08-05T23:59:59-12:00"},
                    {**common, "name": "ACMMM", "paper_deadline": "2026-08-06T23:59:59-12:00"},
                ]
            }
            source = root / "candidates.json"
            output = root / "decision.json"
            source.write_text(json.dumps(candidates), encoding="utf-8")
            result = run_script(
                "select_venue.py",
                source,
                "--output",
                output,
                "--as-of",
                "2026-08-01T00:00:00Z",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            decision = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(decision["selected"]["name"], "NeurIPS")
            self.assertEqual(decision["selected"]["submitted_name"], "NIPS")
            self.assertEqual(decision["selected"]["registry_id"], "neurips")
            self.assertEqual(decision["eligible"][1]["name"], "ACM MM")

    def test_auto_venue_registry_is_exact_and_cannot_inject_3dv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = json.loads((SKILL_ROOT / "references/venue-registry.json").read_text(encoding="utf-8"))
            registry["venues"].append(
                {
                    "id": "3dv",
                    "name": "3DV",
                    "full_name": "International Conference on 3D Vision",
                    "tier": "top",
                }
            )
            injected = root / "registry.json"
            injected.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly the strict default pool"):
                load_registry(injected)

            replaced = json.loads(
                (SKILL_ROOT / "references/venue-registry.json").read_text(encoding="utf-8")
            )
            eccv = next(item for item in replaced["venues"] if item["id"] == "eccv")
            eccv["name"] = "3DV"
            eccv["aliases"] = ["3DV"]
            replaced_path = root / "replaced-registry.json"
            replaced_path.write_text(json.dumps(replaced), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metadata differs from the immutable pool"):
                load_registry(replaced_path)

    def test_venue_decision_is_bound_to_project_intake(self) -> None:
        registry = load_registry(SKILL_ROOT / "references/venue-registry.json")

        errors: list[str] = []
        validate_selection_binding(
            {"target_venue": "auto", "venue_selection_mode": "auto"},
            {"selection_mode": "user_specified"},
            {"name": "3DV"},
            registry,
            errors,
        )
        self.assertTrue(any("selection_mode does not match" in error for error in errors))

        errors = []
        validate_selection_binding(
            {"target_venue": "ICLR", "venue_selection_mode": "user_specified"},
            {"selection_mode": "user_specified"},
            {"name": "CVPR"},
            registry,
            errors,
        )
        self.assertTrue(any("selected venue does not match" in error for error in errors))

        errors = []
        validate_selection_binding(
            {"target_venue": "NIPS", "venue_selection_mode": "user_specified"},
            {"selection_mode": "user_specified"},
            {"name": "NeurIPS"},
            registry,
            errors,
        )
        self.assertEqual(errors, [])

    def test_literature_enrichment_preserves_identity_and_excludes_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "papers_merged.csv"
            output = root / "papers_enriched.csv"
            records = root / "papers"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["title", "year", "doi", "tier", "publication_status"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "title": "A Core Paper",
                        "year": "2025",
                        "doi": "",
                        "tier": "core",
                        "publication_status": "accepted",
                    }
                )
                writer.writerow(
                    {
                        "title": "An Excluded Paper",
                        "year": "2024",
                        "doi": "",
                        "tier": "exclude",
                        "publication_status": "",
                    }
                )

            first = run_script(
                "enrich_literature.py",
                source,
                "--output",
                output,
                "--records-dir",
                records,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            with output.open(newline="", encoding="utf-8") as handle:
                first_rows = list(csv.DictReader(handle))
            first_id = first_rows[0]["stable_id"]
            self.assertEqual(first_rows[0]["publication_status"], "accepted")
            self.assertEqual(first_rows[0]["official_code_status"], "unknown")
            self.assertTrue((records / first_id / "metadata.json").exists())
            self.assertEqual(first_rows[1]["publication_status"], "unknown")
            self.assertFalse((records / first_rows[1]["stable_id"]).exists())

            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["title", "year", "doi", "tier", "publication_status"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "title": "A Core Paper",
                        "year": "2025",
                        "doi": "10.1/newly-indexed",
                        "tier": "core",
                        "publication_status": "",
                    }
                )
            second = run_script(
                "enrich_literature.py",
                source,
                "--output",
                output,
                "--records-dir",
                records,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            with output.open(newline="", encoding="utf-8") as handle:
                second_rows = list(csv.DictReader(handle))
            self.assertEqual(second_rows[0]["stable_id"], first_id)
            self.assertEqual(second_rows[0]["publication_status"], "accepted")

    def test_survey_provenance_is_derived_from_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            related = Path(temporary)
            (related / "00_scope.md").write_text("# Scope\n", encoding="utf-8")
            (related / "01_query_plan.md").write_text("# Query Plan\n", encoding="utf-8")
            (related / "synthesis_outline.md").write_text("# Synthesis\n", encoding="utf-8")
            (related / "coverage_audit.md").write_text(
                "# Coverage Audit\n\n"
                "## Source Ledger Summary\n\nTwo source families.\n\n"
                "## Snowballing\n\nTwo passes.\n\n"
                "## Blind Spots\n\nIndexing delay.\n\n"
                "## Stopping Decision\n\nNear-complete under the listed sources.\n",
                encoding="utf-8",
            )
            invoked_skill = related / "invoked-skill/SKILL.md"
            invoked_skill.parent.mkdir(parents=True, exist_ok=True)
            invoked_skill.write_text(
                "---\nname: ai-literature-survey\ndescription: test fixture\n---\n",
                encoding="utf-8",
            )
            receipt = related / "dispatch-receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "skill_name": "ai-literature-survey",
                        "skill_path": str(invoked_skill),
                        "skill_sha256": hashlib.sha256(invoked_skill.read_bytes()).hexdigest(),
                        "invocation_id": "survey-001",
                        "orchestrator_run_id": "orchestrator-test-001",
                        "request_sha256": "a" * 64,
                        "started_at": "2026-08-01T00:00:00Z",
                        "completed_at": "2026-08-01T00:10:00Z",
                    }
                ),
                encoding="utf-8",
            )

            def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)

            ledger_fields = [
                "run_id",
                "date",
                "source_family",
                "source_name",
                "query",
                "filters",
                "command_or_url",
                "raw_output",
                "raw_hits",
                "unique_hits",
                "status",
                "notes",
            ]

            def ledger_row(run_id: str, family: str, status: str = "ok", notes: str = "") -> dict[str, str]:
                return {
                    "run_id": run_id,
                    "date": "2026-08-01",
                    "source_family": family,
                    "source_name": family,
                    "query": "uncertainty motion",
                    "filters": "",
                    "command_or_url": "https://example.org/",
                    "raw_output": f"raw/{family}.json",
                    "raw_hits": "10" if status == "ok" else "0",
                    "unique_hits": "8" if status == "ok" else "0",
                    "status": status,
                    "notes": notes,
                }

            write_csv(
                related / "source_ledger.csv",
                ledger_fields,
                [
                    ledger_row("S001", "arxiv"),
                    ledger_row("S002", "openalex"),
                    ledger_row("S003", "openreview", "empty"),
                    ledger_row("S004", "proceedings"),
                    ledger_row("S005", "citation_graph"),
                    ledger_row("S006", "web", "skipped", "WAIVER: no project pages for this topic."),
                ],
            )
            write_csv(related / "papers_raw.csv", ["title"], [{"title": "Paper"}])
            write_csv(
                related / "papers_merged.csv",
                ["record_id", "title", "year", "sources", "tier"],
                [{"record_id": "P001", "title": "Paper", "year": "2025", "sources": "arxiv", "tier": "core"}],
            )
            write_csv(
                related / "screening.csv",
                ["record_id", "title", "tier", "reason", "read_priority", "must_cite", "novelty_risk"],
                [
                    {
                        "record_id": "P001",
                        "title": "Paper",
                        "tier": "core",
                        "reason": "Direct prior art",
                        "read_priority": "high",
                        "must_cite": "yes",
                        "novelty_risk": "yes",
                    }
                ],
            )
            write_csv(
                related / "reading_matrix.csv",
                [
                    "record_id",
                    "claim",
                    "method",
                    "data",
                    "metrics",
                    "baselines",
                    "result",
                    "limitation",
                    "relation_to_user_work",
                    "quote_or_evidence",
                ],
                [
                    {
                        "record_id": "P001",
                        "claim": "Claim",
                        "method": "Method",
                        "data": "Data",
                        "metrics": "Metric",
                        "baselines": "Baseline",
                        "result": "Result",
                        "limitation": "Limitation",
                        "relation_to_user_work": "prior art",
                        "quote_or_evidence": "Section 3",
                    }
                ],
            )
            snowball_fields = [
                "anchor_id",
                "anchor_title",
                "direction",
                "pass",
                "new_candidates",
                "new_core",
                "source",
                "notes",
            ]
            write_csv(
                related / "snowball_log.csv",
                snowball_fields,
                [
                    {
                        "anchor_id": "P001",
                        "anchor_title": "Paper",
                        "direction": "backward",
                        "pass": "pass_1",
                        "new_candidates": "0",
                        "new_core": "0",
                        "source": "citation_graph",
                        "notes": "",
                    }
                ],
            )
            one_pass = run_script(
                "record_survey_run.py",
                related,
                "--idea-version",
                "idea_v0",
                "--invocation-id",
                "survey-001",
                "--receipt",
                receipt,
            )
            self.assertNotEqual(one_pass.returncode, 0)
            write_csv(
                related / "snowball_log.csv",
                snowball_fields,
                [
                    {
                        "anchor_id": "P001",
                        "anchor_title": "Paper",
                        "direction": direction,
                        "pass": pass_id,
                        "new_candidates": "0",
                        "new_core": "0",
                        "source": "citation_graph",
                        "notes": "",
                    }
                    for pass_id in ("pass_1", "pass_2")
                    for direction in ("backward", "forward")
                ],
            )
            two_passes = run_script(
                "record_survey_run.py",
                related,
                "--idea-version",
                "idea_v0",
                "--invocation-id",
                "survey-001",
                "--receipt",
                receipt,
            )
            self.assertEqual(two_passes.returncode, 0, two_passes.stdout + two_passes.stderr)
            manifest = json.loads((related / "survey_run.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["skill_name"], "ai-literature-survey")
            self.assertEqual(manifest["coverage"]["consecutive_zero_new_core_passes"], 2)
            self.assertEqual(manifest["status"], "pass")

    def test_todo_lint_allows_sketch_and_blocks_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            source = paper / "main.tex"
            source.write_text(
                "\\PredResult{EXP-MAIN-01}{82.4}\n"
                "% TODO(EXP-MAIN-01): Replace with measured mean and standard deviation.\n",
                encoding="utf-8",
            )
            sketch = run_script("todo_lint.py", paper, "--mode", "sketch")
            self.assertEqual(sketch.returncode, 0, sketch.stdout + sketch.stderr)
            submission = run_script("todo_lint.py", paper, "--mode", "submission")
            self.assertNotEqual(submission.returncode, 0)
            source.write_text("\\PredResult{EXP-MAIN-01}{82.4}\n", encoding="utf-8")
            missing_todo = run_script("todo_lint.py", paper, "--mode", "sketch")
            self.assertNotEqual(missing_todo.returncode, 0)
            source.write_text(
                "\\PredResult\n{EXP-MAIN-01}{82.4}\n"
                "% TODO(EXP-MAIN-01): Replace with a measured result.\n",
                encoding="utf-8",
            )
            multiline = run_script("todo_lint.py", paper, "--mode", "sketch")
            self.assertEqual(multiline.returncode, 0, multiline.stdout + multiline.stderr)
            source.write_text(
                "\\TemplateTODO\n{TEMPLATE-UPDATE}{Use the new template.}\n"
                "% TODO(TEMPLATE-UPDATE): Replace the fallback template.\n",
                encoding="utf-8",
            )
            multiline_template = run_script("todo_lint.py", paper, "--mode", "sketch")
            self.assertEqual(
                multiline_template.returncode,
                0,
                multiline_template.stdout + multiline_template.stderr,
            )
            source.write_text("\\textcolor[rgb]{1,0,0}{untracked draft text}\n", encoding="utf-8")
            direct_color = run_script("todo_lint.py", paper, "--mode", "sketch")
            self.assertNotEqual(direct_color.returncode, 0)

    def test_multiline_template_marker_is_detected_outside_comments(self) -> None:
        self.assertTrue(
            has_draft_marker(
                "\\TemplateTODO\n{TEMPLATE-UPDATE}{Use the new template.}\n",
                "TemplateTODO",
                "TEMPLATE-UPDATE",
            )
        )
        self.assertFalse(
            has_draft_marker(
                "% \\TemplateTODO{TEMPLATE-UPDATE}{Commented out.}\n",
                "TemplateTODO",
                "TEMPLATE-UPDATE",
            )
        )

    def test_title_freeze_binds_current_evidence_and_latex(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project-label"
            for relative in ("title", "paper", "venue", "related_works", "idea", "method", "experiments"):
                (project / relative).mkdir(parents=True, exist_ok=True)

            project_data = {
                "project_id": "project-label",
                "idea_version": "idea_v2",
                "idea_original": "A long raw idea that is not a paper title.",
            }
            venue = {"selected": {"name": "ICLR", "edition": "2027"}}
            venue_path = project / "venue/decision.json"
            venue_path.write_text(json.dumps(venue), encoding="utf-8")
            corpus_path = project / "related_works/papers_enriched.csv"
            with corpus_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["title"])
                writer.writeheader()
                writer.writerow({"title": "An Unrelated Motion Synthesis Paper"})
            matrix_path = project / "experiments/claim_experiment_matrix.csv"
            with matrix_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["claim_id", "contribution_id", "method_component"])
                writer.writeheader()
                writer.writerow({"claim_id": "C-001", "contribution_id": "CONTRIB-001", "method_component": "M-001"})
            terminology_path = project / "idea/terminology.csv"
            with terminology_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["term"])
                writer.writeheader()
                writer.writerow({"term": "hierarchical planning"})
            method_path = project / "method/method_spec.md"
            method_path.write_text("# Method\n\nA hierarchical planning method.\n", encoding="utf-8")

            (project / "title/brief.json").write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "idea_version": "idea_v2",
                        "project_label": "project-label",
                        "project_directory_is_not_title": True,
                        "required_concepts": ["planning"],
                        "forbidden_claims": ["state of the art"],
                    }
                ),
                encoding="utf-8",
            )
            titles = [
                "Plan Before Motion: Executable Hierarchical Planning for Human Motion Generation",
                "Executable Plans for Human Motion Generation",
                "From Language to Motion Programs",
                "Hierarchical Motion Programs for Text-to-Motion Generation",
                "Planning Contacts Before Poses",
                "Verifiable Motion Plans for Controllable Generation",
                "Event-to-Contact Planning for Human Motion",
                "Structured Planning for Long-Horizon Motion Generation",
            ]
            families = ["problem_capability", "method_identity", "insight_mechanism", "application_outcome"]
            score = {
                "faithfulness": 5,
                "specificity": 4,
                "novelty_signal": 4,
                "clarity": 5,
                "memorability": 4,
                "search_distinctiveness": 4,
                "venue_fit": 5,
            }
            candidates = [
                {
                    "candidate_id": f"TITLE-{index:03d}",
                    "title": title,
                    "framing_family": families[(index - 1) % len(families)],
                    "claim_ids": ["C-001"],
                    "contribution_ids": ["CONTRIB-001"],
                    "method_component_ids": ["M-001"],
                    "terms": ["hierarchical planning"],
                    "rationale": "Faithfully names the planning contribution.",
                    "scores": score,
                    "overclaim_risk": 1,
                    "risk_flags": [],
                }
                for index, title in enumerate(titles, start=1)
            ]
            (project / "title/candidates.json").write_text(
                json.dumps(
                    {
                        "status": "reviewed",
                        "idea_version": "idea_v2",
                        "venue_name": "ICLR",
                        "venue_edition": "2027",
                        "generated_at": "2026-08-01T12:00:00Z",
                        "candidates": candidates,
                    }
                ),
                encoding="utf-8",
            )

            def digest(path: Path) -> str:
                return hashlib.sha256(path.read_bytes()).hexdigest()

            selected = titles[0]
            decision = {
                "status": "frozen",
                "title_version": "title_v1",
                "idea_version": "idea_v2",
                "venue_name": "ICLR",
                "venue_edition": "2027",
                "selected_candidate_id": "TITLE-001",
                "selected_title": selected,
                "shortlist": ["TITLE-001", "TITLE-002", "TITLE-003"],
                "selection_rationale": "Best balance of mechanism, scope, and clarity.",
                "reviews": [
                    {"role": "positioning", "verdict": "pass", "notes": "Distinct from audited titles."},
                    {"role": "clarity_faithfulness", "verdict": "pass", "notes": "Matches the frozen claim."},
                ],
                "input_versions": {
                    "idea_version": "idea_v2",
                    "literature_sha256": digest(corpus_path),
                    "claim_graph_sha256": digest(matrix_path),
                    "terminology_sha256": digest(terminology_path),
                    "method_spec_sha256": digest(method_path),
                    "venue_decision_sha256": digest(venue_path),
                },
                "collision_check": {
                    "checked_at": "2026-08-01T12:10:00Z",
                    "corpus_sha256": digest(corpus_path),
                    "exact_match": False,
                    "reviewed_conflicts": [],
                },
                "unresolved_risks": [],
                "frozen_at": "2026-08-01T12:15:00Z",
            }
            (project / "title/decision.json").write_text(json.dumps(decision), encoding="utf-8")
            (project / "paper/title.tex").write_text(
                f"\\newcommand{{\\papertitle}}{{{selected}}}\n", encoding="utf-8"
            )
            (project / "paper/main.tex").write_text(
                "\\input{title}\n\\title{\\papertitle}\n", encoding="utf-8"
            )

            errors: list[str] = []
            validate_title(project, project_data, venue, errors)
            self.assertEqual(errors, [])
            (project / "paper/title.tex").write_text(
                "\\newcommand{\\papertitle}{A Stale Title}\n", encoding="utf-8"
            )
            stale_errors: list[str] = []
            validate_title(project, project_data, venue, stale_errors)
            self.assertTrue(any("does not match" in error for error in stale_errors))

    def test_venue_change_invalidates_literature_and_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            initialized = run_script(
                "init_project.py",
                "--idea",
                "A state-machine idea",
                "--out-dir",
                parent,
                "--slug",
                "state",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            project = parent / "state"
            for stage in (
                "VENUE_LOCKED",
                "LITERATURE_AUDITED",
                "IDEA_REVIEWED",
                "CLAIM_GRAPH_FROZEN",
                "TITLE_FROZEN",
                "MANUSCRIPT_DRAFTED",
            ):
                result = run_script("state_manager.py", "set", project, stage, "complete")
                self.assertEqual(result.returncode, 0, result.stderr)
            invalidated = run_script("state_manager.py", "invalidate", project, "--cause", "venue")
            self.assertEqual(invalidated.returncode, 0, invalidated.stderr)
            state = json.loads((project / "state.json").read_text(encoding="utf-8"))
            for stage in (
                "VENUE_LOCKED",
                "LITERATURE_AUDITED",
                "IDEA_REVIEWED",
                "CLAIM_GRAPH_FROZEN",
                "TITLE_FROZEN",
                "MANUSCRIPT_DRAFTED",
            ):
                self.assertEqual(state["stages"][stage]["status"], "stale")

    def test_figure_validator_rejects_every_non_imagegen_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prompt = project / "figures/prompts/overview.md"
            generated = project / "figures/generated/overview.png"
            paper_asset = project / "paper/figures/overview.png"
            qa = project / "figures/qa/overview.md"
            provenance = project / "figures/qa/overview-provenance.json"
            imagegen_skill = project / "figures/qa/imagegen-SKILL.md"
            main_tex = project / "paper/main.tex"
            for path in (prompt, generated, paper_asset, qa, provenance, imagegen_skill, main_tex):
                path.parent.mkdir(parents=True, exist_ok=True)
            prompt.write_text(
                "Use case: scientific-educational\n"
                "Primary request: Explain the novel uncertainty-aware mechanism.\n"
                "Figure role: overview\n"
                "10-second message: The verifier enables localized repair.\n"
                "Paper claim: C-001\n"
                "Final-size target: 7.0 inches by 3.0 inches; 7:3.\n"
                "Reference synthesis: Three accepted-paper overviews; compact spine.\n"
                "Composition grammar: Three aligned phases on one rectangular grid.\n"
                "Reading order: left to right, then one subordinate repair return.\n"
                "Novelty emphasis: verifier and repair receive the largest central region.\n"
                "Color semantics: blue data, coral failure, teal repair.\n"
                "Text budget: eight labels, at most three words each.\n"
                "Domain visual evidence: pose sequence; trajectory; contact schedule.\n"
                "Generic-box area budget: <= 35%\n"
                "Three-glance hierarchy: claim; mechanism; local evidence.\n"
                "Composition archetypes evaluated: 3\n"
                "Hard vetoes: no crossings, dead corners, paragraphs, or equal-weight cards.\n"
                "Candidate directions evaluated: 6\n"
                "Targeted refinements completed: 3\n",
                encoding="utf-8",
            )
            image_bytes = make_png()
            generated.write_bytes(image_bytes)
            paper_asset.write_bytes(image_bytes)
            qa.write_text(
                "QA status: pass\n"
                "Faithfulness: pass\n"
                "Conciseness: pass\n"
                "Readability: pass\n"
                "Aesthetics: pass\n"
                "Domain evidence: pass\n"
                "Non-generic composition: pass\n"
                "Three-glance hierarchy: pass\n"
                "Novelty salience: pass\n"
                "Rectangular efficiency: pass\n"
                "Final-size inspection: pass\n\n"
                "Terminology, arrows, values, color, readability, and watermark checked.\n",
                encoding="utf-8",
            )
            imagegen_skill.write_text(
                '---\nname: "imagegen"\ndescription: test image generator\n---\n',
                encoding="utf-8",
            )
            main_tex.write_text("\\includegraphics{figures/overview.png}\n", encoding="utf-8")
            output_hash = hashlib.sha256(image_bytes).hexdigest()
            receipt = project / "figures/qa/overview-receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "skill_name": "imagegen",
                        "tool": "image_gen.imagegen",
                        "call_id": "image-call-001",
                        "skill_sha256": hashlib.sha256(imagegen_skill.read_bytes()).hexdigest(),
                        "started_at": "2026-08-01T00:00:00Z",
                        "completed_at": "2026-08-01T00:01:00Z",
                        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                        "output_sha256": output_hash,
                    }
                ),
                encoding="utf-8",
            )
            provenance.write_text(
                json.dumps(
                    {
                        "skill_name": "imagegen",
                        "tool": "image_gen.imagegen",
                        "mode": "generate",
                        "generated_at": "2026-08-01T00:00:00Z",
                        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                        "output_sha256": output_hash,
                        "receipt_path": "figures/qa/overview-receipt.json",
                        "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                        "skill_snapshot_path": "figures/qa/imagegen-SKILL.md",
                        "skill_snapshot_sha256": hashlib.sha256(imagegen_skill.read_bytes()).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            manifest = project / "figures/manifest.csv"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            fields = [
                "figure_id",
                "type",
                "claim_ids",
                "module_ids",
                "result_ids",
                "backend",
                "mode",
                "prompt_path",
                "input_paths",
                "generated_path",
                "paper_path",
                "version",
                "status",
                "qa_path",
                "provenance_path",
                "output_sha256",
            ]

            def write_manifest(backend: str, **overrides: str) -> None:
                with manifest.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    row = {
                        "figure_id": "FIG-OVERVIEW",
                        "type": "overview",
                        "claim_ids": "C-001",
                        "module_ids": "M-001",
                        "result_ids": "",
                        "backend": backend,
                        "mode": "generate",
                        "prompt_path": "figures/prompts/overview.md",
                        "input_paths": "",
                        "generated_path": "figures/generated/overview.png",
                        "paper_path": "paper/figures/overview.png",
                        "version": "v1",
                        "status": "final",
                        "qa_path": "figures/qa/overview.md",
                        "provenance_path": "figures/qa/overview-provenance.json",
                        "output_sha256": output_hash,
                    }
                    row.update(overrides)
                    writer.writerow(row)

            write_manifest("drawio")
            errors: list[str] = []
            validate_figures(project, errors, require_overview=True)
            self.assertTrue(any("backend must be imagegen" in error for error in errors))

            write_manifest("imagegen")
            errors = []
            validate_figures(project, errors, require_overview=True)
            self.assertEqual(errors, [])

            child_prompt = project / "figures/prompts/overview_v2.md"
            child_generated = project / "figures/generated/overview_v2.png"
            child_paper = project / "paper/figures/overview_v2.png"
            child_qa = project / "figures/qa/overview_v2.md"
            child_receipt = project / "figures/qa/overview_v2-receipt.json"
            child_provenance = project / "figures/qa/overview_v2-provenance.json"
            child_prompt.write_text(
                "Make exactly one surgical typography edit to the overview. "
                "Preserve absolutely everything else in content and composition.",
                encoding="utf-8",
            )
            child_generated.write_bytes(image_bytes)
            child_paper.write_bytes(image_bytes)
            child_qa.write_text(
                "QA status: passed\n"
                "Faithfulness: pass\n"
                "Readability: pass\n"
                "Aesthetics: pass\n"
                "Domain evidence: pass\n"
                "Non-generic composition: pass\n"
                "Three-glance hierarchy: pass\n"
                "Final-size inspection: pass\n",
                encoding="utf-8",
            )
            child_receipt.write_text(
                json.dumps(
                    {
                        "skill_name": "imagegen",
                        "tool": "image_gen.imagegen",
                        "call_id": "image-call-002",
                        "skill_sha256": hashlib.sha256(imagegen_skill.read_bytes()).hexdigest(),
                        "started_at": "2026-08-01T00:02:00Z",
                        "completed_at": "2026-08-01T00:03:00Z",
                        "prompt_sha256": hashlib.sha256(child_prompt.read_bytes()).hexdigest(),
                        "output_sha256": output_hash,
                    }
                ),
                encoding="utf-8",
            )
            child_provenance.write_text(
                json.dumps(
                    {
                        "skill_name": "imagegen",
                        "tool": "image_gen.imagegen",
                        "mode": "edit",
                        "generated_at": "2026-08-01T00:02:00Z",
                        "prompt_sha256": hashlib.sha256(child_prompt.read_bytes()).hexdigest(),
                        "output_sha256": output_hash,
                        "input_path": "figures/generated/overview.png",
                        "input_sha256": output_hash,
                        "receipt_path": "figures/qa/overview_v2-receipt.json",
                        "receipt_sha256": hashlib.sha256(child_receipt.read_bytes()).hexdigest(),
                        "skill_snapshot_path": "figures/qa/imagegen-SKILL.md",
                        "skill_snapshot_sha256": hashlib.sha256(imagegen_skill.read_bytes()).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            main_tex.write_text(
                "\\includegraphics{figures/overview_v2.png}\n", encoding="utf-8"
            )
            write_manifest(
                "imagegen",
                mode="edit",
                prompt_path="figures/prompts/overview_v2.md",
                input_paths="figures/generated/overview.png",
                generated_path="figures/generated/overview_v2.png",
                paper_path="paper/figures/overview_v2.png",
                version="v2",
                qa_path="figures/qa/overview_v2.md",
                provenance_path="figures/qa/overview_v2-provenance.json",
            )
            inherited_errors: list[str] = []
            validate_figures(project, inherited_errors, require_overview=True)
            self.assertEqual(inherited_errors, [])

            strong_prompt = prompt.read_text(encoding="utf-8")
            weak_prompt = (
                strong_prompt.replace(
                    "Domain visual evidence: pose sequence; trajectory; contact schedule.",
                    "Domain visual evidence: pose sequence; trajectory.",
                )
                .replace("Generic-box area budget: <= 35%", "Generic-box area budget: <= 60%")
                .replace("Composition archetypes evaluated: 3", "Composition archetypes evaluated: 2")
                .replace("Candidate directions evaluated: 6", "Candidate directions evaluated: 4")
                .replace("Targeted refinements completed: 3", "Targeted refinements completed: 2")
            )
            prompt.write_text(weak_prompt, encoding="utf-8")
            errors = []
            validate_figures(project, errors, require_overview=True)
            self.assertTrue(any("at least six" in error for error in errors))
            self.assertTrue(any("at least three composition archetypes" in error for error in errors))
            self.assertTrue(any("at least three domain visual-evidence" in error for error in errors))
            self.assertTrue(any("at most 35%" in error for error in errors))
            self.assertTrue(any("at least three targeted" in error for error in errors))
            prompt.write_text(strong_prompt, encoding="utf-8")

            unregistered = project / "paper/figures/unregistered.png"
            unregistered.write_bytes(b"not-registered")
            main_tex.write_text("\\includegraphics{figures/unregistered.png}\n", encoding="utf-8")
            errors = []
            validate_figures(project, errors, require_overview=True)
            self.assertTrue(any("unregistered paper figure" in error for error in errors))

    def test_qualitative_placeholder_must_bind_same_figure_imagegen_raster(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            section = project / "paper/sections/experiments.tex"
            section.parent.mkdir(parents=True)
            manifest_rows = [
                {
                    "figure_id": "FIG-QUAL",
                    "type": "qualitative",
                    "result_ids": "QUAL-MAIN",
                    "paper_path": "paper/figures/qualitative.png",
                }
            ]
            section.write_text(
                "\\QualPlaceholder{QUAL-MAIN}{Generate this later.}\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            validate_qualitative_figure_bindings(
                project, manifest_rows, errors, require_qualitative=True
            )
            self.assertTrue(any("must render inside a figure" in error for error in errors))

            section.write_text(
                "\\begin{figure}[t]\n"
                "\\includegraphics[width=\\linewidth]{figures/qualitative.png}\n"
                "\\caption{\\QualPlaceholder{QUAL-MAIN}{Conceptual layout only.}}\n"
                "\\label{fig:qualitative}\n"
                "\\end{figure}\n",
                encoding="utf-8",
            )
            errors = []
            validate_qualitative_figure_bindings(
                project, manifest_rows, errors, require_qualitative=True
            )
            self.assertEqual(errors, [])

    def test_inline_tikz_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paper = project / "paper"
            paper.mkdir()
            (paper / "main.tex").write_text(
                "\\usepackage{tikz}\n"
                "\\begin{figure}\\begin{tikzpicture}\\draw (0,0)--(1,1);"
                "\\end{tikzpicture}\\end{figure}\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            validate_no_alternate_figure_backends(project, errors)
            self.assertTrue(any("forbidden non-imagegen" in error for error in errors))

    def test_includegraphics_cannot_be_redefined_as_a_tex_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paper = project / "paper"
            paper.mkdir()
            (paper / "main.tex").write_text(
                "\\renewcommand{\\includegraphics}[2][]{%\n"
                "\\begin{tabular}{cc}A&B\\\\C&D\\end{tabular}}\n"
                "\\begin{figure}\\includegraphics{figures/token.png}"
                "\\caption{Forged raster.}\\label{fig:forged}\\end{figure}\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            validate_no_alternate_figure_backends(project, errors)
            self.assertTrue(
                any("protected raster command redefinition" in error for error in errors)
            )

    def test_tiny_registered_raster_cannot_cover_tex_composed_figure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paper = project / "paper"
            paper.mkdir()
            (paper / "main.tex").write_text(
                "\\begin{figure}[t]\n"
                "\\includegraphics[width=1pt]{figures/token.png}\n"
                "\\begin{tabular}{cc}A & B\\\\C & D\\end{tabular}\n"
                "\\caption{A TeX-composed diagram.}\\label{fig:bypass}\n"
                "\\end{figure}\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            validate_no_alternate_figure_backends(project, errors)
            self.assertTrue(any("composition primitives" in error for error in errors))
            self.assertTrue(any("token-sized" in error for error in errors))

            bypasses = (
                "\\begin{figure}\n"
                "\\scalebox{0.01}{\\includegraphics{figures/token.png}}\n"
                "\\[\\begin{aligned}A&\\to B\\\\B&\\to C\\end{aligned}\\]\n"
                "\\caption{Math-built diagram.}\\label{fig:scale-bypass}\n"
                "\\end{figure}\n",
                "\\begin{figure}\n"
                "\\resizebox{1pt}{!}{\\includegraphics{figures/token.png}}\n"
                "\\begin{center}$A \\rightarrow B$\\end{center}\n"
                "\\caption{Resized token.}\\label{fig:resize-bypass}\n"
                "\\end{figure}\n",
            )
            for bypass in bypasses:
                (paper / "main.tex").write_text(bypass, encoding="utf-8")
                bypass_errors: list[str] = []
                validate_no_alternate_figure_backends(project, bypass_errors)
                self.assertTrue(
                    any("unauthorized TeX structure" in error for error in bypass_errors)
                )

            (paper / "main.tex").write_text(
                "\\begin{figure}[t]\n"
                "\\begin{subfigure}{0.48\\linewidth}"
                "\\includegraphics[width=\\linewidth]{figures/a.png}"
                "\\caption{A}\\end{subfigure}\n"
                "\\begin{subfigure}{0.48\\linewidth}"
                "\\includegraphics[width=\\linewidth]{figures/b.png}"
                "\\caption{B}\\end{subfigure}\n"
                "\\caption{Standard imagegen raster subfigures.}\\label{fig:allowed}\n"
                "\\end{figure}\n",
                encoding="utf-8",
            )
            allowed_errors: list[str] = []
            validate_no_alternate_figure_backends(project, allowed_errors)
            self.assertEqual(allowed_errors, [])


if __name__ == "__main__":
    unittest.main()
