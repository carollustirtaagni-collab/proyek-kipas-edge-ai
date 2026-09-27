/*
 * 02_ina226_capture.ino  â€”  LANGKAH 4
 * --------------------------------------------------------------
 * Merekam N sampel arus secepat mungkin ke RAM (burst), BARU
 * kemudian mengirimnya ke PC. Dengan begitu kecepatan Serial
 * tidak mengganggu pencuplikan.
 *
 * Pewaktuan sampel ditentukan oleh jam internal INA226:
 * setiap konversi selesai, pin ALERT turun (Conversion Ready),
 * ESP32 membaca hasilnya lalu menghapus flag. Jadi jarak antar
 * sampel teratur, tidak bergantung pada kecepatan loop ESP32.
 *
 * Cara pakai:
 *   - Jalankan capture_fft.py di PC  (otomatis mengirim 'c'), ATAU
 *   - Buka Serial Monitor 921600 baud, ketik  c  lalu Enter.
 *
 * Output di akhir perekaman memberi tahu apakah ada konversi
 * yang TERLEWAT. Kalau ada, ESP32 tidak sempat membaca -> lihat
 * tabel di bawah untuk menurunkan laju atau menaikkan I2C.
 * -------------------------------------------------------------- */

#include <Wire.h>

// ---------------- Sesuaikan ----------------
#define PIN_SDA        8
#define PIN_SCL        9
#define PIN_ALERT      7        // pin ALERT/ALE modul INA226
#define USE_ALERT_PIN  1        // 0 = modul tanpa pin ALERT (pakai polling register)
#define INA_ADDR       0x44     // hasil scan modulmu
#define SERIAL_BAUD    921600

// Kecepatan I2C:
//   400000  = batas RESMI INA226 (mulai dari sini)
//   1000000 = di luar spesifikasi resmi, sering tetap jalan -> uji coba
// Terukur 2026-09-28 (VSHCT 332 us): 400 kHz -> 454 us/sampel (ESP32 tidak
// sempat); 1 MHz -> 3030 SPS, 0 terlewat, 0 error. Jadi pakai 1 MHz.
#define I2C_HZ         1000000

// Waktu konversi shunt (VSHCT)  ->  laju cuplik
//   0 = 140 us -> 7.14 kSPS   (butuh I2C sangat cepat)
//   1 = 204 us -> 4.90 kSPS
//   2 = 332 us -> 3.01 kSPS   (target minggu 1)
//   3 = 588 us -> 1.70 kSPS   (paling aman untuk 400 kHz)
#define VSHCT_CODE     2

#define N_SAMPLES      8192     // 8192 x 332 us = 2.7 detik rekaman
// -------------------------------------------

#define REG_CONFIG  0x00
#define REG_SHUNT   0x01
#define REG_MASK    0x06

static const uint16_t VSHCT_US[] = {140, 204, 332, 588, 1100, 2116, 4156, 8244};

static int16_t  sampleBuf[N_SAMPLES];
static uint32_t timeBuf[N_SAMPLES];

