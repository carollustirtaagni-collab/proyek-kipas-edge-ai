#!/usr/bin/env python3
"""
evaluasi_final.py  —  LOUO + antar-sesi untuk pipeline final PERSIS seperti di firmware
------------------------------------------------------------------
Per lipatan (satu unit ditahan): batas masukan, standarisasi, MLP, dan kuantisasi
int8 dihitung ulang hanya dari data latih lipatan itu; unit uji memakai patokan
Sehat s4 miliknya sendiri dan hanya data sesi lain (s5/s5k) yang dinilai.
Pembanding: ambang batas I_RMS absolut dan ambang batas relatif ΔI/I_patokan.
------------------------------------------------------------------
"""
import os
import sys

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from dataset import load, TIPE  # noqa: E402
from latih_model import (baselines, baseline_key, balance, report, irms, fit_threshold,  # noqa: E402
                         predict_threshold, SEED, HIDDEN)
from ekspor_model import build_inputs, quantize, infer_int8, BASE_FEATS, BATAS_ARUS  # noqa: E402


def fit_pipeline(Xin, y, rng):
    lo = np.percentile(Xin, 0.5, axis=0); hi = np.percentile(Xin, 99.5, axis=0)
    k = len(BASE_FEATS)
    lo[k], hi[k] = np.log10(1 - BATAS_ARUS), np.log10(1 + BATAS_ARUS)
    Xc = np.clip(Xin, lo, hi)
    sc = StandardScaler().fit(Xc)
    Z = sc.transform(Xc)
    Zb, yb = balance(Z, y, rng)
    clf = MLPClassifier(hidden_layer_sizes=HIDDEN, alpha=1e-3, max_iter=300, early_stopping=True,
                        random_state=SEED).fit(Zb, yb)
    return lo, hi, sc, quantize(sc, clf, Z)


def predict_pipeline(model, Xin, dlog):
    lo, hi, sc, layers = model
    p = infer_int8(sc.transform(np.clip(Xin, lo, hi)), layers).argmax(1)
    return np.where(np.abs(10 ** dlog - 1) > BATAS_ARUS, 2, p)


def main():
    d = load()
    names = list(d["names"])
    base = baselines(d, names)
    lat = d["peran"] == "latih"
    Xin, dlog = build_inputs(d, names, lat, base)
    y, grp, sesi = d["y"][lat], d["grp"][lat], d["sesi"][lat]
    rng = np.random.default_rng(SEED)
    ev = ~((y == 0) & (sesi == "s4"))
    li = names.index("log_dc")
    rel = 10 ** dlog - 1
    v_abs = irms(d["X"][lat], names)

    p_ai = np.zeros_like(y); p_abs = np.zeros_like(y); p_rel = np.zeros_like(y)
    for g in np.unique(grp):
        te = (grp == g) & ev; tr = grp != g
        if not te.any():
            continue
        p_ai[te] = predict_pipeline(fit_pipeline(Xin[tr], y[tr], rng), Xin[te], dlog[te])
        p_abs[te] = predict_threshold(v_abs[te], fit_threshold(v_abs[tr], y[tr]))
        th = fit_threshold(rel[tr], y[tr])
        p_rel[te] = np.where(np.abs(rel[te]) > BATAS_ARUS, 2, predict_threshold(rel[te], th))

    y_e, g_e = y[ev], grp[ev]
    report("LOUO + antar-sesi — MLP int8 (pipeline firmware)", y_e, p_ai[ev])
    report("LOUO + antar-sesi — ambang batas I_RMS absolut", y_e, p_abs[ev])
    report("LOUO + antar-sesi — ambang batas relatif + pengaman", y_e, p_rel[ev])
    print("\n   Per unit uji (MLP int8 / ambang absolut / ambang relatif):")
    for g in np.unique(g_e):
        m = g_e == g
        print(f"   {g:16s} tipe {TIPE.get(g, '-')}  n={m.sum():5d}  {np.mean(p_ai[ev][m]==y_e[m])*100:5.1f} %"
              f"  {np.mean(p_abs[ev][m]==y_e[m])*100:5.1f} %  {np.mean(p_rel[ev][m]==y_e[m])*100:5.1f} %")
    sehat5 = (y_e == 0)
    print(f"\n   Alarm palsu pada Sehat sesi lain: MLP {np.mean(p_ai[ev][sehat5] != 0)*100:.1f} %, "
          f"ambang relatif {np.mean(p_rel[ev][sehat5] != 0)*100:.1f} %")

    # Data eksternal dengan model penuh
    model = fit_pipeline(Xin, y, rng)
    ext = d["peran"] == "eksternal"
    Xe, dle = build_inputs(d, names, ext, base)
    pe = predict_pipeline(model, Xe, dle)
    labs = np.array([f"{k}_{g}" for k, g in zip(d["kond"][ext], d["grp"][ext])])
    print("\n   Data eksternal (model penuh):")
    for lab in sorted(set(labs)):
        m = labs == lab
        print(f"   {lab:20s} n={m.sum():5d}  → " + "  ".join(
            f"{n} {np.mean(pe[m] == k)*100:5.1f} %" for k, n in enumerate(["Sehat", "Terhambat", "Tidak Dikenal"])))


if __name__ == "__main__":
    main()
