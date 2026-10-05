#!/usr/bin/env python3
"""
overlay_orde.py  —  Gerbang kelayakan langkah 1: sebaran antar unit kondisi Sehat
------------------------------------------------------------------
Untuk tiap unit: setiap rekaman diubah ke spektrum amplitudo, sumbu
frekuensinya dinormalisasi ke orde (f / f1, f1 = puncak terkuat di
pita fundamental), lalu dirata-rata. Hasil:
  1. overlay spektrum orde antar unit  (data/gerbang_spektrum_orde.png)
  2. sebaran f1 vs arus per rekaman     (data/gerbang_f1_vs_arus.png)
  3. tabel ciri per unit (amplitudo orde 1–4, riak/DC) + sebaran antar unit

Contoh:
    python tools/overlay_orde.py --units u01 u02 u03 u04 --sesi s4 --skip 60
------------------------------------------------------------------
"""
import argparse
import glob
import os
import sys

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
from capture_fft import load_csv  # noqa: E402

LSB_MA = 0.025                      # 2,5 uV / 0,1 ohm
FUND_BAND = (200.0, 400.0)          # pita pencarian fundamental (Hz)
ORDER_GRID = np.linspace(0.05, 4.5, 1781)
# Palet kategorikal tervalidasi (urutan tetap, tidak diputar)
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK2, MUTED, SURFACE = "#0b0b0b", "#52514e", "#898781", "#fcfcfb"


def per_recording(path):
    meta, t, raw = load_csv(path)
    i_ma = raw * LSB_MA
    fs = 1e6 / np.median(np.diff(t))
    ac = i_ma - i_ma.mean()
    win = np.hanning(len(ac))
    amp = 2.0 * np.abs(np.fft.rfft(ac * win)) / win.sum()
    f = np.fft.rfftfreq(len(ac), 1.0 / fs)
    band = (f > FUND_BAND[0]) & (f < FUND_BAND[1])
    f1 = f[band][amp[band].argmax()]
    order = f / f1
    ok = ORDER_GRID * f1 < fs / 2           # hanya orde di bawah Nyquist
    amp_o = np.where(ok, np.interp(ORDER_GRID, order, amp), np.nan)

    def at_order(k):                        # puncak di sekitar orde k (±0,05)
        m = np.abs(order - k) < 0.05
        return amp[m].max() if m.any() and k * f1 < fs / 2 else np.nan

    return dict(f1=f1, dc=i_ma.mean(), ripple=ac.std(), amp_o=amp_o,
                orders=[at_order(k) for k in (1, 2, 3, 4)],
                t=float(meta.get("batch_t_s", "nan")))


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(alpha=0.25, color=MUTED, lw=0.6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="+", required=True)
    ap.add_argument("--sesi", default="s4")
    ap.add_argument("--skip", type=float, default=60, help="buang rekaman t < skip detik (pemanasan)")
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()

    res = {}
    for u in args.units:
        recs = [per_recording(p) for p in sorted(glob.glob(f"data/sehat_{u}_pwm100_{args.sesi}_*.csv"))]
        recs = [r for r in recs if not (r["t"] < args.skip)]
        if recs:
            res[u] = recs
    if not res:
        sys.exit("Tidak ada rekaman yang cocok.")

    # ---- 1. Overlay spektrum orde ----
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=SURFACE)
    style(ax)
    for k, (u, recs) in enumerate(res.items()):
        mean_amp = np.nanmean([r["amp_o"] for r in recs], axis=0)
        ax.semilogy(ORDER_GRID, mean_amp, lw=1.2, color=COLORS[k], label=f"{u.upper()} (n={len(recs)})")
    for k in (1, 2, 3, 4):
        ax.axvline(k, color=MUTED, lw=0.6, ls=":")
    ax.set_xlabel("Orde (f / f₁)", color=INK2)
    ax.set_ylabel("Amplitudo rata-rata (mA)", color=INK2)
    ax.set_title("Spektrum orde kondisi Sehat per unit — rata-rata semua rekaman setelah pemanasan",
                 color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, labelcolor=INK2, fontsize=9)
    fig.tight_layout()
    p1 = os.path.join(args.outdir, "gerbang_spektrum_orde.png")
    fig.savefig(p1, dpi=130, facecolor=SURFACE)

    # ---- 2. f1 vs arus ----
    fig, ax = plt.subplots(figsize=(7.5, 5.5), facecolor=SURFACE)
    style(ax)
    for k, (u, recs) in enumerate(res.items()):
        ax.scatter([r["dc"] for r in recs], [r["f1"] for r in recs], s=14, alpha=0.75,
                   color=COLORS[k], edgecolors=SURFACE, linewidths=0.6, label=u.upper())
    ax.set_xlabel("Arus rata-rata (mA)", color=INK2)
    ax.set_ylabel("Frekuensi fundamental f₁ (Hz)", color=INK2)
    ax.set_title("Tiap titik = satu rekaman 2,7 s", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, labelcolor=INK2, fontsize=9)
    fig.tight_layout()
    p2 = os.path.join(args.outdir, "gerbang_f1_vs_arus.png")
    fig.savefig(p2, dpi=130, facecolor=SURFACE)

    # ---- 3. Tabel ciri ----
    names = ["f1 (Hz)", "I (mA)", "riak/DC (%)", "A orde1 (mA)", "A orde2 (mA)", "A orde3 (mA)", "A orde4 (mA)"]
    rows = {}
    for u, recs in res.items():
        feats = np.array([[r["f1"], r["dc"], 100 * r["ripple"] / r["dc"], *r["orders"]] for r in recs])
        rows[u] = (np.nanmean(feats, axis=0), np.nanstd(feats, axis=0))
    print(f"{'ciri':14s}" + "".join(f"{u.upper():>18s}" for u in rows) + f"{'σ antar-unit':>14s}{'σ dalam-unit':>14s}")
    for j, n in enumerate(names):
        means = np.array([rows[u][0][j] for u in rows])
        within = np.mean([rows[u][1][j] for u in rows])
        print(f"{n:14s}" + "".join(f"{rows[u][0][j]:>10.3f} ± {rows[u][1][j]:<5.3f}" for u in rows)
              + f"{means.std(ddof=1) if len(means) > 1 else float('nan'):>14.3f}{within:>14.3f}")
    print(f"\nGambar: {p1}\n        {p2}")


if __name__ == "__main__":
    main()
