"""Drive every menu flow end-to-end with stubbed prompts so NameError/TypeError regressions are caught."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO

import pytest
from rich.console import Console

from novera import menu
from novera.config import AppConfig
from novera.discovery import Asset


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "5"); self.end_headers(); self.wfile.write(b"hello")


@pytest.fixture
def env(tmp_path, monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for mod in ("novera.downloads.manager", "novera.security"):
        monkeypatch.setattr(mod + ".validate_url", lambda u: u, raising=False)
    monkeypatch.setattr("novera.downloads.manager.validate_redirect", lambda a, b: b, raising=False)
    monkeypatch.setattr(menu, "validate_url", lambda u: u)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = AppConfig(); cfg.downloads.directory = str(tmp_path / "dl")
    out = StringIO()
    console = Console(file=out, width=80, height=40, force_terminal=True, color_system=None, highlight=False)
    yield f"http://127.0.0.1:{srv.server_port}", cfg, console, out, tmp_path
    srv.shutdown()


def _answers(monkeypatch, values):
    it = iter(values)
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(it))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: False)


def test_download_flow_shows_progress_and_completes(env, monkeypatch):
    url, cfg, console, out, tmp = env
    _answers(monkeypatch, ["", "", "python"])
    menu._download_flow(console, cfg, url + "/f.bin")
    assert "Download selesai" in out.getvalue() and (tmp / "dl" / "f.bin").read_bytes() == b"hello"


def test_batch_flow(env, monkeypatch):
    url, cfg, console, out, tmp = env
    lst = tmp / "u.txt"; lst.write_text(f"{url}/a.bin\n{url}/b.bin\n")
    menu._batch_flow(console, cfg, str(lst))
    assert "DONE" in out.getvalue() and (tmp / "dl" / "b.bin").exists()


def test_discover_flow_lists_and_picks(env, monkeypatch):
    url, cfg, console, out, tmp = env
    assets = [Asset("app-arm64-v8a.apk", f"{url}/app.apk", "t", "1", 5, "arm64-v8a", "apk")]
    monkeypatch.setattr(menu, "discover_url", lambda u: assets)
    monkeypatch.setattr(menu, "load_config", lambda: cfg)
    _answers(monkeypatch, ["1", "", "", "python"])
    menu._discover_flow(console, "https://github.com/o/r/releases")
    assert (tmp / "dl" / "app.apk").exists()


def test_verify_extract_plan_gitstatus_queue_flows(env, monkeypatch):
    import hashlib, zipfile
    url, cfg, console, out, tmp = env
    f = tmp / "x.bin"; f.write_bytes(b"abc")
    _answers(monkeypatch, [])
    menu._verify_flow(console, str(f), hashlib.sha256(b"abc").hexdigest())
    assert "COCOK" in out.getvalue()
    z = tmp / "a.zip"
    with zipfile.ZipFile(z, "w") as zf: zf.writestr("d/x.txt", "1")
    menu._extract_flow(console, str(z), str(tmp / "o"))
    assert (tmp / "o/d/x.txt").exists()
    (tmp / "Makefile").write_text("all:\n")
    menu._plan_flow(console, str(tmp))
    assert "make" in out.getvalue()
    menu._gitstatus_flow(console, str(tmp))
    _answers(monkeypatch, [f"a {url}/q.bin", "r", "q"])
    menu._queue_flow(console, cfg)
    assert (tmp / "dl" / "q.bin").exists()
    menu._doctor_flow(console); menu._history_flow(console); menu._config_flow(console)


def test_all_menu_handlers_resolve():
    import ast, inspect
    src = inspect.getsource(menu.run_menu)
    names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name) and n.id.startswith("_")}
    assert all(hasattr(menu, n) for n in names), [n for n in names if not hasattr(menu, n)]
