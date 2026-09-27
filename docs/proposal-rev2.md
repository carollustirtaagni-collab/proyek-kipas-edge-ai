# Sistem Deteksi Dini Degradasi Beban Bermotor DC Berbasis *Edge AI* Melalui Analisis Sidik Jari Arus pada ESP32-S3

*Dokumen dasar untuk pemaparan proyek — Revisi 2 (penyelarasan narasi ke domain arus searah)*

---

## BENANG MERAH PROYEK

> Pada sistem kelistrikan **arus searah**, motor DC — kipas pendingin dan pompa — adalah **satu-satunya komponen yang aus secara mekanis**. Ia tidak mati mendadak, melainkan melemah perlahan melalui bantalannya; degradasinya **mempercepat dirinya sendiri** melalui kenaikan suhu; **tidak ada yang memantau kondisinya**; dan ia justru paling banyak dipasang di tempat yang **jauh dari teknisi dan tanpa jaringan internet**. Karena itu diperlukan pemantau berbasis **arus**, bersifat **non-invasif**, **berbiaya rendah**, dan **berpikir sendiri di tempat**.

Seluruh keputusan rancangan dalam dokumen ini diturunkan dari kalimat tunggal di atas:

| Bagian dari kalimat | Konsekuensi rancangan |
|---|---|
| "sistem kelistrikan **arus searah**" | INA226 — pemantau daya DC berbasis *shunt* — menjadi sensor yang **alami**, bukan kompromi |
| "**aus secara mekanis** melalui bantalan" | Kelas Anomali didefinisikan sebagai peningkatan gesekan dan ketidakseimbangan mekanis |
| "**melemah perlahan**" | Deteksi dini menjadi bermakna; gejalanya ada di riak arus, bukan di arus rata-rata |
| "**mempercepat dirinya sendiri**" | Nilai ekonomis deteksi dini tinggi — menghentikan lingkaran umpan balik positif |
| "**tidak ada yang memantau**" | Celah yang diisi proyek ini |
| "**non-invasif**" | Pengukuran dilakukan di jalur catu daya, bukan sensor tempel pada tiap mesin |
| "**jauh dari teknisi, tanpa internet**" | Inferensi wajib berjalan di perangkat (*edge AI*), bukan di awan |
| "**berbiaya rendah**" | ESP32-S3 + INA226, bukan instrumen laboratorium |

---

## 1. TUJUAN

### 1.1 Tujuan Umum

Merancang dan merealisasikan perangkat pemantau kondisi **beban bermotor arus searah (kipas dan pompa DC)** yang mampu **mendeteksi degradasi mekanis secara dini, waktu-nyata, dan mandiri tanpa koneksi internet**, hanya dari satu titik pengukuran arus pada jalur catu dayanya, dengan menjalankan model kecerdasan buatan langsung di dalam mikrokontroler (*edge AI*).

Inti gagasannya: sensor arus secara fisik hanya mampu menjawab *"berapa ampere yang mengalir sekarang?"*. Dengan menambahkan lapisan kecerdasan buatan, perangkat yang sama dapat menjawab pertanyaan yang jauh lebih tinggi tingkatannya: *"apakah bantalan motor ini masih sehat?"*

### 1.2 Tujuan Khusus

1. **Merancang sistem akuisisi sinyal arus berkecepatan tinggi** (≥ 2.000 sampel/detik) menggunakan INA226 dan ESP32-S3, sehingga komponen **riak (*ripple*) arus** — pembawa informasi kondisi mekanis motor — dapat terekam, bukan hanya nilai rata-ratanya.

2. **Merumuskan dan mengimplementasikan ekstraksi ciri** sinyal arus dalam kawasan waktu dan kawasan frekuensi yang berjalan sepenuhnya di dalam perangkat.

3. **Melatih jaringan saraf tiruan dan mengkuantisasinya ke integer 8-bit (int8)** agar muat dan berjalan efisien dalam keterbatasan memori serta daya komputasi ESP32-S3.

4. **Mengimplementasikan inferensi *on-device*** yang membedakan minimal tiga kelas:

   | Kelas | Nama | Definisi fisis |
   |---|---|---|
   | *True 1* | **Sehat** | Motor DC berputar dengan gesekan bantalan normal dan aliran udara/fluida lancar |
   | *True 2* | **Terdegradasi** | Gesekan bantalan meningkat, bilah tidak seimbang, atau aliran terhambat |
   | Ketiga | **Tidak Dikenal** | Motor mati, beban jenis lain pada jalur yang sama, atau masa transisi penyalaan |

5. **Membuktikan secara kuantitatif** bahwa pendekatan *edge AI* mengungguli metode ambang batas (*threshold*) konvensional pada kondisi operasi yang bervariasi.

6. **Mengukur unjuk kerja sistem** terhadap spesifikasi rancangan awal: latensi, akurasi, dan dimensi fisik.

---

## 2. LATAR BELAKANG

### 2.1 Sistem arus searah dan satu-satunya bagian yang aus

Sistem kelistrikan arus searah semakin banyak dijumpai: pembangkit listrik tenaga surya (PLTS) mandiri di daerah tanpa jaringan PLN, panel kendali industri, rak perangkat elektronik dan telekomunikasi, kendaraan listrik ringan, hingga *DC microgrid*.

Yang menarik dari sistem semacam ini adalah komposisinya. Hampir seluruh komponennya bersifat **solid-state** — modul surya, pengendali pengisian, konverter DC-DC, baterai, papan elektronik — yang **tidak memiliki bagian bergerak**. Dari keseluruhan sistem, praktis hanya ada satu jenis komponen yang **mengalami keausan mekanis**:

> **Beban bermotor: kipas pendingin dan pompa DC.**

Konsekuensi logisnya langsung: dalam sistem arus searah, motor DC adalah **titik kegagalan mekanis satu-satunya**, sekaligus komponen yang paling layak dipantau.

### 2.2 Bagaimana motor DC rusak: perlahan, melalui bantalannya

