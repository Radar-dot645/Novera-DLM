"""File integrity verification; never invents or fetches a checksum implicitly."""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


class VerificationError(ValueError):
    pass


def normalize_sha256(expected: str) -> str:
    value = (expected or "").strip().lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise VerificationError("SHA-256 harus berupa 64 karakter heksadesimal.")
    return value


def sha256_file(path: Path, chunk_size: int = 1024 * 1024, progress=None) -> str:
    digest = hashlib.sha256()
    total, done = path.stat().st_size, 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str, progress=None) -> tuple[bool, str]:
    value = normalize_sha256(expected)
    if not path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    actual = sha256_file(path, progress=progress)
    return hmac.compare_digest(actual, value), actual
