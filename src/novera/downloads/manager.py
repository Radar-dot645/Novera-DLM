"""Streaming HTTP download engine with safe redirects, resume, retry, and mirrors."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from ..backends import choose_backend
from ..backends.external import download_with_external
from ..config import AppConfig
from ..security import SecurityError, redact_url, resolve_download_path, validate_redirect, validate_url
from ..verification import normalize_sha256, sha256_file, verify_sha256


class DownloadError(RuntimeError):
    pass


class DownloadCancelled(DownloadError):
    pass


@dataclass
class DownloadResult:
    url: str
    destination: Path
    size_bytes: int
    sha256: str | None
    backend: str
    status: str = "completed"
    message: str = ""
    verified: bool = False


def filename_from_url(url: str) -> str:
    name = unquote(Path(urlsplit(url).path).name)
    return name or "download.bin"


def _part_paths(destination: Path) -> tuple[Path, Path]:
    part = destination.with_name(destination.name + ".part")
    metadata = destination.with_name(destination.name + ".part.json")
    return part, metadata


def _url_fingerprint(url: str) -> str:
    """Match a resume URL without persisting signed query strings or credentials."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _read_metadata(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _safe_metadata_write(path: Path, value: dict) -> None:
    # A random, exclusively-created temp file avoids following a pre-created
    # metadata-temp symlink in a writable download directory.
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            tmp_name = stream.name
            stream.write(json.dumps(value, ensure_ascii=False))
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


_DESTINATION_LOCK = threading.Lock()
_RESERVED_DESTINATIONS: set[str] = set()


def _choose_destination(directory: Path, filename: str, policy: str) -> Path | None:
    if policy not in {"rename", "skip", "overwrite"}:
        raise ValueError("overwrite_policy harus rename, skip, atau overwrite")
    destination = resolve_download_path(directory, filename)
    with _DESTINATION_LOCK:
        key = str(destination)
        reserved = key in _RESERVED_DESTINATIONS
        exists = destination.exists() or destination.is_symlink()
        if policy == "skip":
            if exists or reserved:
                return None
            _RESERVED_DESTINATIONS.add(key)
            return destination
        if policy == "overwrite":
            if reserved:
                raise DownloadError(f"Tujuan sedang dipakai unduhan lain: {destination}")
            _RESERVED_DESTINATIONS.add(key)
            return destination
        # rename: select an unused disk path that is not already being downloaded.
        if not exists and not reserved:
            _RESERVED_DESTINATIONS.add(key)
            return destination
        stem, suffix = destination.stem, destination.suffix
        for number in range(1, 10000):
            candidate = destination.with_name(f"{stem} ({number}){suffix}")
            candidate_key = str(candidate)
            if not candidate.exists() and not candidate.is_symlink() and candidate_key not in _RESERVED_DESTINATIONS:
                _RESERVED_DESTINATIONS.add(candidate_key)
                return candidate
    raise DownloadError("Terlalu banyak nama file duplikat.")


def _release_destination(destination: Path) -> None:
    with _DESTINATION_LOCK:
        _RESERVED_DESTINATIONS.discard(str(destination))


from ..ratelimit import GLOBAL as _ratelimit


