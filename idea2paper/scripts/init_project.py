#!/usr/bin/env python3
"""Initialize an idempotent idea2paper project workspace."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scan_resources import collect_resources
from state_manager import snapshot_inputs
from todo_lint import lint_directory


STAGES = [
    "INTAKE",
    "VENUE_LOCKED",
    "RESOURCES_READY",
    "LITERATURE_AUDITED",
    "IDEA_REVIEWED",
    "IDEA_FROZEN",
    "CLAIM_GRAPH_FROZEN",
    "METHOD_EXPERIMENT_READY",
    "TITLE_FROZEN",
    "MANUSCRIPT_DRAFTED",
    "SKETCH_COMPLETE",
    "RESULTS_INTEGRATED",
    "SUBMISSION_READY",
]

CLAIM_COLUMNS = [
    "claim_id",
    "limitation",
    "evidence_ids",
    "contribution_id",
    "contribution",
    "method_component",
    "hypothesis",
    "experiment_id",
    "datasets",
    "baselines",
    "metric",
    "figure_or_table",
    "manuscript_locations",
    "status",
]

BASELINE_COLUMNS = [
    "baseline_id",
    "paper_id",
    "method",
    "source_table",
    "dataset_version",
    "split",
    "training_data",
    "backbone",
    "preprocessing",
    "metric_definition",
    "test_setting",
    "reported_value",
    "directly_comparable",
    "notes",
]

FIGURE_COLUMNS = [
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:64].strip("-")
    if slug:
        return slug
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"idea2paper-{digest}"


def write_text_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json_if_missing(path: Path, payload: Any) -> None:
    write_text_if_missing(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_csv_if_missing(path: Path, columns: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(columns)


def state_payload(now: str) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    for stage in STAGES:
        status = "complete" if stage in {"INTAKE", "RESOURCES_READY"} else "pending"
        stages[stage] = {
            "status": status,
            "updated_utc": now if status == "complete" else None,
            "input_versions": {},
            "artifacts": [],
            "notes": [],
        }
    stages["INTAKE"]["artifacts"] = ["project.json", "idea/versions/idea_v0.md"]
    stages["RESOURCES_READY"]["artifacts"] = ["resources.json"]
    return {"schema_version": 1, "updated_utc": now, "stages": stages, "history": []}


def main_tex() -> str:
    return f"""\\documentclass{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{booktabs}}
\\usepackage{{idea2paper-draft}}

\\input{{title}}
\\title{{\\papertitle}}
\\author{{Anonymous Authors}}

\\begin{{document}}
\\maketitle
\\TemplateTODO{{TEMPLATE-UPDATE}}{{Replace the bootstrap article class with the official target-venue template.}}
% TODO(TEMPLATE-UPDATE): Replace with the official current-cycle venue template and recheck layout.

\\input{{sections/teaser}}
\\begin{{abstract}}
\\input{{sections/abstract}}
\\end{{abstract}}

\\input{{sections/introduction}}
\\input{{sections/related_work}}
\\input{{sections/method}}
\\input{{sections/experiments}}
\\input{{sections/conclusion}}
\\input{{sections/limitations}}
\\label{{idea2paper:end-body}}

