"""Configuration loading and safe defaults."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DownloadConfig:
    directory: str = "~/storage/downloads/Novera"
    concurrency: int = 3
    retries: int = 3
    timeout_seconds: float = 30.0
    resume: bool = True
    overwrite_policy: str = "rename"
    bandwidth_limit_kbps: int = 0  # 0 = unlimited; global across all threads


@dataclass
class UIConfig:
    cinematic_seconds: float = 4.0
    color: bool = True


@dataclass
class NetworkConfig:
    mirrors: list[str] = field(default_factory=list)
    user_agent: str = "NoveraDLM/1.5.2"


@dataclass
class SecurityConfig:
    max_redirects: int = 10
    max_file_size_mb: int = 0


@dataclass
class AppConfig:
    downloads: DownloadConfig = field(default_factory=DownloadConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @property
    def download_path(self) -> Path:
        return Path(self.downloads.directory).expanduser()


def default_config_path() -> Path:
    override = os.environ.get("NOVERA_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "novera" / "config.toml"


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or default_config_path()
    if not cfg_path.exists():
        return AppConfig()
    try:
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Tidak bisa membaca konfigurasi {cfg_path}: {exc}") from exc
    base = AppConfig()
    d = data.get("downloads", {})
    u = data.get("ui", {})
    n = data.get("network", {})
    s = data.get("security", {})
    policy = str(d.get("overwrite_policy", base.downloads.overwrite_policy)).lower()
    if policy not in {"rename", "skip", "overwrite"}:
        policy = base.downloads.overwrite_policy
    base.downloads = DownloadConfig(
        directory=str(d.get("directory", base.downloads.directory)),
        concurrency=_bounded_int(d.get("concurrency", 3), 3, 1, 8),
        retries=_bounded_int(d.get("retries", 3), 3, 0, 8),
        timeout_seconds=max(2.0, min(300.0, float(d.get("timeout_seconds", 30.0)))),
        resume=bool(d.get("resume", True)),
        overwrite_policy=policy,
        bandwidth_limit_kbps=_bounded_int(d.get("bandwidth_limit_kbps", 0), 0, 0, 10_000_000),
    )
    base.ui = UIConfig(
        cinematic_seconds=max(0.0, min(10.0, float(u.get("cinematic_seconds", 4.0)))),
        color=bool(u.get("color", True)),
    )
    mirrors = n.get("mirrors", [])
    if not isinstance(mirrors, list):
        mirrors = []
    base.network = NetworkConfig(
        mirrors=[str(x) for x in mirrors if isinstance(x, str)],
        user_agent=str(n.get("user_agent", base.network.user_agent))[:180],
    )
    base.security = SecurityConfig(
        max_redirects=_bounded_int(s.get("max_redirects", 10), 10, 0, 20),
        max_file_size_mb=_bounded_int(s.get("max_file_size_mb", 0), 0, 0, 100_000),
    )
    return base


def write_default_config(path: Path | None = None, *, overwrite: bool = False) -> Path:
    cfg_path = path or default_config_path()
    if cfg_path.exists() and not overwrite:
        return cfg_path
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    content = '''[downloads]\ndirectory = "~/storage/downloads/Novera"\nconcurrency = 3\nretries = 3\ntimeout_seconds = 30\nresume = true\noverwrite_policy = "rename"\nbandwidth_limit_kbps = 0\n\n[ui]\ncinematic_seconds = 4\ncolor = true\n\n[network]\nmirrors = []\nuser_agent = "NoveraDLM/1.5.2"\n\n[security]\nmax_redirects = 10\nmax_file_size_mb = 0\n'''
    cfg_path.write_text(content, encoding="utf-8")
    try:
        cfg_path.chmod(0o600)
    except OSError:
        pass
    return cfg_path
