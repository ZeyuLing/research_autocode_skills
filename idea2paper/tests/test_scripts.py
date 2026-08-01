from __future__ import annotations

import binascii
import csv
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_project import (  # noqa: E402
    has_draft_marker,
    validate_figures,
    validate_no_alternate_figure_backends,
    validate_title,
)
from compile_paper import aux_label_page, command_for, source_tree_sha256  # noqa: E402


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


class Idea2PaperScriptTests(unittest.TestCase):
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
            venue = {"selected": {"name": "3DV", "edition": "2027"}}
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
                        "venue_name": "3DV",
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
                "venue_name": "3DV",
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
                "Primary request: Explain the novel uncertainty-aware mechanism.\n",
                encoding="utf-8",
            )
            image_bytes = make_png()
            generated.write_bytes(image_bytes)
            paper_asset.write_bytes(image_bytes)
            qa.write_text("QA status: pass\n\nTerminology, arrows, values, color, readability, and watermark checked.\n", encoding="utf-8")
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

            def write_manifest(backend: str) -> None:
                with manifest.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerow(
                        {
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
                    )

            write_manifest("drawio")
            errors: list[str] = []
            validate_figures(project, errors, require_overview=True)
            self.assertTrue(any("backend must be imagegen" in error for error in errors))

            write_manifest("imagegen")
            errors = []
            validate_figures(project, errors, require_overview=True)
            self.assertEqual(errors, [])

            unregistered = project / "paper/figures/unregistered.png"
            unregistered.write_bytes(b"not-registered")
            main_tex.write_text("\\includegraphics{figures/unregistered.png}\n", encoding="utf-8")
            errors = []
            validate_figures(project, errors, require_overview=True)
            self.assertTrue(any("unregistered paper figure" in error for error in errors))

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


if __name__ == "__main__":
    unittest.main()