Kipas DC modern umumnya bertipe **brushless (BLDC)**, dengan komutasi dilakukan secara elektronik dan tanpa kontak mekanis. Hilangnya sikat arang menghapus satu sumber keausan, namun justru memusatkan seluruh keausan pada satu titik. Sebagaimana dinyatakan produsen kipas SEPA Europe:

> *"The bearings of the motor shaft represent the decisive service life element in the fan."*

Mekanismenya bersifat progresif, bukan mendadak:

```
Pelumas bantalan menguap / terdegradasi
        ↓
Gesekan bantalan meningkat
        ↓
Putaran (RPM) menurun, torsi riak meningkat
        ↓
Aliran udara / debit fluida berkurang
        ↓
Kipas masih "menyala" — tidak ada indikasi apa pun bagi pengguna
        ↓
(berminggu-minggu hingga berbulan-bulan kemudian)
        ↓
Motor berhenti total
```

Inilah premis yang memungkinkan seluruh proyek ini: **terdapat jendela waktu yang panjang antara mulainya degradasi dan kegagalan total** — asalkan tersedia alat yang mampu membaca gejala halusnya.

Pada motor DC bersikat (*brushed*), terdapat satu mekanisme tambahan: keausan sikat dan komutator, yang secara langsung mengubah bentuk gelombang arus komutasi. Ini justru memperkuat pendekatan berbasis arus yang digunakan proyek ini.

### 2.3 Lingkaran setan: degradasi yang mempercepat dirinya sendiri

Umur bantalan kipas sangat bergantung pada suhu. SEPA Europe menyatakan bahwa **probabilitas kegagalan meningkat secara logaritmik terhadap suhu**. Studi perbandingan NMB Technologies memperlihatkan hal serupa: pada suhu 70 °C ke atas, kipas berbantalan luncur (*sleeve bearing*) berhenti berfungsi, sementara kipas berbantalan bola masih bertahan hingga 45.000 jam — padahal pada suhu rendah keduanya setara.

Hal ini menciptakan umpan balik positif yang berbahaya:

```
        ┌─────────────────────────────────┐
        ↓                                 │
  Bantalan aus  →  Aliran udara turun  →  Suhu naik
        ↑                                 │
        └─────────────────────────────────┘
          (umur bantalan turun logaritmik
           terhadap kenaikan suhu)
```

Artinya, kipas yang mulai melemah **mempercepat kerusakannya sendiri** — dan pada saat yang sama membiarkan peralatan yang seharusnya ia dinginkan bekerja pada suhu berlebih. Kerugian sesungguhnya sering kali bukan pada kipasnya (yang harganya puluhan ribu rupiah), melainkan pada **peralatan yang gagal ia lindungi**.

Menghentikan lingkaran ini sedini mungkin adalah nilai ekonomis utama dari proyek ini.

### 2.4 Mengapa selama ini tidak ada yang memantaunya

Ironisnya, kipas dan pompa DC justru merupakan komponen yang paling jarang dipantau. Penyebabnya terletak pada ketidakseimbangan biaya dan akses:

| Metode | Mengapa tidak terpakai pada kipas/pompa DC |
|---|---|
| Analisis getaran (akselerometer) | Sensor harus ditempel pada badan motor; satu sensor untuk satu unit; harga sensor sering melebihi harga kipasnya sendiri |
| Sensor tachometer / sinyal RPM | Hanya tersedia pada kipas 4-kawat; mendeteksi penurunan RPM yang sudah lanjut, bukan gejala awal; tidak ada pada pompa |
| Pemantauan suhu | Mendeteksi akibat, bukan sebab — pada saat suhu naik, degradasi sudah berjalan jauh |
| Inspeksi manual berkala | Tidak praktis untuk instalasi terpencil (PLTS desa, menara telekomunikasi); tidak kontinu |
| Analisis akustik | Sangat rentan derau lingkungan |

Yang dibutuhkan adalah metode yang **tidak menyentuh motornya sama sekali**, **berbiaya jauh di bawah objek yang dipantau**, dan **bekerja terus-menerus tanpa kehadiran manusia**.

### 2.5 Arus sebagai jendela menuju kondisi mekanis

Terdapat satu besaran yang secara alamiah sudah melewati satu titik dan membawa informasi tentang kondisi mekanis motor: **arus catu dayanya sendiri**.

Gagasan ini merupakan adaptasi dari *Motor Current Signature Analysis* (MCSA), teknik yang telah mapan di dunia motor industri, ke dalam konteks **motor DC berdaya kecil**. Dasarnya adalah bahwa arus yang ditarik motor dapat diuraikan menjadi dua bagian:

$$i(t) = \underbrace{I_{DC}}_{\text{seberapa banyak daya diambil}} + \underbrace{i_{ripple}(t)}_{\text{bagaimana cara daya diambil}}$$

Alat ukur konvensional hanya membaca bagian pertama. Bagian kedua — riak arus — merupakan cerminan langsung dari proses elektromekanis di dalam motor: komutasi, putaran, torsi beban, dan keseimbangan massa yang berputar. Ketika bantalan mulai seret:

- Putaran menurun → frekuensi riak komutasi **bergeser turun**
- Torsi riak meningkat → amplitudo riak **membesar**
- Ketidakseimbangan massa (misalnya penumpukan debu tidak merata) → muncul **komponen sub-harmonik** pada frekuensi putaran

Semua gejala ini muncul **sebelum arus rata-rata berubah secara berarti**, dan semuanya berada dalam pita frekuensi di bawah 1 kHz sehingga dapat diamati dengan perangkat berbiaya rendah.

### 2.6 Mengapa ambang batas tidak cukup — di sinilah AI diperlukan

Pendekatan paling sederhana adalah aturan ambang batas: *"jika arus melebihi X ampere, maka motor bermasalah."* Pendekatan ini **runtuh dalam kondisi operasi nyata**, karena arus yang ditarik kipas atau pompa DC bukan besaran tetap — ia berubah mengikuti tegangan baterai yang menurun sepanjang hari, suhu lingkungan, dan pengaturan kecepatan PWM. Akibatnya:

> Kipas **sehat** yang berputar pada kecepatan penuh dapat menarik arus **lebih besar** daripada kipas **terdegradasi** yang berputar pada kecepatan rendah.

