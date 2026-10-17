# Changelog

## 1.5.2 — 2026-10-18
- Perbaikan: `TextColumn.__init__() got an unexpected keyword argument 'overflow'` (semua progress Rich: download, batch, antrean, clone, ekstrak, verifikasi).
- Perbaikan: `name '_discover_flow' is not defined` (menu Discover / List).
- Tes baru `tests/test_flows.py` menjalankan tiap flow menu (download, batch, discover, verify, ekstrak, plan, git status, antrean, doctor, history, config); 96 tes lulus dengan rich 13.7.1 maupun 15.0.0. Sapuan pty menu 1–13: tidak ada error.

## 1.5.1 — 2026-10-18
- Rename produk menjadi **Novera DLM** (paket `novera-dlm`, arsip `Novera-DLM.zip`, perintah tetap `novera`).
- Clear-screen penuh di setiap pergantian layar lewat perintah sistem `clear` (fallback ANSI `ESC[H ESC[2J ESC[3J` bila `clear` tidak ada/gagal); tiap fitur diawali header layar sendiri, jadi tidak ada tampilan menumpuk.
- Entrance baru: logo gradient dengan scan-reveal, kilau, tagline mengetik, info sistem, dan daftar modul yang menjalankan pemeriksaan nyata; total 4 detik, adaptif terhadap tinggi/lebar terminal.
- Menu bergradient dengan bagian (Download/Repository/Tools/System), sorotan baris aktif, dan jendela gulir (▲/▼) sehingga tidak pernah melebihi tinggi terminal (termasuk saat keyboard Termux terbuka).
- Perbaikan bug: panah atas/bawah tidak terbaca bila urutan ESC dikirim sekaligus (pembacaan stdin kini tanpa buffer); prompt Antrean tidak lagi memakan teks `[a]`/`[r]`.

## 1.5.0 — 2026-10-17
Ditambah
- Startup modular: dependency → API/.env → system check → queue → menu; entrance Rich 4 dtk (spinner nyata, tiap tahap menjalankan pemeriksaan sungguhan). Exit kembali ke shell.
- Menu 0-13 dengan navigasi panah+Enter atau angka; fallback prompt numerik di non-TTY; clear-screen tiap ganti layar.
- `progress.py`: persen = bytes/total*100, kecepatan = Δbytes/Δwaktu, ETA = sisa/kecepatan. Tanpa total: spinner + bytes + kecepatan, tanpa persen/ETA.
- Progress Rich untuk download, batch, antrean, git clone (parse `--progress` Git), ekstraksi ZIP, verifikasi SHA-256.
- Antrean persisten SQLite (`novera queue add|list|run|pause|resume|cancel`), concurrency 3, pause menjaga `.part` untuk resume.
- Batas bandwidth global (`bandwidth_limit_kbps`).
- Ekstraksi ZIP aman (`novera extract`): blok traversal, path absolut, symlink, zip bomb.
- `.env` opsional + wizard (`novera env-setup`, chmod 600, peringatan permission); redaksi token di log.
- Rencana dependency/build (`novera plan`): hanya menampilkan; eksekusi per langkah setelah konfirmasi; `npm --ignore-scripts`; tidak pernah otomatis setelah clone. Git hooks dinonaktifkan saat clone.
- `git-status`, rekomendasi APK per ABI perangkat, pagination 20 item + filter (`f teks`).
Diubah: versi 1.5.0, `sha256_file` menerima callback progress.
Riwayat: hanya SQLite (tidak ditemukan penyimpanan JSON); antrean memakai DB yang sama.

## 1.0.1
Rilis sebelumnya.
