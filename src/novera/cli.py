"""Entry point: `novera` opens the cinematic interactive menu by default."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from . import __version__
from .config import default_config_path, load_config, write_default_config
from .discovery import DiscoveryError, discover_url, recommended_method
from .downloads import DownloadManager
from .history import HistoryStore
from .menu import run_menu
from .security import SecurityError, validate_url
from .ui import make_console, show_assets
from .verification import VerificationError, verify_sha256


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novera", description="Novera DLM · menjalankan `novera` tanpa argumen membuka menu interaktif.")
    parser.add_argument("--version", action="version", version=f"Novera DLM {__version__}")
    parser.add_argument("--no-animation", action="store_true", help="lewati entrance cinematic")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("download", help="unduh satu URL")
    p.add_argument("url")
    p.add_argument("-o", "--output")
    p.add_argument("--backend", choices=["auto", "python", "curl", "wget", "aria2"], default="auto")
    p.add_argument("--sha256")
    p = sub.add_parser("search", aliases=["list", "info"], help="discover aset dari URL tertentu")
    p.add_argument("url")
    p = sub.add_parser("batch", help="unduh URL dari file teks")
    p.add_argument("file")
    p.add_argument("--concurrency", type=int)
    p = sub.add_parser("clone", help="clone repository Git HTTP(S)")
    p.add_argument("url")
    p.add_argument("destination", nargs="?")
    p = sub.add_parser("history", help="tampilkan riwayat")
    p.add_argument("--limit", type=int, default=30)
    p = sub.add_parser("verify", help="verifikasi SHA-256 file")
    p.add_argument("file")
    p.add_argument("--sha256", required=True)
    p = sub.add_parser("inspect-apk", help="inspeksi manifest dan ABI APK lokal")
    p.add_argument("file")
    p = sub.add_parser("extract", help="ekstrak ZIP dengan aman")
    p.add_argument("file")
    p.add_argument("destination", nargs="?")
    p = sub.add_parser("git-status", help="status repository lokal")
    p.add_argument("path", nargs="?", default=".")
    p = sub.add_parser("plan", help="rencana dependency/build (tidak menjalankan apa pun kecuali --run dan disetujui)")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--run", action="store_true")
    p = sub.add_parser("queue", help="antrean persisten")
    p.add_argument("action", choices=["add", "list", "run", "pause", "resume", "cancel"])
    p.add_argument("arg", nargs="?")
    p = sub.add_parser("env-setup", help="wizard .env opsional (token GitHub/GitLab)")
    sub.add_parser("doctor", help="diagnostik dependensi dan platform")
    sub.add_parser("config", help="lihat atau buat konfigurasi default")
    return parser


def _print_discovery(console: Console, url: str) -> int:
    try:
        assets = discover_url(url)
    except (DiscoveryError, SecurityError) as exc:
        console.print(f"[red]Discovery gagal:[/red] {exc}")
        console.print("Discovery berbasis URL; bukan pencarian internet universal.")
        return 2
    show_assets(console, assets, title="NOVERA ASSET DISCOVERY")
    if assets:
        console.print("[dim]Arsitektur sebelum diunduh hanya petunjuk nama file. Gunakan `novera inspect-apk` untuk memeriksa ABI dari isi APK.[/dim]")
    return 0


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # With no subcommand, the user gets the application experience they asked for.
    if not args_list or args_list == ["--no-animation"]:
        return run_menu(animate="--no-animation" not in args_list)
    parser = _parser()
    args = parser.parse_args(args_list)
    console = make_console()
    try:
        if args.command == "download":
            config = load_config()
            manager = DownloadManager(config, history=HistoryStore())
            result = manager.download(args.url, filename=args.output, backend=args.backend, expected_sha256=args.sha256)
            console.print(f"[green]{result.status}[/green]: {result.destination}")
            hash_status = "verified against trusted SHA-256" if result.verified else "local hash only; not compared to a trusted value"
            console.print(f"Ukuran: {result.size_bytes:,} bytes | SHA-256 ({hash_status}): {result.sha256 or 'not calculated'} | Backend: {result.backend}")
            return 0
        if args.command in {"search", "list", "info"}:
            return _print_discovery(console, args.url)
        if args.command == "batch":
            config = load_config()
            if args.concurrency:
                config.downloads.concurrency = max(1, min(args.concurrency, 8))
            path = Path(args.file).expanduser()
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
            manager = DownloadManager(config, history=HistoryStore())
            results = manager.download_batch(lines, concurrency=config.downloads.concurrency)
            failed = 0
            for url, result in zip(lines, results):
                if isinstance(result, Exception):
                    failed += 1
                    console.print(f"[red]FAILED[/red] {url}: {result}")
                else:
                    console.print(f"[green]{result.status.upper()}[/green] {url} -> {result.destination}")
            console.print(f"Selesai: {len(lines) - failed}/{len(lines)} berhasil.")
            return 1 if failed else 0
        if args.command == "clone":
            from .backends.external import clone_repository
            target = Path(args.destination or Path(args.url.rstrip("/")).name.removesuffix(".git") or "repository").expanduser()
            clone_repository(args.url, target)
            console.print(f"[green]Clone selesai:[/green] {target.resolve()}")
            return 0
        if args.command == "extract":
            from .archive import ArchiveError, safe_extract
            from .progress import Reporter
            from .ui import progress_context
            zp = Path(args.file).expanduser()
            out = Path(args.destination or zp.with_suffix("").name).expanduser()
            try:
                pr = progress_context(console)
                with pr:
                    n = safe_extract(zp, out, Reporter(pr, f"Ekstrak {zp.name}"))
            except ArchiveError as exc:
                console.print(f"[red]Ditolak:[/red] {exc}")
                return 2
            console.print(f"{n} file diekstrak ke {out.resolve()}")
            return 0
        if args.command == "git-status":
            from . import gitops
            console.print(gitops.status(Path(args.path).expanduser()), markup=False)
            return 0
        if args.command == "plan":
            from . import devplan
            plan = devplan.make_plan(Path(args.path).expanduser())
            console.print(f"Proyek: {plan.root} ({', '.join(plan.kinds) or 'tidak dikenali'})")
            for st in plan.steps:
                console.print(f" - {' '.join(st.command)} [{'ok' if st.available else 'tool tidak ada'}]", markup=False)
            for n in plan.notes:
                console.print(n, markup=False)
            if args.run:
                from rich.prompt import Confirm
                for st in plan.steps:
                    if Confirm.ask(f"Jalankan: {' '.join(st.command)} ?", default=False):
                        console.print(f"exit {devplan.run_step(st, plan.root, console)}")
            return 0
        if args.command == "queue":
            from .queue import QueueRunner, QueueStore
            store = QueueStore(HistoryStore())
            if args.action == "add":
                console.print(f"Ditambahkan #{store.add(args.arg or '')}")
            elif args.action == "list":
                for j in store.list():
                    console.print(f"{j['id']} {j['status']} {j['url']} {j['error'] or ''}", markup=False)
            elif args.action == "run":
                from .progress import Reporter
                from .ui import progress_context
                pr = progress_context(console)
                with pr:
                    res = QueueRunner(load_config(), store, lambda job: Reporter(pr, f"#{job['id']}")).run()
                console.print(res)
                return 1 if res.get("failed") else 0
            else:
                if not (args.arg or "").isdigit():
                    console.print("ID antrean diperlukan.")
                    return 2
                r = QueueRunner(load_config(), store)
                {"pause": r.pause, "resume": r.resume, "cancel": r.cancel}[args.action](int(args.arg))
            return 0
        if args.command == "env-setup":
            from .menu import _env_wizard
            _env_wizard(console)
            return 0
        if args.command == "history":
            rows = HistoryStore().list(args.limit)
            for row in rows:
                console.print(f"{row['created_at']} | {row['status']} | {row['size_bytes']} B | {row['destination']}")
            return 0
        if args.command == "verify":
            ok, actual = verify_sha256(Path(args.file).expanduser(), args.sha256)
            console.print(f"SHA-256: {actual}")
            console.print("COCOK" if ok else "TIDAK COCOK")
            return 0 if ok else 1
        if args.command == "inspect-apk":
            from .apk_inspector import APKInspectionError, inspect_apk
            info = inspect_apk(args.file)
            console.print(f"File: {info.path}")
            console.print(f"Size: {info.size_bytes:,} bytes")
            console.print(f"Package: {info.package_name or 'unknown'}")
            console.print(f"Version: {info.version_name or 'unknown'} ({info.version_code or 'unknown'})")
            console.print(f"Min SDK: {info.min_sdk or 'unknown'} | Target SDK: {info.target_sdk or 'unknown'}")
            console.print(f"Native ABI (inspected): {', '.join(info.native_abis) if info.native_abis else 'not detected'}")
            console.print(f"Method: {info.inspection_method}")
            for note in info.notes:
                console.print(f"Note: {note}")
            return 0
        if args.command == "doctor":
            from .doctor import diagnostics
            for item, value, status in diagnostics():
                console.print(f"{item:<25} {value:<40} {status}")
            return 0
        if args.command == "config":
            path = default_config_path()
            if not path.exists():
                write_default_config(path)
                console.print(f"Konfigurasi default dibuat: {path}")
            else:
                console.print(path.read_text(encoding="utf-8"))
            return 0
        parser.print_help()
        return 0
    except (ValueError, OSError, RuntimeError, SecurityError, VerificationError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