class DownloadManager:
    def __init__(self, config: AppConfig | None = None, *, progress_callback=None, history=None):
        self.config = config or AppConfig()
        self.progress_callback = progress_callback
        self.history = history
        self._cancel = threading.Event()
        _ratelimit.set_rate(self.config.downloads.bandwidth_limit_kbps * 1024)

    def cancel(self) -> None:
        """Request cooperative cancellation at the next streamed chunk."""
        self._cancel.set()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    def download(self, url: str, *, filename: str | None = None,
                 backend: str = "auto", expected_sha256: str | None = None,
                 overwrite_policy: str | None = None, mirrors: list[str] | None = None,
                 size_bytes: int | None = None) -> DownloadResult:
        original_url = validate_url(url)
        if expected_sha256 is not None:
            expected_sha256 = normalize_sha256(expected_sha256)
        policy = overwrite_policy or self.config.downloads.overwrite_policy
        final_name = filename or filename_from_url(original_url)
        chosen = _choose_destination(self.config.download_path, final_name, policy)
        if chosen is None:
            return DownloadResult(original_url, resolve_download_path(self.config.download_path, final_name),
                                  0, None, "none", "skipped", "File sudah ada atau sedang diunduh; dilewati sesuai kebijakan.")
        from ..logging_utils import get_logger, redact_text
        logger = get_logger()
        try:
            result = self._download_to_destination(original_url, chosen, backend=backend,
                                                   expected_sha256=expected_sha256, mirrors=mirrors,
                                                   size_bytes=size_bytes)
        except Exception as exc:
            logger.warning("download failed url=%s error=%s", redact_url(original_url),
                           redact_text(str(exc)))
            raise
        else:
            logger.info("download completed url=%s destination=%s size_bytes=%d backend=%s checksum_verified=%s",
                        redact_url(original_url), result.destination, result.size_bytes,
                        result.backend, result.verified)
            return result
        finally:
            _release_destination(chosen)

    def _download_to_destination(self, original_url: str, chosen: Path, *, backend: str,
                                 expected_sha256: str | None, mirrors: list[str] | None,
                                 size_bytes: int | None) -> DownloadResult:
        self.config.download_path.mkdir(parents=True, exist_ok=True)
        range_supported = False
        if backend == "auto" and size_bytes is None:
            size_bytes, range_supported = self._probe_remote(original_url)
        url_candidates = [original_url]
        explicit_mirrors = mirrors if mirrors is not None else self.config.network.mirrors
        for mirror in explicit_mirrors:
            try:
                mirror_url = validate_url(mirror)
                # An HTTPS primary must never fall back to an HTTP mirror.
                from ..security import validate_redirect
                mirror_url = validate_redirect(original_url, mirror_url)
                if mirror_url not in url_candidates:
                    url_candidates.append(mirror_url)
            except SecurityError:
                continue
        choice = choose_backend(backend, size_bytes=size_bytes, range_supported=range_supported)
        if choice.name != "python-http" and urlsplit(original_url).query:
            if backend == "auto":
                from ..backends import BackendChoice
                choice = BackendChoice("python-http", "URL memiliki query parameter; menghindari paparan signed URL di daftar proses")
            else:
                raise DownloadError("Backend eksternal ditolak untuk URL dengan query parameter agar token/signed URL tidak terekspos di daftar proses. Gunakan --backend python.")
        if choice.name != "python-http":
            # Stage each external attempt separately so bad checksums never destroy
            # an existing destination. Try configured mirrors with the same selected
            # backend; never silently switch backend when explicitly selected.
            staging = chosen.with_name("." + chosen.name + ".novera-stage")
            errors: list[str] = []
            for candidate in url_candidates:
                if urlsplit(candidate).query:
                    errors.append(f"{redact_url(candidate)}: URL query ditolak untuk backend eksternal agar token tidak terekspos")
                    continue
                try:
                    staging.unlink(missing_ok=True)
                    staging.with_name(staging.name + ".part").unlink(missing_ok=True)
                    download_with_external(choice.name, candidate, staging,
                                           timeout=int(self.config.downloads.timeout_seconds))
                    downloaded_size = staging.stat().st_size
                    max_size = self.config.security.max_file_size_mb * 1024 * 1024
                    if max_size and downloaded_size > max_size:
                        raise DownloadError(f"File melampaui batas konfigurasi ({max_size} bytes).")
                    digest = sha256_file(staging)
                    if expected_sha256:
                        ok, digest = verify_sha256(staging, expected_sha256)
                        if not ok:
                            raise DownloadError("Checksum SHA-256 tidak cocok.")
                    os.replace(staging, chosen)
                    if self.progress_callback:
                        self.progress_callback(chosen.stat().st_size, size_bytes or chosen.stat().st_size)
                    result = DownloadResult(candidate, chosen, chosen.stat().st_size, digest, choice.name,
                                            "verified" if expected_sha256 else "completed", verified=bool(expected_sha256))
                    self._record(result)
                    return result
                except Exception as exc:
                    errors.append(f"{redact_url(candidate)}: {str(exc).replace(candidate, redact_url(candidate))}")
                    staging.unlink(missing_ok=True)
                    staging.with_name(staging.name + ".part").unlink(missing_ok=True)
                    if "Checksum SHA-256" in str(exc) or "File melampaui batas" in str(exc):
                        raise DownloadError(str(exc)) from None
            raise DownloadError("Backend eksternal gagal pada sumber dan mirror: " + " | ".join(errors[-6:]))

        errors: list[str] = []
        for candidate in url_candidates:
            for attempt in range(self.config.downloads.retries + 1):
                if self._cancel.is_set():
                    raise DownloadCancelled("Unduhan dibatalkan pengguna.")
                try:
                    digest = self._download_attempt(candidate, chosen, attempt=attempt,
                                                    max_redirects=self.config.security.max_redirects,
                                                    max_size_bytes=self.config.security.max_file_size_mb * 1024 * 1024,
                                                    expected_sha256=expected_sha256)
                    result = DownloadResult(candidate, chosen, chosen.stat().st_size, digest, "python-http",
                                            "verified" if expected_sha256 else "completed", verified=bool(expected_sha256))
                    self._record(result)
                    return result
                except DownloadCancelled:
                    raise
                except DownloadError as exc:
                    errors.append(f"{redact_url(candidate)}: {str(exc).replace(candidate, redact_url(candidate))}")
                    # Non-retryable integrity/security failures must not be hidden.
                    if "Checksum SHA-256" in str(exc) or "symbolic link" in str(exc):
                        raise
                    if attempt < self.config.downloads.retries:
                        time.sleep(min(0.25 * (2 ** attempt), 2.0))
                except (httpx.HTTPError, OSError, ValueError, SecurityError) as exc:
                    errors.append(f"{redact_url(candidate)}: {str(exc).replace(candidate, redact_url(candidate))}")
                    if attempt < self.config.downloads.retries:
                        time.sleep(min(0.25 * (2 ** attempt), 2.0))
        raise DownloadError("Semua percobaan unduhan gagal. " + " | ".join(errors[-6:]))

    def _probe_remote(self, url: str) -> tuple[int | None, bool]:
        """Probe size and HTTP Range support without downloading the response body.

        Automatic external-backend selection is limited to direct HTTPS resources;
        if HEAD redirects, the Python backend handles the later validated redirect.
        """
        current = url
        if urlsplit(current).scheme.lower() != "https":
            return None, False
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0), follow_redirects=False) as client:
                with client.stream("HEAD", current, headers={"User-Agent": self.config.network.user_agent}) as response:
                    if response.status_code in {301, 302, 303, 307, 308} or response.status_code >= 400:
                        return None, False
                    length = response.headers.get("content-length", "")
                    size = int(length) if length.isdigit() else None
                    ranges = response.headers.get("accept-ranges", "").lower() == "bytes"
                    return size, ranges
        except (httpx.HTTPError, OSError, ValueError, SecurityError):
            return None, False

    def _download_attempt(self, url: str, destination: Path, *, attempt: int,
                          max_redirects: int, max_size_bytes: int,
                          expected_sha256: str | None = None) -> str:
        part, metadata_path = _part_paths(destination)
        if part.is_symlink():
            part.unlink(missing_ok=True)
            raise DownloadError("File partial berbentuk symbolic link; link ditolak demi keamanan.")
        if metadata_path.is_symlink():
            metadata_path.unlink(missing_ok=True)
        meta = _read_metadata(metadata_path)
        if part.exists() and meta.get("url_hash") != _url_fingerprint(url) and meta.get("url") != url:
            part.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            meta = {}
        offset = part.stat().st_size if self.config.downloads.resume and part.exists() else 0
        validator = meta.get("etag") or meta.get("last_modified")
        if offset and not validator:
            # No ETag/Last-Modified means the old partial cannot be safely bound
            # to the current representation; restart instead of appending blindly.
            part.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            offset = 0
            meta = {}
        headers = {"User-Agent": self.config.network.user_agent, "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            headers["If-Range"] = validator

        current_url = url
        with httpx.Client(timeout=httpx.Timeout(self.config.downloads.timeout_seconds), follow_redirects=False) as client:
            for redirect_count in range(max_redirects + 1):
                if self._cancel.is_set():
                    raise DownloadCancelled("Unduhan dibatalkan pengguna.")
                with client.stream("GET", current_url, headers=headers) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise DownloadError("Redirect tanpa header Location.")
                        if redirect_count >= max_redirects:
                            raise DownloadError("Melewati batas redirect.")
                        next_url = validate_redirect(current_url, urljoin(current_url, location))
                        if urlsplit(next_url).netloc.lower() != urlsplit(current_url).netloc.lower():
                            # Never leak validators or partial-range assumptions across hosts.
                            headers.pop("Range", None)
                            headers.pop("If-Range", None)
                            offset = 0
                        current_url = next_url
                        continue
                    response.raise_for_status()
                    append_mode = False
                    if offset and response.status_code == 206:
                        content_range = response.headers.get("content-range", "")
                        match = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", content_range, re.I)
                        current_etag = response.headers.get("etag")
                        current_modified = response.headers.get("last-modified")
                        validator_changed = ((meta.get("etag") and current_etag and meta.get("etag") != current_etag) or
                                             (not meta.get("etag") and meta.get("last_modified") and current_modified and meta.get("last_modified") != current_modified))
                        if not match or int(match.group(1)) != offset or validator_changed:
                            part.unlink(missing_ok=True)
                            metadata_path.unlink(missing_ok=True)
                            raise DownloadError("Server mengirim Content-Range atau validator yang tidak sesuai saat resume.")
                        append_mode = True
                        total = int(match.group(3)) if match.group(3) != "*" else None
                    else:
                        # 200 after Range means range unsupported or validator changed.
                        offset = 0
                        total = int(response.headers.get("content-length", "0") or 0) or None
                    if not offset and response.status_code == 206:
                        raise DownloadError("Server mengirim partial response tanpa permintaan resume.")
                    if total is None:
                        length = int(response.headers.get("content-length", "0") or 0)
                        total = (offset + length) if length else None
                    if max_size_bytes and total and total > max_size_bytes:
                        raise DownloadError(f"File melampaui batas konfigurasi ({max_size_bytes} bytes).")
                    new_meta = {"url_hash": _url_fingerprint(url), "etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified")}
                    _safe_metadata_write(metadata_path, new_meta)
                    mode = "ab" if append_mode else "wb"
                    downloaded = offset if append_mode else 0
                    with part.open(mode) as stream:
                        for chunk in response.iter_bytes(chunk_size=128 * 1024):
                            if self._cancel.is_set():
                                raise DownloadCancelled("Unduhan dibatalkan pengguna.")
                            if not chunk:
                                continue
                            stream.write(chunk)
                            _ratelimit.throttle(len(chunk))
                            downloaded += len(chunk)
                            if max_size_bytes and downloaded > max_size_bytes:
                                raise DownloadError(f"File melampaui batas konfigurasi ({max_size_bytes} bytes).")
                            if self.progress_callback:
                                self.progress_callback(downloaded, total)
                    if total is not None and part.stat().st_size != total:
                        raise DownloadError(f"Ukuran tidak lengkap: diterima {part.stat().st_size}, diharapkan {total} bytes.")
                    digest = sha256_file(part)
                    if expected_sha256:
                        ok, digest = verify_sha256(part, expected_sha256)
                        if not ok:
                            part.unlink(missing_ok=True)
                            metadata_path.unlink(missing_ok=True)
                            raise DownloadError("Checksum SHA-256 tidak cocok; file staging hasil unduhan dihapus.")
                    os.replace(part, destination)
                    metadata_path.unlink(missing_ok=True)
                    return digest
            raise DownloadError("Batas redirect tercapai.")

    def _record(self, result: DownloadResult) -> None:
        if self.history:
            try:
                self.history.add(url=redact_url(result.url), destination=str(result.destination), size_bytes=result.size_bytes,
                                sha256=result.sha256, status=result.status, backend=result.backend)
            except Exception:
                # Download success must not be turned into failure by history I/O.
                pass

    def download_batch(self, urls: list[str], *, backend: str = "auto", concurrency: int | None = None) -> list[DownloadResult | Exception]:
        values = [str(url).strip() for url in urls if str(url).strip() and not str(url).lstrip().startswith("#")]
        workers = concurrency or self.config.downloads.concurrency
        workers = max(1, min(int(workers), 8))
        results: list[DownloadResult | Exception | None] = [None] * len(values)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="novera") as pool:
            futures = {pool.submit(self.download, url, backend=backend): index for index, url in enumerate(values)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    results[index] = exc
        return [r if r is not None else DownloadError("Tidak ada hasil.") for r in results]
