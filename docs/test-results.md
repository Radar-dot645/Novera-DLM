# Hasil pengujian v1.5.2 (18 Oktober 2026)

96 tes lulus (rich 13.7.1 dan 15.0.0); sapuan pty menu 1–13 tanpa error.

Lingkungan: Linux x86_64, Python 3.13. **Bukan perangkat Termux/WSL nyata.**
- `python -m pytest -q` → lihat angka akhir pada laporan rilis (semua lulus); mencakup server HTTP lokal (antrean, pause/cancel/resume, bandwidth), ZIP berbahaya, .env, redaksi token, git, rumus progres, ABI, `clear` (sukses + fallback ANSI), tinggi menu ≤ tinggi terminal (10/14/24/40 baris), entrance.
- `python -m compileall -q src tests` dan `bash -n scripts/*.sh` lulus.
- Instalasi terisolasi: venv baru + `pip install .` → `novera --version` = `Novera DLM 1.5.2`.
- Smoke TTY (pty + emulator layar pyte, 40×80 dan 14×40): entrance ≥4 dtk tanpa sisa saat masuk menu; panah ×3 dalam satu tulis + Enter membuka Antrean; Exit status 0 tanpa traceback; urutan clear terdeteksi di tiap pergantian layar.
- Tidak diuji: Termux/WSL nyata (perilaku `clear`, lebar glyph ikon pada font Termux), layanan GitHub/GitLab/F-Droid live.
