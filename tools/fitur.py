#!/usr/bin/env python3
"""
fitur.py  —  Ekstraksi ciri per jendela (dipakai pelatihan DAN ditiru di firmware)
------------------------------------------------------------------
Satu jendela = N_WIN sampel arus (768 sampel ≈ 253 ms pada 3030 SPS).
Semua ciri dihitung dari jendela itu saja, dengan operasi yang tersedia
di ESP32-S3 (FFT 1024 titik via ESP-DSP, statistik sederhana).

Ciri (urutan TETAP — firmware memakai urutan yang sama):
  0  log_dc        log10(arus DC [mA], min 0,1)
  1  riak_dc       riak RMS / DC
  2  kurtosis      kurtosis (excess) riak
  3  skew          kemencengan riak
  4  crest         puncak |riak| / riak RMS
  5  f1_khz        frekuensi fundamental f1 [kHz] (puncak terkuat 200–400 Hz)
  6  a1_rel        log10(A1 / riak RMS), A1 = amplitudo di f1
  7..13 orde_k     log10(A_k / A1) untuk k = 0,25 0,5 0,75 1,5 2 3 4
 14  lebar         log10(energi ±4 % di sekitar f1 / energi ±1 bin di f1)
 15  flat          kerataan spektrum (geo/arit) pita 50–1500 Hz
 16  lantai_rel    log10(median amplitudo / riak RMS)
------------------------------------------------------------------
"""
import numpy as np

N_WIN = 768                 # sampel per jendela
N_FFT = 1024                # FFT dengan zero-padding
FUND_BAND = (200.0, 400.0)
ORDERS = (0.25, 0.5, 0.75, 1.5, 2.0, 3.0, 4.0)
EPS = 1e-6

FEATURE_NAMES = (["log_dc", "riak_dc", "kurtosis", "skew", "crest", "f1_khz", "a1_rel"]
                 + [f"orde_{k}" for k in ORDERS] + ["lebar", "flat", "lantai_rel"])

_WIN = np.hanning(N_WIN)
_WSUM = _WIN.sum()


def window_features(i_ma, fs):
    """i_ma: array N_WIN sampel arus [mA]; fs: laju cuplik [Hz]. Mengembalikan vektor ciri."""
    dc = float(np.mean(i_ma))
    ac = i_ma - dc
    rms = float(np.sqrt(np.mean(ac ** 2))) + EPS
    m3 = float(np.mean(ac ** 3)); m4 = float(np.mean(ac ** 4))
    kurt = m4 / rms ** 4 - 3.0
    skew = m3 / rms ** 3
    crest = float(np.max(np.abs(ac))) / rms

    amp = 2.0 * np.abs(np.fft.rfft(ac * _WIN, N_FFT)) / _WSUM
    df = fs / N_FFT
    f = np.arange(len(amp)) * df
    b = (f > FUND_BAND[0]) & (f < FUND_BAND[1])
    j1 = int(np.flatnonzero(b)[np.argmax(amp[b])])
    f1 = f[j1]
    a1 = float(amp[j1]) + EPS

    def amp_at(freq):
        if freq >= fs / 2 - 2 * df:
            return EPS
        j = int(round(freq / df))
        return float(np.max(amp[max(j - 1, 0):j + 2])) + EPS

    orde = [np.log10(amp_at(k * f1) / a1) for k in ORDERS]

    p = amp ** 2
    near = p[max(j1 - 1, 0):j1 + 2].sum() + EPS
    span = max(int(round(0.04 * f1 / df)), 2)
    wide = p[max(j1 - span, 0):j1 + span + 1].sum() + EPS
    lebar = np.log10(wide / near)

    band = (f > 50) & (f < 1500)
    pb = p[band] + 1e-12
    flat = float(np.exp(np.mean(np.log(pb))) / np.mean(pb))
    lantai = np.log10(float(np.median(amp[1:])) / rms + EPS)

    return np.array([np.log10(max(dc, 0.1)), rms / max(dc, 1.0), kurt, skew, crest,
                     f1 / 1000.0, np.log10(a1 / rms), *orde, lebar, flat, lantai], dtype=np.float32)


def split_windows(i_ma, n=N_WIN):
    """Potong rekaman menjadi jendela tidak tumpang tindih."""
    k = len(i_ma) // n
    return [i_ma[j * n:(j + 1) * n] for j in range(k)]
