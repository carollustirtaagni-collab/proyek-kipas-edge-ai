# Skenario Demo — Deteksi Kondisi Kipas DC dengan *Edge AI*

*Durasi total ±10 menit (demo inti ±6 menit + tanya jawab). Semua klasifikasi berjalan di ESP32-S3; laptop hanya dipakai sebagai layar (Serial Monitor) dan tidak memerlukan internet.*

---

## 1. Perlengkapan yang dibawa

| Barang | Keterangan |
|---|---|
| ESP32-S3 + modul INA226 (modul yang **sama** dengan saat pengambilan data) | Firmware `03_klasifikasi` sudah terpasang |
| Catu daya 12 V + kapasitor 1000 µF | Sama seperti saat pengambilan data |
| Dudukan kipas yang diperkuat | Kipas harus terikat kokoh |
| **U11** (tipe B) dan **U02** (tipe A) | Kipas kontrol jalur E, masih utuh |
| Karton juring 50 % | Untuk blokade di sisi tiup |
| LED strip pendek (±71 mA) | Beban non-kipas |
| Laptop + kabel USB | Serial Monitor 115200 baud, port UART (CH343) |
| OLED SSD1306 + tombol KALIBRASI & MULAI (opsional) | Bila terpasang, demo dapat dijalankan tanpa laptop: tombol KALIBRASI menggantikan perintah `k`, tombol MULAI memulai/menghentikan pembacaan. *Belum diuji dengan perangkat fisik.* |
| Cadangan: kabel USB kedua, selotip, *cable tie* | |
| Lembar ringkasan hasil (bagian 5) | Dicetak atau ditampilkan di layar |

---

## 2. Persiapan sebelum dosen datang (±10 menit)

1. Rangkai sistem dan colok kabel USB ke port **UART/COM**, bukan port USB *native*.
2. Buka Arduino IDE → Serial Monitor → **115200 baud**, akhiran **No line ending**.
3. Pasang **U11** di dudukan tanpa karton, nyalakan 12 V, dan biarkan **±5 menit** (pemanasan).
4. Pastikan baris keluaran muncul setiap ±0,26 detik.
5. Kirim **`r`** untuk menghapus kalibrasi lama, supaya kalibrasi bisa diperagakan di depan dosen.
6. Siapkan karton 50 % dan LED strip di dekat dudukan.

---

## 3. Alur demo

### Babak 1 — Kalibrasi: "alat mengenal kipasnya sendiri" (±1 menit)

**Tindakan:** kirim **`k`** di Serial Monitor (atau tahan tombol BOOT ±2 detik).

**Yang terlihat:**
```
# KALIBRASI SELESAI: arus patokan 64.14 mA, riak/DC patokan 0.2557
I= 64.37 mA  dI= +0.4%  P=[0.99 0.01 0.00]  jendela: Sehat | KONDISI: Sehat (5/5)  ciri 10051 us, inferensi 124 us
```

**Narasi:**
> "Setiap kipas, walaupun mereknya sama, punya karakter arus sendiri. Dari 11 kipas yang kami ukur, arus kipas sehat berkisar 63–78 mA dan ternyata ada dua tipe rangkaian penggerak yang berbeda. Karena itu alat ini dikalibrasi sekali saat dipasang: 10 detik merekam kondisi normal kipas, lalu patokannya disimpan di memori ESP32."

Tunjukkan bahwa inferensi hanya **±125 µs** dan seluruh proses terjadi di ESP32.

### Babak 2 — Diagnosis aliran terhambat (±2 menit)

**Tindakan:** tempel **karton 50 %** di sisi tiup, tunggu ±30 detik.

**Yang terlihat:** `KONDISI: Aliran Terhambat (5/5)`, ΔI sekitar **+4 %**.

**Narasi:**
> "Saluran udara yang tersumbat membuat kipas bekerja lebih berat: putaran turun dan arus naik sekitar 4 %. Kipas U11 ini tidak pernah dipakai saat melatih model untuk kondisi terhambat, jadi ini benar-benar kipas yang 'baru' bagi model."

