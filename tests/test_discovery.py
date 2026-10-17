from __future__ import annotations
from novera.discovery import discover_url, guess_architecture
from novera.discovery import engine


def test_guess_apk_architecture():
    assert guess_architecture("app-arm64-v8a.apk") == "arm64-v8a"
    assert guess_architecture("app-armeabi-v7a.apk") == "armeabi-v7a"
    assert guess_architecture("app-universal.apk") == "universal"
    assert guess_architecture("app.apk") is None


def test_github_assets_api_parser(monkeypatch):
    def fake_api(url, source):
        assert "api.github.com/repos/o/r" in url
        assert source == "github"
        return {"tag_name": "v2.0", "assets": [{"name": "app-universal.apk", "size": 1234, "browser_download_url": "https://github.com/o/r/releases/download/v2.0/app-universal.apk"}]}
    monkeypatch.setattr(engine, "_api_json", fake_api)
    items = discover_url("https://github.com/o/r/releases/latest")
    assert len(items) == 1
    assert items[0].version == "v2.0"
    assert items[0].architecture == "universal"
    assert items[0].size_bytes == 1234


def test_direct_github_asset_does_not_call_api(monkeypatch):
    monkeypatch.setattr(engine, "_api_json", lambda *args: (_ for _ in ()).throw(AssertionError("API not expected")))
    result = discover_url("https://github.com/o/r/releases/download/v1/app.apk")
    assert result[0].name == "app.apk"
    assert result[0].version == "v1"


def test_html_link_discovery(server):
    assets = discover_url(server + "/page")
    names = {a.name for a in assets}
    assert "app-universal.apk" in names
    assert "archive.zip" in names
    assert all("javascript" not in a.url for a in assets)


def test_direct_url_discovery_does_not_buffer_file(server):
    assets = discover_url(server + "/file.apk")
    assert len(assets) == 1
    assert assets[0].name == "file.apk"
    assert assets[0].size_bytes is not None

# Discovery-focused tiny HTTP fixture; responses are intentionally local-only.
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest


@pytest.fixture()
def server():
    class WebHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_HEAD(self):
            path = self.path.split("?", 1)[0]
            body = b"APK bytes" if path.endswith(".apk") else b""
            self.send_response(200); self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", "application/octet-stream"); self.end_headers()
        def do_GET(self):
            if self.path == "/page":
                body = b'<html><a href="/app-universal.apk">Universal APK</a><a href="/archive.zip">Archive</a><a href="javascript:bad()">bad</a></html>'
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path.endswith(".apk"):
                body = b"APK bytes"
                self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown(); thread.join(timeout=2); httpd.server_close()


def test_github_tag_source_archives(monkeypatch):
    def fake_api(url, source):
        assert url.endswith("/tags?per_page=30")
        return [{"name": "v1.2"}, {"name": "release/with-slash"}]
    monkeypatch.setattr(engine, "_api_json", fake_api)
    items = discover_url("https://github.com/o/r/tags")
    assert len(items) == 2
    assert items[0].kind == "source archive"
    assert items[0].version == "v1.2"


def test_split_package_is_not_mislabeled_apk():
    from novera.discovery import classify_asset
    assert classify_asset("bundle.apks") == "split-package archive"
    assert classify_asset("bundle.xapk") == "split-package archive"
    assert classify_asset("standalone.apk") == "apk"


def test_gitlab_release_assets_api_parser(monkeypatch):
    def fake_api(url, source):
        assert "/api/v4/projects/group%2Fproject/releases" in url
        assert source == "gitlab"
        return [{"tag_name": "v3", "assets": {"links": [{"name": "client-x86_64.apk", "url": "https://example.org/client-x86_64.apk"}]}}]
    monkeypatch.setattr(engine, "_api_json", fake_api)
    items = discover_url("https://gitlab.com/group/project/-/releases")
    assert items[0].version == "v3"
    assert items[0].architecture == "x86_64"
    assert items[0].kind == "apk"


def test_fdroid_app_metadata_enriches_official_apk_links(monkeypatch):
    from novera.discovery.engine import Asset
    monkeypatch.setattr(engine, "_web_assets", lambda url: [
        Asset("org.example.app_420.apk", "https://f-droid.org/repo/org.example.app_420.apk", "Web page", None, 123, "unspecified", "apk")
    ])
    def fake_api(url, source):
        assert url == "https://f-droid.org/api/v1/packages/org.example.app"
        assert source == "fdroid"
        return {"packageName": "org.example.app", "suggestedVersionCode": 420,
                "packages": [{"versionName": "4.2.0", "versionCode": 420}]}
    monkeypatch.setattr(engine, "_api_json", fake_api)
    assets = discover_url("https://f-droid.org/packages/org.example.app/")
    assert assets[0].source == "F-Droid repository"
    assert assets[0].version == "4.2.0 (420)"
    assert "not verified" in assets[0].notes


def test_github_releases_page_lists_assets_across_all_release_pages(monkeypatch):
    calls = []
    def fake_api(url, source):
        calls.append(url)
        assert source == "github"
        if url.endswith("&page=1"):
            return [
                {"tag_name": f"v{i}", "assets": [{
                    "name": f"tool-v{i}-arm64-v8a.apk", "size": i * 100,
                    "browser_download_url": f"https://github.com/o/r/releases/download/v{i}/tool-v{i}-arm64-v8a.apk",
                }]} for i in range(100, 0, -1)
            ]
        if url.endswith("&page=2"):
            return [{"tag_name": "v0", "assets": [{
                "name": "old-release.zip", "size": 77,
                "browser_download_url": "https://github.com/o/r/releases/download/v0/old-release.zip",
            }]}]
        return []
    monkeypatch.setattr(engine, "_api_json", fake_api)
    items = discover_url("https://github.com/o/r/releases")
    assert len(items) == 101
    assert items[0].version == "v100"
    assert items[-1].version == "v0"
    assert len(calls) == 2
    assert all("/releases/latest" not in call for call in calls)


def test_github_release_without_uploaded_assets_offers_source_archive(monkeypatch):
    monkeypatch.setattr(engine, "_api_json", lambda *args: {"tag_name": "v1", "assets": []})
    items = discover_url("https://github.com/o/r/releases/tag/v1")
    assert len(items) == 1
    assert items[0].kind == "source archive"
    assert items[0].version == "v1"
    assert "source code" in items[0].notes
