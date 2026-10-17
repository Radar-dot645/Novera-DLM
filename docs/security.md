# Model keamanan dan batasan

1. URL unduh harus HTTP(S), tidak boleh membawa username/password, dan URL redirect divalidasi. Redirect HTTPS ke HTTP ditolak.
2. Filename dari URL dibatasi ke satu nama file dan dibersihkan. Tujuan yang dihasilkan diperiksa agar tetap di dalam direktori unduhan.
3. Data partial ditulis ke `.part`; metadata resume menyimpan URL dan validator server. Header Range hanya dikirim untuk partial file milik URL yang sama.
4. Unduhan eksternal tidak memakai shell. curl membatasi protokol redirect ke HTTP(S). Backend eksternal punya aturan redirect/resume berbeda; Python HTTP adalah default yang lebih ketat.
5. SHA-256 bukan bukti keaslian secara mandiri. Harus dibandingkan dengan nilai yang didapat dari sumber tepercaya. Bila checksum tidak cocok, hasil Python HTTP dihapus.
6. Riwayat tidak menyimpan nilai query URL mentah; query diganti dengan penanda redaksi.
7. Token API hanya berasal dari environment variable, bukan URL atau config TOML.
8. Novera tidak memasang APK, menjalankan file yang diunduh, atau memerlukan root. APK inspector tidak mengekstrak berkas; ABI dibaca dari direktori ZIP dan metadata richer memakai `aapt` jika tersedia. Nama file hanya petunjuk, bukan bukti ABI.
9. API per-aplikasi F-Droid hanya dipakai untuk memperkaya informasi versi yang ditampilkan. API tersebut bukan sumber verifikasi kriptografis; Novera belum memvalidasi indeks bertanda tangan, tanda tangan APK, atau signer APK secara otomatis.

## Belum termasuk

- Verifikasi tanda tangan GPG, APK certificate, Sigstore atau tanda tangan publisher otomatis.
- Login web, bypass paywall, DRM atau autentikasi browser.
- Crawler / mesin pencari universal.
- Kebijakan SSRF tingkat server. Aplikasi ini ditujukan sebagai program lokal; pengguna tetap bertanggung jawab atas URL yang mereka berikan.

## Logging dan mirror

Log berotasi disimpan secara default di `~/.local/share/novera/novera.log`, dengan target permission direktori/file `0700`/`0600` pada sistem yang mendukungnya. URL query disamarkan sebelum dicatat. `NOVERA_LOG_PATH` dapat mengganti lokasi log. Mirror harus dikonfigurasi secara eksplisit dan tidak digunakan untuk menurunkan sumber HTTPS ke HTTP. Backend eksternal tidak diam-diam diganti jika pengguna memilihnya manual.
