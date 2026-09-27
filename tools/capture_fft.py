#!/usr/bin/env python3
"""
capture_fft.py  —  LANGKAH 4 & 5
------------------------------------------------------------------
Merekam data dari ESP32-S3 (sketch 02_ina226_capture), menyimpan
CSV, lalu menampilkan sinyal waktu + spektrum FFT.

Instalasi (sekali saja):
    pip install pyserial numpy matplotlib

Contoh pemakaian:
    # Rekam langsung dari ESP32 (ganti port sesuai komputermu)
    python tools/capture_fft.py --port COM5 --label sehat_u01
    python tools/capture_fft.py --port /dev/ttyUSB0 --label sehat_u01

    # Analisis ulang file yang sudah tersimpan
    python tools/capture_fft.py --file data/sehat_u01_20260927-1030.csv

    # Bandingkan beberapa rekaman (uji kelayakan minggu 1)
    python tools/capture_fft.py --compare data/sehat_u01*.csv data/sehat_u02*.csv data/massa100_u01*.csv
------------------------------------------------------------------
"""
import argparse
import os
import sys
import time
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt

LSB_SHUNT_V = 2.5e-6  # 2.5 uV per LSB (INA226)


# ------------------------------------------------------------------
# Akuisisi
# ------------------------------------------------------------------
def capture_from_serial(port, baud, timeout_s=60):
    try:
        import serial
    except ImportError:
        sys.exit("pyserial belum terpasang:  pip install pyserial")

    print(f"Membuka {port} @ {baud} ...")
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2.5)                    # ESP32 bisa reset saat port dibuka
    ser.reset_input_buffer()
    ser.write(b"c")
    print("Merekam ... (jangan sentuh kipas/kabel)")

    lines, started, t_start = [], False, time.time()
    while time.time() - t_start < timeout_s:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode(errors="ignore").strip()
        if line.startswith("#ERROR"):
            ser.close()
            sys.exit("ESP32 melapor: " + line)
        if line == "#BEGIN":
            started = True
            continue
        if line == "#END":
            break
        if started:
            lines.append(line)
    ser.close()
    if not lines:
        sys.exit("Tidak menerima data. Cek port, baud (921600), dan sketch 02 sudah ter-upload.")
    return lines


def parse_lines(lines):
    meta, t, raw = {}, [], []
    for line in lines:
        if line.startswith("#"):
            if "=" in line:
                k, v = line[1:].split("=", 1)
                meta[k.strip()] = v.strip()
            continue
        if line.startswith("t_us"):
            continue
        parts = line.split(",")
        if len(parts) != 2:
            continue
        try:
            t.append(int(parts[0]))
            raw.append(int(parts[1]))
        except ValueError:
            pass
    return meta, np.array(t, dtype=np.int64), np.array(raw, dtype=np.int64)


def save_csv(path, meta, t, raw):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for k, v in meta.items():
            f.write(f"#{k}={v}\n")
        f.write("t_us,raw\n")
        for a, b in zip(t, raw):
            f.write(f"{a},{b}\n")


def load_csv(path):
    with open(path) as f:
        return parse_lines([ln.strip() for ln in f])


# ------------------------------------------------------------------
# Analisis
# ------------------------------------------------------------------
def analyze(t_us, raw, r_shunt):
    i_mA = raw * LSB_SHUNT_V / r_shunt * 1e3
    dt = np.diff(t_us).astype(float)
    dt_med = np.median(dt)
    fs = 1e6 / dt_med                          # pewaktuan dari jam INA226
    gaps = int(np.sum(dt > 1.5 * dt_med))

    dc = float(np.mean(i_mA))
    ac = i_mA - dc
    n = len(ac)
    win = np.hanning(n)
    spec = np.fft.rfft(ac * win)
    amp = 2.0 * np.abs(spec) / np.sum(win)     # amplitudo puncak (mA) per bin
    freqs = np.fft.rfftfreq(n, 1.0 / fs)

    floor = float(np.median(amp[1:]))          # estimasi lantai derau
    peaks = find_peaks(freqs, amp, floor)
    snr_db = 20 * np.log10(peaks[0][1] / floor) if peaks else float("nan")

    return dict(
        i_mA=i_mA, fs=fs, gaps=gaps, dc=dc,
        ripple_rms=float(np.std(ac)), ripple_pp=float(np.ptp(ac)),
        freqs=freqs, amp=amp, floor=floor, peaks=peaks, snr_db=snr_db,
        df=fs / n,
    )


def find_peaks(freqs, amp, floor, k=6.0, max_peaks=10, fmin=10.0):
    """Puncak lokal yang > k x lantai derau, dipisah minimal ~10 Hz."""
    cand = []
    for j in range(2, len(amp) - 2):
        if freqs[j] < fmin:
            continue
        if amp[j] > k * floor and amp[j] == amp[j - 2:j + 3].max():
            cand.append((freqs[j], amp[j]))
    cand.sort(key=lambda p: -p[1])
    chosen = []
    for f, a in cand:
        if all(abs(f - g) > 10 for g, _ in chosen):
            chosen.append((f, a))
        if len(chosen) >= max_peaks:
            break
    return chosen


