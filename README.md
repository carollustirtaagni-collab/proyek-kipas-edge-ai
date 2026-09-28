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
| Sensor | **INA226**, alamat IÂ²C `0x44`, *shunt* bawaan **0,1 Î©** (R100) |
| Objek uji | Kipas **Hanaya FAN5010DC**: 50Ã—50Ã—10 mm, *brushless*, 12 V / 0,09 A, 2 kabel (tanpa tacho), **7 bilah**. Total 10 unit (U01â€“U10) |
| Resolusi arus | 2,5 ÂµV/LSB Ã· 0,1 Î© = **25 ÂµA/LSB**; batas ukur 0,819 A |
| Jumlah kelas | **4** (cadangan: 3 kelas bila kelas Aliran Terhambat tidak terpisah) |
| Ciri | Spektrum FFT dengan ***order tracking*** (orde putaran, bukan Hz absolut) + statistik riak |
| Model | MLP kecil, kuantisasi int8, ESP-NN / ESP-DSP |
| Validasi | **Antar-sesi** dan ***leave-one-unit-out*** (LOUO). Tidak memakai pembagian acak per jendela, karena menyebabkan kebocoran data. |
| Pembanding | Metode ambang batas I<sub>RMS</sub> pada data uji yang sama |

**Target kinerja**

- Latensi inferensi < 5 ms; *end-to-end* < 300 ms (jendela 256 ms). Jendela boleh diperpanjang hingga ~1 s bila SNR memerlukan, karena fenomenanya berskala minggu.
- Akurasi dua tingkat: â‰¥ 90 % antar-sesi (unit sama) dan â‰¥ 80 % LOUO.
- *Recall* kelas gangguan â‰¥ 90 %; alarm palsu â‰¤ 5 %; unggul â‰¥ 20 poin atas metode ambang batas.
- Ukuran model < 25 KB; enklosur â‰¤ 110 Ã— 75 Ã— 45 mm.

**Alternatif yang dipertimbangkan dan tidak dipilih:** *shunt* 0,01 Î© dan 0,05 Î© (0,05 Î© disimpan sebagai cadangan); domain 220 V AC; PZEM-004T (hanya RMS ~1 Hz); sistem PLTS + JK-BMS (tidak portabel); kipas 120 mm; kipas 5 V; selotip sebagai massa tambahan.

---

## Kelas Klasifikasi

| # | Kelas | Cara pembuatan | Tingkat | Tanda tangan yang diharapkan |
|---|---|---|---|---|
| 1 | **Sehat** | Kipas apa adanya | â€” | Puncak orde 1Ã—, orde bilah, dan komutasi bersih |
| 2 | **Tidak Seimbang** | Kawat solder Ã˜1 mm (~6,7 mg/mm) di akar satu bilah, direkatkan lem CA | 5/10/15 mm = 33/67/100 mg | Puncak orde 1Ã— naik; arus rata-rata praktis tidak berubah, sehingga tidak terdeteksi metode ambang batas |
| 3 | **Aliran Terhambat** | Templat karton di sisi hisap | Tertutup 25/50/75 % | Derau pita lebar naik, puncak bilah melebar; arus diperkirakan sedikit turun (kipas aksial, *belum diverifikasi*) |
| 4 | **Tidak Dikenal** | Kipas mati, beban non-motor (resistor/LED), masa transisi, dua kipas sekaligus | â€” | â€” |

Setiap kelas direkam dengan **sapuan PWM 40â€“100 %** agar rentang arus antar kelas saling tumpang tindih. Kondisi ini dipakai untuk menunjukkan keterbatasan metode ambang batas.

**Di luar kelas model:**
- **Bilah dipatahkan**: hanya untuk uji kewajaran *pipeline* (kerusakan besar harus tampak jelas di FFT), dilaporkan dalam satu tabel.
- **Operasi 24 jam**: pengamatan kestabilan jangka panjang (opsional), menambah data Sehat lintas waktu.
- Kelas "Bantalan Kering" dibatalkan karena pelumas bantalan pada kipas ini tidak dapat dibersihkan.

