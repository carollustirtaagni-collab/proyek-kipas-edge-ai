# Ringkasan Keputusan & Status Proyek

**Proyek:** Sistem Deteksi Dini Degradasi Kipas Pendingin DC Berbasis *Edge AI* melalui Analisis Sidik Jari Arus pada ESP32-S3
**Status dokumen proposal:** Revisi 2 — perlu diperbarui ke Revisi 3
**Tanggal ringkasan:** 22 September 2026

---

## 1. KEPUTUSAN FINAL (sudah terkunci)

| # | Aspek | Keputusan | Alasan utama |
|---|---|---|---|
| 1 | **Domain kelistrikan** | **DC 12 V** ⚠️ *menunggu konfirmasi dosen* | Keselamatan, sensor sudah dimiliki, narasi sudah selaras |
| 2 | **Sensor arus** | **INA226** + *shunt* **0,1 Ω** bawaan modul | Resolusi 25 µA (16-bit) — resolusi adalah sinyalnya |
| 3 | **Beban uji** | **Kipas HANAYA DC 12 V, 5 cm** — banyak unit | Portabel untuk demo, sekaligus objek penerapan nyata |
| 4 | **Mikrokontroler** | **ESP32-S3** | Instruksi vektor SIMD + pustaka ESP-NN & ESP-DSP |
| 5 | **Laju cuplik** | **4 kSPS** (naik dari 2 kSPS) | Kipas 5 cm berputar 3.500–5.500 RPM → komutasi bisa 1.100 Hz |
| 6 | **Jendela FFT** | **1.024 titik** → 256 ms, Δf = 3,9 Hz, Nyquist 2 kHz | Mempertahankan resolusi frekuensi sambil menaikkan pita |
| 7 | **Jumlah kelas** | **4 kelas** (naik dari 3) | Melampaui syarat tugas; berubah dari deteksi anomali → **diagnosis** |
| 8 | **Ekstraksi ciri** | ***Order tracking*** — orde putaran, bukan Hz absolut | Kebal terhadap variasi RPM antar unit **dan** sapuan PWM |
| 9 | **Validasi** | **Dua lapis:** antar-sesi + **leave-one-unit-out** | Membuktikan model belajar gangguan, bukan identitas kipas |
| 10 | **Model** | MLP kecil, terkuantisasi **int8** | < 25 KB, < 5 ms di ESP32-S3 |
| 11 | **Pembanding wajib** | Metode ambang batas $I_{RMS}$ diuji berdampingan | Bukti kuantitatif bahwa AI memang diperlukan |

### Struktur 4 kelas

| Kelas | Perlakuan fisik | Tanda tangan spektral yang diprediksi | Arus rata-rata |
|---|---|---|---|
| **1. Sehat** | Kipas apa adanya | Puncak bersih di orde 1×, bilah, dan komutasi | acuan |
| **2. Tidak Seimbang** | Solder 33/67/100 mg di akar satu bilah, lem CA | **Orde 1× melonjak**, pita sisi di sekitar komutasi | **± 0% — tidak berubah** |
| **3. Bantalan Kering** | Pelumas dibersihkan (buka stiker hub, *contact cleaner*) | RPM turun → **seluruh spektrum bergeser**, lantai derau naik | +10 … 25% |
| **4. Tidak Dikenal** | Mati, beban non-motor, transisi, dua kipas bersamaan | — | bervariasi |

> **Kelas 2 adalah kelas terpenting secara argumentatif.** Ketidakseimbangan massa hampir tidak mengubah arus rata-rata, sehingga **buta total bagi metode ambang batas apa pun**, tetapi sangat jelas di spektrum. Inilah bukti terkuat bahwa AI diperlukan.

---

## 2. CATATAN KEPUTUSAN — apa yang dipertimbangkan dan mengapa ditolak

Bagian ini berguna kalau penguji bertanya *"mengapa tidak pakai X?"*

