
from __future__ import annotations

import pytest

from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from novera.discovery.engine import Asset
from novera import menu
from novera.ui import show_menu
from novera.ui import clear_screen, show_assets


def test_long_asset_names_wrap_and_sensitive_query_is_not_shown():
    output = StringIO()
    console = Console(file=output, width=42, height=24, force_terminal=True,
                      color_system=None, soft_wrap=False, highlight=False)
    asset = Asset(
        name="Novera DLM universal arm64-v8a release build apk package.apk",
        url="https://example.org/releases/Novera-DLM.apk?token=SUPER_SECRET_TOKEN",
        source="Test Release Source", version="v123.456.789", size_bytes=987654,
        architecture="arm64-v8a", kind="apk",
    )
    show_assets(console, [asset])
    rendered = " ".join(output.getvalue().split())
    assert "Novera DLM universal arm64-v8a release build apk package.apk" in rendered
    assert "v123.456.789" in rendered
    assert "Test Release Source" in rendered
    assert "SUPER_SECRET_TOKEN" not in rendered


def test_clear_screen_runs_system_clear_only_on_tty(monkeypatch):
    from novera import visual
    calls = []
    monkeypatch.setattr(visual.subprocess, "run", lambda *a, **k: calls.append(a[0]) or SimpleNamespace(returncode=0))
    visual.clear_screen(SimpleNamespace(is_terminal=True))
    assert calls == ["clear"]
    visual.clear_screen(SimpleNamespace(is_terminal=False))
    assert calls == ["clear"]


def test_clear_screen_falls_back_to_ansi(monkeypatch, capsys):
    from novera import visual
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(visual.subprocess, "run", boom)
    visual.clear_screen(SimpleNamespace(is_terminal=True))
    assert "\x1b[H\x1b[2J\x1b[3J" in capsys.readouterr().out


@pytest.mark.parametrize("h", [10, 14, 24, 40])
def test_menu_never_exceeds_terminal_height(h):
    out = StringIO()
    console = Console(file=out, width=40, height=h, force_terminal=True, color_system=None, highlight=False)
    for sel in (0, 6, 13):
        out.truncate(0); out.seek(0)
        show_menu(console, sel)
        assert len(out.getvalue().splitlines()) <= h - 1, (h, sel)


def test_cinematic_runs_steps_in_order(monkeypatch):
    from novera import visual
    monkeypatch.setattr(visual, "clear_screen", lambda c: None)
    out = StringIO()
    console = Console(file=out, width=80, height=30, force_terminal=True, color_system=None, highlight=False)
    order = []
    steps = [(f"S{i}", (lambda i=i: order.append(i) or SimpleNamespace(ok=True, detail=f"d{i}"))) for i in range(4)]
    res = visual.cinematic(console, "1.5.2", steps, seconds=0.8)
    assert order == [0, 1, 2, 3] and len(res) == 4
    assert "modul 4/4" in out.getvalue()


def test_asset_picker_paginates_and_can_select_asset_on_second_page(monkeypatch):
    output = StringIO()
    console = Console(file=output, width=50, height=21, force_terminal=True,
                      color_system=None, soft_wrap=False, highlight=False)
    assets = [
        Asset(f"release-{i}-long-universal-arm64-v8a.apk", f"https://example.org/{i}.apk", "test", str(i), 100, "arm64-v8a", "apk")
        for i in range(1, 26)
    ]
    answers = iter(["n", "23"])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *args, **kwargs: next(answers))
    selected = menu._select_asset(console, assets)
    assert selected is assets[22]
    rendered = output.getvalue()
    assert "Halaman 1/2" in rendered and "Halaman 2/2" in rendered
    assert "release-23-long-universal-arm64-v8a.apk" in rendered


def test_menu_items_wrap_on_narrow_terminal():
    from novera.ui import show_menu
    output = StringIO()
    console = Console(file=output, width=38, height=24, force_terminal=True,
                      color_system=None, soft_wrap=False, highlight=False)
    show_menu(console)
    import re
    rendered = " ".join(re.sub(r"[│╭╮╰╯─]", " ", output.getvalue()).split())
    assert "NOVERA DLM" in rendered
    assert "Verify SHA-256" in rendered
    assert "Exit" in rendered


def test_remote_metadata_control_characters_cannot_inject_terminal_sequences():
    output = StringIO()
    console = Console(file=output, width=50, height=24, force_terminal=True,
                      color_system=None, soft_wrap=False, highlight=False)
    asset = Asset(
        name="good-name.apk\x1b[2J\nFAKE SCREEN",
        url="https://example.org/good-name.apk?token=secret",
        source="public repo", version="v1", size_bytes=10, kind="apk",
    )
    show_assets(console, [asset])
    rendered = output.getvalue()
    assert "\x1b" not in rendered
    assert "FAKE SCREEN" in rendered
    assert "secret" not in rendered
