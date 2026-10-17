"""Git clone (with parsed real progress) and status. Never runs repo scripts or builds."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .security import validate_url

_PCT = re.compile(r"^(?P<phase>[A-Za-z ]+):\s+(?P<pct>\d+)%")


def _require_git() -> str:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git belum terpasang. Termux: `pkg install git`; Debian/Ubuntu: `sudo apt install git`.")
    return git


def clone(url: str, destination: Path, *, depth: int | None = None, progress=None) -> None:
    """progress(phase:str, percent:int|None). Hooks are disabled via core.hooksPath=/dev/null."""
    safe = validate_url(url)
    if urlsplit(safe).query:
        raise ValueError("URL clone dengan query parameter ditolak agar token tidak terekspos; gunakan credential helper Git.")
    if destination.exists():
        raise FileExistsError(f"Tujuan sudah ada: {destination}")
    git = _require_git()
    args = [git, "-c", "core.hooksPath=/dev/null", "clone", "--progress"]
    if depth is not None:
        if depth < 1:
            raise ValueError("depth harus >= 1")
        args += ["--depth", str(depth)]
    args += ["--", safe, str(destination)]
    destination.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, errors="replace")
    tail: list[str] = []
    buf = ""
    assert proc.stderr
    while ch := proc.stderr.read(1):
        if ch in "\r\n":
            line = buf.strip()
            buf = ""
            if not line:
                continue
            m = _PCT.match(line.replace("remote: ", ""))
            if m and progress:
                progress(m["phase"].strip(), int(m["pct"]))
            else:
                tail = (tail + [line])[-5:]
                if progress:
                    progress(line[:60], None)
        else:
            buf += ch
    if proc.wait() != 0:
        raise RuntimeError("git clone gagal (exit %d): %s" % (proc.returncode, " | ".join(tail)[:300]))


def status(path: Path) -> str:
    git = _require_git()
    if not (path / ".git").exists():
        raise ValueError(f"{path} bukan repository Git.")
    r = subprocess.run([git, "-C", str(path), "-c", "core.hooksPath=/dev/null", "status", "--short", "--branch"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300] or "git status gagal")
    return r.stdout.strip() or "(bersih)"
