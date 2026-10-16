"""Converter figures of merit from captured samples.

The methods follow IEEE Std 1241 for analogue to digital converter testing:

* Sine tests use coherent sampling (an integer, odd number of cycles in the
  record), so no window is applied and the signal occupies exactly one bin.
* SINAD and ENOB come from a least squares sine fit (the four parameter fit
  of IEEE 1241 clause 4.1.4, started from the known test frequency). ENOB is
  reported the IEEE 1241 way, against the full scale range,
  ``log2(FSR / (NAD sqrt(12)))``; it is also reported from the SINAD at
  the test level.
* SNR, THD and SFDR come from the spectrum: harmonics 2 to 9 are folded back
  into the first Nyquist zone and excluded from noise.
* The noise floor is the standard deviation of a shorted input record; noise
  free resolution uses a 6.6 sigma peak to peak, the convention converter
  datasheets use.
* INL is the deviation from the best fit straight line through a slow DC
  sweep, in ppm of FSR. The end point version is reported as well.

Nothing here knows the data came from a simulation. The same functions are
meant to run on a real capture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SineFit:
    amplitude: float
    frequency: float      # cycles per sample
    phase: float
    offset: float
    residual_rms: float


def sine_fit(x: np.ndarray, cycles_per_sample: float, iterations: int = 8) -> SineFit:
    """Four parameter least squares sine fit (IEEE 1241, 4.1.4)."""
    x = np.asarray(x, float)
    n = np.arange(len(x), dtype=float)
    w = 2 * np.pi * cycles_per_sample
    # Three parameter fit at the known frequency gives the starting point.
    m = np.column_stack([np.cos(w * n), np.sin(w * n), np.ones_like(n)])
    a, b, c = np.linalg.lstsq(m, x, rcond=None)[0]
    dw = 0.0
    for _ in range(iterations):
        wi = w + dw
        m = np.column_stack([np.cos(wi * n), np.sin(wi * n), np.ones_like(n),
                             -a * n * np.sin(wi * n) + b * n * np.cos(wi * n)])
        a, b, c, ddw = np.linalg.lstsq(m, x, rcond=None)[0]
        dw += ddw
        if abs(ddw) < 1e-15:
            break
    wi = w + dw
    model = a * np.cos(wi * n) + b * np.sin(wi * n) + c
    resid = x - model
    return SineFit(float(math.hypot(a, b)), float(wi / (2 * np.pi)),
                   float(math.atan2(-b, a)), float(c),
                   float(np.sqrt(np.mean(resid ** 2))))


@dataclass(frozen=True)
class SineMetrics:
    level_dbfs: float
    sinad_db: float
    enob_ieee: float      # against FSR, IEEE 1241
    enob_sinad: float     # (SINAD - 1.76) / 6.02
    snr_db: float
    thd_db: float
    sfdr_db: float
    noise_rms: float      # in the input units


def sine_metrics(x: np.ndarray, cycles: int, fsr: float) -> SineMetrics:
    """All the sine test figures for one coherent record ``x`` (volts)."""
    x = np.asarray(x, float)
    n = len(x)
    fit = sine_fit(x, cycles / n)
    sig_rms = fit.amplitude / math.sqrt(2)
    sinad = 20 * math.log10(sig_rms / fit.residual_rms)
    enob_ieee = math.log2(fsr / (fit.residual_rms * math.sqrt(12)))

    spec = np.abs(np.fft.rfft(x)) ** 2
    spec[1:-1] *= 2           # one sided power
    spec /= n * n
    sig_p = spec[cycles]
    harm_bins = []
    for k in range(2, 10):
        b = (k * cycles) % n
        if b > n // 2:
            b = n - b
        harm_bins.append(b)
    harm_p = sum(spec[b] for b in set(harm_bins))
    mask = np.ones(len(spec), bool)
    mask[0] = False
    mask[cycles] = False
    for b in harm_bins:
        mask[b] = False
    noise_p = spec[mask].sum()
    spurs = spec.copy()
    spurs[0] = 0
    spurs[cycles] = 0
    sfdr = 10 * math.log10(sig_p / spurs.max())
    return SineMetrics(
        level_dbfs=20 * math.log10(2 * fit.amplitude / fsr),
        sinad_db=sinad,
        enob_ieee=enob_ieee,
        enob_sinad=(sinad - 1.76) / 6.02,
        snr_db=10 * math.log10(sig_p / noise_p),
        thd_db=10 * math.log10(harm_p / sig_p),
        sfdr_db=sfdr,
        noise_rms=math.sqrt(noise_p),
    )


@dataclass(frozen=True)
class NoiseFloor:
    rms: float
    peak_to_peak: float
    effective_bits: float     # log2(FSR / rms)
    noise_free_bits: float    # log2(FSR / (6.6 rms))
    mean: float


def noise_floor(x: np.ndarray, fsr: float) -> NoiseFloor:
    x = np.asarray(x, float)
    rms = float(np.std(x))
    return NoiseFloor(rms, float(x.max() - x.min()), math.log2(fsr / rms),
                      math.log2(fsr / (6.6 * rms)), float(np.mean(x)))


@dataclass(frozen=True)
class Linearity:
    inl_best_fit_ppm: np.ndarray
    inl_end_point_ppm: np.ndarray
    max_best_fit_ppm: float
    max_end_point_ppm: float
    slope: float
    intercept: float


def linearity(applied: np.ndarray, measured: np.ndarray, fsr: float) -> Linearity:
    """INL of ``measured`` against ``applied`` (both volts), ppm of FSR."""
    a = np.asarray(applied, float)
    m = np.asarray(measured, float)
    slope, intercept = np.polyfit(a, m, 1)
    bf = (m - (slope * a + intercept)) / fsr * 1e6
    s_ep = (m[-1] - m[0]) / (a[-1] - a[0])
    ep = (m - (m[0] + s_ep * (a - a[0]))) / fsr * 1e6
    return Linearity(bf, ep, float(np.max(np.abs(bf))), float(np.max(np.abs(ep))),
                     float(slope), float(intercept))
