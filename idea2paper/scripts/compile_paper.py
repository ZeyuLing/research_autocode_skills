#!/usr/bin/env python3
"""Compile a LaTeX paper, check unresolved references, and report PDF pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_sha256(paper: Path) -> str:
    root = paper.expanduser().resolve()
    included_suffixes = {".tex", ".sty", ".cls", ".bst", ".bib", ".png", ".jpg", ".jpeg", ".webp"}
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in included_suffixes),
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
    if not main_tex.exists():
        errors.append(f"missing {main_tex}")
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
    body_pages = aux_label_page(build / "main.aux", body_label)
    if args.max_pages is not None:
        if body_pages is None:
            errors.append(f"could not determine body page count from LaTeX label {body_label}")
        elif body_pages > args.max_pages + args.allow_overrun:
            errors.append(
                f"body has {body_pages} pages; configured maximum is "
                f"{args.max_pages} + {args.allow_overrun} overrun"
            )

    report: dict[str, Any] = {
        "schema_version": 1,
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