| Opsi yang dipertimbangkan | Keputusan | Alasan penolakan |
|---|---|---|
| Sensor ACS758 / INA219 | ❌ | Resolusi puluhan mA (Hall) / 12-bit — riak tenggelam dalam derau |
| *Shunt* 0,01 Ω | ❌ | Resolusi 250 µA (10× lebih kasar); resistansi parasit PCB jadi 20%; *self-heating* menyebabkan *drift* antar sesi |
| *Shunt* 0,05 Ω (Stackpole MR3FT50L0) | ⏸️ **beli, jangan pasang** | Part bagus (*metal foil*, non-induktif), tapi menukar **−6 dB SNR** untuk *headroom* yang tidak dibutuhkan; pemasangan pada modul menambah 2–6 mΩ tak terkontrol. Simpan sebagai cadangan |
| **Pindah ke 220 V AC** | ❌ (kecuali dosen minta) | Kehilangan INA226; resolusi turun ke ±10 bit; wajib merancang *front-end* analog (bias + op-amp + anti-alias + *zero-cross*); butuh sensor tegangan kedua; **risiko fatal**; +2–3 minggu |
| Modul PZEM-004T untuk AC | ❌ | Hanya keluaran RMS pada ± 1 Hz — **membuang bentuk gelombangnya**. Ini *averaging* dalam bentuk perangkat keras yang tidak bisa dimatikan |
| ADE9000 / ADS131M04 untuk AC | ⏸️ | Secara teknis ideal (ADE9000: gelombang 8 kSPS + mesin harmonisa s/d orde 63), tapi hanya tersedia sebagai chip → harus merancang PCB sendiri |
| Sistem PLTS 24 V + JK-BMS | ❌ | **Tidak portabel** — prototipe wajib dibawa & didemokan. Selain itu data 1 Hz → bukan *signal processing*, dan rawan keberatan "Anda hanya membaca BMS" |
| Kipas 120 mm | ❌ | Kurang portabel; kipas 50 mm justru lebih sesuai narasi (kipas panel & rak, bukan kipas casing PC) |
| Selotip untuk massa tak seimbang | ❌ | Kekuatan kupas rendah; pada 5.000 RPM (ujung bilah ± 13 m/s) berisiko terlepas. **Gunakan lem CA** |
| Bilah dipatahkan sebagai kelas demo | ⏸️ **pakai terbatas** | Terlihat jelas oleh mata → mematikan kekuatan demo. Dipakai hanya untuk **validasi pipeline minggu 1** dan sebagai data di laporan |

---

## 3. SPESIFIKASI TEKNIS FINAL

### Akuisisi

| Parameter | Nilai |
|---|---|
| Sensor | INA226, *shunt* 0,1 Ω |
| Mode INA226 | *Shunt voltage continuous* (MODE = 101) |
| Waktu konversi | 140 µs (VSHCT = 000) |
| **Averaging** | **AVG = 1 — WAJIB dinonaktifkan** (averaging menghapus riak) |
| Register yang dibaca | **0x01 (Shunt Voltage) langsung** — tanpa kalibrasi |
| I²C | 1 MHz, *pull-up* 2,2 kΩ |
| Pemicu sampling | Pin **ALERT sebagai *Conversion Ready* + ISR** (bebas *jitter*) |
| Laju cuplik | **4.000 SPS** |
| Rentang arus | 0 – 0,819 A |
| Resolusi | 25 µA |

### Pemrosesan

```
Ring buffer 1024 sampel (256 ms, hop 128 ms → tumpang tindih 50%)
   ↓
Pisahkan DC level │ komponen AC
   ↓
FFT 1024 titik (ESP-DSP) → Δf = 3,9 Hz, s/d 2 kHz
   ↓
ORDER TRACKING:
   1. Estimasi RPM dari puncak dominan
   2. Normalisasi sumbu frekuensi → orde (1×, 2×, 7×, komutasi)
   3. Ekstrak amplitudo & RASIO antar orde
   ↓
± 28 ciri → normalisasi z-score → MLP int8 → softmax 4 kelas
   ↓
Ambang keyakinan: max P(k) < 0,60 → "Tidak Dikenal"
```

