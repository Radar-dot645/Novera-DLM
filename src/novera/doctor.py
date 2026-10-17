"""Runtime diagnostics for platform and optional tools."""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path


def diagnostics() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    rows.append(("Platform", f"{platform.system()} / {platform.machine()}", "OK"))
    rows.append(("Python", sys.version.split()[0], "OK" if sys.version_info >= (3, 11) else "WARN: requires Python 3.11+"))
    for module in ("rich", "httpx"):
        installed = importlib.util.find_spec(module) is not None
        rows.append((f"Python package: {module}", "installed" if installed else "missing", "OK" if installed else "ERROR: run pip install -r requirements.txt"))
    for binary in ("git", "curl", "wget", "aria2c", "termux-notification", "aapt", "apkanalyzer"):
        path = shutil.which(binary)
        rows.append((binary, path or "not found", "optional" if not path else "available"))
    home_storage = Path.home() / "storage" / "downloads"
    rows.append(("Termux shared storage", str(home_storage), "available" if home_storage.exists() else "not initialized (optional)"))
    rows.append(("HOME", os.environ.get("HOME", "unset"), "OK" if os.environ.get("HOME") else "WARN"))
    return rows
