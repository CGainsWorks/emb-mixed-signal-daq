"""The host link frame format, decoder side.

Mirrors ``firmware/src/host_link.c``. One frame::

    offset  size  field
    0       2     sync, 0xA5 0x5A
    2       1     type (FRAME_* below)
    3       2     sequence number, little endian, increments per frame
    5       1     payload word count n (0 to 64)
    6       4n    payload, n little endian int32 words
    6+4n    2     CRC-16/CCITT-FALSE over bytes 2 .. 5+4n, little endian

The decoder resynchronises on the sync bytes, so a corrupted or truncated
frame costs that frame and nothing after it. Every dropped frame and every
gap in the sequence numbers is counted, because a capture that silently lost
data would produce wrong noise figures.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

SYNC = b"\xA5\x5A"
FRAME_SAMPLES = 0x01      # calibrated samples, Q31 of full scale
FRAME_RAW = 0x02          # raw 24-bit codes, sign extended
FRAME_COEFFS = 0x03       # offset_q8, gain_q29, gain index, status
FRAME_STATUS = 0x04       # counters: produced, overflows, errors, timeouts
MAX_WORDS = 64


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def encode(ftype: int, seq: int, words) -> bytes:
    words = list(words)
    if len(words) > MAX_WORDS:
        raise ValueError("too many words for one frame")
    body = struct.pack("<BHB", ftype, seq & 0xFFFF, len(words))
    body += struct.pack(f"<{len(words)}i", *words)
    return SYNC + body + struct.pack("<H", crc16_ccitt(body))


@dataclass
class Frame:
    ftype: int
    seq: int
    words: list


@dataclass
class DecodeStats:
    frames: int = 0
    crc_errors: int = 0
    sequence_gaps: int = 0
    bytes_skipped: int = 0
    by_type: dict = field(default_factory=dict)


def decode(stream: bytes) -> tuple[list[Frame], DecodeStats]:
    frames: list[Frame] = []
    st = DecodeStats()
    i = 0
    last_seq = None
    n = len(stream)
    while i < n:
        j = stream.find(SYNC, i)
        if j < 0:
            st.bytes_skipped += n - i
            break
        st.bytes_skipped += j - i
        if j + 6 > n:
            st.bytes_skipped += n - j
            break
        ftype, seq, count = struct.unpack_from("<BHB", stream, j + 2)
        end = j + 6 + 4 * count + 2
        if count > MAX_WORDS or end > n:
            st.bytes_skipped += 1
            i = j + 1
            continue
        body = stream[j + 2:j + 6 + 4 * count]
        (crc,) = struct.unpack_from("<H", stream, end - 2)
        if crc != crc16_ccitt(body):
            st.crc_errors += 1
            i = j + 1
            continue
        words = list(struct.unpack_from(f"<{count}i", stream, j + 6))
        if last_seq is not None and seq != (last_seq + 1) & 0xFFFF:
            st.sequence_gaps += 1
        last_seq = seq
        frames.append(Frame(ftype, seq, words))
        st.frames += 1
        st.by_type[ftype] = st.by_type.get(ftype, 0) + 1
        i = end
    return frames, st
