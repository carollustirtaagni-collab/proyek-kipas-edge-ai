#!/usr/bin/env python3
"""
cek_firmware.py  —  Verifikasi kesetaraan ciri & model antara firmware 03 dan Python
------------------------------------------------------------------
Mengirim 'd' ke firmware 03_klasifikasi, menerima satu jendela mentah beserta
ciri (dan probabilitas bila sudah dikalibrasi), lalu menghitung ulang di Python
(tools/fitur.py + simulasi MLP int8 dari model_data.h) dan membandingkan.

    python tools/cek_firmware.py --port COM14 --n 5
------------------------------------------------------------------
"""
import argparse
import os
import re
import sys
import time

import numpy as np
import serial

sys.path.insert(0, os.path.dirname(__file__))
from fitur import window_features, FEATURE_NAMES  # noqa: E402

HEADER = os.path.join(os.path.dirname(__file__), "..", "firmware", "03_klasifikasi", "model_data.h")


def load_header():
    txt = open(HEADER, encoding="utf-8").read()
    arr = {m.group(2): np.array([float(v.rstrip("f")) for v in re.findall(r"-?[\d.eE+-]+f?", m.group(3))])
           for m in re.finditer(r"static const (\w+) (\w+)\[\d+\] = \{([^}]*)\}", txt)}
    sc = {m.group(1): float(m.group(2)) for m in re.finditer(r"static const float (\w+) = ([-\d.eE+]+)f;", txt)}
    return arr, sc


def infer(inp, arr, sc):
    x = np.clip(inp, arr["CLIP_LO"], arr["CLIP_HI"])
    z = (x - arr["SC_MEAN"]) / arr["SC_STD"]
    q = np.clip(np.round(z / sc["S_IN0"]), -127, 127)
    dims = [len(inp), len(arr["MDL_B1"]), len(arr["MDL_B2"]), len(arr["MDL_B3"])]
    for i in (1, 2, 3):
        W = arr[f"MDL_W{i}"].reshape(dims[i], dims[i - 1])
        acc = W @ q + arr[f"MDL_B{i}"]
        if i < 3:
            q = np.clip(np.round(acc * sc[f"MDL_M{i}"]), 0, 127)
        else:
            lg = acc * sc["MDL_M3"]
            e = np.exp(lg - lg.max())
            return e / e.sum()


def grab(ser):
    ser.reset_input_buffer()
    ser.write(b"d")
    raw, fs, ciri, base, prob, inside = [], None, None, None, None, False
    t0 = time.time()
    while time.time() - t0 < 10:
        line = ser.readline().decode(errors="ignore").strip()
        if line == "#RAW_BEGIN":
            inside = True
        elif line == "#RAW_END":
            inside = False
        elif line.startswith("#fs="):
            fs = float(line[4:])
        elif inside and line and not line.startswith("#"):
            raw.append(float(line))
        elif line.startswith("#CIRI"):
            ciri = dict(kv.split("=") for kv in line.split()[1:])
        elif line.startswith("#BASE"):
            base = dict(kv.split("=") for kv in line.split()[1:])
        elif line.startswith("#PROB"):
            prob = np.array([float(v) for v in line.split()[1:]])
            break
        elif ciri and not line.startswith("#"):
            break
    return np.array(raw), fs, ciri, base, prob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args()
    arr, sc = load_header()
    ser = serial.Serial(args.port, 115200, timeout=1)
    time.sleep(2.5)
    worst = 0.0
    for k in range(args.n):
        raw, fs, ciri, base, prob = grab(ser)
        if ciri is None or len(raw) != 768:
            print(f"[{k}] gagal menerima jendela (n={len(raw)})"); continue
        f = window_features(raw, fs)
        py = {n: f[FEATURE_NAMES.index(n)] for n in ciri}
        diffs = {n: abs(float(ciri[n]) - py[n]) for n in ciri}
        worst = max(worst, max(diffs.values()))
        print(f"[{k}] fs={fs:.1f}  I={raw.mean():.2f} mA  selisih maks ciri = {max(diffs.values()):.2e}  "
              + "  ".join(f"{n}:{float(ciri[n]):.4f}/{py[n]:.4f}" for n in ciri))
        if base is not None and prob is not None:
            bl, br = float(base["logdc"]), float(base["riak"])
            inp = np.array([py["riak_dc"], py["kurtosis"], py["crest"], py["flat"], py["lantai_rel"],
                            py["log_dc"] - bl, py["riak_dc"] - br])
            pp = infer(inp, arr, sc)
            print(f"      P firmware={np.round(prob, 3)}  P python={np.round(pp, 3)}  "
                  f"kelas sama: {prob.argmax() == pp.argmax()}")
    ser.close()
    print(f"\nSelisih ciri terbesar: {worst:.2e}  → {'OK' if worst < 1e-3 else 'PERIKSA'}")


if __name__ == "__main__":
    main()
