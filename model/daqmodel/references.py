"""Simulated reference instruments: a calibrator and a reference DMM.

The brief's test gear is a precision source and a reference DMM. Neither is
available, so both are simulated with stated, assumed accuracies of the
class a calibration lab would use. Each instrument's error is drawn once with
a fixed seed and then held, which is how a real instrument behaves between
its own calibrations: the error is unknown but systematic.

Because this is a simulation, the true input voltage is known as well, so
the validation report can show the DAQ's error against both the DMM (what a
bench test would see) and the truth (what a bench test never can).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Calibrator:
    """A DC voltage source. Its output is ``nominal * (1 + gain_error)``."""

    #: Assumed accuracy, fraction of setting (uniform within +/- this).
    accuracy: float = 2e-6
    gain_error: float = 0.0

    def output(self, nominal_v: float) -> float:
        return nominal_v * (1.0 + self.gain_error)


@dataclass(frozen=True)
class ReferenceDmm:
    """A DMM reading ``true * (1 + gain_error) + offset_error``."""

    #: Assumed accuracy: ppm of reading plus a fixed offset in volts.
    reading_accuracy: float = 3e-6
    offset_accuracy: float = 0.2e-6
    gain_error: float = 0.0
    offset_error: float = 0.0

    def read(self, true_v: float) -> float:
        return true_v * (1.0 + self.gain_error) + self.offset_error


def instruments(seed: int = 7) -> tuple[Calibrator, ReferenceDmm]:
    rng = np.random.default_rng(seed)
    cal = Calibrator()
    cal = Calibrator(cal.accuracy, cal.accuracy * (2 * rng.random() - 1))
    dmm = ReferenceDmm()
    dmm = ReferenceDmm(dmm.reading_accuracy, dmm.offset_accuracy,
                       dmm.reading_accuracy * (2 * rng.random() - 1),
                       dmm.offset_accuracy * (2 * rng.random() - 1))
    return cal, dmm
