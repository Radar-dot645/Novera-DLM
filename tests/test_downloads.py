from __future__ import annotations

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from novera.config import AppConfig, DownloadConfig, NetworkConfig, SecurityConfig
from novera.downloads import DownloadCancelled, DownloadError, DownloadManager
from novera.history import HistoryStore

PAYLOAD = b"novera test payload\n" * 3000
SLOW_PAYLOAD = b"Z" * (512 * 1024)


class Handler(BaseHTTPRequestHandler):
    counters: dict[str, int] = {}

    def log_message(self, *_args):
        pass

    def do_HEAD(self):
        path = urlsplit(self.path).path
        if path in {"/file.bin", "/flaky", "/no-range", "/primary", "/mirror", "/resume.bin", "/file.apk", "/a.bin", "/b.bin", "/slow.bin"}:
            body = b"mirror payload" if path == "/mirror" else (b"primary payload" if path == "/primary" else (b"A" * 1024 if path == "/a.bin" else (b"B" * 2048 if path == "/b.bin" else PAYLOAD)))
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.send_header("ETag", '"tag1"')
            if path != "/no-range": self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        self.counters[path] = self.counters.get(path, 0) + 1
        if path == "/page":
            body = b'<html><a href="/app-universal.apk">Universal APK</a><a href="/archive.zip">Archive</a><a href="javascript:bad()">bad</a></html>'
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path == "/redirect":
            self.send_response(302); self.send_header("Location", "/file.bin"); self.end_headers(); return
        if path == "/flaky" and self.counters[path] == 1:
            self.send_response(503); self.send_header("Content-Length", "0"); self.end_headers(); return
        if path == "/failure" or path == "/primary":
            self.send_response(503); self.send_header("Content-Length", "0"); self.end_headers(); return
        if path == "/slow.bin":
            body = SLOW_PAYLOAD
            range_header = self.headers.get("Range")
            start = 0
            if range_header:
                try: start = int(range_header.split("=", 1)[1].split("-", 1)[0])
                except Exception: start = 0
            partial = body[start:]
            self.send_response(206 if start else 200)
            if start: self.send_header("Content-Range", f"bytes {start}-{len(body)-1}/{len(body)}")
            self.send_header("Content-Length", str(len(partial))); self.send_header("ETag", '"tag1"'); self.send_header("Accept-Ranges", "bytes"); self.end_headers()
            try:
                for offset in range(0, len(partial), 128 * 1024):
                    self.wfile.write(partial[offset:offset + 128 * 1024]); self.wfile.flush(); time.sleep(0.015)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if path in {"/file.bin", "/flaky", "/no-range", "/mirror", "/resume.bin", "/file.apk", "/a.bin", "/b.bin"}:
            body = b"mirror payload" if path == "/mirror" else (b"A" * 1024 if path == "/a.bin" else (b"B" * 2048 if path == "/b.bin" else PAYLOAD))
            range_header = self.headers.get("Range")
            if range_header and path != "/no-range":
                try:
                    start = int(range_header.split("=", 1)[1].split("-", 1)[0])
                except Exception:
                    start = 0
                if 0 <= start < len(body):
                    part = body[start:]
                    self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{len(body)-1}/{len(body)}")
                    self.send_header("Content-Length", str(len(part))); self.send_header("ETag", '"tag1"'); self.send_header("Accept-Ranges", "bytes"); self.end_headers(); self.wfile.write(part); return
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.send_header("ETag", '"tag1"')
            if path != "/no-range": self.send_header("Accept-Ranges", "bytes")
            self.end_headers(); self.wfile.write(body); return
        self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()


@pytest.fixture()
def server():
    Handler.counters = {}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    host = f"http://127.0.0.1:{httpd.server_port}"
    yield host
    httpd.shutdown(); thread.join(timeout=2); httpd.server_close()


def make_config(tmp_path: Path, **overrides) -> AppConfig:
    d = DownloadConfig(directory=str(tmp_path / "downloads"), concurrency=3, retries=1, timeout_seconds=3, resume=True, overwrite_policy="rename")
    for key, value in overrides.items():
        setattr(d, key, value)
    return AppConfig(downloads=d, network=NetworkConfig(mirrors=[]), security=SecurityConfig(max_redirects=5, max_file_size_mb=0))


def test_download_and_hash(server, tmp_path):
    manager = DownloadManager(make_config(tmp_path))
    result = manager.download(server + "/file.bin", backend="python")
    assert result.destination.read_bytes() == PAYLOAD
    assert result.size_bytes == len(PAYLOAD)
    assert result.sha256 == hashlib.sha256(PAYLOAD).hexdigest()


