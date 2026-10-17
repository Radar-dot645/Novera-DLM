"""Input validation and safe filename helpers."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}
_INVALID_FILENAME = re.compile(r"[^\w.() @,+\-\[\]]", re.UNICODE)


class SecurityError(ValueError):
    """Raised when untrusted input violates a security requirement."""


def validate_url(url: str) -> str:
    """Validate an HTTP(S) URL and return its normalized form.

    Embedded user-info is rejected to avoid leaking credentials into logs. This
    validates syntax, not trustworthiness; downloads can still retrieve any host
    explicitly supplied by the user.
    """
    value = (url or "").strip()
    if not value or any(ord(ch) < 32 for ch in value):
        raise SecurityError("URL kosong atau mengandung karakter kontrol.")
    try:
        parts = urlsplit(value)
        _ = parts.port  # Force malformed ports to raise ValueError.
    except ValueError as exc:
        raise SecurityError(f"URL tidak valid: {exc}") from exc
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise SecurityError("Hanya URL HTTP dan HTTPS yang diizinkan.")
    if not parts.hostname:
        raise SecurityError("URL harus memiliki hostname.")
    if parts.username is not None or parts.password is not None:
        raise SecurityError("URL dengan username/password tertanam ditolak.")
    if parts.fragment:
        parts = parts._replace(fragment="")
    return urlunsplit(parts)


def validate_redirect(source_url: str, target_url: str) -> str:
    """Validate a redirect target; HTTPS-to-HTTP downgrades are rejected."""
    source = validate_url(source_url)
    target = validate_url(target_url)
    if urlsplit(source).scheme.lower() == "https" and urlsplit(target).scheme.lower() != "https":
        raise SecurityError("Redirect dari HTTPS ke HTTP ditolak (downgrade TLS).")
    return target


def sanitize_filename(name: str, fallback: str = "download.bin", max_length: int = 180) -> str:
    """Produce a plain filename with no directories or traversal components."""
    raw = unicodedata.normalize("NFKC", str(name or ""))
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = raw.replace("\x00", "")
    raw = _INVALID_FILENAME.sub("_", raw).strip(" .")
    while ".." in raw:
        raw = raw.replace("..", ".")
    if raw in {"", ".", ".."}:
        raw = fallback
    # Avoid Windows device names for ZIPs that may be unpacked elsewhere.
    stem = raw.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raw = f"_{raw}"
    return raw[:max_length].rstrip(" .") or fallback


def resolve_download_path(directory: Path, filename: str) -> Path:
    """Resolve a sanitized filename and prove it stays inside directory."""
    root = directory.expanduser().resolve()
    clean = sanitize_filename(filename)
    destination = (root / clean).resolve()
    if destination.parent != root:
        raise SecurityError("Path unduhan keluar dari direktori tujuan.")
    return destination


def redact_url(url: str) -> str:
    """Return a URL suitable for user-facing logs (query values are hidden)."""
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "[redacted]" if parts.query else "", ""))
    except Exception:
        return "[invalid-url]"
