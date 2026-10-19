#!/usr/bin/env python3
"""
cek_massa.py  —  Gerbang kelayakan langkah 2: efek massa pada orde putaran
------------------------------------------------------------------
Membandingkan amplitudo di orde ¼ f1 (kandidat 1× putaran) dan beberapa
orde lain antara kondisi Sehat dan kondisi bermassa pada satu unit, lalu
menghitung Cohen's d terhadap sebaran dalam-unit dan (bila diberikan)
sebaran antar-unit kondisi Sehat.

Contoh:
    python tools/cek_massa.py --unit u03 --kondisi sehat:s5 massa034:s5 massa068:s5 \
        --sigma-antar 0.010 --skip 60
------------------------------------------------------------------
"""
import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from capture_fft import load_csv  # noqa: E402

LSB_MA = 0.025
FUND_BAND = (200.0, 400.0)
ORDERS = [0.25, 0.5, 0.75, 1.0]


def features(path):
    meta, t, raw = load_csv(path)
    i_ma = raw * LSB_MA
    fs = 1e6 / np.median(np.diff(t))
    ac = i_ma - i_ma.mean()
    win = np.hanning(len(ac))
    amp = 2.0 * np.abs(np.fft.rfft(ac * win)) / win.sum()
    f = np.fft.rfftfreq(len(ac), 1.0 / fs)
    band = (f > FUND_BAND[0]) & (f < FUND_BAND[1])
    f1 = f[band][amp[band].argmax()]
    vals = [amp[np.abs(f / f1 - k) < 0.01].max() for k in ORDERS]
    return float(meta.get("batch_t_s", "nan")), f1, i_ma.mean(), vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True)
    ap.add_argument("--kondisi", nargs="+", required=True, help="label:sesi, mis. sehat:s5 massa034:s5")
    ap.add_argument("--skip", type=float, default=60, help="buang rekaman t < skip detik")
    ap.add_argument("--sigma-antar", type=float, default=None,
                    help="σ antar-unit Sehat untuk orde ¼ (mA), mis. 0.010 untuk tipe A")
    args = ap.parse_args()

    stats = {}
    for item in args.kondisi:
        label, sesi = item.split(":")
        rows = [features(p) for p in sorted(glob.glob(f"data/{label}_{args.unit}_pwm100_{sesi}_*.csv"))]
        rows = [r for r in rows if not (r[0] < args.skip)]
        if not rows:
            print(f"{label}:{sesi} — tidak ada rekaman")
            continue
        v = np.array([r[3] for r in rows])
        stats[label] = dict(n=len(rows), f1=np.mean([r[1] for r in rows]), i=np.mean([r[2] for r in rows]),
                            mean=v.mean(0), sd=v.std(0, ddof=1))

    base = stats[args.kondisi[0].split(":")[0]]
    hdr = "".join(f"{'orde ' + str(k):>18s}" for k in ORDERS)
    print(f"{'kondisi':12s}{'n':>4s}{'f1 (Hz)':>10s}{'I (mA)':>9s}{hdr}")
    for label, s in stats.items():
        cells = "".join(f"{m:>10.3f} ± {sd:<5.3f}" for m, sd in zip(s["mean"], s["sd"]))
        print(f"{label:12s}{s['n']:>4d}{s['f1']:>10.1f}{s['i']:>9.2f}{cells}")

    print("\nCohen's d terhadap kondisi pertama (orde ¼ = kandidat 1× putaran):")
    for label, s in list(stats.items())[1:]:
        d_in = (s["mean"] - base["mean"]) / np.sqrt((s["sd"] ** 2 + base["sd"] ** 2) / 2)
        line = f"  {label:12s} d(dalam-unit): " + "  ".join(f"{k}: {d:+.1f}" for k, d in zip(ORDERS, d_in))
        if args.sigma_antar:
            d_ant = (s["mean"][0] - base["mean"][0]) / args.sigma_antar
            line += f"   | d(antar-unit, orde ¼): {d_ant:+.1f}"
        print(line)


if __name__ == "__main__":
    main()
