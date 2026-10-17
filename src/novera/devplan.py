"""Detect dependency/build needs and produce a plan. Nothing runs without explicit approval."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Step:
    title: str
    command: list[str]
    tool: str
    available: bool = True


@dataclass
class Plan:
    root: Path
    kinds: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_MARKERS = [
    ("requirements.txt", "Python", "pip", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]),
    ("pyproject.toml", "Python (pyproject)", "pip", [sys.executable, "-m", "pip", "install", "."]),
    ("package.json", "Node.js", "npm", ["npm", "install", "--ignore-scripts"]),
    ("Cargo.toml", "Rust", "cargo", ["cargo", "build", "--release"]),
    ("go.mod", "Go", "go", ["go", "build", "./..."]),
    ("CMakeLists.txt", "CMake", "cmake", ["cmake", "-S", ".", "-B", "build"]),
    ("Makefile", "Make", "make", ["make"]),
    ("build.gradle", "Gradle", "gradle", ["gradle", "build"]),
    ("build.gradle.kts", "Gradle", "gradle", ["gradle", "build"]),
]


def make_plan(root: Path) -> Plan:
    if not root.is_dir():
        raise ValueError(f"Bukan direktori: {root}")
    plan = Plan(root=root.resolve())
    for fname, kind, tool, cmd in _MARKERS:
        if (root / fname).is_file():
            plan.kinds.append(kind)
            plan.steps.append(Step(f"{kind}: {' '.join(cmd[:4] if cmd[0] != sys.executable else ['python'] + cmd[1:4])}",
                                   cmd, tool, shutil.which(cmd[0]) is not None or cmd[0] == sys.executable))
    if not plan.steps:
        plan.notes.append("Tidak ada berkas build yang dikenali.")
    plan.notes.append("Perintah build menjalankan kode dari repository. Tinjau berkas sebelum menyetujui.")
    return plan


def run_step(step: Step, cwd: Path, console=None) -> int:
    """Run one approved step (no shell). Indeterminate work -> Rich spinner, output captured."""
    if not step.available:
        raise RuntimeError(f"Tool '{step.tool}' tidak tersedia; pasang terlebih dahulu.")
    def go():
        return subprocess.run(step.command, cwd=cwd, capture_output=True, text=True, timeout=3600)
    if console:
        with console.status(f"[cyan]Menjalankan: {step.title}[/cyan]"):
            r = go()
    else:
        r = go()
    if r.returncode != 0 and console:
        console.print((r.stderr or r.stdout)[-800:])
    return r.returncode


def missing_python_deps() -> list[str]:
    return [m for m in ("rich", "httpx") if importlib.util.find_spec(m) is None]


def install_python_deps(packages: list[str], console=None) -> int:
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    if console:
        with console.status("[cyan]pip install…[/cyan]"):
            return subprocess.run(cmd, capture_output=True).returncode
    return subprocess.run(cmd).returncode
