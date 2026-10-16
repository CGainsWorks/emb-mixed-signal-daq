"""Behavioural model of the 24-bit sigma-delta converter and its front end.

What it models
--------------
* A 1-bit, 4th order modulator running at f_mod, realised in error feedback
  form directly from its noise transfer function (NTF). The NTF has all four
  zeros at DC and Butterworth poles placed so that its out of band gain is
  1.5 (the Lee criterion), which keeps the loop stable for inputs up to about
  0.6 of the feedback level. Overload is detected and the loop is reset, as
  real parts do.
* A sinc4 decimation filter and truncation to a 24-bit two's complement word.
* Front end and converter thermal noise, white, at the density the noise
  budget calculates (passed in, never invented here).
* Reference noise, which multiplies the signal because the conversion is
  ratiometric.
* Static non-linearity, offset and gain error of a simulated board instance,
  drawn from stated tolerances with a fixed seed.

What it does not model
----------------------
Circuit level effects inside the modulator (integrator leakage, finite
amplifier gain, capacitor mismatch, sampling kickback), 1/f noise,
temperature drift, settling after a gain change and anything layout
dependent. Every result produced with it is a simulation and is labelled so.

Reproducibility
---------------
The Gaussian noise is built from a sum of twelve uniform draws added with
plain element wise arithmetic, so it involves no transcendental functions and
no reduction whose order depends on the CPU. The modulator loop is plain
Python float arithmetic, the decimator is exact integer arithmetic and the
sine test signal is a Taylor series rather than a library ``sin``, because a
last bit difference anywhere upstream of the 1-bit quantiser can flip a
decision and change every sample after it. The FFT and least squares fits in
the analysis can still differ in the last bit between numpy builds, which is
why CI compares the committed results to a tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from .spec import GAINS, SPEC, Converter


# ---------------------------------------------------------------- the loop

def design_ntf(order: int = 4, obg: float = 1.5):
    """NTF(z) = B(z)/A(z) with all zeros at DC and peak gain ``obg``.

    A Butterworth high pass of the given order is normalised so its leading
    numerator coefficient is 1 (the NTF of a realisable loop must have
    NTF(inf) = 1). Its gain at Nyquist is then 1 / b0 and the cut-off is
    found by bisection so that this equals ``obg``.
    """
    lo, hi = 1e-4, 0.99
    for _ in range(80):
        wc = 0.5 * (lo + hi)
        b, _ = signal.butter(order, wc, "high")
        if 1.0 / b[0] > obg:
            hi = wc
        else:
            lo = wc
    b, a = signal.butter(order, 0.5 * (lo + hi), "high")
    # Rounded to twelve significant figures so that a last bit difference in
    # a future scipy cannot change the loop. The NTF moves by about 1e-12.
    b = np.array([float(f"{v:.12g}") for v in b / b[0]])
    a = np.array([float(f"{v:.12g}") for v in a])
    return b, a


@dataclass
class ModulatorResult:
    bits: np.ndarray        # +1 / -1, int8
    overloads: int          # number of loop resets
    peak_state: float       # largest quantiser input seen


def modulate(u: np.ndarray, conv: Converter = SPEC.converter,
             overload_level: float = 8.0) -> ModulatorResult:
    """Run the modulator over ``u`` (in units of the feedback level)."""
    b, a = design_ntf(conv.modulator_order, conv.ntf_out_of_band_gain)
    order = len(b) - 1
    # v[n] = u[n] + f[n], f = ((B - A) / A) e, e = y - v.
    c = [float(b[k] - a[k]) for k in range(1, order + 1)]
    d = [float(a[k]) for k in range(1, order + 1)]
    e_hist = [0.0] * order
    f_hist = [0.0] * order
    out = np.empty(len(u), dtype=np.int8)
    overloads = 0
    peak = 0.0
    for i, ui in enumerate(u.tolist()):
        f = 0.0
        for k in range(order):
            f += c[k] * e_hist[k] - d[k] * f_hist[k]
        v = ui + f
        y = 1.0 if v >= 0.0 else -1.0
        if v > peak or -v > peak:
            peak = abs(v)
        if v > overload_level or v < -overload_level:
            overloads += 1
            e_hist = [0.0] * order
            f_hist = [0.0] * order
        else:
            e_hist.pop()
            e_hist.insert(0, y - v)
            f_hist.pop()
            f_hist.insert(0, f)
        out[i] = int(y)
    return ModulatorResult(out, overloads, peak)


def decimate(bits: np.ndarray, conv: Converter = SPEC.converter,
             osr: int | None = None) -> np.ndarray:
    """Sinc^N decimation in exact integer arithmetic, then scale to +/-1.

    A cascade of N integrators at the modulator rate and N combs at the
    output rate (the Hogenauer structure a real decimator uses). Python
    integers cannot overflow, so the result is exact and identical on every
    platform. The first ``sinc_order`` outputs are the filter filling and are
    dropped.
    """
    osr = osr or conv.osr
    n = conv.sinc_order
    x = bits.astype(np.int64)
    for _ in range(n):
        x = np.cumsum(x, dtype=np.int64)
    x = x[osr - 1::osr]
    for _ in range(n):
        x = np.diff(x, prepend=np.int64(0))
    gain = osr ** n
    return x[n:].astype(np.float64) / gain


def to_code(y: np.ndarray, conv: Converter = SPEC.converter) -> np.ndarray:
    """Decimated modulator level to a 24-bit two's complement code.

    A level equal to ``full_scale_level`` is +Vref, which is code 2^23 - 1
    after clamping. Truncation toward minus infinity, as a hardware
    decimator does when it drops low order bits.
    """
    half = 2 ** (conv.bits - 1)
    codes = np.floor(y / conv.full_scale_level * half)
    return np.clip(codes, -half, half - 1).astype(np.int64)


# ---------------------------------------------------------------- noise

def gaussian(rng: np.random.Generator, n: int) -> np.ndarray:
    """Unit variance noise without transcendental functions (Irwin-Hall)."""
    u = rng.random((12, n))
    s = u[0].copy()
    for k in range(1, 12):
        s = s + u[k]
    return s - 6.0


# ---------------------------------------------------------------- a board

@dataclass(frozen=True)
class Board:
    """One simulated board: the non-idealities a real unit would have.

    Each field is a draw from a stated tolerance, made once with a fixed seed
    by :func:`simulated_board`. None of them is a measurement.
    """

    gain_actual: dict          # nominal -> actual front end gain
    offset_v: float            # input referred offset of the gain stage, V
    adc_offset_v: float        # converter offset at its input, V
    vref_actual: float         # the reference's true value, V
    inl_c2: float              # bow, fraction of FSR at mid scale
    inl_c3: float              # S shape, fraction of FSR
    noise_density_out: dict = field(default_factory=dict)  # gain -> V/rtHz at the pins
    ref_density: float = 0.0   # V/rtHz


def simulated_board(seed: int = 20261016) -> Board:
    """Draw a board from the tolerances in the bill of materials.

    Resistors 0.1 %, amplifier offset within +/-15 uV (zero drift class),
    converter offset within +/-40 uV, reference initial accuracy 0.05 %.
    The static non-linearity is an assumption of about 2 ppm of FSR, of the
    order a good 24-bit converter specifies; it exists so the linearity
    measurement has something real to find.
    """
    from .frontend import FRONT_END
    from .noise_budget import lines

    rng = np.random.default_rng(seed)

    def tol(nominal, frac):
        return nominal * (1.0 + frac * (2.0 * rng.random() - 1.0))

    fe = FRONT_END
    gains = {}
    rf_p = tol(fe.r_f, 1e-3)
    rf_n = tol(fe.r_f, 1e-3)
    for g in GAINS:
        rg = fe.r_g[g]
        gains[g] = 1.0 if rg is None else 1.0 + (rf_p + rf_n) / tol(rg, 1e-3)

    dens = {}
    for g in GAINS:
        psd = sum(float(line.psd_fn(np.array([10.0]))[0]) for line in lines(g))
        dens[g] = math.sqrt(psd)

    return Board(
        gain_actual=gains,
        offset_v=15e-6 * (2 * rng.random() - 1),
        adc_offset_v=40e-6 * (2 * rng.random() - 1),
        vref_actual=tol(SPEC.converter.vref, 5e-4),
        inl_c2=1.0e-6,
        inl_c3=2.0e-6,
        noise_density_out=dens,
        ref_density=fe.en_ref,
    )


@dataclass
class Capture:
    codes: np.ndarray
    odr: float
    gain: int
    overloads: int
    peak_state: float


def convert(vin: np.ndarray | float, n_out: int, gain: int, board: Board,
            conv: Converter = SPEC.converter, seed: int = 1,
            noise: bool = True, osr: int | None = None) -> Capture:
    """Convert a differential input signal and return 24-bit codes.

    ``vin`` is either a constant (volts) or an array at the modulator rate
    whose length is at least ``(n_out + sinc_order) * osr``.
    """
    osr = osr or conv.osr
    n_mod = (n_out + conv.sinc_order) * osr
    rng = np.random.default_rng(seed)
    if np.isscalar(vin):
        v = np.full(n_mod, float(vin))
    else:
        v = np.asarray(vin, float)[:n_mod]

    # Front end: offset, gain, then the noise the budget says arrives at the
    # converter pins (white at the low frequency density; the shaping above
    # 10 kHz changes the decimated total by well under one percent, which
    # the budget reports as the white estimate).
    g = board.gain_actual[gain]
    x = (v + board.offset_v) * g + board.adc_offset_v
    if noise:
        sigma = board.noise_density_out[gain] * math.sqrt(conv.f_mod / 2)
        x = x + sigma * gaussian(rng, n_mod)

    # Ratiometric conversion against a noisy reference.
    vref = board.vref_actual
    if noise:
        sigma_r = board.ref_density * math.sqrt(conv.f_mod / 2)
        vref_t = vref + sigma_r * gaussian(rng, n_mod)
    else:
        vref_t = vref
    r = x / vref_t                     # -1 .. +1 at full scale

    # Static non-linearity, defined on the normalised input so that it is
    # zero at both ends of the range (an end point INL shape).
    r = r + 2 * (board.inl_c2 * (r * r - 1.0) + board.inl_c3 * (r * r * r - r))

    u = r * conv.full_scale_level
    res = modulate(u, conv)
    y = decimate(res.bits, conv, osr)[:n_out]
    return Capture(to_code(y, conv), conv.f_mod / osr, gain,
                   res.overloads, res.peak_state)


def coherent_sine(n_out: int, cycles: int, amplitude: float,
                  conv: Converter = SPEC.converter, osr: int | None = None,
                  phase: float = 0.3) -> tuple[np.ndarray, float]:
    """A sine at the modulator rate with an integer number of cycles in the
    ``n_out`` sample record the decimator will produce (coherent sampling,
    as IEEE 1241 recommends, so no window is needed)."""
    osr = osr or conv.osr
    n_mod = (n_out + conv.sinc_order) * osr
    period = n_out * osr                    # modulator samples per record
    f = cycles * conv.f_mod / period
    # Phase in cycles, reduced exactly in integers, so it is the same double
    # on every platform. Time is aligned so the first retained output sample
    # sees ``phase``, whatever the filter length.
    k = np.arange(n_mod, dtype=np.int64) - conv.sinc_order * osr
    cyc = ((k * cycles) % period).astype(np.float64) / period
    cyc = cyc + phase / (2 * math.pi)
    return amplitude * det_sin_cycles(cyc), f


def det_sin_cycles(c: np.ndarray) -> np.ndarray:
    """sin(2 pi c) from additions and multiplications only.

    Library sine functions differ in the last bit between platforms and
    between SIMD paths and a last bit difference in the modulator input can
    flip a 1-bit decision. Reducing to [-1/4, 1/4] of a cycle and summing the
    Taylor series to x^23 (truncation error below 1e-17) gives the same
    double everywhere.
    """
    c = np.asarray(c, float)
    c = c - np.floor(c + 0.5)              # [-1/2, 1/2)
    c = np.where(c > 0.25, 0.5 - c, c)
    c = np.where(c < -0.25, -0.5 - c, c)   # [-1/4, 1/4]
    x = c * (2 * math.pi)
    x2 = x * x
    term = x.copy()
    total = x.copy()
    for k in range(1, 12):
        term = term * x2 * (-1.0 / ((2 * k) * (2 * k + 1)))
        total = total + term
    return total
