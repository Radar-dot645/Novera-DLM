# Konfigurasi

File aktif: `~/.config/novera/config.toml`, kecuali `NOVERA_CONFIG` diset. `novera config` membuat konfigurasi default jika belum ada. `config.example.toml` adalah referensi.

- `downloads.directory`: direktori output.
- `downloads.concurrency`: 1 sampai 8.
- `downloads.retries`: jumlah percobaan ulang, rentang 0 sampai 8.
- `downloads.timeout_seconds`: timeout koneksi/request, dibatasi 2 sampai 300 detik.
- `downloads.resume`: aktif/nonaktif resume.
- `downloads.overwrite_policy`: `rename`, `skip`, atau `overwrite`.
- `ui.cinematic_seconds`: durasi entrance, 0 sampai 10 detik.
- `network.mirrors`: URL alternatif eksplisit, dicoba setelah sumber utama gagal.
- `security.max_redirects`: maksimum redirect.
- `security.max_file_size_mb`: batas ukuran opsional; 0 tidak membatasi.

Token GitHub/GitLab gunakan `GITHUB_TOKEN` dan `GITLAB_TOKEN` di environment. Jangan commit `.env`, token, ataupun output unduhan ke repository.
