# Status

Last updated 16 October 2026. Everything in this repository is simulated:
there is no board, no bench and no reference instrument. The split below
follows the brief's build checklist.

## Complete (in simulation)

| Brief item | Where | How it is checked |
|---|---|---|
| Written specification: bandwidth, resolution, noise target | [docs/spec.md](docs/spec.md) | Generated from `model/daqmodel/spec.py`; every result is judged against it |
| Noise budget calculated before design | [hardware/docs/noise_budget.md](hardware/docs/noise_budget.md) | Closed form per contributor; ngspice agrees to 1 part in 10,000 at every gain (`scripts/run_ngspice.py`) |
| Analogue front end design | `model/daqmodel/frontend.py`, [hardware/spice](hardware/spice) | ngspice noise and AC analysis in CI |
| Schematic capture | [hardware/kicad](hardware/kicad), [PDF](hardware/outputs/schematic.pdf) | KiCad 8 ERC with no errors or warnings; connectivity parsed back and compared with the simulated netlist in the test suite |
| ADC SPI driver and sampling engine | [firmware](firmware) | Unit tests against a mocked AD7124-8 class device, with sanitisers; compiles for Cortex-M4F with `-Werror` (manual CI job) |
| First captures and sanity checks | `scripts/run_fil.py` | The firmware reads every code the converter model produces, bit for bit |
| Noise floor measurement | [test-results/noise-floor](test-results/noise-floor) | Within 15 percent of the budget at every gain |
| ENOB and SNR measurement | [test-results/enob-snr](test-results/enob-snr) | IEEE 1241 methods; SNR within 1.5 dB of the budget's prediction |
| Linearity measurement | [test-results/linearity](test-results/linearity) | Recovers the non-linearity the model was given |
| Calibration routine and coefficients | `firmware/src/calibration.c`, `host-tools/daqhost/calibration.py` | C and Python agree bit for bit; error after calibration within target at every gain |
| Validation against a reference DMM | [docs/validation_report.md](docs/validation_report.md) | Against a simulated DMM with stated, assumed accuracy |
| Host capture tool | [host-tools/capture.py](host-tools/capture.py) | Decodes the firmware's stream in the firmware in the loop run |
| Validation report | [docs/validation_report.md](docs/validation_report.md) | Generated; every number in it is reproduced by `make demo` |

## Not started

These need hardware or test gear and cannot be simulated honestly.

| Item | What it needs |
|---|---|
| Layout with grounding strategy and controlled impedance routing | A PCB layout. [grounding_strategy.md](hardware/docs/grounding_strategy.md) and [impedance_routing.md](hardware/docs/impedance_routing.md) are design intent only |
| Fabrication and assembly | Gerbers, a bill of materials with real part numbers for the amplifier, reference, multiplexer and input selector |
| Part selection against the noise allowances | Datasheets checked against the allowances in the budget: amplifier e_n 6 nV/rtHz and zero drift, converter 20 nV/rtHz, reference 20 nV/rtHz after filtering |
| Measured noise floor, ENOB, SNR and linearity | The board, a shorted input fixture, a low distortion source (or a filtered DAC) |
| Validation against a real reference DMM | A calibrated 8.5 digit DMM and a precision DC source; the procedure is in [calibration_procedure.md](docs/calibration_procedure.md) |
| Driver bring-up on a real AD7124-8 | The part, a logic analyser to confirm the SPI mode 3 timing, the reset delay and the ID value the driver accepts |
| STM32 board support | HAL glue for SPI, the DOUT/RDY interrupt, GPIO for the selectors and a UART or USB link; a linker script and startup code |
| Renode or QEMU run of the target image | The board support above; the brief lists it as optional |
| Temperature drift, CMRR and EMC | A thermal chamber, a common mode source and a pre-compliance setup |

## Known gaps in the model

* The converter model has no circuit level non-idealities (integrator
  leakage, capacitor mismatch, kickback, settling), no 1/f noise and no
  drift. Its INL is an assumption of about 1 ppm of FSR.
* The budget's 1-bit quantisation noise uses the linear model and is
  conservative: the simulated gain 1 noise floor is lower than the budget.
* Common mode rejection is not modelled at all; resistor mismatch in the
  input filter would convert common mode noise to differential and is the
  first thing a real board would show.
* The reference RC filter (R10, C7) is on the schematic but not in the SPICE
  deck; the budget treats the filtered reference noise as an allowance.

## Reproducibility

The simulation is built to be bit reproducible (no transcendental functions
upstream of the modulator, exact integer decimation). On 16 October 2026 the
generated outputs were byte identical between Windows with numpy 1.26 and
Linux with numpy 2.5. CI still compares them to a tolerance, because the FFT
and least squares fits in the analysis are not guaranteed bit identical
across library builds.
