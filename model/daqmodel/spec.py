"""The written specification, as data.

Everything downstream reads its targets from here: the noise budget checks
itself against them, the behavioural converter is configured from them and
``docs/spec.md`` is generated from this file, so the document and the code
cannot disagree.

The order matters and follows the brief: the specification was fixed first
and the noise budget calculated against it second; only then were the
front end component values chosen. The targets below are requirements, not
results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Boltzmann constant, J/K (exact in the 2019 SI).
K_BOLTZMANN = 1.380649e-23

#: Every noise figure in this repository is evaluated at 27 degC, which is also
#: the default temperature of ngspice, so the Python budget and the SPICE deck
#: compute thermal noise at the same temperature without either needing a
#: special option.
TEMPERATURE_C = 27.0
TEMPERATURE_K = TEMPERATURE_C + 273.15

#: The four front end gain settings. Nominal values; the gain each one
#: actually achieves depends on the E96 resistor chosen for it (see
#: frontend.py) and the difference is removed by calibration.
GAINS = (1, 8, 32, 128)


@dataclass(frozen=True)
class Converter:
    """The 24-bit sigma-delta converter the front end drives."""

    bits: int = 24
    vref: float = 2.5                 # V, precision reference
    f_mod: float = 614_400.0          # Hz, modulator clock
    osr: int = 256                    # oversampling ratio, nominal setting
    sinc_order: int = 4               # decimation filter
    modulator_order: int = 4          # loop filter order
    ntf_out_of_band_gain: float = 1.5  # Lee criterion for a 1-bit quantiser
    #: Modulator input that corresponds to the reference voltage. The loop is
    #: stable to about 0.6 of the feedback level (checked by test), so full
    #: scale sits at 0.5 and leaves 20 percent over-range before overload.
    full_scale_level: float = 0.5

    @property
    def odr(self) -> float:
        """Output data rate, samples per second."""
        return self.f_mod / self.osr

    @property
    def lsb(self) -> float:
        """Weight of one output code at gain 1, volts."""
        return 2 * self.vref / 2 ** self.bits


@dataclass(frozen=True)
class Spec:
    """Requirements for the acquisition channel."""

    converter: Converter = field(default_factory=Converter)

    #: Signal bandwidth the channel must pass. The consumers are DC
    #: measurements (battery cells, bridges, shunts) and surface EMG, whose
    #: useful band ends at about 450 Hz.
    bandwidth_hz: float = 500.0
    #: Largest passband droop allowed at ``bandwidth_hz``, dB. The sinc4
    #: decimator is the only thing that droops in band.
    max_droop_db: float = 3.0

    #: Source the budget is written for: a 350 ohm full bridge, which looks
    #: like 175 ohm in each leg. Battery taps and shunts are lower, so this is
    #: the harder case.
    source_ohm_per_leg: float = 175.0

    #: Input referred noise targets, volts rms, at the nominal output data
    #: rate and over the full digital filter noise bandwidth. These were set
    #: before the budget was calculated, from what the two consuming projects
    #: need: about 22 effective bits on a 5 V span for cell voltages at gain 1,
    #: and well under a microvolt for bridges and sEMG at gain 128.
    noise_target_vrms: dict = field(default_factory=lambda: {
        1: 0.75e-6, 8: 0.40e-6, 32: 0.32e-6, 128: 0.30e-6})

    #: Integral non-linearity, best fit line, parts per million of FSR.
    inl_target_ppm_fsr: float = 5.0
    #: Sine performance at gain 1 and -1 dBFS. The three are set together:
    #: an INL of 5 ppm of FSR, if it were all a third order bow, would put the
    #: third harmonic near -110 dB, so the THD target follows from the INL
    #: target and the ENOB target follows from both. SNR is the noise only
    #: figure and is set from the gain 1 noise target and reference noise.
    snr_target_db: float = 120.0
    thd_target_db: float = -110.0
    #: Effective number of bits, (SINAD - 1.76) / 6.02, at -1 dBFS.
    enob_target_bits: float = 19.0
    #: Absolute error after a two point calibration, ppm of FSR, anywhere in
    #: the range, judged against the reference DMM.
    calibrated_error_target_ppm_fsr: float = 10.0
    #: Alias rejection the analogue filter must provide at the modulator
    #: clock, where the digital filter offers none.
    alias_rejection_target_db: float = 60.0

    def full_scale(self, gain: float) -> float:
        """Positive full scale differential input at ``gain``, volts."""
        return self.converter.vref / gain

    def fsr(self, gain: float) -> float:
        """Full scale range, peak to peak, volts."""
        return 2 * self.full_scale(gain)


SPEC = Spec()
