from pathlib import Path
import pytest
from novera.config import AppConfig, default_config_path, load_config, write_default_config
from novera.history import HistoryStore


def test_default_config_values():
    cfg = AppConfig()
    assert cfg.downloads.concurrency == 3
    assert cfg.ui.cinematic_seconds == 4.0
    assert cfg.downloads.overwrite_policy == "rename"


def test_write_and_read_config(tmp_path):
    path = tmp_path / "config.toml"
    write_default_config(path)
    cfg = load_config(path)
    assert cfg.downloads.concurrency == 3
    assert cfg.downloads.directory == "~/storage/downloads/Novera"
    assert path.exists()


def test_invalid_config_raises(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("[broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Tidak bisa membaca konfigurasi"):
        load_config(path)


def test_history_add_list_clear(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    item_id = store.add(url="https://example.org/a.zip", destination="/tmp/a.zip", size_bytes=12, status="completed")
    assert item_id > 0
    assert store.list()[0]["size_bytes"] == 12
    assert store.clear() == 1
    assert store.list() == []


def test_rotating_log_redacts_query_and_uses_private_permissions(tmp_path):
    import logging
    import os
    from novera.logging_utils import get_logger, redact_text, reset_logger

    target = tmp_path / "private" / "novera.log"
    logger = get_logger(target)
    try:
        logger.warning("failed URL %s", redact_text("https://example.test/file.apk?token=supersecret"))
        for handler in logger.handlers:
            handler.flush()
        content = target.read_text(encoding="utf-8")
        assert "supersecret" not in content
        assert "[redacted]" in content
        if os.name == "posix":
            assert target.stat().st_mode & 0o077 == 0
            assert target.parent.stat().st_mode & 0o077 == 0
    finally:
        reset_logger()
