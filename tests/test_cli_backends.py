import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from novera.backends import choose_backend
from novera.config import AppConfig
from novera.doctor import diagnostics


def test_manual_missing_backend_does_not_silently_fallback(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: None)
    with pytest.raises(RuntimeError, match="tidak terpasang"):
        choose_backend("curl")


def test_python_backend_choice():
    choice = choose_backend("auto", size_bytes=None, range_supported=False)
    assert choice.name == "python-http"


def test_platform_diagnostics_has_optional_tools():
    rows = diagnostics()
    names = {row[0] for row in rows}
    assert "git" in names and "aria2c" in names and "Python" in names


def test_cli_version_subprocess():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "novera", "--version"], cwd=root,
                          env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
                          text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0
    assert "Novera DLM 1.5.2" in proc.stdout


def test_interactive_menu_exit_returns_cleanly():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "novera", "--no-animation"], cwd=root,
                          env={**__import__("os").environ, "PYTHONPATH": str(root / "src"),
                               "HOME": str(root / ".test-home")},
                          input="0\n", text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0
    assert "Sampai jumpa" in proc.stdout
    assert "Exit" in proc.stdout


def test_interactive_menu_eof_at_return_prompt_exits_without_traceback():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "novera", "--no-animation"], cwd=root,
                          env={**__import__("os").environ, "PYTHONPATH": str(root / "src"),
                               "HOME": str(root / ".test-home-eof")},
                          input="7\n", text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0
    assert "Traceback" not in proc.stderr
    assert "Sampai jumpa" in proc.stdout