Dalam situasi ini tidak ada satu pun nilai ambang batas yang mampu memisahkan keduanya, karena informasi pembedanya **tidak terletak pada amplitudo arus, melainkan pada bentuk spektrumnya**. Memisahkan pola berdimensi tinggi semacam ini — yang tidak dapat dinyatakan sebagai satu pertidaksamaan sederhana — secara alamiah merupakan ranah pembelajaran mesin.

Inilah justifikasi utama penggunaan AI dalam proyek ini, dan ia akan **dibuktikan secara eksperimental, bukan sekadar diklaim** (lihat Bagian 4.2).

### 2.7 Mengapa harus di *edge*, bukan di *cloud*

Pada domain ini, alasannya bukan sekadar preferensi teknis melainkan **tuntutan lokasi**:

- **Tidak ada internet.** PLTS desa, menara telekomunikasi terpencil, dan panel kendali di area industri justru merupakan tempat paling membutuhkan pemantauan, sekaligus tempat paling minim konektivitas. Sistem yang bergantung pada jaringan tidak akan berfungsi di sana.
- **Anggaran daya sangat ketat.** Sistem bertenaga baterai tidak dapat menanggung modul radio yang memancar terus-menerus. Inferensi lokal hanya perlu mengirim beberapa byte hasil klasifikasi — itu pun opsional dan jarang.
- **Volume data mentah.** Pencuplikan 2.000 titik/detik × 16 bit ≈ 32 kbps secara terus-menerus per titik ukur. Mengirim data mentah ini tidak masuk akal secara kuota maupun biaya.
- **Waktu tanggap.** Pemantauan yang berguna harus bekerja saat itu juga, tanpa bergantung pada ketersediaan jaringan.

Dengan kata lain, pada proyek ini *edge AI* **bukan pilihan arsitektur, melainkan syarat kelayakan.**

### 2.8 Kemampuan mengatakan "saya tidak tahu"

Sebagian besar model klasifikasi dilatih sebagai **sistem tertutup (*closed-set*)** — dipaksa memilih salah satu kelas yang pernah dilihatnya. Konsekuensinya berbahaya: ketika perangkat menghadapi sesuatu yang belum pernah diajarkan (beban jenis lain dinyalakan pada jalur yang sama, atau sistem sedang dalam masa transisi), model tetap menjawab dengan penuh keyakinan — dan jawaban itu pasti salah.

Untuk sistem pemantauan yang akan dipercaya orang, kemampuan **mengenali batas pengetahuannya sendiri** sama pentingnya dengan kemampuan menjawab benar. Karena itu kelas *Tidak Dikenal* bukan sekadar pemenuhan syarat tugas, melainkan bagian dari perancangan sistem yang jujur (*open-set recognition*).

### 2.9 Posisi proyek ini

Proyek ini menyatukan tiga hal yang jarang ditemukan bersamaan dalam satu perangkat berbiaya rendah:

1. **Pengukuran arus DC beresolusi mikroampere** (16-bit, 25 µA) — memungkinkan riak halus terbaca, bukan hanya arus rata-rata.
2. **Inferensi AI sepenuhnya di dalam perangkat**, sehingga berfungsi penuh tanpa jaringan dan tanpa daya pemancar.
3. **Penanganan kelas tak dikenal secara eksplisit**, sehingga sistem tetap aman saat menghadapi kondisi di luar data latihnya.

---

## 3. DASAR TEORI

### 3.1 Landasan Teoretis

#### 3.1.1 Pengukuran arus dengan resistor *shunt* (Hukum Ohm)

Arus tidak dapat diukur langsung oleh ADC; ia harus dikonversi menjadi tegangan melalui resistor bernilai sangat kecil (*shunt*):

$$V_{shunt} = I \times R_{shunt}$$

Dengan $R_{shunt} = 0{,}1\ \Omega$ dan arus 0,5 A, tegangan terukur adalah 50 mV. Nilai resistor dibuat sekecil mungkin agar **tidak mengganggu rangkaian yang diukur** (rugi daya $I^2R$ minimum), namun tetap cukup besar agar keluarannya terukur di atas derau.

Karena sistem yang dipantau **bersifat arus searah**, metode *shunt* dapat diterapkan secara langsung tanpa memerlukan transformator arus, penyearah, maupun isolasi galvanis. Inilah salah satu keuntungan struktural dari pemilihan domain DC.

#### 3.1.2 Analisis Sidik Jari Arus pada motor DC

Teknik *Motor Current Signature Analysis* (MCSA) berakar pada diagnosis motor induksi AC. Proyek ini **mengadaptasi prinsip yang sama ke ranah motor DC berdaya kecil**, dengan perbedaan mendasar pada sumber riaknya: bukan slip dan frekuensi jala-jala, melainkan **komutasi dan dinamika putaran**.

Uraian sinyalnya:

$$i(t) = I_{DC} + i_{ripple}(t)$$

- **$I_{DC}$** — berapa banyak daya yang diambil beban. Satu-satunya yang dibaca alat ukur konvensional.
- **$i_{ripple}(t)$** — bagaimana cara beban mengambil daya tersebut. Di sinilah identitas dan kondisi kesehatan motor tersimpan.

Proyek ini bekerja hampir seluruhnya pada komponen kedua.

#### 3.1.3 Sumber riak pada motor DC dan kaitannya dengan kondisi mekanis

**(a) Motor DC bersikat (*brushed*)** — komutator memutus dan menyambung arus tiap segmen:

$$f_{komutasi} = \frac{\text{RPM}}{60} \times N_{segmen}$$

**(b) Motor DC tanpa sikat (*BLDC*, umum pada kipas)** — komutasi dilakukan secara elektronik dalam enam langkah:

$$f_{listrik} = \frac{\text{RPM}}{60} \times p \qquad ; \qquad f_{komutasi} \approx 6 \times f_{listrik}$$

dengan $p$ = jumlah pasangan kutub.

**(c) Frekuensi lewat-bilah (*blade passing*)** — modulasi torsi akibat bilah melewati penyangga rumah kipas:

