"""The simulated test campaign: what a bench validation would run.

Each function here corresponds to one section of the validation report and
one folder of ``test-results``. The measurements themselves are made by the
host tools in ``host-tools/daqhost``, which do not know the data is simulated.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import noise_budget as nb
from .references import instruments
from .sigma_delta import Board, coherent_sine, convert, simulated_board
from .spec import GAINS, SPEC

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "host-tools"))
from daqhost import calibration as cal  # noqa: E402
from daqhost import metrics  # noqa: E402

CONV = SPEC.converter
VREF_NV = int(round(CONV.vref * 1e9))


def code_to_volts(codes, gain: int) -> np.ndarray:
    """Uncalibrated conversion, nominal reference and nominal gain."""
    return np.asarray(codes, float) * CONV.lsb / gain


def full_scale_nv(gain: int) -> int:
    fs, rem = divmod(VREF_NV, gain)
    assert rem == 0, "nominal full scale must be a whole number of nanovolts"
    return fs


# ---------------------------------------------------------------- noise

@dataclass
class NoiseResult:
    gain: int
    floor: metrics.NoiseFloor        # input referred volts
    budget_vrms: float
    target_vrms: float
    overloads: int
    codes: np.ndarray


def noise_floor(gain: int, board: Board, n: int = 2048, seed: int = 11) -> NoiseResult:
    cap = convert(0.0, n, gain, board, seed=seed + gain)
    v = code_to_volts(cap.codes, gain)
    b = nb.budget(gain)
    return NoiseResult(gain, metrics.noise_floor(v, SPEC.fsr(gain)),
                       b.total_in_vrms, b.target_vrms, cap.overloads, cap.codes)


# ---------------------------------------------------------------- sine

@dataclass
class SineResult:
    gain: int
    cycles: int
    n: int
    f_hz: float
    m: metrics.SineMetrics
    predicted_snr_db: float
    volts: np.ndarray
    codes: np.ndarray


def sine_test(gain: int, board: Board, n: int = 4096, cycles: int = 67,
              level_dbfs: float = -1.0, seed: int = 23) -> SineResult:
    amp = SPEC.full_scale(gain) * 10 ** (level_dbfs / 20)
    v_in, f = coherent_sine(n, cycles, amp)
    cap = convert(v_in, n, gain, board, seed=seed + gain)
    v = code_to_volts(cap.codes, gain)
    m = metrics.sine_metrics(v, cycles, SPEC.fsr(gain))
    return SineResult(gain, cycles, n, f, m, nb.predicted_snr_db(gain, level_dbfs),
                      v, cap.codes)


# ---------------------------------------------------------------- linearity

@dataclass
class LinearityResult:
    gain: int
    applied: np.ndarray
    measured: np.ndarray
    lin: metrics.Linearity
    injected_max_ppm: float


def injected_inl_ppm(board: Board, r: np.ndarray) -> np.ndarray:
    """The non-linearity the model was given, best fit line removed."""
    dev = 2 * (board.inl_c2 * (r * r - 1) + board.inl_c3 * (r ** 3 - r))
    slope, icpt = np.polyfit(r, dev, 1)
    return (dev - (slope * r + icpt)) / 2 * 1e6


def linearity_sweep(gain: int, board: Board, points: int = 41, avg: int = 32,
                    seed: int = 31) -> LinearityResult:
    fs = SPEC.full_scale(gain)
    applied = np.linspace(-0.95 * fs, 0.95 * fs, points)
    measured = []
    for k, va in enumerate(applied):
        cap = convert(float(va), avg, gain, board, seed=seed + 1000 * gain + k)
        measured.append(float(np.mean(code_to_volts(cap.codes, gain))))
    measured = np.array(measured)
    lin = metrics.linearity(applied, measured, SPEC.fsr(gain))
    r = (applied + board.offset_v) * board.gain_actual[gain] / board.vref_actual
    return LinearityResult(gain, applied, measured, lin,
                           float(np.max(np.abs(injected_inl_ppm(board, r)))))


# ---------------------------------------------------------------- calibration

@dataclass
class CalPoint:
    nominal_v: float
    true_v: float
    dmm_v: float
    raw_v: float          # uncalibrated reading
    cal_v: float          # calibrated reading


@dataclass
class CalibrationResult:
    gain: int
    coeffs: cal.Coefficients
    vcal_nv: int
    zero_codes: np.ndarray
    cal_codes: np.ndarray
    points: list
    worst_raw_ppm: float
    worst_cal_vs_dmm_ppm: float
    worst_cal_vs_true_ppm: float
    vectors: list            # (code, expected calibrated output) for C tests


def calibrate_and_validate(gain: int, board: Board, avg_cal: int = 64,
                           avg_val: int = 32, seed: int = 41) -> CalibrationResult:
    calibrator, dmm = instruments()
    fs = SPEC.full_scale(gain)
    fs_nv = full_scale_nv(gain)

    # Step 1: input shorted at the connector, so the front end offset is
    # included in what is removed.
    zero = convert(0.0, avg_cal, gain, board, seed=seed + 10 * gain).codes
    # Step 2: the calibrator set to 0.9 of full scale. The firmware is told
    # the calibrator's nominal setting; its real output differs by the
    # calibrator's own error, which therefore ends up in the result.
    vcal_nv = round(0.9 * fs * 1e9)
    v_true = calibrator.output(vcal_nv * 1e-9)
    span = convert(v_true, avg_cal, gain, board, seed=seed + 10 * gain + 1).codes
    coeffs = cal.compute(zero, span, vcal_nv, fs_nv)

    points = []
    fsr = SPEC.fsr(gain)
    for k, frac in enumerate(np.linspace(-0.9, 0.9, 11)):
        nominal = float(frac * fs)
        true_v = calibrator.output(nominal)
        dmm_v = dmm.read(true_v)
        codes = convert(true_v, avg_val, gain, board,
                        seed=seed + 100 * gain + k).codes
        raw_v = float(np.mean(code_to_volts(codes, gain)))
        cal_v = float(np.mean([cal.to_volts(cal.apply(c, coeffs), fs)
                               for c in codes]))
        points.append(CalPoint(nominal, true_v, dmm_v, raw_v, cal_v))

    def worst(attr_a, attr_b):
        return max(abs(getattr(p, attr_a) - getattr(p, attr_b)) / fsr * 1e6
                   for p in points)

    vectors = [(int(c), cal.apply(int(c), coeffs)) for c in
               list(zero[:4]) + list(span[:4]) +
               [-(2 ** 23), 2 ** 23 - 1, 0, 1, -1]]
    return CalibrationResult(gain, coeffs, vcal_nv, zero, span, points,
                             worst("raw_v", "true_v"), worst("cal_v", "dmm_v"),
                             worst("cal_v", "true_v"), vectors)


def board() -> Board:
    return simulated_board()


def fsr_bits(gain: int, vrms: float) -> float:
    return math.log2(SPEC.fsr(gain) / vrms)


__all__ = ["GAINS", "board", "noise_floor", "sine_test", "linearity_sweep",
           "calibrate_and_validate", "code_to_volts", "full_scale_nv", "fsr_bits"]
