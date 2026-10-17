# Arsitektur

- `cli.py`: entry point dan command parser; tanpa argumen membuka menu.
- `menu.py` + `ui.py`: UI Rich, entrance, menu, progress, input dan status.
- `config.py`: dataclass defaults, parser TOML, config writer.
- `discovery/engine.py`: adapter URL-first untuk GitHub Releases, GitLab Releases, HTML publik, dan URL langsung.
- `downloads/manager.py`: streaming HTTP, redirect checks, resume, retry, mirror, batch concurrency, SHA-256.
- `backends/`: pemilihan backend dan wrapper subprocess tanpa shell.
- `security.py`: validasi URL, redirect HTTPS downgrade, sanitasi nama, pembatasan path.
- `verification.py`: hash SHA-256 file lokal dan perbandingan constant-time.
- `apk_inspector.py`: inspeksi read-only ZIP/APK, AndroidManifest presence, native ABI directories, dan metadata `aapt` opsional.
- `history.py`: riwayat SQLite.
- `logging_utils.py`: log berotasi, redaksi query URL, permission file privat best-effort.
- `doctor.py`: deteksi Python, modul, binary opsional dan storage Termux.
- `notifications.py`: notifikasi Termux:API opsional.

Jalur Python HTTP diprioritaskan untuk ukuran kecil/tidak diketahui. Auto-select aria2 hanya jika file terdeteksi minimal 100 MiB, server mengiklankan `Accept-Ranges: bytes`, dan aria2c terpasang. Git hanya dipakai untuk clone. Backend manual yang tidak tersedia menghasilkan error eksplisit. Mirror memakai backend yang sama; pilihan backend tidak diganti diam-diam.
