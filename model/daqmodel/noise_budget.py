"""The noise budget, calculated by hand before any simulation.

Every contributor is written out as its own closed form transfer function
from the noise source to the converter pins. Nothing here reads the netlist
or calls a circuit solver, which is what makes the ngspice cross-check in
``scripts/run_ngspice.py`` worth having: two independent routes to the same
number.

Transfer functions used
-----------------------
Input EMI filter, differential mode. Each leg is R_leg = R_src + R_prot into
C_cm to ground with C_diff across the pair. In differential mode the far end
of C_diff moves the other way, so it counts twice::

    H_in(f) = 1 / (1 + j 2 pi f R_leg (C_cm + 2 C_diff))

A noise voltage in series with one leg reaches the differential node through
H_in; an amplifier current noise into one input node sees R_leg H_in.

Gain stage, ideal amplifiers. A voltage at either non-inverting input appears
at the output multiplied by G = 1 + 2 R_f / R_G. Thermal noise of R_G appears
multiplied by G - 1 and each R_f adds its own noise with unity gain.

Anti-alias filter: the same shape as the input filter with R_aa, C_aa_cm and
C_aa_diff and the two R_aa add their noise through it.

Omitted, in both this budget and the SPICE deck: current noise at the
inverting inputs (it flows in R_f, about 0.75 nV/rtHz at the allowance, under
one percent of the total in power at every gain) and every 1/f term (the gain
stage is specified as zero drift).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .frontend import FRONT_END, FrontEnd
from .spec import K_BOLTZMANN, SPEC, TEMPERATURE_K, Converter, Spec

FOUR_KT = 4 * K_BOLTZMANN * TEMPERATURE_K


# ---------------------------------------------------------------- filters

def rc_diff(f, r_leg, c_cm, c_diff):
    """Differential mode response of a symmetric RC filter."""
    return 1.0 / (1.0 + 2j * np.pi * np.asarray(f, float) * r_leg * (c_cm + 2 * c_diff))


def sinc_magnitude(f, conv: Converter = SPEC.converter, osr: int | None = None):
    """|H(f)| of the sinc^N decimator, normalised to 1 at DC.

    Periodic in the modulator clock, which is the point: noise near f_mod
    folds straight back to DC and only the analogue filter stops it.
    """
    osr = osr or conv.osr
    x = np.pi * np.asarray(f, float) / conv.f_mod
    num = np.sin(osr * x)
    den = osr * np.sin(x)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(np.abs(den) < 1e-300, 1.0, num / den)
    return np.abs(r) ** conv.sinc_order


def sinc_taps(conv: Converter = SPEC.converter, osr: int | None = None) -> np.ndarray:
    """Impulse response of the decimator at the modulator rate, unit DC gain."""
    osr = osr or conv.osr
    h = np.ones(osr)
    for _ in range(conv.sinc_order - 1):
        h = np.convolve(h, np.ones(osr))
    return h / h.sum()


def enbw(conv: Converter = SPEC.converter, osr: int | None = None) -> float:
    """Equivalent noise bandwidth of the decimator, one sided, Hz.

    Exact by Parseval: white noise of density e at the modulator rate has
    variance e^2 f_mod / 2 per sample and the filter scales it by sum(h^2).
    """
    h = sinc_taps(conv, osr)
    return float(conv.f_mod / 2 * np.sum(h * h))


def droop_db(f, conv: Converter = SPEC.converter) -> float:
    return float(20 * np.log10(sinc_magnitude(f, conv)))


# ---------------------------------------------------------------- budget

@dataclass(frozen=True)
class Line:
    """One row of the budget."""

    name: str
    block: str
    in_deck: bool           # also present in the ngspice deck
    psd_fn: object          # f -> V^2/Hz at the converter pins


def lines(gain: int, fe: FrontEnd = FRONT_END, spec: Spec = SPEC) -> list[Line]:
    """Every noise contributor at one gain setting, output referred."""
    g = fe.gain(gain)
    rg = fe.r_g[gain]

    def h_in(f):
        return rc_diff(f, fe.r_leg, fe.c_cm, fe.c_diff)

    def h_aa(f):
        return rc_diff(f, fe.r_aa, fe.c_aa_cm, fe.c_aa_diff)

    def front(f):
        return np.abs(g * h_in(f) * h_aa(f)) ** 2

    def after_gain(f):
        return np.abs(h_aa(f)) ** 2

    out = [
        Line("Sensor resistance, 2 x %g ohm" % fe.r_src, "source", True,
             lambda f: FOUR_KT * 2 * fe.r_src * front(f)),
        Line("Protection resistors, 2 x %g ohm" % fe.r_prot, "input filter", True,
             lambda f: FOUR_KT * 2 * fe.r_prot * front(f)),
        Line("Amplifier voltage noise, 2 x %g nV/rtHz" % (fe.en_amp * 1e9),
             "gain stage", True,
             lambda f: 2 * fe.en_amp ** 2 * g ** 2 * after_gain(f)),
        Line("Amplifier current noise, 2 x %g pA/rtHz in R_leg" % (fe.in_amp * 1e12),
             "gain stage", True,
             lambda f: 2 * (fe.in_amp * fe.r_leg) ** 2 * front(f)),
        Line("Feedback resistors R_f, 2 x %g ohm" % fe.r_f, "gain stage", True,
             lambda f: FOUR_KT * 2 * fe.r_f * after_gain(f)),
    ]
    if rg is not None:
        out.append(Line("Gain resistor R_G, %g ohm" % rg, "gain stage", True,
                        lambda f: FOUR_KT * rg * (g - 1) ** 2 * after_gain(f)))
    out += [
        Line("Anti-alias resistors, 2 x %g ohm" % fe.r_aa, "anti-alias filter", True,
             lambda f: FOUR_KT * 2 * fe.r_aa * after_gain(f)),
        Line("Converter input noise, %g nV/rtHz" % (fe.en_adc * 1e9), "converter", False,
             lambda f: fe.en_adc ** 2 * np.ones_like(np.asarray(f, float))),
    ]
    return out


def analogue_psd(gain: int, f, fe: FrontEnd = FRONT_END) -> np.ndarray:
    """Sum of the contributors that the ngspice deck also contains."""
    f = np.asarray(f, float)
    return sum(line.psd_fn(f) for line in lines(gain, fe) if line.in_deck)


def integration_grid(conv: Converter = SPEC.converter, images: int = 4) -> np.ndarray:
    """Frequencies for integrating against the periodic sinc response.

    Linear, fine enough to resolve every sinc lobe and running to several
    multiples of the modulator clock so the noise that folds back from
    around f_mod is counted rather than assumed away.
    """
    step = conv.odr / 64
    return np.arange(step / 2, images * conv.f_mod, step)


def integrate(psd, f, conv: Converter = SPEC.converter) -> float:
    """Variance of the decimated output for a noise of density ``psd``."""
    w = sinc_magnitude(f, conv) ** 2
    return float(np.trapezoid(psd * w, f)) if hasattr(np, "trapezoid") \
        else float(np.trapz(psd * w, f))


def quantisation_noise_vrms(conv: Converter = SPEC.converter) -> float:
    """Linear model estimate of the modulator's in band quantisation noise.

    Treats the 1-bit quantiser error as white with variance Delta^2 / 12,
    Delta = 2, shaped by the NTF and filtered by the decimator. A 1-bit loop
    is not linear, so this is an estimate; ``test-results/noise-floor``
    reports what the behavioural modulator actually produces.
    """
    from .sigma_delta import design_ntf
    b, a = design_ntf(conv.modulator_order, conv.ntf_out_of_band_gain)
    f = np.linspace(0.5, conv.f_mod / 2, 400_001)
    z = np.exp(2j * np.pi * f / conv.f_mod)
    ntf = np.polyval(b, z) / np.polyval(a, z)
    psd = (4.0 / 12.0) / (conv.f_mod / 2) * np.abs(ntf) ** 2
    var = integrate(psd, f, conv)
    scale = conv.vref / conv.full_scale_level   # volts per unit modulator level
    return math.sqrt(var) * scale


@dataclass(frozen=True)
class GainBudget:
    gain_nominal: int
    gain_actual: float
    rows: list            # (name, block, in_deck, density_in_nV, rms_in_nV, share)
    total_in_vrms: float
    white_estimate_in_vrms: float
    deck_only_in_vrms: float
    quantisation_in_vrms: float
    reference_at_fs_in_vrms: float
    folded_share: float   # fraction of noise power from above f_mod / 2
    target_vrms: float

    @property
    def margin_db(self) -> float:
        return 20 * math.log10(self.target_vrms / self.total_in_vrms)


def budget(gain: int, fe: FrontEnd = FRONT_END, spec: Spec = SPEC) -> GainBudget:
    conv = spec.converter
    g = fe.gain(gain)
    f = integration_grid(conv)
    rows = []
    var_total = 0.0
    var_deck = 0.0
    var_low = 0.0
    for line in lines(gain, fe, spec):
        psd = line.psd_fn(f)
        below = f < conv.f_mod / 2
        low = integrate(psd[below], f[below], conv)
        # Analogue noise is sampled by the modulator, so everything above
        # f_mod / 2 folds back. The converter's own noise is defined in band
        # and is not sampled again.
        var = low if line.block == "converter" else integrate(psd, f, conv)
        var_total += var
        var_low += low
        if line.in_deck:
            var_deck += var
        dens = math.sqrt(float(line.psd_fn(np.array([10.0]))[0])) / g
        rows.append([line.name, line.block, line.in_deck, dens * 1e9,
                     math.sqrt(var) / g * 1e9, var])

    q = quantisation_noise_vrms(conv) / g
    rows.append(["Modulator quantisation (linear model)", "converter", False,
                 float("nan"), q * 1e9, (q * g) ** 2])
    var_total += (q * g) ** 2

    for r in rows:
        r[5] = r[5] / var_total
    total = math.sqrt(var_total) / g

    dens_total = math.sqrt(sum(float(line.psd_fn(np.array([10.0]))[0])
                               for line in lines(gain, fe, spec)))
    white = math.sqrt(dens_total ** 2 * enbw(conv) + (q * g) ** 2) / g

    # Reference noise multiplies the signal. For a full scale sine its rms
    # contribution is e_ref sqrt(ENBW) times (signal rms / Vref) = 1/sqrt(2),
    # referred to the input by the same ratio.
    ref = fe.en_ref * math.sqrt(enbw(conv)) / math.sqrt(2) / g

    folded = 1.0 - (var_low + (q * g) ** 2) / var_total
    return GainBudget(gain, g, [tuple(r) for r in rows], total, white,
                      math.sqrt(var_deck) / g, q, ref, folded,
                      spec.noise_target_vrms[gain])


def predicted_snr_db(gain: int = 1, level_dbfs: float = -1.0,
                     fe: FrontEnd = FRONT_END, spec: Spec = SPEC) -> float:
    """SNR the budget predicts for a sine at ``level_dbfs``.

    The reference term scales with signal amplitude, so it is applied at the
    test level rather than at full scale.
    """
    b = budget(gain, fe, spec)
    amp = spec.full_scale(gain) * 10 ** (level_dbfs / 20)
    sig_rms = amp / math.sqrt(2)
    ref = b.reference_at_fs_in_vrms * 10 ** (level_dbfs / 20)
    noise = math.hypot(b.total_in_vrms, ref)
    return 20 * math.log10(sig_rms / noise)


def enob_from_snr(snr_db: float) -> float:
    return (snr_db - 1.76) / 6.02


def alias_rejection_db(fe: FrontEnd = FRONT_END, spec: Spec = SPEC) -> float:
    """Analogue attenuation at the first image band, f_mod - bandwidth."""
    f = spec.converter.f_mod - spec.bandwidth_hz
    h = rc_diff(f, fe.r_leg, fe.c_cm, fe.c_diff) * rc_diff(f, fe.r_aa, fe.c_aa_cm, fe.c_aa_diff)
    return float(-20 * np.log10(np.abs(h)))
