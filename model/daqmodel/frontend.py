"""The analogue front end: topology and component values.

Signal path, one differential channel::

    source --R_src--+--R_prot--+-- in_p --[A1, gain stage]-- out_p --R_aa--+-- ainp
    (bridge)        |          |                |                          |
                    |        C_cm             R_f                      C_aa_cm
                    |          |                +-- R_G (switched) --+     |
                    |        C_diff             |                    |   C_aa_diff
                    |          |              R_f                    |     |
    source --R_src--+--R_prot--+-- in_n --[A2, gain stage]-- out_n --R_aa--+-- ainm

The first stage of a three op-amp instrumentation amplifier, with no
difference amplifier after it. The converter has a differential input, so
it rejects the common mode itself and the difference stage would add four
resistors and a third amplifier of noise for nothing. Gain is switched by
selecting one of four R_G values.

This module is the single description of the circuit. The noise budget, the
ngspice deck and the KiCad schematic are all generated from :func:`netlist`,
so they describe the same circuit by construction.

Amplifier and converter noise figures are *allowances*: what the budget
permits each part to contribute. Part selection then has to meet them. They
are not quoted from any datasheet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .spec import GAINS, SPEC

#: E96 resistor chosen for each gain. None means R_G is open (unity gain).
R_G_E96 = {1: None, 8: 715.0, 32: 162.0, 128: 39.2}


@dataclass(frozen=True)
class FrontEnd:
    r_src: float = SPEC.source_ohm_per_leg   # sensor, per leg (budget case)
    r_prot: float = 499.0     # input protection, limits clamp current
    c_cm: float = 1e-9        # EMI filter, each leg to AGND
    c_diff: float = 10e-9     # EMI filter, across the pair
    r_f: float = 2490.0       # gain stage feedback, each amplifier
    r_g: dict = field(default_factory=lambda: dict(R_G_E96))
    r_aa: float = 499.0       # anti-alias filter, each leg
    c_aa_cm: float = 1e-9
    c_aa_diff: float = 10e-9

    # Noise allowances, all white. The gain stage amplifiers are assumed to be
    # zero drift (chopper stabilised) parts, which is why no 1/f term appears:
    # their flicker noise is modulated out of band. That assumption is the
    # first thing to confirm against a real datasheet.
    en_amp: float = 6e-9      # V/rtHz, each gain stage amplifier
    in_amp: float = 0.3e-12   # A/rtHz, each gain stage amplifier
    en_adc: float = 20e-9     # V/rtHz, converter, referred to its input
    en_ref: float = 20e-9     # V/rtHz, reference after its RC filter

    def gain(self, nominal: int) -> float:
        """Gain the chosen resistors actually achieve at a nominal setting."""
        rg = self.r_g[nominal]
        return 1.0 if rg is None else 1.0 + 2.0 * self.r_f / rg

    @property
    def r_leg(self) -> float:
        """Total series resistance in each input leg."""
        return self.r_src + self.r_prot

    @property
    def f_input_pole(self) -> float:
        """Differential pole of the EMI filter with the budget source, Hz."""
        from math import pi
        return 1.0 / (2 * pi * self.r_leg * (self.c_cm + 2 * self.c_diff))

    @property
    def f_aa_pole(self) -> float:
        """Differential pole of the anti-alias filter, Hz."""
        from math import pi
        return 1.0 / (2 * pi * self.r_aa * (self.c_aa_cm + 2 * self.c_aa_diff))


FRONT_END = FrontEnd()


@dataclass(frozen=True)
class Part:
    """One component: reference, kind, value and the nets on its pins."""

    ref: str
    kind: str          # R, C, OPAMP, VSRC
    value: float | str
    nets: tuple        # pin order: R/C (1, 2); OPAMP (+, -, out); VSRC (+, -)
    note: str = ""


def netlist(gain: int, fe: FrontEnd = FRONT_END) -> list[Part]:
    """The circuit at one gain setting, in a form every generator can read.

    Net names are the ones used in the SPICE deck and as KiCad labels.
    ``0`` is analogue ground. The source is ideal: in noise analysis it is an
    AC short and the sensor's own thermal noise is carried by R1 and R2.
    """
    if gain not in GAINS:
        raise ValueError(f"gain must be one of {GAINS}")
    parts = [
        Part("VSIG", "VSRC", "AC 1", ("src_p", "src_n"), "differential test source"),
        Part("R1", "R", fe.r_src, ("src_p", "a_p"), "sensor, budget case"),
        Part("R2", "R", fe.r_src, ("src_n", "a_n"), "sensor, budget case"),
        Part("R3", "R", fe.r_prot, ("a_p", "in_p"), "input protection"),
        Part("R4", "R", fe.r_prot, ("a_n", "in_n"), "input protection"),
        Part("C1", "C", fe.c_cm, ("in_p", "0"), "EMI filter, common mode"),
        Part("C2", "C", fe.c_cm, ("in_n", "0"), "EMI filter, common mode"),
        Part("C3", "C", fe.c_diff, ("in_p", "in_n"), "EMI filter, differential"),
        Part("U1A", "OPAMP", "zero drift", ("in_p", "fb_p", "out_p"), "gain stage"),
        Part("U1B", "OPAMP", "zero drift", ("in_n", "fb_n", "out_n"), "gain stage"),
        Part("R5", "R", fe.r_f, ("out_p", "fb_p"), "feedback"),
        Part("R6", "R", fe.r_f, ("out_n", "fb_n"), "feedback"),
        Part("R8", "R", fe.r_aa, ("out_p", "ainp"), "anti-alias"),
        Part("R9", "R", fe.r_aa, ("out_n", "ainm"), "anti-alias"),
        Part("C4", "C", fe.c_aa_cm, ("ainp", "0"), "anti-alias, common mode"),
        Part("C5", "C", fe.c_aa_cm, ("ainm", "0"), "anti-alias, common mode"),
        Part("C6", "C", fe.c_aa_diff, ("ainp", "ainm"), "anti-alias, differential"),
    ]
    rg = fe.r_g[gain]
    if rg is not None:
        parts.insert(12, Part("R7", "R", rg, ("fb_p", "fb_n"), f"gain set, G={gain}"))
    return parts