---

## Rancangan Eksperimen

### Matriks unit (10 unit)

Urutan per unit: rekam Sehat â†’ rekam blokade 25/50/75 % (reversibel) â†’ lepas blokade â†’ (jalur A saja) tambah massa bertahap.
**Semua unit direkam dalam kondisi Sehat terlebih dahulu** sebelum perlakuan permanen apa pun.

| Jalur | Unit | Perlakuan | Kelas |
|---|---|---|---|
| A | 4 | Sehat â†’ blokade â†’ massa 33 â†’ 67 â†’ 100 mg | 1, 3, 2 |
| B | 3 | Sehat â†’ blokade | 1, 3 |
| C | 1 | Sehat â†’ bilah dipatahkan | 1 + validasi *pipeline* |
| E | 2 | Tidak diberi perlakuan | 1; kontrol sekaligus cadangan |
| D | (opsional) | Sehat, operasi 24/7 | Memakai salah satu unit E |

Cakupan: Sehat 10 unit, Aliran Terhambat 7 unit (A+B), Tidak Seimbang 4 unit (A). Minimal 3 unit per kelas gangguan diperlukan agar validasi LOUO bermakna.

### Gerbang kelayakan (sebelum tahap pembelajaran mesin)

1. Rekam 6â€“8 kipas **sehat** yang berbeda, lalu tumpuk spektrumnya untuk melihat pita sebaran antar unit.
2. Rekam 1 kipas dengan massa 100 mg dan periksa apakah puncak orde 1Ã— keluar jelas dari pita tersebut.
3. Hitung *effect size* tiap ciri: `d = |Î¼_gangguan âˆ’ Î¼_sehat| / Ïƒ_antar-unit-sehat`. **Lulus bila beberapa ciri memiliki d > 2.**
4. Bila tidak lulus: perbesar massa, atau gunakan skema 3 kelas.

### Konvensi penamaan rekaman

`{kelas}_u{NN}_pwm{duty}[_s{sesi}]`, contoh: `sehat_u01_pwm100`, `massa067_u03_pwm70`, `blok50_u05_pwm100_s2`, `unknown-mati_u00`.

---

## Perangkat Keras

```
ESP32-S3            INA226 (0x44)
3V3   â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€  VCC      (maks. 5,5 V; JANGAN 12 V)
GND   â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€  GND
GPIO8 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€  SDA
GPIO9 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€  SCL
GPIO7 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€  ALERT    (open-drain, INPUT_PULLUP)

12 V (+) â”€â”€ IN+
            INâˆ’ â”€â”€â”¬â”€â”€ kipas (+)
            VBUS â”€â”˜   (input pengukur tegangan, boleh 12 V)
12 V (âˆ’) â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€ kipas (âˆ’)
           â””â”€â”€ GND ESP32   (ground bersama WAJIB)
```

Kapasitor elektrolit 1000 ÂµF dipasang pada keluaran catu daya, **sebelum *shunt***. Kapasitor besar tidak boleh dipasang paralel dengan kipas setelah *shunt*, karena riak arus akan mengalir lewat kapasitor, bukan lewat *shunt*.

---

## Struktur Repositori