**Ciri kunci yang tahan variasi antar unit:**

- Amplitudo orde 1× ÷ amplitudo orde bilah (7×)
- Amplitudo orde 1× ÷ amplitudo orde komutasi
- Lebar puncak orde 1× (kestabilan putaran)
- Energi lantai derau di antara orde (gesekan bantalan)

### Estimasi anggaran arus & derau

| Besaran | Nilai |
|---|---|
| Arus tunak kipas 5 cm | ± 0,15 A |
| *Headroom* terhadap batas 0,819 A | **5,5×** |
| Arus kejut BLDC (2–3×) | 0,3 – 0,45 A → **tidak memotong** |
| *Blanking* saat penyalaan | **tidak diperlukan** (berbeda dari rencana awal) |
| Amplitudo riak | 4 – 8 mA RMS = 160 – 320 LSB |
| SNR estimasi | **32 – 38 dB** |

---

## 4. MATRIKS EKSPERIMEN

Prinsip: **setiap kipas direkam dulu dalam keadaan Sehat, baru dimodifikasi.** Ini memberi data berpasangan yang mengendalikan variasi produksi. Urutan perlakuan dari paling reversibel ke paling permanen.

| Jalur | Unit | Urutan perlakuan | Menghasilkan kelas |
|---|---|---|---|
| **A** | 4 | Sehat → massa 33 mg → 67 mg → 100 mg *(ditambah bertahap, tidak dilepas)* | Sehat + Tidak Seimbang (3 tingkat) |
| **B** | 4 | Sehat → pelumas dibersihkan | Sehat + Bantalan Kering |
| **C** | 1 | Sehat → bilah dipatahkan | **Validasi pipeline** (bukan demo) |
| **D** | 2 | Sehat, **dijalankan 24/7 mulai hari ini** | Penuaan nyata (bonus) |
| **E** | 1–2 | Cadangan, tidak disentuh | Uji akhir & pengganti |

**Total ideal: 12 unit.** Prioritas kalau jumlahnya lebih sedikit: **minimal 3 unit per kelas gangguan** agar *leave-one-unit-out* bermakna.

### Pembuatan massa tak seimbang

Kawat solder 60/40 diameter 1 mm ≈ **6,7 mg per mm**:

| Panjang | Massa | Tingkat | Gaya sentrifugal @5.000 RPM, r=15 mm |
|---|---|---|---|
| 5 mm | 33 mg | Ringan | 0,14 N |
| 10 mm | 67 mg | Sedang | 0,28 N |
| 15 mm | 100 mg | Berat | 0,41 N (420× beratnya sendiri) |

Pasang dengan **lem CA / epoksi** di **akar bilah** (radius kecil = gaya kecil), beri tanda posisi agar konsisten. Uji putar beberapa menit di dalam kotak tertutup sebelum merekam.

### Protokol pengumpulan data

| Aspek | Ketentuan |
|---|---|
| Sapuan PWM | **40 – 100%** pada setiap kelas → rentang arus antar kelas **sengaja tumpang tindih** |
| Jendela per kelas | ≥ 300 (ideal 600) |
| Sesi per kelas | ≥ 5, pada hari/suhu berbeda |
| **Pembagian data** | **Per sesi DAN per unit — tidak pernah acak per jendela** |
| Data uji | Unit + sesi yang belum pernah dilihat model |
| Pelaporan | *Confusion matrix*, precision/recall/F1 per kelas, kurva sensitivitas massa |

---

## 5. TARGET SPESIFIKASI

