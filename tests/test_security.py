from pathlib import Path
import pytest
from novera.security import SecurityError, resolve_download_path, sanitize_filename, validate_redirect, validate_url

@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/file", "javascript:alert(1)", "https://user:pass@example.com/a", "", "https:///missing-host"])
def test_rejects_unsafe_urls(url):
    with pytest.raises(SecurityError):
        validate_url(url)

def test_valid_http_url_and_removes_fragment():
    assert validate_url("https://example.org/a.zip#section") == "https://example.org/a.zip"

def test_https_downgrade_redirect_rejected():
    with pytest.raises(SecurityError, match="downgrade"):
        validate_redirect("https://example.org/file", "http://example.org/file")

def test_sanitizes_traversal_filename():
    name = sanitize_filename("../../outside.txt")
    assert "/" not in name and name not in {".", ".."}

def test_path_stays_inside_directory(tmp_path):
    path = resolve_download_path(tmp_path, "../../outside.txt")
    assert path.parent == tmp_path.resolve()


def test_clone_url_query_credentials_rejected(tmp_path):
    from novera.backends.external import clone_repository
    with pytest.raises(ValueError, match="query parameter"):
        clone_repository("https://github.com/o/r.git?token=secret", tmp_path / "repo")
