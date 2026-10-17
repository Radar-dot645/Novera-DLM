"""URL-based public asset discovery for GitHub, GitLab, and ordinary web pages."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from ..security import SecurityError, validate_url


class DiscoveryError(RuntimeError):
    pass


@dataclass
class Asset:
    name: str
    url: str
    source: str
    version: str | None = None
    size_bytes: int | None = None
    architecture: str | None = None
    kind: str = "file"
    notes: str = ""


def classify_asset(name: str) -> str:
    """Distinguish standalone APK files from split-package containers."""
    lower = name.lower()
    if lower.endswith(".apk"):
        return "apk"
    if lower.endswith((".apks", ".xapk", ".apkm")):
        return "split-package archive"
    return "asset"


def guess_architecture(name: str) -> str | None:
    value = name.lower()
    if "arm64-v8a" in value or "arm64_v8a" in value:
        return "arm64-v8a"
    if "armeabi-v7a" in value or "armeabi_v7a" in value:
        return "armeabi-v7a"
    if "x86_64" in value or "x86-64" in value:
        return "x86_64"
    if "x86" in value:
        return "x86"
    if "universal" in value or "universal.apk" in value:
        return "universal"
    return None


class _Links(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            values = dict(attrs)
            self._href = values.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            label = " ".join(" ".join(self._text).split())
            self.links.append((urljoin(self.base_url, self._href), label))
            self._href = None
            self._text = []


def recommended_method(asset: Asset) -> str:
    """Return a conservative, source-aware download-method recommendation."""
    if asset.kind == "source archive":
        return "HTTP archive (Git clone untuk repo lengkap)"
    if asset.size_bytes is not None and asset.size_bytes >= 100 * 1024 * 1024:
        return "Auto (cek HTTPS + Range; aria2 opsional)"
    return "Auto (Python HTTP default)"


def _request_headers(source: str) -> dict[str, str]:
    headers = {"User-Agent": "NoveraDLM/1.5.2", "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    if source == "github" and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    if source == "gitlab" and os.environ.get("GITLAB_TOKEN"):
        headers["PRIVATE-TOKEN"] = os.environ["GITLAB_TOKEN"]
    return headers


def _api_json(url: str, source: str) -> dict | list:
    try:
        response = httpx.get(url, headers=_request_headers(source), timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DiscoveryError(f"Tidak bisa membaca API {source}: {exc}") from exc


# Bound paginated discovery so a single URL cannot trigger an unbounded API crawl.
_API_PAGE_SIZE = 100
_MAX_API_PAGES = 10


def _api_list_pages(api_url: str, source: str) -> tuple[list[dict], bool]:
    """Fetch public API list pages, returning rows and whether the cap was reached."""
    rows: list[dict] = []
    hit_cap = False
    for page in range(1, _MAX_API_PAGES + 1):
        separator = "&" if "?" in api_url else "?"
        data = _api_json(f"{api_url}{separator}per_page={_API_PAGE_SIZE}&page={page}", source)
        if not isinstance(data, list):
            raise DiscoveryError(f"API {source} mengembalikan format daftar yang tidak valid.")
        page_rows = [row for row in data if isinstance(row, dict)]
        rows.extend(page_rows)
        if len(data) < _API_PAGE_SIZE:
            return rows, False
    hit_cap = True
    return rows, hit_cap


def _github_release_to_assets(releases: list[dict], owner: str, repo: str, *, hit_cap: bool = False) -> list[Asset]:
    assets: list[Asset] = []
    for release in releases:
        version = str(release.get("tag_name") or release.get("name") or "unknown")
        rows = release.get("assets", [])
        release_assets: list[Asset] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get("browser_download_url"):
                continue
            name = str(row.get("name") or "asset")
            release_assets.append(Asset(
                name=name,
                url=str(row["browser_download_url"]),
                source="GitHub Releases",
                version=version,
                size_bytes=row.get("size") if isinstance(row.get("size"), int) else None,
                architecture=guess_architecture(name),
                kind=classify_asset(name),
            ))
        # Releases without uploaded binaries still offer source archives.
        # Expose those so older releases remain useful and selectable.
        if not release_assets and release.get("tag_name"):
            tag = str(release["tag_name"])
            archive_url = f"https://github.com/{quote(owner)}/{quote(repo)}/archive/refs/tags/{quote(tag, safe='')}.zip"
            release_assets.append(Asset(
                name=f"{repo}-{tag}-source.zip",
                url=archive_url,
                source="GitHub source archive",
                version=version,
                size_bytes=None,
                architecture=None,
                kind="source archive",
                notes="Rilis ini tidak memiliki binary asset yang diunggah; ini arsip source code.",
            ))
        assets.extend(release_assets)
    if hit_cap and assets:
        assets[-1].notes = (assets[-1].notes + " " if assets[-1].notes else "") +             f"Daftar release dibatasi pada {_API_PAGE_SIZE * _MAX_API_PAGES} release untuk membatasi permintaan API."
    return assets


def _github_assets(url: str) -> list[Asset] | None:
    parts = urlsplit(url)
    if parts.hostname not in {"github.com", "www.github.com"}:
        return None
    path = [unquote(p) for p in parts.path.strip("/").split("/") if p]
    if len(path) < 2:
        return None
    if len(path) >= 6 and path[2] == "releases" and path[3] == "download":
        name = path[-1]
        return [Asset(name, url, "GitHub Release Asset URL", path[4], None, guess_architecture(name), classify_asset(name))]
    owner, repo = path[0], path[1].removesuffix(".git")
    repo_api = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}"
    if len(path) >= 3 and path[2] == "tags":
        data = _api_json(repo_api + "/tags?per_page=30", "github")
        if not isinstance(data, list):
            return []
        results: list[Asset] = []
        for row in data:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            tag = str(row["name"])
            archive_url = f"https://github.com/{quote(owner)}/{quote(repo)}/archive/refs/tags/{quote(tag, safe='')}.zip"
            results.append(Asset(f"{repo}-{tag}.zip (source archive)", archive_url, "GitHub Tag", tag, None, None, "source archive"))
        return results

    if len(path) >= 4 and path[2] == "releases" and path[3] == "tag" and len(path) >= 5:
        # A specific release page should return assets for that release only.
        api = repo_api + "/releases/tags/" + quote(path[4], safe="")
        data = _api_json(api, "github")
        if not isinstance(data, dict):
            return []
        return _github_release_to_assets([data], owner, repo)

    if len(path) >= 4 and path[2] == "releases" and path[3] == "latest":
        data = _api_json(repo_api + "/releases/latest", "github")
        if not isinstance(data, dict):
            return []
        return _github_release_to_assets([data], owner, repo)

    if len(path) == 3 and path[2] == "releases":
        # `owner/repo/releases` means the entire release list, not just latest.
        releases, hit_cap = _api_list_pages(repo_api + "/releases", "github")
        return _github_release_to_assets(releases, owner, repo, hit_cap=hit_cap)

    # A repository URL defaults to the latest release for concise behavior.
    data = _api_json(repo_api + "/releases/latest", "github")
    if not isinstance(data, dict):
        return []
    return _github_release_to_assets([data], owner, repo)


def _gitlab_assets(url: str) -> list[Asset] | None:
    parts = urlsplit(url)
    if parts.hostname not in {"gitlab.com", "www.gitlab.com"}:
        return None
    path = [unquote(p) for p in parts.path.strip("/").split("/") if p]
    if len(path) < 2:
        return None
    # Projects can have nested groups. The `/-/` segment marks GitLab UI routes.
    marker = path.index("-") if "-" in path else len(path)
    project_path = path[:marker]
    tag_mode = marker + 1 < len(path) and path[marker + 1] == "tags"
    encoded = quote("/".join(project_path), safe="")
    if tag_mode:
        data = _api_json(f"https://gitlab.com/api/v4/projects/{encoded}/repository/tags?per_page=30", "gitlab")
        if not isinstance(data, list):
            return []
        return [Asset(f"{project_path[-1]}-{row['name']}.zip (source archive)",
                      f"https://gitlab.com/api/v4/projects/{encoded}/repository/archive.zip?sha={quote(str(row['name']), safe='')}",
                      "GitLab Tag", str(row["name"]), None, None, "source archive")
                for row in data if isinstance(row, dict) and row.get("name")]
    api = f"https://gitlab.com/api/v4/projects/{encoded}/releases"
    data, hit_cap = _api_list_pages(api, "gitlab")
    assets: list[Asset] = []
    for release in data:
        version = str(release.get("tag_name") or release.get("name") or "unknown")
        links = (release.get("assets") or {}).get("links", [])
        for row in links if isinstance(links, list) else []:
            if not isinstance(row, dict) or not row.get("direct_asset_url") and not row.get("url"):
                continue
            name = str(row.get("name") or unquote(urlsplit(str(row.get("url", ""))).path.split("/")[-1]) or "asset")
            asset_url = str(row.get("direct_asset_url") or row.get("url"))
            assets.append(Asset(name, asset_url, "GitLab Releases", version, None,
                                guess_architecture(name), classify_asset(name)))
    if hit_cap and assets:
        assets[-1].notes = f"Daftar release dibatasi pada {_API_PAGE_SIZE * _MAX_API_PAGES} release untuk membatasi permintaan API."
    return assets


def _fdroid_app_assets(url: str) -> list[Asset] | None:
    """Discover APK links on an F-Droid app page and enrich visible metadata.

    The per-app API is used for display metadata only; it is not treated as a
    trusted download or signature-verification source. The actual download URLs
    come from the public app page and still use the normal download security path.
    """
    parts = urlsplit(url)
    if parts.hostname not in {"f-droid.org", "www.f-droid.org"}:
        return None
    path = [unquote(p) for p in parts.path.strip("/").split("/") if p]
    if len(path) < 2 or path[0] != "packages":
        return None
    package_id = path[1]
    if not all(ch.isalnum() or ch in "._" for ch in package_id):
        raise DiscoveryError("Application ID F-Droid tidak valid.")
    app_assets = _web_assets(url)
    app_assets = [asset for asset in app_assets if asset.kind == "apk"]
    if not app_assets:
        return []
    version_by_code: dict[str, str] = {}
    suggested_code: str | None = None
    try:
        metadata = _api_json(f"https://f-droid.org/api/v1/packages/{quote(package_id, safe='')}", "fdroid")
        if isinstance(metadata, dict):
            if metadata.get("suggestedVersionCode") is not None:
                suggested_code = str(metadata.get("suggestedVersionCode"))
            for item in metadata.get("packages", []) if isinstance(metadata.get("packages"), list) else []:
                if isinstance(item, dict) and item.get("versionCode") is not None and item.get("versionName"):
                    version_by_code[str(item["versionCode"])] = str(item["versionName"])
    except DiscoveryError:
        # An outage/rate limit on the metadata API does not block manual APK links.
        pass
    for asset in app_assets:
        asset.source = "F-Droid repository"
        match = re.search(r"_(\d+)\.apk$", asset.name, re.I)
        code = match.group(1) if match else suggested_code
        if code and code in version_by_code:
            asset.version = f"{version_by_code[code]} ({code})"
        elif code:
            asset.version = code
        asset.notes = "Version metadata is informational only; the APK signature is not verified by Novera."
    return app_assets


def _web_assets(url: str) -> list[Asset]:
    try:
        with httpx.Client(timeout=20, follow_redirects=False, headers=_request_headers("web")) as client:
            current = url
            for _ in range(11):
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise DiscoveryError("Redirect tanpa Location.")
                        from ..security import validate_redirect
                        current = validate_redirect(current, urljoin(current, location))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type and "xml" not in content_type:
                        filename = unquote(urlsplit(current).path.split("/")[-1]) or "download.bin"
                        size = int(response.headers["content-length"]) if response.headers.get("content-length", "").isdigit() else None
                        return [Asset(filename, current, "Direct URL", None, size, guess_architecture(filename), classify_asset(filename))]
                    body = response.read()
                    html_text = body.decode(response.encoding or "utf-8", errors="replace")
                    parser = _Links(current)
                    parser.feed(html_text)
                    valid: list[Asset] = []
                    extensions = (".apk", ".zip", ".tar", ".gz", ".xz", ".7z", ".jar", ".deb", ".rpm", ".whl", ".py", ".bin", ".iso", ".exe", ".msi", ".dmg")
                    seen: set[str] = set()
                    for link, label in parser.links:
                        try:
                            safe_link = validate_url(link)
                        except SecurityError:
                            continue
                        name = unquote(urlsplit(safe_link).path.split("/")[-1])
                        if not name or safe_link in seen:
                            continue
                        if not name.lower().endswith(extensions) and not any(word in (label + " " + name).lower() for word in ("download", "apk", "release asset")):
                            continue
                        seen.add(safe_link)
                        valid.append(Asset(name, safe_link, "Web page", None, None, guess_architecture(name), classify_asset(name)))
                    return valid
            raise DiscoveryError("Batas redirect tercapai.")
    except DiscoveryError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise DiscoveryError(f"Gagal memeriksa URL: {exc}") from exc


def discover_url(target: str) -> list[Asset]:
    """Discover assets from a URL or describe a direct downloadable URL.

    This intentionally does not perform internet-wide search. For a query rather
    than a URL, the caller should explain that a direct/source-specific URL is
    required.
    """
    url = validate_url(target)
    host = urlsplit(url).hostname or ""
    if host.endswith("github.com"):
        assets = _github_assets(url)
        if assets is not None:
            return assets
    if host.endswith("gitlab.com"):
        assets = _gitlab_assets(url)
        if assets is not None:
            return assets
    if host in {"f-droid.org", "www.f-droid.org"}:
        assets = _fdroid_app_assets(url)
        if assets is not None:
            return assets
    return _web_assets(url)
