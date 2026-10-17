"""Download backend selection and optional tool adapters."""
from __future__ import annotations
import shutil
from dataclasses import dataclass

@dataclass(frozen=True)
class BackendChoice:
    name: str
    reason: str


def choose_backend(requested: str = "auto", *, size_bytes: int | None = None, is_git: bool = False, range_supported: bool = False) -> BackendChoice:
    """Choose a backend without silently overriding any explicit user choice."""
    available = {name: shutil.which(binary) for name, binary in {
        "curl": "curl", "wget": "wget", "aria2": "aria2c", "git": "git"
    }.items()}
    if requested != "auto":
        if requested not in {"python", "curl", "wget", "aria2", "git"}:
            raise ValueError(f"Backend tidak dikenal: {requested}")
        if requested in available and not available[requested]:
            raise RuntimeError(f"Backend '{requested}' dipilih manual tetapi tidak terpasang. Pilihan tidak diganti diam-diam.")
        if requested == "git" and not is_git:
            raise ValueError("Backend Git hanya untuk clone repository.")
        return BackendChoice("python-http" if requested == "python" else requested, "dipilih manual oleh pengguna")
    if is_git:
        if available["git"]:
            return BackendChoice("git", "sumber adalah repository dan Git tersedia")
        raise RuntimeError("Git diperlukan untuk clone repository. Pasang dengan `pkg install git` di Termux.")
    # Prefer Python for small/unknown files. aria2 is selected only for known large
    # assets, and only when present; it is implemented with a safe argument list.
    if size_bytes is not None and size_bytes >= 100 * 1024 * 1024 and range_supported and available["aria2"]:
        return BackendChoice("aria2", "file >= 100 MiB, HTTP Range didukung, dan aria2c tersedia")
    return BackendChoice("python-http", "fallback aman dan konsisten; ukuran kecil/tidak diketahui")
