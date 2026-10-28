#!/usr/bin/env python3
"""
ekspor_edgeimpulse.py  —  Ekspor rekaman ke format CSV Edge Impulse
------------------------------------------------------------------
Lingkup versi Edge Impulse: 2 kipas tipe B dengan arus Sehat hampir sama
(U07, U10), 3 kelas:
  sehat          sehat_u07/u10  sesi s4 + s5
  terhambat      blok50_*, blok75_*  (U07, U10)
  tidak_dikenal  unknown-tanpabeban, unknown-led, unknown-ledpendek

Satu rekaman (8192 sampel ≈ 2,7 s) = satu sampel Edge Impulse; pemotongan
jendela dilakukan di Edge Impulse (Create impulse). Kolom: timestamp (ms),
arus_mA. Timestamp dibuat seragam dari median jarak sampel (3030 Hz), sama
dengan definisi laju cuplik pada data latih dan firmware.

Filter kestabilan sama dengan dataset.py (±1 mA dari nilai stabil kondisi).
Jumlah rekaman Sehat s4 dibatasi (--maks-s4) agar kelas tidak terlalu timpang.

Pembagian uji (bukan acak, agar tidak bocor):
  --uji u10   seluruh data kipas U10 menjadi data uji (latih U07 → uji U10);
              rekaman tidak_dikenal: 30 % terakhir tiap kondisi menjadi uji.
  --uji none  semua kipas masuk data latih (model final); tidak_dikenal tetap
              dibagi 70/30 berdasarkan urutan waktu.

Nama berkas: <label>.<asal>.csv → Edge Impulse mengambil label dari bagian
sebelum titik pertama ("Infer from filename").
Keluaran: data/edgeimpulse/<uji>/{training,testing}/ (CSV di-gitignore).
------------------------------------------------------------------
"""
import argparse
import os
import shutil
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from capture_fft import load_csv  # noqa: E402
from dataset import parse_name, LSB_MA, STABIL_MA  # noqa: E402

UNIT = ("u07", "u10")
UNKNOWN = ("unknown-tanpabeban", "unknown-led", "unknown-ledpendek")
PORSI_UJI_UNKNOWN = 0.3


def label_of(kond, unit, sesi):
    if unit in UNIT and kond == "sehat" and sesi in ("s4", "s5"):
        return "sehat"
    if unit in UNIT and kond in ("blok50", "blok75"):
        return "terhambat"
    if kond in UNKNOWN:
        return "tidak_dikenal"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uji", default="u10", help="unit uji (u07/u10) atau 'none'")
    ap.add_argument("--maks-s4", type=int, default=50, help="maks. rekaman Sehat s4 per unit")
    a = ap.parse_args()
    assert a.uji in UNIT + ("none",), "--uji harus u07, u10, atau none"

    groups = defaultdict(list)                        # (kond, unit, sesi) -> [path]
    for p in sorted(os.listdir("data")):
        info = parse_name(p)
        if info and label_of(*info):
            groups[info].append(os.path.join("data", p))

    out = os.path.join("data", "edgeimpulse", a.uji)
    if os.path.isdir(out):
        shutil.rmtree(out)
    for sub in ("training", "testing"):
        os.makedirs(os.path.join(out, sub))

    hitung = defaultdict(int)
    for (kond, unit, sesi), paths in sorted(groups.items()):
        label = label_of(kond, unit, sesi)
        rek = []
        for p in paths:
            _, t, raw = load_csv(p)
            rek.append((p, t, raw * LSB_MA))
        if label != "tidak_dikenal":
            stabil = np.mean([i.mean() for _, _, i in rek[-10:]])
            rek = [r for r in rek if abs(r[2].mean() - stabil) <= STABIL_MA]
            if sesi == "s4" and len(rek) > a.maks_s4:   # ambil merata sepanjang sesi
                idx = np.linspace(0, len(rek) - 1, a.maks_s4).round().astype(int)
                rek = [rek[k] for k in idx]
        n_latih = round(len(rek) * (1 - PORSI_UJI_UNKNOWN))
        for k, (p, t, i_ma) in enumerate(rek):
            if label == "tidak_dikenal":
                sub = "training" if k < n_latih else "testing"
            else:
                sub = "testing" if unit == a.uji else "training"
            dt_ms = np.median(np.diff(t)) / 1000.0
            asal = os.path.splitext(os.path.basename(p))[0]
            with open(os.path.join(out, sub, f"{label}.{asal}.csv"), "w", newline="") as f:
                f.write("timestamp,arus_mA\n")
                for n, v in enumerate(i_ma):
                    f.write(f"{n * dt_ms:.4f},{v:.3f}\n")
            hitung[(sub, label, unit)] += 1

    print(f"Keluaran: {out}")
    for (sub, label, unit), n in sorted(hitung.items()):
        print(f"  {sub:9s} {label:14s} {unit}: {n} rekaman")


if __name__ == "__main__":
    main()
