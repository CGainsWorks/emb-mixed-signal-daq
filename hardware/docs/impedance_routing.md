# Controlled impedance routing notes

Design intent; no layout exists. The brief asks for controlled impedance
routing, so this note records where it is needed on this board and where it
is not and why.

## Where it matters

Nothing on this board is fast in the radio frequency sense. The analogue
signals are below 1 kHz and the fastest clock is the SPI clock, a few MHz.
What decides whether a trace needs to be treated as a transmission line is
the **edge rate**, not the clock rate. A rule of thumb: a trace longer than
about one sixth of the distance an edge travels during its rise time should
be terminated or impedance controlled.

With an assumed microcontroller output rise time of 2 ns (a GPIO speed
setting, to be confirmed against the chosen part) and a signal speed on
FR-4 of about 15 cm/ns, that distance is about 5 cm. So:

* **SPI lines (SCLK, DIN, DOUT/RDY, CS) longer than about 5 cm** get a
  series termination resistor at the driver (22 to 33 ohm, to be tuned on the
  board) and are routed over unbroken ground as 50 ohm single ended traces.
  Ringing on SCLK is the classic cause of double clocking in an SPI
  converter; it is cheap to prevent.
* Better still, keep the converter within 5 cm of the microcontroller, or
  run the link at a slower edge rate setting, which also reduces the energy
  coupled into the front end.

## Where it does not

* **The analogue input pair and the gain stage** are low frequency and high
  impedance. What matters there is symmetry, short length and guarding, not
  characteristic impedance. See [grounding_strategy.md](grounding_strategy.md).
* **The reference** is DC; its trace wants low resistance and a short return.

## What a layout would need to specify

* The stack-up, with the dielectric thickness the fabricator quotes.
* The trace width for 50 ohm on the outer layers, from the fabricator's own
  calculator rather than a generic one.
* Which nets carry the 50 ohm constraint (the SPI group only, if longer than
  the limit above).
* Length matching is not needed: SPI timing at a few MHz has margins of tens
  of nanoseconds.

None of the figures above has been measured; the rise time and the signal
speed are assumptions, labelled as such.