$$f_{bilah} = \frac{\text{RPM}}{60} \times N_{bilah}$$

**Contoh perhitungan** untuk kipas 12 V, 2.000 RPM, 2 pasang kutub, 7 bilah:

| Komponen | Frekuensi |
|---|---|
| Putaran (1×) | 33,3 Hz |
| Frekuensi listrik | 66,7 Hz |
| Riak komutasi (6×) | 400,0 Hz |
| Lewat-bilah | 233,3 Hz |

Seluruhnya berada dalam pita 0–1.000 Hz yang dapat diamati sistem ini.

**Kaitan dengan degradasi mekanis:**

| Gejala mekanis | Perubahan pada spektrum arus |
|---|---|
| Gesekan bantalan meningkat | Seluruh frekuensi **bergeser turun** (RPM menurun); amplitudo riak torsi meningkat |
| Ketidakseimbangan massa (debu tidak merata) | Muncul **komponen kuat pada 1× putaran** (33,3 Hz) dan pita sisi di sekitar frekuensi komutasi |
| Aliran udara terhambat | Torsi beban naik; distribusi energi pada harmonisa orde tinggi **berubah polanya** |

Inilah pola-pola yang dipelajari model AI. Yang penting dicatat: **gejala ini muncul pada motor yang arus rata-ratanya belum berubah secara berarti** — di situlah letak nilai diagnostik pendekatan ini.

#### 3.1.4 Teorema Nyquist dan Transformasi Fourier Cepat (FFT)

Teorema pencuplikan Nyquist–Shannon menyatakan bahwa untuk merekonstruksi sinyal berfrekuensi $f$, laju cuplik minimum adalah $2f$. Dengan laju 2.000 SPS, sistem dapat menganalisis kandungan frekuensi hingga **1.000 Hz** — mencakup seluruh komponen pada tabel Bagian 3.1.3.

FFT mengubah sinyal dari kawasan waktu ke kawasan frekuensi. Dengan jendela 512 titik pada 2.000 SPS:

$$\Delta f = \frac{f_s}{N} = \frac{2000}{512} \approx 3{,}9\ \text{Hz per bin}$$

Resolusi ini cukup halus untuk mendeteksi pergeseran frekuensi akibat penurunan putaran sebesar ±1%.

#### 3.1.5 Ekstraksi ciri (*feature extraction*)

Memasukkan 512 sampel mentah langsung ke jaringan saraf boros memori dan mudah *overfitting*. Sinyal diringkas menjadi ± 28 ciri yang bermakna secara fisis:

| Kelompok | Ciri | Makna fisis |
|---|---|---|
| Kawasan waktu | RMS riak, *crest factor*, *peak-to-peak*, *skewness*, *kurtosis*, *zero-crossing rate* | Kekasaran dan kesimetrian bentuk gelombang |
| Kawasan frekuensi | Energi 16 pita logaritmik (10–1.000 Hz), *spectral centroid*, *spectral flatness*, frekuensi & amplitudo puncak dominan, rasio harmonisa | Distribusi energi, nada dominan, kandungan harmonisa |
| Aras DC | Arus rata-rata | Besar daya yang diambil |

#### 3.1.6 Jaringan Saraf Tiruan dan fungsi *Softmax*

```
Input (28 ciri) → Dense 32 (ReLU) → Dropout 0,3 → Dense 16 (ReLU) → Dense 3 (Softmax)
```

Fungsi **Softmax** mengubah skor mentah menjadi distribusi probabilitas atas ketiga kelas:

$$P(k) = \frac{e^{z_k}}{\sum_{j=1}^{3} e^{z_j}}, \qquad \sum_k P(k) = 1$$

Keluaran berbentuk probabilitas inilah yang memungkinkan penerapan ambang keyakinan pada Bagian 3.1.8.

#### 3.1.7 Kuantisasi INT8

Model hasil pelatihan menggunakan bilangan pecahan 32-bit yang boros memori dan lambat pada mikrokontroler. **Kuantisasi** memetakannya ke bilangan bulat 8-bit:

$$q = \text{round}\left(\frac{r}{S}\right) + Z$$

Hasilnya: ukuran model berkurang ±4×, kecepatan inferensi meningkat 2–4× (ESP32-S3 memiliki instruksi vektor SIMD untuk operasi integer), dengan penurunan akurasi umumnya di bawah 1–2%.

#### 3.1.8 Klasifikasi himpunan terbuka (*open-set*) dan ambang keyakinan

Kelas *Tidak Dikenal* ditangani dengan **dua lapis pengaman**:

1. **Lapis data:** kelas ini diisi secara eksplisit dengan contoh negatif yang beragam (motor mati, beban jenis lain, masa transisi penyalaan), sehingga model memiliki wilayah keputusan tersendiri untuknya.
2. **Lapis keputusan:** ambang keyakinan pada keluaran Softmax —

   ```
   jika max P(k) < 0,60  →  keluarkan "Tidak Dikenal"
   ```

#### 3.1.9 *Edge AI*

*Edge AI* adalah pelaksanaan inferensi model kecerdasan buatan langsung pada perangkat tempat data dihasilkan. Konsekuensi rancangannya: model harus **kecil** (kilobyte, bukan megabyte), **cepat** (milidetik), dan **hemat daya** — dicapai melalui penyederhanaan arsitektur, ekstraksi ciri manual, dan kuantisasi.

---

### 3.2 Komponen yang Digunakan dan Perannya

