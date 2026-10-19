#!/usr/bin/env python3
"""
pantau.py  —  Memantau keluaran firmware 03_klasifikasi dan (opsional) mengirim perintah
------------------------------------------------------------------
    python tools/pantau.py --port COM14 --detik 15              # baca saja
    python tools/pantau.py --port COM14 --kirim k --detik 25    # kalibrasi lalu pantau
Ringkasan di akhir: jumlah jendela per kelas, arus rata-rata, latensi ciri & inferensi.
------------------------------------------------------------------
"""
import argparse
import re
import time
from collections import Counter

import serial

RX = re.compile(r"I=\s*([-\d.]+) mA\s+dI=\s*([-+\d.]+)%.*jendela: (.+?)\s*\| KONDISI: (.+?)\s*\(\d+/\d+\)\s+ciri (\d+) us, inferensi (\d+) us")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--kirim", default="")
    ap.add_argument("--detik", type=float, default=15)
    ap.add_argument("--tampil", type=int, default=6, help="jumlah baris hasil terakhir yang ditampilkan")
    args = ap.parse_args()

    ser = serial.Serial(args.port, 115200, timeout=0.5)   # tanpa reset: port dibuka tanpa toggling
    time.sleep(0.3)
    ser.reset_input_buffer()
    if args.kirim:
        ser.write(args.kirim.encode())
    t0 = time.time(); lines = []
    while time.time() - t0 < args.detik:
        ln = ser.readline().decode(errors="ignore").rstrip()
        if ln:
            lines.append(ln)
            if ln.startswith("#"):
                print(ln)
    ser.close()

    hasil = [m for m in (RX.search(l) for l in lines) if m]
    for l in [l for l in lines if RX.search(l)][-args.tampil:]:
        print(l)
    if hasil:
        win = Counter(m.group(3) for m in hasil)
        cur = [float(m.group(1)) for m in hasil]
        tc = [int(m.group(5)) for m in hasil]; ti = [int(m.group(6)) for m in hasil]
        print(f"\nRingkasan {len(hasil)} jendela: " + ", ".join(f"{k} {v}" for k, v in win.most_common()))
        print(f"Arus rata-rata {sum(cur)/len(cur):.2f} mA | ciri rata-rata {sum(tc)/len(tc):.0f} us, "
              f"maks {max(tc)} us | inferensi rata-rata {sum(ti)/len(ti):.0f} us, maks {max(ti)} us")


if __name__ == "__main__":
    main()