```
firmware/00_diagnosa_i2c/    Scan IÂ²C 100 kHz & 400 kHz + pembacaan ID di tiap alamat
firmware/01_ina226_cek/      Verifikasi ID chip + pembacaan arus lambat (AVG=16, 115200 baud)
firmware/02_ina226_capture/  Akuisisi burst 8192 sampel via ALERT, keluaran CSV (921600 baud, perintah 'c')
tools/capture_fft.py         Rekam dari serial â†’ CSV di data/ â†’ plot domain waktu + FFT; --compare untuk overlay
tools/serial_log.py          Pembacaan serial selama N detik (non-interaktif)
docs/                        Proposal Rev. 2, ringkasan keputusan terdahulu, foto komponen
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

**Lingkungan pengembangan:** Windows 11, arduino-cli 1.5.1, core `esp32:esp32` 3.3.12, Python 3.13. Papan ESP32-S3 terhubung melalui USB-serial CH343 (port UART).

---

## Catatan Teknis

- **Alamat INA226 = `0x44`** pada modul ini (hasil scan). Alamat 0x40 menghasilkan NACK (`endTransmission` kode 4).
- Pembacaan register memakai **`endTransmission()` dengan STOP penuh**, bukan *repeated start*. INA226 menyimpan *register pointer*, dan cara ini kompatibel di semua versi core ESP32.
- Register: `0x00` konfigurasi, `0x01` *shunt* (int16, 2,5 ÂµV/LSB), `0x02` bus (1,25 mV/LSB), `0x06` mask/enable, `0xFE` = `0x5449`, `0xFF` = `0x2260`.
- Mode akuisisi: config = `0x4000 | (VSHCT<<3) | 0x5` (*shunt* kontinu). **AVG = 1 wajib**, karena *averaging* internal bekerja sebagai tapis lolos-rendah yang menghapus riak.
- *Conversion Ready*: mask/enable `0x0400` (CNVR) membuat ALERT turun setiap konversi selesai. Membaca `0x06` menghapus *flag*, sehingga dibutuhkan 2 transaksi IÂ²C per sampel.
- **Urutan baca: `0x06` (hapus *flag*) dulu, baru *shunt*.** Jika urutannya terbalik, *flag* konversi berikutnya ikut terhapus sehingga setiap konversi kedua hilang secara teratur (terukur 597 Âµs/sampel). Pola teratur ini tidak terdeteksi oleh pemeriksaan celah berbasis median. Karena itu, `capture_fft.py` memakai hitungan `#missed` yang dilaporkan ESP32.
- **Laju cuplik terukur: 3030 SPS** (VSHCT 332 Âµs, IÂ²C **1 MHz**, 0 konversi terlewat). Pada 400 kHz, batas resmi INA226, dua transaksi IÂ²C membutuhkan ~454 Âµs, lebih lama dari satu konversi. Pengoperasian 1 MHz berada di luar spesifikasi resmi tetapi terbukti stabil secara empiris. Kipas 5 cm dapat mencapai 3.500â€“5.500 RPM (komutasi hingga ~1,1 kHz), sehingga frekuensi Nyquist harus > ~1,2 kHz. Laju 4,9 kSPS (VSHCT 204 Âµs) belum diuji.
- ***Aliasing*:** INA226 tidak memiliki tapis anti-*alias* (hanya integrasi selama waktu konversi). Harmonik ke-5 dan seterusnya dari 321 Hz terlipat ke bawah frekuensi Nyquist. Saat sapuan PWM, komponen *alias* bergerak berlawanan arah dengan orde sebenarnya, sehingga ciri *order tracking* dibatasi pada orde di bawah Nyquist.
- Bila SNR kurang: perpanjang FFT (1024 â†’ 4096 memberi +6 dB dan Î”f lebih halus) atau gunakan rata-rata Welch.
- Catu daya terbaik untuk pengambilan data adalah aki/baterai 12 V, karena adaptor *switching* murah menambah derau.

---

## Pemecahan Masalah

| Gejala | Kemungkinan penyebab |
|---|---|
| Scan tidak menemukan perangkat | SDA/SCL tertukar, VCC tidak tersambung, kabel longgar |
| `endTransmission` kode 2/4 saat baca register | Alamat salah (modul ini 0x44) atau IÂ²C terlalu cepat untuk *pull-up* â†’ coba 100 kHz |
| ID bukan 0x5449/0x2260 | Bukan INA226 (mis. INA219) |
| Arus bernilai negatif | IN+ / INâˆ’ tertukar |
| Arus 0 padahal kipas berputar | Arus kipas tidak melewati *shunt* |
| Tegangan bus 0 V padahal arus benar | VBUS tidak tersambung (boleh diabaikan) |
| Sketch 02 `#ERROR timeout` | ALERT tidak tersambung â†’ set `USE_ALERT_PIN 0` |
| Konversi terlewat > 0 | IÂ²C tidak sempat â†’ naikkan `I2C_HZ` atau perbesar `VSHCT_CODE` |
| Python: "Tidak menerima data" | Serial Monitor masih terbuka atau port salah |
| Unggah gagal | Tahan BOOT, tekan RESET, lepas BOOT, unggah ulang |

