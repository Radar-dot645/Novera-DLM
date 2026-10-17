"""Safe subprocess wrappers for optional download tools and Git."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from . import choose_backend
from ..security import validate_url


def clone_repository(url: str, destination: Path, *, depth: int | None = None) -> None:
    safe_url = validate_url(url)
    from urllib.parse import urlsplit
    if urlsplit(safe_url).query:
        raise ValueError("URL clone dengan query parameter ditolak untuk menghindari token terekspos di process list; gunakan credential helper Git.")
    if destination.exists():
        raise FileExistsError(f"Tujuan sudah ada: {destination}")
    if not __import__("shutil").which("git"):
        raise RuntimeError("Git belum terpasang. Pasang dengan `pkg install git`.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone", "--", safe_url]
    if depth is not None:
        if depth < 1:
            raise ValueError("depth harus >= 1")
        args = ["git", "clone", "--depth", str(depth), "--", safe_url]
    result = subprocess.run(args + [str(destination)], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git clone gagal dengan exit code {result.returncode}")


def download_with_external(backend: str, url: str, destination: Path, *, timeout: int = 30) -> None:
    """Run a chosen external HTTP tool without invoking a shell.

    External tools are deliberately opt-in except aria2 auto-selection for large
    assets. URL protocols are constrained on curl; Python HTTP remains the most
    strictly redirect-validated backend.
    """
    safe_url = validate_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".part")
    if temp.is_symlink():
        raise RuntimeError("File .part adalah symbolic link; backend eksternal dihentikan demi keamanan.")
    if backend == "curl":
        args = ["curl", "--fail", "--location", "--silent", "--show-error", "--connect-timeout", str(timeout), "--max-time", str(timeout * 100), "--proto", "=http,https", "--proto-redir", "=http,https", "--continue-at", "-", "--output", str(temp), safe_url]
    elif backend == "wget":
        args = ["wget", "--continue", "--timeout", str(timeout), "--tries", "3", "--max-redirect", "0", "--output-document", str(temp), safe_url]
    elif backend == "aria2":
        args = ["aria2c", "--continue=true", "--check-certificate=true", "--max-redirect=0", "--max-tries=3", "--retry-wait=2", "--max-connection-per-server=4", "--split=4", "--allow-overwrite=true", "--auto-file-renaming=false", "--dir", str(destination.parent), "--out", temp.name, safe_url]
    else:
        raise ValueError(f"Backend eksternal tidak didukung: {backend}")
    try:
        subprocess.run(args, check=True, timeout=timeout * 120)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Backend {backend} gagal dengan exit code {exc.returncode}; URL disamarkan dari error.") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Backend {backend} melewati batas waktu.") from None
    if not temp.is_file():
        raise RuntimeError(f"Backend {backend} tidak menghasilkan file.")
    os.replace(temp, destination)
