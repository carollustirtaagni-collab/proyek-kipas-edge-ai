#!/usr/bin/env python3
"""
ekspor_model.py  —  Latih model final, kuantisasi int8, ekspor ke header C
------------------------------------------------------------------
Konfigurasi final (lihat log 20-10-2026 di README):
  masukan 7 ciri = 5 ciri bentuk riak + 2 selisih terhadap patokan unit
      [riak_dc, kurtosis, crest, flat, lantai_rel, Δlog_dc, Δriak_dc]
  MLP 7 → 32 → 16 → 3 (ReLU), dilatih pada seluruh data latih (kelas diseimbangkan)
  pengaman fisik: |I/I_patokan − 1| > 0,25 → Tidak Dikenal

Kuantisasi: simetris per-tensor. Bobot int8, bias int32, aktivasi int8 dengan
skala dari data kalibrasi (persentil 99,9 %). Inferensi int8 disimulasikan di
sini dengan aritmetika yang SAMA dengan firmware (requantisasi pakai float).

Keluaran: firmware/03_klasifikasi/model_data.h
------------------------------------------------------------------
"""
import os
import sys

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from dataset import load, KELAS  # noqa: E402
from latih_model import baselines, baseline_key, balance, report, SEED, HIDDEN  # noqa: E402

BASE_FEATS = ["riak_dc", "kurtosis", "crest", "flat", "lantai_rel"]
DELTA_FEATS = ["log_dc", "riak_dc"]
BATAS_ARUS = 0.25
OUT_H = "firmware/03_klasifikasi/model_data.h"


def build_inputs(d, names, mask, base):
    X = d["X"][mask]
    g = d["grp"][mask]
    B = np.array([base[baseline_key(x)] for x in g])
    bi = [names.index(n) for n in BASE_FEATS]
    di = [names.index(n) for n in DELTA_FEATS]
    inp = np.hstack([X[:, bi], (X - B)[:, di]]).astype(np.float32)
    dlog = X[:, names.index("log_dc")] - B[:, names.index("log_dc")]
    return inp, dlog


def q_scale(x, pct=99.9):
    return max(float(np.percentile(np.abs(x), pct)), 1e-6) / 127.0


def quantize(sc, clf, Z_cal):
    """Mengembalikan parameter kuantisasi per lapisan."""
    layers = []
    s_in = q_scale(Z_cal)
    a = Z_cal
    for li, (W, b) in enumerate(zip(clf.coefs_, clf.intercepts_)):
        sW = max(np.abs(W).max(), 1e-8) / 127.0
        Wq = np.clip(np.round(W / sW), -127, 127).astype(np.int8)
        bq = np.round(b / (s_in * sW)).astype(np.int32)
        real = a @ W + b
        last = li == len(clf.coefs_) - 1
        if not last:
            real = np.maximum(real, 0)
            s_out = q_scale(real)
        else:
            s_out = None
        layers.append(dict(Wq=Wq, bq=bq, s_in=s_in, sW=sW, s_out=s_out))
        a = real
        s_in = s_out
    return layers


def infer_int8(Z, layers):
    """Simulasi persis firmware. Z = masukan ter-standarisasi (float)."""
    q = np.clip(np.round(Z / layers[0]["s_in"]), -127, 127).astype(np.int32)
    for L in layers:
        acc = q @ L["Wq"].astype(np.int32) + L["bq"]
        if L["s_out"] is None:
            return acc.astype(np.float64) * (L["s_in"] * L["sW"])      # logit
        m = L["s_in"] * L["sW"] / L["s_out"]
        q = np.clip(np.round(acc * m), 0, 127).astype(np.int32)        # ReLU + requant


def c_array(name, arr, ctype, per_line=16):
    flat = np.asarray(arr).ravel()
    body = ",\n  ".join(", ".join(str(int(v)) if ctype != "float" else f"{float(v):.9g}f"
                                  for v in flat[i:i + per_line]) for i in range(0, len(flat), per_line))
    return f"static const {ctype} {name}[{len(flat)}] = {{\n  {body}\n}};\n"


