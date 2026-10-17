"""Optional .env loader and wizard. Tokens are optional; public features work without them."""
from __future__ import annotations

import os
import stat
from pathlib import Path

KNOWN_KEYS = ("GITHUB_TOKEN", "GITLAB_TOKEN")


def env_paths() -> list[Path]:
    return [Path.cwd() / ".env", Path.home() / ".config" / "novera" / ".env"]


def find_env() -> Path | None:
    return next((p for p in env_paths() if p.is_file() and not p.is_symlink()), None)


def insecure_permissions(path: Path) -> bool:
    try:
        return bool(path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
    except OSError:
        return False


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        if k in KNOWN_KEYS and v:
            out[k] = v
    return out


def load_env(path: Path | None = None) -> tuple[list[str], list[str]]:
    """Load known keys without overriding real environment. Returns (loaded_key_names, warnings)."""
    path = path or find_env()
    if path is None or not path.is_file():
        return [], []
    warnings = []
    if insecure_permissions(path):
        warnings.append(f"Permission {path} terlalu longgar; jalankan: chmod 600 {path}")
    try:
        values = parse_env(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [], [f"Tidak bisa membaca {path}: {exc}"]
    loaded = []
    for k, v in values.items():
        if k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded, warnings


def write_env(values: dict[str, str], path: Path | None = None) -> Path:
    """Write .env with 0600 permission, atomically; empty values are omitted."""
    path = path or (Path.home() / ".config" / "novera" / ".env")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{k}={v}\n" for k, v in values.items() if k in KNOWN_KEYS and v and "\n" not in v)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return path
