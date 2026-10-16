"""Two point calibration, in the same integer arithmetic as the firmware.

This is the reference implementation of ``firmware/src/calibration.c``. The
firmware is tested against vectors this module generates and the firmware
in the loop run checks that every calibrated sample the C code produces is
bit identical to what this produces from the same raw codes.

Representation
--------------
* Raw sample: signed 24-bit converter code.
* Offset: the mean zero input code in Q8 (1/256 of a code), because an
  average of many noisy codes resolves well below one code.
* Gain: Q29 multiplier, about 2^29 for a perfect channel.
* Calibrated sample: signed Q31 fraction of the nominal full scale at the
  selected gain, so +2^31 would be exactly +Vref / G. Converting to volts on
  the host is ``y / 2^31 * Vref / G``.

All divisions round half away from zero, written out explicitly because C
integer division truncates and Python's floors.
"""

from __future__ import annotations

from dataclasses import dataclass

Q_OFFSET = 8
Q_GAIN = 29
Q_OUT = 31
INT32_MIN, INT32_MAX = -(2 ** 31), 2 ** 31 - 1


def round_div(a: int, b: int) -> int:
    """a / b rounded half away from zero, for b > 0."""
    if b <= 0:
        raise ValueError("divisor must be positive")
    if a >= 0:
        return (a + b // 2) // b
    return -((-a + b // 2) // b)


def mean_q8(codes) -> int:
    codes = [int(c) for c in codes]
    if not codes:
        raise ValueError("no samples")
    return round_div(sum(codes) << Q_OFFSET, len(codes))


@dataclass(frozen=True)
class Coefficients:
    offset_q8: int
    gain_q29: int


class CalibrationError(ValueError):
    pass


def compute(zero_codes, cal_codes, vcal_nv: int, full_scale_nv: int) -> Coefficients:
    """Coefficients from a zero input and one reference input.

    ``vcal_nv`` is the value of the calibration reference as the calibrator
    states it, in nanovolts; ``full_scale_nv`` is Vref / G nominal.
    """
    if full_scale_nv <= 0 or vcal_nv <= 0 or vcal_nv > full_scale_nv:
        raise CalibrationError("reference must be positive and within full scale")
    off = mean_q8(zero_codes)
    span = mean_q8(cal_codes) - off
    vcal_q31 = round_div(vcal_nv << Q_OUT, full_scale_nv)
    # On a perfect channel the Q8 code equals the Q31 output (24 + 8 = 32
    # bits), so the expected span is vcal_q31 itself. A span below half or
    # above twice that means the wrong input, the wrong gain or a broken
    # channel; refuse rather than store it.
    expected = vcal_q31
    if span <= 0 or not (expected // 2 < span < expected * 2):
        raise CalibrationError(f"span {span} outside the plausible range")
    gain = round_div(vcal_q31 << Q_GAIN, span)
    return Coefficients(off, gain)


def apply(code: int, c: Coefficients) -> int:
    x = (int(code) << Q_OFFSET) - c.offset_q8
    y = round_div(x * c.gain_q29, 1 << Q_GAIN)
    return max(INT32_MIN, min(INT32_MAX, y))


def to_volts(y: int, full_scale_v: float) -> float:
    return y / 2 ** Q_OUT * full_scale_v
