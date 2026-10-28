/*
 * 04_edgeimpulse.ino  —  Klasifikasi kondisi kipas dengan model Edge Impulse
 * --------------------------------------------------------------
 * Lingkup: kipas tipe B (U07/U10, arus Sehat ±63–64 mA), tanpa kalibrasi.
 * Alur per jendela (766 sampel ≈ 253 ms pada 3030 SPS):
 *   akuisisi INA226 (ALERT, sama dengan sketch 02/03) → run_classifier()
 *   (Spectral Analysis FFT 256 + Flatten + NN int8, EON Compiler) → kelas
 * Kelas: sehat, terhambat, tidak_dikenal. Jendela dengan keyakinan < 0,6
 * dianggap "tidak pasti" (sama dengan ambang Model testing) dan tidak ikut
 * pemungutan suara 5 jendela.
 *
 * Pustaka: ei-rolsoles-project-1-arduino-1.0.1.zip (folder ini), dipasang
 * lewat Arduino IDE (Sketch → Include Library → Add .ZIP Library) atau
 * arduino-cli compile --library <folder hasil ekstrak>.
 *
 * Antarmuka: OLED SSD1306 (SDA GPIO4, SCL GPIO5) + tombol MULAI (GPIO2).
 * Tanpa OLED, pembacaan langsung berjalan; perintah Serial 'm' = mulai/berhenti.
 * -------------------------------------------------------------- */

#include <Rolsoles-project-1_inferencing.h>
#include <Wire.h>
#include "soc/gpio_reg.h"
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---------------- Perangkat keras (sama dengan sketch 02/03) ----------------
#define PIN_SDA      8
#define PIN_SCL      9
#define PIN_ALERT    7
#define PIN_BTN_MUL  2           // tombol MULAI/BERHENTI ke GND
#define PIN_OLED_SDA 4
#define PIN_OLED_SCL 5
#define INA_ADDR     0x44
#define I2C_HZ       1000000
#define VSHCT_CODE   2           // 332 us -> ±3030 SPS
#define REG_CONFIG   0x00
#define REG_SHUNT    0x01
#define REG_MASK     0x06
#define LSB_MA       0.025f      // 2,5 uV / 0,1 ohm

#define N_WIN        EI_CLASSIFIER_RAW_SAMPLE_COUNT
#define N_VOTE       5
#define MIN_YAKIN    0.6f

static float sig[N_WIN];
int votes[N_VOTE]; int vote_n = 0, vote_i = 0;
bool membaca = true;

// ---------------- OLED & tombol ----------------
TwoWire WireOled = TwoWire(1);
Adafruit_SSD1306 oled(128, 64, &WireOled, -1);
bool oled_ok = false;
volatile bool req_mul = false;
volatile uint32_t t_mul = 0;

void IRAM_ATTR isrMul() { uint32_t t = millis(); if (t - t_mul > 300) { req_mul = true; t_mul = t; } }

void layarTeks(const char *baris1, const char *besar1, const char *besar2, const char *baris4) {
  if (!oled_ok) return;
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1); oled.setCursor(0, 0); oled.print(baris1);
  oled.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  oled.setTextSize(2);
  oled.setCursor(0, 15); oled.print(besar1);
  if (besar2 && besar2[0]) { oled.setCursor(0, 33); oled.print(besar2); }
  oled.setTextSize(1); oled.setCursor(0, 55); oled.print(baris4);
  oled.display();
}

void layarSiap() { layarTeks("Pemantau Kipas DC", "SIAP", "tekan MULAI", "Model Edge Impulse"); }

void layarHasil(int stabil, float dc, float yakin) {
  static const char *A[3] = {"SEHAT", "ALIRAN", "TIDAK"};
  static const char *B[3] = {"", "TERHAMBAT", "DIKENAL"};
  char b4[32];
  if (stabil < 0) { layarTeks("Kondisi kipas:     *", "TIDAK", "PASTI", ""); return; }
  snprintf(b4, sizeof(b4), "%.1f mA  yakin %d%%", dc, (int)(yakin * 100 + 0.5f));
  layarTeks("Kondisi kipas:     *", A[stabil], B[stabil], b4);
}

