#!/usr/bin/env python3
"""Collect a conservative current-machine compute snapshot without secrets."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def total_memory_bytes() -> int | None:
    if sys.platform == "win32":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
        return None

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (AttributeError, OSError, ValueError):
        return None


def query_nvidia_gpus() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    command = [
        executable,
        "--query-gpu=index,name,memory.total,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    except (OSError, subprocess.SubprocessError):
        return []

    gpus: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        index, name, total_mib, free_mib, driver = parts
        try:
            total_value: int | None = int(total_mib)
            free_value: int | None = int(free_mib)
        except ValueError:
            total_value = None
            free_value = None
        gpus.append(
            {
                "index": index,
                "name": name,
                "memory_total_mib": total_value,
                "memory_free_mib": free_value,
                "driver_version": driver,
            }
        )
    return gpus


def collect_resources(path_for_disk: Path | None = None) -> dict[str, Any]:
    target = (path_for_disk or Path.cwd()).resolve()
    disk = shutil.disk_usage(target)
    return {
        "schema_version": 1,
        "source": "current_machine",
        "collected_utc": utc_now(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "cpu": {
            "processor": platform.processor() or "unknown",
            "logical_cores": os.cpu_count(),
        },
        "memory": {"total_bytes": total_memory_bytes()},
        "disk": {
            "path": str(target),
            "total_bytes": disk.total,
            "free_bytes": disk.free,
        },
        "gpus": query_nvidia_gpus(),
        "notes": [
            "This is a capacity snapshot, not authorization to run long or costly jobs.",
            "Unavailable devices are recorded as empty or unknown rather than inferred.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    parser.add_argument("--disk-path", type=Path, help="Path whose volume should be measured")
    args = parser.parse_args()

    payload = collect_resources(args.disk_path)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
