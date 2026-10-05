# Deteksi Dini Degradasi Kipas DC Berbasis *Edge AI* dari Sidik Jari Arus

Sistem pemantau kondisi kipas pendingin **DC 12 V** yang berjalan sepenuhnya di **ESP32-S3**. Kondisi kipas diklasifikasikan secara waktu-nyata oleh model jaringan saraf terkuantisasi (int8), **hanya dari riak arus catu** yang diukur sensor **INA226**. Tujuannya mendeteksi penyebab degradasi, yaitu ketidakseimbangan bilah dan hambatan aliran udara, sebelum bantalan rusak.

**Latar belakang singkat.** Pada sistem kelistrikan DC, kipas dan pompa adalah satu-satunya komponen yang mengalami keausan mekanis. Degradasinya berlangsung perlahan dan mempercepat dirinya sendiri, karena umur bantalan turun secara logaritmik terhadap kenaikan suhu (SEPA Europe; NMB Technologies). Lokasi pemasangan seperti panel kendali, rak perangkat, dan PLTS sering tidak memiliki koneksi internet. Karena itu, inferensi harus dilakukan langsung di perangkat.

---

## Daftar Isi

1. [Spesifikasi Rancangan](#spesifikasi-rancangan)
2. [Kelas Klasifikasi](#kelas-klasifikasi)
3. [Rancangan Eksperimen](#rancangan-eksperimen)
4. [Perangkat Keras](#perangkat-keras)
5. [Struktur Repositori](#struktur-repositori)
6. [Cara Penggunaan](#cara-penggunaan)
7. [Catatan Teknis](#catatan-teknis)
8. [Pemecahan Masalah](#pemecahan-masalah)
9. [Progres dan Log Eksperimen](#progres-dan-log-eksperimen)
10. [Catatan Revisi terhadap Proposal Rev. 2](#catatan-revisi-terhadap-proposal-rev-2)

---

## Spesifikasi Rancangan

| Aspek | Keputusan |
|---|---|
| Domain | **DC 12 V** (disetujui dosen pembimbing) |
| Mikrokontroler | ESP32-S3 (DevKitC-1 atau setara) |
| Sensor | **INA226**, alamat I²C `0x44`, *shunt* bawaan **0,1 Ω** (R100) |
| Objek uji | Kipas **Hanaya FAN5010DC**: 50×50×10 mm, *brushless*, 12 V / 0,09 A, 2 kabel (tanpa tacho), **7 bilah**. Total 10 unit (U01–U10) |
| Resolusi arus | 2,5 µV/LSB ÷ 0,1 Ω = **25 µA/LSB**; batas ukur 0,819 A |
| Jumlah kelas | **4** (cadangan: 3 kelas bila kelas Aliran Terhambat tidak terpisah) |
| Ciri | Spektrum FFT dengan ***order tracking*** (orde putaran, bukan Hz absolut) + statistik riak |
| Model | MLP kecil, kuantisasi int8, ESP-NN / ESP-DSP |
| Validasi | **Antar-sesi** dan ***leave-one-unit-out*** (LOUO). Tidak memakai pembagian acak per jendela, karena menyebabkan kebocoran data. |
| Pembanding | Metode ambang batas I<sub>RMS</sub> pada data uji yang sama |

**Target kinerja**

- Latensi inferensi < 5 ms; *end-to-end* < 300 ms (jendela 256 ms). Jendela boleh diperpanjang hingga ~1 s bila SNR memerlukan, karena fenomenanya berskala minggu.
- Akurasi dua tingkat: ≥ 90 % antar-sesi (unit sama) dan ≥ 80 % LOUO.
- *Recall* kelas gangguan ≥ 90 %; alarm palsu ≤ 5 %; unggul ≥ 20 poin atas metode ambang batas.
- Ukuran model < 25 KB; enklosur ≤ 110 × 75 × 45 mm.

**Alternatif yang dipertimbangkan dan tidak dipilih:** *shunt* 0,01 Ω dan 0,05 Ω (0,05 Ω disimpan sebagai cadangan); domain 220 V AC; PZEM-004T (hanya RMS ~1 Hz); sistem PLTS + JK-BMS (tidak portabel); kipas 120 mm; kipas 5 V; selotip sebagai massa tambahan.

---

## Kelas Klasifikasi

| # | Kelas | Cara pembuatan | Tingkat | Tanda tangan yang diharapkan |
|---|---|---|---|---|
| 1 | **Sehat** | Kipas apa adanya | — | Puncak orde 1×, orde bilah, dan komutasi bersih |
| 2 | **Tidak Seimbang** | Kawat solder Ø1 mm (~6,7 mg/mm) di akar satu bilah, direkatkan lem CA | 5/10/15 mm = 33/67/100 mg | Puncak orde 1× naik; arus rata-rata praktis tidak berubah, sehingga tidak terdeteksi metode ambang batas |
| 3 | **Aliran Terhambat** | Templat karton di sisi hisap | Tertutup 25/50/75 % | Derau pita lebar naik, puncak bilah melebar; arus diperkirakan sedikit turun (kipas aksial, *belum diverifikasi*) |
| 4 | **Tidak Dikenal** | Kipas mati, beban non-motor (resistor/LED), masa transisi, dua kipas sekaligus | — | — |

Setiap kelas direkam dengan **sapuan PWM 40–100 %** agar rentang arus antar kelas saling tumpang tindih. Kondisi ini dipakai untuk menunjukkan keterbatasan metode ambang batas.

**Di luar kelas model:**
- **Bilah dipatahkan**: hanya untuk uji kewajaran *pipeline* (kerusakan besar harus tampak jelas di FFT), dilaporkan dalam satu tabel.
- **Operasi 24 jam**: pengamatan kestabilan jangka panjang (opsional), menambah data Sehat lintas waktu.
- Kelas "Bantalan Kering" dibatalkan karena pelumas bantalan pada kipas ini tidak dapat dibersihkan.

---

## Rancangan Eksperimen

### Matriks unit (10 unit)

Urutan per unit: rekam Sehat → rekam blokade 25/50/75 % (reversibel) → lepas blokade → (jalur A saja) tambah massa bertahap.
**Semua unit direkam dalam kondisi Sehat terlebih dahulu** sebelum perlakuan permanen apa pun.

| Jalur | Unit | Perlakuan | Kelas |
|---|---|---|---|
| A | 4 | Sehat → blokade → massa 33 → 67 → 100 mg | 1, 3, 2 |
| B | 3 | Sehat → blokade | 1, 3 |
| C | 1 | Sehat → bilah dipatahkan | 1 + validasi *pipeline* |
| E | 2 | Tidak diberi perlakuan | 1; kontrol sekaligus cadangan |
| D | (opsional) | Sehat, operasi 24/7 | Memakai salah satu unit E |

Cakupan: Sehat 10 unit, Aliran Terhambat 7 unit (A+B), Tidak Seimbang 4 unit (A). Minimal 3 unit per kelas gangguan diperlukan agar validasi LOUO bermakna.

### Gerbang kelayakan (sebelum tahap pembelajaran mesin)

1. Rekam 6–8 kipas **sehat** yang berbeda, lalu tumpuk spektrumnya untuk melihat pita sebaran antar unit.
2. Rekam 1 kipas dengan massa 100 mg dan periksa apakah puncak orde 1× keluar jelas dari pita tersebut.
3. Hitung *effect size* tiap ciri: `d = |μ_gangguan − μ_sehat| / σ_antar-unit-sehat`. **Lulus bila beberapa ciri memiliki d > 2.**
4. Bila tidak lulus: perbesar massa, atau gunakan skema 3 kelas.

### Konvensi penamaan rekaman

`{kelas}_u{NN}_pwm{duty}[_s{sesi}]`, contoh: `sehat_u01_pwm100`, `massa067_u03_pwm70`, `blok50_u05_pwm100_s2`, `unknown-mati_u00`.

---

## Perangkat Keras

```
ESP32-S3            INA226 (0x44)
3V3   ────────────  VCC      (maks. 5,5 V; JANGAN 12 V)
GND   ────────────  GND
GPIO8 ────────────  SDA
GPIO9 ────────────  SCL
GPIO7 ────────────  ALERT    (open-drain, INPUT_PULLUP)

12 V (+) ── IN+
            IN− ──┬── kipas (+)
            VBUS ─┘   (input pengukur tegangan, boleh 12 V)
12 V (−) ──┬───────── kipas (−)
           └── GND ESP32   (ground bersama WAJIB)
```

Kapasitor elektrolit 1000 µF dipasang pada keluaran catu daya, **sebelum *shunt***. Kapasitor besar tidak boleh dipasang paralel dengan kipas setelah *shunt*, karena riak arus akan mengalir lewat kapasitor, bukan lewat *shunt*.

---

## Struktur Repositori

```
firmware/00_diagnosa_i2c/    Scan I²C 100 kHz & 400 kHz + pembacaan ID di tiap alamat
firmware/01_ina226_cek/      Verifikasi ID chip + pembacaan arus lambat (AVG=16, 115200 baud)
firmware/02_ina226_capture/  Akuisisi burst 8192 sampel via ALERT, keluaran CSV (921600 baud, perintah 'c')
tools/capture_fft.py         Rekam dari serial → CSV di data/ → plot domain waktu + FFT; --compare untuk overlay
tools/serial_log.py          Pembacaan serial selama N detik (non-interaktif)
docs/                        Proposal Rev. 2, ringkasan keputusan terdahulu, laporan analisis, foto komponen
tools/overlay_orde.py        Overlay spektrum orde antar unit + tabel sebaran ciri (gerbang kelayakan)
data/                        Rekaman CSV + grafik PNG
```

---

## Cara Penggunaan

```bash
pip install -r tools/requirements.txt

# Kompilasi & unggah dengan arduino-cli (atau gunakan Arduino IDE)
arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/01_ina226_cek
arduino-cli upload  --fqbn esp32:esp32:esp32s3 -p <PORT> firmware/01_ina226_cek
#   Bila memakai port USB native, tambahkan opsi :CDCOnBoot=cdc pada fqbn

# Baca keluaran sketch 01
python tools/serial_log.py --port <PORT> --seconds 10 --reset

# Rekam + FFT (sketch 02 harus sudah diunggah, Serial Monitor ditutup)
python tools/capture_fft.py --port <PORT> --label sehat_u01_pwm100
python tools/capture_fft.py --compare data/sehat_u01*.csv data/sehat_u02*.csv
python tools/capture_fft.py --file data/<nama>.csv --noshow
```

**Penyimpanan data mentah:** file CSV rekaman tidak disimpan di repositori (lihat `.gitignore`), melainkan di Google Drive (`My Drive/proyek-kipas-edge-ai-data/`, struktur folder sama dengan `data/`). Repositori hanya memuat kode, dokumentasi, dan grafik PNG. Sinkronisasi setelah merekam:

```powershell
robocopy data "G:\My Drive\proyek-kipas-edge-ai-data" *.csv /S /XO
```

**Lingkungan pengembangan:** Windows 11, arduino-cli 1.5.1, core `esp32:esp32` 3.3.12, Python 3.13. Papan ESP32-S3 terhubung melalui USB-serial CH343 (port UART).

---

## Catatan Teknis

- **Alamat INA226 = `0x44`** pada modul ini (hasil scan). Alamat 0x40 menghasilkan NACK (`endTransmission` kode 4).
- Pembacaan register memakai **`endTransmission()` dengan STOP penuh**, bukan *repeated start*. INA226 menyimpan *register pointer*, dan cara ini kompatibel di semua versi core ESP32.
- Register: `0x00` konfigurasi, `0x01` *shunt* (int16, 2,5 µV/LSB), `0x02` bus (1,25 mV/LSB), `0x06` mask/enable, `0xFE` = `0x5449`, `0xFF` = `0x2260`.
- Mode akuisisi: config = `0x4000 | (VSHCT<<3) | 0x5` (*shunt* kontinu). **AVG = 1 wajib**, karena *averaging* internal bekerja sebagai tapis lolos-rendah yang menghapus riak.
- *Conversion Ready*: mask/enable `0x0400` (CNVR) membuat ALERT turun setiap konversi selesai. Membaca `0x06` menghapus *flag*, sehingga dibutuhkan 2 transaksi I²C per sampel.
- **Urutan baca: `0x06` (hapus *flag*) dulu, baru *shunt*.** Jika urutannya terbalik, *flag* konversi berikutnya ikut terhapus sehingga setiap konversi kedua hilang secara teratur (terukur 597 µs/sampel). Pola teratur ini tidak terdeteksi oleh pemeriksaan celah berbasis median. Karena itu, `capture_fft.py` memakai hitungan `#missed` yang dilaporkan ESP32.
- **Laju cuplik terukur: 3030 SPS** (VSHCT 332 µs, I²C **1 MHz**, 0 konversi terlewat). Pada 400 kHz, batas resmi INA226, dua transaksi I²C membutuhkan ~454 µs, lebih lama dari satu konversi. Pengoperasian 1 MHz berada di luar spesifikasi resmi tetapi terbukti stabil secara empiris. Kipas 5 cm dapat mencapai 3.500–5.500 RPM (komutasi hingga ~1,1 kHz), sehingga frekuensi Nyquist harus > ~1,2 kHz. Laju 4,9 kSPS (VSHCT 204 µs) belum diuji.
- ***Aliasing*:** INA226 tidak memiliki tapis anti-*alias* (hanya integrasi selama waktu konversi). Harmonik ke-5 dan seterusnya dari 321 Hz terlipat ke bawah frekuensi Nyquist. Saat sapuan PWM, komponen *alias* bergerak berlawanan arah dengan orde sebenarnya, sehingga ciri *order tracking* dibatasi pada orde di bawah Nyquist.
- Bila SNR kurang: perpanjang FFT (1024 → 4096 memberi +6 dB dan Δf lebih halus) atau gunakan rata-rata Welch.
- Catu daya terbaik untuk pengambilan data adalah aki/baterai 12 V, karena adaptor *switching* murah menambah derau.

---

## Pemecahan Masalah

| Gejala | Kemungkinan penyebab |
|---|---|
| Scan tidak menemukan perangkat | SDA/SCL tertukar, VCC tidak tersambung, kabel longgar |
| `endTransmission` kode 2/4 saat baca register | Alamat salah (modul ini 0x44) atau I²C terlalu cepat untuk *pull-up* → coba 100 kHz |
| ID bukan 0x5449/0x2260 | Bukan INA226 (mis. INA219) |
| Arus bernilai negatif | IN+ / IN− tertukar |
| Arus 0 padahal kipas berputar | Arus kipas tidak melewati *shunt* |
| Tegangan bus 0 V padahal arus benar | VBUS tidak tersambung (boleh diabaikan) |
| Sketch 02 `#ERROR timeout` | ALERT tidak tersambung → set `USE_ALERT_PIN 0` |
| Konversi terlewat > 0 | I²C tidak sempat → naikkan `I2C_HZ` atau perbesar `VSHCT_CODE` |
| Python: "Tidak menerima data" | Serial Monitor masih terbuka atau port salah |
| Unggah gagal | Tahan BOOT, tekan RESET, lepas BOOT, unggah ulang |

---

## Progres dan Log Eksperimen

**Langkah berikutnya:** (1) rekam U05–U10 kondisi Sehat (kipas baru: inreyen 30 menit dulu); (2) rangkaian PWM untuk sapuan 40–100 % — data Sehat pada berbagai *duty* harus terkumpul **sebelum** perlakuan permanen (massa) pada unit jalur A. Pengukuran RPM dengan stroboskop masih tertunda.

- [x] Perakitan perangkat keras (ESP32-S3 + INA226 + kipas 12 V).
- [x] Scan I²C: INA226 terdeteksi di **0x44**.
- [x] **27-09-2026: Verifikasi sensor.** Manufacturer ID 0x5449 dan Die ID 0x2260 sesuai. Tanpa beban: *shunt* ≈ −0,010 mV (≈ −0,1 mA), masih dalam spesifikasi *offset* ±10 µV.
- [~] **Verifikasi arus.** Dengan catu 12 V: tegangan bus 12,72 V, arus ≈ 74 mA, polaritas benar.
  - **28-09-2026:** multimeter ZOTEK ZT102 (DC mA, seri) membaca **84,0 mA** pada U01; INA226 pada saat berdekatan membaca **73,0 mA** (12,721 V). Selisih **+15 %**, jauh di atas akurasi multimeter (~±1 %). Penyebab belum diketahui: pengukuran belum serentak, atau nilai *shunt* efektif ≠ 0,1 Ω (bila INA226 benar membaca 7,3 mV, *shunt* efektif ≈ 0,087 Ω). Uji penentu: ukur mV DC langsung di IN+/IN− bersamaan dengan pembacaan INA226.
  - **28-09-2026:** mV DC di terminal IN+/IN− = **8,89 mV**; INA226 pada saat yang sama = 73,16 mA (**7,32 mV** di pin sensor), stabil antar pengukuran. Dengan arus sebenarnya ≈ 84 mA: hambatan antar-terminal ≈ 0,106 Ω, hambatan yang terbaca INA226 ≈ **0,087 Ω**. Dugaan: nilai resistor *shunt* di bawah label; selisih 19 mΩ = hambatan kontak terminal + jalur PCB. Belum final. Data mentah (LSB) tersimpan, sehingga koreksi kalibrasi (`--rshunt`) dapat diterapkan ulang ke seluruh rekaman.
  - **Keputusan (29-09-2026):** proyek dilanjutkan dengan **skala INA226 apa adanya** (R = 0,1 Ω nominal). Klasifikasi tidak terpengaruh karena selisihnya berupa faktor skala konstan pada satu sensor. Syarat: **satu modul INA226 yang sama dipakai dari pengambilan data hingga demo**; bila modul diganti, verifikasi multimeter diulang. Di laporan, nilai arus dinyatakan dalam skala INA226 dengan catatan selisih ±15 % terhadap multimeter.
- [x] **28-09-2026: Dudukan kipas terstandar.** Pada dudukan baru, fundamental U01 = **327,0 Hz** (sebelumnya 321 Hz di atas alas), konsisten dengan dugaan bahwa posisi lama sedikit menghambat aliran udara.
- [x] **28-09-2026: Spektrum pertama** (`data/sehat_u01_pwm100_20260928-003938`). Laju 3030 SPS, 0 terlewat. DC 73,0 mA, riak RMS 4,29 mA (5,9 %), riak p-p 26 mA, lantai derau 44 µA, SNR 34,9 dB. Terdapat deret harmonik jelas dengan fundamental **321,1 Hz** (642/963/1284 Hz); harmonik ≥ 5 ter-*alias*. Terdapat pula pita sisi ±14,7 Hz (asal belum diketahui) dan puncak 160,5 Hz (½ × 321 Hz). Kecepatan stabil selama rekaman (321,1 → 319,6 Hz).
- [x] **28-09-2026: Identifikasi kipas.** FAN5010DC, 12 V / 0,09 A, 2 kabel, 7 bilah. Arus terukur 73 mA = 81 % rating.
- [x] **28-09-2026: Kapasitor 1000 µF pada catu daya** (saran dosen pembimbing). Data menunjukkan posisinya sebelum *shunt*: riak RMS tetap 4,29 → 4,30 mA. Lantai derau 44 → 40 µA (belum dapat dipastikan bermakna). Sejak sesi s2, setiap rekaman mencatat tegangan bus (`#vbus_V`).
- [x] **29-09-2026: U01 sesi s3 (dudukan terstandar, 2 rekaman berurutan).** 331,1 / 330,3 Hz; 72,91 / 72,84 mA; riak RMS 4,40 / 4,44 mA; 12,722 V. Pengulangan dalam satu sesi konsisten. Fundamental U01 cenderung naik sepanjang waktu nyala (321 → 327 → 331 Hz). Dugaan: pemanasan bantalan (belum diverifikasi). Perlu diuji apakah waktu pemanasan standar diperlukan sebelum merekam.
- [x] **29-09-2026: Uji pemanasan U02** (rekam pada t = 30–600 s setelah dinyalakan, 12,722 V):

  | t (s) | 30 | 60 | 120 | 180 | 300 | 420 | 600 |
  |---|---|---|---|---|---|---|---|
  | f₁ (Hz) | 304,4 | 310,0 | 316,3 | 312,9 | 317,4 | 320,0 | 306,7 |
  | I (mA) | 75,74 | 75,29 | 74,79 | 74,85 | 74,61 | 74,56 | 75,11 |

  Temuan: (1) kecepatan naik ~4 % dalam 2 menit pertama, lalu berfluktuasi 313–320 Hz; (2) terdapat penurunan sesaat (t = 180 s dan 600 s) yang **selalu disertai kenaikan arus**, menandakan perubahan beban mekanis/aerodinamis; (3) dalam satu rekaman 2,7 s, kecepatan dapat bergeser hingga 4 Hz. Penyebab penurunan sesaat belum diketahui (kandidat: aliran udara ruangan, gesekan bantalan *stick-slip*). Implikasi: kecepatan kipas sehat bervariasi ±3 %, sehingga ciri berbasis orde (*order tracking*) diperlukan. Penurunan kecepatan + kenaikan arus menyerupai tanda Aliran Terhambat, sehingga **lingkungan aliran udara harus dikendalikan** saat merekam. Usulan sementara: pemanasan ≥ 3 menit sebelum merekam.
  - Selama uji ini (dan rekaman U01) terdapat **kipas angin ruangan berayun** di dekat meja uji, yang diduga kuat menyebabkan penurunan kecepatan sesaat. Rekaman U01 s1–s3 dan U02 s3 ditandai **berpotensi terpengaruh angin**. Uji pembuktian (U02, 5 rekaman berurutan dengan kipas angin mati) belum dilakukan.
- [x] **05-10-2026: U01 sesi s4, 150 rekaman beruntun** (~4 s/rekaman, ±10 menit sejak kipas dipasang; kipas angin ruangan **mati**; 12,716–12,719 V; 0 konversi terlewat). Mode rekam beruntun ditambahkan ke `capture_fft.py` (`--count`, `--note`; metadata `batch_t_s` dan `catatan`).

  | Selang waktu | n | f₁ (Hz) | I (mA) |
  |---|---|---|---|
  | 0–60 s | 14 | 316,2 ± 5,9 | 74,05 ± 0,54 |
  | 60–180 s | 30 | 325,0 ± 1,2 | 72,92 ± 0,20 |
  | 180–360 s | 45 | 325,6 ± 5,7 | 72,67 ± 0,25 |
  | 360–700 s | 61 | 325,3 ± 4,8 | 72,62 ± 0,24 |

  Temuan: (1) pemanasan ±1 menit (f₁ naik, arus turun); (2) setelah 60 s, kecepatan tetap bervariasi **±1,4 %** (313–337 Hz) dan **berkorelasi negatif kuat dengan arus (r = −0,84)**, walaupun kipas angin ruangan mati. Dugaan bahwa fluktuasi disebabkan angin ruangan **tidak didukung data**; fluktuasi beban tampaknya bersifat intrinsik pada kipas (penyebab belum diketahui). Variasi ini menjadi bagian data latih kelas Sehat dan memperkuat alasan pemakaian ciri berbasis orde.
- [x] **05-10-2026: U02 sesi s4, 150 rekaman beruntun** (kondisi sama dengan U01 s4; 0 konversi terlewat).

  | Selang waktu | n | f₁ (Hz) | I (mA) |
  |---|---|---|---|
  | 0–60 s | 14 | 302,5 ± 2,5 | 76,54 ± 0,43 |
  | 60–180 s | 30 | 313,1 ± 3,6 | 75,22 ± 0,27 |
  | 180–360 s | 44 | 316,4 ± 3,8 | 74,74 ± 0,18 |
  | 360–700 s | 62 | 312,5 ± 4,8 | 74,98 ± 0,23 |

  Perbandingan setelah pemanasan (> 60 s): U01 = 325,3 ± 4,6 Hz / 72,7 mA; U02 = 313,9 ± 4,6 Hz / 75,0 mA. Kedua unit menunjukkan variasi kecepatan ±1,5 % dengan korelasi kecepatan–arus yang sama (r = −0,84) dan rasio riak/DC yang hampir identik (6,0 %). Perbedaan antar unit (±12 Hz, ±2,3 mA) lebih besar daripada variasi dalam satu unit, sehingga identitas unit berpotensi dipelajari model; hal ini harus dikendalikan melalui validasi LOUO dan ciri berbasis orde.
- [x] **05-10-2026: Inreyen dan rekaman U03.** U03 dan U04 adalah kipas baru (belum pernah dinyalakan), sehingga diberi masa inreyen ±30 menit sebelum direkam sebagai data Sehat. 67 rekaman pertama U03 (±4,5 menit sejak pertama kali menyala) disimpan dengan label `runin_u03` (bukan data Sehat): f₁ naik 249 → 328 Hz dalam ±1,5 menit, arus turun 85,3 → 78,8 mA dan masih menurun perlahan. Setelah inreyen, 150 rekaman `sehat_u03_pwm100_s4` (U04 tidak terpasang).

  Ringkasan kondisi Sehat setelah pemanasan (sesi s4):

  | Unit | n | f₁ (Hz) | Variasi f₁ | I (mA) | Riak/DC | r(f₁, I) |
  |---|---|---|---|---|---|---|
  | U01 | 136 | 325,3 ± 4,6 | 1,4 % | 72,70 ± 0,26 | 6,02 % | −0,84 |
  | U02 | 136 | 313,9 ± 4,6 | 1,5 % | 74,95 ± 0,29 | 5,97 % | −0,84 |
  | U03 | 150 | 331,1 ± 1,5 | 0,5 % | 78,34 ± 0,07 | 5,88 % | −0,88 |

  Rasio riak/DC konsisten antar unit (5,9–6,0 %), sedangkan kecepatan dan arus rata-rata berbeda nyata antar unit. U03 (baru) jauh lebih stabil dibanding U01/U02; penyebabnya belum diketahui.
- [x] **05-10-2026: Data mentah dipindahkan ke Google Drive** (316 CSV, 33,7 MB; jumlah file terverifikasi sama).
- [x] **06-10-2026: U04 sesi s4, 150 rekaman** (setelah inreyen 30 menit terpisah tanpa INA226). Setelah pemanasan: f₁ 326,9 ± 2,0 Hz, I 74,82 ± 0,07 mA, riak/DC 5,92 %.
- [~] **06-10-2026: Gerbang kelayakan langkah 1 (4 dari 6–8 unit Sehat)** — laporan lengkap: [`docs/analisis-gerbang-kelayakan-1.md`](docs/analisis-gerbang-kelayakan-1.md); skrip `tools/overlay_orde.py`, grafik `data/gerbang_spektrum_orde.png` dan `data/gerbang_f1_vs_arus.png`; 136–150 rekaman per unit setelah pemanasan.
  - Spektrum yang dinormalisasi ke orde f₁ sangat serupa antar unit pada orde bulat (1, 2, 3, 4 × f₁).
  - Terdapat puncak di **kelipatan ¼ f₁** (0,5; 0,75; 1,25; 1,75; 2,25; 2,75). Ini mendukung hipotesis (a): f₁ = 4 × frekuensi putaran, sehingga **putaran ≈ f₁/4 ≈ 78–83 Hz (≈ 4.700–5.000 RPM)**. Belum dikonfirmasi stroboskop/uji massa.
  - Amplitudo di orde ¼ f₁ (kandidat **1× putaran**, tanda tangan Tidak Seimbang): 0,077 / 0,076 / 0,090 / 0,085 mA (U01–U04), σ antar-unit **0,007 mA**, σ dalam-unit ≈ 0,02 mA, lantai derau ≈ 0,04 mA. Garis dasar yang rendah dan seragam ini menjanjikan untuk mendeteksi massa tambahan.
  - Sebaliknya, orde ½ f₁ (0,21–0,98 mA) dan 1½ f₁ (0,22–0,80 mA) sangat berbeda antar unit, begitu pula arus rata-rata (σ antar-unit 2,33 mA vs σ dalam-unit 0,17 mA; keempat unit terpisah sempurna pada sumbu arus). Ciri-ciri ini berpotensi menjadi **sidik jari unit**, sehingga harus diwaspadai dalam pemilihan ciri dan diuji melalui LOUO.
- [ ] **Pergeseran kecepatan U01 sesi s2.** Rekaman 01:01 menunjukkan 309,6 Hz / 74,3 mA, sedangkan satu menit kemudian 321,8 Hz / 73,2 mA pada 12,716 V. Putaran lebih lambat disertai arus lebih tinggi mengindikasikan beban mekanis sesaat (dugaan: aliran udara terhalang oleh posisi kipas, belum dikonfirmasi). Tindak lanjut: dudukan kipas yang terstandar.
- [ ] **Penetapan orde 1× (RPM).** Hipotesis dari spektrum U01: (a) 321 Hz = 4 komutasi/putaran → **4.816 RPM** (80,3 Hz; orde bilah 7× di 562 Hz hanya +11,6 dB), paling masuk akal untuk kipas 5010; (b) 2 komutasi/putaran → 9.633 RPM (kecil kemungkinan); (c) 6 komutasi/putaran → 3.211 RPM (tidak ada orde 2×). Perlu verifikasi stroboskop atau uji massa.
- [ ] Uji bilah patah (validasi *pipeline* sekaligus konfirmasi orde 1×).
- [ ] Gerbang kelayakan (6–8 unit sehat + massa 100 mg, Cohen's *d*).
- [ ] Rangkaian PWM (MOSFET *logic-level*, mis. IRLZ44N) untuk sapuan 40–100 %.
- [ ] Pengumpulan data lengkap → pelatihan → kuantisasi → implementasi → pengujian dua tingkat.
- [ ] Proposal Revisi 3.

Rekaman uji laju cuplik yang tidak valid disimpan terpisah di `data/_uji_i2c/` beserta keterangannya.

---

## Catatan Revisi terhadap Proposal Rev. 2

`docs/proposal-rev2.md` dan `docs/ringkasan-keputusan-lama.md` tetap relevan untuk latar belakang dan dasar teori. Bagian berikut telah diperbarui:

- Kelas "Bantalan Kering" → diganti **Aliran Terhambat**.
- Kipas 120 mm / contoh 2.000 RPM → **kipas 5 cm, 3.500–5.500 RPM**.
- 2 kSPS / FFT 512 → **3030 SPS terukur**, FFT ≥ 1024.
- Alamat I²C 0x40 → **0x44**.
- I²C 1 MHz sebagai asumsi → batas resmi 400 kHz; 1 MHz dipakai setelah diverifikasi empiris.
- Target akurasi tunggal ≥ 90 % → **dua tingkat** (90 % antar-sesi / 80 % LOUO).
- "Aliran tertutup → arus naik" → untuk kipas aksial kemungkinan **turun**.

**Materi Revisi 3:** pemilihan kipas 5 cm beserta alasannya; laju cuplik aktual; 4 kelas + skema cadangan 3 kelas; *order tracking*; massa dan blokade bertingkat (dua kurva sensitivitas); matriks unit + LOUO; gerbang kelayakan; skenario demo tiga babak (konsistensi lintas unit, diagnosis, perbandingan ambang batas vs AI); serta jawaban atas pertanyaan "bagaimana memastikan model mengenali gangguan, bukan identitas unit kipas?".
