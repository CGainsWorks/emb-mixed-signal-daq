"""The noise budget against hand calculations and the specification."""

import math

import numpy as np
import pytest

from daqmodel import noise_budget as nb
from daqmodel.frontend import FRONT_END, netlist
from daqmodel.spec import GAINS, K_BOLTZMANN, SPEC, TEMPERATURE_K


def test_thermal_noise_of_1k_at_27_degC():
    # The textbook figure: 4.07 nV/rtHz.
    assert math.sqrt(4 * K_BOLTZMANN * TEMPERATURE_K * 1e3) == pytest.approx(4.07e-9, rel=1e-3)


def test_enbw_matches_the_sinc4_closed_form():
    # For sinc^N with large OSR the ENBW tends to (ODR / 2) times the integral
    # of the squared order N B-spline, 151/315 for N = 4.
    assert nb.enbw() == pytest.approx(SPEC.converter.odr / 2 * 151 / 315, rel=1e-3)


def test_sinc_is_unity_at_dc_and_nulls_at_odr_multiples():
    odr = SPEC.converter.odr
    assert nb.sinc_magnitude([1e-6])[0] == pytest.approx(1.0)
    assert np.all(nb.sinc_magnitude([odr, 2 * odr, 5 * odr]) < 1e-12)
    # and comes back to 1 at the modulator clock, which is why the analogue
    # filter has to provide the alias rejection
    assert nb.sinc_magnitude([SPEC.converter.f_mod])[0] == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("gain", GAINS)
def test_budget_meets_targets(gain):
    b = nb.budget(gain)
    assert b.total_in_vrms < b.target_vrms
    assert sum(r[5] for r in b.rows) == pytest.approx(1.0)
    assert abs(b.white_estimate_in_vrms / b.total_in_vrms - 1) < 0.02
    assert b.folded_share < 0.01


def test_amplifier_line_is_the_hand_figure():
    # Two amplifiers of e_n each, referred to the input: sqrt(2) e_n.
    b = nb.budget(128)
    row = next(r for r in b.rows if r[0].startswith("Amplifier voltage"))
    assert row[3] == pytest.approx(math.sqrt(2) * FRONT_END.en_amp * 1e9, rel=1e-3)


def test_gain_values_come_from_the_e96_resistors():
    assert FRONT_END.gain(1) == 1.0
    assert FRONT_END.gain(8) == pytest.approx(1 + 2 * 2490 / 715)
    for g in GAINS:
        assert abs(FRONT_END.gain(g) / g - 1) < 0.01


def test_filters_meet_the_specification():
    assert nb.alias_rejection_db() >= SPEC.alias_rejection_target_db
    assert -nb.droop_db(SPEC.bandwidth_hz) <= SPEC.max_droop_db


def test_predicted_sine_snr_meets_target():
    assert nb.predicted_snr_db(1) >= SPEC.snr_target_db


def test_netlist_has_a_gain_resistor_except_at_unity():
    assert not any(p.ref == "R7" for p in netlist(1))
    assert any(p.ref == "R7" and p.value == 39.2 for p in netlist(128))
    with pytest.raises(ValueError):
        netlist(2)
