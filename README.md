# Bali Snack AI — Versi Siap Dipakai (Starter)

Website UMKM jajanan khas Bali dengan Python Flask + SQLite.

## Fitur yang tersedia
- Katalog produk dari database SQLite.
- Pencarian dan filter produk.
- Keranjang, formulir pelanggan, validasi input, dan penyimpanan pesanan.
- Pengurangan stok saat pesanan dicatat.
- Tautan konfirmasi WhatsApp bila nomor bisnis sudah dikonfigurasi.
- Dashboard admin: ringkasan, tambah/edit produk, stok, dan status pesanan.
- Asisten rekomendasi lokal dan generator caption promosi.
- CSRF token untuk formulir, password admin disimpan melalui konfigurasi environment, cookie sesi HttpOnly/SameSite, validasi stok di server.

## 1. Prasyarat
- Python 3.10+
- pip

## 2. Instalasi lokal (Windows)
Ekstrak ZIP, buka terminal di folder proyek, lalu:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Set environment variable untuk sesi terminal PowerShell saat ini. Ganti contoh di bawah dengan nilai rahasia milik Anda:

```powershell
$env:SECRET_KEY = "ganti-dengan-string-acak-panjang"
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "gunakan-password-admin-yang-kuat"
$env:WHATSAPP_NUMBER = "6281234567890"
python app.py
```

Buka http://127.0.0.1:5000

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY='ganti-dengan-string-acak-panjang'
export ADMIN_USERNAME='admin'
export ADMIN_PASSWORD='gunakan-password-admin-yang-kuat'
export WHATSAPP_NUMBER='6281234567890'
python app.py
```

Buka http://127.0.0.1:5000

## 3. Login admin
Buka http://127.0.0.1:5000/admin/login dan masuk dengan username/password yang Anda set melalui environment variable. Jangan gunakan password contoh untuk deployment.

Dashboard admin memungkinkan pemilik:
- menambah produk baru,
- mengubah nama, kategori, harga, deskripsi, emoji, dan stok,
- menonaktifkan produk,
- melihat pesanan dan memperbarui statusnya.

## 4. Konfigurasi WhatsApp
Gunakan nomor bisnis dengan format internasional tanpa tanda + atau spasi, misalnya `6281234567890`. Setelah pelanggan mengirim pesanan, website menyimpan pesanan lalu menampilkan tombol untuk membuka WhatsApp dengan ringkasan pesanan. Pesan baru terkirim setelah pelanggan menekan tombol kirim di WhatsApp. Ini bukan integrasi WhatsApp Business API otomatis.

## 5. Database
SQLite dibuat otomatis di `instance/bali_snack.sqlite3` pada kunjungan pertama. Simpan backup file database secara berkala. Jangan menghapus file ini jika ingin mempertahankan data pesanan dan produk.

## 6. Catatan sebelum dipublikasikan ke internet
Ini adalah starter yang lebih siap untuk uji operasional, tetapi bukan audit keamanan atau layanan hosting yang sudah aktif. Sebelum dipakai secara publik:
1. Tetapkan `SECRET_KEY` acak yang kuat dan password admin unik.
2. Gunakan hosting dengan HTTPS; set `COOKIE_SECURE=1`.
3. Jangan aktifkan debug mode di server publik.
4. Atur backup database dan uji pemulihan.
5. Uji alur pesanan, stok, dan status pada lingkungan staging.
6. Tambahkan kebijakan privasi dan pemberitahuan pengolahan data pelanggan.
7. Untuk banyak transaksi serentak, pertimbangkan PostgreSQL dan proses deployment WSGI seperti Gunicorn/Waitress.
8. Asisten saat ini berbasis aturan, bukan AI generatif. Integrasi AI eksternal membutuhkan API key dan pengamanan tambahan.
9. Harga, stok, ongkir, dan kontak demo harus diganti sesuai usaha sebenarnya.

## Troubleshooting
- Jika port 5000 terpakai, PowerShell: `$env:PORT=5001; python app.py`, lalu buka port 5001.
- Cek kesehatan aplikasi di `/health`.
- Jika lupa password, hentikan server dan atur kembali environment variable `ADMIN_PASSWORD`.
