import io, os, stat, threading, time, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from novera import abi, archive, devplan, envfile, progress, ratelimit
from novera.config import AppConfig
from novera.discovery import Asset
from novera.history import HistoryStore
from novera.queue import QueueRunner, QueueStore


# ---- progress math
def test_formulas():
    assert progress.percent(50, 200) == 25.0
    assert progress.percent(5, None) is None and progress.percent(5, 0) is None
    assert progress.speed(1000, 2) == 500
    assert progress.speed(10, 0) is None
    assert progress.eta(100, 1100, 500) == 2.0
    assert progress.eta(100, None, 500) is None and progress.eta(100, 1000, 0) is None


def test_rate_meter_uses_delta():
    m = progress.RateMeter(window=1.0, _t=0.0)
    assert m.update(500, now=0.5) is None
    assert m.update(2000, now=2.0) == 1000


# ---- safe zip
def _zip(tmp, entries, symlink=None):
    p = tmp / "a.zip"
    with zipfile.ZipFile(p, "w") as z:
        for n, d in entries.items():
            z.writestr(n, d)
        if symlink:
            i = zipfile.ZipInfo(symlink[0]); i.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(i, symlink[1])
    return p


def test_extract_ok(tmp_path):
    calls = []
    n = archive.safe_extract(_zip(tmp_path, {"d/x.txt": "hello"}), tmp_path / "o", lambda a, b: calls.append((a, b)))
    assert n == 1 and (tmp_path / "o/d/x.txt").read_text() == "hello" and calls[-1] == (5, 5)


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../evil.txt"])
def test_extract_blocks_traversal(tmp_path, name):
    with pytest.raises(archive.ArchiveError):
        archive.safe_extract(_zip(tmp_path, {name: "x"}), tmp_path / "o")
    assert not (tmp_path / "evil.txt").exists()


def test_extract_blocks_symlink_and_corrupt(tmp_path):
    with pytest.raises(archive.ArchiveError):
        archive.safe_extract(_zip(tmp_path, {"a": "1"}, ("ln", "/etc/passwd")), tmp_path / "o")
    bad = tmp_path / "bad.zip"; bad.write_bytes(b"not a zip")
    with pytest.raises(archive.ArchiveError):
        archive.safe_extract(bad, tmp_path / "o2")


