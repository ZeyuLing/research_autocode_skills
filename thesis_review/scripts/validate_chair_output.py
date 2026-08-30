#!/usr/bin/env python3
"""Read-only pre-Stage-S mechanical gate for current Chair outputs.

The sibling validator's explicit ``--pre-stage-s`` mode validates the exact
frozen Stage-C closure.  That mode forbids Stage-S and Stage-V artifacts and
omits only their own validations; it never suppresses diagnostics by matching
error-message text.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


VALIDATOR = Path(__file__).with_name("validate_review_bundle.py")


def parse_errors(stdout: str) -> list[str]:
    errors: list[str] = []
    in_errors = False
    for raw in stdout.splitlines():
        line = raw.strip()
        if line == "## Errors":
            in_errors = True
            continue
        if line == "## Warnings":
            break
        if in_errors and line.startswith("- ") and line != "- none":
            errors.append(line[2:])
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    args = parser.parse_args(argv)
    root = args.round_directory.absolute()
    command = [
        sys.executable, "-B", str(VALIDATOR), str(root), "--pre-stage-s"
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as exc:
        print("FAIL")
        print(f"Chair validator could not launch safely: {exc}")
        return 1
    errors = parse_errors(completed.stdout)
    # A traceback, transport failure, or unparseable failed report is never a
    # valid scoped PASS.
    if completed.returncode != 0 and not errors:
        errors.append(
            "full validator failed without a parseable mechanical error list: "
            + completed.stdout[-2000:].replace("\n", " ")
        )
    canonical_pass = bool(
        re.search(r"(?m)^- Result: \*\*PASS\*\*$", completed.stdout)
        and re.search(r"(?m)^## Errors$", completed.stdout)
        and re.search(r"(?m)^- none$", completed.stdout)
    )
    if completed.returncode == 0 and not canonical_pass:
        errors.append(
            "full validator returned success without its canonical PASS report"
        )
    if completed.returncode != 0 or errors:
        print("FAIL")
        for error in errors:
            print(error)
        return 1
    print("PASS")
    print(
        "All current upstream, reviewer, AI, citation/bibliography/layout, "
        "Chair, 91, and 92 artifacts passed the read-only pre-Stage-S gate; "
        "only the intentionally absent Stage-S outputs were waived."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