def main():
    d = load()
    names = list(d["names"])
    base = baselines(d, names)
    lat = d["peran"] == "latih"
    Xin, dlog = build_inputs(d, names, lat, base)
    y = d["y"][lat]
    rng = np.random.default_rng(SEED)

    # Batas masukan: persentil 0,5–99,5 % data latih; Δlog_dc dibatasi ke ±25 % arus
    # (di luar itu pengaman sudah memutuskan Tidak Dikenal). Mencegah resolusi int8 habis
    # oleh nilai ekstrem (mis. kipas dilepas = −100 %).
    lo = np.percentile(Xin, 0.5, axis=0); hi = np.percentile(Xin, 99.5, axis=0)
    k = len(BASE_FEATS)
    lo[k], hi[k] = np.log10(1 - BATAS_ARUS), np.log10(1 + BATAS_ARUS)
    Xin = np.clip(Xin, lo, hi)
    sc = StandardScaler().fit(Xin)
    Z = sc.transform(Xin)
    Zb, yb = balance(Z, y, rng)
    clf = MLPClassifier(hidden_layer_sizes=HIDDEN, alpha=1e-3, max_iter=300, early_stopping=True,
                        random_state=SEED).fit(Zb, yb)

    layers = quantize(sc, clf, Z)
    logit = infer_int8(Z, layers)
    p_f = clf.predict(Z)
    p_q = logit.argmax(1)
    guard = np.abs(10 ** dlog - 1) > BATAS_ARUS
    p_f = np.where(guard, 2, p_f); p_q = np.where(guard, 2, p_q)
    print(f"Kesesuaian float vs int8: {np.mean(p_f == p_q) * 100:.2f} %")
    report("Model final float (data latih, in-sample)", y, p_f)
    report("Model final int8  (data latih, in-sample)", y, p_q)

    n_w = sum(L["Wq"].size for L in layers); n_b = sum(L["bq"].size for L in layers)
    size = n_w + 4 * n_b + 4 * (2 * Xin.shape[1])
    print(f"Ukuran model: {n_w} bobot int8 + {n_b} bias int32 + skaler ≈ {size} byte")

    # ---- Ekspor header C ----
    os.makedirs(os.path.dirname(OUT_H), exist_ok=True)
    dims = [Xin.shape[1]] + [L["Wq"].shape[1] for L in layers]
    lines = ["// Dibuat otomatis oleh tools/ekspor_model.py — jangan diedit manual.",
             "#pragma once", "#include <stdint.h>", "",
             f"#define MODEL_N_IN {dims[0]}", f"#define MODEL_N_H1 {dims[1]}",
             f"#define MODEL_N_H2 {dims[2]}", f"#define MODEL_N_OUT {dims[3]}",
             f"#define MODEL_BATAS_ARUS {BATAS_ARUS}f", "",
             "// Urutan masukan: " + ", ".join(BASE_FEATS + ["d_" + n for n in DELTA_FEATS]),
             "// Kelas: " + ", ".join(f"{i}={k}" for i, k in enumerate(KELAS)), ""]
    lines.append(c_array("CLIP_LO", lo, "float"))
    lines.append(c_array("CLIP_HI", hi, "float"))
    lines.append(c_array("SC_MEAN", sc.mean_, "float"))
    lines.append(c_array("SC_STD", sc.scale_, "float"))
    lines.append(f"static const float S_IN0 = {layers[0]['s_in']:.9g}f;\n")
    for i, L in enumerate(layers, 1):
        # W disimpan berurutan [neuron keluaran][masukan] agar loop C sederhana
        lines.append(c_array(f"MDL_W{i}", L["Wq"].T, "int8_t"))
        lines.append(c_array(f"MDL_B{i}", L["bq"], "int32_t"))
        lines.append(f"static const float MDL_M{i} = {(L['s_in'] * L['sW'] / L['s_out']) if L['s_out'] else (L['s_in'] * L['sW']):.9g}f;"
                     + ("  // requant" if L["s_out"] else "  // skala logit") + "\n")
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"Header ditulis: {OUT_H}")

    # Simpan vektor uji untuk memverifikasi firmware (masukan mentah → logit)
    idx = rng.choice(len(Xin), 8, replace=False)
    np.savez("data/vektor_uji_model.npz", x=Xin[idx], logit=logit[idx])
    print("Contoh vektor uji (masukan → kelas int8):")
    for i in idx[:4]:
        print("  ", np.round(Xin[i], 4).tolist(), "→", KELAS[int(p_q[i])])


if __name__ == "__main__":
    main()
