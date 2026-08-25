from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import utc_now, write_json


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


def memory_bytes() -> dict[str, int | None]:
    if os.name == "nt":
        status = _MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {
                "total": int(status.total_physical),
                "available": int(status.available_physical),
            }
    if hasattr(os, "sysconf"):
        try:
            page = int(os.sysconf("SC_PAGE_SIZE"))
            return {
                "total": page * int(os.sysconf("SC_PHYS_PAGES")),
                "available": page * int(os.sysconf("SC_AVPHYS_PAGES")),
            }
        except (OSError, ValueError):
            pass
    return {"total": None, "available": None}


def gpu_inventory() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"backend": "nvidia", "available": False, "devices": [], "error": "nvidia-smi not found"}
    query = "index,name,memory.total,driver_version"
    try:
        result = subprocess.run(
            [executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        devices = []
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 4:
                continue
            devices.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_total_mib": int(parts[2]),
                    "driver_version": parts[3],
                }
            )
        return {"backend": "nvidia", "available": bool(devices), "devices": devices}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"backend": "nvidia", "available": False, "devices": [], "error": str(exc)}


def collect_resources(path: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "schema_version": 1,
        "captured_at": utc_now(),
        "source": "current_machine",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "python_executable": str(Path(sys.executable).resolve()),
        },
        "cpu": {"logical_count": os.cpu_count()},
        "memory_bytes": memory_bytes(),
        "disk_bytes": {"path": str(path.resolve()), "total": usage.total, "free": usage.free},
        "accelerators": [gpu_inventory()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a local compute-resource snapshot.")
    parser.add_argument("--path", default=".", help="Filesystem path used for disk-capacity inspection.")
    parser.add_argument("--output", help="Optional JSON output path; otherwise print to stdout.")
    args = parser.parse_args()

    snapshot = collect_resources(Path(args.path).expanduser().resolve())
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), snapshot)
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
