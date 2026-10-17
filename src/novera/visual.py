"""Visual layer for Novera DLM: gradient logo, 4-second cinematic entrance, menu, screen headers.

Palette: slate base with a cyan -> blue -> violet accent gradient.
All screen changes go through clear_screen(), which runs the system `clear` command.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from typing import Callable

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

GRADIENT = ["#22D3EE", "#38BDF8", "#60A5FA", "#818CF8", "#A78BFA"]
INK, MUTED, DIM, LINE = "#E2E8F0", "#94A3B8", "#64748B", "#334155"
OK, WARN, ERR = "#34D399", "#FBBF24", "#F87171"
SEL_BG = "#22D3EE"

_FONT = {
    "N": ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    "O": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    "V": ["█   █", "█   █", "█   █", " █ █ ", "  █  "],
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
}
LOGO = ["  ".join(_FONT[c][r] for c in "NOVERA") for r in range(5)]
LOGO_W = len(LOGO[0])


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def grad(t: float) -> str:
    """Colour at position t in [0,1] along the accent gradient."""
    t = max(0.0, min(1.0, t)) * (len(GRADIENT) - 1)
    i = min(int(t), len(GRADIENT) - 2)
    a, b, f = _hex(GRADIENT[i]), _hex(GRADIENT[i + 1]), t - i
    return "#%02X%02X%02X" % tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))


def gradient_text(s: str, *, bold: bool = True, start: float = 0.0, end: float = 1.0) -> Text:
    out, n = Text(), max(len(s) - 1, 1)
    for i, ch in enumerate(s):
        out.append(ch, style=("bold " if bold else "") + grad(start + (end - start) * i / n))
    return out


def rule(width: int, *, fill: float = 1.0, char: str = "━") -> Text:
    n = int(width * max(0.0, min(1.0, fill)))
    t = gradient_text(char * n, bold=False)
    t.append(char * (width - n), style=LINE)
    return t


# ---------------------------------------------------------------- clear screen
def clear_screen(console) -> None:
    """Clear the whole terminal (screen + scrollback) with the system `clear` command.

    Falls back to raw ANSI (home, erase screen, erase scrollback) when `clear` is
    missing, fails (e.g. TERM unset) or cannot run. Never emits anything off-TTY.
    """
    if not console.is_terminal:
        return
    try:
        sys.stdout.flush()
    except (OSError, ValueError):
        pass
    try:
        ok = subprocess.run("clear", check=False, stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if not ok:
        try:
            sys.stdout.write("\033[H\033[2J\033[3J")
            sys.stdout.flush()
        except (OSError, ValueError):
            pass


def set_title(console, title: str = "Novera DLM") -> None:
    if console.is_terminal:
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()


# ---------------------------------------------------------------------- logo
def logo_frame(width: int, reveal: float, *, glitch: bool = False, rng=random, shimmer: float | None = None) -> Text:
    """Logo with a left-to-right scan wipe. reveal in [0,1]; shaded trail behind the scan head."""
    head = reveal * (LOGO_W + 4)
    out = Text()
    for r, row in enumerate(LOGO):
        for x, ch in enumerate(row):
            if ch == " " or x > head:
                out.append(" ")
                continue
            d = head - x
            if reveal < 1 and d < 1.2:
                out.append("█", style="bold #FFFFFF")
            elif reveal < 1 and d < 2.5:
                out.append("▓", style=grad(x / LOGO_W))
            elif reveal < 1 and d < 4:
                out.append("▒", style=grad(x / LOGO_W))
            elif shimmer is not None and abs(x - ((shimmer * 2.2) % 1.4 - 0.2) * LOGO_W) < 2.2:
                out.append("█", style="bold #FFFFFF")
            elif glitch and rng.random() < 0.012:
                out.append(rng.choice("░▒▓"), style=DIM)
            else:
                out.append("█", style="bold " + grad((x + r * 0.6) / LOGO_W))
        out.append("\n")
    out.rstrip()
    return out


def static_logo(console, version: str) -> None:
    w = console.size.width
    if w >= LOGO_W + 2:
        console.print(Align.center(logo_frame(w, 1.0)))
    else:
        console.print(Align.center(gradient_text("N O V E R A")))
    console.print(Align.center(gradient_text("D L M", start=0.2)))
    console.print(Align.center(Text(f"DOWNLOAD MANAGER  ·  v{version}", style=MUTED)))


def _sysinfo() -> str:
    import os, platform
    termux = "Termux" if "com.termux" in os.environ.get("PREFIX", "") else platform.system()
    return f"{termux} · {platform.machine()} · Python {platform.python_version()}"


TAGLINE = "multi-source download manager · secure by default"


# ------------------------------------------------------------------ entrance
def cinematic(console: Console, version: str, steps: list[tuple[str, Callable[[], object]]],
              seconds: float = 4.0) -> list:
    """Rich Live entrance (~`seconds`). Each step is run for real, in order, while the
    animation plays; the module counter (n/total) is real progress, not an invented percent.
    Returns the list of step results.
    """
    from rich.live import Live
    from rich.spinner import Spinner

    width = max(20, min(console.size.width, 100))
    height = console.size.height
    tall = height >= 22
    big = width >= LOGO_W + 2 and height >= 20
    sysinfo = _sysinfo()
    n = len(steps)
    results: list = [None] * n
    done_at: list[float | None] = [None] * n
    t0 = time.monotonic()
    t_logo, t_stage0, t_stage_end = 0.34 * seconds, 0.42 * seconds, 0.88 * seconds
    slot = (t_stage_end - t_stage0) / n
    spin = Spinner("dots2", style=grad(0.3))
    rng = random.Random(7)
    started = [False] * n

    def frame(t: float) -> Group:
        items: list = []
        if tall:
            items.append(Text(""))
        reveal = min(1.0, t / t_logo)
        if big:
            items.append(Align.center(logo_frame(width, reveal, glitch=t > t_logo, rng=rng, shimmer=(t - t_logo) / seconds if t > t_logo else None)))
        else:
            items.append(Align.center(gradient_text("N O V E R A")))
        sub = "D O W N L O A D   M A N A G E R" if width >= 40 else "D L M"
        items.append(Align.center(gradient_text(sub, start=0.15, end=0.9) if reveal >= 1 else Text("")))
        items.append(Text(""))
        items.append(Align.center(rule(min(width - 4, LOGO_W + 2), fill=min(1.0, t / (0.7 * seconds)))))
        typed = TAGLINE[: int(max(0.0, (t - 0.22 * seconds)) / (0.3 * seconds) * len(TAGLINE))]
        items.append(Align.center(Text(typed if width >= len(TAGLINE) else typed[: width - 2], style=MUTED)))
        if tall and width >= 40:
            items.append(Align.center(Text(sysinfo[: width - 2], style=DIM)))
        items.append(Text(""))
        for i, (label, _fn) in enumerate(steps):
            row = Text("  ")
            if done_at[i] is not None:
                ok = getattr(results[i], "ok", True)
                row.append("✔ " if ok else "! ", style=OK if ok else WARN)
                row.append(f"{label:<12}", style=INK)
                row.append(str(getattr(results[i], "detail", "")), style=DIM)
            elif started[i]:
                row.append_text(Text.from_markup("") )
                row.append(spin.render(t).plain + " ", style=grad(0.3))
                row.append(f"{label:<12}", style=INK)
                row.append("memeriksa…", style=DIM)
            else:
                row.append("· ", style=LINE)
                row.append(label, style=LINE)
            row.truncate(width - 1, overflow="ellipsis")
            items.append(Align.center(row) if False else row)
        items.append(Text(""))
        finished = sum(d is not None for d in done_at)
        items.append(Align.center(rule(min(width - 4, LOGO_W + 2), fill=finished / n, char="▬")))
        status = f"modul {finished}/{n}" + ("  ·  SIAP" if finished == n and t >= t_stage_end else "")
        items.append(Align.center(Text(status, style=OK if finished == n else DIM)))
        return Group(*items)

    clear_screen(console)
    set_title(console)
    with Live(frame(0), console=console, refresh_per_second=20, transient=False, vertical_overflow="crop") as live:
        while True:
            t = time.monotonic() - t0
            for i, (_label, fn) in enumerate(steps):
                if done_at[i] is None and t >= t_stage0 + i * slot:
                    started[i] = True
                    live.update(frame(t))
                    results[i] = fn()
                    done_at[i] = time.monotonic() - t0
                    t = time.monotonic() - t0
            live.update(frame(t))
            if t >= seconds and all(d is not None for d in done_at):
                break
            time.sleep(1 / 20)
    time.sleep(0.15)
    return results


# --------------------------------------------------------------------- menu
SECTIONS = [
    ("DOWNLOAD", [("1", "↓", "Download URL", "Satu file · resume · checksum"),
                  ("2", "⌕", "Discover / List", "Releases, tags, F-Droid · filter"),
                  ("3", "≣", "Batch download", "Daftar URL dari berkas"),
                  ("4", "⟳", "Antrean", "Persisten · jeda/lanjut/batal")]),
    ("REPOSITORY", [("5", "⑂", "Clone repository", "Git clone dengan progres"),
                    ("6", "±", "Git status", "Status repository lokal"),
                    ("7", "▤", "Ekstrak ZIP", "Ekstraksi aman"),
                    ("9", "⚒", "Dependency / build", "Rencana + persetujuan")]),
    ("TOOLS", [("8", "✓", "Verify SHA-256", "Bandingkan hash tepercaya"),
               ("10", "◈", "Inspect APK", "Metadata & ABI APK lokal"),
               ("11", "☰", "Download history", "Riwayat SQLite")]),
    ("SYSTEM", [("12", "✚", "System doctor", "Dependensi & lingkungan"),
                ("13", "⚙", "Konfigurasi / API", "Config & wizard .env"),
                ("0", "⏻", "Exit", "Kembali ke prompt Termux")]),
]
MENU_ITEMS = [(k, name, desc) for _s, rows in SECTIONS for k, _i, name, desc in rows]
MENU_KEYS = [k for k, _n, _d in MENU_ITEMS]


def header(console, version: str, status: str = "") -> Group:
    w = console.size.width
    t = Text()
    t.append("◢◤ ", style=grad(0.0))
    t.append_text(gradient_text("NOVERA DLM", start=0.1, end=0.9))
    t.append(" ◥◣", style=grad(1.0))
    t.append(f"  v{version}", style=DIM)
    parts = [Align.center(t)]
    if status and w >= 36:
        parts.append(Align.center(Text(status[: w - 4], style=DIM)))
    return Group(*parts)


def show_menu(console, selected: int | None = None, *, version: str = "", status: str = "") -> None:
    """Render the menu so it never exceeds the terminal height (windowed when short)."""
    if not version:
        from . import __version__ as version
    w, h = console.size.width, console.size.height
    wide = w >= 62
    rows_all = [(k, i, n, d, sn) for sn, rows in SECTIONS for k, i, n, d in rows]
    chrome = 2 + 2 + 1 + (1 if selected is not None and not wide else 0)  # header, panel border, input line, hint
    sections = h >= len(rows_all) + len(SECTIONS) * 2 + chrome + 1
    budget = max(3, h - chrome - 1)
    if sections:
        budget = len(rows_all) + len(SECTIONS) * 2
    start = 0
    if len(rows_all) > budget:
        view = max(1, budget - 2)  # reserve ▲/▼ rows
        cur = selected or 0
        start = max(0, min(cur - view // 2, len(rows_all) - view))
        visible = list(range(start, start + view))
    else:
        visible = list(range(len(rows_all)))
    lines: list = []
    if start > 0:
        lines.append(Text(f"  ▲ {start} lainnya", style=DIM))
    last = None
    for idx in visible:
        key, icon, name, desc, sname = rows_all[idx]
        if sections and sname != last:
            if last is not None:
                lines.append(Text(""))
            lines.append(Text(f" {sname}", style=f"bold {DIM}"))
        last = sname
        row = Text(no_wrap=True, overflow="ellipsis")
        if idx == selected:
            label = f" {key:>2} {icon} {name}"
            row.append(label, style=f"bold #0B1220 on {SEL_BG}")
            if wide:
                row.append(" " * max(1, 24 - len(name)) + desc, style=f"#0B1220 on {SEL_BG}")
            row.append(" " * max(0, w - 6 - row.cell_len), style=f"on {SEL_BG}")
        else:
            row.append(f" {key:>2} ", style=f"bold {grad(0.0 if key == '0' else int(key) / 13)}")
            row.append(f"{icon} {name}", style=INK)
            if wide:
                row.append(" " * max(1, 24 - len(name)) + desc, style=DIM)
        lines.append(row)
    if start + len(visible) < len(rows_all):
        lines.append(Text(f"  ▼ {len(rows_all) - start - len(visible)} lainnya", style=DIM))
    if selected is not None and not wide:
        lines.append(Text(f" {rows_all[selected][3]}", style=DIM, overflow="ellipsis", no_wrap=True))
    console.print(header(console, version, status))
    console.print(Panel(Group(*lines), border_style=LINE, box=box.ROUNDED, padding=(0, 1),
                        subtitle=Text("↑↓ · Enter · nomor", style=DIM) if w >= 30 else None))


def pick_menu(console, *, version: str = "", status: str = "") -> str:
    """Arrow keys + Enter, or digits (two digits for 10-13). Numeric prompt off-TTY."""
    keys = MENU_KEYS
    try:
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        if not (console.is_terminal and sys.stdin.isatty()):
            raise OSError
        old = termios.tcgetattr(fd)
    except (ImportError, OSError, ValueError, AttributeError):
        from rich.prompt import Prompt
        show_menu(console, version=version, status=status)
        return Prompt.ask("[bold #22D3EE]Pilih menu[/bold #22D3EE]", choices=keys, default="0")
    idx, buf = 0, ""

    def read(timeout=None):
        if timeout is not None and not select.select([fd], [], [], timeout)[0]:
            return ""
        # Unbuffered: sys.stdin.read(1) would slurp a whole ESC [ B sequence into its own
        # buffer where select() cannot see it, which breaks arrow keys.
        b = os.read(fd, 1)
        return b.decode("latin-1") if b else ""

    try:
        tty.setcbreak(fd)
        while True:
            clear_screen(console)
            show_menu(console, idx, version=version, status=status)
            if buf:
                console.print(Text(f" input: {buf}", style=DIM))
            ch = read()
            if ch == "":
                raise EOFError
            if ch == "\x1b":
                seq = read(0.05) + read(0.05)
                if seq == "[A":
                    idx = (idx - 1) % len(keys)
                elif seq == "[B":
                    idx = (idx + 1) % len(keys)
                buf = ""
                continue
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in "\r\n":
                return buf if buf in keys else keys[idx]
            if ch in "\x7f\b":
                buf = buf[:-1]
            elif ch.isdigit():
                buf += ch
                if buf in keys and not any(k != buf and k.startswith(buf) for k in keys):
                    return buf
                if buf == "1" and not read(0.7):
                    return "1"
                if buf not in keys and not any(k.startswith(buf) for k in keys):
                    buf = ""
                elif buf in keys and len(buf) == 2:
                    return buf
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def screen_header(console, title: str, version: str = "") -> None:
    """Printed right after clear_screen() on every feature screen."""
    if not version:
        from . import __version__ as version
    w = console.size.width
    t = Text()
    t.append("◢◤ ", style=grad(0.0))
    t.append_text(gradient_text(title.upper(), end=0.8))
    t.append(f"   NOVERA DLM v{version}" if w >= 50 else "", style=DIM)
    console.print(t)
    console.print(rule(w - 1))
    console.print()
