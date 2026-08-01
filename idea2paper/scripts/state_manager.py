#!/usr/bin/env python3
"""Show, update, and invalidate idea2paper stage state."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_STATUSES = {"pending", "in_progress", "complete", "stale", "blocked"}

INVALIDATION = {
    "idea": [
        "VENUE_LOCKED",
        "LITERATURE_AUDITED",
        "IDEA_REVIEWED",
        "IDEA_FROZEN",
        "CLAIM_GRAPH_FROZEN",
        "METHOD_EXPERIMENT_READY",
        "MANUSCRIPT_DRAFTED",
        "SKETCH_COMPLETE",
        "RESULTS_INTEGRATED",
        "SUBMISSION_READY",
    ],
    "literature": [
        "IDEA_REVIEWED",
        "IDEA_FROZEN",
        "CLAIM_GRAPH_FROZEN",
        "METHOD_EXPERIMENT_READY",
        "MANUSCRIPT_DRAFTED",
        "SKETCH_COMPLETE",
        "RESULTS_INTEGRATED",
        "SUBMISSION_READY",
    ],
    "resources": [
        "IDEA_REVIEWED",
        "IDEA_FROZEN",
        "CLAIM_GRAPH_FROZEN",
        "METHOD_EXPERIMENT_READY",
        "MANUSCRIPT_DRAFTED",
        "SKETCH_COMPLETE",
        "RESULTS_INTEGRATED",
        "SUBMISSION_READY",
    ],
    "venue": [
        "VENUE_LOCKED",
        "LITERATURE_AUDITED",
        "IDEA_REVIEWED",
        "IDEA_FROZEN",
        "CLAIM_GRAPH_FROZEN",
        "METHOD_EXPERIMENT_READY",
        "MANUSCRIPT_DRAFTED",
        "SKETCH_COMPLETE",
        "SUBMISSION_READY",
    ],
    "results": ["MANUSCRIPT_DRAFTED", "SKETCH_COMPLETE", "RESULTS_INTEGRATED", "SUBMISSION_READY"],
    "figure": ["MANUSCRIPT_DRAFTED", "SKETCH_COMPLETE", "SUBMISSION_READY"],
}

STAGE_INPUTS = {
    "INTAKE": ["project.json", "idea/versions/idea_v0.md"],
    "VENUE_LOCKED": ["project.json", "venue/candidates.json", "venue/decision.json", "venue/template/**/*"],
    "RESOURCES_READY": ["resources.json"],
    "LITERATURE_AUDITED": [
        "project.json",
        "venue/decision.json",
        "related_works/*",
        "related_works/papers/**/*",
        "related_works/notes/**/*",
    ],
    "IDEA_REVIEWED": [
        "project.json",
        "resources.json",
        "related_works/*",
        "idea/versions/*.md",
        "idea/meetings/**/*",
    ],
    "IDEA_FROZEN": ["project.json", "idea/versions/*.md", "idea/meetings/**/*", "idea/claims.csv"],
    "CLAIM_GRAPH_FROZEN": [
        "project.json",
        "idea/versions/*.md",
        "idea/claims.csv",
        "experiments/claim_experiment_matrix.csv",
    ],
    "METHOD_EXPERIMENT_READY": [
        "idea/claims.csv",
        "method/**/*",
        "experiments/*",
    ],
    "MANUSCRIPT_DRAFTED": [
        "method/**/*",
        "experiments/*",
        "figures/manifest.csv",
        "figures/generated/**/*",
        "paper/**/*.tex",
        "paper/*.sty",
        "paper/references.bib",
    ],
    "SKETCH_COMPLETE": [
        "project.json",
        "resources.json",
        "venue/**/*",
        "related_works/*",
        "idea/**/*",
        "method/**/*",
        "experiments/**/*",
        "figures/**/*",
        "paper/**/*",
        "qa/**/*",
    ],
    "RESULTS_INTEGRATED": ["experiments/**/*", "figures/**/*", "paper/**/*"],
    "SUBMISSION_READY": ["project.json", "venue/**/*", "experiments/**/*", "figures/**/*", "paper/**/*", "qa/**/*"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_inputs(project: Path, stage: str) -> dict[str, str]:
    root = project.expanduser().resolve()
    paths: set[Path] = set()
    for pattern in STAGE_INPUTS.get(stage, []):
        paths.update(path for path in root.glob(pattern) if path.is_file())
    paths = {
        path
        for path in paths
        if path.name not in {"final_report.json", "sketch_validation.json", "submission_validation.json"}
    }
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(paths, key=lambda item: item.as_posix())
    }


def state_path(project: Path) -> Path:
    return project.expanduser().resolve() / "state.json"


def load_state(project: Path) -> tuple[Path, dict[str, Any]]:
    path = state_path(project)
    if not path.exists():
        raise SystemExit(f"Missing state file: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, payload: dict[str, Any]) -> None:
    payload["updated_utc"] = now()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser("show")
    show.add_argument("project", type=Path)

    set_parser = subparsers.add_parser("set")
    set_parser.add_argument("project", type=Path)
    set_parser.add_argument("stage")
    set_parser.add_argument("status", choices=sorted(VALID_STATUSES))
    set_parser.add_argument("--note", default="")
    set_parser.add_argument("--artifact", action="append", default=[], help="Stage artifact path; repeat as needed")

    invalidate = subparsers.add_parser("invalidate")
    invalidate.add_argument("project", type=Path)
    invalidate.add_argument("--cause", choices=sorted(INVALIDATION), required=True)
    invalidate.add_argument("--note", default="")

    args = parser.parse_args()
    path, state = load_state(args.project)
    stages = state.get("stages", {})

    if args.command == "show":
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    timestamp = now()
    if args.command == "set":
        if args.stage not in stages:
            raise SystemExit(f"Unknown stage: {args.stage}")
        stages[args.stage]["status"] = args.status
        stages[args.stage]["updated_utc"] = timestamp
        if args.status == "complete":
            stages[args.stage]["input_versions"] = snapshot_inputs(args.project, args.stage)
            if args.artifact:
                stages[args.stage]["artifacts"] = list(dict.fromkeys(args.artifact))
        if args.note:
            stages[args.stage].setdefault("notes", []).append(args.note)
        state.setdefault("history", []).append(
            {"time": timestamp, "action": "set", "stage": args.stage, "status": args.status, "note": args.note}
        )
        save_state(path, state)
        print(json.dumps({"stage": args.stage, "status": args.status}, ensure_ascii=False))
        return 0

    changed: list[str] = []
    for stage_name in INVALIDATION[args.cause]:
        if stage_name not in stages:
            continue
        current = stages[stage_name].get("status", "pending")
        if current in {"complete", "in_progress", "blocked"}:
            stages[stage_name]["status"] = "stale"
            stages[stage_name]["updated_utc"] = timestamp
            note = args.note or f"Invalidated by {args.cause} change"
            stages[stage_name].setdefault("notes", []).append(note)
            changed.append(stage_name)
    state.setdefault("history", []).append(
        {"time": timestamp, "action": "invalidate", "cause": args.cause, "stages": changed, "note": args.note}
    )
    save_state(path, state)
    print(json.dumps({"cause": args.cause, "invalidated": changed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
