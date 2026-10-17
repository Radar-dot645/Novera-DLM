"""Modular startup: dependencies -> API/.env -> system check -> queue -> (menu by caller)."""
from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass, field

from . import devplan, envfile
from .config import AppConfig


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class StartupReport:
    stages: list[StageResult] = field(default_factory=list)
    missing_deps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    queue_pending: int = 0


def stage_dependencies(rep: StartupReport, cfg: AppConfig) -> StageResult:
    rep.missing_deps = devplan.missing_python_deps()
    return StageResult("Dependency", not rep.missing_deps, "lengkap" if not rep.missing_deps else "hilang: " + ", ".join(rep.missing_deps))


def stage_api(rep: StartupReport, cfg: AppConfig) -> StageResult:
    loaded, warns = envfile.load_env()
    rep.warnings += warns
    return StageResult("API/.env", True, f"token dimuat: {', '.join(loaded)}" if loaded else "tanpa token (fitur publik tetap aktif)")


def stage_system(rep: StartupReport, cfg: AppConfig) -> StageResult:
    ok = sys.version_info >= (3, 11)
    return StageResult("System", ok, f"Python {platform.python_version()} · {platform.system()}/{platform.machine()}")


def stage_queue(rep: StartupReport, cfg: AppConfig) -> StageResult:
    from .queue import QueueStore
    try:
        rep.queue_pending = len(QueueStore().list("pending"))
    except Exception as exc:  # noqa: BLE001
        return StageResult("Queue", False, str(exc)[:80])
    return StageResult("Queue", True, f"{rep.queue_pending} antrean tertunda")


STAGES = (stage_dependencies, stage_api, stage_system, stage_queue)


def run_startup(cfg: AppConfig, console=None, *, seconds: float = 4.0, animate: bool = True) -> StartupReport:
    """Run stages in order; with animate, show a Rich spinner and pad total time to `seconds`."""
    rep = StartupReport()
    t0 = time.monotonic()
    per = seconds / len(STAGES) if animate and seconds > 0 else 0
    status = console.status("") if (console and animate and console.is_terminal) else None
    if status:
        status.start()
    try:
        for fn in STAGES:
            label = fn.__name__.replace("stage_", "").upper()
            if status:
                status.update(f"[bold #A6DCE0]{label}[/] [dim]memeriksa…[/dim]")
            s = time.monotonic()
            res = fn(rep, cfg)
            rep.stages.append(res)
            if per:
                time.sleep(max(0.0, per - (time.monotonic() - s)))
    finally:
        if status:
            status.stop()
    rep.elapsed = time.monotonic() - t0  # type: ignore[attr-defined]
    return rep


def build_steps(rep: StartupReport, cfg: AppConfig):
    """Startup stages as (label, callable) for the cinematic entrance; real work, real results."""
    labels = {"stage_dependencies": "Dependency", "stage_api": "API/.env", "stage_system": "System", "stage_queue": "Queue"}

    def wrap(fn):
        def run():
            res = fn(rep, cfg)
            rep.stages.append(res)
            return res
        return run
    return [(labels[f.__name__], wrap(f)) for f in STAGES]