---

## Progres dan Log Eksperimen

**Langkah berikutnya:** (1) verifikasi arus dengan multimeter, (2) pengukuran RPM dengan stroboskop, (3) dudukan kipas yang terstandar. Setelah itu: rekam U01â€“U04 kondisi Sehat, lalu U05â€“U10.

- [x] Perakitan perangkat keras (ESP32-S3 + INA226 + kipas 12 V).
- [x] Scan IÂ²C: INA226 terdeteksi di **0x44**.
- [x] **27-09-2026: Verifikasi sensor.** Manufacturer ID 0x5449 dan Die ID 0x2260 sesuai. Tanpa beban: *shunt* â‰ˆ âˆ’0,010 mV (â‰ˆ âˆ’0,1 mA), masih dalam spesifikasi *offset* Â±10 ÂµV.
- [~] **Verifikasi arus.** Dengan catu 12 V: tegangan bus 12,72 V, arus â‰ˆ 74 mA, polaritas benar.
  - **28-09-2026:** multimeter ZOTEK ZT102 (DC mA, seri) membaca **84,0 mA** pada U01; INA226 pada saat berdekatan membaca **73,0 mA** (12,721 V). Selisih **+15 %**, jauh di atas akurasi multimeter (~Â±1 %). Penyebab belum diketahui: pengukuran belum serentak, atau nilai *shunt* efektif â‰  0,1 Î© (bila INA226 benar membaca 7,3 mV, *shunt* efektif â‰ˆ 0,087 Î©). Uji penentu: ukur mV DC langsung di IN+/INâˆ’ bersamaan dengan pembacaan INA226.
  - **28-09-2026:** mV DC di terminal IN+/INâˆ’ = **8,89 mV**; INA226 pada saat yang sama = 73,16 mA (**7,32 mV** di pin sensor), stabil antar pengukuran. Dengan arus sebenarnya â‰ˆ 84 mA: hambatan antar-terminal â‰ˆ 0,106 Î©, hambatan yang terbaca INA226 â‰ˆ **0,087 Î©**. Dugaan: nilai resistor *shunt* di bawah label; selisih 19 mÎ© = hambatan kontak terminal + jalur PCB. Belum final. Data mentah (LSB) tersimpan, sehingga koreksi kalibrasi (`--rshunt`) dapat diterapkan ulang ke seluruh rekaman.
  - **Keputusan (29-09-2026):** proyek dilanjutkan dengan **skala INA226 apa adanya** (R = 0,1 Î© nominal). Klasifikasi tidak terpengaruh karena selisihnya berupa faktor skala konstan pada satu sensor. Syarat: **satu modul INA226 yang sama dipakai dari pengambilan data hingga demo**; bila modul diganti, verifikasi multimeter diulang. Di laporan, nilai arus dinyatakan dalam skala INA226 dengan catatan selisih Â±15 % terhadap multimeter.