\\bibliographystyle{{plain}}
\\bibliography{{references}}
\\label{{idea2paper:end-references}}
\\input{{appendix/appendix}}
\\end{{document}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idea", required=True, help="Original research idea")
    parser.add_argument("--out-dir", type=Path, default=Path("idea2paper-projects"))
    parser.add_argument("--slug", help="Optional project slug")
    parser.add_argument("--venue", default="auto", help="User-specified venue or auto")
    parser.add_argument("--language", default="en")
    parser.add_argument(
        "--resources-file",
        type=Path,
        help="Optional user-supplied compute/data resource JSON; defaults to the current machine",
    )
    parser.add_argument(
        "--data-source",
        choices=["relevant_open_candidates", "user"],
        default="relevant_open_candidates",
        help="Data-resource mode when initializing the project",
    )
    parser.add_argument("--resume", action="store_true", help="Reuse an existing workspace without overwriting files")
    args = parser.parse_args()

    slug = args.slug or slugify(args.idea)
    parent = args.out_dir.expanduser().resolve()
    root = parent / slug
    if root.exists() and any(root.iterdir()) and not args.resume:
        raise SystemExit(f"Project already exists: {root}. Use --resume instead of overwriting it.")
    if root.exists() and args.resume and (root / "project.json").exists():
        existing = json.loads((root / "project.json").read_text(encoding="utf-8"))
        if existing.get("idea_original") != args.idea:
            raise SystemExit(
                "The supplied idea differs from the existing project's original idea. "
                "Resume with the original idea, then version changes through the idea council."
            )
    root.mkdir(parents=True, exist_ok=True)
    is_new_project = not (root / "project.json").exists()

    supplied_resources: dict[str, Any] | None = None
    if args.resources_file:
        supplied_resources = json.loads(args.resources_file.expanduser().read_text(encoding="utf-8"))
        if not isinstance(supplied_resources, dict):
            raise SystemExit("--resources-file must contain a JSON object")
        supplied_resources.setdefault("schema_version", 1)
        supplied_resources["source"] = "user"
        supplied_resources.setdefault("collected_utc", utc_now())

    directories = [
        "venue/template",
        "related_works/papers",
        "related_works/notes",
        "related_works/raw",
        "related_works/exports",
        "idea/versions",
        "idea/meetings",
        "title",
        "method",
        "experiments",
        "figures/prompts",
        "figures/inputs",
        "figures/generated",
        "figures/qa",
        "paper/sections",
        "paper/tables",
        "paper/figures",
        "paper/appendix",
        "qa",
        "build",
    ]
    for relative in directories:
        (root / relative).mkdir(parents=True, exist_ok=True)

    now = utc_now()
    project = {
        "schema_version": 1,
        "project_id": slug,
        "created_utc": now,
        "updated_utc": now,
        "idea_original": args.idea,
        "idea_current": args.idea,
        "idea_version": "idea_v0",
        "language": args.language,
        "target_venue": args.venue,
        "venue_selection_mode": "auto" if args.venue.lower() == "auto" else "user",
        "compute_source": "user" if supplied_resources is not None else "current_machine",
        "data_source": args.data_source,
        "automation_mode": "autopilot",
        "existing_assets": {"papers": [], "code": [], "data": [], "models": [], "results": []},
        "assumptions": [
            f"Paper language is {args.language}.",
            (
                "Venue will be selected automatically by topic fit and the nearest open abstract "
                "deadline."
                if args.venue.lower() == "auto"
                else f"Target venue was supplied by the user: {args.venue}."
            ),
            (
                "Compute capacity defaults to the current machine snapshot."
                if supplied_resources is None
                else "Compute/data resources were supplied by the user."
            ),
            (
                "Candidate data resources are relevant accessible research-licensed open datasets."
                if args.data_source == "relevant_open_candidates"
                else "Data resources are supplied by the user."
            ),
        ],
    }
    write_json_if_missing(root / "project.json", project)
    write_json_if_missing(root / "state.json", state_payload(now))
    write_json_if_missing(root / "resources.json", supplied_resources or collect_resources(root))
    write_json_if_missing(root / "venue/candidates.json", {"candidates": []})
    write_json_if_missing(
        root / "venue/decision.json",
        {"schema_version": 1, "status": "pending", "selection_mode": project["venue_selection_mode"], "selected": None},
    )
    write_json_if_missing(root / "qa/todo_registry.json", {"schema_version": 1, "items": [], "errors": []})
    write_json_if_missing(
        root / "title/brief.json",
        {
            "schema_version": 1,
            "status": "pending",
            "idea_version": "idea_v0",
            "project_label": slug,
            "project_directory_is_not_title": True,
            "required_concepts": [],
            "forbidden_claims": [],
        },
    )
    write_json_if_missing(
        root / "title/candidates.json",
        {"schema_version": 1, "status": "pending", "idea_version": "idea_v0", "candidates": []},
    )
    write_json_if_missing(
        root / "title/decision.json",
        {"schema_version": 1, "status": "pending", "selected_candidate_id": None, "selected_title": None},
    )
    write_text_if_missing(root / "title/history.jsonl", "")

    write_text_if_missing(root / "idea/versions/idea_v0.md", f"# Original Idea\n\n{args.idea}\n")
    write_csv_if_missing(root / "idea/claims.csv", ["claim_id", "statement", "scope", "evidence_ids", "status"])
    write_csv_if_missing(root / "idea/terminology.csv", ["term", "definition", "allowed_variants", "notes"])
    write_text_if_missing(root / "method/method_spec.md", "# Method Specification\n\n")
    write_text_if_missing(root / "method/decision_log.md", "# Internal Method Decision Log\n\n")
    write_text_if_missing(root / "experiments/plan.md", "# Experiment Plan\n\n")
    write_csv_if_missing(root / "experiments/claim_experiment_matrix.csv", CLAIM_COLUMNS)
    write_csv_if_missing(root / "experiments/baseline_provenance.csv", BASELINE_COLUMNS)
    write_csv_if_missing(root / "figures/manifest.csv", FIGURE_COLUMNS)

    skill_root = Path(__file__).resolve().parents[1]
    style_source = skill_root / "assets/idea2paper-draft.sty"
    style_target = root / "paper/idea2paper-draft.sty"
    if not style_target.exists():
        shutil.copy2(style_source, style_target)

    write_text_if_missing(root / "paper/title.tex", "\\newcommand{\\papertitle}{Working Title Pending}\n")
    write_text_if_missing(root / "paper/main.tex", main_tex())
    section_titles = {
        "teaser.tex": "% Teaser is inserted here only when venue rules permit it.\n",
        "abstract.tex": "% Abstract prose.\n",
        "introduction.tex": "\\section{Introduction}\n",
        "related_work.tex": "\\section{Related Work}\n",
        "method.tex": "\\section{Method}\n",
        "experiments.tex": "\\section{Experiments}\n",
        "conclusion.tex": "\\section{Conclusion}\n",
        "limitations.tex": "\\section{Limitations}\n",
    }
    for filename, content in section_titles.items():
        write_text_if_missing(root / "paper/sections" / filename, content)
    write_text_if_missing(root / "paper/appendix/appendix.tex", "\\appendix\n\\section{Additional Material}\n")
    write_text_if_missing(root / "paper/references.bib", "")

    todo_report = lint_directory(root / "paper", mode="sketch")
    (root / "qa/todo_registry.json").write_text(
        json.dumps(todo_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if is_new_project:
        state_path = root / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for stage in ("INTAKE", "RESOURCES_READY"):
            state["stages"][stage]["input_versions"] = snapshot_inputs(root, stage)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"project_root": str(root), "slug": slug, "resumed": args.resume}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