**Tindakan:** lepas karton, tunggu ±30 detik → `KONDISI: Sehat`.

> "Begitu sumbatan dibuang, alat kembali menyatakan kipas sehat. Pemungutan suara 5 jendela terakhir mencegah hasil berkedip-kedip."

### Babak 3 — Mengenali batas pengetahuannya: Tidak Dikenal (±1 menit)

**Tindakan:** lepas kipas, pasang **LED strip pendek** di terminal yang sama (tanpa kalibrasi ulang).

**Yang terlihat:** `KONDISI: Tidak Dikenal (5/5)`, keyakinan **1,00**.

**Narasi:**
> "Arus LED ini hampir sama dengan arus kipas, hanya +8,5 % dari patokan. Sistem tidak memaksakan jawaban 'sehat' atau 'terhambat'; model melihat bahwa riaknya hampir nol, jadi ini bukan kipas yang ia kenal. Untuk perubahan arus yang besar, misalnya kipas dilepas atau dua kipas sekaligus, ada pengaman fisik: perubahan lebih dari 25 % langsung dinyatakan Tidak Dikenal."

### Babak 4 — Lintas tipe kipas (±1,5 menit)

**Tindakan:** pasang **U02** (tipe A), tunggu ±1 menit, kirim **`k`** (kalibrasi untuk kipas baru), lalu ulangi karton 50 %.

**Yang terlihat:** Sehat setelah kalibrasi → Aliran Terhambat dengan karton.

**Narasi:**
> "U02 berasal dari tipe penggerak yang berbeda. Bentuk arusnya jauh berbeda dari U11 (riak 6 % vs 25 % dari arus DC), tetapi model yang sama tetap bekerja setelah kalibrasi."

> ✅ **Diuji 20-10-2026:** U02 dikalibrasi pada 74,09 mA → Sehat 49/50; dengan karton 50 % → Aliran Terhambat 104/105 setelah ±1 menit (ΔI +2,7 %, keyakinan 0,80–0,87). Efek blokade pada U02 lebih kecil daripada U11, jadi **tunggu ±1 menit** setelah karton dipasang sebelum menjelaskan hasil. Pastikan U02 sudah hangat sebelum kalibrasi (arus dingin ±78 mA, hangat ±74 mA).

**Variasi menarik (opsional, sebelum kalibrasi U02):** pasang U02 **tanpa** kalibrasi ulang. Alat menampilkan **Tidak Dikenal**, karena kipas ini berbeda dari kipas yang dikalibrasi (riak/DC 6 % vs 25 %). Ini cara paling meyakinkan untuk menjawab "kenapa perlu kalibrasi?".

### Babak 5 — Mengapa tidak cukup dengan ambang batas arus? (±1 menit, slide)

Tampilkan tabel di bagian 5. Pesan kunci:

> "Aturan 'kalau arus di atas X mA berarti tersumbat' gagal: U03 dalam kondisi **sehat** menarik 77,9 mA, lebih besar dari U01 yang **tersumbat** (76,0 mA). Dengan aturan absolut seperti ini, akurasi hanya 40,8 %. Model kami 95,7 % pada kipas yang tidak pernah dilihat saat pelatihan dan pada hari yang berbeda."

---

## 4. Rencana cadangan

| Masalah | Tindakan |
|---|---|
| Serial Monitor kosong / port tidak ada | Cabut-colok USB di port **UART** (bukan port *native*); pilih port CH343 |
| Muncul `# ERROR akuisisi` | Periksa kabel ALERT (GPIO7) dan I²C; tekan RESET |
| Setelah karton dipasang masih "Sehat" | Tunggu 30–60 detik (kipas butuh waktu menyesuaikan beban); pastikan karton di **sisi tiup** dan tidak menyentuh bilah |
| Kipas sehat terbaca "Terhambat" | Kipas belum hangat saat kalibrasi → tunggu 5 menit, kirim `k` lagi |
| Semua jendela "Tidak Dikenal" | Kalibrasi berasal dari kipas lain → kirim `k` untuk kipas yang terpasang |
| Kipas bergetar/bergeser | Cabut 12 V, ikat ulang ke dudukan |