- [x] **28-09-2026: Dudukan kipas terstandar.** Pada dudukan baru, fundamental U01 = **327,0 Hz** (sebelumnya 321 Hz di atas alas), konsisten dengan dugaan bahwa posisi lama sedikit menghambat aliran udara.
- [x] **28-09-2026: Spektrum pertama** (`data/sehat_u01_pwm100_20260928-003938`). Laju 3030 SPS, 0 terlewat. DC 73,0 mA, riak RMS 4,29 mA (5,9 %), riak p-p 26 mA, lantai derau 44 ÂµA, SNR 34,9 dB. Terdapat deret harmonik jelas dengan fundamental **321,1 Hz** (642/963/1284 Hz); harmonik â‰¥ 5 ter-*alias*. Terdapat pula pita sisi Â±14,7 Hz (asal belum diketahui) dan puncak 160,5 Hz (Â½ Ã— 321 Hz). Kecepatan stabil selama rekaman (321,1 â†’ 319,6 Hz).
- [x] **28-09-2026: Identifikasi kipas.** FAN5010DC, 12 V / 0,09 A, 2 kabel, 7 bilah. Arus terukur 73 mA = 81 % rating.
- [x] **28-09-2026: Kapasitor 1000 ÂµF pada catu daya** (saran dosen pembimbing). Data menunjukkan posisinya sebelum *shunt*: riak RMS tetap 4,29 â†’ 4,30 mA. Lantai derau 44 â†’ 40 ÂµA (belum dapat dipastikan bermakna). Sejak sesi s2, setiap rekaman mencatat tegangan bus (`#vbus_V`).
- [ ] **Pergeseran kecepatan U01 sesi s2.** Rekaman 01:01 menunjukkan 309,6 Hz / 74,3 mA, sedangkan satu menit kemudian 321,8 Hz / 73,2 mA pada 12,716 V. Putaran lebih lambat disertai arus lebih tinggi mengindikasikan beban mekanis sesaat (dugaan: aliran udara terhalang oleh posisi kipas, belum dikonfirmasi). Tindak lanjut: dudukan kipas yang terstandar.
- [ ] **Penetapan orde 1Ã— (RPM).** Hipotesis dari spektrum U01: (a) 321 Hz = 4 komutasi/putaran â†’ **4.816 RPM** (80,3 Hz; orde bilah 7Ã— di 562 Hz hanya +11,6 dB), paling masuk akal untuk kipas 5010; (b) 2 komutasi/putaran â†’ 9.633 RPM (kecil kemungkinan); (c) 6 komutasi/putaran â†’ 3.211 RPM (tidak ada orde 2Ã—). Perlu verifikasi stroboskop atau uji massa.
- [ ] Uji bilah patah (validasi *pipeline* sekaligus konfirmasi orde 1Ã—).
- [ ] Gerbang kelayakan (6â€“8 unit sehat + massa 100 mg, Cohen's *d*).
- [ ] Rangkaian PWM (MOSFET *logic-level*, mis. IRLZ44N) untuk sapuan 40â€“100 %.
- [ ] Pengumpulan data lengkap â†’ pelatihan â†’ kuantisasi â†’ implementasi â†’ pengujian dua tingkat.
- [ ] Proposal Revisi 3.

Rekaman uji laju cuplik yang tidak valid disimpan terpisah di `data/_uji_i2c/` beserta keterangannya.

---

## Catatan Revisi terhadap Proposal Rev. 2

`docs/proposal-rev2.md` dan `docs/ringkasan-keputusan-lama.md` tetap relevan untuk latar belakang dan dasar teori. Bagian berikut telah diperbarui:

- Kelas "Bantalan Kering" â†’ diganti **Aliran Terhambat**.
- Kipas 120 mm / contoh 2.000 RPM â†’ **kipas 5 cm, 3.500â€“5.500 RPM**.
- 2 kSPS / FFT 512 â†’ **3030 SPS terukur**, FFT â‰¥ 1024.
- Alamat IÂ²C 0x40 â†’ **0x44**.
- IÂ²C 1 MHz sebagai asumsi â†’ batas resmi 400 kHz; 1 MHz dipakai setelah diverifikasi empiris.
- Target akurasi tunggal â‰¥ 90 % â†’ **dua tingkat** (90 % antar-sesi / 80 % LOUO).
- "Aliran tertutup â†’ arus naik" â†’ untuk kipas aksial kemungkinan **turun**.

**Materi Revisi 3:** pemilihan kipas 5 cm beserta alasannya; laju cuplik aktual; 4 kelas + skema cadangan 3 kelas; *order tracking*; massa dan blokade bertingkat (dua kurva sensitivitas); matriks unit + LOUO; gerbang kelayakan; skenario demo tiga babak (konsistensi lintas unit, diagnosis, perbandingan ambang batas vs AI); serta jawaban atas pertanyaan "bagaimana memastikan model mengenali gangguan, bukan identitas unit kipas?".