| No | Komponen | Spesifikasi | Peran dalam sistem |
|---|---|---|---|
| 1 | **ESP32-S3-DevKitC-1** | Xtensa LX7 *dual-core* 240 MHz, SRAM 512 KB, PSRAM 8 MB, instruksi vektor untuk AI | Otak sistem: akuisisi, pemrosesan sinyal, inferensi AI |
| 2 | **Modul INA226** | Pemantau daya DC I²C, ADC 16-bit, ±81,92 mV, konversi tercepat 140 µs | Sensor utama: mengubah arus menjadi data digital beresolusi tinggi |
| 3 | **Resistor *shunt* 0,1 Ω** | Bawaan modul INA226, 1% | Mengubah arus menjadi tegangan terukur |
| 4 | **Kipas DC 12 V (BLDC)** | 80–120 mm, 0,1–0,3 A | **Objek utama yang diklasifikasikan** (kelas Sehat & Terdegradasi) |
| 5 | **Pompa DC mini** | 12 V, 0,2–0,5 A | Beban bermotor kedua untuk menguji generalisasi |
| 6 | **Beban non-motor** | LED *strip* 12 V, resistor daya 47 Ω/10 W | Pengisi kelas *Tidak Dikenal* |
| 7 | **MOSFET IRLZ44N** | *Logic-level* | Saklar elektronik & pengatur PWM untuk memvariasikan titik kerja |
| 8 | **Catu daya 12 VDC** | Aki SLA / baterai | Sumber daya beban, bebas derau pensaklaran |
| 9 | **Modul *buck* 12→5 V** | MP1584 atau setara | Menurunkan 12 V ke 5 V untuk ESP32-S3 (mode berdiri sendiri) |
| 10 | **OLED SSD1306 0,96"** | 128×64, I²C | Menampilkan kelas hasil klasifikasi & tingkat keyakinan |
| 11 | **Resistor *pull-up* 2,2 kΩ ×2** | 1/4 W | Menjaga integritas sinyal I²C pada 1 MHz |
| 12 | **Kapasitor 100 nF** | Keramik | *Decoupling* catu INA226 & ESP32-S3 |
| 13 | **LED indikator + *buzzer*** | 5 mm / *buzzer* aktif 5 V | Penanda kondisi terdegradasi |

#### Penjelasan peran tiap komponen

**1. ESP32-S3 — Pusat pemrosesan dan pelaksana Edge AI**

Pemilihannya didasarkan pada tiga kemampuan yang secara spesifik dibutuhkan proyek ini:

- **Instruksi vektor (SIMD) untuk AI.** ESP32-S3 memiliki ekstensi instruksi 128-bit yang dirancang khusus untuk mempercepat perkalian matriks pada bilangan bulat — inti dari inferensi jaringan saraf terkuantisasi. Pustaka **ESP-NN** dari Espressif memanfaatkannya secara langsung. Inilah pembeda utamanya dari ESP32 generasi sebelumnya.
- **Dua inti prosesor.** Memungkinkan pemisahan tugas: satu inti menangani akuisisi dengan pewaktuan ketat (bebas *jitter*), inti lain menangani FFT dan inferensi.
- **Memori memadai.** Cukup untuk menampung penyangga melingkar, tabel FFT, dan bobot model sekaligus.

Espressif juga menyediakan pustaka **ESP-DSP** berisi rutin FFT dalam bahasa rakitan yang dioptimalkan untuk arsitektur Xtensa.

**2. Modul INA226 — Sensor arus beresolusi tinggi, dan mengapa ia cocok secara alami**

INA226 adalah **pemantau daya arus searah berbasis *shunt***. Dalam banyak proyek, keterbatasannya (tidak dapat dipakai pada jaringan AC 220 V) merupakan kompromi. Pada proyek ini, karena domainnya memang sistem arus searah, **keterbatasan tersebut tidak pernah menjadi persoalan** — INA226 justru merupakan sensor yang paling tepat sasaran.

Dua parameternya menentukan keberhasilan proyek:

- **Resolusi 2,5 µV/LSB (ADC 16-bit).** Dengan *shunt* 0,1 Ω, ini setara **resolusi arus 25 µA**. Inilah yang membuat riak sebesar beberapa miliampere — sinyal utama proyek ini — terbaca dengan rasio sinyal-terhadap-derau ±33 dB. Sensor arus berbasis efek Hall hanya mencapai resolusi puluhan miliampere, sehingga riak tersebut akan tenggelam sepenuhnya dalam derau.
- **Waktu konversi dapat diprogram hingga 140 µs.** Memungkinkan laju cuplik hingga ±7 kSPS secara teoretis, jauh di atas kebutuhan 2 kSPS.

> **Catatan konfigurasi penting:** fitur *averaging* internal INA226 **harus dinonaktifkan** (AVG = 1). *Averaging* bekerja sebagai tapis lolos-rendah yang justru menghapus informasi riak yang hendak diklasifikasikan.

**3. Resistor *shunt* 0,1 Ω — Pengubah arus menjadi tegangan**

| Pertimbangan | Konsekuensi |
|---|---|
| Arus maksimum = 81,92 mV ÷ 0,1 Ω | 0,819 A — memadai untuk kipas dan pompa DC yang dipantau |
| Resolusi = 2,5 µV ÷ 0,1 Ω | 25 µA — 10× lebih halus dibanding *shunt* 0,01 Ω |
| Resistansi parasit jalur PCB (±2 mΩ) | Hanya 2% dari nilai *shunt* (pada 0,01 Ω menjadi 20%) |
| Disipasi daya pada 0,5 A | 25 mW — tanpa pemanasan sendiri yang menyebabkan *drift* antar sesi |

Trade-off berupa batas arus 0,819 A ditangani dengan (a) membatasi beban uji di bawah 0,6 A — rentang yang memang sesuai dengan kipas dan pompa DC sasaran, dan (b) menerapkan *blanking* 300 ms saat penyalaan untuk mengabaikan arus kejut (*inrush*).

**4–6. Beban uji — Objek klasifikasi**

**Kipas DC 12 V merupakan objek utama, dan sekaligus merupakan objek penerapan sesungguhnya** — tidak ada jarak antara benda yang diuji di laboratorium dan benda yang akan dipantau di lapangan. Ini memperkuat validitas hasil pengujian.

Kondisi terdegradasi disimulasikan secara **non-destruktif**, dengan tiap simulasi merepresentasikan moda kegagalan nyata:

| Simulasi | Moda kegagalan nyata yang diwakili |
|---|---|
| Beban kecil ditempel pada satu bilah | Penumpukan debu tidak merata pada bilah |
| Gesekan tambahan pada poros | Pelumas bantalan mengering / bantalan aus |
| Penutupan sebagian jalur udara | Filter tersumbat / saluran udara terhalang |

