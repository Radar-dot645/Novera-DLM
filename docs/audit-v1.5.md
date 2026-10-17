# Audit v1.0.1 → v1.5.2

Temuan awal (kode 1.0.1, 67 tes lulus): tidak ada ekstraksi ZIP; tidak ada antrean persisten/pause/cancel; tidak ada batas bandwidth; tidak ada pemuatan `.env`; startup tidak modular (animasi tahap palsu); tidak ada `git status`/progres clone; tidak ada rencana build; halaman aset 5/layar; ABI hanya tebakan nama file tanpa rekomendasi; progres ETA bergantung kolom Rich tanpa rumus eksplisit; kolom persen menampilkan 0% saat total tidak diketahui (diperbaiki).
Konflik SQLite vs JSON: tidak ditemukan kode/dokumen riwayat JSON; SQLite dipertahankan sebagai satu-satunya sumber, antrean memakai DB yang sama.
Sudah baik dan dipertahankan: resume dengan validasi Content-Range/validator, validasi redirect, TLS verifikasi default httpx, sanitasi nama file, redaksi URL.
## Batasan v1.5
- Belum diuji pada perangkat Termux/WSL nyata (hanya Linux x86_64, Python 3.13).
- Sumber diuji dengan server lokal/mock, bukan layanan live. Pencarian global tidak ada; discovery berbasis URL.
- ABI dari nama file adalah petunjuk; verifikasi dengan `inspect-apk`. Signature APK tidak diverifikasi.
- Pause/cancel antrean bersifat kooperatif per chunk; cancel tidak menghapus `.part`.
- Navigasi panah hanya di terminal POSIX (Termux/Linux/WSL); lainnya memakai angka.
- Mirror hanya via konfigurasi `[network] mirrors`; backend eksternal (curl/wget/aria2) tidak memakai batas bandwidth global.
