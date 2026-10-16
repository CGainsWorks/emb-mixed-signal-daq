"""The host analysis against signals whose answers are known."""

import math

import numpy as np
import pytest

from daqhost import metrics


def ideal_quantised_sine(bits, n=8192, cycles=1021, level=0.999):
    k = np.arange(n)
    x = level * np.sin(2 * np.pi * cycles * k / n + 0.1)
    q = 2.0 / 2 ** bits
    return np.round(x / q) * q, cycles


@pytest.mark.parametrize("bits", [12, 16])
def test_ideal_quantiser_gives_its_own_resolution(bits):
    x, cyc = ideal_quantised_sine(bits)
    m = metrics.sine_metrics(x, cyc, fsr=2.0)
    assert m.enob_ieee == pytest.approx(bits, abs=0.05)
    assert m.sinad_db == pytest.approx(6.02 * bits + 1.76, abs=0.4)


def test_harmonic_is_reported_at_its_level():
    n, cyc = 4096, 67
    k = np.arange(n)
    x = np.sin(2 * np.pi * cyc * k / n) + 1e-4 * np.sin(2 * np.pi * 3 * cyc * k / n)
    x += 1e-7 * np.random.default_rng(1).standard_normal(n)
    m = metrics.sine_metrics(x, cyc, fsr=2.0)
    assert m.thd_db == pytest.approx(-80.0, abs=0.01)
    assert m.sfdr_db == pytest.approx(80.0, abs=0.01)
    assert m.snr_db > 130


def test_sine_fit_recovers_an_off_bin_frequency():
    n = 2000
    k = np.arange(n)
    x = 0.7 * np.cos(2 * np.pi * 0.01234 * k + 0.4) + 0.05
    fit = metrics.sine_fit(x, 0.0123)
    assert fit.frequency == pytest.approx(0.01234, rel=1e-9)
    assert fit.amplitude == pytest.approx(0.7, rel=1e-9)
    assert fit.offset == pytest.approx(0.05, abs=1e-9)


def test_noise_floor_of_gaussian_noise():
    x = 1e-6 * np.random.default_rng(2).standard_normal(100_000)
    nf = metrics.noise_floor(x, fsr=5.0)
    assert nf.rms == pytest.approx(1e-6, rel=0.01)
    assert nf.effective_bits == pytest.approx(math.log2(5e6), abs=0.02)
    assert nf.noise_free_bits == pytest.approx(nf.effective_bits - math.log2(6.6), abs=1e-9)


def test_linearity_recovers_a_known_bow():
    a = np.linspace(-1, 1, 41)
    m = 1.001 * a + 0.002 + 4e-6 * (a ** 2 - 1)
    lin = metrics.linearity(a, m, fsr=2.0)
    # A quadratic bow of 4e-6 V on a 2 V range. The best fit line removes the
    # mean of a^2 (1/3 in the continuous limit, 0.35 on 41 points), leaving
    # the peak at the ends; against the end point line the peak is the whole
    # bow, at mid scale.
    peak = (1 - np.mean(a ** 2)) * 4e-6
    assert lin.max_best_fit_ppm == pytest.approx(peak / 2.0 * 1e6, rel=1e-6)
    assert lin.max_end_point_ppm == pytest.approx(4e-6 / 2.0 * 1e6, rel=1e-6)
