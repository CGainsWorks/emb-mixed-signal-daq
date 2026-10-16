"""The committed simulation results are consistent with each other.

These read the generated files rather than rerunning the campaign, so they
are fast. CI regenerates the files first and checks they match what is
committed, so these always see current results.
"""

import csv
import json

import pytest

from conftest import ROOT
from daqmodel.spec import SPEC


def rows(rel):
    with open(ROOT / rel, encoding="utf-8") as h:
        return list(csv.DictReader(h))


def test_simulated_noise_agrees_with_the_budget():
    for r in rows("test-results/noise-floor/noise_floor.csv"):
        ratio = float(r["simulated_uV_rms"]) / float(r["budget_uV_rms"])
        # Statistical spread of a 2048 sample record, plus the budget's
        # conservative linear model of the 1-bit quantiser at gain 1.
        assert 0.85 < ratio < 1.15, r
        assert int(r["overloads"]) == 0


def test_sine_snr_agrees_with_the_budget_prediction():
    for r in rows("test-results/enob-snr/sine.csv"):
        assert abs(float(r["snr_dB"]) - float(r["budget_snr_dB"])) < 1.5, r


def test_linearity_sweep_recovers_the_injected_inl():
    inl = [abs(float(r["inl_best_fit_ppm_fsr"])) for r in rows("test-results/linearity/inl.csv")]
    report = (ROOT / "docs/validation_report.md").read_text(encoding="utf-8")
    given = float(report.split("Non-linearity the model was given, best fit | ")[1].split()[0])
    assert max(inl) == pytest.approx(given, abs=0.2)


def test_calibration_meets_target_everywhere():
    for r in rows("test-results/calibration/validation.csv"):
        assert abs(float(r["cal_error_vs_dmm_ppm_fsr"])) <= SPEC.calibrated_error_target_ppm_fsr
        assert abs(float(r["cal_error_vs_true_ppm_fsr"])) <= SPEC.calibrated_error_target_ppm_fsr


def test_headline_matches_the_readme():
    h = json.loads((ROOT / "test-results/headline.json").read_text())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert h["simulated"] is True
    assert f"{h['snr_dB_g1']:.1f} dB" in readme
    assert f"{h['enob_bits_g1']:.2f} bits" in readme
    assert f"{h['noise_uV_rms']['1']:.3f} uV rms" in readme
