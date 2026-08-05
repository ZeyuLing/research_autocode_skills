#!/usr/bin/env python3
"""Compile a LaTeX paper, check unresolved references, and report PDF pages."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANUAL_PAGINATION_RE = re.compile(r"\\(clearpage|newpage|pagebreak|FloatBarrier)\b")
FORCED_H_FLOAT_RE = re.compile(
    r"\\begin\{(?P<environment>figure\*?|table\*?)\}\s*\[\s*H\s*\]",
    re.IGNORECASE,
)
TEX_FUZZ_REGISTER_RE = re.compile(r"\\(?P<register>[hv]fuzz)(?![A-Za-z@])")
OVERFULL_BOX_RE = re.compile(
    r"Overfull\s+\\(?P<axis>[hv])box\s+\("
    r"(?P<excess>[0-9]+(?:\.[0-9]+)?)pt\s+too\s+(?P<dimension>wide|high)\)"
    r"(?P<context>[^\r\n]*)",
    re.IGNORECASE,
)
MATERIAL_OVERFULL_PT = 2.0
MEDIA_BOX_OVERFLOW_PT = 2.0
CORE_BUILD_ARTIFACTS = (
    "main.aux",
    "main.bbl",
    "main.bcf",
    "main.blg",
    "main.dvi",
    "main.fdb_latexmk",
    "main.fls",
    "main.lof",
    "main.log",
    "main.lot",
    "main.out",
    "main.pdf",
    "main.run.xml",
    "main.synctex.gz",
    "main.toc",
    "main.xdv",
)
INPUT_RE = re.compile(
    r"\\(?P<command>input|include)(?![A-Za-z@])\s*"
    r"(?:\{(?P<braced>[^}]+)\}|(?P<bare>[^\s%{}]+))"
)
FLOAT_RE = re.compile(
    r"\\begin\{((?:figure|table)\*?)\}([\s\S]*?)\\end\{(?:figure|table)\*?\}"
)
CAPTIONOF_RE = re.compile(r"\\captionof\{(?P<kind>figure|table)\}")
TITLE_TEASER_RE = re.compile(
    r"\\begin\{IdeaTwoPaperTitleTeaser\}(?P<header>[^\r\n]*)"
)
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
BODY_END_MARKER = r"\label{idea2paper:end-body}"
BODY_EXEMPT_END_MARKER = r"\label{idea2paper:end-exempt}"
BODY_REFERENCES_END_MARKER = r"\label{idea2paper:end-references}"
CONCLUSION_LABEL = "idea2paper:start-conclusion"
APPENDIX_START_LABEL = "idea2paper:start-appendix"
CONCLUSION_HEADING_RE = re.compile(r"\\section\*?\s*\{Conclusion\}")
CONCLUSION_BLOCK_RE = re.compile(
    r"\\section\*?\s*\{Conclusion\}\s*\\label\{idea2paper:start-conclusion\}"
)
BIBLIOGRAPHY_RE = re.compile(r"\\(?:bibliography\s*\{|printbibliography\b|begin\{thebibliography\})")
APPENDIX_RE = re.compile(r"\\appendix\b")
APPENDIX_BLOCK_RE = re.compile(
    r"\\appendix\s*\\label\{idea2paper:start-appendix\}"
)
TEX_CONDITIONAL_RE = re.compile(r"\\(?:if[A-Za-z@]*|else|fi)\b")
BIBLIOGRAPHY_TARGET_RE = re.compile(r"\\bibliography\s*\{([^}]+)\}")
ADD_BIB_RESOURCE_RE = re.compile(
    r"\\addbibresource\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}"
)
BIBLIOGRAPHY_STYLE_RE = re.compile(r"\\bibliographystyle\s*\{([^}]+)\}")
INCLUDE_GRAPHICS_RE = re.compile(
    r"\\includegraphics\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}"
)
INCLUDE_PDF_RE = re.compile(r"\\includepdf\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
GRAPHICSPATH_RE = re.compile(r"\\graphicspath\b")
DYNAMIC_FILE_READ_RE = re.compile(
    r"\\(?:verbatiminput|lstinputlisting|inputminted|openin|read|InputIfFileExists|"
    r"IfFileExists|import|subimport|includefrom|subincludefrom|externaldocument|@input|"
    r"inputfrom|subinputfrom|file_input(?::[A-Za-z]+)?)\b"
)
DYNAMIC_FILE_WRITE_RE = re.compile(r"\\(?:newwrite|openout|closeout|write)\b")
DYNAMIC_TEX_PRIMITIVE_RE = re.compile(
    r"\\(?:csname|endcsname|expandafter|let|futurelet|catcode|@@input|@@end|ExplSyntaxOn|"
    r"ExplSyntaxOff)\b|\^\^"
)
GUARDED_REDEFINITION_RE = re.compile(
    r"\\(?:def|edef|gdef|xdef)\s*\\(?:appendix|section|label|bibliography|input|include|thepage)\b"
    r"|\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\s*\{?\s*"
    r"\\(?:appendix|section|label|bibliography|input|include|thepage)\b"
)
PACKAGE_RE = re.compile(
    r"\\(?:usepackage|RequirePackage)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}"
)
DOCUMENT_CLASS_RE = re.compile(r"\\documentclass\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
AI_LAYOUT_RE = re.compile(
    r"\\(?:vspace|vfill|hspace|includegraphics|includepdf|rule|parbox|begin|end)\b"
)
PAGE_MANIPULATION_RE = re.compile(
    r"\\(?:setcounter|addtocounter)\s*\{page\}|\\(?:pagenumbering|shipout|afterpage|"
    r"vadjust|insert|output|c@page|countdef)\b|\\count\s*0\b"
)
STATIC_PATH_FORBIDDEN = frozenset("\\{}#$%&^~`")
GRAPHIC_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".eps", ".svg")
BUILTIN_BIBLIOGRAPHY_STYLES = frozenset({"plain", "abbrv", "alpha", "unsrt"})
INTERNAL_AUDITED_LATEX_ASSETS = frozenset({"idea2paper-draft.sty"})


def choose_engine(requested: str) -> str | None:
    if requested != "auto":
        return shutil.which(requested)
    for name in ("latexmk", "tectonic", "pdflatex"):
        found = shutil.which(name)
        if found:
            return found
    return None


def command_for(engine: str, paper: Path, build: Path) -> list[str]:
    name = Path(engine).stem.lower()
    if name == "latexmk":
        return [
            engine,
            "-g",
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-outdir={build}",
            "main.tex",
        ]
    if name == "tectonic":
        return [engine, "--keep-logs", "--keep-intermediates", "--outdir", str(build), "main.tex"]
    return [engine, "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={build}", "main.tex"]


def pdf_pages(path: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            result = subprocess.run([pdfinfo, str(path)], capture_output=True, text=True, timeout=30, check=True)
            match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
            if match:
                return int(match.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except (ImportError, OSError, ValueError):
        return None


def latex_overfull_boxes(log_text: str) -> list[dict[str, Any]]:
    """Return deterministic TeX overfull-box diagnostics from a compiler log."""

    diagnostics: list[dict[str, Any]] = []
    for match in OVERFULL_BOX_RE.finditer(log_text):
        excess = float(match.group("excess"))
        diagnostics.append(
            {
                "axis": match.group("axis").lower(),
                "dimension": match.group("dimension").lower(),
                "excess_pt": excess,
                "context": match.group("context").strip(),
                "material": excess > MATERIAL_OVERFULL_PT,
            }
        )
    return diagnostics


def clean_core_build_artifacts(build: Path) -> list[str]:
    """Remove only known ``main.*`` compiler outputs before a fresh build."""

    removed: list[str] = []
    for name in CORE_BUILD_ARTIFACTS:
        target = build / name
        if target.is_file() or target.is_symlink():
            target.unlink()
            removed.append(name)
        elif target.exists():
            raise OSError(f"expected build artifact to be a file: {target}")
    return removed


def aux_label_page(path: Path, label: str) -> int | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"\\newlabel\{{{re.escape(label)}\}}\{{\{{[^}}]*\}}\{{(\d+)\}}", text)
    return int(match.group(1)) if match else None


def strip_tex_comments(source: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in source.splitlines())


def _validate_static_path(value: str, kind: str) -> str:
    target = value.strip()
    if not target or any(character in STATIC_PATH_FORBIDDEN for character in target):
        raise ValueError(f"{kind} must use a static literal path: {value}")
    if Path(target).is_absolute() or re.match(r"^[A-Za-z]:", target):
        raise ValueError(f"{kind} must stay under the paper directory: {value}")
    return target


def _resolve_under_paper(paper: Path, value: str, kind: str) -> Path:
    target = _validate_static_path(value, kind)
    resolved = (paper / target).resolve()
    try:
        resolved.relative_to(paper.resolve())
    except ValueError as exc:
        raise ValueError(f"{kind} escapes the paper directory: {value}") from exc
    return resolved


def _resolve_input(current: Path, value: str, paper: Path) -> Path:
    del current  # All author inputs are paper-root-relative, matching the compile working directory.
    candidate = _resolve_under_paper(paper, value, "LaTeX input")
    if not candidate.suffix:
        candidate = candidate.with_suffix(".tex")
    if not candidate.is_file():
        raise ValueError(f"LaTeX input does not resolve to a local file: {value}")
    return candidate


def active_tex_segments(paper: Path, stop_marker: str | None = None) -> list[dict[str, Any]]:
    """Recursively expand reachable .tex inputs, optionally stopping at a body marker."""

    paper = paper.resolve()
    main_tex = paper / "main.tex"
    if not main_tex.is_file():
        return []
    segments: list[dict[str, Any]] = []

    def append_segment(path: Path, source: str, start: int, end: int) -> bool:
        text = source[start:end]
        if stop_marker:
            marker_index = text.find(stop_marker)
            if marker_index >= 0:
                text = text[:marker_index]
                if text:
                    segments.append(
                        {
                            "path": path.relative_to(paper).as_posix(),
                            "line": source.count("\n", 0, start) + 1,
                            "column": start - source.rfind("\n", 0, start),
                            "text": text,
                        }
                    )
                return True
        if text:
            segments.append(
                {
                    "path": path.relative_to(paper).as_posix(),
                    "line": source.count("\n", 0, start) + 1,
                    "column": start - source.rfind("\n", 0, start),
                    "text": text,
                }
            )
        return False

    def expand(path: Path, stack: tuple[Path, ...]) -> bool:
        if path in stack:
            chain = " -> ".join(item.name for item in (*stack, path))
            raise ValueError(f"Circular LaTeX input chain: {chain}")
        source = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
        cursor = 0
        for match in INPUT_RE.finditer(source):
            if append_segment(path, source, cursor, match.start()):
                return True
            target = match.group("braced") or match.group("bare") or ""
            child = _resolve_input(path, target, paper)
            if expand(child, (*stack, path)):
                return True
            cursor = match.end()
        return append_segment(path, source, cursor, len(source))

    expand(main_tex, ())
    return segments


def _combined_source(segments: list[dict[str, Any]]) -> str:
    return "".join(str(segment["text"]) for segment in segments)


def _source_match_location(
    path: str, source: str, base_line: int, base_column: int, offset: int
) -> dict[str, Any]:
    line_start = source.rfind("\n", 0, offset) + 1
    line_offset = source.count("\n", 0, offset)
    return {
        "path": path,
        "line": base_line + line_offset,
        "column": (base_column if line_offset == 0 else 1) + offset - line_start,
    }


def tex_fuzz_register_uses(paper: Path) -> list[dict[str, Any]]:
    """Find fuzz-register use in active author inputs and unbound local styles."""

    paper = paper.resolve()
    official_template_hashes = _official_template_asset_hashes(paper)
    segments = active_tex_segments(paper)
    sources = [
        {
            "path": str(segment["path"]),
            "line": int(segment["line"]),
            "column": int(segment.get("column", 1)),
            "text": str(segment["text"]),
        }
        for segment in segments
    ]
    seen_paths = {str(segment["path"]) for segment in sources}
    asset_queue: list[Path] = []

    def enqueue_local(target: str, suffix: str, current: Path | None = None) -> None:
        value = target.strip()
        if not value or any(character in STATIC_PATH_FORBIDDEN for character in value):
            return
        raw = Path(value)
        candidates: list[Path] = []
        if current is not None:
            candidates.append((current.parent / raw).resolve())
        candidates.append((paper / raw).resolve())
        for candidate in candidates:
            if not candidate.suffix:
                candidate = candidate.with_suffix(suffix)
            try:
                relative = candidate.relative_to(paper).as_posix()
            except ValueError:
                continue
            if candidate.is_file() and relative not in seen_paths:
                seen_paths.add(relative)
                if sha256_file(candidate) in official_template_hashes:
                    return
                asset_queue.append(candidate)
                return

    def enqueue_references(source: str, current: Path | None = None) -> None:
        for pattern, suffix in ((PACKAGE_RE, ".sty"), (DOCUMENT_CLASS_RE, ".cls")):
            for match in pattern.finditer(source):
                for target in match.group(1).split(","):
                    enqueue_local(target, suffix, current)

    for segment in sources:
        enqueue_references(str(segment["text"]))

    cursor = 0
    while cursor < len(asset_queue):
        path = asset_queue[cursor]
        cursor += 1
        source = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
        sources.append(
            {
                "path": path.relative_to(paper).as_posix(),
                "line": 1,
                "column": 1,
                "text": source,
            }
        )
        enqueue_references(source, path)
        for match in INPUT_RE.finditer(source):
            enqueue_local(match.group("braced") or match.group("bare") or "", ".tex", path)

    uses: list[dict[str, Any]] = []
    for source_record in sources:
        source = str(source_record["text"])
        for match in TEX_FUZZ_REGISTER_RE.finditer(source):
            uses.append(
                {
                    **_source_match_location(
                        str(source_record["path"]),
                        source,
                        int(source_record["line"]),
                        int(source_record.get("column", 1)),
                        match.start(),
                    ),
                    "command": f"\\{match.group('register').lower()}",
                }
            )
    return sorted(
        uses,
        key=lambda item: (
            str(item["path"]),
            int(item["line"]),
            int(item["column"]),
            str(item["command"]),
        ),
    )


def _official_template_asset_hashes(paper: Path) -> set[str]:
    """Return hashes of LaTeX assets contained in the recorded official author kit."""

    decision_path = paper.parent / "venue/decision.json"
    if not decision_path.is_file():
        return set()
    try:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        selected = decision.get("selected") if isinstance(decision, dict) else None
        template_value = selected.get("template_path") if isinstance(selected, dict) else None
        expected_hash = selected.get("template_sha256") if isinstance(selected, dict) else None
        if not template_value or not expected_hash:
            return set()
        template_path = (paper.parent / str(template_value)).resolve()
        template_path.relative_to((paper.parent / "venue/template").resolve())
        if not template_path.is_file() or sha256_file(template_path) != str(expected_hash).casefold():
            return set()
    except (OSError, ValueError, json.JSONDecodeError):
        return set()

    hashes: set[str] = set()

    def add_asset(name: str, payload: bytes) -> None:
        if Path(name).suffix.casefold() in {".sty", ".cls", ".bst"}:
            hashes.add(hashlib.sha256(payload).hexdigest())

    try:
        if zipfile.is_zipfile(template_path):
            with zipfile.ZipFile(template_path) as archive:
                for name in archive.namelist():
                    if not name.endswith("/"):
                        add_asset(name, archive.read(name))
        elif tarfile.is_tarfile(template_path):
            with tarfile.open(template_path) as archive:
                for member in archive.getmembers():
                    if member.isfile():
                        handle = archive.extractfile(member)
                        if handle is not None:
                            add_asset(member.name, handle.read())
        else:
            add_asset(template_path.name, template_path.read_bytes())
    except (OSError, tarfile.TarError, zipfile.BadZipFile, KeyError):
        return set()
    return hashes


def _resource_dependency_errors(paper: Path, segments: list[dict[str, Any]]) -> list[str]:
    """Reject dynamic or paper-external author resources that make freshness unverifiable."""

    errors: list[str] = []
    official_hashes = _official_template_asset_hashes(paper)
    queue = list(segments)
    audited_paths = {str(segment["path"]) for segment in queue}

    def require_local(target: str, kind: str, extensions: tuple[str, ...]) -> None:
        try:
            candidate = _resolve_under_paper(paper, target, kind)
        except ValueError as exc:
            errors.append(str(exc))
            return
        candidates = [candidate]
        if not candidate.suffix:
            candidates = [candidate.with_suffix(extension) for extension in extensions]
        if not any(path.is_file() for path in candidates):
            errors.append(f"{kind} does not resolve to a local paper resource: {target}")

    def audit_local_latex_asset(path: Path, kind: str) -> None:
        relative = path.relative_to(paper).as_posix()
        asset_hash = sha256_file(path)
        if asset_hash in official_hashes:
            return
        if path.name.casefold() not in INTERNAL_AUDITED_LATEX_ASSETS:
            errors.append(
                f"{kind} is a paper-local asset not present in the recorded official template: {relative}"
            )
            return
        if relative not in audited_paths:
            audited_paths.add(relative)
            queue.append(
                {
                    "path": relative,
                    "line": 1,
                    "text": strip_tex_comments(
                        path.read_text(encoding="utf-8", errors="replace")
                    ),
                }
            )

    cursor = 0
    while cursor < len(queue):
        segment = queue[cursor]
        cursor += 1
        source = str(segment["text"])
        origin = f"{segment['path']}:{segment['line']}"
        if GRAPHICSPATH_RE.search(source):
            errors.append(
                f"{origin}: \\graphicspath is not allowed; use explicit paper-root-relative figure paths"
            )
        if DYNAMIC_FILE_READ_RE.search(source):
            errors.append(
                f"{origin}: dynamic file-reading commands are not allowed in manuscript inputs"
            )
        if DYNAMIC_FILE_WRITE_RE.search(source):
            errors.append(
                f"{origin}: file-writing commands are not allowed in manuscript inputs"
            )
        if DYNAMIC_TEX_PRIMITIVE_RE.search(source):
            errors.append(
                f"{origin}: dynamic TeX control-sequence primitives are not allowed in manuscript inputs"
            )
        if GUARDED_REDEFINITION_RE.search(source):
            errors.append(
                f"{origin}: canonical structure commands may not be redefined in manuscript inputs"
            )
        if PAGE_MANIPULATION_RE.search(source):
            errors.append(f"{origin}: page-counter/output manipulation is not allowed")
        if MANUAL_PAGINATION_RE.search(source):
            errors.append(f"{origin}: manual pagination is not allowed in local LaTeX assets")
        for match in INPUT_RE.finditer(source):
            target = match.group("braced") or match.group("bare") or ""
            try:
                child = _resolve_input(paper / str(segment["path"]), target, paper)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            relative = child.relative_to(paper).as_posix()
            if relative not in audited_paths:
                audited_paths.add(relative)
                queue.append(
                    {
                        "path": relative,
                        "line": 1,
                        "text": strip_tex_comments(
                            child.read_text(encoding="utf-8", errors="replace")
                        ),
                    }
                )
        for match in BIBLIOGRAPHY_TARGET_RE.finditer(source):
            for target in match.group(1).split(","):
                require_local(target, "bibliography resource", (".bib",))
        for match in ADD_BIB_RESOURCE_RE.finditer(source):
            require_local(match.group(1), "bibliography resource", (".bib",))
        for match in INCLUDE_GRAPHICS_RE.finditer(source):
            require_local(match.group(1), "figure resource", GRAPHIC_EXTENSIONS)
        for match in INCLUDE_PDF_RE.finditer(source):
            require_local(match.group(1), "included PDF resource", (".pdf",))
        for match in BIBLIOGRAPHY_STYLE_RE.finditer(source):
            target = match.group(1).strip()
            if target.casefold() in BUILTIN_BIBLIOGRAPHY_STYLES:
                continue
            try:
                candidate = _resolve_under_paper(paper, target, "bibliography style")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if not candidate.suffix:
                candidate = candidate.with_suffix(".bst")
            if not candidate.is_file():
                errors.append(
                    f"bibliography style does not resolve to a local paper resource: {target}"
                )
            else:
                audit_local_latex_asset(candidate, "bibliography style")
        for pattern, kind, extension in (
            (PACKAGE_RE, "LaTeX package", ".sty"),
            (DOCUMENT_CLASS_RE, "document class", ".cls"),
        ):
            for match in pattern.finditer(source):
                for target in match.group(1).split(","):
                    stripped = target.strip()
                    if any(character in STATIC_PATH_FORBIDDEN for character in stripped):
                        errors.append(f"{kind} must use a static literal name: {target}")
                    else:
                        try:
                            candidate = _resolve_under_paper(paper, stripped, kind)
                        except ValueError as exc:
                            errors.append(str(exc))
                            continue
                        if not candidate.suffix:
                            candidate = candidate.with_suffix(extension)
                        if candidate.is_file():
                            audit_local_latex_asset(candidate, kind)
                        elif "/" in stripped or stripped.startswith("."):
                            errors.append(
                                f"{kind} does not resolve to a local paper asset: {target}"
                            )
    return errors


def _normalized_input_target(value: str) -> str:
    target = value.strip().replace("\\", "/")
    return target[:-4].casefold() if target.casefold().endswith(".tex") else target.casefold()


def _balanced_command_calls(
    source: str, command: str, argument_count: int
) -> list[dict[str, Any]]:
    """Extract fixed-arity TeX command calls without accepting unbalanced groups."""

    calls: list[dict[str, Any]] = []
    pattern = re.compile(re.escape(command) + r"(?![A-Za-z@])")
    for match in pattern.finditer(source):
        cursor = match.end()
        arguments: list[dict[str, Any]] = []
        valid = True
        for _ in range(argument_count):
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            if cursor >= len(source) or source[cursor] != "{":
                valid = False
                break
            end = _balanced_group_end(source, cursor)
            if end is None:
                valid = False
                break
            arguments.append(
                {
                    "start": cursor,
                    "end": end,
                    "body": source[cursor + 1 : end - 1],
                }
            )
            cursor = end
        calls.append(
            {
                "start": match.start(),
                "end": cursor,
                "arguments": arguments,
                "valid": valid,
            }
        )
    return calls


def teaser_placement_audit(paper: Path) -> list[str]:
    """Enforce the rendered Title -> Teaser -> Authors -> Abstract contract."""

    paper = paper.resolve()
    main_path = paper / "main.tex"
    teaser_path = paper / "sections/teaser.tex"
    if not main_path.is_file():
        return []

    main_source = strip_tex_comments(main_path.read_text(encoding="utf-8", errors="replace"))
    teaser_source = (
        strip_tex_comments(teaser_path.read_text(encoding="utf-8", errors="replace"))
        if teaser_path.is_file()
        else ""
    )
    teaser_inputs = []
    for match in INPUT_RE.finditer(main_source):
        target = (match.group("braced") or match.group("bare") or "").strip()
        if _normalized_input_target(target) == "sections/teaser":
            teaser_inputs.append(match)
    patch_calls = _balanced_command_calls(
        main_source, r"\IdeaTwoPaperPatchTitleTeaser", 2
    )
    active = bool(teaser_source.strip() or teaser_inputs or patch_calls)
    if not active:
        return []

    errors: list[str] = []
    if not teaser_path.is_file():
        errors.append("title-block teaser hook is active but sections/teaser.tex is missing")
        return errors
    if len(patch_calls) != 1 or not patch_calls[0]["valid"]:
        errors.append(
            "main.tex must contain exactly one balanced "
            r"\IdeaTwoPaperPatchTitleTeaser{<title-anchor>}{\input{sections/teaser}} call"
        )
        return errors

    call = patch_calls[0]
    title_anchor = str(call["arguments"][0]["body"])
    insertion = str(call["arguments"][1]["body"])
    if r"\@title" not in title_anchor:
        errors.append("title-teaser hook anchor must contain the active template's \\@title token")
    if re.sub(r"\s+", "", insertion) != r"\input{sections/teaser}":
        errors.append(
            "title-teaser hook second argument must be exactly "
            r"\input{sections/teaser}"
        )
    if len(teaser_inputs) != 1 or not (
        call["arguments"][1]["start"]
        < teaser_inputs[0].start()
        < call["arguments"][1]["end"]
    ):
        errors.append(
            "sections/teaser must be input exactly once, inside the title-teaser hook only"
        )

    begin_document = re.search(r"\\begin\{document\}", main_source)
    make_titles = list(re.finditer(r"\\maketitle\b", main_source))
    abstracts = list(re.finditer(r"\\begin\{abstract\}", main_source))
    if begin_document is None or len(make_titles) != 1 or len(abstracts) != 1:
        errors.append(
            "title-teaser placement requires one begin{document}, one maketitle, and one abstract"
        )
    elif not (
        call["end"]
        < begin_document.start()
        < make_titles[0].start()
        < abstracts[0].start()
    ):
        errors.append(
            "source order must be title-teaser hook < begin{document} < maketitle < Abstract"
        )

    if teaser_source.strip():
        begins = list(
            re.finditer(r"\\begin\{IdeaTwoPaperTitleTeaser\}", teaser_source)
        )
        ends = list(re.finditer(r"\\end\{IdeaTwoPaperTitleTeaser\}", teaser_source))
        if len(begins) != 1 or len(ends) != 1 or begins[0].start() >= ends[0].start():
            errors.append(
                "sections/teaser.tex must contain exactly one "
                "IdeaTwoPaperTitleTeaser environment"
            )
        if re.search(r"\\begin\{figure\*?\}", teaser_source):
            errors.append(
                "title-block teaser must be non-floating; figure/figure* is forbidden"
            )
        if not INCLUDE_GRAPHICS_RE.search(teaser_source):
            errors.append("title-block teaser must contain a literal \\includegraphics raster")
    return errors


def manuscript_structure_audit(paper: Path) -> dict[str, Any]:
    """Bind canonical boundary labels to the actual Conclusion, bibliography, and appendix."""

    paper = paper.resolve()
    main_tex = paper / "main.tex"
    if not main_tex.is_file():
        return {
            "errors": ["active manuscript is missing main.tex"],
            "segments": [],
            "source": "",
            "conclusion_position": None,
            "end_body_position": None,
            "end_exempt_position": None,
            "bibliography_position": None,
            "end_references_position": None,
            "appendix_position": None,
            "appendix_label_position": None,
        }
    segments = active_tex_segments(paper)
    source = _combined_source(segments)
    errors: list[str] = []
    errors.extend(teaser_placement_audit(paper))
    conditional_commands = list(TEX_CONDITIONAL_RE.finditer(source))
    if conditional_commands:
        path, line = _segment_origin(segments, conditional_commands[0].start())
        errors.append(
            f"{path}:{line}: TeX conditionals are not allowed in the statically audited manuscript graph"
        )
    errors.extend(_resource_dependency_errors(paper, segments))
    conclusion_headings = list(CONCLUSION_HEADING_RE.finditer(source))
    conclusion_blocks = list(CONCLUSION_BLOCK_RE.finditer(source))
    conclusion_labels = list(re.finditer(r"\\label\{idea2paper:start-conclusion\}", source))
    end_body_markers = list(re.finditer(re.escape(BODY_END_MARKER), source))
    end_exempt_markers = list(re.finditer(re.escape(BODY_EXEMPT_END_MARKER), source))
    end_reference_markers = list(re.finditer(re.escape(BODY_REFERENCES_END_MARKER), source))
    bibliographies = list(BIBLIOGRAPHY_RE.finditer(source))
    appendices = list(APPENDIX_RE.finditer(source))
    appendix_blocks = list(APPENDIX_BLOCK_RE.finditer(source))
    appendix_labels = list(
        re.finditer(r"\\label\{idea2paper:start-appendix\}", source)
    )

    if (
        len(conclusion_headings) != 1
        or len(conclusion_blocks) != 1
        or len(conclusion_labels) != 1
    ):
        errors.append(
            "manuscript must contain exactly one Conclusion whose start-conclusion label "
            "immediately follows its heading"
        )
    if len(end_body_markers) != 1:
        errors.append("active manuscript must contain exactly one end-body label")
    if len(end_exempt_markers) != 1:
        errors.append("active manuscript must contain exactly one end-exempt label")
    if len(end_reference_markers) != 1:
        errors.append("active manuscript must contain exactly one end-references label")
    if len(bibliographies) != 1:
        errors.append("active manuscript must contain exactly one bibliography boundary")
    if len(appendices) != 1:
        errors.append("active manuscript must contain exactly one appendix boundary")
    if len(appendix_blocks) != 1 or len(appendix_labels) != 1:
        errors.append(
            "the sole start-appendix label must immediately follow the literal \\appendix command"
        )

    conclusion_position = conclusion_blocks[0].start() if len(conclusion_blocks) == 1 else None
    end_body_position = end_body_markers[0].start() if len(end_body_markers) == 1 else None
    end_exempt_position = (
        end_exempt_markers[0].start() if len(end_exempt_markers) == 1 else None
    )
    bibliography_position = bibliographies[0].start() if len(bibliographies) == 1 else None
    end_references_position = (
        end_reference_markers[0].start() if len(end_reference_markers) == 1 else None
    )
    appendix_position = appendices[0].start() if len(appendices) == 1 else None
    appendix_label_position = (
        appendix_labels[0].start() if len(appendix_labels) == 1 else None
    )
    positions = (
        conclusion_position,
        end_body_position,
        end_exempt_position,
        bibliography_position,
        end_references_position,
        appendix_position,
    )
    if all(position is not None for position in positions) and not (
        conclusion_position
        < end_body_position
        < end_exempt_position
        < bibliography_position
        < end_references_position
        < appendix_position
    ):
        errors.append(
            "manuscript boundaries must be ordered Conclusion < end-body < end-exempt "
            "< bibliography < end-references < appendix"
        )

    if appendix_position is not None:
        appendix_path, _ = _segment_origin(segments, appendix_position)
        if appendix_path != "appendix/appendix.tex":
            errors.append("the sole appendix boundary must originate in appendix/appendix.tex")
    canonical_appendix = paper / "appendix/appendix.tex"
    if canonical_appendix.is_file():
        appendix_source = strip_tex_comments(
            canonical_appendix.read_text(encoding="utf-8", errors="replace")
        )
        if re.match(r"^\s*\\appendix\b", appendix_source) is None:
            errors.append("appendix/appendix.tex must begin with the literal \\appendix command")

    main_source = strip_tex_comments(main_tex.read_text(encoding="utf-8", errors="replace"))
    main_end_body = list(re.finditer(re.escape(BODY_END_MARKER), main_source))
    main_end_exempt = list(re.finditer(re.escape(BODY_EXEMPT_END_MARKER), main_source))
    main_end_references = list(re.finditer(re.escape(BODY_REFERENCES_END_MARKER), main_source))
    main_bibliographies = list(BIBLIOGRAPHY_RE.finditer(main_source))
    main_inputs: list[dict[str, Any]] = []
    for match in INPUT_RE.finditer(main_source):
        target = (match.group("braced") or match.group("bare") or "").strip()
        main_inputs.append(
            {
                "start": match.start(),
                "end": match.end(),
                "target": _normalized_input_target(target),
            }
        )
    conclusion_inputs = [
        item for item in main_inputs if item["target"] == "sections/conclusion"
    ]
    limitation_inputs = [
        item for item in main_inputs if item["target"] == "sections/limitations"
    ]
    appendix_inputs = [
        item for item in main_inputs if item["target"] == "appendix/appendix"
    ]
    if len(main_end_body) != 1 or len(conclusion_inputs) != 1:
        errors.append(
            "main.tex must input sections/conclusion exactly once before its sole end-body label"
        )
    else:
        main_end_position = main_end_body[0].start()
        if conclusion_inputs[0]["start"] >= main_end_position:
            errors.append("main.tex places end-body before the Conclusion input")
        if len(limitation_inputs) > 1:
            errors.append("main.tex may input sections/limitations at most once")
        elif limitation_inputs and limitation_inputs[0]["start"] <= conclusion_inputs[0]["start"]:
            errors.append("main.tex must place Limitations after Conclusion")
        final_body_input = limitation_inputs[0] if limitation_inputs else conclusion_inputs[0]
        if final_body_input["end"] >= main_end_position:
            errors.append("main.tex places end-body before the final body-section input")
        elif main_source[final_body_input["end"] : main_end_position].strip():
            errors.append(
                "main.tex must place end-body immediately after Conclusion/Limitations; "
                "additional body prose or inputs are not allowed in between"
            )

    if (
        len(main_bibliographies) != 1
        or len(main_end_references) != 1
        or len(main_end_exempt) != 1
    ):
        errors.append(
            "main.tex must contain one end-exempt label, bibliography, and end-references label"
        )
    elif len(main_end_body) == 1:
        body_end = main_end_body[0].end()
        exempt_start = main_end_exempt[0].start()
        exempt_end = main_end_exempt[0].end()
        bibliography_start = main_bibliographies[0].start()
        if exempt_start <= body_end or bibliography_start <= exempt_end:
            errors.append("main.tex must place end-exempt between end-body and the bibliography")
        else:
            exempt_region = main_source[body_end:exempt_start]
            exempt_inputs = [
                item
                for item in main_inputs
                if body_end <= item["start"] < exempt_start
            ]
            invalid_exempt_inputs = [
                item for item in exempt_inputs if item["target"] != "sections/ai_use_statement"
            ]
            if invalid_exempt_inputs or len(exempt_inputs) > 1:
                errors.append(
                    "only one sections/ai_use_statement input may appear between end-body "
                    "and the bibliography"
                )
            if exempt_inputs:
                only_input = exempt_inputs[0]
                if (
                    main_source[body_end : only_input["start"]].strip()
                    or main_source[only_input["end"] : exempt_start].strip()
                ):
                    errors.append(
                        "end-exempt must immediately follow the optional AI-use statement input"
                    )
            elif exempt_region.strip():
                errors.append("end-exempt must immediately follow end-body when no disclosure is used")

            formatting_region = main_source[exempt_end:bibliography_start]
            formatting_region = BIBLIOGRAPHY_STYLE_RE.sub("", formatting_region)
            formatting_region = re.sub(
                r"\\(?:small|footnotesize|scriptsize|begingroup|endgroup)\b",
                "",
                formatting_region,
            )
            if re.sub(r"[\s{}]+", "", formatting_region):
                errors.append(
                    "main.tex contains non-formatting content between end-exempt and the bibliography"
                )

    ai_statement = paper / "sections/ai_use_statement.tex"
    if ai_statement.is_file():
        ai_source = strip_tex_comments(ai_statement.read_text(encoding="utf-8", errors="replace"))
        ai_words = re.findall(r"\b[\w'-]+\b", re.sub(r"\\[A-Za-z@]+", " ", ai_source))
        if (
            len(ai_words) > 400
            or len(ai_source) > 5000
            or FLOAT_RE.search(ai_source)
            or INPUT_RE.search(ai_source)
            or AI_LAYOUT_RE.search(ai_source)
        ):
            errors.append(
                "sections/ai_use_statement.tex must be a concise standalone disclosure "
                "without floats or nested inputs"
            )

    if len(main_end_references) == 1 and len(appendix_inputs) == 1:
        end_references_end = main_end_references[0].end()
        appendix_input = appendix_inputs[0]
        if appendix_input["start"] <= end_references_end:
            errors.append("main.tex must input appendix/appendix after end-references")
        elif main_source[end_references_end : appendix_input["start"]].strip():
            errors.append("main.tex must place the appendix input immediately after end-references")
        tail = main_source[appendix_input["end"] :]
        tail = re.sub(r"\\end\s*\{document\}", "", tail)
        if tail.strip():
            errors.append("main.tex may contain only \\end{document} after the appendix input")
    else:
        errors.append("main.tex must input appendix/appendix exactly once after end-references")

    return {
        "errors": errors,
        "segments": segments,
        "source": source,
        "conclusion_position": conclusion_position,
        "end_body_position": end_body_position,
        "end_exempt_position": end_exempt_position,
        "bibliography_position": bibliography_position,
        "end_references_position": end_references_position,
        "appendix_position": appendix_position,
        "appendix_label_position": appendix_label_position,
    }


def _segment_origin(segments: list[dict[str, Any]], offset: int) -> tuple[str, int]:
    consumed = 0
    for segment in segments:
        text = str(segment["text"])
        if offset < consumed + len(text):
            local_offset = offset - consumed
            return str(segment["path"]), int(segment["line"]) + text.count("\n", 0, local_offset)
        consumed += len(text)
    return "main.tex", 1


def manual_pagination_commands(paper: Path) -> list[dict[str, Any]]:
    """Find author-inserted page breaks, float flushes, and forced-here floats."""

    violations: list[dict[str, Any]] = []
    for segment in active_tex_segments(paper):
        source = str(segment["text"])
        for match in MANUAL_PAGINATION_RE.finditer(source):
            violations.append(
                {
                    "path": segment["path"],
                    "line": int(segment["line"]) + source.count("\n", 0, match.start()),
                    "command": f"\\{match.group(1)}",
                }
            )
        for match in FORCED_H_FLOAT_RE.finditer(source):
            environment = match.group("environment")
            violations.append(
                {
                    "path": segment["path"],
                    "line": int(segment["line"]) + source.count("\n", 0, match.start()),
                    "command": f"\\begin{{{environment}}}[H]",
                }
            )
    return violations


def manuscript_float_inventory(paper: Path) -> dict[str, Any]:
    """Inventory floating and source-anchored figure/table artifacts in source order."""

    structure = manuscript_structure_audit(paper)
    segments = list(structure["segments"])
    source = str(structure["source"])
    appendix_position = structure["appendix_position"]
    cutoff = appendix_position if isinstance(appendix_position, int) else len(source)
    conclusion_position = structure["conclusion_position"]
    all_records: list[dict[str, Any]] = []
    all_labels: list[str] = []
    floating_matches = list(FLOAT_RE.finditer(source))
    candidates: list[dict[str, Any]] = [
        {
            "start": match.start(),
            "environment": match.group(1),
            "content": match.group(2),
            "placement": "floating",
        }
        for match in floating_matches
    ]
    for match in CAPTIONOF_RE.finditer(source):
        if any(item.start() <= match.start() < item.end() for item in floating_matches):
            continue
        block_end = source.find(r"\end{minipage}", match.end())
        if block_end < 0:
            block_end = min(len(source), match.end() + 5000)
        candidates.append(
            {
                "start": match.start(),
                "environment": f"captionof_{match.group('kind')}",
                "content": source[match.end() : block_end],
                "placement": "source-anchored",
            }
        )
    for match in TITLE_TEASER_RE.finditer(source):
        label_match = re.search(r"\{(?P<label>[^{}]+)\}\s*$", match.group("header"))
        if label_match is None:
            candidates.append(
                {
                    "start": match.start(),
                    "environment": "title_teaser",
                    "content": "",
                    "placement": "source-anchored",
                }
            )
            continue
        candidates.append(
            {
                "start": match.start(),
                "environment": "title_teaser",
                "content": rf"\label{{{label_match.group('label')}}}",
                "placement": "source-anchored",
            }
        )
    candidates.sort(key=lambda item: int(item["start"]))
    for index, item in enumerate(candidates, start=1):
        offset = int(item["start"])
        path, line = _segment_origin(segments, offset)
        float_labels = LABEL_RE.findall(str(item["content"]))
        region = "body" if offset < cutoff else "appendix"
        record = {
            "float_index": index,
            "environment": item["environment"],
            "placement": item["placement"],
            "path": path,
            "line": line,
            "labels": float_labels,
            "source_offset": offset,
            "region": region,
            "after_conclusion_source": (
                region == "body"
                and isinstance(conclusion_position, int)
                and offset > conclusion_position
            ),
        }
        all_records.append(record)
        all_labels.extend(float_labels)

    body_records = [record for record in all_records if record["region"] == "body"]
    appendix_records = [record for record in all_records if record["region"] == "appendix"]
    body_labels = [label for record in body_records for label in record["labels"]]
    appendix_labels = [label for record in appendix_records for label in record["labels"]]
    active_body_files: set[str] = set()
    consumed = 0
    for segment in segments:
        text = str(segment["text"])
        if consumed < cutoff and text:
            active_body_files.add(str(segment["path"]))
        consumed += len(text)
    return {
        "active_body_files": sorted(active_body_files),
        "active_appendix_files": sorted({record["path"] for record in appendix_records}),
        "records": body_records,
        "labels": sorted(set(body_labels)),
        "unlabeled": [record for record in body_records if not record["labels"]],
        "duplicate_labels": sorted(
            {label for label in body_labels if body_labels.count(label) > 1}
        ),
        "after_conclusion_source": [
            record for record in body_records if record["after_conclusion_source"]
        ],
        "appendix_records": appendix_records,
        "appendix_labels": sorted(set(appendix_labels)),
        "unlabeled_appendix_floats": [
            record for record in appendix_records if not record["labels"]
        ],
        "all_records": all_records,
        "all_labels": sorted(set(all_labels)),
        "duplicate_all_float_labels": sorted(
            {label for label in all_labels if all_labels.count(label) > 1}
        ),
        "structure_errors": list(structure["errors"]),
    }


def body_float_inventory(paper: Path) -> dict[str, Any]:
    """Backward-compatible body view of the whole-manuscript float inventory."""

    return manuscript_float_inventory(paper)


def body_float_labels(paper: Path) -> list[str]:
    return list(body_float_inventory(paper)["labels"])


def aux_label_record(path: Path, label: str) -> tuple[int | None, int | None]:
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        rf"\\newlabel\{{{re.escape(label)}\}}\{{\{{[^}}]*\}}\{{(\d+)\}}", text
    )
    return (int(match.group(1)), match.start()) if match else (None, None)


def body_float_tail_report(
    aux_path: Path, labels: list[str], conclusion_page: int | None
) -> tuple[dict[str, int | None], list[dict[str, Any]]]:
    records = {label: aux_label_record(aux_path, label) for label in labels}
    pages = {label: record[0] for label, record in records.items()}
    violations: list[dict[str, Any]] = []
    if conclusion_page is None:
        return pages, violations
    _, conclusion_index = aux_label_record(aux_path, "idea2paper:start-conclusion")
    for label, (page, aux_index) in records.items():
        later_page = page is not None and page > conclusion_page
        later_on_same_page = (
            page == conclusion_page
            and aux_index is not None
            and conclusion_index is not None
            and aux_index > conclusion_index
        )
        if later_page or later_on_same_page:
            violations.append(
                {
                    "label": label,
                    "page": page,
                    "conclusion_page": conclusion_page,
                    "reason": "later_page" if later_page else "same_page_after_conclusion",
                }
            )
    return pages, violations


def _balanced_group_end(source: str, opening: int) -> int | None:
    """Return the index after a balanced TeX group beginning at ``opening``."""

    if opening >= len(source) or source[opening] != "{":
        return None
    depth = 0
    index = opening
    while index < len(source):
        character = source[index]
        if character == "\\":
            index += 2
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _column_macro_definitions(source: str) -> tuple[dict[str, str], list[tuple[int, int]]]:
    """Extract ordinary command definitions so dormant bodies are not treated as invocations."""

    definitions: dict[str, str] = {}
    spans: list[tuple[int, int]] = []
    command_pattern = re.compile(
        r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*"
        r"(?:\{\s*(\\[A-Za-z@]+)\s*\}|(\\[A-Za-z@]+))"
        r"(?:\s*\[\s*\d+\s*\])?(?:\s*\[[^]]*\])?\s*\{"
    )
    primitive_pattern = re.compile(r"\\(?:long\s*)?(?:gdef|xdef|edef|def)\s*(\\[A-Za-z@]+)[^{]*\{")
    for pattern in (command_pattern, primitive_pattern):
        for match in pattern.finditer(source):
            opening = match.end() - 1
            end = _balanced_group_end(source, opening)
            if end is None:
                continue
            macro = next(
                (value for value in match.groups() if isinstance(value, str) and value.startswith("\\")),
                None,
            )
            if macro:
                definitions[macro] = source[opening + 1 : end - 1]
                spans.append((match.start(), end))
    return definitions, spans


def _mask_spans(source: str, spans: list[tuple[int, int]]) -> str:
    masked = list(source)
    for start, end in spans:
        for index in range(max(0, start), min(len(masked), end)):
            if masked[index] != "\n":
                masked[index] = " "
    return "".join(masked)


def _mask_conditional_regions(source: str) -> str:
    """Mask branches whose runtime truth cannot be established statically."""

    tokens = list(re.finditer(r"\\(?P<name>if[A-Za-z@]*|else|fi)\b", source))
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for token in tokens:
        name = token.group("name")
        if name.startswith("if"):
            stack.append(token.start())
        elif name == "fi" and stack:
            start = stack.pop()
            if not stack:
                spans.append((start, token.end()))
    return _mask_spans(source, spans)


def _active_template_column_evidence(
    template_source: str, active_author_source: str
) -> list[dict[str, Any]]:
    """Find unconditional or author-invoked template column switches."""

    definitions, definition_spans = _column_macro_definitions(template_source)
    top_level = _mask_conditional_regions(_mask_spans(template_source, definition_spans))
    evidence: list[dict[str, Any]] = []
    if re.search(r"\\twocolumn\b", top_level):
        evidence.append({"kind": "template-top-level-command", "command": r"\twocolumn"})

    author_definitions, author_spans = _column_macro_definitions(active_author_source)
    del author_definitions
    reachable_text = _mask_conditional_regions(_mask_spans(active_author_source, author_spans))
    reachable = {
        macro
        for macro in definitions
        if re.search(rf"{re.escape(macro)}(?![A-Za-z@])", reachable_text)
    }
    visited: set[str] = set()
    while reachable:
        macro = reachable.pop()
        if macro in visited:
            continue
        visited.add(macro)
        body = _mask_conditional_regions(definitions[macro])
        if re.search(r"\\twocolumn\b", body):
            evidence.append(
                {
                    "kind": "author-invoked-template-command",
                    "macro": macro,
                    "command": r"\twocolumn",
                }
            )
        for child in definitions:
            if child not in visited and re.search(rf"{re.escape(child)}(?![A-Za-z@])", body):
                reachable.add(child)
    return evidence


def document_column_mode_audit(paper: Path, requested: str = "auto") -> dict[str, Any]:
    """Resolve column mode from active author sources and referenced local templates."""

    # Inspect only active author-level TeX.  Style/class files often contain dormant
    # \twocolumn branches, which made single-column review templates look two-column.
    try:
        source = _combined_source(active_tex_segments(paper))
    except (OSError, ValueError):
        source = strip_tex_comments(
            (paper / "main.tex").read_text(encoding="utf-8", errors="replace")
        )
    evidence: list[dict[str, Any]] = []
    inspected_templates: list[str] = []
    author_definitions, author_definition_spans = _column_macro_definitions(source)
    del author_definitions
    active_author_source = _mask_conditional_regions(
        _mask_spans(source, author_definition_spans)
    )
    if re.search(r"\\twocolumn\b", active_author_source):
        evidence.append({"kind": "active-author-command", "command": r"\twocolumn"})
    class_matches = list(
        re.finditer(r"\\documentclass\s*(?:\[([^]]*)\])?\s*\{([^}]+)\}", source)
    )
    for match in class_matches:
        options = {item.strip().lower() for item in (match.group(1) or "").split(",")}
        if "twocolumn" in options:
            evidence.append(
                {"kind": "documentclass-option", "template": match.group(2), "option": "twocolumn"}
            )
    package_names: set[tuple[str, str]] = set()
    for match in class_matches:
        package_names.add((match.group(2).strip(), ".cls"))
    for match in re.finditer(r"\\usepackage\s*(?:\[[^]]*\])?\s*\{([^}]+)\}", source):
        for name in match.group(1).split(","):
            package_names.add((name.strip(), ".sty"))
    for name, suffix in sorted(package_names):
        if not name or "/" in name or "\\" in name:
            continue
        candidates = sorted(paper.rglob(name + suffix))
        for candidate in candidates:
            relative = candidate.relative_to(paper).as_posix()
            inspected_templates.append(relative)
            template_source = strip_tex_comments(
                candidate.read_text(encoding="utf-8", errors="replace")
            )
            for item in _active_template_column_evidence(template_source, active_author_source):
                evidence.append({**item, "template": relative})
    detected = 2 if evidence else 1
    requested_mode = int(requested) if requested in {"1", "2"} else None
    override_verified = requested_mode is None or requested_mode == detected
    return {
        "mode": detected,
        "requested": requested,
        "source": "explicit-two-column-evidence" if evidence else "audited-single-column-default",
        "evidence": evidence,
        "inspected_template_files": sorted(set(inspected_templates)),
        "override_verified": override_verified,
    }


def document_column_mode(paper: Path, requested: str = "auto") -> int:
    """Backward-compatible integer view of :func:`document_column_mode_audit`."""

    return int(document_column_mode_audit(paper, requested)["mode"])


def float_distribution_audit(
    records: list[dict[str, Any]],
    label_pages: dict[str, int | None],
    appendix_start_page: int | None,
    total_pages: int | None,
    column_mode: int,
) -> dict[str, Any]:
    """Detect page overload, dense runs, and appendix-end float dumping."""

    page_counts: dict[int, int] = {}
    regional_counts: dict[str, dict[int, int]] = {"body": {}, "appendix": {}}
    resolved_records: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for record in records:
        pages = sorted(
            {
                int(label_pages[label])
                for label in record.get("labels", [])
                if label_pages.get(label) is not None
            }
        )
        if not pages:
            continue
        if len(pages) > 1:
            violations.append(
                {
                    "code": "float_label_page_disagreement",
                    "path": record.get("path"),
                    "line": record.get("line"),
                    "pages": pages,
                }
            )
        page = pages[0]
        region = str(record.get("region", "body"))
        if region not in regional_counts:
            region = "body"
        page_counts[page] = page_counts.get(page, 0) + 1
        regional_counts[region][page] = regional_counts[region].get(page, 0) + 1
        resolved_records.append(
            {
                "float_index": record.get("float_index"),
                "region": region,
                "path": record.get("path"),
                "line": record.get("line"),
                "labels": record.get("labels", []),
                "page": page,
            }
        )

    max_per_page = 2 if column_mode == 1 else 4
    dense_threshold = 2 if column_mode == 1 else 3
    overloaded = [
        {"page": page, "float_count": count, "maximum": max_per_page}
        for page, count in sorted(page_counts.items())
        if count > max_per_page
    ]
    violations.extend({"code": "overloaded_float_page", **item} for item in overloaded)

    dense_runs: list[dict[str, Any]] = []
    for region, counts in regional_counts.items():
        dense_pages = sorted(page for page, count in counts.items() if count >= dense_threshold)
        run: list[int] = []
        for page in dense_pages:
            if run and page != run[-1] + 1:
                if len(run) >= 3:
                    dense_runs.append(
                        {
                            "region": region,
                            "start_page": run[0],
                            "end_page": run[-1],
                            "pages": run,
                            "counts": [counts[item] for item in run],
                        }
                    )
                run = []
            run.append(page)
        if len(run) >= 3:
            dense_runs.append(
                {
                    "region": region,
                    "start_page": run[0],
                    "end_page": run[-1],
                    "pages": run,
                    "counts": [counts[item] for item in run],
                }
            )
    violations.extend({"code": "consecutive_dense_float_pages", **item} for item in dense_runs)

    adjacent_appendix_dense_pairs: list[dict[str, Any]] = []
    if column_mode == 1:
        appendix_dense_pages = sorted(
            page
            for page, count in regional_counts["appendix"].items()
            if count >= 2
        )
        for left, right in zip(appendix_dense_pages, appendix_dense_pages[1:]):
            if right == left + 1:
                adjacent_appendix_dense_pairs.append(
                    {
                        "region": "appendix",
                        "pages": [left, right],
                        "counts": [
                            regional_counts["appendix"][left],
                            regional_counts["appendix"][right],
                        ],
                    }
                )
    violations.extend(
        {"code": "adjacent_dense_appendix_float_pages", **item}
        for item in adjacent_appendix_dense_pairs
    )

    terminal_cluster: dict[str, Any] | None = None
    appendix_counts = regional_counts["appendix"]
    appendix_float_total = sum(appendix_counts.values())
    if (
        appendix_start_page is not None
        and total_pages is not None
        and total_pages - appendix_start_page + 1 >= 4
        and appendix_float_total >= 4
    ):
        terminal_pages = list(range(max(appendix_start_page, total_pages - 2), total_pages + 1))
        terminal_float_count = sum(appendix_counts.get(page, 0) for page in terminal_pages)
        terminal_share = terminal_float_count / appendix_float_total
        terminal_cluster = {
            "appendix_start_page": appendix_start_page,
            "appendix_end_page": total_pages,
            "terminal_pages": terminal_pages,
            "terminal_float_count": terminal_float_count,
            "appendix_float_count": appendix_float_total,
            "terminal_share": round(terminal_share, 4),
            "maximum_terminal_share": 0.7,
        }
        if terminal_share > 0.7:
            violations.append({"code": "appendix_terminal_float_cluster", **terminal_cluster})

        terminal_two_pages = list(
            range(max(appendix_start_page, total_pages - 1), total_pages + 1)
        )
        terminal_two_count = sum(appendix_counts.get(page, 0) for page in terminal_two_pages)
        terminal_two_share = terminal_two_count / appendix_float_total
        if terminal_two_count >= 4 and terminal_two_share >= 0.75:
            violations.append(
                {
                    "code": "appendix_terminal_two_page_cluster",
                    "appendix_start_page": appendix_start_page,
                    "appendix_end_page": total_pages,
                    "terminal_pages": terminal_two_pages,
                    "terminal_float_count": terminal_two_count,
                    "appendix_float_count": appendix_float_total,
                    "terminal_share": round(terminal_two_share, 4),
                    "maximum_terminal_share": 0.75,
                }
            )

    return {
        "column_mode": column_mode,
        "maximum_floats_per_page": max_per_page,
        "dense_page_threshold": dense_threshold,
        "page_float_counts": {str(page): count for page, count in sorted(page_counts.items())},
        "body_page_float_counts": {
            str(page): count for page, count in sorted(regional_counts["body"].items())
        },
        "appendix_page_float_counts": {
            str(page): count for page, count in sorted(appendix_counts.items())
        },
        "resolved_float_records": resolved_records,
        "overloaded_float_pages": overloaded,
        "dense_float_page_runs": dense_runs,
        "adjacent_dense_appendix_float_pairs": adjacent_appendix_dense_pairs,
        "appendix_terminal_cluster": terminal_cluster,
        "float_distribution_violations": violations,
    }


def _merge_intervals(
    intervals: list[tuple[float, float]], tolerance: float = 2.0
) -> list[list[float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + tolerance:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def infer_column_mode_from_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Infer a confident two-column signature from repeated mid-page gutter gaps."""

    eligible_rows = 0
    split_rows = 0
    inspected_pages = 0
    for page in pages:
        width = float(page.get("width", 0) or 0)
        height = float(page.get("height", 0) or 0)
        words = page.get("words", [])
        if width <= 0 or height <= 0 or not isinstance(words, list) or len(words) < 60:
            continue
        inspected_pages += 1
        rows: dict[int, list[tuple[float, float]]] = {}
        for word in words:
            try:
                x0 = float(word["x0"])
                x1 = float(word["x1"])
                top = float(word["top"])
            except (KeyError, TypeError, ValueError):
                continue
            if top < 0.08 * height or top > 0.90 * height:
                continue
            rows.setdefault(int(round(top / 2.5)), []).append((x0, x1))
        for row in rows.values():
            if len(row) < 6:
                continue
            eligible_rows += 1
            left_end = max((x1 for x0, x1 in row if x1 < 0.49 * width), default=None)
            right_start = min((x0 for x0, x1 in row if x0 > 0.51 * width), default=None)
            crosses_gutter = any(
                x0 < 0.52 * width and x1 > 0.48 * width for x0, x1 in row
            )
            if (
                not crosses_gutter
                and left_end is not None
                and right_start is not None
                and right_start - left_end > 0.055 * width
            ):
                split_rows += 1
    ratio = split_rows / eligible_rows if eligible_rows else 0.0
    if inspected_pages == 0 or eligible_rows < 20:
        mode: int | None = None
        confidence = 0.0
    elif split_rows >= 10 and ratio >= 0.12:
        mode = 2
        confidence = min(1.0, 0.55 + ratio)
    elif ratio <= 0.04:
        mode = 1
        confidence = min(1.0, 0.75 + (0.04 - ratio) * 4.0)
    else:
        mode = None
        confidence = 0.5
    return {
        "mode": mode,
        "confidence": round(confidence, 4),
        "inspected_pages": inspected_pages,
        "eligible_text_rows": eligible_rows,
        "split_gutter_rows": split_rows,
        "split_gutter_ratio": round(ratio, 4),
    }


