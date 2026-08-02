#!/usr/bin/env python3
"""Compile a LaTeX paper, check unresolved references, and report PDF pages."""

from __future__ import annotations

import argparse
import hashlib
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
INPUT_RE = re.compile(
    r"\\(?P<command>input|include)(?![A-Za-z@])\s*"
    r"(?:\{(?P<braced>[^}]+)\}|(?P<bare>[^\s%{}]+))"
)
FLOAT_RE = re.compile(
    r"\\begin\{((?:figure|table)\*?)\}([\s\S]*?)\\end\{(?:figure|table)\*?\}"
)
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
BODY_END_MARKER = r"\label{idea2paper:end-body}"
BODY_EXEMPT_END_MARKER = r"\label{idea2paper:end-exempt}"
BODY_REFERENCES_END_MARKER = r"\label{idea2paper:end-references}"
CONCLUSION_LABEL = "idea2paper:start-conclusion"
CONCLUSION_HEADING_RE = re.compile(r"\\section\*?\s*\{Conclusion\}")
CONCLUSION_BLOCK_RE = re.compile(
    r"\\section\*?\s*\{Conclusion\}\s*\\label\{idea2paper:start-conclusion\}"
)
BIBLIOGRAPHY_RE = re.compile(r"\\(?:bibliography\s*\{|printbibliography\b|begin\{thebibliography\})")
APPENDIX_RE = re.compile(r"\\appendix\b")
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
        return [engine, "-pdf", "-interaction=nonstopmode", "-halt-on-error", f"-outdir={build}", "main.tex"]
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
                            "text": text,
                        }
                    )
                return True
        if text:
            segments.append(
                {
                    "path": path.relative_to(paper).as_posix(),
                    "line": source.count("\n", 0, start) + 1,
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
        }
    segments = active_tex_segments(paper)
    source = _combined_source(segments)
    errors: list[str] = []
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
    """Find author-inserted page breaks and float flushes in active manuscript inputs."""

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
    return violations


def body_float_inventory(paper: Path) -> dict[str, Any]:
    """Inventory every pre-appendix float and bind it to the canonical Conclusion."""

    structure = manuscript_structure_audit(paper)
    segments = list(structure["segments"])
    source = str(structure["source"])
    appendix_position = structure["appendix_position"]
    cutoff = appendix_position if isinstance(appendix_position, int) else len(source)
    pre_appendix_source = source[:cutoff]
    records: list[dict[str, Any]] = []
    labels: list[str] = []
    unlabeled: list[dict[str, Any]] = []
    after_conclusion_source: list[dict[str, Any]] = []
    conclusion_position = structure["conclusion_position"]
    for index, match in enumerate(FLOAT_RE.finditer(pre_appendix_source), start=1):
        path, line = _segment_origin(segments, match.start())
        float_labels = LABEL_RE.findall(match.group(2))
        record = {
            "float_index": index,
            "environment": match.group(1),
            "path": path,
            "line": line,
            "labels": float_labels,
            "source_offset": match.start(),
            "after_conclusion_source": (
                isinstance(conclusion_position, int) and match.start() > conclusion_position
            ),
        }
        records.append(record)
        if not float_labels:
            unlabeled.append(record)
        if record["after_conclusion_source"]:
            after_conclusion_source.append(record)
        labels.extend(float_labels)
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    active_body_files: set[str] = set()
    consumed = 0
    for segment in segments:
        text = str(segment["text"])
        if consumed < cutoff and text:
            active_body_files.add(str(segment["path"]))
        consumed += len(text)
    return {
        "active_body_files": sorted(active_body_files),
        "records": records,
        "labels": sorted(set(labels)),
        "unlabeled": unlabeled,
        "duplicate_labels": duplicate_labels,
        "after_conclusion_source": after_conclusion_source,
        "structure_errors": list(structure["errors"]),
    }


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
    float_inventory: dict[str, Any] = {
        "active_body_files": [],
        "records": [],
        "labels": [],
        "unlabeled": [],
        "duplicate_labels": [],
        "after_conclusion_source": [],
        "structure_errors": [],
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
            float_inventory = body_float_inventory(paper)
        except ValueError as exc:
            errors.append(str(exc))
    if pagination_commands:
        rendered_commands = ", ".join(
            f"{item['path']}:{item['line']} {item['command']}" for item in pagination_commands
        )
        errors.append(
            "manual page-break/float-flush commands are forbidden in manuscript sources: "
            + rendered_commands
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
        command = command_for(engine, paper, build)
        try:
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
            errors.append(f"failed to start LaTeX engine: {exc}")

    unresolved_patterns = [
        r"Citation .+ undefined",
        r"Reference .+ undefined",
        r"There were undefined references",
        r"There were undefined citations",
    ]
    for pattern in unresolved_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            errors.append(f"compile log contains unresolved references/citations ({pattern})")

    pdf = build / "main.pdf"
    pages = pdf_pages(pdf) if pdf.exists() else None
    body_label = "idea2paper:end-references" if args.references_counted else "idea2paper:end-body"
    aux_path = build / "main.aux"
    body_pages = aux_label_page(aux_path, body_label)
    conclusion_page = aux_label_page(aux_path, "idea2paper:start-conclusion")
    end_body_page = aux_label_page(aux_path, "idea2paper:end-body")
    end_exempt_page = aux_label_page(aux_path, "idea2paper:end-exempt")
    float_labels = list(float_inventory["labels"])
    float_pages, float_tail_violations = body_float_tail_report(
        aux_path, float_labels, conclusion_page
    )
    missing_float_aux_labels = sorted(label for label, page in float_pages.items() if page is None)
    conclusion_record = aux_label_record(aux_path, "idea2paper:start-conclusion")
    end_body_record = aux_label_record(aux_path, "idea2paper:end-body")
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
    if returncode == 0 and not conclusion_before_end_body:
        errors.append("Conclusion must begin before the end-body boundary")
    if returncode == 0 and missing_float_aux_labels:
        errors.append(
            "body float labels are missing from the compiled AUX: "
            + ", ".join(missing_float_aux_labels)
        )
    if float_tail_violations:
        rendered_tail = ", ".join(
            f"{item['label']} on page {item['page']}" for item in float_tail_violations
        )
        errors.append("body floats appear on pages after Conclusion begins: " + rendered_tail)
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
        "schema_version": 5,
        "paper": str(paper),
        "source_sha256": source_tree_sha256(paper),
        "engine": engine,
        "returncode": returncode,
        "build_dir": str(build),
        "pdf": str(pdf) if pdf.exists() else None,
        "pdf_sha256": sha256_file(pdf) if pdf.exists() else None,
        "aux_sha256": sha256_file(build / "main.aux") if (build / "main.aux").exists() else None,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "total_pages": pages,
        "body_pages": body_pages,
        "references_counted": args.references_counted,
        "max_pages": args.max_pages,
        "allow_overrun": args.allow_overrun,
        "manual_pagination_commands": pagination_commands,
        "active_document_files": active_document_files,
        "active_body_files": float_inventory["active_body_files"],
        "conclusion_page": conclusion_page,
        "end_body_page": end_body_page,
        "end_exempt_page": end_exempt_page,
        "exempt_page_span": exempt_page_span,
        "max_exempt_page_span": 1,
        "conclusion_before_end_body": conclusion_before_end_body,
        "tracked_body_float_count": len(float_inventory["records"]),
        "manuscript_structure_errors": float_inventory["structure_errors"],
        "source_body_floats_after_conclusion": float_inventory["after_conclusion_source"],
        "unlabeled_body_floats": float_inventory["unlabeled"],
        "duplicate_body_float_labels": float_inventory["duplicate_labels"],
        "missing_body_float_aux_labels": missing_float_aux_labels,
        "body_float_pages": float_pages,
        "body_float_tail_violations": float_tail_violations,
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
