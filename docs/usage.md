# Penggunaan

Jalankan `novera` untuk entrance dan menu interaktif. `0 · Exit` mengembalikan kontrol ke shell karena aplikasi berakhir normal. `Ctrl+C` saat menu akan membatalkan aksi saat ini atau keluar secara aman tergantung tahap aplikasi.

## Download

Menu **Download URL** menerima HTTP(S), opsi nama file, SHA-256 tepercaya, dan pilihan backend. Progress menyediakan byte, kecepatan, serta ETA saat ukuran diketahui. Kebijakan default untuk file yang sudah ada adalah membuat nama baru seperti `file (1).zip`.

## Discovery

Menu **Discover / List** menerima URL repo, release, halaman unduhan atau direct asset. Aset yang dideteksi ditampilkan dengan nama penuh dan metadata yang membungkus mengikuti lebar terminal. Daftar panjang dipaginasi: ketik nomor aset pada halaman aktif untuk memilih, `n` untuk halaman berikutnya, `p` untuk sebelumnya, atau `q` untuk kembali. URL GitHub `owner/repo/releases` menampilkan semua release yang terpublikasi (maksimum 1.000 release per sesi discovery untuk membatasi permintaan API); `owner/repo/releases/latest` dan `owner/repo/releases/tag/VERSI` tetap membatasi hasil pada release yang ditentukan. Saat berpindah layar, Novera membersihkan tampilan terminal interaktif. Pencarian global berbasis query bukan fitur versi ini; tempel URL sumber yang spesifik.

## Batch

Satu URL per baris, komentar dimulai dengan `#`. Kegagalan satu URL dicatat sendiri dan tidak menghentikan seluruh antrean.

## Exit

Pilih `0` atau tekan Ctrl+C di menu. Proses Novera berhenti; tidak ada shell baru atau loop yang mengambil alih prompt Termux.

## Inspeksi APK lokal

Menu `9 · Inspect APK` atau `novera inspect-apk app.apk` memeriksa ZIP container, `AndroidManifest.xml`, dan direktori ABI native dari isi berkas. Bila `aapt` tersedia, Novera juga mengambil package, version code/name, min SDK, target SDK, dan ABI yang dilaporkan tool. Tanpa `aapt`, informasi manifest dapat tetap unknown. Berkas `.apks`, `.xapk`, dan `.apkm` ditandai sebagai container/split package dan tidak diperlakukan sebagai APK tunggal. Tidak ada APK yang dipasang atau dijalankan.
