"""Small rotating logger with URL query redaction and private log-file permissions."""
from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_TOKEN = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_\-]{16,})")
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def default_log_path() -> Path:
    configured = os.environ.get("NOVERA_LOG_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "novera" / "novera.log"


def redact_text(text: str) -> str:
    """Remove query values from URLs embedded in diagnostic strings."""
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        suffix = ""
        while raw and raw[-1] in ".,;:)]}":
            suffix = raw[-1] + suffix
            raw = raw[:-1]
        try:
            parts = urlsplit(raw)
            safe = urlunsplit((parts.scheme, parts.netloc, parts.path, "[redacted]" if parts.query else "", ""))
        except ValueError:
            safe = "[redacted-url]"
        return safe + suffix
    out = _URL_PATTERN.sub(replace, str(text))
    return _TOKEN.sub("[redacted-token]", out)


def get_logger(path: Path | None = None) -> logging.Logger:
    """Return configured logger. File logging is best-effort and never blocks work."""
    target = (path or default_log_path()).expanduser()
    logger = logging.getLogger("novera")
    if getattr(logger, "_novera_log_path", None) == str(target) and logger.handlers:
        return logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            target.parent.chmod(0o700)
        except OSError:
            pass
        handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        try:
            target.chmod(0o600)
        except OSError:
            pass
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    setattr(logger, "_novera_log_path", str(target))
    return logger


def reset_logger() -> None:
    logger = logging.getLogger("novera")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    if hasattr(logger, "_novera_log_path"):
        delattr(logger, "_novera_log_path")
