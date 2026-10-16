#!/usr/bin/env python3
"""Firmware in the loop: the C firmware against the behavioural converter.

For each gain in the run, the firmware (built for the host as
firmware/build/daq_sim) starts the mocked converter, calibrates it from the
shorted and reference inputs and streams the signal input, all from codes
the behavioural model produced. Its framed output is decoded by the host
capture tool and checked:

* the link: no CRC errors, no sequence gaps, no overflows;
* the raw codes the firmware read over the mocked SPI bus equal the codes
  the model produced, every one;
* the calibration coefficients the C code computed equal the Python
  reference implementation's, bit for bit;
* every calibrated sample equals the Python reference's;
* the ENOB measured on the firmware's calibrated output.

Run scripts/run_all.py first (it writes the inputs to build/fil) and
``make -C firmware sim``. Writes test-results/calibration/firmware_in_loop.csv.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host-tools"))
sys.path.insert(0, str(ROOT / "model"))

import capture  # noqa: E402
from daqhost import calibration as cal  # noqa: E402
from daqhost import metrics  # noqa: E402
from daqmodel.io import write_csv  # noqa: E402

SIM = ROOT / "firmware" / "build" / "daq_sim"
FIL = ROOT / "build" / "fil"
GAINS = (1, 8, 32, 128)
SETTLE = 4


def codes(path: Path) -> list[int]:
    return [int(x) for x in path.read_text().split()]


def run_one(g: int) -> tuple[list, list]:
    gi, vcal_nv, n_avg, cycles = (int(x) for x in (FIL / f"g{g}_meta.txt").read_text().split())
    zero, ref, sig = (codes(FIL / f"g{g}_{n}.txt") for n in ("zero", "cal", "signal"))
    out = FIL / f"g{g}_stream.bin"
    r = subprocess.run([str(SIM), str(gi), str(vcal_nv), str(n_avg),
                        str(FIL / f"g{g}_zero.txt"), str(FIL / f"g{g}_cal.txt"),
                        str(FIL / f"g{g}_signal.txt"), str(out)],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"daq_sim failed at gain {g}")

    cap = capture.parse(out.read_bytes())
    fs_nv = 2_500_000_000 // g
    ref_coeffs = cal.compute(zero[SETTLE:SETTLE + n_avg], ref[SETTLE:SETTLE + n_avg],
                             vcal_nv, fs_nv)
    expect = [cal.apply(c, ref_coeffs) for c in sig]
    (_, off, gain), = cap.coeffs
    st = cap.stats

    problems = []
    if st.crc_errors or st.sequence_gaps or st.bytes_skipped:
        problems.append(f"link: {st}")
    if cap.status is None or any(cap.status[1:]):
        problems.append(f"device counters {cap.status}")
    if cap.raw != sig:
        problems.append("raw codes differ from the model's")
    if (off, gain) != (ref_coeffs.offset_q8, ref_coeffs.gain_q29):
        problems.append(f"coefficients {(off, gain)} != {ref_coeffs}")
    mismatched = sum(a != b for a, b in zip(cap.calibrated, expect))
    if len(cap.calibrated) != len(expect) or mismatched:
        problems.append(f"{mismatched} calibrated samples differ")
    for p in problems:
        print(f"  gain {g}: {p}", file=sys.stderr)

    volts = [cal.to_volts(y, 2.5 / g) for y in cap.calibrated]
    m = metrics.sine_metrics(volts, cycles, 5.0 / g)
    row = [g, len(cap.calibrated), st.frames, st.crc_errors, st.sequence_gaps,
           "yes" if cap.raw == sig else "no",
           "yes" if (off, gain) == (ref_coeffs.offset_q8, ref_coeffs.gain_q29) else "no",
           f"{len(expect) - mismatched}/{len(expect)}",
           off, gain, f"{m.snr_db:.3f}", f"{m.enob_sinad:.3f}"]
    return row, problems


def main() -> int:
    if not SIM.exists():
        raise SystemExit("build the simulator first: make -C firmware sim")
    rows, problems = [], []
    for g in GAINS:
        if (FIL / f"g{g}_meta.txt").exists():
            row, p = run_one(g)
            rows.append(row)
            problems += p
    if not rows:
        raise SystemExit("no inputs in build/fil: run scripts/run_all.py first")
    write_csv("test-results/calibration/firmware_in_loop.csv",
              ["gain", "samples", "frames", "crc_errors", "sequence_gaps",
               "raw_codes_match_model", "coefficients_match_python",
               "calibrated_samples_match_python", "offset_q8", "gain_q29",
               "snr_dB_firmware_output", "enob_bits_firmware_output"], rows)
    if problems:
        print("FAILED", file=sys.stderr)
        return 1
    print("firmware in the loop: every sample and coefficient matches the reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
