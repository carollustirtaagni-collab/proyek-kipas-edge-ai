#!/usr/bin/env python3
"""
latih_model.py  —  Evaluasi model 3 kelas + pembanding ambang batas
------------------------------------------------------------------
Membaca data/fitur_jendela.npz (dibuat tools/dataset.py), lalu:
  1. Leave-one-unit-out (LOUO): MLP vs metode ambang batas I_RMS
  2. Uji antar-sesi kelas Sehat (latih tanpa Sehat s5, uji di Sehat s5)
  3. Uji data eksternal: U09 (tipe C, tak pernah dilihat), massa, bilah patah
Opsi --tanpa log_dc f1_khz untuk menguji model tanpa ciri absolut.
Opsi --baseline: tiap unit punya patokan (median ciri Sehat sesi s4, setara
"kalibrasi saat pemasangan"); model memakai selisih ciri terhadap patokan.
Pada mode ini evaluasi LOUO hanya memakai data sesi lain (s5/s5k) sebagai uji,
sehingga sekaligus menjadi uji antar-sesi.

Contoh:
    python tools/latih_model.py
    python tools/latih_model.py --tanpa log_dc f1_khz
------------------------------------------------------------------
"""
import argparse
import os
import sys

import numpy as np
from sklearn.metrics import confusion_matrix
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from dataset import load, KELAS, TIPE  # noqa: E402

SEED = 0
HIDDEN = (32, 16)


def balance(X, y, rng, per_class=None):
    """Seimbangkan kelas dengan pengambilan ulang (dengan pengembalian)."""
    classes = np.unique(y)
    n = per_class or int(np.median([np.sum(y == c) for c in classes]))
    idx = np.concatenate([rng.choice(np.flatnonzero(y == c), n, replace=True) for c in classes])
    return X[idx], y[idx]


def fit_mlp(X, y, rng):
    sc = StandardScaler().fit(X)
    Xb, yb = balance(sc.transform(X), y, rng)
    clf = MLPClassifier(hidden_layer_sizes=HIDDEN, alpha=1e-3, max_iter=300, early_stopping=True,
                        random_state=SEED).fit(Xb, yb)
    return sc, clf


def predict(clf, sc, X, yakin=0.0):
    """Prediksi dengan ambang keyakinan: max P < yakin → Tidak Dikenal (kelas 2)."""
    pr = clf.predict_proba(sc.transform(X))
    p = clf.classes_[pr.argmax(1)]
    if yakin > 0:
        p = np.where(pr.max(1) < yakin, 2, p)
    return p


def guard(p, dlog, batas):
    """Pengaman fisik: arus menyimpang > batas dari patokan unit → Tidak Dikenal."""
    if batas <= 0:
        return p
    return np.where(np.abs(10 ** dlog - 1) > batas, 2, p)


def irms(X, names):
    """Arus RMS total dari ciri: sqrt(DC² + riak²)."""
    dc = 10 ** X[:, list(names).index("log_dc")]
    rr = X[:, list(names).index("riak_dc")] * np.maximum(dc, 1.0)
    return np.sqrt(dc ** 2 + rr ** 2)


def fit_threshold(v, y):
    """Dua ambang pada I_RMS: kelas = urutan interval terbaik (pencarian grid)."""
    qs = np.unique(np.quantile(v, np.linspace(0, 1, 121)))
    best = (-1, None)
    order_opts = [(0, 1, 2), (2, 0, 1), (0, 2, 1), (1, 0, 2), (2, 1, 0), (1, 2, 0)]
    for i, a in enumerate(qs):
        for b in qs[i + 1:]:
            seg = np.digitize(v, [a, b])
            for o in order_opts:
                pred = np.array(o)[seg]
                acc = np.mean(pred == y)
                if acc > best[0]:
                    best = (acc, (a, b, o))
    return best[1]


def predict_threshold(v, th):
    a, b, o = th
    return np.array(o)[np.digitize(v, [a, b])]


def baseline_key(g):
    """Unit patokan: kipas itu sendiri; beban non-kipas memakai patokan gabungan semua unit."""
    if g == "u02u11":
        return "u02"
    return g if g.startswith("u") and not g.startswith("u00") else "gabungan"


def baselines(d, names):
    """Median ciri jendela Sehat sesi s4 per unit (+ 'gabungan')."""
    m = (d["kond"] == "sehat") & (d["sesi"] == "s4")
    base = {g: np.median(d["X"][m & (d["grp"] == g)], axis=0) for g in np.unique(d["grp"][m])}
    base["gabungan"] = np.median(np.array([v for k, v in base.items() if k != "u09"]), axis=0)
    return base


