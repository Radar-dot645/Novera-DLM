"""Optional Termux:API notifications."""
from __future__ import annotations
import shutil
import subprocess


def notify(title: str, content: str) -> bool:
    binary = shutil.which("termux-notification")
    if not binary:
        return False
    try:
        result = subprocess.run([binary, "--title", title[:100], "--content", content[:300]],
                                check=False, timeout=5, capture_output=True, text=True)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
