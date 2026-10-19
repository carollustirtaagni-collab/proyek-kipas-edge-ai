#!/usr/bin/env python3
"""
dataset.py  —  Menyusun dataset jendela berlabel dari rekaman CSV di data/
------------------------------------------------------------------
Aturan pelabelan (skema 3 kelas):
  0 Sehat            sehat_*  sesi s4, s4u, s5, s5k   (U09 = cadangan, dipisah)
  1 Aliran Terhambat blok50_*, blok75_*
  2 Tidak Dikenal    unknown-*  (transisi: hanya jendela yang memuat peristiwa)
Dikeluarkan dari pelatihan (disimpan sebagai data "eksternal" untuk diuji):
  massa*, patah_*, runin_*, sehat U09, serta sehat sesi lama (s1–s3).

Filter kestabilan (kelas Sehat & Aliran Terhambat): sebuah rekaman dipakai
bila arus DC-nya berada dalam ±1 mA dari nilai stabil kondisinya (rata-rata
10 rekaman terakhir pada kondisi yang sama). Ini membuang fase pemanasan
dan fase penyesuaian setelah karton dipasang.

Hasil disimpan ke data/fitur_jendela.npz (tidak di-commit).
------------------------------------------------------------------
"""
import glob
import os
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from capture_fft import load_csv  # noqa: E402
from fitur import window_features, split_windows, FEATURE_NAMES  # noqa: E402

LSB_MA = 0.025
KELAS = ["Sehat", "Aliran Terhambat", "Tidak Dikenal"]
TIPE = {"u01": "A", "u02": "A", "u03": "A", "u04": "A", "u05": "B", "u06": "B", "u07": "B",
        "u08": "B", "u10": "B", "u11": "B", "u09": "C"}
SESI_SEHAT = {"s4", "s4u", "s5", "s5k"}
STABIL_MA = 1.0
OUT = "data/fitur_jendela.npz"

RX = re.compile(r"^(?P<kond>[a-z0-9\-]+)_(?P<unit>u\d\d(?:u\d\d)?)_pwm100(?:_(?P<sesi>s\w+))?_\d{8}-\d{6}\.csv$")


def parse_name(path):
    m = RX.match(os.path.basename(path))
    return (m.group("kond"), m.group("unit"), m.group("sesi") or "s1") if m else None


def kategori(kond, unit, sesi):
    """Mengembalikan (peran, kelas): peran 'latih' atau 'eksternal' atau None."""
    if kond == "sehat":
        if sesi not in SESI_SEHAT:
            return None, None
        return ("eksternal" if unit == "u09" else "latih"), 0
    if kond in ("blok50", "blok75"):
        return "latih", 1
    if kond.startswith("unknown-"):
        return "latih", 2
    if kond.startswith("massa") or kond == "patah":
        return "eksternal", None
    return None, None


def grup_unit(kond, unit):
    """Kelompok untuk leave-one-unit-out. Beban non-kipas dikelompokkan per kondisi."""
    if unit == "u00":
        return "u00-" + kond.replace("unknown-", "")
    return unit


def is_transisi_event(w):
    """Jendela transisi yang benar-benar memuat peristiwa colok/cabut atau kipas lepas."""
    dc = w.mean()
    half = len(w) // 2
    return dc < 20.0 or abs(w[:half].mean() - w[half:].mean()) > 5.0


def build(verbose=True):
    files = sorted(glob.glob("data/*.csv"))
    batches = defaultdict(list)                       # (kond, unit, sesi) -> [(path, dc, t)]
    cache = {}
    for p in files:
        info = parse_name(p)
        if not info:
            continue
        kond, unit, sesi = info
        peran, _ = kategori(kond, unit, sesi)
        if not peran:
            continue
        meta, t, raw = load_csv(p)
        i_ma = raw * LSB_MA
        fs = 1e6 / np.median(np.diff(t))
        cache[p] = (i_ma, fs)
        batches[(kond, unit, sesi)].append((p, float(i_ma.mean())))

    X, y, grp, sesi_l, kond_l, peran_l, file_l = [], [], [], [], [], [], []
    dibuang = 0
    for (kond, unit, sesi), items in batches.items():
        peran, kls = kategori(kond, unit, sesi)
        stabil = None
        if kls in (0, 1) or kond.startswith("massa") or kond == "patah":
            stabil = np.mean([dc for _, dc in items[-10:]])
        for p, dc in items:
            if stabil is not None and abs(dc - stabil) > STABIL_MA:
                dibuang += 1
                continue
            i_ma, fs = cache[p]
            for w in split_windows(i_ma):
                if kond == "unknown-transisi" and not is_transisi_event(w):
                    continue
                X.append(window_features(w, fs))
                y.append(-1 if kls is None else kls)
                grp.append(grup_unit(kond, unit)); sesi_l.append(sesi); kond_l.append(kond)
                peran_l.append(peran); file_l.append(os.path.basename(p))

    d = dict(X=np.array(X), y=np.array(y), grp=np.array(grp), sesi=np.array(sesi_l),
             kond=np.array(kond_l), peran=np.array(peran_l), berkas=np.array(file_l),
             names=np.array(FEATURE_NAMES))
    np.savez_compressed(OUT, **d)
    if verbose:
        lat = d["peran"] == "latih"
        print(f"Rekaman dibuang (belum stabil): {dibuang}")
        print(f"Jendela latih: {lat.sum()}  | eksternal: {(~lat).sum()}")
        for k, n in enumerate(KELAS):
            print(f"  {n:18s}: {np.sum(d['y'][lat] == k)} jendela, unit: "
                  f"{sorted(set(d['grp'][lat][d['y'][lat] == k]))}")
        print(f"Disimpan: {OUT}")
    return d


def load():
    d = np.load(OUT, allow_pickle=False)
    return {k: d[k] for k in d.files}


if __name__ == "__main__":
    build()
