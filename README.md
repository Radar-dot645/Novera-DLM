# Novera DLM

**Novera DLM** adalah download manager CLI berbasis Python untuk Termux Android, Linux, dan WSL. Menjalankan `novera` tanpa argumen akan membuka entrance cinematic dan menu interaktif Rich. Pilih **0 · Exit** untuk menutup aplikasi dan kembali ke prompt terminal biasa. Layar dibersihkan saat berpindah dari menu ke fitur dan saat berpindah halaman, sementara output yang dialihkan ke file tidak diberi kode clear-screen.

> Status paket ini: implementasi dibuat untuk penggunaan lokal. Jalankan tes di bagian bawah sebelum mengandalkan versi yang telah dimodifikasi. Discovery memakai URL spesifik; Novera bukan mesin pencari internet universal.

## Fitur utama

- Menu terminal dengan ASCII art, warna cyan/abu-abu, Rich progress, dan entrance sekitar 4 detik (lewati dengan `novera --no-animation`).
- Unduh HTTP(S), batch URL, resume yang memeriksa HTTP Range, retry dengan backoff, kebijakan file duplikat, checksum SHA-256, dan mirror opsional.
- Discovery URL publik untuk aset GitHub Releases (semua halaman release dipaginasi sampai batas aman 1.000 release), GitLab Releases, halaman web publik, direct URL, dan APK yang tertaut. Nama aset dan metadata dibungkus agar tidak terpotong di terminal sempit; menu pemilihan memiliki halaman berikut/sebelumnya.
- Riwayat SQLite, log berotasi dengan redaksi query URL, pemeriksaan dependensi, konfigurasi TOML, notifikasi Termux:API opsional, dan inspeksi APK lokal.
- Backend Python HTTP; curl, wget, aria2c dan Git dideteksi sebagai alat opsional. Pemilihan backend manual yang tidak tersedia akan gagal dengan pesan jelas, bukan diganti diam-diam.
- Pengunduhan APK tidak pernah memicu instalasi otomatis.

## Baru di v1.5.2
Startup modular, menu panah/angka, antrean persisten (`novera queue ...`), batas bandwidth, ekstraksi ZIP aman (`novera extract`), `git-status`, rencana build dengan persetujuan (`novera plan`), wizard `.env` opsional (`novera env-setup`), rekomendasi APK per ABI, pagination 20 + filter. Lihat `CHANGELOG.md` dan `docs/audit-v1.5.md` (batasan). Token API opsional; fitur publik jalan tanpa token. APK hanya diunduh, tidak pernah dipasang.

## Instalasi Termux

1. Instal Python dan unduh/ekstrak folder proyek. Bila berkas berada di Download bersama, izinkan akses penyimpanan terlebih dahulu:

   ```bash
   termux-setup-storage
   pkg install python git
   ```

2. Masuk ke folder proyek, lalu jalankan:

   ```bash
   bash scripts/install-termux.sh
   ```

3. Mulai aplikasi:

   ```bash
   novera
   ```

4. Keluar dari menu dengan memilih `0`; prompt Termux akan kembali. Entrance dapat dilewati dengan:

   ```bash
   novera --no-animation
   ```

Default download path adalah `~/storage/downloads/Novera`. Direktori ini memerlukan izin shared storage Termux. Jika tidak ingin memberi izin, ubah path pada config menjadi `~/Novera-Downloads`.

## Instalasi Linux

Dari folder proyek:

```bash
bash scripts/install-linux.sh
```

Jika `~/.local/bin` belum ada di PATH, tambahkan ke konfigurasi shell, misalnya Bash:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Instalasi WSL

Dari shell Linux/Ubuntu di WSL, masuk ke folder proyek lalu:

```bash
bash scripts/install-wsl.sh
```

## Perintah

Jalankan `novera` untuk menu interaktif (mode yang direkomendasikan untuk Termux):

```bash
novera
```

Perintah subcommand juga tersedia untuk automasi:

```bash
novera download "https://example.org/file.zip"
novera download "https://example.org/app.apk" --sha256 <64-hex-hash>
novera search "https://github.com/owner/repo/releases"
novera list "https://example.org/downloads/"
novera info "https://example.org/file.zip"
novera batch examples/urls.txt --concurrency 3
novera clone "https://github.com/owner/repo.git"
novera history --limit 30
novera verify ./file.zip --sha256 <64-hex-hash>
novera inspect-apk ./app.apk
novera doctor
novera config
novera --version
```

