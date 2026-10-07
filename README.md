# IHSG Paper Lab: 5 varian (3 swing + 2 scalp), modal paper Rp100 jt per varian

## Setup GitHub (sekali, ±15 menit)
1. Buat repo **baru** (Public), misal `ihsg-lab`. Upload SEMUA isi zip (Add file → Upload files → drag semua file & folder → Commit).
2. Cek folder `.github/workflows/update-data.yml` ikut ter-upload (folder berawalan titik sering tertinggal).
   Kalau tidak ada: Add file → Create new file → nama `.github/workflows/update-data.yml` → tempel isi file → Commit.
3. **Settings → Pages → Build and deployment → Source: `GitHub Actions`** (BUKAN "Deploy from a branch").
4. Tab **Actions** → kalau diminta, klik "I understand… enable workflows" → pilih **update-data** → **Run workflow**.
   Run pertama ±5–15 menit (unduh 3 tahun data semua emiten). Centang hijau = selesai.
5. Link aplikasi muncul di Settings → Pages: `https://USERNAME.github.io/ihsg-lab/` → buka di HP → Add to Home Screen.
6. Excel: Control!B4 = link tersebut (akhiri `/`) → Ctrl+Alt+F9.

## Jadwal otomatis (WIB, Senin–Jumat)
Tiap 30 menit 09:00–15:30 · 14:45 (data untuk review 15:00) · 16:40 (penutupan final → sinyal swing besok).
GitHub bisa menunda jadwal 5–30 menit. Jadwal otomatis dinonaktifkan GitHub bila repo tidak ada aktivitas 60 hari.
Buka tab Actions dan aktifkan lagi kalau berhenti.

## Isi repo
| Path | Fungsi |
|---|---|
| `index.html`, `manifest.webmanifest`, `sw.js`, `icon-*.png` | Aplikasi HP |
| `ihsg_lab/config.py` | Modal, fee Ajaib, tanggal forward, parameter 5 varian, universe scalp |
| `ihsg_lab/engine.py` | Engine: fraksi harga BEI, lot 100, fee beli/jual, slippage 1 tick, SL/TP/trailing/time stop, flat EOD |
| `ihsg_lab/data.py` | Yahoo Finance (.JK) + cache; daftar emiten dari idx.co.id (fallback `universe.txt`) |
| `ihsg_lab/build_site.py` | Backtest → OOS → paper forward → screener semua emiten → `data/` |
| `ihsg_lab/universe.txt` | Daftar emiten cadangan. Tempel seluruh kode BEI (±950) kalau idx.co.id memblokir bot |
| `ihsg_lab/research.json` | Riset & kalender hari berikutnya (edit di GitHub, tampil di tab Review) |
| `data/` | Contoh output DEMO (sintetis). Ditimpa data asli setelah Actions jalan |

## Batasan
Data Yahoo tertunda (bukan tick real-time). Ajaib tidak punya API trading publik: eksekusi manual / auto-order broker.
Long-only; ARB/ARA, suspensi, papan pemantauan khusus, dan T+2 tidak dimodelkan. Alat simulasi, bukan rekomendasi efek.