def test_download_redirect(server, tmp_path):
    result = DownloadManager(make_config(tmp_path)).download(server + "/redirect", backend="python")
    assert result.destination.read_bytes() == PAYLOAD


def test_retry_transient_error(server, tmp_path):
    Handler.counters = {}
    result = DownloadManager(make_config(tmp_path, retries=1)).download(server + "/flaky", backend="python")
    assert result.destination.read_bytes() == PAYLOAD
    assert Handler.counters["/flaky"] >= 2


def test_all_retries_fail(server, tmp_path):
    with pytest.raises(DownloadError, match="percobaan unduhan gagal"):
        DownloadManager(make_config(tmp_path, retries=1)).download(server + "/failure", backend="python")


def test_resume_partial(server, tmp_path):
    config = make_config(tmp_path)
    url = server + "/resume.bin"
    config.download_path.mkdir(parents=True)
    part = config.download_path / "resume.bin.part"
    meta = config.download_path / "resume.bin.part.json"
    part.write_bytes(PAYLOAD[:1234])
    meta.write_text(json.dumps({"url_hash": hashlib.sha256(url.encode()).hexdigest(), "etag": '"tag1"', "last_modified": None}), encoding="utf-8")
    result = DownloadManager(config).download(url, backend="python")
    assert result.destination.read_bytes() == PAYLOAD
    assert not part.exists() and not meta.exists()


def test_resume_falls_back_when_server_ignores_range(server, tmp_path):
    config = make_config(tmp_path)
    url = server + "/no-range"
    config.download_path.mkdir(parents=True)
    (config.download_path / "no-range.part").write_bytes(b"old partial")
    (config.download_path / "no-range.part.json").write_text(json.dumps({"url_hash": hashlib.sha256(url.encode()).hexdigest(), "etag": '"tag1"'}), encoding="utf-8")
    result = DownloadManager(config).download(url, backend="python")
    assert result.destination.read_bytes() == PAYLOAD


def test_mirror_fallback(server, tmp_path):
    config = make_config(tmp_path)
    result = DownloadManager(config).download(server + "/primary", backend="python", mirrors=[server + "/mirror"])
    assert result.destination.read_bytes() == b"mirror payload"
    assert result.url.endswith("/mirror")


def test_skip_existing_file(server, tmp_path):
    config = make_config(tmp_path)
    config.download_path.mkdir(parents=True)
    (config.download_path / "file.bin").write_bytes(b"keep me")
    result = DownloadManager(config).download(server + "/file.bin", backend="python", overwrite_policy="skip")
    assert result.status == "skipped"
    assert (config.download_path / "file.bin").read_bytes() == b"keep me"


def test_rename_duplicate(server, tmp_path):
    config = make_config(tmp_path)
    config.download_path.mkdir(parents=True)
    (config.download_path / "file.bin").write_bytes(b"existing")
    result = DownloadManager(config).download(server + "/file.bin", backend="python", overwrite_policy="rename")
    assert result.destination.name == "file (1).bin"


def test_checksum_mismatch_removes_file(server, tmp_path):
    with pytest.raises(DownloadError, match="Checksum SHA-256"):
        DownloadManager(make_config(tmp_path)).download(server + "/file.bin", backend="python", expected_sha256="0" * 64)
    assert not (tmp_path / "downloads" / "file.bin").exists()


def test_cancel_before_start(server, tmp_path):
    manager = DownloadManager(make_config(tmp_path))
    manager.cancel()
    with pytest.raises(DownloadCancelled):
        manager.download(server + "/file.bin", backend="python")


def test_batch_download(server, tmp_path):
    config = make_config(tmp_path, concurrency=2)
    manager = DownloadManager(config)
    results = manager.download_batch([server + "/a.bin", server + "/b.bin"], backend="python", concurrency=2)
    assert all(not isinstance(r, Exception) for r in results)
    assert [r.size_bytes for r in results] == [1024, 2048]


def test_history_redacts_query(server, tmp_path):
    config = make_config(tmp_path)
    db = HistoryStore(tmp_path / "history.sqlite3")
    result = DownloadManager(config, history=db).download(server + "/file.bin?token=secret", backend="python")
    row = db.list()[0]
    assert "secret" not in row["url"]
    assert "redacted" in row["url"]