| Kategori | Parameter | Target |
|---|---|---|
| **Latensi** | Inferensi (jendela siap → putusan) | < 5 ms |
| | *End-to-end* keadaan tunak | < 300 ms |
| | Deteksi perubahan kondisi | < 1 detik |
| | Laju keputusan | ≥ 7 /detik |
| **Akurasi** | Keseluruhan (unit & sesi terpisah) | ≥ 90% |
| | Recall Tidak Seimbang & Bantalan Kering | ≥ 92% |
| | Recall Tidak Dikenal | ≥ 85% |
| | Alarm palsu (Sehat → gangguan) | ≤ 5% |
| | **Selisih vs metode ambang batas** | **≥ +20 poin persentase** |
| **Dimensi** | Papan rakitan | ≤ 90 × 60 mm |
| | Enklosur | ≤ 110 × 75 × 45 mm |
| | Berat (tanpa beban uji) | ≤ 250 g |
| **Memori** | Model int8 | < 25 KB |
| | RAM saat berjalan | < 120 KB |

---

## 6. SKENARIO DEMO

**Babak 1 — Konsistensi lintas unit**
> Tiga kipas *Sehat* berbeda, dipasang satu per satu → "SEHAT" ×3
> Tiga kipas *Tidak Seimbang* berbeda → "TIDAK SEIMBANG" ×3
> *"Dan dua di antaranya belum pernah dilihat model saat pelatihan."*

**Babak 2 — Diagnosis, bukan sekadar deteksi**
> Kipas Bantalan Kering → **"BANTALAN KERING"**, bukan sekadar "rusak"

**Babak 3 — Pembunuh argumen ambang batas** ⭐

| | Arus RMS | Metode *threshold* | **Edge AI** |
|---|---|---|---|
| Kipas Sehat @ PWM 100% | 0,155 A | ❌ "Terdegradasi" | ✅ **"Sehat"** |
| Kipas Rusak @ PWM 70% | 0,131 A | ❌ "Sehat" | ✅ **"Tidak Seimbang"** |

Tampilkan **kedua putusan berdampingan di layar**. Ini menjawab pertanyaan *"kenapa tidak pakai if-else saja"* sebelum sempat ditanyakan.

---

## 7. YANG MASIH TERBUKA

| # | Pertanyaan | Dampak | Kepada siapa |
|---|---|---|---|
| **1** | 🔥 **Apakah dosen memaksudkan proyek tetap DC, atau justru harus pindah ke AC 220 V?** | **Menentukan seluruh arah proyek** | **Dosen** |
| 2 | Berapa unit kipas tepatnya? | Alokasi jalur A–E | Kamu |
| 3 | Apakah semua kipas dari batch yang sama? | Besar variasi antar unit (batch berbeda = generalisasi lebih baik) | Kamu |
| 4 | Stiker kipas: arus nominal, jumlah kawat, jumlah bilah | Verifikasi *headroom* & perhitungan orde | Kamu |
| 5 | RPM aktual | Membuka seluruh perhitungan frekuensi; menentukan apakah 4 kSPS cukup | Kamu (aplikasi *strobe* HP / sensor IR) |

### Pertanyaan untuk dosen (poin 1)

Masukan sebelumnya — *"ceritanya belum satu garis karena membahas motor AC di awal padahal proyeknya DC"* — punya dua tafsir yang sangat berbeda:

> **Tafsir A:** "Buang bagian AC-nya, jadikan semuanya DC." → Revisi 2 sudah menjawabnya.
> **Tafsir B:** "Kalau latar belakangnya motor industri AC, proyeknya juga harus AC." → perlu pindah total.

Kalimat yang bisa kamu pakai:

> *"Pak/Bu, setelah masukan tadi saya sudah selaraskan seluruh narasinya ke domain motor DC — kipas pendingin DC pada panel dan rak perangkat, dengan INA226 sebagai sensornya. Apakah ini sesuai maksud Bapak/Ibu, atau justru sebaiknya proyeknya yang dipindah ke 220 V AC agar sejalan dengan konteks motor industri?"*

---

## 8. LANGKAH SELANJUTNYA (berurut prioritas)