Beban dipilih dan dioperasikan agar rentang arusnya **saling tumpang tindih antar kelas**, dengan menyapu *duty cycle* PWM 40–100% pada setiap kelas. Ini disengaja — bila rentang arus tiap kelas terpisah rapi, metode ambang batas sederhana sudah cukup dan premis "diperlukan AI" menjadi gugur.

**7. MOSFET IRLZ44N — Saklar dan pengatur titik kerja**

Berperan ganda: (a) menghasilkan peristiwa penyalaan/pematian yang menjadi bagian kelas *Tidak Dikenal*, dan (b) mengatur PWM untuk memvariasikan titik kerja selama pengumpulan data. Tipe *logic-level* dipilih agar dapat digerakkan langsung oleh keluaran 3,3 V ESP32-S3.

**8. Catu daya 12 VDC — Sumber daya sekaligus penentu batas derau**

Adaptor *switching* murah menyuntikkan derau pensaklaran yang amplitudonya dapat **melebihi riak beban yang hendak diukur**. Karena itu untuk pengumpulan data disarankan **aki SLA atau baterai** — yang juga sesuai dengan domain penerapan (sistem DC bertenaga baterai).

> **Peringatan rancangan:** kapasitor tapis bernilai besar **tidak boleh dipasang paralel dengan beban** (setelah *shunt*). Kapasitor menjadi jalur berimpedansi rendah bagi komponen AC, sehingga riak mengalir ke kapasitor dan bukan melalui *shunt* — sinyal yang hendak diklasifikasikan akan hilang. Bila penapisan diperlukan, letaknya harus **sebelum *shunt***.

**9–13. Komponen pendukung**

- **Modul *buck* 12→5 V:** memungkinkan sistem berdiri sendiri tanpa kabel USB, sejalan dengan skenario penerapan mandiri.
- **OLED SSD1306:** menampilkan hasil klasifikasi, keyakinan, dan arus terukur secara lokal — mewujudkan prinsip *edge* bahwa informasi tersedia tanpa jaringan.
- **Resistor *pull-up* 2,2 kΩ:** nilai standar 10 kΩ terlalu besar untuk I²C 1 MHz; tepi sinyal akan melengkung dan komunikasi gagal.
- **Kapasitor *decoupling* 100 nF:** menstabilkan catu IC terhadap lonjakan arus sesaat.
- **LED & *buzzer*:** antarmuka peringatan langsung saat kelas Terdegradasi terdeteksi.

---

## 4. SPESIFIKASI ALAT (Target Rancangan Awal)

### 4.1 Latensi

#### Rincian anggaran waktu

| Tahap pemrosesan | Waktu | Keterangan |
|---|---|---|
| Pengisian jendela data (512 sampel @ 2 kSPS) | **256,0 ms** | Komponen dominan — ditentukan fisika pencuplikan |
| Pra-pemrosesan (pengurangan DC, jendela Hann) | ± 0,3 ms | |
| FFT 512 titik (ESP-DSP, *assembly* teroptimasi) | < 1 ms | |
| Ekstraksi 28 ciri | ± 0,5 ms | |
| Normalisasi *z-score* | < 0,1 ms | |
| Inferensi MLP int8 (ESP-NN) | ± 0,3 ms | |
| Pasca-pemrosesan & tampilan | ± 1 ms | |
| **Total** | **± 259 ms** | |

**Pengamatan penting:** komputasi AI hanya menyumbang sekitar **1% dari total latensi**. Sisanya adalah waktu yang secara fisis dibutuhkan untuk mengumpulkan cukup sampel. Ini menunjukkan ESP32-S3 sama sekali bukan hambatan — masih tersedia ruang komputasi besar untuk pengembangan model yang lebih kompleks.

#### Spesifikasi target

| Parameter | Target | Justifikasi |
|---|---|---|
| Latensi inferensi (jendela siap → keputusan) | **< 5 ms** | Memastikan beban komputasi AI dapat diabaikan |
| Latensi *end-to-end* keadaan tunak | **< 300 ms** | Didominasi waktu pengisian jendela |
| Latensi deteksi perubahan kondisi | **< 1 detik** | *Blanking* 300 ms + jendela 256 ms + pemungutan suara mayoritas 3 jendela |
| Laju keluaran keputusan | **≥ 7 keputusan/detik** | Dengan *hop* 128 ms (tumpang tindih 50%) |
| *Duty cycle* prosesor | **< 20%** | Menyisakan ruang untuk pengembangan |

> **Catatan perspektif:** degradasi bantalan berlangsung dalam hitungan minggu, sehingga latensi sub-detik jauh melampaui kebutuhan aplikasi. Target ketat ini ditetapkan bukan karena dituntut aplikasi, melainkan untuk **membuktikan kelayakan komputasi *edge*** — bahwa diagnosis semacam ini benar-benar dapat berjalan pada mikrokontroler berbiaya rendah, dan menyisakan ruang untuk memantau beberapa beban secara bergantian pada satu perangkat.

---

### 4.2 Akurasi

#### Spesifikasi target

| Metrik | Target | Alasan |
|---|---|---|
| **Akurasi keseluruhan** (data uji dari sesi terpisah) | **≥ 90%** | Ambang kelayakan sistem pemantauan |
| **Recall kelas Terdegradasi** | **≥ 92%** | Paling kritis — *false negative* berarti degradasi tidak terdeteksi, dan peralatan yang dilindungi kipas ikut terancam |
| **Recall kelas Sehat** | ≥ 90% | |
| **Recall kelas Tidak Dikenal** | ≥ 85% | Kelas paling sulit karena keragamannya tinggi |
| **Macro-F1** | ≥ 0,88 | Metrik seimbang, tidak bias terhadap kelas mayoritas |
| **Laju alarm palsu** (Sehat → Terdegradasi) | **≤ 5%** | Alarm palsu berlebihan membuat sistem diabaikan penggunanya |
| **Penurunan akurasi pada sesi uji baru** | ≤ 5 poin persentase | Menguji kemampuan generalisasi |