def report(name, y, p):
    cm = confusion_matrix(y, p, labels=[0, 1, 2])
    rec = cm.diagonal() / np.maximum(cm.sum(1), 1)
    acc = np.mean(y == p)
    print(f"\n== {name} ==  akurasi {acc*100:.1f} %  | recall: " +
          ", ".join(f"{KELAS[k]} {rec[k]*100:.1f} %" for k in range(3)))
    print("   matriks kebingungan (baris = sebenarnya, kolom = prediksi):")
    for k in range(3):
        print(f"   {KELAS[k]:18s} " + " ".join(f"{v:7d}" for v in cm[k]))
    return acc, rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tanpa", nargs="*", default=[], help="nama ciri yang dibuang")
    ap.add_argument("--baseline", action="store_true", help="pakai selisih terhadap patokan Sehat s4 per unit")
    ap.add_argument("--yakin", type=float, default=0.0,
                    help="ambang keyakinan softmax; di bawahnya prediksi = Tidak Dikenal (mis. 0.6)")
    ap.add_argument("--batas-arus", type=float, default=0.0,
                    help="dengan --baseline: |I/I_patokan - 1| di atas nilai ini → Tidak Dikenal (mis. 0.25)")
    ap.add_argument("--delta", nargs="*", default=None,
                    help="dengan --baseline: ciri yang diberi selisih patokan (bawaan: semua)")
    args = ap.parse_args()

    d = load()
    names = list(d["names"])
    keep = [i for i, n in enumerate(names) if n not in args.tanpa]
    lat = d["peran"] == "latih"
    X_all, y, grp, sesi, kond = d["X"][lat], d["y"][lat], d["grp"][lat], d["sesi"][lat], d["kond"][lat]
    X = X_all[:, keep]
    if args.baseline:
        base = baselines(d, names)
        di = [names.index(n) for n in args.delta] if args.delta else list(range(len(names)))
        X = np.hstack([X, (X_all - np.array([base[baseline_key(g)] for g in grp]))[:, di]])
        print(f"Ciri selisih patokan: {[names[i] for i in di]}")
    v_rms = irms(X_all, names)
    dlog = (X_all[:, names.index("log_dc")] - np.array([base[baseline_key(g)][names.index("log_dc")] for g in grp])
            ) if args.baseline else np.zeros(len(y))
    rng = np.random.default_rng(SEED)
    print(f"Ciri dipakai ({len(keep)}): {[names[i] for i in keep]}")

    # ---- 1. LOUO ----
    p_mlp = np.zeros_like(y); p_thr = np.zeros_like(y)
    eval_mask = np.ones_like(y, dtype=bool)
    if args.baseline:                      # data patokan (Sehat s4) tidak dipakai sebagai uji
        eval_mask = ~((y == 0) & (sesi == "s4"))
    for g in np.unique(grp):
        te = (grp == g) & eval_mask; tr = grp != g
        if not te.any():
            continue
        sc, clf = fit_mlp(X[tr], y[tr], rng)
        p_mlp[te] = guard(predict(clf, sc, X[te], args.yakin), dlog[te], args.batas_arus)
        th = fit_threshold(v_rms[tr], y[tr])
        p_thr[te] = predict_threshold(v_rms[te], th)
    y_full = y
    y, p_mlp, p_thr, grp_e = y[eval_mask], p_mlp[eval_mask], p_thr[eval_mask], grp[eval_mask]
    acc_m, rec_m = report("LOUO — MLP", y, p_mlp)
    acc_t, rec_t = report("LOUO — ambang batas I_RMS", y, p_thr)

    print("\n   Akurasi LOUO per unit uji (MLP / ambang):")
    for g in np.unique(grp_e):
        m = grp_e == g
        tp = TIPE.get(g, "-")
        print(f"   {g:16s} tipe {tp}  n={m.sum():5d}  MLP {np.mean(p_mlp[m]==y[m])*100:5.1f} %"
              f"   ambang {np.mean(p_thr[m]==y[m])*100:5.1f} %")
    for t in ("A", "B"):
        m = np.array([TIPE.get(g) == t for g in grp_e])
        print(f"   Tipe {t}: MLP {np.mean(p_mlp[m]==y[m])*100:.1f} %, ambang {np.mean(p_thr[m]==y[m])*100:.1f} %")

    # ---- 2. Antar-sesi kelas Sehat ----
    y = y_full
    te = (y == 0) & (sesi == "s5")
    tr = ~te
    sc, clf = fit_mlp(X[tr], y[tr], rng)
    p = guard(predict(clf, sc, X[te], args.yakin), dlog[te], args.batas_arus)
    print(f"\n== Antar-sesi: latih tanpa Sehat s5, uji pada Sehat s5 (n={te.sum()}) ==")
    print(f"   benar Sehat {np.mean(p==0)*100:.1f} %  | alarm palsu (diprediksi bukan Sehat) {np.mean(p!=0)*100:.1f} %")

    # ---- 3. Data eksternal dengan model penuh ----
    sc, clf = fit_mlp(X, y, rng)
    ext = d["peran"] == "eksternal"
    Xe = d["X"][ext][:, keep]
    if args.baseline:
        Xe = np.hstack([Xe, (d["X"][ext] - np.array([base[baseline_key(g)] for g in d["grp"][ext]]))[:, di]])
    dlog_e = (d["X"][ext][:, names.index("log_dc")] - np.array([base[baseline_key(g)][names.index("log_dc")]
              for g in d["grp"][ext]])) if args.baseline else np.zeros(ext.sum())
    pe = guard(predict(clf, sc, Xe, args.yakin), dlog_e, args.batas_arus)
    print("\n== Data eksternal (model dilatih dengan semua data latih) ==")
    labs = np.array([f"{k}_{g}" for k, g in zip(d["kond"][ext], d["grp"][ext])])
    for lab in sorted(set(labs)):
        m = labs == lab
        frac = [np.mean(pe[m] == k) * 100 for k in range(3)]
        print(f"   {lab:20s} n={m.sum():5d}  → Sehat {frac[0]:5.1f} %  Terhambat {frac[1]:5.1f} %  Tidak Dikenal {frac[2]:5.1f} %")

    print(f"\nRingkasan: LOUO MLP {acc_m*100:.1f} % vs ambang batas {acc_t*100:.1f} %  "
          f"(selisih {100*(acc_m-acc_t):+.1f} poin)")


if __name__ == "__main__":
    main()