def media_box_overflows_from_boxes(
    width: float,
    height: float,
    boxes: list[dict[str, Any]],
    *,
    page_number: int,
) -> list[dict[str, Any]]:
    """Return content coordinates that exceed the PDF media box by more than 2pt."""

    overflows: list[dict[str, Any]] = []
    for box_index, box in enumerate(boxes):
        try:
            x0 = float(box["x0"])
            x1 = float(box["x1"])
            top = float(box["top"])
            bottom = float(box["bottom"])
        except (KeyError, TypeError, ValueError):
            continue
        excesses = {
            "left": max(0.0, -x0),
            "right": max(0.0, x1 - width),
            "top": max(0.0, -top),
            "bottom": max(0.0, bottom - height),
        }
        for edge, excess in excesses.items():
            if excess > MEDIA_BOX_OVERFLOW_PT:
                overflows.append(
                    {
                        "page": page_number,
                        "box_index": box_index,
                        "kind": str(box.get("kind", "content")),
                        "edge": edge,
                        "excess_pt": round(excess, 6),
                        "text": str(box.get("text", ""))[:160],
                    }
                )
    return overflows


def page_geometry_from_boxes(
    width: float,
    height: float,
    boxes: list[dict[str, Any]],
    *,
    page_number: int,
    float_count: int,
    column_mode: int,
    is_last_page: bool = False,
) -> dict[str, Any]:
    """Measure avoidable blank bands and one-sided occupancy on one rendered page."""

    body_top = 0.07 * height
    body_bottom = 0.92 * height
    body_height = max(body_bottom - body_top, 1.0)
    media_box_overflows = media_box_overflows_from_boxes(
        width, height, boxes, page_number=page_number
    )
    filtered: list[tuple[float, float, float, float]] = []
    for box in boxes:
        try:
            x0 = float(box["x0"])
            x1 = float(box["x1"])
            top = float(box["top"])
            bottom = float(box["bottom"])
        except (KeyError, TypeError, ValueError):
            continue
        if bottom <= body_top or top >= body_bottom or x1 <= x0:
            continue
        text = str(box.get("text", "")).strip()
        if text.isdigit() and (x1 < 0.18 * width or x0 > 0.82 * width):
            continue
        clipped = (
            max(0.0, x0),
            min(width, x1),
            max(body_top, top),
            min(body_bottom, bottom),
        )
        if clipped[1] > clipped[0] and clipped[3] > clipped[2]:
            filtered.append(clipped)

    vertical = _merge_intervals([(top, bottom) for _, _, top, bottom in filtered])
    if vertical:
        internal_gaps = [
            vertical[index + 1][0] - vertical[index][1]
            for index in range(len(vertical) - 1)
        ]
        largest_internal = max(internal_gaps, default=0.0) / body_height
        leading_blank = max(0.0, vertical[0][0] - body_top) / body_height
        trailing_blank = max(0.0, body_bottom - vertical[-1][1]) / body_height
        occupied_height = sum(end - start for start, end in vertical) / body_height
    else:
        largest_internal = 1.0
        leading_blank = 1.0
        trailing_blank = 1.0
        occupied_height = 0.0

    if filtered:
        content_width = (max(item[1] for item in filtered) - min(item[0] for item in filtered)) / width
    else:
        content_width = 0.0
    left_area = 0.0
    right_area = 0.0
    midpoint = width / 2.0
    for x0, x1, top, bottom in filtered:
        box_height = max(0.0, bottom - top)
        left_area += max(0.0, min(x1, midpoint) - x0) * box_height
        right_area += max(0.0, x1 - max(x0, midpoint)) * box_height
    total_area = left_area + right_area
    side_imbalance = abs(left_area - right_area) / total_area if total_area else 1.0

    sparse_regions: list[dict[str, Any]] = []
    if column_mode == 1 and float_count > 0 and filtered:
        blocks = _merge_intervals(
            [(top, bottom) for _, _, top, bottom in filtered],
            tolerance=0.018 * body_height,
        )
        for block_top, block_bottom in blocks:
            block_boxes = [
                item
                for item in filtered
                if item[3] >= block_top and item[2] <= block_bottom
            ]
            block_height_fraction = (block_bottom - block_top) / body_height
            if len(block_boxes) < 8 or block_height_fraction < 0.16:
                continue
            block_width_fraction = (
                max(item[1] for item in block_boxes) - min(item[0] for item in block_boxes)
            ) / width
            if block_width_fraction < 0.46:
                sparse_regions.append(
                    {
                        "code": "single_column_sparse_float_region",
                        "page": page_number,
                        "top_fraction": round((block_top - body_top) / body_height, 4),
                        "height_fraction": round(block_height_fraction, 4),
                        "width_fraction": round(block_width_fraction, 4),
                        "minimum_width": 0.46,
                    }
                )

    violations: list[dict[str, Any]] = [
        {
            "code": "media_box_overflow",
            **item,
            "maximum_pt": MEDIA_BOX_OVERFLOW_PT,
        }
        for item in media_box_overflows
    ]
    visible_text = " ".join(str(box.get("text", "")) for box in boxes)
    has_rendered_artifact = re.search(
        r"\b(?:Table|Figure)\s+(?:\d+|[A-Z])\s*:", visible_text, re.IGNORECASE
    ) is not None
    effective_artifact_count = max(float_count, 1 if has_rendered_artifact else 0)
    if effective_artifact_count > 0:
        if leading_blank > 0.22:
            violations.append(
                {
                    "code": "float_page_leading_blank",
                    "page": page_number,
                    "fraction": round(leading_blank, 4),
                    "maximum": 0.22,
                }
            )
        if is_last_page:
            if trailing_blank > 0.45:
                violations.append(
                    {
                    "code": (
                        "terminal_float_page_trailing_blank"
                        if float_count > 0
                        else "terminal_artifact_page_trailing_blank"
                    ),
                        "page": page_number,
                        "fraction": round(trailing_blank, 4),
                        "maximum": 0.45,
                    }
                )
            if occupied_height < 0.35:
                violations.append(
                    {
                    "code": (
                        "terminal_float_page_too_sparse"
                        if float_count > 0
                        else "terminal_artifact_page_too_sparse"
                    ),
                        "page": page_number,
                        "fraction": round(occupied_height, 4),
                        "minimum": 0.35,
                    }
                )
        elif trailing_blank > 0.22:
            violations.append(
                {
                    "code": "float_page_trailing_blank" if float_count > 0 else "artifact_page_trailing_blank",
                    "page": page_number,
                    "fraction": round(trailing_blank, 4),
                    "maximum": 0.22,
                }
            )
    elif is_last_page:
        # A terminal prose-only stub is still an unprofessional layout failure.
        # Keep this deliberately looser than the float-page thresholds so that a
        # naturally short appendix ending is allowed while a near-empty page is not.
        if trailing_blank > 0.70:
            violations.append(
                {
                    "code": "terminal_page_trailing_blank",
                    "page": page_number,
                    "fraction": round(trailing_blank, 4),
                    "maximum": 0.70,
                }
            )
        if occupied_height < 0.20:
            violations.append(
                {
                    "code": "terminal_page_too_sparse",
                    "page": page_number,
                    "fraction": round(occupied_height, 4),
                    "minimum": 0.20,
                }
            )
    if effective_artifact_count > 0 and largest_internal > 0.16:
        violations.append(
            {
                "code": "float_page_internal_blank_band",
                "page": page_number,
                "fraction": round(largest_internal, 4),
                "maximum": 0.16,
            }
        )
    if not is_last_page and trailing_blank > 0.30:
        violations.append(
            {
                "code": "premature_page_ending",
                "page": page_number,
                "fraction": round(trailing_blank, 4),
                "maximum": 0.30,
            }
        )
    if column_mode == 1 and effective_artifact_count > 0 and occupied_height > 0.20:
        if content_width < 0.50:
            violations.append(
                {
                    "code": "single_column_narrow_content_block",
                    "page": page_number,
                    "fraction": round(content_width, 4),
                    "minimum": 0.50,
                }
            )
        if side_imbalance > 0.38:
            violations.append(
                {
                    "code": "single_column_side_imbalance",
                    "page": page_number,
                    "fraction": round(side_imbalance, 4),
                    "maximum": 0.38,
                }
            )
    violations.extend(sparse_regions)

    return {
        "page": page_number,
        "float_count": float_count,
        "rendered_artifact_detected": has_rendered_artifact,
        "content_box_count": len(filtered),
        "leading_blank_fraction": round(leading_blank, 4),
        "largest_internal_blank_fraction": round(largest_internal, 4),
        "trailing_blank_fraction": round(trailing_blank, 4),
        "occupied_height_fraction": round(occupied_height, 4),
        "content_width_fraction": round(content_width, 4),
        "side_imbalance_fraction": round(side_imbalance, 4),
        "media_box_overflows": media_box_overflows,
        "sparse_float_regions": sparse_regions,
        "violations": violations,
    }


