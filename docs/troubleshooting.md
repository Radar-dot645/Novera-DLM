# Troubleshooting

**`novera: command not found`**: jalankan installer sesuai platform. Pada Linux/WSL, pastikan `~/.local/bin` ada di `PATH`. Pada Termux, pastikan `$PREFIX/bin` ada di `PATH`.

**Download shared storage gagal**: jalankan `termux-setup-storage`, ikuti dialog izin Android, lalu periksa `~/storage/downloads`. Alternatifnya ubah direktori ke `~/Novera-Downloads` di config.

**`aria2`/`curl`/`wget` tidak ada**: pasang alat itu jika memang ingin memilihnya; backend Python tetap tersedia.

**GitHub/GitLab API membatasi request**: gunakan URL asset langsung atau atur token opsional pada environment variable. Token tidak boleh dimasukkan ke URL.

**Resume mulai dari awal**: server harus menerima `Range`, mengembalikan status 206 dengan `Content-Range` yang cocok, dan validator ETag/Last-Modified tidak boleh berubah. Mengulang dari awal lebih aman daripada menggabungkan byte yang salah.

**Discovery tidak menemukan aset**: URL mungkin halaman dinamis, memerlukan login, atau menyajikan asset melalui JavaScript. Tempel URL langsung file jika tersedia.

**Entrance mengganggu script**: gunakan subcommand langsung atau `novera --no-animation`.