// ================= INA226 =================
bool readReg(uint8_t reg, uint16_t &out) {
  Wire.beginTransmission(INA_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom((uint8_t)INA_ADDR, (uint8_t)2) != 2) return false;
  uint8_t hi = Wire.read(), lo = Wire.read();
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

void startContinuous() {
  writeReg(REG_CONFIG, 0x4000 | ((uint16_t)(VSHCT_CODE & 0x7) << 3) | 0x0005);  // AVG=1, shunt kontinu
  writeReg(REG_MASK, 0x0400);                                                     // CNVR → ALERT
  uint16_t dummy; readReg(REG_MASK, dummy);
}

// Rekam satu jendela (sama dengan sketch 03). Mengembalikan laju cuplik [Hz]
// (1 / median jarak antar sampel) atau 0 bila gagal.
static int16_t rawBuf[N_WIN];
static uint16_t dtHist[1024];
float captureWindow() {
  uint32_t t_prev = 0;
  memset(dtHist, 0, sizeof(dtHist));
  Serial.flush();
  uint16_t dummy0; readReg(REG_MASK, dummy0);       // buang konversi yang sudah lama menunggu
  for (int i = 0; i < N_WIN; i++) {
    uint32_t start = micros();
    while (REG_READ(GPIO_IN_REG) & (1UL << PIN_ALERT)) {   // ALERT aktif-LOW
      if (micros() - start > 50000) return 0;
    }
    uint32_t t = micros();
    uint16_t raw, dummy;
    if (!readReg(REG_MASK, dummy)) return 0;        // hapus flag DULU
    if (!readReg(REG_SHUNT, raw)) return 0;
    rawBuf[i] = (int16_t)raw;
    if (i > 0) { uint32_t dt = t - t_prev; dtHist[dt < 1023 ? dt : 1023]++; }
    t_prev = t;
  }
  for (int i = 0; i < N_WIN; i++) sig[i] = rawBuf[i] * LSB_MA;
  uint32_t half = (N_WIN - 1) / 2, cum = 0;
  for (int d = 0; d < 1024; d++) {
    cum += dtHist[d];
    if (cum > half) return 1e6f / (float)d;
  }
  return 0;
}

int ambilData(size_t offset, size_t length, float *out) {
  memcpy(out, sig + offset, length * sizeof(float));
  return 0;
}

// ================= Utama =================
void setup() {
  Serial.begin(115200);
  delay(1500);
  pinMode(PIN_ALERT, INPUT_PULLUP);
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  startContinuous();

  pinMode(PIN_BTN_MUL, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BTN_MUL), isrMul, FALLING);
  WireOled.begin(PIN_OLED_SDA, PIN_OLED_SCL, 400000);
  uint8_t oled_addr = 0;                    // pustaka SSD1306 tidak memeriksa ACK
  for (uint8_t a : {0x3C, 0x3D}) {
    WireOled.beginTransmission(a);
    if (WireOled.endTransmission() == 0) { oled_addr = a; break; }
  }
  oled_ok = oled_addr && oled.begin(SSD1306_SWITCHCAPVCC, oled_addr);
  membaca = !oled_ok;
  layarSiap();

  Serial.println("# Klasifikasi kondisi kipas — model Edge Impulse (int8, EON)");
  Serial.printf("# Jendela %d sampel @ %.1f Hz, kelas: %s / %s / %s\n", N_WIN, (float)EI_CLASSIFIER_FREQUENCY,
                ei_classifier_inferencing_categories[0], ei_classifier_inferencing_categories[1],
                ei_classifier_inferencing_categories[2]);
  Serial.printf("# OLED: %s. Pembacaan %s.\n", oled_ok ? "terdeteksi" : "tidak ada",
                membaca ? "langsung berjalan" : "menunggu tombol MULAI / perintah 'm'");
}

void loop() {
  if (Serial.available()) {
    char ch = Serial.read();
    if (ch == 'm' || ch == 'M') req_mul = true;
  }
  if (req_mul) {
    req_mul = false;
    membaca = !membaca; vote_n = 0;
    Serial.printf("# Pembacaan %s\n", membaca ? "DIMULAI" : "DIHENTIKAN");
    if (!membaca) layarSiap();
  }
  if (!membaca) { delay(20); return; }

  float fs = captureWindow();
  if (fs <= 0) { Serial.println("# ERROR akuisisi (cek kabel ALERT/I2C)"); startContinuous(); delay(200); return; }
  double s = 0;
  for (int n = 0; n < N_WIN; n++) s += sig[n];
  float dc = s / N_WIN;

  signal_t signal;
  signal.total_length = N_WIN;
  signal.get_data = &ambilData;
  ei_impulse_result_t result = {0};
  uint32_t t0 = micros();
  EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);
  uint32_t t1 = micros();
  if (err != EI_IMPULSE_OK) { Serial.printf("# ERROR run_classifier: %d\n", err); return; }

  int kls = 0;
  for (int o = 1; o < EI_CLASSIFIER_LABEL_COUNT; o++)
    if (result.classification[o].value > result.classification[kls].value) kls = o;
  float yakin = result.classification[kls].value;
  if (yakin >= MIN_YAKIN) { votes[vote_i] = kls; vote_i = (vote_i + 1) % N_VOTE; if (vote_n < N_VOTE) vote_n++; }

  int cnt[3] = {0, 0, 0};
  for (int i = 0; i < vote_n; i++) cnt[votes[i]]++;
  int stabil = -1;
  if (vote_n) { stabil = 0; for (int k = 1; k < 3; k++) if (cnt[k] > cnt[stabil]) stabil = k; }

  Serial.printf("I=%6.2f mA  fs=%.1f  P=[%.2f %.2f %.2f]  jendela: %-13s | KONDISI: %-13s (%d/%d)  dsp %d ms, nn %d ms, total %lu us\n",
                dc, fs, result.classification[0].value, result.classification[1].value, result.classification[2].value,
                yakin >= MIN_YAKIN ? result.classification[kls].label : "tidak_pasti",
                stabil < 0 ? "tidak_pasti" : result.classification[stabil].label,
                stabil < 0 ? 0 : cnt[stabil], vote_n, result.timing.dsp, result.timing.classification,
                (unsigned long)(t1 - t0));
  layarHasil(stabil, dc, yakin);
}