Target *recall* sengaja dibuat **asimetris**: melewatkan degradasi berkonsekuensi jauh lebih mahal daripada alarm palsu, karena kerugian sesungguhnya jatuh pada peralatan yang gagal didinginkan.

#### Pembanding wajib: pembuktian bahwa AI memang diperlukan

Sistem diuji berdampingan dengan **metode dasar berbasis ambang batas** pada data uji yang sama:

```
jika I_RMS < a        → Tidak Dikenal
jika a ≤ I_RMS < b    → Sehat
jika I_RMS ≥ b        → Terdegradasi
```

| Metode | Akurasi yang diharapkan |
|---|---|
| Ambang batas $I_{RMS}$ (metode dasar) | 55 – 70% |
| **Edge AI (usulan)** | **≥ 90%** |
| **Selisih yang ditargetkan** | **≥ +20 poin persentase** |

Karena rancangan percobaan sengaja membuat rentang arus antar kelas saling tumpang tindih, metode ambang batas secara teoretis tidak dapat mencapai akurasi tinggi. Perbandingan ini menjadi **bukti kuantitatif bahwa AI merupakan kebutuhan, bukan hiasan**.

#### Protokol pengujian

| Aspek | Ketentuan |
|---|---|
| Jumlah data | ≥ 300 jendela per kelas (ideal 600) |
| Jumlah sesi perekaman | ≥ 5 sesi per kelas, pada hari/suhu/tegangan berbeda |
| **Pembagian data** | **Berdasarkan sesi, bukan acak per jendela** |
| Data uji | 1 sesi penuh yang tidak pernah dilihat saat pelatihan |
| Pelaporan | *Confusion matrix*, *precision*/*recall*/F1 per kelas |

> **Catatan metodologis:** pembagian data secara acak per jendela menyebabkan **kebocoran data (*data leakage*)** — jendela yang saling tumpang tindih dari rekaman yang sama dapat masuk ke data latih dan data uji sekaligus, menghasilkan akurasi semu mendekati 99% yang tidak mencerminkan unjuk kerja sebenarnya. Pembagian berdasarkan sesi menghilangkan kebocoran ini.

---

### 4.3 Dimensi

| Bagian | Dimensi (P × L × T) | Keterangan |
|---|---|---|
| ESP32-S3-DevKitC-1 | 63 × 25,5 × 13 mm | Papan pengembang |
| Modul INA226 | ± 20 × 16 × 4 mm | |
| OLED SSD1306 0,96" | 27 × 27 × 4 mm | |
| Modul *buck* 12→5 V | 22 × 17 × 4 mm | |
| **Papan rakitan (PCB/protoboard)** | **≤ 90 × 60 mm** | Target rancangan |
| **Enklosur keseluruhan** | **≤ 110 × 75 × 45 mm** | Kotak proyek plastik standar |
| **Berat total** (tanpa beban uji) | **≤ 250 g** | |

Sasaran bentuk fisiknya adalah perangkat **seukuran genggaman tangan** yang dapat dipasang secara *inline* pada jalur catu kipas atau pompa, dengan hanya dua terminal masukan dan dua terminal keluaran — sejalan dengan tuntutan pemasangan non-invasif pada instalasi yang sudah berjalan.

---

### 4.4 Spesifikasi Pendukung

| Parameter | Target |
|---|---|
| Tegangan kerja bus | 12 VDC (batas IC: 36 V) |
| Rentang pengukuran arus | 0 – 0,8 A DC |
| Resolusi pengukuran arus | 25 µA (16-bit) |
| Laju pencuplikan | 2.000 SPS ± 1% |
| *Jitter* pencuplikan | < 5% dari perioda |
| Lebar pita analisis | 0 – 1.000 Hz |
| Resolusi frekuensi FFT | 3,9 Hz |
| Ukuran model terkuantisasi | < 25 KB |
| Pemakaian RAM saat berjalan | < 120 KB |
| Pemakaian *flash* | < 1,5 MB |
| Konsumsi daya sistem (di luar beban) | < 1 W (± 150 mA @ 5 V) |
| Antarmuka keluaran | OLED, serial UART, (opsional) *web server* lokal |
| Jumlah kelas keluaran | 3 (Sehat / Terdegradasi / Tidak Dikenal) |

---

## 5. BATASAN MASALAH

1. Sistem dirancang untuk **beban bermotor arus searah 12 V** — kipas dan pompa DC. Jaringan listrik AC 220 V berada di luar lingkup, baik secara domain maupun secara perangkat keras (INA226 memiliki batas tegangan *common-mode* 36 V).
2. Arus terukur dibatasi pada rentang **0–0,8 A**, sesuai kombinasi *shunt* 0,1 Ω dan batas tegangan INA226, serta sesuai rentang arus kipas dan pompa DC sasaran.
3. Lebar pita analisis dibatasi hingga **1 kHz** — mencakup seluruh frekuensi komutasi, putaran, dan lewat-bilah pada motor DC sasaran, namun tidak mencakup frekuensi pensaklaran konverter (ratusan kHz).
4. Kondisi degradasi **disimulasikan secara terkendali dan non-destruktif**; tidak dilakukan pengujian penuaan hingga kerusakan sebenarnya, yang memerlukan waktu berbulan-bulan.
5. Sistem mengklasifikasikan **satu beban bermotor dominan pada satu waktu**; pemisahan beban majemuk secara simultan (*load disaggregation*) berada di luar cakupan.

---

## 6. KONTRIBUSI DAN KEBARUAN

1. **Penerapan analisis sidik jari arus pada motor DC berdaya kecil.** Teknik MCSA umumnya diterapkan pada motor induksi industri berdaya besar dengan instrumen mahal. Proyek ini mengadaptasinya ke kipas dan pompa DC berdaya di bawah 10 watt menggunakan perangkat keras berbiaya rendah.

2. **Pemanfaatan pengukuran arus beresolusi mikroampere untuk diagnosis kondisi mekanis.** Penggunaan ADC 16-bit berbasis *shunt* membuka akses ke informasi riak yang tidak terjangkau sensor efek Hall konvensional.

