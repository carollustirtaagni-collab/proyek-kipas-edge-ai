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
| Objek uji | Kipas **Hanaya FAN5010DC**: 50×50×10 mm, *brushless*, 12 V / 0,09 A, 2 kabel (tanpa tacho), **7 bilah**. 10 unit utama (U01–U08, U10, U11) + U09 cadangan; terdapat dua tipe karakteristik arus (A dan B), lihat log 16-10-2026 |
| Resolusi arus | 2,5 µV/LSB ÷ 0,1 Ω = **25 µA/LSB**; batas ukur 0,819 A |
| Jumlah kelas | Rencana 4; **dipakai skema 3 kelas** (Sehat, Aliran Terhambat, Tidak Dikenal) karena kelas Tidak Seimbang tidak lulus gerbang kelayakan (keputusan 19-10-2026) |
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
| 2 | **Tidak Seimbang** | Kawat **tembaga Ø0,9 mm** (±5,7 mg/mm, dihitung dari diameter dan massa jenis 8,96 g/cm³) di akar satu bilah yang ditandai, direkatkan lem CA; potongan 6 mm ditambahkan berdampingan per tingkat (keputusan 19-10-2026, menggantikan timah solder Ø1 mm yang tidak tersedia) | 6/12/18 mm ≈ **34/68/103 mg** | Puncak orde 1× naik; arus rata-rata praktis tidak berubah, sehingga tidak terdeteksi metode ambang batas |
| 3 | **Aliran Terhambat** | Templat karton berbentuk juring di **sisi tiup** (sisi hisap tidak memiliki penyangga; keputusan 17-10-2026) | Tertutup **50/75 %** (25 % dihapus, keputusan 17-10-2026) | Derau pita lebar naik, puncak bilah melebar; arus diperkirakan sedikit turun (kipas aksial, *belum diverifikasi*) |
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
firmware/03_klasifikasi/     Klasifikasi di perangkat: ciri + FFT 1024 + MLP int8 (model_data.h), kalibrasi per kipas ('k' / tombol BOOT)
tools/capture_fft.py         Rekam dari serial → CSV di data/ → plot domain waktu + FFT; --compare untuk overlay
tools/serial_log.py          Pembacaan serial selama N detik (non-interaktif)
docs/                        Proposal Rev. 2, ringkasan keputusan terdahulu, laporan analisis, foto komponen
tools/overlay_orde.py        Overlay spektrum orde antar unit + tabel sebaran ciri (gerbang kelayakan)
tools/cek_massa.py           Efek massa pada orde putaran (Cohen's d)
tools/fitur.py               Definisi ciri per jendela (acuan firmware)
tools/dataset.py             Penyusunan dataset jendela berlabel → data/fitur_jendela.npz
tools/latih_model.py         Eksperimen model: LOUO, antar-sesi, pembanding ambang batas
tools/ekspor_model.py        Model final + kuantisasi int8 → firmware/03_klasifikasi/model_data.h
tools/evaluasi_final.py      Evaluasi pipeline firmware (int8) dengan LOUO + antar-sesi
tools/cek_firmware.py        Verifikasi kesetaraan ciri & keluaran model firmware vs Python
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
- **Laju cuplik terukur: 3030 SPS (median)** (VSHCT 332 µs, I²C **1 MHz**, 0 konversi terlewat). Catatan 20-10-2026: rata-rata jarak antar sampel 346,7 µs (2884 SPS) karena ±14 % jarak sampel memanjang ke ±440 µs (ESP32 sesekali terlambat membaca); pencuplikan tidak sepenuhnya seragam. Data latih dan firmware klasifikasi memakai definisi yang sama (median), sehingga konsisten. Pada 400 kHz, batas resmi INA226, dua transaksi I²C membutuhkan ~454 µs, lebih lama dari satu konversi. Pengoperasian 1 MHz berada di luar spesifikasi resmi tetapi terbukti stabil secara empiris. Kipas 5 cm dapat mencapai 3.500–5.500 RPM (komutasi hingga ~1,1 kHz), sehingga frekuensi Nyquist harus > ~1,2 kHz. Laju 4,9 kSPS (VSHCT 204 µs) **tidak tercapai**: waktu baca ESP32 ±329 µs per sampel (uji 16-10-2026).
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

**Langkah berikutnya:** gladi demo sesuai [`docs/skenario-demo.md`](docs/skenario-demo.md) (babak 4 dengan U02 belum diuji); penulisan Proposal Revisi 3 / laporan. Opsional: uji beban non-kipas dengan kenaikan arus di rentang blokade (+2–7 %) untuk membandingkan AI dan ambang relatif. Pengukuran RPM dengan stroboskop masih tertunda.

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
- [x] **16-10-2026: Rekaman U05–U11 sesi s4** (7 kipas baru, inreyen 1 jam; 150 rekaman per unit; 0 konversi terlewat; data di Google Drive). U09 direkam ulang 30× (`s4u`) tanpa beban listrik besar lain di jaringan, dengan hasil identik.
- [~] **16-10-2026: Gerbang kelayakan langkah 1 — 11 unit** — laporan: [`docs/analisis-gerbang-kelayakan-2.md`](docs/analisis-gerbang-kelayakan-2.md); grafik `data/gerbang_bentuk_gelombang.png`, `data/gerbang_spektrum_orde.png`, `data/gerbang_f1_vs_arus.png`.
  - Kipas berlabel sama terbagi menjadi **tiga tipe karakteristik arus**: **tipe A** U01–U04 (riak/DC ≈ 6 %, 73–78 mA), **tipe B** U05–U08, U10, U11 (riak/DC ≈ 25 %, 63–65 mA, arus anjlok tajam tiap komutasi), **tipe C** U09 (riak/DC ≈ 10 %, 71 mA).
  - **U09 ditetapkan sebagai unit cadangan**; 10 unit utama: U01–U08, U10, U11.
  - Tipe B mengalami *aliasing* berat (lantai derau ±0,11 mA vs ±0,04 mA tipe A), yang perlu ditangani sebelum sapuan PWM.
  - Usulan pembagian jalur dengan kedua tipe di setiap jalur ada di laporan bagian 5 dan **menunggu persetujuan dosen pembimbing**.
- [x] **16-10-2026: Keputusan pembagian jalur** (dua tipe kipas di setiap jalur; alasan di `docs/analisis-gerbang-kelayakan-2.md` bagian 5): **A** (blokade → massa) U03, U04 (tipe A) + U06, U07 (tipe B); **B** (blokade) U01 (A) + U08, U10 (B); **C** (bilah patah) U05 (B); **E** (kontrol) U02 (A) + U11 (B); **cadangan** U09 (C). U03/U04 dan U06/U07 dipilih untuk jalur massa karena garis dasarnya paling stabil; U05 ke jalur C karena garis dasar orde ¼-nya menyimpang dari unit tipe B lain.
- [x] **16-10-2026: Uji laju cuplik 4,9 kSPS (VSHCT 204 µs) pada U11 — gagal.** Jarak antar sampel tetap ±329 µs karena dibatasi waktu baca ESP32 (dua transaksi I²C per sampel pada 1 MHz), sehingga laju efektif tetap ±3040 SPS dengan pewaktuan tidak teratur. Firmware dikembalikan ke VSHCT 332 µs (3030 SPS, 0 terlewat). **Keputusan:** laju cuplik tetap 3030 SPS; *aliasing* tipe B ditangani dengan membatasi ciri pada orde rendah dan mengecualikan posisi *alias* yang diketahui. Tapis RC anti-*alias* di masukan INA226 dicatat sebagai opsi perbaikan bila hasil klasifikasi tipe B kurang. Data uji di `data/_uji_fs/`.
- [x] **16-10-2026: Keputusan — tanpa sapuan kecepatan (PWM).** Karena keterbatasan waktu, seluruh kelas direkam pada tegangan penuh 12,7 V. Pertimbangan: (1) PWM memutus-sambung arus kipas pada frekuensi tinggi, sehingga pada laju cuplik 3030 SPS akan menimbulkan *aliasing* yang jauh lebih berat; (2) argumen keunggulan AI atas metode ambang batas tetap dapat ditunjukkan karena arus kipas sehat antar unit sudah tersebar 63–78 mA dan kelas Tidak Seimbang praktis tidak mengubah arus rata-rata. Konsekuensi: ketahanan model terhadap perubahan kecepatan tidak diuji; dicatat sebagai keterbatasan.
  Protokol pengambilan data selanjutnya: 50 rekaman per kondisi, sesi **s5**. Urutan: (1) jalur A dan B — Sehat s5 → blokade 50/75 % (templat karton berbentuk juring di sisi tiup, ditempel pada penyangga; bagian tertutup dimulai dari sudut kabel, searah jarum jam); (2) jalur E, C, dan cadangan — Sehat s5; (3) kelas Tidak Dikenal; (4) massa 33/67/100 mg pada jalur A; (5) bilah patah U05.
- [x] **17–18-10-2026: Sesi s5 tahap 1 — Sehat + blokade 50/75 % pada jalur A dan B** (U03, U04, U06, U07, U01, U08, U10; 50 rekaman per kondisi; karton di sisi tiup; 0 konversi terlewat). Rata-rata 20 rekaman terakhir tiap kondisi (arus dalam mA):

  | Unit | Tipe | I Sehat | I Blok 50 % | I Blok 75 % | ΔI 75 % | Riak/DC Sehat | Riak/DC Blok 75 % |
  |---|---|---|---|---|---|---|---|
  | U03 | A | 77,90 | 82,03 | 81,51 | +3,61 | 5,49 % | 5,29 % |
  | U04 | A | 73,65 | 77,20 | 77,00 | +3,35 | 5,99 % | 5,81 % |
  | U01 | A | 72,26 | 76,38 | 75,95 | +3,68 | 5,86 % | 5,57 % |
  | U06 | B | 65,06 | 68,71 | 68,19 | +3,12 | 24,71 % | 24,63 % |
  | U07 | B | 63,53 | 66,90 | 66,59 | +3,06 | 23,75 % | 23,39 % |
  | U08 | B | 64,87 | 69,15 | 69,12 | +4,25 | 23,73 % | 23,16 % |
  | U10 | B | 63,15 | 66,88 | 66,88 | +3,73 | 24,72 % | 24,17 % |

  Temuan: (1) blokade di sisi tiup **menaikkan arus +3,1 s.d. +4,3 mA** dan menurunkan kecepatan pada semua unit dan kedua tipe (berlawanan dengan perkiraan awal "arus turun"); (2) blokade 75 % hampir identik dengan 50 % setelah stabil, sehingga keduanya praktis satu tingkat; (3) kenaikan arus akibat blokade (±3,5 mA) **jauh lebih kecil daripada sebaran arus Sehat antar unit (63–78 mA)**, sehingga ambang batas arus tunggal tidak dapat memisahkan Sehat dan Aliran Terhambat lintas unit; (4) setelah pemasangan karton, arus dan kecepatan masih bergeser selama ±2–3 menit; (5) kipas yang lama tidak dinyalakan (mis. U01, dingin >10 hari) mulai dengan kecepatan rendah dan arus tinggi yang menyerupai blokade, sehingga bagian awal rekaman Sehat yang belum stabil perlu dipisahkan saat pelatihan. Prosedur untuk unit berikutnya: pemanasan ±5 menit sebelum merekam.
- [x] **18–19-10-2026: Sesi s5 tahap 2 — Sehat untuk U02, U11, U05, U09** (50 rekaman per unit; U02 ditambah 30 rekaman setelah hangat karena awal rekaman masih dingin: 236 Hz / 80,5 mA → 309 Hz / 74,1 mA). Nilai setelah stabil sesuai sesi s4: U02 74,1 mA, U11 63,8 mA, U05 65,1 mA, U09 71,4 mA (riak/DC U09 ≈ 9,8 %).
- [x] **19-10-2026: Sesi s5 tahap 3 — kelas Tidak Dikenal.**

  | Kondisi | Label | n | Arus (mA) | Riak RMS (mA) |
  |---|---|---|---|---|
  | Tanpa beban | `unknown-tanpabeban_u00` | 30 | −0,07 (*offset*) | 0,028 (derau sensor) |
  | LED strip 12 V | `unknown-led_u00` | 30 | 140,7–142,4 | 0,03 |
  | LED strip dipotong hingga arus setara kipas | `unknown-ledpendek_u00` | 30 | 71,4–71,9 | 0,05 |
  | Dua kipas paralel (U02 tipe A + U11 tipe B) | `unknown-2kipas_u02u11` | 50 | 137,4–137,8 | ±17,0 |
  | Transisi (kabel negatif U02 dilepas-pasang tiap ±5 s) | `unknown-transisi_u02` | 30 | 0–84 | 0,03–44 |

  Catatan: (1) LED pendek sengaja dibuat berarus sama dengan kipas (71 mA) agar tidak dapat dibedakan dari arus rata-rata, hanya dari pola riak (riak LED ±90× lebih kecil dari kipas tipe A); (2) pada LED pendek terdeteksi puncak sangat kecil di ±702 Hz walaupun tidak ada kipas yang terhubung (asal belum diketahui); (3) rekaman transisi berisi campuran jendela: ±13 jendela memuat peristiwa colok/cabut, ±5 jendela kipas lepas (arus ≈ 0), dan ±12 jendela kipas berjalan stabil yang identik dengan kondisi Sehat. **Saat pelatihan, hanya bagian yang memuat peristiwa transisi yang diberi label Tidak Dikenal**; bagian stabil dikeluarkan agar tidak bertentangan dengan kelas Sehat. Resistor 220 Ω tidak dipakai karena dayanya (¼ W) tidak cukup untuk 0,73 W.
- [x] **19-10-2026: Tahap 4 — massa (gerbang kelayakan langkah 2) — TIDAK LULUS.** Kawat tembaga Ø0,9 mm di akar bilah (sisi hisap). Analisis `tools/cek_massa.py`, ciri amplitudo di orde ¼ f₁ (kandidat 1× putaran), 60 s pertama tiap kondisi dibuang:

  | Unit | Dudukan | Kondisi | Orde ¼ (mA) | d dalam-unit vs Sehat |
  |---|---|---|---|---|
  | U03 | lama (Sehat) / diperkuat (68, 103 mg) | Sehat | 0,064 ± 0,015 | — |
  | U03 | | 34 mg | 0,068 ± 0,018 | +0,2 |
  | U03 | | 68 mg | 0,086 ± 0,020 | +1,2 |
  | U03 | | 103 mg | 0,084 ± 0,037 | +0,7 |
  | U04 | diperkuat (keduanya, `s5k`) | Sehat | 0,080 ± 0,029 | — |
  | U04 | | 103 mg | 0,066 ± 0,022 | −0,5 |

  Temuan: (1) massa hingga 103 mg di akar bilah **tidak menghasilkan perubahan yang andal** di orde putaran maupun orde lain pada dua unit tipe A (syarat d > 2 tidak terpenuhi), walaupun kipas bergetar kuat secara mekanis (pada 68 mg U03 hampir jatuh dari dudukan, sehingga dudukan diperkuat; 9 rekaman yang terganggu dipindah ke `data/_batal/`); (2) arus rata-rata tidak berubah; (3) pemindaian seluruh pita orde memunculkan perbedaan besar palsu di posisi *alias* (orde ≈ 0,93; 1,43; 1,93; …) akibat perbedaan kecepatan antar rekaman, sehingga ciri di posisi *alias* tidak boleh dipakai. Dugaan: pada kipas kecil berbantalan luncur, gaya ketidakseimbangan diteruskan ke rangka/dudukan tetapi modulasi torsi motor per putaran sangat kecil dibanding fluktuasi beban alami (±1,5 % kecepatan).
  **Keputusan: model utama memakai skema cadangan 3 kelas — Sehat, Aliran Terhambat, Tidak Dikenal.** Kelas Tidak Seimbang dilaporkan sebagai hasil negatif terukur. U06 dan U07 tidak diberi massa (tetap utuh). Data massa U03/U04 disimpan di Google Drive.
- [x] **20-10-2026: Tahap 5 — bilah patah U05 (uji kewajaran *pipeline*) — LULUS.** Separuh luar satu bilah dipotong; dudukan diperkuat; pembanding U05 Sehat dengan dudukan yang sama (`s5k`, 30 rekaman); 30 rekaman `patah_u05`.

  | Kondisi | f₁ (Hz) | I (mA) | Orde ½ (mA) | Orde ¼ (mA) |
  |---|---|---|---|---|
  | Sehat | 351,2 | 65,49 | 0,183 ± 0,084 | 0,438 ± 0,281 |
  | Bilah patah | 326,3 | 66,95 | **1,566 ± 0,471** | 0,210 ± 0,051 |

  Amplitudo orde ½ naik 8,6× (**d = +4,1**); kecepatan turun ±7 %; arus naik 1,5 mA (masih jauh lebih kecil dari sebaran arus antar unit). Kerusakan besar terdeteksi jelas dari arus. Catatan: pada tipe B tanda ketidakseimbangan muncul di orde ½ f₁, bukan orde ¼ seperti dugaan dari tipe A; uji massa sebelumnya hanya dilakukan pada tipe A, sehingga kemungkinan massa pada tipe B terdeteksi di orde ½ **belum diuji**.
- [~] **20-10-2026: Pelatihan dan evaluasi model 3 kelas** — skrip `tools/fitur.py` (17 ciri per jendela 768 sampel ≈ 253 ms), `tools/dataset.py` (26.870 jendela latih; filter kestabilan ±1 mA; jendela transisi hanya yang memuat peristiwa), `tools/latih_model.py` (MLP 32-16, LOUO, pembanding ambang batas). Evaluasi utama: **LOUO + antar-sesi sekaligus** — patokan per unit diambil dari Sehat sesi s4, pengujian hanya pada data sesi lain (s5/s5k) dari unit yang tidak ikut dilatih.

  | Konfigurasi | Akurasi | Recall Sehat | Recall Terhambat | Recall Tidak Dikenal | Alarm palsu antar-sesi |
  |---|---|---|---|---|---|
  | Ambang batas I_RMS absolut (pembanding sesuai proposal) | 40,8 % | 89,8 % | 14,0 % | 0,4 % | — |
  | MLP, 17 ciri tanpa patokan (LOUO, semua sesi) | 74,8 % | 80,2 % | 62,9 % | 59,5 % | 28,8 % |
  | MLP, 16 ciri + selisih patokan (arus, riak) + pengaman arus 25 % | 86,1 % | 83,4 % | 85,0 % | 98,9 % | 3,6 % |
  | MLP ringkas (5 ciri + selisih patokan arus & riak) + pengaman 25 % | 91,9 % | 99,6 % | 84,0 % | 99,9 % | 0,1 % |
  | **Ambang batas relatif ΔI/I_patokan + pengaman 25 %** | **99,3 %** | 98,9 % | 99,6 % | 99,5 % | — |

  Temuan: (1) tanpa patokan per unit, sebaran antar unit dan pergeseran antar hari (f₁ hingga ±6 %) membuat semua metode lemah; (2) arus jauh lebih stabil antar hari (≤ 1 mA) dibanding efek blokade (+3–4 mA, ≈ +5 %), sehingga patokan arus per unit sangat efektif, sedangkan patokan pada ciri kecepatan/spektrum justru merugikan; (3) **dengan patokan per unit, ambang batas relatif sederhana (99,3 %) mengungguli MLP (91,9 %)** — blokade terutama tampak sebagai kenaikan arus relatif, bukan perubahan bentuk spektrum; (4) dua kipas paralel (arus ≈ 2×) diklasifikasikan sebagai Terhambat oleh MLP sampai ditambahkan pengaman fisik |ΔI/I_patokan| > 25 % → Tidak Dikenal (batas ditetapkan dari fisika: efek blokade ≈ 5 %); ambang keyakinan *softmax* (0,6/0,8) tidak membantu; (5) unit tipe C (U09, tidak pernah dilatih) dikenali Sehat 98,9–100 % oleh MLP 16/5 ciri; (6) massa ≤ 103 mg dan bilah patah sebagian besar diprediksi Sehat, konsisten dengan hasil gerbang kelayakan.
- [x] **20-10-2026: Model final, kuantisasi, dan firmware.** Masukan 7 ciri: riak/DC, kurtosis, *crest factor*, kerataan spektrum, lantai derau relatif, serta selisih log arus dan selisih riak/DC terhadap patokan kalibrasi. MLP 7–32–16–3; masukan dibatasi pada persentil 0,5–99,5 % (selisih arus dibatasi ±25 %) sebelum standarisasi agar resolusi int8 tidak habis oleh nilai ekstrem. Kuantisasi int8 simetris per-tensor: kesesuaian float–int8 99,99 %; ukuran model **±1 KB** (784 bobot int8 + 51 bias int32). Pengaman fisik |ΔI/I_patokan| > 25 % → Tidak Dikenal. Evaluasi pipeline int8 persis seperti firmware (`tools/evaluasi_final.py`, LOUO + antar-sesi):

  | Metode | Akurasi | Recall Sehat | Recall Terhambat | Recall Tidak Dikenal | Alarm palsu Sehat |
  |---|---|---|---|---|---|
  | **MLP int8 (firmware)** | **95,7 %** | **100 %** | **91,5 %** | **99,8 %** | **0,0 %** |
  | Ambang batas I_RMS absolut | 40,8 % | 89,8 % | 14,0 % | 0,4 % | 10,2 % |
  | Ambang batas relatif ΔI/I_patokan + pengaman | 99,3 % | 98,9 % | 99,6 % | 99,5 % | 1,1 % |

  Unit terlemah: U04 (69,5 %; sebagian jendela blokade diprediksi Sehat). Unit tipe C (U09, tidak pernah dilatih) dikenali Sehat 100 %. Firmware `03_klasifikasi`: jendela 768 sampel, ciri + FFT radix-2 1024 titik, MLP int8, pemungutan suara 5 jendela, kalibrasi ±10 s disimpan di NVS. Verifikasi `tools/cek_firmware.py`: selisih ciri firmware vs Python < 1·10⁻⁶; laju cuplik firmware 3030,3 SPS (median, sama dengan data latih). Model memakai kode C int8 biasa (bukan ESP-NN) karena ukurannya sangat kecil.
- [x] **20-10-2026: Uji langsung firmware `03_klasifikasi`** (U11, tipe B, unit kontrol yang data blokadenya tidak pernah dipakai dalam pelatihan; dipantau dengan `tools/pantau.py`). Kalibrasi ±10 s: arus patokan 64,14 mA, riak/DC 0,256.

  | Kondisi | Jendela | Hasil | ΔI terhadap patokan | Keyakinan |
  |---|---|---|---|---|
  | Sehat setelah kalibrasi | 48 | Sehat 48/48 | −0,4 s.d. +0,4 % | 0,98–0,99 |
  | Blokade 50 % sisi tiup | 71 | **Aliran Terhambat 71/71** | +3,7 s.d. +4,7 % | 0,77–0,96 |
  | Karton dilepas | 70 | Sehat 70/70 | +0,3 s.d. +0,9 % | 0,97–0,98 |
  | LED strip pendek (tanpa kalibrasi ulang) | 70 | **Tidak Dikenal 70/70** | +8,5 % | 1,00 |

  **Latensi:** inferensi MLP int8 rata-rata **125 µs** (maks 153 µs); ciri + FFT ±10,0 ms; *end-to-end* ≈ 253 ms (jendela) + 10 ms ≈ **263 ms** (target < 300 ms). Catatan pembanding: ambang batas relatif hasil pelatihan (batas +2,17 % dan +7,43 %) juga memberi hasil benar untuk keempat kondisi di atas; keunggulan model AI atas ambang relatif hanya dapat diharapkan untuk beban non-kipas yang kenaikan arusnya berada di rentang blokade (+2–7 %), dan **belum diuji**.
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
