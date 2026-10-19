/*
 * 03_klasifikasi.ino  —  Klasifikasi kondisi kipas di perangkat (edge AI)
 * --------------------------------------------------------------
 * Alur per jendela (768 sampel ≈ 253 ms pada 3030 SPS):
 *   akuisisi INA226 (ALERT) → ciri riak + FFT 1024 → MLP int8 → kelas
 * Kelas: Sehat, Aliran Terhambat, Tidak Dikenal.
 *
 * Kalibrasi (WAJIB sekali per kipas, saat kipas terpasang dan sehat):
 *   - kirim 'k' lewat Serial Monitor (115200), ATAU
 *   - tahan tombol BOOT ±2 detik.
 *   Perangkat merekam ±10 detik dan menyimpan patokan arus & riak ke flash.
 * Perintah lain: 'r' = hapus kalibrasi, 'd' = kirim satu jendela mentah +
 *   ciri (untuk verifikasi dengan tools/cek_firmware.py).
 *
 * Model & parameter: model_data.h (dibuat tools/ekspor_model.py).
 * Pengaman fisik: |I/I_patokan − 1| > 25 % → Tidak Dikenal.
 * -------------------------------------------------------------- */

#include <Wire.h>
#include <Preferences.h>
#include <math.h>
#include "soc/gpio_reg.h"
#include "model_data.h"

// ---------------- Perangkat keras (sama dengan sketch 02) ----------------
#define PIN_SDA      8
#define PIN_SCL      9
#define PIN_ALERT    7
#define PIN_BOOT     0
#define INA_ADDR     0x44
#define I2C_HZ       1000000
#define VSHCT_CODE   2           // 332 us -> ±3030 SPS
#define REG_CONFIG   0x00
#define REG_SHUNT    0x01
#define REG_MASK     0x06
#define LSB_MA       0.025f      // 2,5 uV / 0,1 ohm

// ---------------- Pengolahan sinyal ----------------
#define N_WIN        768
#define N_FFT        1024
#define N_BIN        (N_FFT / 2 + 1)
#define N_KALIB      40          // jendela kalibrasi (±10 s)
#define N_VOTE       5           // pemungutan suara jendela terakhir
#define EPSF         1e-6f

struct Ciri { float log_dc, riak_dc, kurtosis, crest, flat, lantai_rel, dc; };

static const char *KELAS[3] = {"Sehat", "Aliran Terhambat", "Tidak Dikenal"};

static float sig[N_WIN];
static float win[N_WIN];
static float re[N_FFT], im[N_FFT];
static float amp[N_BIN];
static float tmp[N_BIN];
static float tw_c[N_FFT / 2], tw_s[N_FFT / 2];
static float win_sum = 0;

Preferences prefs;
bool kalibrasi_ada = false;
float base_logdc = 0, base_riak = 0;
int votes[N_VOTE]; int vote_n = 0, vote_i = 0;

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

// Rekam satu jendela. Mengembalikan laju cuplik [Hz] atau 0 bila gagal.
// Loop dibuat seringan mungkin: waktu baca ESP32 (2 transaksi I2C) hanya
// ±3 us lebih cepat dari satu konversi 332 us, jadi konversi ke mA dan
// pencatatan waktu dilakukan setelah jendela selesai.
static int16_t rawBuf[N_WIN];
static uint16_t dtHist[1024];                      // histogram jarak antar sampel (us)
uint32_t lastMissed = 0;
float captureWindow() {
  uint32_t t_first = 0, t_prev = 0, missed = 0;
  memset(dtHist, 0, sizeof(dtHist));
  Serial.flush();                                   // jangan ada pengiriman Serial selama akuisisi
  uint16_t dummy0; readReg(REG_MASK, dummy0);       // buang konversi yang sudah lama menunggu
  for (int i = 0; i < N_WIN; i++) {
    uint32_t start = micros();
    while (REG_READ(GPIO_IN_REG) & (1UL << PIN_ALERT)) {   // ALERT aktif-LOW (baca register langsung)
      if (micros() - start > 50000) return 0;
    }
    uint32_t t = micros();
    uint16_t raw, dummy;
    if (!readReg(REG_MASK, dummy)) return 0;        // hapus flag DULU
    if (!readReg(REG_SHUNT, raw)) return 0;
    rawBuf[i] = (int16_t)raw;
    if (i == 0) t_first = t;
    else {
      uint32_t dt = t - t_prev;
      dtHist[dt < 1023 ? dt : 1023]++;
      if (dt > 498) missed++;                       // > 1,5 x 332 us
    }
    t_prev = t;
  }
  for (int i = 0; i < N_WIN; i++) sig[i] = rawBuf[i] * LSB_MA;
  lastMissed = missed;
  // Laju cuplik = 1 / median jarak antar sampel (sama dengan tools/capture_fft.py)
  uint32_t half = (N_WIN - 1) / 2, cum = 0;
  for (int d = 0; d < 1024; d++) {
    cum += dtHist[d];
    if (cum > half) return 1e6f / (float)d;
  }
  return 0;
}

