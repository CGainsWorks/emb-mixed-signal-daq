"""The behavioural converter: loop design, stability, decimation, codes."""

import math

import numpy as np
import pytest

from daqmodel import sigma_delta as sd
from daqmodel.spec import SPEC

CONV = SPEC.converter


def test_ntf_has_zeros_at_dc_and_the_chosen_peak_gain():
    b, a = sd.design_ntf(4, 1.5)
    assert b[0] == 1.0
    assert np.allclose(b, [1, -4, 6, -4, 1])
    z = np.exp(1j * np.linspace(0, np.pi, 4001))
    h = np.abs(np.polyval(b, z) / np.polyval(a, z))
    assert h.max() == pytest.approx(1.5, rel=1e-6)
    assert np.all(np.abs(np.roots(a)) < 1)


def test_loop_is_stable_at_the_over_range_limit():
    # Full scale is 0.5 of the feedback level; 20 percent over range is 0.6.
    r = sd.modulate(np.full(100_000, 0.6))
    assert r.overloads == 0
    assert r.bits[1000:].mean() == pytest.approx(0.6, abs=2e-3)


def test_overload_is_detected_and_recovered():
    u = np.concatenate([np.full(20_000, 0.9), np.full(50_000, 0.25)])
    r = sd.modulate(u)
    assert r.overloads > 0
    assert r.bits[40_000:].mean() == pytest.approx(0.25, abs=2e-3)


def test_decimator_is_exact_and_has_unity_dc_gain():
    bits = np.ones(256 * 20, dtype=np.int8)
    y = sd.decimate(bits)
    assert np.all(y == 1.0)
    alt = np.tile(np.array([1, -1], dtype=np.int8), 256 * 10)
    assert np.all(sd.decimate(alt) == 0.0)


def test_codes_clamp_and_scale():
    lvl = CONV.full_scale_level
    c = sd.to_code(np.array([0.0, lvl, -lvl, 2 * lvl, lvl / 2]))
    assert list(c) == [0, 2 ** 23 - 1, -(2 ** 23), 2 ** 23 - 1, 2 ** 22]


def test_gaussian_has_unit_variance():
    x = sd.gaussian(np.random.default_rng(0), 200_000)
    assert x.mean() == pytest.approx(0, abs=0.01)
    assert x.std() == pytest.approx(1, abs=0.01)


def test_deterministic_sine_matches_the_library():
    c = np.linspace(-2, 2, 100_001)
    assert np.max(np.abs(sd.det_sin_cycles(c) - np.sin(2 * np.pi * c))) < 1e-14


def test_noise_free_conversion_is_accurate_to_a_few_codes():
    board = sd.simulated_board()
    v = 1.0
    cap = sd.convert(v, 16, 1, board, noise=False)
    expect = ((v + board.offset_v) * board.gain_actual[1] + board.adc_offset_v) \
        / board.vref_actual * 2 ** 23
    # The INL bow is up to 2 ppm of FSR, about 34 codes at this level.
    assert np.all(np.abs(cap.codes - expect) < 40)


def test_board_draws_are_within_their_tolerances():
    b = sd.simulated_board()
    assert abs(b.offset_v) <= 15e-6 and abs(b.adc_offset_v) <= 40e-6
    assert abs(b.vref_actual / CONV.vref - 1) <= 5e-4
    assert b.gain_actual[1] == 1.0
    assert abs(b.gain_actual[128] / (1 + 2 * 2490 / 39.2) - 1) < 3e-3
    assert math.isclose(sd.simulated_board().offset_v, b.offset_v)
