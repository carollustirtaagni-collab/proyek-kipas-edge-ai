#!/usr/bin/env python3
"""
serial_log.py — membaca output serial ESP32 selama N detik lalu berhenti.

Pengganti Serial Monitor yang tidak berhenti sendiri, supaya output sketch
bisa dibaca secara non-interaktif (mis. dari skrip atau terminal).

Contoh:
    python tools/serial_log.py --port COM5                 # 115200 baud, 10 detik
    python tools/serial_log.py --port COM5 --seconds 20 --reset
    python tools/serial_log.py --port /dev/ttyACM0 --baud 921600 --send c
"""
import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial belum terpasang:  pip install -r tools/requirements.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--reset", action="store_true",
                    help="reset ESP32 lewat DTR/RTS supaya output setup() ikut terbaca")
    ap.add_argument("--send", help="teks yang dikirim setelah port terbuka (mis. 'c')")
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.2)
    if args.reset:
        ser.dtr = False
        ser.rts = True
        time.sleep(0.1)
        ser.rts = False
    time.sleep(0.5)
    if args.send:
        ser.write(args.send.encode())

    end = time.time() + args.seconds
    while time.time() < end:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").rstrip())
            sys.stdout.flush()
    ser.close()


if __name__ == "__main__":
    main()