def test_cancel_midstream_preserves_partial_and_resume(server, tmp_path):
    config = make_config(tmp_path)
    should_cancel = {"value": True}
    manager = None
    def callback(current, total):
        if should_cancel["value"] and current > 0:
            should_cancel["value"] = False
            manager.cancel()
    manager = DownloadManager(config, progress_callback=callback)
    with pytest.raises(DownloadCancelled):
        manager.download(server + "/slow.bin", backend="python")
    part = config.download_path / "slow.bin.part"
    assert part.exists() and 0 < part.stat().st_size < len(SLOW_PAYLOAD)
    manager.reset_cancel()
    result = manager.download(server + "/slow.bin", backend="python")
    assert result.destination.read_bytes() == SLOW_PAYLOAD
    assert not part.exists()


def test_partial_metadata_does_not_store_signed_url(server, tmp_path):
    config = make_config(tmp_path)
    should_cancel = {"value": True}
    manager = None
    def callback(current, total):
        if should_cancel["value"] and current > 0:
            should_cancel["value"] = False
            manager.cancel()
    manager = DownloadManager(config, progress_callback=callback)
    signed_url = server + "/slow.bin?token=supersecret"
    with pytest.raises(DownloadCancelled):
        manager.download(signed_url, backend="python")
    metadata = (config.download_path / "slow.bin.part.json").read_text(encoding="utf-8")
    assert "supersecret" not in metadata
    assert "url_hash" in metadata


def test_failure_message_redacts_query_token(server, tmp_path):
    with pytest.raises(DownloadError) as exc:
        DownloadManager(make_config(tmp_path, retries=0)).download(server + "/failure?token=supersecret", backend="python")
    assert "supersecret" not in str(exc.value)


def test_bad_checksum_never_deletes_overwritten_destination(server, tmp_path):
    config = make_config(tmp_path)
    config.download_path.mkdir(parents=True)
    original = config.download_path / "file.bin"
    original.write_bytes(b"important previous file")
    with pytest.raises(DownloadError, match="Checksum SHA-256"):
        DownloadManager(config).download(server + "/file.bin", backend="python",
                                          expected_sha256="0" * 64, overwrite_policy="overwrite")
    assert original.read_bytes() == b"important previous file"


def test_explicit_external_backend_rejects_signed_url_before_process(server, tmp_path):
    with pytest.raises(DownloadError, match="query parameter"):
        DownloadManager(make_config(tmp_path)).download(server + "/file.bin?token=secret", backend="curl")


@pytest.mark.parametrize("backend", ["curl", "wget"])
def test_external_backends_download_local_file_when_installed(server, tmp_path, backend):
    import shutil
    if not shutil.which(backend):
        pytest.skip(f"{backend} is optional and not installed")
    result = DownloadManager(make_config(tmp_path)).download(server + "/file.bin", backend=backend)
    assert result.destination.read_bytes() == PAYLOAD
    assert result.backend == backend


def test_partial_symlink_is_rejected_without_modifying_target(server, tmp_path):
    config = make_config(tmp_path, retries=0)
    config.download_path.mkdir(parents=True)
    protected = tmp_path / "protected.txt"
    protected.write_bytes(b"do not modify")
    part = config.download_path / "file.bin.part"
    try:
        part.symlink_to(protected)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links unavailable in this environment")
    with pytest.raises(DownloadError, match="symbolic link"):
        DownloadManager(config).download(server + "/file.bin", backend="python")
    assert protected.read_bytes() == b"do not modify"
    assert not part.exists() and not part.is_symlink()


def test_concurrent_duplicate_urls_get_distinct_destinations(server, tmp_path):
    manager = DownloadManager(make_config(tmp_path, concurrency=2))
    results = manager.download_batch([server + "/file.bin", server + "/file.bin"], backend="python", concurrency=2)
    assert all(not isinstance(result, Exception) for result in results)
    paths = [result.destination for result in results]
    assert len(set(paths)) == 2
    assert {path.name for path in paths} == {"file.bin", "file (1).bin"}
    assert all(path.read_bytes() == PAYLOAD for path in paths)

@pytest.mark.parametrize("backend", ["curl", "wget"])
def test_external_backend_mirror_fallback_when_installed(server, tmp_path, backend):
    import shutil
    if not shutil.which(backend):
        pytest.skip(f"{backend} is optional and not installed")
    config = make_config(tmp_path)
    result = DownloadManager(config).download(server + "/primary", backend=backend,
                                              mirrors=[server + "/mirror"])
    assert result.destination.read_bytes() == b"mirror payload"
    assert result.backend == backend
    assert result.url.endswith("/mirror")
