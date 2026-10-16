#!/usr/bin/env python3
"""Host capture tool: decode the firmware's framed stream into a dataset.

Reads a binary stream from a file (a recording, or the firmware in the loop
output) or, with --serial, from a serial port if pyserial is installed.
Writes one CSV row per sample and prints what the link delivered: frames,
CRC errors, sequence gaps and the device's own counters, because a capture
that silently lost samples would give wrong noise figures.

    python host-tools/capture.py STREAM.bin --gain 1 --out capture.csv
    python host-tools/capture.py --serial /dev/ttyACM0 --seconds 10 --gain 128 --out cap.csv

The serial path is untested: there is no board to talk to (see STATUS.md).
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daqhost import framing  # noqa: E402
from daqhost.calibration import to_volts  # noqa: E402

VREF = 2.5


@dataclass
class Capture:
    calibrated: list = field(default_factory=list)   # Q31 of full scale
    raw: list = field(default_factory=list)          # signed codes
    coeffs: list = field(default_factory=list)       # (gain_index, offset_q8, gain_q29)
    status: list | None = None
    stats: framing.DecodeStats | None = None


def parse(stream: bytes) -> Capture:
    frames, stats = framing.decode(stream)
    cap = Capture(stats=stats)
    for f in frames:
        if f.ftype == framing.FRAME_SAMPLES:
            cap.calibrated += f.words
        elif f.ftype == framing.FRAME_RAW:
            cap.raw += f.words
        elif f.ftype == framing.FRAME_COEFFS and len(f.words) == 5:
            w = [x & 0xFFFFFFFF for x in f.words]
            off = (w[1] << 32 | w[0])
            gain = (w[3] << 32 | w[2])
            off -= (1 << 64) if off >= 1 << 63 else 0
            gain -= (1 << 64) if gain >= 1 << 63 else 0
            cap.coeffs.append((f.words[4], off, gain))
        elif f.ftype == framing.FRAME_STATUS:
            cap.status = f.words
    return cap


def read_serial(port: str, seconds: float) -> bytes:
    try:
        import serial  # type: ignore
    except ImportError:
        raise SystemExit("--serial needs pyserial: pip install pyserial")
    import time
    data = bytearray()
    with serial.Serial(port, 921600, timeout=0.1) as s:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            data += s.read(4096)
    return bytes(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stream", nargs="?", help="binary stream file")
    ap.add_argument("--serial", help="serial port to capture from instead")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--gain", type=int, required=True, choices=(1, 8, 32, 128),
                    help="nominal gain the stream was captured at")
    ap.add_argument("--out", required=True, help="CSV to write")
    a = ap.parse_args(argv)
    if bool(a.stream) == bool(a.serial):
        ap.error("give a stream file or --serial, not both")

    data = Path(a.stream).read_bytes() if a.stream else read_serial(a.serial, a.seconds)
    cap = parse(data)
    fs = VREF / a.gain
    with open(a.out, "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h, lineterminator="\n")
        w.writerow(["index", "calibrated_q31", "volts", "raw_code"])
        for i, y in enumerate(cap.calibrated):
            raw = cap.raw[i] if i < len(cap.raw) else ""
            w.writerow([i, y, f"{to_volts(y, fs):.10f}", raw])

    st = cap.stats
    print(f"frames {st.frames}, CRC errors {st.crc_errors}, sequence gaps "
          f"{st.sequence_gaps}, bytes skipped {st.bytes_skipped}")
    print(f"samples {len(cap.calibrated)} calibrated, {len(cap.raw)} raw")
    for gi, off, gain in cap.coeffs:
        print(f"coefficients: gain index {gi}, offset_q8 {off}, gain_q29 {gain}")
    if cap.status:
        names = ("produced", "overflows", "device errors", "bus errors", "timeouts")
        print("device: " + ", ".join(f"{n} {v}" for n, v in zip(names, cap.status)))
    bad = st.crc_errors or st.sequence_gaps or (cap.status and any(cap.status[1:]))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