# ---- env
def test_env_load_and_perms(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    p = envfile.write_env({"GITHUB_TOKEN": "tok123", "OTHER": "x"}, tmp_path / ".env")
    assert stat.S_IMODE(p.stat().st_mode) == 0o600 and "OTHER" not in p.read_text()
    assert envfile.load_env(p) == (["GITHUB_TOKEN"], [])
    assert os.environ["GITHUB_TOKEN"] == "tok123"
    p.chmod(0o644)
    assert envfile.load_env(p)[1]
    monkeypatch.delenv("GITHUB_TOKEN")


def test_env_missing_is_fine(tmp_path):
    assert envfile.load_env(tmp_path / "none") == ([], [])


def test_token_redaction():
    from novera.logging_utils import redact_text
    assert "ghp_" not in redact_text("fail ghp_" + "a" * 30)


# ---- abi
def test_recommend_apk():
    a = [Asset("x-x86.apk", "u1", "t", architecture="x86", kind="apk"), Asset("x-arm64-v8a.apk", "u2", "t", architecture="arm64-v8a", kind="apk")]
    r, why = abi.recommend_apk(a, ["arm64-v8a", "armeabi-v7a"])
    assert r is a[1] and "inspect-apk" in why
    assert abi.recommend_apk(a, ["mips"])[0] is None


# ---- devplan
def test_plan_never_runs(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "Makefile").write_text("all:\n\ttouch pwned\n")
    plan = devplan.make_plan(tmp_path)
    assert plan.kinds == ["Node.js", "Make"] and not (tmp_path / "pwned").exists()
    assert "--ignore-scripts" in plan.steps[0].command


# ---- ratelimit
def test_ratelimit_throttles():
    rl = ratelimit.RateLimiter(100_000)
    t = time.monotonic(); rl.throttle(50_000); rl.throttle(50_000); rl.throttle(1)
    assert time.monotonic() - t >= 0.9


# ---- queue + local HTTP server
DATA = os.urandom(300_000)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/slow"):
            self.send_response(200); self.send_header("Content-Length", str(len(DATA))); self.end_headers()
            try:
                for i in range(0, len(DATA), 10_000):
                    self.wfile.write(DATA[i:i + 10_000]); self.wfile.flush(); time.sleep(0.05)
            except OSError:
                pass
            return
        self.send_response(200); self.send_header("Content-Length", str(len(DATA))); self.end_headers(); self.wfile.write(DATA)


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr("novera.security.validate_url", lambda u: u)
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def _cfg(tmp):
    c = AppConfig(); c.downloads.directory = str(tmp / "dl"); c.downloads.retries = 0
    return c


def _store(tmp, monkeypatch):
    monkeypatch.setattr("novera.security.validate_url", lambda u: u)
    return QueueStore(HistoryStore(tmp / "h.sqlite3"))


def test_queue_persists_and_runs(tmp_path, monkeypatch, server):
    monkeypatch.setattr("novera.downloads.manager.validate_url", lambda u: u, raising=False)
    monkeypatch.setattr("novera.downloads.manager.validate_redirect", lambda a, b: b, raising=False)
    st = _store(tmp_path, monkeypatch)
    ids = [st.add(f"{server}/f{i}.bin") for i in range(4)]
    assert QueueStore(HistoryStore(tmp_path / "h.sqlite3")).list("pending").__len__() == 4  # persisted
    res = QueueRunner(_cfg(tmp_path), st).run()
    assert res == {"done": 4}, st.list()
    assert all((tmp_path / "dl" / f"f{i}.bin").read_bytes() == DATA for i in range(4))


def test_queue_pause_cancel_and_resume(tmp_path, monkeypatch, server):
    monkeypatch.setattr("novera.downloads.manager.validate_url", lambda u: u, raising=False)
    monkeypatch.setattr("novera.downloads.manager.validate_redirect", lambda a, b: b, raising=False)
    st = _store(tmp_path, monkeypatch)
    a, b = st.add(f"{server}/slow-a.bin"), st.add(f"{server}/slow-b.bin")
    r = QueueRunner(_cfg(tmp_path), st)
    t = threading.Thread(target=r.run); t.start()
    time.sleep(0.5)
    r.pause(a); r.cancel(b)
    t.join(10)
    got = {j["id"]: j["status"] for j in st.list()}
    assert got[a] == "paused" and got[b] == "cancelled"
    r.resume(a)
    assert QueueRunner(_cfg(tmp_path), st).run() == {"done": 1}
    assert (tmp_path / "dl" / "slow-a.bin").read_bytes() == DATA


def test_crashed_running_jobs_become_pending(tmp_path, monkeypatch):
    st = _store(tmp_path, monkeypatch)
    j = st.add("https://example.org/a.bin"); st.set(j, "running")
    assert QueueStore(st.h).list("pending")[0]["id"] == j


def test_bandwidth_limit_applies(tmp_path, monkeypatch, server):
    monkeypatch.setattr("novera.downloads.manager.validate_url", lambda u: u, raising=False)
    monkeypatch.setattr("novera.downloads.manager.validate_redirect", lambda a, b: b, raising=False)
    from novera.downloads import DownloadManager
    c = _cfg(tmp_path); c.downloads.bandwidth_limit_kbps = 150
    t = time.monotonic()
    DownloadManager(c).download(f"{server}/fast.bin")
    assert time.monotonic() - t >= 1.4
    ratelimit.GLOBAL.set_rate(0)


def test_git_clone_progress_and_status(tmp_path, monkeypatch):
    import shutil, subprocess
    if not shutil.which("git"):
        pytest.skip("git tidak tersedia")
    from novera import gitops
    src = tmp_path / "src"; src.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    (src / "f").write_text("x"); subprocess.run(["git", "-C", str(src), "add", "."], check=True)
    subprocess.run(["git", "-C", str(src), "commit", "-qm", "m"], check=True, env=env)
    assert "##" in gitops.status(src)
    with pytest.raises(ValueError):
        gitops.status(tmp_path)
    with pytest.raises(ValueError):
        gitops.clone("https://example.org/r.git?token=x", tmp_path / "c")