3. **Inferensi sepenuhnya di perangkat pada mikrokontroler berbiaya rendah.** Model berjalan dalam bujet < 25 KB dan < 5 ms, membuktikan bahwa diagnosis kondisi mesin dapat berjalan tanpa jaringan dan tanpa infrastruktur awan — syarat mutlak untuk instalasi DC terpencil.

4. **Penanganan kelas tak dikenal secara eksplisit dengan dua lapis pengaman**, yang jarang diterapkan pada penelitian tingkat sarjana namun krusial untuk penerapan nyata.

5. **Rancangan percobaan yang membuktikan sendiri kebutuhannya**, melalui pembandingan langsung dengan metode ambang batas pada data uji yang sama.

---

## 7. ANTISIPASI PERTANYAAN PENGUJI

**"Mengapa memilih domain DC, bukan listrik AC yang lebih umum?"**
Karena pada sistem arus searah, motor adalah satu-satunya komponen yang aus secara mekanis — seluruh komponen lain bersifat *solid-state*. Ini membuat sasaran pemantauannya jelas dan tunggal. Selain itu, sistem DC (PLTS mandiri, menara telekomunikasi, panel kendali) justru paling sering berada di lokasi tanpa jaringan internet, sehingga kebutuhan akan *edge AI* bersifat mutlak, bukan sekadar preferensi. Pemilihan domain ini juga membuat INA226 — sebuah pemantau daya DC — menjadi sensor yang tepat sasaran, bukan kompromi.

**"Mengapa tidak cukup menggunakan ambang batas arus saja?"**
Karena rentang arus antar kelas sengaja dibuat saling tumpang tindih melalui variasi *duty cycle* PWM, meniru kondisi nyata di mana tegangan baterai dan pengaturan kecepatan terus berubah. Kipas sehat pada putaran tinggi dapat menarik arus lebih besar daripada kipas terdegradasi pada putaran rendah. Informasi pembedanya terletak pada bentuk spektrum, bukan amplitudo. Metode ambang batas akan diuji sebagai pembanding dan hasilnya dilaporkan.

**"Mengapa tidak diproses di server atau awan saja?"**
Karena lokasi penerapannya justru yang paling minim konektivitas: PLTS desa, menara telekomunikasi, panel industri. Ditambah anggaran daya baterai yang ketat (modul radio yang memancar terus-menerus tidak terjangkau) dan volume data mentah 32 kbps per titik ukur. Pada proyek ini, *edge AI* adalah syarat kelayakan, bukan pilihan arsitektur.

**"Mengapa menggunakan sensor arus, bukan sensor getaran yang lebih lazim?"**
Sensor getaran harus ditempel pada badan motor, hasilnya sangat bergantung pada posisi pemasangan, dan satu sensor hanya melayani satu unit — biayanya sering melebihi harga kipas yang dipantau. Pengukuran arus bersifat non-invasif, dipasang *inline* pada jalur catu yang sudah ada, dan tidak memerlukan modifikasi pada motornya.

**"Apa gunanya kelas Tidak Dikenal?"**
Model klasifikasi tertutup akan selalu memaksakan jawaban, termasuk pada kondisi yang belum pernah diajarkan — dan jawaban itu pasti salah. Sistem pemantauan yang layak dipercaya harus mampu menyatakan ketidaktahuannya. Ini diwujudkan melalui contoh negatif yang beragam pada data latih serta ambang keyakinan pada keluaran Softmax.

**"Mengapa ESP32-S3, bukan ESP32 biasa atau Arduino?"**
ESP32-S3 memiliki ekstensi instruksi vektor 128-bit yang dirancang untuk mempercepat inferensi jaringan saraf terkuantisasi, didukung pustaka ESP-NN dan ESP-DSP dari pabrikannya. ESP32 generasi sebelumnya tidak memilikinya, dan Arduino AVR tidak memiliki daya komputasi maupun memori yang memadai untuk FFT 512 titik beserta inferensi.

**"Bagaimana memastikan akurasi yang dilaporkan bukan angka semu?"**
Melalui pembagian data berdasarkan sesi perekaman, bukan secara acak per jendela. Data uji berasal dari sesi yang terpisah sepenuhnya, direkam pada waktu dan kondisi berbeda. Ini menghilangkan kebocoran data akibat jendela yang saling tumpang tindih.

**"Mengapa memilih *shunt* 0,1 Ω?"**
Karena resolusi adalah parameter paling menentukan dalam pendekatan berbasis riak. Nilai 0,1 Ω memberi resolusi 25 µA — sepuluh kali lebih halus dibanding 0,01 Ω — sekaligus membuat resistansi parasit jalur PCB tidak berarti dan menghilangkan *drift* akibat pemanasan sendiri. Batas arus 0,819 A yang menjadi konsekuensinya justru sesuai dengan rentang arus kipas dan pompa DC yang menjadi sasaran.

**"Degradasi bantalan berlangsung berminggu-minggu. Mengapa perlu latensi di bawah satu detik?"**
Latensi ketat tidak dituntut oleh aplikasinya, melainkan ditetapkan untuk membuktikan kelayakan komputasi *edge* — bahwa diagnosis semacam ini benar-benar dapat berjalan pada mikrokontroler berbiaya rendah. Ruang komputasi yang tersisa memungkinkan satu perangkat memantau beberapa beban secara bergantian, atau menjalankan model yang lebih kompleks di masa depan.

---

## Referensi

1. SEPA Europe GmbH, *Fans, Service life, MTBF*. https://www.sepa-europe.com/en/2006/08/25/fans-service-life-mtbf/
2. NMB Technologies, *Ball vs. Sleeve: A Comparison in Bearing Performance* (white paper). https://nmbtc.com/white-papers/ball-vs-sleeve-a-comparison-in-bearing-performance/
3. Texas Instruments, *INA226 High-Side or Low-Side Measurement, Bi-Directional Current and Power Monitor with I²C Compatible Interface* — lembar data.
4. Espressif Systems, *ESP32-S3 Technical Reference Manual*; pustaka **ESP-DSP** dan **ESP-NN**.
5. Literatur *Motor Current Signature Analysis* (MCSA) sebagai landasan teknik yang diadaptasi ke ranah motor DC.
