#!/usr/bin/env python3
"""Noise and sine analysis of a capture CSV written by capture.py.

    python host-tools/analyse.py capture.csv --gain 1 noise
    python host-tools/analyse.py capture.csv --gain 1 sine --cycles 67

``noise`` expects a shorted input record; ``sine`` a coherently sampled sine
with the given number of cycles in the record (IEEE 1241 methods, see
daqhost/metrics.py).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daqhost import metrics  # noqa: E402

VREF = 2.5


def load(path: str) -> list[float]:
    with open(path, encoding="utf-8") as h:
        return [float(r["volts"]) for r in csv.DictReader(h)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv")
    ap.add_argument("--gain", type=int, required=True, choices=(1, 8, 32, 128))
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("noise")
    s = sub.add_parser("sine")
    s.add_argument("--cycles", type=int, required=True)
    a = ap.parse_args(argv)

    v = load(a.csv)
    fsr = 2 * VREF / a.gain
    if a.mode == "noise":
        n = metrics.noise_floor(v, fsr)
        print(f"{len(v)} samples: {n.rms * 1e6:.4f} uV rms, {n.peak_to_peak * 1e6:.3f} uV p-p, "
              f"mean {n.mean * 1e6:.3f} uV")
        print(f"effective bits {n.effective_bits:.2f}, noise free bits {n.noise_free_bits:.2f}")
    else:
        m = metrics.sine_metrics(v, a.cycles, fsr)
        print(f"{len(v)} samples at {m.level_dbfs:.2f} dBFS")
        print(f"SNR {m.snr_db:.2f} dB, THD {m.thd_db:.2f} dB, SFDR {m.sfdr_db:.2f} dB, "
              f"SINAD {m.sinad_db:.2f} dB")
        print(f"ENOB {m.enob_sinad:.3f} bits, IEEE 1241 (FSR) {m.enob_ieee:.3f} bits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
