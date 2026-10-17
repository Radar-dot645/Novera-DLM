"""Rich-based terminal UI, including a short cinematic entrance."""
from __future__ import annotations

import os
import sys
import time
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.table import Column, Table
from rich.text import Text
from urllib.parse import urlsplit

from .visual import (DIM, INK, MENU_ITEMS, MUTED, clear_screen, cinematic, header, pick_menu, screen_header,  # noqa: F401
                     show_menu, static_logo)

CYAN = "#22D3EE"


def make_console() -> Console:
    no_color = os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()
    return Console(highlight=False, color_system=None if no_color else "truecolor", soft_wrap=False)


def render_logo(console: Console, version: str) -> None:
    static_logo(console, version)


def print_banner(console: Console, version: str) -> None:
    render_logo(console, version)



def _safe_display(value: object) -> str:
    """Flatten control characters from remote metadata before terminal display."""
    printable = "".join(char if char.isprintable() else " " for char in str(value))
    return " ".join(printable.split())


def show_assets(console: Console, assets, *, start_index: int = 1, title: str = "DISCOVERED ASSETS") -> None:
    """Render assets in one flexible column so long names are wrapped, never clipped.

    URL query strings are omitted from display because they may contain temporary
    signed-download tokens; the original URL remains available to the downloader.
    """
    if not assets:
        console.print("[yellow]Tidak ada aset yang terdeteksi.[/yellow] Coba URL aset langsung atau gunakan menu Download URL.")
        return

    from .discovery.engine import recommended_method

    table = Table(box=box.SIMPLE_HEAVY, header_style=f"bold {CYAN}", expand=True, show_lines=True, pad_edge=False)
    table.add_column("#", width=4, justify="right", no_wrap=True)
    table.add_column("Detail aset", ratio=1, overflow="fold", no_wrap=False)
    for offset, asset in enumerate(assets):
        detail = Text()
        detail.append(_safe_display(asset.name), style=f"bold {CYAN}")
        detail.append("\n")
        detail.append("Versi: ", style=DIM)
        detail.append(_safe_display(asset.version or "unknown"))
        detail.append("    Ukuran: ", style=DIM)
        detail.append(f"{asset.size_bytes:,} B" if asset.size_bytes is not None else "unknown")
        detail.append("\n")
        detail.append("Arsitektur: ", style=DIM)
        detail.append(_safe_display(asset.architecture or "unknown"))
        detail.append("    Format: ", style=DIM)
        detail.append(_safe_display(asset.kind or "asset"))
        detail.append("\n")
        detail.append("Sumber: ", style=DIM)
        detail.append(_safe_display(asset.source or "unknown"))
        detail.append("    Metode: ", style=DIM)
        detail.append(_safe_display(recommended_method(asset)))
        parts = urlsplit(str(asset.url))
        display_url = _safe_display(f"{parts.netloc}{parts.path}")
        if display_url:
            detail.append("\n")
            detail.append("URL: ", style=DIM)
            detail.append(display_url)
        if getattr(asset, "notes", ""):
            detail.append("\nCatatan: ", style=DIM)
            detail.append(_safe_display(asset.notes))
        table.add_row(str(start_index + offset), detail)

    end_index = start_index + len(assets) - 1
    console.print(Text(f"{title}  ·  {start_index}-{end_index}", style=f"bold {CYAN}"))
    console.print(table)
    console.print(Text("Nama dan metadata dibungkus mengikuti lebar terminal. Parameter URL sensitif tidak ditampilkan.", style=DIM))

from rich.progress import ProgressColumn


class _PctColumn(ProgressColumn):
    """Percent only when total is known; blank otherwise (never invented)."""
    def render(self, task):
        return Text(f"{task.completed / task.total * 100:5.1f}%" if task.total else "  --  ", justify="right")


def progress_context(console: Console) -> Progress:
    """Rich progress. Bar/percent only appear when total is known; else spinner + bytes + speed."""
    return Progress(
        SpinnerColumn(style=CYAN),
        TextColumn("[progress.description]{task.description}", table_column=Column(overflow="ellipsis", no_wrap=True, ratio=1)),
        BarColumn(bar_width=None, complete_style=CYAN, finished_style="green"),
        _PctColumn(),
        DownloadColumn(),
        TextColumn("[dim]{task.fields[speed]}[/dim]"),
        TextColumn("[dim]{task.fields[eta]}[/dim]"),
        console=console,
        transient=False,
    )
