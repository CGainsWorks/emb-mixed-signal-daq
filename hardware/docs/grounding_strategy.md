# Grounding strategy

Design intent for a layout that does not exist yet. Nothing here has been
checked on a board; it records the decisions the schematic and the noise
budget assume, so a layout can be reviewed against them.

## The aim

Keep return currents from the digital side (SPI, the microcontroller, the
switching supplies) out of the path between the sensor, the gain stage and
the converter inputs. The budget has no line for ground noise; a layout that
lets digital current flow under the front end would add one; it would be
the largest.

## Decisions

1. **One unbroken ground plane, partitioned by placement, not by cuts.** The
   converter's AVSS and DGND pins both go to the same plane directly under
   the part. Analogue parts sit on one side of the converter and digital
   parts on the other, so digital return currents, which follow the path of
   least inductance under their own traces, never cross the analogue area.
   A split plane would force the SPI return current around the gap and
   create the loop it is meant to prevent.
2. **The schematic keeps AGND and DGND as separate net names** so that the
   layout tool can show which pads belong to which side. They join at the
   converter and nowhere else on this page.
3. **Four layer stack: signal, ground, power, signal.** The ground plane is
   adjacent to the component side, so every front end trace has a return
   path directly beneath it.
4. **The input pair is routed as a pair, symmetric, short.** The EMI filter
   capacitors C1, C2 and C3 go at the connector side of the gain stage, with
   C1 and C2 returned to the same point so that any common mode current they
   shunt does not develop a differential voltage. Their tolerance matching
   sets common mode rejection at high frequency (not modelled; see
   STATUS.md).
5. **Gain resistors R7A to R7C sit at the multiplexer, with the multiplexer
   next to the amplifiers.** The inverting nodes are high impedance and the
   most sensitive nets on the board; they should be the shortest.
6. **Reference filter C7 at the converter's REFIN pins**, returned to the
   converter's AVSS pin, not to a general ground via.
7. **Guard the inputs at gain 128.** A guard ring driven at the input common
   mode around the input pair limits leakage from neighbouring nets; at
   gain 128 a leakage of 1 nA through the 674 ohm leg resistance is
   0.67 uV, comparable with the noise floor.
8. **Supplies arrive filtered.** +AVDD comes from a low noise analogue rail
   (the [emb-multirail-smps](https://github.com/CGainsWorks/emb-multirail-smps)
   power tree has one; its voltage has to suit the parts finally chosen)
   through a ferrite and local decoupling. The switching converters stay at
   the far edge of the board.

## To check on a real layout

* Return path of every SPI line drawn and confirmed not to pass under the
  front end.
* A shorted input noise measurement at every gain, compared with the budget.
  Excess at low gain points at the reference or the converter; excess at
  high gain points at the front end or ground noise.
* A noise spectrum with the digital interface idle and then streaming, to
  show the interface does not couple in.