`search`, `list`, dan `info` adalah alias untuk discovery berbasis URL, bukan query bebas. Untuk repositori privat atau batas API yang lebih tinggi, token opsional dapat disediakan melalui environment variable `GITHUB_TOKEN` atau `GITLAB_TOKEN`. Hindari menaruh token dalam perintah yang bisa tersimpan di history shell.

## Batch

Buat `urls.txt` dengan satu URL HTTP(S) per baris. Baris kosong dan komentar `#` diabaikan:

```text
# Arsip rilis
https://example.org/releases/tool.zip
https://example.org/downloads/app.apk
```

Kemudian jalankan `novera batch urls.txt` atau pilih menu Batch download. Maksimal concurrency dibatasi 8 dan default-nya 3.

## Konfigurasi

Config aktif berada di `~/.config/novera/config.toml` atau di lokasi `NOVERA_CONFIG`. Buat contoh config dengan `novera config`, lalu ubah nilai dengan editor teks. Konfigurasi yang lengkap tersedia pada `config.example.toml`.

`overwrite_policy` menerima `rename`, `skip`, atau `overwrite`. Default `rename` menghindari hilangnya berkas secara tidak sengaja. Daftar mirror hanya berisi URL yang kamu percayai.

## Integritas dan batasan keamanan

- Hanya HTTP/HTTPS untuk unduhan dan URL clone; URL dengan kredensial tertanam ditolak.
- Redirect diperiksa, HTTPS ke HTTP ditolak, nama berkas disanitasi, dan unduhan ditulis ke file `.part` sebelum dipindahkan ke tujuan akhir.
- Resume hanya digunakan bila ada partial file lokal; server harus mengembalikan HTTP 206 dan `Content-Range` yang cocok. Jika server mengabaikan Range dan merespons HTTP 200, Novera memulai ulang penulisan dari awal.
- SHA-256 baru dinyatakan cocok jika dibandingkan dengan nilai tepercaya yang diberikan pengguna. Novera tidak mengarang checksum atau menganggap hash hasil unduhan sebagai bukti bahwa file aman.
- API Release dapat membatasi request anonim. URL fallback manual selalu tersedia.
- Discovery HTML bergantung pada struktur halaman publik dan tidak bisa membaca halaman login, DRM, atau sumber dengan proteksi akses.
- Mirror dicoba berurutan memakai backend yang dipilih; backend eksternal tidak diganti diam-diam. Mirror HTTP ditolak bila sumber utama HTTPS. Backend eksternal memiliki perilaku resume dan redirect yang bergantung pada program eksternal; gunakan Python HTTP jika ingin jalur redirect yang paling ketat.
- Log berotasi disimpan pada `~/.local/share/novera/novera.log` (bisa diubah melalui `NOVERA_LOG_PATH`); izin file berusaha dibatasi ke pemilik dan query URL disamarkan. Jika filesystem menolak pengaturan permission, log tetap bersifat best-effort.
- Signature APK/release belum diverifikasi secara otomatis. Inspeksi APK membaca manifest/ABI secara lokal (menggunakan `aapt` bila tersedia), tetapi tidak memvalidasi tanda tangan publisher. APK hanya diunduh, tidak diinstal.

## Tes

Install dependency test kemudian jalankan:

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m compileall -q src
novera --version
novera doctor
```

Tes memakai HTTP server lokal dan mock, sehingga tidak membutuhkan GitHub/GitLab live. Lihat `docs/security.md` dan `docs/troubleshooting.md` untuk rincian batasan. Tes APK membuat berkas ZIP sintetis di direktori sementara, bukan memasang aplikasi.

## Direktori data

- Unduhan: `~/storage/downloads/Novera` (default Termux).
- Konfigurasi: `~/.config/novera/config.toml`.
- Riwayat: `~/.local/share/novera/history.sqlite3`.
- Log: `~/.local/share/novera/novera.log` (rotasi 1 MB, tiga cadangan; override melalui `NOVERA_LOG_PATH`). URL query disamarkan agar signed URL/token tidak tercatat utuh.

## Lisensi

MIT. Lihat `LICENSE`.