def print_report(name, meta, r):
    print("\n" + "=" * 60)
    print(f" {name}")
    print("=" * 60)
    print(f" Jumlah sampel          : {len(r['i_mA'])}")
    print(f" Laju cuplik efektif    : {r['fs']:.1f} SPS  (Nyquist {r['fs']/2:.0f} Hz)")
    print(f" Resolusi frekuensi     : {r['df']:.2f} Hz")
    # Pakai hitungan ESP32 (dibanding VSHCT nominal); celah vs median saja
    # buta bila SETIAP sampel terlewat secara teratur.
    missed = int(meta.get("missed", r["gaps"]))
    print(f" Konversi terlewat      : {missed}"
          + ("   <-- PERLU DIPERBAIKI" if missed else "   OK"))
    if "vshct_us" in meta:
        print(f" Laju nominal (VSHCT)   : {1e6/float(meta['vshct_us']):.1f} SPS")
    if "vbus_V" in meta:
        print(f" Tegangan catu (bus)    : {float(meta['vbus_V']):.3f} V")
    print(f" Arus rata-rata (DC)    : {r['dc']:.2f} mA")
    print(f" Riak RMS               : {r['ripple_rms']:.3f} mA"
          f"  ({100*r['ripple_rms']/max(r['dc'],1e-9):.1f}% dari DC)")
    print(f" Riak puncak-puncak     : {r['ripple_pp']:.3f} mA")
    print(f" Lantai derau spektrum  : {r['floor']*1000:.2f} uA")
    print(f" SNR puncak tertinggi   : {r['snr_db']:.1f} dB")
    print(" Puncak spektrum (terbesar dulu):")
    for f, a in r["peaks"]:
        print(f"    {f:8.1f} Hz   {a:8.4f} mA   ({20*np.log10(a/r['floor']):5.1f} dB di atas lantai)")
    if r["peaks"] and r["peaks"][0][0] > 0.45 * r["fs"]:
        print(" !! Puncak terbesar dekat Nyquist - kemungkinan aliasing. Naikkan laju cuplik.")


def plot_single(name, r, png_path=None):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8))
    n_show = min(len(r["i_mA"]), int(r["fs"] * 0.05))      # 50 ms pertama
    tt = np.arange(n_show) / r["fs"] * 1e3
    ax1.plot(tt, r["i_mA"][:n_show], lw=1)
    ax1.set_xlabel("Waktu (ms)")
    ax1.set_ylabel("Arus (mA)")
    ax1.set_title(f"{name}  —  50 ms pertama  |  DC {r['dc']:.1f} mA, riak RMS {r['ripple_rms']:.2f} mA")
    ax1.grid(alpha=0.3)

    ax2.semilogy(r["freqs"], r["amp"], lw=0.8)
    ax2.axhline(r["floor"], color="gray", ls="--", lw=0.8, label="lantai derau")
    for f, a in r["peaks"][:6]:
        ax2.annotate(f"{f:.0f} Hz", (f, a), textcoords="offset points",
                     xytext=(0, 6), ha="center", fontsize=8)
    ax2.set_xlim(0, r["fs"] / 2)
    ax2.set_xlabel("Frekuensi (Hz)")
    ax2.set_ylabel("Amplitudo (mA)")
    ax2.set_title(f"Spektrum  |  fs {r['fs']:.0f} SPS, Δf {r['df']:.2f} Hz, SNR {r['snr_db']:.1f} dB")
    ax2.grid(alpha=0.3, which="both")
    ax2.legend(loc="upper right")
    fig.tight_layout()
    if png_path:
        fig.savefig(png_path, dpi=130)
        print(f"\nGambar disimpan: {png_path}")
    plt.show()


def plot_compare(results, png_path=None):
    fig, ax = plt.subplots(figsize=(11, 6))
    for name, r in results:
        ax.semilogy(r["freqs"], r["amp"], lw=0.8, alpha=0.8, label=f"{name} ({r['dc']:.0f} mA)")
    ax.set_xlim(0, min(r["fs"] for _, r in results) / 2)
    ax.set_xlabel("Frekuensi (Hz)")
    ax.set_ylabel("Amplitudo (mA)")
    ax.set_title("Perbandingan spektrum")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    if png_path:
        fig.savefig(png_path, dpi=130)
        print(f"\nGambar disimpan: {png_path}")
    plt.show()


# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Rekam & analisis arus INA226")
    ap.add_argument("--port", help="port serial ESP32, mis. COM5 atau /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--label", default="rekaman", help="nama rekaman, mis. sehat_u01_pwm100")
    ap.add_argument("--file", help="analisis CSV yang sudah tersimpan")
    ap.add_argument("--compare", nargs="+", help="bandingkan beberapa CSV")
    ap.add_argument("--rshunt", type=float, default=0.1)
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--noshow", action="store_true", help="jangan buka jendela plot")
    args = ap.parse_args()

    if args.noshow:
        plt.show = lambda *a, **k: None

    if args.compare:
        results = []
        for path in args.compare:
            meta, t, raw = load_csv(path)
            r = analyze(t, raw, args.rshunt)
            name = os.path.splitext(os.path.basename(path))[0]
            print_report(name, meta, r)
            results.append((name, r))
        os.makedirs(args.outdir, exist_ok=True)
        plot_compare(results, os.path.join(args.outdir, "perbandingan.png"))
        return

    if args.file:
        meta, t, raw = load_csv(args.file)
        name = os.path.splitext(os.path.basename(args.file))[0]
        png = os.path.splitext(args.file)[0] + ".png"
    elif args.port:
        lines = capture_from_serial(args.port, args.baud)
        meta, t, raw = parse_lines(lines)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{args.label}_{stamp}"
        csv_path = os.path.join(args.outdir, name + ".csv")
        save_csv(csv_path, meta, t, raw)
        print(f"Data disimpan: {csv_path}")
        png = os.path.join(args.outdir, name + ".png")
    else:
        ap.error("pakai --port (rekam), --file (analisis), atau --compare")

    if len(t) < 64:
        sys.exit("Data terlalu sedikit untuk dianalisis.")
    r = analyze(t, raw, args.rshunt)
    print_report(name, meta, r)
    plot_single(name, r, png)


if __name__ == "__main__":
    main()
