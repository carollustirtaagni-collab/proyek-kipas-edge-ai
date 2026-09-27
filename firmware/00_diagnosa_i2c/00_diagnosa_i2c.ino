// 00_diagnosa_i2c.ino — mencari tahu kenapa register INA226 gagal dibaca
#include <Wire.h>
#define PIN_SDA 8
#define PIN_SCL 9

void tryRead(uint8_t addr, uint8_t reg) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  uint8_t e = Wire.endTransmission();
  Serial.printf("    tulis pointer 0x%02X -> kode %u\n", reg, e);
  uint8_t n = Wire.requestFrom(addr, (uint8_t)2);
  if (n == 2) {
    uint8_t hi = Wire.read(), lo = Wire.read();
    Serial.printf("    baca 2 byte      -> 0x%02X%02X\n", hi, lo);
  } else {
    Serial.printf("    baca             -> hanya dapat %u byte\n", n);
  }
}

void runAt(uint32_t hz) {
  Wire.end();
  Wire.begin(PIN_SDA, PIN_SCL, hz);
  Serial.printf("\n=== I2C %lu Hz ===\n", (unsigned long)hz);
  bool any = false;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      any = true;
      Serial.printf("  alamat 0x%02X ditemukan\n", a);
      tryRead(a, 0xFE);   // harus 0x5449
      tryRead(a, 0xFF);   // harus 0x2260
    }
  }
  if (!any) Serial.println("  tidak ada perangkat");
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  runAt(100000);
  runAt(400000);
  Serial.println("\nSelesai. Salin semua teks di atas.");
}

void loop() {}