---

## 5. Ringkasan hasil untuk slide

**Evaluasi tersulit:** kipas yang tidak pernah dipakai saat pelatihan (*leave-one-unit-out*) **dan** data dari hari yang berbeda dari kalibrasi.

| Metode | Akurasi | Recall Sehat | Recall Terhambat | Recall Tidak Dikenal |
|---|---|---|---|---|
| Ambang batas I_RMS absolut | 40,8 % | 89,8 % | 14,0 % | 0,4 % |
| **MLP int8 di ESP32 (sistem ini)** | **95,7 %** | **100 %** | **91,5 %** | **99,8 %** |

| Spesifikasi | Target | Hasil |
|---|---|---|
| Latensi inferensi | < 5 ms | **0,125 ms** |
| *End-to-end* | < 300 ms | **±263 ms** |
| Alarm palsu (Sehat hari lain) | ≤ 5 % | **0,0 %** |
| Ukuran model | < 25 KB | **±1 KB** |
| Unit tipe C yang tidak pernah dilatih (U09) | — | dikenali Sehat 100 % |

---

## 6. Gladi (lakukan minimal sekali sebelum hari demo)

- [ ] Babak 1–3 dengan U11 (sudah berhasil pada uji 20-10-2026)
- [x] Babak 4 dengan U02 (berhasil pada uji 20-10-2026; tunggu ±1 menit setelah karton dipasang)
- [ ] Waktu total ≤ 6 menit
- [ ] Coba rencana cadangan: cabut-colok USB, kalibrasi ulang

---

## 7. Antisipasi pertanyaan penguji

**"Bagaimana Anda tahu model mengenali gangguan, bukan mengenali unit kipas?"**
> Validasi *leave-one-unit-out*: setiap kipas diuji oleh model yang tidak pernah melihat kipas itu. Kipas U09 (tipe ketiga) yang sama sekali tidak dipakai saat pelatihan dikenali Sehat 100 %. Ciri yang dipakai adalah bentuk riak dan **perubahan** arus terhadap patokan kipas itu sendiri, bukan nilai arus absolut.

**"Kenapa kelas Tidak Seimbang tidak ada, padahal di proposal ada?"**
> Kami menguji massa 34, 68, dan 103 mg pada dua kipas. Kipas bergetar kuat secara mekanis, tetapi perubahan pada arus terlalu kecil dibanding fluktuasi alami kipas (*effect size* d < 1,2, syarat d > 2). Sesuai rancangan cadangan di proposal, kami beralih ke 3 kelas dan melaporkannya sebagai hasil negatif terukur. Bilah patah, yang merupakan ketidakseimbangan jauh lebih besar, tetap terdeteksi jelas di spektrum (d = 4,1).

**"Kalau sudah ada kalibrasi, bukankah ambang batas sederhana juga bisa?"**
> Benar, dan kami melaporkannya secara terbuka: ambang batas relatif terhadap patokan mencapai 99,3 % pada data kami. Model AI tetap memberi nilai tambah karena belajar batas keputusan dan kelas Tidak Dikenal langsung dari data, tanpa menyetel angka ambang secara manual, dan memakai bentuk riak, bukan hanya besar arus. Perbandingan untuk beban non-kipas yang kenaikan arusnya mirip blokade belum kami uji.

**"Kenapa tidak memakai sapuan PWM seperti di proposal?"**
> PWM memutus-sambung arus kipas pada frekuensi tinggi, sedangkan INA226 hanya mencuplik ±3000 kali per detik, sehingga terjadi *aliasing* berat. Ditambah keterbatasan waktu, semua kelas direkam pada 12 V. Akibatnya ketahanan terhadap perubahan kecepatan belum diuji; ini kami catat sebagai keterbatasan.

**"Kenapa arus INA226 berbeda dari multimeter?"**
> Multimeter membaca ±15 % lebih tinggi; kemungkinan nilai *shunt* modul di bawah 0,1 Ω. Karena seluruh data dan demo memakai modul INA226 yang sama, selisih skala konstan ini tidak memengaruhi klasifikasi.