bool readReg(uint8_t reg, uint16_t &out) {
  Wire.beginTransmission(INA_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return false;     // STOP penuh, kompatibel semua core
  if (Wire.requestFrom((uint8_t)INA_ADDR, (uint8_t)2) != 2) return false;
  uint8_t hi = Wire.read();
  uint8_t lo = Wire.read();
  out = ((uint16_t)hi << 8) | lo;
  return true;
}

bool writeReg(uint8_t reg, uint16_t val) {
  Wire.beginTransmission(INA_ADDR);
  Wire.write(reg);
  Wire.write((uint8_t)(val >> 8));
  Wire.write((uint8_t)(val & 0xFF));
  return Wire.endTransmission() == 0;
}

// Konfigurasi capture:
//   AVG = 000 (MATIKAN averaging - averaging menghapus riak!)
//   VBUSCT = 000 (tidak dipakai), VSHCT = VSHCT_CODE
//   MODE = 101 (shunt voltage, continuous)
uint16_t captureConfig() {
  return 0x4000 | ((uint16_t)(VSHCT_CODE & 0x7) << 3) | 0x0005;
}

// Tunggu satu konversi baru, simpan hasilnya.
// return: 0 = ok, 1 = timeout, 2 = error I2C
int waitAndRead(int16_t &val, uint32_t &t) {
  uint32_t start = micros();
#if USE_ALERT_PIN
  while (digitalRead(PIN_ALERT) == HIGH) {          // ALERT aktif-LOW
    if (micros() - start > 50000) return 1;
  }
  t = micros();
  uint16_t raw, dummy;
  // Hapus flag DULU, baru baca shunt. Kalau urutannya dibalik, 2 transaksi I2C
  // bisa lebih lama dari 1 konversi -> flag konversi berikutnya ikut terhapus
  // -> setiap konversi kedua terlewat (terukur: 597 us/sampel, bukan 332).
  // Register shunt tetap memegang hasil ini sampai konversi berikutnya selesai.
  if (!readReg(REG_MASK, dummy)) return 2;          // baca 0x06 = hapus flag
  if (!readReg(REG_SHUNT, raw)) return 2;
#else
  uint16_t mask;
  while (true) {                                     // polling bit CVRF (bit 3)
    if (!readReg(REG_MASK, mask)) return 2;
    if (mask & 0x0008) break;
    if (micros() - start > 50000) return 1;
  }
  t = micros();
  uint16_t raw;
  if (!readReg(REG_SHUNT, raw)) return 2;
#endif
  val = (int16_t)raw;
  return 0;
}

void capture() {
  // Tulis konfigurasi -> konversi dimulai ulang, flag terhapus
  writeReg(REG_CONFIG, captureConfig());
#if USE_ALERT_PIN
  writeReg(REG_MASK, 0x0400);                        // CNVR: ALERT = Conversion Ready
#else
  writeReg(REG_MASK, 0x0000);
#endif
  uint16_t dummy;
  readReg(REG_MASK, dummy);                          // pastikan flag bersih

  int16_t v; uint32_t t;
  int err = waitAndRead(v, t);                       // buang sampel pertama
  if (err) {
    Serial.printf("#ERROR %s pada sampel pertama. Cek kabel ALERT / set USE_ALERT_PIN 0\n",
                  err == 1 ? "timeout" : "I2C");
    return;
  }

  uint32_t errCount = 0;
  for (int i = 0; i < N_SAMPLES; i++) {
    err = waitAndRead(sampleBuf[i], timeBuf[i]);
    if (err) {
      errCount++;
      sampleBuf[i] = (i > 0) ? sampleBuf[i - 1] : 0;
      timeBuf[i]   = micros();
    }
  }

  // ---- Ringkasan cepat di ESP32 ----
  uint32_t t0 = timeBuf[0];
  uint32_t dur = timeBuf[N_SAMPLES - 1] - t0;
  float nominal = VSHCT_US[VSHCT_CODE];
  uint32_t missed = 0;
  double sum = 0;
  for (int i = 0; i < N_SAMPLES; i++) {
    sum += sampleBuf[i];
    if (i > 0 && (timeBuf[i] - timeBuf[i - 1]) > 1.5f * nominal) missed++;
  }
  float meanRaw = sum / N_SAMPLES;

  // ---- Kirim ke PC ----
  Serial.println("#BEGIN");
  Serial.printf("#vshct_us=%u\n", (unsigned)VSHCT_US[VSHCT_CODE]);
  Serial.printf("#i2c_hz=%u\n", (unsigned)I2C_HZ);
  Serial.printf("#n=%u\n", (unsigned)N_SAMPLES);
  Serial.printf("#dur_us=%u\n", (unsigned)dur);
  Serial.printf("#errors=%u\n", (unsigned)errCount);
  Serial.printf("#missed=%u\n", (unsigned)missed);
  Serial.printf("#mean_mA=%.3f\n", meanRaw * 0.025f);   // 2.5 uV / 0.1 ohm = 25 uA per LSB
  Serial.println("t_us,raw");
  for (int i = 0; i < N_SAMPLES; i++) {
    Serial.printf("%u,%d\n", (unsigned)(timeBuf[i] - t0), (int)sampleBuf[i]);
  }
  Serial.println("#END");

  // Ringkasan untuk dibaca manusia
  Serial.printf("# Laju efektif : %.0f SPS (nominal %.0f SPS)\n",
                (N_SAMPLES - 1) * 1e6f / dur, 1e6f / nominal);
  Serial.printf("# Arus rata2   : %.2f mA\n", meanRaw * 0.025f);
  Serial.printf("# Konversi terlewat: %u   Error I2C: %u\n", (unsigned)missed, (unsigned)errCount);
  if (missed > 0) {
    Serial.println("# -> ESP32 tidak sempat membaca setiap konversi.");
    Serial.println("#    Coba: I2C_HZ 1000000, atau VSHCT_CODE lebih besar (lebih lambat).");
  } else {
    Serial.println("# -> Tidak ada yang terlewat. Boleh coba VSHCT_CODE lebih kecil (lebih cepat).");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(2000);
  pinMode(PIN_ALERT, INPUT_PULLUP);                  // ALERT = open-drain
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  Serial.println("# Siap. Kirim 'c' untuk merekam.");
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'c' || c == 'C') capture();
  }
}
