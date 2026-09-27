/*
 * 01_ina226_cek.ino  —  LANGKAH 2 & 3
 * --------------------------------------------------------------
 * Tujuan: memastikan ESP32-S3 dan INA226 bisa "bicara", lalu
 *         membaca arus kipas secara pelan untuk dibandingkan
 *         dengan multimeter.
 *
 * Yang harus terlihat di Serial Monitor (115200 baud):
 *   1. Scan I2C menemukan alamat 0x44
 *   2. Manufacturer ID = 0x5449  dan  Die ID = 0x2260
 *   3. Tanpa kipas: arus ~0 mA
 *      Dengan kipas 12 V: arus ~100-200 mA (cocokkan dengan multimeter)
 *
 * Catatan: di sketch INI averaging sengaja dinyalakan (AVG=16)
 * karena tujuannya pembacaan pelan & stabil. Di sketch capture
 * (02) averaging WAJIB dimatikan.
 * -------------------------------------------------------------- */

#include <Wire.h>

// ---------- Sesuaikan dengan rangkaianmu ----------
#define PIN_SDA   8        // ESP32-S3 DevKitC-1: SDA default = GPIO8
#define PIN_SCL   9        //                      SCL default = GPIO9
#define INA_ADDR  0x44     // modul ini: alamat 0x44 (hasil scan)
#define R_SHUNT   0.1f     // ohm, resistor "R100" di modul
// --------------------------------------------------

// Register INA226
#define REG_CONFIG   0x00
#define REG_SHUNT    0x01
#define REG_BUS      0x02
#define REG_MFG_ID   0xFE
#define REG_DIE_ID   0xFF

int lastErr = 0;   // kode error terakhir, untuk diagnosis

bool readReg(uint8_t reg, uint16_t &out) {
  Wire.beginTransmission(INA_ADDR);
  Wire.write(reg);
  // STOP penuh (bukan repeated start). INA226 mengingat register pointer,
  // jadi aman, dan cara ini kompatibel dengan semua versi core ESP32.
  uint8_t e = Wire.endTransmission();
  if (e != 0) { lastErr = e; return false; }
  uint8_t n = Wire.requestFrom((uint8_t)INA_ADDR, (uint8_t)2);
  if (n != 2) { lastErr = 100 + n; return false; }
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

void scanI2C() {
  Serial.println("\n=== Scan I2C ===");
  int found = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  Perangkat ditemukan di 0x%02X\n", a);
      found++;
    }
  }
  if (found == 0) {
    Serial.println("  TIDAK ADA perangkat. Cek: VCC ke 3V3, GND, SDA/SCL tertukar?");
  }
}

void setup() {
  Serial.begin(115200);
  delay(2000);                           // beri waktu Serial Monitor terbuka
  Wire.begin(PIN_SDA, PIN_SCL, 400000);  // 400 kHz = batas resmi INA226

  scanI2C();

  uint16_t mfg = 0, die = 0;
  bool ok1 = readReg(REG_MFG_ID, mfg);
  bool ok2 = readReg(REG_DIE_ID, die);
  Serial.println("\n=== Identitas chip ===");
  Serial.printf("  Manufacturer ID = 0x%04X  (harus 0x5449) %s\n",
                mfg, (ok1 && mfg == 0x5449) ? "OK" : "<-- SALAH");
  Serial.printf("  Die ID          = 0x%04X  (harus 0x2260) %s\n",
                die, (ok2 && die == 0x2260) ? "OK" : "<-- SALAH");
  if (!ok1 || !ok2) {
    Serial.printf("  Pembacaan register gagal, kode error = %d\n", lastErr);
  }

  // Konfigurasi pelan & stabil:
  // AVG=16 (010), VBUSCT=1.1ms (100), VSHCT=1.1ms (100), MODE=shunt+bus kontinu (111)
  // 0100 010 100 100 111 = 0x4527
  if (!writeReg(REG_CONFIG, 0x4527)) {
    Serial.println("  Gagal menulis register konfigurasi!");
  }
  Serial.println("\n  bus [V] | shunt [mV] | arus [mA]");
}

void loop() {
  uint16_t rawShunt, rawBus;
  if (readReg(REG_SHUNT, rawShunt) && readReg(REG_BUS, rawBus)) {
    float shunt_mV = (int16_t)rawShunt * 0.0025f;       // LSB 2.5 uV
    float bus_V    = rawBus * 0.00125f;                  // LSB 1.25 mV
    float arus_mA  = shunt_mV / R_SHUNT;                 // I = V / R
    Serial.printf("  %6.3f  |  %8.4f  |  %8.3f\n", bus_V, shunt_mV, arus_mA);
  } else {
    Serial.printf("  Gagal membaca INA226 (kode %d)\n", lastErr);
  }
  delay(250);
}