| Prioritas | Tindakan | Catatan |
|---|---|---|
| 🔥 **HARI INI** | **Nyalakan 2 kipas 24/7 (Jalur D)** | Biaya nol, tapi **nilainya hilang permanen kalau ditunda**. Berpeluang memberi dataset penuaan sungguhan dalam 3–4 bulan |
| 🔥 **Segera** | **Tanya dosen: DC atau AC?** | Menghindari mengerjakan arah yang salah |
| 2 | Cek stiker kipas + ukur RPM | Membuka semua perhitungan |
| 3 | Rakit rig minimal: INA226 + ESP32-S3, rekam 10 detik data mentah per kipas | Belum perlu ML sama sekali |
| 4 | **Plot FFT-nya di Python** — cek apakah puncak orde muncul sesuai prediksi Bagian 1 | Membuktikan fisikanya |
| 5 | **Uji kelayakan:** rekam 6–8 kipas sehat, plot bertumpuk → ukur sebaran antar unit. Lalu 1 kipas + 100 mg → hitung *effect size* | **Kriteria lulus: ada beberapa ciri dengan Cohen's d > 2** |
| 6 | Baru setelah lulus uji kelayakan: pengumpulan data penuh sesuai matriks | |
| 7 | Pelatihan model, kuantisasi, *deployment*, pengujian dua lapis | |

> **Langkah 5 adalah gerbang proyek ini.** Kalau variasi produksi antar kipas sehat sama besar dengan efek gangguan, model tidak akan pernah bisa memisahkannya — dan lebih baik kamu tahu itu di minggu pertama, bukan di bulan ketiga. Kalau gagal, solusinya: perbesar massa ketidakseimbangan atau perkuat mekanisme gangguan.

---

## 9. STATUS DOKUMEN

| Dokumen | Revisi | Isi | Perlu diperbarui? |
|---|---|---|---|
| Proposal utama (`proposal-edge-ai-nilm-esp32s3.md`) | **Rev 2** | Tujuan, Latar Belakang, Dasar Teori, Spesifikasi, Batasan, Kontribusi, Antisipasi Pertanyaan | ✅ **Ya → Rev 3** |
| Ringkasan ini | Rev 1 | Catatan keputusan & status | — |

**Yang perlu masuk Revisi 3:**

1. Beban uji: kipas 5 cm (bukan 120 mm) — dan mengapa ini justru lebih sesuai narasi
2. Laju cuplik 4 kSPS, FFT 1.024 titik, Nyquist 2 kHz + perhitungan orde untuk RPM sebenarnya
3. Struktur **4 kelas** menggantikan 3 kelas
4. ***Order tracking*** sebagai metode ekstraksi ciri
5. Metode simulasi gangguan: massa bertingkat + pelumas dibersihkan (menggantikan "beban di bilah")
6. Matriks eksperimen multi-unit + **leave-one-unit-out**
7. Bagian baru: **Skenario Demo** (portabilitas sebagai persyaratan rancangan)
8. Bagian baru: **Kurva sensitivitas deteksi** sebagai hasil kuantitatif yang ditargetkan
9. Tambahan antisipasi pertanyaan: *"bagaimana Anda tahu model mengenali gangguan, bukan identitas unit kipas?"*

---

## Referensi yang sudah terverifikasi

1. SEPA Europe GmbH, *Fans, Service life, MTBF* — "bantalan poros motor adalah elemen penentu umur pakai kipas"; probabilitas kegagalan naik **logaritmik** terhadap suhu. https://www.sepa-europe.com/en/2006/08/25/fans-service-life-mtbf/
2. NMB Technologies, *Ball vs. Sleeve: A Comparison in Bearing Performance* — pada ≥70 °C kipas *sleeve bearing* berhenti berfungsi, *ball bearing* bertahan 45.000 jam. https://nmbtc.com/white-papers/ball-vs-sleeve-a-comparison-in-bearing-performance/
3. Texas Instruments, *INA226* — lembar data.
4. Espressif Systems, *ESP32-S3 Technical Reference Manual*; pustaka **ESP-DSP** dan **ESP-NN**.
5. Literatur *Motor Current Signature Analysis* (MCSA) — teknik yang diadaptasi ke ranah motor DC kecil.
6. Teknik *order tracking* dalam analisis vibrasi mesin berputar.
