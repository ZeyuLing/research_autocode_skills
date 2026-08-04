#!/usr/bin/env python3
"""Validate tracked red draft macros and adjacent LaTeX TODO comments."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


MACRO_TYPES = {
    "PredResult": "PREDICTED_RESULT",
    "PredClaim": "PREDICTED_RESULT",
    "DraftChoice": "METHOD_ALTERNATIVE",
    "QualPlaceholder": "QUALITATIVE_PLACEHOLDER",
    "TemplateTODO": "TEMPLATE_UPDATE",
}
MACRO_RE = re.compile(
    r"\\(PredResult|PredClaim|DraftChoice|QualPlaceholder|TemplateTODO)\s*\{\s*([^{}\s]+)\s*\}",
    re.MULTILINE,
)
DRAFT_MACRO_NAME_RE = re.compile(r"\\(?:PredResult|PredClaim|DraftChoice|QualPlaceholder|TemplateTODO)\b")
TODO_RE = re.compile(r"%\s*TODO\(([^)]+)\)\s*:\s*(.+)", re.IGNORECASE)
ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*$")
INCLUDE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]+)\}", re.MULTILINE)
DIRECT_COLOR_RE = re.compile(
    r"\\(?:textcolor|color|colorbox|fcolorbox|definecolor|rowcolor|cellcolor|pagecolor)\b",
    re.IGNORECASE,
)


def infer_type(item_id: str) -> str:
    upper = item_id.upper()
    if upper.startswith("TEMPLATE"):
        return "TEMPLATE_UPDATE"
    if upper.startswith("M-") or upper.startswith("METHOD"):
        return "METHOD_ALTERNATIVE"
    if upper.startswith("QUAL") or upper.startswith("Q-"):
        return "QUALITATIVE_PLACEHOLDER"
    return "PREDICTED_RESULT"


def strip_tex_comments(text: str) -> str:
    cleaned: list[str] = []
    for line in text.splitlines(keepends=True):
        comment_at: int | None = None
        for index, character in enumerate(line):
            if character != "%":
                continue
            preceding_backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                preceding_backslashes += 1
                cursor -= 1
            if preceding_backslashes % 2 == 0:
                comment_at = index
                break
        if comment_at is None:
            cleaned.append(line)
            continue
        suffix = line[comment_at:]
        newline = "\n" if suffix.endswith("\n") else ""
        cleaned.append(line[:comment_at] + (" " * (len(suffix) - len(newline))) + newline)
    return "".join(cleaned)


def lint_directory(root: Path, mode: str = "sketch", adjacent_lines: int = 3) -> dict[str, Any]:
    root = root.expanduser().resolve()
    macros: list[dict[str, Any]] = []
    todos: list[dict[str, Any]] = []
    includes: list[dict[str, Any]] = []
    errors: list[str] = []
    tex_files = sorted(root.rglob("*.tex"))

    file_lines: dict[Path, list[str]] = {}
    for path in tex_files:
        portable_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        cleaned = strip_tex_comments(text)
        lines = text.splitlines()
        cleaned_lines = cleaned.splitlines()
        file_lines[path] = lines
        for match in MACRO_RE.finditer(cleaned):
            macro_name, item_id = match.groups()
            item_id = item_id.strip()
            line_number = cleaned.count("\n", 0, match.start()) + 1
            macros.append(
                {
                    "id": item_id,
                    "type": MACRO_TYPES[macro_name],
                    "macro": macro_name,
                    "file": portable_path,
                    "line": line_number,
                }
            )
            if not ID_RE.fullmatch(item_id):
                errors.append(f"{path}:{line_number}: invalid draft ID {item_id!r}")
        for match in INCLUDE_RE.finditer(cleaned):
            line_number = cleaned.count("\n", 0, match.start()) + 1
            includes.append({"file": portable_path, "line": line_number, "path": match.group(1).strip()})
        for index, line in enumerate(lines, start=1):
            for match in TODO_RE.finditer(line):
                item_id, message = match.groups()
                item_id = item_id.strip()
                todos.append({"id": item_id, "message": message.strip(), "file": portable_path, "line": index})
                if not ID_RE.fullmatch(item_id):
                    errors.append(f"{path}:{index}: invalid TODO ID {item_id!r}")
            if (
                "TODO" in line.upper()
                and not TODO_RE.search(line)
                and not MACRO_RE.search(line)
                and not DRAFT_MACRO_NAME_RE.search(line)
            ):
                errors.append(f"{path}:{index}: untracked TODO syntax")
            clean_line = cleaned_lines[index - 1] if index <= len(cleaned_lines) else ""
            if DIRECT_COLOR_RE.search(clean_line):
                errors.append(
                    f"{path}:{index}: direct color commands are forbidden; use a tracked idea2paper draft macro or style file"
                )

    macro_by_id: dict[str, list[dict[str, Any]]] = {}
    for item in macros:
        macro_by_id.setdefault(item["id"], []).append(item)

    for macro in macros:
        portable_path = str(macro["file"])
        path = root / portable_path
        nearby = [
            todo
            for todo in todos
            if todo["file"] == portable_path
            and todo["id"] == macro["id"]
            and abs(int(todo["line"]) - int(macro["line"])) <= adjacent_lines
        ]
        if not nearby:
            errors.append(
                f"{path}:{macro['line']}: {macro['macro']} ID {macro['id']} lacks an adjacent matching TODO"
            )

    for todo in todos:
        linked_macro = todo["id"] in macro_by_id
        near_include = any(
            include["file"] == todo["file"]
            and abs(int(include["line"]) - int(todo["line"])) <= adjacent_lines
            for include in includes
        )
        if not linked_macro and not near_include:
            errors.append(f"{todo['file']}:{todo['line']}: TODO {todo['id']} is not linked to a draft macro or figure")

    if mode == "submission" and (macros or todos):
        errors.append("submission mode forbids all idea2paper draft macros and TODO comments")

    registry_items: list[dict[str, Any]] = []
    for item_id in sorted({item["id"] for item in macros + todos}):
        occurrences = [item for item in macros if item["id"] == item_id]
        todo_occurrences = [item for item in todos if item["id"] == item_id]
        item_type = occurrences[0]["type"] if occurrences else infer_type(item_id)
        registry_items.append(
            {
                "id": item_id,
                "type": item_type,
                "status": "open",
                "macro_occurrences": occurrences,
                "todo_occurrences": todo_occurrences,
            }
        )

    return {
        "schema_version": 1,
        "mode": mode,
        "root": ".",
        "files_scanned": len(tex_files),
        "items": registry_items,
        "errors": errors,
        "status": "pass" if not errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Paper directory to scan recursively")
    parser.add_argument("--mode", choices=["sketch", "submission"], default="sketch")
    parser.add_argument("--adjacent-lines", type=int, default=3)
    parser.add_argument("--registry", type=Path, help="Optional registry JSON output")
    args = parser.parse_args()

    report = lint_directory(args.root, args.mode, args.adjacent_lines)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.registry:
        args.registry.parent.mkdir(parents=True, exist_ok=True)
        args.registry.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
