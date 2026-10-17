"""Interactive main menu. Choosing Exit terminates Novera and returns to the shell."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import __version__
from .backends import choose_backend
from .backends.external import clone_repository
from .config import AppConfig, default_config_path, load_config, write_default_config
from .discovery import Asset, DiscoveryError, discover_url
from .doctor import diagnostics
from .downloads import DownloadManager
from .history import HistoryStore
from .security import SecurityError, validate_url
from .ui import CYAN, DIM, clear_screen, make_console, pick_menu, progress_context, show_assets
from .progress import Reporter
from .verification import VerificationError, verify_sha256


def _history() -> HistoryStore:
    return HistoryStore()


def _manager(config: AppConfig, console):
    progress = progress_context(console)
    reporter = Reporter(progress, "Menyiapkan unduhan")
    manager = DownloadManager(config, history=_history(), progress_callback=reporter)
    return manager, progress, reporter.task


def _download_flow(console, config: AppConfig, url: str | None = None) -> None:
    target = url or Prompt.ask("[bold #22D3EE]URL unduhan[/bold #22D3EE]").strip()
    try:
        target = validate_url(target)
    except SecurityError as exc:
        console.print(f"[red]URL ditolak:[/red] {exc}")
        return
    filename = Prompt.ask("Nama file (kosong = otomatis dari URL)", default="").strip() or None
    checksum = Prompt.ask("SHA-256 tepercaya (opsional, kosong = lewati)", default="").strip() or None
    backend = Prompt.ask("Backend", choices=["auto", "python", "curl", "wget", "aria2"], default="auto")
    try:
        if backend == "auto":
            console.print("[dim]Backend: auto · memeriksa ukuran dan dukungan HTTP Range jika tersedia.[/dim]")
        else:
            choice = choose_backend(backend)
            console.print(f"[dim]Backend: {choice.name} · {choice.reason}[/dim]")
        manager, progress, _task = _manager(config, console)
        with progress:
            result = manager.download(target, filename=filename, backend=backend, expected_sha256=checksum)
        if result.status == "skipped":
            console.print(f"[yellow]Dilewati:[/yellow] {result.destination}")
        else:
            hash_status = "cocok dengan SHA-256 tepercaya" if result.verified else "hash lokal saja; belum dibandingkan dengan nilai tepercaya"
            console.print(Panel(f"[bold green]Download selesai[/bold green]\nFile: {result.destination}\nUkuran: {result.size_bytes:,} bytes\nSHA-256 ({hash_status}): {result.sha256}\nBackend: {result.backend}", border_style="#334155", box=box.ROUNDED))
            from .notifications import notify
            if notify("Novera DLM", f"Download selesai: {result.destination.name}"):
                console.print("[dim]Notifikasi Termux terkirim.[/dim]")
    except Exception as exc:
        console.print(f"[bold red]Download gagal:[/bold red] {exc}")


def _show_assets(console, assets: list[Asset], *, start_index: int = 1) -> None:
    show_assets(console, assets, start_index=start_index, title="NOVERA ASSET DISCOVERY")


PAGE_SIZE = 20


def _select_asset(console, assets: list[Asset]) -> Asset | None:
    """Paginated (20/page) asset list with filter; returns the selected asset."""
    from .abi import device_abis, recommend_apk
    if not assets:
        return None
    rec, why = recommend_apk(assets, device_abis()[0])
    if rec is not None:
        console.print(f"[bold green]Rekomendasi APK:[/bold green] {rec.name}\n[dim]{why}[/dim]")
    view, page = assets, 0
    while True:
        total_pages = max(1, (len(view) + PAGE_SIZE - 1) // PAGE_SIZE)
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(view))
        clear_screen(console)
        if view:
            _show_assets(console, view[start:end], start_index=start + 1)
        else:
            console.print("[yellow]Tidak ada aset cocok dengan filter.[/yellow]")
        console.print(f"[dim]Halaman {page + 1}/{total_pages} · {len(view)}/{len(assets)} aset[/dim]")
        console.print("[dim]nomor · n berikutnya · p sebelumnya · f <teks> filter · f reset · q kembali[/dim]")
        raw = Prompt.ask("[bold #22D3EE]Pilih aset[/bold #22D3EE]", default="q").strip().lower()
        if raw == "q":
            return None
        if raw == "n" and page + 1 < total_pages:
            page += 1
        elif raw == "p" and page > 0:
            page -= 1
        elif raw.startswith("f"):
            term = raw[1:].strip()
            view = assets if term in {"", "reset"} else [a for a in assets if term in f"{a.name} {a.version or ''} {a.architecture or ''} {a.kind}".lower()]
            page = 0
        elif raw.isdigit() and start + 1 <= int(raw) <= end:
            return view[int(raw) - 1]
        else:
            console.print("[red]Input tidak valid atau di luar halaman.[/red]")
            Prompt.ask("Tekan Enter", default="")


def _discover_flow(console, target: str | None = None, *, allow_download: bool = True) -> None:
    url = target or Prompt.ask("[bold #22D3EE]URL repo/release/halaman web/aset[/bold #22D3EE]").strip()
    try:
        assets = discover_url(url)
    except (DiscoveryError, SecurityError) as exc:
        console.print(f"[red]Discovery gagal:[/red] {exc}")
        console.print("[dim]Discovery berbasis URL, bukan pencarian internet universal. Tempel URL publik yang spesifik atau gunakan menu Download URL.[/dim]")
        return
    if not allow_download or not assets or not console.is_terminal:
        _show_assets(console, assets)
        return
    asset = _select_asset(console, assets)
    if asset is None:
        clear_screen(console)
        console.print("[dim]Pemilihan aset dibatalkan.[/dim]")
        return
    clear_screen(console)
    _download_flow(console, load_config(), asset.url)


def _batch_flow(console, config: AppConfig, path: str | None = None) -> None:
    raw_path = path or Prompt.ask("Path file URL (contoh: examples/urls.txt)").strip()
    file_path = Path(raw_path).expanduser()
    try:
        urls = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    except OSError as exc:
        console.print(f"[red]Tidak bisa membaca daftar URL:[/red] {exc}")
        return
    if not urls:
        console.print("[yellow]Daftar URL kosong.[/yellow]")
        return
    valid: list[str] = []
    for url in urls:
        try:
            valid.append(validate_url(url))
        except SecurityError as exc:
            console.print(f"[yellow]URL dilewati:[/yellow] {url[:100]} · {exc}")
    if not valid:
        console.print("[red]Tidak ada URL valid.[/red]")
        return
    progress = progress_context(console)
    reporters = [Reporter(progress, Path(url.split("?", 1)[0]).name or "download") for url in valid]
    history = _history()
    results: list[tuple[str, object]] = []
    with progress, ThreadPoolExecutor(max_workers=config.downloads.concurrency, thread_name_prefix="novera") as pool:
        futures = {}
        for idx, url in enumerate(valid):
            mgr = DownloadManager(config, history=history, progress_callback=reporters[idx])
            futures[pool.submit(mgr.download, url)] = url
        for future in as_completed(futures):
            url = futures[future]
            try:
                results.append((url, future.result()))
            except Exception as exc:
                results.append((url, exc))
    table = Table(box=box.SIMPLE, header_style=f"bold {CYAN}")
    table.add_column("Status")
    table.add_column("URL")
    table.add_column("Hasil")
    for url, result in results:
        if isinstance(result, Exception):
            table.add_row("[red]FAILED[/red]", url[:70], str(result)[:100])
        else:
            table.add_row("[green]DONE[/green]", url[:70], str(result.destination))
    console.print(table)
    from .notifications import notify
    notify("Novera DLM", f"Batch selesai: {len(results) - sum(isinstance(r, Exception) for _, r in results)}/{len(results)} berhasil")


def _clone_flow(console, url: str | None = None) -> None:
    from . import gitops
    target = url or Prompt.ask("URL repository HTTP(S)").strip()
    name = Prompt.ask("Nama direktori tujuan", default=Path(target.rstrip("/")).name.removesuffix(".git") or "repository")
    destination = Path(name).expanduser()
    try:
        progress = progress_context(console)
        with progress:
            rep = Reporter(progress, "git clone")
            def cb(phase, pct):
                progress.update(rep.task, description=f"git: {phase}", total=100 if pct is not None else None, completed=pct or 0)
            gitops.clone(target, destination, progress=cb)
        console.print(f"[green]Repository selesai di-clone:[/green] {destination.resolve()}")
        console.print("[dim]Tidak ada build/skrip dijalankan. Gunakan menu Dependency / build untuk rencana.[/dim]")
    except Exception as exc:
        console.print(f"[red]Clone gagal:[/red] {exc}")


def _gitstatus_flow(console, path: str | None = None) -> None:
    from . import gitops
    try:
        console.print(gitops.status(Path(path or Prompt.ask("Path repository", default=".")).expanduser()), markup=False)
    except Exception as exc:
        console.print(f"[red]Gagal:[/red] {exc}")


def _extract_flow(console, zip_path: str | None = None, dest: str | None = None) -> None:
    from .archive import ArchiveError, safe_extract
    zp = Path(zip_path or Prompt.ask("Path file ZIP")).expanduser()
    out = Path(dest or Prompt.ask("Direktori tujuan", default=zp.with_suffix("").name)).expanduser()
    try:
        progress = progress_context(console)
        with progress:
            rep = Reporter(progress, f"Ekstrak {zp.name}")
            n = safe_extract(zp, out, rep)
        console.print(f"[green]{n} file diekstrak ke[/green] {out.resolve()}")
    except (ArchiveError, OSError) as exc:
        console.print(f"[red]Ekstraksi ditolak/gagal:[/red] {exc}")


def _queue_flow(console, config: AppConfig) -> None:
    from .queue import QueueRunner, QueueStore
    store = QueueStore(_history())
    while True:
        jobs = store.list()
        table = Table(box=box.SIMPLE, header_style=f"bold {CYAN}")
        for c in ("ID", "Status", "URL", "Error"):
            table.add_column(c, overflow="fold")
        for j in jobs[-15:]:
            table.add_row(str(j["id"]), j["status"], j["url"][:60], (j["error"] or "")[:40])
        console.print(table)
        cmd = Prompt.ask("a=tambah  r=jalankan  p=jeda <id>  c=lanjut <id>  x=batal <id>  q=keluar", default="q").strip().split()
        if not cmd or cmd[0] == "q":
            return
        try:
            if cmd[0] == "a":
                console.print(f"Ditambahkan #{store.add(cmd[1] if len(cmd) > 1 else Prompt.ask('URL'))}")
            elif cmd[0] == "r":
                progress = progress_context(console)
                with progress:
                    runner = QueueRunner(config, store, lambda job: Reporter(progress, f"#{job['id']}"))
                    console.print(runner.run())
            elif cmd[0] in {"p", "c", "x"} and len(cmd) > 1 and cmd[1].isdigit():
                runner = QueueRunner(config, store)
                {"p": runner.pause, "c": runner.resume, "x": runner.cancel}[cmd[0]](int(cmd[1]))
            else:
                console.print("[yellow]Perintah tidak dikenal.[/yellow]")
        except Exception as exc:
            console.print(f"[red]{exc}[/red]")


def _plan_flow(console, path: str | None = None) -> None:
    from . import devplan
    root = Path(path or Prompt.ask("Direktori proyek", default=".")).expanduser()
    try:
        plan = devplan.make_plan(root)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(f"[bold]Proyek:[/bold] {plan.root} · {', '.join(plan.kinds) or 'tidak dikenali'}")
    for i, st in enumerate(plan.steps, 1):
        console.print(f" {i}. {' '.join(st.command)}  [{'ok' if st.available else 'tool tidak ada: ' + st.tool}]")
    for n in plan.notes:
        console.print(f"[yellow]{n}[/yellow]")
    for st in plan.steps:
        if Confirm.ask(f"Jalankan: {' '.join(st.command)} ?", default=False):
            try:
                rc = devplan.run_step(st, plan.root, console)
                console.print("[green]Selesai[/green]" if rc == 0 else f"[red]Gagal (exit {rc})[/red]")
            except Exception as exc:
                console.print(f"[red]{exc}[/red]")


def _env_wizard(console) -> None:
    from . import envfile
    found = envfile.find_env()
    console.print(f".env aktif: {found or 'belum ada'}  [dim](token opsional; fitur publik tetap berfungsi tanpa token)[/dim]")
    if not Confirm.ask("Jalankan wizard .env (boleh dilewati)?", default=False):
        return
    vals = {k: Prompt.ask(f"{k} (kosong = lewati)", password=True, default="") for k in envfile.KNOWN_KEYS}
    if any(vals.values()):
        console.print(f"[green]Disimpan (chmod 600):[/green] {envfile.write_env(vals)}")
    else:
        console.print("[dim]Tidak ada token disimpan.[/dim]")


def _verify_flow(console, file_name: str | None = None, expected: str | None = None) -> None:
    raw_path = file_name or Prompt.ask("Path file yang diverifikasi").strip()
    hash_value = expected or Prompt.ask("SHA-256 tepercaya (64 karakter hex)").strip()
    try:
        progress = progress_context(console)
        with progress:
            rep = Reporter(progress, "Verifikasi SHA-256")
            fp = Path(raw_path).expanduser()
            ok, actual = verify_sha256(fp, hash_value, rep)
        console.print(f"SHA-256 aktual: [cyan]{actual}[/cyan]")
        console.print("[bold green]COCOK[/bold green]" if ok else "[bold red]TIDAK COCOK[/bold red]")
    except (VerificationError, OSError) as exc:
        console.print(f"[red]Verifikasi gagal:[/red] {exc}")


def _inspect_apk_flow(console, path: str | None = None) -> None:
    from .apk_inspector import APKInspectionError, inspect_apk
    raw = path or Prompt.ask("Path APK lokal (.apk; split container tidak dianggap standalone)").strip()
    try:
        info = inspect_apk(raw)
    except (APKInspectionError, FileNotFoundError, OSError) as exc:
        console.print(f"[red]Inspeksi APK gagal:[/red] {exc}")
        return
    values = [
        f"File: {info.path}", f"Ukuran: {info.size_bytes:,} bytes",
        f"Package: {info.package_name or 'unknown'}", f"Versi: {info.version_name or 'unknown'}",
        f"Version code: {info.version_code or 'unknown'}", f"Min SDK: {info.min_sdk or 'unknown'}",
        f"Target SDK: {info.target_sdk or 'unknown'}",
        f"Native ABI (dari isi APK): {', '.join(info.native_abis) if info.native_abis else 'tidak terdeteksi'}",
        f"Metode: {info.inspection_method}",
    ]
    values.extend(f"Catatan: {note}" for note in info.notes)
    console.print(Panel("\n".join(values), title="APK INSPECTION", border_style="#334155", box=box.ROUNDED))


def _history_flow(console) -> None:
    try:
        rows = _history().list(100)
    except Exception as exc:
        console.print(f"[red]Riwayat tidak bisa dibaca:[/red] {exc}")
        return
    if not rows:
        console.print("[dim]Riwayat masih kosong.[/dim]")
        return
    table = Table(box=box.ROUNDED, header_style=f"bold {CYAN}", expand=True)
    table.add_column("Waktu")
    table.add_column("Status")
    table.add_column("Ukuran", justify="right")
    table.add_column("Tujuan")
    for row in rows:
        table.add_row(str(row["created_at"]), str(row["status"]), f"{row['size_bytes']:,}", str(row["destination"]))
    console.print(table)


def _doctor_flow(console) -> None:
    table = Table(box=box.ROUNDED, header_style=f"bold {CYAN}", expand=True)
    table.add_column("Komponen")
    table.add_column("Nilai")
    table.add_column("Status")
    for component, value, status in diagnostics():
        style = "green" if status in {"OK", "available"} else ("red" if status.startswith("ERROR") else "yellow")
        table.add_row(component, value, f"[{style}]{status}[/{style}]")
    console.print(table)
    if not (Path.home() / "storage" / "downloads").exists():
        console.print("[dim]Termux: jalankan `termux-setup-storage` jika ingin menyimpan file di folder Download bersama.[/dim]")


def _config_flow(console) -> None:
    path = default_config_path()
    console.print(f"Lokasi konfigurasi: [cyan]{path}[/cyan]")
    if path.exists():
        try:
            config = load_config(path)
            console.print(Panel(f"Direktori: {config.downloads.directory}\nConcurrency: {config.downloads.concurrency}\nRetry: {config.downloads.retries}\nTimeout: {config.downloads.timeout_seconds}s\nEntrance: {config.ui.cinematic_seconds}s\nPolicy: {config.downloads.overwrite_policy}", title="Config aktif", border_style="#334155"))
        except Exception as exc:
            console.print(f"[red]Konfigurasi bermasalah:[/red] {exc}")
    else:
        console.print("Konfigurasi belum dibuat; default bawaan tetap aktif.")
        _env_wizard(console)
        if Confirm.ask("Buat config.toml dari nilai default?", default=False):
            try:
                write_default_config(path)
                console.print(f"[green]Konfigurasi dibuat:[/green] {path}")
            except OSError as exc:
                console.print(f"[red]Gagal membuat konfigurasi:[/red] {exc}")
    console.print("[dim]Edit file TOML secara manual. Jangan simpan token API di file ini.[/dim]")


def run_menu(*, animate: bool = True) -> int:
    from . import devplan
    from .startup import build_steps, run_startup, StartupReport
    from .ui import cinematic, screen_header, static_logo
    console = make_console()
    try:
        config = load_config()
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    if animate and console.is_terminal and config.ui.cinematic_seconds > 0:
        report = StartupReport()
        cinematic(console, __version__, build_steps(report, config), seconds=config.ui.cinematic_seconds)
    else:
        clear_screen(console)
        static_logo(console, __version__)
        report = run_startup(config, console, animate=False)
        for st in report.stages:
            console.print(f" {'✔' if st.ok else '!'} {st.name:<11} {st.detail}", markup=False)
    for w in report.warnings:
        console.print(f"[yellow]{w}[/yellow]")
    if report.missing_deps and Confirm.ask(f"Pasang dependensi hilang ({', '.join(report.missing_deps)}) dengan pip?", default=False):
        console.print("Selesai." if devplan.install_python_deps(report.missing_deps, console) == 0 else "[red]Instalasi gagal.[/red]")
    handlers = {
        "1": ("Download URL", lambda: _download_flow(console, config)),
        "2": ("Discover / List", lambda: _discover_flow(console)),
        "3": ("Batch download", lambda: _batch_flow(console, config)),
        "4": ("Antrean", lambda: _queue_flow(console, config)),
        "5": ("Clone repository", lambda: _clone_flow(console)),
        "6": ("Git status", lambda: _gitstatus_flow(console)),
        "7": ("Ekstrak ZIP", lambda: _extract_flow(console)),
        "8": ("Verify SHA-256", lambda: _verify_flow(console)),
        "9": ("Dependency / build", lambda: _plan_flow(console)),
        "10": ("Inspect APK", lambda: _inspect_apk_flow(console)),
        "11": ("Download history", lambda: _history_flow(console)),
        "12": ("System doctor", lambda: _doctor_flow(console)),
        "13": ("Konfigurasi / API", lambda: _config_flow(console)),
    }
    status = " · ".join(f"{st.name} {'✔' if st.ok else '!'}" for st in report.stages)
    bye = Panel("[bold #22D3EE]NOVERA DLM[/bold #22D3EE]\n[dim]Sampai jumpa. Kembali ke shell.[/dim]", border_style="#334155")
    while True:
        try:
            choice = pick_menu(console, version=__version__, status=status)
        except (KeyboardInterrupt, EOFError):
            clear_screen(console)
            console.print(bye)
            return 0
        if choice == "0":
            clear_screen(console)
            console.print(bye)
            return 0
        try:
            title, fn = handlers[choice]
            clear_screen(console)
            screen_header(console, title)
            fn()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Aksi dibatalkan. Menu tetap aktif.[/yellow]")
        except Exception as exc:
            console.print(f"[red]Kesalahan tak terduga:[/red] {exc}")
        try:
            Prompt.ask("[dim]Tekan Enter untuk kembali ke menu[/dim]", default="")
        except (KeyboardInterrupt, EOFError):
            continue