def _pdf_page_boxes(page: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    words = list(page.extract_words())
    boxes: list[dict[str, Any]] = [
        {
            "x0": word.get("x0"),
            "x1": word.get("x1"),
            "top": word.get("top"),
            "bottom": word.get("bottom"),
            "text": word.get("text", ""),
            "kind": "text",
        }
        for word in words
    ]
    boxes.extend(
        {
            "x0": image.get("x0", 0),
            "x1": image.get("x1", page.width),
            "top": image.get("top", 0),
            "bottom": image.get("bottom", page.height),
            "text": "",
            "kind": "image",
        }
        for image in page.images
    )
    return boxes, words


def rendered_media_box_overflows(pdf_path: Path) -> list[dict[str, Any]]:
    """Independently derive media-box overflow records from a rendered PDF."""

    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise RuntimeError("rendered media-box audit requires the pdfplumber package") from exc

    overflows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            boxes, _ = _pdf_page_boxes(page)
            overflows.extend(
                media_box_overflows_from_boxes(
                    float(page.width),
                    float(page.height),
                    boxes,
                    page_number=page_number,
                )
            )
    return overflows


def float_reading_order_violations_from_pages(
    page_samples: list[dict[str, Any]], page_float_counts: dict[str, int]
) -> list[dict[str, Any]]:
    """Detect a top artifact inserted inside a word or unfinished sentence."""

    violations: list[dict[str, Any]] = []
    for index in range(len(page_samples) - 1):
        current = page_samples[index]
        following = page_samples[index + 1]
        page_number = index + 1
        next_page_number = page_number + 1
        if int(page_float_counts.get(str(next_page_number), 0)) <= 0:
            continue

        def content_words(sample: dict[str, Any]) -> list[dict[str, Any]]:
            width = float(sample["width"])
            height = float(sample["height"])
            kept: list[dict[str, Any]] = []
            for word in sample.get("words", []):
                text = str(word.get("text", "")).strip()
                x0 = float(word.get("x0", 0.0))
                top = float(word.get("top", 0.0))
                bottom = float(word.get("bottom", top))
                if not text or x0 < width * 0.16:
                    continue
                if top < height * 0.075 or bottom > height * 0.93:
                    continue
                kept.append(word)
            return sorted(
                kept,
                key=lambda word: (
                    float(word.get("top", 0.0)),
                    float(word.get("x0", 0.0)),
                ),
            )

        current_words = content_words(current)
        next_words = content_words(following)
        if not current_words or not next_words:
            continue
        trailing = str(current_words[-1].get("text", "")).strip()
        first_top = float(next_words[0].get("top", 0.0))
        first_line = " ".join(
            str(word.get("text", "")).strip()
            for word in next_words
            if abs(float(word.get("top", 0.0)) - first_top) <= 3.5
        )
        starts_with_artifact = re.match(
            r"^(?:Table|Figure)\s*(?:\d+|[A-Z])?\s*[:.]?",
            first_line,
            re.IGNORECASE,
        ) is not None
        if not starts_with_artifact:
            continue
        if re.fullmatch(r"[A-Za-z]{3,}-", trailing) is not None:
            violations.append(
                {
                    "code": "float_interrupted_hyphen",
                    "page": page_number,
                    "next_page": next_page_number,
                    "trailing_token": trailing,
                    "next_page_first_line": first_line,
                }
            )
            continue
        if re.search(r"[.!?][\"')\]}]*$", trailing) is None and not trailing.endswith(":"):
            last_top = float(current_words[-1].get("top", 0.0))
            last_line = " ".join(
                str(word.get("text", "")).strip()
                for word in current_words
                if abs(float(word.get("top", 0.0)) - last_top) <= 3.5
            )
            violations.append(
                {
                    "code": "float_interrupted_sentence",
                    "page": page_number,
                    "next_page": next_page_number,
                    "trailing_token": trailing,
                    "previous_page_last_line": last_line,
                    "next_page_first_line": first_line,
                }
            )
    return violations


def rendered_whitespace_audit(
    pdf_path: Path, page_float_counts: dict[str, int], column_mode: int
) -> dict[str, Any]:
    """Audit rendered PDF geometry; page labels alone cannot reveal blank bands."""

    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise RuntimeError("rendered whitespace audit requires the pdfplumber package") from exc

    pages: list[dict[str, Any]] = []
    column_samples: list[dict[str, Any]] = []
    page_samples: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    media_box_overflows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as document:
        total_pages = len(document.pages)
        for page_number, page in enumerate(document.pages, start=1):
            boxes, words = _pdf_page_boxes(page)
            record = page_geometry_from_boxes(
                float(page.width),
                float(page.height),
                boxes,
                page_number=page_number,
                float_count=int(page_float_counts.get(str(page_number), 0)),
                column_mode=column_mode,
                is_last_page=page_number == total_pages,
            )
            pages.append(record)
            violations.extend(record["violations"])
            media_box_overflows.extend(record["media_box_overflows"])
            column_samples.append(
                {"width": float(page.width), "height": float(page.height), "words": words}
            )
            page_samples.append(
                {"width": float(page.width), "height": float(page.height), "words": words}
            )
    column_inference = infer_column_mode_from_pages(column_samples)
    reading_order_violations = float_reading_order_violations_from_pages(
        page_samples, page_float_counts
    )
    return {
        "page_count": total_pages,
        "rendered_column_inference": column_inference,
        "thresholds": {
            "float_page_trailing_blank_maximum": 0.22,
            "float_page_leading_blank_maximum": 0.22,
            "terminal_artifact_page_trailing_blank_maximum": 0.45,
            "terminal_artifact_page_occupied_height_minimum": 0.35,
            "terminal_page_trailing_blank_maximum": 0.70,
            "terminal_page_occupied_height_minimum": 0.20,
            "float_page_internal_blank_maximum": 0.16,
            "premature_page_ending_maximum": 0.30,
            "single_column_content_width_minimum": 0.50,
            "single_column_side_imbalance_maximum": 0.38,
            "single_column_sparse_region_width_minimum": 0.46,
            "single_column_sparse_region_height_minimum": 0.16,
            "media_box_overflow_maximum_pt": MEDIA_BOX_OVERFLOW_PT,
        },
        "pages": pages,
        "media_box_overflows": media_box_overflows,
        "whitespace_violations": violations,
        "float_reading_order_violations": reading_order_violations,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_sha256(paper: Path) -> str:
    root = paper.expanduser().resolve()
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper", type=Path, help="Directory containing main.tex")
    parser.add_argument("--engine", default="auto", choices=["auto", "latexmk", "tectonic", "pdflatex"])
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--allow-overrun", type=int, default=0)
    parser.add_argument(
        "--columns",
        choices=["auto", "1", "2"],
        default="auto",
        help="Column mode; explicit values must agree with the active source/template audit",
    )
    parser.add_argument(
        "--references-counted",
        action="store_true",
        help="Count reference pages in the venue body-page limit",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    paper = args.paper.expanduser().resolve()
    main_tex = paper / "main.tex"
    build = (args.build_dir or paper.parent / "build").expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    pagination_commands: list[dict[str, Any]] = []
    fuzz_register_uses: list[dict[str, Any]] = []
    removed_build_artifacts: list[str] = []
    fresh_build = False
    compilation_attempted = False
    canonical_build = (paper.parent / "build").resolve()
    if build != canonical_build:
        errors.append("build directory must be the canonical project build directory")
    float_inventory: dict[str, Any] = {
        "active_body_files": [],
        "records": [],
        "labels": [],
        "unlabeled": [],
        "duplicate_labels": [],
        "after_conclusion_source": [],
        "appendix_records": [],
        "appendix_labels": [],
        "active_appendix_files": [],
        "unlabeled_appendix_floats": [],
        "all_records": [],
        "all_labels": [],
        "duplicate_all_float_labels": [],
        "structure_errors": [],
    }
    column_audit: dict[str, Any] = {
        "mode": 1,
        "requested": args.columns,
        "source": "unavailable",
        "evidence": [],
        "inspected_template_files": [],
        "override_verified": args.columns in {"auto", "1"},
    }
    active_document_files: list[str] = []
    if not main_tex.exists():
        errors.append(f"missing {main_tex}")
    elif paper.exists():
        try:
            document_segments = active_tex_segments(paper)
            active_document_files = sorted(
                {str(segment["path"]) for segment in document_segments}
            )
            pagination_commands = manual_pagination_commands(paper)
            fuzz_register_uses = tex_fuzz_register_uses(paper)
            float_inventory = body_float_inventory(paper)
        except ValueError as exc:
            errors.append(str(exc))
    if paper.exists():
        column_audit = document_column_mode_audit(paper, args.columns)
        if not column_audit["override_verified"]:
            errors.append(
                "--columns override disagrees with the active source/template audit; "
                "fix the template metadata instead of relaxing the layout gate"
            )
    if importlib.util.find_spec("pdfplumber") is None:
        errors.append(
            "missing required layout dependency pdfplumber; install idea2paper/requirements.txt"
        )
    if pagination_commands:
        rendered_commands = ", ".join(
            f"{item['path']}:{item['line']} {item['command']}" for item in pagination_commands
        )
        errors.append(
            "manual page-break/float-flush commands are forbidden in manuscript sources: "
            + rendered_commands
        )
    if fuzz_register_uses:
        rendered_uses = ", ".join(
            f"{item['path']}:{item['line']}:{item['column']} {item['command']}"
            for item in fuzz_register_uses
        )
        errors.append(
            "TeX fuzz registers are forbidden because they suppress clipping diagnostics: "
            + rendered_uses
        )
    if float_inventory["structure_errors"]:
        errors.extend(
            "invalid manuscript structure: " + str(error)
            for error in float_inventory["structure_errors"]
        )
    if float_inventory["unlabeled"]:
        rendered_unlabeled = ", ".join(
            f"{item['path']}:{item['line']} {item['environment']}"
            for item in float_inventory["unlabeled"]
        )
        errors.append("every active body float requires a unique label: " + rendered_unlabeled)
    if float_inventory["duplicate_labels"]:
        errors.append(
            "duplicate labels across active body floats: "
            + ", ".join(float_inventory["duplicate_labels"])
        )
    if float_inventory["unlabeled_appendix_floats"]:
        rendered_unlabeled = ", ".join(
            f"{item['path']}:{item['line']} {item['environment']}"
            for item in float_inventory["unlabeled_appendix_floats"]
        )
        errors.append("every active appendix float requires a unique label: " + rendered_unlabeled)
    if float_inventory["duplicate_all_float_labels"]:
        errors.append(
            "duplicate labels across active body/appendix floats: "
            + ", ".join(float_inventory["duplicate_all_float_labels"])
        )
    if float_inventory["after_conclusion_source"]:
        rendered_after_conclusion = ", ".join(
            f"{item['path']}:{item['line']} {item['environment']}"
            for item in float_inventory["after_conclusion_source"]
        )
        errors.append(
            "active manuscript contains floats at or after Conclusion begins: "
            + rendered_after_conclusion
        )
    engine = choose_engine(args.engine)
    if not engine:
        errors.append("no LaTeX engine found (latexmk, tectonic, or pdflatex)")

    output = ""
    returncode: int | None = None
    if not errors and engine:
        build.mkdir(parents=True, exist_ok=True)
        try:
            removed_build_artifacts = clean_core_build_artifacts(build)
            fresh_build = True
            compilation_attempted = True
            command = command_for(engine, paper, build)
            result = subprocess.run(command, cwd=paper, capture_output=True, text=True, timeout=args.timeout)
            returncode = result.returncode
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            if returncode != 0:
                errors.append(f"LaTeX engine exited with code {returncode}")
            if Path(engine).stem.lower() == "pdflatex" and returncode == 0:
                aux_path = build / "main.aux"
                aux_text = aux_path.read_text(encoding="utf-8", errors="replace") if aux_path.exists() else ""
                if "\\bibdata" in aux_text:
                    bibtex = shutil.which("bibtex")
                    if not bibtex:
                        errors.append("pdflatex fallback requires bibtex for this manuscript")
                    else:
                        bibliography = subprocess.run(
                            [bibtex, str(build / "main")],
                            cwd=paper,
                            capture_output=True,
                            text=True,
                            timeout=args.timeout,
                        )
                        output += "\n" + (bibliography.stdout or "") + "\n" + (bibliography.stderr or "")
                        if bibliography.returncode != 0:
                            errors.append(f"bibtex exited with code {bibliography.returncode}")
                if not errors:
                    for pass_number in (2, 3):
                        followup = subprocess.run(
                            command,
                            cwd=paper,
                            capture_output=True,
                            text=True,
                            timeout=args.timeout,
                        )
                        returncode = followup.returncode
                        output += "\n" + (followup.stdout or "") + "\n" + (followup.stderr or "")
                        if returncode != 0:
                            errors.append(f"pdflatex pass {pass_number} exited with code {returncode}")
                            break
        except subprocess.TimeoutExpired:
            errors.append(f"LaTeX compilation exceeded {args.timeout} seconds")
        except OSError as exc:
            errors.append(f"failed to prepare or start a fresh LaTeX build: {exc}")

    unresolved_patterns = [
        r"Citation .+ undefined",
        r"Reference .+ undefined",
        r"There were undefined references",
        r"There were undefined citations",
    ]
    for pattern in unresolved_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            errors.append(f"compile log contains unresolved references/citations ({pattern})")

    compiler_log_path = build / "main.log"
    current_compiler_log = compilation_attempted and compiler_log_path.is_file()
    compiler_log = (
        compiler_log_path.read_text(encoding="utf-8", errors="replace")
        if current_compiler_log
        else output
    )
    if returncode == 0 and not current_compiler_log:
        errors.append("LaTeX engine did not produce a fresh build/main.log")
    overfull_boxes = latex_overfull_boxes(compiler_log)
    material_overfull_boxes = [item for item in overfull_boxes if item["material"]]
    subthreshold_overfull_boxes = [item for item in overfull_boxes if not item["material"]]
    if material_overfull_boxes:
        rendered = ", ".join(
            f"{item['axis']}box {item['excess_pt']:.4g}pt {item['context']}".strip()
            for item in material_overfull_boxes
        )
        errors.append(
            f"compile log contains material overfull boxes above {MATERIAL_OVERFULL_PT:g}pt: "
            + rendered
        )
    if subthreshold_overfull_boxes:
        warnings.append(
            f"compile log contains {len(subthreshold_overfull_boxes)} sub-threshold "
            "overfull box(es) at or below "
            f"{MATERIAL_OVERFULL_PT:g}pt; inspect them visually"
        )

    pdf = build / "main.pdf"
    current_pdf = compilation_attempted and pdf.is_file()
    if returncode == 0 and not current_pdf:
        errors.append("LaTeX engine did not produce a fresh build/main.pdf")
    pages = pdf_pages(pdf) if current_pdf else None
    column_mode = int(column_audit["mode"])
    body_label = "idea2paper:end-references" if args.references_counted else "idea2paper:end-body"
    aux_path = build / "main.aux"
    current_aux = compilation_attempted and aux_path.is_file()
    body_pages = aux_label_page(aux_path, body_label) if current_aux else None
    conclusion_page = (
        aux_label_page(aux_path, "idea2paper:start-conclusion") if current_aux else None
    )
    end_body_page = aux_label_page(aux_path, "idea2paper:end-body") if current_aux else None
    end_exempt_page = aux_label_page(aux_path, "idea2paper:end-exempt") if current_aux else None
    appendix_start_page = aux_label_page(aux_path, APPENDIX_START_LABEL) if current_aux else None
    float_labels = list(float_inventory["labels"])
    if current_aux:
        float_pages, float_tail_violations = body_float_tail_report(
            aux_path, float_labels, conclusion_page
        )
    else:
        float_pages = {label: None for label in float_labels}
        float_tail_violations = []
    missing_float_aux_labels = sorted(label for label, page in float_pages.items() if page is None)
    all_float_labels = list(float_inventory["all_labels"])
    all_float_pages = {
        label: aux_label_page(aux_path, label) if current_aux else None
        for label in all_float_labels
    }
    missing_all_float_aux_labels = sorted(
        label for label, page in all_float_pages.items() if page is None
    )
    preliminary_distribution = float_distribution_audit(
        list(float_inventory["all_records"]),
        all_float_pages,
        appendix_start_page,
        pages,
        column_mode,
    )
    whitespace: dict[str, Any] = {
        "page_count": None,
        "rendered_column_inference": {
            "mode": None,
            "confidence": 0.0,
            "inspected_pages": 0,
            "eligible_text_rows": 0,
            "split_gutter_rows": 0,
            "split_gutter_ratio": 0.0,
        },
        "thresholds": {},
        "pages": [],
        "media_box_overflows": [],
        "whitespace_violations": [],
        "float_reading_order_violations": [],
    }
    if returncode == 0 and current_pdf:
        try:
            whitespace = rendered_whitespace_audit(
                pdf, preliminary_distribution["page_float_counts"], column_mode
            )
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"could not complete rendered whitespace audit: {exc}")
    if pages is None and whitespace.get("page_count") is not None:
        pages = int(whitespace["page_count"])
    distribution = float_distribution_audit(
        list(float_inventory["all_records"]),
        all_float_pages,
        appendix_start_page,
        pages,
        column_mode,
    )
    rendered_column = whitespace.get("rendered_column_inference", {})
    if (
        isinstance(rendered_column, dict)
        and rendered_column.get("mode") in {1, 2}
        and float(rendered_column.get("confidence", 0.0)) >= 0.70
        and int(rendered_column["mode"]) != column_mode
    ):
        errors.append(
            "rendered column geometry disagrees with the active source/template column audit"
        )
    conclusion_record = (
        aux_label_record(aux_path, "idea2paper:start-conclusion")
        if current_aux
        else (None, None)
    )
    end_body_record = (
        aux_label_record(aux_path, "idea2paper:end-body") if current_aux else (None, None)
    )
    conclusion_before_end_body = (
        conclusion_record[0] is not None
        and end_body_record[0] is not None
        and conclusion_record[0] <= end_body_record[0]
        and conclusion_record[1] is not None
        and end_body_record[1] is not None
        and conclusion_record[1] < end_body_record[1]
    )
    if returncode == 0 and conclusion_page is None:
        errors.append("missing required LaTeX label idea2paper:start-conclusion")
    if returncode == 0 and end_body_page is None:
        errors.append("missing required LaTeX label idea2paper:end-body")
    if returncode == 0 and end_exempt_page is None:
        errors.append("missing required LaTeX label idea2paper:end-exempt")
    if returncode == 0 and appendix_start_page is None:
        errors.append("missing required LaTeX label idea2paper:start-appendix")
    if returncode == 0 and not conclusion_before_end_body:
        errors.append("Conclusion must begin before the end-body boundary")
    if returncode == 0 and missing_float_aux_labels:
        errors.append(
            "body float labels are missing from the compiled AUX: "
            + ", ".join(missing_float_aux_labels)
        )
    if returncode == 0 and missing_all_float_aux_labels:
        errors.append(
            "body/appendix float labels are missing from the compiled AUX: "
            + ", ".join(missing_all_float_aux_labels)
        )
    if float_tail_violations:
        rendered_tail = ", ".join(
            f"{item['label']} on page {item['page']}" for item in float_tail_violations
        )
        errors.append("body floats appear on pages after Conclusion begins: " + rendered_tail)
    if distribution["float_distribution_violations"]:
        rendered_codes = ", ".join(
            str(item.get("code")) for item in distribution["float_distribution_violations"]
        )
        errors.append("rendered float distribution violates layout gates: " + rendered_codes)
    if whitespace["whitespace_violations"]:
        rendered_codes = ", ".join(
            f"{item.get('code')}@p{item.get('page')}"
            for item in whitespace["whitespace_violations"]
        )
        errors.append("rendered page geometry violates whitespace gates: " + rendered_codes)
    reading_order_violations = whitespace.get("float_reading_order_violations", [])
    if reading_order_violations:
        rendered_codes = ", ".join(
            f"{item.get('code')}@p{item.get('page')}->p{item.get('next_page')}"
            for item in reading_order_violations
        )
        errors.append("rendered floats interrupt reading continuity: " + rendered_codes)
    exempt_page_span = (
        end_exempt_page - end_body_page
        if end_exempt_page is not None and end_body_page is not None
        else None
    )
    if returncode == 0 and (
        exempt_page_span is None or exempt_page_span < 0 or exempt_page_span > 1
    ):
        errors.append(
            "the page-limit-exempt disclosure region must span at most one additional page"
        )
    if args.max_pages is not None:
        if body_pages is None:
            errors.append(f"could not determine body page count from LaTeX label {body_label}")
        elif body_pages > args.max_pages + args.allow_overrun:
            errors.append(
                f"body has {body_pages} pages; configured maximum is "
                f"{args.max_pages} + {args.allow_overrun} overrun"
            )

    report: dict[str, Any] = {
        "schema_version": 10,
        "paper": str(paper),
        "source_sha256": source_tree_sha256(paper),
        "engine": engine,
        "returncode": returncode,
        "build_dir": str(build),
        "fresh_build": fresh_build,
        "fresh_build_removed_artifacts": removed_build_artifacts,
        "compiler_log": str(compiler_log_path) if current_compiler_log else None,
        "compiler_log_sha256": (
            sha256_file(compiler_log_path) if current_compiler_log else None
        ),
        "pdf": str(pdf) if current_pdf else None,
        "pdf_sha256": sha256_file(pdf) if current_pdf else None,
        "aux": str(aux_path) if current_aux else None,
        "aux_sha256": sha256_file(aux_path) if current_aux else None,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "total_pages": pages,
        "body_pages": body_pages,
        "references_counted": args.references_counted,
        "max_pages": args.max_pages,
        "allow_overrun": args.allow_overrun,
        "manual_pagination_commands": pagination_commands,
        "tex_fuzz_register_uses": fuzz_register_uses,
        "active_document_files": active_document_files,
        "active_body_files": float_inventory["active_body_files"],
        "conclusion_page": conclusion_page,
        "end_body_page": end_body_page,
        "end_exempt_page": end_exempt_page,
        "appendix_start_page": appendix_start_page,
        "exempt_page_span": exempt_page_span,
        "max_exempt_page_span": 1,
        "conclusion_before_end_body": conclusion_before_end_body,
        "tracked_body_float_count": len(float_inventory["records"]),
        "manuscript_structure_errors": float_inventory["structure_errors"],
        "source_body_floats_after_conclusion": float_inventory["after_conclusion_source"],
        "unlabeled_body_floats": float_inventory["unlabeled"],
        "duplicate_body_float_labels": float_inventory["duplicate_labels"],
        "tracked_appendix_float_count": len(float_inventory["appendix_records"]),
        "active_appendix_files": float_inventory["active_appendix_files"],
        "unlabeled_appendix_floats": float_inventory["unlabeled_appendix_floats"],
        "duplicate_all_float_labels": float_inventory["duplicate_all_float_labels"],
        "missing_body_float_aux_labels": missing_float_aux_labels,
        "missing_all_float_aux_labels": missing_all_float_aux_labels,
        "body_float_pages": float_pages,
        "all_float_pages": all_float_pages,
        "body_float_tail_violations": float_tail_violations,
        "column_mode": column_mode,
        "column_mode_audit": column_audit,
        "rendered_column_inference": rendered_column,
        "layout_dependencies": {"pdfplumber": "required"},
        "overfull_box_threshold_pt": MATERIAL_OVERFULL_PT,
        "overfull_boxes": overfull_boxes,
        "material_overfull_boxes": material_overfull_boxes,
        "media_box_overflow_threshold_pt": MEDIA_BOX_OVERFLOW_PT,
        "media_box_overflows": whitespace["media_box_overflows"],
        **distribution,
        "rendered_page_geometry": whitespace["pages"],
        "whitespace_thresholds": whitespace["thresholds"],
        "whitespace_violations": whitespace["whitespace_violations"],
        "float_reading_order_violations": reading_order_violations,
        "page_check_note": "Body pages are read from explicit LaTeX boundary labels; total_pages includes the appendix.",
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