// ================= FFT radix-2 (in-place) =================
void fftInit() {
  for (int i = 0; i < N_FFT / 2; i++) {
    tw_c[i] = cosf(2.0f * PI * i / N_FFT);
    tw_s[i] = -sinf(2.0f * PI * i / N_FFT);
  }
  win_sum = 0;
  for (int n = 0; n < N_WIN; n++) {                // = numpy.hanning(N_WIN)
    win[n] = 0.5f - 0.5f * cosf(2.0f * PI * n / (N_WIN - 1));
    win_sum += win[n];
  }
}

void fft() {
  for (int i = 1, j = 0; i < N_FFT; i++) {          // pembalikan bit
    int bit = N_FFT >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (int len = 2; len <= N_FFT; len <<= 1) {
    int step = N_FFT / len;
    for (int i = 0; i < N_FFT; i += len) {
      for (int k = 0; k < len / 2; k++) {
        float wr = tw_c[k * step], wi = tw_s[k * step];
        int a = i + k, b = i + k + len / 2;
        float xr = re[b] * wr - im[b] * wi;
        float xi = re[b] * wi + im[b] * wr;
        re[b] = re[a] - xr; im[b] = im[a] - xi;
        re[a] += xr;        im[a] += xi;
      }
    }
  }
}

int cmpf(const void *a, const void *b) {
  float x = *(const float *)a, y = *(const float *)b;
  return (x > y) - (x < y);
}

// ================= Ciri (harus identik dengan tools/fitur.py) =================
Ciri hitungCiri(float fs) {
  Ciri c;
  double s = 0;
  for (int n = 0; n < N_WIN; n++) s += sig[n];
  float dc = s / N_WIN;
  double m2 = 0, m4 = 0; float pk = 0;
  for (int n = 0; n < N_WIN; n++) {
    float a = sig[n] - dc;
    double a2 = (double)a * a;
    m2 += a2; m4 += a2 * a2;
    if (fabsf(a) > pk) pk = fabsf(a);
  }
  m2 /= N_WIN; m4 /= N_WIN;
  float rms = sqrtf((float)m2) + EPSF;
  c.dc = dc;
  c.log_dc = log10f(fmaxf(dc, 0.1f));
  c.riak_dc = rms / fmaxf(dc, 1.0f);
  c.kurtosis = (float)(m4 / pow(rms, 4)) - 3.0f;
  c.crest = pk / rms;

  for (int n = 0; n < N_FFT; n++) {
    re[n] = (n < N_WIN) ? (sig[n] - dc) * win[n] : 0.0f;
    im[n] = 0.0f;
  }
  fft();
  for (int k = 0; k < N_BIN; k++) amp[k] = 2.0f * sqrtf(re[k] * re[k] + im[k] * im[k]) / win_sum;

  float df = fs / N_FFT;
  double sum_log = 0, sum_p = 0; int nb = 0;
  for (int k = 0; k < N_BIN; k++) {
    float f = k * df;
    if (f > 50.0f && f < 1500.0f) {
      double p = (double)amp[k] * amp[k] + 1e-12;
      sum_log += log(p); sum_p += p; nb++;
    }
  }
  c.flat = nb ? (float)(exp(sum_log / nb) / (sum_p / nb)) : 0.0f;

  for (int k = 1; k < N_BIN; k++) tmp[k - 1] = amp[k];      // median amp[1:]
  qsort(tmp, N_BIN - 1, sizeof(float), cmpf);
  int m = N_BIN - 1;
  float med = (m % 2) ? tmp[m / 2] : 0.5f * (tmp[m / 2 - 1] + tmp[m / 2]);
  c.lantai_rel = log10f(med / rms + EPSF);
  return c;
}

// ================= MLP int8 =================
void inferensi(const float in[MODEL_N_IN], float prob[MODEL_N_OUT]) {
  int32_t q0[MODEL_N_IN], q1[MODEL_N_H1], q2[MODEL_N_H2];
  for (int i = 0; i < MODEL_N_IN; i++) {
    float x = fminf(fmaxf(in[i], CLIP_LO[i]), CLIP_HI[i]);
    float z = (x - SC_MEAN[i]) / SC_STD[i];
    q0[i] = (int32_t)fminf(fmaxf(roundf(z / S_IN0), -127.0f), 127.0f);
  }
  for (int o = 0; o < MODEL_N_H1; o++) {
    int32_t acc = MDL_B1[o];
    for (int i = 0; i < MODEL_N_IN; i++) acc += (int32_t)MDL_W1[o * MODEL_N_IN + i] * q0[i];
    q1[o] = (int32_t)fminf(fmaxf(roundf(acc * MDL_M1), 0.0f), 127.0f);
  }
  for (int o = 0; o < MODEL_N_H2; o++) {
    int32_t acc = MDL_B2[o];
    for (int i = 0; i < MODEL_N_H1; i++) acc += (int32_t)MDL_W2[o * MODEL_N_H1 + i] * q1[i];
    q2[o] = (int32_t)fminf(fmaxf(roundf(acc * MDL_M2), 0.0f), 127.0f);
  }
  float mx = -1e30f, logit[MODEL_N_OUT], s = 0;
  for (int o = 0; o < MODEL_N_OUT; o++) {
    int32_t acc = MDL_B3[o];
    for (int i = 0; i < MODEL_N_H2; i++) acc += (int32_t)MDL_W3[o * MODEL_N_H2 + i] * q2[i];
    logit[o] = acc * MDL_M3;
    if (logit[o] > mx) mx = logit[o];
  }
  for (int o = 0; o < MODEL_N_OUT; o++) { prob[o] = expf(logit[o] - mx); s += prob[o]; }
  for (int o = 0; o < MODEL_N_OUT; o++) prob[o] /= s;
}

// ================= Kalibrasi =================
void muatKalibrasi() {
  prefs.begin("kipas", true);
  kalibrasi_ada = prefs.getBool("ok", false);
  base_logdc = prefs.getFloat("logdc", 0);
  base_riak = prefs.getFloat("riak", 0);
  prefs.end();
}

void kalibrasi() {
  static float a[N_KALIB], b[N_KALIB];
  Serial.println("# KALIBRASI: pastikan kipas SEHAT terpasang. Merekam ±10 detik ...");
  int n = 0;
  while (n < N_KALIB) {
    float fs = captureWindow();
    if (fs <= 0) { Serial.println("# ERROR akuisisi saat kalibrasi"); return; }
    Ciri c = hitungCiri(fs);
    a[n] = c.log_dc; b[n] = c.riak_dc; n++;
  }
  qsort(a, N_KALIB, sizeof(float), cmpf); qsort(b, N_KALIB, sizeof(float), cmpf);
  base_logdc = 0.5f * (a[N_KALIB / 2 - 1] + a[N_KALIB / 2]);
  base_riak = 0.5f * (b[N_KALIB / 2 - 1] + b[N_KALIB / 2]);
  prefs.begin("kipas", false);
  prefs.putFloat("logdc", base_logdc); prefs.putFloat("riak", base_riak); prefs.putBool("ok", true);
  prefs.end();
  kalibrasi_ada = true; vote_n = 0;
  Serial.printf("# KALIBRASI SELESAI: arus patokan %.2f mA, riak/DC patokan %.4f\n",
                powf(10, base_logdc), base_riak);
}

void hapusKalibrasi() {
  prefs.begin("kipas", false); prefs.clear(); prefs.end();
  kalibrasi_ada = false; vote_n = 0;
  Serial.println("# Kalibrasi dihapus.");
}

// ================= Mode debug untuk verifikasi =================
void dumpJendela() {
  float fs = captureWindow();
  if (fs <= 0) { Serial.println("#ERROR akuisisi"); return; }
  Ciri c = hitungCiri(fs);
  Serial.println("#RAW_BEGIN");
  Serial.printf("#fs=%.3f\n", fs);
  Serial.printf("#missed=%lu\n", (unsigned long)lastMissed);
  for (int n = 0; n < N_WIN; n++) Serial.printf("%.4f\n", sig[n]);
  Serial.println("#RAW_END");
  Serial.printf("#CIRI log_dc=%.6f riak_dc=%.6f kurtosis=%.6f crest=%.6f flat=%.6f lantai_rel=%.6f\n",
                c.log_dc, c.riak_dc, c.kurtosis, c.crest, c.flat, c.lantai_rel);
  if (kalibrasi_ada) {
    float in[MODEL_N_IN] = {c.riak_dc, c.kurtosis, c.crest, c.flat, c.lantai_rel,
                            c.log_dc - base_logdc, c.riak_dc - base_riak};
    float pr[MODEL_N_OUT]; inferensi(in, pr);
    Serial.printf("#BASE logdc=%.6f riak=%.6f\n", base_logdc, base_riak);
    Serial.printf("#PROB %.6f %.6f %.6f\n", pr[0], pr[1], pr[2]);
  }
}

// ================= Utama =================
void setup() {
  Serial.begin(115200);
  delay(1500);
  pinMode(PIN_ALERT, INPUT_PULLUP);
  pinMode(PIN_BOOT, INPUT_PULLUP);
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  fftInit();
  startContinuous();
  muatKalibrasi();
  Serial.println("# Klasifikasi kondisi kipas — edge AI (MLP int8, 3 kelas)");
  if (kalibrasi_ada)
    Serial.printf("# Kalibrasi tersimpan: arus patokan %.2f mA\n", powf(10, base_logdc));
  else
    Serial.println("# BELUM DIKALIBRASI: pasang kipas sehat, lalu kirim 'k' atau tahan BOOT 2 detik.");
}

void loop() {
  if (Serial.available()) {
    char ch = Serial.read();
    if (ch == 'k' || ch == 'K') kalibrasi();
    else if (ch == 'r' || ch == 'R') hapusKalibrasi();
    else if (ch == 'd' || ch == 'D') dumpJendela();
  }
  if (digitalRead(PIN_BOOT) == LOW) {
    uint32_t t = millis();
    while (digitalRead(PIN_BOOT) == LOW && millis() - t < 2000) delay(10);
    if (millis() - t >= 2000) kalibrasi();
  }

  float fs = captureWindow();
  if (fs <= 0) { Serial.println("# ERROR akuisisi (cek kabel ALERT/I2C)"); startContinuous(); delay(200); return; }
  uint32_t t0 = micros();
  Ciri c = hitungCiri(fs);
  uint32_t t1 = micros();

  if (!kalibrasi_ada) {
    Serial.printf("I=%6.2f mA  | BELUM DIKALIBRASI (kirim 'k')\n", c.dc);
    return;
  }
  float in[MODEL_N_IN] = {c.riak_dc, c.kurtosis, c.crest, c.flat, c.lantai_rel,
                          c.log_dc - base_logdc, c.riak_dc - base_riak};
  float pr[MODEL_N_OUT];
  inferensi(in, pr);
  uint32_t t2 = micros();

  int kls = 0;
  for (int o = 1; o < MODEL_N_OUT; o++) if (pr[o] > pr[kls]) kls = o;
  float dI = powf(10, c.log_dc - base_logdc) - 1.0f;
  if (fabsf(dI) > MODEL_BATAS_ARUS) kls = 2;                      // pengaman fisik

  votes[vote_i] = kls; vote_i = (vote_i + 1) % N_VOTE; if (vote_n < N_VOTE) vote_n++;
  int cnt[3] = {0, 0, 0};
  for (int i = 0; i < vote_n; i++) cnt[votes[i]]++;
  int stabil = 0;
  for (int k = 1; k < 3; k++) if (cnt[k] > cnt[stabil]) stabil = k;

  Serial.printf("I=%6.2f mA  dI=%+5.1f%%  P=[%.2f %.2f %.2f]  jendela: %-16s | KONDISI: %-16s (%d/%d)  ciri %lu us, inferensi %lu us\n",
                c.dc, dI * 100, pr[0], pr[1], pr[2], KELAS[kls], KELAS[stabil], cnt[stabil], vote_n,
                (unsigned long)(t1 - t0), (unsigned long)(t2 - t1));
}
