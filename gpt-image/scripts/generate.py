#!/usr/bin/env python3
"""Disabled legacy launcher for the Codex-local gpt-image skill.

This local installation is configured as a prompt/reference layer that delegates
image execution to the system `.system/imagegen` skill and built-in `image_gen`
tool. It must not silently fall back to the packaged CLI, uvx, or OpenAI client
path.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "error: this Codex-local gpt-image skill does not execute image calls "
        "through the legacy CLI/client path. Use the installed system imagegen "
        "skill at /root/.codex/skills/.system/imagegen/SKILL.md and its "
        "built-in image_gen tool instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
