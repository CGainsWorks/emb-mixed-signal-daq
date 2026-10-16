# Calibration procedure

What the firmware does, what a bench operator would do and what the
simulation stands in for. The arithmetic is in
[firmware/src/calibration.c](../firmware/src/calibration.c) and its
reference implementation
[host-tools/daqhost/calibration.py](../host-tools/daqhost/calibration.py).

## What is corrected

A two point system calibration per gain setting removes:

* offset of the gain stage and the converter, including anything the input
  selector adds, because the zero is taken with the input shorted at the
  connector side of the protection resistors;
* gain error from the E96 gain resistor, resistor tolerance and the
  reference's initial accuracy, because the reference point is a known
  external voltage.

It does not correct non-linearity, drift or anything that changes after
calibration.

## Sequence (one gain setting)

1. Select the gain and let the front end settle. The firmware discards the
   first four conversions after any change of input or gain, which is what
   a sinc4 decimator needs to flush.
2. **Zero.** Switch the input selector to *short*. Average N conversions
   (N = 64 in the simulation; more on the bench, see below) into a Q8 mean
   code, `offset_q8`.
3. **Reference.** Connect the calibrator to the reference connector, set it
   to 0.9 of full scale for the gain, then switch the input selector to
   *calibration reference*. Average N conversions, `ref_q8`.
4. The firmware computes `gain_q29 = round(Vcal_q31 * 2^29 / (ref_q8 -
   offset_q8))`, where `Vcal_q31` is the calibrator setting as a Q31 fraction
   of nominal full scale. It refuses a span outside half to twice the
   expected value, which catches a disconnected or wrong reference and a
   wrong gain.
5. Store the coefficients in a CRC protected record (one per gain) and send
   them to the host in a coefficients frame.
6. Switch back to the signal input.

Calibrated output is `(code * 256 - offset_q8) * gain_q29 / 2^29`, a Q31
fraction of the nominal full scale.

## Validation against a reference DMM

After calibration, at each of eleven points from -90 % to +90 % of full
scale:

1. Set the calibrator, wait for it to settle.
2. Read the input with the reference DMM, connected at the DAQ's input
   terminals (four wire sense if the calibrator has it).
3. Average N calibrated DAQ readings.
4. Error = (DAQ - DMM) / FSR, in ppm.

Pass if every point is within the target in [spec.md](spec.md). The
uncertainty of the check itself is the DMM's accuracy plus the calibrator's
stability over the test, which the report must state.

## Bench notes (not yet done)

* Use N of 1024 or more on the bench: drift and 1/f noise that the
  simulation does not have make short averages optimistic.
* Allow a warm-up of at least 30 minutes for the board and the instruments.
* Use low thermal EMF connections (copper to copper). At gain 1 they hardly
  matter; at gain 128 a thermocouple voltage of 1 uV is about 26 ppm of FSR.
* Calibrate at the operating temperature, or characterise the drift and
  repeat the calibration across it.

## What the simulation used

* A calibrator with an assumed accuracy of +/-2 ppm of setting.
* A DMM with an assumed accuracy of +/-3 ppm of reading +/-0.2 uV.
* Each instrument's error drawn once with a fixed seed and then held, which
  is how a real instrument behaves between its own calibrations.

The results are in
[test-results/calibration](../test-results/calibration) and the validation
report.
